"""Small HTTP helper: honest User-Agent, timeout, and a pause between requests."""
import json
import time
import urllib.error
import urllib.request

USER_AGENT = "nse-ranker/0.1 (personal research tool; +https://github.com/ryanreo/nse-ranker)"
_last_request = 0.0


def get(url, delay=2.0, timeout=60):
    """Fetch a URL and return its bytes, or None on 404.

    Waits so requests are at least `delay` seconds apart, to go easy on the sites.
    """
    global _last_request
    wait = _last_request + delay - time.monotonic()
    if wait > 0:
        time.sleep(wait)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise
    finally:
        _last_request = time.monotonic()


def send(method, url, body=None, headers=None, timeout=120):
    """Send JSON (POST, PATCH, DELETE...) and return the response bytes. Raises on HTTP errors,
    with the server's message included."""
    data = None if body is None else json.dumps(body, ensure_ascii=False, default=str).encode("utf-8")
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"User-Agent": USER_AGENT, "Content-Type": "application/json",
                                              **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{method} {url.split('?')[0]} failed: HTTP {error.code} {error.read()[:300]!r}") from error
