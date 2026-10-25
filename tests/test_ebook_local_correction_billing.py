"""Offline regression: a local AI correction must not debit the paid-call ledger.

No provider or external service is contacted. The fake chapter function reports
one billable *failed* attempt, then a free local correction. This reproduces
the accounting path through the real orchestrator and manuscript workspace.
"""
from collections import Counter

import pytest

import database
from services import ebook_build_orchestrator as orch
from services import ebook_project_workspace as workspace
from services.ebook_manuscript_engine import chapter_fn_from_full_manuscript
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript


@pytest.mark.parametrize("failed_order", [4, 10])
def test_free_local_correction_does_not_charge_again(monkeypatch, failed_order):
    project = workspace.upsert_acceptance_project(
        database, preserve_live_manuscript=False
    )
    pid = project["id"]
    starting_ledger = database.get_project(pid)["data"]["ebook_workspace"]["paid_call_ledger"]
    starting_spent = float(starting_ledger["spent_usd"])
    starting_remaining = float(starting_ledger["remaining_usd"])
    good = chapter_fn_from_full_manuscript(build_event_photo_strong_manuscript())
    calls = []

    def fake_chapter(book, chapter):
        calls.append(chapter.order)
        if chapter.order == failed_order and calls.count(failed_order) == 1:
            # Simulated provider metadata only; no real paid request.
            return {
                "ebook": f"## {chapter.title}\n\nToo thin.\n",
                "billable_calls": 1,
                "provider": "openai",
            }
        response = dict(good(book, chapter))
        response["billable_calls"] = 0
        response["provider"] = "local"
        return response

    monkeypatch.setattr("services.ebook.generate_one_chapter", fake_chapter)

    for _ in range(20):
        state = orch.advance_build(pid)
        assert state["failed"] is False, state
        if state["percent"] > 30:
            break
    else:
        pytest.fail("bounded manuscript build never reached approval")

    assert state["percent"] == 40
    assert Counter(calls) == {i: (2 if i == failed_order else 1) for i in range(1, 11)}
    saved = database.get_project(pid)["data"]["ebook_workspace"]
    assert workspace.stage_status(saved, "manuscript") == workspace.STATUS_APPROVED
    assert len(saved["accepted_chapters"]) == 10

    ledger = saved["paid_call_ledger"]
    assert float(ledger["spent_usd"]) == pytest.approx(starting_spent + workspace.CHAPTER_UNIT_USD)
    assert float(ledger["remaining_usd"]) == pytest.approx(
        starting_remaining - workspace.CHAPTER_UNIT_USD
    )
    corrections = [
        row for row in ledger["calls"]
        if row.get("purpose") == "correct_manuscript"
    ]
    assert len(corrections) == 1
    assert float(corrections[0]["estimated_cost_usd"]) == 0.0
