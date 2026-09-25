"""The server-side ebook executor — Upgrade 0, Phase 0B-5 slice.

This is the thing that makes "You can leave this page" true.

Previously the only thing advancing a build was a loop in the customer's
browser. This drives the SAME orchestrator — `advance_build`, one bounded
unit per call, checkpointing after each — from the server instead, under
a durable lease.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not reimplement the build. Every stage, every QA gate, every
chapter, the attempt ceilings and the idempotency keys stay exactly where
they are in `services/ebook_build_orchestrator`. The only thing that
changes is WHO calls advance: the server, not the browser. That keeps the
blast radius of this change to "who drives", which is the actual defect.

RESUMPTION IS THE ORCHESTRATOR'S, NOT OURS
------------------------------------------
`advance_build` already starts from the first incomplete stage and
already refuses to redo a validated one, so a book stopped after chapter
five resumes at chapter six because that is what the orchestrator does
when asked to advance. Completed chapters are never regenerated here,
because nothing here decides what to generate.

CRASH SAFETY
------------
Work is checkpointed by the orchestrator after every bounded unit, and
the lease is extended between units. Kill the process mid-chapter and the
lease expires; the next executor claims the job and asks the orchestrator
to advance, which resumes from the last checkpoint. At most one chapter
is repeated, and repeating a chapter is safe because the orchestrator
claims a stage before working on it.
"""
from __future__ import annotations

import logging

from services.jobs import store

log = logging.getLogger(__name__)

#: Bounded units per claim. The job is released back to the queue after
#: this many, so one book can never monopolise an executor and a long
#: book still makes steady progress across ticks.
UNITS_PER_CLAIM = 12


def run_one_job(owner: str | None = None) -> dict:
    """Claim one job and advance it. Returns what happened.

    Safe to call from anywhere and at any frequency: if there is nothing
    to do it claims nothing and returns immediately.
    """
    owner = owner or store.executor_id()
    job = store.claim_next(owner)
    if not job:
        return {"claimed": False, "reason": "nothing runnable"}
    return _drive(job, owner)


def drain(max_jobs: int = 25, owner: str | None = None) -> dict:
    """Advance runnable jobs until there are none left or the cap is hit."""
    owner = owner or store.executor_id()
    ran, finished = 0, 0
    for _ in range(max(1, int(max_jobs))):
        outcome = run_one_job(owner)
        if not outcome.get("claimed"):
            break
        ran += 1
        if outcome.get("finished"):
            finished += 1
    return {"jobs_run": ran, "jobs_finished": finished, "counts": store.counts()}


def run_project(project_id: int, owner: str | None = None, *,
                units: int | None = None) -> dict:
    """Advance ONE named book, claiming only that book's job.

    This is what a Render Workflow task calls. A task is started for one
    project and must work on that one: `run_one_job` takes whichever job
    is next in the queue, so a task started for book A could silently
    spend its whole run on book B — which makes the run id meaningless
    when a customer asks what happened to their book, and lets two tasks
    swap books underneath each other.

    Everything else is identical to `run_one_job`, deliberately: the same
    lease, the same heartbeat, the same orchestrator, the same bounded
    units, the same release-not-fail on a transient error. The executor
    still has no concept of a chapter, so it still cannot regenerate one.
    """
    owner = owner or store.executor_id()
    job = store.claim_for_project(owner, int(project_id))
    if not job:
        return {"claimed": False, "reason": "not runnable",
                "project_id": int(project_id)}
    return _drive(job, owner, units=units)


def _drive(job: dict, owner: str, *, units: int | None = None) -> dict:
    """Advance an already-claimed job. Shared by run_one_job and run_project."""
    project_id = int(job["project_id"])
    budget = int(units) if units and int(units) > 0 else UNITS_PER_CLAIM
    result = {"claimed": True, "job_id": job["id"], "project_id": project_id,
              "units": 0, "finished": False, "failed": False}

    try:
        from services.ebook_build_orchestrator import advance_build

        for _ in range(budget):
            status = advance_build(project_id)
            result["units"] += 1
            result["percent"] = status.get("percent")

            if status.get("finished"):
                result["finished"] = True
                store.finish(job["id"], owner, status=store.SUCCEEDED)
                return result
            if status.get("failed"):
                result["failed"] = True
                store.finish(job["id"], owner, status=store.FAILED,
                             error=str(status.get("message") or "")[:500])
                return result
            if status.get("awaiting_picture_approval"):
                # v1.9.6: waiting for the customer's Approve All Visuals.
                # Not a failure; the builder stops and spends nothing more.
                result["paused"] = True
                store.release(job["id"], owner)
                return result
            if status.get("paused_after"):
                # A deliberate hold for the customer to read something.
                # Not a failure, and not ours to push past.
                result["paused"] = True
                store.release(job["id"], owner)
                return result

            # Still going: keep the lease alive before the next unit.
            if not store.heartbeat(job["id"], owner):
                # The lease was lost (this process stalled long enough for
                # another executor to reclaim it). Stop rather than race.
                result["lease_lost"] = True
                return result

        # Bounded: hand the job back so another tick continues it.
        store.release(job["id"], owner)
        return result

    except Exception as exc:                          # noqa: BLE001
        log.exception("ebook executor failed for project %s", project_id)
        result["failed"] = True
        result["error"] = f"{type(exc).__name__}"
        # Released, not failed: the attempt counter and the orchestrator's
        # own ceilings decide when to stop trying, so a transient provider
        # error does not permanently kill a customer's book.
        store.release(job["id"], owner, error=f"{type(exc).__name__}: {exc}"[:500])
        return result
