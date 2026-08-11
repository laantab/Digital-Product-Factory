"""Regression: math worksheet Final Output Options must offer PDF + ZIP.

Pass 3 Final Output Options previously only rendered a Download PDF control for
word_search / crossword. Math (and other PDF products) got HTML/TXT/ZIP only,
so after Save → Open → Export the PDF appeared missing even when export files
existed. Backend generate/export/download still worked.
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "static" / "js" / "app.js"

os.environ.setdefault("FACTORY_TEST_MODE", "1")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("TAVILY_API_KEY", "")
os.environ.setdefault("AI_INTEGRATIONS_OPENAI_API_KEY", "")


class MathWorksheetFinalOutputPdfLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_js = APP_JS.read_text(encoding="utf-8")

    def test_final_output_card_includes_pdf_link_for_non_puzzle_products(self):
        # Locate finalOutputCard body: puzzle types keep data-pdf button;
        # everyone else must get dl(f.pdf, "Download PDF").
        m = re.search(
            r"function finalOutputCard\([\s\S]*?return card\(\s*`([\s\S]*?)`\s*\)",
            self.app_js,
        )
        self.assertIsNotNone(m, "finalOutputCard template not found")
        body = m.group(1)
        self.assertIn("data-pdf", body)
        self.assertIn('dl(f.pdf, "Download PDF")', body)
        self.assertIn('dl(f.zip, "Download ZIP Package")', body)
        # Puzzle branch must not be the only PDF path (regression guard).
        self.assertRegex(
            body,
            re.compile(
                r"word_search[\s\S]*crossword[\s\S]*data-pdf[\s\S]*"
                r"dl\(f\.pdf,\s*\"Download PDF\"\)",
                re.M,
            ),
        )

    def test_math_export_download_urls_still_serve_pdf_and_zip(self):
        """Customer-path sanity: generate → save → export → PDF/ZIP 200."""
        from unittest.mock import patch

        from app import app
        from services.math_worksheet import pdf_builder as mw

        client = app.test_client()
        fields = {
            "worksheet_title": "Math Final Output PDF Link",
            "grade": "3",
            "math_topic": "Addition",
            "difficulty": "Easy",
            "problems": "6",
            "include_answer_key": "Yes",
            "include_challenge": "No",
            "output_format": "Single Worksheet",
            "audience": "Grade 3 students",
            "goal": "Practice addition",
        }
        with patch.object(mw, "build_math_worksheet_pdf", wraps=mw.build_math_worksheet_pdf):
            prev = client.post(
                "/generate-product",
                json={"product_type": "math_worksheet", "fields": fields},
            )
        self.assertEqual(prev.status_code, 200, prev.data)
        preview = prev.get_json()
        save = client.post(
            "/projects",
            json={
                "name": preview.get("title") or "Math Final Output PDF Link",
                "type": "product",
                "user_saved": True,
                "system_test": True,
                "temporary": True,
                "data": {
                    k: v
                    for k, v in preview.items()
                    if not str(k).startswith("_")
                },
            },
        )
        self.assertEqual(save.status_code, 201, save.data)
        pid = save.get_json()["id"]
        try:
            ex = client.post("/export-product", json={"project_id": pid})
            self.assertEqual(ex.status_code, 200, ex.data)
            body = ex.get_json()
            files = (body.get("exports") or {}).get("files") or {}
            self.assertIn("pdf", files)
            self.assertIn("zip", files)
            self.assertTrue(files["pdf"].get("url"))
            self.assertTrue(files["zip"].get("url"))
            pdf_dl = client.get(files["pdf"]["url"])
            zip_dl = client.get(files["zip"]["url"])
            self.assertEqual(pdf_dl.status_code, 200, pdf_dl.data[:300])
            self.assertEqual(zip_dl.status_code, 200, zip_dl.data[:300])
            self.assertTrue(pdf_dl.data.startswith(b"%PDF"))
            self.assertTrue(zip_dl.data.startswith(b"PK"))
        finally:
            client.delete(f"/projects/{pid}")


if __name__ == "__main__":
    unittest.main()
