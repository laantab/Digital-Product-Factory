"""One database, one `database` module, for the whole test session.

THE FAILURE THIS GUARDS
-----------------------
A test wanted an empty database, so it pointed FACTORY_DB_PATH at a temporary
file and deleted `database` from sys.modules to force a reimport. It restored
neither. Every test that ran afterwards inherited both.

The second part is the dangerous one. The application does not agree with
itself about which module object `database` means:

  * app.py binds `import database` once, at import, and keeps that object.
  * services/quality/download_pipeline_agent._load_project_by_package_id
    imports it lazily, inside the function, so it resolves whatever
    sys.modules["database"] is at call time.

After the leak those are two different modules holding two different file
paths. A customer flow saved its project through the app's database and looked
its export up through the reimported one, which had never heard of it. With no
project resolved, the orphan-package rule correctly refused to serve the file:

    HTTP 403  stale_or_orphan_export_package

about 1,100 tests into the run, in a test that passes on its own. Nothing was
wrong with the validation, the export, or the failing test.

These checks fail in the file that causes the leak instead of somewhere else
entirely, and they are written against the invariant rather than against the
one test that broke it.

No external call is made by any test here.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FACTORY_TEST_MODE", "1")

import database  # noqa: E402

TESTS_DIR = ROOT / "tests"
SESSION_DB = os.environ.get("FACTORY_DB_PATH") or ""


# ------------------------------------------------------ the live invariant ---


class DatabaseIdentityTests(unittest.TestCase):
    def test_the_session_database_is_the_one_conftest_created(self):
        self.assertTrue(SESSION_DB, "FACTORY_DB_PATH is unset")
        self.assertEqual(
            Path(database.DB_PATH).resolve(),
            Path(SESSION_DB).resolve(),
            "an earlier test redirected the database and did not put it back",
        )

    def test_a_lazy_import_reaches_the_same_database_as_the_app(self):
        """The exact asymmetry that produced the 403."""
        import app as flask_app_module

        from database import DB_PATH as lazily_imported

        self.assertEqual(
            Path(flask_app_module.database.DB_PATH).resolve(),
            Path(lazily_imported).resolve(),
            "app.py and a lazy `from database import ...` disagree about the "
            "database file -- exports saved through one are invisible to the other",
        )

    def test_the_module_object_is_singular(self):
        self.assertIs(
            sys.modules.get("database"),
            database,
            "`database` was reimported; two module objects now hold two DB_PATHs",
        )

    def test_the_download_lookup_sees_projects_the_app_just_saved(self):
        """End to end, without a browser: save, then resolve by package id."""
        from services.quality.download_pipeline_agent import _load_project_by_package_id

        package_id = "identity-guard-fixture-pkg"
        project = database.create_project(
            name="Database identity guard fixture",
            type_="product",
            data={"product_type": "ebook", "export_package_id": package_id},
        )
        self.addCleanup(database.delete_project, project["id"])

        found = _load_project_by_package_id(package_id)
        self.assertIsNotNone(
            found,
            "the download pipeline cannot see a project the application just "
            "saved -- it is reading a different database file",
        )
        self.assertEqual(found["id"], project["id"])


# ------------------------------------------------------- the guard itself ---


class LeakIsUndoneBetweenTestsTests(unittest.TestCase):
    """Reproduce the original pollution, then prove it does not survive.

    These two run in declaration order within the class. The first commits the
    exact offence -- redirect the environment variable, drop the module -- and
    deliberately cleans up nothing. The second asserts the session database is
    back, which is only true if the conftest guard put it there.
    """

    def test_a_redirects_the_database_and_cleans_up_nothing(self):
        import tempfile

        stray = os.path.join(tempfile.mkdtemp(prefix="leak_probe_"), "stray.db")
        os.environ["FACTORY_DB_PATH"] = stray
        sys.modules.pop("database", None)
        import database as reimported

        self.assertEqual(Path(reimported.DB_PATH).resolve(), Path(stray).resolve())
        self.assertIsNot(reimported, database, "the probe did not actually reimport")

    def test_b_the_next_test_still_has_the_session_database(self):
        self.assertEqual(
            os.environ.get("FACTORY_DB_PATH"),
            SESSION_DB,
            "the environment variable was not restored after the leaking test",
        )
        self.assertIs(
            sys.modules.get("database"),
            database,
            "the reimported module was not swapped back",
        )
        self.assertEqual(
            Path(sys.modules["database"].DB_PATH).resolve(),
            Path(SESSION_DB).resolve(),
        )


# ------------------------------------------------ the guard, and the habit ---


class NoTestMayKeepTheDatabaseTests(unittest.TestCase):
    """Source checks, so a reintroduction is caught at the point of writing."""

    def _test_sources(self):
        for path in sorted(TESTS_DIR.glob("test_*.py")):
            if path.name == Path(__file__).name:
                continue
            yield path, path.read_text(encoding="utf-8")

    def test_no_test_deletes_the_database_module(self):
        offenders = []
        for path, src in self._test_sources():
            stripped = re.sub(r"^\s*#.*$", "", src, flags=re.M)
            for match in re.finditer(
                r"(?:del\s+sys\.modules|sys\.modules\.pop)\s*[\[(]\s*([^\])]*)", stripped
            ):
                if "database" in match.group(1):
                    offenders.append(path.name)
        self.assertEqual(
            offenders,
            [],
            "reimporting `database` creates a second module object; code that "
            "imports it lazily then reads a different file from app.py. Point "
            "database.DB_PATH at the temporary file instead, and restore it.",
        )

    def test_a_test_that_redirects_the_database_also_restores_it(self):
        offenders = []
        for path, src in self._test_sources():
            stripped = re.sub(r"^\s*#.*$", "", src, flags=re.M)
            redirects = re.search(
                r"""os\.environ\[["']FACTORY_DB_PATH["']\]\s*=|database\.DB_PATH\s*=""",
                stripped,
            )
            if not redirects:
                continue
            restores = re.search(
                r"addCleanup|def tearDown|tearDownClass|monkeypatch\.(setenv|setattr)",
                stripped,
            )
            if not restores:
                offenders.append(path.name)
        self.assertEqual(
            offenders,
            [],
            "these tests redirect the database with no visible cleanup; a test "
            "may borrow the database, but it must give it back",
        )

    def test_the_session_guard_is_installed(self):
        src = (TESTS_DIR / "conftest.py").read_text(encoding="utf-8")
        self.assertIn("keep_one_database_for_the_whole_session", src)
        self.assertIn("FACTORY_DB_PATH", src)
        self.assertIn("sys.modules[\"database\"] = session_module", src)
        self.assertIn("pytest_runtest_teardown", src)


if __name__ == "__main__":
    unittest.main()
