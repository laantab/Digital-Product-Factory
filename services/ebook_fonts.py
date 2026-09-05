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

EBOOK_FONT = "LiberationSans"
EBOOK_FONT_BOLD = "LiberationSans-Bold"
EBOOK_FONT_ITALIC = "LiberationSans-Italic"
EBOOK_FONT_BOLD_ITALIC = "LiberationSans-BoldItalic"

# Serif companion. Design themes that ask for a serif previously named Georgia
# and Times New Roman, neither of which is embedded, so xhtml2pdf silently fell
# back to base-14 Times for the whole book — every designed ebook shipped in a
# typeface nobody chose. Liberation Serif ships under the same OFL and is
# metric-compatible with Times New Roman, so the themes keep their intended
# look and now genuinely embed it (v1.4.1).
EBOOK_SERIF = "LiberationSerif"
EBOOK_SERIF_BOLD = "LiberationSerif-Bold"
EBOOK_SERIF_ITALIC = "LiberationSerif-Italic"
EBOOK_SERIF_BOLD_ITALIC = "LiberationSerif-BoldItalic"

# Faces we must never embed in a product we sell. Redistributing these files, or
# baking them into a customer PDF, needs a licence the Factory does not hold.
# See services/fonts/FONT-PROVENANCE.md.
PROPRIETARY_FONT_MARKERS = (
    "arial",
    "calibri",
    "helvetica neue",
    "times new roman",
    "georgia",
    "verdana",
    "tahoma",
    "segoe",
    "cambria",
    "ebooksans",
)


def _first_existing(paths: list[str]) -> str | None:
    for path in paths:
        if path and os.path.isfile(path):
            return path
    return None


def ebook_font_paths() -> dict[str, str | None]:
    """Resolve the four ebook faces.

    Only fonts we may redistribute and embed in a sold PDF are eligible, so this
    deliberately does NOT look in the operating system font directory. Liberation
    Sans (SIL OFL 1.1) is metric-compatible with Arial, which is why swapping to
    it left pagination intact. See services/fonts/FONT-PROVENANCE.md.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    bundled = os.path.join(here, "fonts")
    reportlab_fonts = os.path.join(os.path.dirname(reportlab.__file__), "fonts")
    return {
        "regular": _first_existing([
            os.path.join(bundled, "LiberationSans-Regular.ttf"),
            os.path.join(bundled, "DejaVuSans.ttf"),
            os.path.join(reportlab_fonts, "Vera.ttf"),
        ]),
        "bold": _first_existing([
            os.path.join(bundled, "LiberationSans-Bold.ttf"),
            os.path.join(bundled, "DejaVuSans-Bold.ttf"),
            os.path.join(reportlab_fonts, "VeraBd.ttf"),
        ]),
        "italic": _first_existing([
            os.path.join(bundled, "LiberationSans-Italic.ttf"),
            os.path.join(bundled, "DejaVuSans-Oblique.ttf"),
            os.path.join(reportlab_fonts, "VeraIt.ttf"),
        ]),
        "bold_italic": _first_existing([
            os.path.join(bundled, "LiberationSans-BoldItalic.ttf"),
            os.path.join(bundled, "DejaVuSans-BoldOblique.ttf"),
            os.path.join(reportlab_fonts, "VeraBI.ttf"),
        ]),
    }


def materialize_ebook_font_files() -> dict[str, str]:
    """Return a local .ttf path per face for xhtml2pdf to open.

    The shipped faces already live in services/fonts, so the common path is a
    straight passthrough. Only a face resolved from outside that directory (the
    ReportLab fallbacks) is copied in, and it keeps its real filename — we never
    rename a font, because a renamed file hides whose font it actually is. That
    is exactly how proprietary Arial ended up shipping as "EbookSans".
    """
    dest_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    os.makedirs(dest_dir, exist_ok=True)
    out: dict[str, str] = {}
    for face, src in ebook_font_paths().items():
        if not src:
            continue
        if os.path.dirname(os.path.abspath(src)) == os.path.abspath(dest_dir):
            out[face] = src
            continue
        dest = os.path.join(dest_dir, os.path.basename(src))
        src_size = os.path.getsize(src)
        dest_size = os.path.getsize(dest) if os.path.isfile(dest) else 0
        if dest_size != src_size:
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
    """Register the ebook faces; return (regular, bold, italic, bold_italic)."""
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
    # Expose the bold TTF as its own family. xhtml2pdf often ignores
    # font-weight matching and will otherwise stamp h1/h2 in the regular face.
    bold_path = local.get("bold") or local.get("regular")
    if bold_path:
        url = bold_path.replace("\\", "/")
        parts.append(
            f"@font-face {{ font-family: '{EBOOK_FONT_BOLD}'; src: url('{url}'); "
            f"font-weight: normal; font-style: normal; }}"
        )
        parts.append(
            f"@font-face {{ font-family: '{EBOOK_FONT_BOLD}'; src: url('{url}'); "
            f"font-weight: bold; font-style: normal; }}"
        )
    return "\n".join(parts)


def ebook_stamp_fontfile() -> str | None:
    """TrueType path for running headers/footers (same face as body, not Helvetica)."""
    local = materialize_ebook_font_files()
    return local.get("regular") or ebook_font_paths()["regular"]


def ebook_serif_paths() -> dict[str, str | None]:
    """Resolve the four serif faces from the bundled OFL family."""
    here = os.path.dirname(os.path.abspath(__file__))
    bundled = os.path.join(here, "fonts")
    return {
        "regular": _first_existing([os.path.join(bundled, "LiberationSerif-Regular.ttf")]),
        "bold": _first_existing([os.path.join(bundled, "LiberationSerif-Bold.ttf")]),
        "italic": _first_existing([os.path.join(bundled, "LiberationSerif-Italic.ttf")]),
        "bold_italic": _first_existing([os.path.join(bundled, "LiberationSerif-BoldItalic.ttf")]),
    }


@lru_cache(maxsize=1)
def ensure_ebook_serif() -> tuple[str, str, str, str]:
    """Register the serif faces; return (regular, bold, italic, bold_italic)."""
    patch_xhtml2pdf_local_ttf()
    paths = ebook_serif_paths()
    if not paths.get("regular"):
        return ("Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic")
    registered = set(pdfmetrics.getRegisteredFontNames())
    mapping = [
        (EBOOK_SERIF, paths["regular"]),
        (EBOOK_SERIF_BOLD, paths.get("bold") or paths["regular"]),
        (EBOOK_SERIF_ITALIC, paths.get("italic") or paths["regular"]),
        (EBOOK_SERIF_BOLD_ITALIC, paths.get("bold_italic") or paths.get("bold") or paths["regular"]),
    ]
    for name, path in mapping:
        if name not in registered and path:
            pdfmetrics.registerFont(TTFont(name, path))
            registered.add(name)
    return (EBOOK_SERIF, EBOOK_SERIF_BOLD, EBOOK_SERIF_ITALIC, EBOOK_SERIF_BOLD_ITALIC)


@lru_cache(maxsize=1)
def ebook_serif_face_css() -> str:
    """@font-face rules for the serif family."""
    ensure_ebook_serif()
    paths = ebook_serif_paths()
    if not paths.get("regular"):
        return ""
    parts: list[str] = []
    faces = [
        (paths.get("regular"), "normal", "normal"),
        (paths.get("bold") or paths.get("regular"), "bold", "normal"),
        (paths.get("italic") or paths.get("regular"), "normal", "italic"),
        (paths.get("bold_italic") or paths.get("bold") or paths.get("regular"), "bold", "italic"),
    ]
    for path, weight, style in faces:
        if not path:
            continue
        url = str(path).replace("\\", "/")
        parts.append(
            f"@font-face {{ font-family: '{EBOOK_SERIF}'; src: url('{url}'); "
            f"font-weight: {weight}; font-style: {style}; }}"
        )
    bold_path = paths.get("bold") or paths.get("regular")
    if bold_path:
        url = str(bold_path).replace("\\", "/")
        for weight in ("normal", "bold"):
            parts.append(
                f"@font-face {{ font-family: '{EBOOK_SERIF_BOLD}'; src: url('{url}'); "
                f"font-weight: {weight}; font-style: normal; }}"
            )
    return "\n".join(parts)
