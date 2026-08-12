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
    PAID_ACTIONS,
    STATUS_NEEDS_CORRECTION,
    cancel_paid_estimate,
    estimate_paid_action,
    execute_correct_manuscript,
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
            "needs_correction",
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
        # Request Correction click handler estimates only; execute is a later confirm click.
        idx_est = js.index("async function estimateCorrectionInWorkspace")
        idx_confirm = js.index("data-ws-confirm-correct", idx_est)
        first_api = js.index("/estimate-cost", idx_est)
        first_exec = js.index("/correct-manuscript", idx_est)
        self.assertLess(first_api, idx_confirm)
        self.assertGreater(first_exec, idx_confirm)


if __name__ == "__main__":
    unittest.main()
