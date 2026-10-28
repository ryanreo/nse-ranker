"""Turn prices and fundamentals into factor scores and one weighted score per stock.

The factors, weights and the evidence behind them are in docs/RESEARCH.md (R1).
Momentum and risk were rebalanced from 25:10 to 15:20 after the backtest (docs/BACKTEST.md):
calm prices beat the market more reliably on the NSE than past winners did.
Every factor score is 0-100, ranked against the other stocks that pass the liquidity gate.
A factor with no data for a stock is left out, and the other weights are scaled up to fill in.
"""
from statistics import median, pstdev

WEIGHTS = {
    "momentum": 15,
    "value": 20,
    "dividend": 20,
    "quality": 15,
    "risk": 20,
    "news": 7,
    "opinion": 3,   # online chatter: the lowest weight, never decides a ranking
}

# Liquidity gate: only rank stocks you could actually buy and sell.
LIQUIDITY_DAYS = 60
MIN_TRADED_VALUE = 100_000    # KES a day, on average
MIN_TRADED_SHARE = 0.5        # traded on at least half of those days

MOMENTUM_LOOKBACK = 126       # about 6 months of trading days
MOMENTUM_SKIP = 21            # leave out the most recent month (short-term reversals)
RISK_DAYS = 126
MIN_RISK_DAYS = 60
MIN_SECTOR_PEERS = 3          # fewer peers than this: compare value with the whole market

# Above these, the figures are almost certainly a data error (wrong currency or units), not a bargain.
MAX_EARNINGS_YIELD = 0.50     # a P/E under 2
MAX_DIVIDEND_YIELD = 0.25


# ---- Raw measures. `rows` is [(date, close, volume), ...], oldest first. ----

def liquidity(rows):
    """(average KES traded a day, share of days with any trades) over the last 60 days."""
    recent = rows[-LIQUIDITY_DAYS:]
    if not recent:
        return 0.0, 0.0
    traded_value = sum(close * volume for _, close, volume in recent) / len(recent)
    traded_share = sum(1 for _, _, volume in recent if volume > 0) / len(recent)
    return traded_value, traded_share


def liquidity_problem(rows):
    """None if the stock trades enough to rank, otherwise a short reason why not."""
    value, share = liquidity(rows)
    if value < MIN_TRADED_VALUE:
        return f"thin trading: KES {value:,.0f} a day (need {MIN_TRADED_VALUE:,})"
    if share < MIN_TRADED_SHARE:
        return f"trades on only {share:.0%} of days"
    return None


def momentum(rows):
    """Price return from ~6 months ago to ~1 month ago. None if there isn't enough history."""
    if len(rows) <= MOMENTUM_LOOKBACK:
        return None
    start = rows[-1 - MOMENTUM_LOOKBACK][1]
    end = rows[-1 - MOMENTUM_SKIP][1]
    return end / start - 1


def volatility(rows):
    """Standard deviation of daily returns over the last ~6 months. Lower is calmer."""
    closes = [close for _, close, _ in rows[-RISK_DAYS - 1:]]
    if len(closes) <= MIN_RISK_DAYS:
        return None
    returns = [b / a - 1 for a, b in zip(closes, closes[1:])]
    return pstdev(returns)


def earnings_yield(eps, price):
    """EPS / price: the inverse of P/E, so it still works for loss-makers (it goes negative)."""
    if eps is None or not price or eps / price > MAX_EARNINGS_YIELD:
        return None
    return eps / price


def covered_yield(eps, dps, price):
    """Dividend yield, counting only the part of the dividend that earnings cover."""
    if eps is None or dps is None or not price:
        return None
    if eps <= 0:
        return 0.0
    covered = min(dps, eps) / price
    return covered if covered <= MAX_DIVIDEND_YIELD else None


def eps_growth(eps_changes):
    """Change between the last two different EPS figures seen. None until results change."""
    if len(eps_changes) < 2:
        return None
    old, new = eps_changes[-2][1], eps_changes[-1][1]
    if not old:
        return None
    return (new - old) / abs(old)


# ---- Turning raw measures into 0-100 scores ----

def percentile_scores(raw, higher_is_better=True):
    """{ticker: number or None} -> {ticker: 0-100}. Stocks with None are left out.

    The best gets 100, the worst 0, ties share a score. A single stock gets 50.
    """
    values = {t: v for t, v in raw.items() if v is not None}
    if len(values) == 1:
        return {t: 50.0 for t in values}
    ordered = sorted(values.values(), reverse=not higher_is_better)
    scores = {}
    for ticker, value in values.items():
        below = sum(1 for v in ordered if (v < value if higher_is_better else v > value))
        equal = ordered.count(value)
        scores[ticker] = 100 * (below + (equal - 1) / 2) / (len(ordered) - 1)
    return scores


def relative_to_sector(raw, sectors):
    """Subtract each stock's sector median, so banks are compared with banks.

    Sectors with fewer than MIN_SECTOR_PEERS stocks are compared with the whole market.
    """
    values = {t: v for t, v in raw.items() if v is not None}
    if not values:
        return {}
    market = median(values.values())
    relative = {}
    for ticker, value in values.items():
        peers = [v for t, v in values.items() if sectors[t] == sectors[ticker]]
        relative[ticker] = value - (median(peers) if len(peers) >= MIN_SECTOR_PEERS else market)
    return relative


def score_all(stocks):
    """Score a list of stocks. Each stock is a dict with:
        ticker, sector, rows [(date, close, volume)...], eps, dps,
        eps_changes [(date, eps, dps)...], and optional news / opinion (0-100).

    Returns a list of results, best first:
        {ticker, score, factors {name: 0-100 or None}, raw {...}, excluded: reason or None}
    Stocks that fail the liquidity gate come last, with score None and the reason.
    """
    ranked, excluded = [], []
    for stock in stocks:
        problem = liquidity_problem(stock["rows"])
        (excluded if problem else ranked).append((stock, problem))
    ranked = [stock for stock, _ in ranked]

    price = {s["ticker"]: s["rows"][-1][1] for s in ranked}
    sectors = {s["ticker"]: s["sector"] for s in ranked}
    raw = {
        "momentum": {s["ticker"]: momentum(s["rows"]) for s in ranked},
        "value": {s["ticker"]: earnings_yield(s.get("eps"), price[s["ticker"]]) for s in ranked},
        "dividend": {s["ticker"]: covered_yield(s.get("eps"), s.get("dps"), price[s["ticker"]]) for s in ranked},
        "quality": {s["ticker"]: eps_growth(s.get("eps_changes", [])) for s in ranked},
        "risk": {s["ticker"]: volatility(s["rows"]) for s in ranked},
        "news": {s["ticker"]: s.get("news") for s in ranked},
        "opinion": {s["ticker"]: s.get("opinion") for s in ranked},
    }
    factor_scores = {
        "momentum": percentile_scores(raw["momentum"]),
        "value": percentile_scores(relative_to_sector(raw["value"], sectors)),
        "dividend": percentile_scores(raw["dividend"]),
        "quality": percentile_scores(raw["quality"]),
        "risk": percentile_scores(raw["risk"], higher_is_better=False),
        # news and opinion arrive already on a 0-100 scale
        "news": {t: v for t, v in raw["news"].items() if v is not None},
        "opinion": {t: v for t, v in raw["opinion"].items() if v is not None},
    }

    results = []
    for stock in ranked:
        ticker = stock["ticker"]
        factors = {name: factor_scores[name].get(ticker) for name in WEIGHTS}
        used = {name: s for name, s in factors.items() if s is not None}
        weight = sum(WEIGHTS[name] for name in used)
        score = sum(WEIGHTS[name] * s for name, s in used.items()) / weight if weight else None
        results.append({
            "ticker": ticker, "score": score, "factors": factors,
            "raw": {name: raw[name][ticker] for name in raw}, "weight_used": weight,
            "excluded": None,
        })
    results.sort(key=lambda r: -(r["score"] or 0))
    for stock, problem in excluded:
        results.append({"ticker": stock["ticker"], "score": None, "factors": {}, "raw": {},
                        "weight_used": 0, "excluded": problem})
    return results
