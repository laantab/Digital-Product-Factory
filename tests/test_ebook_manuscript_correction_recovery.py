"""The live build passed the provider-routing fix, then stalled a new way.

ROOT CAUSE THIS GUARDS
-----------------------
Live traceback, "Container Gardening Step by Step":

    Attempt 1: stage=manuscript failed: Resolve structural/content findings
               before approving the manuscript.
    Attempt 2: stage=manuscript failed: Cannot approve an empty manuscript.

Read-only trace confirmed two real, separate defects in
services/ebook_build_orchestrator.py:

1. _run_manuscript() generated a manuscript, found real structural/content
   findings, and immediately called approve_stage() -- which is GUARANTEED
   to raise whenever the stage is STATUS_NEEDS_CORRECTION (see
   services/ebook_project_workspace.py::approve_stage). The Factory already
   has a full, working correction system (execute_correct_manuscript, the
   same one a human triggers via "Request Correction") that _run_manuscript
   never called. This is attempt 1's exact error.

2. advance_build()'s except-block persisted the STALE, pre-attempt `data`
   snapshot captured before the runner ran -- not the runner's own state at
   the point of failure. execute_generate_manuscript() had already
   persisted real progress incrementally via its persist_progress callback
   (each chapter, as it passed validation) before approve_stage() raised;
   the except-block's write then overwrote the database with the OLDER,
   pre-attempt snapshot, silently discarding all of it. The next attempt
   started from scratch: every chapter regenerated (a real duplicate-billing
   defect), and -- because generation is not perfectly deterministic --
   this specific run produced no chapters that passed at all, giving
   attempt 2 its "empty manuscript" error. Both attempts' distinct messages
   come from this ONE underlying defect, not two separate bugs in approval
   logic.

THE FIX
-------
_run_manuscript() now runs the existing correction pass automatically, once,
when generation leaves the manuscript needing correction -- before ever
calling approve_stage(). advance_build()'s except-block now re-reads the
database's current state before recording a failure, so it can only ADD the
failure record; it can no longer silently subtract progress the runner
already saved during the same attempt. execute_correct_manuscript() gained
the same persist_progress support execute_generate_manuscript() already had,
so a correction interrupted partway through cannot lose repaired chapters
either.

A LATER, DEEPER ROOT CAUSE (same live incident, next layer down)
------------------------------------------------------------------
Even with the fixes above, a real production build later showed the actual
web worker dying mid-manuscript: Render/Gunicorn logs showed a worker
blocked in a network read, then killed by the timeout handler
(gunicorn/workers/base.py::handle_abort -> sys.exit(1) -> "Worker exiting"),
because execute_generate_manuscript() wrote an ENTIRE manuscript -- every
chapter -- inside one synchronous HTTP request. A real multi-chapter book
can take minutes; a web server's request timeout does not know or care that
the work is legitimate.

THE FIX (this layer)
---------------------
services/ebook_build_orchestrator.py::MANUSCRIPT_CHAPTERS_PER_ADVANCE bounds
generation and correction to one chapter per /advance call via the new
max_chapters_per_call parameter on execute_generate_manuscript and
execute_correct_manuscript. When that bound stops chapter writing with
nothing having actually failed, the manuscript stage is reported IN_PROGRESS
(not a failure) and the existing checkpoint/resume loop -- unchanged --
continues it on the next call. Because a real book now legitimately needs
many /advance calls to finish this way, the manuscript stage alone got a
much higher attempt ceiling (_max_attempts); every other stage's ceiling is
unchanged.

No external/paid call is made by any test here.
"""
from __future__ import annotations

from collections import Counter

import pytest

import database
from services import ebook_build_orchestrator as orch
import services.ebook_project_workspace as workspace
from services.ebook_manuscript_engine import (
    EXAMPLE_BUY_VS_RENT_VS_USED,  # noqa: F401 -- confirms manuscript_engine importable here
    chapter_fn_from_full_manuscript,
)
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript
from services.ebook_project_workspace import upsert_acceptance_project


# ============================================================ real engine ===
# Uses the Factory's own acceptance-project fixture (10 real, approved
# chapters) and the real generate -> correct -> approve pipeline. Only the
# chapter-writing function itself is replaced, exactly the way every other
# manuscript test in this suite avoids a real paid call.


def test_orchestrator_auto_corrects_and_advances_past_manuscript(monkeypatch):
    """The end-to-end proof: bounded, repeated /advance calls carry 30% -> 40%.

    services/ebook_build_orchestrator.py::MANUSCRIPT_CHAPTERS_PER_ADVANCE
    bounds each call to one chapter (or one repair), so a real 10-chapter
    book needs multiple /advance calls to finish -- exactly the contract a
    production web server's request timeout requires: no single HTTP
    request writes an entire manuscript.
    """
    project = upsert_acceptance_project(database, preserve_live_manuscript=False)
    pid = project["id"]

    good_fn = chapter_fn_from_full_manuscript(build_event_photo_strong_manuscript())
    call_log: list[int] = []
    chapter_ten_calls = {"n": 0}

    def _fake_chapter(book, chapter):
        call_log.append(chapter.order)
        if chapter.order == 10:
            chapter_ten_calls["n"] += 1
            if chapter_ten_calls["n"] == 1:
                # The one legitimate structural/content failure.
                return {"ebook": f"## {chapter.title}\n\nToo thin.\n"}
        return good_fn(book, chapter)

    monkeypatch.setattr("services.ebook.generate_one_chapter", _fake_chapter)

    percents: list[int] = []
    status = {"failed": False, "finished": False, "percent": 30}
    for _ in range(20):  # generous safety cap: 10 chapters + one repair + margin
        status = orch.advance_build(pid)
        assert status["failed"] is False, status
        percents.append(status["percent"])
        if status["percent"] > 30:
            break

    assert len(percents) > 1, (
        "a real book must take more than one /advance call -- if this is 1, "
        "the whole manuscript is still being written inside a single request"
    )
    # Progress cannot fall from 30% back to 0% (or below 30% at all) merely
    # because one bounded request ends -- every intermediate call must
    # report at least what was already reached.
    assert all(p >= 30 for p in percents), percents
    assert percents[-1] == 40, "research/title/outline/manuscript = 4 of 10 stages"
    assert all(p == 30 for p in percents[:-1]), (
        "manuscript stays at 30% while chapters are still being written, "
        "then advances to 40% only once it is actually approved"
    )

    counts = Counter(call_log)
    # Already-good chapters (1-9) are never regenerated: exactly one call each.
    for order in range(1, 10):
        assert counts[order] == 1, f"chapter {order} was called {counts[order]} times, expected 1"
    # Only the one chapter that actually failed is repaired: bad, then good.
    assert counts[10] == 2, f"chapter 10 was called {counts[10]} times, expected 2 (fail, then repair)"

    row = database.get_project(pid)
    ws = row["data"]["ebook_workspace"]
    assert workspace.stage_status(ws, "manuscript") == workspace.STATUS_APPROVED
    assert len(ws.get("accepted_chapters") or []) == 10
    assert not ws.get("manuscript_qa")
    assert not ws.get("manuscript_structure_findings")


def test_slow_chapter_generation_never_blocks_one_advance_call_for_the_whole_book(monkeypatch):
    """The exact production symptom, reproduced with real timing.

    A web server's request timeout does not know a slow manuscript is
    legitimate -- it only measures how long ONE request took. This gives
    every chapter a real, measurable delay and proves no single
    advance_build() call ever waits for more than about one chapter's
    worth of that delay, no matter how many chapters remain.
    """
    import time

    project = upsert_acceptance_project(database, preserve_live_manuscript=False)
    pid = project["id"]

    good_fn = chapter_fn_from_full_manuscript(build_event_photo_strong_manuscript())
    per_chapter_delay = 0.15
    call_log: list[int] = []

    def _slow_chapter(book, chapter):
        time.sleep(per_chapter_delay)
        call_log.append(chapter.order)
        return good_fn(book, chapter)

    monkeypatch.setattr("services.ebook.generate_one_chapter", _slow_chapter)

    call_durations: list[float] = []
    accepted_counts: list[int] = []
    status = {"percent": 30}
    for _ in range(20):
        started = time.perf_counter()
        status = orch.advance_build(pid)
        call_durations.append(time.perf_counter() - started)
        assert status["failed"] is False, status
        row = database.get_project(pid)
        accepted_counts.append(len(row["data"]["ebook_workspace"].get("accepted_chapters") or []))
        if status["percent"] > 30:
            break

    # A single unbounded call would need ~10 * per_chapter_delay seconds for
    # a fresh book; a bounded call needs about one chapter's worth, however
    # many chapters remain. This margin comfortably separates the two.
    unbounded_threshold = 4 * per_chapter_delay
    for i, duration in enumerate(call_durations):
        assert duration < unbounded_threshold, (
            f"advance_build call {i + 1} took {duration:.3f}s -- a single call "
            f"must not wait for more than roughly one chapter's generation time"
        )

    # Persisted checkpoints between advances: the accepted count only ever
    # goes up, one chapter at a time, and survives between separate calls.
    assert accepted_counts == sorted(accepted_counts)
    assert accepted_counts[-1] == 10
    for prev, nxt in zip(accepted_counts, accepted_counts[1:]):
        assert nxt - prev <= 1, "no single call may accept more than one new chapter"

    # No accepted chapter is regenerated; no duplicate paid calls.
    counts = Counter(call_log)
    assert counts == {order: 1 for order in range(1, 11)}, counts

    assert status["percent"] == 40


# ==================================================== orchestrator wiring ===
# Fakes execute_generate_manuscript / execute_correct_manuscript / approve_stage
# directly, to pin exact call sequencing and exception-handling behaviour
# without depending on the real validators' specific thresholds.


def _project_data():
    data = workspace.ensure_workspace({
        "product_type": "ebook", "title": "Container Gardening Step by Step",
        "artifact_state": "DRAFT",
    })
    ws = data["ebook_workspace"]
    for stage in ("research", "title", "outline"):
        workspace.set_stage_status(ws, stage, workspace.STATUS_APPROVED)
    data["ebook_workspace"] = ws
    return data


def _make(name, data):
    return database.create_project(name, "ebook", data, user_saved=True, system_test=False, temporary=False)


@pytest.fixture()
def _bypass_estimate_machinery(monkeypatch):
    """These tests are about orchestration sequencing, not the cost-estimate flow.

    tests/test_ebook_chapter_production.py and tests/test_ebook_correction_estimate.py
    already cover the real estimate/confirmation machinery in full. NOT autouse:
    the real-engine test above needs the genuine estimate/confirmation flow to
    exercise execute_generate_manuscript/execute_correct_manuscript unfaked.
    """
    def _fake_authorized(data, action):
        return data, {"outline_digest": "digest-x", "max_total_usd": 5.0}

    monkeypatch.setattr(orch, "_authorized", _fake_authorized)


def _fake_generate_needs_correction(calls, accepted_before_failure):
    def _fn(data, *, persist_progress=None, **kwargs):
        calls.append("generate")
        ws = data["ebook_workspace"]
        for i in range(1, len(accepted_before_failure) + 1):
            ws["accepted_chapters"] = list(accepted_before_failure[:i])
            if persist_progress is not None:
                persist_progress(data)
        data["content"] = "\n\n".join(c["body"] for c in accepted_before_failure)
        data["ebook"] = data["content"]
        ws["manuscript_qa"] = []
        ws["manuscript_structure_findings"] = ["Chapter 2 is missing a required section"]
        workspace.set_stage_status(ws, "manuscript", workspace.STATUS_NEEDS_CORRECTION,
                                   note="needs correction")
        data["ebook_workspace"] = ws
        return {"ok": True, "duplicate": False, "data": data, "result": {}}
    return _fn


def _fake_correct_clean(calls, repaired_body):
    def _fn(data, *, persist_progress=None, **kwargs):
        calls.append("correct")
        ws = data["ebook_workspace"]
        accepted = list(ws.get("accepted_chapters") or [])
        for c in accepted:
            if c["order"] == 2:
                c["body"] = repaired_body
        ws["accepted_chapters"] = accepted
        if persist_progress is not None:
            persist_progress(data)
        data["content"] = "\n\n".join(c["body"] for c in accepted)
        data["ebook"] = data["content"]
        ws["manuscript_qa"] = []
        ws["manuscript_structure_findings"] = []
        workspace.set_stage_status(ws, "manuscript", workspace.STATUS_AWAITING,
                                   note="Awaiting human approval")
        data["ebook_workspace"] = ws
        return {"ok": True, "duplicate": False, "data": data, "result": {}}
    return _fn


def _fake_correct_still_broken(calls):
    def _fn(data, *, persist_progress=None, **kwargs):
        calls.append("correct")
        raise ValueError("No remaining budget for manuscript correction.")
    return _fn


def _real_shaped_approve_stage(calls):
    """Reproduces approve_stage's real manuscript-branch decision logic
    (empty check, then needs-correction check, then approve) without the
    real fidelity/quality re-validation -- that behaviour is covered by
    tests/test_ebook_outline_fidelity.py and tests/test_ebook_manuscript_quality.py.
    """
    def _fn(data, stage, **kwargs):
        calls.append(f"approve:{stage}")
        if stage != "manuscript":
            raise AssertionError(f"unexpected stage in this test: {stage}")
        ws = data["ebook_workspace"]
        md = str(data.get("content") or data.get("ebook") or "").strip()
        if not md:
            raise ValueError("Cannot approve an empty manuscript.")
        if workspace.stage_status(ws, "manuscript") == workspace.STATUS_NEEDS_CORRECTION:
            raise ValueError("Resolve structural/content findings before approving the manuscript.")
        workspace.set_stage_status(ws, "manuscript", workspace.STATUS_APPROVED)
        data["ebook_workspace"] = ws
        return data
    return _fn


def test_findings_trigger_the_existing_correction_path_and_reviews_the_result(
    monkeypatch, _bypass_estimate_machinery,
):
    """Items: legitimate findings trigger correction; corrected manuscript is re-reviewed."""
    calls: list[str] = []
    accepted = [
        {"order": 1, "title": "Chapter 1", "body": "Chapter one, a complete real body."},
        {"order": 2, "title": "Chapter 2", "body": "Chapter two, missing its required section."},
    ]
    monkeypatch.setattr(workspace, "execute_generate_manuscript",
                        _fake_generate_needs_correction(calls, accepted))
    monkeypatch.setattr(workspace, "execute_correct_manuscript",
                        _fake_correct_clean(calls, "Chapter two, now repaired and complete."))
    monkeypatch.setattr(workspace, "approve_stage", _real_shaped_approve_stage(calls))

    project = _make("Recovery Test Book", _project_data())
    status = orch.advance_build(project["id"])

    assert calls == ["generate", "correct", "approve:manuscript"], (
        "correction must run automatically, and the result must be reviewed by "
        "approve_stage before the build is allowed to advance"
    )
    assert status["failed"] is False
    assert status["percent"] == 40


def test_qa_rejection_does_not_erase_already_persisted_manuscript_content(
    monkeypatch, _bypass_estimate_machinery,
):
    """Items: valid content with findings is preserved; QA rejection does not erase it."""
    calls: list[str] = []
    accepted = [
        {"order": 1, "title": "Chapter 1", "body": "Chapter one, a complete real body."},
        {"order": 2, "title": "Chapter 2", "body": "Chapter two, missing its required section."},
    ]
    monkeypatch.setattr(workspace, "execute_generate_manuscript",
                        _fake_generate_needs_correction(calls, accepted))
    # Correction itself cannot succeed this time (e.g. budget exhausted) --
    # the failure must still preserve what generation already saved.
    monkeypatch.setattr(workspace, "execute_correct_manuscript", _fake_correct_still_broken(calls))

    project = _make("Preservation Test Book", _project_data())
    pid = project["id"]
    status = orch.advance_build(pid)

    assert status["failed"] is False, "one failed attempt, below the ceiling, must not be final"
    assert status["retrying"] is True

    row = database.get_project(pid)
    ws = row["data"]["ebook_workspace"]
    saved_chapters = ws.get("accepted_chapters") or []
    assert [c["order"] for c in saved_chapters] == [1, 2], (
        "the two chapters generation already persisted must survive a later "
        "failure in the same attempt, not be wiped back to nothing"
    )
    assert row["data"].get("content"), "the assembled draft generation produced must also survive"


def test_correction_reconstructs_the_complete_manuscript_from_persisted_chapters(
    monkeypatch, _bypass_estimate_machinery,
):
    """The retry path a fixed advance_build actually takes: straight to correction.

    Once generation has already left the stage NEEDS_CORRECTION with a
    preserved draft, the *next* attempt must go straight to the correction
    path (matching services.ebook_project_workspace.execute_generate_manuscript's
    own guard: it refuses to regenerate over an existing NEEDS_CORRECTION
    draft). This proves _run_manuscript reaches that same correction call on
    a resumed attempt without needing generation to run again at all.
    """
    calls: list[str] = []
    accepted = [
        {"order": 1, "title": "Chapter 1", "body": "Chapter one, a complete real body."},
        {"order": 2, "title": "Chapter 2", "body": "Chapter two, missing its required section."},
    ]
    data = _project_data()
    ws = data["ebook_workspace"]
    ws["accepted_chapters"] = accepted
    data["content"] = "\n\n".join(c["body"] for c in accepted)
    data["ebook"] = data["content"]
    ws["manuscript_qa"] = []
    ws["manuscript_structure_findings"] = ["Chapter 2 is missing a required section"]
    workspace.set_stage_status(ws, "manuscript", workspace.STATUS_NEEDS_CORRECTION,
                               note="needs correction")
    data["ebook_workspace"] = ws
    project = _make("Resumed Correction Book", data)

    def _generate_must_not_be_called(*_a, **_k):
        raise AssertionError("generation must not run again once a corrected draft is preserved")

    monkeypatch.setattr(workspace, "execute_generate_manuscript", _generate_must_not_be_called)
    monkeypatch.setattr(workspace, "execute_correct_manuscript",
                        _fake_correct_clean(calls, "Chapter two, now repaired and complete."))
    monkeypatch.setattr(workspace, "approve_stage", _real_shaped_approve_stage(calls))

    status = orch.advance_build(project["id"])

    assert calls == ["correct", "approve:manuscript"]
    assert status["failed"] is False
    assert status["percent"] == 40


def test_an_actually_empty_manuscript_still_fails_clearly(
    monkeypatch, _bypass_estimate_machinery,
):
    """Item: an actually empty manuscript still fails clearly (not silently)."""
    calls: list[str] = []

    def _fake_generate_empty(data, *, persist_progress=None, **kwargs):
        calls.append("generate")
        ws = data["ebook_workspace"]
        # A genuine empty result: no chapters, no content, no correction needed
        # because there is nothing to correct -- generation itself failed clean.
        workspace.set_stage_status(ws, "manuscript", workspace.STATUS_AWAITING, note="")
        data["ebook_workspace"] = ws
        return {"ok": True, "duplicate": False, "data": data, "result": {}}

    monkeypatch.setattr(workspace, "execute_generate_manuscript", _fake_generate_empty)
    monkeypatch.setattr(workspace, "approve_stage", _real_shaped_approve_stage(calls))

    project = _make("Empty Manuscript Book", _project_data())
    status = orch.advance_build(project["id"])

    assert status["failed"] is False, "one attempt below the ceiling is recoverable, not final"
    assert status["retrying"] is True
    assert calls == ["generate", "approve:manuscript"]

    row = database.get_project(project["id"])
    assert not (row["data"].get("content") or "").strip()
