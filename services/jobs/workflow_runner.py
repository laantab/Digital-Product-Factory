"""What a Render Workflow task actually does — v1.8.0.

WHY THIS IS SEPARATE FROM workflow_task.py
------------------------------------------
`workflow_task.py` imports Render's SDK, because that is how a task is
registered. Nothing else in the Factory should depend on that package:
local Windows development has no Render, and the test suite must be able
to prove this logic without installing a cloud SDK. So all the behaviour
lives here, where it is ordinary Python, and the entrypoint is four lines
that call it.

WHAT IT DOES NOT DO
-------------------
It does not build a book. It claims the book's durable job and asks the
existing executor — and through it the existing orchestrator — to advance
it. Every stage, gate, attempt ceiling and checkpoint is unchanged. This
release moves the build to a different machine; it does not touch the
ebook engine.

WHY IT LOOPS INSTEAD OF RUNNING ONCE
------------------------------------
`run_project` is deliberately bounded: it does a fixed number of units
and hands the job back, so no single claim can monopolise an executor.
Inline mode calls it again every 20 seconds. A workflow task has no
ticker behind it, so it must keep asking until the book is finished, the
book pauses for the customer, or the run is out of time.

WHY IT HAS A DEADLINE
---------------------
Render stops a task run at its timeout and bills for the compute it used.
Stopping ourselves a little early means the run ends cleanly, the lease
expires on its own, and the next trigger resumes from the last
checkpoint — instead of being killed mid-chapter with a live lease that
has to time out first.
"""
from __future__ import annotations

import logging
import time

from services.jobs import executor, mode, store

log = logging.getLogger(__name__)

#: Leave this much of the run's budget unused so the task can finish the
#: unit it is on and exit cleanly rather than being killed.
DEADLINE_MARGIN_SECONDS = 120

#: Pause between claims when the job is momentarily unclaimable because
#: another owner's lease has not expired yet.
RETRY_SLEEP_SECONDS = 5

#: How many consecutive unclaimable results end the run. A job held by a
#: live lease belongs to another task; this one should stop, not fight.
MAX_UNCLAIMABLE = 3


def builder_version() -> str:
    """The VERSION this builder is running, or "unknown".

    Reported so a website on v1.8.1 and a builder still on v1.8.0 -- which is
    the shape of this repository's two Render services today -- is an obvious
    mismatch rather than a book that quietly ignores what the customer asked
    for.
    """
    import os

    try:
        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as handle:
            return handle.read().strip() or "unknown"
    except Exception:                                  # noqa: BLE001
        return "unknown"


def run_build(project_id: int, *, budget_seconds: int | None = None,
              sleep=time.sleep) -> dict:
    """Drive one book to completion, a pause, a failure or the deadline.

    Safe to call twice for the same book: the second caller cannot claim
    a job that is already leased, and a book that is already SUCCEEDED is
    not claimable at all, so a Render retry never rebuilds a finished
    book or duplicates an export.
    """
    project_id = int(project_id)
    budget = int(budget_seconds or mode.task_timeout_seconds())
    deadline = time.monotonic() + max(1, budget - DEADLINE_MARGIN_SECONDS)
    owner = store.executor_id()

    summary = {"project_id": project_id, "owner": owner, "claims": 0,
               "units": 0, "finished": False, "failed": False,
               "paused": False, "reason": "", "builder_version": builder_version()}
    log.info("builder version %s driving project %s",
             summary["builder_version"], project_id)

    try:
        store.init_jobs_table()
    except Exception:                                  # noqa: BLE001
        log.exception("could not prepare the jobs table")
        summary["reason"] = "the jobs table is unavailable"
        return summary

    # The trigger writes the job before asking for a task, so one should
    # already be here. Writing it only when there is NO row makes a task
    # started by hand do the right thing without re-opening a job that is
    # already finished.
    #
    # THIS IS NOT A TIDINESS DETAIL. `enqueue` deliberately re-opens a
    # SUCCEEDED job, because that is what a customer's explicit Continue
    # means. Render may retry a run it believes failed — including one
    # that actually finished — and an unconditional enqueue here would
    # turn that retry into a second full build of a finished book: a
    # second PDF, a second ZIP, and a second bill for the provider calls.
    try:
        existing = store.get_for_project(project_id)
        if existing is None:
            store.enqueue(project_id)
        elif str(existing.get("status")) == store.SUCCEEDED:
            summary["finished"] = True
            summary["reason"] = "already finished"
            return summary
    except Exception:                                  # noqa: BLE001
        log.exception("could not read the job for project %s", project_id)

    unclaimable = 0
    while True:
        if time.monotonic() >= deadline:
            summary["reason"] = "out of time; the next trigger resumes it"
            return summary

        outcome = executor.run_project(project_id, owner)

        if not outcome.get("claimed"):
            job = store.get_for_project(project_id) or {}
            status = job.get("status") or ""
            if status == store.SUCCEEDED:
                summary["finished"] = True
                summary["reason"] = "already finished"
                return summary
            if status == store.FAILED:
                summary["failed"] = True
                summary["reason"] = job.get("last_error") or "failed"
                return summary
            unclaimable += 1
            if unclaimable >= MAX_UNCLAIMABLE:
                summary["reason"] = "another task holds this book"
                return summary
            sleep(RETRY_SLEEP_SECONDS)
            continue

        unclaimable = 0
        summary["claims"] += 1

        # v1.8.1. The step-by-step screen asks for a SPECIFIC piece of work,
        # recorded on the job row by the website. Perform it here, on the
        # first claim that finds one, with the same function the website
        # would have called inline -- then let the ordinary build loop carry
        # on over the result. Taking the action clears it, so a Render retry
        # never performs it twice.
        job_id = outcome.get("job_id")
        if job_id:
            try:
                store.record_builder_version(int(job_id), summary["builder_version"])
            except Exception:                          # noqa: BLE001
                pass                                   # traceability, not the book
            try:
                from services.jobs.builder_actions import perform_pending

                done = perform_pending(project_id, int(job_id))
                if done.get("performed"):
                    summary["actions"] = int(summary.get("actions") or 0) + 1
                    summary["last_action"] = done.get("route") or ""
                if done.get("error"):
                    # One request failed; the book has not.
                    summary.setdefault("action_errors", []).append(done["error"])
            except Exception:                          # noqa: BLE001
                log.exception("requested action handling failed for %s", project_id)

        summary["units"] += int(outcome.get("units") or 0)
        if outcome.get("percent") is not None:
            summary["percent"] = outcome.get("percent")

        if outcome.get("finished"):
            summary["finished"] = True
            summary["reason"] = "finished"
            return summary
        if outcome.get("failed"):
            summary["failed"] = True
            summary["reason"] = str(outcome.get("error") or "failed")
            return summary
        if outcome.get("paused"):
            summary["paused"] = True
            summary["reason"] = "waiting for the customer"
            return summary
        if outcome.get("lease_lost"):
            summary["reason"] = "lease lost to another executor"
            return summary
        # Bounded claim completed and the book is not done: claim again.
