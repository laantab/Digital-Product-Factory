"""Regression: dual-gated ebook Safe Mode must never call a live provider during repair.

Generation already routes to fixture_one_chapter in Safe Mode. A rejected
chapter triggers the separate correction path, which must use that same
dual-gated fixture routing. This is an offline acceptance test, not evidence
that fixture manuscripts are sellable or that production PDF/ZIP works.
"""
from __future__ import annotations

from collections import Counter

import database

from services import ebook as ebook_service
from services import ebook_build_orchestrator as orchestrator
from services.ebook_manuscript_engine import chapter_fn_from_full_manuscript
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript
from services.ebook_project_workspace import (
    STATUS_APPROVED,
    stage_status,
    upsert_acceptance_project,
)


def test_fixture_mode_correction_never_calls_live_chapter_provider(monkeypatch):
    # Both independent gates are mandatory; do not alter production defaults.
    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    monkeypatch.setenv("EBOOK_CUSTOMER_PATH_FIXTURE", "1")

    project = upsert_acceptance_project(database, preserve_live_manuscript=False)
    pid = project["id"]
    valid_chapter = chapter_fn_from_full_manuscript(
        build_event_photo_strong_manuscript()
    )
    calls = []

    def fixture_chapter(book, chapter):
        calls.append(chapter.order)
        if chapter.order == 10 and calls.count(10) == 1:
            return {"ebook": f"## {chapter.title}\n\nToo thin.\n"}
        return valid_chapter(book, chapter)

    def forbidden_live_provider(*_args, **_kwargs):
        raise AssertionError(
            "Safe Mode correction attempted the live chapter provider"
        )

    monkeypatch.setattr(ebook_service, "fixture_one_chapter", fixture_chapter)
    monkeypatch.setattr(ebook_service, "generate_one_chapter", forbidden_live_provider)

    status = {}
    for _ in range(20):
        status = orchestrator.advance_build(pid)
        if status.get("failed") or status.get("percent", 0) > 30:
            break

    assert status.get("failed") is False, status
    assert status["percent"] == 40, status
    counts = Counter(calls)
    assert counts == {**{order: 1 for order in range(1, 10)}, 10: 2}
    saved = database.get_project(pid)["data"]
    ws = saved["ebook_workspace"]
    assert stage_status(ws, "manuscript") == STATUS_APPROVED
    assert len(ws["accepted_chapters"]) == 10
    assert float(ws["paid_call_ledger"]["spent_usd"]) == 0.0
