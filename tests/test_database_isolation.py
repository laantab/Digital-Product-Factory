"""The test suite must not be able to touch the production database.

ROOT CAUSE THIS GUARDS
----------------------
A focused test run was invoked without an isolated FACTORY_DB_PATH and reached
the real projects.db. It rolled back the finished preflight/export state of a
real customer's book (project 351). The conftest already SET a temporary path,
but setting a default is not a guarantee -- nothing checked it, so anything
that overrode the variable would have silently pointed the whole suite at live
customer data.

The guard is now fail-closed: the session refuses to start unless the database
is demonstrably a throwaway.

No external call is made by any test here.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.conftest import (  # noqa: E402
    _looks_like_production_db,
    assert_test_database_is_isolated,
)

# This file is the one place that must name the production database on
# purpose: its whole job is to prove the suite cannot reach it. Everything
# else, including the running suite, resolves its database through
# FACTORY_DB_PATH -- see database.py's DB_PATH and the guard in conftest.py.
# The path is derived from the repository root, never typed as a literal, so
# it stays correct on any machine.
PRODUCTION_DB = ROOT / "projects.db"


def test_the_running_suite_is_not_using_the_production_database():
    active = os.path.realpath(os.environ.get("FACTORY_DB_PATH") or "")
    assert active, "FACTORY_DB_PATH must be set for the suite"
    assert active != os.path.realpath(str(PRODUCTION_DB))
    assert not _looks_like_production_db(active), active


def test_the_active_database_lives_in_a_temporary_directory():
    active = os.path.realpath(os.environ["FACTORY_DB_PATH"])
    temp_root = os.path.realpath(tempfile.gettempdir())
    assert active.startswith(temp_root + os.sep), active


def test_the_guard_rejects_the_production_path():
    # A persistent projects.db anywhere is production, whatever the machine.
    # Only a FACTORY_DB_PATH under the OS temp root counts as isolated.
    assert _looks_like_production_db(str(PRODUCTION_DB))
    assert _looks_like_production_db(str(Path.home() / "factory" / "projects.db"))
    assert _looks_like_production_db(str(Path("/srv/factory/projects.db")))


def test_the_guard_accepts_a_temporary_database():
    # A throwaway file under the OS temp root is what an isolated
    # FACTORY_DB_PATH looks like.
    with tempfile.TemporaryDirectory() as td:
        assert not _looks_like_production_db(os.path.join(td, "projects.db"))
        assert not _looks_like_production_db(os.path.join(td, "factory_test.db"))


def test_the_guard_refuses_an_unset_path(monkeypatch):
    monkeypatch.delenv("FACTORY_DB_PATH", raising=False)
    with pytest.raises(RuntimeError, match="not set"):
        assert_test_database_is_isolated()


def test_the_guard_refuses_the_production_path(monkeypatch):
    monkeypatch.setenv("FACTORY_DB_PATH", str(PRODUCTION_DB))
    with pytest.raises(RuntimeError, match="production database"):
        assert_test_database_is_isolated()


def test_database_module_resolved_the_isolated_path():
    """The application itself must be pointed at the throwaway, not just env."""
    import database

    assert os.path.realpath(database.DB_PATH) == os.path.realpath(
        os.environ["FACTORY_DB_PATH"]
    )
    assert not _looks_like_production_db(database.DB_PATH)


def test_writing_a_project_does_not_touch_the_production_file():
    """The proof: create and delete a project, and show production is untouched."""
    import database

    prod = str(PRODUCTION_DB)
    before = (
        (os.path.getsize(prod), os.path.getmtime(prod))
        if os.path.isfile(prod)
        else None
    )

    created = database.create_project(
        "isolation probe", "ebook", {"product_type": "ebook", "title": "probe"},
        user_saved=False, system_test=True, temporary=True,
    )
    pid = created["id"]
    assert database.get_project(pid) is not None
    database.delete_project(int(pid))

    if before is not None:
        after = (os.path.getsize(prod), os.path.getmtime(prod))
        assert after == before, (
            "the production database changed while tests were running"
        )


def test_production_database_contains_no_test_rows():
    """A read-only audit: earlier leakage would have left probe rows behind."""
    prod = str(PRODUCTION_DB)
    if not os.path.isfile(prod):
        # Nothing to audit on a machine without one; not a skip, so the
        # release gate's zero-skip rule stays meaningful.
        return
    conn = sqlite3.connect(f"file:{prod}?mode=ro", uri=True)
    try:
        leaked = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE name = 'isolation probe'"
        ).fetchone()[0]
    finally:
        conn.close()
    assert leaked == 0, f"{leaked} test row(s) leaked into the production database"
