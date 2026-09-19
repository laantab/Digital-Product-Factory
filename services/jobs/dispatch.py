"""Who gets the work — v1.8.0.

There is exactly ONE place in the application that decides whether a book
is built by the web process or by a Render Workflow task, and this is it.
`app.py` calls `hand_off` and does not know or care which mode is set.

Keeping the decision in one function is what stops the two modes turning
into two half-maintained execution paths. Adding a third caller in app.py
that forgets to check the mode is how a "workflow-only" service quietly
starts building books in the web process again — which is the memory
failure this release exists to fix.
"""
from __future__ import annotations

import logging

from services.jobs import mode, workflow_trigger

log = logging.getLogger(__name__)


def hand_off(project_id: int, *, reset_attempts: bool = False) -> dict:
    """Make the server own finishing this book, whichever mode is set.

    Inline: write the job and make sure the in-process ticker is running,
    exactly as v1.7.29 did.

    Workflow: write the job and ask Render to run it. The web process
    starts no ticker at all, so it never advances a build.

    Never raises. A queueing or triggering problem must never stop a
    customer starting a book.
    """
    outcome = workflow_trigger.trigger(int(project_id),
                                       reset_attempts=reset_attempts)
    if mode.is_workflow_mode():
        return outcome

    try:
        from services.jobs.runner import start as _start_executor

        outcome["executor_started"] = bool(_start_executor())
    except Exception:                                  # noqa: BLE001
        log.exception("could not start the in-process ebook executor")
        outcome["executor_started"] = False
    return outcome
