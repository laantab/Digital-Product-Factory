"""
User Instruction Controller — strict execution contract for every product.

Purpose:
  Before any generation, export, or download, this controller reads the user's
  actual selected form fields and creates a verifiable execution contract. Every
  downstream path — generation, packaging, download — must honour the contract.

Why this exists:
  The root cause of repeated Single Sheet failures was that /generate-product could
  pass while /export-product silently re-used a stale 13-page PDF. The contract
  travels with the product record so no path can "forget" what the user asked for.

How it works:
  1. build_instruction_contract(product_type, fields) — creates the contract dict
  2. save_instruction_contract(contract, data) — stamps it into product data
  3. get_instruction_contract(data) — retrieves it from product data
  4. verify_instruction_contract(contract, pdf_bytes) — checks output matches contract
  5. enforce_or_raise(contract, pdf_bytes, context) — blocks bad output

Scope:
  All product types. Each product type has its own contract rules.
  Currently enforces Coloring Book Single Sheet most strictly.
"""
from __future__ import annotations

import base64
import fitz

from dataclasses import dataclass, field
from typing import Any


# -------------------------------------------------------------------------- //
# Single Sheet output type constant (matches puzzle_plan.OUTPUT_SINGLE_PAGE)
# -------------------------------------------------------------------------- //
COLORING_OUTPUT_SINGLE_PAGE = "single_page"

# Patterns that count as "Single Sheet" regardless of casing/spacing
_SINGLE_SHEET_PATTERNS = {
    "single sheet", "single_sheet",
    "single page", "single_page",
    "one page", "1 page", "sheet",
}

# Patterns that count as "Digital Book"
_BOOK_PATTERNS = {
    "digital book", "book", "digital book",
    "full book", "coloring book",
}

# Captions: allowed text patterns on a coloring page
_CAPTION_INDICATORS = {
    "page", "chapter", "section",
    "fig ", "figure ", "note:",
    "caption", "label:",
}


@dataclass
class ColoringBookContract:
    """Strict execution contract for Coloring Book products."""

    # --- Identity ---
    product_type: str = "coloring_book"
    title: str = ""
    theme: str = ""

    # --- User's actual selected fields ---
    output_format: str = ""          # e.g. "Single Sheet", "Digital Book"
    output_type: str = ""            # e.g. "single_page", "book"
    quality_mode: str = ""            # e.g. "AI Image Coloring Page"
    target_age: str = ""             # e.g. "12-adult"
    num_pages: str = ""              # e.g. "1"
    art_style: str = ""
    captions: str = ""                # "yes" or "no"

    # --- Computed contract rules ---
    expected_pdf_pages: int = 1      # MUST be exactly this
    cover_allowed: bool = False
    title_page_allowed: bool = False
    front_matter_allowed: bool = False
    headers_allowed: bool = False
    footers_allowed: bool = False
    page_numbers_allowed: bool = False
    scene_labels_allowed: bool = False
    captions_allowed: bool = False
    book_assembly_allowed: bool = False
    digital_book_behavior_allowed: bool = False
    stale_export_allowed: bool = False
    zip_pdf_must_match_standalone: bool = True

    # --- Contract metadata ---
    is_single_sheet: bool = False    # True if contract is for Single Sheet
    is_digital_book: bool = False    # True if contract is for Digital Book

    def to_dict(self) -> dict:
        return {
            "product_type": self.product_type,
            "title": self.title,
            "theme": self.theme,
            "output_format": self.output_format,
            "output_type": self.output_type,
            "quality_mode": self.quality_mode,
            "target_age": self.target_age,
            "num_pages": self.num_pages,
            "art_style": self.art_style,
            "captions": self.captions,
            "expected_pdf_pages": self.expected_pdf_pages,
            "cover_allowed": self.cover_allowed,
            "title_page_allowed": self.title_page_allowed,
            "front_matter_allowed": self.front_matter_allowed,
            "headers_allowed": self.headers_allowed,
            "footers_allowed": self.footers_allowed,
            "page_numbers_allowed": self.page_numbers_allowed,
            "scene_labels_allowed": self.scene_labels_allowed,
            "captions_allowed": self.captions_allowed,
            "book_assembly_allowed": self.book_assembly_allowed,
            "digital_book_behavior_allowed": self.digital_book_behavior_allowed,
            "stale_export_allowed": self.stale_export_allowed,
            "zip_pdf_must_match_standalone": self.zip_pdf_must_match_standalone,
            "is_single_sheet": self.is_single_sheet,
            "is_digital_book": self.is_digital_book,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ColoringBookContract":
        """Reconstitute from a saved contract dict."""
        known = {
            "product_type", "title", "theme", "output_format", "output_type",
            "quality_mode", "target_age", "num_pages", "art_style", "captions",
            "expected_pdf_pages", "cover_allowed", "title_page_allowed",
            "front_matter_allowed", "headers_allowed", "footers_allowed",
            "page_numbers_allowed", "scene_labels_allowed", "captions_allowed",
            "book_assembly_allowed", "digital_book_behavior_allowed",
            "stale_export_allowed", "zip_pdf_must_match_standalone",
            "is_single_sheet", "is_digital_book",
        }
        return cls(**{k: v for k, v in d.items() if k in known})

    def violations(self, pdf_bytes: bytes) -> list[str]:
        """
        Inspect a coloring book PDF against this contract.
        Returns a list of violation descriptions. Empty list = passes.
        """
        violations: list[str] = []

        if not pdf_bytes or len(pdf_bytes) < 100:
            return ["PDF is empty or too small to be valid"]

        try:
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        except Exception as exc:
            return [f"Cannot open PDF: {exc}"]

        page_count = doc.page_count

        # 1. Page count
        if page_count != self.expected_pdf_pages:
            violations.append(
                f"page_count={page_count}, expected={self.expected_pdf_pages}"
            )

        all_text: list[str] = []
        for i, page in enumerate(doc):
            txt = page.get_text().strip()
            all_text.append(txt)

        doc.close()

        # 2. Cover / title page (any page with cover-like text)
        if not self.cover_allowed:
            for i, txt in enumerate(all_text):
                txt_lower = txt.lower()
                if any(kw in txt_lower for kw in [
                    "coloring book", "coloring book cover",
                    "cover page", "front cover", "book cover",
                    "title page",
                ]):
                    violations.append(
                        f"cover_or_title_page: page {i+1} contains cover text: {txt[:60]!r}"
                    )

        # 3. Page numbering
        if not self.page_numbers_allowed:
            for i, txt in enumerate(all_text):
                if "page" in txt.lower() and ("of" in txt.lower()):
                    violations.append(
                        f"page_numbers: page {i+1} contains page numbering: {txt[:60]!r}"
                    )

        # 4. Headers / footers (short repeated text on page tops/bottoms)
        if not self.headers_allowed:
            for i, txt in enumerate(all_text):
                lines = [l.strip() for l in txt.split("\n") if l.strip()]
                if lines:
                    first = lines[0].lower()
                    if (len(first) < 60 and
                        any(kw in first for kw in [
                            "chapter", "section", "page ", "note:",
                            "farm house", "coloring", "title",
                        ]) and
                            first not in (self.title or "").lower().split()
                    ):
                        violations.append(
                            f"header: page {i+1} starts with header text: {lines[0][:60]!r}"
                        )

        # 5. Captions check
        if not self.captions_allowed and self.captions.lower() in ("no", "false", "0"):
            for i, txt in enumerate(all_text):
                txt_lower = txt.lower()
                if len(txt) > 3:  # Short incidental text is ok
                    violations.append(
                        f"caption_disallowed: page {i+1} contains text={txt[:60]!r}"
                    )

        return violations


# -------------------------------------------------------------------------- //
# Contract builder — per product type
# -------------------------------------------------------------------------- //

def build_coloring_book_contract(fields: dict) -> ColoringBookContract:
    """
    Build a strict Coloring Book execution contract from the user's form fields.

    Raises ValueError if the contract cannot be determined from the fields
    (i.e., the user submitted an incomplete form for a Coloring Book).
    """
    fields = dict(fields or {})

    output_format = str(fields.get("output_format") or "").strip()
    output_type = str(fields.get("output_type") or "").strip().lower()
    quality_mode = str(fields.get("quality_mode") or "").strip()
    target_age = str(fields.get("target_age") or "").strip()
    num_pages = str(fields.get("num_pages") or fields.get("pages") or "").strip()
    art_style = str(fields.get("art_style") or "").strip()
    captions = str(fields.get("captions") or fields.get("include_captions") or "").strip()
    title = str(fields.get("title") or fields.get("theme") or fields.get("product_title") or "").strip()
    theme = str(fields.get("theme") or title or "").strip()

    # Normalize output_format to lower
    of_lower = output_format.lower()

    # Determine if Single Sheet
    # Override: 1 page always means single sheet — no cover, no page numbers,
    # no matter what output_format says (e.g. "Digital Book" with pages=1 is a user
    # mismatch and must be treated as single sheet, not a 12-page book).
    is_single_sheet = (
        of_lower in _SINGLE_SHEET_PATTERNS
        or output_type == COLORING_OUTPUT_SINGLE_PAGE
        # Override: explicitly requested 1 page = single sheet regardless of format
        or num_pages == "1"
    )

    # Determine if Digital Book
    is_digital_book = (
        of_lower in _BOOK_PATTERNS
        or output_type == "book"
        # Only digital book if pages is explicitly > 1
        or (num_pages not in ("", "1", "0"))
    )

    captions_bool = captions.lower() in ("yes", "true", "1", "on")
    captions_allowed = captions_bool

    if is_single_sheet:
        contract = ColoringBookContract(
            product_type="coloring_book",
            title=title,
            theme=theme,
            output_format=output_format,
            output_type=output_type or COLORING_OUTPUT_SINGLE_PAGE,
            quality_mode=quality_mode,
            target_age=target_age,
            num_pages=num_pages,
            art_style=art_style,
            captions=captions,
            expected_pdf_pages=1,
            cover_allowed=False,
            title_page_allowed=False,
            front_matter_allowed=False,
            headers_allowed=False,
            footers_allowed=False,
            page_numbers_allowed=False,
            scene_labels_allowed=captions_bool,
            captions_allowed=captions_bool,
            book_assembly_allowed=False,
            digital_book_behavior_allowed=False,
            stale_export_allowed=False,
            zip_pdf_must_match_standalone=True,
            is_single_sheet=True,
            is_digital_book=False,
        )
    elif is_digital_book:
        # Digital Book: allow cover, multi-page, page numbers
        # Page count comes from num_pages or default 12
        try:
            book_pages = int(num_pages) if num_pages else 12
        except (ValueError, TypeError):
            book_pages = 12

        contract = ColoringBookContract(
            product_type="coloring_book",
            title=title,
            theme=theme,
            output_format=output_format,
            output_type=output_type or "book",
            quality_mode=quality_mode,
            target_age=target_age,
            num_pages=num_pages,
            art_style=art_style,
            captions=captions,
            expected_pdf_pages=book_pages,
            cover_allowed=True,
            title_page_allowed=True,
            front_matter_allowed=True,
            headers_allowed=True,
            footers_allowed=True,
            page_numbers_allowed=True,
            scene_labels_allowed=True,
            captions_allowed=True,
            book_assembly_allowed=True,
            digital_book_behavior_allowed=True,
            stale_export_allowed=False,
            zip_pdf_must_match_standalone=True,
            is_single_sheet=False,
            is_digital_book=True,
        )
    else:
        # Unknown output format — conservative contract (block by default)
        raise ValueError(
            f"Cannot determine output format for Coloring Book. "
            f"output_format={output_format!r}, output_type={output_type!r}. "
            f"Cannot generate because product instructions could not be verified."
        )

    return contract


def build_instruction_contract(product_type: str, fields: dict) -> dict:
    """
    Public entry point. Builds a contract for any product type.
    Raises ValueError if the contract cannot be determined.
    """
    product_type = str(product_type or "").strip().lower()

    if product_type == "coloring_book":
        contract = build_coloring_book_contract(fields)
        return contract.to_dict()

    # For other product types, return a minimal permissive contract
    return {
        "product_type": product_type,
        "output_format": fields.get("output_format", ""),
        "fields": dict(fields),
    }


def save_instruction_contract(contract: dict, data: dict) -> dict:
    """
    Stamp the contract into the product data dict.
    Returns the updated data dict (does not mutate in place).
    """
    data = dict(data)
    data["_instruction_contract"] = contract
    return data


def get_instruction_contract(data: dict) -> dict | None:
    """Retrieve the saved contract from product data."""
    return dict(data.get("_instruction_contract") or {})


def verify_coloring_book_contract(
    contract: dict | ColoringBookContract,
    pdf_bytes: bytes,
) -> tuple[bool, list[str]]:
    """
    Verify that a coloring book PDF satisfies its contract.
    Returns (passed, violations).
    """
    if isinstance(contract, dict):
        contract = ColoringBookContract.from_dict(contract)

        violations = selfViolations(pdf_bytes)
    return len(violations) == 0, violations


def enforce_coloring_book_or_raise(
    contract: dict | ColoringBookContract,
    pdf_bytes: bytes,
    context: str = "",
) -> bytes:
    """
    Verify a coloring book PDF against its contract.
    Returns the PDF bytes if it passes.
    Raises ValueError describing the violations if it fails.
    """
    passed, violations = verify_coloring_book_contract(contract, pdf_bytes)
    if not passed:
        ctx = f" [{context}]" if context else ""
        raise ValueError(
            f"Coloring Book QA failed{ctx}: PDF violates instruction contract. "
            f"Violations: {'; '.join(violations)}"
        )
    return pdf_bytes
