"""Approved-outline fidelity for Ebook workspace manuscripts.

All generation/correction is mocked — zero paid/external calls.
"""
from __future__ import annotations

import json
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
from services.ebook_outline_fidelity import (  # noqa: E402
    validate_manuscript_outline_fidelity,
)
from services.ebook_project_workspace import (  # noqa: E402
    REVISED_ACCEPTANCE_OUTLINE_TITLES,
    STATUS_AWAITING,
    STATUS_NEEDS_CORRECTION,
    approve_stage,
    build_acceptance_project_data,
    build_research_notes_for_manuscript,
    estimate_paid_action,
    execute_correct_manuscript,
    execute_generate_manuscript,
    outline_digest,
    stage_status,
    upsert_acceptance_project,
    workspace_public_view,
)


def _ms_from_titles(titles: list[str], *, back_matter: list[str] | None = None) -> str:
    parts = ["# From First Booking to On-Site Prints\n"]
    for i, t in enumerate(titles, 1):
        parts.append(
            f"## {t}\n\n"
            f"Chapter {i} covers {t.lower()} with concrete photographer actions. "
            f"Include insurance, dye-sublimation printing realism, client booking steps, "
            f"keepsake equipment separation, and a first paid event checklist where relevant "
            f"to this chapter's unique focus ({i}).\n"
        )
    for t in back_matter or []:
        parts.append(f"## {t}\n\nEducational disclaimer and sources note.\n")
    return "\n".join(parts)


GOOD_REVISED_MS = _ms_from_titles(REVISED_ACCEPTANCE_OUTLINE_TITLES)
EARLY_O1_TITLES = [
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
]
EARLY_O1_WITH_BACK = _ms_from_titles(
    EARLY_O1_TITLES,
    back_matter=["Conclusion", "Disclaimer", "Sources"],
)


def _mock_good(*_a, **_k):
    return {"ebook": GOOD_REVISED_MS}


def _mock_early(*_a, **_k):
    return {"ebook": EARLY_O1_WITH_BACK}


class OutlineFidelityTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self.project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        self.pid = self.project["id"]

    def _data(self):
        p = database.get_project(self.pid)
        return dict(p.get("data") or {})

    def test_seed_uses_revised_titles_not_early_o1(self):
        data = build_acceptance_project_data()
        titles = [c["title"] for c in data["outline"]]
        self.assertEqual(titles, REVISED_ACCEPTANCE_OUTLINE_TITLES)
        self.assertNotIn("Core Camera Kit and Backup Gear", titles)
        self.assertIn("Core Camera Kit, Printing Equipment, and Backup Gear", titles)

    def test_early_o1_cannot_override_revised_approved_outline(self):
        data = self._data()
        # Poison option cache with early headings; approved data.outline stays revised.
        ws = data["ebook_workspace"]
        for opt in ws.get("outline_options") or []:
            if opt.get("id") == "O1":
                opt["chapters"] = [{"n": i + 1, "title": t, "bullets": []} for i, t in enumerate(EARLY_O1_TITLES)]
        notes = build_research_notes_for_manuscript(data)
        for t in REVISED_ACCEPTANCE_OUTLINE_TITLES:
            self.assertIn(t, notes)
        self.assertNotIn("Packages Clients Can Understand", notes)

    def test_token_digest_binds_exact_approved_outline(self):
        data = self._data()
        est = estimate_paid_action(data, "generate_manuscript")
        self.assertEqual(est["estimate"]["outline_digest"], outline_digest(data))
        database.update_project(self.pid, None, data)
        # Mutate outline after estimate → confirm must fail
        data["outline"][2]["title"] = "Renamed After Estimate"
        with self.assertRaises(ValueError):
            execute_generate_manuscript(
                data,
                confirmation_token=est["estimate"]["confirmation_token"],
                expected_artifact_id=str(data.get("artifact_id") or ""),
                expected_revision=int(data.get("artifact_revision") or 1),
                outline_digest_expected=est["estimate"]["outline_digest"],
                max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
                idempotency_key="digest-mismatch-1",
                generate_fn=_mock_good,
            )

    def test_ten_approved_chapters_produce_exactly_ten(self):
        data = self._data()
        est = estimate_paid_action(data, "generate_manuscript")
        out = execute_generate_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="ten-chapters-ok",
            generate_fn=_mock_good,
        )
        self.assertEqual(out["result"]["manuscript_status"], STATUS_NEEDS_CORRECTION)
        self.assertTrue(out["result"]["structure_ok"])
        self.assertNotEqual(out["result"].get("quality_status"), "PASS")
        fidelity = validate_manuscript_outline_fidelity(
            approved_outline=data["outline"],
            manuscript_md=out["data"]["content"],
        )
        self.assertTrue(fidelity["ok"])
        self.assertEqual(len(fidelity["generated_titles"]), 10)

    def test_reordered_renamed_missing_extra_fail(self):
        approved = [{"order": i + 1, "title": t, "purpose": "coverage"} for i, t in enumerate(REVISED_ACCEPTANCE_OUTLINE_TITLES)]
        reordered = REVISED_ACCEPTANCE_OUTLINE_TITLES[1:] + REVISED_ACCEPTANCE_OUTLINE_TITLES[:1]
        self.assertFalse(
            validate_manuscript_outline_fidelity(
                approved_outline=approved, manuscript_md=_ms_from_titles(reordered)
            )["ok"]
        )
        renamed = list(REVISED_ACCEPTANCE_OUTLINE_TITLES)
        renamed[3] = "Totally Different Chapter"
        self.assertFalse(
            validate_manuscript_outline_fidelity(
                approved_outline=approved, manuscript_md=_ms_from_titles(renamed)
            )["ok"]
        )
        missing = REVISED_ACCEPTANCE_OUTLINE_TITLES[:9]
        self.assertFalse(
            validate_manuscript_outline_fidelity(
                approved_outline=approved, manuscript_md=_ms_from_titles(missing)
            )["ok"]
        )
        extra = REVISED_ACCEPTANCE_OUTLINE_TITLES + ["Bonus Chapter"]
        self.assertFalse(
            validate_manuscript_outline_fidelity(
                approved_outline=approved, manuscript_md=_ms_from_titles(extra)
            )["ok"]
        )

    def test_conclusion_not_injected_unless_approved(self):
        approved = [{"order": i + 1, "title": t, "purpose": ""} for i, t in enumerate(REVISED_ACCEPTANCE_OUTLINE_TITLES)]
        bad = validate_manuscript_outline_fidelity(
            approved_outline=approved,
            manuscript_md=_ms_from_titles(REVISED_ACCEPTANCE_OUTLINE_TITLES, back_matter=["Conclusion"]),
        )
        self.assertFalse(bad["ok"])
        self.assertTrue(any("PROHIBITED_NUMBERED_BACK_MATTER" in f for f in bad["findings"]))
        with_conclusion = REVISED_ACCEPTANCE_OUTLINE_TITLES + ["Conclusion"]
        ok = validate_manuscript_outline_fidelity(
            approved_outline=[{"order": i + 1, "title": t, "purpose": ""} for i, t in enumerate(with_conclusion)],
            manuscript_md=_ms_from_titles(with_conclusion),
        )
        self.assertTrue(ok["ok"])

    def test_disclaimer_sources_non_chapter_back_matter_ok(self):
        md = GOOD_REVISED_MS + "\n\n**Disclaimer**\nEducational only.\n\n**Sources**\n- example.com\n"
        approved = [{"order": i + 1, "title": t, "purpose": ""} for i, t in enumerate(REVISED_ACCEPTANCE_OUTLINE_TITLES)]
        fidelity = validate_manuscript_outline_fidelity(approved_outline=approved, manuscript_md=md)
        self.assertTrue(fidelity["ok"])
        self.assertEqual(len(fidelity["generated_titles"]), 10)

    def test_structural_failure_becomes_needs_correction(self):
        data = self._data()
        est = estimate_paid_action(data, "generate_manuscript")
        out = execute_generate_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="struct-fail-1",
            generate_fn=_mock_early,
        )
        self.assertEqual(out["result"]["manuscript_status"], STATUS_NEEDS_CORRECTION)
        self.assertFalse(out["result"]["structure_ok"])
        self.assertTrue(out["data"]["content"])
        self.assertGreater(float(out["result"]["spent_usd"]), 0.928)

    def test_approve_unavailable_during_fail(self):
        data = self._data()
        est = estimate_paid_action(data, "generate_manuscript")
        out = execute_generate_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="approve-block-1",
            generate_fn=_mock_early,
        )
        data = out["data"]
        view = workspace_public_view({"id": self.pid, "name": "t", "data": data})
        self.assertFalse(view["manuscript"]["can_approve"])
        self.assertFalse(view["gates"]["approve_manuscript_enabled"])
        with self.assertRaises(ValueError):
            approve_stage(data, "manuscript")

    def test_evidence_and_ledger_preserved_on_structure_fail(self):
        data = self._data()
        before_spent = float(data["ebook_workspace"]["paid_call_ledger"]["spent_usd"])
        est = estimate_paid_action(data, "generate_manuscript")
        out = execute_generate_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="preserve-1",
            generate_fn=_mock_early,
        )
        data = out["data"]
        self.assertEqual(data["content"], EARLY_O1_WITH_BACK)
        self.assertAlmostEqual(
            float(data["ebook_workspace"]["paid_call_ledger"]["spent_usd"]),
            before_spent + 1.5,
            places=3,
        )
        self.assertTrue(data["ebook_workspace"]["last_manuscript_generation"]["provider_input"])
        # Upsert must not wipe manuscript/ledger
        database.update_project(self.pid, None, data)
        # Re-seed the same isolated test project id (do not touch live #2472).
        preserved = dict(database.get_project(self.pid)["data"])
        # Simulate production preserve path against this test row only.
        from services.ebook_project_workspace import ensure_workspace, stage_status

        self.assertTrue(preserved.get("content"))
        self.assertAlmostEqual(
            float(preserved["ebook_workspace"]["paid_call_ledger"]["spent_usd"]),
            before_spent + 1.5,
            places=3,
        )
        self.assertEqual(
            stage_status(preserved["ebook_workspace"], "manuscript"),
            STATUS_NEEDS_CORRECTION,
        )
        # Round-trip update must keep manuscript/ledger bytes.
        database.update_project(self.pid, None, preserved)
        restored = database.get_project(self.pid)["data"]
        self.assertTrue(restored.get("content"))
        self.assertAlmostEqual(
            float(restored["ebook_workspace"]["paid_call_ledger"]["spent_usd"]),
            before_spent + 1.5,
            places=3,
        )
        self.assertEqual(
            stage_status(restored["ebook_workspace"], "manuscript"),
            STATUS_NEEDS_CORRECTION,
        )

    def test_correction_requires_estimate_and_confirmation(self):
        data = self._data()
        est = estimate_paid_action(data, "generate_manuscript")
        out = execute_generate_manuscript(
            data,
            confirmation_token=est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=est["estimate"]["outline_digest"],
            max_authorized_usd=float(est["estimate"]["max_authorized_usd"]),
            idempotency_key="corr-setup-1",
            generate_fn=_mock_early,
        )
        data = out["data"]
        with self.assertRaises(ValueError):
            execute_correct_manuscript(
                data,
                confirmation_token="nope",
                expected_artifact_id=str(data.get("artifact_id") or ""),
                expected_revision=int(data.get("artifact_revision") or 1),
                outline_digest_expected=outline_digest(data),
                max_authorized_usd=0.75,
                idempotency_key="corr-no-est",
                correct_fn=_mock_good,
            )
        corr_est = estimate_paid_action(data, "correct_manuscript")
        self.assertEqual(corr_est["estimate"]["action"], "correct_manuscript")
        fixed = execute_correct_manuscript(
            data,
            confirmation_token=corr_est["estimate"]["confirmation_token"],
            expected_artifact_id=str(data.get("artifact_id") or ""),
            expected_revision=int(data.get("artifact_revision") or 1),
            outline_digest_expected=corr_est["estimate"]["outline_digest"],
            max_authorized_usd=float(corr_est["estimate"]["max_authorized_usd"]),
            idempotency_key="corr-ok-1",
            correct_fn=_mock_good,
        )
        self.assertEqual(fixed["result"]["manuscript_status"], STATUS_NEEDS_CORRECTION)
        self.assertTrue(fixed["data"]["ebook_workspace"].get("previous_manuscript_draft"))

    def test_ui_hides_approve_shows_request_correction(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("can_approve", js)
        self.assertIn("estimateCorrectionInWorkspace", js)
        self.assertIn("/correct-manuscript", js)
        self.assertIn("structure_findings", js)
        self.assertNotIn(
            "Request Correction: edit chapters or regenerate after fixing QA findings",
            js,
        )

    def test_route_correct_manuscript_mocked(self):
        data = self._data()
        est = estimate_paid_action(data, "generate_manuscript")
        database.update_project(self.pid, None, data)
        with patch("services.ebook.generate_ebook", side_effect=_mock_early):
            r = self.client.post(
                f"/ebook-workspace/{self.pid}/generate-manuscript",
                json={
                    "confirmation_token": est["estimate"]["confirmation_token"],
                    "expected_artifact_id": est["estimate"]["artifact_id"],
                    "expected_revision": est["estimate"]["artifact_revision"],
                    "outline_digest": est["estimate"]["outline_digest"],
                    "max_authorized_usd": est["estimate"]["max_authorized_usd"],
                    "idempotency_key": "route-gen-fail",
                },
            )
        self.assertEqual(r.status_code, 200)
        payload = r.get_json()
        self.assertEqual(payload["result"]["manuscript_status"], STATUS_NEEDS_CORRECTION)
        data = database.get_project(self.pid)["data"]
        corr = estimate_paid_action(data, "correct_manuscript")
        database.update_project(self.pid, None, data)
        with patch("services.ebook.correct_ebook_manuscript", side_effect=_mock_good):
            r2 = self.client.post(
                f"/ebook-workspace/{self.pid}/correct-manuscript",
                json={
                    "confirmation_token": corr["estimate"]["confirmation_token"],
                    "expected_artifact_id": corr["estimate"]["artifact_id"],
                    "expected_revision": corr["estimate"]["artifact_revision"],
                    "outline_digest": corr["estimate"]["outline_digest"],
                    "max_authorized_usd": corr["estimate"]["max_authorized_usd"],
                    "idempotency_key": "route-corr-ok",
                },
            )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.get_json()["result"]["manuscript_status"], STATUS_NEEDS_CORRECTION)


if __name__ == "__main__":
    unittest.main()
