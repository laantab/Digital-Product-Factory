"""PostgreSQL cutover operations — Upgrade 0, Phase 0B-4.

Runs on the Render instance, which is the only machine that can reach
both `/var/data/projects.db` and the private PostgreSQL endpoint.

THE SEQUENCE
------------
    VERIFIED SQLITE BACKUP -> SCHEMA -> IMPORT -> PARITY -> (owner flips
    FACTORY_DB_BACKEND) -> HEALTH -> SMOKE

Fail-closed at every gate. The SQLite file is never deleted, never
written by this module, and remains the rollback: removing
`FACTORY_DB_BACKEND` puts the Factory straight back on it.

No credential is ever printed. Connection details are reported as
presence only.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from datetime import datetime, timezone

from services.db import dialect
from services.db.connection import BACKEND_VAR, connect, init_postgres_schema, use_postgres
from services.db.migrate_postgres import (
    TABLES,
    export_plan,
    import_into,
    read_rows,
    verify_parity,
)


def sqlite_path() -> str:
    import database

    return database.DB_PATH


def _sha_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def status() -> dict:
    """READ ONLY. Where things stand, with no secret in the output."""
    src = sqlite_path()
    url = dialect.database_url()
    report = {
        "ok": True,
        "sqlite_path": src,
        "sqlite_exists": os.path.exists(src),
        "sqlite_bytes": os.path.getsize(src) if os.path.exists(src) else 0,
        "on_persistent_disk": src.startswith("/var/data"),
        "database_url_present": bool(url),
        "database_url_is_postgres": dialect.is_postgres(),
        f"{BACKEND_VAR}": str(os.environ.get(BACKEND_VAR) or "(unset -> sqlite)"),
        "app_uses_postgres": use_postgres(),
        "storage_driver": str(os.environ.get("FACTORY_STORAGE_DRIVER") or "(unset -> local)"),
    }
    if os.path.exists(src):
        report["sqlite_inventory"] = export_plan(src)["tables"]
    if url:
        try:
            conn = connect()
            try:
                counts = {}
                for table in TABLES:
                    try:
                        cur = conn.execute(f"SELECT COUNT(*) AS n FROM {table}")
                        row = cur.fetchone()
                        counts[table] = int(row["n"] if isinstance(row, dict) else row[0])
                    except Exception:
                        counts[table] = None      # table not created yet
                report["postgres_reachable"] = True
                report["postgres_counts"] = counts
            finally:
                conn.close()
        except Exception as exc:
            report["postgres_reachable"] = False
            report["postgres_error"] = type(exc).__name__
    return report


def backup_sqlite(label: str = "PRE-POSTGRES-CUTOVER") -> dict:
    """Checkpointed, timestamped, checksum-verified copy beside the source."""
    src = sqlite_path()
    if not os.path.exists(src):
        return {"ok": False, "error": "sqlite database not found"}
    try:
        conn = sqlite3.connect(src, timeout=15.0)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchall()
        conn.close()
    except sqlite3.Error:
        pass

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    dest = f"{src}.{label}-{stamp}.bak"
    suffix = 1
    while os.path.exists(dest):
        suffix += 1
        dest = f"{src}.{label}-{stamp}-{suffix}.bak"
        if suffix > 50:
            return {"ok": False, "error": "too many backups this second"}

    shutil.copy2(src, dest)
    src_sha, dest_sha = _sha_file(src), _sha_file(dest)
    return {
        "ok": src_sha == dest_sha,
        "identical": src_sha == dest_sha,
        "source_path": src,
        "backup_path": dest,
        "source_bytes": os.path.getsize(src),
        "backup_bytes": os.path.getsize(dest),
        "source_sha256": src_sha,
        "backup_sha256": dest_sha,
    }


def create_schema() -> dict:
    """Create the approved PostgreSQL schema. Idempotent."""
    conn = connect()
    try:
        init_postgres_schema(conn)
        counts = {}
        for table in TABLES:
            cur = conn.execute(f"SELECT COUNT(*) AS n FROM {table}")
            row = cur.fetchone()
            counts[table] = int(row["n"] if isinstance(row, dict) else row[0])
    finally:
        conn.close()
    return {"ok": True, "schema_created": True, "row_counts": counts}


def parity() -> dict:
    """Compare the live SQLite source against PostgreSQL, row and field."""
    conn = connect()
    try:
        report = verify_parity(sqlite_path(), conn)
    finally:
        conn.close()
    report["ok"] = report.get("ok", False)
    return report


def run_cutover_migration() -> dict:
    """The whole guarded sequence, as one command.

    SAFETY -> VERIFIED BACKUP -> SCHEMA -> IMPORT -> PARITY

    Refuses to import into a PostgreSQL that already holds rows, because
    that would duplicate ids rather than migrate. Stops before touching
    PostgreSQL if the backup cannot be proven byte-identical.
    """
    report: dict = {"ok": False, "aborted_at": None}

    src = sqlite_path()
    url = dialect.database_url()
    safety = {
        "sqlite_exists": os.path.exists(src),
        "database_url_present": bool(url),
        "database_url_is_postgres": dialect.is_postgres(),
    }
    report["safety_check"] = safety
    if not all(safety.values()):
        report["aborted_at"] = "safety_check"
        report["reason"] = [k for k, v in safety.items() if not v]
        return report

    saved = backup_sqlite()
    report["backup"] = {k: saved.get(k) for k in
                        ("backup_path", "source_bytes", "backup_bytes",
                         "source_sha256", "backup_sha256", "identical")}
    if not saved.get("ok"):
        report["aborted_at"] = "backup"
        report["reason"] = saved.get("error") or "backup did not verify"
        return report

    conn = connect()
    try:
        init_postgres_schema(conn)
        existing = {}
        for table in TABLES:
            cur = conn.execute(f"SELECT COUNT(*) AS n FROM {table}")
            row = cur.fetchone()
            existing[table] = int(row["n"] if isinstance(row, dict) else row[0])
        report["postgres_rows_before"] = existing
        if any(v for v in existing.values()):
            report["aborted_at"] = "target_not_empty"
            report["reason"] = (
                "PostgreSQL already holds rows; importing would duplicate ids. "
                "Run `python pgmig.py parity` to check whether it is already migrated."
            )
            return report

        report["sqlite_inventory"] = export_plan(src)["tables"]
        written = import_into(conn, src)
        report["imported"] = written["written"]

        checked = verify_parity(src, conn)
        report["parity"] = {
            "result": checked["result"],
            "tables": {t: {k: v for k, v in e.items() if k != "field_mismatches"}
                       for t, e in checked["tables"].items()},
            "field_mismatches": {t: e["field_mismatches"]
                                 for t, e in checked["tables"].items()
                                 if e["field_mismatches"]},
        }
        if not checked["ok"]:
            report["aborted_at"] = "parity"
            report["reason"] = "parity mismatch -- DO NOT cut over; production stays on SQLite"
            return report
    finally:
        conn.close()

    report["sqlite_retained"] = os.path.exists(src)
    report["next_step"] = (
        f"Parity is green. Set {BACKEND_VAR}=postgres on the web service to switch. "
        f"Rollback is to delete that variable; the SQLite file is untouched."
    )
    report["ok"] = True
    report["result"] = "PASS"
    return report


def health() -> dict:
    """Which backend the application is ACTUALLY using, proven not assumed."""
    import database

    backend = "postgres" if use_postgres() else "sqlite"
    counts, error = {}, None
    try:
        conn = database.get_conn()
        try:
            for table in TABLES:
                cur = conn.execute(f"SELECT COUNT(*) AS n FROM {table}")
                row = cur.fetchone()
                counts[table] = int(row["n"] if isinstance(row, dict) else row[0])
        finally:
            conn.close()
    except Exception as exc:
        error = f"{type(exc).__name__}"

    return {
        "ok": error is None,
        "active_backend": backend,
        "connection_class": type(database.get_conn()).__name__ if error is None else None,
        "row_counts": counts,
        "error": error,
        "sqlite_file_retained": os.path.exists(sqlite_path()),
        "storage_driver": str(os.environ.get("FACTORY_STORAGE_DRIVER") or "(unset -> local)"),
        "r2_reads_enabled": str(
            os.environ.get("FACTORY_STORAGE_DRIVER") or "").strip().lower() == "r2",
        "rollback": f"delete {BACKEND_VAR} to return to SQLite",
    }
