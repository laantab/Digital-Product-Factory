"""CROSSWORD UI REGRESSION REPAIR — customer options restored.

Lonnie found the Product Factory's Crossword form had silently lost
customer choices in an unrelated development pass:

  1. The Single Page output option appeared gone from the customer's view
     of the form (in fact it was still in the field list -- see
     RESTORED-1 below -- but "Number of puzzles" being permanently locked
     to a hardcoded 1-or-12 number input made both non-book formats and
     Full Book itself feel like there was no real choice left).
  2. "Number of puzzles" had become a read-only, always-disabled number
     input instead of a real dropdown.
  3. Every Full Book, regardless of what the (disabled) field showed, was
     silently forced to exactly 12 puzzles -- in THREE separate places:
     the frontend submit path (collectFactoryFields), the backend planner
     (services.product._crossword_plan), and saved-project normalization
     (services.product.normalize_crossword_project_data) -- plus the
     packaging validator (services.packaging) always checked against a
     literal 12 regardless of what the project actually asked for.

This file is the customer-path regression suite this repair adds. It is
separate from the crossword vocabulary/topic-fallback issue (that has its
own coverage in tests/test_crossword_controlled_repair.py -- the Gold Rush
topic-routing and forbidden-answer tests, untouched here).

No external/paid API call is made by any test in this file.
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

from services.factory.puzzle_plan import (  # noqa: E402
    CROSSWORD_BOOK_PUZZLE_COUNTS,
    DEFAULT_BOOK_COUNTS,
    parse_puzzle_output_plan,
)
from services.product import _crossword_plan, normalize_crossword_project_data  # noqa: E402


def _crossword_field_block() -> str:
    src = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    start = src.index('id: "crossword"')
    # The next top-level product-type entry starts the next `{\n    id: "`.
    end = src.index('\n  {\n    id: "', start)
    return src[start:end]


class RESTORED1_OutputFormatDropdownTests(unittest.TestCase):
    """1-2: the form exposes Single Page and Full Book."""

    def test_form_exposes_single_page(self):
        block = _crossword_field_block()
        self.assertIn('"Single page"', block)

    def test_form_exposes_full_book(self):
        block = _crossword_field_block()
        self.assertIn('"Full Book"', block)

    def test_output_format_is_a_real_dropdown_not_a_fixed_field(self):
        block = _crossword_field_block()
        of_start = block.index('name: "output_format"')
        of_line = block[of_start:block.index("\n", of_start)]
        self.assertIn('type: "select"', of_line)


class RESTORED2_PuzzleCountDropdownTests(unittest.TestCase):
    """3: Number of puzzles is a dropdown, not a free/fixed field, and its
    options match the backend's allowed set exactly (no drift between what
    the customer is shown and what the backend will actually honor)."""

    def test_puzzles_field_is_a_select_not_a_number_input(self):
        block = _crossword_field_block()
        p_start = block.index('name: "puzzles"')
        p_block = block[p_start:block.index("},", p_start)]
        self.assertIn('type: "select"', p_block)
        self.assertNotIn('type: "number"', p_block)

    def test_puzzles_dropdown_options_match_the_backend_allowed_set(self):
        block = _crossword_field_block()
        p_start = block.index('name: "puzzles"')
        p_block = block[p_start:block.index("},", p_start)]
        for n in CROSSWORD_BOOK_PUZZLE_COUNTS:
            self.assertIn(f'"{n}"', p_block, f"{n} missing from the puzzles dropdown options")

    def test_puzzles_field_is_hidden_and_shown_by_output_format(self):
        src = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        fn_start = src.index("function _crosswordSetupForm")
        fn_body = src[fn_start:src.index("\n}", fn_start)]
        self.assertIn("puzzlesWrap", fn_body)
        self.assertIn('classList.toggle("hidden"', fn_body)


class RESTORED3_NoHiddenForced12Tests(unittest.TestCase):
    """4-6: Single Page is exactly 1 puzzle; Full Book honors a selected
    count; nothing silently forces every Full Book to exactly 12."""

    def test_single_page_resolves_to_exactly_one_puzzle(self):
        plan = _crossword_plan({
            "book_title": "Ocean Animals",
            "theme": "Ocean Animals",
            "output_format": "Single page",
            "creation_mode": "Topic (AI generates words)",
            "difficulty": "Easy",
        })
        self.assertEqual(plan["worksheets"], 1)
        self.assertEqual(plan["output_type"], "single_page")
        self.assertFalse(plan["is_book"])

    def test_single_worksheet_resolves_to_exactly_one_puzzle(self):
        plan = _crossword_plan({
            "book_title": "Ocean Animals",
            "theme": "Ocean Animals",
            "output_format": "Single Worksheet",
            "creation_mode": "Topic (AI generates words)",
            "difficulty": "Easy",
        })
        self.assertEqual(plan["worksheets"], 1)
        self.assertEqual(plan["output_type"], "single_worksheet")

    def test_full_book_honors_every_allowed_puzzle_count(self):
        for n in CROSSWORD_BOOK_PUZZLE_COUNTS:
            with self.subTest(count=n):
                plan = _crossword_plan({
                    "book_title": "Ocean Animals",
                    "theme": "Ocean Animals",
                    "output_format": "Full Book",
                    "puzzles": str(n),
                    "creation_mode": "Topic (AI generates words)",
                    "difficulty": "Easy",
                })
                self.assertEqual(plan["worksheets"], n)
                self.assertEqual(plan["output_type"], "book")
                self.assertTrue(plan["is_book"])

    def test_no_hidden_forced_12_for_a_different_valid_selection(self):
        """The exact regression: selecting 8 must produce an 8-puzzle plan,
        not a silently-substituted 12."""
        plan = _crossword_plan({
            "book_title": "Ocean Animals",
            "theme": "Ocean Animals",
            "output_format": "Full Book",
            "puzzles": "8",
            "creation_mode": "Topic (AI generates words)",
            "difficulty": "Easy",
        })
        self.assertEqual(plan["worksheets"], 8)
        self.assertNotEqual(plan["worksheets"], 12)

    def test_missing_or_out_of_range_value_still_falls_back_to_the_default(self):
        """Not a regression: the fallback that protects against genuinely
        stale/forged data is still in place, it just no longer overrides a
        deliberate, valid choice."""
        blank = _crossword_plan({
            "book_title": "Ocean Animals", "theme": "Ocean Animals",
            "output_format": "Full Book", "creation_mode": "Topic (AI generates words)",
        })
        self.assertEqual(blank["worksheets"], DEFAULT_BOOK_COUNTS["crossword"])

        out_of_range = _crossword_plan({
            "book_title": "Ocean Animals", "theme": "Ocean Animals",
            "output_format": "Full Book", "puzzles": "999",
            "creation_mode": "Topic (AI generates words)",
        })
        self.assertEqual(out_of_range["worksheets"], DEFAULT_BOOK_COUNTS["crossword"])

    def test_saved_project_reopen_preserves_a_valid_puzzle_count(self):
        data = normalize_crossword_project_data({
            "product_type": "crossword",
            "title": "Ocean Animals",
            "is_book": True,
            "fields": {
                "book_title": "Ocean Animals", "theme": "Ocean Animals",
                "output_format": "Full Book", "puzzles": "15",
                "creation_mode": "Topic (AI generates words)",
                "difficulty": "Easy", "include_answer_key": "Yes",
            },
        })
        self.assertEqual(data["puzzle_count"], 15)
        self.assertEqual(str(data["fields"]["puzzles"]), "15")

    def test_submit_path_does_not_force_puzzles_to_12(self):
        """UI regression assertion: this exact string reappearing in
        collectFactoryFields is what silently defeated every other option
        in the dropdown. It must not come back."""
        src = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        collect_idx = src.index("function collectFactoryFields")
        window = src[collect_idx:collect_idx + 1200]
        self.assertNotIn('fields.puzzles = "12"', window)


class RESTORED4_AnswerKeyBothModesTests(unittest.TestCase):
    """7: answer-key Yes/No works in both Single Page and Full Book."""

    def test_single_page_answer_key_yes(self):
        plan = _crossword_plan({
            "book_title": "T", "theme": "T", "output_format": "Single page",
            "include_answer_key": "Yes",
        })
        self.assertTrue(plan["include_answer_key"])

    def test_single_page_answer_key_no(self):
        plan = _crossword_plan({
            "book_title": "T", "theme": "T", "output_format": "Single page",
            "include_answer_key": "No",
        })
        self.assertFalse(plan["include_answer_key"])

    def test_full_book_answer_key_yes(self):
        plan = _crossword_plan({
            "book_title": "T", "theme": "T", "output_format": "Full Book",
            "puzzles": "8", "include_answer_key": "Yes",
        })
        self.assertTrue(plan["include_answer_key"])

    def test_full_book_answer_key_no(self):
        plan = _crossword_plan({
            "book_title": "T", "theme": "T", "output_format": "Full Book",
            "puzzles": "8", "include_answer_key": "No",
        })
        self.assertFalse(plan["include_answer_key"])


class RESTORED5_CoverBehaviorTests(unittest.TestCase):
    """8: cover behavior.

    CROSSWORD GENERATOR PROTECTED BASELINE REPAIR fixed the actual defect
    this class used to document as "current, unfixed, out of scope": the
    customer's own "Include cover page" Yes/No was silently ignored for
    Full Book (services.product._crossword_pdf_payload always built a
    cover whenever is_book, never reading the field). That is now fixed
    -- see tests/test_crossword_cover_selection_repair.py for the full
    end-to-end (actual generated PDF page count) proof.

    What is intentionally still true, and still out of scope for a
    Crossword-only repair: `_crossword_plan()`'s own returned
    `include_cover` key -- an internal/diagnostic value derived from
    services.factory.puzzle_plan.parse_puzzle_output_plan, shared by every
    worksheet-type product -- still reflects is_book alone. Nothing outside
    _crossword_pdf_payload reads that key for crossword (verified: it is
    only assigned into the plan dict, never consumed elsewhere), so this is
    silent dead weight, not a behavioral bug -- documented here rather than
    silently changed, since the shared function itself is out of scope.
    """

    def test_plan_dict_include_cover_key_is_still_is_book_only(self):
        for choice in ("Yes", "No"):
            with self.subTest(include_cover=choice):
                plan = _crossword_plan({
                    "book_title": "T", "theme": "T", "output_format": "Full Book",
                    "puzzles": "8", "include_cover": choice,
                })
                self.assertTrue(plan["include_cover"])


class RESTORED6_WordSourceTests(unittest.TestCase):
    """9-10: custom word list and topic-generated words both still work."""

    def test_custom_word_list_mode_is_detected(self):
        plan = _crossword_plan({
            "book_title": "T", "theme": "T", "output_format": "Single page",
            "creation_mode": "Custom word list",
        })
        self.assertTrue(plan["use_custom"])

    def test_topic_mode_is_detected(self):
        plan = _crossword_plan({
            "book_title": "T", "theme": "T", "output_format": "Single page",
            "creation_mode": "Topic (AI generates words)",
        })
        self.assertFalse(plan["use_custom"])


class RESTORED7_EndToEndGenerationTests(unittest.TestCase):
    """4/5 end-to-end, not just plan dicts: a selected non-12 count must
    reach the actual PDF generator and produce that many puzzle pages."""

    def test_full_book_with_a_selected_count_produces_that_many_puzzles(self):
        from services.crossword.book import build_crossword_puzzles
        from services.crossword.direct_pdf_renderer import build_crossword_book_pdf_bytes

        # "California Gold Rush Days" -- deliberately NOT one of the shared
        # Universal Topic Vocabulary Engine's curated categories (see
        # services/factory/topic_vocabulary.py), so this test keeps
        # exercising the older, larger generic/AI-less fallback pool and
        # testing what it's actually about (an exact non-12 puzzle count
        # being honored), rather than a small curated pool's own honest
        # adaptive-sizing behavior. "Ocean Animals" used to serve that
        # purpose here too until it became a real, curated, deliberately
        # small (30-word) category as part of Spelling Worksheet's
        # 2026-09-09 release -- a 30-word pool correctly adaptive-sizes an
        # 8-puzzle request down to 3, which is right for that pool but not
        # what this specific test is checking.
        n = 8
        puzzles, _warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=n,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        self.assertEqual(len(puzzles), n, f"errors={errors}")
        pdf_bytes, layout = build_crossword_book_pdf_bytes(
            puzzles,
            product_title="California Gold Rush Days",
            subtitle=f"{n} Crossword Puzzles - Easy Level",
            include_answer_key=True,
            cover_design={"title": "California Gold Rush Days", "subtitle": f"{n} Crossword Puzzles - Easy Level", "author": ""},
        )
        self.assertEqual(layout.page_count, 1 + n * 2)
        self.assertEqual(layout.puzzle_page_count, n)
        self.assertEqual(layout.answer_key_page_count, n)
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


class RESTORED8_NoExternalCallTests(unittest.TestCase):
    """11: choosing any Output Format / puzzle count never triggers a paid
    or external API call on its own."""

    def test_planning_every_output_format_makes_no_network_call(self):
        from unittest.mock import patch

        with patch("services.ebook_pexels._http_get", side_effect=AssertionError("no network calls")):
            for fmt in ("Single page", "Single Worksheet", "Full Book"):
                with self.subTest(output_format=fmt):
                    _crossword_plan({
                        "book_title": "T", "theme": "T", "output_format": fmt,
                        "puzzles": "8", "creation_mode": "Topic (AI generates words)",
                    })

    def test_end_to_end_generation_makes_no_ai_call(self):
        from unittest.mock import patch

        from services.crossword.book import build_crossword_puzzles

        with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json:
            puzzles, _warnings, errors = build_crossword_puzzles(
                mode="topic",
                product_title="Ocean Animals",
                theme="Ocean Animals",
                difficulty="easy",
                grid_size=15,
                number_of_puzzles=6,
                words_per_puzzle=8,
                output_type="book",
                use_ai_words=False,
            )
            self.assertFalse(chat.called)
            self.assertFalse(chat_json.called)
        self.assertEqual(len(puzzles), 6, f"errors={errors}")


if __name__ == "__main__":
    unittest.main()
