"""SQLite -> PostgreSQL migration and parity verifier — Phase 0B-4.

The blueprint calls for a side-by-side export / verify / import with the
data proven row-for-row. This module is that, and its parity verifier is
written so it can be exercised WITHOUT a PostgreSQL server: it compares
any two DB-API connections, so SQLite-to-SQLite proves the comparison
logic itself, and the same code then runs against the real target.

SAFETY
------
The SQLite source is opened READ-ONLY and is never written, moved or
deleted. Nothing here removes a legacy artifact. A failed import leaves
the source exactly as it was, and the rollback is simply to keep using
it -- which is why the SQLite file is retained after a successful cutover
rather than deleted.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from services.db import dialect

#: Column order is fixed so source and target are compared like for like.
PROJECT_COLUMNS = (
    "id", "name", "type", "data", "user_saved", "system_test",
    "temporary", "created_at", "updated_at", "version",
)
ASSET_COLUMNS = (
    "id", "project_id", "kind", "storage_key", "content_type",
    "byte_size", "checksum", "approved", "created_at", "updated_at",
)

TABLES = {"projects": PROJECT_COLUMNS, "assets": ASSET_COLUMNS}


def open_sqlite_readonly(path: str) -> sqlite3.Connection:
    """Read-only handle on the source. It must never be written."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _columns_present(conn, table: str) -> set[str]:
    cur = conn.execute(f"SELECT * FROM {table} LIMIT 0")
    return {d[0] for d in (cur.description or [])}


def read_rows(conn, table: str) -> list[dict]:
    """Every row of `table`, as plain dicts, ordered by id.

    Only the columns this migration knows about are read, so a source
    carrying an extra legacy column does not silently change the shape of
    what is compared.
    """
    wanted = [c for c in TABLES[table] if c in _columns_present(conn, table)]
    cur = conn.execute(f"SELECT {', '.join(wanted)} FROM {table} ORDER BY id")
    out = []
    for row in cur.fetchall():
        out.append({c: (row[c] if not isinstance(row, dict) else row.get(c))
                    for c in wanted})
    return out


def row_fingerprint(row: dict) -> str:
    """A stable hash of one row's values, for field-level comparison."""
    payload = json.dumps(
        {k: ("" if v is None else str(v)) for k, v in sorted(row.items())},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def export_plan(sqlite_path: str) -> dict:
    """DRY RUN. What would be migrated. Reads only."""
    conn = open_sqlite_readonly(sqlite_path)
    try:
        summary = {}
        for table in TABLES:
            try:
                rows = read_rows(conn, table)
            except sqlite3.Error:
                summary[table] = {"rows": 0, "present": False}
                continue
            summary[table] = {
                "rows": len(rows),
                "present": True,
                "max_id": max((int(r["id"]) for r in rows), default=0),
                "bytes": sum(len(str(r.get("data") or "")) for r in rows)
                if table == "projects" else None,
            }
    finally:
        conn.close()
    return {"source": sqlite_path, "tables": summary}


def target_is_sqlite(conn) -> bool:
    """True when the target speaks '?' rather than '%s'.

    The placeholder style has to follow the TARGET, not the configured
    DATABASE_URL: a SQLite-to-SQLite rehearsal is how the migration is
    proven before a PostgreSQL server exists.
    """
    return isinstance(conn, sqlite3.Connection)


def import_into(target_conn, sqlite_path: str, *, batch: int = 200) -> dict:
    """Copy every row into the target, preserving ids and versions.

    Ids are preserved deliberately: `assets.project_id` refers to them,
    Saved Projects links to them, and storage keys embed them
    (`projects/{id}/embedded/pdf_bytes.pdf`). Renumbering would silently
    break every migrated artifact's key.
    """
    source = open_sqlite_readonly(sqlite_path)
    written = {}
    try:
        for table, columns in TABLES.items():
            try:
                rows = read_rows(source, table)
            except sqlite3.Error:
                written[table] = 0
                continue
            if not rows:
                written[table] = 0
                continue
            cols = list(rows[0].keys())
            placeholders = ", ".join("?" for _ in cols)
            sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders})"
            if not target_is_sqlite(target_conn):
                sql = dialect.to_postgres(sql)
            count = 0
            for start in range(0, len(rows), batch):
                for row in rows[start:start + batch]:
                    target_conn.execute(sql, tuple(row[c] for c in cols))
                    count += 1
            written[table] = count
        # Sequences must follow the explicit ids, or the next insert collides.
        for statement in dialect.POSTGRES_RESET_SEQUENCES:
            try:
                target_conn.execute(statement)
            except Exception:
                pass          # SQLite target (used in tests) has no sequences
        target_conn.commit()
    finally:
        source.close()
    return {"written": written}


def verify_parity(sqlite_path: str, target_conn) -> dict:
    """Prove the target matches the source row for row and field for field.

    Reports every difference it finds rather than stopping at the first,
    so a single run says exactly how wrong things are.
    """
    source = open_sqlite_readonly(sqlite_path)
    report: dict[str, Any] = {"tables": {}, "ok": True}
    try:
        for table in TABLES:
            try:
                src_rows = read_rows(source, table)
            except sqlite3.Error:
                src_rows = []
            try:
                dst_rows = read_rows(target_conn, table)
            except Exception:
                dst_rows = []

            src_by_id = {int(r["id"]): r for r in src_rows}
            dst_by_id = {int(r["id"]): r for r in dst_rows}
            missing = sorted(set(src_by_id) - set(dst_by_id))
            extra = sorted(set(dst_by_id) - set(src_by_id))

            mismatched, version_mismatch = [], []
            for pid in sorted(set(src_by_id) & set(dst_by_id)):
                src, dst = src_by_id[pid], dst_by_id[pid]
                shared = [c for c in src if c in dst]
                if row_fingerprint({c: src[c] for c in shared}) != \
                        row_fingerprint({c: dst[c] for c in shared}):
                    differing = [c for c in shared if str(src[c]) != str(dst[c])]
                    mismatched.append({"id": pid, "fields": differing[:8]})
                if "version" in shared and str(src["version"]) != str(dst["version"]):
                    version_mismatch.append(pid)

            entry = {
                "source_rows": len(src_rows),
                "target_rows": len(dst_rows),
                "row_count_matches": len(src_rows) == len(dst_rows),
                "missing_in_target": missing[:20],
                "extra_in_target": extra[:20],
                "field_mismatches": mismatched[:20],
                "version_mismatches": version_mismatch[:20],
                "ok": (len(src_rows) == len(dst_rows) and not missing
                       and not extra and not mismatched and not version_mismatch),
            }
            report["tables"][table] = entry
            report["ok"] = report["ok"] and entry["ok"]
    finally:
        source.close()
    report["result"] = "PASS" if report["ok"] else "FAIL"
    return report
