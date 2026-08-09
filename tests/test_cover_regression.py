"""Regression tests for cover editor — Gold Rush brief, fingerprint, validation, and zero-API calls.

These tests use mocks or fixture data only. No OpenAI or Tavily calls.
"""
import unittest
from unittest.mock import patch, MagicMock

# Ensure flask_app packages are on path
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.product_cover_agent import (
    build_crossword_cover_brief,
    compute_cover_fingerprint,
)
from services.cover_quality_agent import (
    validate_cover_for_export,
    _AI_GIBBERISH_PATTERNS,
    _TEMPLATE_WORDING,
    _DARK_TITLE_BAND_PATTERNS,
)


# ---------------------------------------------------------------------------
# Gold Rush brief tests
# ---------------------------------------------------------------------------

class TestGoldRushCoverBrief(unittest.TestCase):
    """Regression: California Gold Rush produces the correct visual direction."""

    def test_gold_rush_topic_produces_gold_rush_visual_direction(self):
        """Gold Rush in theme → Gold Rush visual direction in brief."""
        brief = build_crossword_cover_brief(
            fields={"theme": "California Gold Rush", "difficulty": "Easy"},
            title="California Gold Rush Terms",
            puzzle_count=10,
        )
        prompt = brief["cover_prompt"]
        prompt_lower = prompt.lower()
        # Must mention Gold Rush / California historical imagery
        self.assertTrue(
            any(k in prompt_lower for k in ("gold rush", "california", "prospectors", "mining")),
            f"Gold Rush brief missing Gold Rush terms in:\n{prompt[:300]}",
        )
        # Must NOT appear as a positive directive (check bare mention, not "no X" negative)
        # The brief says "no modern machinery" etc. — that IS correct. Only fail if bare mention.
        bare_forbidden = ("modern machinery", "modern clothing", "cartoon animal", "food")
        for item in bare_forbidden:
            # Find bare occurrence (not "no X")
            idx = prompt_lower.find(item)
            while idx != -1:
                before = prompt_lower[max(0, idx - 4):idx].strip()
                self.assertIn("no", before, f"Forbidden item '{item}' must only appear after 'no': ...{before} '{item}'")
                idx = prompt_lower.find(item, idx + 1)

    def test_gold_rush_style_is_elegant(self):
        """Gold Rush brief uses the 'elegant' style."""
        brief = build_crossword_cover_brief(
            fields={"theme": "California Gold Rush"},
            title="California Gold Rush Terms",
            puzzle_count=10,
        )
        self.assertEqual(brief["style_preference"], "elegant")

    def test_gold_rush_brief_subtitle_format(self):
        """Gold Rush brief subtitle follows correct format."""
        brief = build_crossword_cover_brief(
            fields={"theme": "California Gold Rush", "difficulty": "Easy"},
            title="California Gold Rush Terms",
            puzzle_count=10,
        )
        self.assertIn("10", brief["subtitle"])
        self.assertIn("Crossword", brief["subtitle"])
        self.assertIn("Easy", brief["subtitle"])

    def test_non_gold_rush_topic_uses_default_direction(self):
        """Non-Gold Rush topics use the standard crossword brief, not Gold Rush."""
        brief = build_crossword_cover_brief(
            fields={"theme": "Fruits and Vegetables", "difficulty": "Medium"},
            title="Fruits and Vegetables",
            puzzle_count=5,
        )
        prompt_lower = brief["cover_prompt"].lower()
        # Should NOT mention Gold Rush imagery for a fruits topic
        gold_rush_terms = ("prospectors", "sierra nevada", "sluice", "gold pan")
        for term in gold_rush_terms:
            self.assertNotIn(term, prompt_lower,
                f"Gold Rush term '{term}' leaked into non-Gold Rush brief")


# ---------------------------------------------------------------------------
# Fingerprint cost-protection tests
# ---------------------------------------------------------------------------

class TestCoverFingerprint(unittest.TestCase):
    """Regression: Cover fingerprint prevents duplicate API calls."""

    def test_same_inputs_produce_same_fingerprint(self):
        """Identical cover inputs always produce the same fingerprint."""
        fp1 = compute_cover_fingerprint(
            topic="California Gold Rush",
            title="California Gold Rush Terms",
            subtitle="10 Crossword Puzzles · Easy Level",
            product_type="crossword",
            audience="General readers",
            difficulty="Easy",
            style="elegant",
        )
        fp2 = compute_cover_fingerprint(
            topic="California Gold Rush",
            title="California Gold Rush Terms",
            subtitle="10 Crossword Puzzles · Easy Level",
            product_type="crossword",
            audience="General readers",
            difficulty="Easy",
            style="elegant",
        )
        self.assertEqual(fp1, fp2)
        self.assertEqual(len(fp1), 32)  # SHA256 truncated to 32 chars

    def test_different_topic_produces_different_fingerprint(self):
        """Different topic → different fingerprint."""
        fp_gold = compute_cover_fingerprint(
            topic="California Gold Rush", title="Gold Rush", subtitle="Sub",
            product_type="crossword",
        )
        fp_fruit = compute_cover_fingerprint(
            topic="Fruits", title="Fruits", subtitle="Sub",
            product_type="crossword",
        )
        self.assertNotEqual(fp_gold, fp_fruit)

    def test_fingerprint_is_case_insensitive(self):
        """Case differences don't change the fingerprint."""
        fp1 = compute_cover_fingerprint(
            topic="CALIFORNIA GOLD RUSH", title="Gold Rush Terms",
            subtitle="Sub", product_type="crossword",
        )
        fp2 = compute_cover_fingerprint(
            topic="california gold rush", title="gold rush terms",
            subtitle="Sub", product_type="crossword",
        )
        self.assertEqual(fp1, fp2)


# ---------------------------------------------------------------------------
# Cover export validation tests
# ---------------------------------------------------------------------------

class TestValidateCoverForExport(unittest.TestCase):
    """Regression: validate_cover_for_export() catches bad covers before export."""

    def test_valid_cover_passes(self):
        """A properly filled cover with no issues passes validation."""
        cover = {
            "title": "California Gold Rush Terms",
            "subtitle": "10 Crossword Puzzles · Easy Level",
            "author": "Lonnie Brown",
            "image_prompt": "California Gold Rush mining camp",
            "cover_asset_url": "/download/pkg/img_cover.png",
            "color_palette": {"primary": "#7c2d12"},
        }
        issues = validate_cover_for_export(
            cover,
            expected_title="California Gold Rush Terms",
            expected_subtitle="10 Crossword Puzzles · Easy Level",
            expected_topic="California Gold Rush",
        )
        self.assertEqual(issues, [], f"Valid cover returned issues: {issues}")

    def test_title_mismatch_fails(self):
        """Title that doesn't match expected → validation fails."""
        cover = {
            "title": "Wrong Title",
            "subtitle": "10 Crossword Puzzles · Easy Level",
        }
        issues = validate_cover_for_export(
            cover,
            expected_title="California Gold Rush Terms",
        )
        self.assertTrue(len(issues) > 0, "Title mismatch should be flagged")
        self.assertTrue(any("title" in i.lower() for i in issues))

    def test_placeholder_text_fails(self):
        """Template placeholder text is detected."""
        cover = {
            "title": "Your Title Here",
            "subtitle": "Your Subtitle Here",
            "author": "Author Name",
        }
        issues = validate_cover_for_export(cover)
        self.assertTrue(len(issues) > 0, "Placeholder text should be flagged")

    def test_professional_digital_guide_fails(self):
        """Forbidden factory phrases are detected."""
        cover = {
            "title": "Professional Digital Guide — California Gold Rush",
            "subtitle": "Something",
        }
        issues = validate_cover_for_export(cover)
        self.assertTrue(len(issues) > 0, "'Professional Digital Guide' should be flagged")
        self.assertTrue(any("professional digital guide" in i.lower() for i in issues))

    def test_digital_product_factory_fails(self):
        """'Digital Product Factory' brand leak is detected."""
        cover = {
            "title": "California Gold Rush by Digital Product Factory",
            "subtitle": "Something",
        }
        issues = validate_cover_for_export(cover)
        self.assertTrue(len(issues) > 0, "'Digital Product Factory' should be flagged")

    def test_dark_navy_color_fails(self):
        """Dark navy / black primary colors are flagged."""
        cover = {
            "title": "Gold Rush",
            "subtitle": "Sub",
            "color_palette": {"primary": "#0f1223"},  # factory-forbidden
        }
        issues = validate_cover_for_export(cover)
        self.assertTrue(len(issues) > 0, "Dark navy #0f1223 should be flagged")
        self.assertTrue(any("dark" in i.lower() or "title band" in i.lower() for i in issues))

    def test_dark_brown_color_fails(self):
        """Dark brown #3d2817 is flagged."""
        cover = {
            "title": "Gold Rush",
            "subtitle": "Sub",
            "color_palette": {"primary": "#3d2817"},
        }
        issues = validate_cover_for_export(cover)
        self.assertTrue(len(issues) > 0, "Dark brown #3d2817 should be flagged")

    def test_pending_placeholder_fails(self):
        """Pending cover-image placeholder flags validation failure."""
        cover = {
            "title": "Gold Rush",
            "preview_html": "cover-image-pending",
        }
        issues = validate_cover_for_export(cover)
        self.assertTrue(len(issues) > 0, "Pending placeholder should be flagged")

    def test_topic_keyword_missing_warns(self):
        """If image prompt doesn't reference the topic, a warning is issued."""
        # Use a topic with 3+ qualifying keywords (5+ chars) so threshold len(missing) > 2 fires
        cover = {
            "title": "African American Inventors and Scientists",
            "subtitle": "Sub",
            "image_prompt": "A red apple on a wooden table",  # unrelated to topic
        }
        issues = validate_cover_for_export(
            cover,
            expected_topic="African American Inventors and Scientists",
        )
        # Should warn about topic mismatch (3+ missing keywords from topic)
        self.assertTrue(
            any("topic" in i.lower() for i in issues),
            f"Topic mismatch should be flagged, got: {issues}",
        )


# ---------------------------------------------------------------------------
# Zero API call tests (local editing / saving / applying)
# ---------------------------------------------------------------------------

class TestZeroApiCalls(unittest.TestCase):
    """Regression: Local editing, saving, and downloading never call OpenAI."""

    @patch("services.product_cover_agent.regenerate_cover_image_for_cover")
    def test_preview_does_not_regenerate(self, mock_regen):
        """preview_cover does not call regenerate_cover_image_for_cover."""
        from services.product_cover_agent import preview_cover

        mock_regen.return_value = ({"title": "Test"}, None)
        project = {
            "data": {
                "product_type": "crossword",
                "title": "Test",
                "cover_design": {"title": "Test", "subtitle": "Sub"},
                "fields": {"theme": "Test"},
            }
        }
        result = preview_cover(project)
        mock_regen.assert_not_called()
        self.assertIsInstance(result, dict)

    @patch("services.cover_agent.regenerate_cover_image")
    def test_save_cover_does_not_call_ai(self, mock_regen):
        """save_cover does not call regenerate_cover_image."""
        from services.product_cover_agent import save_cover

        mock_regen.return_value = ({"title": "Test"}, None)
        existing = {"title": "Gold Rush", "subtitle": "Sub"}
        result = save_cover(existing, {"title": "Gold Rush Updated"})
        mock_regen.assert_not_called()
        self.assertIsInstance(result, dict)


# ---------------------------------------------------------------------------
# Forbidden color patterns
# ---------------------------------------------------------------------------

class TestForbiddenColors(unittest.TestCase):
    """Regression: Factory-forbidden colors are caught by the validator."""

    def test_dark_navy_in_patterns(self):
        """#0f1223 is in _DARK_TITLE_BAND_PATTERNS."""
        self.assertTrue(any("0f1223" in p.lower() for p in _DARK_TITLE_BAND_PATTERNS))

    def test_dark_brown_in_patterns(self):
        """#3d2817 is in _DARK_TITLE_BAND_PATTERNS."""
        self.assertTrue(any("3d2817" in p.lower() for p in _DARK_TITLE_BAND_PATTERNS))

    def test_pure_black_in_patterns(self):
        """#000000 is in _DARK_TITLE_BAND_PATTERNS."""
        self.assertTrue(any("000000" in p.lower() for p in _DARK_TITLE_BAND_PATTERNS))


# ---------------------------------------------------------------------------
# Brief prompt rules
# ---------------------------------------------------------------------------

class TestCoverPromptRules(unittest.TestCase):
    """Regression: AI cover prompts obey the no-text rule."""

    def test_gold_rush_brief_no_text_instruction(self):
        """Gold Rush cover prompt does NOT instruct AI to render text positively."""
        brief = build_crossword_cover_brief(
            fields={"theme": "California Gold Rush"},
            title="California Gold Rush Terms",
            puzzle_count=10,
        )
        prompt_lower = brief["cover_prompt"].lower()
        # These keywords can appear as NEGATIVE instructions ("no lettering") — only fail if bare
        bare_text_keywords = (
            "render the title", "include the title", "show the title",
            "display the title", "readable words in the artwork",
        )
        for kw in bare_text_keywords:
            self.assertNotIn(kw, prompt_lower,
                f"Gold Rush brief should not instruct AI to render text ('{kw}')")
        # "lettering" should only appear in a "no X or lettering" negation, not as a positive instruction
        idx = prompt_lower.find("lettering")
        if idx != -1:
            before = prompt_lower[max(0, idx - 15):idx].strip()
            # Must be preceded by "no" (possibly with "or" in between)
            self.assertTrue(
                "no" in before,
                f"'lettering' must only appear in a negation (e.g. 'no text or lettering'), found: ...{before}lettering",
            )

    def test_gold_rush_brief_background_art_only(self):
        """Gold Rush brief explicitly says background art only."""
        brief = build_crossword_cover_brief(
            fields={"theme": "California Gold Rush"},
            title="California Gold Rush Terms",
            puzzle_count=10,
        )
        self.assertIn("background", brief["cover_prompt"].lower())
        self.assertIn("no text", brief["cover_prompt"].lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
