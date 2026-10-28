"""Historical NSE daily prices, 2007-2025, from Barack Wanjawa's datasets on Mendeley Data.

Licence: CC BY 4.0. Credit: Wanjawa, B., "Kenya Nairobi Securities Exchange (NSE) All Stocks Prices"
(Mendeley Data). The data was compiled from MyStocks (Synergy Systems Ltd.), licensed by the NSE.
"""
import csv
import io
import json
from datetime import datetime

from .. import web

API = "https://data.mendeley.com/public-api/datasets/{}"

# Dataset IDs on Mendeley, by the years they cover.
DATASETS = {
    "2007-2012": "5hk4zw32f5",
    "2013-2020": "73rb78pmzw",
    "2021": "97hkwn5y3x",
    "2022": "jmcdmnyh2s",
    "2023-2024": "ss5pfw8xnk",
    "2025": "2b63rx67xt",
}


def price_files(dataset_id):
    """Return [(filename, download_url), ...] for the price CSVs in one dataset."""
    meta = json.loads(web.get(API.format(dataset_id)))
    files = []
    for f in meta.get("files", []):
        name = f.get("filename", "")
        url = (f.get("content_details") or {}).get("download_url")
        if name.lower().endswith(".csv") and "sector" not in name.lower() and url:
            files.append((name, url))
    return files


def _number(text):
    """'1,347,700' -> 1347700.0; '-' or '' -> None."""
    text = (text or "").strip().replace(",", "")
    if text in ("", "-"):
        return None
    return float(text)


def _date(text):
    """The files use dates like '2-Jan-25' (and in older years '2-Jan-2007' or '1/2/2007')."""
    text = text.strip()
    for fmt in ("%d-%b-%y", "%d-%b-%Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    raise ValueError(f"unknown date format: {text!r}")


def parse_prices(csv_bytes):
    """Turn one Mendeley price CSV into price rows for the store. Skips rows with no price."""
    reader = csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig")))
    for row in reader:
        # Column names vary slightly between years; normalise them.
        row = {key.strip().lower(): value for key, value in row.items() if key}
        close = _number(row.get("day price"))
        if close is None:
            continue
        yield {
            "ticker": row.get("code", "").strip(),
            "date": _date(row["date"]),
            "close": close,
            "high": _number(row.get("day high")),
            "low": _number(row.get("day low")),
            "prev_close": _number(row.get("previous")),
            "volume": int(_number(row.get("volume")) or 0),
            "source": "mendeley",
        }
