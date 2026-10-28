# nse-ranker

A personal research tool that ranks my Nairobi Securities Exchange (NSE) watchlist on demand.

> Research tool only. It ranks stocks using public data and news; it is not financial advice.

## What it does (planned)
1. **Prices**: daily NSE prices for the watchlist.
2. **News**: scrapes Kenyan newspaper finance pages and general Kenyan news that could move specific stocks.
3. **Chatter**: uses Agent-Reach plus Claude Haiku (via the `claude` CLI) to summarise what people say, including analysts on X.
4. **Criteria**: a scoring model built from researched rules for what makes a stock worth buying.
5. **Rank**: `python -m nse_ranker rank` prints a scored list each time I ask.

Full plan: [docs/PLAN.md](docs/PLAN.md)

## Usage
```
python -m nse_ranker watchlist          # the 72 counters and their status
python -m nse_ranker prices history     # load 2007-2025 daily prices (once, ~2 min)
python -m nse_ranker prices eodhd       # fill 2026 from EODHD (needs EODHD_API_KEY in .env)
python -m nse_ranker prices recent      # last ~2 weeks from afx (1 stock a minute)
python -m nse_ranker prices update      # today's closes, after 15:30 Nairobi time
python -m nse_ranker prices status      # what's stored
python -m nse_ranker news fetch         # read the news feeds in news.toml (run daily)
python -m nse_ranker news show KCB      # one stock's news; without a ticker, mentions per stock
python -m nse_ranker news tag           # Haiku reads and tags new articles (rank also does this)
python -m nse_ranker opinion fetch      # Reddit and X posts per stock, summarised by Haiku
python -m nse_ranker rank               # ranked list with Haiku's review (--top N, --no-save, --no-ai)
python -m unittest                      # tests
```
Prices and articles are stored in `data/nse.sqlite` (not committed). The feeds only hold the last day
or two of stories, so news builds up from the day you start running `news fetch`.

### How Haiku is used
Haiku runs through the `claude` CLI (`claude -p --model haiku`), with no tools, and replies in checked JSON.
1. **News tags:** Haiku reads matched articles and tags each one: stock or sector, good or bad, how strong,
   and an exact quote. Tags whose quote isn't in the article are dropped. Each article is read once.
   Business Daily and Nation text is never sent (their sites say reference use only).
2. **Online opinion:** the newest posts in r/nsekenya, r/Kenya and r/nairobi (OpenCLI, through your logged-in Chrome) and X (Agent-Reach's
   `twitter`, with `TWITTER_AUTH_TOKEN` and `TWITTER_CT0` in `.env`). Haiku summarises them and flags hype.
   It's the lowest-weight factor (3 points), and hype counts half.
3. **Review ("does it make sense to buy?"):** Haiku explains every stock's score and rates the case as
   strong, mixed or weak. It may move a stock up to 5 places from the formula order. A move must cite news
   or opinion, since the factor numbers are already in the score, and a move backed only by online opinion
   is capped at 1 place. Both the formula position and the final position are shown.

## Data credits
- Historical prices 2007-2025: Wanjawa, B., *Kenya Nairobi Securities Exchange (NSE) All Stocks Prices*,
  Mendeley Data, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Compiled from MyStocks
  (Synergy Systems Ltd.), licensed by the NSE.
- 2026 prices: [EODHD](https://eodhd.com/) end-of-day API (free plan). Some days arrive 10x or 100x
  too high; `sources/eodhd.py` repairs them.
- Recent prices: [afx.kwayisi.org](https://afx.kwayisi.org/nse/), fetched at most once a minute as its robots.txt asks.

## Roadmap (built in sections, one commit each)
- [x] 1. Project scaffold
- [x] 2. Watchlist and stock profiles (what drives each stock)
- [x] 3. Price data layer
- [x] 4. Scoring criteria (researched)
- [x] 5. Ranking command
- [x] 6. Kenyan news scraper
- [x] 7. Haiku insight layer (Agent-Reach, Reddit, X)
- [ ] 8. Backtest the score
