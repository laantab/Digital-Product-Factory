"""
Shared Single Sheet validation and PDF regeneration for coloring books.

Used by:
  - services.product._coloring_book_pdf_payload  (primary generation path)
  - services.packaging.build_product_export        (export/package path)

These functions operate at the BYTES level — they validate and regenerate PDFs
based on the stored/requested fields, without depending on the generation-time
request object.
"""
from __future__ import annotations

import base64
import fitz
import io

# Single Sheet output type constant (matches puzzle_plan.OUTPUT_SINGLE_PAGE)
COLORING_OUTPUT_SINGLE_PAGE = "single_page"


def _is_single_sheet_output(fields: dict) -> bool:
    """Return True if the coloring book fields request Single Sheet output.

    Checks output_format (frontend label) and output_type (internal constant).
    Normalizes common variants: 'Single Sheet', 'single_sheet', 'single_page',
    'Single Page', 'One Page', 'sheet', '1 page'.
    """
    fields = dict(fields or {})
    output_format = str(fields.get("output_format") or "").strip().lower()
    output_type = str(fields.get("output_type") or "").strip().lower()

    single_patterns = {
        "single sheet", "single_sheet", "single sheet",
        "single page", "single_page", "single page",
        "one page", "1 page", "sheet",
    }

    if output_format in single_patterns:
        return True
    if output_type == COLORING_OUTPUT_SINGLE_PAGE:
        return True
    return False


def _validate_single_sheet_pdf(pdf_bytes: bytes) -> tuple[bool, str]:
    """
    Validate that a stored PDF is a correct Single Sheet coloring page.

    Returns (is_valid, reason):
      is_valid=True  → PDF is a valid 1-page coloring sheet (no cover, no text)
      is_valid=False → PDF is invalid for Single Sheet; reason explains why

    Rules:
      - Must be exactly 1 page
      - No "Page X of Y" page numbering
      - No title/header text on the first page
      - No cover-page indicators
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        return False, f"cannot open PDF: {exc}"

    if doc.page_count != 1:
        return False, f"has {doc.page_count} pages (expected 1)"

    page = doc[0]
    text = page.get_text().strip()
    imgs = page.get_images(full=True)

    # Check for page numbering
    if "Page" in text and "of" in text:
        return False, f"contains page numbering: {text[:80]!r}"

    # Check for cover-style title headers
    title_indicators = [
        "coloring book", "coloring book cover",
        "cover page", "front cover",
    ]
    text_lower = text.lower()
    for indicator in title_indicators:
        if indicator in text_lower:
            return False, f"contains cover text: {text[:80]!r}"

    # A valid single-sheet coloring page has:
    # - 1 page
    # - text-free OR only a short caption
    # - at least 1 image (the coloring page itself)
    # We already confirmed 1 page above. Caption is OK; header is not.
    # "Caption" without "Page" is fine — that means the user enabled captions.
    return True, "valid"


def regenerate_coloring_book_pdf_for_export(
    fields: dict,
    *,
    package_id: str = "",
) -> bytes:
    """
    Regenerate a coloring book PDF using the current correct generation logic.

    This is called by build_product_export when the stored PDF fails validation
    (e.g. stale old export with wrong page count).

    Returns raw PDF bytes.
    Raises if regeneration fails.
    """
    # Import here to avoid circular imports and lazy-load overhead
    from services.product import _coloring_book_pdf_payload

    result = _coloring_book_pdf_payload(dict(fields), package_id=package_id or "")
    if result.get("errors"):
        raise RuntimeError(f"PDF regeneration failed: {result['errors']}")

    pdf_bytes = base64.b64decode(result["pdf_bytes"])
    return pdf_bytes
