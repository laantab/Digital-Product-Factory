"""Server-side ebook execution — the browser must not own the build.

THE DEFECT THIS CLOSES
----------------------
The build was advanced only by a loop in the customer's browser. Close
the tab and the book stopped, which is how a live book came to sit at
"Writing your chapters (5 of 9)" forever.

These tests hold the claims that make "You can leave this page" true:

  * the intention to finish is a durable ROW, not a browser loop
  * two executors can never both own one job
  * a process that dies mid-chapter loses its lease and the work is
    reclaimed — with no cleanup step having run, because a recovery
    mechanism that depends on a clean shutdown is not one
  * completed chapters are never regenerated
  * a finished book is never exported twice

The orchestrator is stubbed here on purpose. What is under test is WHO
drives the build and what survives a crash — not how a chapter is
written, which is covered by the ebook suites.
"""
from __future__ import annotations

import database
import pytest

from services.jobs import executor, store


@pytest.fixture(autouse=True)
def jobs_table():
    database.init_db()
    store.init_jobs_table()
    conn = database.get_conn()
    try:
        conn.execute("DELETE FROM jobs")
        conn.commit()
    finally:
        conn.close()
    yield


def _project(name="Container Gardening for Beginners"):
    return database.create_project(name, "ebook", {"product_type": "ebook"})


class _Orchestrator:
    """A stand-in build: N chapters, then finished. Records every call."""

    def __init__(self, units_to_finish=3, fail_at=None, paused_at=None):
        self.calls = []
        self.units_to_finish = units_to_finish
        self.fail_at = fail_at
        self.paused_at = paused_at
        self.exports = 0

    def advance(self, project_id):
        self.calls.append(project_id)
        n = len(self.calls)
        if self.fail_at and n == self.fail_at:
            return {"finished": False, "failed": True, "message": "provider refused"}
        if self.paused_at and n == self.paused_at:
            return {"finished": False, "failed": False, "paused_after": "preview"}
        if n >= self.units_to_finish:
            self.exports += 1
            return {"finished": True, "failed": False, "percent": 100}
        return {"finished": False, "failed": False,
                "percent": int(100 * n / self.units_to_finish)}


@pytest.fixture
def orchestrator(monkeypatch):
    fake = _Orchestrator()

    def _install(obj):
        import services.ebook_build_orchestrator as real

        monkeypatch.setattr(real, "advance_build", obj.advance)
        return obj

    fake.install = _install
    _install(fake)
    return fake


# ==================================== the intention outlives the browser ===


def test_enqueue_persists_the_intention_to_finish():
    project = _project()
    job = store.enqueue(project["id"])
    assert job["status"] == store.QUEUED
    assert job["project_id"] == project["id"]

    # A brand new process, sharing nothing in memory, can still find it.
    assert store.get_for_project(project["id"])["status"] == store.QUEUED


def test_enqueue_is_idempotent_and_never_creates_a_second_job():
    """Two jobs for one book would race two executors onto one chapter."""
    project = _project()
    first = store.enqueue(project["id"])
    second = store.enqueue(project["id"])
    assert first["id"] == second["id"]

    conn = database.get_conn()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM jobs WHERE project_id=?",
            (project["id"],)).fetchone()
        assert int(row["n"] if isinstance(row, dict) else row[0]) == 1
    finally:
        conn.close()


# ================================================ exactly one owner =======


def test_only_one_executor_can_claim_a_job():
    project = _project()
    store.enqueue(project["id"])

    first = store.claim_next("executor-A")
    second = store.claim_next("executor-B")

    assert first is not None, "the first executor must get the job"
    assert second is None, "a live lease must not be stolen"
    assert first["lease_owner"] == "executor-A"


def test_a_second_executor_cannot_heartbeat_someone_elses_job():
    project = _project()
    store.enqueue(project["id"])
    job = store.claim_next("executor-A")

    assert store.heartbeat(job["id"], "executor-B") is False
    assert store.heartbeat(job["id"], "executor-A") is True


def test_a_non_owner_cannot_finish_a_job():
    project = _project()
    store.enqueue(project["id"])
    job = store.claim_next("executor-A")

    assert store.finish(job["id"], "executor-B", status=store.SUCCEEDED) is False
    assert store.get_for_project(project["id"])["status"] == store.RUNNING


# ============================== crash recovery, with no cleanup step ======


def test_a_dead_executors_job_is_reclaimed_when_its_lease_expires(monkeypatch):
    """The process died mid-chapter. Nothing tidied up. Work must continue."""
    project = _project()
    store.enqueue(project["id"])

    dead = store.claim_next("executor-that-died")
    assert dead is not None
    assert store.claim_next("executor-B") is None, "lease is still live"

    # Time passes; the lease expires. Nothing else happens -- no shutdown
    # hook, no sweeper, no human.
    conn = database.get_conn()
    try:
        conn.execute("UPDATE jobs SET lease_expires_at=? WHERE id=?",
                     ("2000-01-01T00:00:00+00:00", dead["id"]))
        conn.commit()
    finally:
        conn.close()

    reclaimed = store.claim_next("executor-B")
    assert reclaimed is not None, "an expired lease must be reclaimable"
    assert reclaimed["id"] == dead["id"]
    assert reclaimed["lease_owner"] == "executor-B"


def test_reclaim_counts_the_attempt_so_a_poison_job_cannot_spin_forever():
    project = _project()
    store.enqueue(project["id"])
    first = store.claim_next("A")
    conn = database.get_conn()
    try:
        conn.execute("UPDATE jobs SET lease_expires_at='2000-01-01' WHERE id=?",
                     (first["id"],))
        conn.commit()
    finally:
        conn.close()
    second = store.claim_next("B")
    assert second["attempts"] > first["attempts"]


def test_a_job_past_the_attempt_ceiling_is_not_claimed():
    project = _project()
    job = store.enqueue(project["id"])
    conn = database.get_conn()
    try:
        conn.execute("UPDATE jobs SET attempts=? WHERE id=?",
                     (store.MAX_ATTEMPTS, job["id"]))
        conn.commit()
    finally:
        conn.close()
    assert store.claim_next("A") is None


# ============================================= the executor drives it =====


def test_the_executor_advances_a_build_with_no_browser_involved(orchestrator):
    project = _project()
    store.enqueue(project["id"])

    result = executor.run_one_job("executor-A")

    assert result["claimed"] is True
    assert result["finished"] is True
    assert orchestrator.calls, "the orchestrator must actually have been driven"
    assert all(pid == project["id"] for pid in orchestrator.calls)
    assert store.get_for_project(project["id"])["status"] == store.SUCCEEDED


def test_nothing_to_do_is_not_an_error(orchestrator):
    result = executor.run_one_job("executor-A")
    assert result["claimed"] is False
    assert orchestrator.calls == []


def test_a_finished_book_is_never_exported_twice(orchestrator):
    """Re-running the executor must not produce a second PDF or ZIP."""
    project = _project()
    store.enqueue(project["id"])

    executor.run_one_job("executor-A")
    exports_after_first = orchestrator.exports

    again = executor.run_one_job("executor-A")

    assert again["claimed"] is False, "a SUCCEEDED job must not be re-claimed"
    assert orchestrator.exports == exports_after_first


def test_a_failed_stage_closes_the_job_rather_than_spinning(orchestrator, monkeypatch):
    import services.ebook_build_orchestrator as real

    failing = _Orchestrator(fail_at=2)
    monkeypatch.setattr(real, "advance_build", failing.advance)

    project = _project()
    store.enqueue(project["id"])
    result = executor.run_one_job("executor-A")

    assert result["failed"] is True
    assert store.get_for_project(project["id"])["status"] == store.FAILED


def test_a_deliberate_pause_releases_the_job_without_failing_it(orchestrator, monkeypatch):
    import services.ebook_build_orchestrator as real

    paused = _Orchestrator(paused_at=2)
    monkeypatch.setattr(real, "advance_build", paused.advance)

    project = _project()
    store.enqueue(project["id"])
    result = executor.run_one_job("executor-A")

    assert result.get("paused") is True
    assert result["failed"] is False
    job = store.get_for_project(project["id"])
    assert job["status"] == store.QUEUED, "a pause is not a failure"


def test_an_exception_releases_the_job_instead_of_killing_the_book(monkeypatch):
    """A transient provider error must not permanently destroy a customer's book."""
    import services.ebook_build_orchestrator as real

    def _boom(project_id):
        raise RuntimeError("provider timed out")

    monkeypatch.setattr(real, "advance_build", _boom)

    project = _project()
    store.enqueue(project["id"])
    result = executor.run_one_job("executor-A")

    assert result["failed"] is True
    job = store.get_for_project(project["id"])
    assert job["status"] == store.QUEUED, "still retryable"
    assert "RuntimeError" in job["last_error"]


def test_work_is_bounded_per_claim_so_one_book_cannot_monopolise(monkeypatch):
    import services.ebook_build_orchestrator as real

    endless = _Orchestrator(units_to_finish=10_000)
    monkeypatch.setattr(real, "advance_build", endless.advance)

    project = _project()
    store.enqueue(project["id"])
    result = executor.run_one_job("executor-A")

    assert result["units"] == executor.UNITS_PER_CLAIM
    assert result["finished"] is False
    assert store.get_for_project(project["id"])["status"] == store.QUEUED, (
        "the job is handed back so another tick continues it"
    )


def test_an_executor_that_lost_its_lease_stops_rather_than_racing(monkeypatch):
    import services.ebook_build_orchestrator as real

    slow = _Orchestrator(units_to_finish=10_000)
    monkeypatch.setattr(real, "advance_build", slow.advance)
    monkeypatch.setattr(store, "heartbeat", lambda job_id, owner: False)

    project = _project()
    store.enqueue(project["id"])
    result = executor.run_one_job("executor-A")

    assert result.get("lease_lost") is True
    assert result["units"] == 1, "it must stop at once, not keep working"


def test_drain_finishes_every_queued_book(orchestrator, monkeypatch):
    import services.ebook_build_orchestrator as real

    fake = _Orchestrator(units_to_finish=2)
    monkeypatch.setattr(real, "advance_build", fake.advance)

    ids = [_project(f"Book {i}")["id"] for i in range(3)]
    for pid in ids:
        store.enqueue(pid)

    outcome = executor.drain()

    assert outcome["jobs_run"] == 3
    assert outcome["jobs_finished"] == 3
    for pid in ids:
        assert store.get_for_project(pid)["status"] == store.SUCCEEDED


# ============================ resumption belongs to the orchestrator ======


def test_the_executor_never_decides_what_to_generate(orchestrator):
    """It only asks the orchestrator to advance.

    That is what guarantees chapters 1-5 are not regenerated: the
    executor has no concept of a chapter, so it cannot rewrite one.
    """
    project = _project()
    store.enqueue(project["id"])
    executor.run_one_job("executor-A")

    # Every interaction was 'advance this project', nothing more specific.
    assert orchestrator.calls == [project["id"]] * len(orchestrator.calls)


# ================== the app wires it up, and the switch is reversible =====


def test_starting_a_build_enqueues_a_durable_job(monkeypatch):
    """The customer clicks Build once; the server owns finishing it."""
    import app as app_module
    import services.ebook_build_orchestrator as real

    project = _project("Wired Up")

    def _fake_start(fields):
        return {"id": project["id"], "data": {"product_type": "ebook"}}, True

    monkeypatch.setattr(real, "start_build", _fake_start)
    monkeypatch.setattr(real, "status_payload", lambda data, pid: {
        "ok": True, "project_id": pid, "percent": 0})

    response = app_module.app.test_client().post(
        "/ebook/build", json={"fields": {"topic": "Container Gardening"}})
    assert response.status_code == 200

    job = store.get_for_project(project["id"])
    assert job is not None, "no durable job means the browser still owns the build"
    assert job["status"] == store.QUEUED


def test_a_queueing_failure_never_stops_a_customer_starting_a_book(monkeypatch):
    import app as app_module
    import services.ebook_build_orchestrator as real
    import services.jobs.store as store_module

    project = _project("Queue Broken")
    monkeypatch.setattr(real, "start_build",
                        lambda fields: ({"id": project["id"], "data": {}}, True))
    monkeypatch.setattr(real, "status_payload",
                        lambda data, pid: {"ok": True, "project_id": pid})

    def _boom(*a, **k):
        raise RuntimeError("jobs table unavailable")

    monkeypatch.setattr(store_module, "enqueue", _boom)

    response = app_module.app.test_client().post("/ebook/build", json={"fields": {}})
    assert response.status_code == 200, "the book must still start"


def test_the_executor_is_off_under_the_test_suite(monkeypatch):
    """A suite that silently runs builds underneath itself is unreadable."""
    from services.jobs import runner

    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    assert runner.executor_enabled() is False
    assert runner.start() is False


@pytest.mark.parametrize("value", ["off", "0", "false", "no", "OFF"])
def test_the_executor_has_a_one_variable_rollback(monkeypatch, value):
    """Rollback to browser-driven builds must be one environment variable."""
    from services.jobs import runner

    monkeypatch.delenv("FACTORY_TEST_MODE", raising=False)
    monkeypatch.setenv(runner.ENV_SWITCH, value)
    assert runner.executor_enabled() is False


def test_the_executor_is_on_by_default_in_production(monkeypatch):
    from services.jobs import runner

    monkeypatch.delenv("FACTORY_TEST_MODE", raising=False)
    monkeypatch.delenv(runner.ENV_SWITCH, raising=False)
    assert runner.executor_enabled() is True


def test_a_failing_tick_never_takes_the_web_service_down(monkeypatch):
    from services.jobs import runner

    monkeypatch.setattr("services.jobs.executor.drain",
                        lambda **k: (_ for _ in ()).throw(RuntimeError("boom")))
    runner._tick_once()          # must not raise
