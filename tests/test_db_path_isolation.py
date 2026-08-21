"""Regression: the Factory test suite must never read from or write to the
real projects.db or the real exports/ folder.

tests/conftest.py sets FACTORY_DB_PATH / FACTORY_EXPORTS_DIR / FLASK_EXPORTS_DIR
to a fresh temporary directory before any Factory application module is
imported. This test proves that importing database (and the service modules
that resolve their own EXPORTS_DIR at import time) during a pytest run
resolves to that temporary location, not to the real files on disk.

Zero paid/external calls. Pure import + path assertions, no DB writes.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import database  # noqa: E402


class DatabasePathIsolationTests(unittest.TestCase):
    def test_factory_db_path_env_is_set_before_collection(self):
        env_value = os.environ.get("FACTORY_DB_PATH")
        self.assertTrue(
            env_value,
            "FACTORY_DB_PATH was not set before test collection — "
            "tests/conftest.py isolation did not run.",
        )

    def test_database_module_resolved_to_temp_db_not_real_db(self):
        real_db = (ROOT / "projects.db").resolve()
        resolved = Path(database.DB_PATH).resolve()
        self.assertNotEqual(
            resolved,
            real_db,
            "database.DB_PATH resolved to the real projects.db during tests. "
            "Test isolation in tests/conftest.py failed to take effect before "
            "database.py was imported.",
        )
        env_value = os.environ.get("FACTORY_DB_PATH")
        self.assertEqual(
            resolved,
            Path(env_value).resolve(),
            "database.DB_PATH does not match the FACTORY_DB_PATH set by "
            "tests/conftest.py — some other code path is overriding it.",
        )

    def test_real_projects_db_is_not_the_active_db(self):
        real_db = (ROOT / "projects.db").resolve()
        self.assertTrue(real_db.is_file(), "sanity check: real projects.db should exist")
        # The active DB_PATH must not point at that exact file.
        self.assertNotEqual(Path(database.DB_PATH).resolve(), real_db)

    def test_ebook_package_exports_dir_is_isolated(self):
        from services.ebook_package import EXPORTS_DIR as ebook_exports_dir

        real_exports = (ROOT / "exports").resolve()
        resolved = Path(ebook_exports_dir).resolve()
        self.assertNotEqual(
            resolved,
            real_exports,
            "services.ebook_package.EXPORTS_DIR resolved to the real exports/ "
            "folder during tests.",
        )

    def test_coloring_book_builder_exports_dir_is_isolated(self):
        from services.coloring_book.builder import EXPORTS_DIR as coloring_exports_dir

        real_exports = (ROOT / "exports").resolve()
        resolved = Path(coloring_exports_dir).resolve()
        self.assertNotEqual(
            resolved,
            real_exports,
            "services.coloring_book.builder.EXPORTS_DIR resolved to the real "
            "exports/ folder during tests.",
        )

    def test_preview_assets_exports_dir_is_isolated(self):
        from services.coloring_book.preview_assets import EXPORTS_DIR as preview_exports_dir

        real_exports = (ROOT / "exports").resolve()
        resolved = Path(preview_exports_dir).resolve()
        self.assertNotEqual(
            resolved,
            real_exports,
            "services.coloring_book.preview_assets.EXPORTS_DIR resolved to the "
            "real exports/ folder during tests.",
        )

    def test_final_output_gate_exports_and_quarantine_dirs_are_isolated(self):
        from services.quality.final_output_gate import EXPORTS_DIR as gate_exports_dir
        from services.quality.final_output_gate import QUARANTINE_DIR as gate_quarantine_dir

        real_exports = (ROOT / "exports").resolve()
        resolved_exports = Path(gate_exports_dir).resolve()
        resolved_quarantine = Path(gate_quarantine_dir).resolve()
        self.assertNotEqual(
            resolved_exports,
            real_exports,
            "services.quality.final_output_gate.EXPORTS_DIR resolved to the "
            "real exports/ folder during tests.",
        )
        self.assertEqual(
            resolved_quarantine,
            resolved_exports / "_quarantined",
            "QUARANTINE_DIR must derive from the configured EXPORTS_DIR.",
        )
        self.assertFalse(
            str(resolved_quarantine).startswith(str(real_exports)),
            "QUARANTINE_DIR resolved underneath the real exports/ folder during tests.",
        )

    def test_quarantine_export_folder_never_touches_real_exports(self):
        """Exercise quarantine_export_folder end-to-end and prove every path it
        touches stays inside the isolated temp exports root."""
        from services.quality.final_output_gate import (
            EXPORTS_DIR as gate_exports_dir,
        )
        from services.quality.final_output_gate import quarantine_export_folder

        real_exports = (ROOT / "exports").resolve()
        package_id = "isolation_regression_probe_pkg"
        src = Path(gate_exports_dir) / package_id
        src.mkdir(parents=True, exist_ok=True)
        (src / "probe.txt").write_text("isolation probe", encoding="utf-8")
        try:
            moved = quarantine_export_folder(package_id)
            self.assertTrue(moved)
            quarantined_path = Path(gate_exports_dir) / "_quarantined" / package_id
            self.assertTrue(quarantined_path.is_dir())
            self.assertFalse(
                str(quarantined_path.resolve()).startswith(str(real_exports)),
                "quarantine_export_folder wrote underneath the real exports/ "
                "folder during tests.",
            )
            self.assertFalse(
                (real_exports / package_id).exists(),
                "quarantine_export_folder's source package unexpectedly "
                "existed under the real exports/ folder.",
            )
        finally:
            shutil.rmtree(Path(gate_exports_dir) / "_quarantined" / package_id, ignore_errors=True)
            shutil.rmtree(src, ignore_errors=True)


class FrozenProject2472FixtureTests(unittest.TestCase):
    """The sanitized tests/fixtures/frozen_project_2472.json fixture must seed
    into the isolated temp database (never the real one) and reproduce the
    exact immutable values the eight #2472-dependent test files assert."""

    def test_2472_seeded_only_in_isolated_temp_db(self):
        from services.ebook_manuscript_engine import (
            FROZEN_2472_REMAINING_USD,
            FROZEN_2472_SHA256,
            FROZEN_2472_SPENT_USD,
        )

        live = database.get_project(2472)
        self.assertIsNotNone(live, "fixture project #2472 was not seeded into the temp DB")
        content = str(live["data"].get("content") or "")
        self.assertEqual(hashlib.sha256(content.encode("utf-8")).hexdigest(), FROZEN_2472_SHA256)
        ledger = live["data"]["ebook_workspace"]["paid_call_ledger"]
        self.assertAlmostEqual(float(ledger["spent_usd"]), FROZEN_2472_SPENT_USD, places=3)
        self.assertAlmostEqual(float(ledger["remaining_usd"]), FROZEN_2472_REMAINING_USD, places=3)

    def test_2472_fixture_file_has_no_absolute_local_paths(self):
        fixture_path = ROOT / "tests" / "fixtures" / "frozen_project_2472.json"
        raw = fixture_path.read_text(encoding="utf-8")
        self.assertNotIn(str(ROOT), raw)
        self.assertNotIn("C:\\\\Users", raw)


if __name__ == "__main__":
    unittest.main()
