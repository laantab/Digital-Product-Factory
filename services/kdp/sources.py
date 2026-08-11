"""Authoritative Amazon KDP Help Center citations used by Pass 1 foundations.

Every numeric constant encoded in ``services.kdp`` must map to one of these
URLs (or ISO 2108 for ISBN check-digit arithmetic). Do not invent specs.
"""
from __future__ import annotations

# Trim, bleed, margins, gutter, page-count ranges by ink/paper/trim
KDP_TRIM_BLEED_MARGINS = "https://kdp.amazon.com/help/topic/GVBQ3CMEQW3W2VL6"

# Cover size equations + spine coefficients (B&W white/cream, color premium/standard)
KDP_PAPERBACK_COVER = "https://kdp.amazon.com/help/topic/G201953020"

# Spine coefficient for groundwood; cover equations; paperback submission overview
KDP_PAPERBACK_SUBMISSION = "https://kdp.amazon.com/help/topic/G201857950"

# Low-content vs activity (puzzle / coloring) classification + ISBN eligibility
KDP_LOW_CONTENT_BOOKS = "https://kdp.amazon.com/help/topic/GGE5T76TWKA85DJM"

# AI-generated vs AI-assisted disclosure definitions
KDP_CONTENT_GUIDELINES_AI = "https://kdp.amazon.com/help/topic/G200672390"

# ISBN / imprint overview (13-digit 978/979; low-content ISBN options)
KDP_ISBN_IMPRINT = "https://kdp.amazon.com/help/topic/G201834170"

# Free ISBN eligibility note (low-content ineligible for free KDP ISBN)
KDP_GET_ISBN = "https://kdp.amazon.com/en_US/help/topic/GTJ8LBXL6Z4WV5QX"

# ISBN-13 check digit algorithm (ISO 2108) — not Amazon-specific
ISO_2108_ISBN = "ISO 2108 (ISBN-13 check digit)"

SOURCE_INDEX = {
    "trim_bleed_margins": KDP_TRIM_BLEED_MARGINS,
    "paperback_cover": KDP_PAPERBACK_COVER,
    "paperback_submission": KDP_PAPERBACK_SUBMISSION,
    "low_content": KDP_LOW_CONTENT_BOOKS,
    "ai_disclosure": KDP_CONTENT_GUIDELINES_AI,
    "isbn_imprint": KDP_ISBN_IMPRINT,
    "get_isbn": KDP_GET_ISBN,
    "isbn_check_digit": ISO_2108_ISBN,
}
