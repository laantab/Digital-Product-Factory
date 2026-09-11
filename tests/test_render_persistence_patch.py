"""Render persistence: first boot on an empty volume (2026-09-11).

The Render persistence runbook (28 Aug) found that pointing FACTORY_DB_PATH
at a freshly mounted disk (e.g. /var/data/projects.db) failed on first boot
with "unable to open database file", because sqlite3 does not create missing
parent directories. database.get_conn() now creates the directory first.
This file proves that, and that an existing directory is left alone.

No external/paid API call is made by any test in this file.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FACTORY_TEST_MODE", "1")

import database  # noqa: E402


class _TempDbPath:
    """Point database.DB_PATH at `target` for one test, then restore it."""

    def __init__(self, target: str):
        self.target = target

    def __enter__(self):
        self._orig = database.DB_PATH
        database.DB_PATH = self.target
        return self

    def __exit__(self, *exc):
        database.DB_PATH = self._orig
        return False


class FreshVolumeTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="factory_fresh_volume_")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_first_boot_on_a_missing_parent_directory_succeeds(self):
        # Two missing levels, like /var/data on a brand-new Render disk. (The
        # file is named factory.sqlite rather than the production name on
        # purpose: tests/test_no_hardcoded_production_paths.py forbids the
        # literal production filename in test code, and the patch under test
        # is about the missing DIRECTORY, not the file's name.)
        target = os.path.join(self.root, "var", "data", "factory.sqlite")
        self.assertFalse(os.path.isdir(os.path.dirname(target)))
        with _TempDbPath(target):
            database.init_db()
            self.assertTrue(os.path.isfile(target))
            conn = database.get_conn()
            try:
                tables = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'")}
            finally:
                conn.close()
        self.assertIn("projects", tables)

    def test_an_existing_directory_is_left_alone(self):
        existing = os.path.join(self.root, "already-there")
        os.makedirs(existing)
        marker = os.path.join(existing, "keep.txt")
        with open(marker, "w", encoding="utf-8") as fh:
            fh.write("untouched")
        with _TempDbPath(os.path.join(existing, "factory.sqlite")):
            database.init_db()
        self.assertTrue(os.path.isfile(marker))
        with open(marker, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "untouched")


if __name__ == "__main__":
    unittest.main()
