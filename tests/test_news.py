"""Run with: python -m unittest"""
import unittest
from datetime import date

from nse_ranker import news, store

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item>
  <title>Dangote buys 25pc of Kenya Pipeline for Sh42.5b</title>
  <link>https://example.co.ke/dangote-kpc/?utm_source=rss&amp;utm_medium=feed</link>
  <pubDate>Thu, 22 Oct 2026 10:00:00 +0300</pubDate>
  <description>&lt;p&gt;The deal values KPC at &amp;amp; more.&lt;/p&gt;</description>
  <content:encoded><![CDATA[<p><strong>NAIROBI</strong> - Full story about the pipeline.</p>]]></content:encoded>
</item>
<item><title>No link here</title></item>
</channel></rss>"""

SOURCE = {"name": "Test Paper", "ai_use": True}
STOCKS = [
    {"ticker": "KPC", "aliases": ["Kenya Pipeline", "KPC"]},
    {"ticker": "EQTY", "aliases": ["Equity Bank", "Equity Group"]},
    {"ticker": "KNRE", "aliases": ["Kenya Re"]},
    {"ticker": "KCB", "aliases": ["KCB"]},
]
TOPICS = {"interest rates": {"sectors": ["Banking"], "keywords": ["Central Bank Rate", "CBK"]}}


def article(title, summary="", text=None):
    return {"url": f"https://x/{title}", "source": "Test", "published": "2026-10-27T10:00:00+00:00",
            "title": title, "summary": summary, "text": text, "ai_use": 1}


class TestFeed(unittest.TestCase):
    def test_parses_items_and_cleans_them(self):
        [item] = news.parse_feed(FEED, SOURCE)   # the item without a link is skipped
        self.assertEqual(item["url"], "https://example.co.ke/dangote-kpc/")   # tracking removed
        self.assertEqual(item["published"], "2026-10-22T07:00:00+00:00")      # stored in UTC
        self.assertEqual(item["summary"], "The deal values KPC at & more.")
        self.assertEqual(item["text"], "NAIROBI - Full story about the pipeline.")
        self.assertEqual(item["ai_use"], 1)


class TestMatcher(unittest.TestCase):
    def setUp(self):
        self.matcher = news.Matcher(STOCKS, TOPICS)

    def test_names_and_topics(self):
        tickers, topics = self.matcher.match(article("KCB and Equity Bank react as CBK holds rate"))
        self.assertEqual((tickers, topics), (["EQTY", "KCB"], ["interest rates"]))

    def test_capitals_must_match_exactly_for_acronyms(self):
        self.assertEqual(self.matcher.match(article("Kcb fans cheer"))[0], [])
        self.assertEqual(self.matcher.match(article("kenya pipeline output rises"))[0], ["KPC"])

    def test_whole_words_only(self):
        self.assertEqual(self.matcher.match(article("Kenya Revenue Authority targets"))[0], [])
        self.assertEqual(self.matcher.match(article("Kenya Re-Insurance profit up"))[0], ["KNRE"])
        self.assertEqual(self.matcher.match(article("Equity markets rally"))[0], [])

    def test_searches_summary_and_text_too(self):
        tickers, _ = self.matcher.match(article("Deal done", summary="", text="buyer of KPC shares"))
        self.assertEqual(tickers, ["KPC"])


class TestStorage(unittest.TestCase):
    def setUp(self):
        self.db = store.connect(":memory:")
        self.matcher = news.Matcher(STOCKS, TOPICS)

    def test_saving_twice_keeps_one_copy(self):
        items = news.parse_feed(FEED, SOURCE)
        self.assertEqual(news.save_articles(self.db, items, self.matcher), 1)
        self.assertEqual(news.save_articles(self.db, items, self.matcher), 0)

    def test_direct_and_sector_news_for_a_stock(self):
        news.save_articles(self.db, [
            article("KCB profit jumps"),
            article("CBK cuts the Central Bank Rate"),
            article("Kenya Pipeline volumes"),
        ], self.matcher)
        kcb = {"ticker": "KCB", "sector": "Banking"}
        direct, sector = news.for_stock(self.db, kcb, days=7, today=date(2026, 10, 28), topics=TOPICS)
        self.assertEqual([a["title"] for a in direct], ["KCB profit jumps"])
        self.assertEqual([a["title"] for a in sector], ["CBK cuts the Central Bank Rate"])

    def test_rematch_applies_new_aliases(self):
        news.save_articles(self.db, [article("Olympia stake sold")], self.matcher)
        news.rematch(self.db, news.Matcher([{"ticker": "OCH", "aliases": ["Olympia"]}], {}))
        self.assertEqual(news.summary(self.db, 7, today=date(2026, 10, 28)), {"OCH": 1})


if __name__ == "__main__":
    unittest.main()
