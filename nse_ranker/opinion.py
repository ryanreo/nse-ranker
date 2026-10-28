"""Online opinion from Reddit and X, summarised by Haiku. The lowest-weight factor (3 points).

- X: Agent-Reach's `twitter` CLI. Needs TWITTER_AUTH_TOKEN and TWITTER_CT0 in .env, exported by you
  from your own logged-in x.com session. They're passed to the CLI and never printed.
- Reddit: OpenCLI (`opencli reddit search`), which reads through your logged-in Chrome. Needs the
  OpenCLI extension connected.
If a source isn't set up, it's skipped and the run says so.
"""
import json
import os
import shutil
import subprocess
from datetime import date, timedelta

from . import haiku
from .sources.eodhd import ENV_FILE

DAYS = 30
MAX_POSTS = 15          # per source per stock
MIN_POSTS = 2           # fewer than this: no opinion score
HYPE_DISCOUNT = 0.5     # hype or promotion counts half

SCHEMA = """
CREATE TABLE IF NOT EXISTS opinions (
    ticker    TEXT NOT NULL,
    date      TEXT NOT NULL,
    posts     INTEGER NOT NULL,
    sentiment REAL NOT NULL,      -- -1 negative .. +1 positive
    hype      INTEGER NOT NULL,   -- 1 if it reads like hype or paid promotion
    summary   TEXT NOT NULL,
    quotes    TEXT NOT NULL,      -- JSON list of {quote, url}
    PRIMARY KEY (ticker, date)
);
"""

INSTRUCTIONS = """You summarise what people on Reddit and X say about one stock on the Nairobi Securities Exchange.
The input has the stock and a list of posts. Judge only the posts' content.
sentiment: -1 (clearly negative about owning the stock) to 1 (clearly positive); 0 if mixed or off-topic.
hype: true if the positive posts read like hype, promotion, paid signals, WhatsApp/Telegram group adverts
or "guaranteed returns". summary: two sentences on what people are saying and why.
quotes: up to 3 short phrases copied exactly from the posts, with the post number.
Ignore posts that aren't about this company. This is research, not investment advice."""

OPINION_SCHEMA = {
    "type": "object",
    "properties": {
        "sentiment": {"type": "number", "minimum": -1, "maximum": 1},
        "hype": {"type": "boolean"},
        "summary": {"type": "string"},
        "quotes": {"type": "array", "items": {
            "type": "object",
            "properties": {"post": {"type": "integer"}, "quote": {"type": "string"}},
            "required": ["post", "quote"]}},
    },
    "required": ["sentiment", "hype", "summary", "quotes"],
}


def _env(path=ENV_FILE):
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            name, _, value = line.partition("=")
            if value.strip():
                values[name.strip()] = value.strip()
    return values


def _first(item, *keys):
    """The first non-empty value among several possible field names."""
    for key in keys:
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("screen_name") or value.get("username") or value.get("name")
        if value:
            return str(value)
    return ""


def _items(output):
    """CLI JSON can be a list, or {"data": [...]} / {"items": [...]}."""
    data = json.loads(output)
    if isinstance(data, dict):
        if data.get("ok") is False:
            raise RuntimeError((data.get("error") or {}).get("message", "failed"))
        data = data.get("data") or data.get("items") or data.get("results") or []
    return data if isinstance(data, list) else []


def query(stock):
    """Search words: the stock's main name plus words that keep it about the shares."""
    name = (stock.get("aliases") or [stock["name"]])[0]
    return f'"{name}" (shares OR stock OR NSE OR dividend)'


# ---- Sources. Each returns (posts, problem): problem is None if the source worked. ----

def from_x(stock, run=subprocess.run):
    env = _env()
    token, ct0 = env.get("TWITTER_AUTH_TOKEN"), env.get("TWITTER_CT0")
    if not (token and ct0):
        return [], "X not set up: add TWITTER_AUTH_TOKEN and TWITTER_CT0 to .env"
    if not shutil.which("twitter"):
        return [], "X not set up: the `twitter` command (Agent-Reach) isn't on PATH"
    since = (date.today() - timedelta(days=DAYS)).isoformat()
    done = run(["twitter", "search", query(stock), "--type", "latest", "--since", since,
                "-n", str(MAX_POSTS), "--json"],
               capture_output=True, text=True, encoding="utf-8", timeout=120,
               env=dict(os.environ, TWITTER_AUTH_TOKEN=token, TWITTER_CT0=ct0))
    try:
        items = _items(done.stdout)
    except (ValueError, RuntimeError) as error:
        return [], f"X search failed: {str(error)[:120]}"
    posts = []
    for item in items:
        text = _first(item, "text", "full_text", "content")
        if text:
            author = _first(item, "author", "user", "screen_name", "username")
            tweet_id = _first(item, "id", "id_str", "rest_id")
            url = _first(item, "url", "link") or (f"https://x.com/{author}/status/{tweet_id}" if tweet_id else "")
            posts.append({"platform": "X", "author": author, "text": text, "url": url})
    return posts, None


def from_reddit(stock, run=subprocess.run):
    if not shutil.which("opencli"):
        return [], "Reddit not set up: the `opencli` command isn't on PATH"
    name = (stock.get("aliases") or [stock["name"]])[0]
    done = run(["opencli", "reddit", "search", f'"{name}"', "--time", "month", "--sort", "new",
                "--limit", str(MAX_POSTS), "-f", "json"],
               capture_output=True, text=True, encoding="utf-8", timeout=120)
    if done.returncode != 0:
        detail = "connect the OpenCLI extension in Chrome" if "BROWSER_CONNECT" in (done.stdout + done.stderr) \
            else (done.stderr or done.stdout)[:120]
        return [], f"Reddit not available: {detail}"
    try:
        items = _items(done.stdout)
    except (ValueError, RuntimeError) as error:
        return [], f"Reddit search failed: {str(error)[:120]}"
    posts = []
    for item in items:
        text = " ".join(filter(None, [_first(item, "title"), _first(item, "selftext", "body", "text", "content")]))
        if text:
            posts.append({"platform": "Reddit", "author": _first(item, "author", "subreddit"),
                          "text": text, "url": _first(item, "url", "permalink", "link")})
    return posts, None


SOURCES = {"X": from_x, "Reddit": from_reddit}


# ---- Summarising and scoring ----

def summarise(stock, posts, ask=haiku.ask):
    """Haiku's read of the posts, with quotes checked against the posts. None if nothing usable."""
    data = {"stock": {"ticker": stock["ticker"], "name": stock["name"]},
            "posts": [{"post": i, "platform": p["platform"], "text": p["text"][:1000]} for i, p in enumerate(posts)]}
    answer = ask(INSTRUCTIONS, data, OPINION_SCHEMA)
    quotes = [{"quote": q["quote"], "url": posts[q["post"]]["url"]} for q in answer["quotes"]
              if 0 <= q["post"] < len(posts) and q["quote"].strip()
              and q["quote"].strip().lower() in posts[q["post"]]["text"].lower()]
    if not quotes:   # Haiku couldn't point at real words, so don't trust the reading
        return None
    return {"sentiment": max(-1.0, min(1.0, answer["sentiment"])), "hype": answer["hype"],
            "summary": answer["summary"], "quotes": quotes}


def collect(db, stocks, sources=SOURCES, ask=haiku.ask, progress=print):
    """Fetch posts and store Haiku's summary for each stock. Returns the problems met, once each."""
    db.executescript(SCHEMA)
    today = date.today().isoformat()
    problems, broken = [], set()
    for i, stock in enumerate(stocks, 1):
        posts = []
        for name, fetch in sources.items():
            if name in broken:
                continue
            found, problem = fetch(stock)
            if problem:
                broken.add(name)   # a source that isn't set up won't work for the next stock either
                problems.append(problem)
            posts += found
        if len(posts) >= MIN_POSTS:
            reading = summarise(stock, posts, ask)
            if reading:
                db.execute("INSERT OR REPLACE INTO opinions VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (stock["ticker"], today, len(posts), reading["sentiment"], int(reading["hype"]),
                            reading["summary"], json.dumps(reading["quotes"])))
                db.commit()
        progress(f"  [{i}/{len(stocks)}] {stock['ticker']}: {len(posts)} posts")
        if len(broken) == len(sources):
            break   # nothing left to ask
    return problems


def latest(db, today=None):
    """{ticker: opinion dict} from each stock's most recent reading within DAYS days."""
    db.executescript(SCHEMA)
    since = ((today or date.today()) - timedelta(days=DAYS)).isoformat()
    rows = db.execute("SELECT ticker, date, posts, sentiment, hype, summary, quotes FROM opinions "
                      "WHERE date >= ? ORDER BY date", (since,)).fetchall()
    return {t: {"date": d, "posts": n, "sentiment": s, "hype": bool(h), "summary": sm, "quotes": json.loads(q)}
            for t, d, n, s, h, sm, q in rows}


def opinion_score(reading):
    """0-100, 50 neutral. Hype counts half, so a promoted stock can't look loved."""
    sentiment = reading["sentiment"] * (HYPE_DISCOUNT if reading["hype"] else 1)
    return 50 + 50 * sentiment
