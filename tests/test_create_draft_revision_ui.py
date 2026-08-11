"""Gate 13: Create Draft Revision UI (Saved Projects) — Flask client + JS contracts.

Proves the ten UI production requirements for APPROVED → new DRAFT. No Playwright.
No paid/external calls; no product/cover/PDF/ZIP generation.
"""
from __future__ import annotations

import base64
import copy
import os
import re
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
)

APP_JS = ROOT / "static" / "js" / "app.js"
INDEX_HTML = ROOT / "templates" / "index.html"


def _minimal_pdf_b64() -> str:
    return base64.b64encode(b"%PDF-1.4\n%gate13\n%%EOF\n").decode("ascii")


def _approved_record(**extra) -> dict:
    data = {
        "product_type": "math_worksheet",
        "title": "Gate13 Approved Worksheet",
        "package_id": "gate13-approved-pkg-001",
        "artifact_id": "gate13-approved-pkg-001",
        "artifact_revision": 2,
        "problems": [{"prompt": "3+3", "answer": "6"}],
        "pdf_bytes": _minimal_pdf_b64(),
        "qa_status": "accepted",
        "product_exports": {
            "pdf": {"url": "/download/gate13-approved-pkg-001/sheet.pdf"},
            "files": {"meta": {"package_id": "gate13-approved-pkg-001"}},
        },
        "export_package_id": "gate13-approved-pkg-001",
        "exports": {"folder": "exports/gate13-approved-pkg-001"},
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
        "title": "Gate13 Draft Worksheet",
        "package_id": "gate13-draft-pkg-001",
        "artifact_id": "gate13-draft-pkg-001",
        "artifact_revision": 1,
        "problems": [{"prompt": "1+1", "answer": "2"}],
        "pdf_bytes": _minimal_pdf_b64(),
        "artifact_state": ArtifactState.DRAFT.value,
    }
    data.update(extra)
    return data


def _locked_record(**extra) -> dict:
    data = _approved_record(
        title="Gate13 Locked Worksheet",
        package_id="gate13-locked-pkg-001",
        artifact_id="gate13-locked-pkg-001",
        book_locked=True,
        lock_status="LOCKED",
        locked_at="2026-08-10T00:00:00Z",
        artifact_state=ArtifactState.LOCKED.value,
    )
    stamp_artifact_identity(data)
    data.update(extra)
    return data


def _mirror_build_payload(project: dict) -> dict:
    """Mirror static/js/app.js buildCreateDraftRevisionPayload."""
    d = project.get("data") if isinstance(project.get("data"), dict) else {}
    artifact_id = str(
        project.get("artifact_id")
        or d.get("artifact_id")
        or d.get("package_id")
        or ""
    ).strip()
    raw_rev = (
        project.get("artifact_revision")
        if project.get("artifact_revision") is not None
        else d.get("artifact_revision")
    )
    try:
        revision = max(1, int(raw_rev if raw_rev is not None else 1))
    except (TypeError, ValueError):
        revision = 1
    return {
        "create_draft_revision": True,
        "reason": "Create draft revision from approved artifact",
        "expected_artifact_id": artifact_id,
        "expected_revision": revision,
    }


class CreateDraftRevisionUITests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.assertTrue(APP_JS.is_file(), f"missing {APP_JS}")
        self.app_js = APP_JS.read_text(encoding="utf-8")
        self._project_ids: list[int] = []

    def tearDown(self):
        for pid in self._project_ids:
            try:
                self.client.delete(f"/projects/{pid}")
            except Exception:
                pass

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
        saved = resp.get_json()
        self._project_ids.append(int(saved["id"]))
        return saved

    def _forbid_generation_surface(self):
        hits: list[str] = []

        def _hit(name):
            def _inner(*_a, **_k):
                hits.append(name)
                raise AssertionError(f"draft revision UI path must not call {name}")

            return _inner

        return hits, [
            patch(
                "services.product.generate_product",
                side_effect=_hit("generate_product"),
            ),
            patch(
                "services.ebook.generate_ebook",
                side_effect=_hit("generate_ebook"),
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

    # --- 1 & 2: visibility for APPROVED only; hidden for DRAFT / LOCKED ---

    def test_01_control_visible_only_for_approved(self):
        src = self.app_js
        self.assertIn("function shouldShowCreateDraftRevision(", src)
        self.assertIn('state === "APPROVED"', src)
        self.assertIn("data-create-draft-revision", src)
        self.assertIn("Create Draft Revision", src)
        # Dashboard rows must not include the control.
        dash_block = src[src.find("if (isDash)"): src.find("// Full Saved Projects")]
        self.assertNotIn("data-create-draft-revision", dash_block)

        approved = self._create_project(_approved_record(), "Gate13 Approved UI")
        draft = self._create_project(_draft_record(), "Gate13 Draft UI")
        locked = self._create_project(_locked_record(), "Gate13 Locked UI")

        for pid, expect_state in (
            (approved["id"], "APPROVED"),
            (draft["id"], "DRAFT"),
            (locked["id"], "LOCKED"),
        ):
            got = self.client.get(f"/projects/{pid}")
            self.assertEqual(got.status_code, 200, got.data)
            body = got.get_json()
            self.assertEqual(body.get("artifact_state"), expect_state)

        listing = self.client.get("/projects?include_system=1")
        self.assertEqual(listing.status_code, 200, listing.data)
        by_id = {int(p["id"]): p for p in listing.get_json()}
        self.assertEqual(by_id[approved["id"]]["artifact_state"], "APPROVED")
        self.assertEqual(by_id[draft["id"]]["artifact_state"], "DRAFT")
        self.assertEqual(by_id[locked["id"]]["artifact_state"], "LOCKED")

        # Mirror UI visibility predicate.
        self.assertTrue(
            by_id[approved["id"]]["artifact_state"] == "APPROVED"
        )
        self.assertFalse(by_id[draft["id"]]["artifact_state"] == "APPROVED")
        self.assertFalse(by_id[locked["id"]]["artifact_state"] == "APPROVED")

    # --- 3: explanation that approved is preserved ---

    def test_02_explains_approved_preserved_new_draft(self):
        src = self.app_js
        self.assertIn("Approved version preserved", src)
        self.assertIn("editing continues in a new draft", src)
        self.assertIn("data-draft-revision-note", src)
        self.assertIn(
            "Your approved version will be preserved. Editing continues in a new draft",
            src,
        )

    # --- 4: deliberate confirmation before POST ---

    def test_03_requires_confirmation_before_post(self):
        src = self.app_js
        fn = src[src.find("async function createDraftRevision("):]
        fn = fn[: fn.find("\nfunction projectRow(")]
        self.assertIn("confirm(", fn)
        self.assertIn("confirmMsg", fn)
        # Confirm must precede the revisions fetch.
        self.assertLess(fn.find("confirm(confirmMsg)"), fn.find("/revisions"))
        self.assertIn('if (!confirm(confirmMsg)) return;', fn)

    # --- 5: forbidden labels ---

    def test_04_does_not_use_regenerate_replace_start_over_labels(self):
        src = self.app_js
        # Control label and nearby Gate 13 helpers must not use forbidden verbs.
        block_start = src.find("function projectArtifactMeta(")
        block_end = src.find("function projectRow(")
        block = src[block_start:block_end]
        for forbidden in ("Regenerate", "Replace", "Start Over"):
            self.assertNotIn(forbidden, block)
        self.assertIn(">Create Draft Revision<", src)
        self.assertNotRegex(
            src,
            re.compile(
                r'data-create-draft-revision[^>]*>\s*(Regenerate|Replace|Start Over)',
                re.I,
            ),
        )

    # --- 6: double-submit prevention ---

    def test_05_prevents_double_submission_while_pending(self):
        src = self.app_js
        fn = src[src.find("async function createDraftRevision("):]
        fn = fn[: fn.find("\nfunction projectRow(")]
        self.assertIn("if (btn && btn.disabled) return;", fn)
        self.assertIn("setBusyEl(btn, true)", fn)
        self.assertIn("setBusyEl(btn, false)", fn)
        self.assertIn("finally", fn)

    # --- 7 & 8: POST payload only transition fields ---

    def test_06_post_payload_only_transition_fields(self):
        src = self.app_js
        self.assertIn("function buildCreateDraftRevisionPayload(", src)
        self.assertIn("create_draft_revision: true", src)
        self.assertIn("expected_artifact_id:", src)
        self.assertIn("expected_revision:", src)
        self.assertIn("`/projects/${p.id}/revisions`", src)
        self.assertIn('method: "POST"', src)

        approved = self._create_project(_approved_record(), "Gate13 Payload UI")
        got = self.client.get(f"/projects/{approved['id']}")
        project = got.get_json()
        payload = _mirror_build_payload(project)
        self.assertEqual(
            set(payload.keys()),
            {
                "create_draft_revision",
                "reason",
                "expected_artifact_id",
                "expected_revision",
            },
        )
        for forbidden in (
            "content",
            "pdf_bytes",
            "product_exports",
            "exports",
            "cover",
            "problems",
            "data",
            "content_digest",
            "asset_manifest_digest",
        ):
            self.assertNotIn(forbidden, payload)

        hits, patches = self._forbid_generation_surface()
        with patches[0], patches[1], patches[2], patches[3]:
            resp = self.client.post(
                f"/projects/{approved['id']}/revisions", json=payload
            )
        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(hits, [])

    # --- 9: success opens builder / edit view for new DRAFT ---

    def test_07_success_opens_edit_view_for_new_draft(self):
        src = self.app_js
        fn = src[src.find("async function createDraftRevision("):]
        fn = fn[: fn.find("\nfunction projectRow(")]
        self.assertIn("openProject(project)", fn)
        self.assertIn("await api(`/projects/${p.id}`)", fn)
        self.assertIn("loadProjects()", fn)

        approved = self._create_project(_approved_record(), "Gate13 Success UI")
        prior = copy.deepcopy(approved["data"])
        got = self.client.get(f"/projects/{approved['id']}")
        project = got.get_json()
        payload = _mirror_build_payload(project)

        hits, patches = self._forbid_generation_surface()
        with patches[0], patches[1], patches[2], patches[3]:
            resp = self.client.post(
                f"/projects/{approved['id']}/revisions", json=payload
            )
            self.assertEqual(resp.status_code, 201, resp.data)
            body = resp.get_json()
            self.assertEqual(body["artifact_state"], ArtifactState.DRAFT.value)
            self.assertEqual(body["artifact_revision"], current_revision(prior) + 1)

            # UI success path re-fetches project then openProject — same GET.
            reopened = self.client.get(f"/projects/{approved['id']}")
        self.assertEqual(reopened.status_code, 200, reopened.data)
        reopened_body = reopened.get_json()
        self.assertEqual(reopened_body["artifact_state"], "DRAFT")
        self.assertEqual(
            resolve_artifact_state(reopened_body["data"]), ArtifactState.DRAFT
        )
        self.assertEqual(hits, [])

    # --- 10: 409 conflict messaging ---

    def test_08_conflict_409_shows_reopen_guidance(self):
        src = self.app_js
        fn = src[src.find("async function createDraftRevision("):]
        fn = fn[: fn.find("\nfunction projectRow(")]
        self.assertIn("res.status === 409", fn)
        self.assertIn("Reopen it from Saved Projects", fn)
        self.assertIn('toast(', fn)

        approved = self._create_project(_approved_record(), "Gate13 Conflict UI")
        got = self.client.get(f"/projects/{approved['id']}")
        project = got.get_json()
        payload = _mirror_build_payload(project)
        stale = dict(payload)
        stale["expected_revision"] = int(payload["expected_revision"]) + 99

        hits, patches = self._forbid_generation_surface()
        with patches[0], patches[1], patches[2], patches[3]:
            resp = self.client.post(
                f"/projects/{approved['id']}/revisions", json=stale
            )
        self.assertEqual(resp.status_code, 409, resp.data)
        err = resp.get_json().get("error") or ""
        self.assertIn("conflict", err.lower())
        # Authoritative record unchanged (still APPROVED).
        after = self.client.get(f"/projects/{approved['id']}").get_json()
        self.assertEqual(after["artifact_state"], "APPROVED")
        self.assertEqual(hits, [])

    # --- Prior approved preserved + controlled errors show server message ---

    def test_09_prior_approved_preserved_and_errors_surface_server_message(self):
        src = self.app_js
        fn = src[src.find("async function createDraftRevision("):]
        fn = fn[: fn.find("\nfunction projectRow(")]
        # Non-409 errors toast server message; no fallback generation endpoints.
        self.assertIn("data.error || `Request failed (${res.status})`", fn)
        for endpoint in ("/generate-product", "/generate-ebook", "/export-product"):
            self.assertNotIn(endpoint, fn)

        approved = self._create_project(_approved_record(), "Gate13 Preserve UI")
        prior_data = copy.deepcopy(approved["data"])
        prior_rev = current_revision(prior_data)
        prior_id = str(
            prior_data.get("artifact_id") or prior_data.get("package_id") or ""
        )
        prior_digest = prior_data.get("content_digest")
        prior_problems = copy.deepcopy(prior_data.get("problems"))

        got = self.client.get(f"/projects/{approved['id']}")
        payload = _mirror_build_payload(got.get_json())

        hits, patches = self._forbid_generation_surface()
        with patches[0], patches[1], patches[2], patches[3]:
            resp = self.client.post(
                f"/projects/{approved['id']}/revisions", json=payload
            )
        self.assertEqual(resp.status_code, 201, resp.data)
        body = resp.get_json()
        self.assertIsNotNone(body.get("prior_approved_revision"))
        prior = body["prior_approved_revision"]
        self.assertEqual(prior.get("artifact_revision"), prior_rev)
        self.assertEqual(prior.get("artifact_state"), ArtifactState.APPROVED.value)
        self.assertEqual(
            str(prior.get("artifact_id") or prior.get("package_id") or ""),
            prior_id,
        )
        self.assertEqual(prior.get("content_digest"), prior_digest)

        stored = self.client.get(f"/projects/{approved['id']}").get_json()["data"]
        self.assertEqual(resolve_artifact_state(stored), ArtifactState.DRAFT)
        lineage = stored.get("prior_approved_revision") or {}
        self.assertEqual(lineage.get("artifact_revision"), prior_rev)
        self.assertEqual(lineage.get("content_digest"), prior_digest)
        # Working draft keeps product content (no regeneration).
        self.assertEqual(stored.get("problems"), prior_problems)
        self.assertEqual(hits, [])

        # Controlled non-transition error (missing reason) surfaces server text.
        draft = self._create_project(_draft_record(), "Gate13 Draft Reject UI")
        bad = {
            "create_draft_revision": True,
            "reason": "x",
            "expected_artifact_id": "gate13-draft-pkg-001",
            "expected_revision": 1,
        }
        with patches[0], patches[1], patches[2], patches[3]:
            reject = self.client.post(f"/projects/{draft['id']}/revisions", json=bad)
        self.assertEqual(reject.status_code, 409, reject.data)
        self.assertTrue(reject.get_json().get("error"))

    def test_10_js_wiring_near_saved_projects_actions(self):
        """Control lives in projectRow Saved Projects actions (no redesign)."""
        src = self.app_js
        self.assertIn("function projectRow(", src)
        self.assertIn('draftRevBtn.onclick = () => createDraftRevision(p, draftRevBtn)', src)
        self.assertTrue(INDEX_HTML.is_file())
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('id="savedList"', html)
        self.assertIn("js/app.js", html)


if __name__ == "__main__":
    unittest.main()
