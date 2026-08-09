"""ReportLab PDF renderer for Crossword puzzle books — separate from Word Search.

Typography root cause + fix:
  Built-in Helvetica Type1 + non-ASCII punctuation caused viewer font
  substitution with mismatched glyph metrics (looked like "C a lifo..." /
  "Answ er"). This renderer embeds a TrueType face and draws whole strings
  only, with save/restore around specialized drawing.
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from services.crossword.builder import CrosswordPuzzleResult
from services.crossword.clues import simple_clue
from services.crossword.engine import CrosswordClueEntry
from services.crossword.pdf_fonts import (
    ANSWER_HEADING_MIN_PT,
    CLUE_FONT_MIN_PT,
    COVER_TITLE_MIN_PT,
    FOOTER_FONT_MIN_PT,
    HEADING_FONT_MIN_PT,
    INSTRUCTION_FONT_MIN_PT,
    ascii_pdf_text,
    ensure_crossword_fonts,
)

# Re-export size contracts for tests
__all__ = [
    "CrosswordPdfLayoutInfo",
    "build_crossword_book_pdf_bytes",
    "build_single_crossword_pdf_bytes",
    "CLUE_FONT_MIN_PT",
    "HEADING_FONT_MIN_PT",
    "INSTRUCTION_FONT_MIN_PT",
]

_MARGIN_IN = 0.48
_BOX_PADDING_PT = 3.0
_CELL_MIN_PT = 16.5
_CELL_MAX_PT = 28.0
_CLUE_GAP_PT = 11.0
_LINE_HEIGHT_PT = 11.2

_INK = colors.HexColor("#1a1a1a")
_MUTED = colors.HexColor("#44403c")
_RULE = colors.HexColor("#b45309")
_SOFT_BAND = colors.HexColor("#faf7f2")
_ANSWER_BAND = colors.HexColor("#3f2e1e")
# Charcoal blocks — conventional crossword look without pure-black ink floods
_GRID_BLOCK = colors.HexColor("#2a2a2a")
_GRID_STROKE = colors.HexColor("#1c1917")


@dataclass
class CrosswordPdfLayoutInfo:
    render_engine: str = "crossword_direct"
    page_count: int = 0
    cover_page_count: int = 0
    puzzle_page_count: int = 0
    answer_key_page_count: int = 0
    puzzle_fits_one_page: bool = True


def _fonts():
    return ensure_crossword_fonts()


def _paint_white_page(pdf: canvas.Canvas) -> None:
    page_w, page_h = letter
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)


def _draw_text(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    text: str,
    *,
    font_name: str,
    font_size: float,
    align: str = "left",
    fill=None,
) -> float:
    """Whole-string text draw. Returns string width in the active font."""
    safe = ascii_pdf_text(text)
    pdf.saveState()
    try:
        pdf.setFillColor(fill if fill is not None else _INK)
        pdf.setFont(font_name, font_size)
        # Explicitly clear character/word spacing (shared root-cause guard).
        pdf._code.append("0 Tc")
        pdf._code.append("0 Tw")
        width = pdf.stringWidth(safe, font_name, font_size)
        if align == "center":
            pdf.drawCentredString(x, y, safe)
        elif align == "right":
            pdf.drawRightString(x, y, safe)
        else:
            pdf.drawString(x, y, safe)
        return width
    finally:
        pdf.restoreState()


def _draw_centered_text(
    pdf: canvas.Canvas,
    x_center: float,
    y_baseline: float,
    text: str,
    *,
    font_name: str,
    font_size: float,
    fill=None,
) -> None:
    _draw_text(
        pdf, x_center, y_baseline, text,
        font_name=font_name, font_size=font_size, align="center", fill=fill,
    )


def _trim_grid(grid: list[list[str | None]]) -> tuple[list[list[str | None]], int, int]:
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    min_r, max_r = rows, -1
    min_c, max_c = cols, -1
    for r in range(rows):
        for c in range(cols):
            if grid[r][c] is not None:
                min_r = min(min_r, r)
                max_r = max(max_r, r)
                min_c = min(min_c, c)
                max_c = max(max_c, c)
    if max_r < min_r:
        return grid, 0, 0
    trimmed = [row[min_c : max_c + 1] for row in grid[min_r : max_r + 1]]
    return trimmed, min_r, min_c


def _cell_size_pt(
    *,
    page_w: float,
    page_h: float,
    rows: int,
    cols: int,
    clue_line_count: int,
    header_pt: float = 64.0,
) -> float:
    margin = _MARGIN_IN * 72.0
    usable_w = page_w - 2 * margin
    usable_h = page_h - 2 * margin
    # Reserve generous room for readable 9pt+ clues
    footer_pt = _CLUE_GAP_PT + 24.0 + max(4, clue_line_count) * _LINE_HEIGHT_PT + 20.0
    puzzle_h = max(usable_h - header_pt - footer_pt, rows * _CELL_MIN_PT)
    from_width = (usable_w * 0.88) / max(1, cols)
    from_height = puzzle_h / max(1, rows)
    return min(_CELL_MAX_PT, max(_CELL_MIN_PT, min(from_width, from_height)))


def _wrap_clue_line(pdf: canvas.Canvas, text: str, *, font_name: str, font_size: float, max_width: float) -> list[str]:
    words = ascii_pdf_text(text).split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if pdf.stringWidth(trial, font_name, font_size) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_crossword_grid(
    pdf: canvas.Canvas,
    puzzle: CrosswordPuzzleResult,
    *,
    box_top_y: float,
    reveal: bool,
    header_budget: float = 64.0,
) -> tuple[float, float, float, float]:
    """Classic crossword: white letter cells, charcoal blocked cells, thin borders."""
    font_reg, font_bold, _font_italic = _fonts()
    page_w, _page_h = letter
    grid, row_offset, col_offset = _trim_grid(puzzle.grid)
    if not grid:
        margin = _MARGIN_IN * 72.0
        return margin, box_top_y, page_w - 2 * margin, 0.0

    rows = len(grid)
    cols = len(grid[0])
    across = [c for c in puzzle.clues if c.direction == "across"]
    down = [c for c in puzzle.clues if c.direction == "down"]
    clue_lines = len(across) + len(down) + 4

    def _touches_letter(r: int, c: int) -> bool:
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                rr, cc = r + dr, c + dc
                if 0 <= rr < rows and 0 <= cc < cols and grid[rr][cc] is not None:
                    return True
        return False

    # Active cells only: letters + structural blocks (skip empty corner padding).
    active = [
        (r, c)
        for r in range(rows)
        for c in range(cols)
        if grid[r][c] is not None or _touches_letter(r, c)
    ]
    if not active:
        margin = _MARGIN_IN * 72.0
        return margin, box_top_y, page_w - 2 * margin, 0.0
    min_ar = min(r for r, _c in active)
    max_ar = max(r for r, _c in active)
    min_ac = min(c for _r, c in active)
    max_ac = max(c for _r, c in active)
    active_rows = max_ar - min_ar + 1
    active_cols = max_ac - min_ac + 1

    cell = _cell_size_pt(
        page_w=page_w,
        page_h=letter[1],
        rows=active_rows,
        cols=active_cols,
        clue_line_count=clue_lines,
        header_pt=header_budget,
    )
    block_w = active_cols * cell
    block_h = active_rows * cell
    box_w = block_w + 2 * _BOX_PADDING_PT
    box_h = block_h + 2 * _BOX_PADDING_PT
    box_x = (page_w - box_w) / 2.0
    box_y = box_top_y - box_h

    grid_left = box_x + _BOX_PADDING_PT
    grid_bottom = box_y + _BOX_PADDING_PT
    numbers = {(c.row - row_offset, c.col - col_offset): c.number for c in puzzle.clues}

    pdf.saveState()
    try:
        pdf.setFillColor(colors.HexColor("#f3efe7"))
        pdf.rect(box_x + 1.2, box_y - 1.2, box_w, box_h, fill=1, stroke=0)
        pdf.setFillColor(colors.white)
        pdf.setStrokeColor(_GRID_STROKE)
        pdf.setLineWidth(1.2)
        pdf.rect(box_x, box_y, box_w, box_h, fill=1, stroke=1)

        pdf.setLineWidth(0.45)
        for r in range(min_ar, max_ar + 1):
            for c in range(min_ac, max_ac + 1):
                cx = grid_left + (c - min_ac) * cell
                cy = grid_bottom + (max_ar - r) * cell
                cell_letter = grid[r][c]
                if cell_letter is None:
                    if not _touches_letter(r, c):
                        continue
                    pdf.setFillColor(_GRID_BLOCK)
                    pdf.setStrokeColor(_GRID_BLOCK)
                    pdf.rect(cx, cy, cell, cell, fill=1, stroke=1)
                    continue

                pdf.setFillColor(colors.white)
                pdf.setStrokeColor(_GRID_STROKE)
                pdf.rect(cx, cy, cell, cell, fill=1, stroke=1)

                num = numbers.get((r, c))
                if num:
                    _draw_text(
                        pdf,
                        cx + cell * 0.10,
                        cy + cell - cell * 0.30,
                        str(num),
                        font_name=font_bold,
                        font_size=max(6.0, cell * 0.24),
                    )
                if reveal:
                    _draw_text(
                        pdf,
                        cx + cell / 2,
                        cy + cell * 0.22,
                        cell_letter,
                        font_name=font_bold,
                        font_size=max(9.0, cell * 0.50),
                        align="center",
                    )

        pdf.setStrokeColor(_GRID_STROKE)
        pdf.setLineWidth(1.35)
        pdf.rect(grid_left, grid_bottom, block_w, block_h, fill=0, stroke=1)
    finally:
        pdf.restoreState()

    return box_x, box_y, box_w, box_h


def _draw_clue_section(
    pdf: canvas.Canvas,
    clues: list[CrosswordClueEntry],
    *,
    top_y: float,
) -> None:
    font_reg, font_bold, _font_italic = _fonts()
    page_w, _page_h = letter
    margin = _MARGIN_IN * 72.0
    usable_w = page_w - 2 * margin
    col_gap = 18.0
    col_w = (usable_w - col_gap) / 2.0
    font_size = CLUE_FONT_MIN_PT
    line_h = _LINE_HEIGHT_PT

    pdf.saveState()
    try:
        pdf.setStrokeColor(_RULE)
        pdf.setLineWidth(0.8)
        label = "CLUES"
        label_w = pdf.stringWidth(label, font_bold, 8)
        mid = page_w / 2.0
        pdf.line(margin, top_y + 3, mid - label_w / 2 - 8, top_y + 3)
        pdf.line(mid + label_w / 2 + 8, top_y + 3, page_w - margin, top_y + 3)
        _draw_centered_text(pdf, mid, top_y, label, font_name=font_bold, font_size=8, fill=_MUTED)

        header_y = top_y - 15.0
        _draw_text(pdf, margin, header_y, "ACROSS", font_name=font_bold, font_size=9.5)
        _draw_text(pdf, margin + col_w + col_gap, header_y, "DOWN", font_name=font_bold, font_size=9.5)
        pdf.setStrokeColor(colors.HexColor("#d6d3d1"))
        pdf.setLineWidth(0.6)
        pdf.line(margin, header_y - 3, margin + col_w, header_y - 3)
        pdf.line(margin + col_w + col_gap, header_y - 3, page_w - margin, header_y - 3)

        across = sorted([c for c in clues if c.direction == "across"], key=lambda c: c.number)
        down = sorted([c for c in clues if c.direction == "down"], key=lambda c: c.number)

        def _paint_column(entries: list[CrosswordClueEntry], x: float, y_start: float) -> None:
            y = y_start
            for entry in entries:
                prefix = f"{entry.number}. "
                clue_text = ascii_pdf_text(str(entry.clue or "").strip() or simple_clue(entry.answer, theme=""))
                prefix_w = pdf.stringWidth(prefix, font_bold, font_size)
                lines = _wrap_clue_line(
                    pdf,
                    clue_text,
                    font_name=font_reg,
                    font_size=font_size,
                    max_width=col_w - prefix_w - 2,
                )
                for idx, line in enumerate(lines):
                    if y < 42:
                        return
                    if idx == 0:
                        _draw_text(pdf, x, y, prefix, font_name=font_bold, font_size=font_size)
                        _draw_text(pdf, x + prefix_w, y, line, font_name=font_reg, font_size=font_size)
                    else:
                        _draw_text(pdf, x + prefix_w, y, line, font_name=font_reg, font_size=font_size)
                    y -= line_h
                y -= 1.0

        _paint_column(across, margin, header_y - 14.0)
        _paint_column(down, margin + col_w + col_gap, header_y - 14.0)
    finally:
        pdf.restoreState()


def _draw_page_footer(pdf: canvas.Canvas, text: str) -> None:
    font_reg, _b, _i = _fonts()
    page_w, _page_h = letter
    margin = _MARGIN_IN * 72.0
    pdf.saveState()
    try:
        pdf.setStrokeColor(colors.HexColor("#e7e5e4"))
        pdf.setLineWidth(0.5)
        pdf.line(margin, 36, page_w - margin, 36)
        _draw_centered_text(
            pdf, page_w / 2.0, 24, ascii_pdf_text(text)[:90],
            font_name=font_reg, font_size=FOOTER_FONT_MIN_PT, fill=_MUTED,
        )
    finally:
        pdf.restoreState()


def _draw_puzzle_page(
    pdf: canvas.Canvas,
    puzzle: CrosswordPuzzleResult,
    *,
    subtitle: str = "",
    reveal: bool = False,
    page_label: str = "",
    book_title: str = "",
) -> None:
    font_reg, font_bold, font_italic = _fonts()
    page_w, page_h = letter
    margin = _MARGIN_IN * 72.0
    _paint_white_page(pdf)

    if reveal:
        pdf.setFillColor(_ANSWER_BAND)
        pdf.rect(0, page_h - 30, page_w, 30, fill=1, stroke=0)
        _draw_centered_text(
            pdf, page_w / 2.0, page_h - 19, "ANSWER KEY",
            font_name=font_bold, font_size=ANSWER_HEADING_MIN_PT,
            fill=colors.HexColor("#f5e6c8"),
        )
        y = page_h - margin - 6
    else:
        pdf.setFillColor(_SOFT_BAND)
        pdf.rect(0, page_h - 16, page_w, 16, fill=1, stroke=0)
        pdf.setStrokeColor(_RULE)
        pdf.setLineWidth(1.1)
        pdf.line(0, page_h - 16, page_w, page_h - 16)
        y = page_h - margin

    raw_title = puzzle.puzzle_title if not reveal else f"{puzzle.puzzle_title} - Answer Key"
    title = ascii_pdf_text(raw_title)
    _draw_centered_text(
        pdf, page_w / 2.0, y - 10.0, title[:72],
        font_name=font_bold, font_size=HEADING_FONT_MIN_PT,
    )
    y -= 22.0

    if subtitle:
        _draw_centered_text(
            pdf, page_w / 2.0, y - 5.0, ascii_pdf_text(subtitle)[:80],
            font_name=font_reg, font_size=10, fill=_MUTED,
        )
        y -= 14.0

    if page_label:
        _draw_centered_text(
            pdf, page_w / 2.0, y - 4.0, ascii_pdf_text(page_label),
            font_name=font_bold, font_size=9.5,
        )
        y -= 13.0

    instruction = (
        "Filled letters show the completed crossword."
        if reveal
        else "Fill each white square using the clues below. Dark squares are unused."
    )
    _draw_centered_text(
        pdf, page_w / 2.0, y - 4.0, instruction,
        font_name=font_italic, font_size=INSTRUCTION_FONT_MIN_PT, fill=_MUTED,
    )
    y -= 14.0

    header_budget = page_h - y + 8
    _box_x, box_y, _box_w, _box_h = _draw_crossword_grid(
        pdf, puzzle, box_top_y=y, reveal=reveal, header_budget=header_budget,
    )
    clue_top = box_y - _CLUE_GAP_PT
    if puzzle.clues:
        _draw_clue_section(pdf, puzzle.clues, top_y=clue_top)
    else:
        _draw_centered_text(
            pdf, page_w / 2.0, clue_top - 10.0,
            "Clues unavailable for this puzzle.",
            font_name=font_italic, font_size=9, fill=_MUTED,
        )

    footer = book_title or "Crossword Puzzle Book"
    if page_label:
        footer = f"{ascii_pdf_text(footer)}  |  {ascii_pdf_text(page_label)}"
    _draw_page_footer(pdf, footer)


def _fill_vertical_gradient(
    pdf: canvas.Canvas,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    stops: list[tuple[float, colors.Color]],
    steps: int = 64,
) -> None:
    """Draw a multi-stop vertical gradient (local vector only)."""
    stops = sorted(stops, key=lambda s: s[0])
    step_h = h / steps
    for i in range(steps):
        t = i / max(1, steps - 1)
        # Find surrounding stops
        lo, hi = stops[0], stops[-1]
        for a, b in zip(stops, stops[1:]):
            if a[0] <= t <= b[0]:
                lo, hi = a, b
                break
        span = max(1e-6, hi[0] - lo[0])
        u = (t - lo[0]) / span
        c0, c1 = lo[1], hi[1]
        r = c0.red + (c1.red - c0.red) * u
        g = c0.green + (c1.green - c0.green) * u
        b = c0.blue + (c1.blue - c0.blue) * u
        pdf.setFillColor(colors.Color(r, g, b))
        pdf.rect(x, y + h - (i + 1) * step_h, w, step_h + 0.5, fill=1, stroke=0)


def _draw_gold_rush_scene(pdf: canvas.Canvas, page_w: float, page_h: float) -> None:
    """Richer local Gold Rush scene: sunset, foothills, camp, pan, pickaxe."""
    # Warm sunset disc
    pdf.setFillColor(colors.HexColor("#f59e0b"))
    pdf.circle(page_w * 0.72, page_h * 0.62, 54, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#fde68a"))
    pdf.circle(page_w * 0.72, page_h * 0.62, 30, fill=1, stroke=0)

    # Distant foothills
    pdf.setFillColor(colors.HexColor("#5b3a1e"))
    path = pdf.beginPath()
    path.moveTo(0, page_h * 0.34)
    path.lineTo(page_w * 0.14, page_h * 0.46)
    path.lineTo(page_w * 0.28, page_h * 0.36)
    path.lineTo(page_w * 0.46, page_h * 0.52)
    path.lineTo(page_w * 0.62, page_h * 0.38)
    path.lineTo(page_w * 0.80, page_h * 0.50)
    path.lineTo(page_w, page_h * 0.40)
    path.lineTo(page_w, 0)
    path.lineTo(0, 0)
    path.close()
    pdf.drawPath(path, fill=1, stroke=0)

    # Mid ridge
    pdf.setFillColor(colors.HexColor("#3b2716"))
    path2 = pdf.beginPath()
    path2.moveTo(0, page_h * 0.24)
    path2.lineTo(page_w * 0.22, page_h * 0.34)
    path2.lineTo(page_w * 0.40, page_h * 0.26)
    path2.lineTo(page_w * 0.58, page_h * 0.36)
    path2.lineTo(page_w * 0.78, page_h * 0.27)
    path2.lineTo(page_w, page_h * 0.33)
    path2.lineTo(page_w, 0)
    path2.lineTo(0, 0)
    path2.close()
    pdf.drawPath(path2, fill=1, stroke=0)

    # Near ground
    pdf.setFillColor(colors.HexColor("#24160d"))
    pdf.rect(0, 0, page_w, page_h * 0.18, fill=1, stroke=0)

    # Mining-camp silhouette (tent + smoke)
    pdf.setFillColor(colors.HexColor("#1a100a"))
    tent = pdf.beginPath()
    tent.moveTo(page_w * 0.52, page_h * 0.18)
    tent.lineTo(page_w * 0.58, page_h * 0.28)
    tent.lineTo(page_w * 0.64, page_h * 0.18)
    tent.close()
    pdf.drawPath(tent, fill=1, stroke=0)
    pdf.setStrokeColor(colors.HexColor("#d6d3d1"))
    pdf.setLineWidth(1.0)
    pdf.circle(page_w * 0.58, page_h * 0.31, 3, fill=0, stroke=1)
    pdf.circle(page_w * 0.585, page_h * 0.345, 2.2, fill=0, stroke=1)

    # Gold pan with nugget
    pan_x, pan_y = page_w * 0.20, page_h * 0.16
    pdf.setFillColor(colors.HexColor("#92400e"))
    pdf.ellipse(pan_x - 38, pan_y - 12, pan_x + 38, pan_y + 18, fill=1, stroke=0)
    pdf.setStrokeColor(colors.HexColor("#fbbf24"))
    pdf.setLineWidth(1.6)
    pdf.ellipse(pan_x - 38, pan_y - 12, pan_x + 38, pan_y + 18, fill=0, stroke=1)
    pdf.setFillColor(colors.HexColor("#fcd34d"))
    pdf.circle(pan_x + 6, pan_y + 2, 5, fill=1, stroke=0)
    pdf.circle(pan_x - 8, pan_y + 1, 3.2, fill=1, stroke=0)

    # Pickaxe
    pdf.setStrokeColor(colors.HexColor("#fbbf24"))
    pdf.setLineWidth(2.4)
    pdf.line(page_w * 0.78, page_h * 0.14, page_w * 0.88, page_h * 0.30)
    pdf.setLineWidth(3.0)
    pdf.line(page_w * 0.74, page_h * 0.27, page_w * 0.92, page_h * 0.24)


def _wrap_title_lines(
    pdf: canvas.Canvas,
    title: str,
    *,
    font_name: str,
    font_size: float,
    max_width: float,
    max_lines: int = 3,
) -> list[str]:
    words = ascii_pdf_text(title).split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = f"{current} {word}".strip()
        if pdf.stringWidth(trial, font_name, font_size) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return (lines or [ascii_pdf_text(title)[:40]])[:max_lines]


def _parse_subtitle_parts(subtitle: str, cover_design: dict) -> tuple[str, str]:
    """Split '12 Crossword Puzzles - Easy Level' into count line + level line."""
    sub = ascii_pdf_text(subtitle)
    difficulty = ascii_pdf_text(cover_design.get("difficulty") or "")
    m = re.search(r"(\d+)\s*Crossword Puzzles", sub, flags=re.I)
    count_line = f"{m.group(1)} Crossword Puzzles" if m else (sub.split("-")[0].strip() if sub else "Crossword Puzzles")
    level = ""
    if "Easy" in sub or difficulty.lower() == "easy":
        level = "Easy Level"
    elif "Medium" in sub or difficulty.lower() == "medium":
        level = "Medium Level"
    elif "Hard" in sub or difficulty.lower() == "hard":
        level = "Hard Level"
    elif "-" in sub:
        level = sub.split("-", 1)[1].strip()
    return count_line, level


def _draw_professional_local_cover(pdf: canvas.Canvas, cover_design: dict, page_w: float, page_h: float) -> None:
    """Topic-matched local cover using user title/theme/audience/difficulty/count."""
    font_reg, font_bold, _font_italic = _fonts()
    title = ascii_pdf_text(cover_design.get("title") or "Crossword Puzzle Book")
    subtitle = ascii_pdf_text(cover_design.get("subtitle") or "")
    author = ascii_pdf_text(cover_design.get("author") or "")
    audience = ascii_pdf_text(cover_design.get("audience") or "")
    topic = ascii_pdf_text(cover_design.get("topic") or title).lower()
    is_gold_rush = any(k in topic or k in title.lower() for k in (
        "gold rush", "goal rush", "forty-niner", "49er", "prospector",
    ))

    if is_gold_rush:
        _fill_vertical_gradient(
            pdf, x=0, y=0, w=page_w, h=page_h,
            stops=[
                (0.0, colors.HexColor("#7c2d12")),
                (0.35, colors.HexColor("#b45309")),
                (0.62, colors.HexColor("#78350f")),
                (1.0, colors.HexColor("#1c1108")),
            ],
        )
        _draw_gold_rush_scene(pdf, page_w, page_h)
        accent = colors.HexColor("#fbbf24")
        title_c = colors.HexColor("#fffbeb")
        sub_c = colors.HexColor("#fef3c7")
        panel = colors.HexColor("#29180e")
        badge = "CALIFORNIA GOLD RUSH HISTORY"
        footer = "A themed crossword book for adults and history fans"
        if audience:
            footer = f"For {audience}  |  Themed crossword collection"
    else:
        _fill_vertical_gradient(
            pdf, x=0, y=0, w=page_w, h=page_h,
            stops=[
                (0.0, colors.HexColor("#0f172a")),
                (0.5, colors.HexColor("#1e3a5f")),
                (1.0, colors.HexColor("#0b1220")),
            ],
        )
        accent = colors.HexColor("#93c5fd")
        title_c = colors.white
        sub_c = colors.HexColor("#cbd5e1")
        panel = colors.HexColor("#111827")
        badge = "CROSSWORD PUZZLE COLLECTION"
        footer = "Printable crossword puzzle book"

    # Dual frame
    inset = 24
    pdf.setStrokeColor(accent)
    pdf.setLineWidth(2.6)
    pdf.rect(inset, inset, page_w - 2 * inset, page_h - 2 * inset, fill=0, stroke=1)
    pdf.setLineWidth(0.8)
    pdf.rect(inset + 7, inset + 7, page_w - 2 * (inset + 7), page_h - 2 * (inset + 7), fill=0, stroke=1)

    # Cream title card
    panel_h = page_h * 0.34
    panel_y = page_h * 0.42
    pdf.setFillColor(colors.Color(panel.red, panel.green, panel.blue, alpha=0.92))
    pdf.roundRect(44, panel_y, page_w - 88, panel_h, 12, fill=1, stroke=0)
    pdf.setStrokeColor(accent)
    pdf.setLineWidth(1.3)
    pdf.roundRect(44, panel_y, page_w - 88, panel_h, 12, fill=0, stroke=1)

    _draw_centered_text(
        pdf, page_w / 2.0, panel_y + panel_h + 16, badge,
        font_name=font_bold, font_size=8.5, fill=accent,
    )

    pdf.setStrokeColor(accent)
    pdf.setLineWidth(1.2)
    rule_y = panel_y + panel_h - 26
    pdf.line(page_w * 0.28, rule_y, page_w * 0.72, rule_y)

    title_size = max(COVER_TITLE_MIN_PT, 26 if len(title) < 28 else 22 if len(title) < 40 else 18)
    lines = _wrap_title_lines(
        pdf, title, font_name=font_bold, font_size=title_size, max_width=page_w * 0.70,
    )
    while title_size > COVER_TITLE_MIN_PT and any(
        pdf.stringWidth(line, font_bold, title_size) > page_w * 0.72 for line in lines
    ):
        title_size -= 1
        lines = _wrap_title_lines(
            pdf, title, font_name=font_bold, font_size=title_size, max_width=page_w * 0.70,
        )

    title_top = rule_y - 32
    for idx, line in enumerate(lines):
        _draw_centered_text(
            pdf, page_w / 2.0, title_top - idx * (title_size + 7), line,
            font_name=font_bold, font_size=title_size, fill=title_c,
        )

    count_line, level_line = _parse_subtitle_parts(subtitle, cover_design)
    sub_y = title_top - len(lines) * (title_size + 7) - 18
    _draw_centered_text(
        pdf, page_w / 2.0, sub_y, count_line,
        font_name=font_bold, font_size=13, fill=sub_c,
    )
    if level_line:
        _draw_centered_text(
            pdf, page_w / 2.0, sub_y - 18, level_line,
            font_name=font_reg, font_size=12, fill=sub_c,
        )
        sub_y -= 18
    if author:
        _draw_centered_text(
            pdf, page_w / 2.0, sub_y - 18, author[:60],
            font_name=font_reg, font_size=10, fill=sub_c,
        )

    _draw_centered_text(
        pdf, page_w / 2.0, 46, footer,
        font_name=font_reg, font_size=9, fill=accent,
    )


def _draw_cover_page_from_design(pdf: canvas.Canvas, cover_design: dict, layout: CrosswordPdfLayoutInfo) -> None:
    from services.cover_agent import _cover_image_path, _has_cover_image

    page_w, page_h = letter
    pkg = str(cover_design.get("package_id") or "")

    # Explicit AI/uploaded artwork only — never auto-sync HTML covers
    # (CSS letter-spacing previously corrupted title glyphs).
    if pkg and _has_cover_image(pkg) and cover_design.get("use_ai_image"):
        img_path = _cover_image_path(pkg)
        img = ImageReader(img_path)
        iw, ih = img.getSize()
        scale = max(page_w / iw, page_h / ih)
        draw_w = iw * scale
        draw_h = ih * scale
        x = (page_w - draw_w) / 2
        y = (page_h - draw_h) / 2
        pdf.drawImage(img_path, x, y, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")
        if cover_design.get("text_overlay", True) is not False:
            _draw_composited_cover_text_overlay(pdf, cover_design, page_w, page_h)
        layout.cover_page_count = 1
        return

    _draw_professional_local_cover(pdf, cover_design, page_w, page_h)
    layout.cover_page_count = 1


def _draw_composited_cover_text_overlay(pdf: canvas.Canvas, cover_design: dict, page_w: float, page_h: float) -> None:
    from services.cover_agent import (
        _pdf_text_anchor_x,
        _pdf_text_anchor_y,
        cover_author_font_pt,
        cover_subtitle_font_pt,
        cover_title_font_pt,
        normalize_text_position,
    )

    font_reg, font_bold, _i = _fonts()
    palette = cover_design.get("color_palette") if isinstance(cover_design.get("color_palette"), dict) else {}
    title = ascii_pdf_text(cover_design.get("title") or "Untitled")
    subtitle = ascii_pdf_text(cover_design.get("subtitle") or "")
    author = ascii_pdf_text(cover_design.get("author") or "")
    text_c = colors.HexColor(palette.get("text") or "#ffffff")
    sub_c = colors.HexColor(palette.get("muted") or "#e2e8f0")
    pos = normalize_text_position(cover_design)
    align = str(pos["align"])
    anchor_x = _pdf_text_anchor_x(page_w, cover_design)
    anchor_y = _pdf_text_anchor_y(page_h, cover_design)
    title_pt = max(COVER_TITLE_MIN_PT, cover_title_font_pt(cover_design))
    sub_pt = max(11.0, cover_subtitle_font_pt(cover_design))
    auth_pt = max(9.0, cover_author_font_pt(cover_design))
    _draw_text(pdf, anchor_x, anchor_y, title[:80], font_name=font_bold, font_size=title_pt, align=align, fill=text_c)
    if subtitle:
        _draw_text(
            pdf, anchor_x, anchor_y - title_pt - 8, subtitle[:120],
            font_name=font_reg, font_size=sub_pt, align=align, fill=sub_c,
        )
    if author:
        _draw_text(
            pdf, anchor_x, anchor_y - title_pt - sub_pt - 16, author[:80],
            font_name=font_reg, font_size=auth_pt, align=align, fill=sub_c,
        )


def build_single_crossword_pdf_bytes(
    puzzle: CrosswordPuzzleResult,
    *,
    product_title: str,
    subtitle: str = "",
    include_answer_key: bool,
    cover_design: dict | None = None,
) -> tuple[bytes, CrosswordPdfLayoutInfo]:
    ensure_crossword_fonts()
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    layout = CrosswordPdfLayoutInfo()

    pdf.setTitle(ascii_pdf_text(product_title) or "Crossword Puzzle")
    pdf.setAuthor("Digital Product Factory")
    pdf.setSubject(ascii_pdf_text(subtitle) or "Crossword Puzzle")
    pdf.setCreator("Digital Product Factory - Crossword Generator")

    _draw_puzzle_page(pdf, puzzle, subtitle=subtitle, reveal=False, book_title=product_title)
    layout.puzzle_page_count += 1
    pdf.showPage()

    if include_answer_key:
        _draw_puzzle_page(
            pdf, puzzle, subtitle=subtitle, reveal=True,
            page_label="Answer Key", book_title=product_title,
        )
        layout.answer_key_page_count += 1
        pdf.showPage()

    pdf.save()
    layout.page_count = layout.cover_page_count + layout.puzzle_page_count + layout.answer_key_page_count
    return buffer.getvalue(), layout


def build_crossword_book_pdf_bytes(
    puzzles: list[CrosswordPuzzleResult],
    *,
    product_title: str,
    subtitle: str = "",
    include_answer_key: bool,
    cover_design: dict | None = None,
) -> tuple[bytes, CrosswordPdfLayoutInfo]:
    ensure_crossword_fonts()
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    layout = CrosswordPdfLayoutInfo()

    pdf.setTitle(ascii_pdf_text(product_title) or "Crossword Puzzle Book")
    pdf.setAuthor("Digital Product Factory")
    pdf.setSubject(ascii_pdf_text(subtitle) or f"Crossword Puzzle Book - {len(puzzles)} puzzles")
    pdf.setCreator("Digital Product Factory - Crossword Generator")

    if cover_design:
        # Carry difficulty into local cover when present on fields-like keys.
        cover = dict(cover_design)
        if not cover.get("difficulty") and subtitle:
            cover["difficulty"] = "Easy" if "Easy" in subtitle else (
                "Medium" if "Medium" in subtitle else ("Hard" if "Hard" in subtitle else "")
            )
        _draw_cover_page_from_design(pdf, cover, layout)
        pdf.showPage()

    for idx, puzzle in enumerate(puzzles, start=1):
        label = f"Puzzle {idx} of {len(puzzles)}" if len(puzzles) > 1 else ""
        _draw_puzzle_page(
            pdf, puzzle, subtitle=subtitle, reveal=False,
            page_label=label, book_title=product_title,
        )
        layout.puzzle_page_count += 1
        pdf.showPage()

    if include_answer_key:
        for idx, puzzle in enumerate(puzzles, start=1):
            _draw_puzzle_page(
                pdf,
                puzzle,
                subtitle=subtitle,
                reveal=True,
                page_label=f"Answer Key - Puzzle {idx}",
                book_title=product_title,
            )
            layout.answer_key_page_count += 1
            pdf.showPage()

    pdf.save()
    layout.page_count = layout.cover_page_count + layout.puzzle_page_count + layout.answer_key_page_count
    return buffer.getvalue(), layout
