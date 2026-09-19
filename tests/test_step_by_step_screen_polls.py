"""The step-by-step screen starts, polls and re-renders — v1.8.1.

The screen used to wait for one long request per button. In workflow mode a
heavy step no longer finishes inside its request, so a button that keeps
waiting for the answer would either hang or tell the customer their upload
failed when it had simply not finished yet.

These are source contract tests over static/js/app.js. They cannot run a
browser, so they check the things whose absence would break the screen
silently: that the handed-off branch exists at the one choke point every
button goes through, that the confirm flows share ONE copy of it (CLAUDE.md:
"the same logic is sometimes implemented twice -- grep for the second copy"),
and that the upload path no longer reports a false failure.

Zero cost: the file is read, never executed.
"""
from __future__ import annotations

import os
import re
import unittest

APP_JS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "static", "js", "app.js")


class StepByStepScreenContractTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(APP_JS, encoding="utf-8") as handle:
            cls.src = handle.read()

    def test_the_shared_action_helper_handles_a_handed_off_step(self):
        """Every step-by-step button goes through this one function."""
        start = self.src.index("async function postEbookWorkspaceAction(")
        body = self.src[start:start + 2000]
        self.assertIn("handed_off", body,
                      "postEbookWorkspaceAction does not notice a handed-off "
                      "step, so every button would wait for work that is no "
                      "longer done in the request")
        self.assertIn("_wsPollUntilStepLands", body)

    def test_the_screen_polls_the_read_only_status_route(self):
        self.assertIn("/status`", self.src)
        start = self.src.index("async function _wsPollUntilStepLands(")
        body = self.src[start:start + 2500]
        self.assertIn("held_after", body,
                      "the poller does not recognise the builder's hold, so a "
                      "finished step would never land on the screen")
        self.assertIn("status.finished", body)
        self.assertIn("status.failed", body)

    def test_the_customer_is_told_they_can_leave_the_page(self):
        """The same promise the one-click build already makes."""
        self.assertIn("You can leave this page", self.src)

    def test_there_is_exactly_one_copy_of_the_handed_off_handling(self):
        """A second copy is a second thing to forget. That is the v1.8.0 gap."""
        self.assertEqual(
            self.src.count("async function _wsHandedOff("), 1)
        self.assertEqual(
            self.src.count("async function _wsPollUntilStepLands("), 1)

    def test_the_upload_no_longer_reports_a_false_failure(self):
        """In workflow mode there is no registered photograph yet."""
        start = self.src.index("/cover-image`")
        body = self.src[start:start + 1600]
        handed = body.index("handed_off")
        sha = body.index("src.sha256")
        self.assertLess(handed, sha,
                        "the sha256 check runs before the handed-off branch, "
                        "so a successful upload would be reported as failed")

    def test_a_poll_is_cancelled_when_the_customer_moves_on(self):
        """Two steps must never both be re-rendering the screen."""
        self.assertIn("_wsPollRun", self.src)
        start = self.src.index("async function _wsPollUntilStepLands(")
        body = self.src[start:start + 2500]
        self.assertIn("runToken !== _wsPollRun", body)

    def test_the_poll_gives_up_rather_than_spinning_for_ever(self):
        self.assertIn("WS_POLL_TIMEOUT_MS", self.src)
        match = re.search(r"const WS_POLL_MS = (\d+)", self.src)
        self.assertIsNotNone(match, "the poll interval is not stated")
        self.assertGreaterEqual(
            int(match.group(1)), 500,
            "polling faster than twice a second turns a progress check into "
            "load on the service this release exists to protect")


if __name__ == "__main__":
    unittest.main()
