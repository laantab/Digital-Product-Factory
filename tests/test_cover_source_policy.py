"""Global Cover Source Policy: PEXELS FIRST -> quality gate -> paid AI fallback.

Zero paid calls. Pexels and the AI image client are both mocked/patched in
every test here. See services/cover_source_policy.py's module docstring for
the exact, current scope: Ebook, Word Search, and Crossword genuinely attempt
Pexels (gated on ``is_photo_realistic_cover``); Coloring Book and any
Black-History-topic cover never do (a media-type / product-safety fact, not
an arbitrary exclusion); Faith/Budget Planner get the same quality gate on
their existing "let the Factory choose" flow, with an AI fallback function
implemented and tested but deliberately not wired into their live path yet
(see the module docstring for why).
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
from services.cover_quality_agent import evaluate_cover_quality  # noqa: E402
from services.cover_source_policy import (  # noqa: E402
    build_planner_ai_cover_prompt,
    evaluate_pexels_candidate,
    try_ai_fallback_planner_cover,
    try_pexels_first_cover,
)

def _fake_ai_success(package_id: str, visual_id: str, prompt: str, size=None) -> str:
    """Stand-in for a SUCCESSFUL services.ebook_package.render_visual_image
    call: writes a real PNG at the exact path cover_agent.py's own
    _has_cover_image()/_cover_image_path() check, so cover_source tracking
    (which reads real file existence, not the mocked return value alone) is
    exercised the same way a genuine successful generation would be."""
    from PIL import Image

    from services.cover_agent import _cover_image_path

    path = _cover_image_path(package_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (1024, 1536), (20, 30, 40)).save(path, "PNG")
    return f"/download/{package_id}/img_{visual_id}.png"


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
        photo = {"provider": "pexels", "photo_id": "1", "width": 300, "height": 200, "alt": ""}
        result = evaluate_pexels_candidate(photo, title="Container Vegetable Gardening", topic="garden")
        self.assertFalse(result.passed)
        self.assertGreaterEqual(len(result.reasons), 2)


# ---------------------------------------------------------------------------
# try_pexels_first_cover — the PEXELS FIRST step (product-agnostic)
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
# regenerate_cover_image wiring — who genuinely attempts Pexels, and who does not
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
            "services.ebook_package.render_visual_image", side_effect=_fake_ai_success
        ) as mock_ai, patch(
            "services.ebook_package.paid_image_generation_authorized", return_value=True
        ):
            updated, url = regenerate_cover_image(cover, "pkg_wire_2")

        mock_ai.assert_called_once()
        self.assertEqual(updated["cover_source"], "ai_fallback")
        self.assertTrue(updated["paid_ai_attempted"])
        self.assertTrue(updated["paid_ai_used"])
        self.assertTrue(url)

    def test_paid_ai_used_is_false_when_the_call_was_never_authorized(self):
        """A confirmed image existing is not enough to mark cost incurred --
        the AI pipeline's own authorization gate must have actually been open,
        per the owner's 'do not guess' cost-tracking contract."""
        cover = self._cover(product_type="ebook")
        with patch("services.ebook_pexels.pexels_configured", return_value=False), patch(
            "services.ebook_package.render_visual_image", side_effect=_fake_ai_success
        ), patch(
            "services.ebook_package.paid_image_generation_authorized", return_value=False
        ):
            updated, url = regenerate_cover_image(cover, "pkg_wire_2b")

        self.assertTrue(updated["paid_ai_attempted"])
        self.assertFalse(updated["paid_ai_used"])

    def test_word_search_now_genuinely_attempts_pexels(self):
        """Extended scope (owner-approved): Word Search's cover is photo-realistic,
        so it is genuinely eligible for PEXELS FIRST like Ebook."""
        cover = self._cover(product_type="word_search_book")

        def fake_search(query, **kwargs):
            return {"photos": [GOOD_PHOTO], "query": query}

        with patch("services.ebook_pexels.pexels_configured", return_value=True), patch(
            "services.ebook_pexels.search_pexels", side_effect=fake_search
        ), patch(
            "services.cover_source_policy._save_pexels_cover_image", return_value="/tmp/img_cover.png"
        ), patch(
            "services.ebook_package.render_visual_image"
        ) as mock_ai:
            updated, url = regenerate_cover_image(cover, "pkg_wire_3")

        self.assertEqual(updated["cover_source"], "pexels")
        self.assertFalse(updated["paid_ai_used"])
        mock_ai.assert_not_called()

    def test_word_search_falls_back_to_ai_when_pexels_has_nothing_suitable(self):
        """Word Search's own AI-only behavior is preserved as the fallback --
        it is not degraded, only given a free first attempt."""
        cover = self._cover(product_type="word_search_book")
        with patch("services.ebook_pexels.pexels_configured", return_value=False), patch(
            "services.ebook_package.render_visual_image", side_effect=_fake_ai_success
        ) as mock_ai, patch(
            "services.ebook_package.paid_image_generation_authorized", return_value=True
        ):
            updated, url = regenerate_cover_image(cover, "pkg_wire_4")

        mock_ai.assert_called_once()
        self.assertEqual(updated["cover_source"], "ai_fallback")
        self.assertTrue(updated["paid_ai_used"])
        self.assertTrue(url)

    def test_crossword_now_genuinely_attempts_pexels(self):
        cover = self._cover(product_type="crossword_puzzle_book")

        def fake_search(query, **kwargs):
            return {"photos": [GOOD_PHOTO], "query": query}

        with patch("services.ebook_pexels.pexels_configured", return_value=True), patch(
            "services.ebook_pexels.search_pexels", side_effect=fake_search
        ), patch(
            "services.cover_source_policy._save_pexels_cover_image", return_value="/tmp/img_cover.png"
        ), patch(
            "services.ebook_package.render_visual_image"
        ) as mock_ai:
            updated, url = regenerate_cover_image(cover, "pkg_wire_5")

        self.assertEqual(updated["cover_source"], "pexels")
        mock_ai.assert_not_called()

    def test_crossword_falls_back_to_ai_when_pexels_has_nothing_suitable(self):
        cover = self._cover(product_type="crossword_puzzle_book")
        with patch("services.ebook_pexels.pexels_configured", return_value=False), patch(
            "services.ebook_package.render_visual_image", side_effect=_fake_ai_success
        ) as mock_ai, patch(
            "services.ebook_package.paid_image_generation_authorized", return_value=True
        ):
            updated, url = regenerate_cover_image(cover, "pkg_wire_6")

        mock_ai.assert_called_once()
        self.assertEqual(updated["cover_source"], "ai_fallback")
        self.assertTrue(updated["paid_ai_used"])

    def test_coloring_book_never_attempts_pexels_illustrated_media_type(self):
        """Coloring Book is EXPLICITLY excluded by product type (not left to
        is_photo_realistic_cover's classifier -- see cover_agent.py's
        docstring for why that classifier alone would have gotten this
        wrong for most real coloring-book topics)."""
        cover = self._cover(product_type="coloring_book")
        with patch("services.ebook_pexels.search_pexels") as mock_search, patch(
            "services.ebook_package.render_visual_image", side_effect=_fake_ai_success
        ) as mock_ai, patch(
            "services.ebook_package.paid_image_generation_authorized", return_value=True
        ):
            updated, url = regenerate_cover_image(cover, "pkg_wire_7")

        mock_search.assert_not_called()
        mock_ai.assert_called_once()
        self.assertEqual(updated["cover_source"], "ai_only")
        self.assertTrue(updated["paid_ai_used"])

    def test_black_history_topic_never_attempts_pexels_regardless_of_product(self):
        """Product safety carve-out: generic Pexels stock cannot satisfy this
        Factory's specific, safety-reviewed Black History cover requirements."""
        cover = self._cover(product_type="word_search_book")
        cover["title"] = "Black History Word Search Book"
        cover["cover_prompt"] = "Word search puzzles about Black History"
        with patch("services.ebook_pexels.search_pexels") as mock_search, patch(
            "services.ebook_package.render_visual_image", side_effect=_fake_ai_success
        ) as mock_ai, patch(
            "services.ebook_package.paid_image_generation_authorized", return_value=True
        ):
            updated, url = regenerate_cover_image(cover, "pkg_wire_8")

        mock_search.assert_not_called()
        mock_ai.assert_called_once()
        self.assertEqual(updated["cover_source"], "ai_only")
        self.assertTrue(updated["paid_ai_used"])


# ---------------------------------------------------------------------------
# Pexels and AI both fail -> never silently shipped as a finished PHOTO cover
# ---------------------------------------------------------------------------

class BothSourcesFailClearlyTests(unittest.TestCase):
    def _failed_cover(self, package_id: str) -> tuple[dict, str | None]:
        cover = create_cover_design(
            title="Container Vegetable Gardening",
            subtitle="A Beginner's Guide",
            author="Jane Author",
            content_md="# Container Vegetable Gardening\n\nGrow tomatoes in pots.",
            product_type="ebook",
        )
        with patch("services.ebook_pexels.pexels_configured", return_value=False), patch(
            "services.ebook_package.render_visual_image", return_value=None
        ):
            return regenerate_cover_image(cover, package_id)

    def test_final_source_is_honestly_template_fallback_not_ai_fallback(self):
        """When Pexels finds nothing and the paid AI call also fails to
        produce an image, no AI image exists -- cover_source must say
        'template_fallback', never 'ai_fallback' (that would falsely claim
        an AI image is the final cover when cover_agent.py's PRE-EXISTING
        template tier actually rendered it). This was the exact bug the
        owner's review caught."""
        updated, url = self._failed_cover("pkg_both_fail_1")
        self.assertIsNone(url)
        self.assertEqual(updated["cover_source"], "template_fallback")
        self.assertTrue(updated["paid_ai_attempted"])
        # No confirmed successful, fresh, authorized generation occurred --
        # cost tracking stays false rather than assumed true.
        self.assertFalse(updated["paid_ai_used"])

    def test_the_template_is_a_complete_professional_cover_never_blank_or_broken(self):
        """cover_agent.py's PRE-EXISTING template fallback (unchanged by this
        policy) renders a real, complete, professionally-designed gradient
        cover with the actual title -- never a blank or 'pending' placeholder."""
        updated, url = self._failed_cover("pkg_both_fail_2")
        self.assertIn("Container Vegetable Gardening", updated["preview_html"])
        self.assertIn("cda-template-cover", updated["preview_html"])
        self.assertNotIn("cda-cover-pending", updated["preview_html"])

    def test_template_fallback_still_passes_the_same_final_rendered_cover_qa(self):
        """template_fallback is accepted as a legitimate third source ONLY
        because it genuinely passes the same final QA every other source
        must pass -- not because QA treats it specially."""
        updated, url = self._failed_cover("pkg_both_fail_3")
        qa = evaluate_cover_quality(updated)
        self.assertTrue(qa.passed, qa.errors)

    def test_a_broken_template_cover_still_fails_final_qa(self):
        """Proof the template cannot silently bypass QA merely because it is
        deterministic: a cover claiming to be finished but missing its title
        (simulating a corrupted/incomplete template render) must still fail."""
        updated, _url = self._failed_cover("pkg_both_fail_4")
        broken = dict(updated)
        broken["title"] = ""
        broken["preview_html"] = updated["preview_html"].replace(
            "Container Vegetable Gardening", ""
        )
        qa = evaluate_cover_quality(broken)
        self.assertFalse(qa.passed)


# ---------------------------------------------------------------------------
# Deterministic typography is unaffected by the cover's source
# ---------------------------------------------------------------------------

class TypographyUnaffectedByCoverSourceTests(unittest.TestCase):
    def test_title_renders_identically_regardless_of_pexels_or_ai_source(self):
        pexels_cover = create_cover_design(
            title="Container Vegetable Gardening", subtitle="A Beginner's Guide",
            author="Jane Author", content_md="garden content", product_type="ebook",
        )
        pexels_cover["cover_source"] = "pexels"
        ai_cover = create_cover_design(
            title="Container Vegetable Gardening", subtitle="A Beginner's Guide",
            author="Jane Author", content_md="garden content", product_type="ebook",
        )
        ai_cover["cover_source"] = "ai_fallback"
        # Both use the same HTML/CSS text-overlay system (use_ai_image=True
        # controls the composited layer regardless of image origin) -- the
        # rendered title markup must be identical either way.
        self.assertIn("Container Vegetable Gardening", pexels_cover["preview_html"])
        self.assertIn("Container Vegetable Gardening", ai_cover["preview_html"])
        self.assertEqual(pexels_cover["font_style"], ai_cover["font_style"])
        self.assertEqual(pexels_cover["layout"], ai_cover["layout"])


# ---------------------------------------------------------------------------
# Faith Planner / Budget Planner
# ---------------------------------------------------------------------------

class PlannerAutoCoverPhotoGateTests(unittest.TestCase):
    def test_auto_cover_photo_rejects_a_weak_candidate_and_tries_the_next(self):
        from services.planner.cover_photos import auto_cover_photo

        weak = {**GOOD_PHOTO, "photo_id": "1", "alt": ""}
        good = {**GOOD_PHOTO, "photo_id": "2", "alt": "devotional journal desk with candle and bible"}

        def fake_search_cover_photos(**kwargs):
            return {"query": "devotional desk", "_raw_photos": [weak, good], "configured": True}

        with patch(
            "services.planner.cover_photos.search_cover_photos", side_effect=fake_search_cover_photos
        ), patch(
            "services.planner.cover_photos.select_cover_photo",
            return_value={"asset_id": "pexels-2", "path": "/tmp/p2.jpg", "attribution": "Photo by X"},
        ) as mock_select:
            result = auto_cover_photo(title="Daily Devotional", planner_type="faith_planner", design_theme="")

        self.assertIsNotNone(result)
        mock_select.assert_called_once_with("2", photo=good)

    def test_auto_cover_photo_returns_none_when_every_candidate_is_weak(self):
        from services.planner.cover_photos import auto_cover_photo

        weak = {**GOOD_PHOTO, "photo_id": "1", "alt": ""}

        def fake_search_cover_photos(**kwargs):
            return {"query": "devotional desk", "_raw_photos": [weak], "configured": True}

        with patch(
            "services.planner.cover_photos.search_cover_photos", side_effect=fake_search_cover_photos
        ), patch("services.planner.cover_photos.select_cover_photo") as mock_select:
            result = auto_cover_photo(title="Daily Devotional", planner_type="faith_planner", design_theme="")

        self.assertIsNone(result)
        mock_select.assert_not_called()


class PlannerAiFallbackTests(unittest.TestCase):
    """try_ai_fallback_planner_cover is implemented and tested, but is not
    called from services/product.py's live planner build (see module
    docstring: it would break the documented 'no AI call, no paid image
    call, deterministic' invariant for Faith/Budget Planner)."""

    def test_prompt_never_bakes_the_title_as_literal_text_instructions(self):
        prompt = build_planner_ai_cover_prompt(
            title="Daily Devotional", planner_type="faith_planner", design_theme=""
        )
        self.assertIn("background artwork", prompt.lower())
        self.assertNotIn("write the title", prompt.lower())

    def test_returns_none_without_a_package_id(self):
        result = try_ai_fallback_planner_cover(
            title="Daily Devotional", planner_type="faith_planner", design_theme="", package_id=""
        )
        self.assertIsNone(result)

    def test_a_successful_generation_is_tracked_as_ai_fallback_paid(self):
        import tempfile

        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            pkg = "pkg_planner_ai"
            pkg_dir = os.path.join(tmp, pkg)
            img_path = os.path.join(pkg_dir, "img_cover.png")

            def fake_render(*args, **kwargs):
                # File must not exist beforehand -- created BY this call, so
                # the "fresh, not a cache hit" cost signal is genuine.
                os.makedirs(pkg_dir, exist_ok=True)
                Image.new("RGB", (1024, 1536), (10, 20, 30)).save(img_path)
                return f"/download/{pkg}/img_cover.png"

            with patch(
                "services.ebook_package.render_visual_image", side_effect=fake_render
            ), patch(
                "services.cover_agent._cover_image_path", return_value=img_path
            ), patch(
                "services.ebook_package.paid_image_generation_authorized", return_value=True
            ):
                result = try_ai_fallback_planner_cover(
                    title="Daily Devotional", planner_type="faith_planner",
                    design_theme="", package_id=pkg,
                )

        self.assertIsNotNone(result)
        self.assertEqual(result["source"], "ai_fallback")
        self.assertTrue(result["paid_ai_attempted"])
        self.assertTrue(result["paid_ai_used"])
        self.assertEqual(result["width"], 1024)

    def test_reusing_an_existing_file_is_not_billed_again(self):
        """Cost tracking mirrors the cover_agent.py contract: a pre-existing
        file (e.g. a fingerprint/dedup cache hit) means no NEW cost, even
        though generation is reported as successful."""
        import tempfile

        from PIL import Image

        with tempfile.TemporaryDirectory() as tmp:
            pkg = "pkg_planner_ai_cached"
            pkg_dir = os.path.join(tmp, pkg)
            os.makedirs(pkg_dir, exist_ok=True)
            img_path = os.path.join(pkg_dir, "img_cover.png")
            Image.new("RGB", (1024, 1536), (10, 20, 30)).save(img_path)

            with patch(
                "services.ebook_package.render_visual_image",
                return_value=f"/download/{pkg}/img_cover.png",
            ), patch(
                "services.cover_agent._cover_image_path", return_value=img_path
            ), patch(
                "services.ebook_package.paid_image_generation_authorized", return_value=True
            ):
                result = try_ai_fallback_planner_cover(
                    title="Daily Devotional", planner_type="faith_planner",
                    design_theme="", package_id=pkg,
                )

        self.assertIsNotNone(result)
        self.assertTrue(result["paid_ai_attempted"])
        self.assertFalse(result["paid_ai_used"])

    def test_returns_none_when_generation_produces_no_url(self):
        with patch("services.ebook_package.render_visual_image", return_value=None):
            result = try_ai_fallback_planner_cover(
                title="Daily Devotional", planner_type="faith_planner",
                design_theme="", package_id="pkg_planner_ai_fail",
            )
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
