"""WORD SEARCH SHORT-WORD CRASH REPAIR.

REPRODUCTION (smallest deterministic form)
--------------------------------------------
    build_word_search_puzzles(
        mode="custom_word_list", custom_words="<8 real words>",
        number_of_puzzles=2, words_per_puzzle=10, output_type="book",
    )
Requires 20 words, has 8 -- a deficit of 12, within the "small enough to
top up" threshold (deficit <= max(15, 15% of required)) -- which reaches
the top-up call unconditionally on `matched_pack_id`.

ROOT CAUSE
----------
services/word_search/book.py's build_word_search_puzzles() only assigned
`matched_pack_id` inside the `elif mode_key == "topic":` branch. The
shared top-up block below (reached whenever a BOOK's word requirement
comes up short, from EITHER mode) unconditionally reads that name:

    entries, topup_warnings = supplement_entries_to_count(
        entries, required_words, grid_size=size,
        topic=theme_label, matched_pack_id=matched_pack_id,
    )
    ...
    if not matched_pack_id:

For custom_word_list mode, `matched_pack_id` was simply never bound ->
UnboundLocalError, every time a submitted custom list needed topping up.
Topic mode was never affected (it always assigns the name itself).

INTENDED BEHAVIOR (determined from existing code, not invented)
------------------------------------------------------------------
services.word_search.word_lists.supplement_entries_to_count already
documents and implements the correct behavior for "no specific pack
matched": skip pack-specific re-fetching and use ONLY the topic-agnostic
`generic_fallback` word pool ("NEVER pull from unrelated topic packs").
_collect_entries_from_topic itself returns `matched_pack_id=""` in
exactly that situation. The fix initializes `matched_pack_id = ""` before
branching, so custom_word_list mode takes the identical, already-existing
"no pack matched" safe path supplement_entries_to_count was built for --
no new behavior invented, no duplicate/nonsense word generation, no
network/AI call.

If, even after generic-fallback top-up, there still are not enough words,
the function returns a clear customer-safe error (unchanged, pre-existing
message) rather than crashing or fabricating words to hit the count.

No external/paid API call is made by any test in this file (custom-word-
list cases only use local word-list logic; topic-mode cases that DO
exercise `suggest_words_from_topic`/generic fallback are still local-only
-- see NoExternalCallTests).
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from services.word_search.book import build_word_search_puzzles  # noqa: E402
from services.product import _word_search_pdf_payload, normalize_word_search_project_data  # noqa: E402

SIXTY_WORDS = [
    "apple", "banana", "cherry", "dragon", "energy", "forest", "garden", "harbor", "island", "jungle",
    "kitten", "ladder", "meadow", "napkin", "ocean", "pencil", "quartz", "rabbit", "silver", "temple",
    "umbrella", "violet", "walnut", "yellow", "zephyr", "anchor", "bridge", "candle", "desert", "eagle",
    "feather", "granite", "hammer", "igloo", "jacket", "kettle", "lantern", "marble", "needle", "orange",
    "pebble", "quiver", "ribbon", "saddle", "turtle", "unicorn", "velvet", "willow", "xylophone", "yogurt",
    "zebra", "blossom", "canyon", "diamond", "engine", "falcon", "glacier", "harvest", "ivory", "jasmine",
]
EIGHT_WORDS = SIXTY_WORDS[:8]
TWO_WORDS = SIXTY_WORDS[:2]


class ReproductionNoLongerCrashesTests(unittest.TestCase):
    def test_slightly_short_custom_list_no_longer_raises_unboundlocalerror(self):
        """The exact reported crash: must not raise at all."""
        try:
            puzzles, warnings, errors = build_word_search_puzzles(
                mode="custom_word_list", product_title="Test",
                custom_words="\n".join(EIGHT_WORDS),
                difficulty="easy", grid_size=15,
                number_of_puzzles=2, words_per_puzzle=10, output_type="book",
            )
        except UnboundLocalError:
            self.fail("UnboundLocalError on matched_pack_id must never happen")
        self.assertEqual(errors, [])
        self.assertEqual(len(puzzles), 2)

    def test_severely_short_custom_list_returns_a_clear_error_not_a_crash(self):
        """Below the absolute floor (MIN_WORDS_PER_PUZZLE=4 -- cannot build
        even one real puzzle): a customer-safe validation error, not a
        crash, not fabricated/duplicate words. See
        AdaptiveSizingTests below for the case that now succeeds instead
        of erroring: enough words for at least one puzzle, just not the
        full requested count/size."""
        try:
            puzzles, warnings, errors = build_word_search_puzzles(
                mode="custom_word_list", product_title="Test",
                custom_words="\n".join(TWO_WORDS),
                difficulty="easy", grid_size=15,
                number_of_puzzles=5, words_per_puzzle=10, output_type="book",
            )
        except UnboundLocalError:
            self.fail("UnboundLocalError on matched_pack_id must never happen")
        self.assertEqual(puzzles, [])
        self.assertTrue(errors)
        self.assertIn("Not enough", errors[0])


class AdaptiveSizingTests(unittest.TestCase):
    """"If there are not enough words, make the puzzle smaller" (user
    request, 2026-09-08): a request whose word supply cannot fill the
    requested puzzle_count x words_per_puzzle -- even after generic-
    fallback top-up -- must no longer be rejected outright as long as at
    least one real puzzle (>= MIN_WORDS_PER_PUZZLE words) can be built.
    Never fabricates or duplicates words; only ever uses fewer of the
    real, already-collected words than originally requested."""

    FIFTEEN_WORDS = "\n".join([
        "apple", "banana", "cherry", "dragon", "energy", "forest", "garden", "harbor", "island", "jungle",
        "kitten", "ladder", "meadow", "napkin", "ocean",
    ])
    TWENTY_FIVE_WORDS = "\n".join([
        "apple", "banana", "cherry", "dragon", "energy", "forest", "garden", "harbor", "island", "jungle",
        "kitten", "ladder", "meadow", "napkin", "ocean", "pencil", "quartz", "rabbit", "silver", "temple",
        "umbrella", "violet", "walnut", "yellow", "zephyr",
    ])

    def test_reduces_puzzle_count_when_even_the_floor_words_per_puzzle_cannot_be_met(self):
        """15 words, 5 puzzles x 10 words = 50 needed. 15 // 4 (the floor)
        = 3 -- build 3 full-floor puzzles instead of failing."""
        puzzles, warnings, errors = build_word_search_puzzles(
            mode="custom_word_list", product_title="Test",
            custom_words=self.FIFTEEN_WORDS,
            difficulty="easy", grid_size=15,
            number_of_puzzles=5, words_per_puzzle=10, output_type="book",
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(puzzles), 3)
        self.assertTrue(any("built 3 of the requested 5" in w for w in warnings))

    def test_reduces_words_per_puzzle_when_puzzle_count_can_still_be_met(self):
        """25 words, 5 puzzles x 10 words = 50 needed. 25 // 5 = 5 words
        per puzzle (>= the floor) -- keeps all 5 requested puzzles,
        shrinks each one instead."""
        puzzles, warnings, errors = build_word_search_puzzles(
            mode="custom_word_list", product_title="Test",
            custom_words=self.TWENTY_FIVE_WORDS,
            difficulty="easy", grid_size=15,
            number_of_puzzles=5, words_per_puzzle=10, output_type="book",
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(puzzles), 5)
        self.assertTrue(any("reduced to 5 words per puzzle" in w for w in warnings))

    def test_below_the_floor_still_fails_cleanly_rather_than_building_an_empty_puzzle(self):
        """3 words cannot build even one real puzzle (floor is 4) -- must
        still be a clean error, never a crash or a fabricated puzzle."""
        puzzles, warnings, errors = build_word_search_puzzles(
            mode="custom_word_list", product_title="Test",
            custom_words="apple\nbanana\ncherry",
            difficulty="easy", grid_size=15,
            number_of_puzzles=5, words_per_puzzle=10, output_type="book",
        )
        self.assertEqual(puzzles, [])
        self.assertTrue(errors)

    def test_no_words_are_fabricated_or_duplicated_by_adaptive_sizing(self):
        """Every placed word across the shrunk book must come from the
        customer's own submitted list -- nothing invented."""
        submitted = {w.upper() for w in self.FIFTEEN_WORDS.split("\n")}
        puzzles, warnings, errors = build_word_search_puzzles(
            mode="custom_word_list", product_title="Test",
            custom_words=self.FIFTEEN_WORDS,
            difficulty="easy", grid_size=15,
            number_of_puzzles=5, words_per_puzzle=10, output_type="book",
        )
        self.assertEqual(errors, [])
        placed = set()
        for p in puzzles:
            for w in p.placed_words:
                placed.add(str(getattr(w, "display", w)).upper())
        self.assertTrue(placed)
        self.assertTrue(placed <= submitted, f"unexpected words not in the submitted list: {placed - submitted}")

    def test_end_to_end_via_the_real_customer_payload(self):
        """Through services.product._word_search_pdf_payload (the real
        entry point), a request whose word count comes up short still
        produces a downloadable product instead of an error."""
        result = _word_search_pdf_payload({
            "topic": "Test", "output_format": "Full Book", "puzzles": "5",
            "words_per_puzzle": "10", "difficulty": "Easy",
            "creation_mode": "Custom word list", "custom_words": self.FIFTEEN_WORDS,
            "include_answer_key": "No", "include_cover": "No",
        })
        self.assertTrue(result.get("pdf_bytes"))


class NormalTopicWithEnoughWordsTests(unittest.TestCase):
    def test_topic_mode_is_unaffected_by_this_repair(self):
        """Topic mode always assigned matched_pack_id itself -- confirm the
        fix's added initialization does not change its behavior."""
        try:
            puzzles, warnings, errors = build_word_search_puzzles(
                mode="topic", product_title="Test", topic="ocean animals",
                difficulty="easy", grid_size=15,
                number_of_puzzles=1, words_per_puzzle=6, output_type="single_worksheet",
            )
        except UnboundLocalError:
            self.fail("UnboundLocalError must never happen")
        # single_worksheet never reaches the book top-up block at all;
        # this only proves topic mode still runs end to end with no crash.
        self.assertIsInstance(errors, list)


class ManualCustomWordListUnaffectedTests(unittest.TestCase):
    """Manual/custom word-list mode must remain unchanged for the case the
    defect never affected: plenty of words, no top-up ever attempted."""

    def test_custom_list_with_plenty_of_words_builds_normally(self):
        puzzles, warnings, errors = build_word_search_puzzles(
            mode="custom_word_list", product_title="Test",
            custom_words="\n".join(SIXTY_WORDS),
            difficulty="easy", grid_size=15,
            number_of_puzzles=6, words_per_puzzle=10, output_type="book",
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(puzzles), 6)

    def test_custom_list_single_worksheet_never_reaches_the_top_up_path(self):
        puzzles, warnings, errors = build_word_search_puzzles(
            mode="custom_word_list", product_title="Test",
            custom_words="\n".join(EIGHT_WORDS[:4]),
            difficulty="easy", grid_size=15,
            number_of_puzzles=1, words_per_puzzle=10, output_type="single_worksheet",
        )
        self.assertEqual(errors, [])
        self.assertEqual(len(puzzles), 1)


class EndToEndPayloadTests(unittest.TestCase):
    """Through the real customer-facing entry point
    (services.product._word_search_pdf_payload), not just the low-level
    builder function."""

    def test_full_book_with_a_slightly_short_custom_list_generates_cleanly(self):
        result = _word_search_pdf_payload({
            "topic": "Test", "output_format": "Full Book", "puzzles": "2",
            "words_per_puzzle": "10", "difficulty": "Easy",
            "creation_mode": "Custom word list", "custom_words": "\n".join(EIGHT_WORDS),
            "include_answer_key": "Yes", "include_cover": "No",
        })
        self.assertTrue(result.get("pdf_bytes"))


class SaveReopenTests(unittest.TestCase):
    """normalize_word_search_project_data (the reopen path) must not
    itself crash or lose the customer's custom word list."""

    def test_reopen_preserves_a_short_custom_word_list_without_crashing(self):
        data = normalize_word_search_project_data({
            "product_type": "word_search",
            "fields": {
                "topic": "Test", "output_format": "Full Book", "puzzles": "2",
                "words_per_puzzle": "10", "creation_mode": "Custom word list",
                "custom_words": "\n".join(EIGHT_WORDS),
            },
            "custom_words": "\n".join(EIGHT_WORDS),
        })
        self.assertIn("fields", data)


class NoExternalCallTests(unittest.TestCase):
    def test_custom_list_top_up_makes_no_ai_or_network_call(self):
        from unittest.mock import patch

        with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json:
            build_word_search_puzzles(
                mode="custom_word_list", product_title="Test",
                custom_words="\n".join(EIGHT_WORDS),
                difficulty="easy", grid_size=15,
                number_of_puzzles=2, words_per_puzzle=10, output_type="book",
            )
            self.assertFalse(chat.called)
            self.assertFalse(chat_json.called)


class ProtectedBaselineContractTests(unittest.TestCase):
    """PERMANENT REGRESSION CONTRACT: Word Search's custom-word-list book
    path must never crash with UnboundLocalError on matched_pack_id again,
    for any deficit size."""

    def test_no_deficit_size_ever_raises_unboundlocalerror(self):
        for word_count, n_puzzles in ((2, 5), (8, 2), (20, 3), (60, 6)):
            with self.subTest(word_count=word_count, n_puzzles=n_puzzles):
                try:
                    build_word_search_puzzles(
                        mode="custom_word_list", product_title="Test",
                        custom_words="\n".join(SIXTY_WORDS[:word_count]),
                        difficulty="easy", grid_size=15,
                        number_of_puzzles=n_puzzles, words_per_puzzle=10, output_type="book",
                    )
                except UnboundLocalError:
                    self.fail(f"UnboundLocalError for word_count={word_count}, n_puzzles={n_puzzles}")


if __name__ == "__main__":
    unittest.main()
