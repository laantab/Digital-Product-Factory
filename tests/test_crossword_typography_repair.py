"""Regression tests for crossword visual/typography repair.

These lock the shared renderer contracts BEFORE production fixes land.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import unittest
import zipfile

from pypdf import PdfReader

from services.crossword.book import build_crossword_puzzles
from services.crossword.direct_pdf_renderer import (
    CLUE_FONT_MIN_PT,
    HEADING_FONT_MIN_PT,
    INSTRUCTION_FONT_MIN_PT,
    build_crossword_book_pdf_bytes,
)
from services.crossword.pdf_fonts import CROSSWORD_FONT, CROSSWORD_FONT_BOLD, ensure_crossword_fonts


_BAD_SPACING = (
    r"C\s+a\s+l",
    r"C\s+rossword",
    r"Answ\s+er",
    r"C\s+alifo",
    r"G\s+old\s+R",
)
_FORBIDDEN = {
    "KITCHEN", "PILLOW", "CURTAIN", "BEDROOM", "BATHROOM", "BREAKFAST",
    "COFFEE", "LUNCH", "DINNER", "RABBIT", "GIRAFFE", "GRANDMA", "FAMILY",
}


def _build_gold_rush_book(*, seed: int = 11):
    puzzles, warnings, errors = build_crossword_puzzles(
        mode="topic",
        product_title="California Gold Rush Days",
        theme="California Gold Rush Days",
        difficulty="easy",
        grid_size=15,
        number_of_puzzles=12,
        words_per_puzzle=8,
        output_type="book",
        use_ai_words=False,
        seed=seed,
    )
    pdf_bytes, layout = build_crossword_book_pdf_bytes(
        puzzles,
        product_title="California Gold Rush Days",
        subtitle="12 Crossword Puzzles - Easy Level",
        include_answer_key=True,
        cover_design={
            "title": "California Gold Rush Days",
            "subtitle": "12 Crossword Puzzles - Easy Level",
            "topic": "California Gold Rush Days",
            "audience": "Adults",
            "difficulty": "Easy",
            "use_ai_image": False,
        },
    )
    return puzzles, warnings, errors, pdf_bytes, layout


class TestCrosswordTypographyContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        ensure_crossword_fonts()
        cls.puzzles, cls.warnings, cls.errors, cls.pdf_bytes, cls.layout = _build_gold_rush_book()

    def test_title_unchanged(self):
        reader = PdfReader(io.BytesIO(self.pdf_bytes))
        self.assertEqual(str(reader.metadata.title or ""), "California Gold Rush Days")
        # Cover page text must contain exact title string (whole words).
        import fitz
        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        cover = doc.load_page(0).get_text("text")
        self.assertIn("California Gold Rush Days", cover)
        self.assertNotIn("Goal Rush", cover)

    def test_no_artificial_character_spacing_in_extracted_text(self):
        """Check heading/clue spans only — answer-key grid letters are one glyph per cell."""
        import fitz
        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        for i in range(doc.page_count):
            page = doc.load_page(i)
            # Prefer word tokens (grid letters become separate 1-char words and are ignored).
            words = [w[4] for w in page.get_text("words") if len(w[4]) >= 3]
            blob = " ".join(words)
            for pat in _BAD_SPACING:
                self.assertIsNone(
                    re.search(pat, blob, flags=re.I),
                    f"Page {i+1} has artificial spacing matching /{pat}/ in words: {blob[:180]!r}",
                )
            # Also inspect multi-character spans directly.
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text = span.get("text") or ""
                        if len(text) < 4:
                            continue
                        for pat in _BAD_SPACING:
                            self.assertIsNone(
                                re.search(pat, text, flags=re.I),
                                f"Page {i+1} span spacing /{pat}/: {text!r}",
                            )

    def test_no_malformed_heading_forms(self):
        import fitz
        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        blob = "\n".join(doc.load_page(i).get_text("text") for i in range(doc.page_count))
        for bad in ("C a lifo", "C rossword", "Answ er", "C a l i f"):
            self.assertNotIn(bad, blob)

    def test_uses_embedded_crossword_fonts(self):
        import fitz
        ensure_crossword_fonts()
        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        fonts = set()
        for i in (0, 1, 13):
            for block in doc.load_page(i).get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        fonts.add(span.get("font") or "")
        # Must not rely solely on Helvetica Type1 for body text.
        joined = " ".join(fonts).lower()
        self.assertTrue(
            CROSSWORD_FONT.lower() in joined
            or "arial" in joined
            or CROSSWORD_FONT_BOLD.lower() in joined,
            f"Expected embedded crossword fonts, found {fonts}",
        )

    def test_heading_and_clue_minimum_sizes(self):
        import fitz
        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        # Puzzle page 1
        page = doc.load_page(1)
        heading_sizes = []
        clue_sizes = []
        instruction_sizes = []
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text") or ""
                    size = float(span.get("size") or 0)
                    if "Puzzle 1" in text and "Answer" not in text:
                        heading_sizes.append(size)
                    if text.strip().startswith(tuple(str(n) + "." for n in range(1, 40))):
                        clue_sizes.append(size)
                    if "Fill each" in text or "clues below" in text.lower():
                        instruction_sizes.append(size)
        self.assertTrue(heading_sizes, "Missing puzzle heading")
        self.assertGreaterEqual(max(heading_sizes), HEADING_FONT_MIN_PT - 0.05)
        if clue_sizes:
            self.assertGreaterEqual(min(clue_sizes), CLUE_FONT_MIN_PT - 0.05)
        if instruction_sizes:
            self.assertGreaterEqual(min(instruction_sizes), INSTRUCTION_FONT_MIN_PT - 0.05)

        # Answer-key banner
        ak = doc.load_page(13)
        ak_sizes = []
        for block in ak.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if (span.get("text") or "").strip().upper() == "ANSWER KEY":
                        ak_sizes.append(float(span.get("size") or 0))
        self.assertTrue(ak_sizes)
        self.assertGreaterEqual(max(ak_sizes), 14.0 - 0.05)

    def test_clue_text_stays_within_page(self):
        import fitz
        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        page_w, page_h = 612.0, 792.0
        for i in range(1, 13):
            page = doc.load_page(i)
            for block in page.get_text("dict").get("blocks", []):
                bbox = block.get("bbox") or [0, 0, 0, 0]
                self.assertGreaterEqual(bbox[0], -1.0, f"page {i+1} left overflow")
                self.assertLessEqual(bbox[2], page_w + 1.0, f"page {i+1} right overflow")
                self.assertGreaterEqual(bbox[1], -1.0, f"page {i+1} top overflow")
                self.assertLessEqual(bbox[3], page_h + 1.0, f"page {i+1} bottom overflow")

    def test_page_structure_25_with_12_and_12(self):
        self.assertEqual(self.layout.page_count, 25)
        self.assertEqual(self.layout.cover_page_count, 1)
        self.assertEqual(self.layout.puzzle_page_count, 12)
        self.assertEqual(self.layout.answer_key_page_count, 12)
        reader = PdfReader(io.BytesIO(self.pdf_bytes))
        self.assertEqual(len(reader.pages), 25)
        self.assertIn("12 Crossword Puzzles", str(reader.metadata.subject or ""))

    def test_content_quality_unchanged(self):
        self.assertEqual(len(self.puzzles), 12)
        answers = []
        clues = []
        for p in self.puzzles:
            self.assertGreaterEqual(len(p.placed_words), 8)
            answers.extend(w.upper() for w in p.placed_words)
            clues.extend(c.clue.strip().lower() for c in p.clues)
        self.assertEqual(len(answers), len(set(answers)))
        self.assertEqual(len(clues), len(set(clues)))
        self.assertFalse(set(answers) & _FORBIDDEN)

    def test_glyph_advances_have_no_large_internal_gaps(self):
        """Whole-string drawing: consecutive letters must not have large gaps."""
        import fitz
        doc = fitz.open(stream=self.pdf_bytes, filetype="pdf")
        page = doc.load_page(0)
        target = None
        for block in page.get_text("rawdict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    chars = span.get("chars") or []
                    text = "".join(ch.get("c", "") for ch in chars)
                    if text == "California Gold Rush Days":
                        target = chars
                        break
        self.assertIsNotNone(target, "Cover title glyphs not found")
        for i in range(1, len(target)):
            prev = target[i - 1]["bbox"]
            cur = target[i]["bbox"]
            gap = cur[0] - prev[2]
            # Embedded fonts should keep near-zero gaps; allow tiny float noise.
            self.assertLess(gap, 1.5, f"Gap after {target[i-1].get('c')!r} too large: {gap}")
            self.assertGreater(gap, -1.0, f"Collision before {target[i].get('c')!r}: {gap}")


class TestCrosswordExportPreservesTypography(unittest.TestCase):
    def test_save_export_zip_no_ebook_no_paid_api(self):
        from unittest.mock import patch
        from services.packaging import build_product_export
        from services.product import crossword_full_book_pdf_is_valid

        puzzles, _, _, pdf_bytes, _ = _build_gold_rush_book(seed=13)
        self.assertTrue(crossword_full_book_pdf_is_valid(pdf_bytes, expected_puzzles=12))

        project = {
            "id": None,
            "name": "California Gold Rush Days",
            "data": {
                "product_type": "crossword",
                "is_pdf": True,
                "is_book": True,
                "title": "California Gold Rush Days",
                "puzzle_count": 12,
                "pdf_bytes": base64.b64encode(pdf_bytes).decode("ascii"),
                "filename": "california_gold_rush_days.pdf",
                "fields": {
                    "book_title": "California Gold Rush Days",
                    "theme": "California Gold Rush Days",
                    "output_format": "Full Book",
                    "puzzles": "12",
                    "creation_mode": "Topic (AI generates words)",
                    "difficulty": "Easy",
                    "include_answer_key": "Yes",
                    "include_cover": "Yes",
                },
                "cover_design": {
                    "title": "California Gold Rush Days",
                    "subtitle": "12 Crossword Puzzles - Easy Level",
                    "use_ai_image": False,
                },
            },
        }

        with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json:
            result = build_product_export(project)
            self.assertFalse(chat.called)
            self.assertFalse(chat_json.called)

        from services.ebook_package import EXPORTS_DIR
        package_id = result["package_id"]
        pkg_dir = os.path.join(EXPORTS_DIR, package_id)
        names = os.listdir(pkg_dir)
        self.assertNotIn("ebook.pdf", [n.lower() for n in names])
        pdf_path = next(os.path.join(pkg_dir, n) for n in names if n.lower().endswith(".pdf") and n != "ebook.pdf")
        exported = open(pdf_path, "rb").read()
        self.assertTrue(crossword_full_book_pdf_is_valid(exported, expected_puzzles=12))
        self.assertEqual(hashlib.sha256(exported).hexdigest(), hashlib.sha256(pdf_bytes).hexdigest())

        # ZIP match
        zip_path = os.path.join(pkg_dir, "package.zip")
        with zipfile.ZipFile(zip_path, "r") as zf:
            pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
            self.assertTrue(pdf_names)
            self.assertEqual(zf.read(pdf_names[0]), exported)
            self.assertFalse(any(n.lower() == "ebook.pdf" for n in zf.namelist()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
