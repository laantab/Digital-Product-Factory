"""The release manager must not be able to do the dangerous things.

It is a file Lonnie double-clicks and walks away from, so what it CANNOT do
matters more than what it can. This reads the batch file and checks the
promises in its own header are true of its body.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAT = ROOT / "tools" / "Factory Release Manager.bat"


class TheReleaseManagerIsSafeTests(unittest.TestCase):
    def setUp(self):
        self.text = BAT.read_text(encoding="utf-8", errors="ignore")
        self.lowered = self.text.lower()
        # What the file DOES, with its comments and the words it prints into
        # the report removed -- a promise in a comment must not satisfy a test
        # about behaviour.
        commands = []
        for line in self.text.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("rem"):
                continue
            stripped = re.sub(r'>>?\s*"[^"]*"\s*echo.*$', "", stripped)
            stripped = re.sub(r'^echo.*$', "", stripped)
            commands.append(stripped)
        self.commands = "\n".join(commands).lower()

    def test_the_file_exists(self):
        self.assertTrue(BAT.is_file())

    def test_it_never_merges(self):
        for forbidden in ("git merge", "gh pr merge", "--squash", "--rebase"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.commands)

    def test_it_never_touches_env_secrets_or_billing(self):
        for forbidden in (".env", "api_key", "secret_key", "render.com/v1", "billing"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.commands,
                                 f"a command in the file mentions {forbidden}")

    def test_it_never_force_pushes_or_deletes_a_branch(self):
        for forbidden in ("push --force", "push -f", "--delete", "branch -d", "push origin :"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, self.commands)

    def test_it_pushes_only_the_one_named_branch(self):
        pushes = re.findall(r"git push[^\r\n]*", self.text)
        self.assertTrue(pushes, "it never pushes at all")
        for line in pushes:
            with self.subTest(line=line):
                self.assertIn("%BRANCH%:refs/heads/%BRANCH%", line)

    def test_the_push_comes_after_the_gate_and_the_gate_can_stop_it(self):
        gate = self.text.index("MERGE GATE: PASS")
        push = self.text.index("git push origin")
        self.assertLess(gate, push, "the push is not behind the gate check")
        self.assertIn("goto :leave", self.text[gate:push],
                      "a failed gate has no path that stops before the push")

    def test_it_refuses_to_run_on_the_branch_you_have_open(self):
        self.assertIn("git branch --show-current", self.text)
        self.assertIn("this file only runs when it is not", self.text)

    def test_it_stops_when_git_is_busy(self):
        for marker in ("index.lock", "MERGE_HEAD", "rebase-merge"):
            with self.subTest(marker=marker):
                self.assertIn(marker, self.text)

    def test_it_checks_it_is_in_the_right_repository(self):
        self.assertIn("git remote get-url origin", self.text)
        self.assertIn("EXPECTED_REPO", self.text)

    def test_it_tests_in_a_temporary_copy_not_the_working_folder(self):
        self.assertIn("git worktree add --detach", self.text)

    def test_it_writes_a_report_and_opens_it(self):
        self.assertIn("REPORT=", self.text)
        self.assertIn("notepad.exe", self.lowered)

    def test_it_says_plainly_that_merging_is_left_to_a_person(self):
        self.assertIn("click the green Merge button", self.text)

    def test_the_gate_script_it_runs_exists(self):
        for match in re.findall(r"scripts\\(\w+\.py)", self.text):
            with self.subTest(script=match):
                self.assertTrue((ROOT / "scripts" / match).is_file(), match)


if __name__ == "__main__":
    unittest.main()
