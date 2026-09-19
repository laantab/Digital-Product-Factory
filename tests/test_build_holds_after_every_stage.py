"""The build can stop after ANY stage and wait — v1.8.1.

WHY THIS IS NOT A DETAIL
------------------------
The builder's ordinary job is to drive a book all the way to a finished
PDF. That is what the one-click button wants. A customer on the step-by-step
screen wants the opposite: do this one step, then stop and let me look at
it, and I will decide whether to pay for the next one.

Before v1.8.1 `paused_after` understood only "manuscript", and nothing ever
set it or cleared it — so a hold would have been permanent if one had ever
been placed. Handing a step-by-step click to a builder that does not
understand holds would run the whole book behind the customer's back and
spend a budget they authorised one step at a time.

Zero cost: no stage runner is ever invoked. The hold is tested through
`advance_build`, with every runner replaced by one that raises.
"""
from __future__ import annotations

import unittest
from unittest import mock

import database
from services import ebook_build_orchestrator as orch


def _project(title="Holds after every stage"):
    p = database.create_project(title, "ebook", {"title": title})
    return int(p["id"] if isinstance(p, dict) else p)


class HoldAfterAnyStageTests(unittest.TestCase):

    def test_a_hold_can_be_placed_after_every_stage(self):
        for stage in orch.STAGES:
            with self.subTest(stage=stage):
                data = orch.pause_after({}, stage)
                self.assertEqual(data["ebook_build"]["paused_after"], stage)

    def test_an_unknown_stage_is_refused(self):
        """A typo must not become a hold that never releases."""
        with self.assertRaises(ValueError):
            orch.pause_after({}, "manuscrpit")

    def test_a_hold_only_takes_effect_once_the_stage_is_done(self):
        """Otherwise the screen would say 'waiting for you' while it works."""
        data = orch.pause_after({}, "visuals")
        self.assertEqual(orch.held_after(data), "",
                         "a hold took effect before its stage finished")
        with mock.patch("services.ebook_project_workspace.is_approved",
                        side_effect=lambda ws, s: s == "visuals"):
            self.assertEqual(orch.held_after(data), "visuals")

    def test_every_stage_has_plain_language_for_the_customer(self):
        for stage in orch.STAGES:
            with self.subTest(stage=stage):
                message = orch.STAGE_READY_MESSAGES.get(stage, "")
                self.assertTrue(message, f"{stage} has no message")
                # A finished sentence, not a status code. The customer reads
                # this while the build waits for them.
                self.assertTrue(message[0].isupper() and message.endswith("."),
                                f"{stage}: {message!r} is not a sentence")
                for jargon in ("stage", "_", "status", "PASS", "FAIL", "None"):
                    self.assertNotIn(jargon, message,
                                     f"{stage} shows internal wording: {message!r}")

    def test_clearing_the_hold_releases_the_build(self):
        data = orch.pause_after({}, "cover")
        data = orch.clear_pause(data)
        self.assertEqual(data["ebook_build"]["paused_after"], "")
        self.assertEqual(orch.held_after(data), "")

    def test_a_held_build_runs_nothing(self):
        """The whole point: a hold stops work, it does not merely report it."""
        pid = _project()
        data = orch.pause_after({"title": "held"}, "visuals")
        database.update_project(pid, None, data)

        exploding = {s: mock.Mock(side_effect=AssertionError(f"{s} ran while held"))
                     for s in orch.STAGES}
        with mock.patch.dict(orch.STAGE_RUNNERS, exploding), \
             mock.patch("services.ebook_project_workspace.is_approved",
                        side_effect=lambda ws, s: s == "visuals"), \
             mock.patch.object(orch, "next_incomplete_stage", return_value="cover"):
            payload = orch.advance_build(pid)

        self.assertEqual(payload.get("held_after"), "visuals")

    def test_a_released_build_is_free_to_run_again(self):
        pid = _project("released")
        data = orch.clear_pause(orch.pause_after({"title": "released"}, "visuals"))
        database.update_project(pid, None, data)
        ran = []
        with mock.patch.dict(orch.STAGE_RUNNERS,
                             {"cover": lambda d, p: ran.append("cover") or d}), \
             mock.patch.object(orch, "next_incomplete_stage", return_value="cover"), \
             mock.patch.object(orch, "stage_is_validated", return_value=True):
            orch.advance_build(pid)
        self.assertEqual(ran, ["cover"],
                         "a released build did not run the next stage")

    def test_the_manuscript_hold_keeps_its_own_message(self):
        """v1.7.x behaviour that customers already see must not change."""
        data = orch.pause_after({}, "manuscript")
        with mock.patch("services.ebook_project_workspace.is_approved",
                        return_value=True):
            state = orch.build_state(data)
            self.assertTrue(orch._held_after_manuscript(data, state))
        self.assertEqual(orch.STAGE_READY_MESSAGES["manuscript"],
                         orch.MSG_MANUSCRIPT_READY)


if __name__ == "__main__":
    unittest.main()
