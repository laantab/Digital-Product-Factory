"""Keep real PDF checks while bounding the website's native image buffers."""
import threading
from concurrent.futures import ThreadPoolExecutor

import fitz

from services import ebook_release_review as rr
from tests.test_release_review_container_gardening import _book


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

    def opened(*args, **kwargs):
        doc = real(*args, **kwargs)
        documents.append(doc)
        return doc

    def fail(*args, **kwargs):
        raise RuntimeError("interrupted check")

    monkeypatch.setattr(fitz, "open", opened)
    monkeypatch.setattr(rr, "_page_images", fail)
    import pytest
    with pytest.raises(RuntimeError, match="interrupted check"):
        rr.review_release(data, pdf, bundle)
    assert len(documents) == 1 and documents[0].is_closed


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
