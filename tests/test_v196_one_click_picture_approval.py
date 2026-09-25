"""Factory 1.9.6 -- the one-click build stops once for the pictures.

After the pictures are chosen the build waits on one sheet showing every
picture with its chapter and source. Nothing runs, no attempt is spent and no
builder task is started until the customer presses Approve All Visuals once.
Then the build continues by itself to the cover, the PDF and the ZIP.

Zero cost: every stage runner is mocked; no picture search, no paid call.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

os.environ["FACTORY_TEST_MODE"] = "1"

import database  # noqa: E402
from services import ebook_build_orchestrator as orch  # noqa: E402


def _project(title="Picture approval pause"):
    p = database.create_project(title, "ebook", {"title": title})
    return int(p["id"] if isinstance(p, dict) else p)


def _prepared(data):
    """Stand-in for prepare_visuals_local: pictures chosen, nothing approved."""
    data = dict(data)
    data["visual_plan"] = {"chapters": [{"chapter": "Soil", "aids": []}]}
    return data


class PictureApprovalPauseTests(unittest.TestCase):

    def test_01_the_visuals_stage_never_approves_on_its_own(self):
        approve = mock.Mock(side_effect=AssertionError("approved on the customer's behalf"))
        with mock.patch("services.ebook_design_workspace.prepare_visuals_local", side_effect=_prepared), \
             mock.patch("services.ebook_design_workspace.approve_visuals_local", approve):
            out = orch._run_visuals({"title": "t"}, 1)
        self.assertTrue(orch.build_state(out)["awaiting_picture_approval"])
        self.assertTrue(orch.awaiting_picture_approval(out))
        approve.assert_not_called()

    def test_02_first_visuals_run_ends_waiting_not_failing(self):
        pid = _project("waits after pictures")
        database.update_project(pid, None, {"title": "waits"})
        with mock.patch("services.ebook_design_workspace.prepare_visuals_local", side_effect=_prepared), \
             mock.patch.object(orch, "next_incomplete_stage", return_value="visuals"):
            payload = orch.advance_build(pid)
        self.assertTrue(payload["awaiting_picture_approval"])
        self.assertFalse(payload["failed"])
        self.assertFalse(payload["retrying"], "a wait for the customer is not a retry")
        rec = orch.build_state(database.get_project(pid)["data"])["stages"]["visuals"]
        self.assertEqual(rec["status"], orch.PENDING_CUSTOMER)
        self.assertEqual(int(rec["attempts"]), 0, "waiting must not spend attempts")

    def test_03_while_waiting_nothing_runs(self):
        pid = _project("waiting runs nothing")
        data = {"title": "w", "visual_plan": {"chapters": []}}
        orch.build_state(data)["awaiting_picture_approval"] = True
        database.update_project(pid, None, data)
        exploding = {s: mock.Mock(side_effect=AssertionError(f"{s} ran while waiting"))
                     for s in orch.STAGES}
        with mock.patch.dict(orch.STAGE_RUNNERS, exploding), \
             mock.patch.object(orch, "next_incomplete_stage", return_value="visuals"):
            for _ in range(5):  # the screen polling repeatedly
                payload = orch.advance_build(pid)
        self.assertTrue(payload["awaiting_picture_approval"])
        self.assertIsNotNone(payload["picture_review"])

    def test_04_after_approval_the_build_continues_by_itself(self):
        pid = _project("continues after approval")
        data = {"title": "c", "visual_plan": {"chapters": []}}
        orch.build_state(data)["awaiting_picture_approval"] = True
        database.update_project(pid, None, data)
        ran = []
        with mock.patch("services.ebook_project_workspace.is_approved",
                        side_effect=lambda ws, s: s == "visuals"), \
             mock.patch.dict(orch.STAGE_RUNNERS, {"cover": lambda d, p: ran.append("cover") or d}), \
             mock.patch.object(orch, "next_incomplete_stage", return_value="cover"), \
             mock.patch.object(orch, "stage_is_validated", return_value=True):
            payload = orch.advance_build(pid)
        self.assertEqual(ran, ["cover"])
        self.assertFalse(payload.get("awaiting_picture_approval"))

    def test_05_the_builder_stops_and_releases_the_job_while_waiting(self):
        from services.jobs import executor

        job = {"id": 7, "project_id": 42}
        with mock.patch("services.ebook_build_orchestrator.advance_build",
                        return_value={"awaiting_picture_approval": True, "percent": 50}) as adv, \
             mock.patch.object(executor.store, "release") as release, \
             mock.patch.object(executor.store, "finish") as finish:
            out = executor._drive(job, "owner", units=10)
        self.assertEqual(adv.call_count, 1, "the builder kept going while waiting")
        self.assertTrue(out["paused"])
        release.assert_called_once()
        finish.assert_not_called()

    def test_06_polling_in_workflow_mode_starts_no_builder_task_while_waiting(self):
        from app import app

        pid = _project("no task while waiting")
        data = {"title": "n", "visual_plan": {"chapters": []}}
        orch.build_state(data)["awaiting_picture_approval"] = True
        database.update_project(pid, None, data)
        client = app.test_client()
        with mock.patch("services.jobs.mode.is_workflow_mode", return_value=True), \
             mock.patch("app._ebook_workspace_project_or_404",
                        return_value=(database.get_project(pid), None)), \
             mock.patch.object(orch, "next_incomplete_stage", return_value="visuals"), \
             mock.patch("app._workflow_hand_off",
                        side_effect=AssertionError("builder task started while waiting")):
            res = client.post(f"/ebook/build/{pid}/advance", json={"continue": True})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["awaiting_picture_approval"])

    def test_07_approve_all_visuals_ends_the_wait_and_any_hold(self):
        from app import app

        pid = _project("approve ends wait")
        data = orch.pause_after({"title": "a", "visual_plan": {"chapters": []}}, "visuals")
        orch.build_state(data)["awaiting_picture_approval"] = True
        database.update_project(pid, None, data)
        client = app.test_client()
        with mock.patch("app._ebook_workspace_project_or_404",
                        return_value=(database.get_project(pid), None)), \
             mock.patch("app._require_content_mutation_allowed", return_value=None), \
             mock.patch("services.ebook_workspace_actions.visuals",
                        side_effect=lambda d, b: (d, "Visuals approved.")):
            res = client.post(f"/ebook-workspace/{pid}/visuals", json={"action": "approve"})
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True)[:300])
        state = orch.build_state(database.get_project(pid)["data"])
        self.assertFalse(state["awaiting_picture_approval"])
        self.assertEqual(state["paused_after"], "")


if __name__ == "__main__":
    unittest.main()
