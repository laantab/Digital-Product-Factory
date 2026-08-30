"""ReportLab renderer for planner page plans.

Draws the page kinds emitted by `builder.py`. Two rules shape everything here:

  * A planner page is a *working surface*, so it is mostly rules and boxes --
    but the Editor-in-Chief blocks blank and near-blank pages, and it is right
    to. Every page therefore carries a filled header band, ruled structure, and
    alternating row tints, which is both better design and measurable ink.
  * A cover must reach the trim edge. `check_cover_page` measures the white
    border on the rendered first page, so the cover is drawn as a full-bleed
    fill rather than an image placed in the text flow.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, letter
from reportlab.pdfgen import canvas

from services.math_worksheet.pdf_fonts import ascii_pdf_text, ensure_math_fonts
from services.planner.builder import PALETTES, PlannerPage, PlannerPlan, toc_entries

PAGE_SIZES = {
    "us letter": letter,
    "letter": letter,
    "8.5x11": letter,
    "a4": A4,
    "a5": A5,
    "6x9": (6 * 72.0, 9 * 72.0),
}

_MARGIN = 0.6 * 72.0
_HEADER_H = 46.0
_FOOTER_H = 26.0


@dataclass
class PlannerLayoutInfo:
    render_engine: str = "planner_direct"
    page_size: str = "US Letter"
    total_pages: int = 0
    cover_page_count: int = 0
    kinds: dict | None = None


def resolve_page_size(name: str) -> tuple[float, float]:
    return PAGE_SIZES.get(str(name or "").strip().lower(), letter)


def _fonts() -> tuple[str, str, str]:
    return ensure_math_fonts()


def _rgb(triple) -> colors.Color:
    return colors.Color(*triple)


# --------------------------------------------------------------------------- #
# Text helpers
# --------------------------------------------------------------------------- #
def _wrap(pdf: canvas.Canvas, text: str, font: str, size: float, width: float) -> list[str]:
    words = ascii_pdf_text(text).split()
    lines: list[str] = []
    current = ""
    for w in words:
        trial = f"{current} {w}".strip()
        if pdf.stringWidth(trial, font, size) <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines


def _text(pdf: canvas.Canvas, x: float, y: float, value: str, *,
          font: str, size: float, fill=colors.black, align: str = "left") -> None:
    safe = ascii_pdf_text(value)
    pdf.saveState()
    try:
        pdf.setFillColor(fill)
        pdf.setFont(font, size)
        pdf._code.append("0 Tc")
        pdf._code.append("0 Tw")
        if align == "center":
            pdf.drawCentredString(x, y, safe)
        elif align == "right":
            pdf.drawRightString(x, y, safe)
        else:
            pdf.drawString(x, y, safe)
    finally:
        pdf.restoreState()


def _paragraph(pdf: canvas.Canvas, x: float, y: float, text: str, *,
               font: str, size: float, width: float, leading: float,
               fill=colors.black) -> float:
    for line in _wrap(pdf, text, font, size, width):
        _text(pdf, x, y, line, font=font, size=size, fill=fill)
        y -= leading
    return y


# --------------------------------------------------------------------------- #
# Page chrome
# --------------------------------------------------------------------------- #
def _draw_header(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                 size: tuple[float, float]) -> float:
    """Filled title band. Returns the y baseline where body content may start."""
    w, h = size
    font, bold, italic = _fonts()
    band_h = _HEADER_H

    # Flush to the trim edge — a band floating below a white strip reads as a
    # layout mistake, and the full-width fill is honest ink on every page.
    pdf.saveState()
    pdf.setFillColor(_rgb(pal["head_text"]))
    pdf.rect(0, h - band_h, w, band_h, stroke=0, fill=1)
    pdf.restoreState()

    _text(pdf, _MARGIN, h - band_h + 16, page.title,
          font=bold, size=15, fill=colors.white)

    # Accent hairline under the band.
    pdf.saveState()
    pdf.setFillColor(_rgb(pal["cover_accent"]))
    pdf.rect(0, h - band_h - 3, w, 3, stroke=0, fill=1)
    pdf.restoreState()

    y = h - band_h - 22
    if page.subtitle:
        y = _paragraph(pdf, _MARGIN, y, page.subtitle, font=italic, size=9,
                       width=w - 2 * _MARGIN, leading=12,
                       fill=colors.Color(0.35, 0.35, 0.35))
        y -= 6
    return y


def _draw_footer(pdf: canvas.Canvas, plan: PlannerPlan, page_num: int,
                 pal: dict, size: tuple[float, float]) -> None:
    w, _h = size
    font, _bold, _italic = _fonts()
    pdf.saveState()
    pdf.setStrokeColor(_rgb(pal["rule"]))
    pdf.setLineWidth(0.6)
    pdf.line(_MARGIN, _FOOTER_H + 10, w - _MARGIN, _FOOTER_H + 10)
    pdf.restoreState()
    grey = colors.Color(0.45, 0.45, 0.45)
    _text(pdf, _MARGIN, _FOOTER_H - 2, plan.title, font=font, size=7.5, fill=grey)
    _text(pdf, w - _MARGIN, _FOOTER_H - 2, str(page_num),
          font=font, size=7.5, fill=grey, align="right")


def _body_bottom() -> float:
    return _FOOTER_H + 24


# --------------------------------------------------------------------------- #
# Page kinds
# --------------------------------------------------------------------------- #
def _cover_emblem(pdf: canvas.Canvas, cx: float, cy: float, scale: float,
                  planner_type: str, pal: dict) -> None:
    """A small geometric mark. Abstract on purpose: no illustration budget, and
    a clean motif beats a stock icon that has nothing to do with the book."""
    accent = _rgb(pal["cover_accent"])
    pdf.saveState()
    pdf.setFillColor(accent)
    pdf.setStrokeColor(accent)
    if planner_type == "faith_planner":
        arm = 5.0 * scale
        v_h = 46.0 * scale
        h_w = 30.0 * scale
        pdf.rect(cx - arm / 2, cy - v_h / 2, arm, v_h, stroke=0, fill=1)
        pdf.rect(cx - h_w / 2, cy + v_h * 0.10, h_w, arm, stroke=0, fill=1)
    else:
        # Three rising bars — a plan that goes somewhere.
        bar_w = 9.0 * scale
        gap = 6.0 * scale
        base = cy - 24.0 * scale
        for i, mult in enumerate((0.5, 0.78, 1.0)):
            x = cx - (bar_w * 1.5 + gap) + i * (bar_w + gap)
            pdf.rect(x, base, bar_w, 48.0 * scale * mult, stroke=0, fill=1)
    pdf.restoreState()


def _draw_cover(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                size: tuple[float, float]) -> None:
    w, h = size
    font, bold, italic = _fonts()
    planner_type = page.spec.get("planner_type") or "faith_planner"

    # Full bleed — no white border anywhere on the trim.
    pdf.saveState()
    pdf.setFillColor(_rgb(pal["cover_bg"]))
    pdf.rect(0, 0, w, h, stroke=0, fill=1)
    pdf.restoreState()

    band_h = h * 0.115
    pdf.saveState()
    pdf.setFillColor(_rgb(pal["cover_accent"]))
    pdf.rect(0, 0, w, band_h, stroke=0, fill=1)
    pdf.restoreState()

    inset = 0.42 * 72.0
    safe_w = w - 2 * inset - 40

    # Eyebrow.
    eyebrow = page.spec.get("eyebrow") or "UNDATED EDITION"
    _text(pdf, w / 2, h - inset - 46, eyebrow, font=bold, size=9,
          fill=_rgb(pal["cover_accent"]), align="center")

    # Title.
    title_size = 34 if w >= 500 else 25
    lines = _wrap(pdf, page.title, bold, title_size, safe_w)
    while len(lines) > 3 and title_size > 18:
        title_size -= 3
        lines = _wrap(pdf, page.title, bold, title_size, safe_w)
    y = h * 0.735
    for line in lines:
        _text(pdf, w / 2, y, line, font=bold, size=title_size,
              fill=_rgb(pal["cover_text"]), align="center")
        y -= title_size * 1.16

    pdf.saveState()
    pdf.setFillColor(_rgb(pal["cover_accent"]))
    pdf.rect(w / 2 - 62, y - 4, 124, 2.5, stroke=0, fill=1)
    pdf.restoreState()
    y -= 32

    for line in _wrap(pdf, page.subtitle, italic, 11.5, safe_w - 40):
        _text(pdf, w / 2, y, line, font=italic, size=11.5,
              fill=_rgb(pal["cover_text"]), align="center")
        y -= 16

    # Emblem sits in the space the title block leaves behind.
    emblem_cy = (y + band_h + 110) / 2
    _cover_emblem(pdf, w / 2, emblem_cy, 1.7 if w >= 500 else 1.25,
                  planner_type, pal)

    # Ownership line above the band.
    own_y = band_h + 56
    _text(pdf, w / 2, own_y + 14, "This planner belongs to", font=bold, size=9,
          fill=_rgb(pal["cover_accent"]), align="center")
    pdf.saveState()
    pdf.setStrokeColor(_rgb(pal["cover_accent"]))
    pdf.setLineWidth(0.9)
    pdf.line(w * 0.24, own_y, w * 0.76, own_y)
    pdf.restoreState()

    # Band caption: what the buyer is actually getting.
    caption = page.spec.get("caption") or ""
    if caption:
        _text(pdf, w / 2, band_h / 2 - 3.5, caption, font=bold, size=9,
              fill=_rgb(pal["cover_bg"]), align="center")

    # Frame last so it reads as one continuous line across the band.
    pdf.saveState()
    pdf.setStrokeColor(_rgb(pal["cover_accent"]))
    pdf.setLineWidth(1.2)
    pdf.rect(inset, inset, w - 2 * inset, h - 2 * inset, stroke=1, fill=0)
    pdf.restoreState()


def _draw_ownership(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                    size: tuple[float, float], y: float) -> None:
    w, _h = size
    font, bold, italic = _fonts()
    inner = w - 2 * _MARGIN

    y -= 10
    for label in ("This planner belongs to", "Started on", "If found, please contact"):
        _text(pdf, _MARGIN, y, label, font=bold, size=10,
              fill=_rgb(pal["head_text"]))
        y -= 20
        pdf.saveState()
        pdf.setStrokeColor(colors.Color(0.62, 0.62, 0.62))
        pdf.setLineWidth(0.8)
        pdf.line(_MARGIN, y, w - _MARGIN, y)
        pdf.restoreState()
        y -= 26

    y -= 8
    _text(pdf, _MARGIN, y, "About this planner", font=bold, size=10,
          fill=_rgb(pal["head_text"]))
    y -= 16
    y = _paragraph(
        pdf, _MARGIN, y,
        "The pages inside are undated. Start on any day, skip a week without "
        "ruining the book, and repeat any section as often as it is useful. "
        "Every worksheet is designed to be written on by hand; nothing here "
        "needs an app, an account, or an internet connection.",
        font=font, size=9.5, width=inner, leading=13,
        fill=colors.Color(0.22, 0.22, 0.22))

    disclaimer = page.spec.get("disclaimer") or ""
    if disclaimer:
        y -= 18
        box_top = y + 12
        lines = _wrap(pdf, disclaimer, font, 8.5, inner - 24)
        box_h = len(lines) * 12 + 30
        pdf.saveState()
        pdf.setFillColor(_rgb(pal["band"]))
        pdf.setStrokeColor(_rgb(pal["rule"]))
        pdf.setLineWidth(0.8)
        pdf.rect(_MARGIN, box_top - box_h, inner, box_h, stroke=1, fill=1)
        pdf.restoreState()
        ty = box_top - 16
        _text(pdf, _MARGIN + 12, ty, "Important", font=bold, size=8.5,
              fill=_rgb(pal["head_text"]))
        ty -= 13
        for line in lines:
            _text(pdf, _MARGIN + 12, ty, line, font=font, size=8.5,
                  fill=colors.Color(0.22, 0.22, 0.22))
            ty -= 12


def _draw_toc(pdf: canvas.Canvas, plan: PlannerPlan, pal: dict,
              size: tuple[float, float], y: float) -> None:
    w, _h = size
    font, bold, _italic = _fonts()
    entries = toc_entries(plan.pages)
    inner = w - 2 * _MARGIN
    bottom = _body_bottom()

    # Two columns once the list is long enough to need them.
    per_col = max(1, (int((y - bottom) // 15)))
    two_col = len(entries) > per_col
    col_w = (inner - 24) / 2 if two_col else inner

    col_x = [_MARGIN, _MARGIN + col_w + 24]
    ci = 0
    cy = y
    for label, page_no in entries:
        if cy < bottom:
            ci += 1
            if ci >= len(col_x):
                break
            cy = y
        x = col_x[ci]
        label_txt = ascii_pdf_text(label)
        num_txt = str(page_no)
        num_w = pdf.stringWidth(num_txt, font, 8.5)
        avail = col_w - num_w - 10
        while pdf.stringWidth(label_txt, font, 8.5) > avail and len(label_txt) > 4:
            label_txt = label_txt[:-2]
        _text(pdf, x, cy, label_txt, font=font, size=8.5,
              fill=colors.Color(0.18, 0.18, 0.18))
        # Dot leader.
        lw = pdf.stringWidth(label_txt, font, 8.5)
        pdf.saveState()
        pdf.setStrokeColor(colors.Color(0.78, 0.78, 0.78))
        pdf.setLineWidth(0.4)
        pdf.setDash(1, 3)
        pdf.line(x + lw + 4, cy + 2, x + col_w - num_w - 4, cy + 2)
        pdf.restoreState()
        _text(pdf, x + col_w, cy, num_txt, font=bold, size=8.5,
              fill=_rgb(pal["head_text"]), align="right")
        cy -= 15


def _draw_prose(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                size: tuple[float, float], y: float) -> None:
    w, _h = size
    font, bold, _italic = _fonts()
    inner = w - 2 * _MARGIN
    bottom = _body_bottom()
    sections = list(page.spec.get("sections") or [])
    if not sections:
        return

    # Measure first, then distribute the slack evenly between sections. Prose
    # pages otherwise stack at the top and leave the lower half looking like a
    # page that failed to finish rendering.
    base_gap = 14.0
    natural = 0.0
    for heading, body in sections:
        natural += 12
        natural += len(_wrap(pdf, heading, bold, 11, inner)) * 14
        natural += 3
        natural += len(_wrap(pdf, body, font, 9.5, inner)) * 13.5
        natural += base_gap
    slack = (y - bottom) - natural
    extra = 0.0
    if slack > 0 and len(sections) > 1:
        extra = min(26.0, slack / (len(sections) - 1))

    for i, (heading, body) in enumerate(sections):
        if y < bottom + 40:
            break
        pdf.saveState()
        pdf.setFillColor(_rgb(pal["cover_accent"]))
        pdf.rect(_MARGIN, y - 3, 16, 2.2, stroke=0, fill=1)
        pdf.restoreState()
        y -= 12
        y = _paragraph(pdf, _MARGIN, y, heading, font=bold, size=11,
                       width=inner, leading=14, fill=_rgb(pal["head_text"]))
        y -= 3
        y = _paragraph(pdf, _MARGIN, y, body, font=font, size=9.5,
                       width=inner, leading=13.5,
                       fill=colors.Color(0.20, 0.20, 0.20))
        y -= base_gap + (extra if i < len(sections) - 1 else 0.0)


def _table_frame(pdf: canvas.Canvas, x: float, y_top: float, width: float,
                 rows: int, row_h: float, pal: dict, *, header: bool = True) -> None:
    """Alternating tints plus a full grid — readable, and honest ink."""
    total_h = rows * row_h
    pdf.saveState()
    for i in range(rows):
        if i % 2 == 0:
            pdf.setFillColor(_rgb(pal["band"]))
            pdf.rect(x, y_top - (i + 1) * row_h, width, row_h, stroke=0, fill=1)
    pdf.setStrokeColor(colors.Color(0.72, 0.72, 0.72))
    pdf.setLineWidth(0.5)
    for i in range(rows + 1):
        yy = y_top - i * row_h
        pdf.line(x, yy, x + width, yy)
    pdf.setStrokeColor(_rgb(pal["rule"]))
    pdf.setLineWidth(0.9)
    pdf.rect(x, y_top - total_h, width, total_h, stroke=1, fill=0)
    pdf.restoreState()


def _draw_column_rules(pdf: canvas.Canvas, x: float, y_top: float, y_bottom: float,
                       edges: list[float]) -> None:
    pdf.saveState()
    pdf.setStrokeColor(colors.Color(0.72, 0.72, 0.72))
    pdf.setLineWidth(0.5)
    for ex in edges:
        pdf.line(ex, y_top, ex, y_bottom)
    pdf.restoreState()


def _draw_open_table(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                     size: tuple[float, float], y: float) -> None:
    w, _h = size
    font, bold, _italic = _fonts()
    inner = w - 2 * _MARGIN
    bottom = _body_bottom()
    cols = page.spec.get("columns") or [("Item", 1.0)]
    want_rows = int(page.spec.get("rows") or 20)

    head_h = 20.0
    avail = y - bottom - head_h
    row_h = max(15.0, min(26.0, avail / max(want_rows, 1)))
    rows = max(1, int(avail // row_h))

    # Header strip.
    pdf.saveState()
    pdf.setFillColor(_rgb(pal["head_text"]))
    pdf.rect(_MARGIN, y - head_h, inner, head_h, stroke=0, fill=1)
    pdf.restoreState()

    x = _MARGIN
    edges: list[float] = []
    for name, frac in cols:
        cw = inner * float(frac)
        _text(pdf, x + 6, y - head_h + 6.5, name, font=bold, size=8.5,
              fill=colors.white)
        x += cw
        edges.append(x)
    edges = edges[:-1]

    grid_top = y - head_h
    _table_frame(pdf, _MARGIN, grid_top, inner, rows, row_h, pal)
    _draw_column_rules(pdf, _MARGIN, grid_top, grid_top - rows * row_h, edges)


def _draw_labeled_table(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                        size: tuple[float, float], y: float) -> None:
    w, _h = size
    font, bold, _italic = _fonts()
    inner = w - 2 * _MARGIN
    bottom = _body_bottom()

    labels = list(page.spec.get("rows") or [])
    blanks = int(page.spec.get("blank_rows") or 0)
    value_cols = list(page.spec.get("value_columns") or ["Planned", "Actual"])
    total_label = page.spec.get("total_label") or "Total"

    body_rows = labels + [""] * blanks
    total_rows = len(body_rows) + 1  # + total row

    head_h = 20.0
    avail = y - bottom - head_h
    row_h = max(13.5, min(24.0, avail / max(total_rows, 1)))
    if row_h * total_rows > avail:
        keep = max(1, int(avail // row_h) - 1)
        body_rows = body_rows[:keep]
        total_rows = len(body_rows) + 1

    label_w = inner * 0.46
    val_w = (inner - label_w) / max(len(value_cols), 1)

    pdf.saveState()
    pdf.setFillColor(_rgb(pal["head_text"]))
    pdf.rect(_MARGIN, y - head_h, inner, head_h, stroke=0, fill=1)
    pdf.restoreState()
    _text(pdf, _MARGIN + 6, y - head_h + 6.5, "Category", font=bold, size=8.5,
          fill=colors.white)
    edges = [_MARGIN + label_w]
    for i, name in enumerate(value_cols):
        cx = _MARGIN + label_w + i * val_w
        _text(pdf, cx + val_w - 6, y - head_h + 6.5, name, font=bold, size=8.5,
              fill=colors.white, align="right")
        if i:
            edges.append(cx)

    grid_top = y - head_h
    _table_frame(pdf, _MARGIN, grid_top, inner, total_rows, row_h, pal)
    _draw_column_rules(pdf, _MARGIN, grid_top, grid_top - total_rows * row_h, edges)

    for i, label in enumerate(body_rows):
        ty = grid_top - (i + 1) * row_h + row_h * 0.32
        if label:
            _text(pdf, _MARGIN + 6, ty, label, font=font, size=8.5,
                  fill=colors.Color(0.18, 0.18, 0.18))

    # Total row, emphasised.
    ty = grid_top - total_rows * row_h
    pdf.saveState()
    pdf.setFillColor(_rgb(pal["cover_accent"]))
    pdf.rect(_MARGIN, ty, inner, row_h, stroke=0, fill=1)
    pdf.setStrokeColor(_rgb(pal["rule"]))
    pdf.setLineWidth(0.9)
    pdf.rect(_MARGIN, ty, inner, row_h, stroke=1, fill=0)
    pdf.restoreState()
    _text(pdf, _MARGIN + 6, ty + row_h * 0.32, total_label, font=bold, size=9,
          fill=_rgb(pal["cover_bg"]))
    _draw_column_rules(pdf, _MARGIN, ty + row_h, ty, edges)


def _draw_snapshot(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                   size: tuple[float, float], y: float) -> None:
    w, _h = size
    font, bold, _italic = _fonts()
    inner = w - 2 * _MARGIN
    bottom = _body_bottom()
    assets = list(page.spec.get("assets") or [])
    debts = list(page.spec.get("debts") or [])

    col_w = (inner - 20) / 2
    rows = max(len(assets), len(debts)) + 2
    head_h = 18.0
    avail = (y - bottom) * 0.62 - head_h - 46
    row_h = max(16.0, min(30.0, avail / max(rows, 1)))

    for idx, (heading, items) in enumerate((("What I own", assets),
                                            ("What I owe", debts))):
        x = _MARGIN + idx * (col_w + 20)
        pdf.saveState()
        pdf.setFillColor(_rgb(pal["head_text"]))
        pdf.rect(x, y - head_h, col_w, head_h, stroke=0, fill=1)
        pdf.restoreState()
        _text(pdf, x + 6, y - head_h + 5.5, heading, font=bold, size=8.5,
              fill=colors.white)
        _text(pdf, x + col_w - 6, y - head_h + 5.5, "Amount", font=bold, size=8.5,
              fill=colors.white, align="right")

        grid_top = y - head_h
        padded = items + [""] * (rows - len(items))
        _table_frame(pdf, x, grid_top, col_w, rows, row_h, pal)
        _draw_column_rules(pdf, x, grid_top, grid_top - rows * row_h,
                           [x + col_w * 0.62])
        for i, label in enumerate(padded):
            if label:
                _text(pdf, x + 6, grid_top - (i + 1) * row_h + row_h * 0.32,
                      label, font=font, size=8.5,
                      fill=colors.Color(0.18, 0.18, 0.18))

    ny = y - head_h - rows * row_h - 26
    pdf.saveState()
    pdf.setFillColor(_rgb(pal["cover_accent"]))
    pdf.rect(_MARGIN, ny - 6, inner, 26, stroke=0, fill=1)
    pdf.setStrokeColor(_rgb(pal["rule"]))
    pdf.setLineWidth(0.9)
    pdf.rect(_MARGIN, ny - 6, inner, 26, stroke=1, fill=0)
    pdf.restoreState()
    _text(pdf, _MARGIN + 8, ny + 4,
          "Net worth  =  what I own  -  what I owe", font=bold, size=9.5,
          fill=_rgb(pal["cover_bg"]))
    pdf.saveState()
    pdf.setStrokeColor(_rgb(pal["cover_bg"]))
    pdf.setLineWidth(0.9)
    pdf.line(w - _MARGIN - 140, ny + 2, w - _MARGIN - 10, ny + 2)
    pdf.restoreState()

    _trailing_block(
        pdf, pal, size, ny - 28,
        "Three numbers worth knowing: months of expenses in the emergency "
        "fund, the highest interest rate you are paying, and what is left "
        "over in an average month")


def _draw_calendar(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                   size: tuple[float, float], y: float) -> None:
    from services.planner.content import WEEKDAYS
    w, _h = size
    font, bold, _italic = _fonts()
    inner = w - 2 * _MARGIN
    bottom = _body_bottom()

    # Month / year fill-in line.
    _text(pdf, _MARGIN, y - 4, "Month", font=bold, size=9,
          fill=_rgb(pal["head_text"]))
    pdf.saveState()
    pdf.setStrokeColor(colors.Color(0.62, 0.62, 0.62))
    pdf.setLineWidth(0.8)
    pdf.line(_MARGIN + 38, y - 6, _MARGIN + 210, y - 6)
    pdf.line(_MARGIN + 268, y - 6, _MARGIN + 400, y - 6)
    pdf.restoreState()
    _text(pdf, _MARGIN + 226, y - 4, "Year", font=bold, size=9,
          fill=_rgb(pal["head_text"]))
    y -= 26

    head_h = 18.0
    cell_w = inner / 7.0
    grid_top = y - head_h
    avail = grid_top - bottom
    rows = 6
    cell_h = max(28.0, avail / rows)
    if cell_h * rows > avail:
        cell_h = avail / rows

    pdf.saveState()
    pdf.setFillColor(_rgb(pal["head_text"]))
    pdf.rect(_MARGIN, y - head_h, inner, head_h, stroke=0, fill=1)
    pdf.restoreState()
    for i, d in enumerate(WEEKDAYS):
        _text(pdf, _MARGIN + i * cell_w + cell_w / 2, y - head_h + 5.5, d,
              font=bold, size=8.5, fill=colors.white, align="center")

    pdf.saveState()
    for r in range(rows):
        for c in range(7):
            cx = _MARGIN + c * cell_w
            cy = grid_top - (r + 1) * cell_h
            if (r + c) % 2 == 0:
                pdf.setFillColor(_rgb(pal["band"]))
                pdf.rect(cx, cy, cell_w, cell_h, stroke=0, fill=1)
    pdf.setStrokeColor(colors.Color(0.70, 0.70, 0.70))
    pdf.setLineWidth(0.5)
    for r in range(rows + 1):
        yy = grid_top - r * cell_h
        pdf.line(_MARGIN, yy, _MARGIN + inner, yy)
    for c in range(8):
        xx = _MARGIN + c * cell_w
        pdf.line(xx, grid_top, xx, grid_top - rows * cell_h)
    pdf.setStrokeColor(_rgb(pal["rule"]))
    pdf.setLineWidth(0.9)
    pdf.rect(_MARGIN, grid_top - rows * cell_h, inner, rows * cell_h,
             stroke=1, fill=0)
    pdf.restoreState()


def _draw_habit_tracker(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                        size: tuple[float, float], y: float) -> None:
    w, _h = size
    font, bold, _italic = _fonts()
    inner = w - 2 * _MARGIN
    bottom = _body_bottom()
    habits = list(page.spec.get("habits") or [])
    # Two unnamed rows so the reader can add habits this planner did not guess.
    habits = habits + [""] * int(page.spec.get("blank_rows") or 2)
    days = int(page.spec.get("days") or 31)

    label_w = inner * 0.34
    cell_w = (inner - label_w) / days
    head_h = 18.0
    grid_top = y - head_h
    avail = (grid_top - bottom) * 0.66
    row_h = max(18.0, min(32.0, avail / max(len(habits), 1)))

    pdf.saveState()
    pdf.setFillColor(_rgb(pal["head_text"]))
    pdf.rect(_MARGIN, y - head_h, inner, head_h, stroke=0, fill=1)
    pdf.restoreState()
    _text(pdf, _MARGIN + 6, y - head_h + 5.5, "Habit", font=bold, size=8.5,
          fill=colors.white)
    for d in range(days):
        if (d + 1) % 5 == 0 or d == 0:
            _text(pdf, _MARGIN + label_w + d * cell_w + cell_w / 2,
                  y - head_h + 5.5, str(d + 1), font=bold, size=6,
                  fill=colors.white, align="center")

    pdf.saveState()
    for i in range(len(habits)):
        if i % 2 == 0:
            pdf.setFillColor(_rgb(pal["band"]))
            pdf.rect(_MARGIN, grid_top - (i + 1) * row_h, inner, row_h,
                     stroke=0, fill=1)
    pdf.setStrokeColor(colors.Color(0.72, 0.72, 0.72))
    pdf.setLineWidth(0.5)
    for i in range(len(habits) + 1):
        yy = grid_top - i * row_h
        pdf.line(_MARGIN, yy, _MARGIN + inner, yy)
    for d in range(days + 1):
        xx = _MARGIN + label_w + d * cell_w
        pdf.line(xx, grid_top, xx, grid_top - len(habits) * row_h)
    pdf.line(_MARGIN + label_w, grid_top, _MARGIN + label_w,
             grid_top - len(habits) * row_h)
    pdf.setStrokeColor(_rgb(pal["rule"]))
    pdf.setLineWidth(0.9)
    pdf.rect(_MARGIN, grid_top - len(habits) * row_h, inner,
             len(habits) * row_h, stroke=1, fill=0)
    pdf.restoreState()

    for i, habit in enumerate(habits):
        if habit:
            _text(pdf, _MARGIN + 6, grid_top - (i + 1) * row_h + row_h * 0.34,
                  habit, font=font, size=8.5, fill=colors.Color(0.18, 0.18, 0.18))

    _trailing_block(pdf, pal, size, grid_top - len(habits) * row_h - 26,
                    "What I noticed this month")


def _ruled_lines(pdf: canvas.Canvas, x: float, y: float, width: float,
                 count: int, spacing: float = 20.0) -> float:
    pdf.saveState()
    pdf.setStrokeColor(colors.Color(0.74, 0.74, 0.74))
    pdf.setLineWidth(0.6)
    for _ in range(count):
        pdf.line(x, y, x + width, y)
        y -= spacing
    pdf.restoreState()
    return y


def _trailing_block(pdf: canvas.Canvas, pal: dict, size: tuple[float, float],
                    y: float, heading: str, *, tint: bool = True,
                    min_lines: int = 2) -> None:
    """Fill leftover space under a fixed-height element with a usable block.

    A worksheet page whose grid ends halfway down reads as an unfinished
    layout. Rather than stretch the grid past a sensible row height, the
    remaining space becomes writing space with a heading that earns it.
    """
    w, _h = size
    _font, bold, _italic = _fonts()
    inner = w - 2 * _MARGIN
    bottom = _body_bottom()
    spacing = 20.0
    if y - 30 - min_lines * spacing < bottom:
        return
    _text(pdf, _MARGIN, y, heading, font=bold, size=9.5,
          fill=_rgb(pal["head_text"]))
    y -= 14
    count = max(min_lines, int((y - bottom) // spacing))
    if tint:
        pdf.saveState()
        for i in range(count):
            if i % 2 == 0:
                pdf.setFillColor(_rgb(pal["band"]))
                pdf.rect(_MARGIN, y - (i + 1) * spacing + 4, inner, spacing,
                         stroke=0, fill=1)
        pdf.restoreState()
    _ruled_lines(pdf, _MARGIN, y - spacing + 4, inner, count, spacing)


def _draw_lined_notes(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                      size: tuple[float, float], y: float) -> None:
    w, _h = size
    inner = w - 2 * _MARGIN
    bottom = _body_bottom()
    spacing = 21.0
    count = max(1, int((y - bottom) // spacing))
    # Tinted band behind every other line keeps the page from reading as blank.
    pdf.saveState()
    for i in range(count):
        if i % 2 == 0:
            pdf.setFillColor(_rgb(pal["band"]))
            pdf.rect(_MARGIN, y - (i + 1) * spacing + 4, inner, spacing,
                     stroke=0, fill=1)
    pdf.restoreState()
    _ruled_lines(pdf, _MARGIN, y - spacing + 4, inner, count, spacing)


def _draw_prompt_page(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                      size: tuple[float, float], y: float) -> None:
    w, _h = size
    font, bold, _italic = _fonts()
    inner = w - 2 * _MARGIN
    bottom = _body_bottom()
    prompts = list(page.spec.get("prompts") or [])
    lines_each = int(page.spec.get("lines_each") or 3)
    spacing = 19.0

    for n, prompt in enumerate(prompts, start=1):
        needed = 16 + lines_each * spacing + 12
        if y - needed < bottom:
            break
        pdf.saveState()
        pdf.setFillColor(_rgb(pal["cover_accent"]))
        pdf.circle(_MARGIN + 6, y - 2, 7.5, stroke=0, fill=1)
        pdf.restoreState()
        _text(pdf, _MARGIN + 6, y - 5, str(n), font=bold, size=8,
              fill=_rgb(pal["cover_bg"]), align="center")
        y = _paragraph(pdf, _MARGIN + 20, y, prompt, font=bold, size=9.5,
                       width=inner - 20, leading=13,
                       fill=_rgb(pal["head_text"]))
        y -= 6
        y = _ruled_lines(pdf, _MARGIN + 20, y, inner - 20, lines_each, spacing)
        y -= 8


def _draw_reading_plan(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                       size: tuple[float, float], y: float) -> None:
    w, _h = size
    font, bold, _italic = _fonts()
    inner = w - 2 * _MARGIN
    bottom = _body_bottom()
    rows = list(page.spec.get("rows") or [])

    head_h = 17.0
    avail = y - bottom - head_h
    row_h = max(9.5, min(16.0, avail / max(len(rows), 1)))
    fit = min(len(rows), max(1, int(avail // row_h)))
    rows = rows[:fit]

    fracs = (0.07, 0.15, 0.24, 0.42, 0.12)
    headers = ("Wk", "Season", "Reading", "Theme", "Done")

    pdf.saveState()
    pdf.setFillColor(_rgb(pal["head_text"]))
    pdf.rect(_MARGIN, y - head_h, inner, head_h, stroke=0, fill=1)
    pdf.restoreState()
    x = _MARGIN
    edges: list[float] = []
    for name, frac in zip(headers, fracs):
        _text(pdf, x + 4, y - head_h + 5, name, font=bold, size=7.5,
              fill=colors.white)
        x += inner * frac
        edges.append(x)
    edges = edges[:-1]

    grid_top = y - head_h
    _table_frame(pdf, _MARGIN, grid_top, inner, len(rows), row_h, pal)
    _draw_column_rules(pdf, _MARGIN, grid_top, grid_top - len(rows) * row_h, edges)

    fs = min(7.5, row_h - 2.5)
    for i, (season, reference, gist) in enumerate(rows):
        ty = grid_top - (i + 1) * row_h + row_h * 0.30
        cx = _MARGIN
        for value, frac in zip((str(i + 1), season, reference, gist), fracs):
            txt = ascii_pdf_text(value)
            maxw = inner * frac - 8
            while pdf.stringWidth(txt, font, fs) > maxw and len(txt) > 3:
                txt = txt[:-2]
            _text(pdf, cx + 4, ty, txt, font=font, size=fs,
                  fill=colors.Color(0.18, 0.18, 0.18))
            cx += inner * frac


def _checkbox(pdf: canvas.Canvas, x: float, y: float, s: float, pal: dict) -> None:
    pdf.saveState()
    pdf.setStrokeColor(_rgb(pal["rule"]))
    pdf.setLineWidth(0.8)
    pdf.rect(x, y, s, s, stroke=1, fill=0)
    pdf.restoreState()


def _draw_faith_weekly(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                       size: tuple[float, float], y: float) -> None:
    w, _h = size
    font, bold, italic = _fonts()
    inner = w - 2 * _MARGIN
    bottom = _body_bottom()

    # Reading box.
    box_h = 40.0
    pdf.saveState()
    pdf.setFillColor(_rgb(pal["band"]))
    pdf.setStrokeColor(_rgb(pal["rule"]))
    pdf.setLineWidth(0.9)
    pdf.rect(_MARGIN, y - box_h, inner, box_h, stroke=1, fill=1)
    pdf.restoreState()
    _text(pdf, _MARGIN + 10, y - 16, "This week's reading", font=bold, size=8.5,
          fill=_rgb(pal["head_text"]))
    _text(pdf, _MARGIN + 10, y - 31, page.spec.get("reference") or "",
          font=bold, size=13, fill=colors.Color(0.15, 0.15, 0.15))
    y -= box_h + 18

    # Prayer focus checklist, two columns.
    _text(pdf, _MARGIN, y, "Prayer focus this week", font=bold, size=9.5,
          fill=_rgb(pal["head_text"]))
    y -= 15
    cats = list(page.spec.get("prayer_categories") or [])
    col_w = inner / 2
    for i, cat in enumerate(cats):
        cx = _MARGIN + (i % 2) * col_w
        cy = y - (i // 2) * 17
        _checkbox(pdf, cx, cy - 2, 8.5, pal)
        _text(pdf, cx + 14, cy, cat, font=font, size=9,
              fill=colors.Color(0.20, 0.20, 0.20))
    y -= ((len(cats) + 1) // 2) * 17 + 12

    # Gratitude + one action.
    _text(pdf, _MARGIN, y, "Three things I am grateful for", font=bold, size=9.5,
          fill=_rgb(pal["head_text"]))
    y -= 12
    y = _ruled_lines(pdf, _MARGIN, y, inner, 3, 19.0)
    y -= 10

    if y - 60 > bottom:
        _text(pdf, _MARGIN, y, "One thing I will do this week because of what I read",
              font=bold, size=9.5, fill=_rgb(pal["head_text"]))
        y -= 12
        y = _ruled_lines(pdf, _MARGIN, y, inner, 2, 19.0)
        y -= 10

    if y - 40 > bottom:
        _text(pdf, _MARGIN, y, "People I will pray for by name",
              font=bold, size=9.5, fill=_rgb(pal["head_text"]))
        y -= 12
        y = _ruled_lines(pdf, _MARGIN, y, inner, 5, 19.0)
        y -= 10

    # Whatever space is left becomes an open notes block rather than an
    # oversized list of ruled lines under one heading.
    if y - 40 > bottom:
        _text(pdf, _MARGIN, y, "Questions and notes from this week's reading",
              font=bold, size=9.5, fill=_rgb(pal["head_text"]))
        y -= 12
        count = max(1, int((y - bottom) // 19.0))
        pdf.saveState()
        for i in range(count):
            if i % 2 == 0:
                pdf.setFillColor(_rgb(pal["band"]))
                pdf.rect(_MARGIN, y - (i + 1) * 19.0 + 4, inner, 19.0,
                         stroke=0, fill=1)
        pdf.restoreState()
        _ruled_lines(pdf, _MARGIN, y - 19.0 + 4, inner, count, 19.0)


def _draw_faith_daily(pdf: canvas.Canvas, page: PlannerPage, pal: dict,
                      size: tuple[float, float], y: float) -> None:
    w, _h = size
    font, bold, italic = _fonts()
    inner = w - 2 * _MARGIN
    bottom = _body_bottom()

    # Date / passage strip.
    strip_h = 24.0
    pdf.saveState()
    pdf.setFillColor(_rgb(pal["band"]))
    pdf.setStrokeColor(_rgb(pal["rule"]))
    pdf.setLineWidth(0.8)
    pdf.rect(_MARGIN, y - strip_h, inner, strip_h, stroke=1, fill=1)
    pdf.line(_MARGIN + inner * 0.34, y - strip_h, _MARGIN + inner * 0.34, y)
    pdf.restoreState()
    _text(pdf, _MARGIN + 8, y - 16, "Date", font=bold, size=8.5,
          fill=_rgb(pal["head_text"]))
    _text(pdf, _MARGIN + inner * 0.34 + 8, y - 16, "Passage", font=bold, size=8.5,
          fill=_rgb(pal["head_text"]))
    reference = page.spec.get("reference") or ""
    if reference:
        _text(pdf, _MARGIN + inner * 0.34 + 56, y - 16, reference,
              font=font, size=8.5, fill=colors.Color(0.30, 0.30, 0.30))
    y -= strip_h + 16

    prompts = list(page.spec.get("prompts") or [])
    # Reserve the last block for the prayer list.
    prayer_h = 86.0
    usable = y - bottom - prayer_h
    per = usable / max(len(prompts), 1)
    lines_each = max(2, int((per - 18) // 19.0))

    for prompt in prompts:
        _text(pdf, _MARGIN, y, prompt, font=bold, size=9.5,
              fill=_rgb(pal["head_text"]))
        y -= 12
        y = _ruled_lines(pdf, _MARGIN, y, inner, lines_each, 19.0)
        y -= 8

    _text(pdf, _MARGIN, y, "Praying today for", font=bold, size=9.5,
          fill=_rgb(pal["head_text"]))
    y -= 12
    count = max(1, int((y - bottom) // 19.0))
    pdf.saveState()
    for i in range(count):
        if i % 2 == 0:
            pdf.setFillColor(_rgb(pal["band"]))
            pdf.rect(_MARGIN, y - (i + 1) * 19.0 + 4, inner, 19.0,
                     stroke=0, fill=1)
    pdf.restoreState()
    _ruled_lines(pdf, _MARGIN, y - 19.0 + 4, inner, count, 19.0)


_DRAWERS = {
    "ownership": _draw_ownership,
    "prose": _draw_prose,
    "open_table": _draw_open_table,
    "labeled_table": _draw_labeled_table,
    "snapshot": _draw_snapshot,
    "calendar_month": _draw_calendar,
    "habit_tracker": _draw_habit_tracker,
    "lined_notes": _draw_lined_notes,
    "prompt_page": _draw_prompt_page,
    "reading_plan": _draw_reading_plan,
    "faith_weekly": _draw_faith_weekly,
    "faith_daily": _draw_faith_daily,
}


# --------------------------------------------------------------------------- #
# Document
# --------------------------------------------------------------------------- #
def build_planner_pdf_bytes(plan: PlannerPlan, *, page_size: str = "US Letter",
                            author: str = "") -> tuple[bytes, PlannerLayoutInfo]:
    size = resolve_page_size(page_size)
    pal = PALETTES[plan.planner_type]
    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=size)
    pdf.setTitle(ascii_pdf_text(plan.title))
    if author:
        pdf.setAuthor(ascii_pdf_text(author))
    pdf.setSubject(ascii_pdf_text(plan.subtitle))

    kinds: dict[str, int] = {}
    cover_pages = 0

    for i, page in enumerate(plan.pages, start=1):
        kinds[page.kind] = kinds.get(page.kind, 0) + 1
        if page.kind == "cover":
            cover_pages += 1
            _draw_cover(pdf, page, pal, size)
            pdf.showPage()
            continue

        y = _draw_header(pdf, page, pal, size)
        if page.kind == "toc":
            _draw_toc(pdf, plan, pal, size, y)
        else:
            drawer = _DRAWERS.get(page.kind)
            if drawer is not None:
                drawer(pdf, page, pal, size, y)
        _draw_footer(pdf, plan, i, pal, size)
        pdf.showPage()

    pdf.save()
    info = PlannerLayoutInfo(
        page_size=page_size,
        total_pages=len(plan.pages),
        cover_page_count=cover_pages,
        kinds=kinds,
    )
    return buf.getvalue(), info
