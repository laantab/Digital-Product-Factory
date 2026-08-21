"""Central helper for test-owned filesystem paths.

Several test files used to hardcode ``ROOT / "exports"`` — the real,
production ``flask_app/exports`` folder — to write and then re-read their
own scratch fixtures (generated PDFs, PNGs, ZIPs). tests/conftest.py sets
``FACTORY_EXPORTS_DIR`` to a fresh temporary directory before any Factory
application module is imported, and every application EXPORTS_DIR constant
now honors that variable — but a test file that still hardcodes
``ROOT / "exports"`` for its own verification reads will look in the wrong
place (the real folder) even though the application wrote the file into the
isolated temp folder. ``resolve_test_exports_root()`` gives test code the exact same
isolated root the application is using, so test-side reads/writes and
application-side reads/writes always agree.

Use it instead of hardcoding ``ROOT / "exports"``:

    from tests._test_paths import resolve_test_exports_root
    pkg_dir = resolve_test_exports_root() / package_id

Deliberately NOT used by tests/test_ebook_chapter_production.py or
tests/test_ebook_design_export.py — both read a pre-existing, real,
persistent fixture at ``exports/ebook_design_fixture_pass_c`` that this
change is explicitly instructed to leave untouched pending a later, separate
cleanup pass.
"""
from __future__ import annotations

import os
from pathlib import Path

FLASK_APP_ROOT = Path(__file__).resolve().parents[1]


def resolve_test_exports_root() -> Path:
    """The active exports root for this test session.

    Resolved lazily (call this at the point of use, not at import time) so
    it always reflects whatever tests/conftest.py already set up. Fails
    loudly instead of silently falling back to the real ``exports/`` folder
    if isolation somehow did not run.
    """
    configured = os.environ.get("FACTORY_EXPORTS_DIR")
    if configured:
        return Path(configured)
    raise RuntimeError(
        "FACTORY_EXPORTS_DIR is not set — tests/conftest.py isolation did "
        "not run before this helper was used. Refusing to fall back to the "
        "real flask_app/exports folder."
    )
