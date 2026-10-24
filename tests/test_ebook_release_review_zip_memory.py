"""Offline release-review ZIP memory and identity regressions.

No paid providers, customer records, or production files are accessed.
"""
import gc
import hashlib
import io
import os
import tracemalloc
import zipfile

import fitz
from PIL import Image

from services.ebook_release_review import review_release


def _pdf_with_photo(photo=None):
    doc = fitz.open()
    first = doc.new_page()
    first.insert_text((70, 90), "Winter Photo Guide", fontsize=20)
    if photo is not None:
        page = doc.new_page()
        page.insert_text((70, 80), "Chapter One", fontsize=18)
        page.insert_image(fitz.Rect(72, 120, 400, 380), stream=photo)
    pdf = doc.tobytes()
    doc.close()
    return pdf


def _package(pdf, photos):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("ebook.pdf", pdf)
        for name, raw in photos.items():
            zf.writestr("visuals/" + name + ".png", raw)
    return out.getvalue()


def test_review_reads_one_archive_visual_at_a_time():
    # Ten independent, incompressible PNGs reproduce the former eager
    # 12+ MB ZIP visual allocation without creating any production assets.
    photos = {}
    for i in range(10):
        pixels = os.urandom(650 * 650 * 3)
        image = Image.frombytes("RGB", (650, 650), pixels)
        out = io.BytesIO()
        image.save(out, format="PNG", compress_level=0)
        image.close()
        photos[f"sample-{i}"] = out.getvalue()
    total_visual_bytes = sum(map(len, photos.values()))
    assert total_visual_bytes > 12_000_000
    pdf = _pdf_with_photo()
    package = _package(pdf, photos)
    del photos
    gc.collect()

    tracemalloc.start()
    try:
        result = review_release({}, pdf, package)
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert "files_open" in result.checks_run
    assert not any(f.code in ("PDF_UNOPENABLE", "ZIP_UNOPENABLE") for f in result.findings)
    # The old dict of full ZIP image bytes necessarily exceeds this bound.
    # Streaming one image at a time leaves room for the 512 MiB web worker.
    assert peak < total_visual_bytes * 0.75, (
        f"ZIP images were retained during review: peak={peak:,}, "
        f"visual bytes={total_visual_bytes:,}"
    )


def test_photo_identity_gate_still_compares_exact_approved_zip_bytes():
    image = Image.new("RGB", (640, 480), (230, 215, 200))
    for x in range(0, 640, 30):
        for y in range(0, 480, 30):
            image.paste(((x * 3) % 255, (y * 7) % 255, (x + y) % 255),
                        (x, y, min(x + 15, 640), min(y + 15, 480)))
    out = io.BytesIO()
    image.save(out, format="PNG")
    image.close()
    photo = out.getvalue()
    pdf = _pdf_with_photo(photo)
    package = _package(pdf, {"winter-photo": photo})
    aid = {"visual_id": "winter-photo", "type": "photo", "source": "pexels",
           "sha256": hashlib.sha256(photo).hexdigest()}
    data = {"title": "Winter Photo Guide", "visual_plan": {"chapters": [
        {"chapter": "Chapter One", "aids": [aid]}]}}

    verified = review_release(data, pdf, package)
    assert any(v.visual_id == "winter-photo" and v.kind == "photo"
               for v in verified.visuals)
    assert not any(f.code == "PHOTO_NOT_APPROVED_FILE" for f in verified.findings)

    aid["sha256"] = hashlib.sha256(b"different approved file").hexdigest()
    rejected = review_release(data, pdf, package)
    assert any(f.code == "PHOTO_NOT_APPROVED_FILE" for f in rejected.findings)
