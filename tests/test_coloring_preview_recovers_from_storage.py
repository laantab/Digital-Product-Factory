"""A preview must recover the same way a download does.

/download/<package_id>/<filename> falls back to a VERIFIED stored asset when the
file is not on local disk -- that fallback is the whole point of releases
1.8.11 to 1.8.14, because the builder starts every run with an empty disk. The
coloring preview route never got it: it answered 404 on os.path.isfile alone. On
a service that has not written that file locally, the customer's download works
and the picture of it does not.
"""
import os
import unittest
from unittest import mock

os.environ.setdefault("FACTORY_TEST_MODE", "1")

import app as app_module  # noqa: E402
import database  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


class ColoringPreviewRecoversFromStorageTests(unittest.TestCase):
    def setUp(self):
        import tempfile

        self._tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self._tmp.close()
        self._old_db = database.DB_PATH
        database.DB_PATH = self._tmp.name
        database.init_db()
        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()
        self.pkg = "coloring_preview_probe"
        row = database.create_project(
            "Sea Creatures Colouring Book", "product",
            {"product_type": "coloring_book", "package_id": self.pkg},
        )
        self.pid = row["id"]

    def tearDown(self):
        database.DB_PATH = self._old_db
        for suffix in ("", "-wal", "-shm"):
            try:
                os.unlink(self._tmp.name + suffix)
            except OSError:
                pass

    def _get(self, filename="img_cover.png"):
        return self.client.get(f"/projects/{self.pid}/coloring-preview/{filename}")

    def test_a_stored_asset_is_served_when_the_file_is_not_on_this_disk(self):
        with mock.patch.object(app_module, "_verified_export_asset", return_value=PNG):
            r = self._get()
        self.assertEqual(r.status_code, 200, repr(r.get_data()[:120]))
        self.assertEqual(r.get_data(), PNG)

    def test_nothing_stored_still_gives_the_plain_missing_message(self):
        with mock.patch.object(app_module, "_verified_export_asset", return_value=None):
            r = self._get()
        self.assertEqual(r.status_code, 404)
        self.assertNotIn("Traceback", r.get_data(as_text=True))

    def test_the_path_guard_still_refuses_a_filename_it_does_not_know(self):
        r = self._get("../../etc/passwd")
        self.assertIn(r.status_code, (400, 404))


if __name__ == "__main__":
    unittest.main()
