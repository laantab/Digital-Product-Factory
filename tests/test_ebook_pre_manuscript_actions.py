"""Run Research / Title Options / Outline Options executors — zero paid calls.

The Ebook Project workspace blocker: a workspace created from the UI sat at
``next_action: "run_research"`` with no way forward, because the estimate
system knew the pre-manuscript actions but nothing executed them. These tests
pin the estimate -> confirm -> execute path for all three pre-manuscript
actions plus the HTTP journey from a fresh workspace to an approved outline,
entirely in FACTORY_TEST_MODE (no provider calls, $0 spent by providers).
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app import app  # noqa: E402
import database  # noqa: E402
from services.ebook_project_workspace import (  # noqa: E402
    approve_stage,
    ensure_workspace,
    estimate_paid_action,
    execute_generate_outline_options,
    execute_generate_title_options,
    execute_run_research,
    get_workspace,
    is_approved,
    new_workspace,
    sync_document_from_workspace,
)
from services.ebook_research_engine import (  # noqa: E402
    RESEARCH_UNIT_USD,
    generate_outline_options,
    generate_title_options,
    run_topic_research,
)


def _fresh_workspace_data(topic: str = "Backyard beekeeping") -> dict:
    data = {
        "product_type": "ebook",
        "ebook_project_workspace": True,
        "artifact_state": "DRAFT",
        "artifact_revision": 1,
        "title": topic,
        "subtitle": "",
        "author_brand": "Test Author",
        "source": topic,
        "content": "",
        "ebook": "",
        "export_ready": False,
        "ebook_workspace": new_workspace(
            topic=topic,
            audience="curious beginners",
            outcome="a healthy first hive",
            author="Test Author",
            budget_cap_usd=3.5,
        ),
    }
    return sync_document_from_workspace(ensure_workspace(data))


def _estimate_and_token(data: dict, action: str) -> dict:
    result = estimate_paid_action(data, action)
    est = result["estimate"]
    assert est["confirmation_token"]
    return est


def _fake_research_fn(**kwargs):
    return {
        "summary": "A solid research summary for the topic.",
        "key_findings": ["Finding one", "Finding two", "Finding three", "Finding four"],
        "notes_sections": {"Audience": "Beginners."},
        "source_urls": ["https://example.com/a"],
        "live_search": True,
        "paid_calls": 2,
    }


class RunResearchExecutorTests(unittest.TestCase):
    def test_fresh_workspace_next_action_is_run_research(self):
        data = _fresh_workspace_data()
        ws = get_workspace(data)
        self.assertEqual(ws["next_action"], "run_research")

    def test_estimate_then_execute_advances_to_awaiting_approval(self):
        data = _fresh_workspace_data()
        est = _estimate_and_token(data, "run_research")
        out = execute_run_research(
            data,
            confirmation_token=est["confirmation_token"],
            expected_artifact_id=est["artifact_id"],
            expected_revision=est["artifact_revision"],
            max_authorized_usd=est["max_authorized_usd"],
            idempotency_key="k1",
            research_fn=_fake_research_fn,
        )
        data = out["data"]
        ws = get_workspace(data)
        self.assertEqual(ws["next_action"], "approve_research")
        self.assertTrue((ws["research_payload"]["summary"] or "").strip())
        ledger = ws["paid_call_ledger"]
        self.assertAlmostEqual(float(ledger["spent_usd"]), RESEARCH_UNIT_USD, places=4)
        self.assertEqual(int(ledger["paid_calls"]), 2)
        self.assertIsNone(ledger["pending_estimate"])

    def test_idempotent_replay_charges_nothing_extra(self):
        data = _fresh_workspace_data()
        est = _estimate_and_token(data, "run_research")
        out = execute_run_research(
            data,
            confirmation_token=est["confirmation_token"],
            expected_artifact_id=est["artifact_id"],
            expected_revision=est["artifact_revision"],
            max_authorized_usd=est["max_authorized_usd"],
            idempotency_key="k2",
            research_fn=_fake_research_fn,
        )
        data = out["data"]
        spent = float(get_workspace(data)["paid_call_ledger"]["spent_usd"])
        replay = execute_run_research(
            data,
            confirmation_token=est["confirmation_token"],
            expected_artifact_id=est["artifact_id"],
            expected_revision=est["artifact_revision"],
            max_authorized_usd=est["max_authorized_usd"],
            idempotency_key="k2",
            research_fn=_fake_research_fn,
        )
        self.assertTrue(replay["duplicate"])
        self.assertAlmostEqual(
            float(get_workspace(replay["data"])["paid_call_ledger"]["spent_usd"]), spent, places=4
        )

    def test_used_token_cannot_run_again_with_new_key(self):
        data = _fresh_workspace_data()
        est = _estimate_and_token(data, "run_research")
        out = execute_run_research(
            data,
            confirmation_token=est["confirmation_token"],
            expected_artifact_id=est["artifact_id"],
            expected_revision=est["artifact_revision"],
            max_authorized_usd=est["max_authorized_usd"],
            idempotency_key="k3",
            research_fn=_fake_research_fn,
        )
        with self.assertRaises(ValueError):
            execute_run_research(
                out["data"],
                confirmation_token=est["confirmation_token"],
                expected_artifact_id=est["artifact_id"],
                expected_revision=est["artifact_revision"],
                max_authorized_usd=est["max_authorized_usd"],
                idempotency_key="k3-different",
                research_fn=_fake_research_fn,
            )

    def test_offline_engine_charges_zero(self):
        # FACTORY_TEST_MODE engine reports zero provider calls -> $0 charged.
        data = _fresh_workspace_data()
        est = _estimate_and_token(data, "run_research")
        out = execute_run_research(
            data,
            confirmation_token=est["confirmation_token"],
            expected_artifact_id=est["artifact_id"],
            expected_revision=est["artifact_revision"],
            max_authorized_usd=est["max_authorized_usd"],
            idempotency_key="k4",
            research_fn=run_topic_research,
        )
        ledger = get_workspace(out["data"])["paid_call_ledger"]
        self.assertAlmostEqual(float(ledger["spent_usd"]), 0.0, places=4)
        self.assertEqual(int(ledger["paid_calls"]), 0)
        self.assertEqual(get_workspace(out["data"])["next_action"], "approve_research")

    def test_estimate_blocked_when_research_awaits_approval(self):
        data = _fresh_workspace_data()
        est = _estimate_and_token(data, "run_research")
        out = execute_run_research(
            data,
            confirmation_token=est["confirmation_token"],
            expected_artifact_id=est["artifact_id"],
            expected_revision=est["artifact_revision"],
            max_authorized_usd=est["max_authorized_usd"],
            idempotency_key="k5",
            research_fn=_fake_research_fn,
        )
        with self.assertRaises(ValueError):
            estimate_paid_action(out["data"], "run_research")


class TitleAndOutlineExecutorTests(unittest.TestCase):
    def _data_with_approved_research(self) -> dict:
        data = _fresh_workspace_data()
        est = _estimate_and_token(data, "run_research")
        data = execute_run_research(
            data,
            confirmation_token=est["confirmation_token"],
            expected_artifact_id=est["artifact_id"],
            expected_revision=est["artifact_revision"],
            max_authorized_usd=est["max_authorized_usd"],
            idempotency_key="seed-research",
            research_fn=run_topic_research,
        )["data"]
        return approve_stage(data, "research")

    def test_title_options_generate_and_approve(self):
        data = self._data_with_approved_research()
        ws = get_workspace(data)
        self.assertEqual(ws["next_action"], "generate_title_options")
        est = _estimate_and_token(data, "generate_title_options")
        data = execute_generate_title_options(
            data,
            confirmation_token=est["confirmation_token"],
            expected_artifact_id=est["artifact_id"],
            expected_revision=est["artifact_revision"],
            max_authorized_usd=est["max_authorized_usd"],
            idempotency_key="t1",
            titles_fn=generate_title_options,
        )["data"]
        ws = get_workspace(data)
        self.assertEqual(ws["next_action"], "approve_title")
        self.assertGreaterEqual(len(ws["title_options"]), 2)
        choice = ws["title_options"][0]["id"]
        data = approve_stage(data, "title", choice_id=choice)
        ws = get_workspace(data)
        self.assertTrue(is_approved(ws, "title"))
        self.assertEqual(ws["next_action"], "generate_outline_options")
        self.assertTrue((data.get("title") or "").strip())

    def test_outline_options_generate_and_approve_unlocks_manuscript(self):
        data = self._data_with_approved_research()
        est = _estimate_and_token(data, "generate_title_options")
        data = execute_generate_title_options(
            data,
            confirmation_token=est["confirmation_token"],
            expected_artifact_id=est["artifact_id"],
            expected_revision=est["artifact_revision"],
            max_authorized_usd=est["max_authorized_usd"],
            idempotency_key="t2",
            titles_fn=generate_title_options,
        )["data"]
        data = approve_stage(data, "title", choice_id=get_workspace(data)["title_options"][0]["id"])
        est = _estimate_and_token(data, "generate_outline_options")
        data = execute_generate_outline_options(
            data,
            confirmation_token=est["confirmation_token"],
            expected_artifact_id=est["artifact_id"],
            expected_revision=est["artifact_revision"],
            max_authorized_usd=est["max_authorized_usd"],
            idempotency_key="o1",
            outlines_fn=generate_outline_options,
        )["data"]
        ws = get_workspace(data)
        self.assertEqual(ws["next_action"], "approve_outline")
        self.assertGreaterEqual(len(ws["outline_options"]), 1)
        data = approve_stage(data, "outline", choice_id=ws["outline_options"][0]["id"])
        ws = get_workspace(data)
        self.assertTrue(is_approved(ws, "outline"))
        self.assertEqual(ws["next_action"], "generate_manuscript")
        self.assertGreaterEqual(len(data.get("outline") or []), 3)
        ledger = ws["paid_call_ledger"]
        self.assertAlmostEqual(float(ledger["spent_usd"]), 0.0, places=4)
        self.assertEqual(int(ledger["paid_calls"]), 0)

    def test_title_generation_requires_approved_research(self):
        data = _fresh_workspace_data()
        with self.assertRaises(ValueError):
            estimate_paid_action(data, "generate_title_options")


class HttpJourneyFromFreshWorkspaceTests(unittest.TestCase):
    """The customer path over real HTTP routes: create -> research -> title ->
    outline, ending with Generate Manuscript unlocked. $0 provider spend."""

    def setUp(self):
        self.client = app.test_client()

    def _post(self, url, payload):
        res = self.client.post(url, json=payload)
        body = res.get_json() or {}
        self.assertEqual(res.status_code, 200, msg=f"{url}: {body}")
        return body

    def test_full_pre_manuscript_journey(self):
        created = self._post(
            "/ebook-workspace",
            {"topic": "Backyard beekeeping", "audience": "curious beginners",
             "outcome": "a healthy first hive", "author": "Test Author"},
        )
        pid = created["project"]["id"]
        self.addCleanup(lambda: database.delete_project(pid))
        ws = created["workspace"]
        self.assertEqual(ws["next_action"], "run_research")

        def confirmed(action, endpoint):
            est = self._post(f"/ebook-workspace/{pid}/estimate-cost", {"action": action})["estimate"]
            return self._post(
                f"/ebook-workspace/{pid}/{endpoint}",
                {
                    "confirmation_token": est["confirmation_token"],
                    "expected_artifact_id": est["artifact_id"],
                    "expected_revision": est["artifact_revision"],
                    "max_authorized_usd": est["max_authorized_usd"],
                    "idempotency_key": f"http-{action}",
                },
            )

        body = confirmed("run_research", "run-research")
        self.assertEqual(body["workspace"]["next_action"], "approve_research")
        body = self._post(f"/ebook-workspace/{pid}/approve", {"stage": "research"})
        self.assertEqual(body["workspace"]["next_action"], "generate_title_options")

        body = confirmed("generate_title_options", "title-options")
        self.assertEqual(body["workspace"]["next_action"], "approve_title")
        choice = body["workspace"]["title_options"][0]["id"]
        body = self._post(f"/ebook-workspace/{pid}/approve", {"stage": "title", "choice_id": choice})
        self.assertEqual(body["workspace"]["next_action"], "generate_outline_options")

        body = confirmed("generate_outline_options", "outline-options")
        self.assertEqual(body["workspace"]["next_action"], "approve_outline")
        choice = body["workspace"]["outline_options"][0]["id"]
        body = self._post(f"/ebook-workspace/{pid}/approve", {"stage": "outline", "choice_id": choice})
        ws = body["workspace"]
        self.assertEqual(ws["next_action"], "generate_manuscript")
        self.assertTrue(ws["gates"]["manuscript_enabled"], msg=str(ws.get("gates")))
        budget = ws.get("budget") or {}
        self.assertAlmostEqual(float(budget.get("spent_usd") or 0), 0.0, places=4)


if __name__ == "__main__":
    unittest.main()
