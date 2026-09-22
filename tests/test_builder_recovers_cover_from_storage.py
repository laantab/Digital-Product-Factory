"""v1.8.11 -- the builder can finish a book whose files it never wrote.

Every builder run starts with an empty disk. The machine that rendered the
approved cover and the interior pictures is gone by the time preflight
re-renders the bundle, so export refused a book the customer had already
approved ("Photo-backed cover PDF is missing"). The cover files were
published to storage when they were made; these tests prove the export path
fetches them back, writes them where the renderer expects them, and still
reports an honest failure when storage has nothing either.
"""
from __future__ import annotations

import os

import services.ebook_design_export as dex


def test_cover_pdf_read_from_this_machine_when_the_file_is_here(tmp_path):
    path = tmp_path / "cover.pdf"
    path.write_bytes(b"%PDF-1.4 local")
    data = {"_project_id": 5}
    cover = {"workflow": "photo_backed", "local_cover_pdf": str(path)}
    assert dex._approved_cover_pdf_bytes(data, cover) == b"%PDF-1.4 local"


def test_cover_pdf_recovered_from_storage_when_the_disk_is_empty(tmp_path, monkeypatch):
    missing = tmp_path / "gone" / "cover.pdf"
    seen: list[tuple[str, int]] = []

    def fake(path: str, project_id: int | None):
        seen.append((str(path), int(project_id or 0)))
        return b"%PDF-1.4 stored"

    monkeypatch.setattr(
        "services.ebook_photo_cover.cover_bytes_from_storage_or_disk", fake, raising=True
    )
    data = {"_project_id": 5}
    cover = {"workflow": "photo_backed", "local_cover_pdf": str(missing)}
    assert dex._approved_cover_pdf_bytes(data, cover) == b"%PDF-1.4 stored"
    assert seen == [(str(missing), 5)]


def test_recovered_cover_is_written_where_the_renderer_looks(tmp_path, monkeypatch):
    missing = tmp_path / "gone" / "cover.pdf"
    monkeypatch.setattr(
        "services.ebook_photo_cover.cover_bytes_from_storage_or_disk",
        lambda path, project_id: b"%PDF-1.4 stored",
        raising=True,
    )
    dex._approved_cover_pdf_bytes({"_project_id": 5}, {"local_cover_pdf": str(missing)})
    assert os.path.isfile(missing)
    assert missing.read_bytes() == b"%PDF-1.4 stored"


def test_missing_everywhere_still_reports_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.ebook_photo_cover.cover_bytes_from_storage_or_disk",
        lambda path, project_id: None,
        raising=True,
    )
    out = dex._approved_cover_pdf_bytes({"_project_id": 5}, {"local_cover_pdf": str(tmp_path / "x.pdf")})
    assert out == b""


def test_no_project_id_means_no_storage_guess(tmp_path, monkeypatch):
    def explode(path: str, project_id: int | None):
        raise AssertionError("storage must not be read without a project id")

    monkeypatch.setattr(
        "services.ebook_photo_cover.cover_bytes_from_storage_or_disk", explode, raising=True
    )
    assert dex._approved_cover_pdf_bytes({}, {"local_cover_pdf": str(tmp_path / "x.pdf")}) == b""


def test_storage_failure_never_escapes(tmp_path, monkeypatch):
    def boom(path: str, project_id: int | None):
        raise RuntimeError("storage is down")

    monkeypatch.setattr(
        "services.ebook_photo_cover.cover_bytes_from_storage_or_disk", boom, raising=True
    )
    assert dex._approved_cover_pdf_bytes({"_project_id": 5}, {"local_cover_pdf": str(tmp_path / "x.pdf")}) == b""


def test_bundle_project_id_survives_odd_values():
    assert dex._bundle_project_id({"_project_id": "5"}) == 5
    assert dex._bundle_project_id({"_project_id": None}) == 0
    assert dex._bundle_project_id({"_project_id": "not a number"}) == 0
    assert dex._bundle_project_id({}) == 0


def test_bundle_localises_pictures_before_rendering(monkeypatch):
    """The pictures come from storage too, for exactly the same reason."""
    calls: list[int] = []

    def fake_localize(data, project_id=0):
        calls.append(int(project_id))
        return 0

    monkeypatch.setattr(
        "services.ebook_visual_pipeline.localize_visual_plan", fake_localize, raising=True
    )
    monkeypatch.setattr(dex, "require_quality_pass", lambda _data: None, raising=True)
    # An empty project has no bound design, so the render stops right after
    # localisation -- which is the point being proved.
    try:
        dex.render_designed_bundle({"_project_id": 5})
    except ValueError:
        pass
    assert calls == [5]


def test_export_reads_the_cover_through_the_new_helper_only():
    """One helper reads the approved cover, so disk and storage cannot drift."""
    src = open(dex.__file__, encoding="utf-8").read()
    assert src.count('cover.get("local_cover_pdf")') == 0
    assert src.count('(cover or {}).get("local_cover_pdf")') == 1
    assert "_approved_cover_pdf_bytes(data, cover)" in src
