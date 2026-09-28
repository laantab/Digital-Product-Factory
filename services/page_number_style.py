"""One print standard for every page number the Factory prints (v1.9.13).

Before this, each renderer chose its own page-number type, and most chose
small, light or coloured type that was hard to read on paper:

    designed ebooks (six templates)   11 pt bold template ink (9 pt grey before 1.9.12)
    planners                           9.5 pt bold in the theme's accent colour
    coloring books                     9 pt regular black
    math worksheets                    8 pt light grey (#9CA3AF)
    spelling worksheets                9 pt grey, inside the section label
    Publishing Studio PDFs             9 pt bold grey or blue

Every one of them now takes its size, weight and colour from here, so a page
number is the same readable mark whichever product printed it. Only the look
of the number changes: where it sits, which pages carry one and how they are
counted stay exactly as each product already decided.
"""
from __future__ import annotations

#: Printed size of every page number, in points. PDF points are print points,
#: so at 100% scale this is the size on paper.
PAGE_NUMBER_SIZE_PT = 10.0

#: Near-black ink for page numbers (slate-900). Luminance about 0.09, far darker
#: than the 0.2 ceiling the regression tests hold every page number to.
PAGE_NUMBER_INK = "#111827"

#: The darkest a page number may print, as relative luminance (0 black, 1 white).
MAX_PAGE_NUMBER_LUMINANCE = 0.2


def luminance(hex_color: str) -> float:
    """Relative luminance of #rrggbb, 0.0 (black) .. 1.0 (white)."""
    h = str(hex_color or "").strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except ValueError:
        return 1.0
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def page_number_ink(preferred: str | None = None) -> str:
    """The template's own dark text colour when it is near-black, else the standard ink."""
    if preferred and luminance(preferred) <= MAX_PAGE_NUMBER_LUMINANCE:
        return str(preferred)
    return PAGE_NUMBER_INK


def page_number_css(preferred_ink: str | None = None) -> str:
    """Inline CSS for an HTML-rendered (xhtml2pdf) page number.

    Inline on purpose: with xhtml2pdf 0.2.17 stylesheet rules for the number
    competed with each template's footer rules and the printed number kept the
    footer's small grey type. An inline style is what reliably reaches the page.
    """
    return (
        f"font-size: {PAGE_NUMBER_SIZE_PT:g}pt; "
        f"color: {page_number_ink(preferred_ink)}; font-weight: bold;"
    )


_BOLD_FONTS = {
    "Helvetica": "Helvetica-Bold",
    "Helvetica-Oblique": "Helvetica-BoldOblique",
    "Times-Roman": "Times-Bold",
    "Times-Italic": "Times-BoldItalic",
    "Courier": "Courier-Bold",
}


def bold_font(font_name: str, registered: set[str] | None = None) -> str:
    """The bold face of a ReportLab font, if one is available; else the font itself.

    Standard PDF fonts map directly. A registered TTF family named "X" is
    expected to register its bold as "X-Bold"; `registered` (reportlab's
    registered font names) confirms it exists before it is used.
    """
    name = str(font_name or "Helvetica")
    if name in _BOLD_FONTS:
        return _BOLD_FONTS[name]
    if "Bold" in name:
        return name
    candidate = f"{name}-Bold"
    if registered is None:
        try:
            from reportlab.pdfbase import pdfmetrics

            registered = set(pdfmetrics.getRegisteredFontNames())
        except Exception:                                   # noqa: BLE001
            registered = set()
    return candidate if candidate in registered else name
