"""Rank the watchlist from stored data, explain each score, and save every run."""
import json
from datetime import date, timedelta

from . import scoring, store
from .watchlist import load_watchlist

HISTORY_DAYS = 400   # enough calendar days for 6-month momentum plus a margin


def build_inputs(db, today=None):
    """One input dict per "rank" stock, in the shape scoring.score_all() expects."""
    today = today or date.today()
    since = (today - timedelta(days=HISTORY_DAYS)).isoformat()
    stocks = []
    for stock in load_watchlist():
        if stock["status"] != "rank":
            continue
        # Results in another currency (e.g. Rwandan francs) can't be compared with a KES price.
        foreign = stock.get("reports_in", "KES") != "KES"
        eps_changes = [] if foreign else store.eps_history(db, stock["ticker"])
        eps, dps = (eps_changes[-1][1], eps_changes[-1][2]) if eps_changes else (None, None)
        stocks.append({
            "ticker": stock["ticker"], "name": stock["name"], "sector": stock["sector"],
            "rows": store.history(db, stock["ticker"], since=since),
            "eps": eps, "dps": dps, "eps_changes": eps_changes,
        })
    return [s for s in stocks if s["rows"]]


def describe(name, raw, good):
    """One factor in plain words. `good` says whether it's a strength or a weakness."""
    if name == "momentum":
        return f"price {raw:+.0%} over 6 months"
    if name == "value":
        if raw <= 0:
            return "loss-making"
        return f"P/E {1 / raw:.1f}, {'cheap' if good else 'expensive'} for its sector"
    if name == "dividend":
        if not raw:
            return "no dividend covered by earnings"
        return f"dividend yield {raw:.1%}, covered by earnings" if good else f"dividend yield only {raw:.1%}"
    if name == "quality":
        return f"EPS {raw:+.0%} at the latest results"
    if name == "risk":
        return f"{'calm' if good else 'jumpy'} price (typical daily move {raw:.1%})"
    return f"{name} {'positive' if good else 'negative'}"


def reasons(result):
    """Up to three reasons: the two strongest factors (score 60+) and the weakest (40 or less)."""
    scored = sorted((s, name) for name, s in result["factors"].items() if s is not None)
    picks = [(name, True) for s, name in reversed(scored[-2:]) if s >= 60]
    if scored and scored[0][0] <= 40 and scored[0][1] not in [name for name, _ in picks]:
        picks.append((scored[0][1], False))
    return [("+ " if good else "- ") + describe(name, result["raw"][name], good) for name, good in picks]


# Each factor tends to pay off over a different time span (docs/RESEARCH.md, R1):
# momentum on the NSE lasts about 3-6 months; cheapness and dividends take a year or more;
# earnings growth and calm prices sit in between, roughly until the next results.
HOLD_PERIODS = {
    "momentum": "3-6 months",
    "quality": "6-12 months",
    "risk": "6-12 months",
    "value": "12+ months",
    "dividend": "12+ months",
}


def hold_time(result):
    """Suggested holding period: the span of the factors that add the most to this stock's score.

    Each factor's share is its weight times its score. Factors are grouped by span, and the
    biggest group wins. News and online opinion don't set a hold time.
    """
    shares = {}
    for name, score in result["factors"].items():
        if score is not None and name in HOLD_PERIODS:
            period = HOLD_PERIODS[name]
            shares[period] = shares.get(period, 0) + scoring.WEIGHTS[name] * score
    return max(shares, key=shares.get) if shares else None


def rank(db, today=None):
    """Score every "rank" stock. Returns (results, inputs by ticker)."""
    inputs = build_inputs(db, today)
    results = scoring.score_all(inputs)
    by_ticker = {s["ticker"]: s for s in inputs}
    for result in results:
        stock = by_ticker[result["ticker"]]
        result["name"] = stock["name"]
        result["price"] = stock["rows"][-1][1]
        result["price_date"] = stock["rows"][-1][0]
        result["reasons"] = reasons(result) if result["score"] is not None else []
        result["hold"] = hold_time(result) if result["score"] is not None else None
    return results


def _runs_table(db):
    db.execute("""CREATE TABLE IF NOT EXISTS rank_runs (
        run_date TEXT NOT NULL, ticker TEXT NOT NULL, position INTEGER, score REAL,
        factors TEXT, excluded TEXT, PRIMARY KEY (run_date, ticker))""")


def save_run(db, results, run_date=None):
    """Keep every ranking so later runs can be compared and the score backtested."""
    run_date = run_date or date.today().isoformat()
    _runs_table(db)
    db.executemany(
        "INSERT OR REPLACE INTO rank_runs VALUES (?, ?, ?, ?, ?, ?)",
        [(run_date, r["ticker"], i if r["score"] is not None else None, r["score"],
          json.dumps(r["factors"]), r["excluded"]) for i, r in enumerate(results, 1)],
    )
    db.commit()


def previous_positions(db, before):
    """{ticker: position} from the most recent run before `before` (YYYY-MM-DD), or {}."""
    _runs_table(db)
    last = db.execute("SELECT MAX(run_date) FROM rank_runs WHERE run_date < ?", (before,)).fetchone()[0]
    if not last:
        return {}
    return dict(db.execute(
        "SELECT ticker, position FROM rank_runs WHERE run_date = ? AND position IS NOT NULL", (last,)
    ).fetchall())
