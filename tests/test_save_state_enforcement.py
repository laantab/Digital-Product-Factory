"""Gate 11: Save / _persist_product_data enforces DRAFT / APPROVED / LOCKED state.

Proves the nine Save policy points at the shared persistence boundary.
Deterministic local fixtures under FACTORY_TEST_MODE — zero paid/external calls.
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

from app import app, _persist_product_data  # noqa: E402
from services.quality.artifact_identity import (  # noqa: E402
    content_digest_from_pdf_bytes,
    stamp_artifact_identity,
)
from services.quality.artifact_state import (  # noqa: E402
    ArtifactState,
    ArtifactStateError,
    current_revision,
    resolve_artifact_state,
)


FIELDS = {
    "worksheet_title": "Gate11 Save State Enforcement",
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


def _identity_snapshot(project_id: int, data: dict) -> dict:
    pdf = base64.b64decode(data["pdf_bytes"]) if data.get("pdf_bytes") else b""
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    return {
        "project_id": project_id,
        "artifact_id": data.get("artifact_id") or data.get("package_id"),
        "artifact_revision": int(data.get("artifact_revision") or 0),
        "artifact_state": data.get("artifact_state"),
        "product_type": data.get("product_type"),
        "title": data.get("title"),
        "problems": list(data.get("problems") or []),
        "pages": data.get("pages"),
        "words": data.get("words"),
        "challenge_problems": data.get("challenge_problems"),
        "image_jobs": list(data.get("image_jobs") or []),
        "cover_ref": (
            cover.get("local_image_path")
            or cover.get("asset_url")
            or cover.get("image_url")
            or data.get("cover_image")
            or ""
        ),
        "content_digest": data.get("content_digest"),
        "asset_manifest_digest": data.get("asset_manifest_digest"),
        "qa_status": data.get("qa_status"),
        "pdf_digest": content_digest_from_pdf_bytes(pdf) if pdf else None,
        "package_id": data.get("package_id"),
        "book_locked": data.get("book_locked"),
        "lock_status": data.get("lock_status"),
    }


def _minimal_pdf_b64() -> str:
    return base64.b64encode(b"%PDF-1.4\n%gate11\n%%EOF\n").decode("ascii")


def _draft_record(**extra) -> dict:
    base = {
        "product_type": "math_worksheet",
        "title": "Gate11 Draft Worksheet",
        "package_id": "gate11-draft-pkg-001",
        "artifact_id": "gate11-draft-pkg-001",
        "artifact_revision": 1,
        "problems": [{"prompt": "1+1", "answer": "2"}],
        "pdf_bytes": _minimal_pdf_b64(),
        "audience": FIELDS["audience"],
        "goal": FIELDS["goal"],
    }
    base.update(extra)
    return base


def _approved_record(**extra) -> dict:
    data = _draft_record(
        title="Gate11 Approved Worksheet",
        package_id="gate11-approved-pkg-001",
        artifact_id="gate11-approved-pkg-001",
        qa_status="accepted",
    )
    stamp_artifact_identity(data)
    data.update(extra)
    return data


def _locked_record(**extra) -> dict:
    data = _approved_record(
        title="Gate11 Locked Worksheet",
        package_id="gate11-locked-pkg-001",
        artifact_id="gate11-locked-pkg-001",
        book_locked=True,
        lock_status="LOCKED",
        locked_at="2026-08-10T00:00:00Z",
        artifact_state="LOCKED",
    )
    stamp_artifact_identity(data)
    data.update(extra)
    return data


class SaveStateEnforcementTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self._project_ids: list[int] = []

    def tearDown(self):
        for pid in self._project_ids:
            try:
                self.client.delete(f"/projects/{pid}")
            except Exception:
                pass

    def _create_project(self, data: dict, name: str = "Gate11 Project") -> tuple[int, dict]:
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

    def _forbid_side_effects(self):
        """Patch generation / export / transition / cover so Save cannot invoke them."""
        hits: list[str] = []

        def _hit(name):
            def _inner(*_a, **_k):
                hits.append(name)
                raise AssertionError(f"Save must not call {name}")

            return _inner

        return hits, [
            patch(
                "services.quality.artifact_state.transition_artifact_revision",
                side_effect=_hit("transition_artifact_revision"),
            ),
            patch(
                "services.product.generate_product",
                side_effect=_hit("generate_product"),
            ),
            patch(
                "services.packaging.build_product_export",
                side_effect=_hit("build_product_export"),
            ),
            patch(
                "services.product_cover_agent.generate_cover",
                side_effect=_hit("generate_cover"),
            ),
        ]

    def test_01_draft_allows_legitimate_persistence(self):
        """1. DRAFT: allow legitimate existing draft persistence."""
        import database

        project_id, stored = self._create_project(_draft_record())
        self.assertEqual(resolve_artifact_state(stored), ArtifactState.DRAFT)
        baseline_rev = current_revision(stored)

        project = database.get_project(project_id)
        updated = dict(project.get("data") or {})
        updated["title"] = "Gate11 Draft Edited Title"
        updated["problems"] = list(updated.get("problems") or []) + [
            {"prompt": "2+2", "answer": "4"}
        ]
        updated["audience"] = "Updated draft audience"

        hits, patches = self._forbid_side_effects()
        with patches[0], patches[1], patches[2], patches[3]:
            _persist_product_data(project, updated)

        after = database.get_project(project_id).get("data") or {}
        self.assertEqual(resolve_artifact_state(after), ArtifactState.DRAFT)
        self.assertEqual(after.get("title"), "Gate11 Draft Edited Title")
        self.assertEqual(len(after.get("problems") or []), 2)
        self.assertEqual(current_revision(after), baseline_rev)
        self.assertEqual(hits, [])

    def test_02_approved_metadata_ok_content_blocked(self):
        """2. APPROVED: metadata-only ok; block artifact/content/asset mutation."""
        import database

        project_id, stored = self._create_project(_approved_record())
        self.assertEqual(resolve_artifact_state(stored), ArtifactState.APPROVED)
        baseline = _identity_snapshot(project_id, stored)

        project = database.get_project(project_id)
        meta = dict(project.get("data") or {})
        meta["seller_notes"] = "listing ready"
        meta["launch_notes"] = "gate11 metadata"
        meta["publication"] = {"intent": "metadata_only", "external_publish": False}

        hits, patches = self._forbid_side_effects()
        with patches[0], patches[1], patches[2], patches[3]:
            _persist_product_data(project, meta)

        after = database.get_project(project_id).get("data") or {}
        self.assertEqual(_identity_snapshot(project_id, after), baseline)
        self.assertEqual(after.get("seller_notes"), "listing ready")
        self.assertEqual(after.get("launch_notes"), "gate11 metadata")
        self.assertEqual(resolve_artifact_state(after), ArtifactState.APPROVED)

        mutated = copy.deepcopy(after)
        mutated["title"] = "Hijacked Approved Title"
        mutated["problems"] = list(mutated.get("problems") or []) + [
            {"prompt": "SMUGGLE", "answer": "0"}
        ]
        with self.assertRaises((ValueError, ArtifactStateError)):
            _persist_product_data(database.get_project(project_id), mutated)

        blocked = database.get_project(project_id).get("data") or {}
        self.assertEqual(_identity_snapshot(project_id, blocked), baseline)
        self.assertEqual(blocked.get("seller_notes"), "listing ready")
        self.assertEqual(hits, [])

    def test_03_locked_metadata_ok_content_blocked(self):
        """3. LOCKED: metadata-only when policy allows; content mutation blocked."""
        import database

        project_id, stored = self._create_project(_locked_record())
        self.assertEqual(resolve_artifact_state(stored), ArtifactState.LOCKED)
        baseline = _identity_snapshot(project_id, stored)

        project = database.get_project(project_id)
        meta = dict(project.get("data") or {})
        meta["listing_title"] = "Locked listing title"
        meta["next_steps"] = {"panel": "gate11", "note": "metadata only"}

        hits, patches = self._forbid_side_effects()
        with patches[0], patches[1], patches[2], patches[3]:
            _persist_product_data(project, meta)

        after = database.get_project(project_id).get("data") or {}
        self.assertEqual(_identity_snapshot(project_id, after), baseline)
        self.assertEqual(after.get("listing_title"), "Locked listing title")
        self.assertEqual(resolve_artifact_state(after), ArtifactState.LOCKED)

        mutated = copy.deepcopy(after)
        mutated["title"] = "Unlock Attempt"
        mutated["book_locked"] = False
        mutated["lock_status"] = "DRAFT"
        with self.assertRaises((ValueError, ArtifactStateError)):
            _persist_product_data(database.get_project(project_id), mutated)

        blocked = database.get_project(project_id).get("data") or {}
        self.assertEqual(_identity_snapshot(project_id, blocked), baseline)
        self.assertTrue(blocked.get("book_locked"))
        self.assertEqual(str(blocked.get("lock_status") or "").upper(), "LOCKED")
        self.assertEqual(hits, [])

    def test_04_save_never_calls_transition_or_generation(self):
        """4 + 7. Save never calls transition_artifact_revision / generate / export / cover."""
        import database

        project_id, stored = self._create_project(_approved_record())
        project = database.get_project(project_id)
        meta = dict(project.get("data") or {})
        meta["goal"] = "metadata touch only"

        hits, patches = self._forbid_side_effects()
        with patches[0], patches[1], patches[2], patches[3]:
            _persist_product_data(project, meta)

        # Also exercise PUT Save boundary
        put_body = {
            "data": {
                **(database.get_project(project_id).get("data") or {}),
                "audience": "PUT metadata audience",
            }
        }
        with patches[0], patches[1], patches[2], patches[3]:
            resp = self.client.put(f"/projects/{project_id}", json=put_body)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(hits, [])
        self.assertEqual(resolve_artifact_state(stored), ArtifactState.APPROVED)

    def test_05_save_never_bumps_revision(self):
        """5. Save must NEVER bump a revision automatically."""
        import database

        project_id, stored = self._create_project(
            _approved_record(artifact_revision=3)
        )
        self.assertEqual(current_revision(stored), 3)

        project = database.get_project(project_id)
        bumped = dict(project.get("data") or {})
        bumped["artifact_revision"] = 4
        bumped["seller_notes"] = "should not land with bump"

        hits, patches = self._forbid_side_effects()
        with patches[0], patches[1], patches[2], patches[3]:
            with self.assertRaises((ValueError, ArtifactStateError)) as ctx:
                _persist_product_data(project, bumped)
        self.assertIn("artifact_revision", str(ctx.exception).lower())

        after = database.get_project(project_id).get("data") or {}
        self.assertEqual(current_revision(after), 3)
        self.assertNotEqual(after.get("seller_notes"), "should not land with bump")
        self.assertEqual(hits, [])

    def test_06_save_never_clears_approval_or_lock(self):
        """6. Save must NEVER clear approval or lock status."""
        import database

        # Approval clear
        project_id, stored = self._create_project(_approved_record())
        baseline = _identity_snapshot(project_id, stored)
        cleared = dict(database.get_project(project_id).get("data") or {})
        cleared["content_digest"] = ""
        cleared["asset_manifest_digest"] = ""
        with self.assertRaises((ValueError, ArtifactStateError)):
            _persist_product_data(database.get_project(project_id), cleared)
        after = database.get_project(project_id).get("data") or {}
        self.assertEqual(_identity_snapshot(project_id, after), baseline)

        # Lock clear
        locked_id, locked_stored = self._create_project(_locked_record())
        locked_baseline = _identity_snapshot(locked_id, locked_stored)
        unlock = dict(database.get_project(locked_id).get("data") or {})
        unlock["book_locked"] = False
        unlock["lock_status"] = ""
        unlock["artifact_state"] = "DRAFT"
        with self.assertRaises((ValueError, ArtifactStateError)):
            _persist_product_data(database.get_project(locked_id), unlock)
        locked_after = database.get_project(locked_id).get("data") or {}
        self.assertEqual(_identity_snapshot(locked_id, locked_after), locked_baseline)

    def test_07_conflicting_state_fails_safely_record_unchanged(self):
        """8. Conflicting / unverifiable state evidence must fail safely.

        Also proves failed saves leave the stored record unchanged.
        """
        import database

        conflict = _draft_record(
            artifact_state="DRAFT",
            book_locked=True,
            lock_status="LOCKED",
            package_id="gate11-conflict-pkg-001",
            artifact_id="gate11-conflict-pkg-001",
        )
        project_id, stored = self._create_project(conflict)
        baseline = _identity_snapshot(project_id, stored)

        with self.assertRaises(ArtifactStateError):
            resolve_artifact_state(stored)

        project = database.get_project(project_id)
        attempt = dict(project.get("data") or {})
        attempt["audience"] = "should not persist under conflict"

        hits, patches = self._forbid_side_effects()
        with patches[0], patches[1], patches[2], patches[3]:
            with self.assertRaises((ValueError, ArtifactStateError)):
                _persist_product_data(project, attempt)

        after = database.get_project(project_id).get("data") or {}
        self.assertEqual(_identity_snapshot(project_id, after), baseline)
        self.assertNotEqual(after.get("audience"), "should not persist under conflict")
        self.assertEqual(hits, [])

    def test_08_legacy_projects_resolve_without_migration(self):
        """9. Legacy projects resolve via Gate 10 resolver without migration."""
        import database

        # Legacy approved: digests only, no artifact_state field
        legacy_approved = _approved_record()
        legacy_approved.pop("artifact_state", None)
        project_id, stored = self._create_project(legacy_approved)
        self.assertNotIn("artifact_state", stored)
        self.assertEqual(resolve_artifact_state(stored), ArtifactState.APPROVED)

        project = database.get_project(project_id)
        meta = dict(project.get("data") or {})
        meta["publish_notes"] = "legacy metadata"
        baseline = _identity_snapshot(project_id, stored)

        hits, patches = self._forbid_side_effects()
        with patches[0], patches[1], patches[2], patches[3]:
            _persist_product_data(project, meta)

        after = database.get_project(project_id).get("data") or {}
        self.assertNotIn("artifact_state", after)  # no migration write
        self.assertEqual(resolve_artifact_state(after), ArtifactState.APPROVED)
        self.assertEqual(_identity_snapshot(project_id, after), baseline)
        self.assertEqual(after.get("publish_notes"), "legacy metadata")

        # Legacy draft: no digests, no lock
        draft_id, draft_stored = self._create_project(
            _draft_record(package_id="gate11-legacy-draft-001")
        )
        self.assertEqual(resolve_artifact_state(draft_stored), ArtifactState.DRAFT)
        draft_project = database.get_project(draft_id)
        draft_data = dict(draft_project.get("data") or {})
        draft_data["goal"] = "legacy draft edit"
        with patches[0], patches[1], patches[2], patches[3]:
            _persist_product_data(draft_project, draft_data)
        draft_after = database.get_project(draft_id).get("data") or {}
        self.assertEqual(draft_after.get("goal"), "legacy draft edit")
        self.assertEqual(resolve_artifact_state(draft_after), ArtifactState.DRAFT)
        self.assertEqual(hits, [])

    def test_09_put_save_uses_shared_boundary_failed_unchanged(self):
        """PUT Save shares the boundary; failed mutation leaves record unchanged."""
        import database

        project_id, stored = self._create_project(_approved_record())
        baseline = _identity_snapshot(project_id, stored)

        hits, patches = self._forbid_side_effects()
        mutated = copy.deepcopy(stored)
        mutated["title"] = "PUT Hijack"
        mutated["artifact_revision"] = int(stored.get("artifact_revision") or 1) + 9
        mutated["content_digest"] = "0" * 64

        with patches[0], patches[1], patches[2], patches[3]:
            resp = self.client.put(
                f"/projects/{project_id}",
                json={"data": mutated},
            )
        self.assertEqual(resp.status_code, 400, resp.data)

        after = database.get_project(project_id).get("data") or {}
        self.assertEqual(_identity_snapshot(project_id, after), baseline)
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
