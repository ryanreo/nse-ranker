"""Fill the price store from each source, and report what we have."""
from datetime import date, timedelta

from . import store, web
from .sources import afx, eodhd, mendeley
from .watchlist import load_watchlist


def load_history(db, first_year=2007):
    """Download the Mendeley yearly files from first_year on and store every row."""
    total = 0
    for years, dataset_id in mendeley.DATASETS.items():
        if int(years[-4:]) < first_year:
            continue
        for name, url in mendeley.price_files(dataset_id):
            year = int(name[len("NSE_data_all_stocks_"):][:4])
            if year < first_year:
                continue
            count = store.save_prices(db, mendeley.parse_prices(web.get(url)))
            total += count
            print(f"  {name}: {count:,} rows")
    return total


def update_latest(db):
    """Store today's closes from afx. Returns the number of rows (0 before the close)."""
    return store.save_prices(db, afx.latest())


def fill_from_eodhd(db, tickers, start, end):
    """Store EODHD daily prices for each ticker between two dates. One API call per ticker.

    Rows already stored from another source are kept: EODHD only fills missing days.
    """
    key = eodhd.api_key()
    total = 0
    for i, ticker in enumerate(tickers, 1):
        have = {d for d, _, _ in store.history(db, ticker, since=start)}
        rows = [row for row in eodhd.daily(ticker, start, end, key) if row["date"] not in have]
        total += store.save_prices(db, rows)
        print(f"  [{i}/{len(tickers)}] {ticker}: {len(rows)} new days")
    return total


def load_recent(db, tickers):
    """Store the last ~2 weeks of prices and the current EPS/dividend for each ticker from afx.

    One request a minute, so this takes about a minute per ticker.
    """
    total = 0
    today = date.today().isoformat()
    for i, ticker in enumerate(tickers, 1):
        rows, facts = afx.stock_page(ticker)
        count = store.save_prices(db, rows)
        if facts:
            store.save_fundamentals(db, ticker, today, facts, "afx")
        total += count
        print(f"  [{i}/{len(tickers)}] {ticker}: {count} days, EPS {facts.get('eps')}, DPS {facts.get('dps')}")
    return total


def coverage(db, today=None):
    """For each watchlist stock that isn't "out": days stored in the last year and the latest date."""
    today = today or date.today()
    year_ago = (today - timedelta(days=365)).isoformat()
    report = []
    for stock in load_watchlist():
        if stock["status"] == "out":
            continue
        rows = store.history(db, stock["ticker"], since=year_ago)
        report.append({
            "ticker": stock["ticker"],
            "days": len(rows),
            "traded_days": sum(1 for _, _, volume in rows if volume > 0),
            "last": rows[-1][0] if rows else None,
        })
    return report
