"""The Factory's version must be single-sourced, shown, and enforced.

ROOT CAUSE THIS GUARDS
----------------------
The version was a string literal inside app.py, bumped by hand when someone
remembered. Nothing compared it against the code that shipped, so it silently
went stale: three customer-facing releases were committed while the footer
still read v1.3.0.

The number now lives in one plain-text VERSION file, everything reads it
through one helper, and scripts/check_version.py refuses a production change
that forgot to raise it.

No external call is made by any test here.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.factory_version import (  # noqa: E402
    FALLBACK_VERSION,
    InvalidVersion,
    get_version,
    is_newer,
    parse_version,
    read_version_file,
)

sys.path.insert(0, str(ROOT / "scripts"))
import check_version  # noqa: E402

VERSION_FILE = ROOT / "VERSION"
CHANGELOG = ROOT / "CHANGELOG.md"
INDEX_HTML = ROOT / "templates" / "index.html"


# ------------------------------------------------------- the version file ---


def test_version_file_exists_at_the_repository_root():
    assert VERSION_FILE.is_file(), "VERSION must be the single source of truth"


def test_version_is_valid_semantic_versioning():
    parse_version(read_version_file(VERSION_FILE))


def test_version_file_holds_nothing_but_the_number():
    raw = VERSION_FILE.read_text(encoding="utf-8")
    assert raw.strip() == raw.strip("\r\n \t"), "no surrounding padding"
    assert "\n" not in raw.strip(), "one line only"
    for noise in ("v", "version", "#", "=", "release"):
        assert noise not in raw.lower(), f"VERSION must not contain {noise!r}"


@pytest.mark.parametrize(
    "bad",
    ["", "v1.4.0", "1.4", "1.4.0.1", "1.4.0-beta", "one.four.zero",
     "1.4.0 # release", "01.4.0", "1.4.0\n1.5.0"],
)
def test_malformed_versions_are_rejected(bad):
    with pytest.raises(InvalidVersion):
        parse_version(bad)


def test_versions_compare_numerically_not_alphabetically():
    assert is_newer("1.10.0", "1.9.0")
    assert is_newer("2.0.0", "1.99.99")
    assert not is_newer("1.4.0", "1.4.0")
    assert not is_newer("1.3.9", "1.4.0")


# ---------------------------------------------------- reading it safely -----


def test_a_missing_version_file_fails_safely(monkeypatch, tmp_path):
    """Customers must never see a traceback or a filesystem path."""
    import services.factory_version as fv

    monkeypatch.setattr(fv, "VERSION_FILE", tmp_path / "VERSION")
    assert fv.get_version() == FALLBACK_VERSION


def test_a_malformed_version_file_fails_safely(monkeypatch, tmp_path):
    import services.factory_version as fv

    broken = tmp_path / "VERSION"
    broken.write_text("not a version", encoding="utf-8")
    monkeypatch.setattr(fv, "VERSION_FILE", broken)
    assert fv.get_version() == FALLBACK_VERSION


def test_the_fallback_reveals_nothing():
    assert "/" not in FALLBACK_VERSION and "\\" not in FALLBACK_VERSION
    parse_version(FALLBACK_VERSION)


# ------------------------------------------------- one source, no copies ----


def test_the_application_reads_the_version_from_the_file():
    import app

    assert app.APP_VERSION == read_version_file(VERSION_FILE)


def test_app_no_longer_hardcodes_a_version_literal():
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert 'APP_VERSION = "' not in src, "the version must not be a literal"
    assert "get_version" in src


def test_no_customer_template_hardcodes_its_own_version():
    import re

    for template in (ROOT / "templates").rglob("*.html"):
        text = template.read_text(encoding="utf-8", errors="replace")
        literals = re.findall(r"v?\d+\.\d+\.\d+", text)
        # Third-party CDN URLs legitimately pin a library version.
        offenders = [
            m for m in literals
            if not any(tok in text for tok in ("cdn.", "unpkg", "jsdelivr"))
        ]
        assert not offenders, f"{template.name} hardcodes a version: {offenders}"


def test_the_footer_renders_the_version_from_the_file():
    html = INDEX_HTML.read_text(encoding="utf-8")
    assert "app_version" in html, "the footer must render the shared value"
    assert "Digital Product Factory" in html


def test_the_served_page_shows_the_current_version():
    import app as app_module

    client = app_module.app.test_client()
    page = client.get("/").get_data(as_text=True)
    current = read_version_file(VERSION_FILE)
    assert f"v{current}" in page, "the footer must show the current version"


def test_the_page_never_shows_build_internals():
    """No commit hash, branch, build path or development status for customers."""
    import re

    import app as app_module

    page = app_module.app.test_client().get("/").get_data(as_text=True)
    # Whole words only: "git" must not match inside "digital".
    #
    # "debug" is deliberately not in this list. It appears in the admin-only
    # control "Show test/debug/internal records", which is a real feature for
    # the operator, not a build internal leaking to a customer. Asserting on it
    # would force unrelated copy to change to satisfy this test.
    for leak in ("commit", "branch", "git", "sha", "traceback", "stacktrace"):
        assert not re.search(rf"\b{leak}\b", page, re.I), f"page leaks {leak!r}"
    for path_leak in ("C:\\Users", "/sessions/", "Product-Pipeline"):
        assert path_leak not in page, f"page leaks the path {path_leak!r}"
    # A 40-character hex string is a commit hash by any other name.
    assert not re.search(r"\b[0-9a-f]{40}\b", page), "page leaks a commit hash"


# ------------------------------------------------------- the enforcement ---


def test_production_paths_require_a_bump():
    for path in (
        "app.py", "database.py", "services/ebook_package.py",
        "static/js/app.js", "templates/index.html", "static/css/main.css",
        "scripts/run_factory_tests.py", "migrations/0001_init.sql",
        "routes/api.py",
    ):
        assert check_version.is_production(path), path


def test_non_production_paths_do_not_require_a_bump():
    # These are literal strings fed to a path classifier, not files anything
    # opens: no database is connected to and no export is written here. The
    # real locations still resolve through FACTORY_DB_PATH and
    # FACTORY_EXPORTS_DIR, exactly as everywhere else in the suite.
    for path in (
        "tests/test_thing.py", "tests/conftest.py", "CHANGELOG.md",
        "README.md", "docs/guide.md", ".gitignore", "VERSION",
        "projects.db", "exports/pkg/ebook.pdf", "logs/factory.log",
        "test-results/report.xml", "_backup_2026-08-31/app.py",
        "overnight_work/notes.txt", "screenshot.png",
        "Factory Step1.bat",
    ):
        assert not check_version.is_production(path), path


def test_a_mixed_change_set_still_requires_a_bump():
    files = ["tests/test_thing.py", "services/ebook_package.py"]
    assert any(check_version.is_production(f) for f in files)


def test_the_checker_reports_the_required_message():
    src = (ROOT / "scripts" / "check_version.py").read_text(encoding="utf-8")
    assert "Factory code changed. Update VERSION before committing." in src


def test_the_checker_never_edits_anything():
    """It reports and exits non-zero. It must not write, commit, or open a database."""
    src = (ROOT / "scripts" / "check_version.py").read_text(encoding="utf-8")
    for forbidden in (
        "write_text(", "open(", "unlink(", "os.remove", "shutil.",
        "commit -m", "git add", "update_project", "import sqlite3",
        "sqlite3.connect",
    ):
        assert forbidden not in src, f"the checker must not use {forbidden!r}"


def test_the_checker_runs_and_passes_on_the_current_tree():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_version.py"), "--working"],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# ---------------------------------------------------------- the changelog ---


def test_changelog_exists_and_covers_the_current_version():
    assert CHANGELOG.is_file()
    text = CHANGELOG.read_text(encoding="utf-8")
    current = read_version_file(VERSION_FILE)
    assert f"## {current}" in text, f"CHANGELOG has no entry for {current}"


def test_changelog_entry_answers_the_customer_questions():
    text = CHANGELOG.read_text(encoding="utf-8")
    current = read_version_file(VERSION_FILE)
    section = text.split(f"## {current}", 1)[1].split("\n## ", 1)[0]
    for heading in ("What changed", "What was fixed", "steps change", "Release gate"):
        assert heading.lower() in section.lower(), f"missing: {heading}"
    assert len(section.split()) > 60, "the entry should actually explain itself"


def test_changelog_leaks_no_secrets_or_private_paths():
    text = CHANGELOG.read_text(encoding="utf-8")
    for leak in ("sk-", "api_key", "API_KEY", "C:\\Users", "/sessions/",
                 "Traceback", "password", "Bearer "):
        assert leak not in text, f"CHANGELOG leaks {leak!r}"
