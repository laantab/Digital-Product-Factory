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
                updated_at TEXT NOT NULL
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
