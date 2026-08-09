"""Embedded fonts for Crossword PDF rendering.

Root cause of broken visual spacing: ReportLab's built-in Helvetica is a Type1
font that many PDF viewers substitute with mismatched metrics, especially when
non-ASCII punctuation (middle dots, fancy dashes) triggers fallback glyphs.
That appears as artificial gaps/collisions ("C a lifo...", "Answ er").

Fix: embed a common TrueType face (Arial on Windows, DejaVu if bundled) and
draw whole strings only with that registered face.
"""
from __future__ import annotations

import os
from functools import lru_cache

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

CROSSWORD_FONT = "CrosswordSans"
CROSSWORD_FONT_BOLD = "CrosswordSans-Bold"
CROSSWORD_FONT_ITALIC = "CrosswordSans-Italic"

# Exported size contracts used by renderer + tests
COVER_TITLE_MIN_PT = 22.0
HEADING_FONT_MIN_PT = 15.0
INSTRUCTION_FONT_MIN_PT = 9.0
CLUE_FONT_MIN_PT = 9.0
ANSWER_HEADING_MIN_PT = 14.0
FOOTER_FONT_MIN_PT = 7.5


def _first_existing(paths: list[str]) -> str | None:
    for path in paths:
        if path and os.path.isfile(path):
            return path
    return None


def _font_candidates() -> tuple[str | None, str | None, str | None]:
    here = os.path.dirname(os.path.abspath(__file__))
    bundled = os.path.join(here, "fonts")
    windir = os.environ.get("WINDIR", r"C:\Windows")
    fonts_dir = os.path.join(windir, "Fonts")

    regular = _first_existing([
        os.path.join(bundled, "DejaVuSans.ttf"),
        os.path.join(bundled, "LiberationSans-Regular.ttf"),
        os.path.join(fonts_dir, "arial.ttf"),
        os.path.join(fonts_dir, "Arial.ttf"),
        os.path.join(fonts_dir, "calibri.ttf"),
        os.path.join(fonts_dir, "segoeui.ttf"),
    ])
    bold = _first_existing([
        os.path.join(bundled, "DejaVuSans-Bold.ttf"),
        os.path.join(bundled, "LiberationSans-Bold.ttf"),
        os.path.join(fonts_dir, "arialbd.ttf"),
        os.path.join(fonts_dir, "Arialbd.ttf"),
        os.path.join(fonts_dir, "calibrib.ttf"),
        os.path.join(fonts_dir, "segoeuib.ttf"),
        regular,
    ])
    italic = _first_existing([
        os.path.join(bundled, "DejaVuSans-Oblique.ttf"),
        os.path.join(bundled, "LiberationSans-Italic.ttf"),
        os.path.join(fonts_dir, "ariali.ttf"),
        os.path.join(fonts_dir, "Ariali.ttf"),
        os.path.join(fonts_dir, "calibrii.ttf"),
        os.path.join(fonts_dir, "segoeuii.ttf"),
        regular,
    ])
    return regular, bold, italic


@lru_cache(maxsize=1)
def ensure_crossword_fonts() -> tuple[str, str, str]:
    """Register embedded TTF faces once; return (regular, bold, italic) names."""
    registered = set(pdfmetrics.getRegisteredFontNames())
    if CROSSWORD_FONT in registered and CROSSWORD_FONT_BOLD in registered:
        italic = CROSSWORD_FONT_ITALIC if CROSSWORD_FONT_ITALIC in registered else CROSSWORD_FONT
        return CROSSWORD_FONT, CROSSWORD_FONT_BOLD, italic

    regular_path, bold_path, italic_path = _font_candidates()
    if not regular_path:
        # Last resort: built-ins (may reintroduce viewer substitution issues).
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"

    if CROSSWORD_FONT not in registered:
        pdfmetrics.registerFont(TTFont(CROSSWORD_FONT, regular_path))
    if bold_path and CROSSWORD_FONT_BOLD not in registered:
        pdfmetrics.registerFont(TTFont(CROSSWORD_FONT_BOLD, bold_path))
    if italic_path and CROSSWORD_FONT_ITALIC not in registered:
        pdfmetrics.registerFont(TTFont(CROSSWORD_FONT_ITALIC, italic_path))

    bold_name = CROSSWORD_FONT_BOLD if CROSSWORD_FONT_BOLD in pdfmetrics.getRegisteredFontNames() else CROSSWORD_FONT
    italic_name = CROSSWORD_FONT_ITALIC if CROSSWORD_FONT_ITALIC in pdfmetrics.getRegisteredFontNames() else CROSSWORD_FONT
    return CROSSWORD_FONT, bold_name, italic_name


def ascii_pdf_text(value: str) -> str:
    """Normalize to ASCII-safe punctuation so no fallback glyphs are needed."""
    text = str(value or "")
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u00b7": "-",
        "\u2022": "-",
        "\u00a0": " ",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u00ae": "",
        "\u2122": "",
    }
    for src, dst in replacements.items():
        text = text.replace(src, dst)
    # Keep printable ASCII + common accented letters already in Latin fonts;
    # strip other control chars.
    text = "".join(ch if (ord(ch) >= 32 and ord(ch) != 127) else " " for ch in text)
    return " ".join(text.split())
