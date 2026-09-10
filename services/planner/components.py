"""Reusable page components for the planner renderer.

Every visual element a planner page is built from lives here: ornaments,
panels, rules, writing lines, badges, tables, and the page chrome (header and
footer). Each component reads its colours, faces and radius from the theme it
is handed, so a page kind never carries its own styling and two page kinds can
never drift apart.

Coordinates are ReportLab points with the origin at the bottom-left.
"""
from __future__ import annotations

import math

from reportlab.lib import colors
from reportlab.pdfgen import canvas

from services.math_worksheet.pdf_fonts import ascii_pdf_text
from services.planner.themes import SPACING, PlannerTheme

GREY_TEXT = colors.Color(0.22, 0.22, 0.22)


# --------------------------------------------------------------------------- #
# Text
# --------------------------------------------------------------------------- #
def wrap(pdf: canvas.Canvas, text: str, font: str, size: float, width: float) -> list[str]:
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


def text(pdf: canvas.Canvas, x: float, y: float, value: str, *, font: str,
         size: float, fill=colors.black, align: str = "left",
         tracking: float = 0.0) -> None:
    safe = ascii_pdf_text(value)
    pdf.saveState()
    try:
        pdf.setFillColor(fill)
        pdf.setFont(font, size)
        pdf._code.append(f"{tracking:.2f} Tc")
        pdf._code.append("0 Tw")
        if align == "center":
            pdf.drawCentredString(x, y, safe)
        elif align == "right":
            pdf.drawRightString(x, y, safe)
        else:
            pdf.drawString(x, y, safe)
    finally:
        pdf.restoreState()


def text_width(pdf: canvas.Canvas, value: str, font: str, size: float,
               tracking: float = 0.0) -> float:
    safe = ascii_pdf_text(value)
    return pdf.stringWidth(safe, font, size) + tracking * max(len(safe) - 1, 0)


def paragraph(pdf: canvas.Canvas, x: float, y: float, value: str, *, font: str,
              size: float, width: float, leading: float, fill=colors.black,
              align: str = "left") -> float:
    for line in wrap(pdf, value, font, size, width):
        if align == "center":
            text(pdf, x + width / 2, y, line, font=font, size=size, fill=fill, align="center")
        else:
            text(pdf, x, y, line, font=font, size=size, fill=fill)
        y -= leading
    return y


def small_caps(pdf: canvas.Canvas, T: PlannerTheme, x: float, y: float, value: str, *,
               size: float = 7.5, fill=None, align: str = "left") -> None:
    """Uppercase, tracked label -- the quiet voice of the design system."""
    f = T.fonts()
    # Tracking is capped at ~12% of the size: wider gaps make PDF text
    # extraction read "24 PAGES" as "2 4 P A G E S", which would hide the
    # cover's page-count claim from the reviewer.
    text(pdf, x, y, str(value or "").upper(), font=f.label, size=size,
         fill=fill or T.rgb("muted"), align=align, tracking=min(1.1, size * 0.12))


def fit_text_size(pdf: canvas.Canvas, value: str, font: str, size: float,
                  width: float, *, min_size: float = 8.0, max_lines: int = 1) -> float:
    """Largest size (<= size) at which `value` fits `width` in `max_lines`."""
    s = size
    while s > min_size:
        if len(wrap(pdf, value, font, s, width)) <= max_lines:
            return s
        s -= 0.5
    return min_size


# --------------------------------------------------------------------------- #
# Shapes
# --------------------------------------------------------------------------- #
def rounded_panel(pdf: canvas.Canvas, T: PlannerTheme, x: float, y: float,
                  w: float, h: float, *, fill: str | None = "accent_soft",
                  stroke: str | None = "rule", stroke_width: float = 0.7,
                  radius: float | None = None) -> None:
    pdf.saveState()
    r = T.corner_radius if radius is None else radius
    if fill:
        pdf.setFillColor(T.rgb(fill))
    if stroke:
        pdf.setStrokeColor(T.rgb(stroke))
        pdf.setLineWidth(stroke_width)
    pdf.roundRect(x, y, w, h, r, stroke=1 if stroke else 0, fill=1 if fill else 0)
    pdf.restoreState()


def hairline(pdf: canvas.Canvas, T: PlannerTheme, x1: float, y1: float,
             x2: float, y2: float, *, token: str = "rule", width: float = 0.6,
             dotted: bool = False) -> None:
    pdf.saveState()
    pdf.setStrokeColor(T.rgb(token))
    pdf.setLineWidth(width)
    if dotted:
        pdf.setDash(0.8, 2.6)
        pdf.setLineCap(1)
    pdf.line(x1, y1, x2, y2)
    pdf.restoreState()


def accent_bar(pdf: canvas.Canvas, T: PlannerTheme, x: float, y: float,
               w: float = 18.0, h: float = 2.2, token: str = "accent") -> None:
    pdf.saveState()
    pdf.setFillColor(T.rgb(token))
    pdf.rect(x, y, w, h, stroke=0, fill=1)
    pdf.restoreState()


def checkbox(pdf: canvas.Canvas, T: PlannerTheme, x: float, y: float,
             s: float = 9.0) -> None:
    pdf.saveState()
    pdf.setStrokeColor(T.rgb("primary"))
    pdf.setLineWidth(0.8)
    pdf.roundRect(x, y, s, s, 1.6, stroke=1, fill=0)
    pdf.restoreState()


def number_badge(pdf: canvas.Canvas, T: PlannerTheme, cx: float, cy: float,
                 n: int | str, *, r: float = 8.0, fill: str = "accent",
                 ink: str = "paper") -> None:
    f = T.fonts()
    pdf.saveState()
    pdf.setFillColor(T.rgb(fill))
    pdf.circle(cx, cy, r, stroke=0, fill=1)
    pdf.restoreState()
    text(pdf, cx, cy - 3.0, str(n), font=f.label, size=r * 1.05,
         fill=T.rgb(ink), align="center")


# --------------------------------------------------------------------------- #
# Ornaments -- small, print-safe, drawn (never bitmapped)
# --------------------------------------------------------------------------- #
def _leaf(pdf: canvas.Canvas, x: float, y: float, length: float, angle_deg: float,
          flip: float = 1.0) -> None:
    """One leaf as two bezier curves meeting at the tip."""
    a = math.radians(angle_deg)
    tx, ty = x + math.cos(a) * length, y + math.sin(a) * length
    nx, ny = -math.sin(a) * length * 0.32 * flip, math.cos(a) * length * 0.32 * flip
    mx, my = x + math.cos(a) * length * 0.5, y + math.sin(a) * length * 0.5
    p = pdf.beginPath()
    p.moveTo(x, y)
    p.curveTo(mx + nx, my + ny, mx + nx, my + ny, tx, ty)
    p.curveTo(mx - nx * 0.15, my - ny * 0.15, mx - nx * 0.15, my - ny * 0.15, x, y)
    p.close()
    pdf.drawPath(p, stroke=0, fill=1)


def sprig(pdf: canvas.Canvas, T: PlannerTheme, x: float, y: float, *,
          length: float = 48.0, angle_deg: float = 0.0, leaves: int = 5,
          token: str = "accent", scale: float = 1.0) -> None:
    """A botanical sprig: a gently curved stem with alternating leaves."""
    a = math.radians(angle_deg)
    pdf.saveState()
    pdf.setStrokeColor(T.rgb(token))
    pdf.setFillColor(T.rgb(token))
    pdf.setLineWidth(0.8 * scale)
    ex, ey = x + math.cos(a) * length, y + math.sin(a) * length
    cx, cy = x + math.cos(a + 0.35) * length * 0.55, y + math.sin(a + 0.35) * length * 0.55
    p = pdf.beginPath()
    p.moveTo(x, y)
    p.curveTo(cx, cy, cx, cy, ex, ey)
    pdf.drawPath(p, stroke=1, fill=0)
    for i in range(leaves):
        t = (i + 1) / (leaves + 1)
        # Point on the quadratic-ish curve.
        px = (1 - t) ** 2 * x + 2 * (1 - t) * t * cx + t ** 2 * ex
        py = (1 - t) ** 2 * y + 2 * (1 - t) * t * cy + t ** 2 * ey
        side = 1.0 if i % 2 == 0 else -1.0
        leaf_len = (9.0 + 4.0 * (1 - t)) * scale
        _leaf(pdf, px, py, leaf_len, angle_deg + side * 55.0, flip=side)
    pdf.restoreState()


def ornament(pdf: canvas.Canvas, T: PlannerTheme, cx: float, cy: float, *,
             width: float = 120.0, kind: str | None = None, token: str = "accent",
             scale: float = 1.0) -> None:
    """The theme's divider mark, centred on (cx, cy)."""
    kind = kind or T.ornament
    pdf.saveState()
    pdf.setStrokeColor(T.rgb(token))
    pdf.setFillColor(T.rgb(token))
    pdf.setLineWidth(0.7 * scale)
    half = width / 2
    if kind == "line":
        pdf.line(cx - half, cy, cx + half, cy)
    elif kind == "diamond":
        d = 3.6 * scale
        pdf.line(cx - half, cy, cx - d - 5, cy)
        pdf.line(cx + d + 5, cy, cx + half, cy)
        p = pdf.beginPath()
        p.moveTo(cx, cy + d); p.lineTo(cx + d, cy); p.lineTo(cx, cy - d); p.lineTo(cx - d, cy)
        p.close()
        pdf.drawPath(p, stroke=0, fill=1)
    elif kind == "chevron":
        d = 4.0 * scale
        pdf.line(cx - half, cy, cx - d * 3, cy)
        pdf.line(cx + d * 3, cy, cx + half, cy)
        for off in (-d * 1.4, d * 1.4):
            p = pdf.beginPath()
            p.moveTo(cx + off - d, cy - d * 0.8); p.lineTo(cx + off, cy + d * 0.8)
            p.lineTo(cx + off + d, cy - d * 0.8)
            pdf.drawPath(p, stroke=1, fill=0)
    elif kind == "leaf":
        pdf.line(cx - half, cy, cx - 22 * scale, cy)
        pdf.line(cx + 22 * scale, cy, cx + half, cy)
        pdf.restoreState()
        sprig(pdf, T, cx - 18 * scale, cy - 2, length=16 * scale, angle_deg=8, leaves=3,
              token=token, scale=0.75 * scale)
        sprig(pdf, T, cx + 18 * scale, cy - 2, length=16 * scale, angle_deg=172, leaves=3,
              token=token, scale=0.75 * scale)
        return
    elif kind == "sun":
        r = 3.4 * scale
        pdf.line(cx - half, cy, cx - r * 4, cy)
        pdf.line(cx + r * 4, cy, cx + half, cy)
        pdf.circle(cx, cy, r, stroke=0, fill=1)
        for k in range(8):
            a = math.radians(k * 45)
            pdf.line(cx + math.cos(a) * (r + 2), cy + math.sin(a) * (r + 2),
                     cx + math.cos(a) * (r + 5.5), cy + math.sin(a) * (r + 5.5))
    pdf.restoreState()


def corner_flourish(pdf: canvas.Canvas, T: PlannerTheme, x: float, y: float, *,
                    size: float = 26.0, quadrant: str = "tl", token: str = "accent") -> None:
    """A light corner mark for title pages. Quadrant names the corner it sits in."""
    sx = 1.0 if quadrant in ("tl", "bl") else -1.0
    sy = -1.0 if quadrant in ("tl", "tr") else 1.0
    pdf.saveState()
    pdf.setStrokeColor(T.rgb(token))
    pdf.setLineWidth(0.7)
    pdf.line(x, y, x + sx * size, y)
    pdf.line(x, y, x, y + sy * size)
    pdf.line(x + sx * 4, y + sy * 4, x + sx * size * 0.55, y + sy * 4)
    pdf.line(x + sx * 4, y + sy * 4, x + sx * 4, y + sy * size * 0.55)
    pdf.restoreState()


# --------------------------------------------------------------------------- #
# Writing surfaces
# --------------------------------------------------------------------------- #
def writing_lines(pdf: canvas.Canvas, T: PlannerTheme, x: float, y: float,
                  width: float, count: int, *, spacing: float | None = None,
                  zebra: bool = False, style: str | None = None) -> float:
    """`count` writing lines starting at baseline `y`; returns the next y."""
    sp = spacing or SPACING.line
    style = style or T.line_style
    if zebra:
        pdf.saveState()
        pdf.setFillColor(T.rgb("band"))
        for i in range(count):
            if i % 2 == 0:
                pdf.rect(x, y - (i + 1) * sp + 4, width, sp, stroke=0, fill=1)
        pdf.restoreState()
    yy = y
    dotted = style == "dotted"
    for _ in range(count):
        hairline(pdf, T, x, yy, x + width, yy, width=1.0 if dotted else 0.6, dotted=dotted)
        yy -= sp
    return yy


def labeled_lines(pdf: canvas.Canvas, T: PlannerTheme, x: float, y: float,
                  width: float, label: str, count: int, *, spacing: float | None = None,
                  numbered: bool = False, zebra: bool = False,
                  label_size: float = 9.5) -> float:
    """Section label plus writing lines. The standard worksheet building block."""
    f = T.fonts()
    sp = spacing or SPACING.line
    accent_bar(pdf, T, x, y + 2.5, w=10, h=2)
    # Long labels wrap rather than run off the page.
    label_lines = wrap(pdf, label, f.display, label_size, width - 15)
    for k, line in enumerate(label_lines):
        text(pdf, x + 15, y - k * (label_size + 3), line, font=f.display, size=label_size,
             fill=T.rgb("primary"))
    y -= (len(label_lines) - 1) * (label_size + 3)
    y -= sp * 0.55
    if numbered:
        for i in range(count):
            number_badge(pdf, T, x + 7, y - (i + 1) * sp + 9, i + 1, r=6.2)
        writing_lines(pdf, T, x + 18, y, width - 18, count, spacing=sp, zebra=zebra)
    else:
        writing_lines(pdf, T, x, y, width, count, spacing=sp, zebra=zebra)
    return y - count * sp


def prompt_card(pdf: canvas.Canvas, T: PlannerTheme, x: float, y_top: float,
                width: float, n: int | None, prompt: str, lines: int, *,
                spacing: float | None = None, panel: bool = True) -> float:
    """A reflection question with writing room: badge, italic display prompt,
    ruled lines inside a soft card. Returns the y of the card's bottom edge."""
    f = T.fonts()
    sp = spacing or SPACING.line
    pad = SPACING.card_pad
    prompt_lines = wrap(pdf, prompt, f.display_italic, 11.0, width - 2 * pad - (24 if n else 0))
    head_h = 14 + len(prompt_lines) * 14
    h = pad + head_h + lines * sp + pad * 0.6
    if panel:
        rounded_panel(pdf, T, x, y_top - h, width, h, fill="accent_soft", stroke=None)
        # A quiet left edge accent, the mark of a guided page.
        pdf.saveState()
        pdf.setFillColor(T.rgb("accent"))
        pdf.roundRect(x, y_top - h, 3.2, h, 1.6, stroke=0, fill=1)
        pdf.restoreState()
    ty = y_top - pad - 9
    tx = x + pad + 4
    if n is not None:
        number_badge(pdf, T, tx + 6, ty + 3, n, r=7.0)
        tx += 24
    for line in prompt_lines:
        text(pdf, tx, ty, line, font=f.display_italic, size=11.0, fill=T.rgb("primary"))
        ty -= 14
    ty -= 6
    writing_lines(pdf, T, x + pad + 4, ty, width - 2 * pad - 4, lines, spacing=sp)
    return y_top - h


def callout(pdf: canvas.Canvas, T: PlannerTheme, x: float, y_top: float, width: float,
            title: str, body: str, *, fill: str = "band", size: float = 9.0) -> float:
    """A small framed note (a 'mini callout box'). Returns bottom y."""
    f = T.fonts()
    pad = 10.0
    body_lines = wrap(pdf, body, f.body, size, width - 2 * pad)
    h = pad + 13 + len(body_lines) * (size + 3.5) + pad * 0.7
    rounded_panel(pdf, T, x, y_top - h, width, h, fill=fill, stroke="rule")
    text(pdf, x + pad, y_top - pad - 8, title, font=f.body_bold, size=8.5, fill=T.rgb("primary"))
    yy = y_top - pad - 8 - 13
    for line in body_lines:
        text(pdf, x + pad, yy, line, font=f.body, size=size, fill=GREY_TEXT)
        yy -= size + 3.5
    return y_top - h


def section_heading(pdf: canvas.Canvas, T: PlannerTheme, x: float, y: float,
                    width: float, heading: str, *, size: float = 12.0) -> float:
    """Prose heading: accent bar, display face, returns next y."""
    f = T.fonts()
    accent_bar(pdf, T, x, y + 3, w=16, h=2.2)
    return paragraph(pdf, x + 22, y, heading, font=f.display, size=size,
                     width=width - 22, leading=size + 3, fill=T.rgb("primary"))


# --------------------------------------------------------------------------- #
# Tables
# --------------------------------------------------------------------------- #
def table(pdf: canvas.Canvas, T: PlannerTheme, x: float, y_top: float, width: float,
          columns: list[tuple[str, float]], rows: int, row_h: float, *,
          head_h: float = 20.0, zebra: bool = True, header: bool = True,
          align_right: set[int] | None = None) -> tuple[float, list[float]]:
    """Themed table: rounded outer frame, tinted header, zebra rows, column
    rules. Returns (bottom_y, column x edges incl. both outer edges)."""
    f = T.fonts()
    align_right = align_right or set()
    total_h = (head_h if header else 0) + rows * row_h
    r = min(T.corner_radius, 6.0)
    # Fill: header band + zebra, clipped to the rounded frame.
    pdf.saveState()
    clip = pdf.beginPath()
    clip.roundRect(x, y_top - total_h, width, total_h, r)
    pdf.clipPath(clip, stroke=0, fill=0)
    if header:
        pdf.setFillColor(T.rgb("primary"))
        pdf.rect(x, y_top - head_h, width, head_h, stroke=0, fill=1)
    grid_top = y_top - (head_h if header else 0)
    if zebra:
        pdf.setFillColor(T.rgb("band"))
        for i in range(rows):
            if i % 2 == 1:
                pdf.rect(x, grid_top - (i + 1) * row_h, width, row_h, stroke=0, fill=1)
    pdf.setStrokeColor(T.rgb("rule"))
    pdf.setLineWidth(0.5)
    for i in range(1, rows):
        yy = grid_top - i * row_h
        pdf.line(x, yy, x + width, yy)
    edges = [x]
    cx = x
    for _name, frac in columns:
        cx += width * float(frac)
        edges.append(cx)
    for ex in edges[1:-1]:
        pdf.line(ex, grid_top, ex, grid_top - rows * row_h)
    pdf.restoreState()
    # Header labels.
    if header:
        cx = x
        for i, (name, frac) in enumerate(columns):
            cw = width * float(frac)
            if i in align_right:
                text(pdf, cx + cw - 7, y_top - head_h + 6.5, name, font=f.body_bold,
                     size=8.3, fill=T.rgb("paper"), align="right")
            else:
                text(pdf, cx + 7, y_top - head_h + 6.5, name, font=f.body_bold,
                     size=8.3, fill=T.rgb("paper"))
            cx += cw
    # Frame last.
    pdf.saveState()
    pdf.setStrokeColor(T.rgb("primary") if T.header_style == "band" else T.rgb("rule"))
    pdf.setLineWidth(0.9)
    pdf.roundRect(x, y_top - total_h, width, total_h, r, stroke=1, fill=0)
    pdf.restoreState()
    return y_top - total_h, edges


# --------------------------------------------------------------------------- #
# Page chrome
# --------------------------------------------------------------------------- #
def _hex_contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two hex colours."""
    def lum(value: str) -> float:
        v = str(value or "").lstrip("#")
        rgb = [int(v[i:i + 2], 16) / 255.0 for i in (0, 2, 4)] if len(v) == 6 else [0, 0, 0]
        lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
    la, lb = lum(a), lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def page_header(pdf: canvas.Canvas, T: PlannerTheme, size: tuple[float, float], *,
                title: str, subtitle: str = "", eyebrow: str = "") -> float:
    """Draw the page title chrome in the theme's style. Returns the y
    baseline where body content may start."""
    w, h = size
    f = T.fonts()
    m = SPACING.margin
    inner = w - 2 * m
    style = T.header_style

    if style == "band":
        # The band bleeds to the trim; its type stays 0.28 in clear of it so a
        # home printer's unprintable edge never clips a heading.
        band_h = 48.0
        pdf.saveState()
        pdf.setFillColor(T.rgb("primary"))
        pdf.rect(0, h - band_h, w, band_h, stroke=0, fill=1)
        pdf.setFillColor(T.rgb("accent"))
        pdf.rect(0, h - band_h - 2.4, w, 2.4, stroke=0, fill=1)
        pdf.restoreState()
        ts = fit_text_size(pdf, title, f.display, 16.0, inner - 120, min_size=11)
        text(pdf, m, h - band_h + 15, title, font=f.display, size=ts, fill=T.rgb("paper"))
        if eyebrow:
            # Small type on the band needs 4.5:1; the accent is used only when
            # it clears that, otherwise the paper colour does.
            eyebrow_fill = ("cover_accent" if _hex_contrast(T.cover_accent, T.primary) >= 4.5
                            else "paper")
            small_caps(pdf, T, w - m, h - band_h + 17, eyebrow, size=7,
                       fill=T.rgb(eyebrow_fill), align="right")
        y = h - band_h - 24
    elif style == "soft":
        band_h = 52.0
        pdf.saveState()
        pdf.setFillColor(T.rgb("band"))
        pdf.rect(0, h - band_h, w, band_h, stroke=0, fill=1)
        pdf.restoreState()
        hairline(pdf, T, 0, h - band_h, w, h - band_h, token="rule", width=0.8)
        ts = fit_text_size(pdf, title, f.display, 17.0, inner - 130, min_size=11)
        text(pdf, m, h - band_h + 18, title, font=f.display, size=ts, fill=T.rgb("primary"))
        ornament(pdf, T, w - m - 40, h - band_h + 24, width=80, scale=0.9)
        y = h - band_h - 22
    else:  # rule
        top = h - SPACING.top_inset - 12
        if eyebrow:
            small_caps(pdf, T, m, top + 2, eyebrow, size=7)
            top -= 13
        ts = fit_text_size(pdf, title, f.display, 18.0, inner, min_size=11)
        text(pdf, m, top - 6, title, font=f.display, size=ts, fill=T.rgb("primary"))
        hairline(pdf, T, m, top - 15, w - m, top - 15, token="rule", width=0.6)
        accent_bar(pdf, T, m, top - 16, w=34, h=1.8)
        y = top - 34

    if subtitle:
        y = paragraph(pdf, m, y, subtitle, font=f.display_italic, size=9.5,
                      width=inner, leading=12.5, fill=T.rgb("muted"))
        y -= 6
    return y


def page_footer(pdf: canvas.Canvas, T: PlannerTheme, size: tuple[float, float], *,
                running_title: str, page_num: int) -> None:
    w, _h = size
    f = T.fonts()
    m = SPACING.margin
    base = SPACING.footer_h - 6
    hairline(pdf, T, m, base + 12, w - m, base + 12, token="rule", width=0.6)
    small_caps(pdf, T, m, base, running_title, size=6.8)
    ornament(pdf, T, w / 2, base + 12, width=34, scale=0.75)
    text(pdf, w - m, base - 1, str(page_num), font=f.display, size=9.5,
         fill=T.rgb("primary"), align="right")


def body_bottom() -> float:
    return SPACING.footer_h + 22
