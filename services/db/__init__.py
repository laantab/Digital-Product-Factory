"""Database dialect and migration tooling — Upgrade 0, Phase 0B-4.

With `DATABASE_URL` unset the Factory runs on SQLite exactly as before;
nothing in this package changes that. PostgreSQL is opt-in and fails
closed when selected without a driver.
"""
from services.db.dialect import (
    DATABASE_URL_VAR,
    database_url,
    is_postgres,
    postgres_schema_statements,
    to_postgres,
    translate,
)

__all__ = [
    "DATABASE_URL_VAR",
    "database_url",
    "is_postgres",
    "postgres_schema_statements",
    "to_postgres",
    "translate",
]
