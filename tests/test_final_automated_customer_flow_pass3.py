"""Pass 3: final automated customer-flow + write/digest hardening.

Deterministic local/mock path under FACTORY_TEST_MODE:
Research → Choose This Idea → math builder → Preview → Save → Open →
Publish/Next Steps → PDF → ZIP.

Also covers remaining write-bypass gates, export SHA-256 verification,
stale/mismatched download blocks, and public product readiness hiding.

Zero paid/external calls. Does not mutate protected customer artifacts on disk.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
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
    content_digest_from_pdf_bytes,
    stamp_artifact_identity,
)
from services.quality.artifact_state import (  # noqa: E402
    ArtifactState,
    ArtifactStateError,
    assert_content_mutation_allowed,
    current_revision,
    resolve_artifact_state,
)

APP_JS = ROOT / "static" / "js" / "app.js"

MATH_FIELDS = {
    "worksheet_title": "Pass3 Customer Flow Math",
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

SELECTED = {
    "niche": "Grade 3 math practice",
    "product_idea": "Pass3 Customer Flow Math",
    "product_type": "Math Worksheet",
    "target_audience": "Grade 3 students",
    "customer_problem": "Kids need printable addition practice",
    "why_opportunity": "Parents buy grade-level worksheets",
    "price_range": "$3 - $7",
    "difficulty": "Easy",
    "competition": "Medium",
    "opportunity_score": 84,
    "sales_angle": "Clear addition drills with answer key",
}

HOSTILE_AI_PLAN = {
    "product_title": "Pass3 Customer Flow Math",
    "subtitle": "Addition practice",
    "product_type": "Ebook",
    "target_audience": "Grade 3 students",
    "customer_problem": "Kids need printable addition practice",
    "product_promise": "Six addition problems with answers",
    "main_transformation": "From unsure to practiced",
    "price_range": "$3 - $7",
    "product_description": "A math worksheet for grade 3 addition.",
    "outline": ["Warm-up", "Practice", "Review"],
    "bonus_ideas": ["Answer key"],
    "cover_concept": "Simple worksheet cover",
    "sales_angle": "Clear addition drills with answer key",
    "marketing_hook": "Practice addition today",
    "next_step": "Build the math worksheet",
}


def _minimal_pdf_b64(tag: str = "pass3") -> str:
    return base64.b64encode(f"%PDF-1.4\n%{tag}\n%%EOF\n".encode("ascii")).decode(
        "ascii"
    )


class FinalAutomatedCustomerFlowPass3Tests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self._project_ids: list[int] = []
        self._pkg_dirs: list[str] = []
        self.assertTrue(APP_JS.is_file())
        self.app_js = APP_JS.read_text(encoding="utf-8")

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

    # ------------------------------------------------------------------ //
    # Points 1–8: full non-ebook customer flow
    # ------------------------------------------------------------------ //
    def test_01_through_08_research_to_pdf_zip_customer_flow(self):
        import services.product as product_mod
        from services.math_worksheet import pdf_builder as mw

        # 1) Research saved (local fixture — no AI/internet research)
        research_resp = self.client.post(
            "/projects",
            json={
                "name": "Research: Pass3 math",
                "type": "research_plan",
                "user_saved": True,
                "system_test": True,
                "data": {
                    "mode": "local_fixture",
                    "interest": "grade 3 addition worksheets",
                    "goal": "Publish a printable math worksheet",
                    "opportunities": [SELECTED],
                    "stage": "research_saved",
                },
            },
        )
        self.assertEqual(research_resp.status_code, 201, research_resp.data)
        research_id = research_resp.get_json()["id"]
        self._track(project_id=research_id)

        # 2) Choose This Idea → product plan (hostile AI cannot force Ebook)
        form = {
            "idea": SELECTED["product_idea"],
            "product_type": SELECTED["product_type"],
            "audience": SELECTED["target_audience"],
            "problem": SELECTED["customer_problem"],
            "outcome": "",
            "tone": "",
            "length": "",
            "difficulty": SELECTED["difficulty"],
            "notes": SELECTED["why_opportunity"],
        }
        with patch(
            "services.product_plan.chat_json", return_value=HOSTILE_AI_PLAN
        ), patch(
            "ai_client.chat", side_effect=AssertionError("paid chat")
        ), patch(
            "ai_client.chat_json", side_effect=AssertionError("paid chat_json")
        ):
            plan_resp = self.client.post(
                "/generate-product-plan",
                json={"form": form},
            )
        self.assertEqual(plan_resp.status_code, 200, plan_resp.data)
        plan_body = plan_resp.get_json()
        plan = plan_body.get("plan") or plan_body
        # Selected non-ebook type must win over hostile Ebook suggestion.
        self.assertEqual(plan_body.get("product_type"), "Math Worksheet")
        self.assertEqual((plan_body.get("plan") or {}).get("product_type"), "Math Worksheet")
        self.assertNotEqual((plan_body.get("plan") or {}).get("product_type"), "Ebook")

        # Persist Choose This Idea back onto the SAME research ID.
        choose_payload = {
            **plan_body,
            "niche": SELECTED["niche"],
            "audience": SELECTED["target_audience"],
            "opportunity": SELECTED,
            "chosen_idea": SELECTED,
            "stage": "product_plan_saved",
            "_source_project_id": research_id,
        }
        put_research = self.client.put(
            f"/projects/{research_id}",
            json={
                "name": SELECTED["product_idea"],
                "type": "product_plan",
                "user_saved": True,
                "data": choose_payload,
            },
        )
        self.assertEqual(put_research.status_code, 200, put_research.data)
        self.assertEqual(put_research.get_json().get("id"), research_id)

        # 3) Correct builder: Preview generate (math_worksheet, local)
        with patch.object(
            product_mod, "generate_product", wraps=product_mod.generate_product
        ), patch.object(
            mw, "build_math_worksheet_pdf", wraps=mw.build_math_worksheet_pdf
        ):
            preview_resp = self.client.post(
                "/generate-product",
                json={"product_type": "math_worksheet", "fields": MATH_FIELDS},
            )
        self.assertEqual(preview_resp.status_code, 200, preview_resp.data)
        preview = preview_resp.get_json()
        self.assertEqual(preview.get("product_type"), "math_worksheet")
        self.assertTrue(preview.get("pdf_bytes"))
        self.assertTrue(preview.get("content_digest"))
        self.assertTrue(preview.get("asset_manifest_digest"))
        self.assertEqual(
            resolve_artifact_state(preview).value, ArtifactState.DRAFT.value
        )
        artifact_id = preview.get("artifact_id") or preview["package_id"]
        revision = int(preview.get("artifact_revision") or 1)
        content_digest = preview["content_digest"]
        asset_digest = preview["asset_manifest_digest"]
        pdf_preview = base64.b64decode(preview["pdf_bytes"])
        self.assertTrue(pdf_preview.startswith(b"%PDF"))
        self.assertEqual(content_digest, content_digest_from_pdf_bytes(pdf_preview))
        self._track(package_id=preview["package_id"])

        # 4) Save
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
                    "audience": MATH_FIELDS["audience"],
                    "goal": MATH_FIELDS["goal"],
                    "research_project_id": research_id,
                    "chosen_idea": SELECTED,
                },
            },
        )
        self.assertEqual(save_resp.status_code, 201, save_resp.data)
        saved = save_resp.get_json()
        project_id = saved["id"]
        self._track(project_id=project_id)

        # 5) Open Product (Saved Projects reopen)
        open_resp = self.client.get(f"/projects/{project_id}")
        self.assertEqual(open_resp.status_code, 200)
        opened = open_resp.get_json()
        odata = opened.get("data") or {}
        self.assertEqual(odata.get("product_type"), "math_worksheet")
        self.assertEqual(odata.get("artifact_id") or odata.get("package_id"), artifact_id)
        self.assertEqual(int(odata.get("artifact_revision") or 0), revision)
        self.assertEqual(odata.get("content_digest"), content_digest)
        self.assertEqual(odata.get("asset_manifest_digest"), asset_digest)
        self.assertEqual(odata.get("research_project_id"), research_id)
        self.assertEqual(
            (odata.get("chosen_idea") or {}).get("product_type"),
            SELECTED["product_type"],
        )

        # 6) Publish / Next Steps metadata (must not rewrite digests/content)
        with_pub = dict(odata)
        with_pub["publishing"] = {
            "platform": "local_test",
            "status": "ready_for_review",
            "intent": "next_steps",
        }
        with_pub["next_steps"] = {"checklist": ["download_pdf", "download_zip"]}
        put_ns = self.client.put(
            f"/projects/{project_id}",
            json={"data": with_pub},
        )
        self.assertEqual(put_ns.status_code, 200, put_ns.data)
        after_ns = (put_ns.get_json().get("data") or {})
        self.assertEqual(after_ns.get("content_digest"), content_digest)
        self.assertEqual(after_ns.get("asset_manifest_digest"), asset_digest)
        self.assertEqual(int(after_ns.get("artifact_revision") or 0), revision)
        self.assertEqual(after_ns.get("next_steps"), with_pub["next_steps"])

        # 7–8) Export → PDF + ZIP downloads (readable, nonempty, identity preserved)
        export_resp = self.client.post(
            "/export-product", json={"project_id": project_id}
        )
        self.assertEqual(export_resp.status_code, 200, export_resp.data)
        export_body = export_resp.get_json()
        export_pkg = export_body["package_id"]
        self._track(package_id=export_pkg)
        files = (export_body.get("exports") or {}).get("files") or {}
        pdf_meta = files.get("pdf") or {}
        zip_meta = files.get("zip") or {}
        self.assertTrue(pdf_meta.get("url"))
        self.assertTrue(zip_meta.get("url"))
        self.assertTrue(pdf_meta.get("sha256"))
        self.assertTrue(zip_meta.get("sha256"))
        export_meta = (export_body.get("exports") or {}).get("meta") or {}
        self.assertEqual(export_meta.get("artifact_id"), artifact_id)
        self.assertEqual(int(export_meta.get("artifact_revision") or 0), revision)

        after_export = self.client.get(f"/projects/{project_id}").get_json()
        adata = after_export.get("data") or {}
        self.assertEqual(adata.get("content_digest"), content_digest)
        self.assertEqual(adata.get("export_package_id"), export_pkg)
        self.assertEqual(adata.get("research_project_id"), research_id)

        pdf_dl = self.client.get(pdf_meta["url"])
        zip_dl = self.client.get(zip_meta["url"])
        self.assertEqual(pdf_dl.status_code, 200, pdf_dl.data[:300])
        self.assertEqual(zip_dl.status_code, 200, zip_dl.data[:300])
        self.assertTrue(pdf_dl.data.startswith(b"%PDF"))
        self.assertGreater(len(pdf_dl.data), 100)
        self.assertGreater(len(zip_dl.data), 100)
        self.assertEqual(
            hashlib.sha256(pdf_dl.data).hexdigest(), pdf_meta["sha256"]
        )
        self.assertEqual(
            hashlib.sha256(zip_dl.data).hexdigest(), zip_meta["sha256"]
        )
        self.assertEqual(content_digest_from_pdf_bytes(pdf_dl.data), content_digest)

        zf = zipfile.ZipFile(BytesIO(zip_dl.data))
        names = zf.namelist()
        self.assertTrue(names)
        pdf_names = [n for n in names if n.lower().endswith(".pdf")]
        self.assertEqual(len(pdf_names), 1)
        self.assertFalse(any(n.startswith("ebook.") for n in names))
        zip_pdf = zf.read(pdf_names[0])
        self.assertTrue(zip_pdf.startswith(b"%PDF"))
        self.assertEqual(content_digest_from_pdf_bytes(zip_pdf), content_digest)

        # Stale/orphan package blocked
        from reportlab.pdfgen import canvas

        stale_pkg = "pass3stale" + ("c" * 22)
        self._track(package_id=stale_pkg)
        buf = BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(72, 720, "STALE REVISION")
        c.showPage()
        c.save()
        _write_package(stale_pkg, {"stale.pdf": buf.getvalue()})
        stale_dl = self.client.get(f"/download/{stale_pkg}/stale.pdf")
        self.assertEqual(stale_dl.status_code, 403, stale_dl.data[:400])

        # Mismatched bytes vs recorded export sha256 blocked (no auto-regen)
        pdf_disk = Path(EXPORTS_DIR) / export_pkg
        pdf_files = list(pdf_disk.glob("*.pdf"))
        self.assertTrue(pdf_files)
        target = pdf_files[0]
        original = target.read_bytes()
        try:
            target.write_bytes(b"%PDF-1.4\nTAMPERED\n%%EOF\n")
            tampered = self.client.get(pdf_meta["url"])
            self.assertEqual(tampered.status_code, 403, tampered.data[:400])
            body = tampered.get_json() or {}
            self.assertEqual(body.get("error"), "download_blocked")
            self.assertIn("export_sha256_mismatch", body.get("violations") or [])
        finally:
            target.write_bytes(original)

    # ------------------------------------------------------------------ //
    # Write-bypass gates
    # ------------------------------------------------------------------ //
    def test_09_ensure_ebook_visual_package_respects_mutation_policy(self):
        from services.ebook_local_package import ensure_ebook_visual_package

        draft = {
            "type": "ebook",
            "data": {
                "product_type": "ebook",
                "artifact_state": ArtifactState.DRAFT.value,
                "artifact_revision": 1,
                "title": "Pass3 Draft Ebook",
                "content": "# Hello\n\nDraft manuscript for visual package.",
                "ebook": "# Hello\n\nDraft manuscript for visual package.",
                "export_package_id": "pass3-ebook-old-export",
                "product_exports": {"files": {}},
            },
        }
        updated = ensure_ebook_visual_package(draft)
        udata = updated.get("data") or {}
        self.assertTrue(udata.get("visual_plan"))
        self.assertTrue(udata.get("preview_html"))
        self.assertTrue(udata.get("cover_design"))
        self.assertNotIn("export_package_id", udata)
        self.assertNotIn("product_exports", udata)

        approved = {
            "type": "ebook",
            "data": {
                "product_type": "ebook",
                "artifact_state": ArtifactState.APPROVED.value,
                "artifact_revision": 2,
                "title": "Pass3 Approved Ebook",
                "content": "# Approved\n\nMust not mutate.",
                "ebook": "# Approved\n\nMust not mutate.",
                "qa_status": "accepted",
                "pdf_bytes": _minimal_pdf_b64("approved-ebook"),
            },
        }
        stamp_artifact_identity(approved["data"])
        with self.assertRaises(ArtifactStateError) as ctx:
            ensure_ebook_visual_package(approved)
        self.assertIn("Create Draft Revision", str(ctx.exception))

        locked = {
            "type": "ebook",
            "data": {
                "product_type": "ebook",
                "artifact_state": ArtifactState.LOCKED.value,
                "artifact_revision": 3,
                "book_locked": True,
                "title": "Pass3 Locked Ebook",
                "content": "# Locked\n\nMust not mutate.",
                "ebook": "# Locked\n\nMust not mutate.",
            },
        }
        with self.assertRaises(ArtifactStateError) as ctx2:
            ensure_ebook_visual_package(locked)
        self.assertIn("LOCKED", str(ctx2.exception))

    def test_10_finalize_word_search_cover_script_resolves_state(self):
        from services.product_cover_agent import finalize_word_search_production_cover

        approved = {
            "data": {
                "product_type": "word_search",
                "artifact_state": ArtifactState.APPROVED.value,
                "artifact_revision": 2,
                "title": "Pass3 Approved WS",
                "package_id": "pass3-ws-approved",
                "qa_status": "accepted",
                "is_pdf": True,
                "pdf_bytes": _minimal_pdf_b64("ws-approved"),
                "fields": {"theme": "Black History", "brand": "Lonnie Brown"},
                "cover_design": {"title": "Black History", "package_id": "pass3-ws-approved"},
            }
        }
        stamp_artifact_identity(approved["data"])
        with self.assertRaises(ArtifactStateError):
            assert_content_mutation_allowed(
                approved["data"], action="finalize word search cover"
            )
        with self.assertRaises(ArtifactStateError):
            finalize_word_search_production_cover(approved)

        # Offline script gate: resolve + assert before write.
        script = (ROOT / "scripts" / "finalize_word_search_cover.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("resolve_artifact_state", script)
        self.assertIn("assert_content_mutation_allowed", script)
        self.assertIn("ArtifactStateError", script)

    # ------------------------------------------------------------------ //
    # Public product readiness
    # ------------------------------------------------------------------ //
    def test_11_unready_public_product_types_hidden(self):
        # spelling_worksheet lacks e2e acceptance contract → hidden
        self.assertRegex(
            self.app_js,
            re.compile(
                r'id:\s*"spelling_worksheet"[\s\S]*?hidden:\s*true',
                re.M,
            ),
        )
        for already in ("marketing_kit", "cover_design", "flip_book", "planner"):
            self.assertRegex(
                self.app_js,
                re.compile(rf'id:\s*"{already}"[\s\S]*?hidden:\s*true', re.M),
            )
        # Ready types remain visible (no hidden: true on their card)
        for ready in ("ebook", "coloring_book", "word_search", "crossword", "math_worksheet"):
            block = re.search(
                rf'id:\s*"{ready}",([\s\S]*?)(?=\n  \{{|\n\];)',
                self.app_js,
            )
            self.assertIsNotNone(block, ready)
            self.assertNotIn("hidden: true", block.group(1), ready)

        # Backend generate guard
        resp = self.client.post(
            "/generate-product",
            json={"product_type": "spelling_worksheet", "fields": {"worksheet_title": "x"}},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("not ready", (resp.get_json() or {}).get("error", "").lower())


if __name__ == "__main__":
    unittest.main()
