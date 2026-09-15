"""SQLite / PostgreSQL dialect — Upgrade 0, Phase 0B-4.

The Factory's whole database surface is one module (`database.py`), one
connection helper, and about thirty statements. That is small enough to
port properly rather than rewrite, so this module does the translation
and nothing else.

THE GOVERNING RULE
------------------
With `DATABASE_URL` unset the Factory behaves EXACTLY as it always has:
`is_postgres()` is False, `translate()` returns the SQL unchanged, and
the SQLite connection helper is untouched. That is the state for every
existing install and for the entire test suite, so the port cannot
regress behaviour it does not touch. PostgreSQL is opt-in, and selecting
it fails closed if the driver is missing.

WHAT ACTUALLY DIFFERS
---------------------
    parameter style   ? ............... %s
    autoincrement     INTEGER PRIMARY KEY AUTOINCREMENT ... BIGSERIAL
    new row id        cursor.lastrowid ... RETURNING id
    pragmas           WAL / busy_timeout ... not applicable
    row access        sqlite3.Row ... dict row (both support row["col"])

Everything else in the Factory's SQL is ordinary and portable:
`version=version+1`, `AND version=?` compare-and-swap, the timestamps,
the indexes and the UNIQUE constraint on `assets.storage_key`.
"""
from __future__ import annotations

import os
import re

#: Environment variable that selects PostgreSQL. Unset = SQLite = today.
DATABASE_URL_VAR = "DATABASE_URL"

_POSTGRES_SCHEMES = ("postgres://", "postgresql://", "postgresql+psycopg://")


def database_url() -> str:
    return str(os.environ.get(DATABASE_URL_VAR) or "").strip()


def is_postgres() -> bool:
    """True only when a PostgreSQL URL is configured. Default: False."""
    return database_url().lower().startswith(_POSTGRES_SCHEMES)


# Only rewrite '?' that are real placeholders -- never one inside a string
# literal. The Factory's SQL contains no '?' in literals today, but a
# blind replace would be a silent corruption waiting to happen.
_STRING_LITERAL = re.compile(r"'[^']*'")


def translate(sql: str) -> str:
    """Convert SQLite SQL to the configured dialect.

    A no-op unless PostgreSQL is selected.
    """
    if not is_postgres():
        return sql
    return to_postgres(sql)


def to_postgres(sql: str) -> str:
    """Rewrite '?' placeholders as '%s', leaving string literals alone."""
    out, last = [], 0
    for match in _STRING_LITERAL.finditer(sql):
        out.append(sql[last:match.start()].replace("?", "%s"))
        out.append(match.group(0))          # verbatim
        last = match.end()
    out.append(sql[last:].replace("?", "%s"))
    return "".join(out)


# --------------------------------------------------------------------------
# DDL translation
#
# WHY THIS IS GENERAL RATHER THAN A FIX TO ONE MODULE
#
# The first PostgreSQL cutover attempt failed in production on
# `services/billing/store.py`, which creates its three tables at app
# startup using `INTEGER PRIMARY KEY AUTOINCREMENT`. The 0B-4 work had
# given `database.init_db()` its own PostgreSQL branch -- a POINT fix that
# protected only the module that had been looked at. Any other module
# creating a table at startup was still going to take production down.
#
# So the translation lives in the connection everything shares. A module
# may keep writing ordinary SQLite DDL; if PostgreSQL is active it is
# rewritten on the way through, and no future table can repeat this.
# --------------------------------------------------------------------------

#: SQLite's autoincrement spelling, in the several ways it gets written.
_AUTOINCREMENT_PK = re.compile(
    r"\b(?:BIG)?INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b", re.IGNORECASE)
_BARE_AUTOINCREMENT = re.compile(r"\s+AUTOINCREMENT\b", re.IGNORECASE)

#: Statements that mean nothing to PostgreSQL and must not be sent.
_SQLITE_ONLY_STATEMENT = re.compile(r"^\s*(PRAGMA|VACUUM|REINDEX)\b", re.IGNORECASE)


def is_sqlite_only_statement(sql: str) -> bool:
    """True for statements PostgreSQL has no equivalent of.

    These are skipped rather than raised on: a PRAGMA is a SQLite tuning
    hint, and failing an application's startup over one would be absurd.
    """
    return bool(_SQLITE_ONLY_STATEMENT.match(str(sql or "")))


def translate_ddl(sql: str) -> str:
    """Rewrite SQLite DDL as valid PostgreSQL DDL.

    `INTEGER PRIMARY KEY AUTOINCREMENT` becomes `BIGSERIAL PRIMARY KEY`,
    which is PostgreSQL's equivalent: an implicit sequence supplying the
    id. Everything else in the Factory's DDL -- IF NOT EXISTS, TEXT,
    INTEGER, NOT NULL, DEFAULT, UNIQUE, CREATE INDEX -- is already valid
    in both.
    """
    out = _AUTOINCREMENT_PK.sub("BIGSERIAL PRIMARY KEY", str(sql or ""))
    # A trailing bare AUTOINCREMENT (e.g. after an explicit PRIMARY KEY)
    # has no PostgreSQL meaning and is simply dropped.
    return _BARE_AUTOINCREMENT.sub("", out)


# --------------------------------------------------------------------------
# Schema
#
# Deliberately the SAME logical schema as SQLite, column for column, so a
# migrated row is indistinguishable. Only the id type differs, because
# AUTOINCREMENT has no PostgreSQL spelling.
# --------------------------------------------------------------------------

POSTGRES_PROJECTS_DDL = """
CREATE TABLE IF NOT EXISTS projects (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    user_saved INTEGER NOT NULL DEFAULT 1,
    system_test INTEGER NOT NULL DEFAULT 0,
    temporary INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 0,
    product_uuid TEXT
)
"""

POSTGRES_ASSETS_DDL = """
CREATE TABLE IF NOT EXISTS assets (
    id BIGSERIAL PRIMARY KEY,
    project_id BIGINT NOT NULL,
    kind TEXT NOT NULL,
    storage_key TEXT NOT NULL UNIQUE,
    content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
    byte_size BIGINT NOT NULL DEFAULT 0,
    checksum TEXT NOT NULL DEFAULT '',
    approved INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)
"""

POSTGRES_ASSETS_INDEX = (
    "CREATE INDEX IF NOT EXISTS assets_project_kind_idx "
    "ON assets (project_id, kind, approved)"
)

#: After importing rows with explicit ids, the sequence must be advanced or
#: the next INSERT collides with a migrated row. This is the single most
#: common way a database import corrupts itself.
POSTGRES_RESET_SEQUENCES = (
    "SELECT setval(pg_get_serial_sequence('projects','id'), "
    "COALESCE((SELECT MAX(id) FROM projects), 0) + 1, false)",
    "SELECT setval(pg_get_serial_sequence('assets','id'), "
    "COALESCE((SELECT MAX(id) FROM assets), 0) + 1, false)",
)


def postgres_schema_statements() -> tuple[str, ...]:
    return (POSTGRES_PROJECTS_DDL, POSTGRES_ASSETS_DDL, POSTGRES_ASSETS_INDEX)


def connect(url: str | None = None):
    """Open a PostgreSQL connection with mapping-style rows.

    Fails closed: if PostgreSQL is selected but the driver is absent, that
    is an error, never a silent fall back to SQLite.
    """
    target = url or database_url()
    if not target:
        raise RuntimeError("DATABASE_URL is not set")
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "PostgreSQL is selected but the psycopg driver is not installed"
        ) from exc
    return psycopg.connect(target, row_factory=dict_row, autocommit=False)
