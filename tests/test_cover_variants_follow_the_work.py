"""v1.8.13 -- the approved cover's images follow the work to any machine.

Approval and preflight asked whether a cover variant PNG was on the local
disk. On the builder it never is, so an approved cover was refused with
"This photo does not leave enough room for readable cover text. Please
choose another photo." -- advice to replace a photograph that was fine.
These tests prove the files are fetched back, and that the two different
problems no longer share one message.
"""
from __future__ import annotations

import hashlib
import os

import pytest

import services.ebook_photo_cover as pc

PNG = b"\x89PNG\r\n\x1a\n cover variant"
PDF = b"%PDF-1.4 cover variant"


def _cover(tmp_path, *, quality_pass=True):
    base = tmp_path / "pkg" / "variants"
    row = {
        "layout_id": pc.LAYOUT_IDS[0],
        "png_path": str(base / "a.png"),
        "pdf_path": str(base / "a.pdf"),
        "thumb_path": str(base / "a_thumb.png"),
        "png_digest": hashlib.sha256(PNG).hexdigest(),
        "digest": hashlib.sha256(PDF).hexdigest(),
        "quality": {"pass": quality_pass, "findings": []},
    }
    return {"workflow": "photo_backed", "selected_layout": pc.LAYOUT_IDS[0],
            "cover_digest": row["digest"], "variants": {pc.LAYOUT_IDS[0]: row}}


def _storage(mapping):
    def read(path, project_id):
        return mapping.get(os.path.basename(str(path)))
    return read


def test_variant_files_are_fetched_back(tmp_path, monkeypatch):
    cover = _cover(tmp_path)
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk",
                        _storage({"a.png": PNG, "a.pdf": PDF}))
    assert pc.recover_variant_files(cover, project_id=5) == 2
    row = cover["variants"][pc.LAYOUT_IDS[0]]
    assert open(row["png_path"], "rb").read() == PNG
    assert open(row["pdf_path"], "rb").read() == PDF


def test_a_file_that_is_already_here_is_not_refetched(tmp_path, monkeypatch):
    cover = _cover(tmp_path)
    row = cover["variants"][pc.LAYOUT_IDS[0]]
    os.makedirs(os.path.dirname(row["png_path"]), exist_ok=True)
    open(row["png_path"], "wb").write(PNG)
    asked: list[str] = []

    def read(path, project_id):
        asked.append(os.path.basename(str(path)))
        return None

    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk", read)
    pc.recover_variant_files(cover, project_id=5)
    assert "a.png" not in asked


def test_bytes_that_do_not_match_the_recorded_digest_are_refused(tmp_path, monkeypatch):
    cover = _cover(tmp_path)
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk",
                        _storage({"a.png": b"a different image", "a.pdf": PDF}))
    pc.recover_variant_files(cover, project_id=5)
    assert not os.path.exists(cover["variants"][pc.LAYOUT_IDS[0]]["png_path"])


def test_recovery_never_raises(tmp_path, monkeypatch):
    cover = _cover(tmp_path)

    def boom(path, project_id):
        raise RuntimeError("storage is down")

    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk", boom)
    assert pc.recover_variant_files(cover, project_id=5) == 0


def test_an_empty_cover_is_not_an_error():
    assert pc.recover_variant_files({}, project_id=5) == 0
    assert pc.recover_variant_files({"variants": {}}, project_id=5) == 0


def test_missing_files_never_tell_the_customer_to_change_photograph(tmp_path, monkeypatch):
    """The whole point: a fine photograph must not be blamed."""
    cover = _cover(tmp_path, quality_pass=True)
    data = {"cover_design": cover, "title": "T", "subtitle": "S", "author": "A"}
    cover.update({"title": "T", "subtitle": "S", "author": "A"})
    monkeypatch.setattr(pc, "verify_source", lambda *a, **k: {})
    monkeypatch.setattr(pc, "_approved_identity",
                        lambda d: {"title": "T", "subtitle": "S", "author": "A", "series": ""})
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk", lambda path, pid: None)
    with pytest.raises(pc.PhotoCoverError) as err:
        pc.assert_photo_cover_approvable(data, project_id=5)
    assert str(err.value) == pc.COVER_FILES_UNAVAILABLE_MESSAGE
    assert "choose another photo" not in str(err.value).lower()


def test_a_genuinely_unusable_photograph_still_says_so(tmp_path, monkeypatch):
    cover = _cover(tmp_path, quality_pass=False)
    data = {"cover_design": cover}
    cover.update({"title": "T", "subtitle": "S", "author": "A"})
    monkeypatch.setattr(pc, "verify_source", lambda *a, **k: {})
    monkeypatch.setattr(pc, "_approved_identity",
                        lambda d: {"title": "T", "subtitle": "S", "author": "A", "series": ""})
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk", lambda path, pid: None)
    with pytest.raises(pc.PhotoCoverError) as err:
        pc.assert_photo_cover_approvable(data, project_id=5)
    assert str(err.value) == pc.NO_SAFE_COVER_MESSAGE


def test_approval_recovers_the_files_and_proceeds(tmp_path, monkeypatch):
    cover = _cover(tmp_path)
    cover.update({"title": "T", "subtitle": "S", "author": "A"})
    data = {"cover_design": cover}
    monkeypatch.setattr(pc, "verify_source", lambda *a, **k: {})
    monkeypatch.setattr(pc, "_approved_identity",
                        lambda d: {"title": "T", "subtitle": "S", "author": "A", "series": ""})
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk",
                        _storage({"a.png": PNG, "a.pdf": PDF}))
    try:
        pc.assert_photo_cover_approvable(data, project_id=5)
    except pc.PhotoCoverError as exc:
        # It may still stop on a later check of this stub cover, but never
        # on the two "no usable cover" messages -- the files are here now.
        assert str(exc) not in (pc.NO_SAFE_COVER_MESSAGE, pc.COVER_FILES_UNAVAILABLE_MESSAGE), exc
    assert os.path.isfile(cover["variants"][pc.LAYOUT_IDS[0]]["png_path"])


def test_preflight_reports_missing_files_under_their_own_code(tmp_path, monkeypatch):
    cover = _cover(tmp_path)
    cover.update({"title": "T", "subtitle": "S", "author": "A",
                  "source": {"path": "x", "sha256": "y"}})
    data = {"cover_design": cover}
    monkeypatch.setattr(pc, "verify_source", lambda *a, **k: {})
    monkeypatch.setattr(pc, "_approved_identity",
                        lambda d: {"title": "T", "subtitle": "S", "author": "A", "series": ""})
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk", lambda path, pid: None)
    codes = [code for code, _ in pc.photo_cover_preflight_failures(data, project_id=5)]
    assert "cover_files_unavailable" in codes
    assert "unreadable_cover_text" not in codes
