"""Command line: python -m nse_ranker <command>"""
import argparse
import textwrap
from collections import Counter
from datetime import date

from . import haiku, insights, news, opinion, prices, ranking, review, store
from .watchlist import load_watchlist, rankable

STALE_AFTER_DAYS = 4   # warn if the newest price is older than this


def show_watchlist():
    """Print how many stocks have each status, then one line per stock."""
    stocks = load_watchlist()
    counts = Counter(stock["status"] for stock in stocks)
    print(f"{len(stocks)} stocks: {counts['rank']} rank, {counts['watch']} watch, {counts['out']} out")
    print(f"rankable() returned {len(rankable(stocks))} stocks (should be {counts['rank']})")
    print()
    for stock in stocks:
        print(f"{stock['ticker']:<8} {stock['status']:<6} {stock['currency']}  "
              f"{stock['sector']:<30} {stock['name']}")


def show_prices_status(db):
    rows, tickers, first, last = store.summary(db)
    print(f"{rows:,} price rows for {tickers} tickers, {first} to {last}")
    print()
    print("Last 12 months, per watchlist stock (excluding 'out'):")
    print(f"{'ticker':<8} {'days':>5} {'traded':>7}  last date")
    for item in prices.coverage(db):
        print(f"{item['ticker']:<8} {item['days']:>5} {item['traded_days']:>7}  {item['last'] or '-'}")


def _cell(score):
    return f"{score:4.0f}" if score is not None else "   -"


def show_ranking(db, top, save, use_ai):
    """Print the ranked list with factor scores, Haiku's review and reasons, then what was left out."""
    today = date.today()
    ai_problem = None
    if use_ai:
        try:
            print("Haiku is reading new articles...")
            read, kept = insights.tag_pending(db, load_watchlist(), progress=lambda m: print(m))
            if not read:
                print("  no new articles")
        except haiku.HaikuError as error:
            ai_problem = str(error)
    results, tags_by_ticker, readings = ranking.rank(db, today)
    ranked = [r for r in results if r["score"] is not None]
    verdicts = {}
    if use_ai and not ai_problem:
        try:
            verdicts = review.review(db, ranked, tags_by_ticker, readings)
        except haiku.HaikuError as error:
            ai_problem = str(error)
    formula_position = {r["ticker"]: i for i, r in enumerate(ranked, 1)}
    ranked = review.final_order(ranked, verdicts) if verdicts else ranked
    before = ranking.previous_positions(db, today.isoformat())
    if save:
        ranking.save_run(db, ranked + [r for r in results if r["score"] is None], today.isoformat())

    newest = max(r["price_date"] for r in results)
    print()
    print(f"NSE ranking, {today:%d %b %Y}  (prices up to {newest})")
    print("A research tool, not financial advice.")
    if (today - date.fromisoformat(newest)).days > STALE_AFTER_DAYS:
        print(f"! Prices are more than {STALE_AFTER_DAYS} days old: run `prices update` after 15:30.")
    if ai_problem:
        print(f"! Haiku review skipped: {ai_problem}")
    elif not use_ai:
        print("Formula order only (--no-ai).")
    print()
    print(f"{'#':>3}  {'Ticker':<6} {'Score':>5}  {'Mom':>4} {'Val':>4} {'Div':>4} {'Qua':>4} {'Risk':>4}"
          f" {'News':>4} {'Opin':>4}  {'Price':>9}  {'Formula':>7}  {'vs last':>7}  Hold")
    for position, r in enumerate(ranked[:top], 1):
        f = r["factors"]
        since_last = "new" if r["ticker"] not in before else f"{before[r['ticker']] - position:+d}"
        print(f"{position:>3}  {r['ticker']:<6} {r['score']:5.1f}  {_cell(f['momentum'])} {_cell(f['value'])} "
              f"{_cell(f['dividend'])} {_cell(f['quality'])} {_cell(f['risk'])} {_cell(f['news'])} "
              f"{_cell(f['opinion'])}  {r['price']:>9,.2f}  {'#' + str(formula_position[r['ticker']]):>7}"
              f"  {since_last:>7}  {r['hold'] or '-'}")
        print(f"{'':6}{r['name']}. Formula: " + ("; ".join(r["reasons"]) or "no standout factor"))
        verdict = verdicts.get(r["ticker"])
        if verdict:
            moved = (f" Haiku moved it {abs(verdict['move'])} place{'s' if abs(verdict['move']) > 1 else ''} "
                     f"{'up' if verdict['move'] > 0 else 'down'}." if verdict["move"] else "")
            text = f"Does it make sense to buy? {verdict['case'].capitalize()} case.{moved} {verdict['explanation']}"
            print(textwrap.fill(text, width=110, initial_indent=" " * 6, subsequent_indent=" " * 6))
            news_ids = [e for e in verdict["evidence"] if e.startswith("N")]
            for tag in tags_by_ticker.get(r["ticker"], []):
                if f"N{tag['id']}" in news_ids:
                    print(f"{'':8}N{tag['id']} {tag['published'][:10]} {tag['title'][:70]}  {tag['url']}")
        print()
    if len(ranked) > top:
        print(f"... and {len(ranked) - top} more (use --top {len(ranked)} to see all).")
        print()
    print("Hold: a guide from what drives each score (momentum 3-6 months, earnings growth and calm")
    print("prices 6-12 months, cheapness and dividends 12+ months). Re-rank monthly; if a stock drops")
    print("out of the top half, the reason you bought it has probably faded.")
    print("Formula: the position from the scores alone. Haiku can move a stock up to 5 places, only")
    print("when news (or, at most 1 place, online opinion) gives a reason the numbers can't see.")
    if not readings:
        print("Online opinion: none yet. Run `opinion fetch` once Reddit and/or X are set up.")

    left_out = [r for r in results if r["score"] is None]
    if left_out:
        print()
        print("Not ranked (too thinly traded to buy and sell easily):")
        for r in left_out:
            print(f"  {r['ticker']:<6} {r['excluded']}")
    no_eps = [r["ticker"] for r in ranked if r["factors"]["value"] is None]
    if no_eps:
        print()
        print(f"No EPS data yet for {len(no_eps)} stocks, so value and dividend are left out for: "
              + ", ".join(no_eps))
        print("Fill it with `prices recent` (about a minute per stock).")
    watch = [s["ticker"] for s in load_watchlist() if s["status"] == "watch"]
    print()
    print("On the watch list, not ranked: " + ", ".join(watch))


def show_news(db, ticker, days):
    """One stock's news (direct mentions, then sector topics), or a count per stock."""
    if not ticker:
        counts = news.summary(db, days)
        print(f"Stocks named in the news, last {days} days:")
        for name, count in counts.items():
            print(f"  {name:<6} {count}")
        if not counts:
            print("  none yet: run `news fetch`")
        return
    stock = next((s for s in load_watchlist() if s["ticker"] == ticker.upper()), None)
    if not stock:
        print(f"{ticker} isn't on the watchlist.")
        return
    direct, sector = news.for_stock(db, stock, days)
    print(f"{stock['ticker']} ({stock['name']}), last {days} days")
    print(f"\nNamed in {len(direct)} articles:")
    for a in direct:
        print(f"  {a['published'][:10]}  {a['title']}  [{a['source']}]\n               {a['url']}")
    print(f"\n{stock['sector']} topics in {len(sector)} articles:")
    for a in sector[:10]:
        print(f"  {a['published'][:10]}  {a['title']}  ({', '.join(a['topics'])})")
    if len(sector) > 10:
        print(f"  ... and {len(sector) - 10} more")


def main():
    parser = argparse.ArgumentParser(prog="nse_ranker", description="Rank my NSE watchlist.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("watchlist", help="list the stocks and their status")

    price_cmd = commands.add_parser("prices", help="fill or check the price store")
    price_actions = price_cmd.add_subparsers(dest="action", required=True)
    history = price_actions.add_parser("history", help="load 2007-2025 history from Mendeley")
    history.add_argument("--from", dest="first_year", type=int, default=2007)
    gap = price_actions.add_parser("eodhd", help="fill missing days from EODHD (1 API call per stock)")
    gap.add_argument("--from", dest="start", default="2026-01-01")
    gap.add_argument("--to", dest="end", default=date.today().isoformat())
    gap.add_argument("tickers", nargs="*", help="default: every stock that isn't 'out'")
    price_actions.add_parser("update", help="store today's closes from afx (after 15:30)")
    recent = price_actions.add_parser("recent", help="store the last ~2 weeks from afx (1 stock a minute)")
    recent.add_argument("tickers", nargs="*", help="default: every stock that isn't 'out'")
    price_actions.add_parser("status", help="show what's stored")

    news_cmd = commands.add_parser("news", help="fetch or read Kenyan news")
    news_actions = news_cmd.add_subparsers(dest="action", required=True)
    news_actions.add_parser("fetch", help="read every feed in news.toml and store new articles")
    show = news_actions.add_parser("show", help="news for one stock, or counts for all")
    show.add_argument("ticker", nargs="?")
    show.add_argument("--days", type=int, default=14)

    news_actions.add_parser("tag", help="have Haiku read and tag new matched articles")

    opinion_cmd = commands.add_parser("opinion", help="online opinion from Reddit and X")
    opinion_actions = opinion_cmd.add_subparsers(dest="action", required=True)
    opinion_actions.add_parser("fetch", help="search Reddit and X for each ranked stock; Haiku summarises")

    rank_cmd = commands.add_parser("rank", help="rank the watchlist from stored data")
    rank_cmd.add_argument("--top", type=int, default=20, help="how many to show (default 20)")
    rank_cmd.add_argument("--no-save", action="store_true", help="don't record this run")
    rank_cmd.add_argument("--no-ai", action="store_true", help="formula order only, no Haiku")

    args = parser.parse_args()

    if args.command == "watchlist":
        show_watchlist()
    elif args.command == "news":
        db = store.connect()
        if args.action == "fetch":
            for source, (items, new) in news.fetch_all(db).items():
                print(f"  {source}: {items} items, {new} new")
        elif args.action == "tag":
            read, kept = insights.tag_pending(db, load_watchlist())
            print(f"Haiku read {read} articles and kept {kept} tags.")
        else:
            show_news(db, args.ticker, args.days)
    elif args.command == "opinion":
        db = store.connect()
        ranked = [s for s in load_watchlist() if s["status"] == "rank"]
        problems = opinion.collect(db, ranked)
        for problem in problems:
            print(f"! {problem}")
        print(f"Opinion stored for {len(opinion.latest(db))} stocks.")
    elif args.command == "rank":
        show_ranking(store.connect(), args.top, save=not args.no_save, use_ai=not args.no_ai)
    elif args.command == "prices":
        db = store.connect()
        if args.action == "history":
            print(f"Loading Mendeley history from {args.first_year}...")
            print(f"Stored {prices.load_history(db, args.first_year):,} rows.")
        elif args.action == "eodhd":
            tickers = args.tickers or [s["ticker"] for s in load_watchlist() if s["status"] != "out"]
            print(f"Filling {args.start} to {args.end} from EODHD: {len(tickers)} API calls...")
            print(f"Stored {prices.fill_from_eodhd(db, tickers, args.start, args.end):,} rows.")
        elif args.action == "update":
            count = prices.update_latest(db)
            print(f"Stored {count} closes." if count else "Market not closed yet (after 15:30 Nairobi time).")
        elif args.action == "recent":
            tickers = args.tickers or [s["ticker"] for s in load_watchlist() if s["status"] != "out"]
            print(f"Fetching {len(tickers)} stock pages, about {len(tickers)} minutes...")
            print(f"Stored {prices.load_recent(db, tickers):,} rows.")
        elif args.action == "status":
            show_prices_status(db)


if __name__ == "__main__":
    main()
