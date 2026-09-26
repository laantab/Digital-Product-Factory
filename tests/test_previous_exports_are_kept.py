"""v1.9.11 -- exporting a book again keeps its previous PDF and ZIP, verified.

Container Gardening for Beginners was re-exported while its only copies were
at the key the export overwrites. Now the old file is copied aside, read back
and checksum-verified first; if that fails, the new file is not written.
"""
from __future__ import annotations

import hashlib
import os
from unittest.mock import patch

os.environ["FACTORY_TEST_MODE"] = "1"

import pytest  # noqa: E402

import database  # noqa: E402
from services.storage import publish  # noqa: E402
from services.storage.keys import export_object_key  # noqa: E402
from tests.test_builder_images_travel_through_storage import InMemoryDriver  # noqa: E402

OLD = b"%PDF-1.4 first export" + b"\0" * 300
NEW = b"%PDF-1.4 second export" + b"\1" * 300


@pytest.fixture
def world():
    database.init_db()
    pid = int(database.create_project("Keep Previous Book", "ebook", {"title": "Keep Previous Book"})["id"])
    drv = InMemoryDriver()
    with patch("services.storage.get_storage", return_value=drv), \
         patch("services.storage.compat.get_storage", return_value=drv), \
         patch.object(publish, "publishing_enabled", lambda: True):
        yield pid, drv


def test_the_previous_pdf_is_kept_verified_and_recorded(world):
    pid, drv = world
    rel = f"ebook-{pid}/ebook.pdf"
    assert publish.publish_export(pid, rel, payload=OLD, content_type="application/pdf")
    assert publish.publish_export(pid, rel, payload=NEW, content_type="application/pdf")
    old_sha = hashlib.sha256(OLD).hexdigest()
    prev_key = export_object_key(pid, publish.previous_relative_path(rel, old_sha))
    assert drv.get(prev_key) == OLD
    assert drv.get(export_object_key(pid, rel)) == NEW
    rows = [r for r in database.list_assets(pid) if r["kind"] == "export_previous"]
    assert len(rows) == 1 and rows[0]["checksum"] == old_sha and rows[0]["approved"]


def test_the_same_bytes_again_keep_nothing_extra(world):
    pid, drv = world
    rel = f"ebook-{pid}/package.zip"
    publish.publish_export(pid, rel, payload=OLD)
    publish.publish_export(pid, rel, payload=OLD)
    assert not [r for r in database.list_assets(pid) if r["kind"] == "export_previous"]


def test_if_the_previous_copy_cannot_be_verified_the_new_file_is_not_written(world):
    pid, drv = world
    rel = f"ebook-{pid}/ebook.pdf"
    publish.publish_export(pid, rel, payload=OLD)
    real_put = drv.put

    def bad_put(key, data, **kw):
        if "/previous/" in key:
            return real_put(key, b"corrupted", **kw)
        return real_put(key, data, **kw)

    drv.put = bad_put
    assert publish.publish_export(pid, rel, payload=NEW) is False
    assert drv.get(export_object_key(pid, rel)) == OLD          # the original is untouched


def test_other_files_are_not_archived(world):
    pid, drv = world
    rel = f"ebook-{pid}/visuals/v_ch1.png"
    publish.publish_export(pid, rel, payload=OLD)
    publish.publish_export(pid, rel, payload=NEW)
    assert not [r for r in database.list_assets(pid) if r["kind"] == "export_previous"]


def test_the_owner_can_list_and_download_the_previous_version(world):
    import app as app_module

    pid, drv = world
    rel = f"ebook-{pid}/ebook.pdf"
    publish.publish_export(pid, rel, payload=OLD)
    publish.publish_export(pid, rel, payload=NEW)
    app_module.app.config["TESTING"] = True
    with patch.object(app_module, "_ebook_workspace_project_or_404", lambda p: (database.get_project(p), None)):
        c = app_module.app.test_client()
        listing = c.get(f"/ebook-workspace/{pid}/previous-exports").get_json()["previous"]
        assert [(x["name"], x["sha256"]) for x in listing] == [("ebook.pdf", hashlib.sha256(OLD).hexdigest())]
        r = c.get(listing[0]["url"])
        assert r.status_code == 200 and r.data == OLD
        assert c.get(f"/ebook-workspace/{pid}/previous-exports/0000000000000000/ebook.pdf").status_code == 404
