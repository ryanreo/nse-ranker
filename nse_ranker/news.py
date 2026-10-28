"""Kenyan news: read RSS feeds, store articles, and tag each one with the stocks and topics it mentions.

Sources and topics are listed in news.toml. Matching is by name: each stock's aliases in
watchlist.toml, and each topic's keywords in news.toml.
"""
import html
import re
import tomllib
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import web
from .watchlist import load_watchlist

NEWS_FILE = Path(__file__).parent.parent / "news.toml"
CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"

SCHEMA = """
CREATE TABLE IF NOT EXISTS articles (
    url       TEXT PRIMARY KEY,
    source    TEXT NOT NULL,
    published TEXT NOT NULL,    -- ISO date-time, UTC
    title     TEXT NOT NULL,
    summary   TEXT,
    text      TEXT,             -- full text, only where the feed includes it
    ai_use    INTEGER NOT NULL, -- 1 if the source allows passing its text to AI
    tickers   TEXT NOT NULL DEFAULT '',   -- comma-separated, e.g. "KCB,EQTY"
    topics    TEXT NOT NULL DEFAULT '',   -- comma-separated, e.g. "interest rates"
    fetched   TEXT NOT NULL
);
"""


def load_config(path=NEWS_FILE):
    with open(path, "rb") as f:
        return tomllib.load(f)


# ---- Reading feeds ----

def clean(text):
    """Strip HTML tags and entities, and squeeze whitespace."""
    text = re.sub(r"<[^>]+>", " ", text or "")
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def clean_url(url):
    """Drop tracking parameters (?utm_source=...) so the same article isn't stored twice."""
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def parse_feed(xml_bytes, source):
    """Turn one RSS feed into article dicts. Skips items with no link or title."""
    articles = []
    for item in ET.fromstring(xml_bytes).iter("item"):
        link, title = item.findtext("link"), item.findtext("title")
        if not link or not title:
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate")).astimezone(timezone.utc)
        except (TypeError, ValueError):
            published = datetime.now(timezone.utc)
        articles.append({
            "url": clean_url(link),
            "source": source["name"],
            "published": published.isoformat(timespec="seconds"),
            "title": clean(title),
            "summary": clean(item.findtext("description")),
            "text": clean(item.findtext(CONTENT)) or None,
            "ai_use": int(source["ai_use"]),
        })
    return articles


# ---- Matching ----

def _pattern(name):
    """Whole-word pattern. ALL-CAPS names (KCB, EABL) must match exactly; others ignore case."""
    flags = 0 if name.upper() == name and any(c.isalpha() for c in name) else re.IGNORECASE
    return re.compile(rf"(?<!\w){re.escape(name)}(?!\w)", flags)


class Matcher:
    """Finds which stocks and topics an article mentions."""

    def __init__(self, stocks, topics):
        self.stocks = {s["ticker"]: [_pattern(a) for a in s.get("aliases", [])] for s in stocks}
        self.topics = {name: [_pattern(k) for k in t["keywords"]] for name, t in topics.items()}

    def match(self, article):
        text = " ".join(filter(None, [article["title"], article["summary"], article["text"]]))
        tickers = [t for t, patterns in self.stocks.items() if any(p.search(text) for p in patterns)]
        topics = [name for name, patterns in self.topics.items() if any(p.search(text) for p in patterns)]
        return tickers, topics


# ---- Storing ----

def save_articles(db, articles, matcher):
    """Insert new articles (existing ones are kept as first seen). Returns how many were new."""
    db.executescript(SCHEMA)
    fetched = datetime.now(timezone.utc).isoformat(timespec="seconds")
    new = 0
    for article in articles:
        tickers, topics = matcher.match(article)
        cursor = db.execute(
            "INSERT OR IGNORE INTO articles VALUES (:url, :source, :published, :title, :summary, :text, "
            ":ai_use, :tickers, :topics, :fetched)",
            dict(article, tickers=",".join(tickers), topics=",".join(topics), fetched=fetched),
        )
        new += cursor.rowcount
    db.commit()
    return new


def rematch(db, matcher):
    """Re-tag every stored article, e.g. after editing aliases or keywords."""
    db.executescript(SCHEMA)
    rows = db.execute("SELECT url, title, summary, text FROM articles").fetchall()
    for url, title, summary, text in rows:
        tickers, topics = matcher.match({"title": title, "summary": summary, "text": text})
        db.execute("UPDATE articles SET tickers = ?, topics = ? WHERE url = ?",
                   (",".join(tickers), ",".join(topics), url))
    db.commit()
    return len(rows)


def fetch_all(db):
    """Read every feed in news.toml and store new articles. Returns {source: (items, new)}."""
    config = load_config()
    matcher = Matcher(load_watchlist(), config["topics"])
    report = {}
    for source in config["source"]:
        body = web.get(source["feed"], delay=2)
        articles = parse_feed(body, source) if body else []
        report[source["name"]] = (len(articles), save_articles(db, articles, matcher))
    rematch(db, matcher)
    return report


# ---- Reading back ----

def for_stock(db, stock, days=14, today=None, topics=None):
    """Articles from the last `days` days that name this stock or touch its sector's topics.

    Returns (direct, sector): direct mentions first, then topic news for its sector.
    """
    db.executescript(SCHEMA)
    since = ((today or date.today()) - timedelta(days=days)).isoformat()
    topics = topics or load_config()["topics"]
    relevant = {name for name, t in topics.items() if "all" in t["sectors"] or stock["sector"] in t["sectors"]}
    rows = db.execute(
        "SELECT published, source, title, url, tickers, topics, ai_use FROM articles "
        "WHERE published >= ? ORDER BY published DESC", (since,)
    ).fetchall()
    direct, sector = [], []
    for published, source, title, url, tickers, article_topics, ai_use in rows:
        item = {"published": published, "source": source, "title": title, "url": url,
                "topics": [t for t in article_topics.split(",") if t], "ai_use": bool(ai_use)}
        if stock["ticker"] in tickers.split(","):
            direct.append(item)
        elif relevant & set(item["topics"]):
            sector.append(item)
    return direct, sector


def summary(db, days=7, today=None):
    """{ticker: number of articles naming it} over the last `days` days, most-mentioned first."""
    db.executescript(SCHEMA)
    since = ((today or date.today()) - timedelta(days=days)).isoformat()
    counts = {}
    for (tickers,) in db.execute("SELECT tickers FROM articles WHERE published >= ?", (since,)):
        for ticker in filter(None, tickers.split(",")):
            counts[ticker] = counts.get(ticker, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))
