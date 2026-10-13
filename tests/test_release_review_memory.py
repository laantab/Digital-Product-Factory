"""Keep real PDF checks while bounding the website's native image buffers."""
import threading
from concurrent.futures import ThreadPoolExecutor

import fitz

from services import ebook_release_review as rr
from tests.test_release_review_container_gardening import _book


def test_large_photo_analysis_is_bounded_but_resolution_uses_native_pixels(monkeypatch):
    import hashlib
    import io
    import zipfile
    from PIL import Image

    with Image.new("RGB", (2400, 1600), "#38694c") as image:
        buffer = io.BytesIO()
        image.save(buffer, "PNG")
    raw = buffer.getvalue()
    with fitz.open() as document:
        document.new_page()
        page = document.new_page()
        page.insert_image(fitz.Rect(54, 100, 558, 436), stream=raw)
        pdf = document.tobytes()
    aid = {"visual_id": "native-photo", "type": "photo", "source": "pexels",
           "sha256": hashlib.sha256(raw).hexdigest(), "chapter": "Test"}
    bundle_buffer = io.BytesIO()
    with zipfile.ZipFile(bundle_buffer, "w") as bundle:
        bundle.writestr("ebook.pdf", pdf)
        bundle.writestr("visuals/native-photo.png", raw)
    real_check = rr._check_photo
    checked = []

    def check(review, planned, visual, image, placed_width, zip_raw):
        checked.append((visual.width, visual.height, image.width, image.height))
        return real_check(review, planned, visual, image, placed_width, zip_raw)

    monkeypatch.setattr(rr, "_check_photo", check)
    review = rr.review_release({"visual_plan": {"chapters": [
        {"chapter": "Test", "aids": [aid]}]}}, pdf, bundle_buffer.getvalue())
    assert checked == [(2400, 1600, 1200, 800)]
    assert not any(f.code in {"PHOTO_LOW_RESOLUTION", "PHOTO_NOT_APPROVED_FILE"}
                   for f in review.findings)


def test_real_review_extracts_spans_without_copying_embedded_photos(monkeypatch):
    data, pdf, bundle = _book()
    real = fitz.Page.get_text
    span_calls = []
    real_shrink = fitz.TOOLS.store_shrink
    cache_releases = []

    def shrink(percent):
        cache_releases.append(percent)
        return real_shrink(percent)

    def text(page, *args, **kwargs):
        if args and args[0] == "dict":
            assert not kwargs["flags"] & fitz.TEXT_PRESERVE_IMAGES
            span_calls.append(page.number)
        return real(page, *args, **kwargs)

    monkeypatch.setattr(fitz.Page, "get_text", text)
    monkeypatch.setattr(fitz.TOOLS, "store_shrink", shrink)
    review = rr.review_release(data, pdf, bundle)
    assert len(span_calls) == 7
    assert len(review.visuals) == 6
    assert not [f for f in review.findings if f.level == rr.HARD]
    assert review.status == rr.STATUS_HUMAN
    assert cache_releases == [100] * 15


def test_pdf_is_closed_even_when_a_check_raises(monkeypatch):
    data, pdf, bundle = _book()
    real = fitz.open
    documents = []
    memory_releases = []

    def release_memory():
        memory_releases.append([doc.is_closed for doc in documents])

    def opened(*args, **kwargs):
        doc = real(*args, **kwargs)
        documents.append(doc)
        return doc

    def fail(*args, **kwargs):
        raise RuntimeError("interrupted check")

    monkeypatch.setattr(fitz, "open", opened)
    monkeypatch.setattr(rr, "_release_review_memory", release_memory)
    monkeypatch.setattr(rr, "_page_images", fail)
    import pytest
    with pytest.raises(RuntimeError, match="interrupted check"):
        rr.review_release(data, pdf, bundle)
    assert len(documents) == 1 and documents[0].is_closed
    assert memory_releases == [[], [True]]


def test_weighted_contrast_matches_exact_pixel_sort():
    from PIL import Image

    with Image.new('RGB', (80, 60)) as image:
        image.putdata([(i % 256, (i * 13) % 256, (i * 31) % 256)
                       for i in range(80 * 60)])
        pixels = sorted(image.getdata(), key=rr._luminance)
        ink, bg = pixels[int(len(pixels) * .01)], pixels[int(len(pixels) * .6)]
        hi, lo = sorted([rr._luminance(ink), rr._luminance(bg)], reverse=True)
        assert rr.text_contrast(image) == (hi + .05) / (lo + .05)


def test_contrast_analysis_uses_weighted_colours_not_per_pixel_python_list(monkeypatch):
    from PIL import Image

    def forbidden(*args, **kwargs):
        raise AssertionError('Full pixel list allocation is not needed for exact contrast.')

    monkeypatch.setattr(Image.Image, 'getdata', forbidden)
    with Image.new('RGB', (2800, 1800), 'white') as image:
        image.paste('black', (0, 0, 2800, 100))
        assert rr.text_contrast(image) > rr.MIN_CONTRAST


def test_parallel_requests_do_not_overlap_native_book_scans(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    active = []

    def scan(*args, **kwargs):
        active.append(threading.get_ident())
        assert len(active) == 1
        entered.set()
        assert release.wait(3)
        active.pop()
        return rr.Review(status=rr.STATUS_UNVERIFIED)

    monkeypatch.setattr(rr, "_review_release", scan)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(rr.review_release, {}, None, None)
        assert entered.wait(3)
        second = pool.submit(rr.review_release, {}, None, None)
        release.set()
        assert first.result().status == second.result().status == rr.STATUS_UNVERIFIED


def test_timeline_numbers_distinguish_milestones_without_disabling_duplicate_checks():
    aid = {"title": "Eco makeover timeline", "items": [
        "First 30 days - Renters and homeowners",
        "First 90 days - Mostly homeowners, plus renters with permission",
        "First 365 days - Homeowners and long-term planners",
    ]}
    assert not rr.chart_wording_findings(aid, page=48, chapter="Action plan")
    aid["items"] = ["First 30 days - Renters and homeowners"] * 2
    assert any(f.code == "CHART_REPEATED_POINTS" for f in rr.chart_wording_findings(
        aid, page=48, chapter="Action plan"))
