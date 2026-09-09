"""MATH WORKSHEET COVER SELECTION REPAIR.

BASELINE (established before any code change, see the chat transcript for
the exact commands run)
------------------------------------------------------------------------
Empirically, for every problem count tried (5, 10, 20, 30), Include Cover
Yes and No produced identical page counts. Traced end to end:

  UI: no "Include cover page" field existed in the customer-facing Math
      Worksheet form at all (static/js/app.js "math_worksheet" fields list)
      -- unlike Crossword/Word Search/Coloring Book, which all have one.
  services.quality.cover_eligibility_agent.determine_cover_eligibility()
      correctly returned cover_allowed=True for eligible configurations.
  services.product._math_worksheet_pdf_payload() then passed
      include_cover=cover_allowed straight through, NEVER reading the
      customer's own "include_cover" field at all.
  services.math_worksheet.pdf_builder.build_math_worksheet_pdf() never
      passed include_cover to the renderer at all -- the parameter existed
      on the MathWorksheetPdfRequest dataclass but was dead.
  services.math_worksheet.renderer.build_math_worksheet_pdf_bytes() only
      ever drew a cover `if cover_image_path and os.path.isfile(...)` --
      and nothing in the whole pipeline ever produced a real image path
      (no _build_math_worksheet_cover-equivalent function existed, unlike
      crossword/word_search's local AI-free cover builders), so a cover
      was structurally unreachable regardless of any flag.

ROOT CAUSE: not merely "ignored" -- there was no working cover mechanism
at all for Math Worksheet.

REPAIR (smallest Math-Worksheet-specific fix, no shared engine rewrite)
------------------------------------------------------------------------
  1. static/js/app.js: added the missing "Include cover page" field,
     mirroring the identical pattern already used for every other
     worksheet-type product.
  2. services/math_worksheet/renderer.py: build_math_worksheet_pdf_bytes
     gained an `include_cover` parameter. When true and no real cover
     image is available (the normal, zero-cost case), it draws a plain
     text-only cover page (title + grade/topic), reusing the exact
     _paint_white/_draw_text primitives already present as dead code in
     the image-failure fallback. No AI image call, no network call.
  3. services/math_worksheet/pdf_builder.py: threads request.include_cover
     through to the renderer (previously dropped on the floor).
  4. services/product.py:
     - _math_worksheet_pdf_payload now resolves
       `eligibility.cover_allowed and customer_choice`, where
       customer_choice reads the "include_cover" field (explicit Yes/No,
       default Yes when missing/legacy) -- an explicit customer No can
       never be overridden by eligibility, and eligibility remains a hard
       ceiling a customer cannot bypass.
  5. services/quality/cover_eligibility_agent.py: the math_worksheet /
     spelling_worksheet branch of determine_cover_eligibility() did not
     check output mode at all (only page count) -- meaning eligibility
     alone did not stop Single Worksheet from claiming cover_allowed=True;
     a downstream QA post-check (already existing, unmodified here) was
     the only thing blocking it, by hard-rejecting the whole export rather
     than simply not offering a cover. Added the same is_book / single-
     format gate Crossword and Word Search's own branches already use, so
     Single Worksheet is correctly ineligible up front (a valid business
     rule preserved, not manufactured around) instead of raising a QA
     error. This branch is shared with spelling_worksheet (out of scope,
     hidden/inactive product, not customer-visible) -- see
     _SINGLE_PAGE_ANSWER_KEY_SUPPORTED-style scoping note in
     product_qa_agent.py for the general policy; this branch's change
     only makes spelling_worksheet's own (already inert) eligibility more
     correct, never less.

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

from services.product import _math_worksheet_pdf_payload  # noqa: E402

BASE_FIELDS = {
    "worksheet_title": "Addition Practice",
    "grade": "Grade 3",
    "math_topic": "Addition",
    "difficulty": "Medium",
    "include_answer_key": "Yes",
}


def _pages(pdf_bytes_b64: str) -> int:
    return len(PdfReader(io.BytesIO(base64.b64decode(pdf_bytes_b64))).pages)


class UIExposesCoverFieldTests(unittest.TestCase):
    def test_math_worksheet_form_now_has_an_include_cover_field(self):
        src = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        start = src.index('id: "math_worksheet"')
        end = src.index("\n  {\n    id: \"", start)
        block = src[start:end]
        self.assertIn('name: "include_cover"', block)
        self.assertIn('"Include cover page"', block)


class EligibleWorksheetCoverTests(unittest.TestCase):
    """Full Workbook (eligible: is_book, 20 problems well over the 5-page
    minimum): Cover Yes must include the cover, Cover No must exclude it."""

    def test_cover_yes_includes_the_cover(self):
        result = _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="Yes"))
        self.assertEqual(_pages(result["pdf_bytes"]), 3)  # cover + problems + answer key

    def test_cover_no_excludes_the_cover(self):
        result = _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="No"))
        self.assertEqual(_pages(result["pdf_bytes"]), 2)  # problems + answer key

    def test_yes_and_no_differ_by_exactly_the_cover_page(self):
        yes = _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="Yes"))
        no = _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="No"))
        self.assertEqual(_pages(yes["pdf_bytes"]) - _pages(no["pdf_bytes"]), 1)

    def test_explicit_no_is_not_silently_replaced(self):
        """The exact original defect: No used to produce the same PDF as
        Yes. Assert the two are provably different documents now."""
        yes = _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="Yes"))
        no = _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="No"))
        self.assertNotEqual(
            base64.b64decode(yes["pdf_bytes"]),
            base64.b64decode(no["pdf_bytes"]),
        )


class IneligibleSingleWorksheetTests(unittest.TestCase):
    """Single Worksheet cannot have a cover -- a valid, preserved business
    rule, not something a customer's Yes can manufacture around."""

    def test_cover_yes_is_still_blocked_for_single_worksheet(self):
        result = _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Single Worksheet", problems="20", include_cover="Yes"))
        self.assertEqual(_pages(result["pdf_bytes"]), 2)  # problems + answer key, no cover

    def test_cover_no_is_also_blocked_for_single_worksheet(self):
        result = _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Single Worksheet", problems="20", include_cover="No"))
        self.assertEqual(_pages(result["pdf_bytes"]), 2)


class SaveReopenGenerateTests(unittest.TestCase):
    """Math Worksheet has no dedicated normalize/rebuild function (unlike
    Crossword) -- a saved project's fields dict is restored and
    re-submitted to the same _math_worksheet_pdf_payload verbatim, so this
    proves that path preserves the customer's selection directly."""

    def test_reopen_and_regenerate_preserves_cover_no(self):
        saved_fields = dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="No")
        # Simulate reopen: fields dict comes back exactly as saved.
        reopened = dict(saved_fields)
        result = _math_worksheet_pdf_payload(reopened)
        self.assertEqual(_pages(result["pdf_bytes"]), 2)

    def test_reopen_and_regenerate_preserves_cover_yes(self):
        saved_fields = dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="Yes")
        reopened = dict(saved_fields)
        result = _math_worksheet_pdf_payload(reopened)
        self.assertEqual(_pages(result["pdf_bytes"]), 3)


class PackagingAcceptsBothFormsTests(unittest.TestCase):
    """Packaging/export (services.packaging.build_product_export) just
    repackages the stored PDF bytes for math_worksheet -- prove it accepts
    and correctly ships both a cover and a no-cover product."""

    def test_export_accepts_a_worksheet_with_a_cover(self):
        from services.packaging import build_product_export

        payload = _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="Yes"))
        project = {"id": None, "name": "Addition Practice", "data": {
            "product_type": "math_worksheet", "is_pdf": True, "title": "Addition Practice",
            "fields": dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="Yes"),
            "pdf_bytes": payload["pdf_bytes"], "filename": payload["filename"],
            "problems": payload["problems"], "challenge_problems": payload["challenge_problems"],
        }}
        result = build_product_export(project)
        self.assertTrue(result.get("exports", {}).get("pdf_available"))

    def test_export_accepts_a_worksheet_without_a_cover(self):
        from services.packaging import build_product_export

        payload = _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="No"))
        project = {"id": None, "name": "Addition Practice", "data": {
            "product_type": "math_worksheet", "is_pdf": True, "title": "Addition Practice",
            "fields": dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="No"),
            "pdf_bytes": payload["pdf_bytes"], "filename": payload["filename"],
            "problems": payload["problems"], "challenge_problems": payload["challenge_problems"],
        }}
        result = build_product_export(project)
        self.assertTrue(result.get("exports", {}).get("pdf_available"))


class BackwardCompatibleDefaultTests(unittest.TestCase):
    def test_missing_include_cover_field_defaults_to_yes(self):
        """Legacy saved projects (from before this field existed) must not
        break -- matches the same "missing -> default True for an eligible
        book" convention Crossword/Word Search already use."""
        fields = {k: v for k, v in BASE_FIELDS.items()}
        fields.update(output_format="Full Workbook", problems="20")
        # No "include_cover" key at all.
        result = _math_worksheet_pdf_payload(fields)
        self.assertEqual(_pages(result["pdf_bytes"]), 3)

    def test_unrecognized_include_cover_value_safely_declines_the_cover(self):
        """Only a genuinely blank/missing field falls back to the Yes
        default (see the test above) -- this matches _yes_default's
        existing, pre-established, shared semantics (services/product.py),
        unchanged by this repair: a non-blank but unrecognized value (not
        "yes"/"true"/"1"/"on") resolves to False, not to the default. Safe
        in the same spirit the task asks for -- garbage input never grants
        an unrequested cover -- just resolved to False rather than True."""
        result = _math_worksheet_pdf_payload(
            dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="maybe")
        )
        self.assertEqual(_pages(result["pdf_bytes"]), 2)


class NoExternalCallTests(unittest.TestCase):
    def test_cover_generation_makes_no_ai_or_network_call(self):
        from unittest.mock import patch

        with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json:
            for cov in ("Yes", "No"):
                _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover=cov))
            self.assertFalse(chat.called)
            self.assertFalse(chat_json.called)


class ProtectedBaselineContractTests(unittest.TestCase):
    """PERMANENT REGRESSION CONTRACT for Math Worksheet's Include Cover
    behavior. Checks actual resolved generation output (real PDFs, real
    page counts), never only an HTML/JS source string."""

    def test_include_cover_field_exists_in_the_customer_form(self):
        src = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        start = src.index('id: "math_worksheet"')
        end = src.index("\n  {\n    id: \"", start)
        self.assertIn('name: "include_cover"', src[start:end])

    def test_cover_yes_and_no_are_never_identical_for_an_eligible_book(self):
        yes = _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="Yes"))
        no = _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Full Workbook", problems="20", include_cover="No"))
        self.assertNotEqual(_pages(yes["pdf_bytes"]), _pages(no["pdf_bytes"]))

    def test_single_worksheet_never_gets_a_cover_regardless_of_selection(self):
        for cov in ("Yes", "No"):
            with self.subTest(include_cover=cov):
                result = _math_worksheet_pdf_payload(dict(BASE_FIELDS, output_format="Single Worksheet", problems="20", include_cover=cov))
                self.assertEqual(_pages(result["pdf_bytes"]), 2)


if __name__ == "__main__":
    unittest.main()
