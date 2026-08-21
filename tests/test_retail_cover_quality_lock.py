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
        # Thunder Volt uses Factory typography overlay — not cluttered JUMBO chrome.
        self.assertEqual(copy.overlay_style, "clean_title")
        self.assertNotIn("JUMBO", copy.badge.upper())
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
            "clean_title",
        )
        self.assertNotIn("JUMBO", ((result.cover_design or {}).get("badge") or "").upper())

        doc = fitz.open(stream=result.pdf_bytes, filetype="pdf")
        text = (doc[0].get_text("text") or "").upper()
        doc.close()
        self.assertIn("THUNDER VOLT", text)
        self.assertIn("A SUPERHERO COLORING ADVENTURE", text)
        self.assertNotIn("NEW YORK BANK RESCUE", text)
        self.assertNotIn("JUMBO", text)
        self.assertNotIn("COLORING PAGES", text)
        self.assertNotIn("PRINT & SHARE", text)

    def test_stale_jumbo_cover_design_cannot_reach_final_renderer(self):
        """Regression: Cover Editor / old Stage A payloads carried jumbo chrome.

        derive_cover_copy already returns clean_title, but the final renderer used to
        honor a stale cover_design.overlay_style=retail_jumbo_banner. Prove the
        normalizer + draw path force clean_title onto the composed page.
        """
        import io

        import fitz
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        from services.coloring_book.pdf_cover import render_cover_page_pdf_bytes
        from services.coloring_book.prompt_engine import (
            derive_cover_copy,
            normalize_coloring_cover_design,
        )
        from services.coloring_book.renderer import draw_cover_page_on_canvas

        copy = derive_cover_copy(THEME, product_title="Thunder Volt")
        self.assertEqual(copy.overlay_style, "clean_title")

        stale = {
            "title": "THUNDER VOLT",
            "subtitle": "New York Bank Rescue",
            "badge": "Jumbo Coloring & Activity Book",
            "overlay_style": "retail_jumbo_banner",
            "layout": "full_bleed_retail_jumbo",
            "theme": THEME,
        }
        fixed = normalize_coloring_cover_design(stale, theme=THEME)
        self.assertEqual(fixed["overlay_style"], "clean_title")
        self.assertEqual(fixed["subtitle"], "A Superhero Coloring Adventure")
        self.assertNotIn("JUMBO", (fixed.get("badge") or "").upper())

        buf = io.BytesIO()
        pdf = canvas.Canvas(buf, pagesize=letter)
        draw_cover_page_on_canvas(pdf, cover_design=stale)
        pdf.showPage()
        pdf.save()
        doc = fitz.open(stream=buf.getvalue(), filetype="pdf")
        text = (doc[0].get_text("text") or "").upper()
        doc.close()
        self.assertIn("THUNDER VOLT", text)
        self.assertIn("A SUPERHERO COLORING ADVENTURE", text)
        self.assertNotIn("JUMBO", text)
        self.assertNotIn("COLORING PAGES", text)
        self.assertNotIn("PRINT & SHARE", text)
        self.assertNotIn("NEW YORK BANK RESCUE", text)

        # Apply/Cover Editor path uses pdf_cover.merge helper — same guarantee.
        cover_bytes = render_cover_page_pdf_bytes(stale)
        doc = fitz.open(stream=cover_bytes, filetype="pdf")
        text2 = (doc[0].get_text("text") or "").upper()
        # Subtitle must be ~2× the old 13pt size (≥20pt) so it reads at thumbnail.
        sub_sizes = []
        for block in doc[0].get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if "SUPERHERO COLORING ADVENTURE" in (span.get("text") or "").upper():
                        sub_sizes.append(float(span.get("size") or 0))
        doc.close()
        self.assertIn("A SUPERHERO COLORING ADVENTURE", text2)
        self.assertNotIn("JUMBO", text2)
        self.assertNotIn("COLORING PAGES", text2)
        self.assertTrue(sub_sizes, "subtitle span missing from clean_title overlay")
        self.assertGreaterEqual(max(sub_sizes), 20.0)


class TestCoverBriefAdapter(unittest.TestCase):
    def test_coloring_book_cover_brief_retail(self):
        from services.product_cover_agent import build_coloring_book_cover_brief

        brief = build_coloring_book_cover_brief(
            {"theme": THEME, "coloring_title": "Thunder Volt"},
            title="Thunder Volt",
            theme=THEME,
        )
        self.assertEqual(brief["overlay_style"], "clean_title")
        self.assertNotIn("JUMBO", (brief.get("badge") or "").upper())
        from services.coloring_book.prompt_engine import validate_cover_prompt_lock

        self.assertEqual(validate_cover_prompt_lock(brief["cover_prompt"], THEME), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
