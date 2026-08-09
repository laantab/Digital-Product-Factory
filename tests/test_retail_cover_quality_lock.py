"""Lock mass-market retail cover quality for future coloring-book covers (no paid API)."""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

THEME = (
    "Thunder Volt is a Black superhero. "
    "He is stopping two men from robbing a bank in New York City."
)


class TestRetailCoverPromptLock(unittest.TestCase):
    def test_cover_prompt_includes_retail_quality_lock(self):
        from services.coloring_book.prompt_engine import (
            RETAIL_COVER_QUALITY_LOCK,
            PRODUCT_STYLE_COVER,
            THUNDER_VOLT_CHARACTER_LOCK,
            build_character_bible,
            build_cover_image_prompt,
            derive_cover_copy,
            validate_cover_prompt_lock,
        )

        bible = build_character_bible(THEME, main_character="Thunder Volt")
        copy = derive_cover_copy(THEME, product_title="Thunder Volt")
        prompt = build_cover_image_prompt(bible=bible, cover=copy)

        self.assertIn(RETAIL_COVER_QUALITY_LOCK, prompt)
        self.assertIn(PRODUCT_STYLE_COVER, prompt)
        self.assertIn(THUNDER_VOLT_CHARACTER_LOCK, prompt)
        self.assertIn("Jumbo Coloring & Activity Book", copy.badge)
        self.assertEqual(copy.overlay_style, "retail_jumbo_banner")
        self.assertEqual(validate_cover_prompt_lock(prompt, THEME), [])

        low = prompt.lower()
        self.assertIn("night", low)
        self.assertIn("dynamic", low)
        self.assertIn("yellow cape", low)
        self.assertIn("neon", low)
        self.assertIn("bank sign", low)
        self.assertIn("street sign", low)
        self.assertIn("marvel", low)
        self.assertNotIn("lower third kept relatively clear", low)

    def test_character_lock_yellow_cape_on_interiors(self):
        from services.coloring_book.prompt_engine import (
            build_local_story_pages,
            validate_locked_prompts,
        )

        pages, cover, *_ = build_local_story_pages(
            THEME, 12, art_style="Cartoon comic-book", main_character="Thunder Volt"
        )
        self.assertEqual(validate_locked_prompts(pages, THEME), [])
        self.assertIn("yellow cape", pages[0]["line_art_prompt"].lower())
        self.assertIn("yellow cape", cover.lower())


class TestRetailCoverOverlay(unittest.TestCase):
    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid"))
    def test_pdf_cover_uses_retail_banner_text(self, _img):
        import fitz
        from services.coloring_book.pdf_builder import (
            ColoringBookPdfRequest,
            build_coloring_book_pdf,
        )

        result = build_coloring_book_pdf(
            ColoringBookPdfRequest(
                product_title="THUNDER VOLT",
                subtitle="New York Bank Rescue",
                theme=THEME,
                page_count=2,
                include_cover=True,
                output_type="book",
                quality_mode="basic_test",
                package_id="tv_retail_lock_test",
                generation_stage="full",
            )
        )
        self.assertFalse(result.errors, result.errors)
        self.assertEqual(
            (result.cover_design or {}).get("overlay_style"),
            "retail_jumbo_banner",
        )
        self.assertEqual(
            (result.cover_design or {}).get("layout"),
            "full_bleed_retail_jumbo",
        )
        self.assertIn("Jumbo", (result.cover_design or {}).get("badge", ""))

        doc = fitz.open(stream=result.pdf_bytes, filetype="pdf")
        text = (doc[0].get_text("text") or "").upper()
        doc.close()
        self.assertIn("THUNDER VOLT", text)
        self.assertIn("JUMBO", text)
        self.assertIn("COLORING", text)
        self.assertIn("COLORING PAGES", text)


class TestCoverBriefAdapter(unittest.TestCase):
    def test_coloring_book_cover_brief_retail(self):
        from services.product_cover_agent import build_coloring_book_cover_brief

        brief = build_coloring_book_cover_brief(
            {"theme": THEME, "coloring_title": "Thunder Volt"},
            title="Thunder Volt",
            theme=THEME,
        )
        self.assertEqual(brief["overlay_style"], "retail_jumbo_banner")
        self.assertEqual(brief["style_preference"], "retail_jumbo")
        self.assertIn("Jumbo", brief["badge"])
        from services.coloring_book.prompt_engine import validate_cover_prompt_lock

        self.assertEqual(validate_cover_prompt_lock(brief["cover_prompt"], THEME), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
