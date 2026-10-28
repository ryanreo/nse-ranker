"""Online opinion from Reddit and X, summarised by Haiku. The lowest-weight factor (3 points).

- X: OpenCLI (`opencli twitter search`), one search per stock, through your logged-in Chrome.
  (Agent-Reach's `twitter` CLI 0.8.5 gets HTTP 404 from X as of Oct 2026, so it isn't used.)
- Reddit: OpenCLI, which reads through your logged-in Chrome (needs the OpenCLI extension connected).
  Rather than one search per stock, it reads the newest posts from a few Kenyan subreddits once per
  run and matches them to stocks by name, like the news. Fewer requests, gentler on the account.
If a source isn't set up, it's skipped and the run says so.
"""
import json
import shutil
import subprocess
import time
from datetime import date, datetime, timedelta, timezone

from . import haiku
from .news import Matcher

DAYS = 30
MAX_POSTS = 15          # X posts per stock search
MIN_POSTS = 2           # fewer than this: no opinion score
HYPE_DISCOUNT = 0.5     # hype or promotion counts half
MAX_FAILURES_IN_A_ROW = 3   # one-off failures (timeouts) tolerated before a source is dropped for the run
SUBREDDITS = ["nsekenya", "Kenya", "nairobi"]
SUBREDDIT_POSTS = 100   # newest posts read from each subreddit

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
-- The posts behind each reading, for the dashboard. Usernames are never stored; the link is kept
-- only to avoid saving a post twice and isn't exported.
CREATE TABLE IF NOT EXISTS opinion_posts (
    ticker   TEXT NOT NULL,
    platform TEXT NOT NULL,       -- "Reddit" or "X"
    posted   TEXT,                -- YYYY-MM-DD when known
    text     TEXT NOT NULL,
    url      TEXT NOT NULL,
    fetched  TEXT NOT NULL,
    PRIMARY KEY (ticker, platform, text)
);
"""

INSTRUCTIONS = """You summarise what people on Reddit and X say about one stock on the Nairobi Securities Exchange.
The input has the stock and a list of posts. Judge only the posts' content.
investment_posts: how many posts discuss the company as an investment (its shares, price, dividends,
results, buying or selling). Complaints about its products or service don't count.
sentiment: -1 (clearly negative about owning the stock) to 1 (clearly positive), judged ONLY from the
investment posts; 0 if there are none or they're mixed.
hype: true if the positive posts read like hype, promotion, paid signals, WhatsApp/Telegram group adverts
or "guaranteed returns". summary: two sentences on what people are saying and why.
quotes: up to 3 short phrases copied exactly from the posts, with the post number.
Ignore posts that aren't about this company. This is research, not investment advice."""

OPINION_SCHEMA = {
    "type": "object",
    "properties": {
        "investment_posts": {"type": "integer", "minimum": 0},
        "sentiment": {"type": "number", "minimum": -1, "maximum": 1},
        "hype": {"type": "boolean"},
        "summary": {"type": "string"},
        "quotes": {"type": "array", "items": {
            "type": "object",
            "properties": {"post": {"type": "integer"}, "quote": {"type": "string"}},
            "required": ["post", "quote"]}},
    },
    "required": ["investment_posts", "sentiment", "hype", "summary", "quotes"],
}



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

SETUP_PROBLEMS = ("not set up", "connect the OpenCLI extension")


def is_passing(problem):
    """True for a one-off failure worth skipping past (a timeout, an odd reply), not a setup problem."""
    return not any(words in problem for words in SETUP_PROBLEMS)


def _x_date(text):
    """X's 'Wed Oct 28 08:00:10 +0000 2026' -> a datetime, or None."""
    try:
        return datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y")
    except (TypeError, ValueError):
        return None


def from_x(stock, run=subprocess.run, now=None):
    """Latest X posts naming the stock, through OpenCLI and your logged-in Chrome. Replies and
    retweets are left out (they're mostly customer-care chatter)."""
    opencli = shutil.which("opencli")   # full path: on Windows these CLIs are .cmd files
    if not opencli:
        return [], "X not set up: the `opencli` command isn't on PATH"
    try:
        done = run([opencli, "twitter", "search", query(stock), "--product", "live", "--exclude", "replies",
                    "--limit", str(MAX_POSTS), "-f", "json"],
                   capture_output=True, text=True, encoding="utf-8", timeout=180)
    except subprocess.TimeoutExpired:
        return [], "X search timed out"
    if "BROWSER_CONNECT" in done.stdout + done.stderr:
        return [], "X not available: connect the OpenCLI extension in Chrome"
    try:   # OpenCLI sometimes exits with an error code yet still prints usable results
        items = _items(done.stdout)
    except (ValueError, RuntimeError):
        first_line = (done.stderr or done.stdout).strip().splitlines()[:1]
        return [], f"X search failed (exit {done.returncode}): {first_line[0][:100] if first_line else 'no output'}"
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=DAYS)
    posts = []
    for item in items:
        text, posted = _first(item, "text"), _x_date(item.get("created_at"))
        if text and (posted is None or posted >= cutoff):
            posts.append({"platform": "X", "author": _first(item, "author"), "text": text,
                          "url": _first(item, "url"), "posted": posted.date().isoformat() if posted else None})
    return posts, None


def reddit_posts(run=subprocess.run, now=None):
    """The last DAYS days of posts from SUBREDDITS, read once per run. Returns (posts, problem)."""
    opencli = shutil.which("opencli")
    if not opencli:
        return [], "Reddit not set up: the `opencli` command isn't on PATH"
    cutoff = (now or time.time()) - DAYS * 86400
    posts = []
    for subreddit in SUBREDDITS:
        done = run([opencli, "reddit", "subreddit", subreddit, "--sort", "new",
                    "--limit", str(SUBREDDIT_POSTS), "-f", "json"],
                   capture_output=True, text=True, encoding="utf-8", timeout=180)
        if done.returncode != 0:
            output = done.stdout + done.stderr
            detail = "connect the OpenCLI extension in Chrome" if "BROWSER_CONNECT" in output else output.strip()[:120]
            return [], f"Reddit not available: {detail}"
        try:
            items = _items(done.stdout)
        except (ValueError, RuntimeError) as error:
            return [], f"Reddit read failed: {str(error)[:120]}"
        for item in items:
            created = float(item.get("created_utc") or 0)
            text = " ".join(filter(None, [_first(item, "title"), _first(item, "selftext", "body", "text")]))
            if text and created >= cutoff:
                posts.append({"platform": "Reddit", "author": _first(item, "author"), "text": text,
                              "url": _first(item, "url", "permalink"),
                              "posted": datetime.fromtimestamp(created, timezone.utc).date().isoformat()})
    return posts, None


def match_posts(posts, stocks):
    """{ticker: [posts naming it]}, using the same name lists as the news."""
    matcher = Matcher(stocks, {})
    matched = {}
    for post in posts:
        tickers, _ = matcher.match({"title": post["text"], "summary": "", "text": None})
        for ticker in tickers:
            matched.setdefault(ticker, []).append(post)
    return matched


# Per-stock sources take a stock; bulk sources are read once and matched by name.
SOURCES = {"X": from_x}
BULK_SOURCES = {"Reddit": reddit_posts}


# ---- Summarising and scoring ----

def summarise(stock, posts, ask=haiku.ask):
    """Haiku's read of the posts, with quotes checked against the posts. None if nothing usable."""
    data = {"stock": {"ticker": stock["ticker"], "name": stock["name"]},
            "posts": [{"post": i, "platform": p["platform"], "text": p["text"][:1000]} for i, p in enumerate(posts)]}
    answer = ask(INSTRUCTIONS, data, OPINION_SCHEMA)
    if answer.get("investment_posts", 0) < MIN_POSTS:   # chatter about the service, not the shares
        return None
    quotes = [{"quote": q["quote"], "url": posts[q["post"]]["url"]} for q in answer["quotes"]
              if 0 <= q["post"] < len(posts) and q["quote"].strip()
              and q["quote"].strip().lower() in posts[q["post"]]["text"].lower()]
    if not quotes:   # Haiku couldn't point at real words, so don't trust the reading
        return None
    return {"sentiment": max(-1.0, min(1.0, answer["sentiment"])), "hype": answer["hype"],
            "summary": answer["summary"], "quotes": quotes}


def save_posts(db, ticker, posts, today):
    """Keep each post's platform, date and text (never the username) for the dashboard."""
    db.executemany(
        "INSERT OR IGNORE INTO opinion_posts (ticker, platform, posted, text, url, fetched) VALUES (?, ?, ?, ?, ?, ?)",
        [(ticker, p["platform"], p.get("posted"), p["text"], p.get("url") or "", today) for p in posts])
    db.commit()


def collect(db, stocks, sources=SOURCES, bulk_sources=BULK_SOURCES, ask=haiku.ask, progress=print,
            refresh=False):
    """Fetch posts and store them and Haiku's summary for each stock. Returns the problems met, once each.

    A rerun the same day skips stocks already done; with refresh, only stocks whose posts were saved today.
    """
    db.executescript(SCHEMA)
    today = date.today().isoformat()
    problems, broken = [], set()
    bulk = {}
    for name, fetch in bulk_sources.items():
        posts, problem = fetch()
        if problem:
            problems.append(problem)
        else:
            progress(f"  {name}: {len(posts)} recent posts read")
        for ticker, matched in match_posts(posts, stocks).items():
            bulk.setdefault(ticker, []).extend(matched)
    failures = {}   # consecutive one-off failures per source
    done_today = {t for (t,) in db.execute("SELECT ticker FROM opinion_posts WHERE fetched = ?", (today,))}
    if not refresh:
        done_today |= {t for (t,) in db.execute("SELECT ticker FROM opinions WHERE date = ?", (today,))}
    for i, stock in enumerate(stocks, 1):
        if stock["ticker"] in done_today:   # a rerun picks up where the last one stopped
            continue
        posts = list(bulk.get(stock["ticker"], []))
        for name, fetch in sources.items():
            if name in broken:
                continue
            found, problem = fetch(stock)
            if problem and is_passing(problem) and failures.get(name, 0) + 1 < MAX_FAILURES_IN_A_ROW:
                failures[name] = failures.get(name, 0) + 1   # a timeout: skip this stock, try the next
                progress(f"  [{i}/{len(stocks)}] {stock['ticker']}: {name} {problem}, skipped")
            elif problem:
                broken.add(name)   # not set up, or failing every time: stop asking it this run
                problems.append(problem)
            else:
                failures[name] = 0
            posts += found
        save_posts(db, stock["ticker"], posts, today)
        if len(posts) >= MIN_POSTS:
            reading = summarise(stock, posts, ask)
            if reading:
                db.execute("INSERT OR REPLACE INTO opinions VALUES (?, ?, ?, ?, ?, ?, ?)",
                           (stock["ticker"], today, len(posts), reading["sentiment"], int(reading["hype"]),
                            reading["summary"], json.dumps(reading["quotes"])))
                db.commit()
        if posts:
            progress(f"  [{i}/{len(stocks)}] {stock['ticker']}: {len(posts)} posts")
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
