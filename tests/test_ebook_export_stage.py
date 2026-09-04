"""The one-click build's export stage packages; it never regenerates.

ROOT CAUSE THIS GUARDS
----------------------
_run_export called services.ebook_package.build_ebook_package(data). That
function is the *generation* pipeline -- visual planning, photograph
retrieval, cover staging -- and takes (title, content_md, fields), so every
export attempt raised TypeError and the build died at 90% with the customer
message "We couldn't finish your ebook." Even with the right arguments it was
the wrong function: it would have re-run acquisition over an already-approved
artifact.

The export stage now calls services.packaging.build_product_export, the same
renderer the Export button uses, and completion is decided by inspecting the
produced files rather than by trusting a flag.

No external call is made by any test here.
"""
from __future__ import annotations

import os
import pathlib
import zipfile

import pytest

MIN_PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\ntrailer<</Root 1 0 R>>\n%%EOF\n"


def _orchestrator_source() -> str:
    return (pathlib.Path(__file__).resolve().parents[1]
            / "services" / "ebook_build_orchestrator.py").read_text(encoding="utf-8")


def test_export_stage_packages_and_does_not_regenerate():
    src = _orchestrator_source()
    start = src.index("def _run_export")
    body = src[start:src.index("\ndef ", start + 10)]
    assert "build_product_export" in body, "export must use the packaging renderer"
    # The name legitimately appears in the comment explaining why it is wrong.
    # What must not appear is a call to it, or an import of it.
    assert "build_ebook_package(" not in body, (
        "build_ebook_package is the generation pipeline; calling it at export "
        "would re-run visual acquisition over an approved artifact"
    )
    assert "import build_ebook_package" not in body


def test_export_release_state_is_read_from_preflight_not_invented():
    """export_ready must follow the preflight record, both ways."""
    from services.ebook_build_orchestrator import _run_export

    calls: list[dict] = []

    def fake_export(project):
        calls.append(project)
        return {"package_id": "pkg123", "exports": {"files": {"pdf": {}, "zip": {}}}}

    import services.packaging as packaging

    original = packaging.build_product_export
    packaging.build_product_export = fake_export
    try:
        passed = _run_export({"ebook_design_preflight": {"status": "PASS"}}, 1)
        assert passed["export_ready"] is True
        assert passed["release_status"] == "PASS"
        assert passed["export_package_id"] == "pkg123"

        blocked = _run_export({"ebook_design_preflight": {"status": "FAIL"}}, 1)
        assert blocked["export_ready"] is False
        assert blocked["release_status"] != "PASS"

        missing = _run_export({}, 1)
        assert missing["export_ready"] is False
    finally:
        packaging.build_product_export = original
    assert len(calls) == 3


def _write_package(tmp_path, package_id, *, pdf=MIN_PDF, zip_ok=True):
    pkg = tmp_path / package_id
    pkg.mkdir(parents=True, exist_ok=True)
    (pkg / "ebook.pdf").write_bytes(pdf)
    zip_path = pkg / "package.zip"
    if zip_ok:
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("ebook.pdf", pdf)
    else:
        zip_path.write_bytes(b"not a zip")
    return pkg


def _data(package_id):
    return {
        "export_ready": True,
        "export_package_id": package_id,
        "exports": {"files": {"pdf": {"url": "/x"}, "zip": {"url": "/y"}}},
    }


@pytest.fixture()
def exports_dir(tmp_path, monkeypatch):
    import services.packaging as packaging

    monkeypatch.setattr(packaging, "EXPORTS_DIR", str(tmp_path), raising=False)
    return tmp_path


def test_export_is_complete_only_with_real_files(exports_dir):
    from services.ebook_build_orchestrator import stage_is_validated

    _write_package(exports_dir, "ebook-visuals-local")
    # A slug package id with hyphens is legitimate and must be accepted.
    assert stage_is_validated(_data("ebook-visuals-local"), "export") is True


def test_export_is_not_complete_when_the_pdf_is_not_a_pdf(exports_dir):
    from services.ebook_build_orchestrator import stage_is_validated

    _write_package(exports_dir, "badpdf", pdf=b"<html>sorry</html>")
    assert stage_is_validated(_data("badpdf"), "export") is False


def test_export_is_not_complete_when_the_zip_is_not_a_zip(exports_dir):
    from services.ebook_build_orchestrator import stage_is_validated

    _write_package(exports_dir, "badzip", zip_ok=False)
    assert stage_is_validated(_data("badzip"), "export") is False


def test_export_is_not_complete_when_files_are_absent(exports_dir):
    from services.ebook_build_orchestrator import stage_is_validated

    assert stage_is_validated(_data("nothinghere"), "export") is False


def test_export_flag_alone_is_never_enough(exports_dir):
    from services.ebook_build_orchestrator import stage_is_validated

    _write_package(exports_dir, "pkgflag")
    data = _data("pkgflag")
    data["export_ready"] = False
    assert stage_is_validated(data, "export") is False
    data = _data("pkgflag")
    data["exports"] = {"files": {"pdf": {"url": "/x"}}}
    assert stage_is_validated(data, "export") is False


def test_package_id_cannot_escape_the_exports_directory(exports_dir):
    from services.ebook_build_orchestrator import stage_is_validated

    _write_package(exports_dir, "real")
    for evil in ("../real", "..", "a/b", "a\\b", "real/.", ""):
        assert stage_is_validated(_data(evil), "export") is False, evil


def test_workspace_title_is_normalised_before_it_is_stored():
    """A leading colon in the customer's entry must never reach the project."""
    from services.ebook_contamination import normalize_book_title

    assert normalize_book_title(": How to Keep Your Teen Safe Online") == (
        "How to Keep Your Teen Safe Online"
    )
    src = (pathlib.Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    start = src.index("def _start_ebook_workspace_build")
    body = src[start:src.index("\n@app.", start)]
    assert "normalize_book_title" in body, (
        "the workspace build must normalise the title the customer typed"
    )
