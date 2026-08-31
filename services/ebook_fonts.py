"""Embedded TrueType fonts for the shared Ebook PDF generator.

xhtml2pdf + Helvetica + CSS letter-spacing produces artificial gaps inside
words ("S creens", "C hapter"). Fix: embed a real TTF family and ban
letter-spacing in ebook PDF CSS.
"""
from __future__ import annotations

import os
import shutil
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
            os.path.join(bundled, "EbookSans-regular.ttf"),
            os.path.join(bundled, "DejaVuSans.ttf"),
            os.path.join(bundled, "LiberationSans-Regular.ttf"),
            os.path.join(reportlab_fonts, "Vera.ttf"),
            os.path.join(fonts_dir, "arial.ttf"),
            os.path.join(fonts_dir, "Arial.ttf"),
            os.path.join(fonts_dir, "calibri.ttf"),
        ]),
        "bold": _first_existing([
            os.path.join(bundled, "EbookSans-bold.ttf"),
            os.path.join(bundled, "DejaVuSans-Bold.ttf"),
            os.path.join(bundled, "LiberationSans-Bold.ttf"),
            os.path.join(reportlab_fonts, "VeraBd.ttf"),
            os.path.join(fonts_dir, "arialbd.ttf"),
            os.path.join(fonts_dir, "Arialbd.ttf"),
            os.path.join(fonts_dir, "calibrib.ttf"),
        ]),
        "italic": _first_existing([
            os.path.join(bundled, "EbookSans-italic.ttf"),
            os.path.join(bundled, "DejaVuSans-Oblique.ttf"),
            os.path.join(bundled, "LiberationSans-Italic.ttf"),
            os.path.join(reportlab_fonts, "VeraIt.ttf"),
            os.path.join(fonts_dir, "ariali.ttf"),
            os.path.join(fonts_dir, "Ariali.ttf"),
            os.path.join(fonts_dir, "calibrii.ttf"),
        ]),
        "bold_italic": _first_existing([
            os.path.join(bundled, "EbookSans-bold_italic.ttf"),
            os.path.join(bundled, "DejaVuSans-BoldOblique.ttf"),
            os.path.join(bundled, "LiberationSans-BoldItalic.ttf"),
            os.path.join(reportlab_fonts, "VeraBI.ttf"),
            os.path.join(fonts_dir, "arialbi.ttf"),
            os.path.join(fonts_dir, "Arialbi.ttf"),
            os.path.join(fonts_dir, "calibriz.ttf"),
        ]),
    }


def materialize_ebook_font_files() -> dict[str, str]:
    """Copy discovered TTFs into services/fonts so xhtml2pdf can open a .ttf path."""
    dest_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    os.makedirs(dest_dir, exist_ok=True)
    out: dict[str, str] = {}
    for face, src in ebook_font_paths().items():
        if not src:
            continue
        dest = os.path.join(dest_dir, f"EbookSans-{face}.ttf")
        if os.path.abspath(src) != os.path.abspath(dest):
            if (not os.path.isfile(dest)) or os.path.getsize(dest) < 1000:
                shutil.copyfile(src, dest)
        if os.path.isfile(dest):
            out[face] = dest
    return out


def patch_xhtml2pdf_local_ttf() -> None:
    """Stop xhtml2pdf from copying TTFs to extensionless temp files (Windows lock)."""
    from xhtml2pdf.files import pisaFileObject

    if getattr(pisaFileObject.getNamedFile, "_ebook_patched", False):
        return

    orig = pisaFileObject.getNamedFile

    def getNamedFile(self):  # type: ignore[no-untyped-def]
        uri = str(self.uri or "")
        uri = uri.replace("file:///", "").replace("file://", "")
        if uri.startswith("/") and len(uri) > 2 and uri[2] == ":":
            uri = uri[1:]
        uri = uri.replace("/", os.sep)
        if uri.lower().endswith((".ttf", ".ttc", ".otf")) and os.path.isfile(uri):
            return uri
        return orig(self)

    getNamedFile._ebook_patched = True  # type: ignore[attr-defined]
    pisaFileObject.getNamedFile = getNamedFile  # type: ignore[method-assign]


@lru_cache(maxsize=1)
def ensure_ebook_fonts() -> tuple[str, str, str, str]:
    """Register EbookSans faces; return (regular, bold, italic, bold_italic)."""
    patch_xhtml2pdf_local_ttf()
    registered = set(pdfmetrics.getRegisteredFontNames())
    local = materialize_ebook_font_files()
    regular_path = local.get("regular") or ebook_font_paths()["regular"]
    if not regular_path:
        return "Helvetica", "Helvetica-Bold", "Helvetica-Oblique", "Helvetica-BoldOblique"

    mapping = [
        (EBOOK_FONT, local.get("regular") or regular_path),
        (EBOOK_FONT_BOLD, local.get("bold") or local.get("regular") or regular_path),
        (EBOOK_FONT_ITALIC, local.get("italic") or local.get("regular") or regular_path),
        (
            EBOOK_FONT_BOLD_ITALIC,
            local.get("bold_italic") or local.get("bold") or local.get("regular") or regular_path,
        ),
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


@lru_cache(maxsize=1)
def ebook_font_face_css() -> str:
    """@font-face rules pointing at local .ttf files xhtml2pdf can embed."""
    ensure_ebook_fonts()
    local = materialize_ebook_font_files()
    parts: list[str] = []
    faces = [
        (local.get("regular"), "normal", "normal"),
        (local.get("bold") or local.get("regular"), "bold", "normal"),
        (local.get("italic") or local.get("regular"), "normal", "italic"),
        (
            local.get("bold_italic") or local.get("bold") or local.get("regular"),
            "bold",
            "italic",
        ),
    ]
    for path, weight, style in faces:
        if not path:
            continue
        url = path.replace("\\", "/")
        parts.append(
            f"@font-face {{ font-family: '{EBOOK_FONT}'; src: url('{url}'); "
            f"font-weight: {weight}; font-style: {style}; }}"
        )
    return "\n".join(parts)
