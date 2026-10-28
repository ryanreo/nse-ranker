"""Write the ranking and everything behind it as JSON files for the online dashboard.

Each file is a list of plain rows. They go to reports/dashboard/ (not committed) and are then
uploaded to the dashboard, which draws its tables and charts from them.
"""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from . import insights, scoring, store
from .ranking import HOLD_PERIODS
from .watchlist import load_watchlist

OUT_DIR = Path(__file__).parent.parent / "reports" / "dashboard"
PRICE_DAYS = 365

FACTOR_INFO = {
    "momentum": ("Momentum", "Price change from about 6 months ago to 1 month ago"),
    "value": ("Value", "Earnings yield (1/P/E) compared with the stock's own sector"),
    "dividend": ("Dividend", "Dividend yield, counting only the part earnings cover"),
    "quality": ("Quality", "EPS growth between two results"),
    "risk": ("Risk", "How much the price moves day to day (calmer scores higher)"),
    "news": ("News", "Recent Kenyan news tagged by Haiku, fading over two weeks"),
    "opinion": ("Online opinion", "Investment talk on Reddit and X, summarised by Haiku; hype counts half"),
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


def write_all(db, run, today=None, out_dir=OUT_DIR):
    """Write the six files. Returns {name: (path, row count)}."""
    today = today or date.today()
    out_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "ranking": ranking_rows(run),
        "prices": price_rows(db, [r["ticker"] for r in run["ranked"]], today),
        "news": news_rows(db, today),
        "articles": article_rows(db, today),
        "not_ranked": not_ranked_rows(run),
        "method": method_rows(),
    }
    written = {}
    for name, rows in files.items():
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(rows, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        written[name] = (path, len(rows))
    stamp = {"exported": datetime.now(timezone.utc).isoformat(timespec="seconds"), "files": {
        name: rows for name, (_, rows) in written.items()}}
    (out_dir / "export.json").write_text(json.dumps(stamp, indent=1), encoding="utf-8")
    return written
