"""Run the dashboard on localhost: python -m nse_ranker serve

Serves dashboard/index.html with a local stand-in for the online dashboard's functions
(dashboard/local.js and local.css), and the data files `export` wrote to reports/dashboard/.
"""
import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .export import OUT_DIR

DASHBOARD_DIR = Path(__file__).parent.parent / "dashboard"
D3 = "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"
DATA_NAMES = {"ranking", "prices", "news", "articles", "posts", "stats", "not_ranked", "method", "stocks"}


def page(title="NSE Watchlist Ranking (local)"):
    """The dashboard page wrapped in a full HTML document for the browser."""
    body = (DASHBOARD_DIR / "index.html").read_text(encoding="utf-8")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="A research ranking of Nairobi Securities Exchange stocks. Not financial advice.">
<title>{title}</title>
<link rel="stylesheet" href="/local.css">
<script src="{D3}"></script>
<script src="/local.js"></script>
</head>
<body>
<div id="dash-root">
<p id="local-status"></p>
{body}
</div>
</body>
</html>"""


class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0].split("#")[0]
        if path in ("/", "/index.html"):
            return self._send(200, "text/html; charset=utf-8", page().encode("utf-8"))
        if path in ("/local.js", "/local.css"):
            kind = "text/javascript" if path.endswith(".js") else "text/css"
            return self._send(200, f"{kind}; charset=utf-8", (DASHBOARD_DIR / path[1:]).read_bytes())
        if path.startswith("/data/") and path.endswith(".json"):
            name = path[len("/data/"):-len(".json")]
            file = OUT_DIR / f"{name}.json"
            if name in DATA_NAMES and file.exists():
                return self._send(200, "application/json; charset=utf-8", file.read_bytes())
            return self._send(404, "text/plain; charset=utf-8",
                              f"No {name}.json yet: run python -m nse_ranker export".encode("utf-8"))
        return self._send(404, "text/plain; charset=utf-8", b"Not found")

    def _send(self, status, kind, body):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):   # keep the terminal quiet
        pass


def run(port=8000):
    stamp = OUT_DIR / "export.json"
    exported = json.loads(stamp.read_text())["exported"] if stamp.exists() else "never (run export first)"
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Dashboard on http://localhost:{port}  (data exported {exported}). Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
