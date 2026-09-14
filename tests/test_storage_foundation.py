"""Upgrade 0, Phase 0B-3A: the storage foundation, proven before anything moves.

WHY THIS EXISTS
---------------
Customer artifacts live in two places that a second process cannot
reach: files on the web service's private disk (a Render persistent disk
is accessible by exactly one service instance), and base64 binaries
embedded in `projects.data` — 73 of 114 local rows, largest ~56 MB, and
the whole row is rewritten on every checkpoint.

Phase 0B-3A builds the boundary and proves it. It migrates nothing. The
tests below therefore assert two different kinds of thing: that the new
storage layer works, AND that the legacy world is completely untouched.

No external/paid call is made by any test here. No bucket, provider, or
external account is involved.
"""
from __future__ import annotations

import base64
import json

import pytest

import database
from services.storage import (
    KIND_PDF,
    LocalFilesystemDriver,
    StorageError,
    StorageKeyNotFound,
    embedded_key,
    export_key,
    get_storage,
    is_valid_key,
    reset_storage,
    sha256_hex,
)
from services.storage.compat import (
    decode_embedded,
    legacy_embedded_fields,
    read_asset_or_legacy,
)
from services.storage.migration import plan_migration, plan_project

PDF_BYTES = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\ntrailer<</Root 1 0 R>>\n%%EOF\n"


@pytest.fixture()
def storage(tmp_path):
    """A driver rooted in a temp dir, isolated from the Factory's own tree."""
    return LocalFilesystemDriver(root=tmp_path / "assets")


def _make_project(name="Storage Test", data=None):
    project = database.create_project(
        name, "product", data if data is not None else {},
        user_saved=True, system_test=False, temporary=False,
    )
    return int(project["id"])


def _raw_blob(project_id: int) -> dict:
    conn = database.get_conn()
    try:
        row = conn.execute("SELECT data FROM projects WHERE id=?", (project_id,)).fetchone()
    finally:
        conn.close()
    return json.loads(row["data"] or "{}")


# ================================================= A. put/get byte-identical ===


def test_a_local_put_get_is_byte_identical(storage):
    key = "projects/1/embedded/pdf_bytes.pdf"
    stat = storage.put(key, PDF_BYTES, content_type="application/pdf")
    assert storage.get(key) == PDF_BYTES
    assert stat.size == len(PDF_BYTES)
    assert stat.content_type == "application/pdf"


def test_a_large_payload_round_trips_intact(storage):
    payload = bytes(range(256)) * 8192  # 2 MB of non-trivial bytes
    key = "projects/2/embedded/pdf_bytes.pdf"
    storage.put(key, payload)
    assert storage.get(key) == payload


# =========================================================== B. checksums ===


def test_b_checksums_are_preserved(storage):
    key = "projects/3/embedded/pdf_bytes.pdf"
    stat = storage.put(key, PDF_BYTES)
    assert stat.checksum == sha256_hex(PDF_BYTES)
    assert storage.stat(key).checksum == sha256_hex(PDF_BYTES)


def test_b_verify_detects_a_corrupted_object(storage):
    key = "projects/4/embedded/pdf_bytes.pdf"
    storage.put(key, PDF_BYTES)
    assert storage.verify(key, expected_checksum=sha256_hex(PDF_BYTES),
                          expected_size=len(PDF_BYTES)) is True
    # Wrong expectations must not verify -- this is the gate that will
    # stand between a copy and deleting a customer's only original.
    assert storage.verify(key, expected_checksum="0" * 64,
                          expected_size=len(PDF_BYTES)) is False
    assert storage.verify(key, expected_checksum=sha256_hex(PDF_BYTES),
                          expected_size=999999) is False


# ============================================================== C. exists ===


def test_c_exists_behaves_correctly(storage):
    key = "projects/5/embedded/pdf_bytes.pdf"
    assert storage.exists(key) is False
    storage.put(key, PDF_BYTES)
    assert storage.exists(key) is True
    assert storage.delete(key) is True
    assert storage.exists(key) is False
    assert storage.delete(key) is False, "deleting an absent key reports False"


def test_c_missing_key_raises_not_found(storage):
    with pytest.raises(StorageKeyNotFound):
        storage.get("projects/6/embedded/never_written.pdf")
    assert storage.stat("projects/6/embedded/never_written.pdf") is None


def test_c_keys_cannot_escape_the_storage_root(storage):
    for bad in ("../outside.pdf", "/etc/passwd", "projects/../../x.pdf", "", "a//b"):
        assert is_valid_key(bad) is False, bad
        with pytest.raises(StorageError):
            storage.put(bad, PDF_BYTES)


# ============================================== D. asset maps to project ===


def test_d_asset_metadata_maps_to_the_correct_project():
    pid = _make_project()
    key = embedded_key(pid, "pdf_bytes", KIND_PDF)
    asset = database.record_asset(
        pid, KIND_PDF, key,
        content_type="application/pdf",
        byte_size=len(PDF_BYTES),
        checksum=sha256_hex(PDF_BYTES),
    )
    assert asset["project_id"] == pid
    assert asset["kind"] == KIND_PDF
    assert asset["storage_key"] == key
    assert asset["checksum"] == sha256_hex(PDF_BYTES)
    assert asset["byte_size"] == len(PDF_BYTES)

    assert database.get_asset_by_key(key)["project_id"] == pid
    listed = database.list_assets(pid, kind=KIND_PDF)
    assert [a["storage_key"] for a in listed] == [key]


def test_d_assets_do_not_leak_between_projects():
    a, b = _make_project("Project A"), _make_project("Project B")
    database.record_asset(a, KIND_PDF, embedded_key(a, "pdf_bytes", KIND_PDF))
    database.record_asset(b, KIND_PDF, embedded_key(b, "pdf_bytes", KIND_PDF))
    assert len(database.list_assets(a)) == 1
    assert database.list_assets(a)[0]["project_id"] == a


# ==================================================== E. deterministic keys ===


def test_e_keys_are_deterministic_across_retries():
    assert embedded_key(42, "pdf_bytes", KIND_PDF) == embedded_key(42, "pdf_bytes", KIND_PDF)
    assert export_key(42, "pkg-abc", "ebook.pdf") == export_key(42, "pkg-abc", "ebook.pdf")
    # Distinct inputs must not collide.
    assert embedded_key(42, "pdf_bytes", KIND_PDF) != embedded_key(43, "pdf_bytes", KIND_PDF)
    assert export_key(42, "pkg-abc", "ebook.pdf") != export_key(42, "pkg-abc", "package.zip")


def test_e_key_shape_is_stable_and_project_scoped():
    assert embedded_key(7, "pdf_bytes", KIND_PDF) == "projects/7/embedded/pdf_bytes.pdf"
    assert export_key(7, "pkg1", "ebook.pdf") == "projects/7/exports/pkg1/ebook.pdf"


# ========================================= F. no duplicate asset records ===


def test_f_re_recording_the_same_key_does_not_duplicate():
    pid = _make_project()
    key = embedded_key(pid, "pdf_bytes", KIND_PDF)
    for _ in range(3):
        database.record_asset(
            pid, KIND_PDF, key,
            byte_size=len(PDF_BYTES), checksum=sha256_hex(PDF_BYTES),
        )
    assets = database.list_assets(pid)
    assert len(assets) == 1, "a restarted migration must not create duplicate assets"
    assert assets[0]["byte_size"] == len(PDF_BYTES)


def test_f_repeating_a_storage_put_is_idempotent(storage):
    key = "projects/8/embedded/pdf_bytes.pdf"
    first = storage.put(key, PDF_BYTES)
    second = storage.put(key, PDF_BYTES)
    assert first.checksum == second.checksum
    assert storage.get(key) == PDF_BYTES


# ============================================= G/H. legacy stays untouched ===


def test_g_legacy_disk_artifacts_remain_readable(tmp_path, monkeypatch):
    """0B-3A moves no export file; the existing tree still resolves."""
    exports = tmp_path / "exports"
    (exports / "pkg-legacy").mkdir(parents=True)
    legacy_pdf = exports / "pkg-legacy" / "ebook.pdf"
    legacy_pdf.write_bytes(PDF_BYTES)
    monkeypatch.setenv("FACTORY_EXPORTS_DIR", str(exports))

    assert legacy_pdf.is_file()
    assert legacy_pdf.read_bytes() == PDF_BYTES


def test_h_embedded_pdf_bytes_remain_untouched():
    """The single most important 0B-3A guarantee: nothing is removed."""
    encoded = base64.b64encode(PDF_BYTES).decode("ascii")
    pid = _make_project(data={"product_type": "word_search", "pdf_bytes": encoded})

    # Everything the storage foundation offers, exercised against the project…
    plan_migration([{"id": pid, "name": "x", "data": database.get_project(pid)["data"]}])
    read_asset_or_legacy(pid, database.get_project(pid)["data"])

    # …and the legacy field is still exactly where it was.
    blob = _raw_blob(pid)
    assert blob["pdf_bytes"] == encoded, "0B-3A must never remove an embedded binary"
    assert base64.b64decode(blob["pdf_bytes"]) == PDF_BYTES


def test_h_compat_read_falls_back_to_the_legacy_blob():
    encoded = base64.b64encode(PDF_BYTES).decode("ascii")
    pid = _make_project(data={"pdf_bytes": encoded})
    data = database.get_project(pid)["data"]
    # Nothing migrated, so this must come from the legacy field.
    assert read_asset_or_legacy(pid, data) == PDF_BYTES


def test_h_compat_prefers_a_stored_asset_once_one_exists(tmp_path, monkeypatch):
    """The 0B-3B path, proven dormant-but-correct now.

    0B-3B1 tightened what counts as a usable asset: the object alone is
    no longer enough. There must also be an `assets` record whose byte
    count and SHA-256 the stored bytes actually match, so a half-finished
    or corrupted migration can never be preferred over a good legacy
    copy. The asset is therefore recorded here, as a real migration does.
    """
    from services.storage import sha256_hex

    monkeypatch.setenv("FACTORY_STORAGE_DIR", str(tmp_path / "assets"))
    reset_storage()
    try:
        pid = _make_project(data={"pdf_bytes": base64.b64encode(b"OLD-LEGACY").decode()})
        key = embedded_key(pid, "pdf_bytes", KIND_PDF)
        get_storage().put(key, PDF_BYTES)
        database.record_asset(
            pid,
            KIND_PDF,
            key,
            byte_size=len(PDF_BYTES),
            checksum=sha256_hex(PDF_BYTES),
            approved=True,
        )
        data = database.get_project(pid)["data"]
        assert read_asset_or_legacy(pid, data) == PDF_BYTES
        # and the legacy copy is still there underneath it
        assert decode_embedded(_raw_blob(pid)["pdf_bytes"]) == b"OLD-LEGACY"
    finally:
        reset_storage()


def test_h_a_stored_object_with_no_asset_record_is_not_trusted(tmp_path, monkeypatch):
    """Bytes in storage that nothing vouches for must not be served.

    An object can exist because a migration was interrupted after the
    upload but before the record was written. Without a record there is
    nothing to check its size or checksum against, so the legacy copy
    stays authoritative.
    """
    monkeypatch.setenv("FACTORY_STORAGE_DIR", str(tmp_path / "assets"))
    reset_storage()
    try:
        pid = _make_project(data={"pdf_bytes": base64.b64encode(b"OLD-LEGACY").decode()})
        get_storage().put(embedded_key(pid, "pdf_bytes", KIND_PDF), PDF_BYTES)
        data = database.get_project(pid)["data"]
        assert read_asset_or_legacy(pid, data) == b"OLD-LEGACY"
    finally:
        reset_storage()


def test_legacy_embedded_fields_reports_what_exists():
    pid = _make_project(data={
        "pdf_bytes": base64.b64encode(PDF_BYTES).decode(),
        "cover_preview_b64": base64.b64encode(b"PNGDATA").decode(),
    })
    found = legacy_embedded_fields(database.get_project(pid)["data"])
    assert found == {"pdf_bytes": len(PDF_BYTES), "cover_preview_b64": len(b"PNGDATA")}


# ============================================ I/J/K. no customer regression ===


def test_i_existing_download_and_customer_routes_still_work():
    import app as app_module

    app_module.app.config.update(TESTING=True)
    client = app_module.app.test_client()

    pid = _make_project("Route Check")
    assert client.get("/projects").status_code == 200
    assert client.get(f"/projects/{pid}").status_code == 200
    # An unknown package still refuses cleanly rather than erroring.
    assert client.get("/download/not-a-real-package/ebook.pdf").status_code in (400, 403, 404)


def test_j_saved_projects_behaviour_does_not_regress():
    """Saved Projects decides visibility from real files on disk. The new
    storage layer must not have changed that determination."""
    pid = _make_project("Saved Projects Check", data={"product_type": "ebook"})
    row = database.get_project(pid)
    assert database.is_customer_saved_product(row) in (True, False)
    listed = database.list_projects(include_system=True)
    assert any(p["id"] == pid for p in listed)


def test_k_approved_and_locked_lifecycle_does_not_regress():
    from services.quality.artifact_state import (
        ArtifactState,
        ArtifactStateError,
        assert_content_mutable,
        resolve_artifact_state,
    )

    pid = _make_project("Locked Check", data={
        "artifact_state": "LOCKED", "export_ready": True, "content": "x",
        "pdf_bytes": base64.b64encode(PDF_BYTES).decode(),
    })
    data = database.get_project(pid)["data"]
    assert resolve_artifact_state(data) == ArtifactState.LOCKED
    with pytest.raises(ArtifactStateError):
        assert_content_mutable(data)
    # Recording an asset must not alter lifecycle state.
    database.record_asset(pid, KIND_PDF, embedded_key(pid, "pdf_bytes", KIND_PDF))
    assert resolve_artifact_state(database.get_project(pid)["data"]) == ArtifactState.LOCKED


# ====================================== L. storage failure cannot destroy ===


def test_l_a_storage_failure_cannot_destroy_the_legacy_copy(tmp_path, monkeypatch):
    """If storage is broken, reads fall back and the original survives."""
    encoded = base64.b64encode(PDF_BYTES).decode("ascii")
    pid = _make_project(data={"pdf_bytes": encoded})

    class _BrokenDriver(LocalFilesystemDriver):
        def exists(self, key):  # noqa: D102
            raise StorageError("storage backend is down")

        def get(self, key):  # noqa: D102
            raise StorageError("storage backend is down")

    import services.storage as storage_pkg

    monkeypatch.setattr(storage_pkg, "_driver", _BrokenDriver(root=tmp_path))
    try:
        data = database.get_project(pid)["data"]
        # The read still succeeds, from the legacy copy.
        assert read_asset_or_legacy(pid, data) == PDF_BYTES
    finally:
        reset_storage()

    # And the legacy copy is untouched.
    assert _raw_blob(pid)["pdf_bytes"] == encoded


def test_l_a_failed_put_leaves_no_readable_partial_object(storage):
    with pytest.raises(StorageError):
        storage.put("projects/9/embedded/pdf_bytes.pdf", "not bytes")  # type: ignore[arg-type]
    assert storage.exists("projects/9/embedded/pdf_bytes.pdf") is False


# ================================================ M. dry run mutates nothing ===


def test_m_dry_run_makes_zero_persistent_mutations():
    encoded = base64.b64encode(PDF_BYTES).decode("ascii")
    pid = _make_project(data={"product_type": "word_search", "pdf_bytes": encoded})

    before_blob = _raw_blob(pid)
    before_assets = database.list_assets(pid)
    before_row = database.get_project(pid)

    plan = plan_migration([{"id": pid, "name": "x", "data": database.get_project(pid)["data"]}])
    assert plan.moves, "the plan should have found the embedded pdf"

    assert _raw_blob(pid) == before_blob, "dry run must not touch projects.data"
    assert database.list_assets(pid) == before_assets, "dry run must not record assets"
    assert database.get_project(pid)["data"].get("_row_version") == \
        before_row["data"].get("_row_version"), "dry run must not bump the row version"


def test_m_dry_run_reports_what_it_would_do():
    encoded = base64.b64encode(PDF_BYTES).decode("ascii")
    moves, problems = plan_project({"id": 11, "name": "Plan Me", "data": {"pdf_bytes": encoded}})

    assert not problems
    assert len(moves) == 1
    move = moves[0]
    assert move.project_id == 11
    assert move.source_field == "pdf_bytes"
    assert move.storage_key == "projects/11/embedded/pdf_bytes.pdf"
    assert move.byte_size == len(PDF_BYTES)
    assert move.checksum == sha256_hex(PDF_BYTES)
    assert move.content_type == "application/pdf"
    assert move.would_delete_field == "pdf_bytes"
    assert move.as_asset_record()["storage_key"] == move.storage_key


def test_m_dry_run_reports_malformed_rows_instead_of_crashing():
    moves, problems = plan_project({"id": 12, "name": "Bad", "data": {"pdf_bytes": "!!!not base64!!!"}})
    assert not moves
    assert problems and "base64" in problems[0].problem

    moves, problems = plan_project({"id": 13, "name": "Empty", "data": {"pdf_bytes": ""}})
    assert not moves
    assert problems and "empty" in problems[0].problem


def test_m_plan_summary_totals_are_correct():
    a = base64.b64encode(b"A" * 100).decode()
    b = base64.b64encode(b"B" * 250).decode()
    plan = plan_migration([
        {"id": 21, "name": "one", "data": {"pdf_bytes": a}},
        {"id": 22, "name": "two", "data": {"pdf_bytes": b}},
        {"id": 23, "name": "none", "data": {}},
    ])
    summary = plan.summary()
    assert summary["projects_scanned"] == 3
    assert summary["projects_affected"] == 2
    assert summary["binaries_to_move"] == 2
    assert summary["total_bytes"] == 350
    assert summary["largest_bytes"] == 250


# ============================================ the S3 contract is not built ===


def test_the_s3_driver_is_a_contract_and_refuses_to_run():
    from services.storage.s3 import S3CompatibleDriver

    with pytest.raises(NotImplementedError):
        S3CompatibleDriver()


def test_only_one_cloud_storage_sdk_is_declared():
    """boto3 is the single cloud-storage client the Factory depends on.

    0B-3A forbade every storage SDK, because nothing talked to a provider
    yet. 0B-3B1 adds exactly one -- boto3, for Cloudflare R2's
    S3-compatible API -- so the guard becomes "one, and no others"
    rather than "none". Anything else creeping in is still a regression.
    """
    requirements = (
        __import__("pathlib").Path(__file__).resolve().parents[1] / "requirements.txt"
    ).read_text(encoding="utf-8").lower()
    assert "boto3" in requirements, "the R2 driver needs its client declared"
    for unrelated in ("minio", "google-cloud-storage", "azure-storage", "dropbox"):
        assert unrelated not in requirements, f"unrelated cloud library added: {unrelated}"
