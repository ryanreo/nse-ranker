"""Backtest the price-based part of the score on NSE history.

Only momentum and risk can be tested: we have daily prices back to 2007, but not past EPS or
dividends, and news and opinion only exist from now on. So this checks 35 of the 100 weight points.

Method: on the first trading day of each month, score every stock that passes the liquidity gate
(using only data up to that day), then measure each stock's price return over the next 1, 3, 6 and
12 months. Compare the top fifth by score, the bottom fifth and the average stock.
Stocks later delisted are included while they traded, so the test isn't run on survivors only.
"""
from bisect import bisect_left, bisect_right
from datetime import date
from statistics import mean

from . import scoring

HORIZONS = (1, 3, 6, 12)        # months
GROUP_SHARE = 0.2               # top and bottom fifth
ROUND_TRIP_COST = 0.02          # NSE brokerage, levies and spread for one buy plus one sell, roughly
MAX_DAILY_MOVE = 0.45           # bigger one-day moves are usually bonus issues or splits in unadjusted prices
STALE_DAYS = 10                 # a stock must have traded within this many days of the ranking date
WEIGHTS = {"momentum": scoring.WEIGHTS["momentum"], "risk": scoring.WEIGHTS["risk"]}


def add_months(day, months):
    year, month = divmod(day.month - 1 + months, 12)
    return date(day.year + year, month + 1, 1)


def load_all(db):
    """{ticker: (dates, closes, volumes)} for every stock (not indices), dates as date objects."""
    data = {}
    for ticker, day, close, volume in db.execute(
            "SELECT ticker, date, close, volume FROM prices WHERE ticker NOT LIKE '^%' ORDER BY ticker, date"):
        dates, closes, volumes = data.setdefault(ticker, ([], [], []))
        dates.append(date.fromisoformat(day))
        closes.append(close)
        volumes.append(volume)
    return data


def rows_until(series, day):
    """[(date, close, volume)] up to and including `day`, in the shape scoring expects."""
    dates, closes, volumes = series
    end = bisect_right(dates, day)
    start = max(0, end - scoring.MOMENTUM_LOOKBACK - 1)
    return list(zip(dates[start:end], closes[start:end], volumes[start:end]))


def price_on_or_after(series, day, limit_days=STALE_DAYS):
    """First close on or after `day` (within limit_days), else None."""
    dates, closes, _ = series
    i = bisect_left(dates, day)
    if i < len(dates) and (dates[i] - day).days <= limit_days:
        return closes[i]
    return None


def has_jump(series, start, end):
    """True if any one-day move between start and end is bigger than MAX_DAILY_MOVE."""
    dates, closes, _ = series
    i, j = bisect_left(dates, start), bisect_right(dates, end)
    return any(a and abs(b / a - 1) > MAX_DAILY_MOVE for a, b in zip(closes[max(i, 1) - 1:j], closes[max(i, 1):j]))


def spearman(xs, ys):
    """Rank correlation between two equal-length lists (ties get average ranks)."""
    def ranks(values):
        order = sorted(range(len(values)), key=lambda k: values[k])
        result = [0.0] * len(values)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
                j += 1
            for k in range(i, j + 1):
                result[order[k]] = (i + j) / 2
            i = j + 1
        return result
    rx, ry = ranks(xs), ranks(ys)
    mx, my = mean(rx), mean(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    var = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return cov / var if var else 0.0


def score_on(data, day, weights=WEIGHTS):
    """{ticker: (score, momentum score, risk score)} for stocks rankable on `day`, using data up to it."""
    raw_m, raw_r = {}, {}
    for ticker, series in data.items():
        rows = rows_until(series, day)
        if not rows or (day - rows[-1][0]).days > STALE_DAYS or scoring.liquidity_problem(rows):
            continue
        if has_jump(series, rows[0][0], day):
            continue
        m, r = scoring.momentum(rows), scoring.volatility(rows)
        if m is not None and r is not None:
            raw_m[ticker], raw_r[ticker] = m, r
    m_scores = scoring.percentile_scores(raw_m)
    r_scores = scoring.percentile_scores(raw_r, higher_is_better=False)
    total = sum(weights.values())
    return {t: ((weights.get("momentum", 0) * m_scores[t] + weights.get("risk", 0) * r_scores[t]) / total,
                m_scores[t], r_scores[t])
            for t in m_scores}


def run(db, first=date(2008, 1, 1), last=None, min_stocks=10, data=None, weights=WEIGHTS):
    """Monthly backtest. Returns {"periods": [...], "summary": {...}}.

    Each period: the ranking date, how many stocks were ranked, and per horizon the average return of
    the top fifth, bottom fifth and all stocks, plus the score's rank correlation with returns.
    """
    data = data or load_all(db)
    newest = max(series[0][-1] for series in data.values())
    last = last or newest
    periods = []
    day = date(first.year, first.month, 1)
    while day <= last:
        scores = score_on(data, day, weights)
        if len(scores) >= min_stocks:
            period = {"date": day.isoformat(), "stocks": len(scores), "horizons": {}}
            for months in HORIZONS:
                end = add_months(day, months)
                if end > newest:
                    continue
                returns = {}
                for ticker in scores:
                    start_price = price_on_or_after(data[ticker], day)
                    end_price = price_on_or_after(data[ticker], end)
                    if start_price and end_price and not has_jump(data[ticker], day, end):
                        returns[ticker] = end_price / start_price - 1
                if len(returns) < min_stocks:
                    continue
                ranked = sorted(returns, key=lambda t: -scores[t][0])
                size = max(1, round(len(ranked) * GROUP_SHARE))
                period["horizons"][months] = {
                    "top": mean(returns[t] for t in ranked[:size]),
                    "bottom": mean(returns[t] for t in ranked[-size:]),
                    "all": mean(returns.values()),
                    "ic": spearman([scores[t][0] for t in ranked], [returns[t] for t in ranked]),
                    "top_tickers": ranked[:size],
                }
            if period["horizons"]:
                periods.append(period)
        day = add_months(day, 1)
    return {"periods": periods, "summary": summarise(periods)}


def summarise(periods):
    """Per horizon: average returns, how often the top fifth beat the average stock, and the same
    figures after trading costs. Overlapping holding periods mean results aren't independent."""
    summary = {}
    for months in HORIZONS:
        rows = [p["horizons"][months] for p in periods if months in p["horizons"]]
        if not rows:
            continue
        top, bottom, avg = [r["top"] for r in rows], [r["bottom"] for r in rows], [r["all"] for r in rows]
        summary[months] = {
            "periods": len(rows),
            "first": next(p["date"] for p in periods if months in p["horizons"]),
            "top": mean(top), "bottom": mean(bottom), "all": mean(avg),
            "top_after_costs": mean(top) - ROUND_TRIP_COST,
            "all_after_costs": mean(avg) - ROUND_TRIP_COST,
            "top_beat_all": sum(t > a for t, a in zip(top, avg)) / len(rows),
            "top_beat_bottom": sum(t > b for t, b in zip(top, bottom)) / len(rows),
            "ic": mean(r["ic"] for r in rows),
        }
    return summary
