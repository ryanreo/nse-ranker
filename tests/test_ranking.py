"""Run with: python -m unittest"""
import unittest

from nse_ranker import ranking, store


def result(ticker="AAA", score=70.0, **factors):
    names = ("momentum", "value", "dividend", "quality", "risk", "news", "opinion")
    scores = {name: factors.get(name) for name in names}
    raw = {"momentum": 0.42, "value": 0.2, "dividend": 0.08, "quality": None, "risk": 0.017,
           "news": None, "opinion": None}
    return {"ticker": ticker, "score": score, "factors": scores, "raw": raw, "excluded": None}


class TestReasons(unittest.TestCase):
    def test_two_strengths_and_a_weakness(self):
        reasons = ranking.reasons(result(momentum=95, value=80, dividend=50, risk=10))
        self.assertEqual(reasons, [
            "+ price +42% over 6 months",
            "+ P/E 5.0, cheap for its sector",
            "- jumpy price (typical daily move 1.7%)",
        ])

    def test_middling_factors_give_no_reasons(self):
        self.assertEqual(ranking.reasons(result(momentum=55, value=50, risk=45)), [])

    def test_loss_makers_say_so(self):
        self.assertEqual(ranking.describe("value", -0.1, good=False), "loss-making")


class TestRuns(unittest.TestCase):
    def test_runs_are_saved_and_compared(self):
        db = store.connect(":memory:")
        self.assertEqual(ranking.previous_positions(db, "2026-10-28"), {})
        ranking.save_run(db, [result("AAA", 80), result("BBB", 60)], "2026-10-21")
        ranking.save_run(db, [result("BBB", 90), result("AAA", 70)], "2026-10-28")
        self.assertEqual(ranking.previous_positions(db, "2026-10-28"), {"AAA": 1, "BBB": 2})

    def test_excluded_stocks_have_no_position(self):
        db = store.connect(":memory:")
        thin = dict(result("THIN", None), excluded="thin trading")
        ranking.save_run(db, [result("AAA", 80), thin], "2026-10-21")
        self.assertEqual(ranking.previous_positions(db, "2026-10-28"), {"AAA": 1})


if __name__ == "__main__":
    unittest.main()
