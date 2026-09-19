"""The builder does what the customer asked for — v1.8.1.

The website records the customer's choice on the durable job row; a Render
Workflow task reads it and performs it on its own instance. These tests
prove the round trip for every image action the step-by-step screen offers,
using fake providers so nothing is downloaded, generated or paid for.

WHY "TAKE, NOT READ" MATTERS
----------------------------
Render retries a run it believes failed, including one that actually
finished. If the action were merely read, a retry would replace the
customer's photograph a second time: a second paid image, and a picture
they did not choose. The action is taken and cleared in one conditional
UPDATE, so it happens at most once.
"""
from __future__ import annotations

import unittest
from unittest import mock

import database
from services import ebook_workspace_actions as wsa
from services.jobs import builder_actions, store

VISUALS = "/ebook-workspace/<int:project_id>/visuals"
COVER = "/ebook-workspace/<int:project_id>/cover"
COVER_IMAGE = "/ebook-workspace/<int:project_id>/cover-image"


def _project(title="Builder action round trip"):
    p = database.create_project(title, "ebook", {"title": title})
    return int(p["id"] if isinstance(p, dict) else p)


class RequestedActionRoundTripTests(unittest.TestCase):

    def setUp(self):
        store.init_jobs_table()
        self.pid = _project()
        self.job_id = int(store.enqueue(self.pid)["id"])

    def _record(self, route, action, payload=None):
        self.assertTrue(store.set_requested_action(
            self.job_id,
            {"route": route, "action": action, "payload": payload or {}}))

    def test_an_action_is_performed_at_most_once(self):
        self._record(VISUALS, "replace-photo", {"visual_id": "v1"})
        seen = []
        with mock.patch("services.ebook_visual_pipeline.replace_photo_aid",
                        side_effect=lambda d, vid, **k: seen.append(vid) or d):
            first = builder_actions.perform_pending(self.pid, self.job_id)
            second = builder_actions.perform_pending(self.pid, self.job_id)
        self.assertTrue(first["performed"])
        self.assertFalse(second["performed"],
                         "a retried run performed the action a second time")
        self.assertEqual(seen, ["v1"])

    def test_a_newer_request_supersedes_an_unrun_one(self):
        """Clicking 'AI alternative' then 'replace photo' means the second."""
        self._record(VISUALS, "generate-ai", {"visual_id": "v1"})
        self._record(VISUALS, "replace-photo", {"visual_id": "v2"})
        taken = store.take_requested_action(self.job_id)
        self.assertEqual(taken["action"], "replace-photo")
        self.assertEqual(taken["payload"]["visual_id"], "v2")

    def test_each_image_action_reaches_its_own_engine_function(self):
        cases = [
            (VISUALS, "prepare", "services.ebook_design_workspace.prepare_visuals_local"),
            (VISUALS, "replace-photo", "services.ebook_visual_pipeline.replace_photo_aid"),
            (VISUALS, "ai-alternative", "services.ebook_visual_pipeline.replace_photo_aid"),
            (VISUALS, "retry-automatic", "services.ebook_design_workspace.prepare_visuals_local"),
            (VISUALS, "accept-photo", "services.ebook_visual_pipeline.accept_photo_aid"),
        ]
        for route, action, target in cases:
            with self.subTest(action=action):
                pid = _project(f"case {action}")
                job_id = int(store.enqueue(pid)["id"])
                store.set_requested_action(job_id, {
                    "route": route, "action": action,
                    "payload": {"action": action, "visual_id": "v1"}})
                with mock.patch(target, side_effect=lambda d, *a, **k: d) as fn:
                    out = builder_actions.perform_pending(pid, job_id)
                self.assertTrue(out["performed"], out)
                self.assertTrue(fn.called, f"{action} did not reach {target}")

    def test_a_failed_action_does_not_fail_the_book(self):
        """One unavailable photograph must not throw away a whole manuscript."""
        self._record(VISUALS, "replace-photo", {"visual_id": "v1"})
        with mock.patch("services.ebook_visual_pipeline.replace_photo_aid",
                        side_effect=RuntimeError("Pexels is down")):
            out = builder_actions.perform_pending(self.pid, self.job_id)
        self.assertFalse(out["performed"])
        self.assertEqual(out["error"], "RuntimeError")

    def test_stage_work_is_left_to_the_build_loop(self):
        """Writing a chapter has exactly one implementation, the orchestrator's."""
        self._record("/ebook-workspace/<int:project_id>/generate-manuscript",
                     "generate", {})
        out = builder_actions.perform_pending(self.pid, self.job_id)
        self.assertFalse(out["performed"])
        self.assertEqual(out["message"], "handled by the build loop")


class UploadedCoverTravelsThroughStorageTests(unittest.TestCase):
    """The website and the builder share no disk.

    The upload arrives at one machine and is used on another, so it has to go
    through the storage driver. A local path would be a file the builder
    cannot open, and the customer would watch for a cover that never comes.
    """

    def setUp(self):
        store.init_jobs_table()
        self.pid = _project("Uploaded cover")

    def test_the_builder_reads_the_upload_back_out_of_storage(self):
        from services.storage import get_storage

        raw = b"\\x89PNG\\r\\n\\x1a\\n" + b"pretend-image-bytes" * 8
        key = f"test/{self.pid}/cover_upload.png"
        get_storage().put(key, raw, content_type="image/png")

        seen = {}

        def _attach(data, blob, **kwargs):
            seen["bytes"] = blob
            seen["filename"] = kwargs.get("filename")
            return data

        with mock.patch("services.ebook_photo_cover.attach_upload", _attach), \
             mock.patch("services.ebook_design_workspace.stage_photo_cover",
                        side_effect=lambda d, **k: d):
            wsa.cover_image({}, {"storage_key": key, "filename": "mine.png"},
                            project_id=self.pid)

        self.assertEqual(seen["bytes"], raw,
                         "the builder did not get the customer's own bytes")
        self.assertEqual(seen["filename"], "mine.png")

    def test_an_upload_with_no_storage_key_is_refused_not_guessed(self):
        with self.assertRaises(wsa.UnknownAction):
            wsa.cover_image({}, {"filename": "mine.png"}, project_id=self.pid)


if __name__ == "__main__":
    unittest.main()
