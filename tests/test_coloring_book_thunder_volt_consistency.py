"""Thunder Volt consistency repair — prompt locks, metadata, staging (no paid API)."""
from __future__ import annotations

import base64
import os
import sys
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import fitz

THEME = (
    "Thunder Volt is a Black superhero. "
    "He is stopping two men from robbing a bank in New York City."
)


class TestLockedCharacterBible(unittest.TestCase):
    def test_same_character_lock_in_all_twelve_prompts(self):
        from services.coloring_book.prompt_engine import (
            THUNDER_VOLT_CHARACTER_LOCK,
            ROBBER_ONE_LOCK,
            ROBBER_TWO_LOCK,
            build_local_story_pages,
        )

        pages, cover, bible, _ = build_local_story_pages(
            THEME, 12, art_style="Cartoon comic-book", main_character="Thunder Volt"
        )
        self.assertEqual(len(pages), 12)
        for p in pages:
            prompt = p["line_art_prompt"]
            self.assertIn(THUNDER_VOLT_CHARACTER_LOCK, prompt)
            self.assertIn(ROBBER_ONE_LOCK, prompt)
            self.assertIn(ROBBER_TWO_LOCK, prompt)
            self.assertIn(THEME, prompt)
            self.assertIn("large open coloring", prompt.lower())
            self.assertIn("simplified", prompt.lower())
            self.assertIn("third robber", prompt.lower())
            self.assertTrue(
                "exactly two robbers" in prompt.lower()
                or "exactly robber one and robber two" in prompt.lower()
            )
            self.assertIn("do not redefine", prompt.lower())
        # Identical lock text across pages
        locks = [p["line_art_prompt"].split("UNIQUE SCENE ACTION")[0] for p in pages]
        self.assertEqual(len(set(locks)), 1, "Character lock prefix must be identical on every page")
        self.assertIn(THUNDER_VOLT_CHARACTER_LOCK, cover)
        self.assertIn(ROBBER_ONE_LOCK, cover)
        self.assertIn(ROBBER_TWO_LOCK, cover)

    def test_scene_cannot_override_lock_via_finalize(self):
        from services.coloring_book.prompt_engine import (
            THUNDER_VOLT_CHARACTER_LOCK,
            build_character_bible,
            finalize_interior_prompt,
        )

        bible = build_character_bible(THEME)
        bad = (
            "Draw Thunder Volt as a child in armor with three robbers and a different costume."
        )
        fixed = finalize_interior_prompt(bad, bible, "Cartoon comic-book")
        self.assertIn(THUNDER_VOLT_CHARACTER_LOCK, fixed)
        self.assertIn("third robber", fixed.lower())
        self.assertIn(THEME.lower(), fixed.lower())

    def test_validate_locked_prompts_clean(self):
        from services.coloring_book.prompt_engine import (
            build_local_story_pages,
            validate_locked_prompts,
        )

        pages, *_ = build_local_story_pages(THEME, 12, art_style="Cartoon comic-book")
        issues = validate_locked_prompts(pages, THEME)
        self.assertEqual(issues, [])


class TestApprovalGateNoPaidFullBook(unittest.TestCase):
    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid"))
    def test_full_ai_book_requires_approval(self, _img):
        from services.coloring_book.builder import build_coloring_book

        book = build_coloring_book(
            theme=THEME,
            page_count=12,
            quality_mode="ai_image_coloring_page",
            generation_stage="full",
            character_approved=False,
            sample_approved=False,
            art_style="Cartoon comic-book",
        )
        self.assertTrue(book.errors)
        self.assertIn("Approval required", book.errors[0])

    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid"))
    def test_cover_preview_skips_interior_images(self, _img):
        from services.coloring_book.builder import build_coloring_book

        book = build_coloring_book(
            theme=THEME,
            page_count=12,
            quality_mode="ai_image_coloring_page",
            generation_stage="cover_preview",
            art_style="Cartoon comic-book",
        )
        self.assertFalse(book.errors)
        self.assertEqual(book.generation_stage, "cover_preview")
        self.assertTrue(all(not p.image_path for p in book.pages))


class TestPdfMetadata(unittest.TestCase):
    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid"))
    def test_metadata_title_author_subject_keywords(self, _img):
        from services.coloring_book.pdf_builder import ColoringBookPdfRequest, build_coloring_book_pdf

        result = build_coloring_book_pdf(
            ColoringBookPdfRequest(
                product_title="THUNDER VOLT",
                subtitle="New York Bank Rescue",
                theme=THEME,
                page_count=12,
                include_cover=True,
                output_type="book",
                quality_mode="basic_test",
                package_id="tv_meta_test",
                generation_stage="full",
            )
        )
        self.assertFalse(result.errors, result.errors)
        doc = fitz.open(stream=result.pdf_bytes, filetype="pdf")
        meta = doc.metadata or {}
        self.assertEqual(meta.get("title"), "Thunder Volt Coloring Book")
        self.assertEqual(meta.get("author"), "Digital Product Factory")
        self.assertIn("two bank robbers", (meta.get("subject") or "").lower())
        keywords = (meta.get("keywords") or "").lower()
        self.assertIn("thunder volt", keywords)
        self.assertIn("new york", keywords)
        self.assertEqual(doc.page_count, 13)  # cover + 12
        doc.close()


class TestSaveExportPreserveAndNoEbook(unittest.TestCase):
    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid"))
    def test_zip_matches_pdf_and_not_ebook(self, _img):
        from services.packaging import build_product_export
        from services.product import _coloring_book_pdf_payload
        from services.ebook_package import EXPORTS_DIR

        fields = {
            "coloring_title": "Thunder Volt",
            "theme": THEME,
            "pages": "4",
            "output_format": "Digital Book",
            "quality_mode": "Basic Test Fallback",
            "art_style": "Cartoon comic-book",
            "generation_stage": "full",
        }
        payload = _coloring_book_pdf_payload(fields, package_id="tv_consistency_zip")
        self.assertTrue(payload.get("is_pdf"))
        self.assertNotIn("ebook.html", str(payload.get("filename", "")).lower())
        project = {"id": 999002, "name": "Thunder Volt", "data": payload}
        exports = build_product_export(project)
        bundle = exports.get("exports") or exports
        files = bundle.get("files") or {}
        self.assertIn("pdf", files)
        zip_path = os.path.join(EXPORTS_DIR, exports.get("package_id") or payload["package_id"], "package.zip")
        self.assertTrue(os.path.isfile(zip_path))
        with zipfile.ZipFile(zip_path, "r") as zf:
            pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
            self.assertTrue(pdf_names)
            zip_pdf = zf.read(pdf_names[0])
            direct = base64.b64decode(payload["pdf_bytes"])
            self.assertEqual(zip_pdf.count(b"/Type /Page"), direct.count(b"/Type /Page"))


class TestZeroPaidApi(unittest.TestCase):
    def test_no_image_api_in_automated_tests(self):
        calls = {"n": 0}

        def boom(*a, **k):
            calls["n"] += 1
            raise AssertionError("paid")

        with patch("services.coloring_book.builder.generate_visual_image", side_effect=boom):
            from services.coloring_book.pdf_builder import ColoringBookPdfRequest, build_coloring_book_pdf

            result = build_coloring_book_pdf(
                ColoringBookPdfRequest(
                    product_title="THUNDER VOLT",
                    theme=THEME,
                    page_count=12,
                    quality_mode="basic_test",
                    generation_stage="full",
                    package_id="tv_zero_paid_consistency",
                )
            )
        self.assertEqual(calls["n"], 0)
        self.assertFalse(result.errors)


if __name__ == "__main__":
    unittest.main(verbosity=2)
