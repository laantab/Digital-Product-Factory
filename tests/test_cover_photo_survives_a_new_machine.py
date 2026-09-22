"""v1.8.12 -- the registered cover photograph survives a new machine.

The cover variants were published to storage; the photograph they are made
from was not. On a builder with an empty disk the final check therefore
reported "Cover photograph is missing" for a cover the customer had already
approved. These tests prove the photograph is published when it is
registered, is fetched back when it is not on this machine, and that a file
whose SHA-256 does not match the registered digest is refused rather than
quietly used.
"""
from __future__ import annotations

import hashlib
import os

import services.ebook_photo_cover as pc

PHOTO = b"\xff\xd8\xff\xe0 pretend jpeg bytes"
DIGEST = hashlib.sha256(PHOTO).hexdigest()


def _source(path, **kw):
    row = {"path": str(path), "sha256": DIGEST, "source_type": "pexels",
           "pexels": {"photo_id": "12916203"}}
    row.update(kw)
    return row


def test_a_photograph_already_here_is_left_alone(tmp_path, monkeypatch):
    path = tmp_path / "sources" / f"{DIGEST}.jpg"
    path.parent.mkdir()
    path.write_bytes(PHOTO)
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no fetch needed")))
    assert pc.recover_source_photo_file(_source(path), project_id=5, data={}) is True


def test_storage_brings_the_photograph_back(tmp_path, monkeypatch):
    path = tmp_path / "sources" / f"{DIGEST}.jpg"
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk", lambda p, pid: PHOTO)
    assert pc.recover_source_photo_file(_source(path), project_id=5, data={}) is True
    assert path.read_bytes() == PHOTO


def test_storage_bytes_that_do_not_match_are_refused(tmp_path, monkeypatch):
    path = tmp_path / "sources" / f"{DIGEST}.jpg"
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk", lambda p, pid: b"a different photo")
    monkeypatch.setattr("services.ebook_pexels.fetch_pexels_photo",
                        lambda pid: {"photo_id": pid}, raising=False)
    monkeypatch.setattr("services.ebook_pexels.download_pexels_original",
                        lambda photo: b"also different", raising=False)
    assert pc.recover_source_photo_file(_source(path), project_id=5, data={}) is False
    assert not os.path.exists(path)


def test_the_free_pexels_original_is_the_second_try(tmp_path, monkeypatch):
    path = tmp_path / "sources" / f"{DIGEST}.jpg"
    asked: list[str] = []
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk", lambda p, pid: None)
    monkeypatch.setattr("services.ebook_pexels.fetch_pexels_photo",
                        lambda pid: asked.append(pid) or {"photo_id": pid}, raising=False)
    monkeypatch.setattr("services.ebook_pexels.download_pexels_original",
                        lambda photo: PHOTO, raising=False)
    published: list[str] = []
    monkeypatch.setattr(pc, "_publish_cover_files",
                        lambda data, *paths, project_id=None: published.extend(paths))
    assert pc.recover_source_photo_file(_source(path), project_id=5, data={}) is True
    assert path.read_bytes() == PHOTO
    assert asked == ["12916203"]
    assert published == [str(path)]      # the next machine gets it from storage


def test_a_changed_pexels_photograph_is_refused(tmp_path, monkeypatch):
    path = tmp_path / "sources" / f"{DIGEST}.jpg"
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk", lambda p, pid: None)
    monkeypatch.setattr("services.ebook_pexels.fetch_pexels_photo",
                        lambda pid: {"photo_id": pid}, raising=False)
    monkeypatch.setattr("services.ebook_pexels.download_pexels_original",
                        lambda photo: b"the photographer replaced it", raising=False)
    assert pc.recover_source_photo_file(_source(path), project_id=5, data={}) is False
    assert not os.path.exists(path)


def test_an_uploaded_photograph_never_goes_to_the_internet(tmp_path, monkeypatch):
    path = tmp_path / "sources" / f"{DIGEST}.jpg"
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk", lambda p, pid: None)
    monkeypatch.setattr("services.ebook_pexels.fetch_pexels_photo",
                        lambda pid: (_ for _ in ()).throw(AssertionError("upload is not Pexels")),
                        raising=False)
    src = _source(path, source_type="upload")
    src.pop("pexels")
    assert pc.recover_source_photo_file(src, project_id=5, data={}) is False


def test_recovery_never_raises(tmp_path, monkeypatch):
    path = tmp_path / "sources" / f"{DIGEST}.jpg"
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk",
                        lambda p, pid: (_ for _ in ()).throw(RuntimeError("storage is down")))
    assert pc.recover_source_photo_file(_source(path), project_id=5, data={}) is False


def test_verify_source_tries_recovery_before_calling_it_missing(tmp_path, monkeypatch):
    """The end-to-end point: a recovered photograph verifies like any other."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (900, 1200), (34, 90, 40)).save(buf, format="JPEG")
    real_photo = buf.getvalue()
    real_digest = hashlib.sha256(real_photo).hexdigest()

    pkg = tmp_path / "pkg"
    (pkg / "sources").mkdir(parents=True)
    path = pkg / "sources" / f"{real_digest}.jpg"
    monkeypatch.setattr(pc, "EXPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk", lambda p, pid: real_photo)
    source = {
        "path": str(path), "sha256": real_digest, "source_type": "pexels",
        "license_note": "Pexels License: free to use.", "project_id": 5,
        "pexels": {"photo_id": "12916203", "photographer": "A Photographer",
                   "sha256": real_digest, "project_id": 5},
    }
    pc.verify_source(source, project_id=5, data={"package_id": "pkg"})
    assert path.is_file()
    assert hashlib.sha256(path.read_bytes()).hexdigest() == real_digest


def test_a_missing_photograph_storage_cannot_supply_is_still_missing(tmp_path, monkeypatch):
    pkg = tmp_path / "pkg"
    (pkg / "sources").mkdir(parents=True)
    path = pkg / "sources" / f"{DIGEST}.jpg"
    monkeypatch.setattr(pc, "EXPORTS_DIR", str(tmp_path))
    monkeypatch.setattr(pc, "_cover_bytes_from_storage_or_disk", lambda p, pid: None)
    monkeypatch.setattr("services.ebook_pexels.fetch_pexels_photo",
                        lambda pid: {"photo_id": pid}, raising=False)
    monkeypatch.setattr("services.ebook_pexels.download_pexels_original",
                        lambda photo: None, raising=False)
    try:
        pc.verify_source(_source(path), project_id=5, data={"package_id": "pkg"})
        raise AssertionError("a photograph nobody has must not pass")
    except pc.PhotoCoverError as exc:
        assert "missing" in str(exc).lower()


def test_registering_a_photograph_publishes_it(tmp_path, monkeypatch):
    published: list[tuple] = []
    monkeypatch.setattr(pc, "_publish_cover_files",
                        lambda data, *paths, project_id=None: published.append((paths, project_id)))
    monkeypatch.setattr(pc, "_pkg_dir", lambda data: str(tmp_path))
    png = (b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    class _Img:
        size = (1200, 1600)

    monkeypatch.setattr(pc, "_open_rgb_bytes", lambda raw: _Img())
    pc._store_source_bytes(
        {"package_id": "pkg"}, png, source_type="upload", filename="photo.png",
        license_note="I own this photograph.", project_id=5,
    )
    assert published and published[0][1] == 5
    assert published[0][0][0].endswith(".png")
    assert "sources" in published[0][0][0]
