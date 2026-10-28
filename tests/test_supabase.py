"""Run with: python -m unittest"""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from nse_ranker import supabase


class TestPush(unittest.TestCase):
    def setUp(self):
        self.env = Path(tempfile.mkdtemp()) / ".env"
        self.env.write_text("SUPABASE_URL=https://example.supabase.co/\nSUPABASE_SECRET_KEY=sb_secret_test\n")
        self.calls = []

    def send(self, method, url, body=None, headers=None):
        self.calls.append((method, url, body, headers))
        return b""

    def test_missing_settings_explain_what_to_add(self):
        empty = Path(tempfile.mkdtemp()) / ".env"
        with self.assertRaisesRegex(RuntimeError, "SUPABASE_SECRET_KEY"):
            supabase.push({}, env_file=empty, send=self.send)

    def test_rows_are_upserted_with_run_date_and_only_known_columns(self):
        tables = {
            "ranking": [{"ticker": "KCB", "score": 76.4, "position": 1}],
            "posts": [{"id": "abc", "ticker": "KCB", "platform": "X", "posted": "2026-10-28", "text": "hi",
                       "author": "should_not_be_sent"}],
        }
        supabase.push(tables, run_date=date(2026, 10, 28), send=self.send, env_file=self.env, progress=lambda m: None)
        posts = [c for c in self.calls if "/posts?" in c[1]][0]
        self.assertEqual(posts[0], "POST")
        self.assertIn("on_conflict=id", posts[1])
        self.assertNotIn("author", posts[2][0])
        self.assertEqual(posts[3]["apikey"], "sb_secret_test")
        self.assertIn("merge-duplicates", posts[3]["Prefer"])
        rankings = [c for c in self.calls if "/rankings?" in c[1]][0]
        self.assertEqual(rankings[2][0]["run_date"], "2026-10-28")

    def test_not_ranked_is_replaced_not_merged(self):
        supabase.push({"not_ranked": [{"ticker": "LIMT", "status": "Thin trading"}]}, send=self.send,
                      env_file=self.env, progress=lambda m: None)
        methods = [(m, u.split("/rest/v1/")[1].split("?")[0]) for m, u, _, _ in self.calls if "not_ranked" in u]
        self.assertEqual(methods, [("DELETE", "not_ranked"), ("POST", "not_ranked")])

    def test_big_tables_go_in_batches(self):
        rows = [{"ticker": "KCB", "day": f"2026-01-{i % 28 + 1:02d}", "close": 1.0} for i in range(1200)]
        supabase.push({"prices": rows}, send=self.send, env_file=self.env, progress=lambda m: None)
        self.assertEqual(len([c for c in self.calls if "/prices?" in c[1]]), 3)


if __name__ == "__main__":
    unittest.main()
