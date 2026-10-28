"""Haiku reviews the formula ranking: it explains each stock's score ("does it make sense to buy?")
and may move a stock a few places when the news or online opinion justifies it.

Rules, enforced here rather than trusted to the prompt:
- A move is at most MAX_MOVE places.
- A move must cite news or opinion evidence. The factor scores are already in the formula,
  so citing only them can't move a stock (that would count them twice).
- A move backed only by online opinion is capped at OPINION_MAX_MOVE place.
"""
import hashlib
import json
from datetime import date

from . import haiku

MAX_MOVE = 5
OPINION_MAX_MOVE = 1
BATCH = 16   # stocks per Haiku call
CASES = ("strong", "mixed", "weak")

SCHEMA = """
CREATE TABLE IF NOT EXISTS reviews (
    key      TEXT PRIMARY KEY,   -- hash of everything Haiku was shown
    date     TEXT NOT NULL,
    verdicts TEXT NOT NULL       -- JSON {ticker: verdict}
);
"""

INSTRUCTIONS = f"""You are a careful equity research assistant reviewing a ranking of Nairobi Securities Exchange
stocks. Each stock comes with its formula rank, total score (0-100), factor scores (0-100, higher is better;
risk 100 = calmest), raw figures, suggested hold time, recent news tags (ids N...) and an online-opinion
summary (id O:TICKER). Factor names (momentum, value, dividend, quality, risk) are also valid evidence ids.

How the factors work, so you can explain them correctly:
- momentum: price change from about 6 months ago to 1 month ago, ranked against the other stocks.
- value: earnings yield (1/PE) compared with the stock's own sector median, so a P/E is only "cheap" or
  "expensive" relative to its sector; don't compare P/Es across sectors.
- dividend: yield counting only the part of the dividend that earnings cover.
- quality: EPS growth between two results. null means a second EPS reading hasn't been collected yet,
  not that earnings are poor.
- risk: how much the price moves day to day; 100 is calmest.
- A null factor is missing data and is left out of the score, not counted as zero.
The score is the weighted average of the available factors: momentum 25, value 20, dividend 20,
quality 15, risk 10, news 7, online opinion 3.

For EVERY stock, answer "does it make sense to buy?":
- case: how well the data supports owning it, using these definitions:
  "strong" = score 70+, at least three factors at 60+, and no clearly negative recent news;
  "weak" = score under 55, or the score rests on a single factor, or clearly negative recent news;
  "mixed" = everything in between.
- explanation: 2-3 plain sentences explaining why it got this score: what drives it, what counts against it,
  and any news that matters. Mention the hold time if it helps. No hype, no certainty, no price targets.
- move: an integer from -{MAX_MOVE} to {MAX_MOVE}. Positive moves it UP the ranking. Use 0 unless recent news
  (or, much less, online opinion) gives a concrete reason the formula can't see, such as a takeover, a
  profit warning or a dividend cut.
- evidence: the ids you relied on.
Online opinion is the weakest evidence: never move a stock because people online like it.
This is research to help a person decide, not investment advice."""

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {"verdicts": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "ticker": {"type": "string"},
            "case": {"type": "string", "enum": list(CASES)},
            "explanation": {"type": "string"},
            "move": {"type": "integer", "minimum": -MAX_MOVE, "maximum": MAX_MOVE},
            "evidence": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["ticker", "case", "explanation", "move", "evidence"],
    }}},
    "required": ["verdicts"],
}

FACTORS = ("momentum", "value", "dividend", "quality", "risk")


def stock_brief(position, result, tags, reading):
    """The compact picture of one stock that Haiku sees."""
    raw = result["raw"]
    return {
        "ticker": result["ticker"], "name": result["name"], "formula_rank": position,
        "score": round(result["score"], 1), "hold": result["hold"],
        "factors": {f: None if result["factors"][f] is None else round(result["factors"][f]) for f in FACTORS},
        "figures": {
            "six_month_return": None if raw["momentum"] is None else f"{raw['momentum']:+.0%}",
            "pe": round(1 / raw["value"], 1) if raw["value"] and raw["value"] > 0 else None,
            "covered_dividend_yield": None if raw["dividend"] is None else f"{raw['dividend']:.1%}",
            "typical_daily_move": None if raw["risk"] is None else f"{raw['risk']:.1%}",
            "price": result["price"],
        },
        "news": [{"id": f"N{t['id']}", "date": t["published"][:10], "about": t["ticker"] or t["sector"],
                  "event": t["event"], "direction": t["direction"], "strength": t["strength"]} for t in tags],
        "opinion": None if not reading else {
            "id": f"O:{result['ticker']}", "posts": reading["posts"], "sentiment": round(reading["sentiment"], 2),
            "hype": reading["hype"], "summary": reading["summary"]},
    }


def check_verdict(verdict, brief):
    """Apply the rules: valid evidence only, moves need news or opinion, opinion alone moves 1 place."""
    allowed = set(FACTORS) | {n["id"] for n in brief["news"]}
    if brief["opinion"]:
        allowed.add(brief["opinion"]["id"])
    evidence = [e for e in verdict.get("evidence", []) if e in allowed]
    move = max(-MAX_MOVE, min(MAX_MOVE, int(verdict.get("move", 0))))
    news = [e for e in evidence if e.startswith("N")]
    opinion = [e for e in evidence if e.startswith("O:")]
    if not news and not opinion:
        move = 0
    elif not news:
        move = max(-OPINION_MAX_MOVE, min(OPINION_MAX_MOVE, move))
    case = verdict.get("case") if verdict.get("case") in CASES else "mixed"
    return {"case": case, "explanation": verdict.get("explanation", "").strip(), "move": move, "evidence": evidence}


def final_order(ranked, verdicts):
    """Formula order shifted by each stock's move.

    When stocks aim for the same place, one moving up goes ahead of one that stayed, and one
    moving down goes behind it; otherwise the formula order decides.
    """
    keyed = []
    for position, result in enumerate(ranked, 1):
        move = verdicts.get(result["ticker"], {}).get("move", 0)
        keyed.append(((position - move, -move, position), result))
    return [result for _, result in sorted(keyed, key=lambda k: k[0])]


def review(db, ranked, tags_by_ticker, readings, ask=haiku.ask, progress=print):
    """{ticker: verdict} for every ranked stock. Reuses the stored review if nothing changed."""
    db.executescript(SCHEMA)
    briefs = [stock_brief(i, r, tags_by_ticker.get(r["ticker"], []), readings.get(r["ticker"]))
              for i, r in enumerate(ranked, 1)]
    # Redo the review if the stocks, the news or the instructions change.
    key = hashlib.sha256(json.dumps([INSTRUCTIONS, briefs], sort_keys=True, default=str).encode()).hexdigest()
    cached = db.execute("SELECT verdicts FROM reviews WHERE key = ?", (key,)).fetchone()
    if cached:
        return json.loads(cached[0])

    verdicts = {}
    for start in range(0, len(briefs), BATCH):
        chunk = briefs[start:start + BATCH]
        progress(f"  Haiku reviewing stocks {start + 1}-{start + len(chunk)} of {len(briefs)}...")
        by_ticker = {b["ticker"]: b for b in chunk}
        for verdict in ask(INSTRUCTIONS, {"stocks": chunk}, REVIEW_SCHEMA)["verdicts"]:
            if verdict.get("ticker") in by_ticker:
                verdicts[verdict["ticker"]] = check_verdict(verdict, by_ticker[verdict["ticker"]])
    db.execute("INSERT OR REPLACE INTO reviews VALUES (?, ?, ?)",
               (key, date.today().isoformat(), json.dumps(verdicts)))
    db.commit()
    return verdicts
