"""A retry must actually retry, not replay the failure that caused it.

"Container Gardening for Beginners" wrote nine good chapters and then
died. The manuscript needed one correction pass. It got exactly one —
ever.

The orchestrator passed a fixed idempotency key per project and stage
("orch-manuscript-correct-370"). The workspace records that key the first
time the call runs, and every later call carrying it returns the ORIGINAL
result as a duplicate replay: no work, nothing persisted. So attempt 1
corrected what it could and left one finding; attempts 2 through 60
replayed instantly, did nothing at all, and re-raised on the same stale
finding. Sixty attempts burned in about a minute, FAILED_FINAL, and no
Continue could ever help — resume clears the attempt count, but the
replay still short-circuits.

An idempotency key exists so the SAME logical paid call, delivered twice
(two executors racing, a retried request), is charged once. A key that is
constant for the life of the project does not do that job — it makes
every future attempt a replay, so the correction system can only ever run
once per book.

The key must therefore identify one ATTEMPT. `_claim_stage` increments the
stage's attempt counter before the runner is called, so that counter is
exactly the right identity: the same attempt replays safely, a real retry
is a new logical call.
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


def _project(attempts: int, stage: str = "manuscript"):
    data = {
        "product_type": "ebook",
        "content": "# Book\n\n## Chapter 1: One\n\nBody.\n",
        "ebook_build": {
            "build_id": "b1",
            "current_stage": stage,
            "stages": {stage: {"status": "RUNNING", "attempts": attempts}},
        },
    }
    project = database.create_project("Container Gardening", "ebook", data)
    _CREATED.append(project["id"])
    return project["id"], data


# ================================================= the key identifies a try ==


def test_the_same_attempt_produces_the_same_key():
    """Idempotency still works: one logical call is charged once."""
    pid, data = _project(attempts=3)
    first = orch._attempt_idempotency_key(data, "manuscript", pid)
    second = orch._attempt_idempotency_key(data, "manuscript", pid)
    assert first == second


def test_a_later_attempt_produces_a_different_key():
    """The live defect: attempt 2 must not replay attempt 1's result."""
    pid, first_data = _project(attempts=1)
    first = orch._attempt_idempotency_key(first_data, "manuscript", pid)

    first_data["ebook_build"]["stages"]["manuscript"]["attempts"] = 2
    second = orch._attempt_idempotency_key(first_data, "manuscript", pid)

    assert first != second, (
        "a constant key makes every retry a no-op replay, which is how a book "
        "burned 60 attempts in a minute without doing any work"
    )


def test_generation_and_correction_keys_never_collide():
    pid, data = _project(attempts=1)
    generate = orch._attempt_idempotency_key(data, "manuscript", pid)
    correct = orch._attempt_idempotency_key(data, "manuscript", pid, suffix="correct")
    assert generate != correct


def test_two_different_projects_never_share_a_key():
    first_pid, first_data = _project(attempts=1)
    second_pid, second_data = _project(attempts=1)
    assert (orch._attempt_idempotency_key(first_data, "manuscript", first_pid)
            != orch._attempt_idempotency_key(second_data, "manuscript", second_pid))


@pytest.mark.parametrize("stage", ["research", "title", "outline", "manuscript"])
def test_every_stage_key_varies_with_its_own_attempt_count(stage):
    """Each stage had the identical fixed-key dead end, not just manuscript."""
    pid, data = _project(attempts=1, stage=stage)
    before = orch._attempt_idempotency_key(data, stage, pid)
    data["ebook_build"]["stages"][stage]["attempts"] = 2
    assert before != orch._attempt_idempotency_key(data, stage, pid)


def test_the_key_survives_a_missing_stage_record():
    """Never raise while building a key; an unknown attempt is attempt zero."""
    pid = 4242
    key = orch._attempt_idempotency_key({"product_type": "ebook"}, "manuscript", pid)
    assert str(pid) in key


# ============================================ no fixed keys left in the code ==


def test_no_stage_runner_still_passes_a_project_constant_key():
    """Grep the source: a fixed key anywhere reintroduces the dead end."""
    import inspect
    import re

    src = inspect.getsource(orch)
    # f-strings that end at the project id, e.g. f"orch-manuscript-{pid}"
    offenders = re.findall(r'f"orch-[a-z-]+-\{pid\}"', src)
    assert not offenders, (
        f"these keys are constant for the life of the project: {offenders}"
    )
