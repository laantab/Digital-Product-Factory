"""Phase 0B-3B1 — R2 driver, reader-first cutover, migration executor.

Proves requirements A-Z for the phase. The theme running through all of
them: a customer must never be worse off. A broken, missing, corrupt or
unreachable new asset always falls back to the legacy copy, and no code
path here can damage a source artifact.

Nothing in this file talks to Cloudflare, uploads a customer artifact, or
migrates anything. The R2 driver is exercised through an in-memory fake
S3 client that behaves the way boto3's does.
"""
from __future__ import annotations

import base64
import json
import os
import sqlite3
from pathlib import Path

import pytest

import database
from services.storage import get_storage, reset_storage, sha256_hex
from services.storage.base import StorageError, StorageKeyNotFound
from services.storage.compat import (
    export_asset_is_available,
    read_asset_or_legacy,
    read_export_or_legacy,
    verified_asset_bytes,
)
from services.storage.executor import (
    MigrationDisabled,
    STEP_COPY,
    STEP_DONE,
    STEP_MARK_VERIFIED,
    STEP_RECORD,
    STEP_VERIFY_CHECKSUM,
    STEP_VERIFY_READBACK,
    STEP_VERIFY_SIZE,
    migrate_artifact,
)
from services.storage.keys import (
    InvalidStorageKey,
    KIND_PDF,
    embedded_key,
    export_key_to_relpath,
    export_object_key,
)
from services.storage.r2 import (
    CHECKSUM_META_KEY,
    R2ConfigurationError,
    R2Driver,
    r2_endpoint,
)

PDF = b"%PDF-1.7\nphase 0B-3B1 customer artifact\n%%EOF\n"
PDF_B64 = base64.b64encode(PDF).decode()


def _real_pdf_bytes() -> bytes:
    """A genuinely parseable PDF.

    The download route runs every file through the Download Pipeline
    Agent, which refuses to serve a PDF it cannot read -- correctly. A
    route test therefore needs a real document, not a byte string that
    merely starts with %PDF.
    """
    import io

    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    pdf.setTitle("Phase 0B-3B1 Route Test")
    for page in range(3):
        pdf.drawString(72, 720, f"Customer artifact page {page + 1}")
        pdf.drawString(72, 700, "This document exists to exercise the download route.")
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()

R2_ENV = (
    "FACTORY_R2_ACCOUNT_ID",
    "FACTORY_R2_BUCKET",
    "FACTORY_R2_ACCESS_KEY_ID",
    "FACTORY_R2_SECRET_ACCESS_KEY",
    "FACTORY_R2_ENDPOINT",
    "FACTORY_R2_REGION",
)


# ================================================================ fixtures ===


@pytest.fixture
def factory(tmp_path, monkeypatch):
    """An isolated Factory: own database, own exports, own storage root.

    Every path lives under pytest's tmp_path and is published through
    FACTORY_DB_PATH / FACTORY_EXPORTS_DIR / FACTORY_STORAGE_DIR before
    anything else runs, so no test here can reach the real projects.db or
    the real exports folder.
    """
    monkeypatch.setenv("FACTORY_DB_PATH", str(tmp_path / "projects.db"))
    monkeypatch.setenv("FACTORY_EXPORTS_DIR", str(tmp_path / "exports"))
    monkeypatch.setenv("FACTORY_STORAGE_DIR", str(tmp_path / "assets"))
    db = Path(os.environ["FACTORY_DB_PATH"])
    exports = Path(os.environ["FACTORY_EXPORTS_DIR"])
    exports.mkdir()
    monkeypatch.setattr(database, "DB_PATH", str(db))
    for var in R2_ENV:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("FACTORY_STORAGE_DRIVER", raising=False)
    reset_storage()
    database.init_db()
    yield {"db": db, "exports": exports, "root": tmp_path}
    reset_storage()


class FakeS3:
    """In-memory stand-in for boto3's S3 client, including its error shape."""

    class ClientError(Exception):
        def __init__(self, code="404"):
            super().__init__(f"An error occurred ({code})")
            self.response = {"Error": {"Code": code}}

    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.calls: list[str] = []
        self.fail_put = False
        self.fail_get = False
        self.corrupt_on_read = False

    def put_object(self, *, Bucket, Key, Body, ContentType, Metadata):
        self.calls.append(f"put:{Key}")
        if self.fail_put:
            raise RuntimeError("simulated R2 upload failure")
        self.objects[Key] = {
            "body": bytes(Body),
            "content_type": ContentType,
            "metadata": dict(Metadata),
        }

    def get_object(self, *, Bucket, Key):
        self.calls.append(f"get:{Key}")
        if self.fail_get:
            raise RuntimeError("simulated R2 outage")
        if Key not in self.objects:
            raise self.ClientError("NoSuchKey")
        body = self.objects[Key]["body"]
        if self.corrupt_on_read:
            body = b"corrupted-in-flight" + body[:4]

        class _Body:
            def __init__(self, raw):
                self._raw = raw

            def read(self):
                return self._raw

        return {"Body": _Body(body)}

    def head_object(self, *, Bucket, Key):
        self.calls.append(f"head:{Key}")
        if Key not in self.objects:
            raise self.ClientError("404")
        obj = self.objects[Key]
        return {
            "ContentLength": len(obj["body"]),
            "ContentType": obj["content_type"],
            "Metadata": obj["metadata"],
        }

    def delete_object(self, *, Bucket, Key):
        self.calls.append(f"delete:{Key}")
        self.objects.pop(Key, None)


@pytest.fixture
def r2():
    client = FakeS3()
    driver = R2Driver(bucket="factory-private", client=client, region="auto")
    return driver, client


def _make_project(name="Customer Product", data=None, ptype="product"):
    return database.create_project(name, ptype, data or {})


# ======================================= A. R2 driver contract (put/get/…) ===


def test_a_r2_driver_round_trips_put_get_exists_stat_delete(r2):
    driver, client = r2
    key = "projects/1/embedded/pdf_bytes.pdf"

    stat = driver.put(key, PDF, content_type="application/pdf")
    assert stat.size == len(PDF)
    assert stat.checksum == sha256_hex(PDF)
    assert stat.content_type == "application/pdf"

    assert driver.exists(key) is True
    assert driver.get(key) == PDF
    assert driver.stat(key).size == len(PDF)
    assert client.objects[key]["metadata"][CHECKSUM_META_KEY] == sha256_hex(PDF)

    assert driver.delete(key) is True
    assert driver.exists(key) is False
    assert driver.delete(key) is False, "deleting an absent key reports False"


def test_a_r2_missing_key_raises_not_found_and_stats_none(r2):
    driver, _ = r2
    assert driver.stat("projects/9/embedded/pdf_bytes.pdf") is None
    with pytest.raises(StorageKeyNotFound):
        driver.get("projects/9/embedded/pdf_bytes.pdf")


def test_a_r2_rejects_escaping_keys(r2):
    driver, _ = r2
    for bad in ("../outside.pdf", "/etc/passwd", "projects/../../x.pdf", "", "a//b"):
        with pytest.raises(StorageError):
            driver.put(bad, PDF)


def test_a_r2_verify_confirms_checksum_and_size(r2):
    driver, _ = r2
    key = "projects/3/embedded/pdf_bytes.pdf"
    driver.put(key, PDF)
    assert driver.verify(key, expected_checksum=sha256_hex(PDF), expected_size=len(PDF))
    assert not driver.verify(key, expected_checksum="deadbeef", expected_size=len(PDF))
    assert not driver.verify(key, expected_checksum=sha256_hex(PDF), expected_size=1)


# =============================================== B. endpoint + auto region ===


def test_b_endpoint_is_derived_from_the_account_id():
    assert r2_endpoint("abc123") == "https://abc123.r2.cloudflarestorage.com"


def test_b_region_defaults_to_auto_and_endpoint_comes_from_account(monkeypatch):
    for var in R2_ENV:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("FACTORY_R2_ACCOUNT_ID", "acct42")
    monkeypatch.setenv("FACTORY_R2_BUCKET", "factory-private")
    monkeypatch.setenv("FACTORY_R2_ACCESS_KEY_ID", "AKIAEXAMPLE")
    monkeypatch.setenv("FACTORY_R2_SECRET_ACCESS_KEY", "s3cr3t-value-abcdef")

    captured = {}

    class _Boto:
        @staticmethod
        def client(service, **kwargs):
            captured.update(kwargs)
            captured["service"] = service
            return FakeS3()

    import sys
    import types

    monkeypatch.setitem(sys.modules, "boto3", _Boto)
    cfg_mod = types.ModuleType("botocore.config")
    cfg_mod.Config = lambda **kw: kw
    monkeypatch.setitem(sys.modules, "botocore.config", cfg_mod)
    monkeypatch.setitem(sys.modules, "botocore", types.ModuleType("botocore"))

    driver = R2Driver()
    assert driver.endpoint_url == "https://acct42.r2.cloudflarestorage.com"
    assert driver.region == "auto"
    assert captured["region_name"] == "auto"
    assert captured["endpoint_url"] == "https://acct42.r2.cloudflarestorage.com"
    assert captured["service"] == "s3"


def test_b_explicit_endpoint_overrides_the_derived_one():
    driver = R2Driver(
        bucket="b", client=FakeS3(), endpoint_url="https://custom.example.com"
    )
    assert driver.endpoint_url == "https://custom.example.com"


# ================================================= C. missing creds fail closed ===


@pytest.mark.parametrize(
    "present",
    [
        {},
        {"FACTORY_R2_BUCKET": "b"},
        {"FACTORY_R2_BUCKET": "b", "FACTORY_R2_ACCESS_KEY_ID": "k"},
        {"FACTORY_R2_ACCOUNT_ID": "a", "FACTORY_R2_ACCESS_KEY_ID": "k"},
    ],
)
def test_c_incomplete_configuration_fails_closed(monkeypatch, present):
    for var in R2_ENV:
        monkeypatch.delenv(var, raising=False)
    for key, value in present.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(R2ConfigurationError):
        R2Driver()


def test_c_selecting_r2_without_configuration_raises_rather_than_falling_back(
    factory, monkeypatch
):
    monkeypatch.setenv("FACTORY_STORAGE_DRIVER", "r2")
    reset_storage()
    with pytest.raises(StorageError):
        get_storage()


def test_c_a_malformed_account_id_is_rejected():
    with pytest.raises(R2ConfigurationError):
        r2_endpoint("bad account/id")
    with pytest.raises(R2ConfigurationError):
        r2_endpoint("")


# ================================================ D. no credential in output ===


def test_d_no_credential_appears_in_configuration_errors(monkeypatch):
    for var in R2_ENV:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("FACTORY_R2_ACCESS_KEY_ID", "AKIA-SUPER-SECRET-ID")
    monkeypatch.setenv("FACTORY_R2_SECRET_ACCESS_KEY", "totally-secret-value")
    with pytest.raises(R2ConfigurationError) as exc:
        R2Driver()
    message = str(exc.value)
    assert "AKIA-SUPER-SECRET-ID" not in message
    assert "totally-secret-value" not in message
    assert "FACTORY_R2_BUCKET" in message, "names are fine, values are not"


def test_d_a_backend_error_message_redacts_the_secret(monkeypatch):
    monkeypatch.setenv("FACTORY_R2_SECRET_ACCESS_KEY", "totally-secret-value")
    monkeypatch.setenv("FACTORY_R2_ACCESS_KEY_ID", "AKIA-SUPER-SECRET-ID")
    client = FakeS3()
    driver = R2Driver(bucket="b", client=client)

    def _boom(**kwargs):
        raise RuntimeError("auth failed for totally-secret-value / AKIA-SUPER-SECRET-ID")

    client.put_object = _boom
    with pytest.raises(StorageError) as exc:
        driver.put("projects/1/embedded/pdf_bytes.pdf", PDF)
    assert "totally-secret-value" not in str(exc.value)
    assert "AKIA-SUPER-SECRET-ID" not in str(exc.value)
    assert "redacted" in str(exc.value)


def test_d_credentials_are_never_written_into_the_repo():
    root = Path(__file__).resolve().parents[1]
    source = (root / "services" / "storage" / "r2.py").read_text(encoding="utf-8")
    # Names of variables are expected; a literal key is not.
    assert "FACTORY_R2_SECRET_ACCESS_KEY" in source
    for leaked in ("AKIA", "aws_secret_access_key=\"", "aws_secret_access_key='"):
        assert leaked not in source


# ========================================= E-I. reader prefers verified asset ===


def test_e_reader_prefers_a_verified_asset_over_the_legacy_blob(factory):
    project = _make_project(data={"pdf_bytes": base64.b64encode(b"OLD-LEGACY").decode()})
    pid = project["id"]
    new_bytes = b"%PDF-new-migrated-copy"
    key = embedded_key(pid, "pdf_bytes", KIND_PDF)

    get_storage().put(key, new_bytes, content_type="application/pdf")
    database.record_asset(
        pid, KIND_PDF, key,
        content_type="application/pdf",
        byte_size=len(new_bytes),
        checksum=sha256_hex(new_bytes),
        approved=True,
    )

    served = read_asset_or_legacy(pid, {"pdf_bytes": base64.b64encode(b"OLD-LEGACY").decode()})
    assert served == new_bytes


def test_f_reader_falls_back_when_no_asset_exists(factory):
    project = _make_project(data={"pdf_bytes": PDF_B64})
    assert read_asset_or_legacy(project["id"], {"pdf_bytes": PDF_B64}) == PDF


def test_g_reader_falls_back_when_storage_is_unavailable(factory, monkeypatch):
    project = _make_project(data={"pdf_bytes": PDF_B64})
    pid = project["id"]
    key = embedded_key(pid, "pdf_bytes", KIND_PDF)
    get_storage().put(key, b"stored-copy")
    database.record_asset(
        pid, KIND_PDF, key, byte_size=len(b"stored-copy"),
        checksum=sha256_hex(b"stored-copy"), approved=True,
    )

    class DeadStorage:
        def stat(self, key):
            raise StorageError("R2 is down")

        def get(self, key):
            raise StorageError("R2 is down")

    monkeypatch.setattr("services.storage.compat.get_storage", lambda: DeadStorage())
    assert read_asset_or_legacy(pid, {"pdf_bytes": PDF_B64}) == PDF, (
        "an outage must degrade to the legacy copy, not to an error"
    )


def test_h_reader_falls_back_when_the_asset_is_corrupt(factory):
    project = _make_project(data={"pdf_bytes": PDF_B64})
    pid = project["id"]
    key = embedded_key(pid, "pdf_bytes", KIND_PDF)

    # Record the checksum of the GOOD bytes, then store different bytes.
    get_storage().put(key, b"corrupted-payload-entirely")
    database.record_asset(
        pid, KIND_PDF, key, byte_size=len(PDF), checksum=sha256_hex(PDF), approved=True,
    )
    assert read_asset_or_legacy(pid, {"pdf_bytes": PDF_B64}) == PDF


def test_h_reader_falls_back_when_the_asset_is_the_wrong_size(factory):
    project = _make_project(data={"pdf_bytes": PDF_B64})
    pid = project["id"]
    key = embedded_key(pid, "pdf_bytes", KIND_PDF)
    get_storage().put(key, PDF)
    database.record_asset(
        pid, KIND_PDF, key, byte_size=len(PDF) + 999,
        checksum=sha256_hex(PDF), approved=True,
    )
    assert read_asset_or_legacy(pid, {"pdf_bytes": PDF_B64}) == PDF


def test_h_reader_falls_back_when_the_object_is_missing_entirely(factory):
    project = _make_project(data={"pdf_bytes": PDF_B64})
    pid = project["id"]
    key = embedded_key(pid, "pdf_bytes", KIND_PDF)
    # An asset row with no object behind it.
    database.record_asset(
        pid, KIND_PDF, key, byte_size=len(PDF), checksum=sha256_hex(PDF), approved=True,
    )
    assert read_asset_or_legacy(pid, {"pdf_bytes": PDF_B64}) == PDF


def test_h_an_asset_row_that_cannot_prove_itself_is_unusable(factory):
    project = _make_project(data={"pdf_bytes": PDF_B64})
    pid = project["id"]
    key = embedded_key(pid, "pdf_bytes", KIND_PDF)
    get_storage().put(key, b"whatever")
    database.record_asset(pid, KIND_PDF, key, byte_size=0, checksum="", approved=True)
    assert verified_asset_bytes(key) is None
    assert read_asset_or_legacy(pid, {"pdf_bytes": PDF_B64}) == PDF


def test_i_a_broken_asset_never_hides_a_valid_legacy_export_file(factory):
    exports = factory["exports"]
    (exports / "pkgdir").mkdir()
    disk = exports / "pkgdir" / "product.pdf"
    disk.write_bytes(PDF)

    project = _make_project(data={"pdf_path": str(disk)})
    pid = project["id"]
    key = export_object_key(pid, "pkgdir/product.pdf")
    get_storage().put(key, b"garbage")
    database.record_asset(
        pid, "pdf", key, byte_size=len(PDF), checksum=sha256_hex(PDF), approved=True,
    )

    assert read_export_or_legacy(pid, "pkgdir/product.pdf", disk) == PDF
    assert disk.read_bytes() == PDF, "the legacy file is untouched"


# ================================================ J-K. Saved Projects ========


def test_j_saved_projects_still_sees_a_legacy_disk_product(factory):
    exports = factory["exports"]
    (exports / "legacydir").mkdir()
    pdf = exports / "legacydir" / "book.pdf"
    pdf.write_bytes(PDF)

    project = _make_project(data={"pdf_path": str(pdf)})
    found = database._existing_customer_output_files(
        {"id": project["id"], "data": {"pdf_path": str(pdf)}}
    )
    assert [p.name for p in found] == ["book.pdf"]


def test_j_with_zero_assets_saved_projects_behaviour_is_unchanged(factory):
    exports = factory["exports"]
    (exports / "d1").mkdir()
    (exports / "d1" / "a.pdf").write_bytes(PDF)
    data = {"pdf_path": str(exports / "d1" / "a.pdf")}
    project = _make_project(data=data)

    assert database.list_assets_exist() is False
    found = database._existing_customer_output_files({"id": project["id"], "data": data})
    assert len(found) == 1


def test_k_saved_projects_recognizes_an_asset_backed_product(factory):
    """A migrated product with no disk copy must stay visible."""
    project = _make_project(data={})
    pid = project["id"]
    rel = "migrated-pkg/book.pdf"
    key = export_object_key(pid, rel)

    get_storage().put(key, PDF, content_type="application/pdf")
    database.record_asset(
        pid, "pdf", key, content_type="application/pdf",
        byte_size=len(PDF), checksum=sha256_hex(PDF), approved=True,
    )

    assert export_asset_is_available(pid, rel) is True
    found = database._existing_customer_output_files({"id": pid, "data": {}})
    assert [p.name for p in found] == ["book.pdf"]


def test_k_an_unverified_asset_does_not_make_a_product_look_available(factory):
    project = _make_project(data={})
    pid = project["id"]
    rel = "migrated-pkg/book.pdf"
    key = export_object_key(pid, rel)
    # Recorded but never stored, and not approved.
    database.record_asset(
        pid, "pdf", key, byte_size=len(PDF), checksum=sha256_hex(PDF), approved=False,
    )
    assert database._existing_customer_output_files({"id": pid, "data": {}}) == []


# ============================================== L. delivery routes compatible ===


def test_l_download_route_still_serves_legacy_files_unchanged(factory, monkeypatch):
    import app as app_module

    real_pdf = _real_pdf_bytes()
    exports = factory["exports"]
    package = "routedir"
    (exports / package).mkdir()
    (exports / package / "ebook.pdf").write_bytes(real_pdf)
    monkeypatch.setattr(app_module, "EXPORTS_DIR", str(exports))

    # The Download Pipeline Agent refuses to serve an export that is not
    # linked to a saved project -- correct behaviour, so the fixture has to
    # be a properly linked product rather than a loose file.
    _make_project(
        name="Route Test Ebook",
        ptype="product",
        data={"package_id": package, "product_type": "ebook", "pdf_available": True},
    )

    client = app_module.app.test_client()
    response = client.get(f"/download/{package}/ebook.pdf")
    assert response.status_code == 200, response.data[:300]
    assert response.data == real_pdf, "byte-for-byte the legacy file"


def test_l_download_route_returns_not_found_when_nothing_exists(factory, monkeypatch):
    import app as app_module

    monkeypatch.setattr(app_module, "EXPORTS_DIR", str(factory["exports"]))
    client = app_module.app.test_client()
    assert client.get("/download/nosuchdir/ebook.pdf").status_code == 404


def test_l_verified_export_asset_helper_is_a_noop_with_zero_assets(factory):
    import app as app_module

    assert database.list_assets_exist() is False
    assert app_module._verified_export_asset("anydir", "ebook.pdf") is None


def test_l_the_owning_project_comes_from_the_asset_record_not_package_id(factory):
    """A download URL names the directory; the asset record names the owner."""
    import app as app_module

    project = _make_project(data={"package_id": "totally-different-id"})
    pid = project["id"]
    rel = "realdir/ebook.pdf"
    key = export_object_key(pid, rel)
    get_storage().put(key, PDF, content_type="application/pdf")
    database.record_asset(
        pid, "pdf", key, content_type="application/pdf",
        byte_size=len(PDF), checksum=sha256_hex(PDF), approved=True,
    )

    found = database.find_asset_by_export_path("realdir", "ebook.pdf")
    assert found is not None and found["project_id"] == pid
    assert app_module._verified_export_asset("realdir", "ebook.pdf") == PDF


def test_l_an_unapproved_export_asset_is_not_served(factory):
    import app as app_module

    project = _make_project(data={})
    pid = project["id"]
    key = export_object_key(pid, "d/ebook.pdf")
    get_storage().put(key, PDF)
    database.record_asset(
        pid, "pdf", key, byte_size=len(PDF), checksum=sha256_hex(PDF), approved=False,
    )
    assert app_module._verified_export_asset("d", "ebook.pdf") is None


def test_l_like_wildcards_in_a_filename_cannot_match_another_asset(factory):
    """A filename is data. "%" in it must not behave as a SQL wildcard."""
    project = _make_project(data={})
    pid = project["id"]
    real_key = export_object_key(pid, "dir/report.pdf")
    get_storage().put(real_key, PDF)
    database.record_asset(
        pid, "pdf", real_key, byte_size=len(PDF), checksum=sha256_hex(PDF), approved=True,
    )

    assert database.find_asset_by_export_path("dir", "%.pdf") is None
    assert database.find_asset_by_export_path("dir", "_eport.pdf") is None
    assert database.find_asset_by_export_path("dir", "report.pdf") is not None


def test_l_a_missing_asset_record_falls_back_to_the_disk_file(factory, monkeypatch):
    """Belt and braces on the route: no record means serve the legacy file."""
    import app as app_module

    real_pdf = _real_pdf_bytes()
    exports = factory["exports"]
    package = "fallbackdir"
    (exports / package).mkdir()
    (exports / package / "ebook.pdf").write_bytes(real_pdf)
    monkeypatch.setattr(app_module, "EXPORTS_DIR", str(exports))
    _make_project(
        name="Fallback Ebook",
        data={"package_id": package, "product_type": "ebook", "pdf_available": True},
    )

    # An unrelated asset exists, so the fast path is switched on.
    other = _make_project(name="Other")
    other_key = export_object_key(other["id"], "somewhere/else.pdf")
    get_storage().put(other_key, PDF)
    database.record_asset(
        other["id"], "pdf", other_key, byte_size=len(PDF),
        checksum=sha256_hex(PDF), approved=True,
    )
    assert database.list_assets_exist() is True

    response = app_module.app.test_client().get(f"/download/{package}/ebook.pdf")
    assert response.status_code == 200, response.data[:300]
    assert response.data == real_pdf


# ================== M-P. the canonical key rule comes from the REAL path =====


def test_m_export_key_is_derived_from_the_stored_path_not_package_id(factory):
    """The 0B-3A checkpoint's finding, encoded as a permanent test."""
    exports = factory["exports"]
    actual_dir = "b46724e3db52435bab9a4a348a6e9b78"
    (exports / actual_dir).mkdir()
    pdf = exports / actual_dir / "flower_parts.pdf"
    pdf.write_bytes(PDF)

    # The record declares a DIFFERENT package id -- exactly the live shape.
    data = {"package_id": "8bc848062cb140bb9462258d3e37d594", "pdf_path": str(pdf)}
    project = _make_project(name="Flower Parts", data=data)
    pid = project["id"]

    from services.storage.resolve import resolve_project_artifacts

    artifacts, problems = resolve_project_artifacts({"id": pid, "name": "x", "data": data})
    assert problems == []
    assert len(artifacts) == 1
    artifact = artifacts[0]

    assert artifact.storage_key == f"projects/{pid}/exports/{actual_dir}/flower_parts.pdf"
    assert data["package_id"] not in artifact.storage_key, (
        "a package-id key would map back to no file at all"
    )


def test_m_every_key_inverts_to_the_exact_existing_file(factory):
    exports = factory["exports"]
    (exports / "dirA").mkdir()
    (exports / "dirA" / "one.pdf").write_bytes(PDF)
    data = {"pdf_path": str(exports / "dirA" / "one.pdf")}
    project = _make_project(data=data)

    from services.storage.resolve import resolve_project_artifacts

    artifacts, _ = resolve_project_artifacts({"id": project["id"], "name": "", "data": data})
    for artifact in artifacts:
        rel = export_key_to_relpath(artifact.storage_key)
        assert (exports / rel).is_file()
        assert (exports / rel).read_bytes() == PDF


def test_n_package_id_directory_mismatches_are_detected(factory):
    exports = factory["exports"]
    (exports / "realdir").mkdir()
    (exports / "realdir" / "x.pdf").write_bytes(PDF)
    data = {"package_id": "declared-but-wrong", "pdf_path": str(exports / "realdir" / "x.pdf")}
    project = _make_project(data=data)

    from services.storage.resolve import audit_projects

    report = audit_projects([{"id": project["id"], "name": "n", "data": data}])
    assert report.package_id_mismatches, "the disagreement must be reported"
    pid, declared, dirs = report.package_id_mismatches[0]
    assert declared == "declared-but-wrong"
    assert dirs == ["realdir"]


def test_o_missing_path_pointers_are_reported_not_guessed(factory):
    data = {"package_id": "some-package", "pdf_bytes": PDF_B64}
    project = _make_project(data=data)

    from services.storage.resolve import audit_projects

    report = audit_projects([{"id": project["id"], "name": "n", "data": data}])
    assert report.artifacts == [], "nothing may be invented for an unresolvable product"
    assert len(report.missing_path_pointers) == 1
    pid, declared, has_embedded = report.missing_path_pointers[0]
    assert declared == "some-package"
    assert has_embedded is True


def test_p_keys_are_deterministic_and_stable():
    assert export_object_key(7, "dir/file.pdf") == "projects/7/exports/dir/file.pdf"
    assert export_object_key(7, "dir/file.pdf") == export_object_key(7, "dir/file.pdf")
    assert export_object_key(7, "dir\\file.pdf") == export_object_key(7, "dir/file.pdf")
    assert export_object_key(8, "dir/file.pdf") != export_object_key(7, "dir/file.pdf")
    assert embedded_key(7, "pdf_bytes", KIND_PDF) == "projects/7/embedded/pdf_bytes.pdf"


def test_p_a_legacy_filename_with_a_space_survives_the_key_rule():
    """One real customer file is "Thunder Volt.pdf". It must round-trip."""
    key = export_object_key(12, "d661340ee2a44246ab8e197899ab5c60/Thunder Volt.pdf")
    assert export_key_to_relpath(key) == "d661340ee2a44246ab8e197899ab5c60/Thunder Volt.pdf"


def test_p_traversal_can_never_enter_a_key():
    for bad in ("../x.pdf", "a/../../b.pdf", "", "/abs.pdf", "a/./b.pdf"):
        with pytest.raises(InvalidStorageKey):
            export_object_key(5, bad)


# ================================= Q-V. migration executor safety properties ===


def test_q_executor_refuses_to_run_unless_explicitly_enabled(factory):
    with pytest.raises(MigrationDisabled):
        migrate_artifact(
            project_id=1,
            storage_key="projects/1/embedded/pdf_bytes.pdf",
            source_bytes=PDF,
            kind=KIND_PDF,
        )


def test_q_executor_completes_the_full_sequence_when_enabled(factory):
    project = _make_project(data={"pdf_bytes": PDF_B64})
    pid = project["id"]
    key = embedded_key(pid, "pdf_bytes", KIND_PDF)

    outcome = migrate_artifact(
        project_id=pid, storage_key=key, source_bytes=PDF, kind=KIND_PDF,
        content_type="application/pdf", enable_customer_migration=True,
    )
    assert outcome.ok is True
    assert outcome.step_reached == STEP_DONE
    assert outcome.byte_size == len(PDF)
    assert outcome.checksum == sha256_hex(PDF)
    assert outcome.legacy_kept is True

    record = database.get_asset_by_key(key)
    assert record["approved"] is True
    assert record["checksum"] == sha256_hex(PDF)
    assert get_storage().get(key) == PDF


def test_r_running_twice_does_not_duplicate_the_asset(factory):
    project = _make_project(data={"pdf_bytes": PDF_B64})
    pid = project["id"]
    key = embedded_key(pid, "pdf_bytes", KIND_PDF)
    kwargs = dict(
        project_id=pid, storage_key=key, source_bytes=PDF, kind=KIND_PDF,
        enable_customer_migration=True,
    )

    first = migrate_artifact(**kwargs)
    second = migrate_artifact(**kwargs)

    assert first.ok and second.ok
    assert second.already_present is True, "a rerun recognises the verified copy"
    assert first.asset_id == second.asset_id
    assert len(database.list_assets(pid)) == 1

    conn = sqlite3.connect(str(factory["db"]))
    count = conn.execute(
        "SELECT COUNT(*) FROM assets WHERE storage_key=?", (key,)
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_q_the_legacy_source_survives_a_successful_migration(factory):
    exports = factory["exports"]
    (exports / "keepdir").mkdir()
    disk = exports / "keepdir" / "keep.pdf"
    disk.write_bytes(PDF)
    project = _make_project(data={"pdf_path": str(disk), "pdf_bytes": PDF_B64})
    pid = project["id"]

    migrate_artifact(
        project_id=pid, storage_key=export_object_key(pid, "keepdir/keep.pdf"),
        source_path=disk, kind="pdf", enable_customer_migration=True,
    )

    assert disk.is_file() and disk.read_bytes() == PDF, "no deletion step exists"
    stored = database.get_project(pid)
    assert stored["data"]["pdf_bytes"] == PDF_B64, "pdf_bytes is never removed"


def test_s_a_failed_upload_leaves_the_source_unchanged(factory):
    exports = factory["exports"]
    (exports / "faildir").mkdir()
    disk = exports / "faildir" / "src.pdf"
    disk.write_bytes(PDF)
    project = _make_project(data={"pdf_path": str(disk)})
    pid = project["id"]

    class FailingStorage:
        def stat(self, key):
            return None

        def put(self, key, data, *, content_type="application/octet-stream"):
            raise StorageError("upload exploded")

    outcome = migrate_artifact(
        project_id=pid, storage_key=export_object_key(pid, "faildir/src.pdf"),
        source_path=disk, kind="pdf", enable_customer_migration=True,
        storage=FailingStorage(),
    )
    assert outcome.ok is False
    assert outcome.step_reached == STEP_COPY
    assert outcome.legacy_kept is True
    assert disk.read_bytes() == PDF
    assert database.list_assets(pid) == [], "no asset row for a failed copy"


def test_t_a_failed_checksum_leaves_the_source_unchanged(factory):
    exports = factory["exports"]
    (exports / "sumdir").mkdir()
    disk = exports / "sumdir" / "src.pdf"
    disk.write_bytes(PDF)
    project = _make_project(data={"pdf_path": str(disk)})
    pid = project["id"]

    from services.storage.base import StorageStat

    class LyingStorage:
        def __init__(self):
            self.n = 0

        def stat(self, key):
            self.n += 1
            if self.n == 1:
                return None  # not already present
            return StorageStat(key=key, size=len(PDF), checksum="wrong-checksum")

        def put(self, key, data, *, content_type="application/octet-stream"):
            return None

    outcome = migrate_artifact(
        project_id=pid, storage_key=export_object_key(pid, "sumdir/src.pdf"),
        source_path=disk, kind="pdf", enable_customer_migration=True,
        storage=LyingStorage(),
    )
    assert outcome.ok is False
    assert outcome.step_reached == STEP_VERIFY_CHECKSUM
    assert disk.read_bytes() == PDF
    assert database.list_assets(pid) == []


def test_t_a_byte_count_mismatch_stops_before_recording(factory):
    project = _make_project(data={"pdf_bytes": PDF_B64})
    pid = project["id"]

    from services.storage.base import StorageStat

    class ShortStorage:
        def __init__(self):
            self.n = 0

        def stat(self, key):
            self.n += 1
            if self.n == 1:
                return None
            return StorageStat(key=key, size=3, checksum=sha256_hex(PDF))

        def put(self, key, data, *, content_type="application/octet-stream"):
            return None

    outcome = migrate_artifact(
        project_id=pid, storage_key=embedded_key(pid, "pdf_bytes", KIND_PDF),
        source_bytes=PDF, kind=KIND_PDF, enable_customer_migration=True,
        storage=ShortStorage(),
    )
    assert outcome.ok is False
    assert outcome.step_reached == STEP_VERIFY_SIZE
    assert database.list_assets(pid) == []
    assert database.get_project(pid)["data"]["pdf_bytes"] == PDF_B64


def test_u_a_failed_metadata_write_leaves_the_source_unchanged(factory, monkeypatch):
    exports = factory["exports"]
    (exports / "metadir").mkdir()
    disk = exports / "metadir" / "src.pdf"
    disk.write_bytes(PDF)
    project = _make_project(data={"pdf_path": str(disk), "pdf_bytes": PDF_B64})
    pid = project["id"]

    def _boom(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(database, "record_asset", _boom)

    outcome = migrate_artifact(
        project_id=pid, storage_key=export_object_key(pid, "metadir/src.pdf"),
        source_path=disk, kind="pdf", enable_customer_migration=True,
    )
    assert outcome.ok is False
    assert outcome.step_reached == STEP_RECORD
    assert outcome.legacy_kept is True
    assert disk.read_bytes() == PDF
    assert database.get_project(pid)["data"]["pdf_bytes"] == PDF_B64


def test_v_a_failed_readback_leaves_the_source_unchanged(factory):
    exports = factory["exports"]
    (exports / "backdir").mkdir()
    disk = exports / "backdir" / "src.pdf"
    disk.write_bytes(PDF)
    project = _make_project(data={"pdf_path": str(disk)})
    pid = project["id"]

    from services.storage.base import StorageStat

    class BadReadbackStorage:
        def __init__(self):
            self.n = 0

        def stat(self, key):
            self.n += 1
            if self.n == 1:
                return None
            return StorageStat(key=key, size=len(PDF), checksum=sha256_hex(PDF))

        def put(self, key, data, *, content_type="application/octet-stream"):
            return None

        def get(self, key):
            return b"not-what-was-written"

    outcome = migrate_artifact(
        project_id=pid, storage_key=export_object_key(pid, "backdir/src.pdf"),
        source_path=disk, kind="pdf", enable_customer_migration=True,
        storage=BadReadbackStorage(),
    )
    assert outcome.ok is False
    assert outcome.step_reached == STEP_VERIFY_READBACK
    assert disk.read_bytes() == PDF
    # The asset was recorded but never marked verified, so no reader
    # will prefer it over the legacy copy.
    record = database.get_asset_by_key(export_object_key(pid, "backdir/src.pdf"))
    assert record is not None and record["approved"] is False


def test_v_an_unapproved_asset_is_still_ignored_by_saved_projects(factory):
    project = _make_project(data={})
    pid = project["id"]
    rel = "half/done.pdf"
    key = export_object_key(pid, rel)
    get_storage().put(key, PDF)
    database.record_asset(
        pid, "pdf", key, byte_size=len(PDF), checksum=sha256_hex(PDF), approved=False,
    )
    assert database._existing_customer_output_files({"id": pid, "data": {}}) == []


# ================================== W-Y. dry run mutates nothing =============


def test_w_the_dry_run_planner_performs_zero_mutations(factory):
    exports = factory["exports"]
    (exports / "dry").mkdir()
    (exports / "dry" / "a.pdf").write_bytes(PDF)
    data = {"pdf_bytes": PDF_B64, "pdf_path": str(exports / "dry" / "a.pdf")}
    project = _make_project(data=data)
    pid = project["id"]

    before = database.get_project(pid)["data"]
    disk_before = (exports / "dry" / "a.pdf").read_bytes()

    from services.storage.migration import plan_exports, plan_migration

    projects = [{"id": pid, "name": "n", "data": data}]
    embedded_plan = plan_migration(projects)
    export_plan = plan_exports(projects)

    assert embedded_plan.moves and export_plan.moves
    assert database.get_project(pid)["data"] == before
    assert (exports / "dry" / "a.pdf").read_bytes() == disk_before
    assert database.list_assets(pid) == [], "planning records no assets"
    assert get_storage().exists(embedded_plan.moves[0].storage_key) is False


def test_x_the_embedded_pdf_field_is_never_touched_by_any_0b3b1_code(factory):
    data = {"pdf_bytes": PDF_B64}
    project = _make_project(data=data)
    pid = project["id"]

    from services.storage.migration import plan_migration
    from services.storage.resolve import audit_projects

    plan_migration([{"id": pid, "name": "n", "data": data}])
    audit_projects([{"id": pid, "name": "n", "data": data}])
    read_asset_or_legacy(pid, data)

    assert database.get_project(pid)["data"]["pdf_bytes"] == PDF_B64


def test_y_legacy_export_files_are_never_moved_or_deleted(factory):
    exports = factory["exports"]
    (exports / "untouched").mkdir()
    paths = []
    for name in ("a.pdf", "b.zip", "c.png"):
        p = exports / "untouched" / name
        p.write_bytes(PDF)
        paths.append(p)
    data = {"exports": {"folder": str(exports / "untouched")}}
    project = _make_project(data=data)

    from services.storage.migration import plan_exports
    from services.storage.resolve import audit_projects

    projects = [{"id": project["id"], "name": "n", "data": data}]
    audit_projects(projects)
    plan_exports(projects)

    for p in paths:
        assert p.is_file(), f"{p.name} disappeared"
        assert p.read_bytes() == PDF


# ============================== Z. locked behaviour and concurrency hold =====


def test_z_optimistic_concurrency_still_rejects_a_stale_write(factory):
    project = _make_project(data={"content": "v1"})
    pid = project["id"]

    first = database.get_project(pid)
    second = database.get_project(pid)

    first["data"]["content"] = "winner"
    database.update_project(pid, None, first["data"])

    second["data"]["content"] = "loser"
    with pytest.raises(database.StaleProjectWrite):
        database.update_project(pid, None, second["data"])

    assert database.get_project(pid)["data"]["content"] == "winner"


def test_z_asset_reads_do_not_bump_the_project_version(factory):
    project = _make_project(data={"pdf_bytes": PDF_B64})
    pid = project["id"]
    before = database.get_project(pid)["data"]["_row_version"]

    read_asset_or_legacy(pid, {"pdf_bytes": PDF_B64})
    export_asset_is_available(pid, "some/path.pdf")
    database.list_assets_exist()

    assert database.get_project(pid)["data"]["_row_version"] == before


def test_z_recording_an_asset_does_not_touch_the_project_row(factory):
    project = _make_project(data={"pdf_bytes": PDF_B64})
    pid = project["id"]
    before = database.get_project(pid)

    database.record_asset(
        pid, KIND_PDF, embedded_key(pid, "pdf_bytes", KIND_PDF),
        byte_size=len(PDF), checksum=sha256_hex(PDF), approved=True,
    )

    after = database.get_project(pid)
    assert after["data"]["pdf_bytes"] == before["data"]["pdf_bytes"]
    assert after["data"]["_row_version"] == before["data"]["_row_version"]
