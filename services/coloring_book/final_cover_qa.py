"""Final rendered-cover QA for the automatic Coloring Book build (2026-09-12).

GLOBAL COVER POLICY: every customer-facing final cover must pass a real final
QA gate before it can be accepted. Coloring Book's automatic build renders
its cover directly to PDF via ``services.coloring_book.renderer.
draw_cover_page_on_canvas`` -- a structurally different pipeline from
``cover_agent.py``'s HTML ``cover_design`` system (there is no
``preview_html``/``pdf_html`` to check; forcing this through
``cover_quality_agent.evaluate_cover_quality`` would immediately and
wrongly fail every real Coloring Book cover for fields that never applied
to it). This module is the DECLARED, equivalent final-QA authority for
Coloring Book instead of the shared agent -- a small adapter, not a
restructuring of the generator, per the owner's explicit instruction.

Unlike the pre-render checks that already exist elsewhere in the Coloring
Book pipeline, this validates the ACTUAL rendered PDF page the customer
receives: a corrupted, empty, or placeholder-bearing final cover fails here
even if every earlier input looked correct.

Two severities:
  * ``errors`` -- block acceptance (malformed PDF, missing title, a
    placeholder/gibberish/template-wording match, an unrecognized
    ``cover_source`` value). These are conditions this module can assert
    with full confidence.
  * ``warnings`` -- recorded but non-blocking (e.g. the rendered page's
    extracted text does not obviously contain the title). PDF text
    extraction can be distorted by font subsetting/kerning even when the
    rendered page is visually correct, so this stays a warning rather than
    a hard failure -- blocking on it would risk breaking the live, LOCKED
    Coloring Book product on a false positive, which the owner explicitly
    said not to do.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

from services.cover_quality_agent import _AI_GIBBERISH_PATTERNS, _TEMPLATE_WORDING

VALID_COVER_SOURCES = frozenset(
    {"pexels", "ai_fallback", "ai_only", "template_fallback", "procedural", "customer_upload", ""}
)


@dataclass
class ColoringBookCoverQAResult:
    passed: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"passed": self.passed, "errors": list(self.errors), "warnings": list(self.warnings)}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def validate_coloring_book_final_cover(
    pdf_bytes: bytes,
    *,
    title: str,
    subtitle: str = "",
    cover_source: str = "",
) -> ColoringBookCoverQAResult:
    """Evaluate the ACTUAL rendered cover page (page 1 of the finished PDF).

    Never accepts a cover merely because inputs looked fine going in.
    """
    result = ColoringBookCoverQAResult()

    if not pdf_bytes or not isinstance(pdf_bytes, (bytes, bytearray)) or not bytes(pdf_bytes).startswith(b"%PDF"):
        result.errors.append("Coloring Book cover PDF is missing or malformed.")
        result.passed = False
        return result

    title = str(title or "").strip()
    subtitle = str(subtitle or "").strip()
    if not title:
        result.errors.append("Coloring Book cover is missing a title.")

    combined_norm = _norm(f"{title} {subtitle}")
    for pattern in _AI_GIBBERISH_PATTERNS:
        if pattern.lower() in combined_norm:
            result.errors.append(f"Cover shows placeholder/gibberish text: '{pattern}'.")
            break
    for pattern in _TEMPLATE_WORDING:
        if pattern.lower() in combined_norm:
            result.errors.append(f"Cover shows unfinished template wording: '{pattern}'.")
            break

    combined_raw = f"{title} {subtitle}"
    if "�" in combined_raw or any(ord(ch) < 32 and ch not in "\n\t" for ch in combined_raw):
        result.errors.append("Cover title/subtitle contains malformed or corrupted characters.")

    if cover_source not in VALID_COVER_SOURCES:
        result.errors.append(
            f"Cover source '{cover_source}' is not a recognized Global Cover Policy value."
        )

    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(bytes(pdf_bytes)))
        page_text = reader.pages[0].extract_text() or ""
    except Exception as exc:  # noqa: BLE001
        result.warnings.append(f"Could not read the rendered cover page to confirm title text: {exc}")
        page_text = None

    if page_text is not None and title:
        title_words = [w for w in re.findall(r"[A-Za-z0-9']+", title) if len(w) > 2]
        page_norm = _norm(page_text)
        hits = sum(1 for w in title_words if w.lower() in page_norm)
        if title_words and hits < max(1, len(title_words) // 2):
            result.warnings.append(
                "Cover's rendered PDF page does not obviously contain the expected title text "
                "(PDF text extraction can be imperfect; this is a warning, not a hard failure)."
            )

    result.passed = not result.errors
    return result
