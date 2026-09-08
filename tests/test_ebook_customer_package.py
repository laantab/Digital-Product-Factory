"""Canonical customer ZIP promotion. Zero paid/external calls.

A designed verification archive may say verification_copy=true. The customer
package must copy the approved PDF and assets byte-for-byte and rewrite only
the manifest. Packaging must reuse a certified on-disk PDF instead of
re-rendering.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""
os.environ["PEXELS_API_KEY"] = ""

from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

from services.ebook_customer_package import (  # noqa: E402
    PACKAGE_STATUS_CUSTOMER_FINAL,
    apply_promoted_identity,
    certified_pdf_sha256,
    is_customer_final_manifest,
    load_reusable_workspace_export,
    promote_package_dir,
    promote_zip_to_customer_final,
)
from services.packaging import EXPORTS_DIR, build_product_export  # noqa: E402


def _sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _certified_pdf_bytes(label: str = "certified-customer-pdf") -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setTitle(label)
    c.drawString(72, 720, label)
    c.save()
    return buf.getvalue()


def _verification_zip(pdf_bytes: bytes, *, extra: dict[str, bytes] | None = None) -> bytes:
    manifest = {
        "title": "5-Minute Mindfulness for Busy Beginners",
        "subtitle": "A short daily reset",
        "author": "Lonnie Brown",
        "theme_id": "warm_wellness",
        "pdf_sha256": _sha(pdf_bytes),
        "paid_images": False,
        "verification_copy": True,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("ebook.pdf", pdf_bytes)
        zf.writestr("ebook.html", "<html><body>approved manuscript</body></html>")
        zf.writestr("cover/cover.png", b"\x89PNG\r\n\x1a\n" + b"cover-bytes")
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))
        for name, blob in (extra or {}).items():
            zf.writestr(name, blob)
    return buf.getvalue()


def _inner_manifest(zip_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        return json.loads(zf.read("manifest.json").decode("utf-8"))


def _inner_pdf(zip_bytes: bytes) -> bytes:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        return zf.read("ebook.pdf")


class PromoteZipTests(unittest.TestCase):
    def test_promote_rewrites_manifest_and_keeps_pdf_bytes(self):
        pdf = _certified_pdf_bytes()
        pdf_sha = _sha(pdf)
        verification = _verification_zip(pdf, extra={"visuals/aid.bin": b"approved-visual"})
        verification_sha = _sha(verification)
        self.assertTrue(_inner_manifest(verification)["verification_copy"] is True)

        promoted = promote_zip_to_customer_final(
            verification,
            expected_pdf_sha256=pdf_sha,
        )
        self.assertTrue(promoted["changed"])
        self.assertEqual(promoted["pdf_sha256"], pdf_sha)
        self.assertNotEqual(promoted["zip_sha256"], verification_sha)
        self.assertEqual(_inner_pdf(promoted["zip_bytes"]), pdf)
        with zipfile.ZipFile(io.BytesIO(promoted["zip_bytes"]), "r") as zf:
            self.assertEqual(zf.read("visuals/aid.bin"), b"approved-visual")
            self.assertEqual(zf.read("cover/cover.png"), b"\x89PNG\r\n\x1a\n" + b"cover-bytes")

        manifest = promoted["manifest"]
        self.assertIs(manifest.get("verification_copy"), False)
        self.assertEqual(manifest.get("package_status"), PACKAGE_STATUS_CUSTOMER_FINAL)
        self.assertEqual(manifest.get("pdf_sha256"), pdf_sha)
        self.assertNotIn("zip_sha256", manifest)
        self.assertNotIn('"verification_copy": true', json.dumps(manifest).lower())

        again = promote_zip_to_customer_final(
            promoted["zip_bytes"],
            expected_pdf_sha256=pdf_sha,
        )
        self.assertFalse(again["changed"])
        self.assertEqual(again["zip_sha256"], promoted["zip_sha256"])
        self.assertEqual(again["zip_bytes"], promoted["zip_bytes"])

    def test_promote_refuses_wrong_pdf_hash(self):
        pdf = _certified_pdf_bytes()
        verification = _verification_zip(pdf)
        with self.assertRaises(ValueError):
            promote_zip_to_customer_final(
                verification,
                expected_pdf_sha256="0" * 64,
            )

    def test_promote_package_dir_leaves_pdf_file_untouched(self):
        import tempfile

        pdf = _certified_pdf_bytes("dir-promote")
        pdf_sha = _sha(pdf)
        with tempfile.TemporaryDirectory() as tmp:
            pkg = Path(tmp) / "ebook-351-warm-wellness-final"
            pkg.mkdir()
            (pkg / "ebook.pdf").write_bytes(pdf)
            (pkg / "package.zip").write_bytes(_verification_zip(pdf))
            (pkg / "historical.txt").write_text("keep", encoding="utf-8")
            promoted = promote_package_dir(pkg, expected_pdf_sha256=pdf_sha)
            self.assertEqual(_sha((pkg / "ebook.pdf").read_bytes()), pdf_sha)
            self.assertEqual(_sha((pkg / "package.zip").read_bytes()), promoted["zip_sha256"])
            self.assertEqual((pkg / "historical.txt").read_text(encoding="utf-8"), "keep")
            disk_manifest = json.loads((pkg / "manifest.json").read_text(encoding="utf-8"))
            self.assertIs(disk_manifest["verification_copy"], False)
            self.assertEqual(disk_manifest["package_status"], PACKAGE_STATUS_CUSTOMER_FINAL)


class PackagingReusePromotionTests(unittest.TestCase):
    def setUp(self):
        self.pdf = _certified_pdf_bytes("workspace-reuse")
        self.pdf_sha = _sha(self.pdf)
        self.package_id = "ebook-customer-final-reuse"
        self.pkg_dir = Path(EXPORTS_DIR) / self.package_id
        self.pkg_dir.mkdir(parents=True, exist_ok=True)
        self.verification_zip = _verification_zip(self.pdf)
        (self.pkg_dir / "ebook.pdf").write_bytes(self.pdf)
        (self.pkg_dir / "ebook.html").write_text(
            "<html><body>approved manuscript</body></html>",
            encoding="utf-8",
        )
        (self.pkg_dir / "package.zip").write_bytes(self.verification_zip)
        self.project = {
            "type": "ebook",
            "name": "5-Minute Mindfulness for Busy Beginners",
            "data": {
                "product_type": "ebook",
                "ebook_project_workspace": True,
                "artifact_state": "DRAFT",
                "package_id": self.package_id,
                "export_package_id": self.package_id,
                "artifact_id": self.package_id,
                "title": "5-Minute Mindfulness for Busy Beginners",
                "author_brand": "Lonnie Brown",
                "content": "# 5-Minute Mindfulness for Busy Beginners\n\nBreathe.",
                "ebook": "# 5-Minute Mindfulness for Busy Beginners\n\nBreathe.",
                "ebook_preview_html": "<html><body>approved manuscript</body></html>",
                "ebook_export_identity": {
                    "preview_digest": self.pdf_sha,
                    "pdf_sha256": self.pdf_sha,
                    "zip_sha256": _sha(self.verification_zip),
                    "manuscript_digest": "keep-manuscript-digest",
                    "design_digest": "keep-design-digest",
                    "theme_id": "warm_wellness",
                },
            },
        }

    def tearDown(self):
        if self.pkg_dir.is_dir():
            for child in self.pkg_dir.glob("*"):
                try:
                    child.unlink()
                except OSError:
                    pass
            try:
                self.pkg_dir.rmdir()
            except OSError:
                pass

    def test_certified_pdf_prefers_preview_digest(self):
        self.assertEqual(certified_pdf_sha256(self.project["data"]), self.pdf_sha)

    def test_load_reusable_requires_matching_pdf(self):
        loaded = load_reusable_workspace_export(self.project["data"], EXPORTS_DIR)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["pdf_bytes"], self.pdf)
        self.project["data"]["ebook_export_identity"]["preview_digest"] = "a" * 64
        self.project["data"]["ebook_export_identity"]["pdf_sha256"] = "a" * 64
        self.assertIsNone(load_reusable_workspace_export(self.project["data"], EXPORTS_DIR))

    def test_build_product_export_reuses_pdf_and_promotes_zip(self):
        with patch(
            "services.ebook_design_export.apply_workspace_design_to_export",
            side_effect=AssertionError("must not re-render approved PDF"),
        ):
            result = build_product_export(self.project)

        disk_pdf = (self.pkg_dir / "ebook.pdf").read_bytes()
        disk_zip = (self.pkg_dir / "package.zip").read_bytes()
        self.assertEqual(_sha(disk_pdf), self.pdf_sha)
        self.assertEqual(_inner_pdf(disk_zip), self.pdf)

        ident = self.project["data"]["ebook_export_identity"]
        self.assertEqual(ident["pdf_sha256"], self.pdf_sha)
        self.assertEqual(ident["preview_digest"], self.pdf_sha)
        self.assertEqual(ident["zip_sha256"], _sha(disk_zip))
        self.assertNotEqual(ident["zip_sha256"], _sha(self.verification_zip))
        self.assertIs(ident["verification_copy"], False)
        self.assertEqual(ident["package_status"], PACKAGE_STATUS_CUSTOMER_FINAL)
        self.assertEqual(ident["manuscript_digest"], "keep-manuscript-digest")
        self.assertEqual(ident["design_digest"], "keep-design-digest")

        inner = _inner_manifest(disk_zip)
        self.assertTrue(is_customer_final_manifest(inner))
        self.assertIs(inner.get("verification_copy"), False)
        self.assertNotIn("true", json.dumps({"verification_copy": inner.get("verification_copy")}))

        files = (result["exports"] or {}).get("files") or {}
        self.assertEqual(files["pdf"]["sha256"], self.pdf_sha)
        self.assertEqual(files["zip"]["sha256"], ident["zip_sha256"])
        self.assertEqual(files["pdf"]["url"], f"/download/{self.package_id}/ebook.pdf")
        self.assertEqual(files["zip"]["url"], f"/download/{self.package_id}/package.zip")

    def test_first_export_promotes_rendered_verification_zip(self):
        fresh_id = "ebook-customer-final-first"
        pdf = self.pdf
        verification = self.verification_zip

        def fake_render(project):
            data = dict(project.get("data") or {})
            data["ebook_export_identity"] = {
                "preview_digest": self.pdf_sha,
                "pdf_sha256": self.pdf_sha,
                "zip_sha256": _sha(verification),
            }
            data["ebook_preview_html"] = "<html><body>approved manuscript</body></html>"
            project = dict(project)
            project["data"] = data
            project["_design_export_pdf"] = pdf
            project["_design_export_zip"] = verification
            return project

        project = {
            "type": "ebook",
            "data": {
                "product_type": "ebook",
                "ebook_project_workspace": True,
                "artifact_state": "DRAFT",
                "package_id": fresh_id,
                "content": "# New Workspace Ebook\n\nBody.",
                "ebook": "# New Workspace Ebook\n\nBody.",
            },
        }
        pkg_dir = Path(EXPORTS_DIR) / fresh_id
        try:
            with patch(
                "services.ebook_design_export.apply_workspace_design_to_export",
                side_effect=fake_render,
            ):
                result = build_product_export(project)
            zip_bytes = (pkg_dir / "package.zip").read_bytes()
            self.assertEqual(_sha((pkg_dir / "ebook.pdf").read_bytes()), self.pdf_sha)
            self.assertEqual(_inner_pdf(zip_bytes), pdf)
            inner = _inner_manifest(zip_bytes)
            self.assertIs(inner.get("verification_copy"), False)
            self.assertEqual(inner.get("package_status"), PACKAGE_STATUS_CUSTOMER_FINAL)
            self.assertEqual(result["exports"]["files"]["zip"]["sha256"], _sha(zip_bytes))
            self.assertNotEqual(_sha(zip_bytes), _sha(verification))
        finally:
            if pkg_dir.is_dir():
                for child in pkg_dir.glob("*"):
                    try:
                        child.unlink()
                    except OSError:
                        pass
                try:
                    pkg_dir.rmdir()
                except OSError:
                    pass

    def test_second_packaging_pass_is_idempotent(self):
        with patch(
            "services.ebook_design_export.apply_workspace_design_to_export",
            side_effect=AssertionError("must not re-render approved PDF"),
        ):
            first = build_product_export(self.project)
        disk_pdf = (self.pkg_dir / "ebook.pdf").read_bytes()
        disk_zip = (self.pkg_dir / "package.zip").read_bytes()
        with patch(
            "services.ebook_design_export.apply_workspace_design_to_export",
            side_effect=AssertionError("must not re-render approved PDF"),
        ):
            again = build_product_export(self.project)
        self.assertEqual((self.pkg_dir / "ebook.pdf").read_bytes(), disk_pdf)
        self.assertEqual((self.pkg_dir / "package.zip").read_bytes(), disk_zip)
        self.assertEqual(
            again["exports"]["files"]["zip"]["sha256"],
            first["exports"]["files"]["zip"]["sha256"],
        )


class SavedProjectsDownloadIdentityTests(unittest.TestCase):
    def setUp(self):
        from app import app
        import database

        self.app = app
        self.client = app.test_client()
        self.database = database
        self.pdf = _certified_pdf_bytes("saved-projects-download")
        self.pdf_sha = _sha(self.pdf)
        self.package_id = "ebook-customer-final-dl"
        self.pkg_dir = Path(EXPORTS_DIR) / self.package_id
        self.pkg_dir.mkdir(parents=True, exist_ok=True)
        verification = _verification_zip(self.pdf)
        (self.pkg_dir / "ebook.pdf").write_bytes(self.pdf)
        (self.pkg_dir / "ebook.html").write_text("<html>ok</html>", encoding="utf-8")
        (self.pkg_dir / "package.zip").write_bytes(verification)
        data = {
            "product_type": "ebook",
            "ebook_project_workspace": True,
            "artifact_state": "DRAFT",
            "package_id": self.package_id,
            "export_package_id": self.package_id,
            "artifact_id": self.package_id,
            "title": "Download Identity Fixture",
            "content": "# Download Identity Fixture\n\nBody.",
            "ebook": "# Download Identity Fixture\n\nBody.",
            "ebook_export_identity": {
                "preview_digest": self.pdf_sha,
                "pdf_sha256": self.pdf_sha,
                "zip_sha256": _sha(verification),
            },
        }
        created = database.create_project(
            "Download Identity Fixture",
            "ebook",
            data,
            user_saved=True,
            system_test=True,
            temporary=True,
        )
        self.project_id = created["id"]
        created["data"] = data
        with patch(
            "services.ebook_design_export.apply_workspace_design_to_export",
            side_effect=AssertionError("must not re-render approved PDF"),
        ):
            result = build_product_export(created)
        data["export_package_id"] = result["package_id"]
        data["product_exports"] = result["exports"]
        data["ebook_export_identity"] = created["data"]["ebook_export_identity"]
        database.update_project(self.project_id, None, data)
        self.zip_sha = data["ebook_export_identity"]["zip_sha256"]

    def tearDown(self):
        try:
            self.client.delete(f"/projects/{self.project_id}")
        except Exception:
            pass
        if self.pkg_dir.is_dir():
            for child in self.pkg_dir.glob("*"):
                try:
                    child.unlink()
                except OSError:
                    pass
            try:
                self.pkg_dir.rmdir()
            except OSError:
                pass

    def test_two_saved_projects_downloads_share_promoted_identity(self):
        pdf_one = self.client.get(f"/download/{self.package_id}/ebook.pdf")
        pdf_two = self.client.get(f"/download/{self.package_id}/ebook.pdf")
        zip_one = self.client.get(f"/download/{self.package_id}/package.zip")
        zip_two = self.client.get(f"/download/{self.package_id}/package.zip")
        self.assertEqual(pdf_one.status_code, 200, pdf_one.data[:400])
        self.assertEqual(pdf_two.status_code, 200, pdf_two.data[:400])
        self.assertEqual(zip_one.status_code, 200, zip_one.data[:400])
        self.assertEqual(zip_two.status_code, 200, zip_two.data[:400])
        self.assertEqual(_sha(pdf_one.data), self.pdf_sha)
        self.assertEqual(_sha(pdf_two.data), self.pdf_sha)
        self.assertEqual(pdf_one.data, pdf_two.data)
        self.assertEqual(_sha(zip_one.data), self.zip_sha)
        self.assertEqual(_sha(zip_two.data), self.zip_sha)
        self.assertEqual(zip_one.data, zip_two.data)
        self.assertEqual(_inner_pdf(zip_one.data), pdf_one.data)
        manifest = _inner_manifest(zip_one.data)
        self.assertIs(manifest.get("verification_copy"), False)
        self.assertEqual(manifest.get("package_status"), PACKAGE_STATUS_CUSTOMER_FINAL)
        raw = zip_one.data.decode("latin-1")
        self.assertNotIn('"verification_copy": true', raw)
        self.assertNotIn('"verification_copy":true', raw.replace(" ", ""))


class IdentityHelperTests(unittest.TestCase):
    def test_apply_promoted_identity_preserves_preview_digest(self):
        data = {
            "ebook_export_identity": {
                "preview_digest": "ecd2a570d14a2cce60c79e4f2098b25936fba0a9f0d090310315ce50e012ad4b",
                "pdf_sha256": "ecd2a570d14a2cce60c79e4f2098b25936fba0a9f0d090310315ce50e012ad4b",
                "zip_sha256": "old-zip",
            }
        }
        apply_promoted_identity(
            data,
            {
                "pdf_sha256": "ecd2a570d14a2cce60c79e4f2098b25936fba0a9f0d090310315ce50e012ad4b",
                "zip_sha256": "new-zip",
            },
        )
        ident = data["ebook_export_identity"]
        self.assertEqual(
            ident["preview_digest"],
            "ecd2a570d14a2cce60c79e4f2098b25936fba0a9f0d090310315ce50e012ad4b",
        )
        self.assertEqual(ident["zip_sha256"], "new-zip")
        self.assertEqual(ident["package_status"], PACKAGE_STATUS_CUSTOMER_FINAL)
        self.assertIs(ident["verification_copy"], False)


if __name__ == "__main__":
    unittest.main()
