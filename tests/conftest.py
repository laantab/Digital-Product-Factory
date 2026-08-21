"""Global safety fixtures for the Factory test suite."""
from __future__ import annotations

import atexit
import json
import os
import shutil
import socket
import tempfile
from urllib.parse import urlparse

import pytest


# ---------------------------------------------------------------------------
# Database / exports isolation.
#
# This block MUST run before any Factory application module (app, database,
# services.*) is imported anywhere in the test session. pytest always
# imports a directory's conftest.py before it imports any test file in that
# directory, so placing this at module level (not inside a fixture) here
# wins the race against the first `from app import app` / `import database`
# in any test module. database.DB_PATH and the various service EXPORTS_DIR
# constants are computed ONCE at import time from these env vars, so setting
# them later (e.g. inside a fixture, which only runs once a test is already
# executing) would be too late.
#
# Only environment variables the application already reads are set here —
# see database.py (FACTORY_DB_PATH), and database.py/services/cover_agent.py/
# services/ebook_visual_pipeline.py/services/visual_fallback.py/
# services/ebook_package.py/services/coloring_book/*.py/
# services/customer_keep_exports.py/services/quality/download_pipeline_agent.py/
# services/quality/final_output_gate.py/services/ebook_project_workspace.py/
# services/kdp/preflight.py/services/math_worksheet/pdf_builder.py/
# services/spelling_worksheet/pdf_builder.py (FACTORY_EXPORTS_DIR, with
# FLASK_EXPORTS_DIR as the name a second family of modules already honors
# instead). No new environment variable is invented.
#
# Known, deliberately deferred gap: tests/test_ebook_chapter_production.py
# and tests/test_ebook_design_export.py still read/write a pre-existing,
# real, persistent fixture at exports/ebook_design_fixture_pass_c — left
# untouched on explicit instruction, pending a later, separate cleanup pass.
_FACTORY_TEST_ROOT = tempfile.mkdtemp(prefix="factory_test_root_")
_FACTORY_TEST_DB = os.path.join(_FACTORY_TEST_ROOT, "projects.db")
_FACTORY_TEST_EXPORTS = os.path.join(_FACTORY_TEST_ROOT, "exports")
os.makedirs(_FACTORY_TEST_EXPORTS, exist_ok=True)

os.environ["FACTORY_DB_PATH"] = _FACTORY_TEST_DB
os.environ["FACTORY_EXPORTS_DIR"] = _FACTORY_TEST_EXPORTS
os.environ["FLASK_EXPORTS_DIR"] = _FACTORY_TEST_EXPORTS


def _cleanup_factory_test_root() -> None:
    shutil.rmtree(_FACTORY_TEST_ROOT, ignore_errors=True)


atexit.register(_cleanup_factory_test_root)


_FROZEN_FIXTURE_FILES = (
    "frozen_project_2472.json",   # FROZEN_LIVE_EBOOK_PROJECT_ID — internal QA record
    "frozen_project_4249.json",   # real, protected customer product (database._PROTECTED_PROJECT_IDS)
    "frozen_project_14626.json",  # real, protected customer product (database._PROTECTED_PROJECT_IDS)
    "frozen_project_17365.json",  # real customer product (Deep Sea Ocean Creatures)
)


def _seed_frozen_fixtures() -> None:
    """Seed deterministic, sanitized regression fixtures into the isolated
    temp database — never into the real projects.db.

    Numerous test files hard-code lookups of project ids 2472, 4249, and
    14626 (see FROZEN_LIVE_EBOOK_PROJECT_ID / database._PROTECTED_PROJECT_IDS
    / database.CUSTOMER_KEEP_PROJECT_IDS), records the application itself
    treats as permanently protected. tests/fixtures/frozen_project_*.json
    are small, reviewable, checked-in fixtures that reproduce the exact
    values those tests assert without ever reading the real database or the
    backup at test time.
    """
    import database

    database.init_db()
    conn = database.get_conn()
    try:
        for filename in _FROZEN_FIXTURE_FILES:
            fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", filename)
            with open(fixture_path, "r", encoding="utf-8") as f:
                fixture = json.load(f)
            row = fixture["row"]
            # Fixtures may reference on-disk assets (e.g. synthetic visual_plan
            # images) with the placeholder "__EXPORTS__" standing in for the
            # isolated temp exports root, whose exact path is only known at
            # session start. Substitute it now, in the serialized JSON, before
            # the row is written.
            data_json = json.dumps(fixture["data"]).replace(
                "__EXPORTS__", _FACTORY_TEST_EXPORTS.replace("\\", "/")
            )
            conn.execute(
                "INSERT INTO projects "
                "(id, name, type, data, user_saved, system_test, temporary, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    row["id"],
                    row["name"],
                    row["type"],
                    data_json,
                    row["user_saved"],
                    row["system_test"],
                    row["temporary"],
                    row["created_at"],
                    row["updated_at"],
                ),
            )
        conn.commit()
    finally:
        conn.close()


def _seed_frozen_visual_assets() -> None:
    """Copy the small, synthetic, deterministic "TEST FIXTURE"-marked PNG/JPG
    images under tests/fixtures/frozen_4249_visuals/ into the isolated temp
    exports root at the paths frozen_project_4249.json references (visual_plan
    aids under .../visuals/, the registered cover source under
    .../cover_photo/). These are locally rendered placeholder graphics
    generated once by a one-off script — never real or licensed photographs,
    and never copied from or into the real exports/ folder.
    """
    src_dir = os.path.join(os.path.dirname(__file__), "fixtures", "frozen_4249_visuals")
    if not os.path.isdir(src_dir):
        return
    pkg_dir = os.path.join(_FACTORY_TEST_EXPORTS, "frozen-4249-fixture-pkg")
    visuals_dst = os.path.join(pkg_dir, "visuals")
    cover_photo_dst = os.path.join(pkg_dir, "cover_photo")
    os.makedirs(visuals_dst, exist_ok=True)
    os.makedirs(cover_photo_dst, exist_ok=True)
    for filename in os.listdir(src_dir):
        dst_dir = cover_photo_dst if filename == "cover_source.jpg" else visuals_dst
        shutil.copy2(os.path.join(src_dir, filename), os.path.join(dst_dir, filename))


def _seed_frozen_export_artifacts() -> None:
    """Create minimal, valid, deterministic PDF/ZIP files on disk for the
    #4249 and #14626 fixtures' package_id, inside the isolated temp exports
    root only. Several tests download these via /download/<package_id>/... —
    those routes serve existing files as-is and do not regenerate content,
    so a small deterministic PDF/ZIP (not a byte-for-byte copy of any real
    customer file) is sufficient and is never sourced from real exports/.
    """
    import zipfile

    from reportlab.pdfgen import canvas

    for package_id, pdf_name in (
        ("frozen-4249-fixture-pkg", "ebook.pdf"),
        ("frozen-14626-fixture-pkg", "ebook.pdf"),
        ("frozen-17365-fixture-pkg", "product.pdf"),
    ):
        pkg_dir = os.path.join(_FACTORY_TEST_EXPORTS, package_id)
        os.makedirs(pkg_dir, exist_ok=True)
        pdf_path = os.path.join(pkg_dir, pdf_name)
        zip_path = os.path.join(pkg_dir, "package.zip")
        c = canvas.Canvas(pdf_path)
        for i in range(3):
            c.drawString(72, 720, f"Frozen QA fixture page {i + 1} for {package_id}")
            c.showPage()
        c.save()
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(pdf_path, arcname=pdf_name)
            zf.writestr("ebook.html", "<html><body>Frozen QA fixture.</body></html>")


def _seed_acceptance_export_fixture() -> None:
    """Copy the fully synthetic tests/fixtures/acceptance_export/*.json files
    into the isolated temp exports root's ebook_live_acceptance_lonnie_event_photo/
    folder, so services.ebook_project_workspace.build_acceptance_project_data()
    — a shared seed helper used by setUp() across most of the ebook test
    suite — has something to read there instead of the real exports/ folder.

    Every value in these 5 files is synthetic; build_acceptance_project_data()
    itself overwrites the outline/chapter content from the application's own
    public REVISED_ACCEPTANCE_OUTLINE_TITLES / event_photo_catalog_by_title()
    constants regardless of what these files contain, so no real historical
    content was needed to build them.
    """
    src_dir = os.path.join(os.path.dirname(__file__), "fixtures", "acceptance_export")
    dst_dir = os.path.join(_FACTORY_TEST_EXPORTS, "ebook_live_acceptance_lonnie_event_photo")
    os.makedirs(dst_dir, exist_ok=True)
    for filename in os.listdir(src_dir):
        shutil.copy2(os.path.join(src_dir, filename), os.path.join(dst_dir, filename))


def _seed_admin_baseline_rows() -> None:
    """Seed a handful of harmless, system_test=1 filler rows so the isolated
    DB has a non-trivial baseline row count for admin-only ("/projects?admin=1",
    include_system=True) views, independent of execution order.

    The real, unisolated projects.db always had thousands of historical rows,
    so some tests assert things like "the admin list has more than 10 rows"
    without creating that data themselves. system_test=1 keeps these out of
    every customer-facing list (list_projects() default, is_customer_saved_product,
    etc.), so they cannot affect customer-list assertions elsewhere.
    """
    import database

    conn = database.get_conn()
    try:
        for i in range(12):
            conn.execute(
                "INSERT INTO projects "
                "(name, type, data, user_saved, system_test, temporary, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"Isolation admin baseline filler {i + 1}",
                    "product",
                    json.dumps({"system_test": True}),
                    0,
                    1,
                    0,
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:00:00+00:00",
                ),
            )
        conn.commit()
    finally:
        conn.close()


_seed_frozen_fixtures()
_seed_frozen_export_artifacts()
_seed_acceptance_export_fixture()
_seed_frozen_visual_assets()
_seed_admin_baseline_rows()
# ---------------------------------------------------------------------------


_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


@pytest.fixture(autouse=True)
def block_paid_and_external_network(monkeypatch):
    """Fail every external network call; local Flask test traffic is allowed."""
    monkeypatch.setenv("FACTORY_TEST_MODE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("AI_INTEGRATIONS_OPENAI_API_KEY", "")
    monkeypatch.setenv("PEXELS_API_KEY", "")

    original_connect = socket.socket.connect
    original_create_connection = socket.create_connection

    def checked_connect(sock, address):
        host = address[0] if isinstance(address, tuple) else str(address)
        if str(host).lower() not in _LOCAL_HOSTS:
            raise RuntimeError(f"External network blocked during tests: {host}")
        return original_connect(sock, address)

    def checked_create_connection(address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else str(address)
        if str(host).lower() not in _LOCAL_HOSTS:
            raise RuntimeError(f"External network blocked during tests: {host}")
        return original_create_connection(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", checked_connect)
    monkeypatch.setattr(socket, "create_connection", checked_create_connection)

    try:
        import requests.sessions

        original_request = requests.sessions.Session.request

        def checked_request(session, method, url, *args, **kwargs):
            host = (urlparse(str(url)).hostname or "").lower()
            if host not in _LOCAL_HOSTS:
                raise RuntimeError(f"External HTTP blocked during tests: {url}")
            return original_request(session, method, url, *args, **kwargs)

        monkeypatch.setattr(requests.sessions.Session, "request", checked_request)
    except ImportError:
        pass
