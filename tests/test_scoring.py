"""Run with: python -m unittest"""
import unittest

from nse_ranker import scoring


def rows(closes, volume=100_000):
    """Make [(date, close, volume), ...] from a list of closes."""
    return [(f"day{i:03d}", close, volume) for i, close in enumerate(closes)]


def steady(start, end, days=200, volume=100_000):
    """A price that moves in a straight line from start to end."""
    return rows([start + (end - start) * i / (days - 1) for i in range(days)], volume)


class TestLiquidity(unittest.TestCase):
    def test_busy_stock_passes(self):
        self.assertIsNone(scoring.liquidity_problem(steady(10, 10)))   # 10 x 100,000 = KES 1M a day

    def test_thin_stock_is_excluded(self):
        self.assertIn("thin trading", scoring.liquidity_problem(steady(10, 10, volume=500)))

    def test_rarely_traded_stock_is_excluded(self):
        mostly_idle = rows([10.0] * 60, volume=0)[:-20] + rows([10.0] * 20, volume=1_000_000)
        self.assertIn("only 33%", scoring.liquidity_problem(mostly_idle))


class TestFactors(unittest.TestCase):
    def test_momentum_skips_the_last_month(self):
        closes = [10.0] * 110 + [20.0] * 96 + [5.0] * 21   # doubled, then crashed last month
        self.assertAlmostEqual(scoring.momentum(rows(closes)), 1.0)

    def test_momentum_needs_six_months(self):
        self.assertIsNone(scoring.momentum(steady(10, 20, days=100)))

    def test_volatility_is_zero_for_a_flat_price(self):
        self.assertEqual(scoring.volatility(steady(10, 10)), 0)

    def test_loss_makers_get_negative_earnings_yield(self):
        self.assertEqual(scoring.earnings_yield(-2, 20), -0.1)

    def test_dividend_counts_only_the_part_earnings_cover(self):
        self.assertAlmostEqual(scoring.covered_yield(eps=2, dps=3, price=20), 0.10)   # not 0.15
        self.assertAlmostEqual(scoring.covered_yield(eps=4, dps=1, price=20), 0.05)
        self.assertEqual(scoring.covered_yield(eps=-1, dps=1, price=20), 0.0)

    def test_impossible_yields_are_treated_as_bad_data(self):
        self.assertIsNone(scoring.earnings_yield(120, 59))                  # BKG: EPS in RWF, price in KES
        self.assertIsNone(scoring.covered_yield(eps=120, dps=53, price=59))

    def test_eps_growth_needs_two_different_results(self):
        self.assertIsNone(scoring.eps_growth([("2026-10-28", 2.0, 1.0)]))
        self.assertAlmostEqual(scoring.eps_growth([("a", 2.0, 1.0), ("b", 2.5, 1.0)]), 0.25)
        self.assertAlmostEqual(scoring.eps_growth([("a", -2.0, 0), ("b", -1.0, 0)]), 0.5)


class TestScores(unittest.TestCase):
    def test_percentiles_run_from_0_to_100_and_share_ties(self):
        scores = scoring.percentile_scores({"A": 1, "B": 2, "C": 2, "D": 3, "E": None})
        self.assertEqual(scores, {"A": 0, "B": 50, "C": 50, "D": 100})

    def test_lower_is_better_flips_the_order(self):
        scores = scoring.percentile_scores({"A": 1, "B": 3}, higher_is_better=False)
        self.assertEqual(scores, {"A": 100, "B": 0})

    def test_sector_relative_value(self):
        raw = {"B1": 0.10, "B2": 0.20, "B3": 0.30, "T1": 0.05}
        sectors = {"B1": "Banking", "B2": "Banking", "B3": "Banking", "T1": "Telecom"}
        relative = scoring.relative_to_sector(raw, sectors)
        self.assertAlmostEqual(relative["B2"], 0.0)              # the median bank
        self.assertAlmostEqual(relative["T1"], 0.05 - 0.15)      # a lone telco vs the market


class TestScoreAll(unittest.TestCase):
    def stock(self, ticker, start, end, eps=1.0, dps=0.5, sector="Banking", volume=100_000, **extra):
        return dict(ticker=ticker, sector=sector, rows=steady(start, end, volume=volume),
                    eps=eps, dps=dps, eps_changes=[], **extra)

    def test_better_stock_ranks_first_and_thin_stock_is_excluded(self):
        results = scoring.score_all([
            self.stock("WEAK", 20, 10, eps=0.5, dps=0.1),   # falling, expensive, low dividend
            self.stock("GOOD", 10, 20, eps=3.0, dps=1.5),   # rising, cheap, good dividend
            self.stock("THIN", 10, 20, volume=10),
        ])
        self.assertEqual([r["ticker"] for r in results], ["GOOD", "WEAK", "THIN"])
        self.assertGreater(results[0]["score"], results[1]["score"])
        self.assertIsNone(results[2]["score"])
        self.assertIn("thin trading", results[2]["excluded"])

    def test_missing_factors_are_left_out_not_counted_as_zero(self):
        result = scoring.score_all([self.stock("A", 10, 20), self.stock("B", 10, 15)])[0]
        self.assertIsNone(result["factors"]["quality"])
        self.assertEqual(result["weight_used"], 25 + 20 + 20 + 10)   # no quality, news, opinion

    def test_opinion_can_only_nudge_the_score(self):
        base = dict(start=10, end=12)
        quiet = scoring.score_all([self.stock("A", **base, opinion=50), self.stock("B", 10, 14, opinion=50)])
        hyped = scoring.score_all([self.stock("A", **base, opinion=100), self.stock("B", 10, 14, opinion=50)])
        score = {r["ticker"]: r["score"] for r in quiet}
        hyped_score = {r["ticker"]: r["score"] for r in hyped}
        self.assertLess(hyped_score["A"] - score["A"], 2.0)   # 3 points of weight out of 78


if __name__ == "__main__":
    unittest.main()
