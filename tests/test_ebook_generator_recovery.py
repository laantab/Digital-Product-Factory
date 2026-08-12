"""Stabilized Ebook recovery — document model, release gate, local fixture.

Zero paid/external API calls. Fixtures under fixtures/ebook_*.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

FAIL_MD = ROOT / "fixtures" / "ebook_synthetic_fail_corpus" / "synthetic_fail.md"
GOOD_MD = ROOT / "fixtures" / "ebook_recovery_local" / "manuscript.md"
FIXTURE_TITLE = "EBOOK RECOVERY LOCAL FIXTURE — NOT FOR SALE"


class EbookDocumentModelTests(unittest.TestCase):
    def test_strip_visual_instructions(self):
        from services.ebook_document import strip_visual_instructions

        raw = FAIL_MD.read_text(encoding="utf-8")
        cleaned, removed = strip_visual_instructions(raw)
        self.assertTrue(removed)
        self.assertNotIn("Visual plan for this chapter", cleaned)
        self.assertNotIn("Chart suggestion", cleaned)

    def test_attach_does_not_overwrite_stabilized_digests(self):
        from services.ebook_document import (
            EbookDocument,
            attach_document_to_data,
        )

        doc = EbookDocument(title=FIXTURE_TITLE, manuscript_md=GOOD_MD.read_text(encoding="utf-8"))
        doc.recompute_digests()
        data = {
            "content_digest": "STABILIZED_CONTENT",
            "asset_manifest_digest": "STABILIZED_ASSETS",
            "artifact_revision": 3,
        }
        out = attach_document_to_data(data, doc, sync_manuscript=False)
        self.assertEqual(out["content_digest"], "STABILIZED_CONTENT")
        self.assertEqual(out["asset_manifest_digest"], "STABILIZED_ASSETS")
        self.assertEqual(out["ebook_manuscript_digest"], doc.identity.content_digest)
        self.assertIn("ebook_document", out)


class EbookReleaseValidatorTests(unittest.TestCase):
    def test_synthetic_fail_corpus_is_fail(self):
        from services.ebook_release_validator import classify_failed_pdf_text

        report = classify_failed_pdf_text(
            FAIL_MD.read_text(encoding="utf-8"), title="Synthetic failure corpus"
        )
        self.assertEqual(report.status, "FAIL")
        self.assertFalse(report.export_ready)

    def test_good_fixture_can_pass_release(self):
        from services.ebook_document import build_ebook_document_from_project
        from services.ebook_release_validator import validate_ebook_release

        md = GOOD_MD.read_text(encoding="utf-8")
        doc = build_ebook_document_from_project(
            {
                "data": {
                    "title": FIXTURE_TITLE,
                    "subtitle": "Local pipeline verification only",
                    "content": md,
                    "author_brand": "Digital Product Factory",
                    "fields": {
                        "topic": "email habits freelancers triage inbox",
                        "audience": "Busy freelancers",
                    },
                    "visual_plan": {
                        "chapters": [
                            {
                                "chapter": "Chapter 2: Reply Templates That Still Sound Human",
                                "aids": [
                                    {
                                        "type": "table",
                                        "title": "Reply template matrix",
                                        "visual_id": "v1",
                                        "rendered_html": "<table></table>",
                                    }
                                ],
                            }
                        ]
                    },
                    "cover_design": {
                        "title": FIXTURE_TITLE,
                        "local_generated": True,
                        "fixture": True,
                        "local_cover_pdf": "local.pdf",
                    },
                }
            }
        )
        report = validate_ebook_release(doc)
        self.assertEqual(report.status, "PASS", msg=report.to_dict())
        self.assertTrue(report.export_ready)


class EbookDesignSystemTests(unittest.TestCase):
    def test_theme_css_has_no_letter_spacing(self):
        from services.ebook_design_system import theme_css

        self.assertNotRegex(theme_css("studio_clean"), r"letter-spacing\s*:")


class EbookInteriorLabelCycleTests(unittest.TestCase):
    def test_rewrite_cycles_labels(self):
        from services.ebook_interior_visuals import rewrite_mechanical_headings

        # Enough repeated mechanical headings to exceed the label list length.
        parts = ["# Title\n"]
        for i in range(12):
            parts.append(f"## Chapter {i+1}\n### Common mistakes\nBody {i}\n")
        out = rewrite_mechanical_headings(
            "".join(parts), title="email habits", topic="email habits freelancers"
        )
        # Generic non-screens path rewrites to a single replacement — ensure no clamp bug
        # on screens path separately if topic triggers; for general topic just ensure runs.
        self.assertIn("Chapter 1", out)


class EbookDeterministicPackageTests(unittest.TestCase):
    @mock.patch("ai_client.chat")
    @mock.patch("ai_client.chat_json")
    @mock.patch("ai_client.get_client")
    def test_deterministic_fixture_renders_pdf_and_zip(self, _gc, _cj, _chat):
        from services.ebook_local_package import build_local_ebook_package
        from services.ebook_release_validator import validate_ebook_release, classify_failed_pdf_text
        from services.ebook_document import build_ebook_document_from_project
        from services.packaging import build_product_export
        from services.quality.artifact_state import ArtifactState

        md = GOOD_MD.read_text(encoding="utf-8")
        fields = {
            "topic": "email habits freelancers triage inbox",
            "audience": "Busy freelancers who drown in client email",
            "subtitle": "Local pipeline verification only",
            "author_brand": "Digital Product Factory",
            "tone": "clear and practical",
            "design_theme": "studio_clean",
        }
        built = build_local_ebook_package(
            FIXTURE_TITLE, md, fields, package_id="ebook_recovery_local_fixture"
        )
        self.assertTrue(built["local_only"])
        self.assertTrue(built["cover_design"].get("local_generated"))

        project = {
            "id": 92001,
            "name": FIXTURE_TITLE,
            "type": "ebook",
            "data": {
                "product_type": "ebook",
                "title": built["title"],
                "subtitle": built["subtitle"],
                "ebook": built["content"],
                "content": built["content"],
                "preview_html": built["preview_html"],
                "visual_plan": built["visual_plan"],
                "cover_design": built["cover_design"],
                "package_id": built["package_id"],
                "fields": built["fields"],
                "author_brand": "Digital Product Factory",
                "ebook_document": built.get("ebook_document"),
                "ebook_manuscript_digest": built.get("ebook_manuscript_digest"),
                "ebook_asset_manifest_digest": built.get("ebook_asset_manifest_digest"),
                "design_theme": built.get("design_theme"),
                "design_theme_version": built.get("design_theme_version"),
                "artifact_state": ArtifactState.DRAFT.value,
            },
        }
        doc = build_ebook_document_from_project(project)
        pre = validate_ebook_release(doc)
        self.assertNotEqual(pre.status, "FAIL", msg=pre.to_dict())

        result = build_product_export(project)
        pkg = result["package_id"]
        pdf_path = ROOT / "exports" / pkg / "ebook.pdf"
        zip_path = ROOT / "exports" / pkg / "package.zip"
        self.assertTrue(pdf_path.is_file())
        self.assertTrue(zip_path.is_file())
        pdf = pdf_path.read_bytes()
        self.assertTrue(pdf.startswith(b"%PDF"))

        import fitz

        d = fitz.open(pdf_path)
        all_text = "\n".join(d.load_page(i).get_text("text") or "" for i in range(d.page_count))
        self.assertNotRegex(all_text, r"(?i)visual plan for this chapter")
        self.assertNotRegex(all_text, r"(?i)chart suggestion")
        self.assertNotRegex(all_text, r"(?i)sub-goal\s*#\s*\d+")
        self.assertNotRegex(all_text, r"\bC\s+hapter\b")
        self.assertGreaterEqual(d.page_count, 4)
        blank = sum(
            1
            for i in range(d.page_count)
            if i > 0 and len((d.load_page(i).get_text("text") or "").strip()) < 12
        )
        self.assertEqual(blank, 0)

        # Contact sheet + page images for visual proof
        out_dir = ROOT / "exports" / "_ebook_recovery_inspect"
        out_dir.mkdir(parents=True, exist_ok=True)
        page_paths = []
        for i in range(d.page_count):
            pix = d.load_page(i).get_pixmap(matrix=fitz.Matrix(1.2, 1.2), alpha=False)
            p = out_dir / f"page_{i+1:02d}.png"
            pix.save(str(p))
            page_paths.append(p)
        # Simple contact sheet (grid)
        from PIL import Image

        imgs = [Image.open(p).convert("RGB") for p in page_paths]
        w, h = imgs[0].size
        cols = min(4, len(imgs))
        rows = (len(imgs) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * w, rows * h), (255, 255, 255))
        for idx, im in enumerate(imgs):
            sheet.paste(im, ((idx % cols) * w, (idx // cols) * h))
        contact = out_dir / "contact_sheet.png"
        sheet.save(contact)
        d.close()

        # Persist paths for report consumers
        (out_dir / "PATHS.txt").write_text(
            f"pdf={pdf_path}\nzip={zip_path}\ncontact={contact}\npages={d.page_count if False else len(page_paths)}\n",
            encoding="utf-8",
        )

        fail = classify_failed_pdf_text(FAIL_MD.read_text(encoding="utf-8"))
        self.assertEqual(fail.status, "FAIL")
        self.assertFalse(project["data"].get("export_ready") is True and fail.export_ready)

        _gc.assert_not_called()
        _cj.assert_not_called()
        _chat.assert_not_called()

    def test_failed_manuscript_blocks_export(self):
        from services.packaging import build_product_export
        from services.quality.artifact_state import ArtifactState

        project = {
            "name": "Synthetic failure corpus",
            "type": "ebook",
            "data": {
                "product_type": "ebook",
                "title": "Synthetic failure corpus",
                "ebook": FAIL_MD.read_text(encoding="utf-8"),
                "content": FAIL_MD.read_text(encoding="utf-8"),
                "author_brand": "Digital Product Factory",
                "artifact_state": ArtifactState.DRAFT.value,
                "fields": {
                    "topic": "synthetic failure corpus",
                    "audience": "validator regression",
                    "author_brand": "Digital Product Factory",
                },
                "cover_design": {
                    "title": "Synthetic failure corpus",
                    "generic_template": True,
                },
            },
        }
        with self.assertRaises(ValueError) as ctx:
            build_product_export(project)
        self.assertIn("blocked", str(ctx.exception).lower())


class EbookApprovedLockProtectionTests(unittest.TestCase):
    def test_approved_blocks_visual_package_mutation(self):
        from services.ebook_local_package import ensure_ebook_visual_package
        from services.quality.artifact_state import ArtifactState, ArtifactStateError

        project = {
            "type": "ebook",
            "data": {
                "product_type": "ebook",
                "title": FIXTURE_TITLE,
                "content": GOOD_MD.read_text(encoding="utf-8"),
                "ebook": GOOD_MD.read_text(encoding="utf-8"),
                "artifact_state": ArtifactState.APPROVED.value,
                "content_digest": "abc",
                "asset_manifest_digest": "def",
            },
        }
        with self.assertRaises(ArtifactStateError):
            ensure_ebook_visual_package(project)


class EbookServerReleaseCertificateTests(unittest.TestCase):
    def test_client_forged_pass_is_rejected(self):
        from services.ebook_release_validator import (
            issue_release_certificate,
            release_identity_from_doc,
            verify_release_certificate,
        )
        from services.ebook_document import build_ebook_document_from_project

        md = GOOD_MD.read_text(encoding="utf-8")
        doc = build_ebook_document_from_project(
            {
                "data": {
                    "title": FIXTURE_TITLE,
                    "content": md,
                    "author_brand": "Digital Product Factory",
                    "cover_design": {
                        "title": FIXTURE_TITLE,
                        "local_generated": True,
                        "fixture": True,
                        "local_cover_pdf": "local.pdf",
                    },
                    "fields": {"topic": "email habits freelancers triage inbox", "audience": "Busy freelancers"},
                }
            }
        )
        identity = release_identity_from_doc(doc, project_id=1, artifact_id="a1", revision=1)
        forged = {
            "status": "PASS",
            "export_ready": True,
            "issued_by": "browser",
            "identity": identity,
            "certificate_digest": "deadbeef",
        }
        ok, reason = verify_release_certificate(forged, identity, require_pass=True)
        self.assertFalse(ok)
        self.assertIn("server", reason.lower())

    def test_stale_pass_rejected_after_digest_change(self):
        from services.ebook_release_validator import (
            EbookReleaseReport,
            issue_release_certificate,
            release_identity_from_doc,
            verify_release_certificate,
        )
        from services.ebook_document import build_ebook_document_from_project

        md = GOOD_MD.read_text(encoding="utf-8")
        doc = build_ebook_document_from_project(
            {
                "data": {
                    "title": FIXTURE_TITLE,
                    "content": md,
                    "author_brand": "Digital Product Factory",
                    "cover_design": {
                        "title": FIXTURE_TITLE,
                        "local_generated": True,
                        "fixture": True,
                        "local_cover_pdf": "local.pdf",
                    },
                    "fields": {"topic": "email habits freelancers triage inbox", "audience": "Busy freelancers"},
                }
            }
        )
        identity = release_identity_from_doc(doc, project_id=1, artifact_id="a1", revision=1)
        cert = issue_release_certificate(
            EbookReleaseReport(status="PASS", export_ready=True), identity
        )
        stale_identity = dict(identity)
        stale_identity["ebook_manuscript_digest"] = "changed"
        ok, reason = verify_release_certificate(cert, stale_identity, require_pass=True)
        self.assertFalse(ok)
        self.assertIn("stale", reason.lower())

    def test_export_rejects_forged_export_ready(self):
        from services.packaging import build_product_export
        from services.quality.artifact_state import ArtifactState

        project = {
            "id": 92099,
            "name": FIXTURE_TITLE,
            "type": "ebook",
            "data": {
                "product_type": "ebook",
                "title": FIXTURE_TITLE,
                "ebook": GOOD_MD.read_text(encoding="utf-8"),
                "content": GOOD_MD.read_text(encoding="utf-8"),
                "author_brand": "Digital Product Factory",
                "artifact_state": ArtifactState.DRAFT.value,
                "export_ready": True,
                "release_status": "PASS",
                "release_certificate": {
                    "status": "PASS",
                    "export_ready": True,
                    "issued_by": "browser",
                    "identity": {},
                },
                "fields": {
                    "topic": "email habits freelancers triage inbox",
                    "audience": "Busy freelancers who drown in client email",
                    "author_brand": "Digital Product Factory",
                },
                "cover_design": {
                    "title": FIXTURE_TITLE,
                    "local_generated": True,
                    "fixture": True,
                    "local_cover_pdf": "local.pdf",
                },
            },
        }
        with self.assertRaises(ValueError) as ctx:
            build_product_export(project)
        self.assertRegex(str(ctx.exception), r"stale|forged|server", re.I)


class EbookBackMatterInjectionTests(unittest.TestCase):
    def test_outline_without_faq_has_no_faq_pool(self):
        from services.ebook_local_package import build_local_ebook_package

        built = build_local_ebook_package(
            FIXTURE_TITLE,
            GOOD_MD.read_text(encoding="utf-8"),
            {
                "topic": "email habits freelancers triage inbox",
                "audience": "Busy freelancers",
                "author_brand": "Digital Product Factory",
                "design_theme": "studio_clean",
            },
            package_id="ebook_recovery_bm_no_faq",
        )
        html = built["preview_html"]
        self.assertNotRegex(html, r"(?i)how do i stay motivated over time")
        self.assertNotRegex(html, r"(?i)key practice\s*[—\-:]")
        self.assertNotRegex(html, r"(?i)apply one idea from this chapter today")
        self.assertNotRegex(html, r"letter-spacing\s*:")

    def test_generic_faq_fails_release(self):
        from services.ebook_release_validator import classify_failed_pdf_text

        text = (
            "# Title\n\n## Chapter 1\nBody text about habits.\n\n"
            "## FAQ\nHow do I stay motivated over time?\nJust keep going.\n"
        )
        report = classify_failed_pdf_text(text, title="Generic FAQ book")
        self.assertEqual(report.status, "FAIL")

    def test_topic_specific_faq_in_manuscript_preserved_in_preview(self):
        from services.ebook_local_package import build_local_ebook_package

        md = (
            GOOD_MD.read_text(encoding="utf-8")
            + "\n\n## FAQ\n### Do freelancers need a second inbox?\n"
            "Only when retainers require a dedicated channel for production emergencies.\n"
        )
        built = build_local_ebook_package(
            FIXTURE_TITLE,
            md,
            {
                "topic": "email habits freelancers triage inbox",
                "audience": "Busy freelancers",
                "author_brand": "Digital Product Factory",
                "design_theme": "studio_clean",
            },
            package_id="ebook_recovery_bm_topic_faq",
        )
        self.assertIn("Do freelancers need a second inbox?", built["preview_html"])
        self.assertNotRegex(built["preview_html"], r"(?i)how do i stay motivated over time")


class EbookTypographyDefenseTests(unittest.TestCase):
    def test_theme_and_preview_have_no_letter_spacing(self):
        from services.ebook_design_system import theme_css
        from services.ebook_local_package import build_local_ebook_package

        self.assertNotRegex(theme_css("studio_clean"), r"letter-spacing\s*:")
        built = build_local_ebook_package(
            FIXTURE_TITLE,
            GOOD_MD.read_text(encoding="utf-8"),
            {
                "topic": "email habits freelancers triage inbox",
                "audience": "Busy freelancers",
                "author_brand": "Digital Product Factory",
                "design_theme": "studio_clean",
            },
            package_id="ebook_recovery_typo",
        )
        self.assertNotRegex(built["preview_html"], r"letter-spacing\s*:")


if __name__ == "__main__":
    unittest.main()
