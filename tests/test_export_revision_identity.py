"""Approved stages and displayed hashes must describe the same revision.

WHAT SHIPPED
------------
A workspace screen read Visuals / Cover / Design / Preview / Preflight
"Approved" beside a PDF and ZIP hash that did not match the files a customer
would download, and nothing said so.

The two came from different moments. `ebook_export_identity` is stamped when
design preflight last ran; the downloadable files are written later, by a
separate packaging pass that recorded its hash in an unrelated top-level key
and never refreshed the identity block. `artifact_revision` is deliberately
held constant across packaging, so nothing changed to signal the divergence.

A hash a customer cannot reproduce is worse than no hash: it looks like
verification. The rule these tests hold to is that a hash is shown only when it
was read from the bytes now on disk.

No external call is made by any test here.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from services.ebook_revision_identity import (  # noqa: E402
    approvals_match_current_revision,
    certified_pdf_sha256,
    current_package_id,
    customer_download_refs,
    reconcile,
    stamp_current_revision,
    workspace_export_action,
)

PDF_BYTES = b"%PDF-1.4\n% a small but real-looking file\n%%EOF\n"
ZIP_BYTES = b"PK\x03\x04" + b"\x00" * 40


def _sha(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


class _Package(unittest.TestCase):
    """A book with real files on disk under its own package id."""

    def setUp(self):
        import services.ebook_package as pkg

        self.root = Path(tempfile.mkdtemp(prefix="revid_"))
        self._old_exports = pkg.EXPORTS_DIR
        pkg.EXPORTS_DIR = str(self.root)
        self.addCleanup(setattr, pkg, "EXPORTS_DIR", self._old_exports)

        self.package_id = "revision-identity-fixture"
        self.dir = self.root / self.package_id
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "ebook.pdf").write_bytes(PDF_BYTES)
        (self.dir / "package.zip").write_bytes(ZIP_BYTES)

    def _data(self, **over):
        data = {
            "export_package_id": self.package_id,
            "artifact_revision": 3,
            "ebook_export_identity": {
                "pdf_sha256": _sha(PDF_BYTES),
                "zip_sha256": _sha(ZIP_BYTES),
                "preview_digest": "preview-digest",
            },
        }
        data.update(over)
        return data


class WhatMayBeDisplayedTests(_Package):
    def test_hashes_that_match_the_files_are_shown(self):
        identity = reconcile(self._data())
        self.assertTrue(identity.verified)
        self.assertFalse(identity.stale)
        self.assertEqual(identity.pdf_sha256, _sha(PDF_BYTES))
        self.assertEqual(identity.as_public_dict()["zip_sha256"], _sha(ZIP_BYTES))

    def test_a_hash_from_another_revision_is_never_displayed_as_if_current(self):
        """The exact defect: stored hash belongs to an earlier build."""
        data = self._data(ebook_export_identity={
            "pdf_sha256": _sha(b"an earlier revision"),
            "zip_sha256": _sha(b"an earlier zip"),
        })
        identity = reconcile(data)
        self.assertTrue(identity.stale)
        public = identity.as_public_dict()
        self.assertEqual(public["pdf_sha256"], _sha(PDF_BYTES),
                         "the displayed hash must come from the file on disk")
        self.assertNotEqual(public["pdf_sha256"], _sha(b"an earlier revision"))
        self.assertIn("earlier revision", " ".join(public["findings"]))

    def test_no_files_means_no_hashes_rather_than_stale_ones(self):
        for name in ("ebook.pdf", "package.zip"):
            (self.dir / name).unlink()
        public = reconcile(self._data()).as_public_dict()
        self.assertEqual(public["pdf_sha256"], "")
        self.assertEqual(public["zip_sha256"], "")
        self.assertFalse(public["verified"])
        self.assertTrue(public["stale"])

    def test_a_book_with_no_package_yet_says_so_calmly(self):
        identity = reconcile({"artifact_revision": 1})
        self.assertFalse(identity.verified)
        self.assertFalse(identity.stale)
        self.assertIn("no export package", " ".join(identity.findings))

    def test_a_package_id_that_is_not_a_package_id_is_refused(self):
        self.assertEqual(current_package_id({"export_package_id": "../../etc"}), "")
        self.assertEqual(current_package_id({"package_id": "fine-id_1"}), "fine-id_1")


class StampingTests(_Package):
    def test_packaging_records_the_bytes_it_just_wrote(self):
        data = self._data(ebook_export_identity={"pdf_sha256": "stale", "zip_sha256": "stale"})
        stamp_current_revision(data)
        self.assertEqual(data["ebook_export_identity"]["pdf_sha256"], _sha(PDF_BYTES))
        self.assertEqual(data["ebook_export_identity"]["zip_sha256"], _sha(ZIP_BYTES))
        self.assertEqual(data["ebook_export_identity"]["verified_at_revision"], 3)

    def test_the_two_parallel_keys_are_kept_in_step(self):
        """Packaging used to write its own hash into an unrelated key."""
        data = self._data()
        stamp_current_revision(data)
        self.assertEqual(data["pdf_sha256"], data["ebook_export_identity"]["pdf_sha256"])
        self.assertEqual(data["zip_sha256"], data["ebook_export_identity"]["zip_sha256"])

    def test_stamping_after_a_rebuild_clears_the_mismatch(self):
        data = self._data(ebook_export_identity={"pdf_sha256": "from-an-old-build"})
        self.assertTrue(reconcile(data).stale)
        stamp_current_revision(data)
        self.assertFalse(reconcile(data).stale)

    def test_nothing_is_stamped_when_there_is_nothing_to_read(self):
        (self.dir / "ebook.pdf").unlink()
        data = self._data()
        before = dict(data["ebook_export_identity"])
        stamp_current_revision(data)
        self.assertEqual(data["ebook_export_identity"], before)

    def test_a_verification_rerender_cannot_replace_an_approved_packages_digest(self):
        """An ACCEPTED package: a re-render must never silently replace it."""
        certified = _sha(PDF_BYTES)
        data = self._data(
            artifact_state="APPROVED",
            ebook_export_identity={
                "pdf_sha256": certified,
                "zip_sha256": _sha(ZIP_BYTES),
                "preview_digest": certified,
            },
        )
        (self.dir / "ebook.pdf").write_bytes(PDF_BYTES + b"\n")
        stamp_current_revision(data)
        self.assertEqual(data["ebook_export_identity"]["pdf_sha256"], certified)
        self.assertEqual(data["ebook_export_identity"]["preview_digest"], certified)
        self.assertEqual(certified_pdf_sha256(data), certified)
        self.assertEqual(workspace_export_action(data), "keep_existing")

    def test_a_draft_whose_identity_changed_rebuilds_instead_of_serving_stale_bytes(self):
        """The exact Project 351 failure: a DRAFT edit must not keep serving
        the pre-edit PDF/ZIP forever while every screen reports a new hash.

        Unlike the APPROVED case above, a DRAFT project's certified identity
        is expected to move whenever the project is edited -- so a mismatch
        here means "rebuild", not "protect what's on disk".
        """
        certified = _sha(PDF_BYTES)
        data = self._data(ebook_export_identity={
            "pdf_sha256": certified,
            "zip_sha256": _sha(ZIP_BYTES),
            "preview_digest": certified,
        })
        from services.quality.artifact_state import ArtifactState, resolve_artifact_state

        self.assertEqual(resolve_artifact_state(data), ArtifactState.DRAFT)
        (self.dir / "ebook.pdf").write_bytes(PDF_BYTES + b"\n")
        stamp_current_revision(data)
        self.assertEqual(certified_pdf_sha256(data), certified)
        self.assertEqual(workspace_export_action(data), "render")


class ApprovalsCannotBeStaleTests(_Package):
    def test_matching_files_and_approvals_agree(self):
        ok, findings = approvals_match_current_revision(self._data())
        self.assertTrue(ok, findings)

    def test_approvals_beside_another_revisions_files_are_reported(self):
        data = self._data(ebook_export_identity={"pdf_sha256": _sha(b"different")})
        ok, findings = approvals_match_current_revision(data)
        self.assertFalse(ok)
        self.assertIn("earlier revision", " ".join(findings))


def _function_body(src: str, name: str) -> str:
    """Source of one top-level function, up to the next one or end of file.

    The obvious version searches for the next "\\ndef " and blows up with
    "substring not found" when the function happens to be the last in its file
    — which design_public_view is. A source-reading assertion must not depend
    on something else being defined below it.
    """
    start = src.index(name)
    following = src.find("\ndef ", start + len(name))
    if following == -1:
        following = src.find("\nclass ", start + len(name))
    return src[start: following if following != -1 else len(src)]


class TheDisplayPathUsesReconciliationTests(unittest.TestCase):
    def test_design_public_view_does_not_show_the_stored_block_unchecked(self):
        src = (ROOT / "services" / "ebook_design_workspace.py").read_text(encoding="utf-8")
        body = _function_body(src, "def design_public_view")
        self.assertIn("reconcile", body,
                      "the screen still displays the stored identity unchecked")

    def test_packaging_stamps_the_revision_it_produced(self):
        src = (ROOT / "services" / "ebook_build_orchestrator.py").read_text(encoding="utf-8")
        body = _function_body(src, "def _run_export")
        self.assertIn("stamp_current_revision", body)

    def test_workspace_packaging_reuses_the_certified_package_before_rerender(self):
        src = (ROOT / "services" / "packaging.py").read_text(encoding="utf-8")
        body = _function_body(src, "def build_product_export")
        reuse = body.index("workspace_export_action")
        render = body.index("apply_workspace_design_to_export")
        self.assertLess(
            reuse, render,
            "workspace export still re-renders before checking the certified package",
        )

    def test_download_context_carries_the_certified_preview_digest(self):
        src = (ROOT / "services" / "quality" / "download_pipeline_agent.py").read_text(
            encoding="utf-8"
        )
        body = _function_body(src, "def resolve_download_request")
        self.assertIn("ebook_preview_digest", body)

    def test_customer_download_refs_name_one_package(self):
        refs = customer_download_refs({
            "export_package_id": "ebook-351-warm-wellness-final",
            "package_id": "other-id",
            "artifact_id": "ebook-351-warm-wellness-final",
        })
        self.assertEqual(refs["package_id"], "ebook-351-warm-wellness-final")
        self.assertEqual(refs["pdf_url"], "/download/ebook-351-warm-wellness-final/ebook.pdf")
        self.assertEqual(refs["zip_url"], "/download/ebook-351-warm-wellness-final/package.zip")

    def test_the_helper_handles_a_function_at_the_end_of_a_file(self):
        """The bug this file shipped with, caught in the helper itself."""
        self.assertEqual(_function_body("def only():\n    return 1\n", "def only"),
                         "def only():\n    return 1\n")
        self.assertEqual(_function_body("def a():\n    pass\ndef b():\n    pass\n", "def a"),
                         "def a():\n    pass")


class WorkspaceExportReusesCertifiedPackageTests(_Package):
    def test_packaging_does_not_rerender_when_the_certified_files_are_present(self):
        from unittest.mock import patch

        import services.packaging as packaging_mod
        from services.packaging import build_product_export

        data = self._data()
        data["ebook_workspace"] = {"rail": {}}
        data["product_type"] = "ebook"
        data["artifact_state"] = "DRAFT"
        data["ebook_export_identity"]["preview_digest"] = _sha(PDF_BYTES)
        project = {"id": 3510, "type": "ebook", "data": data}
        before_pdf = (self.dir / "ebook.pdf").read_bytes()
        before_zip = (self.dir / "package.zip").read_bytes()
        with patch.object(packaging_mod, "EXPORTS_DIR", str(self.root)), patch(
            "services.ebook_design_export.apply_workspace_design_to_export",
            side_effect=AssertionError("must not re-render a certified package"),
        ):
            result = build_product_export(project)
        self.assertEqual(result["package_id"], self.package_id)
        self.assertEqual((self.dir / "ebook.pdf").read_bytes(), before_pdf)
        self.assertEqual((self.dir / "package.zip").read_bytes(), before_zip)
        self.assertEqual(result["exports"]["files"]["pdf"]["sha256"], _sha(PDF_BYTES))
        self.assertEqual(result["exports"]["files"]["zip"]["sha256"], _sha(ZIP_BYTES))

    def test_a_draft_with_a_changed_identity_rerenders_instead_of_reusing_stale_files(self):
        """The Project 351 failure at the full build_product_export level, not
        just workspace_export_action() in isolation: a DRAFT project whose
        content changed (here standing in for a corrected caption) must
        actually get a fresh PDF/ZIP, not the old bytes with a new-looking
        hash bolted on."""
        from unittest.mock import patch

        import services.packaging as packaging_mod
        from services.packaging import build_product_export

        new_pdf = b"%PDF-1.4\n% the corrected re-render\n%%EOF\n"
        new_zip = b"PK\x03\x04" + b"\x01" * 40

        data = self._data()
        data["ebook_workspace"] = {"rail": {}}
        data["product_type"] = "ebook"
        data["artifact_state"] = "DRAFT"
        # build_product_export's render branch resolves its OUTPUT directory
        # from data["package_id"] specifically (export_package_id is what the
        # reuse/keep_existing check above it reads) -- set to the same
        # package this fixture's stale files already live under.
        data["package_id"] = self.package_id
        # The certified identity has already moved (the preview rebuild
        # after a content fix stamps this) but the OLD files are still what
        # is sitting on disk from before that fix -- exactly the mismatch
        # that used to trigger "keep_existing" regardless of lifecycle state.
        data["ebook_export_identity"]["preview_digest"] = _sha(b"a corrected render, not on disk yet")
        project = {"id": 3511, "type": "ebook", "data": data}

        def _fake_rerender(proj):
            proj = dict(proj)
            proj["data"] = dict(proj["data"])
            proj["_design_export_pdf"] = new_pdf
            proj["_design_export_zip"] = new_zip
            return proj

        with patch.object(packaging_mod, "EXPORTS_DIR", str(self.root)), patch(
            "services.ebook_design_export.apply_workspace_design_to_export",
            side_effect=_fake_rerender,
        ) as rerender:
            result = build_product_export(project)
        rerender.assert_called_once()
        self.assertEqual((self.dir / "ebook.pdf").read_bytes(), new_pdf)
        self.assertEqual((self.dir / "package.zip").read_bytes(), new_zip)
        self.assertEqual(result["exports"]["files"]["pdf"]["sha256"], _sha(new_pdf))
        self.assertEqual(result["exports"]["files"]["zip"]["sha256"], _sha(new_zip))


def _readable_pdf() -> bytes:
    import io

    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    page = canvas.Canvas(buf)
    page.drawString(72, 720, "Revision identity fixture")
    page.save()
    return buf.getvalue()


class CustomerDownloadSameBytesTests(unittest.TestCase):
    def test_two_saved_projects_downloads_are_byte_identical_to_the_certified_files(self):
        import services.ebook_package as pkg
        from app import app

        import zipfile
        from io import BytesIO

        pdf_bytes = _readable_pdf()
        zip_buf = BytesIO()
        with zipfile.ZipFile(zip_buf, "w") as zf:
            zf.writestr("ebook.pdf", pdf_bytes)
        zip_bytes = zip_buf.getvalue()
        package_id = "revision-identity-download-fixture"
        folder = Path(pkg.EXPORTS_DIR) / package_id
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "ebook.pdf").write_bytes(pdf_bytes)
        (folder / "package.zip").write_bytes(zip_bytes)
        self.addCleanup(shutil.rmtree, folder, True)

        data = {
            "export_package_id": package_id,
            "package_id": package_id,
            "artifact_id": package_id,
            "artifact_revision": 1,
            "artifact_state": "DRAFT",
            "product_type": "ebook",
            "ebook_workspace": {"rail": {}},
            "ebook_export_identity": {
                "pdf_sha256": _sha(pdf_bytes),
                "zip_sha256": _sha(zip_bytes),
                "preview_digest": _sha(pdf_bytes),
            },
            "product_exports": {
                "pdf_available": True,
                "files": {
                    "pdf": {
                        "name": "product.pdf",
                        "url": f"/download/{package_id}/ebook.pdf",
                        "sha256": _sha(pdf_bytes),
                    },
                    "zip": {
                        "name": "product.zip",
                        "url": f"/download/{package_id}/package.zip",
                        "sha256": _sha(zip_bytes),
                    },
                },
            },
        }
        client = app.test_client()
        created = client.post(
            "/projects",
            json={
                "name": "Revision identity download fixture",
                "type": "ebook",
                "user_saved": True,
                "system_test": True,
                "temporary": True,
                "data": data,
            },
        )
        self.assertEqual(created.status_code, 201, created.data)
        pid = created.get_json()["id"]
        try:
            first_pdf = client.get(f"/download/{package_id}/ebook.pdf")
            second_pdf = client.get(f"/download/{package_id}/ebook.pdf")
            first_zip = client.get(f"/download/{package_id}/package.zip")
            second_zip = client.get(f"/download/{package_id}/package.zip")
            self.assertEqual(first_pdf.status_code, 200, first_pdf.data[:300])
            self.assertEqual(second_pdf.status_code, 200, second_pdf.data[:300])
            self.assertEqual(first_zip.status_code, 200, first_zip.data[:300])
            self.assertEqual(second_zip.status_code, 200, second_zip.data[:300])
            self.assertEqual(first_pdf.data, second_pdf.data)
            self.assertEqual(first_zip.data, second_zip.data)
            self.assertEqual(_sha(first_pdf.data), _sha(pdf_bytes))
            self.assertEqual(_sha(first_zip.data), _sha(zip_bytes))
        finally:
            client.delete(f"/projects/{pid}")


if __name__ == "__main__":
    unittest.main()
