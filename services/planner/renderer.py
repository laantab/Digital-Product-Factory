"""ReportLab renderer for planner page plans.

Draws the page kinds emitted by `builder.py` through the design system in
`themes.py` (tokens) and `components.py` (reusable parts). Three rules:

  * A planner page is a *working surface*, but the Editor-in-Chief blocks
    blank and near-blank pages, and it is right to. Every page carries themed
    chrome, tinted panels and ruled structure -- better design and measurable
    ink.
  * A cover must reach the trim edge. The cover is full-bleed artwork from
    `cover.py` with vector typography on top (`check_cover_page` measures the
    white border on the rendered first page).
  * Nothing here chooses a colour or a face. Page kinds ask the theme, so five
    themes come out of one code path and no page kind can drift from another.

The renderer records what it could not fit (`render_notes`) so the reviewer can
flag truncated content instead of a quietly shortened page.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from services.math_worksheet.pdf_fonts import ascii_pdf_text
from services.planner import components as C
from services.planner.builder import PALETTES, PlannerPage, PlannerPlan, toc_entries  # noqa: F401
from services.planner.cover import build_cover_art, cover_art_effective_dpi
from services.planner.themes import SPACING, PlannerTheme, resolve_theme

PAGE_SIZES = {
    "us letter": letter,
    "letter": letter,
    "8.5x11": letter,
    "a4": A4,
    "a5": A5,
    "6x9": (6 * 72.0, 9 * 72.0),
}

_MARGIN = SPACING.margin
GREY_TEXT = C.GREY_TEXT


@dataclass
class PlannerLayoutInfo:
    render_engine: str = "planner_direct"
    page_size: str = "US Letter"
    total_pages: int = 0
    cover_page_count: int = 0
    kinds: dict | None = None
    design_theme: str = ""
    design_theme_label: str = ""
    cover_style: str = ""
    cover_image_source: str = ""
    cover_image_dpi: float = 0.0
    render_notes: list[str] = field(default_factory=list)


def resolve_page_size(name: str) -> tuple[float, float]:
    return PAGE_SIZES.get(str(name or "").strip().lower(), letter)


class _Ctx:
    """Per-document render context: theme, size, and the notes log."""

    def __init__(self, theme: PlannerTheme, size: tuple[float, float]):
        self.T = theme
        self.size = size
        self.notes: list[str] = []

    @property
    def inner(self) -> float:
        return self.size[0] - 2 * _MARGIN


# --------------------------------------------------------------------------- #
# Cover
# --------------------------------------------------------------------------- #
def _draw_cover(pdf: canvas.Canvas, ctx: _Ctx, page: PlannerPage, plan: PlannerPlan,
                info: PlannerLayoutInfo) -> None:
    T = ctx.T
    w, h = ctx.size
    f = T.fonts()
    style = page.spec.get("cover_style") or plan.cover_style or T.cover_style_default
    art = build_cover_art(T, ctx.size, style=style, image_path=plan.cover_image_path)
    ctx.notes.extend(art.notes)
    info.cover_style = art.style
    info.cover_image_source = art.source
    info.cover_image_dpi = round(cover_art_effective_dpi(art, ctx.size), 1)

    # Full-bleed artwork.
    pdf.drawImage(ImageReader(io.BytesIO(art.to_jpeg_bytes())), 0, 0, width=w, height=h,
                  preserveAspectRatio=False, mask=None)

    dark = art.text_on_dark
    ink = T.rgb("cover_text") if (dark == T.cover_is_dark) else (
        colors.Color(0.98, 0.96, 0.93) if dark else colors.Color(0.14, 0.12, 0.11))
    accent = T.rgb("cover_accent")
    muted_ink = colors.Color(ink.red, ink.green, ink.blue, alpha=0.82)
    # Small labels take the cover ink: the accent is right for rules and
    # ornaments, but gold on a photograph, or mid-blue on a pale sky, falls
    # under the 4.5:1 floor that small type needs.
    label_ink = ink

    inset = 0.42 * 72.0
    safe_w = w - 2 * inset - 56

    # Layout anchors differ by style: the panel style puts the title block on
    # the solid panel; the others centre it in the upper-middle of the page.
    if art.style == "photo_panel":
        block_top = h * (1 - art.panel_top_frac) - 34
        title_size_max = 32 if w >= 500 else 23
    elif art.style == "minimal_texture":
        block_top = h * 0.70
        title_size_max = 40 if w >= 500 else 28
    else:
        block_top = h * 0.68
        title_size_max = 38 if w >= 500 else 27

    # Eyebrow.
    eyebrow = page.spec.get("eyebrow") or "UNDATED EDITION"
    C.small_caps(pdf, T, w / 2, block_top + 26, eyebrow, size=8.5, fill=label_ink, align="center")
    C.ornament(pdf, T, w / 2, block_top + 12, width=150, token="cover_accent", scale=1.1)

    # Title.
    title_size = title_size_max
    lines = C.wrap(pdf, page.title, f.display, title_size, safe_w)
    while len(lines) > 3 and title_size > 18:
        title_size -= 2
        lines = C.wrap(pdf, page.title, f.display, title_size, safe_w)
    y = block_top - title_size - 6
    for line in lines:
        C.text(pdf, w / 2, y, line, font=f.display, size=title_size, fill=ink, align="center")
        y -= title_size * 1.14

    # Accent rule + subtitle.
    y -= 4
    C.ornament(pdf, T, w / 2, y + 2, width=110, token="cover_accent", kind="line")
    y -= 24
    for line in C.wrap(pdf, page.subtitle, f.display_italic, 12.0, safe_w - 30):
        C.text(pdf, w / 2, y, line, font=f.display_italic, size=12.0, fill=muted_ink, align="center")
        y -= 16.5

    # Faith mark: small, only where it improves the design (dark or panel styles).
    if page.spec.get("planner_type") == "faith_planner" and art.style in ("photo_panel", "soft_overlay", "minimal_texture"):
        _cover_mark(pdf, T, w / 2, y - 34, accent, scale=1.0 if w >= 500 else 0.8)
        y -= 62

    # Ownership line.
    own_y = 0.42 * 72.0 + 74
    if art.style == "photo_panel" and own_y > y - 40:
        own_y = y - 40
    C.small_caps(pdf, T, w / 2, own_y + 12, "This planner belongs to", size=7.5,
                 fill=label_ink, align="center")
    pdf.saveState()
    pdf.setStrokeColor(accent)
    pdf.setLineWidth(0.8)
    pdf.line(w * 0.27, own_y, w * 0.73, own_y)
    pdf.restoreState()

    # Caption: what the buyer is actually getting. Kept as real text on the
    # page so the reviewer can verify the page count it advertises.
    caption = page.spec.get("caption") or ""
    if caption:
        C.small_caps(pdf, T, w / 2, inset + 14, caption, size=6.8, fill=muted_ink, align="center")

    # Fine inset frame, the mark of a giftable printable.
    pdf.saveState()
    pdf.setStrokeColor(accent)
    pdf.setLineWidth(0.9)
    pdf.rect(inset, inset, w - 2 * inset, h - 2 * inset, stroke=1, fill=0)
    pdf.setLineWidth(0.35)
    pdf.rect(inset + 5, inset + 5, w - 2 * inset - 10, h - 2 * inset - 10, stroke=1, fill=0)
    pdf.restoreState()


def _cover_mark(pdf: canvas.Canvas, T: PlannerTheme, cx: float, cy: float,
                accent, scale: float = 1.0) -> None:
    """A slender cross in a thin ring -- a faith symbol that reads as a
    brand mark rather than a church handout."""
    pdf.saveState()
    pdf.setStrokeColor(accent)
    pdf.setFillColor(accent)
    r = 17.0 * scale
    pdf.setLineWidth(0.8)
    pdf.circle(cx, cy, r, stroke=1, fill=0)
    arm = 2.1 * scale
    pdf.rect(cx - arm / 2, cy - r * 0.62, arm, r * 1.24, stroke=0, fill=1)
    pdf.rect(cx - r * 0.42, cy + r * 0.16, r * 0.84, arm, stroke=0, fill=1)
    pdf.restoreState()


# --------------------------------------------------------------------------- #
# Front matter
# --------------------------------------------------------------------------- #
def _draw_ownership(pdf: canvas.Canvas, ctx: _Ctx, page: PlannerPage, plan: PlannerPlan,
                    y: float) -> None:
    """Title / belongs-to page: centred title block, name lines, about panel."""
    T = ctx.T
    w, h = ctx.size
    f = T.fonts()
    inner = ctx.inner
    bottom = C.body_bottom()

    C.corner_flourish(pdf, T, _MARGIN, y + 8, quadrant="tl")
    C.corner_flourish(pdf, T, w - _MARGIN, y + 8, quadrant="tr")

    y -= 30
    C.ornament(pdf, T, w / 2, y, width=170)
    y -= 34
    ts = C.fit_text_size(pdf, page.title, f.display, 24, inner - 40, min_size=15, max_lines=2)
    for line in C.wrap(pdf, page.title, f.display, ts, inner - 40):
        C.text(pdf, w / 2, y, line, font=f.display, size=ts, fill=T.rgb("primary"), align="center")
        y -= ts * 1.18
    y -= 4
    for line in C.wrap(pdf, page.subtitle, f.display_italic, 11, inner - 80):
        C.text(pdf, w / 2, y, line, font=f.display_italic, size=11, fill=T.rgb("muted"), align="center")
        y -= 15
    y -= 8
    C.ornament(pdf, T, w / 2, y, width=170)
    y -= 40

    line_w = inner * 0.62
    lx = (w - line_w) / 2
    for label in ("This planner belongs to", "Started on", "If found, please contact"):
        C.small_caps(pdf, T, w / 2, y, label, size=7.5, fill=T.rgb("primary"), align="center")
        y -= 22
        C.hairline(pdf, T, lx, y, lx + line_w, y, token="rule", width=0.8)
        y -= 26

    y -= 6
    about = (
        "The pages inside are undated. Start on any day, skip a week without "
        "ruining the book, and repeat any section as often as it is useful. "
        "Every worksheet is designed to be written on by hand; nothing here "
        "needs an app, an account, or an internet connection."
    )
    about_lines = C.wrap(pdf, about, f.body, 9.5, inner - 2 * 14)
    box_h = 14 + 14 + len(about_lines) * 13.5 + 10
    C.rounded_panel(pdf, T, _MARGIN, y - box_h, inner, box_h, fill="accent_soft", stroke=None)
    C.text(pdf, _MARGIN + 14, y - 14 - 4, "About this planner", font=f.display, size=10.5,
           fill=T.rgb("primary"))
    ty = y - 14 - 4 - 15
    for line in about_lines:
        C.text(pdf, _MARGIN + 14, ty, line, font=f.body, size=9.5, fill=GREY_TEXT)
        ty -= 13.5
    y -= box_h + 16

    disclaimer = page.spec.get("disclaimer") or ""
    if disclaimer and y - 40 > bottom:
        lines = C.wrap(pdf, disclaimer, f.body, 8.5, inner - 28)
        box_h = len(lines) * 12 + 34
        if y - box_h < bottom:
            ctx.notes.append("ownership: disclaimer trimmed to fit the page")
            lines = lines[: max(1, int((y - bottom - 34) // 12))]
            box_h = len(lines) * 12 + 34
        C.rounded_panel(pdf, T, _MARGIN, y - box_h, inner, box_h, fill="band", stroke="rule")
        C.text(pdf, _MARGIN + 14, y - 16, "Important", font=f.body_bold, size=8.5, fill=T.rgb("primary"))
        ty = y - 16 - 13
        for line in lines:
            C.text(pdf, _MARGIN + 14, ty, line, font=f.body, size=8.5, fill=GREY_TEXT)
            ty -= 12


def _draw_toc(pdf: canvas.Canvas, ctx: _Ctx, plan: PlannerPlan, y: float) -> None:
    T = ctx.T
    w, _h = ctx.size
    f = T.fonts()
    entries = toc_entries(plan.pages)
    inner = ctx.inner
    bottom = C.body_bottom()
    pitch = 15.5

    C.ornament(pdf, T, w / 2, y + 4, width=120, scale=0.9)
    y -= 22

    per_col = max(1, int((y - bottom) // pitch))
    two_col = len(entries) > per_col
    col_w = (inner - SPACING.gutter * 2) / 2 if two_col else inner
    col_x = [_MARGIN, _MARGIN + col_w + SPACING.gutter * 2]
    ci = 0
    cy = y
    drawn = 0
    for label, page_no in entries:
        if cy < bottom:
            ci += 1
            if ci >= len(col_x):
                break
            cy = y
        x = col_x[ci]
        label_txt = ascii_pdf_text(label)
        num_txt = str(page_no)
        num_w = pdf.stringWidth(num_txt, f.display, 9)
        avail = col_w - num_w - 12
        while pdf.stringWidth(label_txt, f.body, 9) > avail and len(label_txt) > 4:
            label_txt = label_txt[:-2]
        C.text(pdf, x, cy, label_txt, font=f.body, size=9, fill=colors.Color(0.2, 0.2, 0.2))
        lw = pdf.stringWidth(label_txt, f.body, 9)
        C.hairline(pdf, T, x + lw + 5, cy + 2.5, x + col_w - num_w - 5, cy + 2.5,
                   token="rule", width=0.5, dotted=True)
        C.text(pdf, x + col_w, cy, num_txt, font=f.display, size=9, fill=T.rgb("primary"), align="right")
        cy -= pitch
        drawn += 1
    if drawn < len(entries):
        ctx.notes.append(f"toc: {len(entries) - drawn} contents entries did not fit")
    # A short orientation note where the list leaves room: beginners open the
    # contents page first, and it should tell them where to begin.
    low = min(cy, y - per_col * pitch) if not two_col else (bottom + 1)
    if not two_col and (cy - 90) > bottom:
        first = next((e for e in entries if e[0].lower().startswith("how to use")), None)
        start = first[1] if first else 2
        note_top = max(bottom + 92, cy - 24)
        C.callout(pdf, T, _MARGIN, note_top, inner, "Where to start",
                  f"New here? Read 'How to Use This Planner' on page {start} first, "
                  "then go straight to the first weekly page. Everything else in this "
                  "list is a tool you can reach for whenever you need it.")


def _draw_prose(pdf: canvas.Canvas, ctx: _Ctx, page: PlannerPage, y: float) -> None:
    T = ctx.T
    f = T.fonts()
    inner = ctx.inner
    bottom = C.body_bottom()
    sections = list(page.spec.get("sections") or [])
    if not sections:
        return

    # Measure first, then distribute slack evenly between sections; prose
    # otherwise stacks at the top and leaves the lower half looking unfinished.
    base_gap = SPACING.section_gap
    body_size, body_leading = 9.6, 13.8
    natural = 0.0
    for heading, body in sections:
        natural += len(C.wrap(pdf, heading, f.display, 12, inner - 22)) * 15
        natural += 5
        natural += len(C.wrap(pdf, body, f.body, body_size, inner - 22)) * body_leading
        natural += base_gap
    slack = (y - bottom) - natural
    extra = min(38.0, slack / (len(sections) - 1)) if slack > 0 and len(sections) > 1 else 0.0

    drawn = 0
    for i, (heading, body) in enumerate(sections):
        need = len(C.wrap(pdf, body, f.body, body_size, inner - 22)) * body_leading + 20
        if y - need < bottom:
            break
        y = C.section_heading(pdf, T, _MARGIN, y, inner, heading, size=12)
        y -= 3
        y = C.paragraph(pdf, _MARGIN + 22, y, body, font=f.body, size=body_size,
                        width=inner - 22, leading=body_leading, fill=GREY_TEXT)
        y -= base_gap + (extra if i < len(sections) - 1 else 0.0)
        drawn += 1
    if drawn < len(sections):
        ctx.notes.append(f"{page.title}: {len(sections) - drawn} prose section(s) did not fit")
    # A short section list can leave the lower third bare; a notes block turns
    # that into writing room instead of a page that looks unfinished.
    if y - bottom > 150:
        _trailing_block(pdf, ctx, y - 8, "Notes from this section", min_lines=3)


# --------------------------------------------------------------------------- #
# Tables and grids
# --------------------------------------------------------------------------- #
def _draw_open_table(pdf: canvas.Canvas, ctx: _Ctx, page: PlannerPage, y: float) -> None:
    T = ctx.T
    inner = ctx.inner
    bottom = C.body_bottom()
    cols = page.spec.get("columns") or [("Item", 1.0)]
    want_rows = int(page.spec.get("rows") or 20)
    head_h = 21.0
    avail = y - bottom - head_h
    row_h = max(16.0, min(27.0, avail / max(want_rows, 1)))
    rows = max(1, int(avail // row_h))
    C.table(pdf, T, _MARGIN, y, inner, list(cols), rows, row_h, head_h=head_h)


def _draw_labeled_table(pdf: canvas.Canvas, ctx: _Ctx, page: PlannerPage, y: float) -> None:
    T = ctx.T
    f = T.fonts()
    inner = ctx.inner
    bottom = C.body_bottom()
    labels = list(page.spec.get("rows") or [])
    blanks = int(page.spec.get("blank_rows") or 0)
    value_cols = list(page.spec.get("value_columns") or ["Planned", "Actual"])
    total_label = page.spec.get("total_label") or "Total"

    body_rows = labels + [""] * blanks
    total_rows = len(body_rows) + 1
    head_h = 21.0
    avail = y - bottom - head_h
    row_h = max(14.0, min(24.0, avail / max(total_rows, 1)))
    if row_h * total_rows > avail:
        keep = max(1, int(avail // row_h) - 1)
        if keep < len(labels):
            ctx.notes.append(f"{page.title}: {len(labels) - keep} category rows did not fit")
        body_rows = body_rows[:keep]
        total_rows = len(body_rows) + 1

    label_frac = 0.46
    val_frac = (1 - label_frac) / max(len(value_cols), 1)
    columns = [("Category", label_frac)] + [(v, val_frac) for v in value_cols]
    bottom_y, edges = C.table(pdf, T, _MARGIN, y, inner, columns, total_rows, row_h,
                              head_h=head_h, align_right=set(range(1, len(columns))))
    grid_top = y - head_h
    for i, label in enumerate(body_rows):
        if label:
            C.text(pdf, _MARGIN + 7, grid_top - (i + 1) * row_h + row_h * 0.32, label,
                   font=f.body, size=8.6, fill=colors.Color(0.18, 0.18, 0.18))
    # Total row, emphasised in the accent.
    ty = bottom_y
    pdf.saveState()
    pdf.setFillColor(T.rgb("accent_soft"))
    pdf.rect(_MARGIN + 1, ty + 1, inner - 2, row_h - 1, stroke=0, fill=1)
    pdf.restoreState()
    C.accent_bar(pdf, T, _MARGIN + 1, ty + 1, w=4, h=row_h - 1)
    C.text(pdf, _MARGIN + 10, ty + row_h * 0.32, total_label, font=f.display, size=9.5,
           fill=T.rgb("primary"))
    # A short category list leaves the lower page bare; notes earn the space.
    if ty - bottom > 110:
        _trailing_block(pdf, ctx, ty - 26, "Notes for this month", min_lines=2)


def _draw_snapshot(pdf: canvas.Canvas, ctx: _Ctx, page: PlannerPage, y: float) -> None:
    T = ctx.T
    f = T.fonts()
    w, _h = ctx.size
    inner = ctx.inner
    bottom = C.body_bottom()
    assets = list(page.spec.get("assets") or [])
    debts = list(page.spec.get("debts") or [])
    col_w = (inner - SPACING.gutter) / 2
    rows = max(len(assets), len(debts)) + 2
    head_h = 19.0
    avail = (y - bottom) * 0.62 - head_h - 46
    row_h = max(16.0, min(30.0, avail / max(rows, 1)))

    for idx, (heading, items) in enumerate((("What I own", assets), ("What I owe", debts))):
        x = _MARGIN + idx * (col_w + SPACING.gutter)
        C.table(pdf, T, x, y, col_w, [(heading, 0.62), ("Amount", 0.38)], rows, row_h,
                head_h=head_h, align_right={1})
        grid_top = y - head_h
        for i, label in enumerate(items):
            C.text(pdf, x + 7, grid_top - (i + 1) * row_h + row_h * 0.32, label,
                   font=f.body, size=8.6, fill=colors.Color(0.18, 0.18, 0.18))

    ny = y - head_h - rows * row_h - 28
    C.rounded_panel(pdf, T, _MARGIN, ny - 8, inner, 28, fill="accent_soft", stroke="rule")
    C.text(pdf, _MARGIN + 12, ny + 2, "Net worth  =  what I own  -  what I owe",
           font=f.display, size=10, fill=T.rgb("primary"))
    C.hairline(pdf, T, w - _MARGIN - 150, ny, w - _MARGIN - 12, ny, token="primary", width=0.9)
    _trailing_block(pdf, ctx, ny - 30,
                    "Three numbers worth knowing: months of expenses in the emergency "
                    "fund, the highest interest rate you are paying, and what is left "
                    "over in an average month")


def _draw_calendar(pdf: canvas.Canvas, ctx: _Ctx, page: PlannerPage, y: float) -> None:
    from services.planner.content import WEEKDAYS
    T = ctx.T
    f = T.fonts()
    inner = ctx.inner
    bottom = C.body_bottom()

    C.small_caps(pdf, T, _MARGIN, y - 2, "Month", size=7.5, fill=T.rgb("primary"))
    C.hairline(pdf, T, _MARGIN + 44, y - 4, _MARGIN + 230, y - 4, token="primary", width=0.7)
    C.small_caps(pdf, T, _MARGIN + 250, y - 2, "Year", size=7.5, fill=T.rgb("primary"))
    C.hairline(pdf, T, _MARGIN + 286, y - 4, _MARGIN + 400, y - 4, token="primary", width=0.7)
    y -= 24

    head_h = 19.0
    rows = 6
    focus_h = 54.0
    avail = y - head_h - bottom - focus_h
    cell_h = max(28.0, avail / rows)
    if cell_h * rows > avail:
        cell_h = avail / rows
    columns = [(d, 1 / 7.0) for d in WEEKDAYS]
    grid_bottom, _edges = C.table(pdf, T, _MARGIN, y, inner, columns, rows, cell_h,
                                  head_h=head_h, zebra=False)
    # Soft checker tint keeps the grid readable at a glance.
    pdf.saveState()
    pdf.setFillColor(T.rgb("band"))
    cell_w = inner / 7.0
    grid_top = y - head_h
    for r in range(rows):
        for c in range(7):
            if (r + c) % 2 == 0:
                pdf.rect(_MARGIN + c * cell_w + 0.5, grid_top - (r + 1) * cell_h + 0.5,
                         cell_w - 1, cell_h - 1, stroke=0, fill=1)
    pdf.restoreState()
    C.labeled_lines(pdf, T, _MARGIN, grid_bottom - 22, inner, "Focus this month", 1,
                    spacing=SPACING.line_tight)


def _draw_habit_tracker(pdf: canvas.Canvas, ctx: _Ctx, page: PlannerPage, y: float) -> None:
    T = ctx.T
    f = T.fonts()
    inner = ctx.inner
    bottom = C.body_bottom()
    habits = list(page.spec.get("habits") or []) + [""] * int(page.spec.get("blank_rows") or 2)
    days = int(page.spec.get("days") or 31)

    label_frac = 0.32
    day_frac = (1 - label_frac) / days
    head_h = 19.0
    grid_top = y - head_h
    avail = (grid_top - bottom) * 0.64
    row_h = max(18.0, min(30.0, avail / max(len(habits), 1)))
    columns = [("Habit", label_frac)] + [((str(d + 1) if (d == 0 or (d + 1) % 5 == 0) else ""), day_frac)
                                          for d in range(days)]
    grid_bottom, edges = C.table(pdf, T, _MARGIN, y, inner, columns, len(habits), row_h,
                                 head_h=head_h)
    # Weekly separators, a touch heavier, so the month reads in weeks.
    pdf.saveState()
    pdf.setStrokeColor(T.rgb("accent"))
    pdf.setLineWidth(0.9)
    for d in range(7, days, 7):
        xx = edges[1 + d]
        pdf.line(xx, grid_top, xx, grid_bottom)
    pdf.restoreState()
    for i, habit in enumerate(habits):
        if habit:
            C.text(pdf, _MARGIN + 7, grid_top - (i + 1) * row_h + row_h * 0.34, habit,
                   font=f.body, size=8.6, fill=colors.Color(0.18, 0.18, 0.18))
    _trailing_block(pdf, ctx, grid_bottom - 26, "What I noticed this month")


def _draw_reading_plan(pdf: canvas.Canvas, ctx: _Ctx, page: PlannerPage, y: float) -> None:
    T = ctx.T
    f = T.fonts()
    inner = ctx.inner
    bottom = C.body_bottom()
    rows = list(page.spec.get("rows") or [])
    head_h = 18.0
    avail = y - bottom - head_h
    row_h = max(9.4, min(16.5, avail / max(len(rows), 1)))
    fit = min(len(rows), max(1, int((avail + 0.5) // row_h)))
    if fit < len(rows):
        ctx.notes.append(f"{page.title}: {len(rows) - fit} reading-plan rows did not fit")
    rows = rows[:fit]
    columns = [("Wk", 0.06), ("Season", 0.15), ("Reading", 0.25), ("Theme", 0.44), ("Done", 0.10)]
    grid_bottom, edges = C.table(pdf, T, _MARGIN, y, inner, columns, len(rows), row_h,
                                 head_h=head_h, zebra=False)
    grid_top = y - head_h
    # Season groups alternate a soft tint, so the year reads in movements.
    pdf.saveState()
    tint = False
    prev = None
    for i, (season, _ref, _gist) in enumerate(rows):
        if season != prev:
            tint = not tint
            prev = season
        if tint:
            pdf.setFillColor(T.rgb("band"))
            pdf.rect(_MARGIN + 0.5, grid_top - (i + 1) * row_h, inner - 1, row_h, stroke=0, fill=1)
    pdf.restoreState()
    fs = min(7.8, row_h - 2.6)
    box = min(7.0, row_h - 3.5)
    for i, (season, reference, gist) in enumerate(rows):
        ty = grid_top - (i + 1) * row_h + row_h * 0.30
        cx = _MARGIN
        for value, (name, frac) in zip((str(i + 1), season, reference, gist), columns[:4]):
            txt = ascii_pdf_text(value)
            maxw = inner * frac - 8
            while pdf.stringWidth(txt, f.body, fs) > maxw and len(txt) > 3:
                txt = txt[:-2]
            face = f.body_bold if name == "Reading" else f.body
            C.text(pdf, cx + 4, ty, txt, font=face, size=fs,
                   fill=T.rgb("primary") if name == "Reading" else colors.Color(0.18, 0.18, 0.18))
            cx += inner * frac
        C.checkbox(pdf, T, edges[4] + (inner * 0.10 - box) / 2, grid_top - (i + 1) * row_h + (row_h - box) / 2, box)


# --------------------------------------------------------------------------- #
# Writing pages
# --------------------------------------------------------------------------- #
def _trailing_block(pdf: canvas.Canvas, ctx: _Ctx, y: float, heading: str, *,
                    min_lines: int = 2) -> None:
    """Fill leftover space under a fixed-height element with a usable block."""
    T = ctx.T
    inner = ctx.inner
    bottom = C.body_bottom()
    sp = SPACING.line
    if y - 30 - min_lines * sp < bottom:
        return
    count = max(min_lines, int((y - 14 - bottom) // sp))
    C.labeled_lines(pdf, T, _MARGIN, y, inner, heading, count, spacing=sp, zebra=True)


def _draw_lined_notes(pdf: canvas.Canvas, ctx: _Ctx, page: PlannerPage, y: float) -> None:
    T = ctx.T
    inner = ctx.inner
    bottom = C.body_bottom()
    sp = 21.0
    C.ornament(pdf, T, ctx.size[0] / 2, y + 2, width=110, scale=0.9)
    y -= 16
    count = max(1, int((y - bottom) // sp))
    C.writing_lines(pdf, T, _MARGIN, y, inner, count, spacing=sp, zebra=True)


def _draw_prompt_page(pdf: canvas.Canvas, ctx: _Ctx, page: PlannerPage, y: float) -> None:
    T = ctx.T
    inner = ctx.inner
    bottom = C.body_bottom()
    prompts = list(page.spec.get("prompts") or [])
    lines_each = int(page.spec.get("lines_each") or 3)
    sp = SPACING.line_tight
    drawn = 0
    for n, prompt in enumerate(prompts, start=1):
        est = 12 + 28 + lines_each * sp + 8
        if y - est < bottom:
            break
        y = C.prompt_card(pdf, T, _MARGIN, y, inner, n, prompt, lines_each, spacing=sp)
        y -= 10
        drawn += 1
    if drawn < len(prompts):
        ctx.notes.append(f"{page.title}: {len(prompts) - drawn} prompt(s) did not fit")


def _draw_faith_weekly(pdf: canvas.Canvas, ctx: _Ctx, page: PlannerPage, y: float) -> None:
    T = ctx.T
    f = T.fonts()
    w, _h = ctx.size
    inner = ctx.inner
    bottom = C.body_bottom()
    gutter = SPACING.gutter

    # 1. Reading card: reference large, theme line, ornament.
    box_h = 58.0
    C.rounded_panel(pdf, T, _MARGIN, y - box_h, inner, box_h, fill="accent_soft", stroke=None)
    C.accent_bar(pdf, T, _MARGIN, y - box_h, w=4, h=box_h)
    C.small_caps(pdf, T, _MARGIN + 16, y - 15, "This week's reading", size=7.2, fill=T.rgb("primary"))
    reference = page.spec.get("reference") or ""
    C.text(pdf, _MARGIN + 16, y - 36, reference, font=f.display, size=17, fill=T.rgb("primary"))
    gist = (page.subtitle.split(" - ", 1)[1] if " - " in page.subtitle else page.subtitle).strip()
    if gist:
        gs = C.fit_text_size(pdf, gist, f.display_italic, 10, inner * 0.5, min_size=8)
        C.text(pdf, w - _MARGIN - 14, y - 36, gist, font=f.display_italic, size=gs,
               fill=T.rgb("muted"), align="right")
    C.small_caps(pdf, T, _MARGIN + 16, y - 50, "Read it first, then come back to this page", size=6.6)
    y -= box_h + 16

    # 2. Prayer focus (two columns of checkboxes) beside gratitude (three lines).
    cats = list(page.spec.get("prayer_categories") or [])
    col_w = (inner - gutter) / 2
    left_x, right_x = _MARGIN, _MARGIN + col_w + gutter
    cat_rows = (len(cats) + 1) // 2
    focus_h = 26 + cat_rows * 17 + 6
    C.rounded_panel(pdf, T, left_x, y - focus_h, col_w, focus_h, fill="band", stroke="rule")
    C.accent_bar(pdf, T, left_x + 12, y - 15.5, w=10, h=2)
    C.text(pdf, left_x + 27, y - 18, "Prayer focus this week", font=f.display, size=9.5, fill=T.rgb("primary"))
    half = (col_w - 24) / 2
    for i, cat in enumerate(cats):
        cx = left_x + 12 + (i % 2) * half
        cy = y - 36 - (i // 2) * 17
        C.checkbox(pdf, T, cx, cy - 2, 8.5)
        C.text(pdf, cx + 13, cy, cat, font=f.body, size=8.2, fill=GREY_TEXT)
    # Gratitude on the right.
    grat_lines = 3
    C.labeled_lines(pdf, T, right_x, y - 10, col_w, "Three things I am grateful for",
                    grat_lines, spacing=SPACING.line, numbered=True)
    y -= max(focus_h, 10 + SPACING.line * 0.55 + grat_lines * SPACING.line) + 16

    # 3. One step this week: a callout with a single strong line.
    step_h = 52.0
    if y - step_h > bottom + 60:
        C.rounded_panel(pdf, T, _MARGIN, y - step_h, inner, step_h, fill="paper", stroke="accent",
                        stroke_width=1.0)
        C.small_caps(pdf, T, _MARGIN + 12, y - 14, "One thing I will do this week because of what I read",
                     size=7.2, fill=T.rgb("primary"))
        C.writing_lines(pdf, T, _MARGIN + 12, y - 40, inner - 24, 1, spacing=SPACING.line)
        y -= step_h + 16

    # 4. People to pray for, then notes fill the rest.
    if y - 120 > bottom:
        y = C.labeled_lines(pdf, T, _MARGIN, y, inner, "People I will pray for by name", 4,
                            spacing=SPACING.line_tight)
        y -= 14
    if y - 44 > bottom:
        count = max(1, int((y - 12 - bottom) // SPACING.line_tight))
        C.labeled_lines(pdf, T, _MARGIN, y, inner, "Questions and notes from this week's reading",
                        count, spacing=SPACING.line_tight, zebra=True)


def _draw_faith_daily(pdf: canvas.Canvas, ctx: _Ctx, page: PlannerPage, y: float) -> None:
    T = ctx.T
    f = T.fonts()
    inner = ctx.inner
    bottom = C.body_bottom()

    # Date / passage strip.
    strip_h = 30.0
    C.rounded_panel(pdf, T, _MARGIN, y - strip_h, inner, strip_h, fill="band", stroke="rule")
    split = _MARGIN + inner * 0.36
    C.hairline(pdf, T, split, y - strip_h + 6, split, y - 6, token="rule", width=0.7)
    C.small_caps(pdf, T, _MARGIN + 12, y - 19, "Date", size=7.2, fill=T.rgb("primary"))
    C.hairline(pdf, T, _MARGIN + 46, y - 21, split - 12, y - 21, token="rule", width=0.6)
    C.small_caps(pdf, T, split + 12, y - 19, "Passage", size=7.2, fill=T.rgb("primary"))
    reference = page.spec.get("reference") or ""
    if reference:
        C.text(pdf, split + 66, y - 19.5, reference, font=f.display, size=10, fill=T.rgb("primary"))
        C.hairline(pdf, T, split + 66 + pdf.stringWidth(reference, f.display, 10) + 8, y - 21,
                   _MARGIN + inner - 12, y - 21, token="rule", width=0.6)
    else:
        C.hairline(pdf, T, split + 66, y - 21, _MARGIN + inner - 12, y - 21, token="rule", width=0.6)
    y -= strip_h + 16

    prompts = list(page.spec.get("prompts") or [])
    # Reserve the closing block: praying today + one line to remember.
    closing_h = 112.0
    usable = y - bottom - closing_h - 10 * len(prompts)
    per = usable / max(len(prompts), 1)
    sp = SPACING.line_tight
    lines_each = max(2, int((per - 44) // sp))
    for n, prompt in enumerate(prompts, start=1):
        y = C.prompt_card(pdf, T, _MARGIN, y, inner, n, prompt, lines_each, spacing=sp)
        y -= 10

    # Closing block.
    y -= 2
    C.labeled_lines(pdf, T, _MARGIN, y, inner, "One line I want to remember", 1, spacing=sp)
    y -= sp * 0.55 + sp + 14
    count = max(1, int((y - 12 - bottom) // sp))
    C.labeled_lines(pdf, T, _MARGIN, y, inner, "Praying today for", count, spacing=sp, zebra=True)


_DRAWERS = {
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
                            author: str = "",
                            theme: PlannerTheme | str | None = None) -> tuple[bytes, PlannerLayoutInfo]:
    size = resolve_page_size(page_size)
    if isinstance(theme, PlannerTheme):
        T = theme
    else:
        T, _warn = resolve_theme(str(theme or plan.design_theme or ""), plan.planner_type)
    ctx = _Ctx(T, size)
    info = PlannerLayoutInfo(page_size=page_size, design_theme=T.key, design_theme_label=T.label)

    buf = io.BytesIO()
    pdf = canvas.Canvas(buf, pagesize=size)
    pdf.setTitle(ascii_pdf_text(plan.title))
    if author:
        pdf.setAuthor(ascii_pdf_text(author))
    pdf.setSubject(ascii_pdf_text(plan.subtitle))
    pdf.setCreator("Digital Product Factory planner engine")

    kinds: dict[str, int] = {}
    cover_pages = 0
    running_title = plan.title
    eyebrow = {"faith_planner": "Faith Planner", "budget_planner": "Budget Planner"}.get(
        plan.planner_type, "")

    for i, page in enumerate(plan.pages, start=1):
        kinds[page.kind] = kinds.get(page.kind, 0) + 1
        # Paper colour first: a warm-white ground is part of the theme.
        if T.paper.lower() != "#ffffff":
            pdf.saveState()
            pdf.setFillColor(T.rgb("paper"))
            pdf.rect(0, 0, size[0], size[1], stroke=0, fill=1)
            pdf.restoreState()
        if page.kind == "cover":
            cover_pages += 1
            _draw_cover(pdf, ctx, page, plan, info)
            pdf.showPage()
            continue

        if page.kind == "ownership":
            # A title page carries its own typography; chrome would repeat it.
            y = size[1] - SPACING.top_inset - 26
            C.small_caps(pdf, T, size[0] / 2, y + 6, eyebrow, size=7.5, align="center")
            _draw_ownership(pdf, ctx, page, plan, y - 6)
            C.page_footer(pdf, T, size, running_title=running_title, page_num=i)
            pdf.showPage()
            continue
        y = C.page_header(pdf, T, size, title=page.title, subtitle=page.subtitle, eyebrow=eyebrow)
        if page.kind == "toc":
            _draw_toc(pdf, ctx, plan, y)
        else:
            drawer = _DRAWERS.get(page.kind)
            if drawer is not None:
                drawer(pdf, ctx, page, y)
            else:
                ctx.notes.append(f"page {i}: no drawer for kind {page.kind!r}")
        C.page_footer(pdf, T, size, running_title=running_title, page_num=i)
        pdf.showPage()

    pdf.save()
    info.total_pages = len(plan.pages)
    info.cover_page_count = cover_pages
    info.kinds = kinds
    info.render_notes = list(ctx.notes)
    return buf.getvalue(), info
