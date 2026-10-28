"""Build the dashboard as a static website (site/) and deploy it to Netlify.

The site is the same page as `serve`, with the exported data files beside it, so it shows the
data as of the last `export`. Run `python -m nse_ranker site --deploy` after each export to update it.
"""
import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import serve
from .export import OUT_DIR

SITE_DIR = OUT_DIR.parent.parent / "site"


def build(site_dir=SITE_DIR):
    """Write index.html, the local scripts and data/*.json into site_dir. Returns the files written."""
    if site_dir.exists():
        shutil.rmtree(site_dir)
    (site_dir / "data").mkdir(parents=True)
    (site_dir / "index.html").write_text(serve.page("NSE Watchlist"), encoding="utf-8")
    for name in ("local.js", "local.css"):
        shutil.copy(serve.DASHBOARD_DIR / name, site_dir / name)
    missing = []
    for name in sorted(serve.DATA_NAMES):
        source = OUT_DIR / f"{name}.json"
        if source.exists():
            shutil.copy(source, site_dir / "data" / f"{name}.json")
        else:
            missing.append(name)
    if missing:
        raise RuntimeError(f"Missing export files: {', '.join(missing)}. Run python -m nse_ranker export first.")
    # Data changes with every export, so browsers should always check for a newer copy.
    (site_dir / "_headers").write_text("/data/*\n  Cache-Control: no-cache\n/\n  Cache-Control: no-cache\n")
    return sorted(p.relative_to(site_dir).as_posix() for p in site_dir.rglob("*") if p.is_file())


def deploy(site_dir=SITE_DIR):
    """Deploy site_dir to production through Netlify's API. Returns the live URL.

    Uses the API directly, because the CLI reports refusals as a bare "Forbidden" while the API says why
    (e.g. "Account credit usage exceeded"): send every file's SHA-1, upload only the ones Netlify asks for,
    then wait until the deploy is live. The login is the one the Netlify CLI saved; it's never printed.
    """
    site_id = json.loads((site_dir.parent / ".netlify" / "state.json").read_text())["siteId"]
    token = _token()
    files = {f"/{p.relative_to(site_dir).as_posix()}": p for p in site_dir.rglob("*") if p.is_file()}
    digests = {path: hashlib.sha1(p.read_bytes()).hexdigest() for path, p in files.items()}
    created = _api("POST", f"/sites/{site_id}/deploys", token,
                   json.dumps({"files": digests, "title": "nse-ranker export"}).encode(), "application/json")
    needed = set(created.get("required", []))
    for path, p in files.items():
        if digests[path] in needed:
            _api("PUT", f"/deploys/{created['id']}/files{urllib.parse.quote(path)}", token,
                 p.read_bytes(), "application/octet-stream")
    for _ in range(60):
        state = _api("GET", f"/deploys/{created['id']}", token)
        if state["state"] == "ready":
            return state.get("ssl_url") or state.get("url")
        if state["state"] == "error":
            raise RuntimeError(f"Netlify deploy failed: {state.get('error_message')}")
        time.sleep(2)
    raise RuntimeError(f"Netlify deploy {created['id']} wasn't ready after two minutes")


def _token():
    """NETLIFY_AUTH_TOKEN if set, else the login the Netlify CLI saved."""
    if os.environ.get("NETLIFY_AUTH_TOKEN"):
        return os.environ["NETLIFY_AUTH_TOKEN"]
    config = Path(os.environ.get("APPDATA", Path.home())) / "netlify" / "Config" / "config.json"
    if config.exists():
        saved = json.loads(config.read_text(encoding="utf-8"))
        user = saved.get("users", {}).get(saved.get("userId"), {})
        if (user.get("auth") or {}).get("token"):
            return user["auth"]["token"]
    raise RuntimeError("No Netlify login found: run `netlify login` once, or set NETLIFY_AUTH_TOKEN.")


def _api(method, path, token, body=None, kind=None):
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "nse-ranker"}
    if kind:
        headers["Content-Type"] = kind
    request = urllib.request.Request(f"https://api.netlify.com/api/v1{path}", data=body, method=method,
                                     headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            text = response.read()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Netlify {method} {path.split('/files')[0]} failed: HTTP {error.code} "
                           f"{error.read()[:200]!r}") from error
    return json.loads(text) if text else {}
