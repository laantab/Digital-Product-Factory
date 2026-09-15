"""Phase 0B-4 — SQLite/PostgreSQL compatibility, migration and parity.

Two things are proven here without needing a PostgreSQL server:

  1. With DATABASE_URL unset, NOTHING changes. That is the state of every
     existing install and of this entire suite, so the port cannot
     regress behaviour it does not touch.
  2. The parity verifier genuinely detects corruption. It compares two
     DB-API connections, so SQLite-to-SQLite exercises the comparison
     logic itself -- and the same code runs against the real target
     later. A verifier that only ever returns PASS would be worthless,
     so most of these tests make it FAIL on purpose.
"""
from __future__ import annotations

import json
import sqlite3

import pytest

from services.db import dialect
from services.db.migrate_postgres import (
    export_plan,
    import_into,
    open_sqlite_readonly,
    row_fingerprint,
    verify_parity,
)


# ===================================== 1. unset DATABASE_URL changes nothing ==


def test_sqlite_is_the_default_and_translation_is_a_noop(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert dialect.is_postgres() is False
    sql = "SELECT id FROM projects WHERE id=? AND version=?"
    assert dialect.translate(sql) == sql, "SQLite SQL must pass through untouched"


def test_an_empty_or_whitespace_url_is_still_sqlite(monkeypatch):
    for value in ("", "   "):
        monkeypatch.setenv("DATABASE_URL", value)
        assert dialect.is_postgres() is False


def test_a_non_postgres_url_does_not_select_postgres(monkeypatch):
    for value in ("mysql://x/y", "sqlite:///thing.db", "redis://localhost"):
        monkeypatch.setenv("DATABASE_URL", value)
        assert dialect.is_postgres() is False, value


@pytest.mark.parametrize("scheme", ["postgres://", "postgresql://", "postgresql+psycopg://"])
def test_postgres_urls_are_recognised(monkeypatch, scheme):
    monkeypatch.setenv("DATABASE_URL", f"{scheme}user:pw@host:5432/db")
    assert dialect.is_postgres() is True


# ================================================ 2. placeholder translation ==


def test_placeholders_become_percent_s(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    assert dialect.translate("SELECT * FROM projects WHERE id=?") == \
        "SELECT * FROM projects WHERE id=%s"
    assert dialect.translate(
        "UPDATE projects SET name=?, version=version+1 WHERE id=? AND version=?"
    ) == "UPDATE projects SET name=%s, version=version+1 WHERE id=%s AND version=%s"


def test_a_question_mark_inside_a_string_literal_is_never_rewritten():
    """A blind replace here would be silent data corruption."""
    sql = "SELECT * FROM projects WHERE name='what? really' AND id=?"
    assert dialect.to_postgres(sql) == \
        "SELECT * FROM projects WHERE name='what? really' AND id=%s"


def test_translation_is_idempotent_for_sql_with_no_placeholders():
    sql = "SELECT COUNT(*) FROM assets"
    assert dialect.to_postgres(sql) == sql


# ============================================================== 3. schema =====


def test_postgres_schema_covers_both_tables_and_the_index():
    statements = dialect.postgres_schema_statements()
    joined = " ".join(statements)
    assert "CREATE TABLE IF NOT EXISTS projects" in joined
    assert "CREATE TABLE IF NOT EXISTS assets" in joined
    assert "assets_project_kind_idx" in joined
    assert "AUTOINCREMENT" not in joined, "AUTOINCREMENT has no PostgreSQL spelling"
    assert "BIGSERIAL" in joined


def test_postgres_schema_preserves_every_column_the_factory_relies_on():
    joined = " ".join(dialect.postgres_schema_statements())
    for column in ("version", "user_saved", "system_test", "temporary",
                   "created_at", "updated_at", "product_uuid"):
        assert column in joined, f"projects.{column} missing from the target schema"
    for column in ("storage_key", "checksum", "byte_size", "approved", "project_id"):
        assert column in joined, f"assets.{column} missing from the target schema"


def test_optimistic_concurrency_and_uniqueness_survive_the_port():
    joined = " ".join(dialect.postgres_schema_statements())
    assert "version INTEGER NOT NULL DEFAULT 0" in joined
    assert "storage_key TEXT NOT NULL UNIQUE" in joined, (
        "the UNIQUE storage_key is what makes migration idempotent"
    )


def test_sequences_are_reset_after_an_id_preserving_import():
    joined = " ".join(dialect.POSTGRES_RESET_SEQUENCES)
    assert "setval" in joined and "projects" in joined and "assets" in joined


def test_selecting_postgres_without_a_driver_fails_closed(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h/db")
    with pytest.raises(RuntimeError):
        dialect.connect()


def test_connect_refuses_when_no_url_is_configured(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        dialect.connect()


# ========================== 4. migration + parity, proven on real databases ===


def _make_source(path, projects=3, assets=2):
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE projects (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,"
        " type TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}', user_saved INTEGER NOT NULL"
        " DEFAULT 1, system_test INTEGER NOT NULL DEFAULT 0, temporary INTEGER NOT NULL"
        " DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, version INTEGER"
        " NOT NULL DEFAULT 0)"
    )
    conn.execute(
        "CREATE TABLE assets (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER"
        " NOT NULL, kind TEXT NOT NULL, storage_key TEXT NOT NULL UNIQUE, content_type TEXT"
        " NOT NULL DEFAULT '', byte_size INTEGER NOT NULL DEFAULT 0, checksum TEXT NOT NULL"
        " DEFAULT '', approved INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,"
        " updated_at TEXT NOT NULL)"
    )
    for i in range(1, projects + 1):
        conn.execute(
            "INSERT INTO projects (name, type, data, created_at, updated_at, version)"
            " VALUES (?,?,?,?,?,?)",
            (f"Project {i}", "product", json.dumps({"pdf_bytes": "x" * 20, "n": i}),
             "2026-09-15", "2026-09-15", i),
        )
    for i in range(1, assets + 1):
        conn.execute(
            "INSERT INTO assets (project_id, kind, storage_key, byte_size, checksum,"
            " approved, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (i, "pdf", f"projects/{i}/embedded/pdf_bytes.pdf", 100 + i,
             f"sha{i}", 1, "2026-09-15", "2026-09-15"),
        )
    conn.commit()
    conn.close()


def _empty_target(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    for statement in dialect.postgres_schema_statements():
        conn.execute(statement.replace("BIGSERIAL PRIMARY KEY",
                                       "INTEGER PRIMARY KEY AUTOINCREMENT")
                     .replace("BIGINT", "INTEGER"))
    conn.commit()
    return conn


def test_export_plan_is_read_only_and_counts_what_would_move(tmp_path):
    src = tmp_path / "source.db"
    _make_source(src)
    before = src.read_bytes()

    plan = export_plan(str(src))
    assert plan["tables"]["projects"]["rows"] == 3
    assert plan["tables"]["assets"]["rows"] == 2
    assert plan["tables"]["projects"]["max_id"] == 3
    assert src.read_bytes() == before, "the source must not be written"


def test_the_source_is_opened_read_only(tmp_path):
    src = tmp_path / "source.db"
    _make_source(src)
    conn = open_sqlite_readonly(str(src))
    try:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("DELETE FROM projects")
            conn.commit()
    finally:
        conn.close()


def test_import_then_parity_passes_and_preserves_ids_and_versions(tmp_path):
    src = tmp_path / "source.db"
    _make_source(src)
    target = _empty_target(tmp_path / "target.db")
    try:
        written = import_into(target, str(src))
        assert written["written"]["projects"] == 3
        assert written["written"]["assets"] == 2

        report = verify_parity(str(src), target)
        assert report["ok"] is True, report
        assert report["result"] == "PASS"
        assert report["tables"]["projects"]["row_count_matches"] is True
        assert report["tables"]["projects"]["version_mismatches"] == []

        rows = target.execute("SELECT id, version FROM projects ORDER BY id").fetchall()
        assert [r["id"] for r in rows] == [1, 2, 3], "ids must be preserved"
        assert [r["version"] for r in rows] == [1, 2, 3], "versions must be preserved"
    finally:
        target.close()


def test_parity_detects_a_missing_row(tmp_path):
    src = tmp_path / "source.db"
    _make_source(src)
    target = _empty_target(tmp_path / "target.db")
    try:
        import_into(target, str(src))
        target.execute("DELETE FROM projects WHERE id=2")
        target.commit()

        report = verify_parity(str(src), target)
        assert report["ok"] is False
        assert report["result"] == "FAIL"
        assert 2 in report["tables"]["projects"]["missing_in_target"]
    finally:
        target.close()


def test_parity_detects_an_altered_field(tmp_path):
    """The check that matters: silently corrupted data must not pass."""
    src = tmp_path / "source.db"
    _make_source(src)
    target = _empty_target(tmp_path / "target.db")
    try:
        import_into(target, str(src))
        target.execute("UPDATE projects SET data='{\"pdf_bytes\": \"TAMPERED\"}' WHERE id=1")
        target.commit()

        report = verify_parity(str(src), target)
        assert report["ok"] is False
        mismatches = report["tables"]["projects"]["field_mismatches"]
        assert any(m["id"] == 1 and "data" in m["fields"] for m in mismatches)
    finally:
        target.close()


def test_parity_detects_a_lost_version_number(tmp_path):
    """Losing version would silently disable optimistic concurrency."""
    src = tmp_path / "source.db"
    _make_source(src)
    target = _empty_target(tmp_path / "target.db")
    try:
        import_into(target, str(src))
        target.execute("UPDATE projects SET version=0 WHERE id=3")
        target.commit()

        report = verify_parity(str(src), target)
        assert report["ok"] is False
        assert 3 in report["tables"]["projects"]["version_mismatches"]
    finally:
        target.close()


def test_parity_detects_an_extra_row_in_the_target(tmp_path):
    src = tmp_path / "source.db"
    _make_source(src)
    target = _empty_target(tmp_path / "target.db")
    try:
        import_into(target, str(src))
        target.execute(
            "INSERT INTO projects (id, name, type, data, created_at, updated_at, version)"
            " VALUES (99,'Ghost','product','{}','2026-09-15','2026-09-15',0)")
        target.commit()

        report = verify_parity(str(src), target)
        assert report["ok"] is False
        assert 99 in report["tables"]["projects"]["extra_in_target"]
    finally:
        target.close()


def test_asset_relationships_and_storage_keys_survive(tmp_path):
    """Storage keys embed the project id -- renumbering would break every
    migrated artifact."""
    src = tmp_path / "source.db"
    _make_source(src)
    target = _empty_target(tmp_path / "target.db")
    try:
        import_into(target, str(src))
        rows = target.execute(
            "SELECT project_id, storage_key, checksum, approved FROM assets ORDER BY id"
        ).fetchall()
        assert [r["storage_key"] for r in rows] == [
            "projects/1/embedded/pdf_bytes.pdf",
            "projects/2/embedded/pdf_bytes.pdf",
        ]
        assert [r["project_id"] for r in rows] == [1, 2]
        assert all(r["approved"] == 1 for r in rows)
    finally:
        target.close()


def test_the_migration_never_writes_to_the_source(tmp_path):
    src = tmp_path / "source.db"
    _make_source(src)
    before = src.read_bytes()
    target = _empty_target(tmp_path / "target.db")
    try:
        import_into(target, str(src))
        verify_parity(str(src), target)
    finally:
        target.close()
    assert src.read_bytes() == before, "the SQLite source is the rollback copy"


def test_row_fingerprint_is_stable_and_order_independent():
    a = {"id": 1, "name": "x", "version": 2}
    b = {"version": 2, "name": "x", "id": 1}
    assert row_fingerprint(a) == row_fingerprint(b)
    assert row_fingerprint(a) != row_fingerprint({"id": 1, "name": "y", "version": 2})
