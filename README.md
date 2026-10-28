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

## Roadmap (built in sections, one commit each)
- [x] 1. Project scaffold
- [ ] 2. Watchlist and stock profiles (what drives each stock)
- [ ] 3. Price data layer
- [ ] 4. Scoring criteria (researched)
- [ ] 5. Ranking command
- [ ] 6. Kenyan news scraper
- [ ] 7. Haiku insight layer (Agent-Reach, X)
- [ ] 8. Backtest the score
