"""v1.8.14 -- a finished book is finished on every machine.

The PDF and ZIP are built on the builder and published to storage. The
website, whose disk never held them, judged the book unfinished and left it
at 90% with its downloads working -- a book that was done but did not say
so. These tests prove the finished files are fetched back, that only real
PDF and ZIP bytes are accepted, and that a book with no files is still
reported unfinished.
"""
from __future__ import annotations

import os

import services.ebook_build_orchestrator as orch

PDF = b"%PDF-1.4 finished book"
ZIP = b"PK\x03\x04 finished package"


def _data(pkg="ebook-5", pid=5):
    return {"export_package_id": pkg, "_project_id": pid,
            "export_ready": True,
            "exports": {"files": {"pdf": "ebook.pdf", "zip": "package.zip"}}}


def _storage(mapping):
    def read(project_id, relative_path, legacy_path=None):
        return mapping.get(str(relative_path))
    return read


def test_files_already_here_are_not_refetched(tmp_path, monkeypatch):
    monkeypatch.setattr("services.packaging.EXPORTS_DIR", str(tmp_path))
    pkg = tmp_path / "ebook-5"
    pkg.mkdir()
    (pkg / "ebook.pdf").write_bytes(PDF)
    (pkg / "package.zip").write_bytes(ZIP)

    def explode(*a, **k):
        raise AssertionError("storage must not be read when the files are here")

    monkeypatch.setattr("services.storage.compat.read_export_or_legacy", explode)
    assert orch._export_files_on_disk(_data()) is True


def test_finished_files_are_fetched_back_from_storage(tmp_path, monkeypatch):
    monkeypatch.setattr("services.packaging.EXPORTS_DIR", str(tmp_path))
    monkeypatch.setattr("services.storage.compat.read_export_or_legacy",
                        _storage({"ebook-5/ebook.pdf": PDF, "ebook-5/package.zip": ZIP}))
    assert orch._export_files_on_disk(_data()) is True
    assert (tmp_path / "ebook-5" / "ebook.pdf").read_bytes() == PDF
    assert (tmp_path / "ebook-5" / "package.zip").read_bytes() == ZIP


def test_bytes_that_are_not_a_pdf_are_refused(tmp_path, monkeypatch):
    monkeypatch.setattr("services.packaging.EXPORTS_DIR", str(tmp_path))
    monkeypatch.setattr("services.storage.compat.read_export_or_legacy",
                        _storage({"ebook-5/ebook.pdf": b"<html>an error page</html>",
                                  "ebook-5/package.zip": ZIP}))
    assert orch._export_files_on_disk(_data()) is False
    assert not (tmp_path / "ebook-5" / "ebook.pdf").exists()


def test_a_missing_zip_still_means_unfinished(tmp_path, monkeypatch):
    monkeypatch.setattr("services.packaging.EXPORTS_DIR", str(tmp_path))
    monkeypatch.setattr("services.storage.compat.read_export_or_legacy",
                        _storage({"ebook-5/ebook.pdf": PDF}))
    assert orch._export_files_on_disk(_data()) is False


def test_storage_with_nothing_means_unfinished(tmp_path, monkeypatch):
    monkeypatch.setattr("services.packaging.EXPORTS_DIR", str(tmp_path))
    monkeypatch.setattr("services.storage.compat.read_export_or_legacy",
                        _storage({}))
    assert orch._export_files_on_disk(_data()) is False


def test_without_a_project_id_storage_is_not_guessed_at(tmp_path, monkeypatch):
    monkeypatch.setattr("services.packaging.EXPORTS_DIR", str(tmp_path))

    def explode(*a, **k):
        raise AssertionError("no project id means no storage read")

    monkeypatch.setattr("services.storage.compat.read_export_or_legacy", explode)
    data = _data()
    data.pop("_project_id")
    assert orch._export_files_on_disk(data) is False


def test_storage_failure_never_escapes(tmp_path, monkeypatch):
    monkeypatch.setattr("services.packaging.EXPORTS_DIR", str(tmp_path))

    def boom(*a, **k):
        raise RuntimeError("storage is down")

    monkeypatch.setattr("services.storage.compat.read_export_or_legacy", boom)
    assert orch._export_files_on_disk(_data()) is False


def test_a_suspicious_package_id_is_still_refused(tmp_path, monkeypatch):
    monkeypatch.setattr("services.packaging.EXPORTS_DIR", str(tmp_path))
    monkeypatch.setattr("services.storage.compat.read_export_or_legacy",
                        _storage({"../../etc/ebook.pdf": PDF}))
    assert orch._export_files_on_disk(_data(pkg="../../etc")) is False


def test_the_export_stage_counts_a_recovered_book_as_done(tmp_path, monkeypatch):
    """The whole point: a finished book reads as finished on any machine."""
    monkeypatch.setattr("services.packaging.EXPORTS_DIR", str(tmp_path))
    monkeypatch.setattr("services.storage.compat.read_export_or_legacy",
                        _storage({"ebook-5/ebook.pdf": PDF, "ebook-5/package.zip": ZIP}))
    assert orch.stage_is_validated(_data(), "export") is True
