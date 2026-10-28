"""Run with: python -m unittest"""
import unittest
from datetime import datetime

from nse_ranker import store
from nse_ranker.sources import afx, mendeley

MENDELEY_CSV = (
    "﻿Date,Code,Name,12m Low,12m High,Day Low,Day High,Day Price,Previous,Change,Change%,Volume,Adjusted Price\n"
    "2-Jan-25,EGAD,Eaagads Ltd,10.8,24.1,12,12,12,12,-,-,-,-\n"
    "2-Jan-25,SCOM,Safaricom Plc,14.1,31,17.15,17.4,17.2,17.05,0.15,0.88%,\"1,347,700\",-\n"
    "2-Jan-25,XYZ,No Price Ltd,1,2,-,-,-,-,-,-,-,-\n"
).encode("utf-8")

AFX_MAIN = (
    '<tr><td><a href=https://afx.kwayisi.org/nse/scom.html title="Safaricom Plc">SCOM</a>'
    '<td><a href=https://afx.kwayisi.org/nse/scom.html title="Safaricom Plc">Safaricom Plc</a>'
    '<td>1,063,934<td>33.75<td class=hi>+0.50'
    '<tr class=ss><td><a href=https://afx.kwayisi.org/nse/arm.html title="ARM Cement Ltd">ARM</a>'
    '<td><a href=https://afx.kwayisi.org/nse/arm.html title="ARM Cement Ltd">ARM Cement Ltd</a><td><td>5.50<td>'
)

AFX_STOCK = (
    "<tr><td>2026-10-21<td>6,274,461<td>34.15<td class=lo>-1.05<td class=lo>-2.98%"
    "<tr><td>2026-10-13<td>5,729,934<td>35.20<td><td></table>"
)


class TestMendeley(unittest.TestCase):
    def test_parses_rows_and_skips_rows_without_a_price(self):
        rows = list(mendeley.parse_prices(MENDELEY_CSV))
        self.assertEqual([r["ticker"] for r in rows], ["EGAD", "SCOM"])
        scom = rows[1]
        self.assertEqual(scom["date"], "2025-01-02")
        self.assertEqual(scom["close"], 17.2)
        self.assertEqual(scom["prev_close"], 17.05)
        self.assertEqual(scom["volume"], 1347700)

    def test_no_trades_means_volume_zero(self):
        egad = next(mendeley.parse_prices(MENDELEY_CSV))
        self.assertEqual(egad["volume"], 0)


class TestAfx(unittest.TestCase):
    def test_main_page_skips_suspended_rows(self):
        rows = list(afx.parse_main(AFX_MAIN, "2026-10-28"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["close"], 33.75)
        self.assertEqual(rows[0]["prev_close"], 33.25)
        self.assertEqual(rows[0]["volume"], 1063934)

    def test_stock_page_history(self):
        rows = list(afx.parse_history(AFX_STOCK, "SCOM"))
        self.assertEqual([r["date"] for r in rows], ["2026-10-21", "2026-10-13"])
        self.assertEqual(rows[0]["prev_close"], 35.2)
        self.assertIsNone(rows[1]["prev_close"])

    def test_only_trusts_main_page_after_the_close(self):
        tuesday = datetime(2026, 10, 27, tzinfo=afx.NAIROBI)
        self.assertFalse(afx.market_closed_today(tuesday.replace(hour=11)))
        self.assertTrue(afx.market_closed_today(tuesday.replace(hour=16)))
        self.assertFalse(afx.market_closed_today(datetime(2026, 10, 31, 16, tzinfo=afx.NAIROBI)))


class TestStore(unittest.TestCase):
    def test_save_and_read_back(self):
        db = store.connect(":memory:")
        store.save_prices(db, mendeley.parse_prices(MENDELEY_CSV))
        store.save_prices(db, mendeley.parse_prices(MENDELEY_CSV))   # saving twice doesn't duplicate
        self.assertEqual(store.history(db, "SCOM"), [("2025-01-02", 17.2, 1347700)])
        self.assertEqual(store.summary(db)[0], 2)


if __name__ == "__main__":
    unittest.main()
