"""Continue must hand the book to the server, not just tidy the state.

v1.7.24 made "You can leave this page" true by enqueueing a durable job
when a build STARTS. v1.7.25 put a Continue button on the stalled panel
so a stranded book could be rescued. The two were never joined up:
Continue cleared the stalled stage and then handed the work to nobody.

A customer who clicks Continue and closes the tab — which the panel
invites them to do — got nothing at all. The promise was false on
precisely the path that exists to rescue a stalled book.

Two ways that failed, both covered here:
  * no job was enqueued by resume, so no executor ever picked it up; and
  * a job that had already exhausted its attempts was re-opened to QUEUED
    without clearing them, and `claim_next` skips `attempts >= MAX_ATTEMPTS`
    — so it sat QUEUED forever while the screen span "being picked back up".
"""
from __future__ import annotations

import database
import pytest

from services.jobs import store


#: Projects this file creates, removed afterwards. Resuming a build writes a
#: live `ebook_build` with a current timestamp, so a project left behind here
#: would outrank the fixtures of any other test that asks for the newest
#: unfinished book. Tests share one database; they must not leave litter in it.
_CREATED: list[int] = []


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
    _CREATED.clear()
    yield
    for project_id in _CREATED:
        try:
            database.delete_project(project_id)
        except Exception:  # noqa: BLE001
            pass
    _CREATED.clear()


def _project():
    project = database.create_project(
        "Container Gardening for Beginners", "ebook", {"product_type": "ebook"})
    _CREATED.append(project["id"])
    return project


def _exhaust(job_id):
    conn = database.get_conn()
    try:
        conn.execute("UPDATE jobs SET attempts=?, status=? WHERE id=?",
                     (store.MAX_ATTEMPTS, store.FAILED, job_id))
        conn.commit()
    finally:
        conn.close()


# ============================== an exhausted job must be reclaimable by hand ==


def test_an_exhausted_job_is_not_claimable_after_a_plain_reenqueue():
    """The automatic ceiling still holds — retries must not loop forever."""
    project = _project()
    job = store.enqueue(project["id"])
    _exhaust(job["id"])

    store.enqueue(project["id"])
    assert store.claim_next("executor-A") is None, (
        "an automatic re-enqueue must not defeat the attempt ceiling"
    )


def test_the_customers_explicit_continue_clears_the_ceiling():
    """A human saying "keep going" is a fresh start, not another retry."""
    project = _project()
    job = store.enqueue(project["id"])
    _exhaust(job["id"])

    store.enqueue(project["id"], reset_attempts=True)
    claimed = store.claim_next("executor-A")
    assert claimed is not None, "Continue must make the book runnable again"
    assert claimed["project_id"] == project["id"]


def test_resetting_attempts_still_reuses_the_one_job_row():
    """Two jobs for one book would race two executors onto the same chapter."""
    project = _project()
    first = store.enqueue(project["id"])
    _exhaust(first["id"])
    second = store.enqueue(project["id"], reset_attempts=True)
    assert second["id"] == first["id"]

    conn = database.get_conn()
    try:
        rows = conn.execute("SELECT COUNT(*) FROM jobs WHERE project_id=?",
                            (project["id"],)).fetchone()
    finally:
        conn.close()
    assert int(rows[0]) == 1


def test_a_live_running_job_is_left_alone_by_continue():
    """Continue must never yank a lease out from under a working executor."""
    project = _project()
    store.enqueue(project["id"])
    running = store.claim_next("executor-A")

    store.enqueue(project["id"], reset_attempts=True)
    job = store.get_for_project(project["id"])
    assert job["status"] == store.RUNNING
    assert job["lease_owner"] == "executor-A"
    assert store.heartbeat(running["id"], "executor-A") is True


# ========================================= the route actually does the handoff ==


def test_the_resume_route_enqueues_the_work():
    """The end-to-end contract: Continue leaves a runnable job behind."""
    import app as app_module

    project = _project()
    client = app_module.app.test_client()
    resp = client.post(f"/ebook/build/{project['id']}/resume", json={})
    assert resp.status_code == 200

    job = store.get_for_project(project["id"])
    assert job is not None, (
        "Continue cleared the stalled stage and handed the work to nobody"
    )
    assert job["status"] in (store.QUEUED, store.RUNNING)


def test_a_queueing_failure_never_breaks_the_continue_button(monkeypatch):
    """A broken queue must not take away the customer's way forward."""
    import app as app_module

    def _boom(*a, **k):
        raise RuntimeError("jobs table gone")

    monkeypatch.setattr(store, "enqueue", _boom)
    project = _project()
    client = app_module.app.test_client()
    resp = client.post(f"/ebook/build/{project['id']}/resume", json={})
    assert resp.status_code == 200
