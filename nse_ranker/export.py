"""Write the ranking and everything behind it as JSON files for the online dashboard.

Each file is a list of plain rows. They go to reports/dashboard/ (not committed) and are then
uploaded to the dashboard, which draws its tables and charts from them.
"""
import hashlib
import html
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median, pstdev

from . import insights, scoring, store
from .ranking import HOLD_PERIODS
from .watchlist import load_watchlist

OUT_DIR = Path(__file__).parent.parent / "reports" / "dashboard"
PRICE_DAYS = 365
TRADING_YEAR = 252
POST_CHARS = 600   # longer posts are cut

FACTOR_INFO = {
    "momentum": ("Momentum", "Price change from about 6 months ago to 1 month ago"),
    "value": ("Value", "Earnings yield (1/P/E) compared with the stock's own sector"),
    "dividend": ("Dividend", "Dividend yield, counting only the part earnings cover"),
    "quality": ("Quality", "EPS growth between two results"),
    "risk": ("Risk", "How much the price moves day to day (calmer scores higher)"),
    "news": ("News", "Recent Kenyan news, rated by AI, fading over two weeks"),
    "opinion": ("Online opinion", "Investment talk on Reddit and X, summarised by AI; hype counts half"),
}


def _round(value, places=4):
    return None if value is None else round(value, places)


def ranking_rows(run):
    sectors = {s["ticker"]: s["sector"] for s in load_watchlist()}
    rows = []
    for position, r in enumerate(run["ranked"], 1):
        raw, f = r["raw"], r["factors"]
        verdict = run["verdicts"].get(r["ticker"], {})
        reading = run["readings"].get(r["ticker"])
        rows.append({
            "position": position, "formula_position": run["formula_position"][r["ticker"]],
            "move": verdict.get("move", 0), "ticker": r["ticker"], "name": r["name"],
            "sector": sectors[r["ticker"]],
            "score": round(r["score"], 1), "case": verdict.get("case"), "explanation": verdict.get("explanation"),
            "evidence": ", ".join(verdict.get("evidence", [])), "reasons": " · ".join(r["reasons"]),
            "hold": r["hold"], "price": r["price"], "price_date": r["price_date"],
            "ret_6m": _round(raw["momentum"]),
            "pe": round(1 / raw["value"], 1) if raw["value"] and raw["value"] > 0 else None,
            "div_yield": _round(raw["dividend"]), "daily_move": _round(raw["risk"]),
            **{f"f_{name}": None if f[name] is None else round(f[name]) for name in scoring.WEIGHTS},
            "opinion_summary": reading["summary"] if reading else None,
            "opinion_posts": reading["posts"] if reading else None,
        })
    return rows


def price_rows(db, tickers, today):
    since = (today - timedelta(days=PRICE_DAYS)).isoformat()
    return [{"ticker": t, "day": d, "close": c} for t in tickers for d, c, _ in store.history(db, t, since=since)]


def news_rows(db, today):
    return [{"id": f"N{t['id']}", "day": t["published"][:10], "ticker": t["ticker"], "sector": t["sector"],
             "about": t["ticker"] or t["sector"], "event": t["event"], "direction": t["direction"],
             "strength": t["strength"], "title": t["title"], "url": t["url"]}
            for t in insights.recent_tags(db, today)]


def article_rows(db, today):
    """Every article from the last 30 days that names a stock, one row per (stock, article).

    Includes headlines Haiku didn't tag (e.g. Business Daily, which is headline-and-link only).
    """
    since = (today - timedelta(days=insights.WINDOW_DAYS)).isoformat()
    rows = []
    for published, source, title, url, tickers in db.execute(
            "SELECT published, source, title, url, tickers FROM articles WHERE tickers != '' AND published >= ? "
            "ORDER BY published DESC", (since,)):
        for ticker in filter(None, tickers.split(",")):
            rows.append({"key": f"{ticker}|{url}", "ticker": ticker, "day": published[:10], "title": title,
                         "source": source, "url": url})
    return rows


def not_ranked_rows(run):
    names = {s["ticker"]: s for s in load_watchlist()}
    rows = [{"ticker": r["ticker"], "name": r["name"], "status": "Thin trading", "reason": r["excluded"]}
            for r in run["results"] if r["score"] is None]
    for stock in names.values():
        if stock["status"] == "watch":
            rows.append({"ticker": stock["ticker"], "name": stock["name"], "status": "Watch list",
                         "reason": stock.get("notes") or "Not ranked: new listing, penny stock or few trades"})
        elif stock["status"] == "out":
            rows.append({"ticker": stock["ticker"], "name": stock["name"], "status": "Left out",
                         "reason": stock.get("notes") or "Not an ordinary share"})
    return rows


def method_rows():
    return [{"factor": FACTOR_INFO[name][0], "key": name, "weight": weight, "measures": FACTOR_INFO[name][1],
             "hold": HOLD_PERIODS.get(name)} for name, weight in scoring.WEIGHTS.items()]


def stock_rows():
    return [{"ticker": s["ticker"], "name": s["name"], "sector": s["sector"], "type": s["type"],
             "currency": s["currency"], "status": s["status"], "notes": s.get("notes")} for s in load_watchlist()]


def post_rows(db, today):
    """Posts from the last 30 days per stock: platform, date and text only (never usernames or links)."""
    since = (today - timedelta(days=insights.WINDOW_DAYS)).isoformat()
    rows = []
    for ticker, platform, posted, text in db.execute(
            "SELECT ticker, platform, posted, text FROM opinion_posts WHERE fetched >= ? "
            "ORDER BY ticker, posted DESC", (since,)):
        key = hashlib.sha1(f"{ticker}|{platform}|{text}".encode()).hexdigest()[:16]
        rows.append({"id": key, "ticker": ticker, "platform": platform, "posted": posted,
                     "text": html.unescape(text)[:POST_CHARS]})
    return rows


def _return(closes, days):
    return closes[-1] / closes[-1 - days] - 1 if len(closes) > days and closes[-1 - days] else None


def _max_drawdown(closes):
    peak, worst = closes[0], 0.0
    for close in closes:
        peak = max(peak, close)
        worst = min(worst, close / peak - 1)
    return worst


def stats_rows(db, ranking, news, articles, posts, today):
    """Per-stock analysis worked out from stored prices, the ranking, news and posts. No AI, no fetching."""
    since = (today - timedelta(days=400)).isoformat()
    by_sector = {}
    for r in ranking:
        by_sector.setdefault(r["sector"], []).append(r)
    rows = []
    for r in ranking:
        history = store.history(db, r["ticker"], since=since)
        closes = [c for _, c, _ in history]
        year = closes[-TRADING_YEAR:]
        returns = [b / a - 1 for a, b in zip(year, year[1:]) if a]
        traded_value, traded_share = scoring.liquidity(history)
        peers = sorted(by_sector[r["sector"]], key=lambda p: -p["score"])
        pes = [p["pe"] for p in peers if p["pe"] is not None]
        yields = [p["div_yield"] for p in peers if p["div_yield"] is not None]
        own_news = [n for n in news if n["ticker"] == r["ticker"]]
        own_posts = [p for p in posts if p["ticker"] == r["ticker"]]
        rows.append({
            "ticker": r["ticker"],
            **{f"ret_{m}m": _round(_return(closes, days)) for m, days in ((1, 21), (3, 63), (6, 126), (12, 252))},
            "high_52w": max(year) if year else None, "low_52w": min(year) if year else None,
            "from_high": _round(closes[-1] / max(year) - 1) if year else None,
            "ma50": _round(mean(closes[-50:]), 2) if len(closes) >= 50 else None,
            "ma200": _round(mean(closes[-200:]), 2) if len(closes) >= 200 else None,
            "volatility_yr": _round(pstdev(returns) * TRADING_YEAR ** 0.5) if len(returns) > 20 else None,
            "max_drawdown_12m": _round(_max_drawdown(year)) if year else None,
            "traded_value_60d": round(traded_value), "traded_days_share": _round(traded_share, 3),
            "sector_rank": [p["ticker"] for p in peers].index(r["ticker"]) + 1, "sector_size": len(peers),
            "sector_median_pe": _round(median(pes), 1) if pes else None,
            "sector_median_yield": _round(median(yields)) if yields else None,
            "news_good": sum(1 for n in own_news if n["direction"] > 0),
            "news_bad": sum(1 for n in own_news if n["direction"] < 0),
            "news_neutral": sum(1 for n in own_news if n["direction"] == 0),
            "articles_30d": sum(1 for a in articles if a["ticker"] == r["ticker"]),
            "posts_reddit": sum(1 for p in own_posts if p["platform"] == "Reddit"),
            "posts_x": sum(1 for p in own_posts if p["platform"] == "X"),
        })
    return rows


def build_all(db, run, today=None):
    """Every table the dashboard uses, as {name: rows}."""
    today = today or date.today()
    ranking = ranking_rows(run)
    news, articles, posts = news_rows(db, today), article_rows(db, today), post_rows(db, today)
    return {
        "ranking": ranking,
        "prices": price_rows(db, [r["ticker"] for r in run["ranked"]], today),
        "news": news,
        "articles": articles,
        "posts": posts,
        "stats": stats_rows(db, ranking, news, articles, posts, today),
        "not_ranked": not_ranked_rows(run),
        "method": method_rows(),
        "stocks": stock_rows(),
    }


def write_all(db, run, today=None, out_dir=OUT_DIR):
    """Write every table as a JSON file. Returns {name: (path, row count)}."""
    out_dir.mkdir(parents=True, exist_ok=True)
    files = build_all(db, run, today)
    written = {}
    for name, rows in files.items():
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        written[name] = (path, len(rows))
    stamp = {"exported": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": {
        name: rows for name, (_, rows) in written.items()}}
    (out_dir / "export.json").write_text(json.dumps(stamp, indent=1), encoding="utf-8")
    return written
