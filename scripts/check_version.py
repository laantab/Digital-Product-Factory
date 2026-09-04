"""Refuse a production change that forgot to update VERSION.

WHY
---
"Remember to bump the version" is not a process, it is a hope. This script is
the process: it compares the staged (or working) change set against the last
committed VERSION and fails before the commit is made when Factory code moved
and the version did not.

WHAT COUNTS AS PRODUCTION
-------------------------
Anything a customer can end up running: application code, services, templates,
JavaScript, CSS, customer-facing assets, schema/migration code, the build
scripts used to operate the Factory, product-generation logic, and defaults
that change behaviour. Tests, generated products, logs, databases, caches,
screenshots, recovery folders, notes and gitignore housekeeping do not count on
their own -- but a change set containing BOTH production and test files does.

WHAT IT NEVER DOES
------------------
It never edits VERSION, never rewrites a commit, never touches a customer
project or a database. It reports, and it exits non-zero.

    python scripts/check_version.py            # staged changes (pre-commit)
    python scripts/check_version.py --working   # staged + unstaged
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.factory_version import (  # noqa: E402
    InvalidVersion,
    parse_version,
    read_version_file,
)

VERSION_PATH = "VERSION"
CHANGELOG_PATH = "CHANGELOG.md"

#: Directories whose contents are production code when they change.
PRODUCTION_DIRS = (
    "services/",
    "routes/",
    "static/",
    "templates/",
    "scripts/",
    "migrations/",
)
#: Individual files at the root that are production code.
PRODUCTION_FILES = (
    "app.py",
    "database.py",
    "ai_client.py",
    "wsgi.py",
    "requirements.txt",
)
#: Extensions that make a file production code when it lives in a production
#: directory (or at the root of the repository).
PRODUCTION_SUFFIXES = (".py", ".js", ".css", ".html", ".jinja", ".sql")

#: Never require a bump for these on their own.
EXEMPT_DIRS = (
    "tests/",
    "test-results/",
    "exports/",
    "uploads/",
    "downloads/",
    "logs/",
    "overnight_work/",
    "overnight_recovery_",
    "_backup_",
    "docs/",
    "notes/",
    ".github/",
)
EXEMPT_FILES = (
    ".gitignore",
    "CHANGELOG.md",
    "README.md",
    "VERSION",
)
EXEMPT_SUFFIXES = (
    ".md", ".txt", ".log", ".db", ".sqlite", ".sqlite3", ".png", ".jpg",
    ".jpeg", ".gif", ".pdf", ".zip", ".csv", ".ttf", ".otf", ".woff",
    ".woff2", ".ico", ".bat", ".lock",
)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(ROOT), capture_output=True, text=True
    )
    if result.returncode != 0:
        return ""
    return result.stdout


def changed_files(include_working: bool) -> list[str]:
    names: set[str] = set()
    for line in _git("diff", "--cached", "--name-only").splitlines():
        if line.strip():
            names.add(line.strip())
    if include_working:
        for line in _git("diff", "--name-only").splitlines():
            if line.strip():
                names.add(line.strip())
    return sorted(names)


def is_exempt(path: str) -> bool:
    lowered = path.lower()
    if path in EXEMPT_FILES or Path(path).name in EXEMPT_FILES:
        return True
    if any(lowered.startswith(d) or f"/{d}" in lowered for d in EXEMPT_DIRS):
        return True
    return Path(lowered).suffix in EXEMPT_SUFFIXES


def is_production(path: str) -> bool:
    """A change a customer could end up running."""
    if is_exempt(path):
        return False
    if path in PRODUCTION_FILES:
        return True
    suffix = Path(path).suffix
    if any(path.startswith(d) for d in PRODUCTION_DIRS):
        return suffix in PRODUCTION_SUFFIXES
    # A code file at the repository root is production too.
    if "/" not in path and suffix in PRODUCTION_SUFFIXES:
        return True
    return False


def committed_version() -> str | None:
    """The VERSION recorded in HEAD, or None on the very first release."""
    raw = _git("show", f"HEAD:{VERSION_PATH}")
    if not raw.strip():
        return None
    try:
        return read_version_file_text(raw)
    except InvalidVersion:
        return None


def read_version_file_text(raw: str) -> str:
    text = raw.strip()
    parse_version(text)
    return text


def main() -> int:
    include_working = "--working" in sys.argv
    files = changed_files(include_working)
    production = [f for f in files if is_production(f)]

    print("=" * 70)
    print("FACTORY VERSION CHECK")
    print("=" * 70)
    if not files:
        print("  no changes to check")
        return 0
    print(f"  changed files    : {len(files)}")
    print(f"  production files : {len(production)}")
    for path in production[:20]:
        print(f"     {path}")
    if len(production) > 20:
        print(f"     ... and {len(production) - 20} more")

    # 1. VERSION must be present and well formed, always.
    try:
        current = read_version_file(ROOT / VERSION_PATH)
    except FileNotFoundError:
        print("\nFAIL: VERSION file is missing at the repository root.")
        return 1
    except InvalidVersion as exc:
        print(f"\nFAIL: VERSION is not a bare MAJOR.MINOR.PATCH value ({exc}).")
        return 1
    print(f"\n  VERSION on disk  : {current}")

    if not production:
        print("\nPASS: no production code changed; no version bump required.")
        return 0

    previous = committed_version()
    print(f"  VERSION at HEAD  : {previous or '(none yet)'}")

    if previous is None:
        print("\nPASS: first recorded version.")
    elif current == previous:
        print("\nFactory code changed. Update VERSION before committing.")
        print(f"  VERSION is still {current}. Choose the increase:")
        major, minor, patch = parse_version(current)
        print(f"    PATCH -> {major}.{minor}.{patch + 1}   fix, reliability, wording")
        print(f"    MINOR -> {major}.{minor + 1}.0   new customer-facing feature")
        print(f"    MAJOR -> {major + 1}.0.0   breaking redesign")
        print("  Then add a matching CHANGELOG.md entry.")
        return 1
    elif parse_version(current) < parse_version(previous):
        print(f"\nFAIL: VERSION moved backward, {previous} -> {current}.")
        return 1
    else:
        print(f"\n  version raised   : {previous} -> {current}")

    # 2. The changelog must mention the version being released.
    changelog = ROOT / CHANGELOG_PATH
    if not changelog.is_file():
        print(f"\nFAIL: {CHANGELOG_PATH} is missing.")
        return 1
    if current not in changelog.read_text(encoding="utf-8"):
        print(f"\nFAIL: {CHANGELOG_PATH} has no entry for {current}.")
        return 1
    print(f"  changelog entry  : found for {current}")

    print("\nPASS: production changes carry a version bump and a changelog entry.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
