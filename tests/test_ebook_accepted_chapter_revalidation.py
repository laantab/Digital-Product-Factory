"""An already-accepted chapter that no longer passes is never repaired.

THE CUSTOMER SYMPTOM
--------------------
Approval repeats forever while the correction rounds in between do nothing.
The customer presses Continue, the Factory says it is correcting, the
manuscript comes back byte-for-byte identical, approval fails again with
"Resolve structural/content findings before approving the manuscript", and
the book can never leave the manuscript stage without a human clearing the
acceptance cache by hand (recorded in SESSION_HANDOFF_2026-09-16.md, "Found
but NOT fixed", item 2, where project 370 needed exactly that intervention).

ROOT CAUSE: TWO GATES READING DIFFERENT TRUTHS
----------------------------------------------
services/ebook_project_workspace.py::approve_stage re-validates the whole
manuscript from its bytes every single time -- it trusts nothing cached.

services/ebook_project_workspace.py::execute_correct_manuscript decides what
to repair from the acceptance cache instead:

    if stored_accepted:
        accepted_keep = stored_accepted
        failed_orders = [c.order for c in book_contract.chapters
                         if c.order not in accepted_orders]

`prior_quality` is computed immediately above and then ignored on this
branch. So a chapter that sits in `accepted_chapters` can never appear in
`failed_orders`, however loudly the validator is failing it right now.

When every chapter is in the cache, `failed_orders` is empty, the chapter
pipeline is handed nothing to repair, the manuscript is returned unchanged,
and approve_stage refuses it again -- the loop, exactly.

A chapter goes stale in the cache whenever the book contract changes under
it: a validator repair, a tightened interior floor, or the required-material
contract that shipped in v1.7.27. The cache was written under the old rules
and is never re-examined under the new ones.

WHY THE FIX MUST BE NARROW
--------------------------
Naively re-opening every accepted chapter on a contract change would
regenerate whole books and spend real money on customers' projects. The only
chapters that may be re-opened are the ones the validator is failing right
now -- which is what these tests pin.
"""

from collections import Counter

import database
import services.ebook_project_workspace as workspace
from services import ebook_build_orchestrator as orch
from services.ebook_manuscript_engine import chapter_fn_from_full_manuscript
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript
from services.ebook_project_workspace import upsert_acceptance_project

STALE_ORDER = 7
STALE_BODY_MARKER = "This chapter was accepted under the previous contract."


def _advance_until_manuscript_approved(pid, limit=40):
    """Drive /advance until the manuscript stage is approved. Returns status."""
    status = {"failed": False, "percent": 0}
    for _ in range(limit):
        status = orch.advance_build(pid)
        if status["failed"]:
            return status
        row = database.get_project(pid)
        ws = row["data"]["ebook_workspace"]
        if workspace.stage_status(ws, "manuscript") == workspace.STATUS_APPROVED:
            return status
    return status


def _stale_one_accepted_chapter(pid, order=STALE_ORDER):
    """Make one cached-accepted chapter fail today's validator.

    This is the persisted state a contract change leaves behind: the chapter
    is still listed in `accepted_chapters`, and the manuscript still contains
    it, but its body no longer satisfies the contract the validator now
    applies. Nothing else about the project is touched.
    """
    row = database.get_project(pid)
    data = dict(row["data"])
    ws = data["ebook_workspace"]

    accepted = list(ws.get("accepted_chapters") or [])
    target = next(c for c in accepted if int(c["order"]) == order)
    old_body = str(target["body"])
    new_body = f"{STALE_BODY_MARKER}\n"

    md = str(data.get("content") or data.get("ebook") or "")
    assert old_body.strip() in md, "fixture drift: chapter body not found in manuscript"
    data["content"] = md.replace(old_body.strip(), new_body.strip())
    if data.get("ebook"):
        data["ebook"] = str(data["ebook"]).replace(old_body.strip(), new_body.strip())

    target["body"] = new_body
    ws["accepted_chapters"] = accepted
    workspace.set_stage_status(
        ws, "manuscript", workspace.STATUS_NEEDS_CORRECTION,
        note="Contract changed after these chapters were accepted",
    )
    data["ebook_workspace"] = ws
    database.update_project(pid, None, data)
    return data


def _build_to_accepted_manuscript(monkeypatch):
    """A real book, written by the real pipeline, with a full acceptance cache."""
    project = upsert_acceptance_project(database, preserve_live_manuscript=False)
    pid = project["id"]

    good_fn = chapter_fn_from_full_manuscript(build_event_photo_strong_manuscript())
    call_log: list[int] = []

    def _chapter(book, chapter):
        call_log.append(chapter.order)
        return good_fn(book, chapter)

    monkeypatch.setattr("services.ebook.generate_one_chapter", _chapter)

    status = _advance_until_manuscript_approved(pid)
    assert status["failed"] is False, status
    row = database.get_project(pid)
    ws = row["data"]["ebook_workspace"]
    assert workspace.stage_status(ws, "manuscript") == workspace.STATUS_APPROVED
    assert len(ws.get("accepted_chapters") or []) >= 3
    call_log.clear()
    return pid, call_log


# ================================================= the defect, end to end ===


def test_a_stale_accepted_chapter_is_repaired_instead_of_looping(monkeypatch):
    """The whole point: the book must be able to finish without a human.

    Before the fix this loops until the safety cap and the build reports
    failed, because `failed_orders` is empty and the correction pass has
    nothing to do.
    """
    pid, call_log = _build_to_accepted_manuscript(monkeypatch)
    _stale_one_accepted_chapter(pid)

    status = _advance_until_manuscript_approved(pid)

    row = database.get_project(pid)
    ws = row["data"]["ebook_workspace"]

    assert status["failed"] is False, (
        "the build stalled on a chapter the validator is failing but the "
        f"correction pass refused to re-open: {status}"
    )
    assert workspace.stage_status(ws, "manuscript") == workspace.STATUS_APPROVED

    counts = Counter(call_log)
    assert counts[STALE_ORDER] >= 1, (
        f"chapter {STALE_ORDER} fails the current contract and was never "
        "sent to the writer -- the correction pass read the acceptance "
        "cache instead of the validator"
    )
    md = str(row["data"].get("content") or "")
    assert STALE_BODY_MARKER not in md, "the stale body is still in the manuscript"


def test_only_the_failing_chapter_is_re_opened(monkeypatch):
    """The guard against the naive fix: no mass regeneration, no mass spend.

    Re-opening every cached chapter whenever one has gone stale would
    rewrite whole books that customers have already paid for. Only chapters
    the validator is failing right now may be re-opened.
    """
    pid, call_log = _build_to_accepted_manuscript(monkeypatch)
    before = database.get_project(pid)
    accepted_before = {
        int(c["order"]): str(c["body"])
        for c in before["data"]["ebook_workspace"]["accepted_chapters"]
    }

    _stale_one_accepted_chapter(pid)
    status = _advance_until_manuscript_approved(pid)
    assert status["failed"] is False, status

    counts = Counter(call_log)
    for order in sorted(accepted_before):
        if order == STALE_ORDER:
            continue
        assert counts[order] == 0, (
            f"chapter {order} still passed the validator but was regenerated "
            f"{counts[order]} time(s) -- that is a real duplicate charge on a "
            "customer's book"
        )

    after = database.get_project(pid)
    accepted_after = {
        int(c["order"]): str(c["body"])
        for c in after["data"]["ebook_workspace"]["accepted_chapters"]
    }
    for order, body in accepted_before.items():
        if order == STALE_ORDER:
            continue
        assert accepted_after.get(order) == body, (
            f"chapter {order} was rewritten even though it still passes"
        )


def test_accepted_chapters_and_failed_orders_stay_in_sync(monkeypatch):
    """`accepted_chapters` must never contain an order listed in `failed_orders`.

    The two lists are the correction pass's whole model of the manuscript.
    When a chapter appears in both, the pipeline is told to repair something
    it has also been told to preserve, and the repair is silently dropped.
    """
    pid, _call_log = _build_to_accepted_manuscript(monkeypatch)
    _stale_one_accepted_chapter(pid)

    for _ in range(40):
        status = orch.advance_build(pid)
        row = database.get_project(pid)
        ws = row["data"]["ebook_workspace"]
        accepted = {int(c["order"]) for c in (ws.get("accepted_chapters") or [])}
        failed = {int(o) for o in ((ws.get("chapter_pipeline") or {}).get("failed_orders") or [])}
        assert not (accepted & failed), (
            f"orders {sorted(accepted & failed)} are marked accepted and failed "
            "at the same time"
        )
        if status["failed"] or workspace.stage_status(
            ws, "manuscript"
        ) == workspace.STATUS_APPROVED:
            break


def test_the_repair_survives_a_restart(monkeypatch):
    """Persistence, not just the happy path in one process.

    The customer's browser is closed for most of a real build. The repaired
    chapter must be on disk, not only in the object the runner returned.
    """
    pid, _call_log = _build_to_accepted_manuscript(monkeypatch)
    _stale_one_accepted_chapter(pid)
    status = _advance_until_manuscript_approved(pid)
    assert status["failed"] is False, status

    reread = database.get_project(pid)
    ws = reread["data"]["ebook_workspace"]
    assert workspace.stage_status(ws, "manuscript") == workspace.STATUS_APPROVED
    stale = next(
        (c for c in ws["accepted_chapters"] if int(c["order"]) == STALE_ORDER), None
    )
    assert stale is not None
    assert STALE_BODY_MARKER not in str(stale["body"])
    assert str(stale["body"]).strip(), "the repaired chapter must have a real body"
