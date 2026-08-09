"""Gates for ebook cover edit, author, originality, and pipeline agents."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)


class EbookDesignrrQualityTests(unittest.TestCase):
    def test_originality_detects_copied_source(self):
        from services.ebook_originality_agent import score_originality

        source = (
            "Young children benefit most from conversation, play, books, movement, "
            "and everyday connection when families set clear screen habits."
        )
        copied = source + " " + source
        report = score_originality(copied, [source], n=5)
        self.assertLess(report.score, 0.98)
        self.assertFalse(report.passed)

        original = (
            "Families do better when they treat tablets as a tool for learning and "
            "connection, not as the default way to fill every quiet moment at home."
        )
        report2 = score_originality(original, [source], n=5)
        self.assertGreaterEqual(report2.score, 0.98)
        self.assertTrue(report2.passed)

    def test_apply_ebook_cover_sets_author_and_package(self):
        from services.product import apply_ebook_cover_to_saved_data

        data = {
            "product_type": "ebook",
            "title": "Screens with Purpose",
            "ebook": "# Screens\n\nHello world chapter content here.",
            "fields": {"topic": "screen habits"},
        }
        cover = {
            "title": "Screens with Purpose",
            "subtitle": "A practical guide",
            "author": "Jordan Lee",
            "package_id": "ebook_cover_apply_test",
        }
        out = apply_ebook_cover_to_saved_data(data, cover)
        self.assertEqual(out["author_brand"], "Jordan Lee")
        self.assertEqual(out["cover_design"]["author"], "Jordan Lee")
        self.assertTrue(out.get("cover_dirty"))
        self.assertEqual(out["package_id"], "ebook_cover_apply_test")

    def test_ui_exposes_ebook_cover_and_author(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn('name: "author_brand"', js)
        self.assertIn('d.product_type === "ebook"', js)
        self.assertIn('data-pri="cover"', js)
        self.assertIn("ebookAuthor", html)

    def test_pipeline_requires_author(self):
        from services.ebook_pipeline_agents import run_ebook_quality_pipeline

        report = run_ebook_quality_pipeline(
            title="Test Book",
            manuscript="## Chapter One\n\n" + ("Useful practical guidance. " * 40),
            fields={"topic": "testing", "audience": "adults"},
            require_visuals=False,
            require_cover=False,
            block_on_originality=False,
        )
        self.assertTrue(any("Author" in b or "author" in b.lower() for b in report.blocking))


if __name__ == "__main__":
    unittest.main()
