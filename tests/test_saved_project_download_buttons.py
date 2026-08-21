"""Regression: Saved Project Download must not orphan product_plan packages.

Bug class: Download PDF/ZIP rendered on every Saved Projects row. Clicking them
on a product_plan (e.g. Thunder Volt plan marketed as \"the book\") called
/export-product, wrote an export folder, then /download returned 403
stale_or_orphan because the download pipeline only resolves type=product.
"""
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "static" / "js" / "app.js"

os.environ.setdefault("FACTORY_TEST_MODE", "1")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("TAVILY_API_KEY", "")
os.environ.setdefault("AI_INTEGRATIONS_OPENAI_API_KEY", "")


class SavedProjectDownloadButtonsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_js = APP_JS.read_text(encoding="utf-8")

    def test_project_row_gates_download_on_product_type(self):
        m = re.search(
            r"function projectRow\([\s\S]*?return row;\s*\}",
            self.app_js,
        )
        self.assertIsNotNone(m, "projectRow not found")
        body = m.group(0)
        self.assertIn("canDownloadProduct", body)
        self.assertIn('p.type === "product"', body)
        self.assertIn('p.type === "ebook"', body)
        # Download markup must be conditional — not hard-coded for every row.
        self.assertIn("${dlPdfBtn}", body)
        self.assertIn("${dlZipBtn}", body)
        self.assertNotIn(
            '<button class="rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-3 py-1.5" data-dl-pdf>Download PDF</button>',
            body,
        )

    def test_trigger_download_surfaces_gate_failures(self):
        m = re.search(
            r"async function triggerDownload\([\s\S]*?\n\}",
            self.app_js,
        )
        self.assertIsNotNone(m, "async triggerDownload not found")
        body = m.group(0)
        self.assertIn("fetch(", body)
        self.assertIn("application/json", body)
        self.assertIn("throw new Error", body)

    def test_visual_id_ok_uses_visual_id_argument(self):
        from services.ebook_package import _VISUAL_ID_OK

        self.assertTrue(_VISUAL_ID_OK("cover"))
        self.assertTrue(_VISUAL_ID_OK("v0_0"))
        self.assertFalse(_VISUAL_ID_OK("not-a-visual"))
        self.assertFalse(_VISUAL_ID_OK(""))

    def test_export_product_rejects_product_plan(self):
        from app import app

        client = app.test_client()
        created = client.post(
            "/projects",
            json={
                "name": "Thunder Volt Plan Download Guard",
                "type": "product_plan",
                "user_saved": True,
                "system_test": True,
                "temporary": True,
                "data": {
                    "product_type": "Coloring Book",
                    "stage": "product_plan_saved",
                    "plan": {"title": "Thunder Volt Bank Rescue"},
                    "user_saved": True,
                },
            },
        )
        self.assertEqual(created.status_code, 201, created.data)
        pid = created.get_json()["id"]
        try:
            ex = client.post("/export-product", json={"project_id": pid})
            self.assertEqual(ex.status_code, 400, ex.data)
            body = ex.get_json() or {}
            err = str(body.get("error") or "")
            self.assertIn("Only saved products", err)
            # Must not leave a downloadable package linked on a plan.
            proj = client.get(f"/projects/{pid}").get_json()
            data = proj.get("data") or {}
            self.assertFalse(data.get("export_package_id"))
            self.assertFalse((data.get("product_exports") or {}).get("files"))
        finally:
            client.delete(f"/projects/{pid}")

    def test_math_product_export_download_still_works(self):
        from app import app
        from services.math_worksheet import pdf_builder as mw

        client = app.test_client()
        fields = {
            "worksheet_title": "Download Guard Math Smoke",
            "grade": "3",
            "math_topic": "Addition",
            "difficulty": "Easy",
            "problems": "4",
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
                "name": preview.get("title") or "Download Guard Math Smoke",
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
            files = ((ex.get_json() or {}).get("exports") or {}).get("files") or {}
            self.assertIn("pdf", files)
            pdf_dl = client.get(files["pdf"]["url"])
            self.assertEqual(pdf_dl.status_code, 200, pdf_dl.data[:300])
            self.assertTrue(pdf_dl.data.startswith(b"%PDF"))
        finally:
            client.delete(f"/projects/{pid}")


if __name__ == "__main__":
    unittest.main()
