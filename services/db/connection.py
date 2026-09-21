"""PostgreSQL connection wrapper — Upgrade 0, Phase 0B-4.

`database.py` was written against sqlite3 and uses `?` placeholders,
`conn.execute(...)`, and `cursor.lastrowid`. Rather than rewrite thirty
statements and risk the Factory's most critical module, this wrapper
makes a psycopg connection answer to the same small surface.

TWO-STAGE CUTOVER, AND WHY
--------------------------
`DATABASE_URL` says WHERE PostgreSQL is. `FACTORY_DB_BACKEND=postgres`
says to USE it. They are deliberately separate.

If the application switched the instant `DATABASE_URL` appeared, then
linking the database in Render would immediately point production at an
EMPTY PostgreSQL: every customer's Saved Projects would vanish, every
download would 404, and the only clue would be an empty list. Separating
the two means the database can be created, migrated and verified while
production carries on reading SQLite, and the switch is a single
deliberate act that is reversed by deleting one variable.

This is the same discipline that made the R2 cutover safe: configure
first, prove, then switch.
"""
from __future__ import annotations

import os

from services.db import dialect

#: The switch that actually moves the application onto PostgreSQL.
BACKEND_VAR = "FACTORY_DB_BACKEND"


def use_postgres() -> bool:
    """True only when the app is explicitly told to run on PostgreSQL.

    Requires BOTH an explicit backend choice AND a URL to connect to.
    Either one alone leaves the Factory on SQLite, unchanged.
    """
    backend = str(os.environ.get(BACKEND_VAR) or "").strip().lower()
    # The URL must actually BE a PostgreSQL URL. Requiring only that one
    # exists would let a MySQL or Redis URL send the app at the wrong
    # server with the wrong driver.
    return backend in ("postgres", "postgresql") and dialect.is_postgres()


class _NullCursor:
    """Stands in for a statement PostgreSQL never received."""

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def __iter__(self):
        return iter(())


class _CursorProxy:
    """A psycopg cursor that also answers `lastrowid`.

    sqlite3 exposes the new row's id as `cursor.lastrowid`; PostgreSQL
    returns it from `RETURNING id`. The wrapper captures that value so
    `database.create_project` and `record_asset` need no change.
    """

    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class PostgresConnection:
    """Enough of the sqlite3 connection surface for `database.py`."""

    def __init__(self, conn):
        self._conn = conn
        #: Present so assignment in get_conn() is harmless; psycopg rows
        #: are already mappings, so this is ignored by design.
        self.row_factory = None

    def execute(self, sql: str, params=()):
        # SQLite-only statements (PRAGMA, VACUUM, REINDEX) are tuning
        # hints with no PostgreSQL equivalent. Skipping them beats failing
        # an application's startup over one.
        if dialect.is_sqlite_only_statement(sql):
            return _CursorProxy(_NullCursor())

        # DDL is translated here, in the connection every module shares,
        # rather than module by module: the first cutover attempt failed
        # in production because billing's CREATE TABLE still said
        # AUTOINCREMENT, and a point fix would leave the next module to
        # fail the same way.
        statement = dialect.to_postgres(dialect.translate_ddl(sql))
        wants_id = (
            statement.lstrip().upper().startswith("INSERT")
            and "RETURNING" not in statement.upper()
        )
        if wants_id:
            statement = statement.rstrip().rstrip(";") + " RETURNING id"
        cursor = self._conn.execute(statement, tuple(params or ()))
        if wants_id:
            try:
                row = cursor.fetchone()
                value = row["id"] if isinstance(row, dict) else (row[0] if row else None)
            except Exception:
                value = None
            return _CursorProxy(cursor, value)
        return _CursorProxy(cursor)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def cursor(self):
        return self._conn.cursor()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def connect(url: str | None = None) -> PostgresConnection:
    """Open a wrapped PostgreSQL connection. Fails closed without a driver."""
    return PostgresConnection(dialect.connect(url))


def init_postgres_schema(conn) -> None:
    """Create the approved schema. Idempotent (IF NOT EXISTS throughout)."""
    for statement in dialect.postgres_schema_statements():
        conn.execute(statement)
    for statement in dialect.postgres_upgrade_statements():
        conn.execute(statement)
    conn.commit()
