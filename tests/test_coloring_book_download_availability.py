"""Coloring Book download availability — cover eligibility must not use stale pages."""
from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import unittest
import uuid
from io import BytesIO
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _tiny_book_pdf(pages: int = 2) -> bytes:
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    for i in range(pages):
        if i == 0:
            c.setFont("Helvetica-Bold", 20)
            c.drawString(72, 700, "THUNDER VOLT")
            c.drawString(72, 670, "Superhero Coloring Book")
        else:
            c.setFont("Helvetica", 12)
            c.drawString(72, 700, f"Interior {i}")
        c.showPage()
    c.save()
    return buf.getvalue()


class TestColoringBookDownloadAvailability(unittest.TestCase):
    def test_stale_fields_pages_does_not_block_book_with_cover(self):
        """
        Real failure mode: fields.pages=4 but data.pages has 12 interiors and
        the PDF includes a cover badge containing 'Coloring Book'.
        """
        from services.quality.download_pipeline_agent import (
            resolve_download_request,
            validate_download,
        )

        pdf_bytes = _tiny_book_pdf(pages=13)
        pkg = uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "thunder_volt.pdf")
            with open(path, "wb") as fh:
                fh.write(pdf_bytes)

            project = {
                "id": 900327,
                "name": "Thunder Volt",
                "data": {
                    "product_type": "coloring_book",
                    "is_book": True,
                    "pdf_has_cover_page": True,
                    "pages": [{"page_number": i} for i in range(1, 13)],
                    "fields": {
                        "pages": "4",
                        "output_format": "Digital Book",
                        "theme": "Thunder Volt bank rescue",
                    },
                    "package_id": pkg,
                },
            }

            with patch(
                "services.quality.download_pipeline_agent._load_project_by_package_id",
                return_value=project,
            ):
                ctx = resolve_download_request(
                    route="/download/<package_id>/<filename>",
                    filename="thunder_volt.pdf",
                    file_path=path,
                    package_id=pkg,
                )
                self.assertEqual(ctx.expected_page_count, 12)
                self.assertTrue(ctx.cover_eligible)
                result = validate_download(ctx)
                self.assertEqual(result.status, "passed", result.message)

    def test_export_sanitizes_spaced_pdf_filename(self):
        from services.packaging import build_product_export
        from services.ebook_package import is_allowed_download

        pdf_bytes = _tiny_book_pdf(pages=6)
        b64 = base64.b64encode(pdf_bytes).decode("ascii")
        project = {
            "id": 900329,
            "name": "Thunder Volt",
            "data": {
                "product_type": "coloring_book",
                "title": "Thunder Volt",
                "is_pdf": True,
                "is_book": True,
                "pdf_bytes": b64,
                "filename": "Thunder Volt.pdf",
                "package_id": uuid.uuid4().hex,
                "pdf_has_cover_page": True,
                "pages": [{"page_number": i} for i in range(1, 6)],
                "fields": {
                    "pages": "5",
                    "output_format": "Digital Book",
                    "theme": "Thunder Volt",
                },
            },
        }
        with patch(
            "services.coloring_book.coloring_book_qa_agent.validate_and_correct_coloring_book_output",
            return_value=(pdf_bytes, False),
        ):
            result = build_product_export(project)
        pdf_meta = result["exports"]["files"]["pdf"]
        self.assertTrue(is_allowed_download(pdf_meta["name"]))
        self.assertNotIn(" ", pdf_meta["name"])
        self.assertIn("/download/", pdf_meta["url"])
        # Stale form pages synced from interior list
        self.assertEqual(str(project["data"]["fields"]["pages"]), "5")


if __name__ == "__main__":
    unittest.main()
