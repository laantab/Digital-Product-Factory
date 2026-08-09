"""Regression: Save/Download must work for readable generation package_ids.

Coloring books use slugs like farm_friends_animals_<ts>, not only uuid hex.
/download used to reject those with 400 Invalid download id — so Save+Export
succeeded but the PDF file could never be downloaded.
"""
from __future__ import annotations

import json
import os
import sys
import unittest
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app import app, _PACKAGE_ID_RE  # noqa: E402
from services.ebook_package import _PACKAGE_ID_OK  # noqa: E402


class DownloadSlugPackageIdTests(unittest.TestCase):
    def test_package_id_regex_accepts_generation_slugs(self):
        self.assertTrue(_PACKAGE_ID_RE.match("a" * 32))  # uuid hex still ok
        self.assertTrue(_PACKAGE_ID_RE.match("farm_friends_animals_1786212765"))
        self.assertTrue(_PACKAGE_ID_OK("farm_friends_animals_1786212765"))
        self.assertFalse(_PACKAGE_ID_RE.match("../etc"))
        self.assertFalse(_PACKAGE_ID_RE.match("bad/id"))
        self.assertFalse(_PACKAGE_ID_RE.match("has.dot"))

    def test_save_export_download_slug_package(self):
        pkg = "farm_friends_animals_1786212765"
        pdf_path = ROOT / "exports" / pkg / "farm_friends.pdf"
        if not pdf_path.is_file():
            # Sanitized source packages intentionally exclude generated PDFs.
            # Create a small valid local fixture so this test is self-contained.
            from reportlab.pdfgen import canvas

            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            buffer = BytesIO()
            document = canvas.Canvas(buffer)
            document.setTitle("Farm Friends Download Fixture")
            document.drawString(72, 720, "Farm Friends download-route fixture")
            document.showPage()
            document.save()
            pdf_path.write_bytes(buffer.getvalue())

        client = app.test_client()
        body = {
            "product_type": "coloring_book",
            "title": "Farm Friends Save Test",
            "package_id": pkg,
            "filename": "farm_friends.pdf",
            "is_pdf": True,
            "is_book": True,
            "pdf_stored_on_disk": True,
            "fields": {
                "theme": "farm animals",
                "pages": "12",
                "output_format": "Digital Book",
            },
            "pages": [{"page_number": i + 1, "title": f"Page {i+1}"} for i in range(12)],
            "user_saved": True,
        }
        # No pdf_bytes — mirrors ensureProductSaved omit path
        create = client.post(
            "/projects",
            data=json.dumps(
                {
                    "name": "Farm Friends Save Test",
                    "type": "product",
                    "data": body,
                    "user_saved": True,
                }
            ),
            content_type="application/json",
        )
        self.assertEqual(create.status_code, 201, create.data)
        project_id = create.get_json()["id"]

        export = client.post("/export-product", json={"project_id": project_id})
        self.assertEqual(export.status_code, 200, export.data)
        files = (export.get_json().get("exports") or {}).get("files") or {}
        pdf_url = (files.get("pdf") or {}).get("url")
        self.assertTrue(pdf_url, files)
        self.assertIn(pkg, pdf_url)

        dl = client.get(pdf_url)
        self.assertEqual(dl.status_code, 200, dl.data[:500])
        self.assertTrue(dl.data.startswith(b"%PDF"), dl.data[:20])
        self.assertGreater(len(dl.data), 500)


if __name__ == "__main__":
    unittest.main()
