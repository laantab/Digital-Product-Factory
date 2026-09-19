"""The website builds nothing in workflow mode — v1.8.1.

WHAT THIS PROVES
----------------
For every step-by-step route that v1.8.1 hands to the builder: with
`FACTORY_EXECUTION_MODE=workflow`, the route runs NO stage in the web
process, hands the work off exactly once, and answers with a read-only
status payload rather than an error.

The engine functions are replaced with ones that raise if they are called
at all, so "nothing ran" is proved by the absence of an explosion, not by
reading a flag the code under test sets itself.

WHY THE ANSWER MUST BE STATUS AND NOT AN ERROR
----------------------------------------------
A customer whose browser is running last week's JavaScript, or who left a
tab open across the deploy, must not be shown a broken screen because the
server changed which machine does the work. `/advance` has answered this
way since v1.8.0; every heavy route now does the same.

ZERO COST. No provider is reachable: every function that could spend money
is replaced before the request is made, and the Render SDK is never
imported because the trigger is replaced too.
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
            f"This is the defect v1.8.1 exists to close.")


#: Every engine entry point a step-by-step route could reach. If v1.8.1 is
#: correct, none of these is reachable from a request in workflow mode.
_FORBIDDEN = [
    ("services.ebook_project_workspace", "execute_generate_manuscript"),
    ("services.ebook_project_workspace", "execute_correct_manuscript"),
    ("services.ebook_project_workspace", "execute_run_research"),
    ("services.ebook_project_workspace", "execute_generate_title_options"),
    ("services.ebook_project_workspace", "execute_generate_outline_options"),
    ("services.ebook_design_workspace", "prepare_visuals_local"),
    ("services.ebook_design_workspace", "build_preview"),
    ("services.ebook_design_workspace", "run_preflight_stage"),
    ("services.ebook_design_workspace", "select_and_stage_theme"),
    ("services.ebook_design_workspace", "stage_photo_cover"),
    ("services.ebook_build_orchestrator", "advance_build"),
]


class NothingHeavyRunsInTheWebsiteTests(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        self.pid = _make_project()
        store.init_jobs_table()
        # The trigger is recorded, never sent. Nothing imports the Render SDK.
        self.started = []
        patcher = mock.patch(
            "services.jobs.workflow_trigger._start_task",
            side_effect=lambda task, pid: (self.started.append((task, pid))
                                           or "run-abc123"))
        self.addCleanup(patcher.stop)
        patcher.start()

    def _forbid_everything(self):
        for module, name in _FORBIDDEN:
            p = mock.patch(f"{module}.{name}", _Exploder(f"{module}.{name}"))
            self.addCleanup(p.stop)
            p.start()

    # -- the routes, and the body each one needs to get past validation ----
    def _requests(self):
        return [
            ("/ebook-workspace/%s/visuals" % self.pid, {"action": "prepare"}),
            ("/ebook-workspace/%s/cover" % self.pid,
             {"action": "pexels-search", "query": "tomatoes"}),
            ("/ebook-workspace/%s/design" % self.pid, {"theme_id": "serif-classic"}),
            ("/ebook-workspace/%s/preview" % self.pid, {}),
            ("/ebook-workspace/%s/preflight" % self.pid, {}),
        ]

    def test_no_stage_runs_and_the_answer_is_status(self):
        self._forbid_everything()
        with _workflow_env():
            for path, body in self._requests():
                with self.subTest(route=path):
                    resp = self.client.post(path, json=body)
                    self.assertEqual(
                        resp.status_code, 200,
                        f"{path} answered {resp.status_code}; a heavy route "
                        f"must answer with status, never an error")
                    payload = resp.get_json() or {}
                    self.assertTrue(payload.get("handed_off"),
                                    f"{path} did not hand the work off")
                    self.assertFalse(payload.get("advanced"),
                                     f"{path} claims it advanced the build")
                    self.assertEqual(payload.get("execution_mode"), "workflow")

    def test_the_work_is_recorded_on_the_job_row_before_render_is_asked(self):
        """Render being down must cost a delay, never a book."""
        self._forbid_everything()
        with _workflow_env():
            resp = self.client.post("/ebook-workspace/%s/design" % self.pid,
                                    json={"theme_id": "serif-classic"})
        self.assertEqual(resp.status_code, 200)
        job = store.get_for_project(self.pid)
        self.assertIsNotNone(job, "no durable job row was written")
        self.assertIn(job["status"], (store.QUEUED, store.RUNNING))

    def test_a_trigger_failure_still_answers_the_customer(self):
        self._forbid_everything()
        with mock.patch("services.jobs.workflow_trigger._start_task",
                        side_effect=RuntimeError("Render is down")):
            with _workflow_env():
                resp = self.client.post("/ebook-workspace/%s/preview" % self.pid,
                                        json={})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue((resp.get_json() or {}).get("handed_off"))

    def test_five_clicks_start_one_task(self):
        """Five instances racing one book is five bills and one broken book."""
        self._forbid_everything()
        with _workflow_env():
            for _ in range(5):
                self.client.post("/ebook-workspace/%s/preview" % self.pid, json={})
        self.assertEqual(
            len(self.started), 1,
            f"{len(self.started)} tasks were started for one book; the "
            f"duplicate guard in the job row did not hold")

    def test_the_builder_is_told_which_stage_to_stop_after(self):
        """Otherwise it would build the whole book behind the customer."""
        self._forbid_everything()
        with _workflow_env():
            self.client.post("/ebook-workspace/%s/preview" % self.pid, json={})
        project = database.get_project(self.pid)
        state = (project.get("data") or {}).get("ebook_build") or {}
        self.assertEqual(state.get("paused_after"), "preview")

    def test_light_actions_still_run_in_the_web_process(self):
        """Approving a photograph must not start a cloud instance."""
        with _workflow_env():
            with mock.patch("services.ebook_design_workspace.approve_visuals_local",
                            side_effect=lambda d: d) as approve:
                resp = self.client.post(
                    "/ebook-workspace/%s/visuals" % self.pid,
                    json={"action": "approve"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(approve.called,
                        "an instant, free action was sent to the builder")
        self.assertFalse((resp.get_json() or {}).get("handed_off"))


class InlineModeIsUnchangedTests(unittest.TestCase):
    """With the variable unset, every route behaves exactly as before."""

    def setUp(self):
        self.client = app.test_client()
        self.pid = _make_project("Inline stays inline")

    def test_inline_mode_runs_the_work_in_the_web_process(self):
        self.assertTrue(mode.is_inline_mode())
        with mock.patch("services.ebook_design_workspace.select_and_stage_theme",
                        side_effect=lambda d, t: d) as staged:
            resp = self.client.post("/ebook-workspace/%s/design" % self.pid,
                                    json={"theme_id": "serif-classic"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(staged.called,
                        "inline mode must still do the work itself")
        self.assertNotIn("handed_off", resp.get_json() or {})

    def test_inline_mode_never_sets_a_hold(self):
        with mock.patch("services.ebook_design_workspace.select_and_stage_theme",
                        side_effect=lambda d, t: d):
            self.client.post("/ebook-workspace/%s/design" % self.pid,
                             json={"theme_id": "serif-classic"})
        project = database.get_project(self.pid)
        state = (project.get("data") or {}).get("ebook_build") or {}
        self.assertFalse(state.get("paused_after"))


if __name__ == "__main__":
    unittest.main()
