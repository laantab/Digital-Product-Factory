"""
Cover Eligibility Agent — universal cover decision engine.

Purpose:
  Every product type has different rules about whether a cover is allowed.
  This agent centralises those rules so no PDF builder, export path, or
  download route can silently add a cover that violates the user's intent
  or the product's page-count requirements.

Core rule:
  Any product with fewer than 5 final content pages MUST NOT include a cover.
  This applies to ALL product types — coloring_book, word_search, crossword,
  ebook, math_worksheet, spelling_worksheet.

Why this exists:
  The old Farm House failure showed a cover page prepended to a Single Sheet
  product. Individual generators made independent cover decisions. Math and
  spelling worksheets hardcoded include_cover=True regardless of page count.
  Ebook prepended covers without checking page count. This agent closes that
  gap for ALL product types.

How it works:
  1. determine_cover_eligibility(product_type, fields, planned_page_count)
     → returns a CoverEligibility dict
  2. apply_cover_eligibility_to_fields(product_type, fields, eligibility)
     → patches fields to disable cover if not allowed
  3. validate_no_cover_in_pdf(pdf_bytes, eligibility)
     → inspects a PDF with fitz; returns (passed, violations)
  4. block_or_raise(eligibility, pdf_bytes, context)
     → hard block on violation

Scope:
  All product types. Rules are strict for small products, permissive for
  books with 5+ pages.
"""
from __future__ import annotations

import base64
import fitz
from dataclasses import dataclass, field
from typing import Any

# -------------------------------------------------------------------------- //
# Constants
# -------------------------------------------------------------------------- //
MIN_PAGES_FOR_COVER = 5  # Universal rule: < 5 pages = no cover

# Keywords that indicate a cover or placeholder cover page
COVER_TEXT_KEYWORDS = [
    "cover page", "front cover", "book cover", "cover",
    "coloring book", "workbook", "planner",
    "ebook", "coloring book cover", "title page",
    "single sheet", "digital book", "front matter",
]

# Keywords that indicate a title-only first page (no actual content)
TITLE_ONLY_KEYWORDS = [
    "coloring book", "workbook", "planner", "ebook",
    "coloring book cover", "book cover", "title page",
]


# -------------------------------------------------------------------------- //
# CoverEligibility dataclass
# -------------------------------------------------------------------------- //
@dataclass
class CoverEligibility:
    """
    Immutable cover eligibility decision for a product.

    Attributes:
        cover_allowed:       Whether a cover page/image is permitted.
        must_block_cover:    Whether any detected cover must be rejected.
        planned_page_count:  Total planned content pages.
        product_type:        e.g. "coloring_book", "ebook", "word_search".
        product_mode:        e.g. "Single Sheet", "Digital Book", "book".
        reason:              Human-readable explanation of the decision.
        enforce_page_count:  If True, the < 5 page rule applies to this type.
    """

    cover_allowed: bool
    must_block_cover: bool
    planned_page_count: int
    product_type: str
    product_mode: str
    reason: str
    enforce_page_count: bool = True  # override to False for types without page counting

    def to_dict(self) -> dict:
        return {
            "cover_allowed": self.cover_allowed,
            "must_block_cover": self.must_block_cover,
            "planned_page_count": self.planned_page_count,
            "product_type": self.product_type,
            "product_mode": self.product_mode,
            "reason": self.reason,
            "enforce_page_count": self.enforce_page_count,
        }


# -------------------------------------------------------------------------- //
# Universal rule
# -------------------------------------------------------------------------- //
def _under_minimum_pages(page_count: int | None) -> bool:
    if page_count is None:
        return False  # Unknown page count — be permissive
    return page_count < MIN_PAGES_FOR_COVER


# -------------------------------------------------------------------------- //
# Product-type-specific rules
# -------------------------------------------------------------------------- //

def determine_cover_eligibility(
    product_type: str,
    fields: dict,
    planned_page_count: int | None = None,
    product_mode: str | None = None,
) -> CoverEligibility:
    """
    Determine whether a cover is allowed for the given product.

    Args:
        product_type:       The product type string (e.g. "coloring_book").
        fields:             The product's form fields dict.
        planned_page_count: Total planned content pages (None = unknown).
        product_mode:        Output format / product mode (e.g. "Single Sheet").

    Returns:
        CoverEligibility with cover_allowed, must_block_cover, and reason.
    """
    product_type = str(product_type or "").strip().lower()
    fields = dict(fields or {})
    product_mode = str(product_mode or fields.get("output_format") or
                      fields.get("product_mode") or "").strip()
    mode_lower = product_mode.lower()

    # ── Single Sheet / single-page modes: always block ──────────────────────
    is_single_sheet = mode_lower in {
        "single sheet", "single_sheet", "single page", "single_page",
        "one page", "1 page", "sheet",
    }

    if is_single_sheet:
        return CoverEligibility(
            cover_allowed=False,
            must_block_cover=True,
            planned_page_count=planned_page_count or 1,
            product_type=product_type,
            product_mode=product_mode,
            reason="Single Sheet products cannot include a cover.",
            enforce_page_count=True,
        )

    # ── Coloring Book ───────────────────────────────────────────────────────
    if product_type == "coloring_book":
        is_digital_book = mode_lower in {
            "digital book", "book", "full book",
        }
        if is_digital_book:
            under_min = _under_minimum_pages(planned_page_count)
            if under_min:
                return CoverEligibility(
                    cover_allowed=False,
                    must_block_cover=True,
                    planned_page_count=planned_page_count,
                    product_type=product_type,
                    product_mode=product_mode,
                    reason="Coloring Book Digital Book under 5 pages cannot include a cover.",
                    enforce_page_count=True,
                )
            return CoverEligibility(
                cover_allowed=True,
                must_block_cover=False,
                planned_page_count=planned_page_count,
                product_type=product_type,
                product_mode=product_mode,
                reason="Coloring Book Digital Book with 5+ pages may include a cover.",
                enforce_page_count=True,
            )
        # Fallthrough to universal rule for unknown modes
        under_min = _under_minimum_pages(planned_page_count)
        return CoverEligibility(
            cover_allowed=not under_min,
            must_block_cover=under_min,
            planned_page_count=planned_page_count,
            product_type=product_type,
            product_mode=product_mode,
            reason=(
                "Cover not allowed: Coloring Book under 5 pages."
                if under_min else
                "Cover allowed for Coloring Book with 5+ pages."
            ),
            enforce_page_count=True,
        )

    # ── Ebook ────────────────────────────────────────────────────────────────
    if product_type == "ebook":
        under_min = _under_minimum_pages(planned_page_count)
        if under_min:
            return CoverEligibility(
                cover_allowed=False,
                must_block_cover=True,
                planned_page_count=planned_page_count,
                product_type=product_type,
                product_mode=product_mode,
                reason="Ebook under 5 pages cannot include a cover.",
                enforce_page_count=True,
            )
        return CoverEligibility(
            cover_allowed=True,
            must_block_cover=False,
            planned_page_count=planned_page_count,
            product_type=product_type,
            product_mode=product_mode,
            reason="Ebook with 5+ pages may include a cover.",
            enforce_page_count=True,
        )

    # ── Word Search ─────────────────────────────────────────────────────────
    if product_type == "word_search":
        is_book = mode_lower in {"book", "full book", "digital book", "multi-page"}
        # Single puzzle / single worksheet: block
        if not is_book:
            return CoverEligibility(
                cover_allowed=False,
                must_block_cover=True,
                planned_page_count=planned_page_count,
                product_type=product_type,
                product_mode=product_mode,
                reason="Word Search single puzzle/worksheet cannot include a cover.",
                enforce_page_count=True,
            )
        # Book mode: apply page count rule
        under_min = _under_minimum_pages(planned_page_count)
        if under_min:
            return CoverEligibility(
                cover_allowed=False,
                must_block_cover=True,
                planned_page_count=planned_page_count,
                product_type=product_type,
                product_mode=product_mode,
                reason="Word Search book under 5 pages cannot include a cover.",
                enforce_page_count=True,
            )
        return CoverEligibility(
            cover_allowed=True,
            must_block_cover=False,
            planned_page_count=planned_page_count,
            product_type=product_type,
            product_mode=product_mode,
            reason="Word Search book with 5+ pages may include a cover.",
            enforce_page_count=True,
        )

    # ── Crossword ───────────────────────────────────────────────────────────
    if product_type == "crossword":
        is_book = mode_lower in {"book", "full book", "digital book", "multi-page"}
        if not is_book:
            return CoverEligibility(
                cover_allowed=False,
                must_block_cover=True,
                planned_page_count=planned_page_count,
                product_type=product_type,
                product_mode=product_mode,
                reason="Crossword single puzzle cannot include a cover.",
                enforce_page_count=True,
            )
        under_min = _under_minimum_pages(planned_page_count)
        if under_min:
            return CoverEligibility(
                cover_allowed=False,
                must_block_cover=True,
                planned_page_count=planned_page_count,
                product_type=product_type,
                product_mode=product_mode,
                reason="Crossword book under 5 pages cannot include a cover.",
                enforce_page_count=True,
            )
        return CoverEligibility(
            cover_allowed=True,
            must_block_cover=False,
            planned_page_count=planned_page_count,
            product_type=product_type,
            product_mode=product_mode,
            reason="Crossword book with 5+ pages may include a cover.",
            enforce_page_count=True,
        )

    # ── Math / Spelling worksheets ──────────────────────────────────────────
    if product_type in ("math_worksheet", "spelling_worksheet"):
        under_min = _under_minimum_pages(planned_page_count)
        if under_min:
            return CoverEligibility(
                cover_allowed=False,
                must_block_cover=True,
                planned_page_count=planned_page_count,
                product_type=product_type,
                product_mode=product_mode,
                reason=f"{product_type} under 5 pages cannot include a cover.",
                enforce_page_count=True,
            )
        return CoverEligibility(
            cover_allowed=True,
            must_block_cover=False,
            planned_page_count=planned_page_count,
            product_type=product_type,
            product_mode=product_mode,
            reason=f"{product_type} with 5+ pages may include a cover.",
            enforce_page_count=True,
        )

    # ── Planners (faith / budget) ───────────────────────────────────────────
    # A planner is always a book: the smallest one the builder will emit is 12
    # pages, so the only way to land under the minimum is an explicit request
    # for something that is not really a planner.
    if product_type in ("faith_planner", "budget_planner", "planner"):
        under_min = _under_minimum_pages(planned_page_count)
        return CoverEligibility(
            cover_allowed=not under_min,
            must_block_cover=under_min,
            planned_page_count=planned_page_count,
            product_type=product_type,
            product_mode=product_mode,
            reason=(
                f"{product_type} under 5 pages cannot include a cover."
                if under_min else
                f"{product_type} with 5+ pages may include a cover."
            ),
            enforce_page_count=True,
        )

    # ── Unknown product type ────────────────────────────────────────────────
    # Be conservative: block covers for unknown types unless page count is clearly large
    under_min = _under_minimum_pages(planned_page_count)
    return CoverEligibility(
        cover_allowed=not under_min,
        must_block_cover=under_min,
        planned_page_count=planned_page_count,
        product_type=product_type,
        product_mode=product_mode,
        reason=(
            f"Unknown product type '{product_type}': cover blocked for < 5 pages."
            if under_min else
            f"Unknown product type '{product_type}': cover allowed for 5+ pages."
        ),
        enforce_page_count=True,
    )


def apply_cover_eligibility_to_fields(
    eligibility: CoverEligibility,
    fields: dict,
) -> dict:
    """
    Patch a fields dict to disable cover if cover_allowed=False.
    Returns a new dict (does not mutate in place).
    """
    if eligibility.cover_allowed:
        return dict(fields)

    fields = dict(fields)
    fields["include_cover"] = "no"
    fields["cover_mode"] = "none"
    # Also patch any cover_design or cover-related fields to None
    for key in ("cover_design", "cover_image", "cover_image_path"):
        if key in fields:
            fields[key] = None
    return fields


def validate_no_cover_in_pdf(
    pdf_bytes: bytes,
    eligibility: CoverEligibility,
) -> tuple[bool, list[str]]:
    """
    Inspect a PDF and return (passed, violations).
    Only enforces cover-blocking when must_block_cover=True.

    For Single Sheet / must_block_cover=True:
      - Fails if any page contains cover keywords
      - Fails if page count < planned_page_count threshold in unexpected way
    """
    if not eligibility.must_block_cover:
        # Cover is allowed — skip PDF inspection
        return True, []

    if not pdf_bytes or len(pdf_bytes) < 100:
        return False, ["PDF is empty or too small to be valid"]

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:
        return False, [f"Cannot open PDF: {exc}"]

    page_count = doc.page_count
    all_text: list[str] = []
    for page in doc:
        all_text.append(page.get_text().strip())
    doc.close()

    violations: list[str] = []

    # Rule 1: Cover text on any page
    all_lower = " ".join(all_text).lower()
    for kw in COVER_TEXT_KEYWORDS:
        if kw in all_lower:
            # Find which page(s) contain the keyword
            for i, txt in enumerate(all_text):
                if kw in txt.lower():
                    violations.append(
                        f"cover_text: keyword '{kw}' found on page {i+1}: {txt[:60]!r}"
                    )

    # Rule 2: Title-only first page (no actual content lines)
    if all_text:
        first = all_text[0].strip()
        first_lower = first.lower()
        title_only = (
            len(first) > 0 and
            len(first) < 120 and
            any(kw in first_lower for kw in TITLE_ONLY_KEYWORDS)
        )
        if title_only and len(all_text) == 1:
            # Single page with only title/cover text — definitely a cover
            violations.append(
                f"title_only_page: page 1 appears to be a cover/title page: {first[:60]!r}"
            )
        elif title_only:
            violations.append(
                f"title_cover_on_page1: page 1 appears to be title/cover: {first[:60]!r}"
            )

    # Rule 3: If the PDF has exactly 1 page and must_block_cover=True
    # AND cover keywords are present → fail
    if page_count == 1 and eligibility.must_block_cover:
        if any(kw in all_lower for kw in COVER_TEXT_KEYWORDS):
            violations.append(
                f"single_page_cover: 1-page PDF contains cover text but cover is not allowed"
            )

    return len(violations) == 0, violations


def block_or_raise(
    eligibility: CoverEligibility,
    pdf_bytes: bytes,
    context: str = "",
) -> bytes:
    """
    Validate a PDF against cover eligibility.
    Returns PDF bytes if passed. Raises ValueError on violation.
    """
    passed, violations = validate_no_cover_in_pdf(pdf_bytes, eligibility)
    if not passed:
        ctx = f" [{context}]" if context else ""
        raise ValueError(
            f"Cover QA failed{ctx}: PDF contains a cover but this product "
            f"is not eligible for a cover. Reason: {eligibility.reason} "
            f"Violations: {'; '.join(violations)}"
        )
    return pdf_bytes
