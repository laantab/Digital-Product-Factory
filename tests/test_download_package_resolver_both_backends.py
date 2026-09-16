"""A stored download URL must resolve to its project on BOTH backends.

THE LIVE DEFECT
---------------
Every download in production returned

    403 {"error":"download_blocked",
         "violations":["stale_or_orphan_export_package"]}

while the identical download served 200 locally. The orphan guard was right;
what it was told was wrong.

Two copies of the package -> project lookup read their rows POSITIONALLY:

    for pid, name, ptype, data_str in rows:
        try:
            d = json.loads(data_str or "{}")
        except Exception:
            pass

SQLite returns sqlite3.Row, which unpacks as a sequence, so that worked.
PostgreSQL is opened with psycopg's dict_row, so every row is a MAPPING —
unpacking one yields its KEYS. `data_str` became the literal string "data",
json.loads raised, and the bare `except: pass` swallowed it. The resolver then
reported "no project owns this package" for every row, and the guard refused
to serve a package it had been told was orphaned.

HOW THESE TESTS REACH POSTGRESQL WITHOUT A POSTGRESQL SERVER
------------------------------------------------------------
The defect is entirely a ROW SHAPE difference. psycopg's dict_row hands back
mappings; sqlite3.Row hands back a row that is both. So the PostgreSQL cases
here run the real resolver against a connection whose rows are plain dicts —
the exact shape psycopg produces (services/db/dialect.connect passes
row_factory=dict_row). That reproduces the production failure deterministically
and in the gate, which a live server dependency never could.

The fixture data is production-shaped: the real Word Search row stores its
files under product_exports.files with a /download/<export_package_id>/... URL
and a package_id that differs from the export package id.
"""
from __future__ import annotations

import itertools

import database
import pytest


#: The live row's real shape. Each test gets its own ids so that two tests
#: cannot both own the same package and make "which project?" ambiguous.
_COUNTER = itertools.count(1)
_CREATED: list[int] = []


def _ids():
    n = next(_COUNTER)
    return (f"cee4f49477b943d08441eb69e2afef{n:02d}",
            f"6c905b99847a48aeb2eddb29c00c9{n:03d}")


def _production_shaped_data(PACKAGE_ID, EXPORT_PACKAGE_ID) -> dict:
    """The shape the live Word Search row actually has."""
    return {
        "package_id": PACKAGE_ID,
        "export_package_id": EXPORT_PACKAGE_ID,
        "product_type": "word_search",
        "title": "Flower Parts",
        "product_exports": {
            "files": {
                "pdf": {
                    "name": "flower_parts.pdf",
                    "url": f"/download/{EXPORT_PACKAGE_ID}/flower_parts.pdf",
                },
                "zip": {
                    "name": "flower_parts.zip",
                    "url": f"/download/{EXPORT_PACKAGE_ID}/package.zip",
                },
            },
            "meta": {"package_id": EXPORT_PACKAGE_ID},
            "pdf_available": True,
        },
    }


@pytest.fixture(autouse=True)
def _project():
    database.init_db()
    _CREATED.clear()
    package_id, export_package_id = _ids()
    project = database.create_project(
        "Flower Parts", "product",
        _production_shaped_data(package_id, export_package_id))
    project["package_id"] = package_id
    project["export_package_id"] = export_package_id
    _CREATED.append(project["id"])
    yield project
    for pid in _CREATED:
        try:
            database.delete_project(pid)
        except Exception:  # noqa: BLE001
            pass
    _CREATED.clear()


# ----------------------------------------------------------- backend shims --


class _DictRowCursor:
    """Rows as psycopg's dict_row returns them: mappings, never sequences."""

    def __init__(self, rows):
        self._rows = [dict(r) for r in rows]

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _DictRowConnection:
    """A connection whose rows are plain dicts, as PostgreSQL's are.

    Each execute opens and closes its own real connection, so this shim can
    never leave a SQLite handle open and lock the shared test database.
    """

    def __init__(self, opener):
        self._opener = opener

    def execute(self, sql, params=()):
        real = self._opener()
        try:
            rows = real.execute(sql, params).fetchall()
        finally:
            real.close()
        return _DictRowCursor(rows)

    def commit(self):
        return None

    def close(self):
        return None


def _as_postgres(monkeypatch):
    """Point database.get_conn at PostgreSQL-shaped rows."""
    real_get_conn = database.get_conn
    monkeypatch.setattr(
        database, "get_conn", lambda: _DictRowConnection(real_get_conn))


@pytest.fixture
def postgres_rows(monkeypatch):
    """Run the resolver against PostgreSQL-shaped rows."""
    _as_postgres(monkeypatch)


# ========================================= the lookup, on each backend =====


def test_package_id_lookup_on_sqlite(_project):
    found = database.find_project_by_package(_project["package_id"])
    assert found is not None
    assert found["id"] == _project["id"]


def test_export_package_id_lookup_on_sqlite(_project):
    found = database.find_project_by_package(_project["export_package_id"])
    assert found is not None
    assert found["id"] == _project["id"]


def test_package_id_lookup_on_postgres_rows(_project, postgres_rows):
    found = database.find_project_by_package(_project["package_id"])
    assert found is not None, "mapping rows must resolve exactly as tuple rows do"
    assert found["id"] == _project["id"]


def test_export_package_id_lookup_on_postgres_rows(_project, postgres_rows):
    """The exact live failure: this returned None and every download 403'd."""
    found = database.find_project_by_package(_project["export_package_id"])
    assert found is not None, (
        "the stored export package id must resolve on PostgreSQL; returning "
        "None here is what made the orphan guard refuse every real download"
    )
    assert found["id"] == _project["id"]


def test_both_backends_agree(_project, monkeypatch):
    sqlite_result = database.find_project_by_package(_project["export_package_id"])
    _as_postgres(monkeypatch)
    postgres_result = database.find_project_by_package(_project["export_package_id"])
    assert sqlite_result["id"] == postgres_result["id"]
    assert sqlite_result["data"] == postgres_result["data"]


# ===================================== the stored customer URL resolves =====


def test_the_real_stored_customer_download_url_resolves(_project):
    """Saved Projects builds its buttons from these URLs."""
    data = _project["data"]
    url = data["product_exports"]["files"]["pdf"]["url"]
    package_from_url = url.split("/download/", 1)[1].split("/", 1)[0]

    found = database.find_project_by_package(package_from_url)
    assert found is not None and found["id"] == _project["id"]


def test_a_url_only_package_still_resolves():
    """A row that records the package ONLY inside its download URL."""
    project = database.create_project(
        "URL only", "product",
        {"product_exports": {"files": {"pdf": {"url": "/download/urlonly123/x.pdf"}}}},
    )
    _CREATED.append(project["id"])
    found = database.find_project_by_package("urlonly123")
    assert found is not None and found["id"] == project["id"]


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_every_recorded_identifier_resolves(_project, monkeypatch, backend):
    if backend == "postgres":
        _as_postgres(monkeypatch)
    for identifier in (_project["package_id"], _project["export_package_id"]):
        found = database.find_project_by_package(identifier)
        assert found is not None, f"{identifier} unresolved on {backend}"


# ================================ the guard itself must NOT be weakened =====


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_a_genuinely_orphaned_package_is_still_refused(_project, monkeypatch, backend):
    """The stale/orphan protection must keep working. Fix the lookup, not it."""
    if backend == "postgres":
        _as_postgres(monkeypatch)
    assert database.find_project_by_package("deadbeefdeadbeefdeadbeefdeadbeef") is None


def test_a_blank_package_never_matches_anything(_project):
    assert database.find_project_by_package("") is None
    assert database.find_project_by_package(None) is None


def test_a_substring_of_a_real_id_is_not_a_match(_project):
    """The SQL LIKE only narrows; the structure decides."""
    assert database.find_project_by_package(_project["export_package_id"][:12]) is None


class _FixedRowsConnection:
    """A connection that returns exactly the rows a test hands it.

    Used so a malformed row can be exercised WITHOUT writing invalid JSON
    into the shared test database. An earlier version of this test did write
    one, database.delete_project could not parse it to remove it, and the bad
    row then broke 29 unrelated tests later in the gate.
    """

    def __init__(self, rows):
        self._rows = rows

    def execute(self, sql, params=()):
        return _DictRowCursor(self._rows)

    def commit(self):
        return None

    def close(self):
        return None


def test_an_unreadable_row_is_reported_not_silently_swallowed(monkeypatch, caplog):
    """The bare `except: pass` is what hid this defect for a whole release.

    A row whose JSON cannot be parsed must be logged and skipped, never
    silently reported as "this package belongs to nobody".
    """
    import logging

    monkeypatch.setattr(database, "get_conn", lambda: _FixedRowsConnection([
        {"id": 999001, "name": "broken", "type": "product", "data": "{not json"},
    ]))

    with caplog.at_level(logging.WARNING, logger="database"):
        found = database.find_project_by_package("anything")

    assert found is None, "an unparseable row cannot claim ownership"
    assert any("unreadable" in r.getMessage().lower() for r in caplog.records), (
        "an unparseable row must be reported, not swallowed"
    )


def test_one_unreadable_row_does_not_hide_a_good_one(monkeypatch):
    """A single bad row must not cost the customer a working download."""
    monkeypatch.setattr(database, "get_conn", lambda: _FixedRowsConnection([
        {"id": 999001, "name": "broken", "type": "product", "data": "{not json"},
        {"id": 999002, "name": "good", "type": "product",
         "data": '{"export_package_id": "goodpkg0001"}'},
    ]))

    found = database.find_project_by_package("goodpkg0001")
    assert found is not None and found["id"] == 999002


# ================================= both call sites use the one resolver =====


def test_the_download_pipeline_agent_uses_the_canonical_resolver(_project):
    from services.quality.download_pipeline_agent import _load_project_by_package_id

    found = _load_project_by_package_id(_project["export_package_id"])
    assert found is not None and found["id"] == _project["id"]


def test_the_final_output_gate_uses_the_canonical_resolver(_project):
    from services.quality.final_output_gate import _load_project_by_package_id

    found = _load_project_by_package_id(_project["export_package_id"])
    assert found is not None and found["id"] == _project["id"]


@pytest.mark.parametrize("backend", ["sqlite", "postgres"])
def test_both_call_sites_work_on_both_backends(_project, monkeypatch, backend):
    if backend == "postgres":
        _as_postgres(monkeypatch)
    from services.quality.download_pipeline_agent import (
        _load_project_by_package_id as agent_lookup,
    )
    from services.quality.final_output_gate import (
        _load_project_by_package_id as gate_lookup,
    )

    assert agent_lookup(_project["export_package_id"]) is not None
    assert gate_lookup(_project["export_package_id"]) is not None


def test_no_resolver_reads_a_row_positionally():
    """Grep the source: positional unpacking is what broke production."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    offenders = []
    for path in (root / "services" / "quality").rglob("*.py"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if re.search(r"for\s+\w+,\s*\w+,\s*\w+,\s*\w+\s+in\s+rows", line):
                offenders.append(f"{path.name}: {line.strip()}")
    assert not offenders, (
        "these unpack database rows positionally, which yields dict KEYS on "
        f"PostgreSQL: {offenders}"
    )


# ============================ the real route, on both backends, end to end ==


class TestTheDownloadRouteServesOnBothBackends:
    """The customer's own URL must return 200, not 403, on either backend.

    This is the live symptom end to end: a real PDF and ZIP on disk, a
    production-shaped project row that records them, and the stored URL
    fetched through the actual Flask route.
    """

    @staticmethod
    def _package(tmp_path_factory, pkg):
        """A real, valid PDF and ZIP under a real export package folder."""
        import zipfile
        from io import BytesIO

        from reportlab.pdfgen import canvas

        from tests._test_paths import resolve_test_exports_root

        folder = resolve_test_exports_root() / pkg
        folder.mkdir(parents=True, exist_ok=True)

        buffer = BytesIO()
        document = canvas.Canvas(buffer)
        document.setTitle("Flower Parts")
        document.drawString(72, 720, "Flower Parts word search fixture")
        document.showPage()
        document.save()
        (folder / "flower_parts.pdf").write_bytes(buffer.getvalue())

        with zipfile.ZipFile(folder / "package.zip", "w") as zf:
            zf.writestr("flower_parts.pdf", buffer.getvalue())
        return folder

    def _row(self, pkg):
        data = _production_shaped_data(f"artifact-{pkg}", pkg)
        data["filename"] = "flower_parts.pdf"
        data["is_pdf"] = True
        project = database.create_project("Flower Parts", "product", data)
        _CREATED.append(project["id"])
        return project

    @pytest.mark.parametrize("backend", ["sqlite", "postgres"])
    def test_the_stored_pdf_url_returns_200(self, tmp_path_factory, monkeypatch, backend):
        from app import app as flask_app

        pkg = f"pkgpdf{backend}0001"
        self._package(tmp_path_factory, pkg)
        project = self._row(pkg)
        url = project["data"]["product_exports"]["files"]["pdf"]["url"]

        if backend == "postgres":
            _as_postgres(monkeypatch)

        response = flask_app.test_client().get(url)
        assert response.status_code == 200, (
            f"{backend}: the stored customer URL was refused: {response.get_data()[:200]!r}"
        )
        assert response.data[:4] == b"%PDF"

    @pytest.mark.parametrize("backend", ["sqlite", "postgres"])
    def test_the_stored_zip_url_returns_200(self, tmp_path_factory, monkeypatch, backend):
        from app import app as flask_app

        pkg = f"pkgzip{backend}0001"
        self._package(tmp_path_factory, pkg)
        project = self._row(pkg)
        url = project["data"]["product_exports"]["files"]["zip"]["url"]

        if backend == "postgres":
            _as_postgres(monkeypatch)

        response = flask_app.test_client().get(url)
        assert response.status_code == 200, (
            f"{backend}: the stored ZIP URL was refused: {response.get_data()[:200]!r}"
        )
        assert response.data[:2] == b"PK"

    def test_a_truly_orphaned_package_is_still_refused_by_the_route(self, tmp_path_factory):
        """The guard must still block. Fix the lookup, never the guard."""
        from app import app as flask_app

        pkg = "orphanpkg00000001"
        self._package(tmp_path_factory, pkg)   # files on disk, but NO project row

        response = flask_app.test_client().get(f"/download/{pkg}/flower_parts.pdf")
        assert response.status_code == 403
        assert b"stale_or_orphan_export_package" in response.data
