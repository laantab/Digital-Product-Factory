"""LOCKED projects cannot be deleted, pruned, or have assets removed.

Deterministic local fixtures under FACTORY_TEST_MODE — zero paid/external calls.
Uses an isolated SQLite file so bulk delete cannot touch live saved projects.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""
os.environ["PEXELS_API_KEY"] = ""

from app import app  # noqa: E402
import database  # noqa: E402
from services.quality.artifact_identity import stamp_artifact_identity  # noqa: E402
from services.quality.artifact_state import (  # noqa: E402
    ArtifactState,
    ArtifactStateError,
    LOCKED_DELETION_MESSAGE,
    assert_content_mutation_allowed,
    assert_project_deletion_allowed,
    project_is_locked,
    resolve_artifact_state,
)


def _paid_patches():
    return (
        patch("ai_client.get_client", side_effect=AssertionError("paid client")),
        patch("ai_client.chat", side_effect=AssertionError("paid chat")),
        patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json")),
    )


def _draft_data(**extra) -> dict:
    pkg = extra.pop("package_id", None) or f"lockdel-draft-{uuid.uuid4().hex[:12]}"
    data = {
        "product_type": "math_worksheet",
        "title": "LockDel Draft Worksheet",
        "package_id": pkg,
        "artifact_id": pkg,
        "artifact_revision": 1,
        "artifact_state": ArtifactState.DRAFT.value,
        "problems": [{"prompt": "1+1", "answer": "2"}],
        "exports": {"folder": f"exports/{pkg}"},
        "export_package_id": pkg,
        "cover_design": {"local_image_path": f"exports/{pkg}/img_cover.png"},
    }
    data.update(extra)
    return data


def _approved_data(**extra) -> dict:
    pkg = extra.pop("package_id", None) or f"lockdel-approved-{uuid.uuid4().hex[:12]}"
    data = _draft_data(
        title="LockDel Approved Worksheet",
        package_id=pkg,
        artifact_id=pkg,
        qa_status="accepted",
        content_digest="a" * 64,
        asset_manifest_digest="b" * 64,
        artifact_state=ArtifactState.APPROVED.value,
    )
    stamp_artifact_identity(data)
    data["artifact_state"] = ArtifactState.APPROVED.value
    data.update(extra)
    return data


def _locked_data(**extra) -> dict:
    pkg = extra.pop("package_id", None) or f"lockdel-locked-{uuid.uuid4().hex[:12]}"
    data = _approved_data(
        title="LockDel Locked Worksheet",
        package_id=pkg,
        artifact_id=pkg,
        book_locked=True,
        lock_status="LOCKED",
        locked_at="2026-08-14T00:00:00Z",
        artifact_state=ArtifactState.LOCKED.value,
    )
    data.update(extra)
    return data


def _write_assets(exports_root: Path, data: dict) -> Path:
    pkg = str(data.get("package_id") or data.get("export_package_id") or "pkg")
    folder = exports_root / pkg
    folder.mkdir(parents=True, exist_ok=True)
    marker = folder / "img_cover.png"
    marker.write_bytes(b"locked-asset-bytes")
    (folder / "interior.pdf").write_bytes(b"%PDF-1.4\n%%EOF\n")
    return marker


class LockedProjectDeletionTests(unittest.TestCase):
    def setUp(self):
        self._patches = _paid_patches()
        for p in self._patches:
            p.start()
        self._tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp_db.close()
        self._old_db = database.DB_PATH
        database.DB_PATH = self._tmp_db.name
        database.init_db()
        self._asset_root = Path(tempfile.mkdtemp(prefix="lockdel-assets-"))
        self.client = app.test_client()
        app.config["TESTING"] = True

    def tearDown(self):
        for p in self._patches:
            p.stop()
        database.DB_PATH = self._old_db
        shutil.rmtree(self._asset_root, ignore_errors=True)
        for suffix in ("", "-wal", "-shm"):
            path = self._tmp_db.name + suffix
            try:
                os.unlink(path)
            except OSError:
                pass
        parent = Path(self._tmp_db.name).parent
        stem = Path(self._tmp_db.name).name
        for leftover in parent.glob(f"{stem}*"):
            try:
                leftover.unlink()
            except OSError:
                pass

    def _create(
        self,
        data: dict,
        *,
        name: str,
        user_saved: bool = True,
        system_test: bool = False,
        temporary: bool = False,
    ) -> int:
        project = database.create_project(
            name,
            "product",
            data,
            user_saved=user_saved,
            system_test=system_test,
            temporary=temporary,
        )
        return int(project["id"])

    def test_single_locked_delete_returns_409(self):
        data = _locked_data()
        marker = _write_assets(self._asset_root, data)
        pid = self._create(data, name="LockDel Single Locked")
        resp = self.client.delete(f"/projects/{pid}")
        self.assertEqual(resp.status_code, 409, resp.data)
        self.assertEqual(resp.get_json().get("error"), LOCKED_DELETION_MESSAGE)
        self.assertIsNotNone(database.get_project(pid))
        self.assertTrue(marker.is_file())
        self.assertEqual(marker.read_bytes(), b"locked-asset-bytes")

    def test_database_delete_project_raises_for_locked(self):
        pid = self._create(_locked_data(), name="LockDel DB Locked")
        with self.assertRaises(ArtifactStateError) as ctx:
            database.delete_project(pid)
        self.assertEqual(str(ctx.exception), LOCKED_DELETION_MESSAGE)
        self.assertIsNotNone(database.get_project(pid))

    def test_bulk_mixed_locked_and_unlocked(self):
        locked = _locked_data()
        unlocked = _draft_data()
        locked_marker = _write_assets(self._asset_root, locked)
        unlocked_marker = _write_assets(self._asset_root, unlocked)
        locked_id = self._create(locked, name="LockDel Bulk Locked")
        unlocked_id = self._create(unlocked, name="LockDel Bulk Unlocked")
        result = database.delete_matching_projects(
            "id IN (?, ?)", (locked_id, unlocked_id)
        )
        self.assertEqual(result["deleted"], 1)
        self.assertEqual(result["locked_skipped"], 1)
        self.assertEqual(result["skipped_ids"], [locked_id])
        self.assertIsNone(database.get_project(unlocked_id))
        self.assertIsNotNone(database.get_project(locked_id))
        self.assertTrue(locked_marker.is_file())
        self.assertTrue(unlocked_marker.is_file())

    def test_delete_all_saved_projects_skips_locked(self):
        locked_id = self._create(_locked_data(), name="LockDel Saved Locked")
        unlocked_id = self._create(_draft_data(), name="LockDel Saved Unlocked")
        extra_locked = self._create(_locked_data(), name="LockDel Saved Locked Two")
        resp = self.client.delete("/projects?delete_all=1&user_saved_only=1")
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.get_json()
        self.assertTrue(body.get("ok"))
        self.assertEqual(body.get("deleted"), 1)
        self.assertEqual(body.get("locked_skipped"), 2)
        self.assertEqual(sorted(body.get("skipped_ids") or []), sorted([locked_id, extra_locked]))
        self.assertIsNone(database.get_project(unlocked_id))
        self.assertIsNotNone(database.get_project(locked_id))
        self.assertIsNotNone(database.get_project(extra_locked))

    def test_admin_delete_test_projects_skips_locked(self):
        locked_id = self._create(
            _locked_data(),
            name="[TEST] Debug LockDel Hidden",
            user_saved=False,
            system_test=True,
            temporary=True,
        )
        unlocked_id = self._create(
            _draft_data(),
            name="[TEST] Debug LockDel Unlocked",
            user_saved=False,
            system_test=True,
            temporary=True,
        )
        resp = self.client.delete("/admin/delete-test-projects")
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.get_json()
        self.assertEqual(body.get("deleted"), 1)
        self.assertEqual(body.get("locked_skipped"), 1)
        self.assertEqual(body.get("skipped_ids"), [locked_id])
        self.assertIsNone(database.get_project(unlocked_id))
        self.assertIsNotNone(database.get_project(locked_id))

    def test_cleanup_prune_and_orphan_paths_skip_locked(self):
        data = _locked_data()
        marker = _write_assets(self._asset_root, data)
        pid = self._create(data, name="LockDel Cleanup Locked")
        with self.assertRaises(ArtifactStateError) as ctx:
            database.cleanup_project_storage(
                pid, exports_root=self._asset_root, remove_assets=True, remove_db_row=True
            )
        self.assertEqual(str(ctx.exception), LOCKED_DELETION_MESSAGE)
        self.assertIsNotNone(database.get_project(pid))
        self.assertTrue(marker.is_file())
        with self.assertRaises(ArtifactStateError):
            database.remove_project_assets(pid, exports_root=self._asset_root)
        self.assertTrue(marker.is_file())
        self.assertEqual(marker.read_bytes(), b"locked-asset-bytes")

    def test_locked_assets_not_deleted_moved_or_orphaned(self):
        data = _locked_data()
        marker = _write_assets(self._asset_root, data)
        original = marker.read_bytes()
        pid = self._create(data, name="LockDel Asset Locked")
        self.client.delete(f"/projects/{pid}")
        with self.assertRaises(ArtifactStateError) as ctx:
            database.remove_project_assets(pid, exports_root=self._asset_root)
        self.assertEqual(str(ctx.exception), LOCKED_DELETION_MESSAGE)
        self.assertTrue(marker.is_file())
        self.assertEqual(marker.read_bytes(), original)
        self.assertTrue(marker.parent.is_dir())
        self.assertIsNotNone(database.get_project(pid))

    def test_database_reference_not_removed_for_locked(self):
        pid = self._create(_locked_data(), name="LockDel Ref Locked")
        with self.assertRaises(ArtifactStateError):
            database.delete_project(pid)
        row = database.get_project(pid)
        self.assertIsNotNone(row)
        self.assertEqual(resolve_artifact_state(row["data"]), ArtifactState.LOCKED)

    def test_hidden_test_debug_labels_do_not_override_locked(self):
        names = (
            "[TEST] LockDel Hidden",
            "Debug LockDel Record",
            "QA Smoke LockDel Auto",
        )
        ids = []
        for name in names:
            ids.append(
                self._create(
                    _locked_data(),
                    name=name,
                    user_saved=False,
                    system_test=True,
                    temporary=True,
                )
            )
        for pid in ids:
            resp = self.client.delete(f"/projects/{pid}")
            self.assertEqual(resp.status_code, 409, resp.data)
            self.assertEqual(resp.get_json().get("error"), LOCKED_DELETION_MESSAGE)
            self.assertIsNotNone(database.get_project(pid))
        bulk = self.client.delete("/admin/delete-test-projects")
        self.assertEqual(bulk.status_code, 200, bulk.data)
        body = bulk.get_json()
        self.assertEqual(body.get("deleted"), 0)
        self.assertEqual(body.get("locked_skipped"), 3)
        self.assertEqual(sorted(body.get("skipped_ids") or []), sorted(ids))
        for pid in ids:
            self.assertIsNotNone(database.get_project(pid))

    def test_approved_and_draft_may_still_delete(self):
        draft_data = _draft_data()
        approved_data = _approved_data()
        draft_marker = _write_assets(self._asset_root, draft_data)
        approved_marker = _write_assets(self._asset_root, approved_data)
        draft_id = self._create(draft_data, name="LockDel Draft May Delete")
        approved_id = self._create(approved_data, name="LockDel Approved May Delete")
        draft_resp = self.client.delete(f"/projects/{draft_id}")
        approved_resp = self.client.delete(f"/projects/{approved_id}")
        self.assertEqual(draft_resp.status_code, 200, draft_resp.data)
        self.assertEqual(approved_resp.status_code, 200, approved_resp.data)
        self.assertIsNone(database.get_project(draft_id))
        self.assertIsNone(database.get_project(approved_id))
        self.assertTrue(draft_marker.is_file())
        self.assertTrue(approved_marker.is_file())

    def test_no_partial_deletion_of_locked_project(self):
        data = _locked_data()
        marker = _write_assets(self._asset_root, data)
        pid = self._create(data, name="LockDel Partial Locked")
        before = database.get_project(pid)
        self.assertIsNotNone(before)
        with self.assertRaises(ArtifactStateError) as ctx:
            database.cleanup_project_storage(
                pid, exports_root=self._asset_root, remove_assets=True, remove_db_row=True
            )
        self.assertEqual(str(ctx.exception), LOCKED_DELETION_MESSAGE)
        after = database.get_project(pid)
        self.assertIsNotNone(after)
        self.assertEqual(after["data"].get("package_id"), before["data"].get("package_id"))
        self.assertEqual(after["data"].get("artifact_state"), ArtifactState.LOCKED.value)
        self.assertTrue(marker.is_file())
        self.assertTrue((marker.parent / "interior.pdf").is_file())
        self.assertEqual(resolve_artifact_state(after["data"]), ArtifactState.LOCKED)

    def test_content_mutation_protections_preserved(self):
        locked = _locked_data()
        approved = _approved_data()
        with self.assertRaises(ArtifactStateError) as locked_ctx:
            assert_content_mutation_allowed(locked, action="edit content")
        self.assertIn("LOCKED", str(locked_ctx.exception))
        with self.assertRaises(ArtifactStateError) as approved_ctx:
            assert_content_mutation_allowed(approved, action="edit content")
        self.assertIn("APPROVED", str(approved_ctx.exception))
        self.assertEqual(
            assert_content_mutation_allowed(_draft_data(), action="edit content"),
            ArtifactState.DRAFT,
        )
        self.assertEqual(LOCKED_DELETION_MESSAGE, "This project is locked and cannot be deleted.")
        self.assertTrue(project_is_locked(locked))
        self.assertFalse(project_is_locked(approved))
        self.assertFalse(project_is_locked(_draft_data()))
        with self.assertRaises(ArtifactStateError) as del_ctx:
            assert_project_deletion_allowed(locked)
        self.assertEqual(str(del_ctx.exception), LOCKED_DELETION_MESSAGE)
        self.assertEqual(assert_project_deletion_allowed(approved), ArtifactState.APPROVED)
        self.assertEqual(assert_project_deletion_allowed(_draft_data()), ArtifactState.DRAFT)

    def test_unlocked_cleanup_may_remove_assets_and_row(self):
        data = _draft_data()
        marker = _write_assets(self._asset_root, data)
        pid = self._create(data, name="LockDel Unlocked Cleanup")
        result = database.cleanup_project_storage(
            pid, exports_root=self._asset_root, remove_assets=True, remove_db_row=True
        )
        self.assertTrue(result["deleted"])
        self.assertTrue(result["assets_removed"])
        self.assertIsNone(database.get_project(pid))
        self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
