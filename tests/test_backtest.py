"""Run with: python -m unittest"""
import unittest
from datetime import date, timedelta

from nse_ranker import backtest


def series(daily_growth, days=900, start=date(2020, 1, 1), price=10.0, volume=100_000, jump_on=None):
    """A stock that grows by `daily_growth` each weekday; optionally doubles in one day (a bonus issue)."""
    dates, closes, volumes = [], [], []
    day = start
    while len(dates) < days:
        if day.weekday() < 5:
            price *= 1 + daily_growth
            if jump_on and day == jump_on:
                price *= 2
            dates.append(day)
            closes.append(round(price, 4))
            volumes.append(volume)
        day += timedelta(days=1)
    return dates, closes, volumes


class TestHelpers(unittest.TestCase):
    def test_add_months(self):
        self.assertEqual(backtest.add_months(date(2026, 11, 1), 3), date(2027, 2, 1))

    def test_price_on_or_after_skips_weekends_but_not_gaps(self):
        s = series(0, days=10, start=date(2026, 1, 5))     # Mon 5 Jan onwards
        self.assertIsNotNone(backtest.price_on_or_after(s, date(2026, 1, 10)))   # Saturday -> Monday
        self.assertIsNone(backtest.price_on_or_after(s, date(2026, 3, 1)))       # long after the data ends

    def test_jumps_are_detected(self):
        s = series(0, days=60, start=date(2026, 1, 5), jump_on=date(2026, 2, 2))
        self.assertTrue(backtest.has_jump(s, date(2026, 1, 20), date(2026, 2, 10)))
        self.assertFalse(backtest.has_jump(s, date(2026, 2, 10), date(2026, 3, 20)))

    def test_spearman(self):
        self.assertAlmostEqual(backtest.spearman([1, 2, 3], [10, 20, 30]), 1.0)
        self.assertAlmostEqual(backtest.spearman([1, 2, 3], [30, 20, 10]), -1.0)


class TestRun(unittest.TestCase):
    def test_trending_stocks_rank_top_and_beat_the_rest(self):
        # 10 steady risers and 10 steady fallers: momentum persists, so the top fifth must win.
        data = {f"UP{i}": series(0.001 + i * 0.0001) for i in range(10)}
        data.update({f"DN{i}": series(-0.001 - i * 0.0001) for i in range(10)})
        result = backtest.run(None, first=date(2021, 1, 1), last=date(2022, 6, 1), data=data)
        three = result["summary"][3]
        self.assertGreater(three["top"], three["all"])
        self.assertGreater(three["all"], three["bottom"])
        self.assertEqual(three["top_beat_bottom"], 1.0)
        self.assertGreater(three["ic"], 0.9)
        self.assertTrue(all(t.startswith("UP") for p in result["periods"] for t in p["horizons"][3]["top_tickers"]))

    def test_stocks_with_a_jump_are_left_out(self):
        data = {f"S{i}": series(0.0005 * i) for i in range(12)}
        data["BONUS"] = series(0.002, jump_on=date(2021, 6, 1))
        result = backtest.run(None, first=date(2021, 5, 1), last=date(2021, 7, 1), data=data)
        for period in result["periods"]:
            for horizon in period["horizons"].values():
                self.assertNotIn("BONUS", horizon["top_tickers"])

    def test_thin_stocks_are_not_ranked(self):
        data = {f"S{i}": series(0.0005 * i) for i in range(12)}
        data["THIN"] = series(0.01, volume=10)
        scores = backtest.score_on(data, date(2021, 6, 1))
        self.assertNotIn("THIN", scores)
        self.assertEqual(len(scores), 12)


if __name__ == "__main__":
    unittest.main()
