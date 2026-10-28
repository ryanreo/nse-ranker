# Backtest (section 8)

Run with `python -m nse_ranker backtest`. Results below are from 28 Oct 2026.

## What was tested
Only the **price-based factors**, momentum and risk (35 of the 100 weight points), plus the liquidity gate.
Value, dividend and quality need past EPS and dividends, which we don't have; news and online opinion only
exist from now on. So this tests part of the score, not all of it.

**Method:** on the first trading day of each month from January 2008, score every stock that passes the
liquidity gate, using only data up to that day. Then measure each stock's price change over the next 1, 3, 6
and 12 months, and compare the top fifth by score, the bottom fifth and the average stock (equal-weighted).
- Stocks later delisted are included while they traded, so this isn't a test on survivors only.
- Prices aren't adjusted for bonus issues and splits, so a stock with a one-day move over 45% in the window
  is left out of that month.
- Between 13 and 50 stocks were rankable each month.

## Results (current weights, momentum 25 : risk 10)

| Hold | Months tested | Top fifth | Average stock | Bottom fifth | Top beat average | Rank correlation |
|---|---|---|---|---|---|---|
| 1 month | 225 | +0.9% | +0.4% | −0.0% | 55% | 0.07 |
| 3 months | 223 | +2.0% | +1.2% | −0.1% | 57% | 0.09 |
| 6 months | 220 | +4.5% | +2.7% | +1.0% | 58% | 0.10 |
| 12 months | 214 | +9.7% | +7.0% | +2.3% | 62% | 0.11 |

After a 2% round-trip trading cost, the top fifth still gains at 6 months (+2.5%) and 12 months (+7.7%), but
not at 1 month (−1.1%). **Short holds don't pay on the NSE**: the edge is smaller than the cost of trading.

**Stable over time.** Split in two: 2008–2016 the top fifth beat the average by 2.1 points over 6 months,
and 2017–2026 by 1.5 points. Weaker lately, still positive.

## Which factor does the work

| Score from | 3-month edge | 6-month edge | 12-month edge | Beat average (12 mo) |
|---|---|---|---|---|
| Momentum + risk (25:10) | +0.9% | +1.8% | +2.8% | 62% |
| Momentum only | −0.2% | +0.6% | +2.1% | 53% |
| Risk only (calm prices) | +1.4% | +1.5% | +2.0% | 58% |

- **Calm, steady stocks beat jumpy ones more reliably than past winners beat past losers.** Low volatility is
  the stronger factor on the NSE in this test.
- **Momentum only pays over about 12 months.** Over 3 months, past winners did no better than average. This
  contradicts the "3–6 months" hold time the ranking gives momentum-led stocks.
- Together they work better than either alone.

## Weights chosen on 2008–2016, checked on 2017–2026

To avoid fitting the weights to luck, each mix was judged on 2008–2016 and then checked on the later years
it never saw.

| Momentum : risk | 2008–16 edge (12 mo) | 2008–16 beat | 2017–26 edge (12 mo) | 2017–26 beat (3 / 6 / 12 mo) |
|---|---|---|---|---|
| 25 : 10 (current) | +3.3% | 65% | +2.3% | 55% / 58% / 58% |
| 20 : 15 | +4.2% | 72% | +2.0% | 63% / 58% / 62% |
| 15 : 20 | +4.4% | 72% | +1.8% | 61% / 62% / 62% |
| 10 : 25 | +4.3% | 66% | +1.2% | 60% / 63% / 61% |

15:20 did best on 2008–2016, and on 2017–2026 it beat the average stock more often than the current 25:10
at every hold (61–62% against 55–58%), though its average edge at 12 months was a little lower.

## Recommendations
Recommendations 1 and 2 were applied on 28 Oct 2026.

1. **Shift weight from momentum to risk**: momentum 15, risk 20 (total unchanged at 35).
2. **Change momentum's hold time from 3–6 months to 6–12 months.**
3. **Hold at least 6 months.** Re-ranking monthly is fine for watching, but trading on monthly changes loses
   the edge to costs.

## Limits
- Price returns only; dividends aren't included, which understates high-yield stocks.
- Overlapping holding periods (a 12-month hold starting every month) mean the months aren't independent, so
  the effective sample is closer to 18 years than 214 months.
- A small market: 13–50 stocks a month, so a top fifth is 3–10 stocks.
- The liquidity threshold is in today's shillings, applied to all years.
- Past results don't guarantee future ones. This is research, not investment advice.
