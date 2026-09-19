"""The one place a heavy route hands its work to the builder — v1.8.1.

WHAT THIS CLOSES
----------------
v1.8.0 put the mode decision in exactly one function, `dispatch.hand_off`,
and wired three routes to it. Every other heavy route ignored the mode and
kept building inside the web process. On 2026-09-18 the step-by-step
screen killed a gunicorn worker at the 120-second timeout and then took the
512 MB instance out of memory, while the builder sat at zero runs.

This module is what the other routes call. `app.py` still does not know
which mode is set: it calls `hand_off_if_workflow` and either gets a status
payload back (workflow mode — return it, do nothing else) or `None` (inline
mode — carry on exactly as before). One function, one decision, and adding
a heavy route that forgets to call it is caught by
`tests/test_post_route_registry.py`.

WHAT A HEAVY ROUTE DOES IN WORKFLOW MODE
----------------------------------------
Three things, in this order, all of them fast:

 1. VALIDATE AND RECORD THE CUSTOMER'S DECISION exactly as it does today.
    The confirmation token, `max_authorized_usd`, `idempotency_key`, the
    expected artifact id and revision and the outline digest are the spend
    gate, and v1.8.1 does not touch it. Validation stays in the route,
    BEFORE this is called, so an unauthorised or stale request is still
    refused with the same error the customer gets now, and a rejected
    request never starts a task.

 2. PERSIST THE REQUESTED ACTION on the durable job row, so the builder can
    read what was asked for.

 3. HAND OFF and answer with the read-only status payload the screen
    already polls.

WHY IT RETURNS STATUS AND NEVER AN ERROR
-----------------------------------------
`/advance` already answers workflow-mode calls with read-only status rather
than an error, so an old tab or a stale script sees progress instead of a
failure. Every heavy route now behaves the same way. A customer whose
browser is running last week's JavaScript must not be shown a broken screen
because the server changed which machine does the work.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

#: Shown while the builder picks the work up. The screen polls
#: /ebook/build/<id>/status from here, exactly as the one-click build does.
MSG_HANDED_OFF = "Working on it. You can leave this page."


def workflow_mode() -> bool:
    """Whether the builder owns heavy work right now."""
    from services.jobs import mode

    return mode.is_workflow_mode()


def _status_payload(project_id: int) -> dict:
    """The same read-only payload /ebook/build/<id>/status returns."""
    import database
    from services.ebook_build_orchestrator import status_payload

    project = database.get_project(int(project_id))
    data = dict(project.get("data") or {}) if project else {}
    return status_payload(data, int(project_id))


def record_action(project_id: int, action: dict) -> bool:
    """Write the requested action onto the book's durable job row.

    The job row must exist first, which it does: `hand_off` enqueues before
    it triggers, and `enqueue` is idempotent per project. Recording the
    action before handing off means a task that starts immediately still
    finds it.
    """
    from services.jobs import store

    try:
        store.init_jobs_table()
        job = store.enqueue(int(project_id))
        job_id = job.get("id")
        if not job_id:
            log.error("no job row for project %s; action not recorded", project_id)
            return False
        return store.set_requested_action(int(job_id), dict(action or {}))
    except Exception:                                  # noqa: BLE001
        log.exception("could not record the requested action for project %s",
                      project_id)
        return False


def hand_off_if_workflow(project_id: int, *, route: str, action: str = "",
                         payload: dict | None = None,
                         reset_attempts: bool = False) -> dict | None:
    """Give this work to the builder, or return None to run it inline.

    Returns:
        None  - inline mode. The caller does the work itself, unchanged.
        dict  - workflow mode. The caller must return this and do nothing
                else. It is the read-only status payload the screen polls.

    Never raises. A heavy route must always answer the customer, and a
    problem queueing the work is reported on the payload rather than thrown:
    an exception here would turn a working screen into a 500 for a reason
    the customer can do nothing about.
    """
    if not workflow_mode():
        return None

    pid = int(project_id)
    recorded = record_action(pid, {"route": str(route), "action": str(action or ""),
                                   "payload": dict(payload or {})})

    triggered = {}
    try:
        from services.jobs.dispatch import hand_off

        triggered = hand_off(pid, reset_attempts=bool(reset_attempts)) or {}
    except Exception:                                  # noqa: BLE001
        log.exception("could not hand off %s for project %s", route, pid)

    try:
        out = _status_payload(pid)
    except Exception:                                  # noqa: BLE001
        log.exception("could not read status for project %s", pid)
        out = {"project_id": pid}

    out["ok"] = True
    out["handed_off"] = True
    out["advanced"] = False
    out["execution_mode"] = "workflow"
    out["requested_route"] = str(route)
    out["requested_action"] = str(action or "")
    out["action_recorded"] = bool(recorded)
    out["enqueued"] = bool(triggered.get("enqueued"))
    out["triggered"] = bool(triggered.get("triggered"))
    if triggered.get("run_id"):
        out["run_id"] = triggered.get("run_id")
    # Only overwrite the customer message when the build has nothing more
    # specific to say. A real stage message ("Writing your chapters") beats
    # a generic one.
    if not str(out.get("customer_message") or "").strip():
        out["customer_message"] = MSG_HANDED_OFF
    out["can_leave_page"] = True
    return out
