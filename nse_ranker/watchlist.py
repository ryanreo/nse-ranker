"""Load the watchlist: the stocks we track, with their sector, type and status."""
import tomllib
from pathlib import Path

# watchlist.toml sits in the project folder, one level above this package.
WATCHLIST_FILE = Path(__file__).parent.parent / "watchlist.toml"


def load_watchlist(path=WATCHLIST_FILE):
    """Read watchlist.toml and return a list of stock dictionaries.

    Each stock also gets a "drivers" list: the things that move its sector.
    """
    with open(path, "rb") as f:
        data = tomllib.load(f)

    stocks = data["stock"]
    for stock in stocks:
        stock["drivers"] = data["sectors"].get(stock["sector"], [])
    return stocks


def rankable(stocks):
    """Return a new list with only the stocks whose status is "rank".

    Example: given ABSA ("rank"), GLD ("out") and HBE ("watch"), return a list
    holding just ABSA. Keep them in the same order, and don't change the list
    you were given.
    """
    # TODO: your code here (a for loop and an if)
    return []
