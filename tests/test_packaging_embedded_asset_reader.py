"""Phase 0B-3B2B — packaging reads embedded PDFs through the storage layer.

services/packaging.py is the real consumer of the embedded `pdf_bytes`
blob, so it is where the storage cutover has to happen for a customer read
to actually come from shared storage.

The contract these tests hold:

    VERIFIED stored asset  -> use those bytes
    anything else at all   -> the legacy pdf_bytes, exactly as before

"Anything else" means every one of: no asset record, an unverified
(unapproved) asset, a missing object, a wrong byte count, a wrong
checksum, storage misconfigured, storage unreachable. No customer may
lose access to a product because the new copy is missing or broken.

Nothing here migrates an artifact, removes a `pdf_bytes`, or touches the
real database.
"""
from __future__ import annotations

import base64
import io
import os

import pytest

import database
from services.packaging import _verified_embedded_pdf, build_product_export
from services.storage import get_storage, reset_storage, sha256_hex
from services.storage.base import StorageError, StorageStat
from services.storage.keys import KIND_PDF, embedded_key


def _real_pdf(marker: str = "legacy") -> bytes:
    """A genuinely parseable PDF; packaging validates the %PDF header."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle(f"0B-3B2B {marker}")
    for page in range(2):
        pdf.drawString(72, 720, f"{marker} page {page + 1}")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


LEGACY_PDF = _real_pdf("legacy")
ASSET_PDF = _real_pdf("migrated-to-object-storage")


@pytest.fixture
def factory(tmp_path, monkeypatch):
    """Storage isolation on top of the suite's existing DB/exports isolation.

    tests/conftest.py already points FACTORY_DB_PATH and FACTORY_EXPORTS_DIR at
    temporary locations for the whole session, and the service modules bind
    their EXPORTS_DIR at import time -- so this fixture deliberately does NOT
    redirect those. It only gives each test its own object-storage root.
    """
    monkeypatch.setenv("FACTORY_STORAGE_DIR", str(tmp_path / "assets"))
    monkeypatch.delenv("FACTORY_STORAGE_DRIVER", raising=False)
    reset_storage()
    database.init_db()
    yield tmp_path
    reset_storage()


def _planner_project(pdf: bytes = LEGACY_PDF) -> dict:
    """A faith_planner whose export path reads the embedded PDF."""
    data = {
        "product_type": "faith_planner",
        "is_pdf": True,
        "title": "Family Faith Planner",
        "pdf_bytes": base64.b64encode(pdf).decode("ascii"),
        "fields": {},
    }
    created = database.create_project("Family Faith Planner", "product", data)
    return {"id": created["id"], "name": created["name"], "data": data}


def _record_verified_asset(project_id: int, payload: bytes, *, approved=True) -> str:
    key = embedded_key(project_id, "pdf_bytes", KIND_PDF)
    get_storage().put(key, payload, content_type="application/pdf")
    database.record_asset(
        project_id, KIND_PDF, key,
        content_type="application/pdf",
        byte_size=len(payload),
        checksum=sha256_hex(payload),
        approved=approved,
    )
    return key


def _exported_pdf(result: dict, tmp_path=None) -> bytes:
    """The PDF packaging actually wrote for the customer, read back.

    Located through packaging's own EXPORTS_DIR, which the module binds at
    import time, rather than through the environment variable.
    """
    from pathlib import Path

    from services.packaging import EXPORTS_DIR

    exports = Path(EXPORTS_DIR) / result["package_id"]
    pdfs = sorted(p for p in exports.glob("*.pdf"))
    assert pdfs, f"packaging wrote no PDF into {exports}"
    return pdfs[0].read_bytes()


def _exported_pdf_sha(result: dict) -> str:
    """The SHA-256 packaging itself recorded for the customer's PDF."""
    return (result["exports"]["files"]["pdf"] or {})["sha256"]


# ======================================== the helper's contract, in isolation ===


def test_helper_returns_none_when_no_asset_exists(factory):
    """A project nothing has migrated keeps using its legacy blob.

    Deliberately asserts on THIS project rather than on the global
    "are there any assets at all" probe: the suite shares one database,
    so another test's asset must not change this project's answer.
    """
    project = _planner_project()
    assert database.list_assets(project["id"]) == []
    assert _verified_embedded_pdf(project, project["data"]) is None


def test_helper_returns_asset_bytes_when_verified(factory):
    project = _planner_project()
    _record_verified_asset(project["id"], ASSET_PDF)
    assert _verified_embedded_pdf(project, project["data"]) == ASSET_PDF


def test_helper_returns_none_for_an_unverified_asset(factory):
    """An unapproved row means the migration never finished its readback.

    The object may hash correctly right now, but "verified" is a distinct
    step the executor performs last. Until it is marked, the legacy blob
    stays authoritative.
    """
    project = _planner_project()
    _record_verified_asset(project["id"], ASSET_PDF, approved=False)
    assert _verified_embedded_pdf(project, project["data"]) is None


def test_packaging_falls_back_for_an_unverified_asset(factory):
    project = _planner_project()
    _record_verified_asset(project["id"], ASSET_PDF, approved=False)
    result = build_product_export(project)
    assert _exported_pdf(result) == LEGACY_PDF


def test_helper_returns_none_when_the_object_is_missing(factory):
    project = _planner_project()
    key = embedded_key(project["id"], "pdf_bytes", KIND_PDF)
    database.record_asset(
        project["id"], KIND_PDF, key,
        byte_size=len(ASSET_PDF), checksum=sha256_hex(ASSET_PDF), approved=True,
    )
    assert _verified_embedded_pdf(project, project["data"]) is None


def test_helper_returns_none_on_checksum_mismatch(factory):
    project = _planner_project()
    key = embedded_key(project["id"], "pdf_bytes", KIND_PDF)
    get_storage().put(key, b"corrupted-payload")
    database.record_asset(
        project["id"], KIND_PDF, key,
        byte_size=len(ASSET_PDF), checksum=sha256_hex(ASSET_PDF), approved=True,
    )
    assert _verified_embedded_pdf(project, project["data"]) is None


def test_helper_returns_none_on_byte_count_mismatch(factory):
    project = _planner_project()
    key = _record_verified_asset(project["id"], ASSET_PDF)
    database.record_asset(
        project["id"], KIND_PDF, key,
        byte_size=len(ASSET_PDF) + 500, checksum=sha256_hex(ASSET_PDF), approved=True,
    )
    assert _verified_embedded_pdf(project, project["data"]) is None


def test_helper_returns_none_when_storage_is_unreachable(factory, monkeypatch):
    project = _planner_project()
    _record_verified_asset(project["id"], ASSET_PDF)

    class DeadStorage:
        def stat(self, key):
            raise StorageError("simulated outage")

        def get(self, key):
            raise StorageError("simulated outage")

    monkeypatch.setattr("services.storage.compat.get_storage", lambda: DeadStorage())
    assert _verified_embedded_pdf(project, project["data"]) is None


def test_helper_never_raises_on_a_broken_project(factory):
    for bad in ({}, {"id": 0}, {"id": -1}, {"id": None}):
        assert _verified_embedded_pdf(bad, {"pdf_bytes": "x"}) is None


# ============================ the REAL packaging path, end to end =============


def test_packaging_uses_the_legacy_blob_when_nothing_is_migrated(factory, tmp_path):
    project = _planner_project()
    result = build_product_export(project)
    assert _exported_pdf(result, tmp_path) == LEGACY_PDF


def test_packaging_prefers_a_verified_asset(factory, tmp_path):
    """The whole point of 0B-3B2B: a customer read comes from storage."""
    project = _planner_project()
    _record_verified_asset(project["id"], ASSET_PDF)

    result = build_product_export(project)
    exported = _exported_pdf(result, tmp_path)
    assert exported == ASSET_PDF, "packaging must serve the migrated bytes"
    assert exported != LEGACY_PDF


def test_packaging_falls_back_when_storage_is_unavailable(factory, tmp_path, monkeypatch):
    project = _planner_project()
    _record_verified_asset(project["id"], ASSET_PDF)

    class DeadStorage:
        def stat(self, key):
            raise StorageError("R2 is down")

        def get(self, key):
            raise StorageError("R2 is down")

    monkeypatch.setattr("services.storage.compat.get_storage", lambda: DeadStorage())
    result = build_product_export(project)
    assert _exported_pdf(result, tmp_path) == LEGACY_PDF, (
        "an outage must degrade to the legacy blob, never to a failed export"
    )


def test_packaging_falls_back_when_the_asset_is_corrupt(factory, tmp_path):
    project = _planner_project()
    key = embedded_key(project["id"], "pdf_bytes", KIND_PDF)
    get_storage().put(key, b"not-a-pdf-at-all")
    database.record_asset(
        project["id"], KIND_PDF, key,
        byte_size=len(ASSET_PDF), checksum=sha256_hex(ASSET_PDF), approved=True,
    )
    result = build_product_export(project)
    assert _exported_pdf(result, tmp_path) == LEGACY_PDF


def test_packaging_falls_back_when_the_object_is_missing(factory, tmp_path):
    project = _planner_project()
    key = embedded_key(project["id"], "pdf_bytes", KIND_PDF)
    database.record_asset(
        project["id"], KIND_PDF, key,
        byte_size=len(ASSET_PDF), checksum=sha256_hex(ASSET_PDF), approved=True,
    )
    result = build_product_export(project)
    assert _exported_pdf(result, tmp_path) == LEGACY_PDF


def test_a_broken_asset_can_never_cost_a_customer_their_product(factory, tmp_path):
    """The single most important guarantee of the whole cutover."""
    project = _planner_project()
    key = embedded_key(project["id"], "pdf_bytes", KIND_PDF)
    get_storage().put(key, b"")
    database.record_asset(
        project["id"], KIND_PDF, key,
        byte_size=999_999, checksum="deadbeef", approved=True,
    )
    result = build_product_export(project)
    assert _exported_pdf(result, tmp_path) == LEGACY_PDF
    assert result["package_id"], "the export still completes"


def test_packaging_never_removes_the_legacy_pdf_bytes(factory, tmp_path):
    project = _planner_project()
    _record_verified_asset(project["id"], ASSET_PDF)
    before = database.get_project(project["id"])["data"]["pdf_bytes"]

    build_product_export(project)

    after = database.get_project(project["id"])["data"]["pdf_bytes"]
    assert after == before
    assert base64.b64decode(after) == LEGACY_PDF


def test_packaging_does_not_change_lifecycle_state_or_row_version(factory, tmp_path):
    project = _planner_project()
    _record_verified_asset(project["id"], ASSET_PDF)
    before = database.get_project(project["id"])

    build_product_export(project)

    after = database.get_project(project["id"])
    assert after["data"].get("artifact_state") == before["data"].get("artifact_state")
    assert after["data"]["_row_version"] == before["data"]["_row_version"]


def test_export_layout_is_identical_with_and_without_an_asset(factory, tmp_path):
    """Only the PDF's source changes -- never the shape of the package."""
    legacy_project = _planner_project()
    legacy_result = build_product_export(legacy_project)
    legacy_names = sorted(
        (legacy_result["exports"].get("files") or {}).keys()
    )

    asset_project = _planner_project()
    _record_verified_asset(asset_project["id"], ASSET_PDF)
    asset_result = build_product_export(asset_project)
    asset_names = sorted((asset_result["exports"].get("files") or {}).keys())

    assert legacy_names == asset_names
