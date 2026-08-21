"""
Thunder Volt Coloring Book — controlled quality repair regression tests.

Authoritative request:
  "Thunder Volt is a Black superhero. He is stopping two men from robbing a bank
   in New York City."

NO OpenAI / Tavily / image generation calls — all networked image paths mocked.
"""
from __future__ import annotations

import base64
import io
import os
import sys
import unittest
import zipfile
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image
from reportlab.lib.pagesizes import letter

THEME = (
    "Thunder Volt is a Black superhero. "
    "He is stopping two adult men from robbing a bank and getting away in New York City."
)
# Legacy shorter theme still used by some consistency fixtures
THEME_SHORT = (
    "Thunder Volt is a Black superhero. "
    "He is stopping two men from robbing a bank in New York City."
)

SCENE_KEYWORDS = [
    "alarm",
    "skyline",
    "leave",
    "lands",
    "blocks",
    "getaway",
    "car",
    "lightning",
    "shield",
    "pedestrian",
    "bag",
    "second",
    "police",
    "returns",
    "money",
    "finale",
]


def _mock_png(path: str, w: int = 900, h: int = 1200, color=(255, 255, 255)) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    Image.new("RGB", (w, h), color).save(path, "PNG")
    return path


class TestPromptEngineBibleAndScenes(unittest.TestCase):
    def test_character_bible_has_hero_and_two_robbers(self):
        from services.coloring_book.prompt_engine import build_character_bible

        bible = build_character_bible(THEME)
        self.assertEqual(bible.hero_name, "Thunder Volt")
        self.assertIn("Black", bible.hero_identity)
        self.assertIn("New York", bible.location)
        self.assertIn("knit cap", bible.robber_a.lower())
        self.assertIn("taller", bible.robber_a.lower())
        self.assertIn("shorter", bible.robber_b.lower())
        self.assertIn("heavier", bible.robber_b.lower())
        block = bible.as_prompt_block()
        self.assertIn("CHARACTER BIBLE", block)
        self.assertIn("Thunder Volt", block)

    def test_twenty_five_unique_bank_rescue_scenes(self):
        from services.coloring_book.prompt_engine import (
            BANK_RESCUE_SCENES,
            story_scenes_for_theme,
        )

        scenes = story_scenes_for_theme(THEME, 25)
        self.assertEqual(len(scenes), 25)
        self.assertEqual(len(BANK_RESCUE_SCENES), 25)
        topics = [s["topic"] for s in scenes]
        self.assertEqual(len(set(topics)), 25, f"Duplicate topics: {topics}")
        ids = [s["id"] for s in scenes]
        self.assertEqual(len(set(ids)), 25, f"Duplicate scene ids: {ids}")
        joined = " ".join(s["topic"] + " " + s["beat"] for s in scenes).lower()
        for kw in (
            "alarm", "skyline", "lands", "getaway", "lightning", "police",
            "finale", "civilian", "surrender", "get away", "adult",
        ):
            self.assertIn(kw, joined, f"Missing scene keyword {kw!r}")
        # First 12 pages remain a coherent subset for smaller books.
        subset = story_scenes_for_theme(THEME, 12)
        self.assertEqual(len(subset), 12)
        self.assertEqual(len(set(s["topic"] for s in subset)), 12)

    def test_bank_rescue_does_not_pad_alternate_angles(self):
        from services.coloring_book.prompt_engine import story_scenes_for_theme

        with self.assertRaises(ValueError):
            story_scenes_for_theme(THEME, 26)

    def test_cover_copy_from_layout_not_full_theme(self):
        from services.coloring_book.prompt_engine import derive_cover_copy

        copy = derive_cover_copy(THEME)
        self.assertEqual(copy.title.upper(), "THUNDER VOLT")
        self.assertIn("Superhero", copy.subtitle)
        self.assertEqual(copy.overlay_style, "clean_title")
        self.assertNotIn("JUMBO", copy.badge.upper())
        self.assertNotEqual(copy.title.lower(), THEME.lower())


class TestUserThemeReachesPrompts(unittest.TestCase):
    @patch("services.coloring_book.builder.chat_json", side_effect=AssertionError("AI planner must not run for bank-rescue"))
    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid image calls"))
    def test_theme_and_bible_in_every_page_prompt(self, _img, _chat):
        from services.coloring_book.builder import build_coloring_book

        book = build_coloring_book(
            theme=THEME,
            page_count=12,
            age_group="12-adult",
            art_style="Cartoon comic-book",
            product_title="Thunder Volt",
            quality_mode="basic_test",
            creation_mode="theme",
        )
        self.assertTrue(book.pages)
        self.assertEqual(len(book.pages), 12)
        for page in book.pages:
            p = page.line_art_prompt
            self.assertIn(THEME, p, "Full user theme must appear in every page prompt")
            self.assertIn("CHARACTER BIBLE", p)
            self.assertIn("Thunder Volt", p)
            self.assertIn("knit cap", p.lower())
            self.assertIn("American comic-book", p)
            self.assertIn("no guns", p.lower())
            self.assertNotIn("kawaii", p.lower())

    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid image calls"))
    def test_unique_scene_per_page(self, _img):
        from services.coloring_book.builder import build_coloring_book

        book = build_coloring_book(
            theme=THEME,
            page_count=25,
            quality_mode="basic_test",
            creation_mode="theme",
            art_style="Cartoon comic-book",
        )
        topics = [p.topic for p in book.pages]
        self.assertEqual(len(set(topics)), 25)
        prompts = [p.line_art_prompt for p in book.pages]
        # Distinct story beats across the full 25-page sequence
        self.assertTrue(any("alarm" in p.lower() or "skyline" in p.lower() for p in prompts))
        self.assertTrue(any("getaway" in p.lower() for p in prompts))
        self.assertTrue(any("police" in p.lower() for p in prompts))
        self.assertTrue(any("finale" in p.lower() for p in prompts))
        self.assertTrue(any("civilian" in p.lower() for p in prompts))

    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid image calls"))
    def test_cover_prompt_full_color_topic_matched(self, _img):
        from services.coloring_book.builder import build_coloring_book

        book = build_coloring_book(
            theme=THEME,
            page_count=12,
            quality_mode="basic_test",
            creation_mode="theme",
        )
        cover = book.cover_prompt.lower()
        self.assertIn("full-color", cover)
        self.assertIn("thunder volt", cover)
        self.assertIn("new york", cover)
        self.assertIn("character bible", cover)
        self.assertIn("do not paint any words", cover)


class TestPipelineFields(unittest.TestCase):
    def test_theme_not_replaced_by_short_title(self):
        from services.product import _coloring_book_pdf_payload
        from services.coloring_book.pdf_builder import ColoringBookPdfResult

        captured = {}

        def mock_build(req):
            captured["theme"] = req.theme
            captured["title"] = req.product_title
            captured["subtitle"] = req.subtitle
            return ColoringBookPdfResult(errors=["mocked"])

        fields = {
            "coloring_title": "Thunder Volt",
            "theme": THEME,
            "pages": "12",
            "output_format": "Digital Book",
            "quality_mode": "Basic Test Fallback",
            "art_style": "Cartoon comic-book",
            "age_group": "12-adult",
        }
        with patch("services.product.build_coloring_book_pdf", mock_build):
            try:
                _coloring_book_pdf_payload(fields)
            except Exception:
                pass
        self.assertEqual(captured.get("theme"), THEME)
        self.assertNotEqual(captured.get("title"), THEME)
        self.assertIn("Thunder", captured.get("title", ""))


class TestInteriorLayout(unittest.TestCase):
    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid image calls"))
    def test_no_long_prompt_on_interior_pages(self, _img):
        from services.coloring_book.pdf_builder import ColoringBookPdfRequest, build_coloring_book_pdf
        import fitz

        req = ColoringBookPdfRequest(
            product_title="THUNDER VOLT",
            subtitle="New York Bank Rescue",
            theme=THEME,
            page_count=12,
            include_cover=True,
            output_type="book",
            quality_mode="basic_test",
            art_style="Cartoon comic-book",
            package_id="tv_layout_test",
        )
        result = build_coloring_book_pdf(req)
        self.assertFalse(result.errors, result.errors)
        doc = fitz.open(stream=result.pdf_bytes, filetype="pdf")
        # Skip cover (page 0); check interiors
        for i in range(1, min(len(doc), 4)):
            text = doc[i].get_text()
            self.assertNotIn(THEME, text)
            self.assertNotIn("CHARACTER BIBLE", text)
            self.assertNotIn("USER THEME", text)
            # Small page number only
            self.assertTrue(any(ch.isdigit() for ch in text) or text.strip() == "" or len(text.strip()) < 20)

    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid image calls"))
    def test_interior_image_area_and_aspect(self, _img):
        from services.coloring_book.renderer import _coloring_image_box

        page_w, page_h = letter
        x, y, w, h = _coloring_image_box(page_w, page_h, footer_h=16)
        page_area = page_w * page_h
        box_area = w * h
        self.assertGreaterEqual(box_area / page_area, 0.80, f"Coloring area {box_area/page_area:.2%} < 80%")
        self.assertAlmostEqual(w / 72.0, 7.5, delta=0.3)
        self.assertAlmostEqual(h / 72.0, 10.0, delta=0.5)
        # Portrait box
        self.assertGreater(h, w)

    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid image calls"))
    def test_cover_title_from_renderer_layout(self, _img):
        from services.coloring_book.pdf_builder import ColoringBookPdfRequest, build_coloring_book_pdf
        import fitz

        req = ColoringBookPdfRequest(
            product_title="THUNDER VOLT",
            subtitle="New York Bank Rescue",
            theme=THEME,
            page_count=4,
            include_cover=True,
            output_type="book",
            quality_mode="basic_test",
            package_id="tv_cover_title_test",
        )
        result = build_coloring_book_pdf(req)
        self.assertFalse(result.errors, result.errors)
        self.assertTrue(result.cover_design)
        self.assertEqual(result.cover_design.get("title", "").upper(), "THUNDER VOLT")
        doc = fitz.open(stream=result.pdf_bytes, filetype="pdf")
        cover_text = doc[0].get_text()
        self.assertIn("THUNDER VOLT", cover_text.upper())
        self.assertIn("A Superhero Coloring Adventure", cover_text)
        self.assertNotIn("JUMBO", cover_text.upper())
        self.assertNotIn("COLORING PAGES", cover_text.upper())


class TestSaveExportPreserve(unittest.TestCase):
    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid image calls"))
    def test_payload_preserves_pages_and_cover(self, _img):
        from services.product import _coloring_book_pdf_payload

        fields = {
            "coloring_title": "Thunder Volt",
            "theme": THEME,
            "pages": "12",
            "output_format": "Digital Book",
            "quality_mode": "Basic Test Fallback",
            "art_style": "Cartoon comic-book",
            "age_group": "12-adult",
            "include_captions": "No",
        }
        payload = _coloring_book_pdf_payload(fields, package_id="tv_save_export_test")
        self.assertEqual(payload["product_type"], "coloring_book")
        self.assertTrue(payload.get("is_pdf"))
        self.assertTrue(payload.get("pdf_bytes"))
        self.assertTrue(payload.get("pages"))
        self.assertEqual(len(payload["pages"]), 12)
        self.assertTrue(payload.get("cover_design"))
        self.assertTrue(payload.get("cover_prompt"))
        # Not an ebook fallback
        self.assertNotIn("ebook.html", str(payload.get("filename", "")).lower())

    @patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid image calls"))
    def test_zip_pdf_matches_direct_and_not_ebook(self, _img):
        from services.packaging import build_product_export
        from services.product import _coloring_book_pdf_payload

        fields = {
            "coloring_title": "Thunder Volt",
            "theme": THEME,
            "pages": "4",
            "output_format": "Digital Book",
            "quality_mode": "Basic Test Fallback",
            "art_style": "Cartoon comic-book",
            "age_group": "12-adult",
        }
        payload = _coloring_book_pdf_payload(fields, package_id="tv_zip_match_test")
        project = {
            "id": 999001,
            "name": "Thunder Volt",
            "data": payload,
        }
        exports = build_product_export(project)
        # packaging nests under exports.files
        bundle = exports.get("exports") or exports
        files = bundle.get("files") or {}
        self.assertTrue(bundle.get("pdf_available") or files.get("pdf"), exports)
        self.assertIn("pdf", files)
        export_pkg = exports.get("package_id") or payload["package_id"]
        from services.ebook_package import EXPORTS_DIR

        zip_path = os.path.join(EXPORTS_DIR, export_pkg, "package.zip")
        self.assertTrue(os.path.isfile(zip_path), f"Missing ZIP at {zip_path}")
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            pdf_names = [n for n in names if n.lower().endswith(".pdf")]
            self.assertTrue(pdf_names, names)
            # Read ZIP PDF and compare to direct payload PDF
            zip_pdf = zf.read(pdf_names[0])
            direct_pdf = base64.b64decode(payload["pdf_bytes"])
            self.assertTrue(zip_pdf.startswith(b"%PDF"))
            self.assertTrue(direct_pdf.startswith(b"%PDF"))
            # Same page count (cover edits may rewrite bytes; length/page parity is the contract)
            self.assertEqual(zip_pdf.count(b"/Type /Page"), direct_pdf.count(b"/Type /Page"))

    def test_apply_cover_preserves_pages(self):
        from services.product import apply_coloring_book_cover_to_saved_data
        from services.coloring_book.pdf_builder import ColoringBookPdfRequest, build_coloring_book_pdf

        with patch("services.coloring_book.builder.generate_visual_image", side_effect=AssertionError("No paid")):
            result = build_coloring_book_pdf(
                ColoringBookPdfRequest(
                    product_title="THUNDER VOLT",
                    subtitle="New York Bank Rescue",
                    theme=THEME,
                    page_count=3,
                    include_cover=True,
                    output_type="book",
                    quality_mode="basic_test",
                    package_id="tv_apply_cover_test",
                )
            )
        data = {
            "product_type": "coloring_book",
            "is_book": True,
            "pdf_has_cover_page": True,
            "pdf_bytes": base64.b64encode(result.pdf_bytes).decode("ascii"),
            "package_id": "tv_apply_cover_test",
            "pages": result.pages,
            "fields": {"output_format": "Digital Book", "theme": THEME},
            "cover_design": result.cover_design,
        }
        new_cover = dict(result.cover_design or {})
        new_cover["title"] = "THUNDER VOLT"
        new_cover["subtitle"] = "New York Bank Rescue"
        updated = apply_coloring_book_cover_to_saved_data(data, new_cover)
        self.assertEqual(len(updated.get("pages") or []), 3)
        self.assertTrue(updated.get("pdf_bytes"))
        self.assertTrue(updated.get("pdf_has_cover_page"))


class TestZeroPaidApiCalls(unittest.TestCase):
    def test_basic_test_mode_never_calls_image_api(self):
        calls = {"n": 0}

        def boom(*a, **k):
            calls["n"] += 1
            raise AssertionError("Paid image API called")

        with patch("services.coloring_book.builder.generate_visual_image", side_effect=boom):
            with patch("services.coloring_book.builder.chat_json", side_effect=AssertionError("chat")):
                from services.coloring_book.pdf_builder import ColoringBookPdfRequest, build_coloring_book_pdf

                result = build_coloring_book_pdf(
                    ColoringBookPdfRequest(
                        product_title="THUNDER VOLT",
                        theme=THEME,
                        page_count=12,
                        include_cover=True,
                        output_type="book",
                        quality_mode="basic_test",
                        package_id="tv_zero_api_test",
                    )
                )
        self.assertEqual(calls["n"], 0)
        self.assertFalse(result.errors, result.errors)


class TestCoverEditorWiring(unittest.TestCase):
    def test_coloring_book_cover_adapter(self):
        from services.product_cover_agent import build_cover_payload_from_project

        project = {
            "name": "Thunder Volt",
            "data": {
                "product_type": "coloring_book",
                "title": "THUNDER VOLT",
                "package_id": "tv_cover_adapt",
                "fields": {"theme": THEME, "coloring_title": "Thunder Volt"},
                "cover_design": {"title": "THUNDER VOLT", "subtitle": "New York Bank Rescue"},
            },
        }
        payload = build_cover_payload_from_project(project)
        self.assertEqual(payload.engine_product_type, "coloring_book")
        self.assertIn("Thunder Volt", payload.image_prompt)
        self.assertIn("full-color", payload.image_prompt.lower())
        self.assertTrue(payload.content_md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
