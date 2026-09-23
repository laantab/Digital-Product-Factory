"""A customer's own words must not classify their book as disposable test data.

classify_customer_visibility runs at creation and stamps system_test=1 into the
database permanently. A bare word in the title -- test, qa, debug, fixture,
placeholder, regression, handoff -- was enough. So a paid-for book called "Test
Kitchen Favourites" or "The QA Handbook" was hidden from its owner's Saved
Projects with no message and no route back through the product, AND was
classified as deletable by the bulk clean-up route.

Those words are ordinary in real book titles. The signal was never the
customer's wording; it is what the caller and the record's own metadata say.
A bare word in the title alone is now a needs_decision, the same treatment
"system", "internal", "seed" and "pipeline" already had. Unambiguous markers --
a [TEST] label, a strong phrase like "smoke test" or "download proof", or the
word appearing in the record's type or product label rather than its title --
still hide, because those are not a customer's wording.
"""
import os
import unittest

os.environ.setdefault("FACTORY_TEST_MODE", "1")

import database  # noqa: E402


REAL_TITLES = [
    "Test Kitchen Favourites",
    "The QA Handbook",
    "Debug Your Life",
    "The Placeholder Generation",
    "Fixture Photography",
    "QA for Software Teams",
    "Regression to the Mean",
    "The Handoff: Leading Through Change",
    "Workflow Mastery",
    "Seed Starting for Beginners",
    "Container Gardening for Beginners",
]

STILL_HIDDEN = [
    "[TEST] LockDel Hidden",
    "Smoke Test Run 4",
    "Download Proof Test",
    "Guided Cover Isolated",
    "Pipeline Test Harness",
]


class ACustomersTitleDoesNotHideTheirBookTests(unittest.TestCase):
    def test_a_real_book_title_is_never_classified_as_a_test_record(self):
        for title in REAL_TITLES:
            with self.subTest(title=title):
                vis = database.classify_customer_visibility(title, "ebook", {"title": title})
                self.assertFalse(
                    vis.get("hide"),
                    f"{title!r} was hidden from its own owner: {vis}",
                )
                self.assertFalse(vis.get("system_test"), title)
                self.assertFalse(vis.get("internal_record"), title)

    def test_an_unmistakable_internal_record_is_still_hidden(self):
        for title in STILL_HIDDEN:
            with self.subTest(title=title):
                vis = database.classify_customer_visibility(title, "ebook", {"title": title})
                self.assertTrue(vis.get("hide"), f"{title!r} should still be hidden: {vis}")

    def test_the_word_still_counts_when_it_is_the_records_own_metadata(self):
        """"test" in a product label is the system's word, not the customer's."""
        vis = database.classify_customer_visibility(
            "Container Gardening for Beginners", "ebook",
            {"title": "Container Gardening for Beginners", "product_label": "debug record"},
        )
        self.assertTrue(vis.get("hide"), f"a debug product label should hide: {vis}")

    def test_an_explicit_flag_from_the_caller_is_still_obeyed(self):
        vis = database.classify_customer_visibility(
            "System Test - Six Template Studio", "ebook",
            {"title": "System Test - Six Template Studio", "_test_reason": "system test"},
        )
        self.assertTrue(vis.get("hide"), f"a declared system test should hide: {vis}")


class TheBookSurvivesTheWholeSavePathTests(unittest.TestCase):
    """The classifier is one step; what matters is the row the customer gets."""

    def setUp(self):
        import tempfile

        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._old = database.DB_PATH
        database.DB_PATH = self._tmp.name
        database.init_db()

    def tearDown(self):
        database.DB_PATH = self._old
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(self._tmp.name + suffix)
            except OSError:
                pass

    def test_a_customer_can_find_their_own_book_in_saved_projects(self):
        missing = []
        for title in REAL_TITLES:
            row = database.create_project(title, "ebook", {"title": title})
            visible = {p["id"] for p in database.list_projects()}
            if row["id"] not in visible:
                missing.append((title, row["system_test"], row["temporary"], row["user_saved"]))
        self.assertEqual(missing, [], f"books hidden from their own owner: {missing}")

    def test_a_flagged_system_record_is_still_kept_out_of_the_customer_list(self):
        row = database.create_project(
            "Container Gardening for Beginners", "ebook", {"title": "Container Gardening for Beginners"},
            system_test=True, temporary=True,
        )
        visible = {p["id"] for p in database.list_projects()}
        self.assertNotIn(row["id"], visible, "an explicitly flagged record leaked into the customer list")


if __name__ == "__main__":
    unittest.main()
