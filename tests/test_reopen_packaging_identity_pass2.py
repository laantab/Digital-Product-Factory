"""Pass 2: saved-project reopen, packaging/rebuild, and new-project identity.

Deterministic local/mock fixtures under FACTORY_TEST_MODE. Zero paid or
external calls. Does not rewrite protected artifacts on disk.
"""
from __future__ import annotations

import base64
import copy
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
from services.ebook_package import EXPORTS_DIR, _write_package  # noqa: E402
from services.quality.artifact_identity import (  # noqa: E402
    content_digest_from_pdf_bytes,
    package_belongs_to_project,
    stamp_artifact_identity,
)
from services.quality.artifact_state import (  # noqa: E402
    ArtifactState,
    assert_packaging_allowed,
    current_revision,
    packaging_may_rebuild_content,
    resolve_artifact_state,
    transition_artifact_revision,
)


def _minimal_pdf_b64(tag: str = "pass2") -> str:
    return base64.b64encode(f"%PDF-1.4\n%{tag}\n%%EOF\n".encode("ascii")).decode(
        "ascii"
    )


def _export_refs(pkg: str) -> dict:
    return {
        "product_exports": {
            "pdf": {"url": f"/download/{pkg}/sheet.pdf"},
            "zip": {"url": f"/download/{pkg}/package.zip"},
            "files": {
                "pdf": {"url": f"/download/{pkg}/sheet.pdf", "name": "sheet.pdf"},
                "zip": {"url": f"/download/{pkg}/package.zip", "name": "package.zip"},
                "meta": {"package_id": pkg},
            },
            "pdf_available": True,
        },
        "export_package_id": pkg,
        "exports": {"folder": f"exports/{pkg}"},
    }


def _draft_record(**extra) -> dict:
    data = {
        "product_type": "math_worksheet",
        "title": "Pass2 Draft Worksheet",
        "package_id": "pass2-draft-pkg-001",
        "artifact_id": "pass2-draft-pkg-001",
        "artifact_revision": 2,
        "artifact_state": ArtifactState.DRAFT.value,
        "is_pdf": True,
        "problems": [{"prompt": "1+1", "answer": "2"}],
        "pdf_bytes": _minimal_pdf_b64("draft"),
        "fields": {
            "worksheet_title": "Pass2 Draft Worksheet",
            "grade": "3",
            "math_topic": "Addition",
            "output_format": "Single Worksheet",
        },
        "cover_design": {
            "title": "Pass2 Draft Worksheet",
            "package_id": "pass2-draft-pkg-001",
            "local_image_path": "exports/pass2-draft-pkg-001/img_cover.png",
        },
        **_export_refs("pass2-draft-export-old"),
    }
    stamp_artifact_identity(data)
    data["artifact_state"] = ArtifactState.DRAFT.value
    data.update(extra)
    return data


def _approved_record(**extra) -> dict:
    data = {
        "product_type": "math_worksheet",
        "title": "Pass2 Approved Worksheet",
        "package_id": "pass2-approved-pkg-001",
        "artifact_id": "pass2-approved-pkg-001",
        "artifact_revision": 3,
        "is_pdf": True,
        "problems": [{"prompt": "2+2", "answer": "4"}],
        "pdf_bytes": _minimal_pdf_b64("approved"),
        "qa_status": "accepted",
        "fields": {
            "worksheet_title": "Pass2 Approved Worksheet",
            "grade": "3",
            "math_topic": "Addition",
            "output_format": "Single Worksheet",
        },
        "cover_design": {
            "title": "Pass2 Approved Worksheet",
            "package_id": "pass2-approved-pkg-001",
            "local_image_path": "exports/pass2-approved-pkg-001/img_cover.png",
        },
        **_export_refs("pass2-approved-pkg-001"),
    }
    stamp_artifact_identity(data)
    data["artifact_state"] = ArtifactState.APPROVED.value
    data.update(extra)
    return data


def _locked_record(**extra) -> dict:
    data = _approved_record(
        title="Pass2 Locked Worksheet",
        package_id="pass2-locked-pkg-001",
        artifact_id="pass2-locked-pkg-001",
        book_locked=True,
        lock_status="LOCKED",
        locked_at="2026-08-10T00:00:00Z",
        artifact_state=ArtifactState.LOCKED.value,
        pdf_bytes=_minimal_pdf_b64("locked"),
        **_export_refs("pass2-locked-pkg-001"),
    )
    stamp_artifact_identity(data)
    data["artifact_state"] = ArtifactState.LOCKED.value
    data.update(extra)
    return data


def _conflict_record(**extra) -> dict:
    data = _approved_record(
        package_id="pass2-conflict-pkg-001",
        artifact_id="pass2-conflict-pkg-001",
        artifact_state=ArtifactState.DRAFT.value,
        book_locked=True,
        lock_status="LOCKED",
    )
    data.update(extra)
    return data


def _identity_snapshot(data: dict) -> dict:
    return {
        "artifact_id": data.get("artifact_id") or data.get("package_id"),
        "artifact_revision": current_revision(data),
        "artifact_state": data.get("artifact_state"),
        "content_digest": data.get("content_digest"),
        "asset_manifest_digest": data.get("asset_manifest_digest"),
        "package_id": data.get("package_id"),
        "pdf_bytes": data.get("pdf_bytes"),
        "problems": copy.deepcopy(data.get("problems")),
        "cover_design": copy.deepcopy(data.get("cover_design")),
        "export_package_id": data.get("export_package_id"),
        "product_exports": copy.deepcopy(data.get("product_exports")),
    }


MATH_FIELDS = {
    "worksheet_title": "Pass2 New Project Math",
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


class ReopenPackagingIdentityPass2Tests(unittest.TestCase):
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

    def _create_project(self, data: dict, name: str) -> dict:
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
        body = resp.get_json()
        self._track(project_id=int(body["id"]))
        return body

    def _forbid_mutation_surface(self):
        hits: list[str] = []

        def _hit(name):
            def _inner(*_a, **_k):
                hits.append(name)
                raise AssertionError(f"must not call {name}")

            return _inner

        return hits, [
            patch("services.product.generate_product", side_effect=_hit("generate_product")),
            patch(
                "services.packaging.build_product_export",
                side_effect=_hit("build_product_export"),
            ),
            patch(
                "services.product_cover_agent.generate_cover",
                side_effect=_hit("generate_cover"),
            ),
            patch(
                "services.ebook_package.build_ebook_package",
                side_effect=_hit("build_ebook_package"),
            ),
        ]

    # --- 1–5 / 9: reopen state, identity, no mutation, conflict ---

    def test_01_reopen_resolves_draft_approved_locked(self):
        draft = self._create_project(_draft_record(), "Pass2 Reopen Draft")
        approved = self._create_project(_approved_record(), "Pass2 Reopen Approved")
        locked = self._create_project(_locked_record(), "Pass2 Reopen Locked")

        hits, patches = self._forbid_mutation_surface()
        with patches[0], patches[1], patches[2], patches[3]:
            for project, expected in (
                (draft, ArtifactState.DRAFT),
                (approved, ArtifactState.APPROVED),
                (locked, ArtifactState.LOCKED),
            ):
                resp = self.client.get(f"/projects/{project['id']}")
                self.assertEqual(resp.status_code, 200, resp.data)
                body = resp.get_json()
                self.assertEqual(body.get("artifact_state"), expected.value)
                self.assertEqual(
                    resolve_artifact_state(body.get("data") or {}), expected
                )
                self.assertEqual(
                    int(body.get("artifact_revision") or 0),
                    current_revision(project.get("data") or {}),
                )
                self.assertEqual(
                    body.get("artifact_id")
                    or (body.get("data") or {}).get("artifact_id"),
                    (project.get("data") or {}).get("artifact_id"),
                )
        self.assertEqual(hits, [])

    def test_02_reopen_preserves_authoritative_identity_no_mutation(self):
        project = self._create_project(_approved_record(), "Pass2 Reopen Identity")
        before = _identity_snapshot(project.get("data") or {})

        hits, patches = self._forbid_mutation_surface()
        with patches[0], patches[1], patches[2], patches[3]:
            resp = self.client.get(f"/projects/{project['id']}")
        self.assertEqual(resp.status_code, 200, resp.data)
        after_body = resp.get_json()
        after = _identity_snapshot(after_body.get("data") or {})
        self.assertEqual(after, before)
        self.assertEqual(after_body.get("artifact_state"), "APPROVED")
        self.assertEqual(hits, [])

    def test_03_reopen_conflict_fails_safely(self):
        project = self._create_project(_conflict_record(), "Pass2 Reopen Conflict")
        before = copy.deepcopy(project.get("data") or {})
        hits, patches = self._forbid_mutation_surface()
        with patches[0], patches[1], patches[2], patches[3]:
            resp = self.client.get(f"/projects/{project['id']}")
        self.assertEqual(resp.status_code, 409, resp.data)
        err = (resp.get_json() or {}).get("error") or ""
        self.assertIn("conflict", err.lower())
        import database

        stored = database.get_project(int(project["id"])).get("data") or {}
        self.assertEqual(stored, before)
        self.assertEqual(hits, [])

    def test_04_approved_edit_requires_create_draft_revision(self):
        project = self._create_project(_approved_record(), "Pass2 Approved Edit")
        pid = int(project["id"])
        hits, patches = self._forbid_mutation_surface()
        with patches[0], patches[1], patches[2], patches[3]:
            blocked = self.client.post(
                "/generate-product",
                json={
                    "project_id": pid,
                    "product_type": "math_worksheet",
                    "fields": MATH_FIELDS,
                },
            )
        self.assertEqual(blocked.status_code, 409, blocked.data)

        rev = self.client.post(
            f"/projects/{pid}/revisions",
            json={
                "create_draft_revision": True,
                "reason": "Pass2 edit after reopen",
                "expected_revision": current_revision(project.get("data") or {}),
                "expected_artifact_id": (project.get("data") or {}).get("artifact_id"),
            },
        )
        self.assertEqual(rev.status_code, 201, rev.data)
        reopened = self.client.get(f"/projects/{pid}").get_json()
        self.assertEqual(reopened.get("artifact_state"), "DRAFT")
        self.assertEqual(
            resolve_artifact_state(reopened.get("data") or {}), ArtifactState.DRAFT
        )

    def test_05_locked_edit_blocked(self):
        project = self._create_project(_locked_record(), "Pass2 Locked Edit")
        pid = int(project["id"])
        hits, patches = self._forbid_mutation_surface()
        with patches[0], patches[1], patches[2], patches[3]:
            for path, payload in (
                (
                    "/generate-product",
                    {
                        "project_id": pid,
                        "product_type": "math_worksheet",
                        "fields": MATH_FIELDS,
                    },
                ),
                (
                    "/cover/save",
                    {"project_id": pid, "overrides": {"title": "Nope"}},
                ),
            ):
                resp = self.client.post(path, json=payload)
                self.assertEqual(resp.status_code, 409, resp.data)
        rev = self.client.post(
            f"/projects/{pid}/revisions",
            json={
                "create_draft_revision": True,
                "reason": "locked should fail",
                "expected_revision": current_revision(project.get("data") or {}),
                "expected_artifact_id": (project.get("data") or {}).get("artifact_id"),
            },
        )
        self.assertEqual(rev.status_code, 409, rev.data)
        self.assertEqual(hits, [])

    def test_06_reopen_keeps_non_ebook_builder_and_research_brief(self):
        """Product-stage coloring project reopens with same type/brief — no ebook."""
        brief = {
            "product_title": "Pass2 Farm Friends Coloring",
            "target_audience": "Kids ages 4-8",
            "customer_problem": "Need calm screen-free coloring",
            "product_promise": "Cute farm animal pages",
            "main_transformation": "Relaxed creative time",
            "research_notes": "PASS2_RESEARCH_BRIEF_TOKEN_UNIQUE",
        }
        data = {
            "product_type": "coloring_book",
            "title": brief["product_title"],
            "type": "product",
            "fields": {
                "theme": "Farm Friends",
                "audience": brief["target_audience"],
                "pages": "8",
                "output_format": "Book",
            },
            "plan": dict(brief),
            "research_notes": brief["research_notes"],
            "artifact_state": ArtifactState.DRAFT.value,
            "artifact_revision": 1,
            "package_id": "pass2-coloring-reopen-001",
            "artifact_id": "pass2-coloring-reopen-001",
        }
        project = self._create_project(data, "Pass2 Coloring Reopen")
        hits, patches = self._forbid_mutation_surface()
        with patches[0], patches[1], patches[2], patches[3]:
            resp = self.client.get(f"/projects/{project['id']}")
        body = resp.get_json()
        pdata = body.get("data") or {}
        self.assertEqual(pdata.get("product_type"), "coloring_book")
        self.assertNotEqual(pdata.get("product_type"), "ebook")
        self.assertEqual(
            (pdata.get("plan") or {}).get("research_notes"),
            brief["research_notes"],
        )
        self.assertEqual(pdata.get("research_notes"), brief["research_notes"])
        self.assertEqual(hits, [])

    # --- 7–8 / 10–11: packaging, crossword, stale/orphan, new-project stamp ---

    def test_07_packaging_draft_approved_locked_policy(self):
        from services.packaging import build_product_export
        import database

        draft = self._create_project(_draft_record(), "Pass2 Pack Draft")
        approved = self._create_project(_approved_record(), "Pass2 Pack Approved")
        locked = self._create_project(
            _locked_record(), "Pass2 Pack Locked"
        )

        # Materialize LOCKED export package on disk for reuse.
        locked_data = locked.get("data") or {}
        locked_pkg = str(locked_data.get("export_package_id") or "")
        self._track(package_id=locked_pkg)
        pdf = base64.b64decode(locked_data["pdf_bytes"])
        _write_package(locked_pkg, {"sheet.pdf": pdf, "ebook.html": "<html></html>"})

        self.assertEqual(
            assert_packaging_allowed(draft["data"]), ArtifactState.DRAFT
        )
        self.assertEqual(
            assert_packaging_allowed(approved["data"]), ArtifactState.APPROVED
        )
        self.assertEqual(
            assert_packaging_allowed(locked["data"]), ArtifactState.LOCKED
        )
        self.assertFalse(packaging_may_rebuild_content(approved["data"]))
        self.assertFalse(packaging_may_rebuild_content(locked["data"]))
        self.assertFalse(packaging_may_rebuild_content(draft["data"]))

        # APPROVED packaging reproduces stored bytes; no content rewrite.
        before_approved = _identity_snapshot(approved["data"])
        with patch("services.product._crossword_pdf_payload") as cw_rebuild:
            export_resp = self.client.post(
                "/export-product", json={"project_id": approved["id"]}
            )
            self.assertEqual(export_resp.status_code, 200, export_resp.data)
            self.assertFalse(cw_rebuild.called)
        after_approved = database.get_project(int(approved["id"])).get("data") or {}
        snap = _identity_snapshot(after_approved)
        for key in (
            "content_digest",
            "asset_manifest_digest",
            "artifact_id",
            "artifact_revision",
            "pdf_bytes",
            "problems",
            "cover_design",
        ):
            self.assertEqual(snap[key], before_approved[key], key)
        self.assertEqual(
            resolve_artifact_state(after_approved), ArtifactState.APPROVED
        )
        self._track(package_id=export_resp.get_json()["package_id"])

        # LOCKED reuses existing export package; does not replace refs.
        locked_before = _identity_snapshot(locked_data)
        locked_export = self.client.post(
            "/export-product", json={"project_id": locked["id"]}
        )
        self.assertEqual(locked_export.status_code, 200, locked_export.data)
        self.assertEqual(
            locked_export.get_json()["package_id"], locked_pkg
        )
        locked_after = database.get_project(int(locked["id"])).get("data") or {}
        self.assertEqual(
            _identity_snapshot(locked_after)["pdf_bytes"],
            locked_before["pdf_bytes"],
        )
        self.assertEqual(
            locked_after.get("export_package_id"), locked_before["export_package_id"]
        )

        # DRAFT packaging from authoritative draft is allowed.
        draft_export = self.client.post(
            "/export-product", json={"project_id": draft["id"]}
        )
        self.assertEqual(draft_export.status_code, 200, draft_export.data)
        self._track(package_id=draft_export.get_json()["package_id"])

    def test_08_crossword_rebuild_blocked_for_approved_and_no_db_bypass(self):
        import io
        from pypdf import PdfReader, PdfWriter
        from reportlab.pdfgen import canvas
        from services.packaging import build_product_export
        from services.product import crossword_full_book_pdf_is_valid

        thin = io.BytesIO()
        c = canvas.Canvas(thin)
        for _ in range(21):
            c.drawString(72, 720, "stale thin crossword")
            c.showPage()
        c.save()
        writer = PdfWriter()
        writer.append(PdfReader(io.BytesIO(thin.getvalue())))
        writer.add_metadata(
            {
                "/Title": "Pass2 Thin Crossword",
                "/Subject": "10 Crossword Puzzles - Easy Level",
            }
        )
        stale_buf = io.BytesIO()
        writer.write(stale_buf)
        stale_pdf = stale_buf.getvalue()
        self.assertFalse(
            crossword_full_book_pdf_is_valid(stale_pdf, expected_puzzles=12)
        )

        approved = {
            "product_type": "crossword",
            "is_pdf": True,
            "is_book": True,
            "title": "Pass2 Thin Crossword",
            "puzzle_count": 10,
            "pdf_bytes": base64.b64encode(stale_pdf).decode("ascii"),
            "filename": "pass2_thin_crossword.pdf",
            "artifact_revision": 1,
            "package_id": "pass2-cw-approved-001",
            "artifact_id": "pass2-cw-approved-001",
            "fields": {
                "book_title": "Pass2 Thin Crossword",
                "theme": "Pass2 Thin Crossword",
                "output_format": "Full Book",
                "puzzles": "10",
                "creation_mode": "Topic (AI generates words)",
                "difficulty": "Easy",
                "include_answer_key": "Yes",
                "include_cover": "Yes",
            },
        }
        stamp_artifact_identity(approved)
        approved["artifact_state"] = ArtifactState.APPROVED.value
        self.assertFalse(packaging_may_rebuild_content(approved))

        with patch("database.update_project") as db_write, patch(
            "services.product._crossword_pdf_payload"
        ) as rebuild:
            with self.assertRaises(ValueError) as ctx:
                build_product_export(
                    {"id": 999001, "name": "Pass2 CW", "data": approved}
                )
            self.assertIn("silently regenerate", str(ctx.exception).lower())
            self.assertFalse(rebuild.called)
            self.assertFalse(db_write.called)

        # Unstamped DRAFT may rebuild export bytes only (no DB write / no mutate).
        legacy = dict(approved)
        legacy.pop("content_digest", None)
        legacy.pop("asset_manifest_digest", None)
        legacy.pop("artifact_state", None)
        self.assertTrue(packaging_may_rebuild_content(legacy))
        before_pdf = legacy.get("pdf_bytes")
        before_keys = set(legacy.keys())
        fake_rebuilt = {
            "pdf_bytes": _minimal_pdf_b64("cw-rebuilt-export-only"),
            "filename": "pass2_thin_crossword.pdf",
            "puzzle_count": 12,
        }
        valid_calls = {"n": 0}

        def _valid_after_rebuild(*_a, **_k):
            valid_calls["n"] += 1
            # First check on stored thin PDF → invalid; later checks on export → ok.
            return valid_calls["n"] > 1

        with patch("database.update_project") as db_write, patch(
            "services.product._crossword_pdf_payload", return_value=fake_rebuilt
        ), patch(
            "services.product.crossword_full_book_pdf_is_valid",
            side_effect=_valid_after_rebuild,
        ):
            result = build_product_export(
                {"id": 999002, "name": "Pass2 CW Draft", "data": legacy}
            )
            self.assertFalse(db_write.called)
        self.assertEqual(legacy.get("pdf_bytes"), before_pdf)
        self.assertEqual(set(legacy.keys()), before_keys)
        self.assertTrue(result.get("exports", {}).get("pdf_available"))
        self._track(package_id=result["package_id"])

    def test_09_stale_orphan_and_identity_mismatch_blocked(self):
        project = self._create_project(_approved_record(), "Pass2 Orphan Block")
        data = project.get("data") or {}
        self.assertTrue(
            package_belongs_to_project(data, data["export_package_id"])
        )
        self.assertFalse(
            package_belongs_to_project(data, "pass2-orphan-not-linked-zzzz")
        )

        from io import BytesIO
        from reportlab.pdfgen import canvas

        stale_pkg = "pass2orphan" + ("c" * 20)
        self._track(package_id=stale_pkg)
        buf = BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(72, 720, "STALE ORPHAN PASS2")
        c.showPage()
        c.save()
        _write_package(stale_pkg, {"stale.pdf": buf.getvalue()})
        stale_dl = self.client.get(f"/download/{stale_pkg}/stale.pdf")
        self.assertEqual(stale_dl.status_code, 403, stale_dl.data[:400])
        stale_json = stale_dl.get_json() or {}
        self.assertEqual(stale_json.get("error"), "download_blocked")
        self.assertIn(
            "stale_or_orphan_export_package",
            stale_json.get("violations") or [],
        )

        import database

        bad = dict(database.get_project(int(project["id"])).get("data") or {})
        bad["content_digest"] = "0" * 64
        database.update_project(int(project["id"]), None, bad, None)
        with patch("services.product._crossword_pdf_payload") as rebuild, patch(
            "services.product.generate_product"
        ) as gen:
            mismatch = self.client.post(
                "/export-product", json={"project_id": project["id"]}
            )
            self.assertEqual(mismatch.status_code, 400, mismatch.data)
            self.assertIn(
                "identity mismatch",
                ((mismatch.get_json() or {}).get("error") or "").lower(),
            )
            self.assertFalse(rebuild.called)
            self.assertFalse(gen.called)

    def test_10_new_project_generate_stamps_draft_identity(self):
        import services.product as product_mod
        from services.math_worksheet import pdf_builder as mw

        with patch.object(product_mod, "generate_product", wraps=product_mod.generate_product), patch.object(
            mw, "build_math_worksheet_pdf", wraps=mw.build_math_worksheet_pdf
        ):
            preview = self.client.post(
                "/generate-product",
                json={"product_type": "math_worksheet", "fields": MATH_FIELDS},
            )
        self.assertEqual(preview.status_code, 200, preview.data)
        body = preview.get_json()
        self.assertTrue(body.get("content_digest"))
        self.assertTrue(body.get("asset_manifest_digest"))
        self.assertTrue(body.get("artifact_id") or body.get("package_id"))
        self.assertEqual(int(body.get("artifact_revision") or 0), 1)
        self.assertEqual(body.get("artifact_state"), ArtifactState.DRAFT.value)
        self.assertEqual(resolve_artifact_state(body), ArtifactState.DRAFT)
        self.assertNotEqual(resolve_artifact_state(body), ArtifactState.APPROVED)
        self.assertNotEqual(resolve_artifact_state(body), ArtifactState.LOCKED)

        pdf = base64.b64decode(body["pdf_bytes"])
        self.assertEqual(
            body["content_digest"], content_digest_from_pdf_bytes(pdf)
        )

        saved = self._create_project(body, "Pass2 New Project Save")
        reopened = self.client.get(f"/projects/{saved['id']}").get_json()
        self.assertEqual(reopened.get("artifact_state"), "DRAFT")
        self.assertEqual(
            resolve_artifact_state(reopened.get("data") or {}), ArtifactState.DRAFT
        )
        rdata = reopened.get("data") or {}
        self.assertEqual(rdata.get("content_digest"), body.get("content_digest"))
        self.assertEqual(
            rdata.get("asset_manifest_digest"), body.get("asset_manifest_digest")
        )
        self.assertEqual(
            int(rdata.get("artifact_revision") or 0),
            int(body.get("artifact_revision") or 0),
        )

    def test_11_same_identity_rebuild_does_not_bump_revision(self):
        import database

        project = self._create_project(_approved_record(), "Pass2 Same Identity")
        before = database.get_project(int(project["id"])).get("data") or {}
        rev_before = current_revision(before)
        digest_before = before.get("content_digest")

        export1 = self.client.post(
            "/export-product", json={"project_id": project["id"]}
        )
        self.assertEqual(export1.status_code, 200, export1.data)
        self._track(package_id=export1.get_json()["package_id"])
        mid = database.get_project(int(project["id"])).get("data") or {}
        self.assertEqual(current_revision(mid), rev_before)
        self.assertEqual(mid.get("content_digest"), digest_before)

        export2 = self.client.post(
            "/export-product", json={"project_id": project["id"]}
        )
        self.assertEqual(export2.status_code, 200, export2.data)
        self._track(package_id=export2.get_json()["package_id"])
        after = database.get_project(int(project["id"])).get("data") or {}
        self.assertEqual(current_revision(after), rev_before)
        self.assertEqual(after.get("content_digest"), digest_before)
        self.assertEqual(
            resolve_artifact_state(after), ArtifactState.APPROVED
        )
        # Revision transition remains explicit — packaging never opens DRAFT.
        self.assertNotEqual(
            after.get("artifact_state"), ArtifactState.DRAFT.value
        )


if __name__ == "__main__":
    unittest.main()
