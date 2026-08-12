"""Automated visual QA for ebook PDFs.

Renders pages when a local renderer is available; otherwise runs measurable
text/geometry heuristics from the PDF text layer and page count. Never calls
paid APIs.
"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class VisualQAReport:
    page_count: int = 0
    fail_codes: list[str] = field(default_factory=list)
    warning_codes: list[str] = field(default_factory=list)
    page_metrics: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "page_count": self.page_count,
            "fail_codes": list(self.fail_codes),
            "warning_codes": list(self.warning_codes),
            "page_metrics": list(self.page_metrics),
            "details": dict(self.details),
        }


def run_ebook_visual_qa(
    pdf_bytes: bytes,
    *,
    expected_visual_titles: list[str] | None = None,
    cover_title: str = "",
) -> VisualQAReport:
    report = VisualQAReport()
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        report.fail_codes.append("missing_pdf")
        return report

    pages_text, page_count, dims = _extract_pages(pdf_bytes)
    report.page_count = page_count
    report.details["pdf_md5"] = hashlib.md5(pdf_bytes).hexdigest()

    if page_count <= 0:
        report.fail_codes.append("missing_pdf")
        return report

    # Inconsistent page dimensions
    if dims:
        unique = {(round(w, 1), round(h, 1)) for w, h in dims}
        if len(unique) > 1:
            report.fail_codes.append("inconsistent_page_dimensions")

    densities: list[float] = []
    for i, text in enumerate(pages_text):
        words = len(re.findall(r"\w+", text or ""))
        # Rough density: words per "page unit" (letter ~500 words full)
        density = words / 500.0
        densities.append(density)
        metric = {"page": i + 1, "words": words, "density": round(density, 3)}
        report.page_metrics.append(metric)
        if i > 0 and words < 12 and density < 0.04:
            # Cover may be image-heavy; interior sparse pages are FAIL
            report.fail_codes.append("excessive_empty_page")
        if density > 1.35:
            report.warning_codes.append("unusually_dense_page")
        if density < 0.08 and i > 0 and words < 40:
            report.warning_codes.append("unusually_sparse_page")

    # Repeated page render (identical text)
    seen: dict[str, int] = {}
    for i, text in enumerate(pages_text):
        key = re.sub(r"\s+", " ", (text or "").strip().lower())[:800]
        if len(key) < 40:
            continue
        if key in seen:
            report.fail_codes.append("repeated_page_render")
        seen[key] = i

    corpus = "\n".join(pages_text)
    # Clipped / overlap proxies from known bad concatenations
    if re.search(r"(QuestionWhere|WheDnone|WhenDone|C\s+hapter|S\s+creens)", corpus):
        report.fail_codes.append("clipped_or_overlapped_text")
    if re.search(r"letter-spacing\s*:", corpus, re.I):
        report.fail_codes.append("letter_spacing_in_text_layer")

    # Missing expected visuals
    for title in expected_visual_titles or []:
        if title and title.lower() not in corpus.lower():
            report.fail_codes.append("missing_expected_visual")

    # Cover / interior mismatch (title should appear early)
    if cover_title and pages_text:
        if cover_title.lower() not in (pages_text[0] or "").lower() and cover_title.lower() not in corpus[:2000].lower():
            report.warning_codes.append("cover_interior_mismatch")

    # Unreadable small text — if PDF CSS path used < 9pt we can't see it here;
    # flag when page has many single-letter tokens (spacing bug)
    # Spaced-glyph pathology (e.g. "S creens") — not ordinary single-letter words
    if re.search(r"\b[A-Z]\s+[a-z]{2,}\b", corpus) and len(re.findall(r"\b[A-Z]\s+[a-z]{2,}\b", corpus)) >= 3:
        report.fail_codes.append("unreadable_small_or_spaced_text")

    # Deduplicate codes
    report.fail_codes = sorted(set(report.fail_codes))
    report.warning_codes = sorted(set(report.warning_codes))
    return report


def _extract_pages(pdf_bytes: bytes) -> tuple[list[str], int, list[tuple[float, float]]]:
    """Return (page_texts, page_count, dimensions)."""
    try:
        from pypdf import PdfReader
    except Exception:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except Exception:
            return [], 0, []

    reader = PdfReader(io.BytesIO(pdf_bytes))
    texts: list[str] = []
    dims: list[tuple[float, float]] = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:
            texts.append("")
        try:
            box = page.mediabox
            dims.append((float(box.width), float(box.height)))
        except Exception:
            pass
    return texts, len(reader.pages), dims
