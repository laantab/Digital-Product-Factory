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


def test_57_page_review_has_bounded_native_peak_rss(tmp_path):
    """Guard MuPDF/native allocations, which tracemalloc cannot measure.

    This runs a realistic illustrated 57-page PDF/ZIP review in a fresh
    process on Linux, separate from pytest's resident memory. It uses
    deterministic local files and makes no provider calls.
    """
    import json
    import subprocess
    import sys

    import pytest

    if sys.platform != "linux":
        pytest.skip("ru_maxrss is compared in Linux KiB")

    pdf_path = tmp_path / "ebook.pdf"
    zip_path = tmp_path / "package.zip"
    photo_paths = []
    with fitz.open() as doc:
        for index in range(57):
            page = doc.new_page()
            page.insert_text((72, 82), f"Winter chapter page {index + 1}", fontsize=16)
            if index < 12:
                # Unique, uncompressible images exercise the real native
                # image-decoding path, rather than tiny repeated icons.
                raw = os.urandom(600 * 600 * 3)
                photo = Image.frombytes("RGB", (600, 600), raw)
                output = io.BytesIO()
                photo.save(output, format="PNG", compress_level=0)
                photo.close()
                image_bytes = output.getvalue()
                page.insert_image(fitz.Rect(72, 125, 425, 425), stream=image_bytes)
                image_path = tmp_path / f"photo-{index}.png"
                image_path.write_bytes(image_bytes)
                photo_paths.append(image_path)
                del raw, image_bytes
        doc.save(str(pdf_path), garbage=4, deflate=True)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.write(pdf_path, "ebook.pdf")
        for photo_path in photo_paths:
            archive.write(photo_path, "visuals/" + photo_path.name)

    # The child measures only the reviewer, not construction of the fixture.
    child = """
import gc
import json
import resource
import sys
from services.ebook_release_review import review_release

with open(sys.argv[1], 'rb') as stream:
    pdf = stream.read()
with open(sys.argv[2], 'rb') as stream:
    package = stream.read()
gc.collect()
baseline = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
review = review_release({}, pdf, package)
peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(json.dumps({
    'baseline_kib': baseline,
    'peak_kib': peak,
    'checks': review.checks_run,
    'errors': [finding.code for finding in review.findings
               if finding.code in ('PDF_UNOPENABLE', 'ZIP_UNOPENABLE',
                                   'ZIP_PDF_DIFFERS')],
}))
"""
    env = dict(os.environ)
    env.update({
        "FACTORY_TEST_MODE": "1",
        "OPENAI_API_KEY": "",
        "ANTHROPIC_API_KEY": "",
        "TAVILY_API_KEY": "",
        "PEXELS_API_KEY": "",
        "UNSPLASH_ACCESS_KEY": "",
    })
    result = subprocess.run(
        [sys.executable, "-c", child, str(pdf_path), str(zip_path)],
        cwd=str(__import__("pathlib").Path(__file__).resolve().parents[1]),
        env=env, capture_output=True, text=True, timeout=120, check=True,
    )
    metrics = json.loads(result.stdout.strip().splitlines()[-1])
    assert not metrics["errors"], metrics
    assert "files_open" in metrics["checks"]
    assert "zip_pdf_identical" in metrics["checks"]
    # Linux ru_maxrss is KiB. The standalone 512-MiB web instance also needs
    # space for Gunicorn, Flask, request buffers and concurrent requests.
    assert metrics["peak_kib"] < 420 * 1024, metrics
    assert metrics["peak_kib"] - metrics["baseline_kib"] < 260 * 1024, metrics
