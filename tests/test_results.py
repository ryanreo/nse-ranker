"""Run with: python -m unittest"""
import unittest
from datetime import date

from nse_ranker import results, store

ITEMS = [{
    "article": 0, "title": "KCB H1 profit rises",
    "text": "KCB Group said earnings per share rose to KSh 9.13 from KSh 7.50 in the half year to June 2026. "
            "The board declared an interim dividend of KSh 1.50.",
    "stocks": [{"ticker": "KCB", "name": "KCB Group"}],
}]


def figure(**changes):
    base = {"article": 0, "ticker": "KCB", "period": "h1 2026", "period_end": "2026-06-30", "eps": 9.13,
            "prior_eps": 7.5, "quote": "earnings per share rose to KSh 9.13 from KSh 7.50"}
    return dict(base, **changes)


class TestNumbers(unittest.TestCase):
    def test_numbers_match_how_stories_write_them(self):
        self.assertTrue(results.number_in("rose to KSh 7.50", 7.5))
        self.assertTrue(results.number_in("EPS of 12", 12.0))
        self.assertTrue(results.number_in("EPS of Sh1,234.50", 1234.5))
        self.assertFalse(results.number_in("rose to KSh 7.55", 7.5))

    def test_a_loss_per_share_matches_its_absolute_value(self):
        self.assertTrue(results.number_in("a loss per share of KSh 0.85", -0.85))


class TestCheck(unittest.TestCase):
    def test_good_figure_is_kept_and_period_tidied(self):
        kept = results.check(figure(), ITEMS)
        self.assertEqual((kept["eps"], kept["prior_eps"], kept["period"]), (9.13, 7.5, "H1 2026"))

    def test_quote_not_in_article_is_dropped(self):
        self.assertIsNone(results.check(figure(quote="earnings per share hit a record KSh 9.13"), ITEMS))

    def test_eps_not_in_quote_is_dropped(self):
        self.assertIsNone(results.check(figure(eps=10.2), ITEMS))

    def test_prior_eps_not_in_quote_is_cleared_but_eps_kept(self):
        kept = results.check(figure(prior_eps=6.9), ITEMS)
        self.assertEqual((kept["eps"], kept["prior_eps"]), (9.13, None))

    def test_stock_not_named_in_the_article_is_dropped(self):
        self.assertIsNone(results.check(figure(ticker="EQTY"), ITEMS))


class TestGrowth(unittest.TestCase):
    def test_latest_period_with_a_prior_figure_wins(self):
        db = store.connect(":memory:")
        db.executescript(results.SCHEMA)
        rows = [("KCB", "FY2025", "2025-12-31", 20.0, 16.0, "q", "u1", "2026-03-15T00:00:00+00:00"),
                ("KCB", "H1 2026", "2026-06-30", 9.13, 7.5, "q", "u2", "2026-08-20T00:00:00+00:00"),
                ("SCOM", "FY2026", None, 1.2, None, "q", "u3", "2026-05-10T00:00:00+00:00")]
        db.executemany("INSERT INTO reported_eps VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        growth = results.latest_growth(db, today=date(2026, 10, 28))
        self.assertAlmostEqual(growth["KCB"][0], 9.13 / 7.5 - 1)
        self.assertEqual(growth["KCB"][1], "H1 2026")
        self.assertNotIn("SCOM", growth)   # no prior-year figure, so no growth

    def test_period_labels(self):
        self.assertEqual(results.period_key("H1 2026"), ("H1", 2026))
        self.assertEqual(results.period_key("HALF-YEAR (INTERIM) 2026"), ("H1", 2026))
        self.assertEqual(results.period_key("FY2025"), ("FY", 2025))
        self.assertEqual(results.period_key("2025"), ("FY", 2025))
        self.assertEqual(results.period_key("Q3 2026"), ("Q3", 2026))
        self.assertIsNone(results.period_key("HALF-YEAR (INTERIM)"))

    def test_growth_pairs_with_the_same_period_a_year_earlier(self):
        db = store.connect(":memory:")
        db.executescript(results.SCHEMA)
        rows = [("KCB", "H1 2025", None, 18.0, None, "q", "u1", "2025-08-14T00:00:00+00:00"),
                ("KCB", "H1 2026", None, 22.45, None, "q", "u2", "2026-08-13T00:00:00+00:00"),
                ("KCB", "FY2025", None, 40.0, None, "q", "u3", "2026-03-20T00:00:00+00:00")]
        db.executemany("INSERT INTO reported_eps VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        growth = results.latest_growth(db, today=date(2026, 10, 28))
        self.assertAlmostEqual(growth["KCB"][0], 22.45 / 18.0 - 1)   # H1 vs H1, not H1 vs FY
        self.assertEqual(growth["KCB"][1], "H1 2026")

    def test_read_results_stores_checked_figures_and_marks_articles_read(self):
        db = store.connect(":memory:")
        from nse_ranker import news
        db.executescript(news.SCHEMA)
        db.execute("INSERT INTO articles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   ("u1", "KWS", "2026-08-20T00:00:00+00:00", ITEMS[0]["title"], "", ITEMS[0]["text"], 1, "KCB", "", "x"))
        fake = lambda *_: {"figures": [figure(), figure(ticker="KCB", period="FY2025", eps=99.0)]}
        read, kept = results.read_results(db, [{"ticker": "KCB", "name": "KCB Group"}], "2026-01-01", ask=fake,
                                          progress=lambda m: None)
        self.assertEqual((read, kept), (1, 1))                       # the made-up 99.0 is dropped
        self.assertEqual(results.candidates(db, "2026-01-01"), [])   # not read twice


if __name__ == "__main__":
    unittest.main()
