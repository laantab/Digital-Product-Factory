"""Manual and one-button exports must honor the same final editorial verdict.

Only the reviewer verdict is substituted in wiring cases; the PDF and ZIP
are real files, opened and rendered by the production completion path.
"""
import copy
import hashlib
import zipfile
from pathlib import Path
from unittest.mock import patch

import fitz
import pytest

from services import ebook_build_orchestrator as orch
from services.editor_in_chief import ReviewReport, VERDICT_PASS, VERDICT_CORRECTION


@pytest.fixture
def export_candidate(tmp_path, monkeypatch):
    import services.packaging as packaging

    monkeypatch.setattr(packaging, "EXPORTS_DIR", str(tmp_path))
    package = tmp_path / "quality-candidate"
    package.mkdir()
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "A finished ebook candidate", fontsize=12)
        doc.save(package / "ebook.pdf")
    (package / "ebook.html").write_text("<p>A finished ebook candidate</p>")
    with zipfile.ZipFile(package / "package.zip", "w") as z:
        z.write(package / "ebook.pdf", "ebook.pdf")
    data = {"title": "A finished ebook candidate", "content": "Preserved approved text",
            "ebook_design_preflight": {"status": "PASS"},
            "fields": {"ebook_creation_mode": "ai_recommended"}}
    result = {"package_id": package.name,
              "exports": {"files": {"pdf": {"url": "/ebook.pdf"}, "zip": {"url": "/package.zip"}}}}
    monkeypatch.setattr(packaging, "build_product_export", lambda project: copy.deepcopy(result))
    return data, package


@pytest.mark.parametrize("verdict,ready", [(VERDICT_PASS, True), (VERDICT_CORRECTION, False)])
def test_one_button_completion_obeys_the_final_editorial_verdict(export_candidate, verdict, ready):
    data, package = export_candidate
    rendered = []

    def review(candidate):
        assert Path(candidate["pdf_path"]).read_bytes() == (package / "ebook.pdf").read_bytes()
        assert candidate["manuscript"] == data["content"]
        assert len(candidate["page_images"]) == 1
        rendered.extend(candidate["page_images"])
        assert all(Path(p).is_file() for p in rendered)
        return ReviewReport(verdict=verdict, overall=10, checks_run=["rendered_page_analysis"])

    before = {p.name: p.read_bytes() for p in package.iterdir()}
    with patch("services.editor_in_chief_ebook.review_ebook", side_effect=review) as reviewer:
        result = orch._run_export(data, 99)
    assert reviewer.call_count == 1, "one-button completion bypassed the final quality review"
    assert result["export_ready"] is ready
    assert result["editor_in_chief"]["verdict"] == verdict
    assert result["editor_in_chief"]["pdf_sha256"] == hashlib.sha256(before["ebook.pdf"]).hexdigest()
    assert result["content"] == "Preserved approved text"
    assert all(not Path(p).exists() for p in rendered), "review must remove its temporary page images"
    assert {p.name: p.read_bytes() for p in package.iterdir()} == before


def test_reviewer_failure_cannot_leave_an_old_pass_or_mark_a_book_ready(export_candidate):
    data, _ = export_candidate
    data["editor_in_chief"] = {"verdict": VERDICT_PASS, "pdf_sha256": "old-pdf"}
    rendered = []

    def unavailable(candidate):
        rendered.extend(candidate["page_images"])
        raise RuntimeError("review unavailable")

    with patch("services.editor_in_chief_ebook.review_ebook", side_effect=unavailable):
        result = orch._run_export(data, 99)
    assert not result["export_ready"], "a failed quality review must not advertise a finished book"
    assert result["editor_in_chief"]["verdict"] != VERDICT_PASS
    assert rendered and all(not Path(p).exists() for p in rendered)


def test_missing_pdf_cannot_be_editorially_ready(export_candidate):
    data, package = export_candidate
    (package / "ebook.pdf").unlink()
    result = orch._run_export(data, 99)
    assert not result["export_ready"], "a preflight flag cannot substitute for reviewing the actual PDF"
    assert result["editor_in_chief"]["verdict"] != VERDICT_PASS


def test_pdf_metadata_reader_uses_document_identity_instead_of_bookmark_titles(tmp_path):
    from services.editor_in_chief_ebook import read_pdf_metadata

    path = tmp_path / "book.pdf"
    with fitz.open() as doc:
        doc.new_page()
        doc.set_metadata({"title": "A Gardener’s Guide", "author": "José Brown"})
        doc.set_toc([[1, "Contents", 1]])
        doc.save(path)
    metadata = read_pdf_metadata(str(path))
    assert metadata["Title"] == "A Gardener’s Guide"
    assert metadata["Author"] == "José Brown"


def test_final_book_assembly_keeps_metadata_and_bookmarks():
    from services.ebook_design_export import _add_chapter_bookmarks

    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "Chapter 1\nPlanning a Small Garden")
        doc.set_metadata({"title": "A Small Garden", "author": "Lonnie Brown"})
        original = doc.tobytes()
    final = _add_chapter_bookmarks(original, ["Planning a Small Garden"])
    with fitz.open(stream=final, filetype="pdf") as doc:
        assert doc.metadata["title"] == "A Small Garden"
        assert doc.metadata["author"] == "Lonnie Brown"
        assert doc.get_toc(), "metadata must not be preserved at the expense of navigation"


def test_shared_review_detects_a_different_pdf_inside_the_real_zip(export_candidate):
    from services.ebook_completion_quality import review_exported_ebook

    data, package = export_candidate
    with zipfile.ZipFile(package / "package.zip", "w") as archive:
        archive.writestr("ebook.pdf", b"different PDF")
    report = review_exported_ebook(data, package_dir=str(package))
    assert report["verdict"] != VERDICT_PASS
    assert "PKG_ZIP_PDF_MISMATCH" in {f["code"] for f in report["findings"]}
    assert (package / "ebook.pdf").is_file(), "retain the candidate for inspection"


def test_incomplete_render_analysis_cannot_receive_a_pass(export_candidate):
    from services.editor_in_chief_ebook import review_ebook

    _, package = export_candidate
    candidate = {"page_images": [str(package / "missing.png")],
                 "pdf_path": str(package / "ebook.pdf")}
    with patch("services.editor_in_chief_ebook.analyse_rendered_pages",
               return_value={"available": False, "pages": []}):
        report = review_ebook(candidate)
    assert report.verdict != VERDICT_PASS
    assert "PAGE_ANALYSIS_INCOMPLETE" in {f.code for f in report.findings}


def test_acceptance_chapters_satisfy_the_existing_originality_rule():
    from types import SimpleNamespace
    from services.ebook import fixture_one_chapter
    from services.editor_in_chief import check_self_duplication

    chapter = SimpleNamespace(title="Why Mindfulness Matters", order=1,
                              purpose="Help beginners build a daily mindfulness practice suitable for beginners.")
    manuscript = fixture_one_chapter(SimpleNamespace(), chapter)["chapter"]
    assert check_self_duplication(manuscript) == []


def test_quality_failure_does_not_repeat_export_without_explicit_resume(export_candidate, monkeypatch):
    import database

    data, _ = export_candidate
    data["ebook_workspace"] = {"rail": {stage: {"status": "approved"}
                                         for stage in orch.STAGES if stage != "export"}}
    project = database.create_project("Quality candidate", "ebook", data)
    pid = project["id"]
    try:
        from services.editor_in_chief import Finding, KIND_OBJECTIVE, SEV_CRITICAL
        report = ReviewReport(verdict=VERDICT_CORRECTION,
                              findings=[Finding("PAGE_BLANK", "interior_design", SEV_CRITICAL,
                                                KIND_OBJECTIVE, "An interior page is blank.")])
        with patch("services.editor_in_chief_ebook.review_ebook", return_value=report) as reviewer:
            failed = orch.advance_build(pid)
            assert not failed["finished"] and failed["failed"]
            assert "An interior page is blank" in failed["message"]
            again = orch.advance_build(pid)
            assert again["failed"] and reviewer.call_count == 1
        stored = database.get_project(pid)["data"]
        assert stored["content"] == data["content"]
        assert stored["editor_in_chief"]["findings"][0]["code"] == "PAGE_BLANK"
    finally:
        database.delete_project(pid)


def test_review_uses_verified_source_when_factory_copy_is_on_another_machine(tmp_path):
    from PIL import Image
    from services.editor_in_chief_ebook import collect_ebook_candidate
    image = tmp_path / "source.png"
    Image.new("RGB", (100, 100), "green").save(image)
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    data = {"visual_plan": {"chapters": [{"chapter": "A", "aids": [{
        "type": "photo", "asset_path": str(image), "sha256": digest,
        "factory_asset_path": str(tmp_path / "retired-builder" / "img.png")
    }]}]}}
    before = copy.deepcopy(data)
    candidate = collect_ebook_candidate(data, package_dir=str(tmp_path))
    assert candidate["assets"][0]["_info"]["exists"] is True
    assert candidate["assets"][0]["path"] == str(image)
    assert data == before


@pytest.mark.parametrize('damage', ['', 'pdf_differs', 'broken_zip', 'missing_zip', 'unsafe_id'])
def test_preserved_draft_downloads_require_matching_real_files(tmp_path, monkeypatch, damage):
    import services.packaging as packaging
    from services.ebook_saved_downloads import saved_downloads
    monkeypatch.setattr(packaging, 'EXPORTS_DIR', str(tmp_path))
    folder = tmp_path / 'preserved'
    folder.mkdir()
    pdf = b'%PDF-1.4\noriginal draft\n%%EOF'
    (folder / 'ebook.pdf').write_bytes(pdf)
    with zipfile.ZipFile(folder / 'package.zip', 'w') as z:
        z.writestr('ebook.pdf', b'%PDF different' if damage == 'pdf_differs' else pdf)
    if damage == 'broken_zip':
        (folder / 'package.zip').write_bytes(b'bad zip')
    if damage == 'missing_zip':
        (folder / 'package.zip').unlink()
    before = {p.name: p.read_bytes() for p in folder.iterdir()}
    data = {'package_id': '../preserved' if damage == 'unsafe_id' else 'preserved'}
    result = saved_downloads(data)
    assert bool(result) == (not damage)
    if result:
        assert set(result) == {'pdf', 'zip'}
    assert {p.name: p.read_bytes() for p in folder.iterdir()} == before
