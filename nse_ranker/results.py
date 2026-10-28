"""Earnings per share read from results news, for the quality factor (EPS growth).

Results stories say things like "earnings per share rose to KSh 6.80 from KSh 5.90". AI reads each
results article and returns the stock, the period, this EPS and the same period's EPS a year earlier,
with a quote. A figure is kept only if the quote is in the article and contains both numbers, so a
number can't be made up or worked out. Growth is then simply (EPS - prior EPS) / |prior EPS|.
"""
import re
from datetime import date, datetime, timezone

from . import haiku

BATCH = 5
MAX_TEXT = 4000

SCHEMA = """
CREATE TABLE IF NOT EXISTS reported_eps (
    ticker     TEXT NOT NULL,
    period     TEXT NOT NULL,      -- e.g. "FY2025", "H1 2026"
    period_end TEXT,               -- YYYY-MM-DD when stated
    eps        REAL NOT NULL,
    prior_eps  REAL,               -- the same period a year earlier
    quote      TEXT NOT NULL,
    url        TEXT NOT NULL,
    published  TEXT NOT NULL,
    PRIMARY KEY (ticker, period)
);
CREATE TABLE IF NOT EXISTS results_read (url TEXT PRIMARY KEY, read TEXT NOT NULL);
"""

INSTRUCTIONS = """You read Kenyan company results news. The input is a JSON list of articles, each with the
listed stocks it names. For each stock whose results the article reports, return:
- period: the reporting period, written like "FY2025", "H1 2026" or "Q3 2026".
- period_end: the period's last day as YYYY-MM-DD if the article makes it clear, else null.
- eps: basic earnings per share for that period, as stated in the article (a negative number for a loss per share).
- prior_eps: EPS for the same period a year earlier, as stated in the article, else null.
- quote: one short passage copied exactly from the article that contains the EPS figure(s) you used.
Only use figures the article states as earnings (or loss) per share. Do not work anything out from profit,
dividends or share counts. Skip stocks whose EPS the article doesn't give. Use only the listed tickers."""

EPS_SCHEMA = {
    "type": "object",
    "properties": {"figures": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "article": {"type": "integer"},
            "ticker": {"type": "string"},
            "period": {"type": "string"},
            "period_end": {"type": ["string", "null"]},
            "eps": {"type": "number"},
            "prior_eps": {"type": ["number", "null"]},
            "quote": {"type": "string"},
        },
        "required": ["article", "ticker", "period", "eps", "prior_eps", "quote"],
    }}},
    "required": ["figures"],
}


def _setup(db):
    db.executescript(SCHEMA)


def _squash(text):
    return re.sub(r"\s+", " ", text or "").strip().lower()


def number_in(text, value):
    """True if `value` appears in `text` as written in a typical results story (6.8, 6.80, 1,234.5...)."""
    shown = {f"{abs(value):g}", f"{abs(value):.2f}", f"{abs(value):.1f}", f"{abs(value):,.2f}", f"{abs(value):,g}"}
    if abs(value) == int(abs(value)):
        shown.add(str(int(abs(value))))
    found = re.findall(r"\d[\d,]*(?:\.\d+)?", text)
    return any(f in shown or f.replace(",", "") in {s.replace(",", "") for s in shown} for f in found)


def check(figure, items):
    """Keep a figure only if its stock, quote and numbers all hold up against the article."""
    if not 0 <= figure.get("article", -1) < len(items):
        return None
    item = items[figure["article"]]
    if figure.get("ticker") not in [s["ticker"] for s in item["stocks"]]:
        return None
    quote = figure.get("quote", "")
    if not quote.strip() or _squash(quote) not in _squash(item["title"] + " " + item["text"]):
        return None
    if not number_in(quote, figure["eps"]):
        return None
    prior = figure.get("prior_eps")
    if prior is not None and not number_in(quote, prior):
        prior = None   # the growth can't be trusted, but this period's EPS still can
    return dict(figure, prior_eps=prior, period=figure["period"].strip().upper().replace("  ", " "))


def candidates(db, since):
    """Unread articles from `since` that name a stock and mention earnings per share."""
    _setup(db)
    rows = db.execute(
        "SELECT url, title, text, tickers, published FROM articles WHERE ai_use = 1 AND tickers != '' "
        "AND published >= ? AND text IS NOT NULL "
        "AND (lower(text) LIKE '%per share%' OR text LIKE '%EPS%') "
        "AND url NOT IN (SELECT url FROM results_read) ORDER BY published DESC", (since,)).fetchall()
    return [dict(zip(("url", "title", "text", "tickers", "published"), r)) for r in rows]


def read_results(db, stocks, since, ask=haiku.ask, progress=print):
    """Have AI read every unread results article since `since`. Returns (articles read, figures kept)."""
    names = {s["ticker"]: s["name"] for s in stocks}
    articles = candidates(db, since)
    read = kept = 0
    for start in range(0, len(articles), BATCH):
        chunk = articles[start:start + BATCH]
        items = [{"article": i, "title": a["title"], "text": a["text"][:MAX_TEXT],
                  "stocks": [{"ticker": t, "name": names.get(t, t)} for t in a["tickers"].split(",") if t]}
                 for i, a in enumerate(chunk)]
        for figure in ask(INSTRUCTIONS, items, EPS_SCHEMA)["figures"]:
            good = check(figure, items)
            if good:
                article = chunk[good["article"]]
                db.execute("INSERT OR REPLACE INTO reported_eps VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (good["ticker"], good["period"], good.get("period_end"), good["eps"], good["prior_eps"],
                            good["quote"], article["url"], article["published"]))
                kept += 1
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        db.executemany("INSERT OR REPLACE INTO results_read VALUES (?, ?)", [(a["url"], now) for a in chunk])
        db.commit()
        read += len(chunk)
        progress(f"  read {read}/{len(articles)} results articles, {kept} EPS figures kept")
    return read, kept


def period_key(period):
    """("H1", 2026) from labels like "H1 2026", "HALF-YEAR 2026", "FY2025" or "2025"; None if unclear."""
    year = re.search(r"20\d\d", period)
    if not year:
        return None
    text = period.upper()
    if re.search(r"\bQ([1-4])\b", text):
        kind = "Q" + re.search(r"\bQ([1-4])\b", text).group(1)
    elif re.search(r"H1|HALF|INTERIM|SIX MONTHS", text):
        kind = "H1"
    elif re.search(r"H2", text):
        kind = "H2"
    else:
        kind = "FY"   # "FY2025", "FULL YEAR 2025" or a bare year
    return kind, int(year.group())


def latest_growth(db, today=None):
    """{ticker: (growth, period)} from each stock's most recent results with a year-earlier EPS.

    The year-earlier figure is the one the article gave, or else the same period a year before among
    the stored figures (KCB H1 2026 against KCB H1 2025).
    """
    _setup(db)
    cutoff = (today or date.today()).isoformat()
    rows = db.execute(
        "SELECT ticker, period, eps, prior_eps, COALESCE(period_end, substr(published, 1, 10)) AS ended "
        "FROM reported_eps WHERE substr(published, 1, 10) <= ? ORDER BY ended", (cutoff,)).fetchall()
    by_period = {(t, period_key(p)): eps for t, p, eps, _, _ in rows if period_key(p)}
    growth = {}
    for ticker, period, eps, prior, _ in rows:
        key = period_key(period)
        if prior is None and key:
            prior = by_period.get((ticker, (key[0], key[1] - 1)))
        if prior:
            growth[ticker] = ((eps - prior) / abs(prior), period)   # later rows replace earlier ones
    return growth
