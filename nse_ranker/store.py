"""SQLite store for daily prices. One row per ticker per trading day."""
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DB_FILE = DATA_DIR / "nse.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    ticker     TEXT NOT NULL,
    date       TEXT NOT NULL,   -- YYYY-MM-DD
    close      REAL NOT NULL,
    high       REAL,
    low        REAL,
    prev_close REAL,
    volume     INTEGER NOT NULL DEFAULT 0,   -- 0 means no trades that day
    source     TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
);
-- Which daily NSE price lists we've already read, so we never fetch one twice.
CREATE TABLE IF NOT EXISTS fetched_days (
    date   TEXT PRIMARY KEY,
    status TEXT NOT NULL      -- "ok" or "missing" (holiday / no list published)
);
"""

PRICE_COLUMNS = ("ticker", "date", "close", "high", "low", "prev_close", "volume", "source")


def connect(path=DB_FILE):
    """Open the database, creating the file and tables if needed."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)   # wait for another writer instead of failing
    db.executescript(SCHEMA)
    return db


def save_prices(db, rows):
    """Insert or replace price rows (dicts with PRICE_COLUMNS). Returns the count."""
    rows = list(rows)
    db.executemany(
        f"INSERT OR REPLACE INTO prices ({', '.join(PRICE_COLUMNS)}) "
        f"VALUES ({', '.join(':' + c for c in PRICE_COLUMNS)})",
        rows,
    )
    db.commit()
    return len(rows)


def mark_fetched(db, date, status):
    db.execute("INSERT OR REPLACE INTO fetched_days (date, status) VALUES (?, ?)", (date, status))
    db.commit()


def fetched_dates(db):
    return {row[0] for row in db.execute("SELECT date FROM fetched_days")}


def history(db, ticker, since=None):
    """Return [(date, close, volume), ...] for one ticker, oldest first."""
    sql = "SELECT date, close, volume FROM prices WHERE ticker = ?"
    args = [ticker]
    if since:
        sql += " AND date >= ?"
        args.append(since)
    return db.execute(sql + " ORDER BY date", args).fetchall()


def summary(db):
    """Return (rows, tickers, first date, last date) for the whole table."""
    return db.execute(
        "SELECT COUNT(*), COUNT(DISTINCT ticker), MIN(date), MAX(date) FROM prices"
    ).fetchone()
