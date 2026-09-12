"""Global Cover Source Policy: PEXELS FIRST -> quality gate -> paid AI fallback.

Zero paid calls. Pexels and the AI image client are both mocked/patched in
every test here — see services/cover_source_policy.py's module docstring for
what this module does and does not do (Ebook-scoped for this pass; Word
Search / Crossword / Coloring Book keep their prior AI-only behavior
unchanged, proven explicitly below).
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
os.environ["PEXELS_API_KEY"] = ""

from services.cover_agent import create_cover_design, regenerate_cover_image  # noqa: E402
from services.cover_source_policy import (  # noqa: E402
    evaluate_pexels_candidate,
    try_pexels_first_cover,
)

GOOD_PHOTO = {
    "provider": "pexels",
    "photo_id": "12345",
    "photographer": "Jane Doe",
    "photographer_url": "https://www.pexels.com/@janedoe",
    "page_url": "https://www.pexels.com/photo/12345",
    "preview_url": "https://images.pexels.com/photos/12345/preview.jpg",
    "original_url": "https://images.pexels.com/photos/12345/original.jpg",
    "width": 2000,
    "height": 3000,
    "orientation": "portrait",
    "alt": "container vegetable garden with tomatoes and herbs in pots on a sunny patio",
    "attribution": "Photo by Jane Doe on Pexels",
    "license_note": "Pexels License",
}


# ---------------------------------------------------------------------------
# evaluate_pexels_candidate — the deterministic, zero-cost gate
# ---------------------------------------------------------------------------

class EvaluatePexelsCandidateTests(unittest.TestCase):
    def test_a_genuinely_appropriate_candidate_passes(self):
        result = evaluate_pexels_candidate(
            GOOD_PHOTO, title="Container Vegetable Gardening", topic="container vegetable garden"
        )
        self.assertTrue(result.passed, result.reasons)
        self.assertEqual(result.reasons, [])

    def test_low_resolution_is_rejected(self):
        photo = {**GOOD_PHOTO, "width": 400, "height": 600}
        result = evaluate_pexels_candidate(photo, title="Container Vegetable Gardening", topic="garden")
        self.assertFalse(result.passed)
        self.assertTrue(any("resolution" in r.lower() for r in result.reasons))

    def test_landscape_orientation_is_rejected_for_a_portrait_cover(self):
        photo = {**GOOD_PHOTO, "width": 3000, "height": 2000}
        result = evaluate_pexels_candidate(photo, title="Container Vegetable Gardening", topic="garden")
        self.assertFalse(result.passed)
        self.assertTrue(any("landscape" in r.lower() for r in result.reasons))

    def test_missing_alt_text_is_rejected_rather_than_assumed_fine(self):
        photo = {**GOOD_PHOTO, "alt": ""}
        result = evaluate_pexels_candidate(photo, title="Container Vegetable Gardening", topic="garden")
        self.assertFalse(result.passed)
        self.assertTrue(any("alt text" in r.lower() for r in result.reasons))

    def test_topic_irrelevant_photo_is_rejected(self):
        photo = {**GOOD_PHOTO, "alt": "a red sports car parked in a city street at night"}
        result = evaluate_pexels_candidate(
            photo, title="Container Vegetable Gardening", topic="container vegetable garden"
        )
        self.assertFalse(result.passed)
        self.assertTrue(any("does not appear to relate" in r.lower() for r in result.reasons))

    def test_stock_watermark_marker_in_alt_text_is_rejected(self):
        photo = {**GOOD_PHOTO, "alt": "garden tomatoes stock photo watermark sample"}
        result = evaluate_pexels_candidate(photo, title="Container Vegetable Gardening", topic="garden")
        self.assertFalse(result.passed)
        self.assertTrue(any("generic/watermarked" in r.lower() for r in result.reasons))

    def test_a_weak_candidate_is_never_accepted_just_because_one_was_returned(self):
        """Multiple independent failure reasons on one bad photo -- not a single soft check."""
        photo = {"provider": "pexels", "photo_id": "1", "width": 300, "height": 200, "alt": ""}
        result = evaluate_pexels_candidate(photo, title="Container Vegetable Gardening", topic="garden")
        self.assertFalse(result.passed)
        self.assertGreaterEqual(len(result.reasons), 2)


# ---------------------------------------------------------------------------
# try_pexels_first_cover — the PEXELS FIRST step
# ---------------------------------------------------------------------------

class TryPexelsFirstCoverTests(unittest.TestCase):
    def _cover(self, *, product_type: str = "ebook") -> dict:
        return create_cover_design(
            title="Container Vegetable Gardening",
            subtitle="A Beginner's Guide",
            author="Jane Author",
            content_md="# Container Vegetable Gardening\n\nGrow tomatoes in pots.",
            product_type=product_type,
        )

    def test_not_configured_falls_through_with_a_clear_note(self):
        cover = self._cover()
        with patch("services.ebook_pexels.pexels_configured", return_value=False):
            updated, url = try_pexels_first_cover(cover, "pkg_test_1")
        self.assertIsNone(updated)
        self.assertIsNone(url)
        self.assertIn("not configured", cover["cover_source_note"].lower())

    def test_no_package_id_is_a_no_op(self):
        cover = self._cover()
        updated, url = try_pexels_first_cover(cover, "")
        self.assertIsNone(updated)
        self.assertIsNone(url)

    def test_a_good_candidate_is_accepted_as_the_source_with_no_paid_call(self):
        cover = self._cover()

        def fake_search(query, **kwargs):
            return {"photos": [GOOD_PHOTO], "query": query}

        with patch("services.ebook_pexels.pexels_configured", return_value=True), patch(
            "services.ebook_pexels.search_pexels", side_effect=fake_search
        ), patch(
            "services.cover_source_policy._save_pexels_cover_image", return_value="/tmp/img_cover.png"
        ) as mock_save:
            updated, url = try_pexels_first_cover(cover, "pkg_test_2")

        self.assertIsNotNone(updated)
        self.assertEqual(updated["cover_source"], "pexels")
        self.assertFalse(updated["paid_ai_used"])
        self.assertIn("Jane Doe", updated["cover_source_note"])
        self.assertTrue(url)
        mock_save.assert_called_once()

    def test_every_candidate_failing_the_gate_falls_through_to_ai(self):
        cover = self._cover()
        bad_photo = {**GOOD_PHOTO, "width": 200, "height": 150, "alt": ""}

        def fake_search(query, **kwargs):
            return {"photos": [bad_photo], "query": query}

        with patch("services.ebook_pexels.pexels_configured", return_value=True), patch(
            "services.ebook_pexels.search_pexels", side_effect=fake_search
        ):
            updated, url = try_pexels_first_cover(cover, "pkg_test_3")

        self.assertIsNone(updated)
        self.assertIsNone(url)
        self.assertIn("falling back to paid ai", cover["cover_source_note"].lower())

    def test_no_search_results_at_all_falls_through_to_ai(self):
        cover = self._cover()
        with patch("services.ebook_pexels.pexels_configured", return_value=True), patch(
            "services.ebook_pexels.search_pexels", return_value={"photos": [], "query": "x"}
        ):
            updated, url = try_pexels_first_cover(cover, "pkg_test_4")
        self.assertIsNone(updated)
        self.assertIsNone(url)


# ---------------------------------------------------------------------------
# regenerate_cover_image wiring — Ebook gets Pexels-first; other products do not
# ---------------------------------------------------------------------------

class RegenerateCoverImageWiringTests(unittest.TestCase):
    def _cover(self, *, product_type: str) -> dict:
        return create_cover_design(
            title="Container Vegetable Gardening",
            subtitle="A Beginner's Guide",
            author="Jane Author",
            content_md="# Container Vegetable Gardening\n\nGrow tomatoes in pots.",
            product_type=product_type,
        )

    def test_ebook_uses_pexels_when_a_good_candidate_exists_and_never_calls_paid_ai(self):
        cover = self._cover(product_type="ebook")

        def fake_search(query, **kwargs):
            return {"photos": [GOOD_PHOTO], "query": query}

        with patch("services.ebook_pexels.pexels_configured", return_value=True), patch(
            "services.ebook_pexels.search_pexels", side_effect=fake_search
        ), patch(
            "services.cover_source_policy._save_pexels_cover_image", return_value="/tmp/img_cover.png"
        ), patch(
            "services.ebook_package.render_visual_image"
        ) as mock_ai:
            updated, url = regenerate_cover_image(cover, "pkg_wire_1")

        self.assertEqual(updated["cover_source"], "pexels")
        self.assertFalse(updated["paid_ai_used"])
        mock_ai.assert_not_called()

    def test_ebook_falls_back_to_paid_ai_when_pexels_has_no_acceptable_candidate(self):
        cover = self._cover(product_type="ebook")
        with patch("services.ebook_pexels.pexels_configured", return_value=False), patch(
            "services.ebook_package.render_visual_image", return_value="/download/pkg/img_cover.png"
        ) as mock_ai:
            updated, url = regenerate_cover_image(cover, "pkg_wire_2")

        mock_ai.assert_called_once()
        self.assertEqual(updated["cover_source"], "ai_fallback")
        self.assertTrue(updated["paid_ai_used"])
        self.assertTrue(url)

    def test_word_search_never_attempts_pexels_and_keeps_prior_ai_only_behavior(self):
        """Function Lock proof: Word Search's own behavior is unchanged by this
        shared-file edit -- Pexels is never even attempted for it."""
        cover = self._cover(product_type="word_search_book")
        with patch("services.ebook_pexels.pexels_configured", return_value=True) as mock_configured, patch(
            "services.ebook_pexels.search_pexels"
        ) as mock_search, patch(
            "services.ebook_package.render_visual_image", return_value="/download/pkg/img_cover.png"
        ) as mock_ai:
            updated, url = regenerate_cover_image(cover, "pkg_wire_3")

        mock_configured.assert_not_called()
        mock_search.assert_not_called()
        mock_ai.assert_called_once()
        self.assertEqual(updated["cover_source"], "ai_only")
        self.assertTrue(updated["paid_ai_used"])

    def test_crossword_never_attempts_pexels_and_keeps_prior_ai_only_behavior(self):
        cover = self._cover(product_type="crossword_puzzle_book")
        with patch("services.ebook_pexels.search_pexels") as mock_search, patch(
            "services.ebook_package.render_visual_image", return_value="/download/pkg/img_cover.png"
        ) as mock_ai:
            updated, url = regenerate_cover_image(cover, "pkg_wire_4")

        mock_search.assert_not_called()
        mock_ai.assert_called_once()
        self.assertEqual(updated["cover_source"], "ai_only")

    def test_coloring_book_never_attempts_pexels_and_keeps_prior_ai_only_behavior(self):
        cover = self._cover(product_type="coloring_book")
        with patch("services.ebook_pexels.search_pexels") as mock_search, patch(
            "services.ebook_package.render_visual_image", return_value="/download/pkg/img_cover.png"
        ) as mock_ai:
            updated, url = regenerate_cover_image(cover, "pkg_wire_5")

        mock_search.assert_not_called()
        mock_ai.assert_called_once()
        self.assertEqual(updated["cover_source"], "ai_only")


if __name__ == "__main__":
    unittest.main()
