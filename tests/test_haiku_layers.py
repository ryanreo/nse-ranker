"""Tests for the Haiku layers, with a fake Haiku. Run with: python -m unittest"""
import unittest
from datetime import date

from nse_ranker import insights, opinion, review, store

ITEMS = [{
    "article": 0, "title": "KCB profit jumps 20%", "summary": "Net profit rose to Sh60bn.",
    "text": "KCB Group said net profit rose 20 percent to Sh60 billion on higher lending.",
    "stocks": [{"ticker": "KCB", "name": "KCB Group"}], "sectors": ["Banking"],
}]


def tag(**changes):
    base = {"article": 0, "ticker": "KCB", "sector": None, "event": "profit up", "direction": 1,
            "strength": 3, "quote": "net profit rose 20 percent"}
    return dict(base, **changes)


class TestNewsTags(unittest.TestCase):
    def test_good_tag_is_kept(self):
        self.assertEqual(len(insights.check_tags([tag()], ITEMS)), 1)

    def test_made_up_quote_is_dropped(self):
        self.assertEqual(insights.check_tags([tag(quote="record dividend announced")], ITEMS), [])

    def test_stock_not_matched_to_the_article_is_dropped(self):
        self.assertEqual(insights.check_tags([tag(ticker="EQTY")], ITEMS), [])

    def test_sector_tag_must_be_an_allowed_sector(self):
        self.assertEqual(len(insights.check_tags([tag(ticker=None, sector="Banking")], ITEMS)), 1)
        self.assertEqual(insights.check_tags([tag(ticker=None, sector="Insurance")], ITEMS), [])

    def test_bad_article_number_is_dropped(self):
        self.assertEqual(insights.check_tags([tag(article=5)], ITEMS), [])

    def test_news_score(self):
        stocks = [{"ticker": "KCB", "sector": "Banking"}, {"ticker": "EQTY", "sector": "Banking"},
                  {"ticker": "SCOM", "sector": "Telecommunication"}]
        tags = [
            {"ticker": "KCB", "sector": None, "direction": 1, "strength": 3, "published": "2026-10-28"},
            {"ticker": None, "sector": "Banking", "direction": -1, "strength": 2, "published": "2026-10-28"},
        ]
        scores = insights.news_scores(tags, stocks, today=date(2026, 10, 28))
        self.assertGreater(scores["KCB"], 50)     # +3 own news, -1 sector news
        self.assertLess(scores["EQTY"], 50)       # only the bad sector news
        self.assertNotIn("SCOM", scores)          # no news: factor left out

    def test_old_news_fades(self):
        stock = [{"ticker": "KCB", "sector": "Banking"}]
        fresh = insights.news_scores([{"ticker": "KCB", "sector": None, "direction": 1, "strength": 2,
                                       "published": "2026-10-28"}], stock, date(2026, 10, 28))
        old = insights.news_scores([{"ticker": "KCB", "sector": None, "direction": 1, "strength": 2,
                                     "published": "2026-10-01"}], stock, date(2026, 10, 28))
        self.assertGreater(fresh["KCB"], old["KCB"])


class TestOpinion(unittest.TestCase):
    STOCK = {"ticker": "SCOM", "name": "Safaricom", "aliases": ["Safaricom"]}
    POSTS = [{"platform": "Reddit", "author": "a", "text": "Safaricom dividend looks safe this year", "url": "u1"},
             {"platform": "X", "author": "b", "text": "Bought more Safaricom shares today", "url": "u2"}]

    def test_quotes_are_checked_against_the_posts(self):
        fake = lambda *_: {"sentiment": 0.6, "hype": False, "summary": "Positive.",
                           "quotes": [{"post": 0, "quote": "dividend looks safe"}, {"post": 1, "quote": "to the moon"}]}
        reading = opinion.summarise(self.STOCK, self.POSTS, ask=fake)
        self.assertEqual(reading["quotes"], [{"quote": "dividend looks safe", "url": "u1"}])

    def test_no_real_quotes_means_no_reading(self):
        fake = lambda *_: {"sentiment": 1, "hype": False, "summary": "x", "quotes": [{"post": 0, "quote": "made up"}]}
        self.assertIsNone(opinion.summarise(self.STOCK, self.POSTS, ask=fake))

    def test_hype_counts_half(self):
        self.assertEqual(opinion.opinion_score({"sentiment": 0.8, "hype": False}), 90)
        self.assertEqual(opinion.opinion_score({"sentiment": 0.8, "hype": True}), 70)

    def test_a_source_that_isnt_set_up_is_skipped_once(self):
        calls = []

        def broken(stock):
            calls.append(stock["ticker"])
            return [], "X not set up"
        db = store.connect(":memory:")
        stocks = [self.STOCK, dict(self.STOCK, ticker="KCB")]
        problems = opinion.collect(db, stocks, sources={"X": broken}, progress=lambda m: None)
        self.assertEqual(problems, ["X not set up"])
        self.assertEqual(calls, ["SCOM"])   # not tried again for KCB


def brief(news_ids=(), opinion_id=None):
    return {"ticker": "KCB", "news": [{"id": i} for i in news_ids],
            "opinion": {"id": opinion_id} if opinion_id else None}


class TestReview(unittest.TestCase):
    def verdict(self, move, evidence, case="strong"):
        return {"ticker": "KCB", "case": case, "explanation": "Cheap with good news.",
                "move": move, "evidence": evidence}

    def test_news_backed_move_is_kept(self):
        self.assertEqual(review.check_verdict(self.verdict(3, ["N7"]), brief(["N7"]))["move"], 3)

    def test_moves_are_capped_at_five(self):
        self.assertEqual(review.check_verdict(self.verdict(9, ["N7"]), brief(["N7"]))["move"], 5)

    def test_factors_alone_cannot_move_a_stock(self):
        self.assertEqual(review.check_verdict(self.verdict(4, ["value", "momentum"]), brief())["move"], 0)

    def test_opinion_alone_moves_at_most_one_place(self):
        checked = review.check_verdict(self.verdict(5, ["O:KCB"]), brief(opinion_id="O:KCB"))
        self.assertEqual(checked["move"], 1)

    def test_made_up_evidence_is_ignored(self):
        checked = review.check_verdict(self.verdict(4, ["N99"]), brief(["N7"]))
        self.assertEqual((checked["move"], checked["evidence"]), (0, []))

    def test_unknown_case_becomes_mixed(self):
        self.assertEqual(review.check_verdict(self.verdict(0, [], case="buy now"), brief())["case"], "mixed")

    def test_final_order_applies_moves(self):
        ranked = [{"ticker": t} for t in ("A", "B", "C", "D")]
        # A, B and D all aim for 2nd: D (moving up) first, then B (stayed), then A (moving down)
        order = review.final_order(ranked, {"D": {"move": 2}, "A": {"move": -1}})
        self.assertEqual([r["ticker"] for r in order], ["D", "B", "A", "C"])
        self.assertEqual([r["ticker"] for r in review.final_order(ranked, {})], ["A", "B", "C", "D"])


if __name__ == "__main__":
    unittest.main()
