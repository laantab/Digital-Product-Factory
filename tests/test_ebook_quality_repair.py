"""Acceptance gates for the shared Ebook generator quality repair.

Uses a repository fixture. Makes ZERO paid API calls.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from tests._test_paths import resolve_test_exports_root  # noqa: E402


def _screens_manuscript() -> str:
    fixture = ROOT / "tests" / "fixtures" / "screens_with_purpose.md"
    text = fixture.read_text(encoding="utf-8")
    if len(text) < 500:
        raise AssertionError("Screens with Purpose fixture is unexpectedly short")
    return text


class EbookQualityRepairTests(unittest.TestCase):
    def test_letter_spacing_stripped_from_pdf_css(self):
        from services import pdf_export

        # Ban actual CSS declarations (comments mentioning the phrase are fine)
        self.assertIsNone(
            re.search(r"letter-spacing\s*:", pdf_export._PDF_CSS, flags=re.I)
        )

    def test_fonts_embed(self):
        from services.ebook_fonts import EBOOK_FONT, ebook_font_paths, ensure_ebook_fonts

        names = ensure_ebook_fonts()
        self.assertEqual(names[0], EBOOK_FONT)
        paths = ebook_font_paths()
        self.assertTrue(paths["regular"])

    def test_rewrite_removes_mechanical_headings(self):
        from services.ebook_interior_visuals import rewrite_mechanical_headings

        md = _screens_manuscript()
        out = rewrite_mechanical_headings(
            md, title="Screens with Purpose", topic="screen habits"
        )
        self.assertNotRegex(out, r"(?im)^###\s*Chapter takeaway")
        self.assertNotRegex(out, r"(?im)^###\s*A step-by-step method")
        self.assertNotRegex(
            out, r"(?im)^###\s*What this chapter helps you solve"
        )

    def test_contract_forbids_repeated_labels(self):
        from services.ebook_contract import (
            FORBIDDEN_REPEATED_HEADINGS,
            build_contract,
            contract_to_prompt_guidance,
        )

        c = build_contract(
            topic="Screens with Purpose",
            audience="Parents of young children",
            tone="supportive",
            reading_level="6th-8th grade",
        )
        guide = contract_to_prompt_guidance(c)
        for phrase in FORBIDDEN_REPEATED_HEADINGS:
            self.assertIn(phrase, guide)
        self.assertIn("vary", guide.lower())

    @mock.patch("ai_client.chat")
    @mock.patch("ai_client.chat_json")
    @mock.patch("ai_client.get_client")
    def test_local_package_and_pdf_zero_paid_calls(self, _gc, _cj, _chat):
        from services.ebook_local_package import build_local_ebook_package
        from services.packaging import build_product_export

        md = _screens_manuscript()
        fields = {
            "topic": "Screens with Purpose",
            "audience": (
                "Parents and caregivers of toddlers, preschoolers, "
                "and early-elementary children"
            ),
            "subtitle": (
                "A Practical Guide to Low-Conflict, Developmentally Appropriate "
                "Screen Habits for Young Children"
            ),
            "tone": "supportive and practical",
            "author_brand": "Digital Product Factory",
        }
        built = build_local_ebook_package(
            "Screens with Purpose", md, fields, package_id="screens_repair_test"
        )
        self.assertTrue(built["local_only"])
        self.assertTrue(built["cover_design"].get("local_generated"))
        titles = [
            a.get("title")
            for ch in built["visual_plan"]["chapters"]
            for a in (ch.get("aids") or [])
        ]
        self.assertTrue(any("Support, Not Replace" in (t or "") for t in titles))
        self.assertTrue(any("Family Screen Plan" in (t or "") for t in titles))

        project = {
            "id": 336,
            "name": "Screens with Purpose",
            "type": "ebook",
            "data": {
                "product_type": "ebook",
                "title": "Screens with Purpose",
                "ebook": built["content"],
                "content": built["content"],
                "subtitle": built["subtitle"],
                "preview_html": built["preview_html"],
                "visual_plan": built["visual_plan"],
                "cover_design": built["cover_design"],
                "package_id": built["package_id"],
                "fields": fields,
                "author_brand": "Digital Product Factory",
            },
        }
        result = build_product_export(project)
        pdf_url = result["exports"]["files"]["pdf"]["url"]
        self.assertIn("/download/", pdf_url)
        pkg = result["package_id"]
        pdf_path = resolve_test_exports_root() / pkg / "ebook.pdf"
        self.assertTrue(pdf_path.is_file())
        pdf = pdf_path.read_bytes()
        self.assertTrue(pdf.startswith(b"%PDF"))

        # Spacing operators: reject large Tc / Tw artificial spacing streams
        # (xhtml2pdf letter-spacing historically emitted suspicious advances)
        self.assertNotRegex(pdf, rb"(?i)letter-spacing")

        import fitz
        from pypdf import PdfReader

        reader = PdfReader(str(pdf_path))
        meta = reader.metadata or {}
        self.assertIn("Screens", str(meta.get("/Title") or ""))
        self.assertIn("Digital Product Factory", str(meta.get("/Author") or ""))
        self.assertTrue(str(meta.get("/Subject") or "").strip())
        self.assertTrue(str(meta.get("/Keywords") or "").strip())

        doc = fitz.open(pdf_path)
        self.assertGreaterEqual(doc.page_count, 8)
        # Cover page should not be tiny purple shell only — has substantial paint
        pix0 = doc[0].get_pixmap(matrix=fitz.Matrix(0.4, 0.4))
        self.assertGreater(pix0.width * pix0.height, 10000)

        # No accidental blank interior pages
        blank = 0
        for i in range(doc.page_count):
            text = (doc.load_page(i).get_text("text") or "").strip()
            if i > 0 and len(text) < 12:
                blank += 1
        self.assertEqual(blank, 0, "accidental blank pages present")

        # TOC has digits (page numbers)
        toc_text = ""
        for i in range(min(6, doc.page_count)):
            t = doc.load_page(i).get_text("text") or ""
            if "table of contents" in t.lower():
                toc_text = t
                break
        self.assertIn("table of contents", toc_text.lower())
        self.assertRegex(toc_text, r"\d")

        # Corrupted spacing smoke: "S creens" / "C hapter" patterns
        all_text = "\n".join(doc.load_page(i).get_text("text") or "" for i in range(doc.page_count))
        self.assertNotRegex(all_text, r"\bS\s+creens\b")
        self.assertNotRegex(all_text, r"\bC\s+hapter\b")
        self.assertNotRegex(all_text, r"(?i)chapter takeaway")

        # Required visuals present in text layer
        self.assertIn("Screens Support", all_text)
        self.assertIn("Family Screen Plan", all_text)

        # ZIP PDF matches direct PDF
        import hashlib
        import zipfile

        zpath = resolve_test_exports_root() / pkg / "package.zip"
        with zipfile.ZipFile(zpath) as zf:
            zpdf = zf.read("ebook.pdf")
        self.assertEqual(hashlib.md5(pdf).hexdigest(), hashlib.md5(zpdf).hexdigest())
        doc.close()

        _gc.assert_not_called()
        _cj.assert_not_called()
        _chat.assert_not_called()

    def test_forbidden_marketing_allows_honest_negation(self):
        """'not guaranteed' is disclaimer language, not a hype claim."""
        from services.ebook_quality_agent import _find_forbidden_marketing

        honest = (
            "Compounding is not instant, and it is not guaranteed. "
            "Nothing is guaranteed in markets. Results are never guaranteed."
        )
        self.assertEqual(_find_forbidden_marketing(honest), [])

        hype = (
            "This method is guaranteed to work. "
            "You get guaranteed results with zero effort."
        )
        found = _find_forbidden_marketing(hype)
        self.assertIn("guaranteed", found)


if __name__ == "__main__":
    unittest.main()
