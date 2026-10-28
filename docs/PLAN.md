# nse-ranker: project plan

## Goal
When I run `python -m nse_ranker rank`, I get a ranked list of my NSE watchlist. Each stock gets a
0-100 score and a short reason, built from four inputs:
1. prices and fundamentals
2. Kenyan finance news and general Kenyan news that affects each stock
3. what people and well-known market analysts say online (X, Reddit, YouTube), collected with Agent-Reach
   and summarised by Claude Haiku through the `claude` CLI
4. a scoring model based on researched rules for what makes a stock worth buying

**Not in scope:** placing trades, or giving advice. This is a research tool, and every score has to show
where it came from.

## How it fits together

```
 sources                     store            analysis                     output
 -------                     -----            --------                     ------
 NSE prices      ─┐                           factor scores (formulas)  ─┐
 fundamentals    ─┼──▶  data/ (SQLite)  ──▶   news matched to stocks    ─┼──▶  rank report
 Kenyan news     ─┤                           Haiku: sentiment + events ─┘     (terminal + HTML)
 Agent-Reach / X ─┘
```

- **Formulas do the scoring. Haiku reads text.** Haiku turns news and posts into tags (stock, event type,
  positive or negative, source link). The formulas then turn those tags into points. An LLM never sets a
  score directly, because then nobody could check or backtest it.
- Every run is saved, so I can compare today's ranking with last week's and backtest the score later.

## The watchlist (72 tickers, from the 27 Oct 2026 heatmap)
ABSA, ALP, AMAC, ARM, BAMB, BAT, BKG, BOC, BRIT, CABL, CARB, CGEN, CIC, COOP, CRWN, CTUM, DCON, DTK,
EABL, EGAD, EQTY, EVRD, FMLY, FTGH, GLD, HAFR, HBE, HFCB, HFCK, IMH, JUB, KAPC, KCB, KEGN, KNRE, KPC,
KPLC, KPLC-P4, KPLC-P7, KQ, KUKZ, KURV, LAPR, LBTY, LIMT, LKL, MSC, NBV, NCBA, NMG, NSE, OCH, PORT,
SASN, SBIC, SCAN, SCBK, SCOM, SGL, SKL, SLAM, SMER, SMWF, TCL, TOTL, TPSE, TRFC, UCHM, UMME, UNGA,
WTK, XPRS

Not all of these are ordinary shares. GLD and SMWF are ETFs, KPLC-P4 and KPLC-P7 are preference shares,
and some (LAPR, TRFC and others) may be REITs or other products. They are scored separately or left out.
Thinly traded and suspended counters get flagged instead of ranked. Phase 2 checks each one.

## Research (before any scoring code)
All findings go in `docs/RESEARCH.md` with a source link for each claim.

**R1. What makes a stock worth buying.** Compare the main approaches (value, quality, dividend,
momentum, low volatility, growth) and find which have evidence in frontier and African markets, not
just the US. Expected result: 5-7 factors, each with a formula and a reason. Likely candidates:
- Value: P/E, P/B, compared within the sector
- Dividend: yield, and whether earnings cover the dividend
- Quality: ROE, earnings stability, debt
- Momentum: 3-12 month return
- Liquidity: average daily traded value (a gate, not a bonus, because thin NSE counters are hard to exit)
- News: events from Kenyan news (results, dividends, policy changes), a small capped weight
- Online opinion: what analysts and people say on X, Reddit and YouTube. **This gets the lowest weight of
  any factor.** It can nudge a score but never decide a ranking on its own, and "an analyst said buy" is
  never shown as the reason to buy.

**R2. What drives each stock.** Write a short profile per stock: business, sector, main drivers and the
news to watch. Group them by sector, since most drivers are shared:
- Banks: Central Bank Rate, government bond yields, non-performing loans, credit growth, dividend policy
- Telecoms (SCOM): M-Pesa growth, Ethiopia business, regulation, the shilling
- Insurance: claims, investment income, IFRS 17
- Tea and agriculture: auction prices, weather, the shilling, export demand
- Energy and utilities: power tariffs set by EPRA, fuel prices, government ownership and dividends
- Manufacturing and consumer: excise duty, Finance Bill changes, input costs, consumer spending
- Construction: infrastructure spending, cement demand
- Macro (affects everything): inflation, the shilling, Treasury bill rates, foreign investor flows,
  elections, IMF programme news

**R3. Data sources.** For each source, check what it offers, whether it's free, and whether scraping it is
allowed (robots.txt and terms):
- Prices: the NSE website, the NSE crawler found on GitHub (`kwoshvick/NSE-Stock-Price-Crawler`), and
  other sites that publish NSE prices
- Fundamentals: company annual reports and results announcements
- News: Business Daily, The Standard (business), The Star (business), Nation, Capital FM Business,
  Kenyan Wall Street, plus general news feeds for macro and policy stories

**R4. Who to listen to online.** Build a list of Kenyan market analysts and finance accounts on X, plus
active Reddit and YouTube sources, with the reason each one is worth following. Agent-Reach collects
their posts; Haiku summarises them. Their views feed only the online-opinion factor, which has the
lowest weight (see R1). They're a signal to check, not a reason to buy.

## Build sections (one commit each)
| # | Section | Built | Done when |
|---|---|---|---|
| 1 | Scaffold | README, folders, package | `python -m nse_ranker` runs |
| 2 | Watchlist and profiles | `watchlist.toml` with ticker, name, sector, type, drivers | all 72 checked and tagged |
| 3 | Price data | price fetcher, SQLite store | a year of daily prices for every listed counter |
| 4 | Scoring criteria | factor functions, weights from R1 | each factor tested on sample numbers |
| 5 | Rank command | `rank` prints a table with score and reasons | ranking runs from stored data in seconds |
| 6 | News scraper | per-site scrapers, matched to tickers and sectors | a day's articles stored and tagged |
| 7 | Haiku insights | Agent-Reach collection, `claude -p --model haiku` summaries, cache | each stock gets cited sentiment and events |
| 8 | Backtest | replay old scores against later returns | a report showing whether high scores beat low ones |

The project is useful from section 5 on (prices and formulas only). Sections 6-8 make it better.

## How the Haiku step works
1. Agent-Reach fetches posts and articles for a stock or sector and saves them as text.
2. `claude -p --model haiku` reads that text with a fixed prompt and returns JSON:
   `{ticker, event, direction, strength, quote, url}`.
3. Python checks the JSON. Any item without a source link gets dropped.
4. Results are cached by URL so the same article is never paid for twice.

## Risks and how to handle them
- **Sites change or block scraping.** Keep one small scraper per site, and fail gracefully so the ranking
  still runs without that source.
- **Following the crowd.** Online "buy" calls are often hype or paid promotion. That's why online
  opinion has the lowest weight and can't push a stock up the ranking by itself.
- **X access can break.** X works through Agent-Reach today, but cookies expire. If X fails, the run
  skips it and says so in the report.
- **Thin trading.** Many NSE counters barely trade, so prices and momentum can mislead. The liquidity gate
  handles this.
- **LLM mistakes.** Haiku only tags text that comes with a link, the formulas cap how much news can move
  a score, and the report shows the quote it relied on.
- **Cost.** Haiku is cheap, but daily runs over 72 stocks add up. The cache, plus summarising by sector
  rather than per stock where possible, keeps it low.

## Setup still needed
- Python packages: `requests`, `beautifulsoup4`, `pandas` (not installed yet). The watchlist uses TOML, which
  Python 3.11 reads with the built-in `tomllib`.
- Git: public GitHub repo; each section is committed and pushed as it's finished.
