"""CROSSWORD GENERATOR PROTECTED BASELINE — Include Cover selection repair.

ROOT CAUSE
----------
services.product._crossword_pdf_payload decided whether to build a cover
from `is_book` alone: `if is_book: cover = ...`. It never read the
customer's own "Include cover page" Yes/No field at all. Confirmed
end-to-end before this fix: a Full Book with Include Cover = "No" produced
the exact same 13-page PDF (with a cover) as Include Cover = "Yes".

This is NOT the same bug the "Number of puzzles" repair fixed (that one
was a hard override -- `worksheets = 12` -- this one is a field that was
simply never consulted).

WHY THIS IS A SAFE, CROSSWORD-ONLY FIX
---------------------------------------
services.factory.puzzle_plan.parse_puzzle_output_plan (shared by every
worksheet-type product: word_search, crossword, math_worksheet,
spelling_worksheet) also ties its own `include_cover` key to `is_book`
alone and does not read the customer's field either -- but nothing outside
_crossword_pdf_payload ever consumes that specific dict key for crossword,
so changing the SHARED function was unnecessary and out of scope (wider
blast radius across three other product types, forbidden by this task).

The actual, already-shipped, already-correct pattern lives one function
away: _word_search_pdf_payload (same file, sister puzzle-book product)
already has an explicit "form field > default to is_book" override that
correctly makes Include Cover Yes/No control the real PDF. This repair
copies that exact, proven pattern into _crossword_pdf_payload instead of
touching the shared planner -- the smallest safe fix available.

Math Worksheet has the same class of defect (Include Cover Yes/No is
ignored, driven by services.quality.cover_eligibility_agent's
cover_allowed alone) but is NOT touched here -- it is characterized as a
pre-existing, unrelated, out-of-scope finding (see the completion report),
consistent with "do not change shared behavior blindly" and "test Word
Search and Math Worksheet before/after; their behavior must remain
unchanged unless a test proves it defective" (this task does not ask for
that proof or that fix for Math Worksheet).

No external/paid API call is made by any test in this file.
"""
from __future__ import annotations

import base64
import io
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from pypdf import PdfReader  # noqa: E402

from services.factory.puzzle_plan import CROSSWORD_BOOK_PUZZLE_COUNTS  # noqa: E402
from services.product import (  # noqa: E402
    _crossword_pdf_payload,
    _math_worksheet_pdf_payload,
    _word_search_pdf_payload,
    normalize_crossword_project_data,
    rebuild_crossword_pdf_from_data,
)

GOLD_RUSH_FIELDS = {
    "book_title": "California Gold Rush Days",
    "theme": "California Gold Rush Days",
    "creation_mode": "Topic (AI generates words)",
    "difficulty": "Easy",
    "include_answer_key": "Yes",
}

# 60 plain, grid-friendly words -- enough for a 6-puzzle x 10-words-per-
# puzzle Word Search Full Book with no topic-fetch/top-up involved at all.
WORD_SEARCH_SIXTY_WORDS = [
    "apple", "banana", "cherry", "dragon", "energy", "forest", "garden", "harbor", "island", "jungle",
    "kitten", "ladder", "meadow", "napkin", "ocean", "pencil", "quartz", "rabbit", "silver", "temple",
    "umbrella", "violet", "walnut", "yellow", "zephyr", "anchor", "bridge", "candle", "desert", "eagle",
    "feather", "granite", "hammer", "igloo", "jacket", "kettle", "lantern", "marble", "needle", "orange",
    "pebble", "quiver", "ribbon", "saddle", "turtle", "unicorn", "velvet", "willow", "xylophone", "yogurt",
    "zebra", "blossom", "canyon", "diamond", "engine", "falcon", "glacier", "harvest", "ivory", "jasmine",
]


def _page_count(pdf_bytes_b64: str) -> int:
    return len(PdfReader(io.BytesIO(base64.b64decode(pdf_bytes_b64))).pages)


class CoverSelectionBookTests(unittest.TestCase):
    """6.1 / 6.2: Full Book + 8 puzzles + Cover Yes / Cover No."""

    def test_full_book_8_puzzles_cover_yes_includes_the_cover(self):
        fields = dict(GOLD_RUSH_FIELDS, output_format="Full Book", puzzles="8", include_cover="Yes")
        result = _crossword_pdf_payload(fields)
        self.assertEqual(_page_count(result["pdf_bytes"]), 1 + 8 * 2)  # cover + 8 puzzles + 8 keys

    def test_full_book_8_puzzles_cover_no_excludes_the_cover(self):
        fields = dict(GOLD_RUSH_FIELDS, output_format="Full Book", puzzles="8", include_cover="No")
        result = _crossword_pdf_payload(fields)
        self.assertEqual(_page_count(result["pdf_bytes"]), 8 * 2)  # 8 puzzles + 8 keys, no cover

    def test_cover_yes_vs_no_differ_by_exactly_one_page_for_every_allowed_count(self):
        for n in CROSSWORD_BOOK_PUZZLE_COUNTS:
            with self.subTest(count=n):
                yes = _crossword_pdf_payload(dict(GOLD_RUSH_FIELDS, output_format="Full Book", puzzles=str(n), include_cover="Yes"))
                no = _crossword_pdf_payload(dict(GOLD_RUSH_FIELDS, output_format="Full Book", puzzles=str(n), include_cover="No"))
                self.assertEqual(_page_count(yes["pdf_bytes"]) - _page_count(no["pdf_bytes"]), 1)


class CoverSelectionSinglePageTests(unittest.TestCase):
    """6.3 / 6.4: Single Page + Cover Yes / Cover No -- never a cover, by
    product design (matches the pre-existing is_book gate, the universal
    Cover Eligibility Agent rule for single-page products, and Word
    Search's own identical behavior). Include Cover only has an effect
    when a book is being built."""

    def test_single_page_cover_yes_still_has_no_cover(self):
        # include_answer_key explicitly "No" to isolate cover behavior --
        # Single page's answer key is independently selectable since
        # 2026-09-09 (see tests/test_crossword_single_format_answer_key_repair.py
        # and tests/test_crossword_scope_answerkey_zip_repair.py), so with
        # it off this test's only variable is the cover.
        fields = dict(GOLD_RUSH_FIELDS, output_format="Single page", include_cover="Yes", include_answer_key="No")
        result = _crossword_pdf_payload(fields)
        self.assertEqual(_page_count(result["pdf_bytes"]), 1)

    def test_single_page_cover_no_has_no_cover(self):
        fields = dict(GOLD_RUSH_FIELDS, output_format="Single page", include_cover="No", include_answer_key="No")
        result = _crossword_pdf_payload(fields)
        self.assertEqual(_page_count(result["pdf_bytes"]), 1)

    def test_single_worksheet_cover_yes_still_has_no_cover(self):
        # include_answer_key explicitly "No" here to isolate cover behavior:
        # Single Worksheet's answer key is independently selectable (a
        # separate, later repair -- see
        # tests/test_crossword_single_format_answer_key_repair.py), so with
        # it off this test's only variable is the cover.
        fields = dict(GOLD_RUSH_FIELDS, output_format="Single Worksheet", include_cover="Yes", include_answer_key="No")
        result = _crossword_pdf_payload(fields)
        self.assertEqual(_page_count(result["pdf_bytes"]), 1)


class SaveReopenGenerateTests(unittest.TestCase):
    """6.5: customer selections (puzzle count AND cover) survive
    Save -> Reopen -> Generate -> Download. rebuild_crossword_pdf_from_data
    is the real reopen/regenerate entry point (services.product), used by
    the actual export/rebuild path -- not a simulation of it."""

    def _saved_project(self, *, puzzles: str, include_cover: str) -> dict:
        """A project dict shaped the way one comes back from the database
        after a customer's initial Save -- fields exactly as submitted,
        nothing yet normalized."""
        return {
            "product_type": "crossword",
            "is_book": True,
            "is_pdf": True,
            "title": "California Gold Rush Days",
            "fields": dict(
                GOLD_RUSH_FIELDS,
                output_format="Full Book",
                puzzles=puzzles,
                include_cover=include_cover,
            ),
        }

    def test_reopen_preserves_a_selected_puzzle_count_and_cover_no(self):
        data = normalize_crossword_project_data(self._saved_project(puzzles="8", include_cover="No"))
        self.assertEqual(data["puzzle_count"], 8)
        self.assertEqual(str(data["fields"]["puzzles"]), "8")
        self.assertEqual(data["fields"]["include_cover"], "No")

        rebuilt = rebuild_crossword_pdf_from_data(data)
        self.assertEqual(_page_count(rebuilt["pdf_bytes"]), 8 * 2)  # no cover

    def test_reopen_preserves_a_selected_puzzle_count_and_cover_yes(self):
        data = normalize_crossword_project_data(self._saved_project(puzzles="10", include_cover="Yes"))
        self.assertEqual(data["puzzle_count"], 10)
        self.assertEqual(str(data["fields"]["puzzles"]), "10")
        self.assertEqual(data["fields"]["include_cover"], "Yes")

        rebuilt = rebuild_crossword_pdf_from_data(data)
        self.assertEqual(_page_count(rebuilt["pdf_bytes"]), 1 + 10 * 2)  # with cover

    def test_reopen_does_not_silently_replace_a_valid_count_with_12(self):
        """The exact prior regression, re-checked from the reopen path
        specifically (not just the plan function)."""
        data = normalize_crossword_project_data(self._saved_project(puzzles="6", include_cover="Yes"))
        self.assertEqual(data["puzzle_count"], 6)
        self.assertNotEqual(data["puzzle_count"], 12)


class PackagingUsesResolvedValuesTests(unittest.TestCase):
    """6.6: packaging/export uses the exact resolved values (puzzle count
    AND cover), not a hardcoded assumption -- exercised through
    services.packaging.build_product_export, the real export entry point."""

    def test_export_produces_a_pdf_matching_the_saved_selection(self):
        from services.packaging import build_product_export

        project = {
            "id": None,
            "name": "California Gold Rush Days",
            "data": {
                "product_type": "crossword",
                "is_pdf": True,
                "is_book": True,
                "title": "California Gold Rush Days",
                "fields": dict(
                    GOLD_RUSH_FIELDS,
                    output_format="Full Book",
                    puzzles="8",
                    include_cover="No",
                ),
            },
        }
        result = build_product_export(project)
        self.assertTrue(result.get("exports", {}).get("pdf_available"))
        from services.ebook_package import EXPORTS_DIR

        pkg_dir = os.path.join(EXPORTS_DIR, result["package_id"])
        pdf_path = next(
            os.path.join(pkg_dir, n) for n in os.listdir(pkg_dir)
            if n.lower().endswith(".pdf") and n != "ebook.pdf"
        )
        with open(pdf_path, "rb") as handle:
            page_count = len(PdfReader(handle).pages)
        self.assertEqual(page_count, 8 * 2)  # 8 puzzles + 8 keys, no cover -- not the 12-puzzle default


class WordSearchAndMathWorksheetUnaffectedTests(unittest.TestCase):
    """7: Word Search and Math Worksheet exercised before/after this patch.
    Word Search's Include Cover already worked (the pattern this repair
    copied FROM it); it must keep working. Math Worksheet's Include Cover
    was already a no-op before this patch and is untouched -- it must stay
    exactly as it was, not newly "fixed" as an accidental side effect."""

    def test_word_search_cover_yes_and_no_still_differ_by_one_page(self):
        # Custom word list, not Topic mode: under FACTORY_TEST_MODE, topic
        # resolution for word_search returns a fixed ~10-word stub
        # regardless of topic text, well short of a 6-puzzle book's 60-word
        # requirement -- deterministically triggering a pre-existing,
        # unrelated crash (services/word_search/book.py raises
        # UnboundLocalError on matched_pack_id when the shortfall reaches
        # its top-up path in custom/non-topic mode). Out of scope for this
        # Crossword-only repair; supplying enough real custom words sidesteps
        # it entirely rather than fighting test-mode word resolution.
        words = "\n".join(WORD_SEARCH_SIXTY_WORDS)
        common = {
            "output_format": "Full Book", "puzzles": "6", "difficulty": "Easy",
            "include_answer_key": "Yes", "creation_mode": "Custom word list",
            "custom_words": words,
        }
        yes = _word_search_pdf_payload(dict(common, include_cover="Yes"))
        no = _word_search_pdf_payload(dict(common, include_cover="No"))
        self.assertEqual(_page_count(yes["pdf_bytes"]) - _page_count(no["pdf_bytes"]), 1)

    def test_math_worksheet_cover_field_now_has_an_effect(self):
        """UPDATED: at the time this file was written, Math Worksheet's
        Include Cover was a documented, deliberately out-of-scope no-op.
        It was fixed in the very next task
        (tests/test_math_worksheet_cover_selection_repair.py has the full
        protected-baseline coverage) -- this assertion is intentionally the
        one that changed, per that test file's own note that it should."""
        yes = _math_worksheet_pdf_payload({
            "worksheet_title": "Addition Practice", "grade": "Grade 3", "math_topic": "Addition",
            "difficulty": "Medium", "output_format": "Full Workbook", "problems": "20",
            "include_answer_key": "Yes", "include_cover": "Yes",
        })
        no = _math_worksheet_pdf_payload({
            "worksheet_title": "Addition Practice", "grade": "Grade 3", "math_topic": "Addition",
            "difficulty": "Medium", "output_format": "Full Workbook", "problems": "20",
            "include_answer_key": "Yes", "include_cover": "No",
        })
        self.assertEqual(_page_count(yes["pdf_bytes"]) - _page_count(no["pdf_bytes"]), 1)


class NoExternalCallTests(unittest.TestCase):
    def test_cover_selection_generation_makes_no_ai_or_network_call(self):
        from unittest.mock import patch

        with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json, \
             patch("services.ebook_pexels._http_get", side_effect=AssertionError("no network calls")):
            for cov in ("Yes", "No"):
                _crossword_pdf_payload(dict(GOLD_RUSH_FIELDS, output_format="Full Book", puzzles="8", include_cover=cov))
            self.assertFalse(chat.called)
            self.assertFalse(chat_json.called)


class ProtectedBaselineContractTests(unittest.TestCase):
    """PERMANENT REGRESSION CONTRACT for the Crossword customer interface.

    This class is the one a future, unrelated Factory repair must break
    (and therefore be caught by CI) before it can silently remove Single
    Page, Single Worksheet, or Full Book, remove the puzzle-count selector,
    force Full Book back to a fixed 12, ignore Include Cover Yes/No, or let
    a saved/reopened selection get silently rewritten. Every assertion here
    checks actual resolved generation and packaging behavior (real PDFs,
    real page counts, real normalize/rebuild functions) -- never just an
    HTML/JS source string.
    """

    def test_output_format_offers_single_page_single_worksheet_and_full_book(self):
        # Since 2026-09-09, "Single page" honors Include Answer Key exactly
        # like "Single Worksheet" does (a real customer, project #362,
        # selected Answer Key: Yes on Single page and silently got none --
        # see tests/test_crossword_scope_answerkey_zip_repair.py). Both
        # single formats are 1 page without an answer key, 2 pages with
        # one; GOLD_RUSH_FIELDS defaults include_answer_key to "Yes".
        page = _crossword_pdf_payload(dict(GOLD_RUSH_FIELDS, output_format="Single page", include_cover="No"))
        self.assertEqual(_page_count(page["pdf_bytes"]), 2)
        no_ak = _crossword_pdf_payload(dict(GOLD_RUSH_FIELDS, output_format="Single page", include_cover="No", include_answer_key="No"))
        self.assertEqual(_page_count(no_ak["pdf_bytes"]), 1)
        worksheet = _crossword_pdf_payload(dict(GOLD_RUSH_FIELDS, output_format="Single Worksheet", include_cover="No"))
        self.assertEqual(_page_count(worksheet["pdf_bytes"]), 2)
        book = _crossword_pdf_payload(dict(GOLD_RUSH_FIELDS, output_format="Full Book", puzzles="6", include_cover="No"))
        self.assertEqual(_page_count(book["pdf_bytes"]), 12)

    def test_puzzle_count_selector_offers_all_six_curated_sizes_and_each_is_honored(self):
        self.assertEqual(CROSSWORD_BOOK_PUZZLE_COUNTS, (6, 8, 10, 12, 15, 20))
        for n in CROSSWORD_BOOK_PUZZLE_COUNTS:
            with self.subTest(count=n):
                result = _crossword_pdf_payload(
                    dict(GOLD_RUSH_FIELDS, output_format="Full Book", puzzles=str(n), include_cover="No")
                )
                self.assertEqual(_page_count(result["pdf_bytes"]), n * 2)

    def test_full_book_is_never_silently_forced_back_to_12(self):
        result = _crossword_pdf_payload(dict(GOLD_RUSH_FIELDS, output_format="Full Book", puzzles="8", include_cover="No"))
        self.assertEqual(_page_count(result["pdf_bytes"]), 16)  # would be 24 if silently forced to 12

    def test_include_cover_yes_and_no_are_both_honored_for_full_book(self):
        yes = _crossword_pdf_payload(dict(GOLD_RUSH_FIELDS, output_format="Full Book", puzzles="8", include_cover="Yes"))
        no = _crossword_pdf_payload(dict(GOLD_RUSH_FIELDS, output_format="Full Book", puzzles="8", include_cover="No"))
        self.assertEqual(_page_count(yes["pdf_bytes"]), 17)
        self.assertEqual(_page_count(no["pdf_bytes"]), 16)

    def test_saved_and_reopened_selections_are_not_silently_altered(self):
        data = normalize_crossword_project_data({
            "product_type": "crossword", "is_book": True, "is_pdf": True,
            "title": "California Gold Rush Days",
            "fields": dict(GOLD_RUSH_FIELDS, output_format="Full Book", puzzles="15", include_cover="No"),
        })
        self.assertEqual(data["puzzle_count"], 15)
        self.assertEqual(data["fields"]["include_cover"], "No")
        rebuilt = rebuild_crossword_pdf_from_data(data)
        self.assertEqual(_page_count(rebuilt["pdf_bytes"]), 15 * 2)


if __name__ == "__main__":
    unittest.main()
