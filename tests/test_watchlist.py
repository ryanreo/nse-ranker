"""Run with: python -m unittest"""
import unittest

from nse_ranker.watchlist import load_watchlist, rankable


class TestLoadWatchlist(unittest.TestCase):
    def test_has_all_72_stocks(self):
        self.assertEqual(len(load_watchlist()), 72)

    def test_every_stock_has_sector_drivers(self):
        for stock in load_watchlist():
            self.assertIsInstance(stock["drivers"], list, stock["ticker"])

    def test_dollar_reits_are_marked_usd(self):
        currency = {stock["ticker"]: stock["currency"] for stock in load_watchlist()}
        self.assertEqual(currency["ALP"], "USD")
        self.assertEqual(currency["TRFC"], "USD")
        self.assertEqual(currency["SCOM"], "KES")


class TestRankable(unittest.TestCase):
    def setUp(self):
        self.stocks = [
            {"ticker": "ABSA", "status": "rank"},
            {"ticker": "GLD", "status": "out"},
            {"ticker": "HBE", "status": "watch"},
            {"ticker": "KCB", "status": "rank"},
        ]

    def test_keeps_only_rank_in_order(self):
        tickers = [stock["ticker"] for stock in rankable(self.stocks)]
        self.assertEqual(tickers, ["ABSA", "KCB"])

    def test_does_not_change_the_input(self):
        rankable(self.stocks)
        self.assertEqual(len(self.stocks), 4)

    def test_empty_list(self):
        self.assertEqual(rankable([]), [])

    def test_real_watchlist_has_52(self):
        self.assertEqual(len(rankable(load_watchlist())), 52)


if __name__ == "__main__":
    unittest.main()
