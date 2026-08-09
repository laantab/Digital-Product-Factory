"""Embedded TrueType fonts for the shared Ebook PDF generator.

xhtml2pdf + Helvetica + CSS letter-spacing produces artificial gaps inside
words ("S creens", "C hapter"). Fix: embed a real TTF family and ban
letter-spacing in ebook PDF CSS.
"""
from __future__ import annotations

import os
from functools import lru_cache

import reportlab
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

EBOOK_FONT = "EbookSans"
EBOOK_FONT_BOLD = "EbookSans-Bold"
EBOOK_FONT_ITALIC = "EbookSans-Italic"
EBOOK_FONT_BOLD_ITALIC = "EbookSans-BoldItalic"


def _first_existing(paths: list[str]) -> str | None:
    for path in paths:
        if path and os.path.isfile(path):
            return path
    return None


def ebook_font_paths() -> dict[str, str | None]:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    fonts_dir = os.path.join(windir, "Fonts")
    here = os.path.dirname(os.path.abspath(__file__))
    bundled = os.path.join(here, "fonts")
    reportlab_fonts = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    return {
        "regular": _first_existing([
            os.path.join(bundled, "DejaVuSans.ttf"),
            os.path.join(bundled, "LiberationSans-Regular.ttf"),
            os.path.join(reportlab_fonts, "Vera.ttf"),
            os.path.join(fonts_dir, "arial.ttf"),
            os.path.join(fonts_dir, "Arial.ttf"),
            os.path.join(fonts_dir, "calibri.ttf"),
        ]),
        "bold": _first_existing([
            os.path.join(bundled, "DejaVuSans-Bold.ttf"),
            os.path.join(bundled, "LiberationSans-Bold.ttf"),
            os.path.join(reportlab_fonts, "VeraBd.ttf"),
            os.path.join(fonts_dir, "arialbd.ttf"),
            os.path.join(fonts_dir, "Arialbd.ttf"),
            os.path.join(fonts_dir, "calibrib.ttf"),
        ]),
        "italic": _first_existing([
            os.path.join(bundled, "DejaVuSans-Oblique.ttf"),
            os.path.join(bundled, "LiberationSans-Italic.ttf"),
            os.path.join(reportlab_fonts, "VeraIt.ttf"),
            os.path.join(fonts_dir, "ariali.ttf"),
            os.path.join(fonts_dir, "Ariali.ttf"),
            os.path.join(fonts_dir, "calibrii.ttf"),
        ]),
        "bold_italic": _first_existing([
            os.path.join(bundled, "DejaVuSans-BoldOblique.ttf"),
            os.path.join(bundled, "LiberationSans-BoldItalic.ttf"),
            os.path.join(reportlab_fonts, "VeraBI.ttf"),
            os.path.join(fonts_dir, "arialbi.ttf"),
            os.path.join(fonts_dir, "Arialbi.ttf"),
            os.path.join(fonts_dir, "calibriz.ttf"),
        ]),
    }


@lru_cache(maxsize=1)
def ensure_ebook_fonts() -> tuple[str, str, str, str]:
    """Register EbookSans faces; return (regular, bold, italic, bold_italic)."""
    registered = set(pdfmetrics.getRegisteredFontNames())
    paths = ebook_font_paths()
    regular_path = paths["regular"]
    if not regular_path:
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"

    mapping = [
        (EBOOK_FONT, paths["regular"]),
        (EBOOK_FONT_BOLD, paths["bold"] or paths["regular"]),
        (EBOOK_FONT_ITALIC, paths["italic"] or paths["regular"]),
        (EBOOK_FONT_BOLD_ITALIC, paths["bold_italic"] or paths["bold"] or paths["regular"]),
    ]
    for name, path in mapping:
        if name not in registered and path:
            pdfmetrics.registerFont(TTFont(name, path))
            registered.add(name)

    bold = EBOOK_FONT_BOLD if EBOOK_FONT_BOLD in registered else EBOOK_FONT
    italic = EBOOK_FONT_ITALIC if EBOOK_FONT_ITALIC in registered else EBOOK_FONT
    bold_italic = (
        EBOOK_FONT_BOLD_ITALIC if EBOOK_FONT_BOLD_ITALIC in registered else bold
    )
    return EBOOK_FONT, bold, italic, bold_italic


def ebook_font_face_css() -> str:
    """@font-face rules pointing at absolute file URLs for xhtml2pdf."""
    ensure_ebook_fonts()
    paths = ebook_font_paths()
    parts: list[str] = []
    faces = [
        (EBOOK_FONT, paths["regular"], "normal", "normal"),
        (EBOOK_FONT_BOLD, paths["bold"] or paths["regular"], "bold", "normal"),
        (EBOOK_FONT_ITALIC, paths["italic"] or paths["regular"], "normal", "italic"),
        (
            EBOOK_FONT_BOLD_ITALIC,
            paths["bold_italic"] or paths["bold"] or paths["regular"],
            "bold",
            "italic",
        ),
    ]
    for family, path, weight, style in faces:
        if not path:
            continue
        url = path.replace("\\", "/")
        if not url.startswith("/"):
            # Windows drive path for xhtml2pdf
            url = "/" + url
        parts.append(
            f"@font-face {{ font-family: '{EBOOK_FONT}'; src: url('file://{url}'); "
            f"font-weight: {weight}; font-style: {style}; }}"
        )
    return "\n".join(parts)
