"""v1.9.14: after Continue, a retry must not replay the attempts before it.

Live failure, 2026-09-28, project 7 "Container Gardening" (build
48011f833d736df3). The manuscript stage had failed on 2026-09-17 after 60
attempts whose correction calls were keyed orch-manuscript-correct-7-a1 .. a60.
Continue (resume_build) set the stage's attempt count back to 0, so the next
60 attempts built exactly the same keys. The workspace found each key in its
idempotency store and replayed the 2026-09-17 result: no chapter was
corrected, approval raised "Resolve structural/content findings before
approving the manuscript." every time, and the build hit FAILED_FINAL again
in about four minutes -- having done no work at all.

Each Continue now starts a new generation that is part of the key.
"""
from __future__ import annotations

import database
import pytest

from services import ebook_build_orchestrator as orch

_CREATED: list[int] = []


@pytest.fixture(autouse=True)
def _cleanup():
    _CREATED.clear()
    yield
    for project_id in _CREATED:
        try:
            database.delete_project(project_id)
        except Exception:  # noqa: BLE001
            pass
    _CREATED.clear()


def _failed_project(prior_keys: list[str]) -> int:
    """A build whose manuscript stage died at the ceiling, as project 7's did."""
    data = {
        "product_type": "ebook",
        "content": "# Book\n\n## Chapter 1: One\n\nBody.\n",
        "ebook_workspace": {
            "rail": {s: {"status": "approved"} for s in ("research", "title", "outline")},
            "paid_call_ledger": {"idempotency_keys": {k: {"result": {}} for k in prior_keys}},
        },
        "ebook_build": {
            "build_id": "48011f833d736df3",
            "current_stage": "manuscript",
            "failed": True,
            "stages": {"manuscript": {"status": "FAILED_FINAL", "attempts": 60,
                                      "error": "Resolve structural/content findings "
                                               "before approving the manuscript."}},
        },
    }
    project = database.create_project("Container Gardening", "ebook", data)
    _CREATED.append(project["id"])
    return project["id"]


def _key_for_attempt(pid: int, attempt: int, suffix: str = "correct") -> str:
    data = dict(database.get_project(pid)["data"])
    data["ebook_build"]["stages"]["manuscript"]["attempts"] = attempt
    return orch._attempt_idempotency_key(data, "manuscript", pid, suffix=suffix)


def test_attempts_after_continue_never_reuse_a_key_from_before_it():
    pid = _failed_project([])
    # The keys the first run used, built exactly as it built them, and
    # recorded in the workspace's idempotency store as the workspace does.
    before = [_key_for_attempt(pid, n) for n in range(1, 61)]
    data = dict(database.get_project(pid)["data"])
    data["ebook_workspace"]["paid_call_ledger"]["idempotency_keys"] = {k: {"result": {}} for k in before}
    database.update_project(pid, None, data)

    orch.resume_build(pid)

    state = database.get_project(pid)["data"]["ebook_build"]
    assert state["stages"]["manuscript"]["attempts"] == 0, "Continue still resets the count"
    after = [_key_for_attempt(pid, n) for n in range(1, 61)]
    reused = sorted(set(after) & set(before))
    assert not reused, f"these attempts would replay the old result: {reused[:3]}"


def test_every_continue_is_a_new_generation():
    pid = _failed_project([])
    orch.resume_build(pid)
    first = _key_for_attempt(pid, 1)
    # Fail again, Continue again.
    project = database.get_project(pid)
    data = dict(project["data"])
    data["ebook_build"]["stages"]["manuscript"].update({"status": "FAILED_FINAL", "attempts": 60})
    database.update_project(pid, None, data)
    orch.resume_build(pid)
    second = _key_for_attempt(pid, 1)
    assert first != second


def test_one_attempt_still_replays_safely_within_a_generation():
    """Idempotency is kept: the same attempt of the same generation is one call."""
    pid = _failed_project([])
    orch.resume_build(pid)
    assert _key_for_attempt(pid, 3) == _key_for_attempt(pid, 3)


def test_a_build_never_resumed_keeps_its_original_keys():
    """In-flight builds from before this release must not change identity."""
    pid = _failed_project([])
    assert _key_for_attempt(pid, 7) == f"orch-manuscript-correct-{pid}-a7"
