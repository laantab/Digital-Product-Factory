"""Single-format Include Answer Key repair — Crossword and Word Search.

ROOT CAUSE
----------
services.factory.product_qa_agent.safe_fix_plan() carried a "safe auto-fix"
(Fix 2) applied to EVERY product type sharing the function: "A single-page
artifact cannot contain a separate answer-key page" -- it unconditionally
forced Include Answer Key to False whenever the resolved output_type was
single_page or single_worksheet, discarding the customer's own selection.

That premise was false for Crossword and Word Search: both single-format
renderers already correctly build a second, separate answer-key page when
asked --
  services.crossword.direct_pdf_renderer.build_single_crossword_pdf_bytes
  services.word_search.direct_pdf_renderer.build_single_worksheet_pdf_bytes
-- confirmed by direct inspection, and now by the tests below.

DISCOVERED VIA A REAL CUSTOMER PRODUCT
---------------------------------------
A customer generated a Word Search ("American Cars", Single Worksheet,
Include Cover: Yes, Include Answer Key: Yes) and received a 1-page PDF with
neither the cover (correct -- Single Worksheet never gets a cover, a
separate and valid rule) nor the answer key (the bug this file repairs).

UPDATE 2026-09-09 — "Single page" no longer stays exempt
----------------------------------------------------------
At the time this file was first written, Crossword's "Single page" format
(distinct from "Single Worksheet" -- see the dropdown: Single page /
Single Worksheet / Full Book) had its OWN, separate, dedicated guard in
services/crossword/pdf_builder.py (`include_answer_key=... and
output_type != "single_page"`) that always blocked the answer key,
documented then as intentional -- the same "Single Page/Single Sheet =
always exactly N pages, no exceptions" concept Coloring Book's Single
Sheet uses (services/coloring_book/sheet_validator.py:
COLORING_OUTPUT_SINGLE_PAGE).

A real customer product (project #362, "American Automobiles", Single
page, Include Answer Key: Yes) proved that premise wrong in practice: the
customer explicitly selected Include Answer Key: Yes and received a
1-page PDF with no solution page -- a visible control whose value was
silently ignored. That dedicated guard has been removed; "Single page"
now behaves exactly like "Single Worksheet" for answer-key purposes (see
test_single_page_now_honors_answer_key_same_as_single_worksheet below,
and tests/test_crossword_scope_answerkey_zip_repair.py for the fuller
regression coverage from that repair).

Word Search never had an equivalent extra guard distinguishing "Single
page" from "Single Worksheet", so both of its single formats were always
fixed together by this file's original repair.

spelling_worksheet also calls safe_fix_plan() but was not inspected for
this repair and is intentionally excluded from the fix
(_SINGLE_PAGE_ANSWER_KEY_SUPPORTED in product_qa_agent.py) -- its
pre-existing behavior is unchanged.

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

from services.factory.product_qa_agent import _SINGLE_PAGE_ANSWER_KEY_SUPPORTED, safe_fix_plan  # noqa: E402
from services.product import _crossword_pdf_payload, _word_search_pdf_payload  # noqa: E402

GOLD_RUSH = {
    "book_title": "California Gold Rush Days",
    "theme": "California Gold Rush Days",
    "creation_mode": "Topic (AI generates words)",
    "difficulty": "Easy",
}

# Same 60-word list used by tests/test_crossword_cover_selection_repair.py,
# large enough to avoid a pre-existing, unrelated word_search engine
# flakiness under FACTORY_TEST_MODE (topic-mode word resolution returns a
# fixed ~10-word stub there regardless of topic).
WORD_SEARCH_WORDS = "\n".join([
    "apple", "banana", "cherry", "dragon", "energy", "forest", "garden", "harbor", "island", "jungle",
    "kitten", "ladder", "meadow", "napkin", "ocean", "pencil", "quartz", "rabbit", "silver", "temple",
])


def _pages(pdf_bytes_b64: str) -> int:
    return len(PdfReader(io.BytesIO(base64.b64decode(pdf_bytes_b64))).pages)


class SafeFixPlanScopeTests(unittest.TestCase):
    def test_supported_set_is_exactly_the_four_verified_types(self):
        # "spelling_worksheet" added 2026-09-09 during its release-
        # readiness task: its own renderer was directly confirmed capable
        # of building a real, separate answer-key page for single-
        # worksheet output (see services/spelling_worksheet/pdf_builder.py
        # and the module comment on _SINGLE_PAGE_ANSWER_KEY_SUPPORTED).
        self.assertEqual(
            _SINGLE_PAGE_ANSWER_KEY_SUPPORTED,
            {"crossword", "word_search", "math_worksheet", "spelling_worksheet"},
        )

    def test_spelling_worksheet_now_honors_its_own_answer_key_choice(self):
        """Spelling Worksheet's renderer can build a real answer-key page
        for single-worksheet output (verified 2026-09-09), so it was added
        to _SINGLE_PAGE_ANSWER_KEY_SUPPORTED and this auto-fix no longer
        silently overrides the customer's own "Include answer key: Yes"."""
        plan = {"output_type": "single_worksheet", "include_answer_key": True}
        fixed_fields, fixes = safe_fix_plan("spelling_worksheet", {"include_answer_key": "Yes"}, plan)
        self.assertEqual(fixed_fields["include_answer_key"], "Yes")
        self.assertFalse(any("answer key" in f for f in fixes))

    def test_book_output_is_never_touched_by_the_single_page_fix(self):
        plan = {"output_type": "book", "include_answer_key": True}
        fixed_fields, fixes = safe_fix_plan("crossword", {"include_answer_key": "Yes"}, plan)
        self.assertEqual(fixed_fields["include_answer_key"], "Yes")
        self.assertEqual(fixes, [])


class CrosswordSingleWorksheetAnswerKeyTests(unittest.TestCase):
    """Crossword's "Single Worksheet" (distinct from "Single page")."""

    def test_single_worksheet_answer_key_yes_includes_the_answer_key(self):
        result = _crossword_pdf_payload(dict(GOLD_RUSH, output_format="Single Worksheet", include_answer_key="Yes"))
        self.assertEqual(_pages(result["pdf_bytes"]), 2)

    def test_single_worksheet_answer_key_no_excludes_it(self):
        result = _crossword_pdf_payload(dict(GOLD_RUSH, output_format="Single Worksheet", include_answer_key="No"))
        self.assertEqual(_pages(result["pdf_bytes"]), 1)

    def test_single_page_now_honors_answer_key_same_as_single_worksheet(self):
        """UPDATED 2026-09-09: "Single page" used to have its own dedicated
        guard that always stripped the answer key regardless of the
        customer's own selection -- documented at the time as intentional
        ("Single Page = always exactly N pages, no exceptions", mirroring
        Coloring Book's Single Sheet). A real customer product (project
        #362, "American Automobiles", Single page, Include Answer Key:
        Yes) proved that design wrong in practice: the customer explicitly
        asked for an answer key and silently got none -- a visible control
        whose value is ignored. The dedicated guard in
        services/crossword/pdf_builder.py was removed; "Single page" now
        behaves exactly like "Single Worksheet" for answer-key purposes.
        See tests/test_crossword_scope_answerkey_zip_repair.py for the
        full regression coverage."""
        yes = _crossword_pdf_payload(dict(GOLD_RUSH, output_format="Single page", include_answer_key="Yes"))
        no = _crossword_pdf_payload(dict(GOLD_RUSH, output_format="Single page", include_answer_key="No"))
        self.assertEqual(_pages(yes["pdf_bytes"]), 2)
        self.assertEqual(_pages(no["pdf_bytes"]), 1)

    def test_full_book_answer_key_selection_is_unaffected_by_this_repair(self):
        yes = _crossword_pdf_payload(dict(GOLD_RUSH, output_format="Full Book", puzzles="6", include_answer_key="Yes"))
        no = _crossword_pdf_payload(dict(GOLD_RUSH, output_format="Full Book", puzzles="6", include_answer_key="No"))
        self.assertEqual(_pages(yes["pdf_bytes"]) - _pages(no["pdf_bytes"]), 6)


class WordSearchSingleFormatAnswerKeyTests(unittest.TestCase):
    """The exact real-world defect: Word Search Single Worksheet / Single
    page + Include Answer Key: Yes must actually include the answer key."""

    def test_single_worksheet_answer_key_yes_includes_the_answer_key(self):
        result = _word_search_pdf_payload({
            "topic": "American Cars", "output_format": "Single Worksheet", "difficulty": "Medium",
            "include_answer_key": "Yes", "include_cover": "No",
            "creation_mode": "Custom word list", "custom_words": WORD_SEARCH_WORDS,
        })
        self.assertEqual(_pages(result["pdf_bytes"]), 2)

    def test_single_worksheet_answer_key_no_excludes_it(self):
        result = _word_search_pdf_payload({
            "topic": "American Cars", "output_format": "Single Worksheet", "difficulty": "Medium",
            "include_answer_key": "No", "include_cover": "No",
            "creation_mode": "Custom word list", "custom_words": WORD_SEARCH_WORDS,
        })
        self.assertEqual(_pages(result["pdf_bytes"]), 1)

    def test_single_page_answer_key_yes_also_includes_it(self):
        """Word Search, unlike Crossword, does not distinguish "Single
        page" from "Single Worksheet" for answer-key purposes -- it never
        did (no separate guard exists in services/word_search/pdf_builder.py
        the way Crossword's does), so both are fixed together here."""
        result = _word_search_pdf_payload({
            "topic": "American Cars", "output_format": "Single page", "difficulty": "Medium",
            "include_answer_key": "Yes", "include_cover": "No",
            "creation_mode": "Custom word list", "custom_words": WORD_SEARCH_WORDS,
        })
        self.assertEqual(_pages(result["pdf_bytes"]), 2)

    def test_cover_still_never_appears_for_single_worksheet_regardless(self):
        """Distinct rule, unaffected by this repair: cover stays blocked
        for single-format Word Search no matter what Include Answer Key
        or Include Cover say."""
        for cov in ("Yes", "No"):
            with self.subTest(include_cover=cov):
                result = _word_search_pdf_payload({
                    "topic": "American Cars", "output_format": "Single Worksheet", "difficulty": "Medium",
                    "include_answer_key": "No", "include_cover": cov,
                    "creation_mode": "Custom word list", "custom_words": WORD_SEARCH_WORDS,
                })
                self.assertEqual(_pages(result["pdf_bytes"]), 1)

    def test_reproduces_the_reported_american_cars_case_now_fixed(self):
        """The exact customer report: Single Worksheet, Cover Yes, Answer
        Key Yes. Cover is correctly still absent (by design); the answer
        key must now be present."""
        result = _word_search_pdf_payload({
            "topic": "American Cars", "output_format": "Single Worksheet", "difficulty": "Medium",
            "include_answer_key": "Yes", "include_cover": "Yes",
            "creation_mode": "Custom word list", "custom_words": WORD_SEARCH_WORDS,
        })
        self.assertEqual(_pages(result["pdf_bytes"]), 2)


class NoExternalCallTests(unittest.TestCase):
    def test_single_format_answer_key_generation_makes_no_external_call(self):
        from unittest.mock import patch

        with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json:
            _crossword_pdf_payload(dict(GOLD_RUSH, output_format="Single Worksheet", include_answer_key="Yes"))
            _word_search_pdf_payload({
                "topic": "American Cars", "output_format": "Single Worksheet", "difficulty": "Medium",
                "include_answer_key": "Yes", "include_cover": "No",
                "creation_mode": "Custom word list", "custom_words": WORD_SEARCH_WORDS,
            })
            self.assertFalse(chat.called)
            self.assertFalse(chat_json.called)


if __name__ == "__main__":
    unittest.main()
