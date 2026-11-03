"""Preservation tests use isolated databases and never import a provider."""
import copy
from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import tempfile
from pathlib import Path
import unittest

from services.ebook_v2.legacy_snapshot import Snapshots, snapshot
from services.ebook_v2.recovery import CorruptCheckpoint, InputConflict


class LegacySnapshots(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "isolated.sqlite"
        self.store = Snapshots(self.connect)
        self.store.initialize()
        self.project = {"id": 42, "user_id": 7, "type": "ebook", "version": 3,
                        "name": "Preserved book", "data": {
                            "content": "# Book\n\nExact original — text\n",
                            "ebook_workspace": {"accepted_chapters": [
                                {"order": 1, "title": "First", "body": "Saved text.\n"}],
                                "pending": {"body": "Unapproved text.", "quality": "FAIL"}},
                            "export": {"storage_key": "existing-private-object"}}}

    def connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def test_save_reopen_preserves_all_data_without_changing_source(self):
        before = copy.deepcopy(self.project)
        key = self.store.save(self.project, 7)
        restored = Snapshots(self.connect).reopen(7, key)
        self.assertEqual(restored["data"], before["data"])
        self.assertEqual(self.project, before)
        self.project["data"]["content"] = "Changed after save"
        self.assertEqual(restored["data"]["content"], before["data"]["content"])

    def test_other_account_cannot_save_or_reopen(self):
        with self.assertRaises(LookupError):
            self.store.save(self.project, 8)
        key = self.store.save(self.project, 7)
        with self.assertRaises(LookupError):
            self.store.reopen(8, key)

    def test_unowned_and_unversioned_projects_fail_closed(self):
        for field in ("user_id", "version", "id"):
            project = copy.deepcopy(self.project)
            project.pop(field)
            with self.assertRaises((LookupError, ValueError)):
                snapshot(project, 7)

    def test_duplicate_save_is_idempotent_and_changed_version_is_retained(self):
        key = self.store.save(self.project, 7)
        self.assertEqual(self.store.save(self.project, 7), key)
        self.project["version"] += 1
        self.project["data"]["content"] = "New draft"
        newer = self.store.save(self.project, 7)
        self.assertNotEqual(key, newer)
        self.assertNotEqual(self.store.reopen(7, key)["data"], self.store.reopen(7, newer)["data"])

    def test_same_version_cannot_silently_replace_preserved_content(self):
        key = self.store.save(self.project, 7)
        original = self.store.reopen(7, key)
        self.project["data"]["content"] = "Different bytes"
        with self.assertRaises(InputConflict):
            self.store.save(self.project, 7)
        self.assertEqual(self.store.reopen(7, key), original)

    def test_corrupt_saved_payload_is_not_returned(self):
        key = self.store.save(self.project, 7)
        # sqlite3's transaction context commits but does not close the file.
        # Close explicitly before TemporaryDirectory cleanup on Windows.
        with closing(self.connect()) as conn:
            with conn:
                conn.execute("UPDATE ebook_v2_legacy_snapshots SET payload='{}' WHERE id=?", (key,))
        with self.assertRaises(CorruptCheckpoint):
            self.store.reopen(7, key)

    def test_concurrent_saves_keep_one_snapshot(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            keys = list(pool.map(lambda _: self.store.save(self.project, 7), range(4)))
        self.assertEqual(len(set(keys)), 1)


if __name__ == "__main__":
    unittest.main()
