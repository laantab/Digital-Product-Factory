"""The runbook has to stay true, or it is worse than having none.

A recovery document that names a script that does not exist, or an environment
variable the code does not read, sends somebody down a dead end at the worst
possible moment. This checks the parts a change could quietly break.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "BACKUP_AND_RECOVERY.md"


class TheBackupRunbookMatchesTheCodeTests(unittest.TestCase):
    def setUp(self):
        self.text = DOC.read_text(encoding="utf-8")

    def test_the_runbook_exists_and_says_something(self):
        self.assertGreater(len(self.text), 2000, "the runbook is a stub")

    def test_every_script_it_tells_you_to_run_exists(self):
        for match in re.findall(r"python (scripts/[\w_]+\.py)", self.text):
            with self.subTest(script=match):
                self.assertTrue((ROOT / match).is_file(), f"{match} does not exist")

    def test_every_environment_variable_it_names_is_read_by_the_code(self):
        source = "\n".join(
            (ROOT / name).read_text(encoding="utf-8", errors="ignore")
            for name in ("app.py", "database.py", ".env.example", "render.yaml")
        )
        for var in sorted(set(re.findall(r"\b(FACTORY_[A-Z0-9_]+|DATABASE_URL)\b", self.text))):
            with self.subTest(var=var):
                self.assertIn(var, source, f"the runbook names {var}, which nothing reads")

    def test_it_says_plainly_that_the_admin_backup_route_is_not_a_backup(self):
        self.assertIn("/admin/backup-db", self.text)
        self.assertIn("not a backup", self.text.lower())

    def test_it_covers_the_three_things_there_are_to_lose(self):
        lowered = self.text.lower()
        for topic in ("postgres", "r2", "github"):
            with self.subTest(topic=topic):
                self.assertIn(topic, lowered)

    def test_it_tells_you_to_rehearse_a_restore(self):
        self.assertIn("rehearsal", self.text.lower())


if __name__ == "__main__":
    unittest.main()
