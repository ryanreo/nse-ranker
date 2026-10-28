"""Run with: python -m unittest"""
import unittest
from datetime import datetime

from nse_ranker import store
from nse_ranker.sources import afx, eodhd, mendeley

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


class TestEodhd(unittest.TestCase):
    def bars(self, closes):
        return [{"date": f"2026-05-{i + 10}", "close": c, "high": c, "low": c, "volume": 100}
                for i, c in enumerate(closes)]

    def test_repairs_a_day_recorded_in_cents(self):
        rows = eodhd.parse(self.bars([9.16, 916.0, 9.32]), "HFCB")
        self.assertEqual([r["close"] for r in rows], [9.16, 9.16, 9.32])
        self.assertEqual(rows[1]["high"], 9.16)

    def test_repairs_a_10x_slip(self):
        rows = eodhd.parse(self.bars([1.29, 12.7, 1.25]), "HAFR")
        self.assertAlmostEqual(rows[1]["close"], 1.27)

    def test_repairs_a_bad_first_day(self):
        rows = eodhd.parse(self.bars([228.0, 2.35, 2.4]), "FTGH")
        self.assertEqual(rows[0]["close"], 2.28)

    def test_drops_a_jump_no_factor_explains(self):
        rows = eodhd.parse(self.bars([10.0, 70.0, 10.2]), "XYZ")
        self.assertEqual([r["close"] for r in rows], [10.0, 10.2])

    def test_keeps_normal_moves_and_links_prev_close(self):
        rows = eodhd.parse(self.bars([10.0, 11.0, 9.9]), "XYZ")
        self.assertEqual([r["prev_close"] for r in rows], [None, 10.0, 11.0])

    def test_api_key_error_is_clear(self):
        with self.assertRaisesRegex(RuntimeError, "EODHD_API_KEY"):
            eodhd.api_key("no-such-file.env")


class TestLoadRecent(unittest.TestCase):
    def test_a_timeout_skips_one_stock_and_a_rerun_skips_finished_ones(self):
        from unittest import mock
        from nse_ranker import prices
        db = store.connect(":memory:")
        page = ([{"ticker": "AAA", "date": "2026-10-27", "close": 10.0, "high": None, "low": None,
                  "prev_close": 9.5, "volume": 100, "source": "afx"}], {"eps": 1.0, "dps": 0.5})
        with mock.patch.object(afx, "stock_page", side_effect=[page, TimeoutError("read timed out")]):
            self.assertEqual(prices.load_recent(db, ["AAA", "BBB"]), 1)   # BBB failed, no crash
        with mock.patch.object(afx, "stock_page", return_value=page) as fetch:
            prices.load_recent(db, ["AAA", "BBB"])
        self.assertEqual(fetch.call_count, 1)                              # only BBB fetched again


class TestStore(unittest.TestCase):
    def test_save_and_read_back(self):
        db = store.connect(":memory:")
        store.save_prices(db, mendeley.parse_prices(MENDELEY_CSV))
        store.save_prices(db, mendeley.parse_prices(MENDELEY_CSV))   # saving twice doesn't duplicate
        self.assertEqual(store.history(db, "SCOM"), [("2025-01-02", 17.2, 1347700)])
        self.assertEqual(store.summary(db)[0], 2)


if __name__ == "__main__":
    unittest.main()
