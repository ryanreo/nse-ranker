"""Recent NSE prices from afx.kwayisi.org.

Its robots.txt asks for 60 seconds between requests, so every request here waits that long.
- latest(): today's closing prices for every counter, from the main page (1 request).
- stock_page(ticker): the last ~2 weeks of closes plus EPS, dividend and shares, from its own page.
"""
import re
from datetime import datetime, timedelta, timezone

from .. import web

BASE = "https://afx.kwayisi.org/nse/"
CRAWL_DELAY = 60
NAIROBI = timezone(timedelta(hours=3))
MARKET_CLOSE = (15, 30)   # trading ends at 15:00; give the site half an hour to settle

# Main page rows: <a ...>SCOM</a><td><a ...>Safaricom Plc</a><td>1,063,934<td>33.75<td class=hi>+0.50
_MAIN_ROW = re.compile(
    r'<tr><td><a href=[^>]*>([A-Z0-9^-]+)</a><td><a [^>]*>[^<]*</a>'
    r'<td>([\d,]*)<td>([\d,.]+)<td(?: class=\w+)?>([+-]?[\d,.]*)'
)
# Stock page rows: <tr><td>2026-10-21<td>6,274,461<td>34.15<td class=lo>-1.05<td class=lo>-2.98%
_HISTORY_ROW = re.compile(r'<tr><td>(\d{4}-\d\d-\d\d)<td>([\d,]*)<td>([\d,.]+)<td(?: class=\w+)?>([+-]?[\d,.]*)')
# Stock page "Growth & Valuation" table: <tr><td>Earnings Per Share<td class=hi>2.3863
_FACT_ROW = re.compile(r'<tr><td>([A-Za-z/ ]+)<td(?: class=\w+)?>(-?[\d,.]+)([KMBT%]?)')
_FACTS = {"Earnings Per Share": "eps", "Dividend Per Share": "dps", "Shares Outstanding": "shares"}
_SCALE = {"": 1, "%": 1, "K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def _num(text):
    text = text.replace(",", "").strip()
    return float(text) if text not in ("", "+", "-") else None


def market_closed_today(now=None):
    """True after 15:30 Nairobi time on a weekday: the main page then shows today's closes."""
    now = now or datetime.now(NAIROBI)
    return now.weekday() < 5 and (now.hour, now.minute) >= MARKET_CLOSE


def parse_main(html, date):
    for ticker, volume, price, change in _MAIN_ROW.findall(html):
        close, change = _num(price), _num(change)
        yield {
            "ticker": ticker, "date": date, "close": close, "high": None, "low": None,
            "prev_close": round(close - change, 4) if change is not None else None,
            "volume": int(_num(volume) or 0), "source": "afx",
        }


def parse_history(html, ticker):
    for date, volume, price, change in _HISTORY_ROW.findall(html):
        close, change = _num(price), _num(change)
        yield {
            "ticker": ticker, "date": date, "close": close, "high": None, "low": None,
            "prev_close": round(close - change, 4) if change is not None else None,
            "volume": int(_num(volume) or 0), "source": "afx",
        }


def parse_facts(html):
    """EPS, dividend per share and shares outstanding. Missing items are left out."""
    facts = {}
    for label, number, suffix in _FACT_ROW.findall(html):
        if label.strip() in _FACTS:
            facts[_FACTS[label.strip()]] = float(number.replace(",", "")) * _SCALE[suffix]
    return facts


def latest(now=None):
    """Today's closing prices for every counter. Returns [] before the market has closed."""
    now = now or datetime.now(NAIROBI)
    if not market_closed_today(now):
        return []
    html = web.get(BASE, delay=CRAWL_DELAY).decode("utf-8")
    return list(parse_main(html, now.strftime("%Y-%m-%d")))


def stock_page(ticker):
    """One counter's page (one request, 60 s apart): (last ~2 weeks of closes, fundamentals)."""
    html = web.get(f"{BASE}{ticker.lower()}.html", delay=CRAWL_DELAY)
    if not html:
        return [], {}
    html = html.decode("utf-8", errors="replace")
    return list(parse_history(html, ticker)), parse_facts(html)
