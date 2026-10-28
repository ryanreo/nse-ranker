"""Command line: python -m nse_ranker <command>"""
import argparse
from collections import Counter

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


def main():
    parser = argparse.ArgumentParser(prog="nse_ranker", description="Rank my NSE watchlist.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("watchlist", help="list the stocks and their status")
    args = parser.parse_args()

    if args.command == "watchlist":
        show_watchlist()


if __name__ == "__main__":
    main()
