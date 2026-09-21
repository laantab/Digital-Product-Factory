"""Continue must give an exhausted book a fresh set of attempts — v1.8.3.

THE DEFECT THIS CLOSES
----------------------
v1.8.2 made "Continue where you left off" hand the book to the builder.
The builder then refused it: the job had used all 60 attempts, and
`claim_for_project` turns away any job at MAX_ATTEMPTS.

Continue never cleared that counter, for two reasons:

1. The Continue click polls /advance, which handed off with
   reset_attempts=False.
2. Even /resume, which does ask for a reset, could not get one:
   `store.enqueue` returned a QUEUED job untouched before it ever looked at
   reset_attempts. An exhausted job sits QUEUED, so it stayed exhausted.

WHAT THESE TESTS PROVE
----------------------
- The customer's Continue click resets an exhausted job and a task starts.
- Polling (no Continue flag) never resets the counter: the 60-attempt
  ceiling still holds for everything automatic.
- A job a builder is working on right now (live lease) is never touched.
- /resume now actually clears an exhausted QUEUED job.
- The screen sends the Continue flag on the first request only.

ZERO COST. `_start_task` is replaced, so Render is never reached, and the
orchestrator is replaced so no stage ever runs.
"""
from __future__ import annotations

import os
import pathlib
import re
import unittest
from unittest import mock

import database
from app import app
from services.jobs import mode, store


def _workflow_env():
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


def _set_job(job_id, **fields):
    conn = database.get_conn()
    try:
        cols = ", ".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE jobs SET {cols} WHERE id=?",
                     (*fields.values(), int(job_id)))
        conn.commit()
    finally:
        conn.close()


class _Exploder:
    def __call__(self, *a, **k):
        raise AssertionError("the web process built in workflow mode")


class ContinueResetsExhaustedRetriesTests(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        store.init_jobs_table()
        try:
            store.ensure_trigger_columns()
        except Exception:  # noqa: BLE001
            pass
        self.pid = _make_project()
        job = store.enqueue(self.pid)
        self.job_id = job["id"]
        # The exact state found on the live site: QUEUED, all 60 used.
        _set_job(self.job_id, status=store.QUEUED,
                 attempts=store.MAX_ATTEMPTS, workflow_triggered_at="")
        self.started = []
        p = mock.patch("services.jobs.workflow_trigger._start_task",
                       side_effect=lambda task, pid: (self.started.append(pid)
                                                      or "run-v183"))
        self.addCleanup(p.stop)
        p.start()
        f = mock.patch("services.ebook_build_orchestrator.advance_build",
                       _Exploder())
        self.addCleanup(f.stop)
        f.start()

    def _job(self):
        return store.get_for_project(self.pid)

    def test_exhausted_job_is_refused_before_the_fix(self):
        """Pins the defect: this is the state the builder turned away."""
        self.assertIsNone(store.claim_for_project("builder-test", self.pid))

    def test_continue_click_resets_the_counter_and_builder_can_claim(self):
        with _workflow_env():
            resp = self.client.post("/ebook/build/%s/advance" % self.pid,
                                    json={"continue": True})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue((resp.get_json() or {}).get("handed_off"))
        self.assertEqual(int(self._job()["attempts"]), 0,
                         "Continue did not clear the 60 used attempts")
        self.assertEqual(len(self.started), 1, "no builder task was started")
        claimed = store.claim_for_project("builder-test", self.pid)
        self.assertIsNotNone(claimed, "the builder still refuses the book")

    def test_polling_never_resets_the_counter(self):
        with _workflow_env():
            for _ in range(3):
                self.client.post("/ebook/build/%s/advance" % self.pid, json={})
        self.assertEqual(int(self._job()["attempts"]), store.MAX_ATTEMPTS,
                         "automatic polling reset the retry ceiling")

    def test_live_lease_is_never_touched(self):
        _set_job(self.job_id, status=store.RUNNING, lease_owner="builder-1",
                 lease_expires_at="9999-12-31T00:00:00+00:00", attempts=5)
        job = store.enqueue(self.pid, reset_attempts=True)
        self.assertEqual(job["status"], store.RUNNING)
        now = self._job()
        self.assertEqual(int(now["attempts"]), 5)
        self.assertEqual(now["lease_owner"], "builder-1")

    def test_expired_lease_is_reset(self):
        _set_job(self.job_id, status=store.RUNNING, lease_owner="builder-1",
                 lease_expires_at="2000-01-01T00:00:00+00:00",
                 attempts=store.MAX_ATTEMPTS)
        store.enqueue(self.pid, reset_attempts=True)
        now = self._job()
        self.assertEqual(now["status"], store.QUEUED)
        self.assertEqual(int(now["attempts"]), 0)

    def test_resume_route_now_clears_an_exhausted_queued_job(self):
        with mock.patch("services.ebook_build_orchestrator.resume_build",
                        return_value={"ok": True}):
            with _workflow_env():
                resp = self.client.post("/ebook/build/%s/resume" % self.pid,
                                        json={})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(int(self._job()["attempts"]), 0)

    def test_plain_enqueue_keeps_the_ceiling(self):
        store.enqueue(self.pid)
        self.assertEqual(int(self._job()["attempts"]), store.MAX_ATTEMPTS)


class ScreenSendsContinueOnceTests(unittest.TestCase):

    def setUp(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        self.js = (root / "static" / "js" / "app.js").read_text(encoding="utf-8")

    def test_continue_button_passes_the_flag(self):
        self.assertIn("openEbookBuild(rid, { continued: true })", self.js)

    def test_flag_is_sent_on_the_first_request_only(self):
        loop = self.js.split("async function _ebookBuildLoop", 1)[1].split("\nasync function", 1)[0]
        self.assertIn("JSON.stringify({ continue: true })", loop)
        self.assertRegex(loop, r"continued = false;")


if __name__ == "__main__":
    unittest.main()
