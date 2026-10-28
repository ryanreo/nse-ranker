"""Command line: python -m nse_ranker <command>"""
import argparse
from collections import Counter

from . import prices, store
from .watchlist import load_watchlist, rankable


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


def main():
    parser = argparse.ArgumentParser(prog="nse_ranker", description="Rank my NSE watchlist.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("watchlist", help="list the stocks and their status")

    price_cmd = commands.add_parser("prices", help="fill or check the price store")
    price_actions = price_cmd.add_subparsers(dest="action", required=True)
    history = price_actions.add_parser("history", help="load 2007-2025 history from Mendeley")
    history.add_argument("--from", dest="first_year", type=int, default=2007)
    price_actions.add_parser("update", help="store today's closes from afx (after 15:30)")
    recent = price_actions.add_parser("recent", help="store the last ~2 weeks from afx (1 stock a minute)")
    recent.add_argument("tickers", nargs="*", help="default: every stock that isn't 'out'")
    price_actions.add_parser("status", help="show what's stored")

    args = parser.parse_args()

    if args.command == "watchlist":
        show_watchlist()
    elif args.command == "prices":
        db = store.connect()
        if args.action == "history":
            print(f"Loading Mendeley history from {args.first_year}...")
            print(f"Stored {prices.load_history(db, args.first_year):,} rows.")
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
