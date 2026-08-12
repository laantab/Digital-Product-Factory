"""Ebook Project workspace integration — stage rail, resume, gates, cost confirm.

Zero paid/external calls. Uses Flask test client + HTML/JS structure checks.
"""
from __future__ import annotations

import json
import os
import re
import sys
import unittest
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
    approve_stage,
    build_acceptance_project_data,
    edit_outline,
    edit_title,
    estimate_paid_action,
    get_workspace,
    save_research,
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
        listed = self.client.get("/projects").get_json()
        match = next(p for p in listed if p["id"] == pid)
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
        self.assertEqual(project["name"], ACCEPTANCE_PROJECT_NAME)
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
        listed = self.client.get("/projects").get_json()
        self.assertTrue(any(p["name"] == ACCEPTANCE_PROJECT_NAME for p in listed))

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
        # project has no workspace until flagged — create workspace project already has it
        self.assertEqual(r.status_code, 400)
        self.assertIn("outline", r.get_json().get("error", "").lower())

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
        self.assertIn("confirmation", r2.get_json().get("error", "").lower())

        # Wrong token
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
        self.assertEqual((project["data"].get("ebook_workspace") or {}).get("marker"), ACCEPTANCE_MARKER)

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


if __name__ == "__main__":
    unittest.main()
