"""Continue must actually ask somebody to build the book — v1.8.2.

THE DEFECT THIS CLOSES
----------------------
v1.8.0 stopped `/ebook/build/<id>/advance` building in the web process,
which was right: it was the last way a browser could push the web service
past its memory limit. But it stopped there. It answered 200 with an
ordinary status payload and asked NOBODY to do the work.

That was invisible until it mattered. "Continue where you left off" calls
`openEbookBuild`, which polls this route; it never calls `/resume`, which
is where the hand-off lived. So a resumed book in workflow mode reached
only this route: the job sat QUEUED for ever, the builder ran zero tasks,
the screen showed a spinner, and no log line, status flag or HTTP code
anywhere said anything was wrong. A silent refusal is worse than a 500 —
a 500 gets looked at.

WHAT THESE TESTS PROVE
----------------------
1. Workflow mode: /advance hands the work off and a task is started.
2. The polling loop cannot start a second task for the same book.
3. Inline mode still builds in the web process, exactly as v1.7.29 did,
   and never asks Render for anything.

(3) is the one that matters most. The patch must not reopen the memory
failure v1.8.0 exists to close.

ZERO COST. `_start_task` is replaced before any request is made, so the
Render SDK is never imported and no provider is ever reached. In the
inline test the orchestrator is replaced too, so no stage ever runs.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

import database
from app import app
from services.jobs import mode, store


def _workflow_env():
    """Workflow mode, fully configured, with no real Render behind it."""
    return mock.patch.dict(os.environ, {
        mode.ENV_MODE: "workflow",
        mode.ENV_TASK: "test-builder/build_ebook",
        mode.ENV_API_KEY: "not-a-real-key",
    })


def _make_project(title="Container Gardening for Beginners"):
    project = database.create_project(
        title, "ebook",
        {"title": title, "artifact_id": "art-1", "artifact_revision": 1,
         "artifact_state": "DRAFT"})
    return int(project["id"] if isinstance(project, dict) else project)


class _Exploder:
    """Any call is a failure: this work must not happen in the web process."""

    def __init__(self, name):
        self.name = name

    def __call__(self, *a, **k):
        raise AssertionError(
            f"{self.name} ran inside the web process in workflow mode. "
            f"This is the defect v1.8.0 exists to close.")


class AdvanceHandsOffTests(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        self.pid = _make_project()
        store.init_jobs_table()
        self.started = []
        patcher = mock.patch(
            "services.jobs.workflow_trigger._start_task",
            side_effect=lambda task, pid: (self.started.append((task, pid))
                                           or "run-abc123"))
        self.addCleanup(patcher.stop)
        patcher.start()
        # The web process must not build. If it tries, the test fails loudly.
        forbid = mock.patch("services.ebook_build_orchestrator.advance_build",
                            _Exploder("advance_build"))
        self.addCleanup(forbid.stop)
        forbid.start()

    def _advance(self):
        return self.client.post("/ebook/build/%s/advance" % self.pid, json={})

    def test_advance_asks_the_builder_to_run(self):
        """The whole defect in one assertion: somebody must be asked."""
        with _workflow_env():
            resp = self._advance()
        self.assertEqual(resp.status_code, 200,
                         "a resumed build must get a screen, never an error")
        payload = resp.get_json() or {}
        self.assertTrue(payload.get("handed_off"),
                        "/advance answered 200 without handing the work off — "
                        "this is the silent refusal v1.8.2 fixes")
        self.assertFalse(payload.get("advanced"),
                         "/advance claims the web process advanced the build")
        self.assertEqual(payload.get("execution_mode"), "workflow")
        self.assertEqual(
            len(self.started), 1,
            "no Render task was started, so the book would sit queued for ever")

    def test_the_job_is_recorded_even_if_render_is_down(self):
        """Render being unreachable must cost a delay, never a book."""
        with mock.patch("services.jobs.workflow_trigger._start_task",
                        side_effect=RuntimeError("Render is down")):
            with _workflow_env():
                resp = self._advance()
        self.assertEqual(resp.status_code, 200)
        self.assertTrue((resp.get_json() or {}).get("handed_off"))
        job = store.get_for_project(self.pid)
        self.assertIsNotNone(job, "no durable job row was written")
        self.assertIn(job["status"], (store.QUEUED, store.RUNNING))

    def test_the_polling_loop_starts_exactly_one_task(self):
        """The screen polls /advance in a loop. Twenty polls is one book.

        Twenty instances racing each other onto the same chapter would be
        twenty bills and one corrupted book.
        """
        with _workflow_env():
            for _ in range(20):
                self._advance()
        self.assertEqual(
            len(self.started), 1,
            f"{len(self.started)} tasks were started for one book; the "
            f"duplicate guard in the job row did not hold")

    def _exhaust_manuscript(self):
        from services.ebook_project_workspace import upsert_acceptance_project
        from services.ebook_build_orchestrator import build_state, FAILED_FINAL

        project = upsert_acceptance_project(database, preserve_live_manuscript=False)
        self.pid = int(project["id"])
        data = dict(project["data"])
        state = build_state(data)
        state["failed"] = True
        state["current_stage"] = "manuscript"
        state["stages"]["manuscript"] = {
            "status": FAILED_FINAL, "attempts": 60,
            "running_since": 0, "error": "provider timed out"}
        database.update_project(self.pid, None, data)
        return data

    def test_continue_resets_the_failed_stage_as_well_as_the_job(self):
        before = self._exhaust_manuscript()
        job = store.enqueue(self.pid)
        owner = "failed-worker"
        store.claim_for_project(owner, self.pid)
        store.finish(job["id"], owner, status=store.FAILED)

        with _workflow_env():
            resp = self.client.post("/ebook/build/%s/advance" % self.pid,
                                    json={"continue": True})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.get_json()["failed"],
                         "Continue must reset the manuscript, not only its job")
        after = database.get_project(self.pid)["data"]
        stage = after["ebook_build"]["stages"]["manuscript"]
        self.assertEqual(stage["attempts"], 0)
        self.assertEqual(after["ebook_build"]["resume_generation"], 1)
        self.assertEqual(after["ebook_workspace"], before["ebook_workspace"])
        self.assertEqual(len(self.started), 1)

    def test_polling_does_not_reset_a_failed_stage(self):
        self._exhaust_manuscript()
        with _workflow_env():
            resp = self._advance()
        self.assertTrue(resp.get_json()["failed"])
        after = database.get_project(self.pid)["data"]["ebook_build"]
        self.assertEqual(after["stages"]["manuscript"]["attempts"], 60)
        self.assertNotIn("resume_generation", after)

    def test_continue_does_not_reset_a_stage_owned_by_a_live_worker(self):
        before = self._exhaust_manuscript()
        store.enqueue(self.pid)
        claimed = store.claim_for_project("active-worker", self.pid)
        with _workflow_env():
            resp = self.client.post("/ebook/build/%s/advance" % self.pid,
                                    json={"continue": True})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(database.get_project(self.pid)["data"], before)
        self.assertEqual(store.get_for_project(self.pid)["lease_owner"],
                         claimed["lease_owner"])
        self.assertEqual(self.started, [])

    def test_an_unknown_project_is_still_refused(self):
        """The 404 guard must survive the patch."""
        with _workflow_env():
            resp = self.client.post("/ebook/build/99999999/advance", json={})
        self.assertNotEqual(resp.status_code, 200)
        self.assertEqual(self.started, [],
                         "a task was started for a project that does not exist")


class InlineModeIsUnchangedTests(unittest.TestCase):
    """With the variable unset, /advance behaves exactly as v1.7.29 did.

    This is the regression that would hurt most: if the patch leaked the
    hand-off into inline mode, local Windows development and the rollback
    path would both stop building books.
    """

    def setUp(self):
        self.client = app.test_client()
        self.pid = _make_project("Inline stays inline")
        self.started = []
        patcher = mock.patch(
            "services.jobs.workflow_trigger._start_task",
            side_effect=lambda task, pid: (self.started.append((task, pid))
                                           or "run-abc123"))
        self.addCleanup(patcher.stop)
        patcher.start()

    def test_inline_mode_advances_in_the_web_process(self):
        self.assertTrue(mode.is_inline_mode())
        with mock.patch("services.ebook_build_orchestrator.advance_build",
                        side_effect=lambda pid: {"ok": True, "advanced": True}
                        ) as advanced:
            resp = self.client.post("/ebook/build/%s/advance" % self.pid, json={})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(advanced.called,
                        "inline mode must still build in the web process")
        self.assertTrue((resp.get_json() or {}).get("advanced"))

    def test_inline_mode_never_asks_render_for_anything(self):
        with mock.patch("services.ebook_build_orchestrator.advance_build",
                        side_effect=lambda pid: {"ok": True, "advanced": True}):
            self.client.post("/ebook/build/%s/advance" % self.pid, json={})
        self.assertEqual(self.started, [],
                         "inline mode started a Render task; the rollback "
                         "path must never depend on Render being reachable")

    def test_inline_mode_does_not_claim_a_hand_off(self):
        with mock.patch("services.ebook_build_orchestrator.advance_build",
                        side_effect=lambda pid: {"ok": True, "advanced": True}):
            resp = self.client.post("/ebook/build/%s/advance" % self.pid, json={})
        self.assertNotIn("handed_off", resp.get_json() or {})


if __name__ == "__main__":
    unittest.main()
