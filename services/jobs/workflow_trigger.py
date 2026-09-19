"""Asking Render to build the book — v1.8.0.

WHAT THIS IS FOR
----------------
In workflow mode the web process does not build anything. It writes the
durable job and asks Render Workflows to start a task, which runs on its
own instance with its own CPU and RAM and disappears when the book is
done. That is what stops one customer's build from exhausting the web
service's memory, which is the defect v1.8.0 exists to close.

THE TWO RULES THIS MODULE OBEYS
-------------------------------
1. THE JOB IS WRITTEN BEFORE THE TASK IS ASKED FOR. The row is the
   durable intention; the task is only a request to act on it now. If the
   trigger fails, is rate-limited, or Render is down, the work is still
   recorded and a later trigger — or a retry — picks it up. Triggering
   first and writing after would lose books to a crash in between.

2. IT NEVER RAISES INTO A REQUEST. A customer clicking Build must get a
   page back. Every failure here is reported in the returned dict and
   logged, never thrown.

DUPLICATE PROTECTION LIVES IN THE DATABASE, NOT HERE
----------------------------------------------------
A customer who clicks Continue five times must not start five tasks on
one book: five instances would race each other onto the same chapter and
every one of them would be billed. The guard is `store.claim_trigger`, a
single conditional UPDATE, because two web instances handling two clicks
at the same instant cannot be separated by anything held in memory.

NO PAID CALL IS MADE FROM A TEST
--------------------------------
The Render SDK is imported inside the function, so importing this module
costs nothing and the suite can replace `_start_task` without the SDK
being installed at all.
"""
from __future__ import annotations

import logging

from services.jobs import mode, store

log = logging.getLogger(__name__)


def _start_task(task: str, project_id: int) -> str:
    """Start a Render Workflow task and return its run id, without waiting.

    `start_task` is deliberately not `run_task`: the customer's request
    must return immediately. Waiting for the book here would put the
    build back inside the web request, which is the thing being fixed.
    """
    from render import Render                          # noqa: PLC0415

    client = Render()                                  # reads RENDER_API_KEY
    started = client.workflows.start_task(task, [int(project_id)])
    return str(getattr(started, "id", "") or "")


def trigger(project_id: int, *, reset_attempts: bool = False) -> dict:
    """Record the work, then ask Render to do it. Never raises.

    Returns a dict describing what happened. `enqueued` is the part that
    matters for correctness: if it is True the book will be built, with
    or without this particular trigger succeeding.
    """
    outcome = {"project_id": int(project_id), "mode": mode.execution_mode(),
               "enqueued": False, "triggered": False, "run_id": "", "reason": ""}

    # 1. Durable first, always — in both modes.
    try:
        job = store.enqueue(int(project_id), reset_attempts=reset_attempts)
        outcome["enqueued"] = True
        outcome["job_id"] = job.get("id")
    except Exception:                                  # noqa: BLE001
        log.exception("could not enqueue the ebook build job")
        outcome["reason"] = "the job could not be recorded"
        return outcome

    if not mode.is_workflow_mode():
        outcome["reason"] = "execution mode is inline"
        return outcome

    ready, why = mode.is_configured()
    if not ready:
        # The work is safe in the table; it just has nobody to run it yet.
        # Saying so plainly is the point — a half-configured service that
        # silently accepts books is how a customer waits for nothing.
        log.error("workflow mode is not usable: %s", why)
        outcome["reason"] = why
        return outcome

    job_id = outcome.get("job_id")
    if not job_id:
        outcome["reason"] = "the job has no id"
        return outcome

    # 2. Win the right to start exactly one task for this book.
    if not store.claim_trigger(int(job_id)):
        outcome["reason"] = "a task for this book was already started"
        return outcome

    # 3. Ask Render. A failure here is recoverable: the row survives.
    try:
        run_id = _start_task(mode.workflow_task(), int(project_id))
    except Exception as exc:                           # noqa: BLE001
        log.exception("could not start the Render Workflow task")
        outcome["reason"] = f"{type(exc).__name__}"
        return outcome

    outcome["triggered"] = True
    outcome["run_id"] = run_id
    try:
        store.record_workflow_run(int(job_id), run_id)
    except Exception:                                  # noqa: BLE001
        # Losing the run id costs traceability, not the book.
        log.exception("could not record the workflow run id")
    return outcome
