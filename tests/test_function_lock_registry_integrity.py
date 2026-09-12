"""FUNCTION LOCK REGISTRY INTEGRITY (2026-09-12).

Why this exists
---------------
A read-only audit (see PROTECTED_GENERATOR_RULE.md and SESSION_HANDOFF_2026-09-11.md)
found that the Factory's prior "lock" discipline was mostly documentation: fifteen
`*_LOCKED_STATE.md` files, none re-verified by an automated test after the day they
were written, and one of Coloring Book's directly claimed the exact "no text when
captions = No" behavior that regressed and shipped to a live customer two months
later. A markdown file said "locked"; nothing machine-checked it.

`command_center/function_lock_registry.json` is the new, single source of truth for
each customer-facing function's protection status. This file is what stops a claim
in that registry from ever being accepted on its own word again: it fails if a
function marked LOCKED

  1. lists a protected test file that does not exist on disk,
  2. lists a protected test file that is not registered in
     tests/acceptance_manifest.json (so the Fast/Full Gates would silently never run it),
  3. has no protected customer-path test at all,
  4. claims a last_known_good_commit that does not actually exist in this repository's
     git history (never trust an unverifiable hash), or
  5. carries inconsistent unlock/relock metadata (e.g. LOCKED with an open unlock
     reason still set, or UNLOCKED with no reason given at all).

This test only reads the registry, the filesystem, the acceptance manifest, and git
history. It makes no network or paid-API call and changes nothing.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

REGISTRY_PATH = ROOT / "command_center" / "function_lock_registry.json"
MANIFEST_PATH = ROOT / "tests" / "acceptance_manifest.json"

_VALID_STATUSES = {"LOCKED", "UNLOCKED", "PROTECTED", "UNPROTECTED", "REGRESSION"}


def _load_registry() -> dict:
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


def _load_manifest_tests() -> set[str]:
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        data = json.load(f)
    # Manifest entries are sometimes bare filenames (no "tests/" prefix, e.g. a
    # root-level test file) -- normalize both forms so membership checks agree
    # regardless of how a given entry happens to be spelled.
    raw = set(data.get("tests") or [])
    normalized = set()
    for entry in raw:
        normalized.add(entry)
        normalized.add(entry.replace("tests/", "", 1) if entry.startswith("tests/") else f"tests/{entry}")
    return normalized


def _commit_exists(commit: str) -> bool:
    if not commit:
        return False
    try:
        result = subprocess.run(
            ["git", "cat-file", "-e", commit],
            cwd=str(ROOT), capture_output=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


class RegistryLoadsTests(unittest.TestCase):
    def test_registry_file_exists_and_is_valid_json(self):
        self.assertTrue(REGISTRY_PATH.is_file(), REGISTRY_PATH)
        registry = _load_registry()
        self.assertIn("functions", registry)
        self.assertIsInstance(registry["functions"], dict)
        self.assertGreater(len(registry["functions"]), 0)


class PerFunctionIntegrityTests(unittest.TestCase):
    """One subTest per function, so a single bad entry names itself clearly."""

    @classmethod
    def setUpClass(cls):
        cls.registry = _load_registry()
        cls.manifest_tests = _load_manifest_tests()

    def test_every_function_has_a_recognized_status(self):
        for name, entry in self.registry["functions"].items():
            with self.subTest(function=name):
                status = entry.get("status")
                self.assertIn(
                    status, _VALID_STATUSES,
                    f"{name}: status {status!r} is not one of {sorted(_VALID_STATUSES)}",
                )

    def test_locked_functions_have_a_protected_customer_path_test(self):
        for name, entry in self.registry["functions"].items():
            if entry.get("status") != "LOCKED":
                continue
            with self.subTest(function=name):
                files = entry.get("protected_test_files") or []
                self.assertTrue(
                    files, f"{name}: LOCKED but lists no protected_test_files at all",
                )

    def test_locked_functions_protected_test_files_exist_on_disk(self):
        for name, entry in self.registry["functions"].items():
            if entry.get("status") != "LOCKED":
                continue
            for rel_path in entry.get("protected_test_files") or []:
                with self.subTest(function=name, file=rel_path):
                    self.assertTrue(
                        (ROOT / rel_path).is_file(),
                        f"{name}: protected test file {rel_path!r} does not exist on disk",
                    )

    def test_locked_functions_protected_test_files_are_in_acceptance_manifest(self):
        for name, entry in self.registry["functions"].items():
            if entry.get("status") != "LOCKED":
                continue
            for rel_path in entry.get("protected_test_files") or []:
                with self.subTest(function=name, file=rel_path):
                    self.assertIn(
                        rel_path, self.manifest_tests,
                        f"{name}: protected test file {rel_path!r} exists but is not "
                        f"registered in tests/acceptance_manifest.json -- the Fast/Full "
                        f"Gates would never actually run it",
                    )

    def test_locked_functions_have_a_real_verifiable_last_known_good_commit(self):
        for name, entry in self.registry["functions"].items():
            if entry.get("status") != "LOCKED":
                continue
            with self.subTest(function=name):
                commit = entry.get("last_known_good_commit")
                self.assertTrue(
                    commit,
                    f"{name}: LOCKED but last_known_good_commit is empty -- a LOCKED "
                    f"claim must name the commit it was proven at (Rule 9, "
                    f"PROTECTED_GENERATOR_RULE.md: never manufacture one, but a real "
                    f"LOCKED status requires a real commit)",
                )
                if commit:
                    self.assertTrue(
                        _commit_exists(commit),
                        f"{name}: last_known_good_commit {commit!r} does not exist in "
                        f"this repository's git history",
                    )

    def test_unlock_relock_metadata_is_internally_consistent(self):
        for name, entry in self.registry["functions"].items():
            status = entry.get("status")
            unlocked_by = entry.get("unlocked_by")
            unlocked_reason = entry.get("unlocked_reason")
            relocked_by = entry.get("relocked_by")
            relocked_after_tests = entry.get("relocked_after_tests")

            with self.subTest(function=name, check="locked_has_no_open_unlock"):
                if status == "LOCKED":
                    self.assertIsNone(
                        unlocked_by,
                        f"{name}: status is LOCKED but unlocked_by is still set "
                        f"({unlocked_by!r}) -- an unlock was never closed out",
                    )
                    self.assertIsNone(
                        unlocked_reason,
                        f"{name}: status is LOCKED but unlocked_reason is still set",
                    )

            with self.subTest(function=name, check="unlocked_has_a_reason"):
                if status == "UNLOCKED":
                    self.assertTrue(
                        unlocked_by,
                        f"{name}: status is UNLOCKED but unlocked_by is empty -- "
                        f"an explicit unlock must name who unlocked it",
                    )
                    self.assertTrue(
                        unlocked_reason,
                        f"{name}: status is UNLOCKED but unlocked_reason is empty -- "
                        f"an explicit unlock must state why",
                    )
                    self.assertIsNone(
                        relocked_by,
                        f"{name}: status is UNLOCKED but relocked_by is already set -- "
                        f"it has not been relocked yet",
                    )
                    self.assertIsNone(
                        relocked_after_tests,
                        f"{name}: status is UNLOCKED but relocked_after_tests is "
                        f"already set -- it has not been relocked yet",
                    )

            with self.subTest(function=name, check="relock_fields_are_paired"):
                self.assertEqual(
                    relocked_by is None, relocked_after_tests is None,
                    f"{name}: relocked_by and relocked_after_tests must both be set "
                    f"or both be null, not one without the other",
                )

    def test_protected_or_better_functions_declare_at_least_one_test_file(self):
        # PROTECTED/UNPROTECTED/REGRESSION are not held to the LOCKED bar, but a
        # function claiming PROTECTED must still point at something real, or the
        # distinction between PROTECTED and UNPROTECTED is meaningless.
        for name, entry in self.registry["functions"].items():
            if entry.get("status") != "PROTECTED":
                continue
            with self.subTest(function=name):
                files = entry.get("protected_test_files") or []
                self.assertTrue(files, f"{name}: status PROTECTED but no test files listed")
                for rel_path in files:
                    self.assertTrue(
                        (ROOT / rel_path).is_file(),
                        f"{name}: protected test file {rel_path!r} does not exist on disk",
                    )


if __name__ == "__main__":
    unittest.main()
