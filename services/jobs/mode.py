"""Which machine finishes the book — Upgrade 0, v1.8.0.

THE DEFECT THIS CLOSES
----------------------
A live Resume Build for "Container Gardening for Beginners" pushed the
Render web service past its memory limit. The book was being written
inside the same process that serves pages, so one customer's build could
take the whole site down with it.

The fix is not a bigger web service. It is that the web service stops
doing the heavy work at all. This module is the single switch that says
who does it.

THE TWO MODES
-------------
``inline``   (default)  The web process advances builds itself, exactly
                        as v1.7.29 shipped. Nothing about this module
                        changes behaviour until the variable is set, so
                        merging it is not a production change.

``workflow``            The web process never advances a build. It writes
                        the durable job and asks Render Workflows to run
                        it on its own instance, which starts on demand,
                        gets its own CPU and RAM, and disappears when the
                        book is done.

WHY A VARIABLE AND NOT A CODE PATH DELETED
------------------------------------------
Local Windows development has no Render, and must not need one. Inline
mode IS local development. Keeping both behind one variable means the
same code runs on the PC and in production, and the rollback for the
whole of v1.8.0 is deleting one environment variable.

NOTHING HERE READS A SECRET'S VALUE
-----------------------------------
``describe()`` is surfaced on a read-only route. It reports whether a
credential is configured, never what it is.
"""
from __future__ import annotations

import os

#: The web process advances builds itself. The v1.7.29 behaviour.
INLINE = "inline"

#: Builds run in a Render Workflow task. The web process only triggers.
WORKFLOW = "workflow"

#: The switch. Absent or unrecognised means inline, deliberately: a typo
#: must never silently stop books being built.
ENV_MODE = "FACTORY_EXECUTION_MODE"

#: Which workflow task to run, as "<workflow-service-name>/<task-name>".
#: Not a secret — it is a name, and it is reported by describe().
ENV_TASK = "FACTORY_WORKFLOW_TASK"

#: Render API credential used to trigger a task. Its VALUE is never read
#: by this module and never leaves the SDK.
ENV_API_KEY = "RENDER_API_KEY"

#: How long a triggered task may run before Render times it out. Render's
#: own default is 2 hours; a long illustrated book is comfortably inside
#: that, and this exists so the value is stated in one place.
ENV_TASK_TIMEOUT = "FACTORY_WORKFLOW_TASK_TIMEOUT_SECONDS"

DEFAULT_TASK_TIMEOUT_SECONDS = 7200

_WORKFLOW_SPELLINGS = frozenset(
    {"workflow", "workflows", "render_workflow", "render-workflow",
     "render_workflows", "render-workflows"}
)


def execution_mode() -> str:
    """Return ``inline`` or ``workflow``. Never raises, never guesses wrong.

    Anything that is not clearly the word "workflow" is inline. An unset,
    empty, misspelt or half-deployed variable therefore leaves the
    Factory building books the way it already does.
    """
    raw = str(os.environ.get(ENV_MODE) or "").strip().lower()
    return WORKFLOW if raw in _WORKFLOW_SPELLINGS else INLINE


def is_workflow_mode() -> bool:
    return execution_mode() == WORKFLOW


def is_inline_mode() -> bool:
    return execution_mode() == INLINE


def workflow_task() -> str:
    """The task identifier Render is asked to run, or "" if unset."""
    return str(os.environ.get(ENV_TASK) or "").strip()


def api_key_configured() -> bool:
    """Whether a Render credential exists. The value is never returned."""
    return bool(str(os.environ.get(ENV_API_KEY) or "").strip())


def task_timeout_seconds() -> int:
    try:
        value = int(str(os.environ.get(ENV_TASK_TIMEOUT) or "").strip())
    except (TypeError, ValueError):
        return DEFAULT_TASK_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_TASK_TIMEOUT_SECONDS


def is_configured() -> tuple[bool, str]:
    """Can workflow mode actually trigger anything? With the reason if not.

    Kept separate from ``is_workflow_mode`` so a half-configured service
    is visible on the status route rather than discovered by a customer
    whose book never starts.
    """
    if not is_workflow_mode():
        return False, "execution mode is inline"
    if not workflow_task():
        return False, f"{ENV_TASK} is not set"
    if not api_key_configured():
        return False, f"{ENV_API_KEY} is not set"
    return True, ""


def website_version() -> str:
    """The VERSION this web service is running, or "unknown"."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as handle:
            return handle.read().strip() or "unknown"
    except Exception:                                  # noqa: BLE001
        return "unknown"


def describe() -> dict:
    """Read-only summary for the execution-mode route. Contains no secrets.

    v1.8.1 adds the two versions. The website and the builder deploy from
    different Render services and can be on different commits; a builder that
    does not understand a requested action would otherwise fail silently, and
    this is the one page that can be checked without opening a shell.
    """
    ready, reason = is_configured()
    return {
        "website_version": website_version(),
        "builder_version_last_seen": _last_seen_builder_version(),
        "execution_mode": execution_mode(),
        "workflow_task": workflow_task(),
        "render_api_key_configured": api_key_configured(),
        "task_timeout_seconds": task_timeout_seconds(),
        "ready": ready,
        "reason": reason,
    }


def _last_seen_builder_version() -> str:
    """The VERSION reported by the most recent builder run, or "".

    Read from the job row the builder already writes, so this costs one small
    query and adds no new table. Empty means no run has reported yet -- which
    is itself worth seeing on a service that believes it is in workflow mode.
    """
    try:
        from services.jobs import store

        return store.last_builder_version()
    except Exception:                                  # noqa: BLE001
        return ""
