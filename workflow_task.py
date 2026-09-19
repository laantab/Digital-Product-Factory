"""Render Workflows entrypoint — v1.8.0.

This file is the whole of the Factory's workflow service. Render runs it
with `python workflow_task.py`; the SDK registers the tasks below and
then waits for runs to be dispatched to it.

It is deliberately four lines of logic. Everything the task does lives in
`services/jobs/workflow_runner`, which imports no cloud SDK, so the
behaviour is testable on a Windows PC with no Render account and the
local development experience is unchanged.

WHY THE BUILDER IS ITS OWN SERVICE
----------------------------------
A live Resume Build pushed the web service past its memory limit, because
the book was being written inside the process that serves pages. Here the
book gets its own instance, started on demand, with its own CPU and RAM,
which shuts down when the book is done. The website keeps serving pages
while a book is being written, and neither can take the other down.
"""
from __future__ import annotations

import logging
import os
import sys

# The repository root, so `services.*` imports work however the service
# was started.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    level=os.environ.get("FACTORY_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("factory.workflow")

from render import Retry, TaskContext, Workflows      # noqa: E402

from services.jobs import mode                         # noqa: E402
from services.jobs.workflow_runner import run_build    # noqa: E402

#: Compute for one book. `flex` is up to 1 CPU and 4 GB, started on demand
#: and billed for what it uses — eight times the memory the 512 MB web
#: service had when a live Resume Build exhausted it. Deliberately NOT
#: `starter`, which is 512 MB: that is the size that already failed.
#: Overridable by environment so it can be raised without a code change.
TASK_PLAN = os.environ.get("FACTORY_WORKFLOW_PLAN", "flex").strip() or "flex"

#: Retries are safe because the work is a leased row and the orchestrator
#: checkpoints after every bounded unit: a retry resumes from the last
#: checkpoint rather than starting the book again. Few and slow, because
#: a provider outage is the usual cause and hammering it helps nobody.
TASK_RETRY = Retry(max_retries=3, wait_duration_ms=30_000, backoff_scaling=2.0)

app = Workflows()


@app.task(timeout_seconds=mode.task_timeout_seconds(), plan=TASK_PLAN,
          retry=TASK_RETRY)
def build_ebook(ctx: TaskContext, project_id: int) -> dict:
    """Finish the ebook for one project, then exit.

    Retry-safe by construction: the work is a leased row and the
    orchestrator checkpoints after every bounded unit, so a retried run
    resumes from the last checkpoint, and a book that already SUCCEEDED
    is returned as finished without being rebuilt or exported twice.
    """
    log.info("workflow task starting for project %s", project_id)
    summary = run_build(int(project_id))
    log.info("workflow task finished for project %s: %s", project_id, summary)
    return summary


def _version() -> str:
    """The VERSION file next to this entrypoint, or "unknown"."""
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "VERSION"), encoding="utf-8") as handle:
            return handle.read().strip() or "unknown"
    except Exception:                                  # noqa: BLE001
        return "unknown"


if __name__ == "__main__":
    # v1.8.1. THE TWO SERVICES CAN RUN DIFFERENT COMMITS. The website deploys
    # from `main`; the builder was created from `feature/v1.8.0-workflows`. A
    # builder still running v1.8.0 would not understand a requested action at
    # all -- it would claim the job, build the book straight through, and the
    # customer's chosen photograph would never appear, with nothing in any log
    # saying why. Printing the version at start makes that mismatch visible in
    # the first line of the run rather than in a confused customer.
    log.info("Digital Product Factory workflow service starting (VERSION %s)",
             _version())
    app.start()
