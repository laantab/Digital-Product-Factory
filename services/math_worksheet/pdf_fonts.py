"""Embedded fonts for Math Worksheet PDF rendering.

ReportLab's built-in Helvetica is a Type1 face that many viewers substitute
with mismatched metrics when non-ASCII punctuation (em dashes, ×, ÷) appears.
That shows up as stretched letter spacing and "doubled"/overlapping instruction
text. Embed a TrueType face and normalize PDF text to ASCII-safe glyphs.
"""
from __future__ import annotations

import os
from functools import lru_cache

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

MATH_FONT = "MathWorksheetSans"
MATH_FONT_BOLD = "MathWorksheetSans-Bold"
MATH_FONT_ITALIC = "MathWorksheetSans-Italic"


def _first_existing(paths: list[str]) -> str | None:
    for path in paths:
        if path and os.path.isfile(path):
            return path
    return None


def _font_candidates() -> tuple[str | None, str | None, str | None]:
    """Resolve the three faces from the shared redistributable family.

    This deliberately does NOT look in the operating system font directory. The
    crossword fonts directory it used to prefer has never existed, so every
    candidate fell through to C:\\Windows\\Fonts\\arial.ttf and Monotype Arial was
    embedded into every worksheet offered for sale. A Windows licence covers
    using Arial on that machine; it does not cover shipping it in a product.

    Liberation Sans (SIL OFL 1.1) is metric-compatible with Arial, so this swap
    does not move a single line of any existing worksheet layout.
    See services/fonts/FONT-PROVENANCE.md (v1.4.1).
    """
    shared = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts"
    )
    reportlab_fonts = os.path.join(os.path.dirname(reportlab.__file__), "fonts")

    regular = _first_existing([
        os.path.join(shared, "LiberationSans-Regular.ttf"),
        os.path.join(reportlab_fonts, "Vera.ttf"),
    ])
    bold = _first_existing([
        os.path.join(shared, "LiberationSans-Bold.ttf"),
        os.path.join(reportlab_fonts, "VeraBd.ttf"),
        regular,
    ])
    italic = _first_existing([
        os.path.join(shared, "LiberationSans-Italic.ttf"),
        os.path.join(reportlab_fonts, "VeraIt.ttf"),
        regular,
    ])
    return regular, bold, italic


@lru_cache(maxsize=1)
def ensure_math_fonts() -> tuple[str, str, str]:
    """Register embedded TTF faces once; return (regular, bold, italic) names."""
    registered = set(pdfmetrics.getRegisteredFontNames())
    if MATH_FONT in registered and MATH_FONT_BOLD in registered:
        italic = MATH_FONT_ITALIC if MATH_FONT_ITALIC in registered else MATH_FONT
        return MATH_FONT, MATH_FONT_BOLD, italic

    regular_path, bold_path, italic_path = _font_candidates()
    if not regular_path:
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"

    if MATH_FONT not in registered:
        pdfmetrics.registerFont(TTFont(MATH_FONT, regular_path))
    if bold_path and MATH_FONT_BOLD not in registered:
        pdfmetrics.registerFont(TTFont(MATH_FONT_BOLD, bold_path))
    if italic_path and MATH_FONT_ITALIC not in registered:
        pdfmetrics.registerFont(TTFont(MATH_FONT_ITALIC, italic_path))

    names = set(pdfmetrics.getRegisteredFontNames())
    bold_name = MATH_FONT_BOLD if MATH_FONT_BOLD in names else MATH_FONT
    italic_name = MATH_FONT_ITALIC if MATH_FONT_ITALIC in names else MATH_FONT
    return MATH_FONT, bold_name, italic_name


def ascii_pdf_text(value: str) -> str:
    """Normalize to ASCII-safe punctuation/operators for stable PDF metrics."""
    text = str(value or "")
    replacements = {
        "\u2014": "-",  # em dash
        "\u2013": "-",  # en dash
        "\u00d7": "x",  # multiplication sign
        "\u00f7": "/",  # division sign
        "\u2212": "-",  # minus sign
        "\u00b7": "-",
        "\u2022": "-",
        "\u00a0": " ",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    text = "".join(ch if (ord(ch) >= 32 and ord(ch) != 127) else " " for ch in text)
    return " ".join(text.split())
