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
-- EPS and dividends as seen on each fetch. Keeping every snapshot lets us see EPS change
-- when new results come out (the quality factor).
CREATE TABLE IF NOT EXISTS fundamentals (
    ticker  TEXT NOT NULL,
    date    TEXT NOT NULL,    -- when we fetched it
    eps     REAL,
    dps     REAL,
    shares  REAL,
    source  TEXT NOT NULL,
    PRIMARY KEY (ticker, date)
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


def save_fundamentals(db, ticker, date, facts, source):
    """Store one snapshot of EPS, dividend per share and shares outstanding."""
    db.execute(
        "INSERT OR REPLACE INTO fundamentals (ticker, date, eps, dps, shares, source) VALUES (?, ?, ?, ?, ?, ?)",
        (ticker, date, facts.get("eps"), facts.get("dps"), facts.get("shares"), source),
    )
    db.commit()


def eps_history(db, ticker):
    """Distinct EPS values seen for a ticker, oldest first: [(date first seen, eps, dps), ...]."""
    rows = db.execute(
        "SELECT date, eps, dps FROM fundamentals WHERE ticker = ? AND eps IS NOT NULL ORDER BY date",
        (ticker,),
    ).fetchall()
    changes = []
    for date, eps, dps in rows:
        if not changes or eps != changes[-1][1]:
            changes.append((date, eps, dps))
        else:
            changes[-1] = (changes[-1][0], eps, dps)   # same results; keep the latest dividend
    return changes


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
