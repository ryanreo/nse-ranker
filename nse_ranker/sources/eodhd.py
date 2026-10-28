"""End-of-day NSE prices from the EODHD API (eodhd.com), used to fill January-October 2026.

Needs EODHD_API_KEY in the project's .env file. The free plan allows 20 calls a day,
20 a minute, plus 500 one-time bonus calls, with up to a year of history. One call per stock.
"""
import json
from pathlib import Path

from .. import web

API = "https://eodhd.com/api/eod/{}.XNAI?from={}&to={}&fmt=json&api_token={}"
REQUEST_GAP = 3.5   # seconds; the free plan allows 20 requests a minute
ENV_FILE = Path(__file__).parent.parent.parent / ".env"

# Our NSE tickers -> EODHD's codes, where they differ (checked against /exchange-symbol-list/XNAI).
CODES = {
    "ABSA": "BBLK", "ARM": "ATHI", "BAMB": "BAMBURI", "BAT": "BATK", "BRIT": "BRITAM",
    "CABL": "EACABLES", "CARB": "CIL", "CGEN": "C&G", "COOP": "CBKL", "CRWN": "CPKL",
    "CTUM": "CENTUM", "DCON": "DEAP", "DTK": "DTB", "EABL": "EABREW", "EGAD": "EAAGADS",
    "EQTY": "EBL", "EVRD": "EVREADY", "GLD": "NEWGOLDETF", "HAFR": "HAL", "HBE": "HEL",
    "HFCB": "HFCK", "IMH": "CTL", "JUB": "JUBILEE", "KAPC": "KTCL", "KEGN": "KENGEN",
    "KNRE": "KENRE", "KQ": "KAL", "KUKZ": "KAKUZI", "KURV": "KVL", "LAPR": "LAPTRUST",
    "LBTY": "CFCI", "LIMT": "LIMURU", "MSC": "MUMIAS", "NBV": "NBVL", "NCBA": "NIC",
    "PORT": "EAPORTLAND", "SASN": "SASINI", "SBIC": "CFC", "SCAN": "SG", "SCOM": "SAFARI",
    "SGL": "STANGROUP", "SLAM": "PAN", "SMER": "SAMEER", "TOTL": "TOTAL", "TPSE": "TPS",
    "UCHM": "UCHUMI", "UMME": "UMEME", "WTK": "WTKL", "XPRS": "EXP",
}
# Not on EODHD: the KPLC preference shares and the Satrix world ETF (all "out" anyway).
MISSING = {"KPLC-P4", "KPLC-P7", "SMWF"}


def api_key(env_file=ENV_FILE):
    """Read EODHD_API_KEY from .env. Raises a clear error if it isn't set."""
    if Path(env_file).exists():
        for line in Path(env_file).read_text().splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "EODHD_API_KEY" and value.strip():
                return value.strip()
    raise RuntimeError("EODHD_API_KEY is missing: add it to the .env file in the project folder.")


def fix_units(rows):
    """Repair EODHD's unit slips: some days are recorded 10x or 100x too high (cents, not shillings).

    Each close is compared with the last good close (for the first row, the median of the
    first five closes). A jump of more than 5x is divided by 100 or 10 if that brings it
    within 30%; otherwise the row is dropped. prev_close is then rebuilt from the cleaned closes.
    Returns (cleaned rows, number fixed, number dropped).
    """
    cleaned, fixed, dropped = [], 0, 0
    start = sorted(row["close"] for row in rows[:5])
    for row in rows:
        reference = cleaned[-1]["close"] if cleaned else (start[len(start) // 2] if start else None)
        if reference and not 0.2 <= row["close"] / reference <= 5:
            factor = next((f for f in (100, 10) if abs(row["close"] / f / reference - 1) <= 0.3), None)
            if factor is None:
                dropped += 1
                continue
            row = dict(row, close=row["close"] / factor,
                       high=row["high"] / factor if row["high"] else None,
                       low=row["low"] / factor if row["low"] else None)
            fixed += 1
        cleaned.append(row)
    for prev, row in zip([None] + cleaned, cleaned):
        row["prev_close"] = prev["close"] if prev else None
    return cleaned, fixed, dropped


def parse(data, ticker):
    """Turn EODHD's JSON list into price rows, with unit slips repaired."""
    rows = [{
        "ticker": ticker, "date": bar["date"], "close": bar["close"],
        "high": bar.get("high"), "low": bar.get("low"), "prev_close": None,
        "volume": int(bar.get("volume") or 0), "source": "eodhd",
    } for bar in data]
    return fix_units(rows)[0]


def daily(ticker, start, end, key=None):
    """Daily prices for one of our tickers between two YYYY-MM-DD dates (one API call)."""
    if ticker in MISSING:
        return []
    code = CODES.get(ticker, ticker).replace("&", "%26")
    body = web.get(API.format(code, start, end, key or api_key()), delay=REQUEST_GAP)
    return parse(json.loads(body), ticker) if body else []
