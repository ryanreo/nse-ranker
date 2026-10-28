"""Build the dashboard as a static website (site/) and deploy it to Netlify.

The site is the same page as `serve`, with the exported data files beside it, so it shows the
data as of the last `export`. Run `python -m nse_ranker site --deploy` after each export to update it.
"""
import re
import shutil
import subprocess

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


def deploy(site_dir=SITE_DIR, run=subprocess.run):
    """Deploy site_dir to the Netlify site this folder is linked to (production). Returns the live URL."""
    netlify = shutil.which("netlify")
    if not netlify:
        raise RuntimeError("The Netlify CLI isn't installed: npm install -g netlify-cli")
    done = run([netlify, "deploy", "--prod", "--dir", str(site_dir), "--message", "nse-ranker export"],
               cwd=site_dir.parent, capture_output=True, text=True, encoding="utf-8", timeout=600)
    if done.returncode != 0:
        raise RuntimeError(f"Netlify deploy failed: {(done.stderr or done.stdout).strip()[-400:]}")
    # The CLI's output has decorations Windows' console can't print; keep just the site address.
    urls = re.findall(r"https://[\w.-]+\.netlify\.app", done.stdout)
    return min(urls, key=len) if urls else "deployed (no URL in Netlify's reply)"
