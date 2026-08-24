"""Re-export must move the legacy download pointers to the new package.

Root cause (project 20090): /export-product persisted product_exports and
export_package_id for the fresh package but left pdf_path, _pdf_path,
pdf_sha256, and export_files pointing at the previous package. Row-level
download buttons that read the legacy fields then requested the stale file and
the download pipeline blocked it as a bytes-vs-authoritative mismatch — the
customer saw a failed download immediately after a successful export.
"""

import hashlib
import os
import unittest

import database
from services.ebook_package import EXPORTS_DIR


class ExportPointerSyncTests(unittest.TestCase):
    def test_reexport_updates_legacy_pdf_pointers(self):
        from app import app

        client = app.test_client()
        fields = {
            "worksheet_title": "Pointer Sync Math Smoke",
            "grade": "3",
            "math_topic": "Addition",
            "difficulty": "Easy",
            "problems": "4",
            "include_answer_key": "Yes",
            "include_challenge": "No",
            "output_format": "Single Worksheet",
            "audience": "Grade 3 students",
            "goal": "Practice addition",
        }
        prev = client.post(
            "/generate-product",
            json={"product_type": "math_worksheet", "fields": fields},
        )
        self.assertEqual(prev.status_code, 200, prev.data)
        preview = prev.get_json()
        save = client.post(
            "/projects",
            json={
                "name": "Pointer Sync Math Smoke",
                "type": "product",
                "user_saved": True,
                "system_test": True,
                "temporary": True,
                "data": {k: v for k, v in preview.items() if not str(k).startswith("_")},
            },
        )
        self.assertEqual(save.status_code, 201, save.data)
        pid = save.get_json()["id"]
        try:
            # Seed stale legacy pointers as if a previous package existed.
            project = database.get_project(pid)
            data = dict(project["data"])
            data["pdf_path"] = os.path.join(EXPORTS_DIR, "stale-package", "ebook.pdf")
            data["_pdf_path"] = data["pdf_path"]
            data["pdf_sha256"] = "0" * 64
            data["export_files"] = {"dir": os.path.join(EXPORTS_DIR, "stale-package")}
            database.update_project(pid, None, data)

            ex = client.post("/export-product", json={"project_id": pid})
            self.assertEqual(ex.status_code, 200, ex.data)
            new_pkg = (ex.get_json() or {}).get("package_id") or (
                ((ex.get_json() or {}).get("exports") or {}).get("meta") or {}
            ).get("package_id")
            self.assertTrue(new_pkg, "export must report its package id")

            refreshed = database.get_project(pid)["data"]
            new_pdf = os.path.join(EXPORTS_DIR, new_pkg, "ebook.pdf")
            if os.path.isfile(new_pdf):
                # Legacy pointers must all follow the new package.
                self.assertEqual(refreshed.get("pdf_path"), new_pdf)
                self.assertEqual(refreshed.get("_pdf_path"), new_pdf)
                with open(new_pdf, "rb") as fh:
                    expected_sha = hashlib.sha256(fh.read()).hexdigest()
                self.assertEqual(refreshed.get("pdf_sha256"), expected_sha)
                self.assertEqual(
                    refreshed.get("export_files", {}).get("dir"),
                    os.path.join(EXPORTS_DIR, new_pkg),
                )
                # And nothing may still reference the stale package.
                self.assertNotIn("stale-package", str(refreshed.get("export_files")))
        finally:
            client.delete(f"/projects/{pid}")


if __name__ == "__main__":
    unittest.main()
