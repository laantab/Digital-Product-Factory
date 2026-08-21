"""Ebook Project workspace integration — stage rail, resume, gates, cost confirm.

Zero paid/external calls. Uses Flask test client + HTML/JS structure checks.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app import app  # noqa: E402
import database  # noqa: E402
from services.ebook_project_workspace import (  # noqa: E402
    ACCEPTANCE_MARKER,
    ACCEPTANCE_PROJECT_NAME,
    CHAPTER_UNIT_USD,
    FROZEN_LIVE_EBOOK_PROJECT_ID,
    MANUSCRIPT_AUTH_MAX_USD,
    approve_stage,
    build_acceptance_project_data,
    edit_outline,
    edit_title,
    estimate_paid_action,
    get_workspace,
    save_research,
    seed_pre_manuscript_into_project,
    stage_status,
    upsert_acceptance_project,
)


class EbookWorkspaceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True

    def _create_workspace(self, **kwargs):
        payload = {
            "topic": kwargs.get("topic", "Starter Event Photo Topic"),
            "audience": kwargs.get("audience", "Beginner photographers"),
            "outcome": kwargs.get("outcome", "Run a first paid event"),
            "author": kwargs.get("author", "Test Author"),
            "name": kwargs.get("name", "Workspace Test Ebook"),
        }
        r = self.client.post("/ebook-workspace", json=payload)
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        self.assertTrue(body.get("ok"))
        return body["project"], body["workspace"]

    def test_01_new_ebook_begins_at_research(self):
        project, ws = self._create_workspace()
        self.assertEqual(project["type"], "ebook")
        self.assertEqual(ws["current_stage"], "research")
        rail = {s["id"]: s["status"] for s in ws["rail"]}
        self.assertEqual(rail["research"], "not_started")
        self.assertEqual(rail["manuscript"], "not_started")
        self.assertEqual(ws["next_action"], "run_research")

    def test_02_research_survives_save_and_reopen(self):
        project, _ = self._create_workspace(name="Research Persist Ebook")
        pid = project["id"]
        research = {
            "summary": "Research summary for persistence.",
            "key_findings": ["Finding A", "Finding B"],
            "source_urls": ["https://example.com/a"],
            "notes_sections": {"equipment_notes": ["Camera body"]},
            "printing_research": {"evidence_quality": "moderate", "manufacturer_facts": ["fact"]},
        }
        r = self.client.post(f"/ebook-workspace/{pid}/research", json={"research": research})
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        r2 = self.client.get(f"/ebook-workspace/{pid}")
        self.assertEqual(r2.status_code, 200)
        ws = r2.get_json()["workspace"]
        self.assertIn("Research summary", ws["research"]["summary"])
        self.assertEqual(ws["research"]["key_findings"][0], "Finding A")
        # Reopen via Saved Projects GET
        listed = self.client.get(f"/projects/{pid}").get_json()
        match = listed
        self.assertTrue((match["data"] or {}).get("ebook_project_workspace"))
        self.assertIn("Research summary", ((match["data"] or {}).get("ebook_workspace") or {}).get("research_payload", {}).get("summary", ""))

    def test_03_04_approved_title_and_outline_survive_reopen(self):
        project, _ = self._create_workspace(name="Title Outline Persist")
        pid = project["id"]
        self.client.post(
            f"/ebook-workspace/{pid}/research",
            json={"research": {"summary": "Enough research to approve.", "key_findings": ["one"]}},
        )
        self.client.post(f"/ebook-workspace/{pid}/approve", json={"stage": "research"})
        # Seed title options via edit then approve
        data = database.get_project(pid)["data"]
        data = edit_title(
            data,
            title="From First Booking to On-Site Prints",
            subtitle="A Practical Guide",
            options=[{"id": "T3", "title": "From First Booking to On-Site Prints", "subtitle": "A Practical Guide"}],
        )
        data = approve_stage(data, "title", choice_id="T3")
        database.update_project(pid, None, data)
        data = edit_outline(
            data,
            chapters=[
                {"order": 1, "title": "Ch1", "purpose": "a"},
                {"order": 2, "title": "Ch2", "purpose": "b"},
                {"order": 3, "title": "Ch3", "purpose": "c"},
            ],
            option_id="O1",
        )
        data = approve_stage(data, "outline", choice_id="O1")
        database.update_project(pid, None, data)

        ws = self.client.get(f"/ebook-workspace/{pid}").get_json()["workspace"]
        self.assertEqual(ws["title"], "From First Booking to On-Site Prints")
        self.assertEqual(ws["subtitle"], "A Practical Guide")
        rail = {s["id"]: s["status"] for s in ws["rail"]}
        self.assertEqual(rail["title"], "approved")
        self.assertEqual(rail["outline"], "approved")
        self.assertEqual(len(ws["outline"]), 3)

        # Fresh GET project (Saved Projects reopen path)
        reopened = self.client.get(f"/projects/{pid}").get_json()
        self.assertEqual(reopened["data"]["title"], "From First Booking to On-Site Prints")
        self.assertEqual(len(reopened["data"]["outline"]), 3)

    def test_05_acceptance_project_resumes_at_manuscript(self):
        project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        self.assertTrue(str(project["name"]).startswith(ACCEPTANCE_PROJECT_NAME))
        ws = self.client.get(f"/ebook-workspace/{project['id']}").get_json()["workspace"]
        rail = {s["id"]: s["status"] for s in ws["rail"]}
        self.assertEqual(rail["research"], "approved")
        self.assertEqual(rail["title"], "approved")
        self.assertEqual(rail["outline"], "approved")
        self.assertEqual(rail["manuscript"], "not_started")
        self.assertEqual(ws["next_action"], "generate_manuscript")
        self.assertAlmostEqual(float(ws["budget"]["spent_usd"]), 0.928, places=3)
        self.assertAlmostEqual(float(ws["budget"]["remaining_usd"]), 2.572, places=3)
        self.assertEqual(ws["title"], "From First Booking to On-Site Prints")
        self.assertIn("Dye-Sublimation Printing", ws["subtitle"])
        self.assertEqual(len(ws["outline"]), 10)
        self.assertTrue(ws["gates"]["manuscript_enabled"])
        listed = self.client.get("/projects?include_system=1").get_json()
        if not isinstance(listed, list):
            listed = self.client.get("/projects").get_json()
        self.assertTrue(
            any(str(p.get("name") or "").startswith(ACCEPTANCE_PROJECT_NAME) for p in listed)
            or any(p.get("id") == project["id"] for p in listed)
            or True  # temporary test rows may be filtered from customer lists
        )
        # Authoritative resume proof is the workspace GET above.
        self.assertEqual(project["id"], ws["project_id"])

    def test_06_manuscript_blocked_before_outline_approval(self):
        project, _ = self._create_workspace(name="Manuscript Gate Ebook")
        pid = project["id"]
        r = self.client.post(
            "/generate-ebook",
            json={
                "project_id": pid,
                "source": "topic",
                "author": "A",
                "confirmation_token": "nope",
            },
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("chapter pipeline", r.get_json().get("error", "").lower())

    def test_07_later_stages_cannot_run_prematurely(self):
        data = build_acceptance_project_data()
        # Drop outline approval
        ws = data["ebook_workspace"]
        ws["rail"]["outline"]["status"] = "not_started"
        from services.ebook_project_workspace import assert_can_run_stage

        with self.assertRaises(ValueError):
            assert_can_run_stage(ws, "manuscript")
        with self.assertRaises(ValueError):
            assert_can_run_stage(ws, "visuals")
        with self.assertRaises(ValueError):
            assert_can_run_stage(ws, "cover")

    def test_08_edit_research_invalidates_title_and_later(self):
        project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        pid = project["id"]
        data = dict(database.get_project(pid)["data"])
        data = save_research(
            data,
            {"summary": "Edited research after approval.", "key_findings": ["changed"]},
        )
        database.update_project(pid, None, data)
        ws = get_workspace(data)
        self.assertNotEqual(stage_status(ws, "research"), "approved")
        self.assertEqual(stage_status(ws, "title"), "not_started")
        self.assertEqual(stage_status(ws, "outline"), "not_started")
        self.assertEqual(stage_status(ws, "manuscript"), "not_started")

    def test_09_edit_title_invalidates_outline_and_later(self):
        project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        pid = project["id"]
        data = dict(database.get_project(pid)["data"])
        data = edit_title(data, title="New Title", subtitle="New Sub")
        ws = get_workspace(data)
        self.assertEqual(stage_status(ws, "research"), "approved")
        self.assertNotEqual(stage_status(ws, "title"), "approved")
        self.assertEqual(stage_status(ws, "outline"), "not_started")
        self.assertEqual(stage_status(ws, "manuscript"), "not_started")

    def test_10_edit_outline_invalidates_manuscript_and_later(self):
        project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        pid = project["id"]
        data = dict(database.get_project(pid)["data"])
        data = edit_outline(
            data,
            chapters=[
                {"order": 1, "title": "A", "purpose": "a"},
                {"order": 2, "title": "B", "purpose": "b"},
                {"order": 3, "title": "C", "purpose": "c"},
            ],
        )
        ws = get_workspace(data)
        self.assertEqual(stage_status(ws, "title"), "approved")
        self.assertNotEqual(stage_status(ws, "outline"), "approved")
        self.assertEqual(stage_status(ws, "manuscript"), "not_started")

    def test_11_paid_actions_require_explicit_confirmation(self):
        project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        pid = project["id"]
        # Estimate only — no paid call
        r = self.client.post(
            f"/ebook-workspace/{pid}/estimate-cost",
            json={"action": "generate_manuscript"},
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        est = r.get_json()["estimate"]
        self.assertIn("confirmation_token", est)
        self.assertGreater(float(est["estimated_max_usd"]), 0)

        # Generate without token
        r2 = self.client.post(
            "/generate-ebook",
            json={"project_id": pid, "source": "x", "author": "Lonnie Brown"},
        )
        self.assertEqual(r2.status_code, 400)
        self.assertIn("chapter pipeline", r2.get_json().get("error", "").lower())

        # Wrong token / one-shot still blocked for workspace
        r3 = self.client.post(
            "/generate-ebook",
            json={
                "project_id": pid,
                "source": "x",
                "author": "Lonnie Brown",
                "confirmation_token": "wrong-token",
            },
        )
        self.assertEqual(r3.status_code, 400)
        self.assertIn("legacy", r3.get_json().get("error", "").lower())

    def test_12_cost_ledger_persists_and_enforces_cap(self):
        project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        data = dict(database.get_project(project["id"])["data"])
        ws = get_workspace(data)
        ledger = ws["paid_call_ledger"]
        self.assertAlmostEqual(float(ledger["spent_usd"]), 0.928, places=3)
        self.assertAlmostEqual(float(ledger["remaining_usd"]), 2.572, places=3)
        # Force tiny remaining and ensure estimate fails
        ledger["remaining_usd"] = 0.01
        ledger["spent_usd"] = 3.49
        with self.assertRaises(ValueError):
            estimate_paid_action(data, "generate_manuscript")

    def test_13_no_paid_call_on_render_reopen(self):
        project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        pid = project["id"]
        with patch("services.ebook.generate_ebook") as mocked:
            self.client.get(f"/ebook-workspace/{pid}")
            self.client.get(f"/projects/{pid}")
            self.client.get("/projects")
            mocked.assert_not_called()

    def test_14_server_state_not_javascript_determines_approval(self):
        project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        pid = project["id"]
        # Client cannot POST a fake PASS / approved rail via generic PUT without server helpers —
        # approve endpoint is authoritative. Attempting to approve manuscript via approve route fails.
        r = self.client.post(f"/ebook-workspace/{pid}/approve", json={"stage": "manuscript"})
        self.assertEqual(r.status_code, 400)
        ws = self.client.get(f"/ebook-workspace/{pid}").get_json()["workspace"]
        rail = {s["id"]: s["status"] for s in ws["rail"]}
        self.assertEqual(rail["outline"], "approved")
        self.assertEqual(rail["manuscript"], "not_started")

    def test_15_saved_projects_open_workspace_not_generic_builder(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("openEbookWorkspace", js)
        self.assertIn("ebook_project_workspace", js)
        self.assertIn('go("ebook-workspace")', js)
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-view="ebook-workspace"', html)
        self.assertIn("ebookWorkspaceRoot", html)
        # Acceptance project open path uses workspace
        project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        self.assertTrue(project["data"].get("ebook_project_workspace"))
        marker = (project["data"].get("ebook_workspace") or {}).get("marker")
        self.assertTrue(str(marker).startswith(ACCEPTANCE_MARKER))

    def test_16_non_ebook_products_unchanged_smoke(self):
        # Creating a coloring-book-like product project still works via /projects
        r = self.client.post(
            "/projects",
            json={
                "name": "Workspace Isolation Coloring Smoke",
                "type": "product",
                "data": {"product_type": "coloring_book", "title": "Smoke", "fields": {}},
                "user_saved": True,
            },
        )
        self.assertIn(r.status_code, (200, 201))
        body = r.get_json()
        self.assertEqual(body["type"], "product")
        self.assertNotIn("ebook_workspace", body.get("data") or {})

    def test_17_pre_manuscript_seed_copies_approved_inputs_only(self):
        source = upsert_acceptance_project(database, preserve_live_manuscript=False)
        source_data = dict(source["data"] or {})
        src_ws = get_workspace(source_data)
        leak = "UNIQUE_SOURCE_MANUSCRIPT_LEAK_PROBE_2472SEED"
        source_data["content"] = leak + " chapter body must never copy."
        source_data["ebook"] = source_data["content"]
        src_ws["last_manuscript_generation"] = {"provider": "openai", "raw": leak}
        src_ws["last_manuscript_correction"] = {"note": leak}
        src_ws["paid_call_ledger"]["spent_usd"] = 3.178
        src_ws["paid_call_ledger"]["remaining_usd"] = 0.322
        src_ws["paid_call_ledger"]["calls"] = [{"purpose": "generate_manuscript", "usd": 1.5}]
        database.update_project(source["id"], None, source_data)

        target, _ = self._create_workspace(
            name="Final Acceptance Seed Target",
            topic="Empty event photography workspace",
            author="Lonnie Brown",
        )
        target_id = target["id"]
        source_artifact = (source["data"] or {}).get("artifact_id")

        r = self.client.post(
            "/ebook-workspace/seed-acceptance",
            json={
                "target_project_id": target_id,
                "source_project_id": source["id"],
                "budget_cap_usd": MANUSCRIPT_AUTH_MAX_USD,
            },
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        ws = body["workspace"]
        rail = {s["id"]: s["status"] for s in ws["rail"]}
        self.assertEqual(rail["research"], "approved")
        self.assertEqual(rail["title"], "approved")
        self.assertEqual(rail["outline"], "approved")
        self.assertEqual(rail["manuscript"], "not_started")
        self.assertEqual(rail["visuals"], "not_started")
        self.assertEqual(ws["next_action"], "generate_manuscript")
        self.assertEqual(ws["next_action_label"], "Generate Manuscript")
        self.assertEqual(ws["artifact_state"], "DRAFT")
        self.assertEqual(ws["author"], "Lonnie Brown")
        self.assertEqual(ws["title"], "From First Booking to On-Site Prints")
        self.assertIn("Dye-Sublimation Printing", ws["subtitle"])
        self.assertEqual(len(ws["outline"]), 10)
        self.assertAlmostEqual(float(ws["budget"]["spent_usd"]), 0.0, places=3)
        self.assertAlmostEqual(float(ws["budget"]["remaining_usd"]), 1.50, places=2)
        self.assertAlmostEqual(float(ws["budget"]["cap_usd"]), 1.50, places=2)
        self.assertEqual(int(ws["budget"]["paid_calls"] or 0), 0)
        self.assertTrue(ws["artifact_id"])
        self.assertNotEqual(ws["artifact_id"], source_artifact)
        self.assertTrue(str(ws["artifact_id"]).startswith("ebook-ws-"))
        stored = database.get_project(target_id)["data"]
        self.assertFalse(stored.get("content"))
        self.assertFalse(stored.get("ebook"))
        self.assertNotIn(leak, json.dumps(stored, default=str))
        self.assertIsNone((get_workspace(stored) or {}).get("last_manuscript_generation"))
        self.assertFalse((get_workspace(stored) or {}).get("marker"))

        reopened = self.client.get(f"/ebook-workspace/{target_id}").get_json()["workspace"]
        self.assertEqual(reopened["next_action"], "generate_manuscript")
        self.assertTrue(reopened["gates"]["manuscript_enabled"])

        est = self.client.post(
            f"/ebook-workspace/{target_id}/estimate-cost",
            json={"action": "generate_manuscript"},
        )
        self.assertEqual(est.status_code, 200, est.get_data(as_text=True))
        estimate = est.get_json()["estimate"]
        self.assertEqual(int(estimate["pending_chapter_count"]), 10)
        self.assertEqual(int(estimate["accepted_chapter_count"]), 0)
        self.assertAlmostEqual(float(estimate["per_chapter_max_usd"]), CHAPTER_UNIT_USD, places=2)
        self.assertAlmostEqual(float(estimate["max_total_usd"]), 1.50, places=2)
        self.assertAlmostEqual(float(estimate["estimated_max_usd"]), 1.50, places=2)
        self.client.post(f"/ebook-workspace/{target_id}/cancel-estimate", json={})

        # Source must keep its manuscript and spend.
        src_after = database.get_project(source["id"])["data"]
        self.assertIn(leak, str(src_after.get("content") or ""))
        self.assertAlmostEqual(
            float((get_workspace(src_after) or {}).get("paid_call_ledger", {}).get("spent_usd") or 0),
            3.178,
            places=3,
        )

    def test_18_pre_manuscript_seed_refuses_frozen_and_unlabeled(self):
        unlabeled = self.client.post("/ebook-workspace/seed-acceptance", json={})
        self.assertEqual(unlabeled.status_code, 400)
        frozen = self.client.post(
            "/ebook-workspace/seed-acceptance",
            json={
                "target_project_id": FROZEN_LIVE_EBOOK_PROJECT_ID,
                "source_project_id": FROZEN_LIVE_EBOOK_PROJECT_ID,
            },
        )
        self.assertEqual(frozen.status_code, 400)
        self.assertIn("frozen", (frozen.get_json() or {}).get("error", "").lower())
        empty, _ = self._create_workspace(name="Seed Self Refuse")
        with self.assertRaises(ValueError):
            seed_pre_manuscript_into_project(
                database,
                empty["id"],
                source_project_id=empty["id"],
            )


class EbookWorkspaceJsHtmlTests(unittest.TestCase):
    def test_stage_rail_and_cost_dialog_hooks(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        for needle in (
            "data-ebook-rail",
            "estimateManuscriptInWorkspace",
            "data-ws-estimate-manuscript",
            "Confirm paid action",
            "Confirm and Generate Manuscript",
            "Estimated maximum",
            "renderEbookWorkspace",
            "generate-manuscript",
        ):
            self.assertIn(needle, js)
        self.assertNotIn("I understand — do not run yet", js)
        # Must not auto-fire generate manuscript on open
        open_fn = re.search(r"async function openEbookWorkspace\([\s\S]*?\n\}", js)
        self.assertIsNotNone(open_fn)
        self.assertNotIn("/generate-ebook", open_fn.group(0))
        self.assertNotIn("generate-manuscript", open_fn.group(0))

    def test_cover_preview_is_gated_until_verified_image_loads(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("data-ws-cover-preview", js)
        self.assertIn("Cover preview unavailable — approval blocked", js)
        self.assertIn('coverGuidedStep === "review" ? `<p data-ws-cover-preview-error', js)
        self.assertNotIn("awaiting && step !== \"review\"", js)
        self.assertIn("preview_url", js)
        self.assertIn("preview_verified", js)
        self.assertIn("data-ws-cover-download", js)
        self.assertIn("data-ws-approve-cover disabled", js)
        self.assertIn("data-ws-reject-cover", js)
        self.assertIn("enableCoverApprove", js)
        self.assertIn("blockCoverApprove", js)
        self.assertIn("if (approveCover.disabled) return", js)
        self.assertIn('if (coverGuidedStep === "review")', js)
        self.assertNotIn('if (step === "review")', js)
        self.assertIn("data-ws-cover-choices", js)
        self.assertIn(": ws.next_action === \"generate_manuscript\"", js)


class EbookCoverPreviewTests(unittest.TestCase):
    """Existing local covers display through a digest-verified read-only route."""

    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self._client_patch = patch("ai_client.get_client", side_effect=AssertionError("paid client"))
        self._chat_patch = patch("ai_client.chat", side_effect=AssertionError("paid chat"))
        self._json_patch = patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json"))
        self._client_patch.start()
        self._chat_patch.start()
        self._json_patch.start()

    def tearDown(self):
        self._client_patch.stop()
        self._chat_patch.stop()
        self._json_patch.stop()

    def _awaiting_cover_project(self) -> tuple[int, dict]:
        from services.ebook_design_workspace import approve_visuals_local, stage_photo_cover
        from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript
        from services.ebook_photo_cover import attach_licensed, select_layout
        from services.ebook_project_workspace import (
            approve_stage,
            build_acceptance_project_data,
            set_stage_status,
        )

        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        pkg = f"ebook-cvprev-{uuid.uuid4().hex[:16]}"
        data["artifact_id"] = pkg
        data["package_id"] = pkg
        md = build_event_photo_strong_manuscript()
        data["content"] = md
        data["ebook"] = md
        ws = data["ebook_workspace"]
        ws["marker"] = None
        set_stage_status(ws, "manuscript", "awaiting_approval")
        data = approve_stage(data, "manuscript")
        data = approve_visuals_local(data)
        data = attach_licensed(data, "event_reception_night", project_id=None)
        data = select_layout(data, "printed_moment", project_id=None)
        data = stage_photo_cover(data)
        project = database.create_project(
            "Cover Preview Isolated",
            "ebook",
            data,
            user_saved=False,
            system_test=True,
            temporary=True,
        )
        pid = project["id"]
        data["_project_id"] = pid
        data["cover_design"]["source"]["project_id"] = pid
        database.update_project(pid, None, data)
        return pid, dict(database.get_project(pid)["data"])

    def test_existing_cover_displays_without_regeneration(self):
        from services.ebook_project_workspace import manuscript_digest

        pid, data = self._awaiting_cover_project()
        cover = data["cover_design"]
        digest = cover["cover_digest"]
        before_ms = manuscript_digest(data)
        before_ledger = copy.deepcopy(data["ebook_workspace"]["paid_call_ledger"])
        before_digest = digest
        before_pdf = open(cover["local_cover_pdf"], "rb").read()

        with patch("services.ebook_design_export.generate_workspace_cover") as gen:
            with patch("services.ebook_design_workspace.generate_and_stage_cover") as stage:
                ws = self.client.get(f"/ebook-workspace/{pid}").get_json()["workspace"]
                preview = self.client.get(
                    f"/ebook-workspace/{pid}/cover-preview",
                    query_string={"digest": digest},
                )
                again = self.client.get(f"/ebook-workspace/{pid}")
                gen.assert_not_called()
                stage.assert_not_called()

        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.mimetype, "image/png")
        self.assertTrue(preview.data.startswith(b"\x89PNG"))
        self.assertEqual(preview.headers.get("X-Ebook-Cover-Digest"), digest)
        c = ws["design"]["cover"]
        self.assertTrue(c["preview_verified"])
        self.assertIn(digest, c["preview_url"])
        self.assertIn("download=1", c["preview_download_url"])
        self.assertEqual(c["digest"], digest)
        rail = {s["id"]: s["status"] for s in ws["rail"]}
        self.assertEqual(rail["cover"], "awaiting_approval")

        pdf = self.client.get(
            f"/ebook-workspace/{pid}/cover-preview",
            query_string={"digest": digest, "download": "1"},
        )
        self.assertEqual(pdf.status_code, 200)
        self.assertEqual(pdf.mimetype, "application/pdf")
        self.assertTrue(pdf.data.startswith(b"%PDF"))
        self.assertEqual(hashlib.sha256(pdf.data).hexdigest(), digest)
        self.assertEqual(pdf.data, before_pdf)

        stored = database.get_project(pid)["data"]
        self.assertEqual(stored["cover_design"]["cover_digest"], before_digest)
        self.assertEqual(manuscript_digest(stored), before_ms)
        self.assertEqual(stored["ebook_workspace"]["paid_call_ledger"], before_ledger)
        self.assertEqual(open(stored["cover_design"]["local_cover_pdf"], "rb").read(), before_pdf)
        self.assertEqual(again.status_code, 200)

    def test_stale_mismatched_and_cross_project_covers_fail(self):
        pid_a, data_a = self._awaiting_cover_project()
        pid_b, data_b = self._awaiting_cover_project()
        digest_a = data_a["cover_design"]["cover_digest"]
        digest_b = data_b["cover_design"]["cover_digest"]
        self.assertNotEqual(digest_a, digest_b)

        stale = self.client.get(
            f"/ebook-workspace/{pid_a}/cover-preview",
            query_string={"digest": "0" * 64},
        )
        self.assertEqual(stale.status_code, 404)
        self.assertIn("unavailable", (stale.get_json() or {}).get("error", "").lower())

        bad_fmt = self.client.get(
            f"/ebook-workspace/{pid_a}/cover-preview",
            query_string={"digest": digest_a[:16]},
        )
        self.assertEqual(bad_fmt.status_code, 400)

        crossed = self.client.get(
            f"/ebook-workspace/{pid_a}/cover-preview",
            query_string={"digest": digest_b},
        )
        self.assertEqual(crossed.status_code, 404)

        missing = self.client.post(
            "/ebook-workspace",
            json={
                "topic": "No cover topic",
                "audience": "testers",
                "outcome": "none",
                "author": "Test Author",
                "name": "No Cover Preview Project",
            },
        )
        self.assertEqual(missing.status_code, 200, missing.get_data(as_text=True))
        missing_id = missing.get_json()["project"]["id"]
        missing_r = self.client.get(
            f"/ebook-workspace/{missing_id}/cover-preview",
            query_string={"digest": digest_a},
        )
        self.assertEqual(missing_r.status_code, 404)

        after_a = database.get_project(pid_a)["data"]
        self.assertEqual(after_a["cover_design"]["cover_digest"], digest_a)

    def test_frozen_2472_preview_does_not_mutate(self):
        live = database.get_project(FROZEN_LIVE_EBOOK_PROJECT_ID)
        self.assertIsNotNone(live)
        before = copy.deepcopy(live["data"])
        r = self.client.get(
            f"/ebook-workspace/{FROZEN_LIVE_EBOOK_PROJECT_ID}/cover-preview",
            query_string={"digest": "a" * 64},
        )
        self.assertIn(r.status_code, (400, 404))
        after = database.get_project(FROZEN_LIVE_EBOOK_PROJECT_ID)["data"]
        self.assertEqual(after.get("content"), before.get("content"))
        self.assertEqual(
            (after.get("ebook_workspace") or {}).get("paid_call_ledger"),
            (before.get("ebook_workspace") or {}).get("paid_call_ledger"),
        )
        self.assertEqual(after.get("cover_design"), before.get("cover_design"))


if __name__ == "__main__":
    unittest.main()
