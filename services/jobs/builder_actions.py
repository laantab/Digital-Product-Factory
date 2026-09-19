"""Performing the customer's recorded action on the builder — v1.8.1.

The website records what the customer asked for on the durable job row
(services/jobs/store.set_requested_action). A workflow task reads it here,
performs it with the SAME function the website would have called inline
(services/ebook_workspace_actions), persists the result, and then lets the
ordinary build loop carry on.

WHY THE ACTION RUNS BEFORE THE BUILD LOOP
-----------------------------------------
"Replace this photograph, then continue" is one intention, not two. Running
the action first means the build advances over the customer's choice rather
than over the state that choice was meant to change -- so a replaced
photograph is the one that ends up in the preview, and a chosen cover is the
one that gets designed.

WHY A FAILED ACTION DOES NOT FAIL THE BOOK
------------------------------------------
An action is one customer request: a photograph that could not be fetched, a
layout that did not pass quality. The book itself is still fine, and the
build should keep going and report. Turning "that photograph was
unavailable" into a failed build would throw away the whole book over one
picture.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def perform_pending(project_id: int, job_id: int) -> dict:
    """Take the pending action for this job and perform it, at most once.

    Returns a small report. Never raises: the caller is a task run that must
    go on to build the book whatever happened to one requested action.
    """
    out = {"performed": False, "route": "", "action": "", "message": "",
           "error": ""}
    try:
        from services.jobs import store

        recorded = store.take_requested_action(int(job_id))
    except Exception:                                  # noqa: BLE001
        log.exception("could not read the requested action for job %s", job_id)
        return out

    if not recorded:
        return out

    route = str(recorded.get("route") or "")
    action = str(recorded.get("action") or "")
    payload = recorded.get("payload") if isinstance(recorded.get("payload"), dict) else {}
    out["route"], out["action"] = route, action

    try:
        import database
        from services import ebook_workspace_actions as wsa

        if not wsa.handles(route):
            # Manuscript, correction, research, titles and outlines are
            # stages the orchestrator already owns. There is nothing extra to
            # do here: advancing the build runs them, which is why they are
            # deliberately not handlers in that module.
            out["message"] = "handled by the build loop"
            return out

        project = database.get_project(int(project_id))
        if not project:
            out["error"] = "project not found"
            return out

        data = dict(project.get("data") or {})
        data, message = wsa.perform(data, project_id=int(project_id),
                                    route=route, action=action, payload=payload)
        database.update_project(int(project_id), None, data)
        out["performed"] = True
        out["message"] = message
        log.info("performed %s (%s) for project %s", route, action, project_id)
    except Exception as exc:                           # noqa: BLE001
        log.exception("requested action %s failed for project %s", route, project_id)
        out["error"] = f"{type(exc).__name__}"
    return out
