"""Gate 12: controlled APPROVED → new DRAFT revision entrypoint.

Proves the fourteen production-entrypoint requirements. Deterministic local
fixtures under FACTORY_TEST_MODE — zero paid/external calls. Does not wire
Generate Product, enhancement, cover, packaging, or dashboard buttons.
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
from services.quality.artifact_identity import stamp_artifact_identity  # noqa: E402
from services.quality.artifact_state import (  # noqa: E402
    ArtifactState,
    current_revision,
    has_verified_approval_evidence,
    resolve_artifact_state,
    transition_artifact_revision,
)


def _minimal_pdf_b64() -> str:
    return base64.b64encode(b"%PDF-1.4\n%gate12\n%%EOF\n").decode("ascii")


def _approved_record(**extra) -> dict:
    data = {
        "product_type": "math_worksheet",
        "title": "Gate12 Approved Worksheet",
        "package_id": "gate12-approved-pkg-001",
        "artifact_id": "gate12-approved-pkg-001",
        "artifact_revision": 3,
        "problems": [{"prompt": "1+1", "answer": "2"}],
        "pdf_bytes": _minimal_pdf_b64(),
        "qa_status": "accepted",
        "product_exports": {
            "pdf": {"url": "/download/gate12-approved-pkg-001/sheet.pdf"},
            "files": {"meta": {"package_id": "gate12-approved-pkg-001"}},
        },
        "export_package_id": "gate12-approved-pkg-001",
        "exports": {"folder": "exports/gate12-approved-pkg-001"},
        "audience": "Grade 3 students",
        "goal": "Practice addition facts",
    }
    stamp_artifact_identity(data)
    data["artifact_state"] = ArtifactState.APPROVED.value
    data.update(extra)
    return data


def _draft_record(**extra) -> dict:
    data = {
        "product_type": "math_worksheet",
        "title": "Gate12 Draft Worksheet",
        "package_id": "gate12-draft-pkg-001",
        "artifact_id": "gate12-draft-pkg-001",
        "artifact_revision": 1,
        "problems": [{"prompt": "2+2", "answer": "4"}],
        "pdf_bytes": _minimal_pdf_b64(),
    }
    data.update(extra)
    return data


def _locked_record(**extra) -> dict:
    data = _approved_record(
        title="Gate12 Locked Worksheet",
        package_id="gate12-locked-pkg-001",
        artifact_id="gate12-locked-pkg-001",
        book_locked=True,
        lock_status="LOCKED",
        locked_at="2026-08-10T00:00:00Z",
        artifact_state=ArtifactState.LOCKED.value,
    )
    stamp_artifact_identity(data)
    data.update(extra)
    return data


class ControlledRevisionTransitionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self._project_ids: list[int] = []

    def tearDown(self):
        for pid in self._project_ids:
            try:
                self.client.delete(f"/projects/{pid}")
            except Exception:
                pass

    def _create_project(self, data: dict, name: str = "Gate12 Project") -> tuple[int, dict]:
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

    def _revision_body(self, data: dict, **overrides) -> dict:
        body = {
            "create_draft_revision": True,
            "reason": "controlled gate12 revision",
            "expected_artifact_id": str(
                data.get("artifact_id") or data.get("package_id") or ""
            ),
            "expected_revision": int(data.get("artifact_revision") or 1),
        }
        body.update(overrides)
        return body

    def _forbid_generation_surface(self):
        hits: list[str] = []

        def _hit(name):
            def _inner(*_a, **_k):
                hits.append(name)
                raise AssertionError(f"revision entrypoint must not call {name}")

            return _inner

        return hits, [
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
            patch(
                "services.ebook_package.build_ebook_package",
                side_effect=_hit("build_ebook_package"),
                create=True,
            ),
        ]

    def test_01_requires_explicit_new_revision_request(self):
        """1. Require an explicit new-revision request."""
        project_id, stored = self._create_project(_approved_record())
        missing = self._revision_body(stored)
        del missing["create_draft_revision"]
        resp = self.client.post(f"/projects/{project_id}/revisions", json=missing)
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn("create_draft_revision", resp.get_json()["error"])

        false_flag = self._revision_body(stored, create_draft_revision=False)
        resp2 = self.client.post(f"/projects/{project_id}/revisions", json=false_flag)
        self.assertEqual(resp2.status_code, 400, resp2.data)

        import database

        after = database.get_project(project_id).get("data") or {}
        self.assertEqual(resolve_artifact_state(after), ArtifactState.APPROVED)
        self.assertEqual(current_revision(after), current_revision(stored))

    def test_02_through_07_approved_transition_preserves_lineage(self):
        """2–7, 9–12: load, resolve, APPROVED-only transition, persist, return."""
        import database

        approved = _approved_record()
        prior_export = copy.deepcopy(approved["product_exports"])
        prior_digest = approved["content_digest"]
        prior_assets = approved["asset_manifest_digest"]
        prior_rev = current_revision(approved)
        prior_artifact_id = approved["artifact_id"]

        project_id, stored = self._create_project(approved)
        self.assertEqual(resolve_artifact_state(stored), ArtifactState.APPROVED)

        hits, patches = self._forbid_generation_surface()
        with patches[0], patches[1], patches[2], patches[3]:
            # Spy: transition called exactly once; Save must not call it again.
            with patch(
                "services.quality.artifact_state.transition_artifact_revision",
                wraps=transition_artifact_revision,
            ) as transition_spy:
                resp = self.client.post(
                    f"/projects/{project_id}/revisions",
                    json=self._revision_body(stored),
                )

        self.assertEqual(resp.status_code, 201, resp.data)
        payload = resp.get_json()
        self.assertTrue(payload.get("ok"))
        self.assertEqual(payload["project_id"], project_id)
        self.assertEqual(payload["artifact_id"], prior_artifact_id)
        self.assertEqual(payload["artifact_revision"], prior_rev + 1)
        self.assertEqual(payload["artifact_state"], ArtifactState.DRAFT.value)
        self.assertEqual(transition_spy.call_count, 1)
        self.assertEqual(hits, [])

        after = database.get_project(project_id).get("data") or {}
        self.assertEqual(resolve_artifact_state(after), ArtifactState.DRAFT)
        self.assertEqual(current_revision(after), prior_rev + 1)
        self.assertEqual(after.get("artifact_id"), prior_artifact_id)
        self.assertEqual(after.get("package_id"), "gate12-approved-pkg-001")

        # 5–7 / 9–10: prior approved revision preserved; new DRAFT clears refs.
        prior = after.get("prior_approved_revision") or {}
        self.assertEqual(prior.get("artifact_revision"), prior_rev)
        self.assertEqual(prior.get("artifact_state"), ArtifactState.APPROVED.value)
        self.assertEqual(prior.get("content_digest"), prior_digest)
        self.assertEqual(prior.get("asset_manifest_digest"), prior_assets)
        self.assertEqual(prior.get("artifact_id"), prior_artifact_id)
        lineage = after.get("artifact_lineage") or []
        self.assertTrue(lineage)
        self.assertEqual(lineage[-1].get("content_digest"), prior_digest)
        self.assertIsNone(after.get("content_digest"))
        self.assertIsNone(after.get("asset_manifest_digest"))
        self.assertIsNone(after.get("qa_status"))
        self.assertNotIn("product_exports", after)
        self.assertNotIn("export_package_id", after)
        self.assertNotIn("exports", after)
        self.assertFalse(has_verified_approval_evidence(after))
        # Content lineage preserved on the new DRAFT (no regeneration).
        self.assertEqual(after.get("problems"), approved["problems"])
        self.assertEqual(after.get("pdf_bytes"), approved["pdf_bytes"])
        self.assertEqual(after.get("title"), approved["title"])
        # Snapshot still holds prior export identity proof.
        self.assertEqual(prior_export["files"]["meta"]["package_id"], prior_artifact_id)

        # 11–12: Save path does not additional-bump after success.
        project = database.get_project(project_id)
        meta = dict(project.get("data") or {})
        meta["seller_notes"] = "post-revision metadata"
        _persist_product_data(project, meta)
        final = database.get_project(project_id).get("data") or {}
        self.assertEqual(current_revision(final), prior_rev + 1)
        self.assertEqual(resolve_artifact_state(final), ArtifactState.DRAFT)
        self.assertEqual(final.get("seller_notes"), "post-revision metadata")

    def test_08_same_project_lineage(self):
        """8. Keep same project lineage (project id + artifact id)."""
        import database

        project_id, stored = self._create_project(_approved_record())
        resp = self.client.post(
            f"/projects/{project_id}/revisions",
            json=self._revision_body(stored),
        )
        self.assertEqual(resp.status_code, 201, resp.data)
        after = database.get_project(project_id).get("data") or {}
        self.assertEqual(int(database.get_project(project_id)["id"]), project_id)
        self.assertEqual(after.get("artifact_id"), stored.get("artifact_id"))
        self.assertEqual(after.get("package_id"), stored.get("package_id"))

    def test_13_reject_locked_draft_conflicting_missing_stale(self):
        """13. Reject LOCKED, DRAFT, conflicting, missing, or stale-source."""
        import database

        # DRAFT rejected
        draft_id, draft = self._create_project(_draft_record())
        resp_draft = self.client.post(
            f"/projects/{draft_id}/revisions",
            json=self._revision_body(draft),
        )
        self.assertEqual(resp_draft.status_code, 409, resp_draft.data)
        self.assertIn("APPROVED", resp_draft.get_json()["error"])
        self.assertEqual(
            resolve_artifact_state(database.get_project(draft_id)["data"]),
            ArtifactState.DRAFT,
        )

        # LOCKED rejected
        locked_id, locked = self._create_project(_locked_record())
        resp_locked = self.client.post(
            f"/projects/{locked_id}/revisions",
            json=self._revision_body(locked),
        )
        self.assertEqual(resp_locked.status_code, 409, resp_locked.data)
        self.assertIn("LOCKED", resp_locked.get_json()["error"].upper())
        self.assertEqual(
            resolve_artifact_state(database.get_project(locked_id)["data"]),
            ArtifactState.LOCKED,
        )

        # Conflicting evidence rejected (no storage change)
        conflict = _approved_record(
            artifact_state=ArtifactState.DRAFT.value,
            book_locked=True,
            lock_status="LOCKED",
        )
        # Force conflicting markers without going through stamp cleanly.
        conflict["content_digest"] = "a" * 64
        conflict["asset_manifest_digest"] = "b" * 64
        conflict_id, _ = self._create_project(conflict, name="Gate12 Conflict")
        # If create stored conflicting state, revision must 409.
        stored_conflict = database.get_project(conflict_id).get("data") or {}
        resp_conflict = self.client.post(
            f"/projects/{conflict_id}/revisions",
            json=self._revision_body(
                stored_conflict,
                expected_artifact_id=str(
                    stored_conflict.get("artifact_id")
                    or stored_conflict.get("package_id")
                    or "gate12-approved-pkg-001"
                ),
                expected_revision=current_revision(stored_conflict),
            ),
        )
        self.assertIn(resp_conflict.status_code, (409, 400), resp_conflict.data)

        # Missing project
        resp_missing = self.client.post(
            "/projects/999999991/revisions",
            json={
                "create_draft_revision": True,
                "reason": "missing",
                "expected_artifact_id": "x",
                "expected_revision": 1,
            },
        )
        self.assertEqual(resp_missing.status_code, 404, resp_missing.data)

        # Stale expected revision / artifact id → 409, no change
        ok_id, ok_stored = self._create_project(
            _approved_record(package_id="gate12-stale-pkg", artifact_id="gate12-stale-pkg")
        )
        before = copy.deepcopy(database.get_project(ok_id).get("data") or {})
        stale_rev = self.client.post(
            f"/projects/{ok_id}/revisions",
            json=self._revision_body(ok_stored, expected_revision=current_revision(ok_stored) + 9),
        )
        self.assertEqual(stale_rev.status_code, 409, stale_rev.data)
        self.assertIn("conflict", stale_rev.get_json()["error"].lower())
        stale_id = self.client.post(
            f"/projects/{ok_id}/revisions",
            json=self._revision_body(ok_stored, expected_artifact_id="not-the-saved-id"),
        )
        self.assertEqual(stale_id.status_code, 409, stale_id.data)
        after_stale = database.get_project(ok_id).get("data") or {}
        self.assertEqual(after_stale, before)

    def test_14_reject_smuggled_content_assets_cover_digests_exports(self):
        """14. Reject replacement content/assets/cover/digests/export fields."""
        import database

        project_id, stored = self._create_project(_approved_record())
        before = copy.deepcopy(database.get_project(project_id).get("data") or {})
        smuggled_keys = [
            ("problems", [{"prompt": "SMUGGLE", "answer": "9"}]),
            ("pdf_bytes", _minimal_pdf_b64() + "x"),
            ("cover_design", {"local_image_path": "exports/tampered/img_cover.png"}),
            ("cover_image", "exports/tampered/img_cover.png"),
            ("content_digest", "0" * 64),
            ("asset_manifest_digest", "f" * 64),
            ("product_exports", {"pdf": {"url": "/hijack.pdf"}}),
            ("export_package_id", "hijacked-export"),
            ("exports", {"folder": "exports/hijacked"}),
            ("image_jobs", [{"id": "smuggle"}]),
            ("data", {"title": "nested hijack"}),
            ("pages", [{"n": 1}]),
            ("words", ["hijack"]),
        ]
        for key, value in smuggled_keys:
            body = self._revision_body(stored)
            body[key] = value
            resp = self.client.post(f"/projects/{project_id}/revisions", json=body)
            self.assertEqual(resp.status_code, 400, f"{key}: {resp.data}")
            err = resp.get_json()["error"].lower()
            self.assertTrue(
                "unsupported" in err or "cannot include" in err,
                msg=f"{key}: {err}",
            )
        after = database.get_project(project_id).get("data") or {}
        self.assertEqual(after, before)
        self.assertEqual(resolve_artifact_state(after), ArtifactState.APPROVED)

    def test_15_never_generate_and_repeat_request_conflicts(self):
        """15 + concurrency: no generation; identical repeat → 409 stale."""
        import database

        project_id, stored = self._create_project(_approved_record())
        body = self._revision_body(stored)
        hits, patches = self._forbid_generation_surface()
        with patches[0], patches[1], patches[2], patches[3]:
            first = self.client.post(f"/projects/{project_id}/revisions", json=body)
            self.assertEqual(first.status_code, 201, first.data)
            repeat = self.client.post(f"/projects/{project_id}/revisions", json=body)
        self.assertEqual(repeat.status_code, 409, repeat.data)
        self.assertIn("conflict", repeat.get_json()["error"].lower())
        self.assertEqual(hits, [])

        after = database.get_project(project_id).get("data") or {}
        self.assertEqual(current_revision(after), current_revision(stored) + 1)
        self.assertEqual(resolve_artifact_state(after), ArtifactState.DRAFT)
        # Only one new revision was created.
        self.assertEqual(len(after.get("artifact_lineage") or []), 1)

    def test_16_save_does_not_transition_or_bump_on_ordinary_path(self):
        """Ordinary Save never transitions and never bumps revision."""
        import database

        project_id, stored = self._create_project(_approved_record())
        baseline_rev = current_revision(stored)
        project = database.get_project(project_id)
        meta = dict(project.get("data") or {})
        meta["listing_title"] = "ordinary save metadata"

        with patch(
            "services.quality.artifact_state.transition_artifact_revision",
            side_effect=AssertionError("Save must not call transition"),
        ):
            _persist_product_data(project, meta)

        after = database.get_project(project_id).get("data") or {}
        self.assertEqual(current_revision(after), baseline_rev)
        self.assertEqual(resolve_artifact_state(after), ArtifactState.APPROVED)
        self.assertEqual(after.get("listing_title"), "ordinary save metadata")

        # Attempted Save revision bump still rejected.
        bumped = copy.deepcopy(after)
        bumped["artifact_revision"] = baseline_rev + 1
        with self.assertRaises(Exception):
            _persist_product_data(database.get_project(project_id), bumped)
        blocked = database.get_project(project_id).get("data") or {}
        self.assertEqual(current_revision(blocked), baseline_rev)


if __name__ == "__main__":
    unittest.main()
