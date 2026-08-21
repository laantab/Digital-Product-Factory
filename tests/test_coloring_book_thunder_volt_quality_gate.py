"""Thunder Volt Coloring Book — quality gates for the 25-page acceptance product.

Zero paid APIs. Self-contained fixtures only.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import sys
import unittest
import zipfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw

THEME = (
    "Thunder Volt is a Black superhero. "
    "He is stopping two adult men from robbing a bank and getting away in New York City."
)


def _line_art_ok(path: str, w: int = 900, h: int = 1200) -> str:
    """Large subject, open white space, pure B&W — should PASS deterministic QA."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Large central figure (~55% bbox)
    draw.ellipse((180, 200, 720, 1000), outline=(0, 0, 0), width=6)
    draw.rectangle((320, 420, 580, 900), outline=(0, 0, 0), width=5)
    img.save(path, "PNG")
    return path


def _line_art_tiny(path: str, w: int = 900, h: int = 1200) -> str:
    """Tiny floating subject — should FAIL subject-size QA."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((420, 560, 480, 640), outline=(0, 0, 0), width=3)
    img.save(path, "PNG")
    return path


def _line_art_gray(path: str, w: int = 900, h: int = 1200) -> str:
    """Gray shading — should FAIL B&W QA."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse((150, 150, 750, 1050), fill=(160, 160, 160), outline=(0, 0, 0), width=4)
    img.save(path, "PNG")
    return path


class TestThunderVoltThemeAndBible(unittest.TestCase):
    def test_exact_theme_in_bible_and_every_scene_prompt(self):
        from services.coloring_book.prompt_engine import (
            build_character_bible,
            build_interior_page_prompt,
            story_scenes_for_theme,
        )

        bible = build_character_bible(THEME)
        self.assertIn("Black", bible.hero_identity)
        self.assertIn("deep-brown skin", bible.hero_description.lower())
        self.assertIn(THEME, bible.story_summary)
        self.assertIn("adult", bible.story_summary.lower())
        self.assertIn("getting away", bible.story_summary.lower())
        self.assertIn("adult man", bible.robber_a.lower())
        self.assertIn("adult man", bible.robber_b.lower())

        scenes = story_scenes_for_theme(THEME, 25, bible=bible)
        self.assertEqual(len(scenes), 25)
        prompts = [
            build_interior_page_prompt(
                bible=bible, scene=s, page_number=i + 1, total_pages=25
            )
            for i, s in enumerate(scenes)
        ]
        self.assertEqual(len(set(prompts)), 25)
        for p in prompts:
            self.assertIn(THEME, p)
            self.assertIn("CHARACTER BIBLE", p)
            self.assertIn("Thunder Volt", p)
            self.assertIn("Black", p)

    def test_cover_prompt_differs_from_interior_and_forbids_ai_lettering(self):
        from services.coloring_book.prompt_engine import (
            build_character_bible,
            build_cover_image_prompt,
            build_interior_page_prompt,
            derive_cover_copy,
            story_scenes_for_theme,
        )

        bible = build_character_bible(THEME)
        copy = derive_cover_copy(THEME, product_title="Thunder Volt")
        cover_p = build_cover_image_prompt(bible=bible, cover=copy)
        scene = story_scenes_for_theme(THEME, 1, bible=bible)[0]
        interior_p = build_interior_page_prompt(
            bible=bible, scene=scene, page_number=1, total_pages=25
        )
        self.assertNotEqual(cover_p, interior_p)
        low = cover_p.lower()
        self.assertTrue(
            "no text" in low or "no lettering" in low or "never paint the title" in low
        )
        self.assertEqual(copy.title.upper(), "THUNDER VOLT")


class TestApprovalGate(unittest.TestCase):
    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("paid"))
    @patch("services.coloring_book.builder.chat_json", side_effect=AssertionError("paid"))
    def test_full_generation_blocked_without_approvals(self, *_mocks):
        from services.coloring_book.builder import build_coloring_book

        book = build_coloring_book(
            theme=THEME,
            page_count=25,
            age_group="Children ages 8–12",
            art_style="Cartoon comic-book",
            product_title="Thunder Volt",
            quality_mode="ai_image_coloring_page",
            generation_stage="full",
            character_approved=False,
            sample_approved=False,
        )
        self.assertTrue(book.errors)
        self.assertIn("Approval required", book.errors[0])


class TestDeterministicImageQA(unittest.TestCase):
    def test_small_subject_fails(self):
        from services.coloring_book.quality_agent import _run_deterministic_image_checks
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = _line_art_tiny(os.path.join(td, "tiny.png"))
            with open(path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
            issues = _run_deterministic_image_checks(b64)
            self.assertTrue(any("too small" in i.lower() for i in issues), issues)

    def test_gray_fill_fails(self):
        from services.coloring_book.quality_agent import _run_deterministic_image_checks
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = _line_art_gray(os.path.join(td, "gray.png"))
            with open(path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
            issues = _run_deterministic_image_checks(b64)
            self.assertTrue(any("non-black/white" in i.lower() or "gray" in i.lower() for i in issues), issues)

    def test_open_line_art_passes(self):
        from services.coloring_book.quality_agent import _run_deterministic_image_checks
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            path = _line_art_ok(os.path.join(td, "ok.png"))
            with open(path, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
            issues = _run_deterministic_image_checks(b64)
            self.assertEqual(issues, [], issues)


class TestExportGates(unittest.TestCase):
    def test_qa_blocked_project_has_no_pdf_bytes_on_full_ai_fail(self):
        from services.coloring_book.pdf_builder import (
            ColoringBookPdfRequest,
            build_coloring_book_pdf,
        )

        with patch(
            "services.coloring_book.builder.generate_visual_image",
            return_value=False,
        ), patch(
            "services.coloring_book.builder.chat_json",
            side_effect=AssertionError("no planner"),
        ):
            result = build_coloring_book_pdf(
                ColoringBookPdfRequest(
                    product_title="Thunder Volt",
                    theme=THEME,
                    page_count=25,
                    include_cover=True,
                    output_type="book",
                    quality_mode="ai_image_coloring_page",
                    package_id="tv_qa_block_test",
                    generation_stage="full",
                    character_approved=True,
                    sample_approved=True,
                )
            )
        self.assertTrue(result.errors)
        self.assertFalse(result.pdf_bytes)

    def test_export_does_not_regenerate_when_pdf_missing(self):
        from services.packaging import build_product_export

        project = {
            "id": 910001,
            "name": "Thunder Volt",
            "data": {
                "product_type": "coloring_book",
                "is_pdf": True,
                "is_book": True,
                "title": "Thunder Volt",
                "pdf_bytes": "",
                "package_id": "missing_pdf_pkg",
                "fields": {
                    "pages": "25",
                    "output_format": "Digital Book",
                    "theme": THEME,
                    "quality_mode": "AI Image Coloring Page",
                },
            },
        }
        with self.assertRaises(ValueError) as ctx:
            build_product_export(project)
        self.assertIn("will not call image generation", str(ctx.exception).lower())

    def test_export_blocks_when_quality_blocked_export_flag_set(self):
        from services.packaging import build_product_export
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        for _ in range(26):
            c.showPage()
        c.save()
        pdf = buf.getvalue()
        project = {
            "id": 910002,
            "name": "Thunder Volt",
            "data": {
                "product_type": "coloring_book",
                "is_pdf": True,
                "is_book": True,
                "title": "Thunder Volt",
                "pdf_bytes": base64.b64encode(pdf).decode("ascii"),
                "pdf_has_cover_page": True,
                "pages": [{"page_number": i} for i in range(1, 26)],
                "quality_result": {"blocked_export": True, "all_passed": False},
                "fields": {
                    "pages": "25",
                    "output_format": "Digital Book",
                    "theme": THEME,
                    "quality_mode": "AI Image Coloring Page",
                },
            },
        }
        with self.assertRaises(ValueError) as ctx:
            build_product_export(project)
        self.assertIn("QA blocked", str(ctx.exception))


class TestCoverEditorAndPdfZipParity(unittest.TestCase):
    def test_cover_editor_entry_and_apply_preserve_interiors(self):
        app_js = os.path.join(os.path.dirname(__file__), "..", "static", "js", "app.js")
        with open(app_js, encoding="utf-8") as fh:
            js = fh.read()
        self.assertIn('coverBtn.textContent = "Edit Cover"', js)
        self.assertIn("openCoverEditor", js)
        self.assertIn("coloring_book", js)

        import base64 as b64
        from pypdf import PdfReader
        from services.product import apply_coloring_book_cover_to_saved_data
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(72, 720, "COVER")
        c.showPage()
        for i in range(1, 26):
            c.drawString(72, 720, f"INTERIOR {i}")
            c.showPage()
        c.save()
        before = buf.getvalue()
        data = {
            "product_type": "coloring_book",
            "is_book": True,
            "pdf_bytes": b64.b64encode(before).decode("ascii"),
            "pdf_has_cover_page": True,
            "package_id": "tv_cover_apply_test",
            "pages": [{"page_number": i} for i in range(1, 26)],
            "fields": {"output_format": "Digital Book", "theme": THEME},
            "cover_design": {"title": "THUNDER VOLT", "subtitle": "A Superhero Coloring Adventure"},
        }
        out = apply_coloring_book_cover_to_saved_data(
            data,
            {
                "title": "THUNDER VOLT",
                "subtitle": "A Superhero Coloring Adventure",
                "overlay_style": "clean_title",
                "package_id": "tv_cover_apply_test",
            },
        )
        after = b64.b64decode(out["pdf_bytes"])
        r1 = PdfReader(io.BytesIO(before))
        r2 = PdfReader(io.BytesIO(after))
        self.assertEqual(len(r1.pages), 26)
        self.assertEqual(len(r2.pages), 26)
        t1 = "".join((r1.pages[i].extract_text() or "") for i in range(1, 26))
        t2 = "".join((r2.pages[i].extract_text() or "") for i in range(1, 26))
        self.assertEqual(t1, t2)

    def test_pdf_zip_byte_identical_for_stored_book(self):
        from services.packaging import build_product_export
        from reportlab.pdfgen import canvas

        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        for _ in range(26):
            c.showPage()
        c.save()
        pdf = buf.getvalue()
        project = {
            "id": 910003,
            "name": "Thunder Volt",
            "data": {
                "product_type": "coloring_book",
                "is_pdf": True,
                "is_book": True,
                "title": "Thunder Volt",
                "filename": "thunder_volt.pdf",
                "pdf_bytes": base64.b64encode(pdf).decode("ascii"),
                "pdf_has_cover_page": True,
                "pages": [{"page_number": i} for i in range(1, 26)],
                "fields": {
                    "pages": "25",
                    "output_format": "Digital Book",
                    "theme": THEME,
                    "quality_mode": "Basic Test Fallback",
                },
            },
        }
        result = build_product_export(project)
        files = result["exports"]["files"]
        from services.ebook_package import EXPORTS_DIR

        pkg = result["package_id"]
        pdf_path = os.path.join(EXPORTS_DIR, pkg, "thunder_volt.pdf")
        zip_path = os.path.join(EXPORTS_DIR, pkg, "package.zip")
        with open(pdf_path, "rb") as fh:
            direct = fh.read()
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
            zipped = zf.read(names[0])
        self.assertEqual(hashlib.sha256(direct).hexdigest(), hashlib.sha256(zipped).hexdigest())
        self.assertEqual(hashlib.sha256(direct).hexdigest(), hashlib.sha256(pdf).hexdigest())


class TestContractStrictPages(unittest.TestCase):
    def test_ai_digital_book_expects_cover_plus_interiors(self):
        from services.quality.user_instruction_controller import build_coloring_book_contract

        contract = build_coloring_book_contract(
            {
                "coloring_title": "Thunder Volt",
                "theme": THEME,
                "output_format": "Digital Book",
                "pages": "25",
                "quality_mode": "AI Image Coloring Page",
            }
        )
        self.assertEqual(contract.title, "Thunder Volt")
        self.assertNotEqual(contract.title, THEME)
        self.assertEqual(contract.expected_pdf_pages, 26)
        self.assertTrue(contract.strict_page_count)


if __name__ == "__main__":
    unittest.main(verbosity=2)
