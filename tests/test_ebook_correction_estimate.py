"""Correction estimate/confirmation wiring — zero paid provider calls."""
from __future__ import annotations

import copy
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
    CHAPTER_UNIT_USD,
    FROZEN_LIVE_EBOOK_PROJECT_ID,
    PAID_ACTIONS,
    STATUS_NEEDS_CORRECTION,
    authorize_workspace_budget_cap,
    authorize_workspace_budget_into_project,
    cancel_paid_estimate,
    estimate_paid_action,
    execute_correct_manuscript,
    get_workspace,
    manuscript_digest,
    normalize_paid_action,
    outline_digest,
    set_stage_status,
    structural_findings_digest,
    _recompute_next_action,
)


REVISED = [
    "What This Business Actually Looks Like",
    "Startup Reality Check: Budget, Legal Basics, and Insurance",
    "Core Camera Kit, Printing Equipment, and Backup Gear",
    "Finding Clients and Turning Inquiries into Signed Bookings",
    "Packages and Pricing Scenarios That Protect Your Margin",
    "Planning the Event: Contracts, Timelines, Space, Power, and Staffing",
    "Event-Day Operations: From Photograph to Guest Delivery",
    "Dye-Sublimation Printing: Setup, Queue, Ordering, Payment, and Pickup",
    "Keepsakes Beyond Photo Prints: Separate Equipment and Workflow",
    "Common Mistakes and Your 30-Day First Paid Event Plan",
]


def _seed_needs_correction_project() -> tuple[int, dict]:
    """Create an isolated needs-correction ebook project (does not touch #2472)."""
    from services.ebook_project_workspace import (
        REVISED_ACCEPTANCE_OUTLINE_TITLES,
        build_acceptance_project_data,
        new_workspace,
        empty_ledger,
        ensure_workspace,
        _recompute_next_action,
    )

    data = build_acceptance_project_data()
    data["acceptance_marker"] = None
    data["outline"] = [
        {"order": i + 1, "title": t, "purpose": f"Purpose for {t}", "approved": True}
        for i, t in enumerate(REVISED)
    ]
    body = ["# From First Booking to On-Site Prints\n"]
    early = [
        "What This Business Actually Looks Like",
        "Startup Reality Check: Budget, Legal Basics, and Insurance",
        "Core Camera Kit and Backup Gear",
        "Packages Clients Can Understand",
        "Pricing Scenarios That Protect Your Margin",
        "From Inquiry to Signed Booking",
        "Event-Day Operations Without Chaos",
        "Dye-Sublimation On-Site Printing",
        "Keepsakes Beyond Photo Prints",
        "Common Mistakes and Your First Paid Event Checklist",
        "Conclusion",
        "Disclaimer",
    ]
    for i, t in enumerate(early, 1):
        body.append(f"## {t}\n\nUnique chapter {i} body about {t.lower()}.\n")
    md = "\n".join(body)
    data["content"] = md
    data["ebook"] = md
    ws = data["ebook_workspace"]
    ws["marker"] = None
    ws["manuscript_structure_findings"] = [
        "CHAPTER_TITLE_MISMATCH order=3: approved vs generated",
        "PROHIBITED_NUMBERED_BACK_MATTER: ['Conclusion', 'Disclaimer']",
    ]
    ws["manuscript_qa"] = list(ws["manuscript_structure_findings"])
    ledger = ws["paid_call_ledger"]
    ledger["spent_usd"] = 2.428
    ledger["remaining_usd"] = 1.072
    ledger["budget_cap_usd"] = 3.5
    ledger["paid_calls"] = 11
    set_stage_status(ws, "manuscript", STATUS_NEEDS_CORRECTION, note="structure fail")
    _recompute_next_action(ws)
    project = database.create_project(
        "Correction Estimate Wiring Smoke",
        "ebook",
        data,
        user_saved=False,
        system_test=True,
        temporary=True,
    )
    pid = project["id"]
    data["_project_id"] = pid
    database.update_project(pid, None, data)
    return pid, data


class CorrectionEstimateWiringTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self.pid, self.data = _seed_needs_correction_project()

    def _reload(self):
        self.data = dict(database.get_project(self.pid)["data"])
        self.data["_project_id"] = self.pid
        return self.data

    def test_canonical_action_registered(self):
        self.assertIn("correct_manuscript", PAID_ACTIONS)
        self.assertEqual(normalize_paid_action("request_correction"), "correct_manuscript")

    def test_estimate_succeeds_and_fits_remaining(self):
        data = self._reload()
        before = copy.deepcopy(data)
        est = estimate_paid_action(data, "correct_manuscript")
        e = est["estimate"]
        self.assertEqual(e["action"], "correct_manuscript")
        self.assertLessEqual(float(e["estimated_max_usd"]), 1.072 + 1e-9)
        self.assertLessEqual(float(e["estimated_max_usd"]), float(e["remaining_usd"]) + 1e-9)
        self.assertEqual(float(e["spent_usd"]), 2.428)
        self.assertEqual(float(e["remaining_usd"]), 1.072)
        self.assertEqual(e["outline_digest"], outline_digest(data))
        self.assertEqual(e["manuscript_digest"], manuscript_digest(data))
        self.assertEqual(e["structural_findings_digest"], structural_findings_digest(data))
        self.assertEqual(int(e["project_id"]), self.pid)
        self.assertTrue(e["confirmation_required"])
        self.assertIn("Confirmation required", e["expires_note"])
        self.assertTrue(e["confirmation_token"])
        self.assertTrue(e["expires_at"])
        self.assertEqual(e["artifact_id"], str(data.get("artifact_id") or data.get("package_id") or ""))
        self.assertEqual(int(e["artifact_revision"]), int(data.get("artifact_revision") or 1))
        # Estimate must not mutate manuscript/findings/ledger spend.
        self.assertEqual(data["content"], before["content"])
        self.assertEqual(
            data["ebook_workspace"]["manuscript_structure_findings"],
            before["ebook_workspace"]["manuscript_structure_findings"],
        )
        self.assertEqual(
            float(data["ebook_workspace"]["paid_call_ledger"]["spent_usd"]),
            2.428,
        )
        self.assertEqual(
            float(data["ebook_workspace"]["paid_call_ledger"]["remaining_usd"]),
            1.072,
        )

    def test_route_estimate_costs_zero_no_provider(self):
        data = self._reload()
        database.update_project(self.pid, None, data)
        with patch("services.ebook.correct_ebook_manuscript") as mocked:
            r = self.client.post(
                f"/ebook-workspace/{self.pid}/estimate-cost",
                json={"action": "correct_manuscript"},
            )
            self.assertEqual(r.status_code, 200)
            body = r.get_json()
            self.assertTrue(body["ok"])
            self.assertEqual(body["estimate"]["action"], "correct_manuscript")
            self.assertLessEqual(float(body["estimate"]["estimated_max_usd"]), 1.072 + 1e-9)
            self.assertTrue(body["estimate"]["confirmation_required"])
            self.assertEqual(float(body["estimate"]["spent_usd"]), 2.428)
            self.assertEqual(float(body["estimate"]["remaining_usd"]), 1.072)
            mocked.assert_not_called()
        with patch("services.ebook_project_workspace.execute_correct_manuscript") as exec_ms:
            r2 = self.client.post(
                f"/ebook-workspace/{self.pid}/estimate-cost",
                json={"action": "request_correction"},
            )
            self.assertEqual(r2.status_code, 200)
            self.assertEqual(r2.get_json()["estimate"]["action"], "correct_manuscript")
            exec_ms.assert_not_called()
        after = database.get_project(self.pid)["data"]
        self.assertEqual(float(after["ebook_workspace"]["paid_call_ledger"]["spent_usd"]), 2.428)
        self.assertEqual(float(after["ebook_workspace"]["paid_call_ledger"]["remaining_usd"]), 1.072)
        self.assertEqual(after["content"], data["content"])
        self.assertEqual(
            after["ebook_workspace"]["rail"]["manuscript"]["status"],
            STATUS_NEEDS_CORRECTION,
        )

    def _try_correct(self, data, est, **overrides):
        kwargs = {
            "confirmation_token": est["estimate"]["confirmation_token"],
            "expected_artifact_id": str(data.get("artifact_id") or ""),
            "expected_revision": int(data.get("artifact_revision") or 1),
            "outline_digest_expected": est["estimate"]["outline_digest"],
            "max_authorized_usd": float(est["estimate"]["max_authorized_usd"]),
            "idempotency_key": "token-check",
            "correct_fn": lambda **k: {"ebook": data.get("content") or ""},
        }
        kwargs.update(overrides)
        return execute_correct_manuscript(data, **kwargs)

    def test_invalid_and_reused_tokens_fail(self):
        data = self._reload()
        est = estimate_paid_action(data, "correct_manuscript")
        with self.assertRaises(ValueError):
            self._try_correct(data, est, confirmation_token="bogus", idempotency_key="bad-token")
        with self.assertRaises(ValueError):
            self._try_correct(data, est, confirmation_token="", idempotency_key="missing-token")
        # Mark used then reuse
        data = self._reload()
        est = estimate_paid_action(data, "correct_manuscript")
        pending = data["ebook_workspace"]["paid_call_ledger"]["pending_estimate"]
        pending["used"] = True
        with self.assertRaises(ValueError):
            self._try_correct(data, est, idempotency_key="reused-token")
        # Stale manuscript digest
        data = self._reload()
        est = estimate_paid_action(data, "correct_manuscript")
        data["content"] = data["content"] + "\n\nTampered."
        data["ebook"] = data["content"]
        with self.assertRaises(ValueError):
            self._try_correct(data, est, idempotency_key="stale-ms", correct_fn=lambda **k: {"ebook": "# x\n"})
        # Expired token
        data = self._reload()
        est = estimate_paid_action(data, "correct_manuscript")
        pending = data["ebook_workspace"]["paid_call_ledger"]["pending_estimate"]
        pending["expires_at"] = "2000-01-01T00:00:00+00:00"
        with self.assertRaises(ValueError):
            self._try_correct(data, est, idempotency_key="expired-token")
        # Mismatched findings digest
        data = self._reload()
        est = estimate_paid_action(data, "correct_manuscript")
        data["ebook_workspace"]["manuscript_structure_findings"] = ["tampered-finding"]
        with self.assertRaises(ValueError):
            self._try_correct(data, est, idempotency_key="stale-findings")
        # Mismatched artifact
        data = self._reload()
        est = estimate_paid_action(data, "correct_manuscript")
        with self.assertRaises(ValueError):
            self._try_correct(data, est, expected_artifact_id="wrong-artifact", idempotency_key="mismatch-art")
        # Mismatched project
        data = self._reload()
        est = estimate_paid_action(data, "correct_manuscript")
        data["_project_id"] = 999999
        with self.assertRaises(ValueError):
            self._try_correct(data, est, idempotency_key="mismatch-project")

    def test_cancel_estimate_preserves_ledger_and_manuscript(self):
        data = self._reload()
        estimate_paid_action(data, "correct_manuscript")
        data = cancel_paid_estimate(data)
        self.assertIsNone(data["ebook_workspace"]["paid_call_ledger"]["pending_estimate"])
        self.assertEqual(float(data["ebook_workspace"]["paid_call_ledger"]["spent_usd"]), 2.428)
        self.assertTrue(data["content"])

    def test_other_paid_actions_still_known(self):
        for action in (
            "run_research",
            "generate_title_options",
            "generate_outline_options",
            "generate_manuscript",
            "correct_manuscript",
        ):
            self.assertIn(action, PAID_ACTIONS)
        data = self._reload()
        with self.assertRaises(ValueError) as ctx:
            estimate_paid_action(data, "generate_manuscript")
        msg = str(ctx.exception)
        self.assertNotIn("Unknown paid action", msg)
        self.assertIn("Request Correction", msg)

    def test_live_2472_unchanged_by_isolated_estimate(self):
        live = database.get_project(2472)
        self.assertIsNotNone(live)
        before = copy.deepcopy(live["data"])
        before_ledger = copy.deepcopy(before["ebook_workspace"]["paid_call_ledger"])
        before_ms = manuscript_digest(before)
        before_find = structural_findings_digest(before)
        data = self._reload()
        with patch("services.ebook.correct_ebook_manuscript") as mocked:
            est = estimate_paid_action(data, "correct_manuscript")
            self.assertTrue(est["ok"])
            mocked.assert_not_called()
        after = database.get_project(2472)["data"]
        self.assertEqual(after["content"], before["content"])
        self.assertEqual(manuscript_digest(after), before_ms)
        self.assertEqual(structural_findings_digest(after), before_find)
        self.assertEqual(
            after["ebook_workspace"]["manuscript_structure_findings"],
            before["ebook_workspace"]["manuscript_structure_findings"],
        )
        self.assertEqual(
            after["ebook_workspace"]["paid_call_ledger"]["spent_usd"],
            before_ledger["spent_usd"],
        )
        self.assertEqual(
            after["ebook_workspace"]["paid_call_ledger"]["remaining_usd"],
            before_ledger["remaining_usd"],
        )
        self.assertEqual(
            after["ebook_workspace"]["rail"]["manuscript"]["status"],
            before["ebook_workspace"]["rail"]["manuscript"]["status"],
        )
        self.assertEqual(
            after["ebook_workspace"]["rail"]["manuscript"]["status"],
            "awaiting_approval",
        )
        self.assertIsNone((after["ebook_workspace"]["paid_call_ledger"] or {}).get("pending_estimate"))

    def test_kdp_and_other_products_unchanged(self):
        from services.kdp.preflight import run_kdp_preflight, assert_prepare_kdp_package_allowed
        from services.kdp.metadata import validate_book_metadata
        from services.coloring_book.builder import validate_theme_adherence

        self.assertTrue(callable(run_kdp_preflight))
        self.assertTrue(callable(assert_prepare_kdp_package_allowed))
        self.assertTrue(callable(validate_book_metadata))
        self.assertTrue(callable(validate_theme_adherence))
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Amazon KDP Preflight", js)
        self.assertIn("kdpPreflightPanel", js)

    def test_ui_wires_estimate_not_auto_execute(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('action: "correct_manuscript"', js)
        self.assertIn("estimateCorrectionInWorkspace", js)
        self.assertIn("Confirm and Correct Manuscript", js)
        self.assertIn("/estimate-cost", js)
        self.assertIn("/correct-manuscript", js)
        self.assertIn("authorize_paid_call: true", js)
        self.assertIn("This estimate cost", js)
        self.assertIn("data-ws-authorize-paid", js)
        # Request Correction click handler estimates only; execute is a later confirm click.
        idx_est = js.index("async function estimateCorrectionInWorkspace")
        idx_confirm = js.index("data-ws-confirm-correct", idx_est)
        first_api = js.index("/estimate-cost", idx_est)
        first_exec = js.index("/correct-manuscript", idx_est)
        self.assertLess(first_api, idx_confirm)
        self.assertGreater(first_exec, idx_confirm)

    def test_estimate_route_never_calls_provider_or_charges(self):
        data = self._reload()
        database.update_project(self.pid, None, data)
        before_spent = float(data["ebook_workspace"]["paid_call_ledger"]["spent_usd"])
        before_calls = list(data["ebook_workspace"]["paid_call_ledger"].get("calls") or [])
        before_content = data["content"]
        with patch("services.ebook.generate_one_chapter") as mocked:
            r1 = self.client.post(
                f"/ebook-workspace/{self.pid}/estimate-cost",
                json={"action": "correct_manuscript"},
            )
            self.assertEqual(r1.status_code, 200, r1.get_data(as_text=True))
            r2 = self.client.post(
                f"/ebook-workspace/{self.pid}/estimate-cost",
                json={"action": "request_correction"},
            )
            self.assertEqual(r2.status_code, 200, r2.get_data(as_text=True))
            mocked.assert_not_called()
        est = r2.get_json()["estimate"]
        self.assertEqual(float(est["estimate_cost_usd"]), 0.0)
        self.assertTrue(est["estimate_is_free"])
        self.assertFalse(est["used"])
        self.assertTrue(est["confirmation_required"])
        self.assertEqual(float(est["spent_usd"]), before_spent)
        after = database.get_project(self.pid)["data"]
        ledger = after["ebook_workspace"]["paid_call_ledger"]
        self.assertEqual(float(ledger["spent_usd"]), before_spent)
        self.assertEqual(list(ledger.get("calls") or []), before_calls)
        self.assertEqual(after["content"], before_content)
        self.assertFalse((ledger.get("pending_estimate") or {}).get("used"))
        r3 = self.client.post(f"/ebook-workspace/{self.pid}/cancel-estimate", json={})
        self.assertEqual(r3.status_code, 200)
        cancelled = database.get_project(self.pid)["data"]
        self.assertEqual(
            float(cancelled["ebook_workspace"]["paid_call_ledger"]["spent_usd"]),
            before_spent,
        )
        self.assertIsNone(cancelled["ebook_workspace"]["paid_call_ledger"].get("pending_estimate"))
        with patch("services.ebook.generate_one_chapter") as mocked:
            reopened = self.client.get(f"/ebook-workspace/{self.pid}")
            self.assertEqual(reopened.status_code, 200)
            mocked.assert_not_called()
        self.assertEqual(
            float(reopened.get_json()["workspace"]["budget"]["spent_usd"]),
            before_spent,
        )

    def test_correct_route_rejects_estimate_without_paid_authorization(self):
        data = self._reload()
        est = estimate_paid_action(data, "correct_manuscript")
        database.update_project(self.pid, None, data)
        spent = float(data["ebook_workspace"]["paid_call_ledger"]["spent_usd"])
        with patch("services.ebook.generate_one_chapter") as mocked:
            r = self.client.post(
                f"/ebook-workspace/{self.pid}/correct-manuscript",
                json={
                    "confirmation_token": est["estimate"]["confirmation_token"],
                    "expected_artifact_id": est["estimate"]["artifact_id"],
                    "expected_revision": est["estimate"]["artifact_revision"],
                    "outline_digest": est["estimate"]["outline_digest"],
                    "max_authorized_usd": est["estimate"]["max_authorized_usd"],
                    "idempotency_key": "no-auth-flag",
                },
            )
            mocked.assert_not_called()
        self.assertEqual(r.status_code, 400)
        after = database.get_project(self.pid)["data"]
        self.assertEqual(
            float(after["ebook_workspace"]["paid_call_ledger"]["spent_usd"]),
            spent,
        )

    def test_duplicate_confirmation_does_not_double_charge(self):
        data = self._reload()
        est = estimate_paid_action(data, "correct_manuscript")
        spent_before = float(data["ebook_workspace"]["paid_call_ledger"]["spent_usd"])

        def _one_failed_chapter(book, chapter):
            return f"## {chapter.title}\n\nShort failing body without required example.\n"

        first = execute_correct_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="dup-corr-once",
            correct_chapter_fn=_one_failed_chapter,
        )
        spent_after = float(first["data"]["ebook_workspace"]["paid_call_ledger"]["spent_usd"])
        self.assertAlmostEqual(spent_after, spent_before + 0.15, places=2)
        self.assertEqual(int(first["result"]["chapter_calls"]), 1)
        replay = execute_correct_manuscript(
            first["data"],
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="dup-corr-once",
            correct_chapter_fn=_one_failed_chapter,
        )
        self.assertTrue(replay.get("duplicate"))
        self.assertEqual(
            float(replay["data"]["ebook_workspace"]["paid_call_ledger"]["spent_usd"]),
            spent_after,
        )

    def test_project_4249_estimate_copy_does_not_change_manuscript_or_spend(self):
        live = database.get_project(4249)
        if not live:
            self.skipTest("project 4249 not present")
        data = copy.deepcopy(live["data"])
        data["_project_id"] = 4249
        before_spent = float((data["ebook_workspace"]["paid_call_ledger"] or {}).get("spent_usd") or 0)
        before_content = data.get("content") or ""
        before_qa = copy.deepcopy((data.get("ebook_workspace") or {}).get("manuscript_qa"))
        from services.ebook_project_workspace import accepted_chapter_digests

        before_digests = accepted_chapter_digests(data)
        with patch("services.ebook.generate_one_chapter") as mocked:
            est = estimate_paid_action(data, "correct_manuscript")
            mocked.assert_not_called()
        self.assertEqual(float(est["estimate"]["estimate_cost_usd"]), 0.0)
        self.assertEqual(
            float(data["ebook_workspace"]["paid_call_ledger"]["spent_usd"]),
            before_spent,
        )
        self.assertEqual(data.get("content") or "", before_content)
        self.assertEqual(data["ebook_workspace"].get("manuscript_qa"), before_qa)
        after_digests = accepted_chapter_digests(data)
        self.assertGreaterEqual(len(after_digests), len(before_digests))
        self.assertEqual(after_digests[: len(before_digests)], before_digests)
        stored = database.get_project(4249)["data"]
        self.assertEqual(stored.get("content") or "", before_content)
        self.assertEqual(accepted_chapter_digests(stored), before_digests)
        self.assertEqual(
            float(stored["ebook_workspace"]["paid_call_ledger"]["spent_usd"]),
            before_spent,
        )


class ProjectBudgetAuthorizationTests(unittest.TestCase):
    """User cap raise is metadata, not a paid call. Isolated from #2472 and #4249."""

    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True

    def _isolated_stopped_at_ch3(self) -> tuple[int, dict]:
        from services.ebook_project_workspace import build_acceptance_project_data

        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        data["artifact_id"] = "ebook-ws-budget-auth-test"
        data["artifact_revision"] = 1
        data["artifact_state"] = "DRAFT"
        md = "# Budget Auth Test\n\n## What This Business Actually Looks Like\n\nCh1 body.\n\n## Startup Reality Check: Budget, Legal Basics, and Insurance\n\nCh2 body.\n\n## Core Camera Kit, Printing Equipment, and Backup Gear\n\nCh3 missing used-vs-rent-vs-buy.\n"
        data["content"] = md
        data["ebook"] = md
        ws = data["ebook_workspace"]
        ws["marker"] = None
        ws["accepted_chapters"] = [
            {"order": 1, "title": REVISED[0], "body": "Ch1 preserved body"},
            {"order": 2, "title": REVISED[1], "body": "Ch2 preserved body"},
        ]
        ws["manuscript_qa"] = [
            "Ch3 MISSING_REQUIRED_EXAMPLE: Missing required example: used vs rent vs buy"
        ]
        ws["manuscript_structure_findings"] = list(ws["manuscript_qa"])
        ws["last_manuscript_generation"] = {"ts": "test", "charge_usd": 0.45}
        ledger = ws["paid_call_ledger"]
        ledger["spent_usd"] = 0.45
        ledger["remaining_usd"] = 1.05
        ledger["budget_cap_usd"] = 1.50
        ledger["paid_calls"] = 3
        ledger["calls"] = [
            {"purpose": "generate_manuscript", "estimated_cost_usd": 0.45, "meta": {"failed_orders": [3]}}
        ]
        ledger["idempotency_keys"] = ["ms-test-budget-auth"]
        set_stage_status(ws, "manuscript", STATUS_NEEDS_CORRECTION, note="ch3 fail")
        _recompute_next_action(ws)
        project = database.create_project(
            "Budget Auth Isolated Ebook",
            "ebook",
            data,
            user_saved=False,
            system_test=True,
            temporary=True,
        )
        pid = project["id"]
        data["_project_id"] = pid
        database.update_project(pid, None, data)
        return pid, dict(database.get_project(pid)["data"])

    def test_cap_raise_preserves_manuscript_and_unlocks_1_20_correction(self):
        pid, data = self._isolated_stopped_at_ch3()
        before_content = data["content"]
        before_calls = copy.deepcopy(data["ebook_workspace"]["paid_call_ledger"]["calls"])
        before_accepted = copy.deepcopy(data["ebook_workspace"]["accepted_chapters"])
        before_qa = copy.deepcopy(data["ebook_workspace"]["manuscript_qa"])
        before_artifact = data.get("artifact_id")
        before_rev = data.get("artifact_revision")
        before_gen = copy.deepcopy(data["ebook_workspace"]["last_manuscript_generation"])
        before_paid = int(data["ebook_workspace"]["paid_call_ledger"]["paid_calls"])

        r = self.client.post(
            f"/ebook-workspace/{pid}/authorize-budget",
            json={
                "budget_cap_usd": 1.65,
                "reason": "User authorized Chapter 3 correction plus Chapters 4-10",
            },
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        ws = r.get_json()["workspace"]
        self.assertAlmostEqual(float(ws["budget"]["cap_usd"]), 1.65, places=2)
        self.assertAlmostEqual(float(ws["budget"]["spent_usd"]), 0.45, places=2)
        self.assertAlmostEqual(float(ws["budget"]["remaining_usd"]), 1.20, places=2)
        self.assertEqual(int(ws["budget"]["paid_calls"] or 0), 3)
        self.assertEqual(ws["next_action"], "request_correction")

        stored = database.get_project(pid)["data"]
        self.assertEqual(stored["content"], before_content)
        self.assertEqual(stored["artifact_id"], before_artifact)
        self.assertEqual(stored["artifact_revision"], before_rev)
        self.assertEqual(stored["ebook_workspace"]["accepted_chapters"], before_accepted)
        self.assertEqual(stored["ebook_workspace"]["manuscript_qa"], before_qa)
        self.assertEqual(stored["ebook_workspace"]["last_manuscript_generation"], before_gen)
        self.assertEqual(stored["ebook_workspace"]["paid_call_ledger"]["calls"], before_calls)
        self.assertEqual(int(stored["ebook_workspace"]["paid_call_ledger"]["paid_calls"]), before_paid)
        auths = stored["ebook_workspace"]["paid_call_ledger"]["budget_authorizations"]
        self.assertEqual(len(auths), 1)
        self.assertFalse(auths[0]["paid_call"])
        self.assertAlmostEqual(float(auths[0]["old_cap_usd"]), 1.50, places=2)
        self.assertAlmostEqual(float(auths[0]["new_cap_usd"]), 1.65, places=2)

        est_data = dict(stored)
        est_data["_project_id"] = pid
        est = estimate_paid_action(est_data, "correct_manuscript")["estimate"]
        self.assertEqual(int(est["accepted_chapter_count"]), 2)
        self.assertEqual(int(est["pending_chapter_count"]), 8)
        self.assertEqual(int(est["resume_from_order"]), 3)
        self.assertEqual(int(est["failed_chapter_order"]), 3)
        self.assertAlmostEqual(float(est["per_chapter_max_usd"]), CHAPTER_UNIT_USD, places=2)
        self.assertAlmostEqual(float(est["max_total_usd"]), 1.20, places=2)
        self.assertAlmostEqual(float(est["estimated_max_usd"]), 1.20, places=2)
        self.assertAlmostEqual(float(est["spent_usd"]), 0.45, places=2)
        self.assertAlmostEqual(float(est["remaining_usd"]), 1.20, places=2)
        self.assertAlmostEqual(float(est["budget_cap_usd"]), 1.65, places=2)
        self.assertTrue(est["confirmation_required"])
        # In-memory estimate must not be the persisted live path for #4249; cancel if routed.
        live = database.get_project(pid)["data"]
        self.assertEqual(live["content"], before_content)

    def test_refuses_frozen_2472_and_does_not_lower_cap(self):
        frozen = self.client.post(
            f"/ebook-workspace/{FROZEN_LIVE_EBOOK_PROJECT_ID}/authorize-budget",
            json={"budget_cap_usd": 1.65},
        )
        self.assertEqual(frozen.status_code, 400)
        self.assertIn("frozen", (frozen.get_json() or {}).get("error", "").lower())
        pid, data = self._isolated_stopped_at_ch3()
        with self.assertRaises(ValueError):
            authorize_workspace_budget_cap(data, 1.00)
        with self.assertRaises(ValueError):
            authorize_workspace_budget_into_project(database, pid, 1.40)


class ValidatedChapterReconciliationTests(unittest.TestCase):
    """PASS chapters already in the manuscript must be accepted locally, not regenerated."""

    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self._client_patch = patch("ai_client.get_client", side_effect=AssertionError("paid client"))
        self._chat_patch = patch("ai_client.chat", side_effect=AssertionError("paid chat"))
        self._json_patch = patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json"))
        self._gen_patch = patch(
            "services.ebook.generate_one_chapter",
            side_effect=AssertionError("provider generate_one_chapter"),
        )
        self._client_patch.start()
        self._chat_patch.start()
        self._json_patch.start()
        self._gen_patch.start()

    def tearDown(self):
        self._client_patch.stop()
        self._chat_patch.stop()
        self._json_patch.stop()
        self._gen_patch.stop()

    def _isolated_ch3_pass_not_accepted(self, *, mention_only: bool = False) -> tuple[int, dict]:
        from services.ebook_manuscript_engine import (
            assemble_manuscript,
            split_front_chapters_back,
        )
        from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript
        from services.ebook_project_workspace import build_acceptance_project_data

        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        data["artifact_id"] = "ebook-ws-reconcile-ch3"
        data["artifact_revision"] = 1
        data["artifact_state"] = "DRAFT"
        strong = build_event_photo_strong_manuscript()
        _front, chapters, _back = split_front_chapters_back(strong)
        ch3 = next(c for c in chapters if c.order == 3)
        if mention_only:
            marker = "**Hypothetical planning example: Buy vs. Rent vs. Used**"
            idx = ch3.body.find(marker)
            self.assertGreaterEqual(idx, 0)
            ch3.body = (
                ch3.body[:idx]
                + "You might buy a camera or rent a lens. Used gear exists. "
                + "For example, some photographers buy a second body.\n"
            )
        md = assemble_manuscript(
            title=str(data.get("title") or "From First Booking to On-Site Prints"),
            subtitle=str(data.get("subtitle") or ""),
            author="Lonnie Brown",
            chapters=chapters[:3],
            disclaimer="",
            sources="",
        )
        data["content"] = md
        data["ebook"] = md
        ws = data["ebook_workspace"]
        ws["marker"] = None
        ws["accepted_chapters"] = [
            {"order": c.order, "title": c.title, "body": c.body}
            for c in chapters[:2]
        ]
        ledger = ws["paid_call_ledger"]
        ledger["spent_usd"] = 0.6
        ledger["remaining_usd"] = 1.2
        ledger["budget_cap_usd"] = 1.8
        ledger["paid_calls"] = 4
        ledger["calls"] = [{"purpose": "generate_manuscript", "estimated_cost_usd": 0.6}]
        ledger["budget_authorizations"] = [
            {"paid_call": False, "new_cap_usd": 1.8, "reason": "test cap"}
        ]
        set_stage_status(ws, "manuscript", STATUS_NEEDS_CORRECTION, note="ch3 pass not accepted")
        _recompute_next_action(ws)
        project = database.create_project(
            "Reconcile Ch3 PASS Isolated",
            "ebook",
            data,
            user_saved=False,
            system_test=True,
            temporary=True,
        )
        pid = project["id"]
        data["_project_id"] = pid
        database.update_project(pid, None, data)
        return pid, dict(database.get_project(pid)["data"])

    def test_reconcile_accepts_pass_chapter_without_provider_or_charge(self):
        from services.ebook_project_workspace import (
            accepted_chapter_digests,
            chapter_acceptance_digest,
            chapter_pipeline_stats,
            manuscript_digest,
            reconcile_validated_preserved_chapters,
            reconcile_validated_preserved_chapters_into_project,
        )
        from services.ebook_manuscript_engine import split_front_chapters_back

        pid, data = self._isolated_ch3_pass_not_accepted()
        before_ms = manuscript_digest(data)
        before_content = data["content"]
        before_spent = float(data["ebook_workspace"]["paid_call_ledger"]["spent_usd"])
        before_calls = copy.deepcopy(data["ebook_workspace"]["paid_call_ledger"]["calls"])
        before_paid = int(data["ebook_workspace"]["paid_call_ledger"]["paid_calls"])
        before_accepted = copy.deepcopy(data["ebook_workspace"]["accepted_chapters"])
        _f, chapters, _b = split_front_chapters_back(before_content)
        ch3 = next(c for c in chapters if c.order == 3)
        ch3_digest = chapter_acceptance_digest(ch3.order, ch3.title, ch3.body)
        self.assertEqual(chapter_pipeline_stats(data)["accepted_chapter_count"], 2)
        self.assertEqual(chapter_pipeline_stats(data)["resume_from_order"], 3)

        out = reconcile_validated_preserved_chapters(dict(data))
        stats = chapter_pipeline_stats(out)
        self.assertEqual(int(stats["accepted_chapter_count"]), 3)
        self.assertEqual(int(stats["pending_chapter_count"]), 7)
        self.assertEqual(int(stats["resume_from_order"]), 4)
        self.assertEqual(manuscript_digest(out), before_ms)
        self.assertEqual(out["content"], before_content)
        kept = {c["order"]: c["body"] for c in out["ebook_workspace"]["accepted_chapters"]}
        self.assertEqual(kept[1], before_accepted[0]["body"])
        self.assertEqual(kept[2], before_accepted[1]["body"])
        self.assertEqual(kept[3], ch3.body)
        self.assertEqual(
            accepted_chapter_digests(out)[2],
            ch3_digest,
        )
        self.assertEqual(float(out["ebook_workspace"]["paid_call_ledger"]["spent_usd"]), before_spent)
        self.assertEqual(out["ebook_workspace"]["paid_call_ledger"]["calls"], before_calls)
        self.assertEqual(int(out["ebook_workspace"]["paid_call_ledger"]["paid_calls"]), before_paid)

        persisted = reconcile_validated_preserved_chapters_into_project(database, pid)
        stored = dict((persisted.get("data") if isinstance(persisted, dict) else None) or database.get_project(pid)["data"])
        stored["_project_id"] = pid
        self.assertEqual(manuscript_digest(stored), before_ms)
        self.assertEqual(
            [c["order"] for c in stored["ebook_workspace"]["accepted_chapters"]],
            [1, 2, 3],
        )
        self.assertEqual(float(stored["ebook_workspace"]["paid_call_ledger"]["spent_usd"]), 0.6)
        self.assertEqual(stored["ebook_workspace"]["paid_call_ledger"]["calls"], before_calls)

        est = estimate_paid_action(stored, "correct_manuscript")["estimate"]
        self.assertEqual(int(est["accepted_chapter_count"]), 3)
        self.assertEqual(int(est["pending_chapter_count"]), 7)
        self.assertEqual(int(est["resume_from_order"]), 4)
        self.assertEqual(int(est["failed_chapter_order"]), 4)
        self.assertAlmostEqual(float(est["per_chapter_max_usd"]), CHAPTER_UNIT_USD, places=3)
        self.assertAlmostEqual(float(est["max_total_usd"]), 1.05, places=3)
        self.assertAlmostEqual(float(est["spent_usd"]), 0.6, places=3)
        self.assertAlmostEqual(float(est["remaining_usd"]), 1.2, places=3)
        self.assertAlmostEqual(float(est["budget_cap_usd"]), 1.8, places=3)
        self.assertAlmostEqual(float(est["estimate_cost_usd"]), 0.0, places=3)

    def test_mention_only_chapter_is_not_accepted(self):
        from services.ebook_project_workspace import (
            chapter_pipeline_stats,
            reconcile_validated_preserved_chapters,
        )

        _pid, data = self._isolated_ch3_pass_not_accepted(mention_only=True)
        out = reconcile_validated_preserved_chapters(data)
        stats = chapter_pipeline_stats(out)
        self.assertEqual(int(stats["accepted_chapter_count"]), 2)
        self.assertEqual(int(stats["resume_from_order"]), 3)

    def test_correction_after_reconcile_starts_at_chapter_4(self):
        from services.ebook_project_workspace import (
            reconcile_validated_preserved_chapters,
        )

        self._gen_patch.stop()
        _pid, data = self._isolated_ch3_pass_not_accepted()
        data = reconcile_validated_preserved_chapters(data)
        ch3_body = next(
            c["body"] for c in data["ebook_workspace"]["accepted_chapters"] if c["order"] == 3
        )
        seen = []

        def _resume(book, chapter):
            seen.append(chapter.order)
            return {"ebook": f"## {chapter.title}\n\nToo thin to pass.\n"}

        est = estimate_paid_action(data, "correct_manuscript")
        fixed = execute_correct_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="reconcile-start-at-4",
            correct_chapter_fn=_resume,
        )
        self.assertTrue(seen)
        self.assertEqual(seen[0], 4)
        self.assertNotIn(1, seen)
        self.assertNotIn(2, seen)
        self.assertNotIn(3, seen)
        kept = next(
            c["body"]
            for c in fixed["data"]["ebook_workspace"]["accepted_chapters"]
            if c["order"] == 3
        )
        self.assertEqual(kept, ch3_body)

    def test_frozen_2472_is_not_reconciled(self):
        from services.ebook_project_workspace import (
            reconcile_validated_preserved_chapters,
            reconcile_validated_preserved_chapters_into_project,
        )

        live = database.get_project(FROZEN_LIVE_EBOOK_PROJECT_ID)
        data = dict(live["data"])
        data["_project_id"] = FROZEN_LIVE_EBOOK_PROJECT_ID
        before = copy.deepcopy(data.get("ebook_workspace", {}).get("accepted_chapters"))
        out = reconcile_validated_preserved_chapters(data)
        self.assertEqual(out["ebook_workspace"].get("accepted_chapters"), before)
        with self.assertRaises(ValueError):
            reconcile_validated_preserved_chapters_into_project(
                database, FROZEN_LIVE_EBOOK_PROJECT_ID
            )


class PlaceholderLeakLocalSanitizationTests(unittest.TestCase):
    """Leaked production labels are stripped locally at $0 and never billed."""

    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self._client_patch = patch("ai_client.get_client", side_effect=AssertionError("paid client"))
        self._chat_patch = patch("ai_client.chat", side_effect=AssertionError("paid chat"))
        self._json_patch = patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json"))
        self._gen_patch = patch(
            "services.ebook.generate_one_chapter",
            side_effect=AssertionError("provider generate_one_chapter"),
        )
        self._client_patch.start()
        self._chat_patch.start()
        self._json_patch.start()
        self._gen_patch.start()

    def tearDown(self):
        self._client_patch.stop()
        self._chat_patch.stop()
        self._json_patch.stop()
        self._gen_patch.stop()

    def _isolated_ch8_leak(self, *, thin_after_leak: bool = False) -> tuple[int, dict]:
        from services.ebook_manuscript_engine import (
            assemble_manuscript,
            split_front_chapters_back,
        )
        from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript
        from services.ebook_project_workspace import build_acceptance_project_data

        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        data["artifact_id"] = "ebook-ws-ch8-placeholder-leak"
        data["artifact_revision"] = 1
        data["artifact_state"] = "DRAFT"
        strong = build_event_photo_strong_manuscript()
        _front, chapters, _back = split_front_chapters_back(strong)
        ch8 = next(c for c in chapters if c.order == 8)
        if thin_after_leak:
            ch8.body = (
                "Too thin to pass this chapter.\n\n"
                "**PLACEHOLDER: Placeholder/production instruction: key takeaway**\n"
            )
        else:
            ch8.body = (
                "The key takeaway from the comparison is operational. "
                "The DS-RX1HS is positioned for throughput.\n\n"
                + ch8.body
                + "\n\n**PLACEHOLDER: Placeholder/production instruction: key takeaway**\n"
            )
        md = assemble_manuscript(
            title=str(data.get("title") or "From First Booking to On-Site Prints"),
            subtitle=str(data.get("subtitle") or ""),
            author="Lonnie Brown",
            chapters=chapters[:8],
            disclaimer="",
            sources="",
        )
        data["content"] = md
        data["ebook"] = md
        ws = data["ebook_workspace"]
        ws["marker"] = None
        ws["accepted_chapters"] = [
            {"order": c.order, "title": c.title, "body": c.body}
            for c in chapters[:7]
        ]
        ledger = ws["paid_call_ledger"]
        ledger["spent_usd"] = 1.5
        ledger["remaining_usd"] = 0.3
        ledger["budget_cap_usd"] = 1.8
        ledger["paid_calls"] = 10
        ledger["calls"] = [
            {"purpose": "generate_manuscript", "estimated_cost_usd": 1.05},
            {"purpose": "correct_manuscript", "estimated_cost_usd": 0.45},
        ]
        set_stage_status(ws, "manuscript", STATUS_NEEDS_CORRECTION, note="ch8 placeholder leak")
        _recompute_next_action(ws)
        project = database.create_project(
            "Sanitize Ch8 Placeholder Isolated",
            "ebook",
            data,
            user_saved=False,
            system_test=True,
            temporary=True,
        )
        pid = project["id"]
        data["_project_id"] = pid
        database.update_project(pid, None, data)
        return pid, dict(database.get_project(pid)["data"])

    def test_local_sanitization_accepts_ch8_preserves_1_7_and_ledger(self):
        from services.ebook_project_workspace import (
            chapter_pipeline_stats,
            manuscript_digest,
            sanitize_and_reconcile_preserved_chapter_into_project,
        )

        pid, data = self._isolated_ch8_leak()
        data["_project_id"] = pid
        before_ms = manuscript_digest(data)
        before_accepted = copy.deepcopy(data["ebook_workspace"]["accepted_chapters"])
        before_ledger = copy.deepcopy(data["ebook_workspace"]["paid_call_ledger"])
        before_bodies = {int(c["order"]): c["body"] for c in before_accepted}

        updated = sanitize_and_reconcile_preserved_chapter_into_project(database, pid, 8)
        stored = dict(
            (updated.get("data") if isinstance(updated, dict) else None)
            or database.get_project(pid)["data"]
        )
        stored["_project_id"] = pid
        result = stored["ebook_workspace"]["local_chapter_sanitization_result"]
        self.assertTrue(result["passed"])
        self.assertFalse(result["paid_call"])
        self.assertEqual(result["finding_codes"], [])
        self.assertNotEqual(manuscript_digest(stored), before_ms)
        kept = {
            int(c["order"]): c["body"]
            for c in stored["ebook_workspace"]["accepted_chapters"]
        }
        for order in range(1, 8):
            self.assertEqual(kept[order], before_bodies[order])
        self.assertIn(8, kept)
        self.assertNotIn("PLACEHOLDER:", kept[8])
        self.assertNotIn("key takeaway", kept[8].lower())
        self.assertIn("DS-RX1HS is positioned for throughput", kept[8])
        self.assertIn("from the comparison is operational", kept[8])
        ledger = stored["ebook_workspace"]["paid_call_ledger"]
        self.assertEqual(ledger["calls"], before_ledger["calls"])
        self.assertEqual(int(ledger["paid_calls"]), int(before_ledger["paid_calls"]))
        self.assertAlmostEqual(float(ledger["spent_usd"]), 1.5, places=3)
        self.assertAlmostEqual(float(ledger["remaining_usd"]), 0.3, places=3)
        self.assertAlmostEqual(float(ledger["budget_cap_usd"]), 1.8, places=3)
        stats = chapter_pipeline_stats(stored)
        self.assertEqual(int(stats["accepted_chapter_count"]), 8)
        self.assertEqual(int(stats["pending_chapter_count"]), 2)
        self.assertEqual(int(stats["resume_from_order"]), 9)
        est = estimate_paid_action(stored, "correct_manuscript")["estimate"]
        self.assertEqual(int(est["accepted_chapter_count"]), 8)
        self.assertEqual(int(est["pending_chapter_count"]), 2)
        self.assertEqual(int(est["resume_from_order"]), 9)
        self.assertAlmostEqual(float(est["max_total_usd"]), 0.3, places=3)
        self.assertAlmostEqual(float(est["spent_usd"]), 1.5, places=3)
        self.assertAlmostEqual(float(est["remaining_usd"]), 0.3, places=3)
        self.assertAlmostEqual(float(est["budget_cap_usd"]), 1.8, places=3)
        self.assertAlmostEqual(float(est["estimate_cost_usd"]), 0.0, places=3)
        live_after = database.get_project(pid)["data"]
        self.assertEqual(live_after["ebook_workspace"]["paid_call_ledger"]["calls"], before_ledger["calls"])

    def test_substantive_remaining_defect_is_not_accepted(self):
        from services.ebook_project_workspace import (
            chapter_pipeline_stats,
            sanitize_and_reconcile_preserved_chapter_into_project,
            stage_status,
        )

        pid, data = self._isolated_ch8_leak(thin_after_leak=True)
        data["_project_id"] = pid
        before_accepted = [int(c["order"]) for c in data["ebook_workspace"]["accepted_chapters"]]
        before_calls = copy.deepcopy(data["ebook_workspace"]["paid_call_ledger"]["calls"])
        updated = sanitize_and_reconcile_preserved_chapter_into_project(database, pid, 8)
        stored = dict(
            (updated.get("data") if isinstance(updated, dict) else None)
            or database.get_project(pid)["data"]
        )
        stored["_project_id"] = pid
        result = stored["ebook_workspace"]["local_chapter_sanitization_result"]
        self.assertFalse(result["passed"])
        self.assertNotIn("PLACEHOLDER", result["finding_codes"])
        self.assertTrue(result["finding_codes"])
        accepted = [int(c["order"]) for c in stored["ebook_workspace"]["accepted_chapters"]]
        self.assertEqual(accepted, before_accepted)
        self.assertNotIn(8, accepted)
        stats = chapter_pipeline_stats(stored)
        self.assertEqual(int(stats["resume_from_order"]), 8)
        self.assertEqual(stored["ebook_workspace"]["paid_call_ledger"]["calls"], before_calls)
        self.assertEqual(stage_status(stored["ebook_workspace"], "manuscript"), STATUS_NEEDS_CORRECTION)

    def test_frozen_2472_is_not_sanitized(self):
        from services.ebook_project_workspace import (
            sanitize_and_reconcile_preserved_chapter_into_project,
        )

        with self.assertRaises(ValueError):
            sanitize_and_reconcile_preserved_chapter_into_project(
                database, FROZEN_LIVE_EBOOK_PROJECT_ID, 8
            )


if __name__ == "__main__":
    unittest.main()
