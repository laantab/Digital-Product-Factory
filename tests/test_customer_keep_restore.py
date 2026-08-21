"""Customer-keep restore: #4249 and #14626 on Saved Projects with existing files.

Zero paid/external calls. Does not regenerate #4249 manuscript/cover/preview.
"""
from __future__ import annotations

import hashlib
import os
import sys
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FACTORY_TEST_MODE", "1")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("TAVILY_API_KEY", "")
os.environ.setdefault("PEXELS_API_KEY", "")

from app import app  # noqa: E402
import database  # noqa: E402
from services.customer_keep_exports import (  # noqa: E402
    COVER_DIGEST_4249,
    COVER_SHA_4249,
    MANUSCRIPT_DIGEST_4249,
    PREVIEW_DIGEST_4249,
    assert_4249_identity,
)
from tests._test_paths import resolve_test_exports_root  # noqa: E402


def _identity(data: dict) -> dict:
    cover = data.get("cover_design") or {}
    source = cover.get("source") or {}
    ident = data.get("ebook_export_identity") or {}
    return {
        "cover_sha": str(source.get("sha256") or ""),
        "cover_digest": str(cover.get("cover_digest") or ident.get("cover_digest") or ""),
        "manuscript_digest": str(
            ident.get("manuscript_digest") or data.get("ebook_manuscript_digest") or ""
        ),
        "preview_digest": str(
            ident.get("preview_digest") or data.get("ebook_preview_digest") or ""
        ),
        "preview_html": str(data.get("ebook_preview_html") or data.get("preview_html") or ""),
        "content": str(data.get("content") or data.get("ebook") or ""),
    }


class CustomerKeepRestoreTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True

    def test_keep_ids_appear_on_customer_list(self):
        resp = self.client.get("/projects")
        self.assertEqual(resp.status_code, 200, resp.data)
        rows = resp.get_json() or []
        ids = {int(p["id"]) for p in rows}
        names = " | ".join(str(p.get("name") or "") for p in rows).lower()
        self.assertIn(4249, ids)
        self.assertIn(14626, ids)
        self.assertTrue(
            "first booking" in names
            or "on-site" in names
            or "event photography" in names
            or "photo printing" in names
        )
        self.assertIn("teen safe online", names)
        self.assertNotIn("customer real product check", names)
        self.assertNotIn("guided cover isolated", names)
        self.assertNotIn("needs correction customer probe", names)
        self.assertLessEqual(len(rows), 10)

    def test_other_needs_correction_still_hidden(self):
        pid = None
        try:
            created = self.client.post(
                "/projects",
                json={
                    "name": "Needs Correction Customer Probe Keep",
                    "type": "product",
                    "user_saved": True,
                    "user_confirmed_save": True,
                    "data": {
                        "title": "Needs Correction Customer Probe Keep",
                        "status": "needs_correction",
                        "stage": "needs_correction",
                        "status_label": "Needs correction.",
                        "quality_blocking": True,
                        "user_confirmed_save": True,
                    },
                },
            )
            self.assertEqual(created.status_code, 201, created.data)
            pid = int(created.get_json()["id"])
            resp = self.client.get("/projects")
            ids = {int(p["id"]) for p in (resp.get_json() or [])}
            self.assertNotIn(pid, ids)
        finally:
            if pid:
                database.delete_project(pid)

    def test_4249_pdf_zip_download_and_identity(self):
        row = database.get_project(4249)
        self.assertIsNotNone(row)
        data = row.get("data") or {}
        assert_4249_identity(data)
        before = _identity(data)
        self.assertEqual(before["cover_sha"], COVER_SHA_4249)
        self.assertEqual(before["cover_digest"], COVER_DIGEST_4249)
        self.assertEqual(before["manuscript_digest"], MANUSCRIPT_DIGEST_4249)
        self.assertEqual(before["preview_digest"], PREVIEW_DIGEST_4249)

        pkg = str(data.get("package_id") or "")
        pdf = self.client.get(f"/download/{pkg}/ebook.pdf")
        self.assertEqual(pdf.status_code, 200, pdf.data[:300])
        self.assertTrue(pdf.data.startswith(b"%PDF"))
        self.assertGreater(len(pdf.data), 1000)

        zipped = self.client.get(f"/download/{pkg}/package.zip")
        self.assertEqual(zipped.status_code, 200, zipped.data[:300])
        with zipfile.ZipFile(__import__("io").BytesIO(zipped.data)) as zf:
            names = zf.namelist()
            self.assertTrue(any(n.lower().endswith(".pdf") for n in names))

        after = database.get_project(4249)
        after_ident = _identity(after.get("data") or {})
        self.assertEqual(after_ident["cover_sha"], before["cover_sha"])
        self.assertEqual(after_ident["cover_digest"], before["cover_digest"])
        self.assertEqual(after_ident["manuscript_digest"], before["manuscript_digest"])
        self.assertEqual(after_ident["preview_digest"], before["preview_digest"])
        self.assertEqual(after_ident["preview_html"], before["preview_html"])
        self.assertEqual(after_ident["content"], before["content"])

    def test_14626_zip_download_no_stub_pdf_claim(self):
        row = database.get_project(14626)
        self.assertIsNotNone(row)
        data = row.get("data") or {}
        pkg = str(data.get("package_id") or "")
        zipped = self.client.get(f"/download/{pkg}/package.zip")
        self.assertEqual(zipped.status_code, 200, zipped.data[:300])
        pdf_path = resolve_test_exports_root() / pkg / "ebook.pdf"
        if pdf_path.is_file():
            pdf = self.client.get(f"/download/{pkg}/ebook.pdf")
            self.assertEqual(pdf.status_code, 200)
            self.assertTrue(pdf.data.startswith(b"%PDF"))
        else:
            missing = self.client.get(f"/download/{pkg}/ebook.pdf")
            self.assertIn(missing.status_code, {400, 403, 404})
        # Honesty: still a blocked factory ebook until the photo exists.
        self.assertFalse(data.get("ebook_ready") is True and data.get("pdf_available") is True)

    def test_export_product_does_not_regenerate_4249(self):
        row = database.get_project(4249)
        before = _identity(row.get("data") or {})
        pkg = str((row.get("data") or {}).get("package_id") or "")
        pdf_path = resolve_test_exports_root() / pkg / "ebook.pdf"
        sha_before = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
        resp = self.client.post("/export-product", json={"project_id": 4249})
        self.assertEqual(resp.status_code, 200, resp.data)
        after = database.get_project(4249)
        after_ident = _identity(after.get("data") or {})
        self.assertEqual(after_ident["preview_html"], before["preview_html"])
        self.assertEqual(after_ident["content"], before["content"])
        self.assertEqual(after_ident["cover_sha"], COVER_SHA_4249)
        self.assertEqual(hashlib.sha256(pdf_path.read_bytes()).hexdigest(), sha_before)

    def test_keep_allowlist_not_global(self):
        src = (ROOT / "database.py").read_text(encoding="utf-8")
        self.assertIn("CUSTOMER_KEEP_PROJECT_IDS", src)
        self.assertIn("is_customer_keep_product", src)
        self.assertIn("customer_keep", src)


if __name__ == "__main__":
    unittest.main()
