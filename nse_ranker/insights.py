"""Haiku reads matched news and tags it: which stock or sector, good or bad, how strong, and a quote.

Every tag is checked in code: the stock or sector must be one the article was matched to, and the
quote must really appear in the article. Tags that fail are dropped. Each article is read once.
"""
import math
import re
from datetime import date, datetime, timedelta, timezone

from . import haiku
from .news import SCHEMA as ARTICLES_SCHEMA, load_config

BATCH = 8               # articles per Haiku call
MAX_TEXT = 3000         # characters of article text sent per article
WINDOW_DAYS = 30        # news older than this doesn't count
HALF_LIFE_DAYS = 14     # a tag's weight halves every two weeks
SECTOR_WEIGHT = 0.5     # sector-wide news counts half as much as news naming the stock
SCALE = 3.0             # raw news total that maps to roughly 87/100

SCHEMA = """
CREATE TABLE IF NOT EXISTS article_tags (
    url       TEXT NOT NULL,
    ticker    TEXT,          -- set for news about one stock
    sector    TEXT,          -- set for news about a whole sector
    event     TEXT NOT NULL,
    direction INTEGER NOT NULL,   -- -1 bad, 0 neutral, +1 good for shareholders
    strength  INTEGER NOT NULL,   -- 1 minor, 2 notable, 3 major
    quote     TEXT NOT NULL,
    tagged    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS articles_read (url TEXT PRIMARY KEY, read TEXT NOT NULL);
"""

INSTRUCTIONS = """You are a careful equity research assistant for the Nairobi Securities Exchange.
The input is a JSON list of news articles. Each lists the stocks and sectors it was matched to.
For each article, say how it affects shareholders of those stocks or sectors, using only the article.
Return one tag per (article, stock) or (article, sector) that the article really says something about;
skip mentions in passing. direction: 1 good for shareholders, -1 bad, 0 unclear or mixed.
strength: 1 minor, 2 notable, 3 major (results, dividends, takeovers, big regulatory changes).
quote: copy one short sentence or phrase exactly from the article that supports the tag.
Use only tickers and sectors listed for that article. If an article says nothing useful, return no tag for it.
Do not guess beyond the text, and do not give investment advice."""

TAG_SCHEMA = {
    "type": "object",
    "properties": {"tags": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "article": {"type": "integer"},
            "ticker": {"type": ["string", "null"]},
            "sector": {"type": ["string", "null"]},
            "event": {"type": "string"},
            "direction": {"type": "integer", "enum": [-1, 0, 1]},
            "strength": {"type": "integer", "enum": [1, 2, 3]},
            "quote": {"type": "string"},
        },
        "required": ["article", "event", "direction", "strength", "quote"],
    }}},
    "required": ["tags"],
}


def _setup(db):
    db.executescript(ARTICLES_SCHEMA)
    db.executescript(SCHEMA)


def _squash(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


def pending(db, today=None, limit=None):
    """Articles Haiku hasn't read yet: allowed for AI use, matched to something, recent."""
    _setup(db)
    since = ((today or date.today()) - timedelta(days=WINDOW_DAYS)).isoformat()
    sql = ("SELECT url, title, summary, text, tickers, topics FROM articles "
           "WHERE ai_use = 1 AND (tickers != '' OR topics != '') AND published >= ? "
           "AND url NOT IN (SELECT url FROM articles_read) ORDER BY published DESC")
    rows = db.execute(sql + (f" LIMIT {int(limit)}" if limit else ""), (since,)).fetchall()
    return [dict(zip(("url", "title", "summary", "text", "tickers", "topics"), r)) for r in rows]


def batch_input(articles, stocks, topics):
    """What Haiku sees: numbered articles, each with its candidate stocks and sectors."""
    names = {s["ticker"]: s["name"] for s in stocks}
    items = []
    for i, article in enumerate(articles):
        tickers = [t for t in article["tickers"].split(",") if t]
        sectors = sorted({sector for topic in article["topics"].split(",") if topic
                          for sector in topics[topic]["sectors"] if sector != "all"})
        if any(topic and "all" in topics[topic]["sectors"] for topic in article["topics"].split(",")):
            sectors = sorted({s["sector"] for s in stocks} | set(sectors))
        items.append({
            "article": i, "title": article["title"], "summary": article["summary"],
            "text": (article["text"] or "")[:MAX_TEXT],
            "stocks": [{"ticker": t, "name": names.get(t, t)} for t in tickers],
            "sectors": sectors,
        })
    return items


def check_tags(tags, items):
    """Keep only tags that point at a real article, an allowed stock or sector, and a real quote."""
    good = []
    for tag in tags:
        if not 0 <= tag.get("article", -1) < len(items):
            continue
        item = items[tag["article"]]
        ticker, sector = tag.get("ticker"), tag.get("sector")
        if ticker and ticker not in [s["ticker"] for s in item["stocks"]]:
            continue
        if not ticker and sector not in item["sectors"]:
            continue
        source = _squash(" ".join([item["title"], item["summary"] or "", item["text"]]))
        if not tag["quote"].strip() or _squash(tag["quote"]) not in source:
            continue
        good.append(dict(tag, ticker=ticker or None, sector=None if ticker else sector))
    return good


def tag_pending(db, stocks, ask=haiku.ask, today=None, limit=None, progress=print):
    """Tag every unread article, BATCH at a time. Returns (articles read, tags kept)."""
    topics = load_config()["topics"]
    articles = pending(db, today, limit)
    read = kept = 0
    for start in range(0, len(articles), BATCH):
        chunk = articles[start:start + BATCH]
        items = batch_input(chunk, stocks, topics)
        tags = check_tags(ask(INSTRUCTIONS, items, TAG_SCHEMA)["tags"], items)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.executemany(
            "INSERT INTO article_tags VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(chunk[t["article"]]["url"], t["ticker"], t["sector"], t["event"], t["direction"],
              t["strength"], t["quote"], now) for t in tags],
        )
        db.executemany("INSERT OR REPLACE INTO articles_read VALUES (?, ?)", [(a["url"], now) for a in chunk])
        db.commit()
        read += len(chunk)
        kept += len(tags)
        progress(f"  read {read}/{len(articles)} articles, {kept} tags kept")
    return read, kept


def recent_tags(db, today=None):
    """Tags from the last WINDOW_DAYS days with their article's date, title and link."""
    _setup(db)
    since = ((today or date.today()) - timedelta(days=WINDOW_DAYS)).isoformat()
    rows = db.execute(
        "SELECT t.rowid, t.ticker, t.sector, t.event, t.direction, t.strength, t.quote, "
        "a.published, a.title, a.url FROM article_tags t JOIN articles a ON a.url = t.url "
        "WHERE a.published >= ? ORDER BY a.published DESC", (since,)).fetchall()
    keys = ("id", "ticker", "sector", "event", "direction", "strength", "quote", "published", "title", "url")
    return [dict(zip(keys, r)) for r in rows]


def news_scores(tags, stocks, today=None):
    """{ticker: 0-100}: 50 is neutral. Stocks with no relevant tags are left out.

    Each tag counts direction x strength, halving every HALF_LIFE_DAYS, and sector tags count half.
    """
    today = today or date.today()
    totals = {}
    for stock in stocks:
        total, found = 0.0, False
        for tag in tags:
            if tag["ticker"] == stock["ticker"]:
                weight = 1.0
            elif tag["ticker"] is None and tag["sector"] == stock["sector"]:
                weight = SECTOR_WEIGHT
            else:
                continue
            age = (today - date.fromisoformat(tag["published"][:10])).days
            total += weight * tag["direction"] * tag["strength"] * 0.5 ** (max(age, 0) / HALF_LIFE_DAYS)
            found = True
        if found:
            totals[stock["ticker"]] = 50 + 50 * math.tanh(total / SCALE)
    return totals
