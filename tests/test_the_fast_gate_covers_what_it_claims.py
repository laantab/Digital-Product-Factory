"""The fast gate must actually run what the registry says it protects.

Every LOCKED and PROTECTED function carries fast_gate: true, but the gate was a
list of file names typed into CLAUDE.md, and 17 protected test files across six
functions were never in it. A change could pass the Fast Stability Gate and
still have broken a guarantee the registry claims the gate covers.

The gate is now derived from the registry. This test is what stops it drifting
again: a protected file is either in the gate or named in EXCLUDED with a reason.
"""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))

import fast_gate  # noqa: E402


class TheFastGateCoversWhatItClaimsTests(unittest.TestCase):
    def test_every_protected_file_is_run_or_excluded_with_a_reason(self):
        registry = json.loads(
            (ROOT / "command_center" / "function_lock_registry.json").read_text(encoding="utf-8")
        )
        running = set(fast_gate.gate_files())
        gaps = []
        for name, entry in (registry.get("functions") or {}).items():
            if not entry.get("fast_gate"):
                continue
            for path in entry.get("protected_test_files") or []:
                path = str(path).replace("\\", "/")
                if not (ROOT / path).is_file():
                    continue          # a file the registry names but the tree does not have
                if path in running:
                    continue
                if fast_gate.EXCLUDED.get(path):
                    continue
                gaps.append(f"{name}: {path}")
        self.assertEqual(
            gaps, [],
            "the registry says the fast gate protects these, and it does not run them:\n  "
            + "\n  ".join(gaps),
        )

    def test_every_exclusion_gives_a_reason(self):
        for path, reason in fast_gate.EXCLUDED.items():
            with self.subTest(path=path):
                self.assertTrue(str(reason).strip(), f"{path} is excluded with no reason")
                self.assertGreater(len(str(reason)), 40, f"{path}'s reason says too little")

    def test_every_file_the_gate_would_run_exists(self):
        for path in fast_gate.gate_files():
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file(), path)

    def test_the_gate_is_not_quietly_empty(self):
        self.assertGreater(len(fast_gate.gate_files()), 25)


if __name__ == "__main__":
    unittest.main()
