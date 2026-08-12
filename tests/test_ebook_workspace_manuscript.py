"""Confirmed manuscript generation for Ebook Project workspace.

All generation is mocked — zero paid/external calls.
"""
from __future__ import annotations

import os
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
    ACCEPTANCE_PROJECT_NAME,
    cancel_paid_estimate,
    estimate_paid_action,
    execute_generate_manuscript,
    get_workspace,
    outline_digest,
    stage_status,
    upsert_acceptance_project,
)


GOOD_MS = """# From First Booking to On-Site Prints

## What This Business Actually Looks Like

Event photography with on-site dye-sub prints is a practical service model for weddings, parties, schools, churches, reunions, and community events. Guests leave with a finished print the same day.

Keep pricing and printer claims as planning scenarios. Equipment and media prices vary and must be verified with current suppliers.

## Startup Reality Check: Budget, Legal Basics, and Insurance

Plan a lean or event-focused kit budget as a planning range, not a guarantee. Register the business and arrange liability and equipment insurance before the first paid event.

## Core Camera Kit, Printing Equipment, and Backup Gear

Carry a body, lenses for wide/medium/telephoto roles, flash, computer, editing software, backup batteries and cards, and the dye-sub printer plan. Add a second body as soon as practical.

## Finding Clients and Turning Inquiries into Signed Bookings

Collect venue constraints, shot lists, deposits, and print expectations before event day. Turn inquiries into signed bookings with clear contracts.

## Packages and Pricing Scenarios That Protect Your Margin

Define hours, deliverables, planning meetings, and turnaround. Hypothetical planning scenario only: cover shooting, planning, editing, travel, taxes, gear recovery, and profit.

## Planning the Event: Contracts, Timelines, Space, Power, and Staffing

Lock contracts, timelines, booth space, power, and staffing before the event so print and coverage plans hold under pressure.

## Event-Day Operations: From Photograph to Guest Delivery

Use a before/during/after workflow from capture to guest delivery. Coordinate guest flow to the print station without inventing unverified POS procedures.

## Dye-Sublimation Printing: Setup, Queue, Ordering, Payment, and Pickup

Use DS-RX1HS, DS620A, and QW410 specifications only where manufacturer sources support them. Plan setup, queue, ordering, payment, and pickup. Media prices vary — verify with current suppliers.

## Keepsakes Beyond Photo Prints: Separate Equipment and Workflow

Mugs, buttons, shirts, and plates require separate equipment, materials, production time, staffing, and safety planning. They were not verified by the printer-manufacturer sources used for dye-sub photo printers here. Do not invent production specs.

## Common Mistakes and Your 30-Day First Paid Event Plan

Avoid underpricing, missing backup gear, vague packages, and weak print planning. Use a 30-day first-paid-event plan spanning kit, insurance, packages, booking, and print readiness.
"""

BAD_MS = GOOD_MS + "\n\n## Chapter Extra\n\nsub-goal #1 invent a Lonnie story here\n"


def _mock_generate_ok(source, contract=None, author="", research_notes=""):
    assert "Lonnie Brown" in (author or research_notes)
    assert "APPROVED OUTLINE" in research_notes or "What This Business" in research_notes
    assert "LOCKED EDITORIAL" in research_notes or "DS-RX1HS" in research_notes
    assert "sub-goal" not in research_notes.lower() or "FORBIDDEN" in research_notes
    return {"ebook": GOOD_MS, "source": source, "source_type": "topic"}


def _mock_generate_bad(source, contract=None, author="", research_notes=""):
    return {"ebook": BAD_MS, "source": source, "source_type": "topic"}


class ManuscriptExecutionTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self.project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        self.pid = self.project["id"]

    def _fresh(self):
        self.project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        self.pid = self.project["id"]
        # Reset manuscript state if prior test left content
        data = dict(database.get_project(self.pid)["data"])
        ws = get_workspace(data)
        for stage in ("manuscript", "visuals", "cover", "design", "preview", "preflight", "export"):
            ws["rail"][stage]["status"] = "not_started"
            ws["rail"][stage]["approved_at"] = None
        ws["manuscript_qa"] = []
        ws["last_manuscript_generation"] = None
        ledger = ws["paid_call_ledger"]
        ledger["pending_estimate"] = None
        ledger["idempotency_keys"] = {}
        # Keep original spend
        data["content"] = ""
        data["ebook"] = ""
        if isinstance(data.get("ebook_document"), dict):
            data["ebook_document"]["manuscript_md"] = ""
            data["ebook_document"]["chapters"] = []
        database.update_project(self.pid, None, data)
        return database.get_project(self.pid)

    def _estimate(self):
        r = self.client.post(
            f"/ebook-workspace/{self.pid}/estimate-cost",
            json={"action": "generate_manuscript"},
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        return r.get_json()

    def test_01_open_workspace_spends_nothing(self):
        self._fresh()
        before = database.get_project(self.pid)["data"]["ebook_workspace"]["paid_call_ledger"]["spent_usd"]
        r = self.client.get(f"/ebook-workspace/{self.pid}")
        self.assertEqual(r.status_code, 200)
        after = database.get_project(self.pid)["data"]["ebook_workspace"]["paid_call_ledger"]["spent_usd"]
        self.assertAlmostEqual(float(before), float(after), places=4)

    def test_02_opening_confirmation_spends_nothing(self):
        self._fresh()
        before = float(
            database.get_project(self.pid)["data"]["ebook_workspace"]["paid_call_ledger"]["spent_usd"]
        )
        est = self._estimate()
        after = float(
            database.get_project(self.pid)["data"]["ebook_workspace"]["paid_call_ledger"]["spent_usd"]
        )
        self.assertAlmostEqual(before, after, places=4)
        self.assertIn("confirmation_token", est["estimate"])
        self.assertAlmostEqual(float(est["estimate"]["estimated_max_usd"]), 1.5, places=3)

    def test_03_cancel_spends_nothing(self):
        self._fresh()
        before = float(
            database.get_project(self.pid)["data"]["ebook_workspace"]["paid_call_ledger"]["spent_usd"]
        )
        self._estimate()
        r = self.client.post(f"/ebook-workspace/{self.pid}/cancel-estimate", json={})
        self.assertEqual(r.status_code, 200)
        after = float(
            database.get_project(self.pid)["data"]["ebook_workspace"]["paid_call_ledger"]["spent_usd"]
        )
        self.assertAlmostEqual(before, after, places=4)
        self.assertIsNone(
            database.get_project(self.pid)["data"]["ebook_workspace"]["paid_call_ledger"]["pending_estimate"]
        )

    def test_04_confirm_button_targets_server_endpoint_only(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Confirm and Generate Manuscript", js)
        self.assertIn("/ebook-workspace/${projectId}/generate-manuscript", js)
        self.assertNotIn("I understand — do not run yet", js)
        self.assertNotIn("intentionally not started from this integration step", js)
        # UI must not call providers directly
        self.assertNotIn("api.openai.com", js)
        open_fn = js[js.find("async function estimateManuscriptInWorkspace") : js.find("async function runEbook")]
        self.assertIn("generate-manuscript", open_fn)
        self.assertNotIn("generate-ebook", open_fn)

    def test_05_missing_stale_reused_token_rejected(self):
        self._fresh()
        data = dict(database.get_project(self.pid)["data"])
        est = estimate_paid_action(data, "generate_manuscript")
        database.update_project(self.pid, None, data)
        token = est["estimate"]["confirmation_token"]
        od = est["estimate"]["outline_digest"]
        art = est["estimate"]["artifact_id"]
        rev = est["estimate"]["artifact_revision"]

        # Missing token
        r = self.client.post(
            f"/ebook-workspace/{self.pid}/generate-manuscript",
            json={
                "confirmation_token": "",
                "expected_artifact_id": art,
                "expected_revision": rev,
                "outline_digest": od,
                "max_authorized_usd": 1.5,
                "idempotency_key": "k-missing",
            },
        )
        self.assertEqual(r.status_code, 400)

        # Wrong token
        r2 = self.client.post(
            f"/ebook-workspace/{self.pid}/generate-manuscript",
            json={
                "confirmation_token": "wrong",
                "expected_artifact_id": art,
                "expected_revision": rev,
                "outline_digest": od,
                "max_authorized_usd": 1.5,
                "idempotency_key": "k-wrong",
            },
        )
        self.assertEqual(r2.status_code, 400)

        with patch(
            "services.ebook_project_workspace.generate_fn", create=True
        ):
            with patch("services.ebook.generate_ebook", side_effect=_mock_generate_ok) as mocked:
                r3 = self.client.post(
                    f"/ebook-workspace/{self.pid}/generate-manuscript",
                    json={
                        "confirmation_token": token,
                        "expected_artifact_id": art,
                        "expected_revision": rev,
                        "outline_digest": od,
                        "max_authorized_usd": 1.5,
                        "idempotency_key": "k-ok-once",
                    },
                )
                self.assertEqual(r3.status_code, 200, r3.get_data(as_text=True))
                mocked.assert_called_once()

        # Reused token (need new estimate first would be required; token marked used)
        r4 = self.client.post(
            f"/ebook-workspace/{self.pid}/generate-manuscript",
            json={
                "confirmation_token": token,
                "expected_artifact_id": art,
                "expected_revision": rev,
                "outline_digest": od,
                "max_authorized_usd": 1.5,
                "idempotency_key": "k-reuse",
            },
        )
        self.assertEqual(r4.status_code, 400)

    def test_06_changed_outline_or_revision_rejected(self):
        self._fresh()
        data = dict(database.get_project(self.pid)["data"])
        est = estimate_paid_action(data, "generate_manuscript")
        database.update_project(self.pid, None, data)
        token = est["estimate"]["confirmation_token"]
        with patch("services.ebook.generate_ebook", side_effect=_mock_generate_ok):
            r = self.client.post(
                f"/ebook-workspace/{self.pid}/generate-manuscript",
                json={
                    "confirmation_token": token,
                    "expected_artifact_id": est["estimate"]["artifact_id"],
                    "expected_revision": 999,
                    "outline_digest": est["estimate"]["outline_digest"],
                    "max_authorized_usd": 1.5,
                    "idempotency_key": "k-stale-rev",
                },
            )
            self.assertEqual(r.status_code, 400)
            self.assertIn("revision", r.get_json().get("error", "").lower())

        data = dict(database.get_project(self.pid)["data"])
        est2 = estimate_paid_action(data, "generate_manuscript")
        database.update_project(self.pid, None, data)
        with patch("services.ebook.generate_ebook", side_effect=_mock_generate_ok):
            r2 = self.client.post(
                f"/ebook-workspace/{self.pid}/generate-manuscript",
                json={
                    "confirmation_token": est2["estimate"]["confirmation_token"],
                    "expected_artifact_id": est2["estimate"]["artifact_id"],
                    "expected_revision": est2["estimate"]["artifact_revision"],
                    "outline_digest": "not-the-digest",
                    "max_authorized_usd": 1.5,
                    "idempotency_key": "k-stale-outline",
                },
            )
            self.assertEqual(r2.status_code, 400)

    def test_07_duplicate_click_no_duplicate_paid_calls(self):
        self._fresh()
        data = dict(database.get_project(self.pid)["data"])
        est = estimate_paid_action(data, "generate_manuscript")
        database.update_project(self.pid, None, data)
        payload = {
            "confirmation_token": est["estimate"]["confirmation_token"],
            "expected_artifact_id": est["estimate"]["artifact_id"],
            "expected_revision": est["estimate"]["artifact_revision"],
            "outline_digest": est["estimate"]["outline_digest"],
            "max_authorized_usd": 1.5,
            "idempotency_key": "k-dup-1",
        }
        with patch("services.ebook.generate_ebook", side_effect=_mock_generate_ok) as mocked:
            r1 = self.client.post(f"/ebook-workspace/{self.pid}/generate-manuscript", json=payload)
            self.assertEqual(r1.status_code, 200, r1.get_data(as_text=True))
            calls_after_first = mocked.call_count
            spent1 = float(
                database.get_project(self.pid)["data"]["ebook_workspace"]["paid_call_ledger"]["spent_usd"]
            )
            r2 = self.client.post(f"/ebook-workspace/{self.pid}/generate-manuscript", json=payload)
            self.assertEqual(r2.status_code, 200)
            self.assertTrue(r2.get_json().get("duplicate"))
            self.assertEqual(mocked.call_count, calls_after_first)
            spent2 = float(
                database.get_project(self.pid)["data"]["ebook_workspace"]["paid_call_ledger"]["spent_usd"]
            )
            self.assertAlmostEqual(spent1, spent2, places=4)

    def test_08_budget_cap_enforced_server_side(self):
        self._fresh()
        data = dict(database.get_project(self.pid)["data"])
        ledger = data["ebook_workspace"]["paid_call_ledger"]
        ledger["spent_usd"] = 3.40
        ledger["remaining_usd"] = 0.10
        database.update_project(self.pid, None, data)
        r = self.client.post(
            f"/ebook-workspace/{self.pid}/estimate-cost",
            json={"action": "generate_manuscript"},
        )
        self.assertEqual(r.status_code, 400)

    def test_09_mocked_generation_uses_approved_inputs(self):
        self._fresh()
        data = dict(database.get_project(self.pid)["data"])
        est = estimate_paid_action(data, "generate_manuscript")
        database.update_project(self.pid, None, data)
        with patch("services.ebook.generate_ebook", side_effect=_mock_generate_ok) as mocked:
            r = self.client.post(
                f"/ebook-workspace/{self.pid}/generate-manuscript",
                json={
                    "confirmation_token": est["estimate"]["confirmation_token"],
                    "expected_artifact_id": est["estimate"]["artifact_id"],
                    "expected_revision": est["estimate"]["artifact_revision"],
                    "outline_digest": est["estimate"]["outline_digest"],
                    "max_authorized_usd": 1.5,
                    "idempotency_key": "k-inputs",
                },
            )
            self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
            kwargs = mocked.call_args.kwargs
            notes = kwargs.get("research_notes") or ""
            self.assertIn("Lonnie Brown", kwargs.get("author") or notes)
            self.assertIn("What This Business Actually Looks Like", notes)
            self.assertIn("DS-RX1HS", notes)
            self.assertTrue(str(self.project["name"]).startswith(ACCEPTANCE_PROJECT_NAME))

    def test_10_result_awaiting_approval(self):
        self._fresh()
        data = dict(database.get_project(self.pid)["data"])
        est = estimate_paid_action(data, "generate_manuscript")
        database.update_project(self.pid, None, data)
        with patch("services.ebook.generate_ebook", side_effect=_mock_generate_ok):
            r = self.client.post(
                f"/ebook-workspace/{self.pid}/generate-manuscript",
                json={
                    "confirmation_token": est["estimate"]["confirmation_token"],
                    "expected_artifact_id": est["estimate"]["artifact_id"],
                    "expected_revision": est["estimate"]["artifact_revision"],
                    "outline_digest": est["estimate"]["outline_digest"],
                    "max_authorized_usd": 1.5,
                    "idempotency_key": "k-await",
                },
            )
        ws = r.get_json()["workspace"]
        rail = {s["id"]: s["status"] for s in ws["rail"]}
        self.assertEqual(rail["manuscript"], "needs_correction")
        self.assertEqual(ws["manuscript"]["can_approve"], False)
        self.assertNotEqual(ws["manuscript"].get("quality_status"), "PASS")

    def test_11_failed_qa_needs_correction(self):
        self._fresh()
        data = dict(database.get_project(self.pid)["data"])
        est = estimate_paid_action(data, "generate_manuscript")
        database.update_project(self.pid, None, data)
        with patch("services.ebook.generate_ebook", side_effect=_mock_generate_bad):
            r = self.client.post(
                f"/ebook-workspace/{self.pid}/generate-manuscript",
                json={
                    "confirmation_token": est["estimate"]["confirmation_token"],
                    "expected_artifact_id": est["estimate"]["artifact_id"],
                    "expected_revision": est["estimate"]["artifact_revision"],
                    "outline_digest": est["estimate"]["outline_digest"],
                    "max_authorized_usd": 1.5,
                    "idempotency_key": "k-qa-fail",
                },
            )
        self.assertEqual(r.status_code, 200)
        ws = r.get_json()["workspace"]
        rail = {s["id"]: s["status"] for s in ws["rail"]}
        self.assertEqual(rail["manuscript"], "needs_correction")
        self.assertTrue(ws["manuscript"]["qa_findings"])

    def test_12_later_stages_remain_blocked(self):
        self._fresh()
        data = dict(database.get_project(self.pid)["data"])
        est = estimate_paid_action(data, "generate_manuscript")
        database.update_project(self.pid, None, data)
        with patch("services.ebook.generate_ebook", side_effect=_mock_generate_ok):
            r = self.client.post(
                f"/ebook-workspace/{self.pid}/generate-manuscript",
                json={
                    "confirmation_token": est["estimate"]["confirmation_token"],
                    "expected_artifact_id": est["estimate"]["artifact_id"],
                    "expected_revision": est["estimate"]["artifact_revision"],
                    "outline_digest": est["estimate"]["outline_digest"],
                    "max_authorized_usd": 1.5,
                    "idempotency_key": "k-blocked",
                },
            )
        ws = r.get_json()["workspace"]
        self.assertFalse(ws["gates"]["visuals_enabled"])
        rail = {s["id"]: s["status"] for s in ws["rail"]}
        for s in ("visuals", "cover", "design", "preview", "preflight", "export"):
            self.assertEqual(rail[s], "not_started")

    def test_13_ledger_updates_exactly_once(self):
        self._fresh()
        before_calls = int(
            database.get_project(self.pid)["data"]["ebook_workspace"]["paid_call_ledger"]["paid_calls"]
        )
        before_spent = float(
            database.get_project(self.pid)["data"]["ebook_workspace"]["paid_call_ledger"]["spent_usd"]
        )
        data = dict(database.get_project(self.pid)["data"])
        est = estimate_paid_action(data, "generate_manuscript")
        database.update_project(self.pid, None, data)
        with patch("services.ebook.generate_ebook", side_effect=_mock_generate_ok):
            self.client.post(
                f"/ebook-workspace/{self.pid}/generate-manuscript",
                json={
                    "confirmation_token": est["estimate"]["confirmation_token"],
                    "expected_artifact_id": est["estimate"]["artifact_id"],
                    "expected_revision": est["estimate"]["artifact_revision"],
                    "outline_digest": est["estimate"]["outline_digest"],
                    "max_authorized_usd": 1.5,
                    "idempotency_key": "k-ledger",
                },
            )
        ledger = database.get_project(self.pid)["data"]["ebook_workspace"]["paid_call_ledger"]
        self.assertEqual(int(ledger["paid_calls"]), before_calls + 1)
        self.assertAlmostEqual(float(ledger["spent_usd"]), before_spent + 1.5, places=3)
        ms_calls = [c for c in ledger.get("calls") or [] if c.get("purpose") == "generate_manuscript"]
        self.assertEqual(len(ms_calls), 1)

    def test_14_reopen_preserves_manuscript_and_status(self):
        self._fresh()
        data = dict(database.get_project(self.pid)["data"])
        est = estimate_paid_action(data, "generate_manuscript")
        database.update_project(self.pid, None, data)
        with patch("services.ebook.generate_ebook", side_effect=_mock_generate_ok):
            self.client.post(
                f"/ebook-workspace/{self.pid}/generate-manuscript",
                json={
                    "confirmation_token": est["estimate"]["confirmation_token"],
                    "expected_artifact_id": est["estimate"]["artifact_id"],
                    "expected_revision": est["estimate"]["artifact_revision"],
                    "outline_digest": est["estimate"]["outline_digest"],
                    "max_authorized_usd": 1.5,
                    "idempotency_key": "k-reopen",
                },
            )
        ws = self.client.get(f"/ebook-workspace/{self.pid}").get_json()["workspace"]
        self.assertEqual(
            {s["id"]: s["status"] for s in ws["rail"]}["manuscript"], "needs_correction"
        )
        self.assertIn("Dye-Sublimation Printing", ws["manuscript"]["content"])
        proj = self.client.get(f"/projects/{self.pid}").get_json()
        self.assertIn("Dye-Sublimation", proj["data"].get("content") or "")

    def test_15_no_cover_image_pdf_zip_call(self):
        self._fresh()
        data = dict(database.get_project(self.pid)["data"])
        est = estimate_paid_action(data, "generate_manuscript")
        database.update_project(self.pid, None, data)
        with patch("services.ebook.generate_ebook", side_effect=_mock_generate_ok):
            with patch("services.ebook_cover_local.build_local_cover", create=True) as cover:
                with patch("services.packaging.build_product_export", create=True) as export:
                    self.client.post(
                        f"/ebook-workspace/{self.pid}/generate-manuscript",
                        json={
                            "confirmation_token": est["estimate"]["confirmation_token"],
                            "expected_artifact_id": est["estimate"]["artifact_id"],
                            "expected_revision": est["estimate"]["artifact_revision"],
                            "outline_digest": est["estimate"]["outline_digest"],
                            "max_authorized_usd": 1.5,
                            "idempotency_key": "k-no-assets",
                        },
                    )
                    cover.assert_not_called()
                    export.assert_not_called()

    def test_16_non_ebook_unchanged_smoke(self):
        r = self.client.post(
            "/projects",
            json={
                "name": "Manuscript Isolation Product Smoke",
                "type": "product",
                "data": {"product_type": "coloring_book", "title": "Smoke"},
                "user_saved": True,
            },
        )
        self.assertIn(r.status_code, (200, 201))
        self.assertEqual(r.get_json()["type"], "product")


if __name__ == "__main__":
    unittest.main()
