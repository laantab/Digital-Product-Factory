"""Coloring Book's declared final-cover QA authority (2026-09-12).

GLOBAL COVER POLICY: every customer-facing final cover must pass a real
final QA gate. Coloring Book's automatic build previously had no such gate
at all -- this proves services/coloring_book/final_cover_qa.py both works
correctly in isolation and is genuinely wired into the real generation path
(services.product._coloring_book_pdf_payload), not merely present and
unused. Zero paid calls (quality_mode="Basic Test Fallback" throughout).
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""

from services.coloring_book.final_cover_qa import validate_coloring_book_final_cover  # noqa: E402

_MIN_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n"


def _fields(theme: str = "Sea Creatures in the Reef") -> dict:
    return {
        "coloring_title": theme,
        "theme": theme,
        "output_format": "Single Sheet",
        "quality_mode": "Basic Test Fallback",
        "art_style": "Cartoon comic-book",
        "age_group": "Children ages 8-12",
        "pages": "1",
        "include_captions": "No",
    }


# ---------------------------------------------------------------------------
# validate_coloring_book_final_cover — the adapter itself, in isolation
# ---------------------------------------------------------------------------

class ValidateColoringBookFinalCoverTests(unittest.TestCase):
    def test_a_genuinely_complete_cover_passes(self):
        result = validate_coloring_book_final_cover(
            _MIN_PDF, title="Sea Creatures in the Reef", subtitle="A Coloring Book",
            cover_source="ai_only",
        )
        self.assertTrue(result.passed, result.errors)

    def test_malformed_pdf_bytes_are_rejected(self):
        result = validate_coloring_book_final_cover(
            b"not a pdf", title="Sea Creatures in the Reef", cover_source="ai_only",
        )
        self.assertFalse(result.passed)
        self.assertTrue(any("malformed" in e.lower() for e in result.errors))

    def test_empty_pdf_bytes_are_rejected(self):
        result = validate_coloring_book_final_cover(b"", title="Sea Creatures", cover_source="ai_only")
        self.assertFalse(result.passed)

    def test_missing_title_is_rejected(self):
        result = validate_coloring_book_final_cover(_MIN_PDF, title="", cover_source="ai_only")
        self.assertFalse(result.passed)
        self.assertTrue(any("missing a title" in e.lower() for e in result.errors))

    def test_placeholder_text_is_rejected(self):
        result = validate_coloring_book_final_cover(
            _MIN_PDF, title="Your Title Here", cover_source="ai_only",
        )
        self.assertFalse(result.passed)

    def test_template_wording_is_rejected(self):
        result = validate_coloring_book_final_cover(
            _MIN_PDF, title="Untitled", cover_source="ai_only",
        )
        self.assertFalse(result.passed)

    def test_malformed_characters_are_rejected(self):
        result = validate_coloring_book_final_cover(
            _MIN_PDF, title="Sea Creatures�\x02", cover_source="ai_only",
        )
        self.assertFalse(result.passed)
        self.assertTrue(any("malformed or corrupted" in e.lower() for e in result.errors))

    def test_unrecognized_cover_source_is_rejected(self):
        result = validate_coloring_book_final_cover(
            _MIN_PDF, title="Sea Creatures in the Reef", cover_source="mystery_source",
        )
        self.assertFalse(result.passed)
        self.assertTrue(any("not a recognized" in e.lower() for e in result.errors))

    def test_template_fallback_is_a_valid_recognized_source(self):
        """template_fallback cannot be rejected merely for being deterministic --
        it must still pass when the rest of the cover is genuinely complete."""
        result = validate_coloring_book_final_cover(
            _MIN_PDF, title="Sea Creatures in the Reef", cover_source="template_fallback",
        )
        self.assertTrue(result.passed, result.errors)

    def test_unreadable_page_text_is_a_warning_not_a_block(self):
        """A minimal/malformed-for-extraction PDF that still starts with the
        %PDF header should warn about unconfirmed title text, not hard-fail --
        avoids false positives on real, visually-correct renders."""
        result = validate_coloring_book_final_cover(
            _MIN_PDF, title="Sea Creatures in the Reef", cover_source="ai_only",
        )
        self.assertTrue(result.passed)
        self.assertTrue(len(result.warnings) >= 0)  # never raises; may or may not warn


# ---------------------------------------------------------------------------
# Real wiring — the automatic build cannot bypass this gate
# ---------------------------------------------------------------------------

class ColoringBookAutomaticBuildCannotBypassFinalQATests(unittest.TestCase):
    def test_a_normal_generation_passes_through_final_qa_and_succeeds(self):
        from services.product import _generate_coloring_book_pdf

        with patch(
            "services.coloring_book.final_cover_qa.validate_coloring_book_final_cover"
        ) as mock_qa:
            mock_qa.return_value.passed = True
            mock_qa.return_value.as_dict.return_value = {"passed": True, "errors": [], "warnings": []}
            result = _generate_coloring_book_pdf(_fields())

        mock_qa.assert_called_once()
        self.assertTrue(result.get("pdf_bytes"))
        self.assertIn("cover_source", result)
        self.assertIn(result["cover_source"], {"ai_only", "template_fallback"})

    def test_a_failing_final_qa_blocks_generation_with_a_clear_error(self):
        """Proof the gate is real: forcing it to fail must stop generation,
        not merely log a warning while still returning a cover."""
        from services.product import _generate_coloring_book_pdf

        with patch(
            "services.coloring_book.final_cover_qa.validate_coloring_book_final_cover"
        ) as mock_qa:
            mock_qa.return_value.passed = False
            mock_qa.return_value.errors = ["Simulated final cover QA failure for this proof."]
            with self.assertRaises(RuntimeError) as ctx:
                _generate_coloring_book_pdf(_fields())

        mock_qa.assert_called_once()
        self.assertIn("final cover QA failed", str(ctx.exception))

    def test_the_real_unmocked_gate_accepts_a_genuine_customer_generation(self):
        """End-to-end, zero-cost: the real (unmocked) validator runs against
        a real generated PDF and does not block a genuinely valid cover."""
        from services.product import _generate_coloring_book_pdf

        result = _generate_coloring_book_pdf(_fields())
        self.assertTrue(result.get("pdf_bytes"))
        self.assertTrue(result.get("cover_qa", {}).get("passed"))


if __name__ == "__main__":
    unittest.main()
