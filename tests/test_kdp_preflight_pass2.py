"""KDP Implementation Pass 2: combined preflight validator, UI gate, package gate.

Zero paid/external calls. Does not regenerate locked PDFs or invent Amazon uploads.
"""
from __future__ import annotations

import base64
import hashlib
import os
import sys
import unittest
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
from services.kdp.preflight import (  # noqa: E402
    RESULT_FAIL,
    RESULT_PASS,
    RESULT_WARNING,
    KdpPreflightError,
    assert_prepare_kdp_package_allowed,
    run_kdp_preflight,
)

VALID_ISBN13 = "9780306406157"

# Minimal valid PDF header for digest/identity tests (not a regenerated product).
_MIN_PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def _pdf_b64(data: bytes = _MIN_PDF) -> str:
    return base64.b64encode(data).decode("ascii")


def _approved_coloring(**extra):
    pdf = _MIN_PDF
    digest = hashlib.sha256(pdf).hexdigest()
    base = {
        "product_type": "coloring_book",
        "title": "Pass2 Coloring Book",
        "package_id": "kdp-pass2-coloring-001",
        "artifact_id": "kdp-pass2-coloring-001",
        "artifact_revision": 2,
        "artifact_state": "APPROVED",
        "content_digest": digest,
        "asset_manifest_digest": "c" * 64,
        "qa_status": "accepted",
        "pdf_bytes": _pdf_b64(pdf),
        "page_count": 100,
        "is_pdf": True,
        "pages": [
            {"id": f"p{i}", "image": f"img_{i}.png", "content": "line art"}
            for i in range(1, 101)
        ],
    }
    # Recompute asset digest to match pages/title
    from services.quality.artifact_identity import asset_manifest_digest

    base["asset_manifest_digest"] = asset_manifest_digest(base)
    base.update(extra)
    if "pages" in extra or "title" in extra:
        base["asset_manifest_digest"] = asset_manifest_digest(base)
    return base


def _print_ok():
    return {
        "binding": "paperback",
        "ink": "black",
        "paper": "white",
        "trim_width_in": "6",
        "trim_height_in": "9",
        "has_bleed": True,
        "page_count": 100,
    }


def _meta_ok(**extra):
    m = {
        "title": "Pass2 Coloring Book",
        "author": "Test Author",
        "description": "A complete activity coloring book for kids.",
        "isbn_option": "kdp_free",
        "product_type": "coloring_book",
    }
    m.update(extra)
    return m


def _ai_none():
    return {"text": "none", "images": "none", "translations": "none"}


def _ai_generated():
    return {"text": "ai_generated", "images": "ai_generated", "translations": "none"}


def _ai_assisted():
    return {"text": "ai_assisted", "images": "none", "translations": "none"}


class KdpPreflightPass2Tests(unittest.TestCase):
    def test_01_valid_paperback_profile_passes(self):
        data = _approved_coloring()
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(result.overall, RESULT_PASS)
        self.assertTrue(result.package_allowed)
        self.assertIsNotNone(result.print_profile)
        self.assertEqual(result.print_profile["trim_label"], '6" x 9"')

    def test_02_invalid_trim_bleed_margin_spine_fail(self):
        data = _approved_coloring()
        bad = _print_ok()
        bad["trim_width_in"] = "3"
        bad["trim_height_in"] = "3"
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=bad,
            metadata=_meta_ok(),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(result.overall, RESULT_FAIL)
        self.assertTrue(any("TRIM" in f.rule_id or "PRINT" in f.rule_id for f in result.findings))

        missing_pages = dict(_print_ok())
        missing_pages.pop("page_count", None)
        data2 = _approved_coloring()
        data2.pop("page_count", None)
        data2["pages"] = None
        # force no page count resolution
        data2.pop("pages", None)
        with patch("services.kdp.preflight.decode_pdf_bytes", return_value=b""):
            result2 = run_kdp_preflight(
                data2,
                publication_format="paperback",
                print_settings={
                    "binding": "paperback",
                    "ink": "black",
                    "paper": "white",
                    "trim_width_in": "6",
                    "trim_height_in": "9",
                    "has_bleed": True,
                },
                metadata=_meta_ok(title=data2["title"]),
                ai_disclosure=_ai_none(),
            )
        self.assertEqual(result2.overall, RESULT_FAIL)
        self.assertTrue(any(f.rule_id == "KDP-PAGE-COUNT-MISSING" for f in result2.findings))

    def test_03_hardcover_fails_closed(self):
        data = _approved_coloring()
        result = run_kdp_preflight(
            data,
            publication_format="hardcover",
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(result.overall, RESULT_FAIL)
        self.assertTrue(any(f.rule_id == "KDP-FORMAT-HARDCOVER" for f in result.findings))

    def test_04_metadata_match_and_mismatch(self):
        data = _approved_coloring()
        ok = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(ok.overall, RESULT_PASS)
        self.assertFalse(any(f.rule_id == "KDP-METADATA-TITLE-MISMATCH" for f in ok.findings))

        bad = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(title="Different Title Entirely"),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(bad.overall, RESULT_FAIL)
        self.assertTrue(any(f.rule_id == "KDP-METADATA-TITLE-MISMATCH" for f in bad.findings))

    def test_05_valid_isbn_passes(self):
        data = _approved_coloring()
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(isbn_option="own", isbn=VALID_ISBN13, imprint="Test Imprint"),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(result.overall, RESULT_PASS)
        self.assertTrue(any(f.rule_id == "KDP-ISBN" and f.severity == "INFO" for f in result.findings))

    def test_06_invalid_isbn_fails(self):
        data = _approved_coloring()
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(isbn_option="own", isbn="9780306406150"),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(result.overall, RESULT_FAIL)
        self.assertTrue(any(f.rule_id == "KDP-ISBN-INVALID" for f in result.findings))

    def test_07_isbn_not_incorrectly_required_for_ebook(self):
        data = {
            "product_type": "ebook",
            "title": "Pass2 Ebook",
            "artifact_state": "APPROVED",
            "artifact_revision": 1,
            "content_digest": "a" * 64,
            "asset_manifest_digest": "b" * 64,
            "ebook": "Chapter 1\nReal content for the ebook manuscript.",
            "qa_status": "accepted",
        }
        result = run_kdp_preflight(
            data,
            publication_format="ebook",
            metadata={
                "title": "Pass2 Ebook",
                "author": "Author",
                "description": "Nonfiction ebook description.",
                "isbn_option": "none",
                "product_type": "ebook",
            },
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(result.overall, RESULT_PASS)
        self.assertFalse(any(f.rule_id == "KDP-ISBN-INVALID" for f in result.findings))

    def test_08_activity_classification(self):
        for pt in ("coloring_book", "word_search", "crossword", "math_worksheet"):
            data = _approved_coloring(product_type=pt, title=f"Pass2 {pt}")
            # fix digests after title/type change
            from services.quality.artifact_identity import asset_manifest_digest

            data["asset_manifest_digest"] = asset_manifest_digest(data)
            result = run_kdp_preflight(
                data,
                publication_format="paperback",
                print_settings=_print_ok(),
                metadata=_meta_ok(title=data["title"], product_type=pt),
                ai_disclosure=_ai_none(),
            )
            self.assertEqual(result.classification["content_class"], "activity")
            self.assertNotEqual(result.classification["content_class"], "low_content")

    def test_09_low_content_classification_separate(self):
        data = _approved_coloring(product_type="planner")
        from services.quality.artifact_identity import asset_manifest_digest

        data["asset_manifest_digest"] = asset_manifest_digest(data)
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(
                title=data["title"],
                product_type="planner",
                content_class="low_content",
                isbn_option="publish_without",
            ),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(result.classification["content_class"], "low_content")
        self.assertTrue(result.classification["low_content_checkbox_required"])

    def test_10_ai_generated_disclosure_complete(self):
        data = _approved_coloring()
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure=_ai_generated(),
        )
        self.assertEqual(result.overall, RESULT_PASS)
        self.assertTrue(result.ai_disclosure["requires_kdp_ai_generated_disclosure"])

    def test_11_ai_assisted_distinguishable(self):
        data = _approved_coloring()
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure=_ai_assisted(),
        )
        self.assertEqual(result.overall, RESULT_PASS)
        self.assertEqual(result.ai_disclosure["text"], "ai_assisted")
        self.assertFalse(result.ai_disclosure["requires_kdp_ai_generated_disclosure"])

    def test_12_unknown_provenance_blocks(self):
        data = _approved_coloring()
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure={"text": "unknown", "images": "none", "translations": "none"},
        )
        self.assertEqual(result.overall, RESULT_FAIL)
        self.assertTrue(any(f.rule_id == "KDP-AI-DISCLOSURE" for f in result.findings))

    def test_13_stale_tampered_exports_fail(self):
        data = _approved_coloring(
            export_package_id="kdp-pass2-missing-pkg",
            product_exports={
                "files": {
                    "pdf": {
                        "name": "missing.pdf",
                        "sha256": "a" * 64,
                    }
                }
            },
        )
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(result.overall, RESULT_FAIL)
        self.assertTrue(any(f.rule_id == "KDP-EXPORT-HASH" for f in result.findings))

    def test_14_failed_qa_blocks_packaging(self):
        data = _approved_coloring(qa_blocked=True, blocked_export=True)
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(result.overall, RESULT_FAIL)
        with self.assertRaises(KdpPreflightError):
            assert_prepare_kdp_package_allowed(
                data,
                preflight_token=result.preflight_token,
                print_settings=_print_ok(),
                metadata=_meta_ok(),
                ai_disclosure=_ai_none(),
                publication_format="paperback",
            )

    def test_15_pass_enables_packaging(self):
        data = _approved_coloring()
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(result.overall, RESULT_PASS)
        allowed = assert_prepare_kdp_package_allowed(
            data,
            preflight_token=result.preflight_token,
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure=_ai_none(),
            publication_format="paperback",
        )
        self.assertTrue(allowed.package_allowed)

    def test_16_warning_requires_acknowledgment(self):
        data = _approved_coloring()
        # Empty description → metadata WARNING (no FAIL)
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(description=""),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(result.overall, RESULT_WARNING)
        with self.assertRaises(KdpPreflightError):
            assert_prepare_kdp_package_allowed(
                data,
                preflight_token=result.preflight_token,
                warning_acknowledged=False,
                print_settings=_print_ok(),
                metadata=_meta_ok(description=""),
                ai_disclosure=_ai_none(),
                publication_format="paperback",
            )
        allowed = assert_prepare_kdp_package_allowed(
            data,
            preflight_token=result.preflight_token,
            warning_acknowledged=True,
            print_settings=_print_ok(),
            metadata=_meta_ok(description=""),
            ai_disclosure=_ai_none(),
            publication_format="paperback",
        )
        self.assertTrue(allowed.package_allowed)

    def test_17_fail_cannot_be_bypassed(self):
        data = _approved_coloring()
        result = run_kdp_preflight(
            data,
            publication_format="hardcover",
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(result.overall, RESULT_FAIL)
        with self.assertRaises(KdpPreflightError):
            assert_prepare_kdp_package_allowed(
                data,
                preflight_token=result.preflight_token,
                warning_acknowledged=True,
                print_settings=_print_ok(),
                metadata=_meta_ok(),
                ai_disclosure=_ai_none(),
                publication_format="hardcover",
            )

    def test_18_stale_preflight_cannot_be_reused(self):
        data = _approved_coloring()
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure=_ai_none(),
        )
        # Tamper identity after preflight
        data["content_digest"] = "f" * 64
        with self.assertRaises(KdpPreflightError) as ctx:
            assert_prepare_kdp_package_allowed(
                data,
                preflight_token=result.preflight_token,
                print_settings=_print_ok(),
                metadata=_meta_ok(),
                ai_disclosure=_ai_none(),
                publication_format="paperback",
            )
        self.assertIn("Stale", str(ctx.exception))

    def test_19_ordinary_pdf_zip_export_route_unchanged(self):
        """Ordinary /export-product still callable; KDP gate is separate."""
        client = app.test_client()
        # No project required assertion here — route exists and is not removed.
        src = Path(ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('@app.post("/export-product")', src)
        self.assertIn('@app.post("/projects/<int:project_id>/kdp/preflight")', src)
        self.assertIn('@app.post("/projects/<int:project_id>/kdp/prepare-package")', src)
        # JS still wires ordinary downloads
        js = Path(ROOT / "static/js/app.js").read_text(encoding="utf-8")
        self.assertIn('data-ns="dl-pdf"', js)
        self.assertIn("Run KDP Preflight", js)
        self.assertIn("Prepare KDP Package", js)
        self.assertIn("kdpPreflightPanel", js)
        _ = client  # keep import side-effect free

    def test_20_no_external_paid_calls(self):
        self.assertEqual(os.environ.get("OPENAI_API_KEY"), "")
        self.assertEqual(os.environ.get("TAVILY_API_KEY"), "")
        data = _approved_coloring()
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure=_ai_none(),
        )
        self.assertIn(
            result.overall, {RESULT_PASS, RESULT_WARNING, RESULT_FAIL}
        )
        # Finding schema completeness
        for f in result.findings:
            self.assertTrue(f.rule_id)
            self.assertIn(f.severity, {"FAIL", "WARNING", "INFO"})
            self.assertTrue(f.product_format)
            self.assertTrue(f.affected)
            self.assertTrue(f.explanation)
            self.assertTrue(f.required_correction)
            self.assertTrue(f.evidence)

    def test_routes_preflight_and_prepare_gate(self):
        client = app.test_client()
        data = _approved_coloring()
        create = client.post(
            "/projects",
            json={
                "name": "KDP Pass2 Route Fixture",
                "type": "product",
                "user_saved": True,
                "data": data,
            },
        )
        self.assertEqual(create.status_code, 201)
        pid = create.get_json()["id"]
        try:
            body = {
                "publication_format": "paperback",
                "print_settings": _print_ok(),
                "metadata": _meta_ok(),
                "ai_disclosure": _ai_none(),
            }
            pref = client.post(f"/projects/{pid}/kdp/preflight", json=body)
            self.assertEqual(pref.status_code, 200)
            payload = pref.get_json()
            self.assertEqual(payload["overall"], RESULT_PASS)
            self.assertTrue(payload["preflight_token"])

            blocked = client.post(
                f"/projects/{pid}/kdp/prepare-package",
                json={**body, "preflight_token": "deadbeef"},
            )
            self.assertEqual(blocked.status_code, 403)

            ok = client.post(
                f"/projects/{pid}/kdp/prepare-package",
                json={**body, "preflight_token": payload["preflight_token"]},
            )
            self.assertEqual(ok.status_code, 200)
            pkg = ok.get_json()
            self.assertEqual(pkg["label"], "Ready for Amazon Previewer")
            self.assertIsNone(pkg["amazon_approval_claim"])
            self.assertIn("manifest", pkg)
            self.assertNotEqual(pkg["label"], "Guaranteed Amazon Approved")
            self.assertIn("never Guaranteed Amazon Approved", pkg["manifest"]["note"])
        finally:
            client.delete(f"/projects/{pid}")

    def test_draft_fails_closed(self):
        data = _approved_coloring(
            artifact_state="DRAFT",
            content_digest="",
            asset_manifest_digest="",
        )
        # Without digests, resolve may still be DRAFT
        result = run_kdp_preflight(
            data,
            publication_format="paperback",
            print_settings=_print_ok(),
            metadata=_meta_ok(),
            ai_disclosure=_ai_none(),
        )
        self.assertEqual(result.overall, RESULT_FAIL)
        self.assertTrue(
            any(f.rule_id in {"KDP-ARTIFACT-DRAFT", "KDP-ARTIFACT-IDENTITY-MISSING"} for f in result.findings)
        )


if __name__ == "__main__":
    unittest.main()
