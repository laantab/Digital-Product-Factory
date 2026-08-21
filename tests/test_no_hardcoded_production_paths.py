"""Static guard: fail the gate if application or test source re-introduces an
unguarded hardcoded reference to a real production write path — the
database file, the exports folder, or any cover/PDF/ZIP/upload/quarantine/
asset directory derived from it — or if a test resolves FACTORY_DB_PATH to
the real projects.db.

This is deliberately a source-text scan (not an import-time check) so it
catches new offenders before they ever run and touch anything real. The
guard itself performs no writes anywhere — it only reads .py files already
on disk and asserts on their text.

Scope: tests/, database.py, routes/, services/ (including services/coloring_book/
and every other builder module) — i.e. every application module a test can
reach, plus the tests themselves.

A hardcoded "exports"/"projects.db" reference is SAFE and not flagged when
it is a default fallback guarded by the same environment variables the test
suite already sets (FACTORY_EXPORTS_DIR / FLASK_EXPORTS_DIR / FACTORY_DB_PATH)
somewhere in the same function — e.g. `os.environ.get("FACTORY_EXPORTS_DIR")
or <real path>`. A bare hardcoded reference with no such guard anywhere
nearby is flagged.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_SCAN_ROOTS = ("tests", "routes", "services")
_SCAN_SINGLE_FILES = ("database.py",)

_EXCLUDE_DIR_PARTS = {".venv", "venv", "__pycache__", "node_modules", ".git"}

# Any of these appearing within _LOOKBACK_LINES lines above a hardcoded-path
# match (i.e. earlier in the same function) makes that match a guarded
# default fallback rather than an unguarded hardcoded path.
_SAFE_MARKERS_RE = re.compile(
    r"FACTORY_EXPORTS_DIR|FLASK_EXPORTS_DIR|FACTORY_DB_PATH|FACTORY_CALL_LOG|FACTORY_PORT"
)
_LOOKBACK_LINES = 15

# Patterns that indicate a hardcoded reference to a real production write
# path: the exports tree (and cover/PDF/ZIP/upload/quarantine/asset
# subfolders under it), or the real database file.
_HARDCODED_PATTERNS = [
    re.compile(r'ROOT\s*/\s*["\']exports["\']'),
    re.compile(r'repo_root\s*/\s*["\']exports["\']'),
    re.compile(r'os\.path\.join\([^)\n]*["\']exports["\']'),
    # Path(...)/"exports", including chained attribute calls in between, e.g.
    # Path(__file__).resolve().parents[2] / "exports".
    re.compile(r'Path\([^)\n]*\)(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\([^)\n]*\)|\[[^\]\n]*\])*)*\s*/\s*["\']exports["\']'),
    re.compile(r'["\']projects\.db["\']'),
]

# Narrow, documented allowlist. Each entry must state exactly why every
# match in that file is safe. Prefer fixing the code over adding an entry
# here — only use this for genuinely read-only verification code.
_ALLOWLIST: dict[str, str] = {
    "test_db_path_isolation.py": (
        "Read-only verification code: intentionally computes the real "
        "exports/ path and real projects.db path to assert application "
        "constants do NOT resolve to them during tests."
    ),
    "test_no_hardcoded_production_paths.py": "This file's own pattern literals.",
    "_test_paths.py": "Match is inside this file's own docstring, describing the pattern to avoid — not executable code.",
    "test_ebook_real_browser_customer_path.py": (
        "cls.db_path = tmp / 'projects.db' — tmp is cls._tmp = "
        "tempfile.TemporaryDirectory(...), a fresh isolated directory, not "
        "the repo root. The literal filename 'projects.db' matches the "
        "guard's regex but this is already fully isolated."
    ),
}


def _iter_scan_files():
    for name in _SCAN_SINGLE_FILES:
        p = ROOT / name
        if p.is_file():
            yield p
    for root_name in _SCAN_ROOTS:
        base = ROOT / root_name
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            if any(part in _EXCLUDE_DIR_PARTS for part in p.parts):
                continue
            yield p


def _find_unguarded_matches(path: Path) -> list[tuple[int, str]]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    found: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        for pattern in _HARDCODED_PATTERNS:
            if not pattern.search(line):
                continue
            window_start = max(0, lineno - 1 - _LOOKBACK_LINES)
            window = "\n".join(lines[window_start:lineno])
            if _SAFE_MARKERS_RE.search(window):
                continue
            found.append((lineno, line.strip()))
    return found


class NoHardcodedProductionPathsTests(unittest.TestCase):
    def test_no_unguarded_hardcoded_production_paths(self):
        offenders: dict[str, list[tuple[int, str]]] = {}
        for path in _iter_scan_files():
            rel = str(path.relative_to(ROOT)).replace("\\", "/")
            name = path.name
            if name in _ALLOWLIST:
                continue
            matches = _find_unguarded_matches(path)
            if matches:
                offenders[rel] = matches
        self.assertFalse(
            offenders,
            "Unguarded hardcoded production path reference(s) found. Guard "
            "the reference with FACTORY_EXPORTS_DIR/FLASK_EXPORTS_DIR/"
            "FACTORY_DB_PATH (see database.py's DB_PATH or _exports_root() "
            "for the pattern), route test code through "
            "tests._test_paths.resolve_test_exports_root(), or add a narrowly "
            "justified allowlist entry in this file for genuinely read-only "
            "verification code: " + repr(offenders),
        )

    def test_allowlist_entries_still_exist(self):
        """Keep the allowlist honest — no stale entries for deleted/renamed files."""
        scanned_names = {p.name for p in _iter_scan_files()}
        for name in _ALLOWLIST:
            self.assertIn(
                name, scanned_names, f"Allowlist entry {name!r} no longer exists — remove it."
            )

    def test_factory_db_path_is_not_the_real_projects_db(self):
        import database

        real_db = (ROOT / "projects.db").resolve()
        self.assertNotEqual(Path(database.DB_PATH).resolve(), real_db)


if __name__ == "__main__":
    unittest.main()
