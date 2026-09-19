"""Durable job table — Upgrade 0, Phase 0B-5 (ebook-blocking slice).

WHY THIS EXISTS
---------------
The ebook build was driven entirely by a browser loop: `_ebookBuildLoop`
in static/js/app.js called POST /advance once per chapter. Close the tab
and the book stopped — which is exactly how a live customer's book came
to sit at "Writing your chapters (5 of 9)" forever.

The customer-facing promise is "You can leave this page." That has to be
true in architecture, not just in text. This table is the durable memory
that makes it true: the intention to finish a book survives the browser,
the request, the process and the deploy, because it is a row.

WHAT MAKES IT SURVIVE A RESTART
-------------------------------
Nothing is held in memory. A job is a row with a LEASE — an owner and an
expiry. An executor claims a job by compare-and-swap and extends the
lease while it works. If the process dies mid-chapter the lease simply
expires, and the next executor reclaims the job and carries on from the
persisted work. No cleanup step has to run for that to happen, which
matters: a recovery mechanism that itself depends on a clean shutdown is
no recovery mechanism at all.

The claim is a single conditional UPDATE rather than SELECT-then-UPDATE,
so two processes cannot both believe they own one job. It is written in
portable SQL (no FOR UPDATE SKIP LOCKED) so it behaves identically on
SQLite and PostgreSQL — the Factory runs on SQLite locally and PostgreSQL
in production, and a queue that only works on one of them would be
untestable exactly where it matters.
"""
from __future__ import annotations

import os
import socket
import uuid
from datetime import datetime, timedelta, timezone

QUEUED = "QUEUED"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"

#: How long a claim is good for. Long enough for one bounded work unit
#: (one chapter), short enough that a dead process is reclaimed promptly.
LEASE_SECONDS = 180

#: A job that has been attempted this many times stops retrying on its own.
MAX_ATTEMPTS = 60

KIND_EBOOK_BUILD = "ebook_build"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _future(seconds: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def executor_id() -> str:
    """Identifies one executor, so a lease has a visible owner."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def init_jobs_table() -> None:
    """Create the table. Idempotent; DDL is dialect-translated on the way."""
    import database

    conn = database.get_conn()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'QUEUED',
                lease_owner TEXT NOT NULL DEFAULT '',
                lease_expires_at TEXT NOT NULL DEFAULT '',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                workflow_run_id TEXT NOT NULL DEFAULT '',
                workflow_triggered_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS jobs_project_kind_idx "
            "ON jobs (project_id, kind)"
        )
        conn.commit()
    finally:
        conn.close()

    # A production database created before v1.8.0 already has this table
    # without the two workflow columns, and CREATE TABLE IF NOT EXISTS will
    # not add them. This does, and it is a no-op everywhere else.
    ensure_trigger_columns()


_COLUMNS = ("id", "project_id", "kind", "status", "lease_owner",
            "lease_expires_at", "attempts", "last_error", "created_at", "updated_at")


def _row_to_dict(row) -> dict:
    return {k: (row.get(k) if isinstance(row, dict) else row[k]) for k in _COLUMNS}


def enqueue(project_id: int, kind: str = KIND_EBOOK_BUILD, *,
            reset_attempts: bool = False) -> dict:
    """Record the intention to finish this work. Idempotent per project+kind.

    A repeat enqueue re-queues the existing job rather than creating a
    second one: two jobs for one book would race two executors onto the
    same chapter.

    `reset_attempts` is for the customer's explicit Continue and nothing
    else. `claim_next` skips any job at MAX_ATTEMPTS, so re-opening an
    exhausted job to QUEUED without clearing its attempts left it queued
    forever and never claimed, while the screen span "being picked back
    up" — the exact kind of lie v1.7.25 set out to remove. A human saying
    "keep going" is a fresh start; an automatic retry is not, so the
    ceiling still holds for every ordinary enqueue (v1.7.26).
    """
    import database

    now = _now()
    conn = database.get_conn()
    try:
        existing = conn.execute(
            "SELECT * FROM jobs WHERE project_id=? AND kind=?",
            (int(project_id), str(kind)),
        ).fetchone()
        if existing is not None:
            job = _row_to_dict(existing)
            if job["status"] in (QUEUED, RUNNING):
                return job
            # A finished or failed job is re-opened, never duplicated.
            if reset_attempts:
                conn.execute(
                    "UPDATE jobs SET status=?, lease_owner='', lease_expires_at='',"
                    " last_error='', attempts=0, updated_at=? WHERE id=?",
                    (QUEUED, now, job["id"]),
                )
            else:
                conn.execute(
                    "UPDATE jobs SET status=?, lease_owner='', lease_expires_at='',"
                    " last_error='', updated_at=? WHERE id=?",
                    (QUEUED, now, job["id"]),
                )
            conn.commit()
            return {**job, "status": QUEUED,
                    "attempts": 0 if reset_attempts else job["attempts"]}

        conn.execute(
            "INSERT INTO jobs (project_id, kind, status, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (int(project_id), str(kind), QUEUED, now, now),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM jobs WHERE project_id=? AND kind=?",
            (int(project_id), str(kind)),
        ).fetchone()
        return _row_to_dict(row) if row is not None else {}
    finally:
        conn.close()


def claim_next(owner: str, kind: str = KIND_EBOOK_BUILD) -> dict | None:
    """Atomically take ownership of one runnable job, or return None.

    Runnable means QUEUED, or RUNNING with an EXPIRED lease — which is how
    a job owned by a process that died is picked up again without any
    cleanup having run.

    The claim is one conditional UPDATE. Two executors racing will both
    issue it; exactly one will see a changed row.
    """
    import database

    now = _now()
    conn = database.get_conn()
    try:
        candidates = conn.execute(
            "SELECT * FROM jobs WHERE kind=? AND status IN (?, ?)"
            " AND attempts < ? ORDER BY updated_at LIMIT 20",
            (str(kind), QUEUED, RUNNING, MAX_ATTEMPTS),
        ).fetchall()
        for row in candidates or []:
            job = _row_to_dict(row)
            if job["status"] == RUNNING and str(job["lease_expires_at"] or "") > now:
                continue                      # someone else holds a live lease
            cur = conn.execute(
                "UPDATE jobs SET status=?, lease_owner=?, lease_expires_at=?,"
                " attempts=attempts+1, updated_at=? "
                "WHERE id=? AND status=? AND lease_expires_at=?",
                (RUNNING, owner, _future(LEASE_SECONDS), now,
                 job["id"], job["status"], job["lease_expires_at"]),
            )
            conn.commit()
            if int(getattr(cur, "rowcount", 0) or 0) == 1:
                return {**job, "status": RUNNING, "lease_owner": owner,
                        "attempts": int(job["attempts"]) + 1}
        return None
    finally:
        conn.close()


def heartbeat(job_id: int, owner: str) -> bool:
    """Extend the lease. Only the owner can; a lost lease is never taken back."""
    import database

    conn = database.get_conn()
    try:
        cur = conn.execute(
            "UPDATE jobs SET lease_expires_at=?, updated_at=? "
            "WHERE id=? AND lease_owner=? AND status=?",
            (_future(LEASE_SECONDS), _now(), int(job_id), str(owner), RUNNING),
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0) == 1
    finally:
        conn.close()


def finish(job_id: int, owner: str, *, status: str, error: str = "") -> bool:
    """Close a job out. Only the owner may."""
    import database

    conn = database.get_conn()
    try:
        cur = conn.execute(
            "UPDATE jobs SET status=?, lease_owner='', lease_expires_at='',"
            " last_error=?, updated_at=? WHERE id=? AND lease_owner=?",
            (str(status), str(error)[:500], _now(), int(job_id), str(owner)),
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0) == 1
    finally:
        conn.close()


def release(job_id: int, owner: str, *, error: str = "") -> bool:
    """Return a job to the queue without marking it finished.

    Used when a bounded unit completes but the book is not done, so the
    next tick — in this process or another — picks it straight up.
    """
    import database

    conn = database.get_conn()
    try:
        cur = conn.execute(
            "UPDATE jobs SET status=?, lease_owner='', lease_expires_at='',"
            " last_error=?, updated_at=? WHERE id=? AND lease_owner=?",
            (QUEUED, str(error)[:500], _now(), int(job_id), str(owner)),
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0) == 1
    finally:
        conn.close()


def get_for_project(project_id: int, kind: str = KIND_EBOOK_BUILD) -> dict | None:
    import database

    conn = database.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE project_id=? AND kind=?",
            (int(project_id), str(kind)),
        ).fetchone()
    finally:
        conn.close()
    return _row_to_dict(row) if row is not None else None


def counts() -> dict:
    import database

    conn = database.get_conn()
    out: dict = {}
    try:
        for status in (QUEUED, RUNNING, SUCCEEDED, FAILED):
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM jobs WHERE status=?", (status,)).fetchone()
            out[status] = int(row["n"] if isinstance(row, dict) else row[0])
    except Exception:
        return {}
    finally:
        conn.close()
    return out


# ===========================================================================
# Workflow triggering — v1.8.0.
#
# In workflow mode the web process does not build the book; it writes the
# job and asks Render to run a task. Two extra facts have to be durable
# for that to be safe:
#
#   * WHEN a task was last asked for, so a customer who clicks Continue
#     five times does not start five tasks on the same book — which would
#     race five instances onto one chapter and bill for all of them.
#   * WHICH task run was started, so a stuck book can be traced to a
#     Render run without guessing.
#
# Both live on the existing job row. A second table would have to be kept
# in step with the first, and the row is already the thing that survives
# a restart.
# ===========================================================================

#: A job may not be re-triggered inside this window. Long enough that an
#: impatient customer cannot fan out tasks, short enough that a task which
#: died before claiming anything is retried promptly.
TRIGGER_COOLDOWN_SECONDS = 120

_TRIGGER_COLUMNS = (
    ("workflow_run_id", "TEXT NOT NULL DEFAULT ''"),
    ("workflow_triggered_at", "TEXT NOT NULL DEFAULT ''"),
    # v1.8.1. The step-by-step screen asks for a SPECIFIC piece of work --
    # replace this photograph, use this uploaded cover, rebuild the preview --
    # not just "carry on with the book". `build_ebook(project_id)` takes only
    # a project id, so the request itself has to be durable somewhere the task
    # can read it. It lives on the job row rather than in the task arguments
    # so the task signature, the duplicate guard and the lease logic are all
    # unchanged from v1.8.0.
    ("requested_action", "TEXT NOT NULL DEFAULT ''"),
    ("requested_action_at", "TEXT NOT NULL DEFAULT ''"),
    # v1.8.1. The website and the builder are two Render services and can be
    # running different commits. A builder on v1.8.0 does not understand a
    # requested action: it would build the book straight through and the
    # customer's chosen photograph would never appear, with nothing saying
    # why. Recording the version that actually did the work makes that
    # visible on /ebook/execution-mode.
    ("builder_version", "TEXT NOT NULL DEFAULT ''"),
)


def ensure_trigger_columns() -> None:
    """Add the workflow columns if they are not there. Idempotent.

    Each ALTER gets its own connection: PostgreSQL aborts a transaction
    on a failed statement, so sharing one connection would make the first
    "column already exists" poison every ALTER after it.
    """
    import database

    for name, ddl in _TRIGGER_COLUMNS:
        conn = database.get_conn()
        try:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {ddl}")
            conn.commit()
        except Exception:                              # noqa: BLE001
            # Already present. This is the normal path on every boot after
            # the first, and it is not worth logging.
            try:
                conn.rollback()
            except Exception:                          # noqa: BLE001
                pass
        finally:
            conn.close()


def _trigger_cutoff(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def claim_trigger(job_id: int, *, cooldown: int = TRIGGER_COOLDOWN_SECONDS) -> bool:
    """Win the right to start ONE workflow task for this job.

    Returns True at most once per cooldown window, and never while another
    task holds a live lease on the job — a running task is already doing
    the work, so a second one would only race it.

    This is one conditional UPDATE, not a read followed by a write, so two
    web instances handling two clicks at the same moment cannot both win.
    """
    import database

    now = _now()
    conn = database.get_conn()
    try:
        cur = conn.execute(
            "UPDATE jobs SET workflow_triggered_at=?, updated_at=? "
            "WHERE id=? "
            "  AND (workflow_triggered_at IS NULL OR workflow_triggered_at=''"
            "       OR workflow_triggered_at < ?) "
            "  AND NOT (status=? AND lease_expires_at > ?)",
            (now, now, int(job_id), _trigger_cutoff(cooldown), RUNNING, now),
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0) == 1
    except Exception:                                  # noqa: BLE001
        # A missing column means ensure_trigger_columns has not run. Refuse
        # to trigger rather than trigger without protection.
        try:
            conn.rollback()
        except Exception:                              # noqa: BLE001
            pass
        return False
    finally:
        conn.close()


def record_workflow_run(job_id: int, run_id: str) -> bool:
    """Remember which Render task run was started for this job."""
    import database

    conn = database.get_conn()
    try:
        cur = conn.execute(
            "UPDATE jobs SET workflow_run_id=?, updated_at=? WHERE id=?",
            (str(run_id or "")[:200], _now(), int(job_id)),
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0) == 1
    except Exception:                                  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:                              # noqa: BLE001
            pass
        return False
    finally:
        conn.close()


def trigger_info(project_id: int, kind: str = KIND_EBOOK_BUILD) -> dict:
    """What we know about this book's last workflow trigger. Read-only."""
    import database

    conn = database.get_conn()
    try:
        row = conn.execute(
            "SELECT workflow_run_id, workflow_triggered_at FROM jobs"
            " WHERE project_id=? AND kind=?",
            (int(project_id), str(kind)),
        ).fetchone()
    except Exception:                                  # noqa: BLE001
        return {}
    finally:
        conn.close()
    if row is None:
        return {}

    def _get(key):
        return (row.get(key) if isinstance(row, dict) else row[key]) or ""

    return {"workflow_run_id": _get("workflow_run_id"),
            "workflow_triggered_at": _get("workflow_triggered_at")}


def claim_for_project(owner: str, project_id: int,
                      kind: str = KIND_EBOOK_BUILD) -> dict | None:
    """Claim THIS book's job, rather than whichever is next in the queue.

    A workflow task is started for one project and must work on that one:
    claiming "the next runnable job" would let a task started for book A
    pick up book B, which makes a run id meaningless and makes two tasks
    able to swap books underneath each other.

    Same conditional-UPDATE discipline as claim_next, so the running web
    process and a starting task cannot both own the row.
    """
    import database

    now = _now()
    conn = database.get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE project_id=? AND kind=?",
            (int(project_id), str(kind)),
        ).fetchone()
        if row is None:
            return None
        job = _row_to_dict(row)
        if job["status"] not in (QUEUED, RUNNING):
            return None
        if int(job["attempts"]) >= MAX_ATTEMPTS:
            return None
        if job["status"] == RUNNING and str(job["lease_expires_at"] or "") > now:
            return None
        cur = conn.execute(
            "UPDATE jobs SET status=?, lease_owner=?, lease_expires_at=?,"
            " attempts=attempts+1, updated_at=? "
            "WHERE id=? AND status=? AND lease_expires_at=?",
            (RUNNING, owner, _future(LEASE_SECONDS), now,
             job["id"], job["status"], job["lease_expires_at"]),
        )
        conn.commit()
        if int(getattr(cur, "rowcount", 0) or 0) == 1:
            return {**job, "status": RUNNING, "lease_owner": owner,
                    "attempts": int(job["attempts"]) + 1}
        return None
    finally:
        conn.close()


# ===========================================================================
# The customer's requested action — v1.8.1.
#
# v1.8.0 moved "Build My Ebook" to the builder. That button means one thing:
# finish this book. The step-by-step screen is different — every button on it
# asks for a particular piece of work, and several of them carry the
# customer's own choice with them (which photograph, which layout, which
# theme, which uploaded file).
#
# The action is written on the job row, in the same UPDATE discipline as
# everything else here, because the row is already the thing that survives a
# restart and is already what the builder claims. Passing the action as a
# task argument instead would change `build_ebook`'s signature, and with it
# the duplicate guard and the lease logic that v1.8.0's tests hold in place.
#
# TAKE, NOT READ. `take_requested_action` clears the action in the same
# conditional UPDATE that returns it, so an action is performed at most once
# even if two tasks race or Render retries a run. "Replace this photograph"
# executed twice is a second paid image and a second surprise for the
# customer.
# ===========================================================================


def set_requested_action(job_id: int, action: dict) -> bool:
    """Record what the customer actually asked for. Overwrites any pending one.

    Overwriting is correct: a customer who clicks "AI alternative" and then
    "replace photo" before the first has run wants the second. Only the most
    recent request is meaningful, and keeping a queue of superseded image
    requests would spend money on choices the customer has already changed.
    """
    import json

    import database

    conn = database.get_conn()
    try:
        cur = conn.execute(
            "UPDATE jobs SET requested_action=?, requested_action_at=?,"
            " updated_at=? WHERE id=?",
            (json.dumps(action or {}, separators=(",", ":"))[:8000],
             _now(), _now(), int(job_id)),
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0) == 1
    except Exception:                                  # noqa: BLE001
        # A missing column means ensure_trigger_columns has not run. Refuse
        # rather than silently drop the customer's choice.
        try:
            conn.rollback()
        except Exception:                              # noqa: BLE001
            pass
        return False
    finally:
        conn.close()


def peek_requested_action(project_id: int, kind: str = KIND_EBOOK_BUILD) -> dict:
    """Read the pending action WITHOUT clearing it. For status routes only."""
    import json

    import database

    conn = database.get_conn()
    try:
        row = conn.execute(
            "SELECT requested_action FROM jobs WHERE project_id=? AND kind=?",
            (int(project_id), str(kind)),
        ).fetchone()
    except Exception:                                  # noqa: BLE001
        return {}
    finally:
        conn.close()
    if row is None:
        return {}
    raw = (row.get("requested_action") if isinstance(row, dict)
           else row["requested_action"]) or ""
    try:
        parsed = json.loads(raw) if raw else {}
    except Exception:                                  # noqa: BLE001
        return {}
    return parsed if isinstance(parsed, dict) else {}


def take_requested_action(job_id: int) -> dict:
    """Return the pending action and clear it, atomically. At most once.

    The clear is part of the same conditional UPDATE as the read's guard, so
    two executors cannot both come away believing they own the action. An
    action performed twice would mean a second paid image or a second cover.
    """
    import json

    import database

    pending = ""
    conn = database.get_conn()
    try:
        row = conn.execute(
            "SELECT requested_action FROM jobs WHERE id=?", (int(job_id),)
        ).fetchone()
        if row is None:
            return {}
        pending = (row.get("requested_action") if isinstance(row, dict)
                   else row["requested_action"]) or ""
        if not str(pending).strip():
            return {}
        cur = conn.execute(
            "UPDATE jobs SET requested_action='', updated_at=? "
            "WHERE id=? AND requested_action=?",
            (_now(), int(job_id), pending),
        )
        conn.commit()
        if int(getattr(cur, "rowcount", 0) or 0) != 1:
            # Someone else took it first. Theirs to perform, not ours.
            return {}
    except Exception:                                  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:                              # noqa: BLE001
            pass
        return {}
    finally:
        conn.close()

    try:
        parsed = json.loads(pending)
    except Exception:                                  # noqa: BLE001
        return {}
    return parsed if isinstance(parsed, dict) else {}


def record_builder_version(job_id: int, version: str) -> bool:
    """Remember which build of the builder claimed this job."""
    import database

    conn = database.get_conn()
    try:
        cur = conn.execute(
            "UPDATE jobs SET builder_version=?, updated_at=? WHERE id=?",
            (str(version or "")[:40], _now(), int(job_id)),
        )
        conn.commit()
        return int(getattr(cur, "rowcount", 0) or 0) == 1
    except Exception:                                  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:                              # noqa: BLE001
            pass
        return False
    finally:
        conn.close()


def last_builder_version() -> str:
    """The most recently reported builder version, or "".

    Empty on a service that believes it is in workflow mode means no builder
    run has ever reported -- which is exactly what was true on the evening of
    2026-09-18, when the builder showed zero runs all night.
    """
    import database

    conn = database.get_conn()
    try:
        row = conn.execute(
            "SELECT builder_version FROM jobs WHERE builder_version <> ''"
            " ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
    except Exception:                                  # noqa: BLE001
        return ""
    finally:
        conn.close()
    if row is None:
        return ""
    return str((row.get("builder_version") if isinstance(row, dict)
                else row["builder_version"]) or "")
