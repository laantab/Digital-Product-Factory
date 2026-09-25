"""v1.9.8 -- a book exported again downloads its NEW files, not a stale copy.

Container Gardening for Beginners, live, 2026-09-25: re-exported on the
builder, status Finished 100%, but /download kept serving the website's own
older copy, which the download check correctly refused
(export_sha256_mismatch) -- 403 for both PDF and ZIP, even after a restart,
because that copy lives on the website's persistent disk.

Zero cost: in-memory storage, a temporary exports folder, no paid call.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ["FACTORY_TEST_MODE"] = "1"

import pytest  # noqa: E402

import database  # noqa: E402
import services.storage.compat as compat  # noqa: E402
from services.storage.base import sha256_hex  # noqa: E402
from services.storage.keys import export_object_key  # noqa: E402
from tests.test_builder_images_travel_through_storage import InMemoryDriver  # noqa: E402

OLD = b"%PDF-1.4 the book as it was exported the first time" + b"\0" * 200
NEW = b"%PDF-1.4 the book exported again, with its new digest" + b"\1" * 200


@pytest.fixture
def world():
    database.init_db()
    project = database.create_project("Stale Copy Garden Book", "ebook", {"title": "Stale Copy Garden Book"})
    pid = int(project["id"])
    pkg = f"ebook-{pid}"
    root = Path(tempfile.mkdtemp(prefix="website-exports-"))
    (root / pkg).mkdir(parents=True)
    driver = InMemoryDriver()
    with patch("services.storage.get_storage", return_value=driver), \
         patch("services.storage.compat.get_storage", return_value=driver):
        yield {"pid": pid, "pkg": pkg, "root": root, "driver": driver}


def _publish(w, payload):
    key = export_object_key(w["pid"], f"{w['pkg']}/ebook.pdf")
    w["driver"].put(key, payload)
    database.record_asset(w["pid"], "export_file", key, content_type="application/pdf",
                          byte_size=len(payload), checksum=sha256_hex(payload), approved=True)


def test_a_stale_local_copy_is_replaced_by_the_newer_stored_export(world):
    local = world["root"] / world["pkg"] / "ebook.pdf"
    local.write_bytes(OLD)          # the website's copy from the first export
    _publish(world, NEW)            # the builder's re-export
    assert compat.refresh_stale_export(world["root"], world["pkg"], "ebook.pdf") is True
    assert local.read_bytes() == NEW


def test_a_matching_local_copy_is_left_alone(world):
    local = world["root"] / world["pkg"] / "ebook.pdf"
    local.write_bytes(NEW)
    _publish(world, NEW)
    before = local.stat().st_mtime_ns
    assert compat.refresh_stale_export(world["root"], world["pkg"], "ebook.pdf") is False
    assert local.stat().st_mtime_ns == before


def test_stored_bytes_that_fail_verification_never_replace_the_local_copy(world):
    local = world["root"] / world["pkg"] / "ebook.pdf"
    local.write_bytes(OLD)
    _publish(world, NEW)
    key = export_object_key(world["pid"], f"{world['pkg']}/ebook.pdf")
    world["driver"].objects[key] = b"%PDF-1.4 corrupted in storage" + b"\2" * 200
    assert compat.refresh_stale_export(world["root"], world["pkg"], "ebook.pdf") is False
    assert local.read_bytes() == OLD


def test_an_unapproved_record_never_replaces_the_local_copy(world):
    local = world["root"] / world["pkg"] / "ebook.pdf"
    local.write_bytes(OLD)
    key = export_object_key(world["pid"], f"{world['pkg']}/ebook.pdf")
    world["driver"].put(key, NEW)
    database.record_asset(world["pid"], "export_file", key, content_type="application/pdf",
                          byte_size=len(NEW), checksum=sha256_hex(NEW), approved=False)
    assert compat.refresh_stale_export(world["root"], world["pkg"], "ebook.pdf") is False
    assert local.read_bytes() == OLD


def test_no_local_copy_means_nothing_to_refresh(world):
    _publish(world, NEW)
    assert compat.refresh_stale_export(world["root"], world["pkg"], "ebook.pdf") is False


def test_the_download_route_refreshes_before_serving():
    text = Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")
    route = text[text.index("def download_export_route"):]
    route = route[:route.index("\n@app.")]
    assert route.index("refresh_stale_export(") < route.index("pipeline_download(")
