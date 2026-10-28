"""Kenyan news: read RSS feeds, store articles, and tag each one with the stocks and topics it mentions.

Sources and topics are listed in news.toml. Matching is by name: each stock's aliases in
watchlist.toml, and each topic's keywords in news.toml.
"""
import html
import http.client
import json
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
    """Whole-word pattern. ALL-CAPS names (KCB, EABL) and single capitalised words (Equity, Unga)
    must match exactly, so "private equity" isn't Equity Group; longer names ignore case."""
    exact = (name.upper() == name and any(c.isalpha() for c in name)) or (" " not in name and name[:1].isupper())
    flags = 0 if exact else re.IGNORECASE
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


def parse_article_page(page, url, source):
    """One article page -> article dict, from its schema.org NewsArticle data and its paragraphs."""
    data = {}
    for block in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', page, re.S) or \
            re.findall(r'(\{"@context":"https://schema.org","@type":"NewsArticle".*?\})(?=\{"@context"|<|$)', page, re.S):
        try:
            candidate = json.loads(block)
        except ValueError:
            continue
        if isinstance(candidate, dict) and candidate.get("@type") == "NewsArticle":
            data = candidate
            break
    title = data.get("headline") or (re.search(r"<title>(.*?)</title>", page, re.S) or [None, ""])[1]
    published = data.get("datePublished")
    if not title or not published:
        return None
    paragraphs = [clean(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", page, re.S)]
    body = [p for p in paragraphs if 40 <= len(p) <= 2000 and "@context" not in p and "TURBOPACK" not in p]
    return {
        "url": clean_url(url), "source": source["name"],
        "published": datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(timezone.utc)
                     .isoformat(timespec="seconds"),
        "title": clean(title).split(" | ")[0], "summary": clean(data.get("description")),
        "text": " ".join(body) or None, "ai_use": int(source["ai_use"]),
    }


def sitemap_urls(xml_bytes):
    """[(url, lastmod), ...] from a sitemap or a sitemap index."""
    root = ET.fromstring(xml_bytes)
    found = []
    for entry in root:
        loc = entry.findtext("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
        lastmod = entry.findtext("{http://www.sitemaps.org/schemas/sitemap/0.9}lastmod") or ""
        if loc:
            found.append((loc.strip(), lastmod.strip()))
    return found


def read_sitemap_source(db, source, since, limit, url_filter=None, newest_lists=None, matcher=None,
                        progress=None):
    """New articles from a sitemap source: recent posts not already stored, at most `limit` pages.

    url_filter: a regex the post's address must match (e.g. results stories only).
    newest_lists: only read the N highest-numbered post lists (posts-11.xml, posts-10.xml...). A site may
      refresh old posts' dates in bulk, so "modified since" alone can pull in years of archive.
    matcher: if given, each article is saved as soon as it's read (old ones too, so a rerun skips them),
      making a long backfill resumable.
    """
    index = sitemap_urls(web.get(source["sitemap"], delay=2) or b"<urlset/>")
    children = [(u, m) for u, m in index if m[:10] >= since]   # child sitemaps changed in the window
    if newest_lists:
        number = lambda u: int((re.findall(r"(\d+)\.xml$", u) or ["0"])[0])
        children = sorted(children, key=lambda c: -number(c[0]))[:newest_lists]
    known = {u for (u,) in db.execute("SELECT url FROM articles")}
    wanted = []
    for child, _ in children:
        for url, lastmod in sitemap_urls(web.get(child, delay=2) or b"<urlset/>"):
            if lastmod[:10] >= since and clean_url(url) not in known \
                    and (not url_filter or re.search(url_filter, url.rsplit("/", 1)[-1], re.I)):
                wanted.append((lastmod, url))
    articles = []
    chosen = sorted(wanted, reverse=True)[:limit]   # newest first
    for i, (_, url) in enumerate(chosen, 1):
        try:
            page = web.get(url, delay=2)
        except (OSError, http.client.HTTPException):   # a timeout or a cut-off download: skip this page
            continue
        article = parse_article_page(page.decode("utf-8", errors="replace"), url, source) if page else None
        if article and matcher:
            save_articles(db, [article], matcher)
        if article and article["published"][:10] >= since:
            articles.append(article)
        if progress and i % 20 == 0:
            progress(f"  {source['name']}: {i}/{len(chosen)} pages read, {len(articles)} in range")
    return articles


def read_feed_source(source, since, backfill):
    """Articles from an RSS feed; with backfill, also its older pages back to `since`."""
    articles = []
    for page in range(1, (source.get("pages", 1) if backfill else 1) + 1):
        url = source["feed"] if page == 1 else f"{source['feed']}?paged={page}"
        body = web.get(url, delay=2)
        items = parse_feed(body, source) if body else []
        articles += items
        if not items or min(a["published"] for a in items)[:10] < since:
            break
    return articles


def fetch_all(db, backfill=False, days=30):
    """Read every source in news.toml and store new articles. Returns {source: (items, new)}.

    Without backfill: each feed's latest page, and up to 40 new sitemap articles.
    With backfill: feeds' older pages and up to 400 sitemap articles, back `days` days.
    """
    db.executescript(SCHEMA)
    config = load_config()
    matcher = Matcher(load_watchlist(), config["topics"])
    since = (date.today() - timedelta(days=days)).isoformat()
    report = {}
    for source in config["source"]:
        if "sitemap" in source:
            articles = read_sitemap_source(db, source, since, limit=400 if backfill else 40)
        else:
            articles = read_feed_source(source, since, backfill)
        report[source["name"]] = (len(articles), save_articles(db, articles, matcher))
    rematch(db, matcher)
    return report


RESULTS_WORDS = r"(profit|earnings|eps|results|net-income|loss|half-year|h1|fy-?20|dividend|interim|full-year|pat-)"


def fetch_results(db, since, newest_lists=4, progress=print):
    """Backfill results stories (profit, earnings, dividends) from sitemap sources back to `since`,
    so earnings per share can be read from them. Saves as it goes. Returns {source: articles in range}."""
    db.executescript(SCHEMA)
    config = load_config()
    matcher = Matcher(load_watchlist(), config["topics"])
    report = {}
    for source in config["source"]:
        if "sitemap" in source:
            articles = read_sitemap_source(db, source, since, limit=400, url_filter=RESULTS_WORDS,
                                           newest_lists=newest_lists, matcher=matcher, progress=progress)
            report[source["name"]] = len(articles)
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
