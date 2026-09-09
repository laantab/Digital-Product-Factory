"""In-memory progress for long server-side actions.

Generating an 8-chapter manuscript is one HTTP request that makes eight
sequential provider calls and can run for minutes. The browser had no way to
tell that apart from a hung app: the button simply sat there. This module lets
a long action publish "chapter 3 of 8" while it runs, and a cheap polling
endpoint hand that to the page.

Deliberately simple and dependency-free:

* process-local and in-memory — progress is a live view of work happening in
  this process, never persisted state and never a source of truth for anything;
* thread-safe, because Flask serves the polling GET on another thread while the
  worker thread is still inside the POST;
* self-pruning, so an abandoned job cannot leak memory;
* never raises into the caller. A progress update failing must not be able to
  break the real work it is reporting on, so every public call swallows its own
  errors.
"""
from __future__ import annotations

import threading
import time
from typing import Any

# A finished job stays readable for a short while so the page can poll once
# more and paint the final state; an abandoned one ages out on the same clock.
RETENTION_SECONDS = 300.0
MAX_JOBS = 200

_LOCK = threading.Lock()
_JOBS: dict[str, dict[str, Any]] = {}


def job_key(kind: str, identifier: Any) -> str:
    """Stable key for one long action on one record, e.g. ``ebook:21312``."""
    return f"{str(kind).strip() or 'job'}:{identifier}"


def _prune_locked(now: float) -> None:
    stale = [k for k, v in _JOBS.items() if now - float(v.get("updated_at") or 0) > RETENTION_SECONDS]
    for key in stale:
        _JOBS.pop(key, None)
    if len(_JOBS) > MAX_JOBS:
        for key in sorted(_JOBS, key=lambda k: _JOBS[k].get("updated_at") or 0)[: len(_JOBS) - MAX_JOBS]:
            _JOBS.pop(key, None)


def start(key: str, *, action: str = "", total: int = 0, label: str = "") -> None:
    """Begin (or restart) a job. Any earlier run under this key is replaced."""
    try:
        now = time.time()
        with _LOCK:
            _prune_locked(now)
            _JOBS[str(key)] = {
                "active": True,
                "action": str(action or ""),
                "label": str(label or ""),
                "total": max(int(total or 0), 0),
                "done": 0,
                "step_label": "",
                "status": "running",
                "message": "",
                "started_at": now,
                "updated_at": now,
            }
    except Exception:  # noqa: BLE001 - progress must never break the real work
        pass


def advance(key: str, *, done: int | None = None, step_label: str = "", total: int | None = None) -> None:
    """Record a completed unit of work (or just relabel the current step)."""
    try:
        now = time.time()
        with _LOCK:
            job = _JOBS.get(str(key))
            if not job:
                return
            if total is not None:
                job["total"] = max(int(total), 0)
            if done is not None:
                job["done"] = max(int(done), 0)
            if step_label:
                job["step_label"] = str(step_label)
            job["updated_at"] = now
    except Exception:  # noqa: BLE001
        pass


def finish(key: str, *, status: str = "done", message: str = "") -> None:
    """Mark the job finished. It stays readable for RETENTION_SECONDS."""
    try:
        now = time.time()
        with _LOCK:
            job = _JOBS.get(str(key))
            if not job:
                return
            job["active"] = False
            job["status"] = str(status or "done")
            job["message"] = str(message or "")
            job["updated_at"] = now
    except Exception:  # noqa: BLE001
        pass


def read(key: str) -> dict[str, Any]:
    """Current progress for a key. Always a dict; unknown keys read as idle."""
    try:
        now = time.time()
        with _LOCK:
            _prune_locked(now)
            job = _JOBS.get(str(key))
            if not job:
                return {"active": False, "status": "idle", "done": 0, "total": 0}
            snapshot = dict(job)
        snapshot["elapsed_seconds"] = round(max(now - float(snapshot.get("started_at") or now), 0.0), 1)
        snapshot.pop("started_at", None)
        snapshot.pop("updated_at", None)
        total = int(snapshot.get("total") or 0)
        done = int(snapshot.get("done") or 0)
        snapshot["percent"] = int(round(100 * min(done / total, 1.0))) if total > 0 else None
        return snapshot
    except Exception:  # noqa: BLE001
        return {"active": False, "status": "idle", "done": 0, "total": 0}


def clear(key: str) -> None:
    try:
        with _LOCK:
            _JOBS.pop(str(key), None)
    except Exception:  # noqa: BLE001
        pass
