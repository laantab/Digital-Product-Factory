"""Pass 1: content-mutation paths respect artifact write policy.

Covers Generate Product (with project_id), Enhance Ebook, and cover
save / regenerate / upload / apply-to-pdf families.

Proves policy points 1–12 under FACTORY_TEST_MODE with mocks — zero paid
or external calls. Does not rewrite protected artifacts on disk.
"""
from __future__ import annotations

import base64
import copy
import io
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
from services.quality.artifact_identity import stamp_artifact_identity  # noqa: E402
from services.quality.artifact_state import (  # noqa: E402
    ArtifactState,
    current_revision,
    resolve_artifact_state,
    transition_artifact_revision,
)


def _minimal_pdf_b64(tag: str = "pass1") -> str:
    return base64.b64encode(f"%PDF-1.4\n%{tag}\n%%EOF\n".encode("ascii")).decode(
        "ascii"
    )


def _tiny_png_b64() -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1, 1), color=(255, 255, 255)).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _export_refs(pkg: str) -> dict:
    return {
        "product_exports": {
            "pdf": {"url": f"/download/{pkg}/sheet.pdf"},
            "zip": {"url": f"/download/{pkg}/package.zip"},
            "files": {"meta": {"package_id": pkg}},
        },
        "export_package_id": pkg,
        "exports": {"folder": f"exports/{pkg}"},
        "pdf_download_url": f"/download/{pkg}/sheet.pdf",
        "zip_download_url": f"/download/{pkg}/package.zip",
    }


def _draft_record(**extra) -> dict:
    data = {
        "product_type": "math_worksheet",
        "title": "Pass1 Draft Worksheet",
        "package_id": "pass1-draft-pkg-001",
        "artifact_id": "pass1-draft-pkg-001",
        "artifact_revision": 2,
        "artifact_state": ArtifactState.DRAFT.value,
        "problems": [{"prompt": "1+1", "answer": "2"}],
        "pdf_bytes": _minimal_pdf_b64("draft"),
        "cover_design": {
            "title": "Pass1 Draft Worksheet",
            "package_id": "pass1-draft-pkg-001",
            "local_image_path": "exports/pass1-draft-pkg-001/img_cover.png",
        },
        "prior_approved_revision": {
            "artifact_revision": 1,
            "artifact_state": ArtifactState.APPROVED.value,
            "artifact_id": "pass1-prior-approved",
            "package_id": "pass1-prior-approved",
            "content_digest": "a" * 64,
            "asset_manifest_digest": "b" * 64,
        },
        "artifact_lineage": [
            {
                "artifact_revision": 1,
                "artifact_state": ArtifactState.APPROVED.value,
                "artifact_id": "pass1-prior-approved",
            }
        ],
        **_export_refs("pass1-draft-export-old"),
    }
    data.update(extra)
    return data


def _approved_record(**extra) -> dict:
    data = {
        "product_type": "math_worksheet",
        "title": "Pass1 Approved Worksheet",
        "package_id": "pass1-approved-pkg-001",
        "artifact_id": "pass1-approved-pkg-001",
        "artifact_revision": 3,
        "problems": [{"prompt": "2+2", "answer": "4"}],
        "pdf_bytes": _minimal_pdf_b64("approved"),
        "qa_status": "accepted",
        "cover_design": {
            "title": "Pass1 Approved Worksheet",
            "package_id": "pass1-approved-pkg-001",
            "local_image_path": "exports/pass1-approved-pkg-001/img_cover.png",
        },
        **_export_refs("pass1-approved-pkg-001"),
    }
    stamp_artifact_identity(data)
    data["artifact_state"] = ArtifactState.APPROVED.value
    data.update(extra)
    return data


def _locked_record(**extra) -> dict:
    data = _approved_record(
        title="Pass1 Locked Worksheet",
        package_id="pass1-locked-pkg-001",
        artifact_id="pass1-locked-pkg-001",
        book_locked=True,
        lock_status="LOCKED",
        locked_at="2026-08-10T00:00:00Z",
        artifact_state=ArtifactState.LOCKED.value,
    )
    data.update(extra)
    return data


def _conflict_record(**extra) -> dict:
    data = _approved_record(
        package_id="pass1-conflict-pkg-001",
        artifact_id="pass1-conflict-pkg-001",
        artifact_state=ArtifactState.DRAFT.value,
        book_locked=True,
        lock_status="LOCKED",
    )
    data.update(extra)
    return data


MUTATION_ROUTES = (
    (
        "generate",
        "/generate-product",
        lambda pid, data: {
            "project_id": pid,
            "product_type": "math_worksheet",
            "fields": {"worksheet_title": "Mutated"},
        },
    ),
    (
        "enhance",
        "/enhance-ebook",
        lambda pid, data: {
            "project_id": pid,
            "title": "Enhanced",
            "content": "Chapter one content for enhance path.",
            "fields": {},
        },
    ),
    (
        "cover_save",
        "/cover/save",
        lambda pid, data: {
            "project_id": pid,
            "cover": data.get("cover_design") or {},
            "overrides": {"subtitle": "Saved subtitle"},
        },
    ),
    (
        "cover_regen",
        "/cover/regenerate",
        lambda pid, data: {
            "project_id": pid,
            "cover": {
                **(data.get("cover_design") or {}),
                "cover_fingerprint": "stale-fingerprint",
            },
        },
    ),
    (
        "cover_upload",
        "/cover/upload-image",
        lambda pid, data: {
            "project_id": pid,
            "image_data": _tiny_png_b64(),
        },
    ),
    (
        "cover_apply",
        "/cover/apply-to-pdf",
        lambda pid, data: {
            "project_id": pid,
            "cover": data.get("cover_design") or {"title": data.get("title") or "T"},
        },
    ),
)


class ArtifactLifecycleMutationPathsTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self._project_ids: list[int] = []

    def tearDown(self):
        for pid in self._project_ids:
            try:
                self.client.delete(f"/projects/{pid}")
            except Exception:
                pass

    def _create_project(self, data: dict, name: str = "Pass1 Mutation") -> tuple[int, dict]:
        resp = self.client.post(
            "/projects",
            json={
                "name": name,
                "type": "product",
                "user_saved": True,
                "temporary": True,
                "system_test": True,
                "data": data,
            },
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        saved = resp.get_json()
        project_id = int(saved["id"])
        self._project_ids.append(project_id)
        return project_id, saved.get("data") or {}

    def _identity_core(self, data: dict) -> dict:
        return {
            "artifact_id": data.get("artifact_id") or data.get("package_id"),
            "artifact_revision": current_revision(data),
            "package_id": data.get("package_id"),
            "product_type": data.get("product_type"),
            "prior_approved_revision": copy.deepcopy(
                data.get("prior_approved_revision")
            ),
            "artifact_lineage": copy.deepcopy(data.get("artifact_lineage")),
        }

    def _assert_blocked_approved_or_locked(
        self, family: str, path: str, body: dict, *, locked: bool
    ):
        with patch("app.generate_product") as gen, patch(
            "app.build_ebook_package"
        ) as enh, patch(
            "services.ebook_pipeline_agents.run_ebook_quality_pipeline"
        ) as pipe, patch(
            "app.save_cover"
        ) as save_c, patch(
            "app.regenerate_cover_image_for_cover"
        ) as regen, patch(
            "app.build_product_export"
        ) as export, patch(
            "app.validate_cover_for_export",
            return_value=[],
        ), patch(
            "services.quality.artifact_state.transition_artifact_revision",
            wraps=transition_artifact_revision,
        ) as transition:
            resp = self.client.post(path, json=body)
        self.assertEqual(resp.status_code, 409, f"{family}: {resp.data}")
        err = (resp.get_json() or {}).get("error") or ""
        if locked:
            self.assertIn("LOCKED", err)
            self.assertIn("cannot", err.lower())
        else:
            self.assertIn("APPROVED", err)
            self.assertIn("Create Draft Revision", err)
        gen.assert_not_called()
        enh.assert_not_called()
        pipe.assert_not_called()
        save_c.assert_not_called()
        regen.assert_not_called()
        export.assert_not_called()
        transition.assert_not_called()

    # --- Point 1: new project may create DRAFT (no project_id) ---
    def test_01_new_generate_without_project_creates_preview(self):
        fake = {
            "product_type": "math_worksheet",
            "title": "New Draft Preview",
            "package_id": "pass1-new-pkg",
            "pdf_bytes": _minimal_pdf_b64("new"),
            "is_pdf": True,
            "problems": [{"prompt": "3+3", "answer": "6"}],
        }
        with patch("app.generate_product", return_value=copy.deepcopy(fake)) as gen:
            resp = self.client.post(
                "/generate-product",
                json={
                    "product_type": "math_worksheet",
                    "fields": {"worksheet_title": "New"},
                },
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.get_json()
        self.assertEqual(body.get("product_type"), "math_worksheet")
        self.assertTrue(body.get("pdf_bytes"))
        gen.assert_called_once()

    # --- Points 2, 6, 8, 9, 10, 11, 12: DRAFT generate ---
    def test_02_draft_generate_mutates_invalidates_exports_preserves_prior(self):
        import database

        project_id, stored = self._create_project(_draft_record())
        prior_core = self._identity_core(stored)
        prior_approved = copy.deepcopy(stored.get("prior_approved_revision"))
        prior_lineage = copy.deepcopy(stored.get("artifact_lineage"))
        new_pdf = _minimal_pdf_b64("draft-regen")
        fake = {
            "product_type": "math_worksheet",
            "title": "Draft Regenerated",
            "package_id": "pass1-draft-pkg-001",
            "pdf_bytes": new_pdf,
            "is_pdf": True,
            "problems": [{"prompt": "9+9", "answer": "18"}],
            "artifact_revision": 99,  # must not auto-bump via smuggled result
        }
        with patch("app.generate_product", return_value=copy.deepcopy(fake)), patch(
            "services.quality.artifact_state.transition_artifact_revision",
            wraps=transition_artifact_revision,
        ) as transition:
            resp = self.client.post(
                "/generate-product",
                json={
                    "project_id": project_id,
                    "product_type": "math_worksheet",
                    "fields": {"worksheet_title": "Draft Regenerated"},
                },
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        after = database.get_project(project_id)["data"]
        self.assertEqual(resolve_artifact_state(after), ArtifactState.DRAFT)
        self.assertEqual(current_revision(after), prior_core["artifact_revision"])
        self.assertEqual(after.get("title"), "Draft Regenerated")
        self.assertEqual(after.get("product_type"), "math_worksheet")
        self.assertNotIn("export_package_id", after)
        self.assertNotIn("product_exports", after)
        self.assertNotIn("exports", after)
        self.assertNotIn("pdf_download_url", after)
        self.assertEqual(after.get("prior_approved_revision"), prior_approved)
        self.assertEqual(after.get("artifact_lineage"), prior_lineage)
        self.assertEqual(after.get("artifact_id"), prior_core["artifact_id"])
        transition.assert_not_called()

    # --- Points 3, 5, 6: APPROVED blocked on all families ---
    def test_03_approved_blocks_all_mutation_families(self):
        import database

        project_id, stored = self._create_project(_approved_record())
        baseline = copy.deepcopy(database.get_project(project_id)["data"])
        for family, path, body_fn in MUTATION_ROUTES:
            with self.subTest(family=family):
                self._assert_blocked_approved_or_locked(
                    family, path, body_fn(project_id, stored), locked=False
                )
                after = database.get_project(project_id)["data"]
                self.assertEqual(after, baseline)
                self.assertEqual(resolve_artifact_state(after), ArtifactState.APPROVED)

    # --- Point 4: LOCKED blocked on all families ---
    def test_04_locked_blocks_all_mutation_families(self):
        import database

        project_id, stored = self._create_project(_locked_record())
        baseline = copy.deepcopy(database.get_project(project_id)["data"])
        for family, path, body_fn in MUTATION_ROUTES:
            with self.subTest(family=family):
                self._assert_blocked_approved_or_locked(
                    family, path, body_fn(project_id, stored), locked=True
                )
                after = database.get_project(project_id)["data"]
                self.assertEqual(after, baseline)
                self.assertEqual(resolve_artifact_state(after), ArtifactState.LOCKED)

    # --- Point 7: conflicting evidence fails safely ---
    def test_05_conflicting_state_fails_safely_all_families(self):
        import database

        project_id, stored = self._create_project(_conflict_record())
        baseline = copy.deepcopy(database.get_project(project_id)["data"])
        for family, path, body_fn in MUTATION_ROUTES:
            with self.subTest(family=family):
                with patch("app.generate_product") as gen, patch(
                    "app.build_ebook_package"
                ) as enh, patch(
                    "app.save_cover"
                ) as save_c, patch(
                    "app.regenerate_cover_image_for_cover"
                ) as regen, patch(
                    "app.build_product_export"
                ) as export, patch(
                    "services.quality.artifact_state.transition_artifact_revision",
                    wraps=transition_artifact_revision,
                ) as transition:
                    resp = self.client.post(path, json=body_fn(project_id, stored))
                self.assertEqual(resp.status_code, 409, f"{family}: {resp.data}")
                err = ((resp.get_json() or {}).get("error") or "").lower()
                self.assertTrue(
                    "conflict" in err or "locked" in err or "draft" in err,
                    err,
                )
                self.assertEqual(database.get_project(project_id)["data"], baseline)
                gen.assert_not_called()
                enh.assert_not_called()
                save_c.assert_not_called()
                regen.assert_not_called()
                export.assert_not_called()
                transition.assert_not_called()

    # --- Enhance Ebook DRAFT success ---
    def test_06_draft_enhance_ebook_invalidates_exports(self):
        import database

        project_id, stored = self._create_project(
            _draft_record(product_type="ebook", title="Draft Ebook", content="Old")
        )
        prior_approved = copy.deepcopy(stored.get("prior_approved_revision"))
        fake_pkg = {
            "preview_html": "<p>enhanced</p>",
            "visual_plan": {"chapters": []},
            "product_summary": "summary",
            "package_id": "pass1-draft-pkg-001",
            "cover_design": {"title": "Draft Ebook"},
            "quality_score": 90,
            "quality_blocking": False,
        }

        class _Pipe:
            steps = []

            def to_dict(self):
                return {"ok": True, "steps": []}

        with patch("services.ebook_customer_path.build_ebook_package", return_value=copy.deepcopy(fake_pkg)), patch(
            "app.build_ebook_package", return_value=copy.deepcopy(fake_pkg)
        ), patch(
            "services.ebook_pipeline_agents.run_ebook_quality_pipeline",
            return_value=_Pipe(),
        ), patch(
            "services.quality.artifact_state.transition_artifact_revision",
            wraps=transition_artifact_revision,
        ) as transition:
            resp = self.client.post(
                "/enhance-ebook",
                json={
                    "project_id": project_id,
                    "title": "Draft Ebook",
                    "content": "Enhanced manuscript body text.",
                    "fields": {},
                },
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        after = database.get_project(project_id)["data"]
        self.assertEqual(resolve_artifact_state(after), ArtifactState.DRAFT)
        self.assertEqual(after.get("content"), "Enhanced manuscript body text.")
        self.assertNotIn("export_package_id", after)
        self.assertNotIn("product_exports", after)
        self.assertEqual(after.get("prior_approved_revision"), prior_approved)
        self.assertEqual(current_revision(after), current_revision(stored))
        transition.assert_not_called()

    # --- Cover families DRAFT success ---
    def test_07_draft_cover_save_invalidates_exports(self):
        import database

        project_id, stored = self._create_project(_draft_record())
        prior_approved = copy.deepcopy(stored.get("prior_approved_revision"))
        saved_cover = {
            **(stored.get("cover_design") or {}),
            "subtitle": "Saved subtitle",
            "image_prompt": "prompt",
        }
        with patch(
            "app.save_cover", return_value=copy.deepcopy(saved_cover)
        ), patch(
            "services.quality.artifact_state.transition_artifact_revision",
            wraps=transition_artifact_revision,
        ) as transition:
            resp = self.client.post(
                "/cover/save",
                json={
                    "project_id": project_id,
                    "cover": stored.get("cover_design") or {},
                    "overrides": {"subtitle": "Saved subtitle"},
                },
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        after = database.get_project(project_id)["data"]
        self.assertEqual(after.get("cover_design", {}).get("subtitle"), "Saved subtitle")
        self.assertNotIn("export_package_id", after)
        self.assertEqual(after.get("prior_approved_revision"), prior_approved)
        self.assertEqual(current_revision(after), current_revision(stored))
        transition.assert_not_called()

    def test_08_draft_cover_regenerate_invalidates_exports(self):
        import database

        project_id, stored = self._create_project(_draft_record())
        prior_approved = copy.deepcopy(stored.get("prior_approved_revision"))
        new_cover = {
            **(stored.get("cover_design") or {}),
            "cover_asset_url": "/download/pass1-draft-pkg-001/img_cover.png",
            "image_prompt": "new art",
        }
        with patch(
            "app.regenerate_cover_image_for_cover",
            return_value=(copy.deepcopy(new_cover), new_cover["cover_asset_url"]),
        ), patch(
            "services.quality.artifact_state.transition_artifact_revision",
            wraps=transition_artifact_revision,
        ) as transition:
            resp = self.client.post(
                "/cover/regenerate",
                json={
                    "project_id": project_id,
                    "cover": {
                        **(stored.get("cover_design") or {}),
                        "cover_fingerprint": "old",
                    },
                },
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        after = database.get_project(project_id)["data"]
        self.assertEqual(after.get("cover_design", {}).get("image_prompt"), "new art")
        self.assertNotIn("product_exports", after)
        self.assertEqual(after.get("prior_approved_revision"), prior_approved)
        transition.assert_not_called()

    def test_09_draft_cover_upload_invalidates_exports(self):
        import database
        import tempfile

        project_id, stored = self._create_project(_draft_record())
        prior_approved = copy.deepcopy(stored.get("prior_approved_revision"))
        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.EXPORTS_DIR", tmp), patch(
                "services.quality.artifact_state.transition_artifact_revision",
                wraps=transition_artifact_revision,
            ) as transition:
                resp = self.client.post(
                    "/cover/upload-image",
                    json={
                        "project_id": project_id,
                        "image_data": _tiny_png_b64(),
                    },
                )
            self.assertEqual(resp.status_code, 200, resp.data)
            out = Path(tmp) / "pass1-draft-pkg-001" / "img_cover.png"
            self.assertTrue(out.is_file())
        after = database.get_project(project_id)["data"]
        self.assertNotIn("export_package_id", after)
        self.assertNotIn("zip_download_url", after)
        self.assertEqual(after.get("prior_approved_revision"), prior_approved)
        self.assertEqual(current_revision(after), current_revision(stored))
        transition.assert_not_called()

    def test_10_draft_cover_apply_invalidates_then_may_reexport(self):
        import database

        stored_seed = _draft_record(product_type="crossword", title="Pass1 Crossword")
        project_id, stored = self._create_project(stored_seed)
        prior_approved = copy.deepcopy(stored.get("prior_approved_revision"))
        applied = copy.deepcopy(stored)
        applied["product_type"] = "crossword"
        applied["pdf_bytes"] = _minimal_pdf_b64("covered")
        applied["cover_design"] = {
            **(stored.get("cover_design") or {}),
            "applied": True,
        }
        export_result = {
            "package_id": "pass1-new-export",
            "exports": {"pdf": {"url": "/download/pass1-new-export/sheet.pdf"}},
        }

        with patch(
            "app.validate_cover_for_export", return_value=[]
        ), patch(
            "app.apply_crossword_cover_to_saved_data",
            return_value=copy.deepcopy(applied),
        ), patch(
            "app.build_product_export", return_value=copy.deepcopy(export_result)
        ) as export, patch(
            "services.quality.artifact_state.transition_artifact_revision",
            wraps=transition_artifact_revision,
        ) as transition:
            resp = self.client.post(
                "/cover/apply-to-pdf",
                json={
                    "project_id": project_id,
                    "cover": stored.get("cover_design") or {"title": "T"},
                },
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertTrue((resp.get_json() or {}).get("ok"))
        export.assert_called_once()
        after = database.get_project(project_id)["data"]
        # Either still cleared (if export did not re-persist) or replaced by export.
        # Prior approved lineage must remain intact either way.
        self.assertEqual(after.get("prior_approved_revision"), prior_approved)
        self.assertEqual(after.get("product_type"), "crossword")
        self.assertNotEqual(after.get("product_type"), "ebook")
        self.assertTrue(after.get("cover_design", {}).get("applied"))
        transition.assert_not_called()

    # --- Point 10: metadata-only Save must not bump revision (control) ---
    def test_11_metadata_only_save_does_not_bump_revision(self):
        import database
        from app import _persist_product_data

        project_id, stored = self._create_project(_approved_record())
        rev_before = current_revision(stored)
        project = database.get_project(project_id)
        meta = dict(project.get("data") or {})
        meta["seller_notes"] = "metadata only note"
        _persist_product_data(project, meta)
        after = database.get_project(project_id)["data"]
        self.assertEqual(current_revision(after), rev_before)
        self.assertEqual(resolve_artifact_state(after), ArtifactState.APPROVED)
        self.assertEqual(after.get("seller_notes"), "metadata only note")
        self.assertEqual(after.get("title"), stored.get("title"))

    # --- Point 5 + 12: APPROVED must use Create Draft Revision, then DRAFT may edit ---
    def test_12_approved_requires_explicit_revision_then_draft_may_edit(self):
        import database

        project_id, stored = self._create_project(_approved_record())
        # Direct generate blocked
        with patch("app.generate_product") as gen:
            blocked = self.client.post(
                "/generate-product",
                json={
                    "project_id": project_id,
                    "product_type": "math_worksheet",
                    "fields": {},
                },
            )
        self.assertEqual(blocked.status_code, 409)
        gen.assert_not_called()

        rev = self.client.post(
            f"/projects/{project_id}/revisions",
            json={
                "create_draft_revision": True,
                "reason": "pass1 open draft for edit",
                "expected_artifact_id": stored.get("artifact_id"),
                "expected_revision": current_revision(stored),
            },
        )
        self.assertEqual(rev.status_code, 201, rev.data)
        draft_data = database.get_project(project_id)["data"]
        self.assertEqual(resolve_artifact_state(draft_data), ArtifactState.DRAFT)
        # Attach export refs to prove invalidation after edit
        draft_data = {**draft_data, **_export_refs("pass1-after-revision-export")}
        database.update_project(project_id, None, draft_data, None)

        fake = {
            "product_type": "math_worksheet",
            "title": "Post Revision Edit",
            "package_id": draft_data.get("package_id"),
            "pdf_bytes": _minimal_pdf_b64("post-rev"),
            "is_pdf": True,
            "problems": [{"prompt": "5+5", "answer": "10"}],
        }
        with patch("app.generate_product", return_value=copy.deepcopy(fake)):
            ok = self.client.post(
                "/generate-product",
                json={
                    "project_id": project_id,
                    "product_type": "math_worksheet",
                    "fields": {"worksheet_title": "Post Revision Edit"},
                },
            )
        self.assertEqual(ok.status_code, 200, ok.data)
        after = database.get_project(project_id)["data"]
        self.assertEqual(resolve_artifact_state(after), ArtifactState.DRAFT)
        self.assertEqual(after.get("title"), "Post Revision Edit")
        self.assertNotIn("export_package_id", after)
        self.assertIsNotNone(after.get("prior_approved_revision"))
        self.assertEqual(
            after["prior_approved_revision"].get("artifact_id"),
            stored.get("artifact_id"),
        )


if __name__ == "__main__":
    unittest.main()
