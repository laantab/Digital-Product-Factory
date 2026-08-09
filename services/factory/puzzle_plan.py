"""Shared output-format planning for factory worksheet products."""
from __future__ import annotations

OUTPUT_SINGLE_PAGE = "single_page"
OUTPUT_SINGLE_WORKSHEET = "single_worksheet"
OUTPUT_BOOK = "book"

DEFAULT_BOOK_COUNTS = {
    "word_search": 10,
    "crossword": 12,
    "coloring_book": 40,
    "math_worksheet": 10,
    "spelling_worksheet": 10,
}


def _field(fields: dict, key: str, default: str = "") -> str:
    value = fields.get(key)
    if value is None:
        return default
    # Handle booleans (plan dict passes booleans for include_answer_key/include_cover)
    if isinstance(value, bool):
        return str(value).strip()
    return str(value).strip()


def _bool_field(fields: dict, key: str, default: bool = False) -> bool:
    """Parse a boolean field from fields dict — handles both bool and string values."""
    raw = fields.get(key)
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return default
    return str(raw).strip().lower() in {"yes", "true", "1", "on"}


def _parse_count_token(raw: str, *, default: int) -> int:
    token = str(raw or "").strip()
    if not token:
        return default
    head = token.split("-", 1)[0].strip()
    try:
        return max(1, int(head))
    except ValueError:
        return default


# Standard defaults for coloring books
COLORING_BOOK_DEFAULT = 40
COLORING_BOOK_MIN = 12
COLORING_BOOK_MAX = 100  # safe cap without confirmation
COLORING_BOOK_RECOMMENDED_MIN = 24
COLORING_BOOK_RECOMMENDED_MAX = 50


def normalize_coloring_page_count(product_mode: str, requested_count: int | None) -> tuple[int, list[str]]:
    """Normalize a coloring book page count.

    Returns (normalized_count, warnings).

    Rules:
    - Single Sheet → always 1
    - Digital Book blank/invalid → 40
    - Digital Book 1–11 → 12 (minimum for a sellable book)
    - Digital Book 12–100 → user value
    - Digital Book over 100 → 40 (safe cap; caller can add a confirmation prompt)
    """
    warnings: list[str] = []

    # Single Sheet always = 1
    if product_mode == OUTPUT_SINGLE_PAGE:
        return 1, warnings

    # Digital Book normalization
    if requested_count is None or requested_count <= 0:
        warnings.append(
            f"Page count was blank or invalid — set to the standard default of {COLORING_BOOK_DEFAULT}."
        )
        return COLORING_BOOK_DEFAULT, warnings

    if requested_count < COLORING_BOOK_MIN:
        warnings.append(
            f"Page count {requested_count} is too low for a sellable coloring book — "
            f"reset to {COLORING_BOOK_MIN}."
        )
        return COLORING_BOOK_MIN, warnings

    if requested_count > COLORING_BOOK_MAX:
        warnings.append(
            f"Page count {requested_count} exceeds the safe limit of {COLORING_BOOK_MAX}. "
            f"Reset to the standard default of {COLORING_BOOK_DEFAULT}. "
            f"To generate a larger book, confirm explicitly in a later update."
        )
        return COLORING_BOOK_DEFAULT, warnings

    # 12–100: accept as-is
    if requested_count < COLORING_BOOK_RECOMMENDED_MIN:
        warnings.append(
            f"{requested_count} pages is below the recommended range ({COLORING_BOOK_RECOMMENDED_MIN}–"
            f"{COLORING_BOOK_RECOMMENDED_MAX}). Results may look thin. "
            f"Consider 24–50 pages for a sellable book."
        )
    elif requested_count > COLORING_BOOK_RECOMMENDED_MAX:
        warnings.append(
            f"{requested_count} pages is above the recommended range ({COLORING_BOOK_RECOMMENDED_MIN}–"
            f"{COLORING_BOOK_RECOMMENDED_MAX}). This will generate {requested_count} AI images "
            f"and may be slower or cost more."
        )

    return requested_count, warnings


def _parse_book_count(fields: dict, *, product_type: str, is_legacy_book: bool) -> int:
    default = DEFAULT_BOOK_COUNTS.get(product_type, 10)
    raw = (
        _field(fields, "book_size")
        or _field(fields, "puzzles")
        or _field(fields, "worksheets")
        or _field(fields, "pages")
    )
    count = _parse_count_token(raw, default=default)
    if is_legacy_book and count == 1:
        return default
    return count


def parse_puzzle_output_plan(fields: dict, *, product_type: str = "") -> dict:
    """Normalize book / worksheet / single-page settings from factory form fields.

    Supports the unified ``output_format`` field and legacy ``generator`` +
    ``worksheets`` values so saved projects keep working.
    """
    fields = dict(fields or {})
    product_type = str(product_type or "").strip().lower()

    output_format = _field(fields, "output_format")
    legacy_generator = _field(fields, "generator")
    legacy_is_book = "Book" in legacy_generator

    # Normalize output_format to lowercase for robust matching
    of_lower = output_format.lower()

    if output_format:
        if "single page" in of_lower or "single sheet" in of_lower or of_lower == "single_page":
            output_type = OUTPUT_SINGLE_PAGE
            page_count = 1
            is_book = False
        elif "single worksheet" in of_lower or of_lower == "single_worksheet":
            output_type = OUTPUT_SINGLE_WORKSHEET
            page_count = 1
            is_book = False
        elif "book" in of_lower or "digital book" in of_lower:
            output_type = OUTPUT_BOOK
            page_count = _parse_book_count(fields, product_type=product_type, is_legacy_book=False)
            is_book = True
        else:
            output_type = OUTPUT_SINGLE_WORKSHEET
            page_count = 1
            is_book = False
    elif legacy_generator:
        if legacy_is_book:
            output_type = OUTPUT_BOOK
            page_count = _parse_book_count(fields, product_type=product_type, is_legacy_book=True)
            is_book = True
        else:
            worksheets_raw = _field(fields, "worksheets", "1")
            page_count = _parse_count_token(worksheets_raw, default=1)
            if page_count <= 1:
                output_type = OUTPUT_SINGLE_WORKSHEET
                is_book = False
            else:
                output_type = OUTPUT_BOOK
                is_book = True
    else:
        worksheets_raw = _field(fields, "worksheets") or _field(fields, "book_size") or _field(fields, "pages")
        if worksheets_raw:
            page_count = _parse_count_token(worksheets_raw, default=1)
            if page_count <= 1:
                output_type = OUTPUT_SINGLE_WORKSHEET
                is_book = False
            else:
                output_type = OUTPUT_BOOK
                is_book = True
        else:
            output_type = OUTPUT_SINGLE_WORKSHEET
            page_count = 1
            is_book = False

    # ── SINGLE SHEET OVERRIDE ────────────────────────────────────────────────
    # Critical: if the user explicitly requests 1 page for a coloring book,
    # that always means single sheet — no cover, no page numbers, exactly 1 page.
    # This override fires AFTER output_format is parsed so it catches mismatches
    # like "Digital Book" + pages=1 or "Single Sheet" + pages=1.
    if product_type == "coloring_book" and page_count == 1:
        output_type = OUTPUT_SINGLE_PAGE
        is_book = False

    # Parse answer key — handles booleans (from plan dict) and strings (from form fields)
    include_answers = _bool_field(fields, "include_answer_key", default=True)
    # Also support legacy "include_answers" string field
    if fields.get("include_answers") is not None:
        include_answers = _bool_field(fields, "include_answers", default=True)

    return {
        "output_type": output_type,
        "page_count": page_count,
        "is_book": is_book,
        "include_answer_key": include_answers,
        "include_cover": is_book,
    }
