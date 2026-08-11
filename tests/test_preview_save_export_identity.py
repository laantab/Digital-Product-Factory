"""Gate 5: Preview → Save → Open → PDF → ZIP same-artifact identity.

Uses a deterministic local math_worksheet fixture under FACTORY_TEST_MODE.
PDF/ZIP binary hashes may differ; identity is proven via project/artifact
record + canonical content/asset digests + revision.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import unittest
import zipfile
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""

from app import app  # noqa: E402
from services.ebook_package import EXPORTS_DIR, _write_package  # noqa: E402
from services.quality.artifact_identity import (  # noqa: E402
    asset_manifest_digest,
    content_digest_from_pdf_bytes,
)


FIELDS = {
    "worksheet_title": "Gate5 Identity Math Fixture",
    "grade": "3",
    "math_topic": "Addition",
    "difficulty": "Easy",
    "problems": "6",
    "include_answer_key": "Yes",
    "include_challenge": "No",
    "output_format": "Single Worksheet",
    "audience": "Grade 3 students",
    "goal": "Practice addition facts",
}


class PreviewSaveExportIdentityTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self._project_ids: list[int] = []
        self._pkg_dirs: list[str] = []

    def tearDown(self):
        for pid in self._project_ids:
            try:
                self.client.delete(f"/projects/{pid}")
            except Exception:
                pass
        for pkg in self._pkg_dirs:
            path = Path(EXPORTS_DIR) / pkg
            if path.is_dir():
                for child in path.glob("*"):
                    try:
                        child.unlink()
                    except OSError:
                        pass
                try:
                    path.rmdir()
                except OSError:
                    pass

    def _track(self, project_id: int | None = None, package_id: str | None = None):
        if project_id is not None:
            self._project_ids.append(int(project_id))
        if package_id:
            self._pkg_dirs.append(str(package_id))

    def test_preview_save_open_pdf_zip_same_artifact_identity(self):
        import services.product as product_mod
        from services.math_worksheet import pdf_builder as mw

        gen_calls = {"generate_product": 0, "build_math": 0}
        orig_gen = product_mod.generate_product
        orig_build = mw.build_math_worksheet_pdf

        def gen_wrap(*a, **k):
            gen_calls["generate_product"] += 1
            return orig_gen(*a, **k)

        def build_wrap(*a, **k):
            gen_calls["build_math"] += 1
            return orig_build(*a, **k)

        # 1–3: deterministic preview without external calls
        with patch.object(product_mod, "generate_product", side_effect=gen_wrap), patch.object(
            mw, "build_math_worksheet_pdf", side_effect=build_wrap
        ):
            preview_resp = self.client.post(
                "/generate-product",
                json={"product_type": "math_worksheet", "fields": FIELDS},
            )
            self.assertEqual(preview_resp.status_code, 200, preview_resp.data)
            preview = preview_resp.get_json()
            self.assertEqual(preview.get("product_type"), "math_worksheet")
            self.assertTrue(preview.get("package_id"))
            self.assertTrue(preview.get("content_digest"))
            self.assertTrue(preview.get("asset_manifest_digest"))
            self.assertEqual(int(preview.get("artifact_revision") or 0), 1)

            pdf_preview = base64.b64decode(preview["pdf_bytes"])
            self.assertTrue(pdf_preview.startswith(b"%PDF"))
            content_digest = preview["content_digest"]
            self.assertEqual(content_digest, content_digest_from_pdf_bytes(pdf_preview))
            asset_digest = preview["asset_manifest_digest"]
            self.assertEqual(asset_digest, asset_manifest_digest(preview))
            artifact_id = preview.get("artifact_id") or preview["package_id"]
            problems = list(preview.get("problems") or [])
            self.assertEqual(len(problems), 6)

            preview_identity = {
                "artifact_id": artifact_id,
                "package_id": preview["package_id"],
                "product_type": preview["product_type"],
                "title": preview["title"],
                "audience": FIELDS["audience"],
                "goal": FIELDS["goal"],
                "content_digest": content_digest,
                "asset_manifest_digest": asset_digest,
                "artifact_revision": int(preview["artifact_revision"]),
                "problems": problems,
            }

            # 4: Save that previewed artifact
            save_resp = self.client.post(
                "/projects",
                json={
                    "name": preview["title"],
                    "type": "product",
                    "user_saved": True,
                    "temporary": True,
                    "system_test": True,
                    "data": {
                        **preview,
                        "audience": FIELDS["audience"],
                        "goal": FIELDS["goal"],
                    },
                },
            )
            self.assertEqual(save_resp.status_code, 201, save_resp.data)
            saved = save_resp.get_json()
            project_id = saved["id"]
            self._track(project_id=project_id, package_id=preview["package_id"])
            saved_data = saved.get("data") or {}

            # 5: Reopen via Saved Projects / Open Product
            open_resp = self.client.get(f"/projects/{project_id}")
            self.assertEqual(open_resp.status_code, 200)
            opened = open_resp.get_json()
            odata = opened.get("data") or {}

            for stage_name, stage_data in (
                ("saved", saved_data),
                ("opened", odata),
            ):
                with self.subTest(stage=stage_name):
                    self.assertEqual(stage_data.get("package_id"), preview_identity["package_id"])
                    self.assertEqual(
                        stage_data.get("artifact_id") or stage_data.get("package_id"),
                        preview_identity["artifact_id"],
                    )
                    self.assertEqual(stage_data.get("product_type"), "math_worksheet")
                    self.assertEqual(stage_data.get("title"), preview_identity["title"])
                    self.assertEqual(stage_data.get("audience"), FIELDS["audience"])
                    self.assertEqual(stage_data.get("goal"), FIELDS["goal"])
                    self.assertEqual(stage_data.get("content_digest"), content_digest)
                    self.assertEqual(stage_data.get("asset_manifest_digest"), asset_digest)
                    self.assertEqual(
                        int(stage_data.get("artifact_revision") or 0),
                        preview_identity["artifact_revision"],
                    )
                    self.assertEqual(stage_data.get("problems"), problems)
                    self.assertEqual(
                        content_digest_from_pdf_bytes(base64.b64decode(stage_data["pdf_bytes"])),
                        content_digest,
                    )

            # 6–8: PDF + ZIP export; no generation during Save/Open/PDF/ZIP
            gen_before_export = dict(gen_calls)
            export_resp = self.client.post("/export-product", json={"project_id": project_id})
            self.assertEqual(export_resp.status_code, 200, export_resp.data)
            export_body = export_resp.get_json()
            export_pkg = export_body["package_id"]
            self._track(package_id=export_pkg)
            self.assertEqual(
                gen_calls["generate_product"] - gen_before_export["generate_product"],
                0,
            )
            self.assertEqual(
                gen_calls["build_math"] - gen_before_export["build_math"],
                0,
            )

            files = (export_body.get("exports") or {}).get("files") or {}
            pdf_url = (files.get("pdf") or {}).get("url")
            zip_url = (files.get("zip") or {}).get("url")
            self.assertTrue(pdf_url)
            self.assertTrue(zip_url)

            # Re-open after export — same authoritative artifact/revision
            after_export = self.client.get(f"/projects/{project_id}").get_json()
            adata = after_export.get("data") or {}
            self.assertEqual(adata.get("package_id"), preview_identity["package_id"])
            self.assertEqual(adata.get("content_digest"), content_digest)
            self.assertEqual(adata.get("asset_manifest_digest"), asset_digest)
            self.assertEqual(
                int(adata.get("artifact_revision") or 0),
                preview_identity["artifact_revision"],
            )
            self.assertEqual(adata.get("export_package_id"), export_pkg)
            self.assertEqual(adata.get("problems"), problems)

            pdf_dl = self.client.get(pdf_url)
            zip_dl = self.client.get(zip_url)
            self.assertEqual(pdf_dl.status_code, 200, pdf_dl.data[:300])
            self.assertEqual(zip_dl.status_code, 200, zip_dl.data[:300])
            self.assertTrue(pdf_dl.data.startswith(b"%PDF"))
            self.assertGreater(len(pdf_dl.data), 100)
            self.assertGreater(len(zip_dl.data), 100)
            self.assertEqual(content_digest_from_pdf_bytes(pdf_dl.data), content_digest)

            # 10–11: ZIP readable with expected files + manifest; PDF page count
            zf = zipfile.ZipFile(BytesIO(zip_dl.data))
            names = zf.namelist()
            self.assertIn("metadata.json", names)
            pdf_names = [n for n in names if n.lower().endswith(".pdf")]
            self.assertEqual(len(pdf_names), 1)
            self.assertTrue(any(n == "problems.txt" for n in names))
            self.assertFalse(any(n.startswith("ebook.") for n in names))
            meta = json.loads(zf.read("metadata.json").decode("utf-8"))
            self.assertEqual(meta.get("product_type"), "math_worksheet")
            self.assertEqual(meta.get("title"), preview_identity["title"])
            zip_pdf = zf.read(pdf_names[0])
            self.assertEqual(content_digest_from_pdf_bytes(zip_pdf), content_digest)
            # PDF/ZIP archives themselves may differ; content identity holds via digest.
            self.assertNotEqual(
                hashlib.sha256(pdf_dl.data).hexdigest(),
                hashlib.sha256(zip_dl.data).hexdigest(),
            )

            from pypdf import PdfReader

            pages = len(PdfReader(BytesIO(pdf_dl.data)).pages)
            self.assertGreaterEqual(pages, 1)

            # 13: stale export from another revision must not be returned
            from reportlab.pdfgen import canvas

            stale_pkg = "gate5stale" + ("b" * 22)
            self._track(package_id=stale_pkg)
            buf = BytesIO()
            c = canvas.Canvas(buf)
            c.drawString(72, 720, "STALE REVISION")
            c.showPage()
            c.save()
            _write_package(stale_pkg, {"stale.pdf": buf.getvalue()})
            stale_dl = self.client.get(f"/download/{stale_pkg}/stale.pdf")
            self.assertEqual(stale_dl.status_code, 403, stale_dl.data[:400])
            stale_json = stale_dl.get_json() or {}
            self.assertEqual(stale_json.get("error"), "download_blocked")

            # Prior export package becomes stale after a new authoritative export
            # (simulate by clearing export_package_id link while leaving folder).
            prior_pkg = export_pkg
            bumped = dict(adata)
            bumped["artifact_revision"] = int(adata["artifact_revision"]) + 1
            # Keep same content digests/pdf — only revision bump + new export later.
            put = self.client.put(f"/projects/{project_id}", json={"data": bumped})
            self.assertEqual(put.status_code, 200)
            export2 = self.client.post("/export-product", json={"project_id": project_id})
            self.assertEqual(export2.status_code, 200, export2.data)
            new_pkg = export2.get_json()["package_id"]
            self._track(package_id=new_pkg)
            self.assertNotEqual(new_pkg, prior_pkg)
            stale_prior = self.client.get(
                f"/download/{prior_pkg}/gate5_identity_math_fixture.pdf"
            )
            self.assertEqual(stale_prior.status_code, 403, stale_prior.data[:400])

            # 14: identity mismatch fails clearly (no silent regen)
            bad = dict(self.client.get(f"/projects/{project_id}").get_json()["data"])
            bad["content_digest"] = "0" * 64
            put_bad = self.client.put(f"/projects/{project_id}", json={"data": bad})
            self.assertEqual(put_bad.status_code, 200)
            gen_before_mismatch = dict(gen_calls)
            mismatch = self.client.post("/export-product", json={"project_id": project_id})
            self.assertEqual(mismatch.status_code, 400, mismatch.data)
            err = mismatch.get_json() or {}
            self.assertIn("identity mismatch", (err.get("error") or "").lower())
            self.assertEqual(
                gen_calls["generate_product"] - gen_before_mismatch["generate_product"],
                0,
            )
            self.assertEqual(
                gen_calls["build_math"] - gen_before_mismatch["build_math"],
                0,
            )


if __name__ == "__main__":
    unittest.main()
