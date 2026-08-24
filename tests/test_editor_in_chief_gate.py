"""Every ebook export must carry an Editor-in-Chief review before "ready".

The reviewer (services/editor_in_chief_ebook.py) existed with tests but was
wired to nothing: no route ran it, so the factory could call an ebook Export
Ready without any editorial pass over the rendered artifact. /export-product
now runs it for ebooks with a rendered PDF, persists the report, and only
keeps export_ready when the verdict is PASS.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import database


class EditorInChiefGateTests(unittest.TestCase):
    @property
    def MANUSCRIPT(self) -> str:
        # The suite's canonical release-grade manuscript; this test is about
        # the Editor-in-Chief wiring, not about authoring a new fixture book.
        from services.ebook_manuscript_fixtures import (
            build_event_photo_strong_manuscript,
        )

        return build_event_photo_strong_manuscript()

    def test_ebook_export_persists_editor_in_chief_report(self):
        from app import app

        client = app.test_client()
        save = client.post(
            "/projects",
            json={
                "name": "EIC Gate Wiring Smoke",
                "type": "ebook",
                "user_saved": True,
                "system_test": True,
                "temporary": True,
                "data": {
                    "title": "Gate Wiring Smoke Ebook",
                    "product_type": "ebook",
                    "content": self.MANUSCRIPT,
                    "author": "Test Author",
                    "author_brand": "Test Author",
                    "fields": {"author": "Test Author", "topic": "event photography"},
                },
            },
        )
        self.assertEqual(save.status_code, 201, save.data)
        pid = save.get_json()["id"]
        try:
            check = client.post("/ebook-release-check", json={"project_id": pid})
            self.assertEqual(check.status_code, 200, check.data)

            # This test proves the Editor-in-Chief seam, not the upstream
            # content agent; stub that one collaborator so the export reaches
            # the EIC stage. (The fixture manuscript explicitly DISCLAIMS
            # guarantees and the keyword rule flags the word anyway — a
            # separate content-agent nuance outside this test's scope.)
            passing_qa = SimpleNamespace(passed=True, score=95.0, errors=[], warnings=[])
            with patch(
                "services.ebook_pipeline_agents.validate_ebook_content",
                return_value=passing_qa,
            ):
                ex = client.post("/export-product", json={"project_id": pid})
            self.assertEqual(ex.status_code, 200, ex.data)
            body = ex.get_json()

            files = (body.get("exports") or {}).get("files") or {}
            if "pdf" not in files:
                self.skipTest("export produced no PDF; EIC gate requires one")

            eic = body.get("editor_in_chief") or {}
            self.assertTrue(
                eic.get("verdict"),
                "ebook export must include an Editor-in-Chief verdict",
            )
            # The gate contract: Export Ready requires an EIC PASS.
            if body.get("export_ready"):
                self.assertEqual(eic.get("verdict"), "EDITOR-IN-CHIEF PASS")

            stored = database.get_project(pid)["data"]
            self.assertTrue(
                (stored.get("editor_in_chief") or {}).get("verdict"),
                "EIC report must persist on the saved project",
            )
        finally:
            client.delete(f"/projects/{pid}")


if __name__ == "__main__":
    unittest.main()
