"""The reviewer only looks, unless you name one id.

Rows stamped system_test=1 by the old title rule keep their flags: a sweep that
guessed again could just as easily un-hide a genuine internal record. This
script lists the candidates and restores exactly the one you name, and refuses
any row that still has a real reason to be hidden.
"""
import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("FACTORY_TEST_MODE", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import database  # noqa: E402


class ReviewHiddenBooksTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._old = database.DB_PATH
        database.DB_PATH = self._tmp.name
        database.init_db()
        self.review = importlib.import_module("review_hidden_books")
        importlib.reload(self.review)
        self.review.database.DB_PATH = self._tmp.name

    def tearDown(self):
        database.DB_PATH = self._old
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(self._tmp.name + suffix)
            except OSError:
                pass

    def _stamp_as_the_old_rule_would(self, title: str) -> int:
        """Create the row the old classifier produced: hidden, on title alone."""
        row = database.create_project(title, "ebook", {"title": title},
                                      user_saved=False, system_test=True, temporary=True)
        return int(row["id"])

    def test_a_real_book_hidden_by_its_title_is_listed(self):
        pid = self._stamp_as_the_old_rule_would("Test Kitchen Favourites")
        listed = {row["id"] for row in self.review.candidates()}
        self.assertIn(pid, listed)

    def test_a_genuine_internal_record_is_not_listed(self):
        pid = self._stamp_as_the_old_rule_would("[TEST] Download Proof Test")
        listed = {row["id"] for row in self.review.candidates()}
        self.assertNotIn(pid, listed, "an unmistakable internal record was offered for restoring")

    def test_listing_changes_nothing(self):
        pid = self._stamp_as_the_old_rule_would("The QA Handbook")
        self.review.candidates()
        row = database.get_project(pid)
        self.assertEqual((row["user_saved"], row["system_test"], row["temporary"]), (0, 1, 1))

    def test_unhide_restores_exactly_the_one_named(self):
        keep_hidden = self._stamp_as_the_old_rule_would("Debug Your Life")
        pid = self._stamp_as_the_old_rule_would("Test Kitchen Favourites")
        self.assertEqual(self.review.unhide(pid), 0)
        visible = {p["id"] for p in database.list_projects()}
        self.assertIn(pid, visible)
        self.assertNotIn(keep_hidden, visible, "unhide touched a row it was not given")

    def test_unhide_refuses_a_record_that_still_classifies_as_hidden(self):
        pid = self._stamp_as_the_old_rule_would("[TEST] Download Proof Test")
        self.assertEqual(self.review.unhide(pid), 2)
        visible = {p["id"] for p in database.list_projects()}
        self.assertNotIn(pid, visible)

    def test_unhide_refuses_an_unknown_id(self):
        self.assertEqual(self.review.unhide(99999999), 1)


if __name__ == "__main__":
    unittest.main()
