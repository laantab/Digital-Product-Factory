"""FUNCTION LOCK ENFORCEMENT (2026-09-12, strengthened 2026-09-12).

This is the piece that makes a LOCKED function mean something at the moment a
change is made -- not only while it is still sitting uncommitted in the working
tree, and not only in a document someone might remember to read.

Why "diff against HEAD" alone is not enough
--------------------------------------------
The first version of this test compared the working tree to `HEAD` (plus new
untracked files). That catches an in-progress, uncommitted edit -- but the
moment the edit is committed, `git diff HEAD` goes back to empty and the check
silently stops protecting anything. A clean-tree Fast/Full Gate run after the
commit, and CI/GitHub evaluating the pushed commit, would both see nothing.
That is a real gap: a locked function's files can be changed, committed, and
released without ever tripping this test.

The fix: compare against each dependency's own durable baseline, not HEAD
--------------------------------------------------------------------------
For every file, the baseline is **the most recent `last_known_good_commit`,
among every currently-LOCKED function that declares that file as one of its
own files or shared dependencies.** Concretely:

  - `git diff <baseline>` (one ref, no second ref) compares that historical
    commit's tree against the CURRENT WORKING TREE -- which is HEAD's tree
    when the tree is clean, and HEAD-plus-uncommitted-edits when it is not.
    One comparison therefore catches an uncommitted edit, an edit that has
    already been committed since the baseline, or both, with no special case
    for "is the tree clean right now" -- exactly what is needed for this to
    survive a commit, a clean-tree gate run, and CI checking out the pushed
    tree.
  - New untracked files never show up in any `git diff`, so they are unioned
    in separately via `git ls-files --others --exclude-standard`.

Why "most recent LKG among the file's owners" and not "each function's own
LKG" or a single global baseline
------------------------------------------------------------------------------
This repository is a single linear branch (`main`); LOCKED functions do not
all reach LOCKED at the same commit, and several declare the SAME shared file
(`static/js/app.js`, `services/packaging.py`, `data/topic_vocabulary_packs.json`,
...). If function A's shared file is legitimately changed and relocked at a
later commit than sibling function B's own `last_known_good_commit`, then
diffing from B's OWN (older) LKG would flag A's already-tested, already-
shipped change as a fresh violation against B -- a permanent false positive
baked into ordinary history. This was verified directly against this repo,
not assumed: `git diff a021385 HEAD --name-only` (Word Search's own LKG)
already shows `static/js/app.js` changed, because Coloring Book's later,
fully-gated v1.7.3 fix (`984b268`) touched that same shared file. A
per-function-own-LKG baseline would make Word Search's lock permanently red
today, for a change that has nothing to do with Word Search and was already
verified.

Grouping by the newest LKG among a file's actual owners solves this: every
owner of that file was itself proven good no earlier than its own LKG, so the
most recent of those LKGs is the newest point at which the whole group's
shared file is jointly known-good. Diffing from THAT point forward correctly
reports "nothing new" for legitimate prior history, and correctly flags a
real, not-yet-verified change to that file for every LOCKED function that
depends on it (matching the "shared-code protection is mandatory" rule in
PROTECTED_GENERATOR_RULE.md) -- not invented, just the max of real,
already-recorded, integrity-checked commits (see
`tests/test_function_lock_registry_integrity.py`, which independently proves
every LKG used here really exists in this repository's git history).

One further refinement, found while proving this empirically: "owners" for
baseline purposes means every function with a recorded `last_known_good_commit`
-- LOCKED **or** UNLOCKED -- not only functions that are LOCKED at this exact
moment. An UNLOCKED function's last LKG still records real, previously-verified
history for any file it shares with a LOCKED sibling; dropping it from the
baseline the instant it is unlocked would resurrect the very false positive
described above (a sibling's already-shipped shared-file change reappearing as
a fresh violation) for as long as that one function happens to be mid-change.
Only the REPORTING step -- which functions get named as "hit" -- is filtered
to functions that are LOCKED right now; an UNLOCKED function is deliberately
never reported against its own in-progress change.

This test makes no network call and never modifies anything; it only reads
`git diff`/`git log`/`git ls-files`.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

REGISTRY_PATH = ROOT / "command_center" / "function_lock_registry.json"


def _load_registry() -> dict:
    with open(REGISTRY_PATH, encoding="utf-8") as f:
        return json.load(f)


def _git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=str(ROOT), capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"git {' '.join(args)} failed to run: {exc}") from exc
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


@lru_cache(maxsize=None)
def _commit_timestamp(commit: str) -> int:
    """Committer timestamp (seconds), used only to pick the newer of two real
    commits -- never to invent a baseline, only to order ones already recorded
    in the registry and independently verified to exist."""
    out = _git("log", "-1", "--format=%ct", commit)
    return int(out.strip())


@lru_cache(maxsize=None)
def _untracked_files() -> frozenset[str]:
    out = _git("ls-files", "--others", "--exclude-standard")
    return frozenset(p.strip().replace("\\", "/") for p in out.splitlines() if p.strip())


@lru_cache(maxsize=None)
def _changed_files_since(baseline_commit: str) -> frozenset[str]:
    """Every file different between `baseline_commit` and right now.

    `git diff <commit>` (a single ref, no second ref) compares that commit's
    tree against the current index + working directory -- so this captures
    both changes already committed since `baseline_commit` AND any
    uncommitted edit on top of them, in one comparison. Untracked files never
    appear in a diff regardless of what it is compared against, so they are
    unioned in separately.
    """
    changed = set()
    diff_output = _git("diff", baseline_commit, "--name-only")
    changed.update(line.strip() for line in diff_output.splitlines() if line.strip())
    changed.update(_untracked_files())
    return frozenset(p.replace("\\", "/") for p in changed)


def _matches(changed_file: str, dependency: str) -> bool:
    if dependency.endswith("/"):
        return changed_file.startswith(dependency)
    return changed_file == dependency


def _every_recorded_lkg(registry: dict) -> dict[str, str]:
    """name -> last_known_good_commit, for every function that has one at all
    -- LOCKED or UNLOCKED. An UNLOCKED function's last_known_good_commit is
    NOT dropped from this map: it still records the last commit at which that
    function (and everything it shares with siblings) was jointly verified
    good, and every LOCKED sibling that shares a file with it is entitled to
    treat that same historical commit as part of the "known good" baseline
    for that file -- unlocking one function does not retroactively erase
    already-shipped, already-verified history for the files it shares with
    others. (Only PROTECTED/UNPROTECTED/REGRESSION functions have no
    last_known_good_commit at all, per the registry's own schema.)
    """
    return {
        name: entry["last_known_good_commit"]
        for name, entry in registry["functions"].items()
        if entry.get("last_known_good_commit")
    }


def _currently_locked(registry: dict) -> set[str]:
    """Names of functions whose status is LOCKED right now -- only these are
    ever reported as "hit"; an UNLOCKED function's own files are deliberately
    exempt from being reported against itself (that is the point of an
    explicit unlock), even though its recorded LKG still counts toward its
    siblings' shared-dependency baselines (see `_every_recorded_lkg`).
    """
    return {
        name for name, entry in registry["functions"].items()
        if entry.get("status") == "LOCKED"
    }


def _locked_functions_touched_since_their_baselines(registry: dict) -> dict[str, list[str]]:
    """Map function_name -> [changed files that touch it], for every
    CURRENTLY-LOCKED function whose own files or shared dependencies have
    changed since the correct baseline for that specific file (see module
    docstring for why the baseline is per-dependency-file, not per-function).

    Every function with a recorded last_known_good_commit -- LOCKED or
    UNLOCKED -- contributes to that per-file baseline (an unlock does not
    erase a sibling's already-verified history); only currently-LOCKED
    functions are ever reported as hit (an UNLOCKED function is deliberately
    exempt from being flagged against its own in-progress change).
    """
    all_lkgs = _every_recorded_lkg(registry)
    locked_now = _currently_locked(registry)
    if not all_lkgs or not locked_now:
        return {}

    # Group every dependency-holding function's declared dependency strings
    # by their literal text -- the registry reuses the exact same string
    # ("static/js/app.js", "services/packaging.py", ...) across every
    # function that shares it, so exact-string grouping correctly finds every
    # owner of a given file or directory-prefix entry.
    owners_by_dep: dict[str, list[str]] = {}
    for name in all_lkgs:
        deps = registry["functions"][name].get("shared_code_dependencies") or []
        for dep in deps:
            owners_by_dep.setdefault(dep, []).append(name)

    hits: dict[str, set[str]] = {}
    for dep, owners in owners_by_dep.items():
        baseline = max((all_lkgs[o] for o in owners), key=_commit_timestamp)
        changed = _changed_files_since(baseline)
        matched_files = [f for f in changed if _matches(f, dep)]
        if not matched_files:
            continue
        for owner in owners:
            if owner not in locked_now:
                continue  # UNLOCKED (or otherwise not LOCKED) -- not reported
            hits.setdefault(owner, set()).update(matched_files)

    return {name: sorted(files) for name, files in hits.items()}


class FunctionLockEnforcementTests(unittest.TestCase):
    def test_no_change_since_baseline_touches_a_locked_function_without_an_explicit_unlock(self):
        try:
            registry = _load_registry()
            hits = _locked_functions_touched_since_their_baselines(registry)
        except RuntimeError as exc:
            self.skipTest(f"could not read git state: {exc}")
            return

        if not hits:
            return

        lines = [
            "A LOCKED function's files have changed since its last-known-good "
            "baseline -- committed, uncommitted, or both -- without an explicit "
            "unlock. To proceed:",
            "  1. In command_center/function_lock_registry.json, set the affected "
            "function's \"status\" to \"UNLOCKED\" and fill in unlocked_by / "
            "unlocked_reason.",
            "  2. Make the change.",
            "  3. Run every file that function lists under protected_test_files "
            "(and any OTHER locked function listed below, if the touched file is "
            "shared with it).",
            "  4. Set \"status\" back to \"LOCKED\" with the new "
            "last_known_good_commit (the commit that contains the verified "
            "change) and relocked_by/relocked_after_tests filled in.",
            "",
            "Locked functions affected by the current change:",
        ]
        for name, files in sorted(hits.items()):
            lines.append(f"  - {name}: {', '.join(files)}")

        self.fail("\n".join(lines))


if __name__ == "__main__":
    unittest.main()
