"""Images the builder makes reach the website — v1.8.1.

THE PROBLEM THIS TESTS
----------------------
The website and the builder are two Render services with two filesystems.
A cover the builder renders onto its own disk is on a disk the website
cannot read, and that disk disappears when the task ends. The customer
would sit watching for a cover that had already been built and could never
be served.

So anything the builder produces that the website must serve goes through
the storage driver. These tests use a fake driver with NO filesystem behind
it, so a read that only works because both halves happen to share a disk
cannot pass.

Zero cost: no image is downloaded or generated; the payloads are literal
bytes.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

import database
from services.storage.base import StorageDriver, StorageKeyNotFound, StorageStat, sha256_hex


class InMemoryDriver(StorageDriver):
    """A storage driver with no disk at all.

    If a test passes with this driver, the bytes really did travel through
    storage: there is nowhere else they could have come from.
    """

    name = "memory"

    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def put(self, key, data, *, content_type="application/octet-stream"):
        self.objects[key] = bytes(data)
        return StorageStat(key=key, size=len(data), checksum=sha256_hex(data),
                           content_type=content_type)

    def get(self, key):
        if key not in self.objects:
            raise StorageKeyNotFound(key)
        return self.objects[key]

    def exists(self, key):
        return key in self.objects

    def delete(self, key):
        return self.objects.pop(key, None) is not None

    def stat(self, key):
        if key not in self.objects:
            return None
        blob = self.objects[key]
        return StorageStat(key=key, size=len(blob), checksum=sha256_hex(blob),
                           content_type="application/octet-stream")

    def verify(self, key, *, expected_checksum, expected_size):
        blob = self.objects.get(key)
        return (blob is not None and len(blob) == expected_size
                and sha256_hex(blob) == expected_checksum)


def _project(title="Images through storage"):
    p = database.create_project(title, "ebook", {"title": title})
    return int(p["id"] if isinstance(p, dict) else p)


class PublishedFilesAreReadableByTheWebProcessTests(unittest.TestCase):

    def setUp(self):
        self.driver = InMemoryDriver()
        # compat.py binds get_storage at import time, publish.py imports it
        # inside the function. Both have to point at the fake driver or the
        # test would silently exercise the real one.
        for target in ("services.storage.get_storage",
                       "services.storage.compat.get_storage"):
            patch_driver = mock.patch(target, return_value=self.driver)
            self.addCleanup(patch_driver.stop)
            patch_driver.start()
        # Publishing is on in workflow mode; force it on directly so the test
        # does not depend on the rest of the mode plumbing.
        env = mock.patch.dict(os.environ, {"FACTORY_PUBLISH_EXPORTS": "1"})
        self.addCleanup(env.stop)
        env.start()
        self.pid = _project()

    def test_a_builder_produced_file_is_readable_with_no_shared_disk(self):
        from services.storage.compat import read_export_or_legacy
        from services.storage.publish import publish_export

        payload = b"PNG-ish cover bytes" * 64
        self.assertTrue(
            publish_export(self.pid, "pkg-1/variants/a/full/cover.png",
                           payload=payload, kind="cover",
                           content_type="image/png"))

        # The web process, with no path on disk to fall back to.
        got = read_export_or_legacy(self.pid, "pkg-1/variants/a/full/cover.png")
        self.assertEqual(got, payload,
                         "the website could not read a file the builder made")

    def test_an_unpublished_file_is_simply_absent(self):
        """The reader must not invent bytes when nothing was published."""
        from services.storage.compat import read_export_or_legacy

        self.assertIsNone(
            read_export_or_legacy(self.pid, "pkg-1/never/published.png"))

    def test_publishing_verifies_before_it_records(self):
        """An asset row pointing at bytes that are not there is worse than none.

        The reader trusts a recorded asset and stops falling back to disk, so
        recording one that cannot be read would turn a servable cover into a
        missing one.
        """
        from services.storage.publish import publish_export

        with mock.patch.object(self.driver, "stat", return_value=None):
            self.assertFalse(
                publish_export(self.pid, "pkg-1/bad.png", payload=b"x" * 32))

    def test_publishing_is_off_inline_so_local_development_is_unchanged(self):
        from services.storage.publish import publish_export, publishing_enabled

        with mock.patch.dict(os.environ, {"FACTORY_PUBLISH_EXPORTS": "0"}):
            self.assertFalse(publishing_enabled())
            self.assertFalse(publish_export(self.pid, "pkg-1/x.png",
                                            payload=b"y" * 32))
        self.assertEqual(self.driver.objects, {})

    def test_a_storage_failure_never_raises_into_a_build(self):
        """One missing picture must not throw away a whole book."""
        from services.storage.publish import publish_export

        with mock.patch.object(self.driver, "put",
                               side_effect=RuntimeError("R2 is down")):
            self.assertFalse(
                publish_export(self.pid, "pkg-1/x.png", payload=b"z" * 32))

    def test_a_path_outside_the_exports_root_is_not_published(self):
        """Publishing is for exports, not for whatever path it is handed."""
        from services.storage.publish import publish_file

        self.assertFalse(
            publish_file(self.pid, "/tmp/exports", "/etc/passwd"))


class UploadedCoverReachesTheBuilderTests(unittest.TestCase):
    """The reverse direction: the customer uploads, the builder reads."""

    def setUp(self):
        self.driver = InMemoryDriver()
        p = mock.patch("services.storage.get_storage", return_value=self.driver)
        self.addCleanup(p.stop)
        p.start()

    def test_the_bytes_survive_the_trip(self):
        from services import ebook_workspace_actions as wsa

        raw = b"\\x89PNG" + b"customer's own photograph" * 16
        self.driver.put("uploads/cover.png", raw, content_type="image/png")

        seen = {}

        def _capture(d, blob, **k):
            seen["b"] = blob
            return d

        with mock.patch("services.ebook_photo_cover.attach_upload", _capture), \
             mock.patch("services.ebook_design_workspace.stage_photo_cover",
                        side_effect=lambda d, **k: d):
            wsa.cover_image({}, {"storage_key": "uploads/cover.png",
                                 "filename": "mine.png"}, project_id=1)
        self.assertEqual(seen["b"], raw)


if __name__ == "__main__":
    unittest.main()
