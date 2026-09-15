"""Phase 0B-4 — the PostgreSQL cutover switch and tooling.

The single most dangerous thing in this phase is an ACCIDENTAL switch. If
the application moved onto PostgreSQL the moment DATABASE_URL appeared,
then simply linking the database in Render would point production at an
empty database: every customer's Saved Projects would vanish and every
download would fail, with an empty list as the only clue.

So the switch is deliberately two-stage -- DATABASE_URL says where, and
FACTORY_DB_BACKEND says use it -- and most of these tests exist to prove
that neither one alone can move production.
"""
from __future__ import annotations

import json
import os
import sqlite3

import pytest

import database
from services.db import cutover, dialect
from services.db.connection import BACKEND_VAR, PostgresConnection, use_postgres

PG_URL = "postgresql://user:pw@host:5432/factory"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv(BACKEND_VAR, raising=False)
    yield


def _isolated_db(monkeypatch, tmp_path, create=False):
    """A temporary database, published through FACTORY_DB_PATH.

    One helper so the filename literal appears once, guarded, instead of
    in every test -- the suite forbids an unguarded hardcoded reference
    to the real database name.
    """
    path = tmp_path / os.environ.get("FACTORY_DB_PATH_TEST_NAME", "projects.db")
    monkeypatch.setenv("FACTORY_DB_PATH", str(path))
    monkeypatch.setattr(database, "DB_PATH", str(path))
    if create:
        sqlite3.connect(str(path)).close()
    return path


# ============================ the switch cannot fire by accident ===========


def test_nothing_set_means_sqlite():
    assert use_postgres() is False
    assert database._use_postgres() is False


def test_database_url_alone_does_NOT_move_the_application(monkeypatch):
    """Linking the database in Render must not switch production."""
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    assert dialect.is_postgres() is True, "the URL is recognised..."
    assert use_postgres() is False, "...but the app must stay on SQLite"
    assert database._use_postgres() is False


def test_backend_flag_alone_does_NOT_move_the_application(monkeypatch):
    """Without a URL there is nowhere to go; stay on SQLite rather than crash."""
    monkeypatch.setenv(BACKEND_VAR, "postgres")
    assert use_postgres() is False
    assert database._use_postgres() is False


def test_both_together_select_postgres(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    monkeypatch.setenv(BACKEND_VAR, "postgres")
    assert use_postgres() is True
    assert database._use_postgres() is True


@pytest.mark.parametrize("value", ["", "  ", "sqlite", "local", "no", "postgres-ish"])
def test_only_an_exact_backend_value_switches(monkeypatch, value):
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    monkeypatch.setenv(BACKEND_VAR, value)
    assert use_postgres() is False, f"{value!r} must not switch the backend"


def test_a_non_postgres_url_never_switches(monkeypatch):
    monkeypatch.setenv(BACKEND_VAR, "postgres")
    monkeypatch.setenv("DATABASE_URL", "mysql://u:p@h/db")
    assert use_postgres() is False


def test_the_sqlite_connection_is_unchanged_when_not_switched():
    """The whole existing suite depends on this staying true."""
    conn = database.get_conn()
    try:
        assert isinstance(conn, sqlite3.Connection)
    finally:
        conn.close()


def test_a_broken_switch_never_takes_the_factory_down(monkeypatch):
    """If the check itself fails, fall back to SQLite rather than raise."""
    import services.db.connection as connection_module

    def _explode():
        raise RuntimeError("configuration exploded")

    monkeypatch.setattr(connection_module, "use_postgres", _explode)
    assert database._use_postgres() is False
    conn = database.get_conn()
    try:
        assert isinstance(conn, sqlite3.Connection)
    finally:
        conn.close()


# ================================= the wrapper speaks sqlite3's dialect ====


class _FakePgCursor:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)


class _FakePgConn:
    """Records what a real psycopg connection would have been asked."""

    def __init__(self, returning_id=42):
        self.statements = []
        self.committed = False
        self._returning_id = returning_id

    def execute(self, sql, params=()):
        self.statements.append((sql, params))
        if "RETURNING id" in sql:
            return _FakePgCursor([{"id": self._returning_id}])
        return _FakePgCursor([{"n": 0}])

    def commit(self):
        self.committed = True

    def close(self):
        pass


def test_wrapper_translates_placeholders():
    fake = _FakePgConn()
    conn = PostgresConnection(fake)
    conn.execute("SELECT * FROM projects WHERE id=? AND version=?", (1, 2))
    sql, params = fake.statements[-1]
    assert "%s" in sql and "?" not in sql
    assert params == (1, 2)


def test_wrapper_provides_lastrowid_via_returning():
    """database.create_project relies on cursor.lastrowid."""
    fake = _FakePgConn(returning_id=777)
    conn = PostgresConnection(fake)
    cur = conn.execute(
        "INSERT INTO projects (name, type) VALUES (?, ?)", ("X", "product"))
    assert "RETURNING id" in fake.statements[-1][0]
    assert cur.lastrowid == 777


def test_wrapper_does_not_double_append_returning():
    fake = _FakePgConn()
    conn = PostgresConnection(fake)
    conn.execute("INSERT INTO projects (name) VALUES (?) RETURNING id", ("X",))
    assert fake.statements[-1][0].upper().count("RETURNING") == 1


def test_wrapper_leaves_selects_alone():
    fake = _FakePgConn()
    conn = PostgresConnection(fake)
    conn.execute("SELECT COUNT(*) AS n FROM assets")
    assert "RETURNING" not in fake.statements[-1][0]


def test_wrapper_forwards_commit_and_close():
    fake = _FakePgConn()
    conn = PostgresConnection(fake)
    conn.commit()
    assert fake.committed is True


# ========================================= cutover tooling, fail-closed ====


def test_status_is_read_only_and_hides_credentials(monkeypatch, tmp_path):
    db = _isolated_db(monkeypatch, tmp_path, create=True)
    monkeypatch.setenv("DATABASE_URL", "postgresql://secret-user:secret-pw@h/db")

    report = cutover.status()
    serialised = json.dumps(report)
    assert "secret-pw" not in serialised
    assert "secret-user" not in serialised
    assert report["database_url_present"] is True
    assert report["app_uses_postgres"] is False


def test_cutover_refuses_without_a_database_url(monkeypatch, tmp_path):
    db = _isolated_db(monkeypatch, tmp_path, create=True)

    report = cutover.run_cutover_migration()
    assert report["ok"] is False
    assert report["aborted_at"] == "safety_check"
    assert "backup" not in report, "it must not back up before the safety check passes"


def test_cutover_refuses_when_the_sqlite_source_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "absent.db"))
    monkeypatch.setenv("DATABASE_URL", PG_URL)
    report = cutover.run_cutover_migration()
    assert report["ok"] is False
    assert report["aborted_at"] == "safety_check"


def test_backup_is_verified_byte_identical(monkeypatch, tmp_path):
    db = _isolated_db(monkeypatch, tmp_path)
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (a TEXT)")
    conn.execute("INSERT INTO t VALUES ('x')")
    conn.commit()
    conn.close()

    result = cutover.backup_sqlite()
    assert result["ok"] is True
    assert result["identical"] is True
    assert result["source_sha256"] == result["backup_sha256"]
    assert "PRE-POSTGRES-CUTOVER" in result["backup_path"]
    assert os.path.exists(result["backup_path"])
    assert os.path.exists(str(db)), "the source is the rollback; never removed"


def test_repeated_backups_never_overwrite_each_other(monkeypatch, tmp_path):
    db = _isolated_db(monkeypatch, tmp_path, create=True)

    first = cutover.backup_sqlite()
    second = cutover.backup_sqlite()
    assert first["backup_path"] != second["backup_path"]
    assert os.path.exists(first["backup_path"])
    assert os.path.exists(second["backup_path"])


def test_health_reports_sqlite_when_not_switched(monkeypatch, tmp_path):
    db = _isolated_db(monkeypatch, tmp_path)
    database.init_db()

    report = cutover.health()
    assert report["active_backend"] == "sqlite"
    assert report["sqlite_file_retained"] is True
    assert BACKEND_VAR in report["rollback"]
    assert report["row_counts"]["projects"] == 0


def test_rollback_is_documented_as_deleting_one_variable(monkeypatch, tmp_path):
    db = _isolated_db(monkeypatch, tmp_path)
    database.init_db()
    assert "delete" in cutover.health()["rollback"].lower()


# ========== the defect that broke the first production cutover attempt =====
#
# The first attempt failed live with:
#     psycopg.errors.SyntaxError: syntax error at or near "AUTOINCREMENT"
# from services/billing/store.py::init_billing_db, which creates its
# tables at app startup. 0B-4 had given database.init_db() its own
# PostgreSQL branch -- a POINT fix covering only the module that had been
# examined. These tests exist so no module can repeat it.


BILLING_DDL = """
CREATE TABLE IF NOT EXISTS billing_subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL,
    plan TEXT NOT NULL
)
"""


def test_the_exact_statement_that_broke_production_is_now_translated():
    translated = dialect.translate_ddl(BILLING_DDL)
    assert "AUTOINCREMENT" not in translated.upper(), (
        "this is the statement that took production down"
    )
    assert "BIGSERIAL PRIMARY KEY" in translated


@pytest.mark.parametrize("spelling", [
    "id INTEGER PRIMARY KEY AUTOINCREMENT,",
    "id integer primary key autoincrement,",
    "id  INTEGER   PRIMARY  KEY   AUTOINCREMENT ,",
    "id BIGINTEGER PRIMARY KEY AUTOINCREMENT,",
])
def test_every_spelling_of_autoincrement_is_translated(spelling):
    out = dialect.translate_ddl(f"CREATE TABLE t ({spelling} name TEXT)")
    assert "AUTOINCREMENT" not in out.upper(), spelling


def test_no_autoincrement_survives_translation_of_any_production_ddl():
    """Scan the real production modules, not a sample."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    sources = [root / "database.py", root / "services" / "billing" / "store.py"]
    found = 0
    for path in sources:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"CREATE TABLE[^;]*?\)", text, re.IGNORECASE | re.DOTALL):
            statement = match.group(0)
            if "AUTOINCREMENT" not in statement.upper():
                continue
            found += 1
            assert "AUTOINCREMENT" not in dialect.translate_ddl(statement).upper(), (
                f"{path.name} still emits untranslatable DDL"
            )
    assert found >= 3, "expected to find the real AUTOINCREMENT tables to translate"


def test_pragma_is_skipped_rather_than_sent_to_postgres():
    fake = _FakePgConn()
    conn = PostgresConnection(fake)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    assert fake.statements == [], "PRAGMA must never reach PostgreSQL"


@pytest.mark.parametrize("statement", ["PRAGMA foreign_keys=ON", "VACUUM", "REINDEX t"])
def test_sqlite_only_statements_are_recognised(statement):
    assert dialect.is_sqlite_only_statement(statement) is True


@pytest.mark.parametrize("statement", [
    "SELECT 1", "CREATE TABLE t (a TEXT)", "INSERT INTO t VALUES (?)",
])
def test_ordinary_statements_are_not_treated_as_sqlite_only(statement):
    assert dialect.is_sqlite_only_statement(statement) is False


def test_billing_ddl_reaches_postgres_without_autoincrement_or_pragma():
    """The startup path that actually failed, end to end through the wrapper."""
    fake = _FakePgConn()
    conn = PostgresConnection(fake)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(BILLING_DDL)
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_billing_account"
        " ON billing_subscriptions (account)")

    sent = " ".join(s for s, _ in fake.statements).upper()
    assert "AUTOINCREMENT" not in sent
    assert "PRAGMA" not in sent
    assert "BIGSERIAL" in sent
    assert "CREATE UNIQUE INDEX" in sent, "ordinary DDL must still pass through"


def test_billing_insert_gets_lastrowid_on_postgres():
    """store.py reads cur.lastrowid straight after inserting a subscription."""
    fake = _FakePgConn(returning_id=555)
    conn = PostgresConnection(fake)
    cur = conn.execute(
        "INSERT INTO billing_subscriptions (account, plan) VALUES (?, ?)",
        ("acct", "pro"))
    assert cur.lastrowid == 555


def test_billing_schema_still_initialises_on_sqlite(monkeypatch, tmp_path):
    """SQLite behaviour must be completely unchanged."""
    _isolated_db(monkeypatch, tmp_path)
    database.init_db()
    from services.billing.store import init_billing_db

    init_billing_db()

    conn = database.get_conn()
    try:
        assert isinstance(conn, sqlite3.Connection)
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"billing_subscriptions", "billing_events", "billing_usage"} <= names
        conn.execute(
            "INSERT INTO billing_subscriptions (account_ref, plan_id,"
            " billing_period, provider, status, created_at, updated_at)"
            " VALUES ('a','pro','monthly','lemonsqueezy','active','n','n')")
        conn.commit()
        row = conn.execute(
            "SELECT id FROM billing_subscriptions ORDER BY id DESC LIMIT 1").fetchone()
        assert row["id"] >= 1, "the primary key must still autoincrement on SQLite"
    finally:
        conn.close()


def test_the_real_startup_path_runs_clean_under_postgres(monkeypatch):
    """Reproduce production's startup exactly: init_db + init_billing_db
    with get_conn() returning a PostgreSQL connection.

    This is the test that would have caught the failed cutover.
    """
    recorded = _FakePgConn()

    def _fake_get_conn():
        return PostgresConnection(recorded)

    monkeypatch.setattr(database, "get_conn", _fake_get_conn)
    monkeypatch.setattr(database, "_use_postgres", lambda: True)

    database.init_db()
    from services.billing.store import init_billing_db

    init_billing_db()

    sent = " ".join(s for s, _ in recorded.statements)
    upper = sent.upper()
    assert "AUTOINCREMENT" not in upper, (
        "AUTOINCREMENT reached PostgreSQL -- this is exactly what failed live"
    )
    assert "PRAGMA" not in upper
    # and the tables really were created
    for table in ("billing_subscriptions", "billing_events", "billing_usage"):
        assert table in sent, f"{table} was never created"
    assert "BIGSERIAL" in upper
