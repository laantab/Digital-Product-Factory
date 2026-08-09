# tests/test_product_qa_agent.py
"""Unit tests for services.factory.product_qa_agent."""

import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "flask_app"))

from services.factory.product_qa_agent import (
    ProductQAResult,
    QA_PRODUCT_TYPES,
    safe_fix_plan,
    validate_generated_product,
    validate_product_plan,
)


class TestProductQAResultAsDict(unittest.TestCase):
    """Sanity-check ProductQAResult and as_dict()."""

    def test_clean_result_fields(self):
        r = ProductQAResult()
        d = r.as_dict()
        self.assertIsInstance(d, dict)
        self.assertIn("errors", d)
        self.assertIn("warnings", d)
        self.assertIn("fixes_applied", d)
        self.assertIn("blocked_export", d)
        self.assertFalse(d["blocked_export"])

    def test_result_with_errors(self):
        # blocked_export is derived by validate_product_plan, not __init__
        r = ProductQAResult(errors=["boom", "crash"])
        self.assertEqual(len(r.errors), 2)
        # manually set blocked_export to match what validate_product_plan does
        r.blocked_export = not r.passed
        self.assertTrue(r.blocked_export)
        d = r.as_dict()
        self.assertEqual(d["errors"], ["boom", "crash"])

    def test_result_with_fixes_applied(self):
        r = ProductQAResult(fixes_applied=["cover removed", "answer key disabled"])
        self.assertEqual(len(r.fixes_applied), 2)
        d = r.as_dict()
        self.assertEqual(len(d["fixes_applied"]), 2)

    def test_result_with_warnings(self):
        r = ProductQAResult(warnings=["low contrast detected"])
        d = r.as_dict()
        self.assertEqual(d["warnings"], ["low contrast detected"])

    def test_result_cover_allowed_and_answer_key_fields(self):
        r = ProductQAResult(
            cover_allowed=True,
            answer_key_requested=True,
            answer_key_included=False,
        )
        d = r.as_dict()
        self.assertTrue(d["cover_allowed"])
        self.assertTrue(d["answer_key_requested"])
        self.assertFalse(d["answer_key_included"])

    def test_result_passed_flag(self):
        r = ProductQAResult(passed=True, blocked_export=False)
        self.assertTrue(r.passed)
        d = r.as_dict()
        self.assertTrue(d["passed"])


class TestQaProductTypes(unittest.TestCase):
    """Verify all worksheet product types are covered."""

    def test_all_worksheet_types_present(self):
        for pt in ["word_search", "crossword", "math_worksheet", "spelling_worksheet", "coloring_book"]:
            self.assertIn(pt, QA_PRODUCT_TYPES)


class TestOutputFormatVsCover(unittest.TestCase):
    """Rule 1: single worksheet must not have a cover."""

    def test_single_worksheet_with_cover_blocked(self):
        fields = {"output_format": "single_worksheet"}
        plan = {"output_type": "single_worksheet", "include_cover": True}
        r = validate_product_plan("word_search", fields, plan)
        self.assertTrue(r.blocked_export)
        self.assertTrue(any("cover" in e.lower() for e in r.errors))

    def test_single_worksheet_no_cover_passes(self):
        fields = {"output_format": "single_worksheet"}
        plan = {"output_type": "single_worksheet", "include_cover": False}
        r = validate_product_plan("word_search", fields, plan)
        self.assertFalse(r.blocked_export)

    def test_book_with_cover_allowed(self):
        fields = {"output_format": "book"}
        plan = {"output_type": "book", "include_cover": True}
        r = validate_product_plan("word_search", fields, plan)
        self.assertFalse(r.blocked_export)

    def test_single_page_with_cover_blocked(self):
        fields = {}
        plan = {"output_type": "single_page", "include_cover": True}
        r = validate_product_plan("word_search", fields, plan)
        self.assertTrue(r.blocked_export)

    def test_single_page_no_cover_passes(self):
        fields = {}
        plan = {"output_type": "single_page", "include_cover": False}
        r = validate_product_plan("word_search", fields, plan)
        self.assertFalse(r.blocked_export)


class TestPlanFieldConflicts(unittest.TestCase):
    """Rule 3: safe_fix_plan auto-fixes cover in single worksheet."""

    def test_cover_removed_from_single_worksheet(self):
        fields = {"output_format": "single_worksheet"}
        plan = {"output_type": "single_worksheet", "include_cover": True}
        fixed_plan, fixes = safe_fix_plan("word_search", fields, plan)
        self.assertTrue(len(fixes) > 0)
        self.assertFalse(fixed_plan.get("include_cover"))

    def test_book_no_fix_needed(self):
        fields = {"output_format": "book"}
        plan = {"output_type": "book", "include_cover": True}
        fixed_plan, fixes = safe_fix_plan("word_search", fields, plan)
        self.assertFalse(fixes)

    def test_single_page_answer_key_disabled(self):
        fields = {}
        plan = {"output_type": "single_page", "include_answer_key": True}
        fixed_plan, fixes = safe_fix_plan("word_search", fields, plan)
        self.assertTrue(any("answer key" in f.lower() for f in fixes))
        self.assertFalse(fixed_plan.get("include_answer_key"))

    def test_safe_fix_returns_plan_dict_not_fields(self):
        """safe_fix_plan returns (fixed_plan, fixes) — not (fixed_fields, fixes)."""
        fields = {"output_format": "single_worksheet"}
        plan = {"output_type": "single_worksheet", "include_cover": True}
        fixed_plan, fixes = safe_fix_plan("word_search", fields, plan)
        self.assertIsInstance(fixed_plan, dict)
        self.assertIn("include_cover", fixed_plan)
        self.assertNotEqual(fixed_plan.get("include_cover"), True)

    def test_conflicting_generator_field_cleared(self):
        """Legacy generator field conflicts with explicit output_format → cleared."""
        fields = {"output_format": "Single Worksheet", "generator": "Book Generator"}
        plan = {"output_type": "single_worksheet", "include_cover": False}
        fixed_fields, fixes = safe_fix_plan("word_search", fields, plan)
        # generator should be removed
        self.assertNotIn("generator", fixed_fields)
        self.assertTrue(len(fixes) > 0)


class TestPreGenValidationNonWorksheetTypes(unittest.TestCase):
    """Unknown/unsupported product types return a clean pass-through."""

    def test_unknown_type_passes(self):
        r = validate_product_plan("ebook", {}, None)
        self.assertTrue(r.passed)
        self.assertFalse(r.blocked_export)

    def test_cover_design_passes(self):
        r = validate_product_plan("cover_design", {}, None)
        self.assertTrue(r.passed)


class TestPostGenQaCleanLayout(unittest.TestCase):
    """Post-gen QA with valid layout info passes cleanly."""

    def test_word_search_book_clean(self):
        fields = {"output_format": "book"}
        plan = {"output_type": "book", "include_answer_key": True}
        layout_info = {"cover_page_count": 1, "answer_key_validated": True, "pages": 5}
        pdf_bytes = b"PDF"
        r = validate_generated_product(
            "word_search", fields, plan, pdf_bytes, layout_info
        )
        self.assertFalse(r.blocked_export)
        self.assertTrue(r.answer_key_included)

    def test_crossword_book_clean(self):
        fields = {"output_format": "book"}
        plan = {"output_type": "book", "include_answer_key": True}
        layout_info = {"cover_page_count": 1, "answer_key_validated": True}
        pdf_bytes = b"PDF"
        r = validate_generated_product(
            "crossword", fields, plan, pdf_bytes, layout_info
        )
        self.assertFalse(r.blocked_export)

    def test_math_worksheet_book_clean(self):
        fields = {"output_format": "book"}
        plan = {"output_type": "book", "include_answer_key": True}
        layout_info = {"pages": 10, "answer_fill_count": 20}
        r = validate_generated_product(
            "math_worksheet", fields, plan, b"PDF", layout_info
        )
        self.assertFalse(r.blocked_export)

    def test_spelling_worksheet_book_clean(self):
        fields = {"output_format": "book"}
        plan = {"output_type": "book", "include_answer_key": True}
        layout_info = {"pages": 5, "answer_oval_count": 10}
        r = validate_generated_product(
            "spelling_worksheet", fields, plan, b"PDF", layout_info
        )
        self.assertFalse(r.blocked_export)

    def test_coloring_book_no_answer_key(self):
        fields = {"output_format": "book"}
        plan = {"output_type": "book", "include_answer_key": False}
        layout_info = {"cover_page_count": 1, "pages": 12}
        r = validate_generated_product(
            "coloring_book", fields, plan, b"PDF", layout_info
        )
        self.assertFalse(r.blocked_export)


class TestPostGenQaCoverInSingleWorksheet(unittest.TestCase):
    """Post-gen Rule 1b: cover found in single worksheet → blocked."""

    def test_cover_detected_in_single_worksheet_blocks(self):
        fields = {"output_format": "single_worksheet"}
        plan = {"output_type": "single_worksheet"}
        # layout_info says there IS a cover page — this is the error
        layout_info = {"cover_page_count": 1, "pages": 2}
        pdf_bytes = b"PDF"
        r = validate_generated_product(
            "word_search", fields, plan, pdf_bytes, layout_info
        )
        self.assertTrue(r.blocked_export)
        self.assertTrue(any("cover" in e.lower() for e in r.errors))

    def test_no_layout_info_no_cover_detection(self):
        """Without layout_info, cover can't be detected — no false positive."""
        fields = {"output_format": "single_worksheet"}
        plan = {"output_type": "single_worksheet"}
        # No layout_info at all
        r = validate_generated_product(
            "word_search", fields, plan, b"PDF", None
        )
        self.assertFalse(r.blocked_export)


class TestPostGenQaAnswerKeyMismatch(unittest.TestCase):
    """Post-gen Rule 2: answer key inclusion must match request."""

    def test_answer_key_requested_but_missing(self):
        fields = {"output_format": "book"}
        plan = {"output_type": "book", "include_answer_key": True}
        # layout_info shows NO answer key present
        layout_info = {"pages": 5}
        r = validate_generated_product(
            "word_search", fields, plan, b"PDF", layout_info
        )
        self.assertTrue(r.blocked_export)
        self.assertTrue(any("answer key" in e.lower() and "not included" in e.lower() for e in r.errors))

    def test_answer_key_not_requested_but_present(self):
        fields = {"output_format": "book"}
        plan = {"output_type": "book", "include_answer_key": False}
        # layout_info shows answer key IS present (wrong)
        layout_info = {"pages": 6, "answer_key_validated": True}
        r = validate_generated_product(
            "word_search", fields, plan, b"PDF", layout_info
        )
        self.assertTrue(r.blocked_export)
        self.assertTrue(any("not requested" in e.lower() for e in r.errors))

    def test_single_page_answer_key_present_blocks(self):
        fields = {}
        plan = {"output_type": "single_page", "include_answer_key": False}
        # answer key somehow in the PDF
        layout_info = {"pages": 2, "answer_oval_count": 5}
        r = validate_generated_product(
            "word_search", fields, plan, b"PDF", layout_info
        )
        self.assertTrue(r.blocked_export)

    def test_answer_key_matches_request_passes(self):
        fields = {"output_format": "book"}
        plan = {"output_type": "book", "include_answer_key": True}
        layout_info = {"pages": 6, "answer_key_validated": True}
        r = validate_generated_product(
            "word_search", fields, plan, b"PDF", layout_info
        )
        self.assertFalse(r.blocked_export)


class TestResultSoFarPassThrough(unittest.TestCase):
    """Pre-gen errors survive into post-gen via result_so_far."""

    def test_pregen_errors_preserved(self):
        pre = ProductQAResult(
            blocked_export=True,
            errors=["pre-generation error"],
        )
        fields = {"output_format": "book"}
        plan = {"output_type": "book"}
        layout_info = {"pages": 3}
        r = validate_generated_product(
            "word_search", fields, plan, b"PDF", layout_info, result_so_far=pre
        )
        self.assertTrue(r.blocked_export)
        self.assertTrue(any("pre-generation" in e for e in r.errors))


class TestAllProductTypesHandled(unittest.TestCase):
    """All worksheet types pass through the full QA pipeline without crashing."""

    def _round_trip(self, product_type: str, output_type: str = "book"):
        fields = {"output_format": output_type}
        plan = {"output_type": output_type, "include_answer_key": True}
        fixed_plan, fixes = safe_fix_plan(product_type, fields, plan)
        r1 = validate_product_plan(product_type, fields, plan)
        layout_info = {"pages": 3, "answer_key_validated": True}
        r2 = validate_generated_product(
            product_type, fields, plan, b"PDF", layout_info
        )
        return r1, r2

    def test_word_search(self):
        r1, r2 = self._round_trip("word_search")
        self.assertFalse(r2.blocked_export)

    def test_crossword(self):
        r1, r2 = self._round_trip("crossword")
        self.assertFalse(r2.blocked_export)

    def test_coloring_book(self):
        r1, r2 = self._round_trip("coloring_book")
        self.assertFalse(r2.blocked_export)

    def test_math_worksheet(self):
        r1, r2 = self._round_trip("math_worksheet")
        self.assertFalse(r2.blocked_export)

    def test_spelling_worksheet(self):
        r1, r2 = self._round_trip("spelling_worksheet")
        self.assertFalse(r2.blocked_export)

    def test_word_search_single_worksheet_blocked_due_to_cover(self):
        """Single WS with cover triggers block pre-gen."""
        fields = {"output_format": "single_worksheet"}
        plan = {"output_type": "single_worksheet", "include_cover": True}
        r = validate_product_plan("word_search", fields, plan)
        self.assertTrue(r.blocked_export)


if __name__ == "__main__":
    unittest.main(verbosity=2)
