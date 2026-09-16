"""The progress screen must tell the truth about whether work is happening.

A customer watched "Writing your chapters (5 of 9)" on a moving-looking
screen while nothing at all was running. An indicator that always
animates is not reassurance — it is the defect, because it cannot tell
"working" apart from "abandoned", and that is the single thing the
customer needs to know.

So `activity_for` reports a state derived from two real signals: how long
ago the build last actually persisted progress, and whether a durable job
holds a live lease. Either driver counts — a customer watching the screen
advances the build from the browser, the server executor advances it when
they are away.

Most of these tests exist to make the spinner STOP.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import database
import pytest

from services.ebook_build_orchestrator import (
    ACTIVE_WITHIN_SECONDS,
    ACTIVITY_DONE,
    ACTIVITY_FAILED,
    ACTIVITY_QUEUED,
    ACTIVITY_RETRYING,
    ACTIVITY_STALLED,
    ACTIVITY_WORKING,
    activity_for,
)
from services.jobs import store


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


def _data(*, seconds_ago=0, finished=False, failed=False):
    when = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    return {
        "ebook_build": {
            "build_id": "b1",
            "started_at": when.isoformat(),
            "updated_at": when.isoformat(),
            "current_stage": "manuscript",
            "stages": {"manuscript": {"status": "IN_PROGRESS", "attempts": 5}},
            "customer_message": "Writing chapters (5/9)",
            "finished": finished,
            "failed": failed,
        }
    }


def _project():
    return database.create_project("Container Gardening", "ebook", {"product_type": "ebook"})


# ================================ it spins only when something is running ==


def test_recent_progress_means_working():
    """A customer watching the screen drives it from the browser."""
    project = _project()
    activity = activity_for(project["id"], _data(seconds_ago=2))
    assert activity["state"] == ACTIVITY_WORKING
    assert activity["spinning"] is True


def test_a_live_job_lease_means_working_even_with_no_recent_progress():
    """The server executor owns it; a slow chapter is not a stall."""
    project = _project()
    store.enqueue(project["id"])
    store.claim_next("executor-A")

    activity = activity_for(project["id"], _data(seconds_ago=ACTIVE_WITHIN_SECONDS + 600))
    assert activity["state"] == ACTIVITY_WORKING
    assert activity["spinning"] is True


def test_no_progress_and_no_job_is_STALLED_and_must_not_spin():
    """The exact live failure: nothing is running, so say so."""
    project = _project()
    activity = activity_for(project["id"], _data(seconds_ago=ACTIVE_WITHIN_SECONDS + 600))

    assert activity["state"] == ACTIVITY_STALLED
    assert activity["spinning"] is False, (
        "a spinner over a build that stopped is the bug, not the reassurance"
    )
    assert activity["label"] == "Paused"


def test_an_expired_lease_is_not_mistaken_for_work_in_progress():
    """The process died. The row still says RUNNING. Nothing is running."""
    project = _project()
    store.enqueue(project["id"])
    job = store.claim_next("executor-that-died")

    conn = database.get_conn()
    try:
        conn.execute("UPDATE jobs SET lease_expires_at=? WHERE id=?",
                     ("2000-01-01T00:00:00+00:00", job["id"]))
        conn.commit()
    finally:
        conn.close()

    activity = activity_for(project["id"], _data(seconds_ago=ACTIVE_WITHIN_SECONDS + 600))
    assert activity["state"] == ACTIVITY_STALLED
    assert activity["spinning"] is False


def test_a_queued_job_says_it_is_being_picked_back_up():
    project = _project()
    store.enqueue(project["id"])
    activity = activity_for(project["id"], _data(seconds_ago=ACTIVE_WITHIN_SECONDS + 600))
    assert activity["state"] == ACTIVITY_QUEUED
    assert activity["spinning"] is True
    assert "pick" in activity["label"].lower()


def test_retrying_is_reported_distinctly_from_plain_working():
    project = _project()
    activity = activity_for(project["id"], _data(seconds_ago=2), retrying=True)
    assert activity["state"] == ACTIVITY_RETRYING
    assert activity["spinning"] is True


def test_finished_and_failed_never_spin():
    project = _project()
    done = activity_for(project["id"], _data(finished=True))
    assert done["state"] == ACTIVITY_DONE and done["spinning"] is False

    failed = activity_for(project["id"], _data(failed=True, seconds_ago=1))
    assert failed["state"] == ACTIVITY_FAILED and failed["spinning"] is False


def test_a_missing_timestamp_is_treated_as_stalled_not_as_working():
    """Unknown must never be optimistic."""
    project = _project()
    data = _data()
    data["ebook_build"]["updated_at"] = ""
    activity = activity_for(project["id"], data)
    assert activity["state"] == ACTIVITY_STALLED
    assert activity["spinning"] is False


def test_a_malformed_timestamp_does_not_raise_and_does_not_spin():
    project = _project()
    data = _data()
    data["ebook_build"]["updated_at"] = "not-a-date"
    activity = activity_for(project["id"], data)
    assert activity["spinning"] is False


def test_activity_never_raises_when_the_jobs_table_is_unavailable(monkeypatch):
    """The progress screen must render even if the queue is broken."""
    import services.jobs.store as store_module

    def _boom(*a, **k):
        raise RuntimeError("jobs table gone")

    monkeypatch.setattr(store_module, "get_for_project", _boom)
    project = _project()
    activity = activity_for(project["id"], _data(seconds_ago=2))
    assert activity["state"] == ACTIVITY_WORKING


# ================================================= it reaches the screen ===


def test_the_status_payload_carries_activity():
    from services.ebook_build_orchestrator import status_payload

    project = _project()
    payload = status_payload(_data(seconds_ago=2), project["id"])
    assert "activity" in payload
    assert payload["activity"]["state"] in (
        ACTIVITY_WORKING, ACTIVITY_QUEUED, ACTIVITY_RETRYING, ACTIVITY_STALLED)


def test_the_screen_stops_spinning_and_offers_continue_when_stalled():
    """The browser code must render the stalled panel, not an animation."""
    import pathlib

    js = (pathlib.Path(__file__).resolve().parents[1]
          / "static" / "js" / "app.js").read_text(encoding="utf-8")

    assert "_ebookActivityDot" in js
    assert 'data-ebook-stalled' in js, "there must be a paused panel"
    assert 'act.state === "stalled"' in js, "the panel must be driven by real state"
    # The spinner is reachable only after the non-spinning states return.
    dot = js.split("function _ebookActivityDot", 1)[1].split("function _ebookBuildBar", 1)[0]
    assert dot.index('state === "stalled"') < dot.index("animate-spin"), (
        "stalled must be handled before the spinning branch"
    )


def test_the_leave_this_page_promise_is_no_longer_about_saved_projects():
    """The old copy pointed customers at a list that excluded unfinished books."""
    import pathlib

    js = (pathlib.Path(__file__).resolve().parents[1]
          / "static" / "js" / "app.js").read_text(encoding="utf-8")
    assert "You can leave this page" in js
    assert "Continue where you left off" in js
