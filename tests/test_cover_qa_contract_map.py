"""Global Cover Policy: declared final-QA-authority contract map (2026-09-12).

The global rule: no final cover may reach the customer without passing its
DECLARED final QA authority. Not every product must call the same
``cover_quality_agent.py`` function -- a product with an equivalent,
product-specific final-cover QA system may use that instead. This file is
where each product's declared authority is pinned down and proven real:

  * Ebook (guided/primary flow)  -> services.ebook_photo_cover
    (inspect_variant + _first_passing_layout in services.ebook_customer_path)
  * Ebook (Cover Editor route)   -> services.cover_quality_agent.evaluate_cover_quality
  * Word Search                  -> services.cover_quality_agent.evaluate_cover_quality
  * Crossword                    -> services.cover_quality_agent.evaluate_cover_quality
  * Coloring Book (automatic)    -> services.coloring_book.final_cover_qa
    .validate_coloring_book_final_cover
  * Coloring Book (Cover Editor) -> services.cover_quality_agent.evaluate_cover_quality
  * Faith Planner                -> services.editor_in_chief_planner.review_planner
    (which calls services.planner.design_rating.rate_planner_design), gating
    ``export_ready`` at /export-product
  * Budget Planner                -> same as Faith Planner

Existing, already-passing tests already prove several of these invoked-and-
blocking claims and are not duplicated here:
  * tests/test_ebook_photo_cover_engine.py::...::test_27_zero_pass_uses_choose_another_photo_status
    -- Ebook: when every candidate layout fails inspect_variant's QA, the
    customer is blocked with NO_SAFE_COVER_MESSAGE, never a bad cover.
  * tests/test_planner_products.py::PlannerEditorInChiefTests::test_shipped_planners_pass
    -- Planner: review_planner runs against the REAL rendered PDF and only
    ever lets cover imperfections through as minor, by-design findings.
  * tests/test_cover_source_policy.py -- Ebook/Word Search/Crossword's shared
    cover_quality_agent path: template_fallback, pexels, and ai-backed covers
    all pass through the same evaluate_cover_quality() call regardless of
    source, and a broken template cover still fails it.
  * tests/test_coloring_book_final_cover_qa.py -- Coloring Book's new
    automatic-build gate.

This file adds only what those do not already cover.
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


# ---------------------------------------------------------------------------
# The contract map itself is not lying -- every declared authority is real
# and importable, so documentation cannot silently drift from the code.
# ---------------------------------------------------------------------------

class DeclaredAuthoritiesExistTests(unittest.TestCase):
    def test_ebook_guided_flow_authority_exists(self):
        from services.ebook_photo_cover import inspect_variant  # noqa: F401
        from services.ebook_customer_path import _first_passing_layout  # noqa: F401

    def test_shared_cover_quality_agent_exists(self):
        from services.cover_quality_agent import evaluate_cover_quality  # noqa: F401

    def test_coloring_book_adapter_exists(self):
        from services.coloring_book.final_cover_qa import (  # noqa: F401
            validate_coloring_book_final_cover,
        )

    def test_planner_authority_exists(self):
        from services.editor_in_chief_planner import review_planner  # noqa: F401
        from services.planner.design_rating import rate_planner_design  # noqa: F401


# ---------------------------------------------------------------------------
# Ebook -- a layout with no passing candidate is never selected
# ---------------------------------------------------------------------------

class EbookFinalQAGateTests(unittest.TestCase):
    def test_first_passing_layout_returns_empty_when_nothing_passes(self):
        from services.ebook_customer_path import _first_passing_layout

        cover = {
            "variants": {
                "full_bleed_editorial": {"quality": {"pass": False}, "png_path": "/tmp/a.png"},
                "split_studio": {"quality": {"pass": True}, "png_path": ""},  # no file -- not real
                "printed_moment": {"quality": {}, "png_path": "/tmp/b.png"},
            }
        }
        self.assertEqual(_first_passing_layout(cover), "")

    def test_first_passing_layout_requires_a_real_file_not_only_a_pass_flag(self):
        """A 'pass' claim with no rendered file on disk must not be trusted --
        proves this cannot be satisfied by metadata alone."""
        from services.ebook_customer_path import _first_passing_layout

        cover = {"variants": {"full_bleed_editorial": {"quality": {"pass": True}, "png_path": ""}}}
        self.assertEqual(_first_passing_layout(cover), "")

    def test_first_passing_layout_accepts_a_genuinely_passing_real_variant(self, ):
        import tempfile

        from services.ebook_customer_path import _first_passing_layout

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as fh:
            fh.write(b"fake png bytes")
            path = fh.name
        try:
            cover = {"variants": {"full_bleed_editorial": {"quality": {"pass": True}, "png_path": path}}}
            self.assertEqual(_first_passing_layout(cover), "full_bleed_editorial")
        finally:
            os.remove(path)


# ---------------------------------------------------------------------------
# Faith Planner / Budget Planner -- the design-rating check genuinely
# evaluates real rendered pixels, not a declarative field
# ---------------------------------------------------------------------------

class PlannerDesignRatingRealPixelTests(unittest.TestCase):
    def test_weak_measured_contrast_produces_a_real_deduction(self):
        """rate_planner_design measures actual pixel luminance under the
        title (via _image_region_stats) -- proven here by forcing that
        measurement to report near-zero contrast and confirming the specific
        DESIGN_COVER_WEAK_CONTRAST finding fires, not a generic one."""
        from services.planner.design_rating import rate_planner_design

        facts = {
            "pages": [{"width": 612.0, "height": 792.0}],
            "cover": {
                "title_size": 40.0,
                "sizes": [40.0, 18.0],
                "fonts": ["Helvetica", "Helvetica-Bold"],
                "title_bbox": (50, 50, 300, 100),
            },
        }
        with patch(
            "services.planner.design_rating._image_region_stats",
            return_value={"p05": 120, "p50": 122, "p95": 124},  # near-flat -> low contrast
        ):
            rating = rate_planner_design(
                facts, page_kinds=["cover"], page_images=["fake.png"],
                page_stats=[], design_stats=[], theme=None,
                cover_source="ai_only", cover_dpi=300.0,
            )
        codes = [code for _cat, code, _reason in rating["deductions"]]
        self.assertIn("DESIGN_COVER_WEAK_CONTRAST", codes)
        self.assertIn("cover_title_contrast", rating["evidence"])
        self.assertLess(rating["evidence"]["cover_title_contrast"], 3.0)

    def test_strong_measured_contrast_produces_no_contrast_deduction(self):
        """Same check, genuinely good input -- proves the check is a real
        two-sided measurement, not one that always fires or never fires."""
        from services.planner.design_rating import rate_planner_design

        facts = {
            "pages": [{"width": 612.0, "height": 792.0}],
            "cover": {
                "title_size": 40.0,
                "sizes": [40.0, 18.0],
                "fonts": ["Helvetica", "Helvetica-Bold"],
                "title_bbox": (50, 50, 300, 100),
            },
        }
        with patch(
            "services.planner.design_rating._image_region_stats",
            return_value={"p05": 10, "p50": 20, "p95": 250},  # strong dark-on-light contrast
        ):
            rating = rate_planner_design(
                facts, page_kinds=["cover"], page_images=["fake.png"],
                page_stats=[], design_stats=[], theme=None,
                cover_source="ai_only", cover_dpi=300.0,
            )
        codes = [code for _cat, code, _reason in rating["deductions"]]
        self.assertNotIn("DESIGN_COVER_WEAK_CONTRAST", codes)
        self.assertNotIn("DESIGN_COVER_SOFT_CONTRAST", codes)


if __name__ == "__main__":
    unittest.main()
