"""Direct ReportLab PDF renderer for Word Search single-worksheet interiors.

ACTIVE WORD SEARCH RENDERER: MiniMax-style renderer
- clean puzzle page, capsule/ellipse answer marks, red answer letters
- no yellow HTML highlights, no legacy cell-box answer keys

Locked answer-key drawing uses the solution table plus capsule geometry.
"""
from __future__ import annotations

import io
import math
from dataclasses import dataclass

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF

from .builder import PuzzleResult
from .solution_table import (
    SolutionTable,
    WordSolutionEntry,
    finalize_solution_ovals,
    prepare_answer_key_geometry,
    validate_solution_table_for_render,
    _OVAL_END_PAD_RATIO,
    _OVAL_SIDE_PAD_RATIO,
)

_DIFFICULTY_HELP = {
    "easy": "Words may appear horizontally or vertically.",
    "medium": "Words may appear horizontally, vertically, or diagonally.",
    "hard": "Words may appear in any direction, including backward.",
}

_MARGIN_IN = 0.45
_WORD_LIST_COLUMNS = 3
_PUZZLE_WORD_GAP_PT = 24.0
_BOX_PADDING_PT = 8.0
_CELL_MIN_PT = 18.0
_CELL_MAX_PT = 28.0

# Answer key styling - black capsule outline with red letters inside
_CAPSULE_STROKE = colors.black  # Black outline
_CAPSULE_WIDTH = 1.5
_ANSWER_COLOR = colors.HexColor("#dc2626")  # Red letters
# Capsule geometry rules:
# - Capsule width = font_size + side_pad * 2
# - Capsule length = word_length + end_pad * 2
# - Semicircle radius = capsule_width / 2
# - Gap from letter to semicircle = end_pad - capsule_width/2
# - To NOT touch letters: end_pad >= capsule_width/2
# - With font_size=16, side_pad=2: capsule_width=20, so end_pad >= 10
_CAPSULE_SIDE_PAD = 2.0  # Space on sides of letter
# end_pad must be >= capsule_width/2 for semicircles not to touch letters
# Use 14 to give a 4-point buffer (14 > 10)
_CAPSULE_END_PAD = 14.0  # Space at ends - semicircles don't touch letters


@dataclass
class DirectPdfLayoutInfo:
    render_engine: str = "minimax_direct"
    page_count: int = 0
    outer_box_count: int = 0
    word_list_columns: int = _WORD_LIST_COLUMNS
    cell_size_pt: float = 0.0
    grid_size: int = 0
    cell_border_count: int = 0
    answer_fill_count: int = 0
    answer_outline_count: int = 0
    answer_oval_count: int = 0
    answer_line_mark_count: int = 0
    answer_cell_box_segment_count: int = 0
    puzzle_page_mark_count: int = 0
    answer_key_validated: bool = False
    grid_centered: bool = True
    puzzle_fits_one_page: bool = True
    word_list_draw_count: int = 0
    answer_box_top_y: float = 0.0
    answer_ovals_validated: bool = False
    cover_page_count: int = 0


def _draw_composited_cover_text_overlay(pdf: canvas.Canvas, cover_design: dict, page_w: float, page_h: float) -> None:
    """Draw editable title/subtitle/author over a full-page cover image."""
    from reportlab.lib import colors

    from services.cover_agent import (
        _is_puzzle_book_cover,
        _pdf_draw_aligned_string,
        _pdf_text_anchor_x,
        _pdf_text_anchor_y,
        _TEXT_PANEL_ALPHA,
        _TEXT_PANEL_ALPHA_PUZZLE,
        cover_author_font_pt,
        cover_subtitle_font_pt,
        cover_title_font_pt,
        normalize_text_position,
    )

    palette = cover_design.get("color_palette") if isinstance(cover_design.get("color_palette"), dict) else {}
    title = str(cover_design.get("title") or "Untitled")
    subtitle = str(cover_design.get("subtitle") or "")
    author = str(cover_design.get("author") or "")
    text_c = colors.HexColor(palette.get("text") or "#ffffff")
    sub_c = colors.HexColor(palette.get("muted") or "#e2e8f0")

    pos = normalize_text_position(cover_design)
    align = str(pos["align"])
    anchor_x = _pdf_text_anchor_x(page_w, cover_design)
    anchor_y = _pdf_text_anchor_y(page_h, cover_design)
    title_pt = cover_title_font_pt(cover_design)
    sub_pt = cover_subtitle_font_pt(cover_design)
    auth_pt = cover_author_font_pt(cover_design)
    pad_x, pad_y = 18.0, 14.0
    line_gap = max(title_pt + 6, 18)
    sub_offset = sub_pt + 6 if subtitle else 0
    auth_offset = auth_pt + 6 if author else 0
    pdf.setFont("Helvetica-Bold", title_pt)
    title_w = pdf.stringWidth(title[:80], "Helvetica-Bold", title_pt)
    sub_w = pdf.stringWidth(subtitle[:120], "Helvetica", sub_pt) if subtitle else 0
    auth_w = pdf.stringWidth(author[:80], "Helvetica", auth_pt) if author else 0
    content_w = max(title_w, sub_w, auth_w)
    panel_w = min(page_w * 0.86, content_w + pad_x * 2)
    panel_top = anchor_y + title_pt * 0.75 + pad_y
    panel_bottom = anchor_y - line_gap - sub_offset - auth_offset - pad_y
    if not subtitle and not author:
        panel_bottom = anchor_y - pad_y
    elif not author:
        panel_bottom = anchor_y - line_gap - pad_y
    panel_h = max(panel_top - panel_bottom, title_pt + pad_y * 2)
    if align == "left":
        panel_x = max(18.0, anchor_x - pad_x)
    elif align == "right":
        panel_x = min(page_w - panel_w - 18.0, anchor_x - panel_w + pad_x)
    else:
        panel_x = max(18.0, min(page_w - panel_w - 18.0, anchor_x - panel_w / 2))

    pdf.saveState()
    panel_alpha = _TEXT_PANEL_ALPHA_PUZZLE if _is_puzzle_book_cover(cover_design) else _TEXT_PANEL_ALPHA
    pdf.setFillColor(colors.Color(0, 0, 0, alpha=panel_alpha))
    pdf.roundRect(panel_x, panel_bottom, panel_w, panel_h, 8, fill=1, stroke=0)
    pdf.setStrokeColor(colors.Color(1, 1, 1, alpha=0.12))
    pdf.setLineWidth(0.5)
    pdf.roundRect(panel_x, panel_bottom, panel_w, panel_h, 8, fill=0, stroke=1)
    if _is_puzzle_book_cover(cover_design):
        pdf.saveState()
        pdf.setStrokeColor(colors.Color(1, 1, 1, alpha=0.05))
        pdf.setLineWidth(0.3)
        cell = 11.0
        cols = max(1, int(panel_w // cell))
        rows = max(1, int(panel_h // cell))
        for i in range(cols + 1):
            x = panel_x + i * cell
            if x > panel_x + panel_w:
                break
            pdf.line(x, panel_bottom, x, panel_bottom + panel_h)
        for j in range(rows + 1):
            y = panel_bottom + j * cell
            if y > panel_bottom + panel_h:
                break
            pdf.line(panel_x, y, panel_x + panel_w, y)
        pdf.restoreState()
    pdf.setFillColor(text_c)
    pdf.setFont("Helvetica-Bold", title_pt)
    _pdf_draw_aligned_string(pdf, anchor_x, anchor_y, title[:80], align=align)
    if subtitle:
        pdf.setFillColor(sub_c)
        pdf.setFont("Helvetica", sub_pt)
        _pdf_draw_aligned_string(pdf, anchor_x, anchor_y - line_gap, subtitle[:120], align=align)
    if author:
        pdf.setFillColor(sub_c)
        pdf.setFont("Helvetica", auth_pt)
        auth_y = anchor_y - line_gap - sub_offset
        _pdf_draw_aligned_string(pdf, anchor_x, auth_y, author[:80], align=align)
    pdf.restoreState()


def _draw_cover_page_from_design(pdf: canvas.Canvas, cover_design: dict, layout: DirectPdfLayoutInfo) -> None:
    """Draw the shared cover agent artwork as the first PDF page."""
    from services.cover_agent import _cover_image_path, _has_cover_image, sync_cover_html_if_needed

    page_w, page_h = letter
    pkg = str(cover_design.get("package_id") or "")
    synced = sync_cover_html_if_needed(dict(cover_design), pkg) if cover_design else cover_design

    if pkg and _has_cover_image(pkg):
        img_path = _cover_image_path(pkg)
        img = ImageReader(img_path)
        iw, ih = img.getSize()
        scale = max(page_w / iw, page_h / ih)
        draw_w = iw * scale
        draw_h = ih * scale
        x = (page_w - draw_w) / 2
        y = (page_h - draw_h) / 2
        pdf.drawImage(img_path, x, y, width=draw_w, height=draw_h, preserveAspectRatio=True, mask="auto")
        synced_cover = synced or cover_design
        if synced_cover.get("text_overlay", True) and synced_cover.get("use_ai_image", True):
            _draw_composited_cover_text_overlay(pdf, synced_cover, page_w, page_h)
    else:
        from services.cover_template_fallback import draw_template_cover_pdf_page

        draw_template_cover_pdf_page(pdf, synced or cover_design, layout)
        return

    layout.cover_page_count = 1
    layout.page_count += 1
    layout.outer_box_count += 1


@dataclass(frozen=True)
class GridLayout:
    """Shared coordinate system for letters, outer box, and answer marks."""

    cell_size: float
    font_size: float
    grid_size: int
    box_x: float
    box_y: float
    box_w: float
    box_h: float
    box_top: float
    grid_left: float
    grid_top: float
    grid_bottom: float
    letter_center_x: tuple[float, ...]
    letter_center_y: tuple[float, ...]

    def letter_center(self, row: int, col: int) -> tuple[float, float]:
        return self.letter_center_x[col], self.letter_center_y[row]

    @property
    def puzzle_left(self) -> float:
        return self.grid_left

    @property
    def puzzle_top(self) -> float:
        return self.grid_top

    @property
    def cell_width(self) -> float:
        return self.cell_size

    @property
    def cell_height(self) -> float:
        return self.cell_size

    @property
    def puzzle_outer_box(self) -> tuple[float, float, float, float]:
        return self.box_x, self.box_y, self.box_w, self.box_h


def compute_answer_page_grid(
    puzzle: PuzzleResult,
    *,
    product_title: str,
    cell_size_pt: float = 0.0,
) -> tuple[GridLayout, float, float]:
    """Compute the answer-key page grid without rendering PDF bytes."""
    page_w, page_h = letter
    margin = _MARGIN_IN * 72.0
    y = page_h - margin - 28.0 - 24.0
    cell_size = cell_size_pt if cell_size_pt > 0 else _cell_size_pt(
        page_w=page_w,
        page_h=page_h,
        grid_size=puzzle.grid_size,
        word_count=0,
        include_word_list=False,
    )
    grid = calculate_grid_layout(
        page_w=page_w,
        box_top_y=y,
        grid_size=puzzle.grid_size,
        cell_size=cell_size,
    )
    return grid, cell_size, y


def calculate_grid_layout(
    *,
    page_w: float,
    box_top_y: float,
    grid_size: int,
    cell_size: float,
) -> GridLayout:
    """Compute one shared grid layout used by letters, outer box, and answer marks."""
    pad = max(
        _BOX_PADDING_PT,
        cell_size * (_OVAL_END_PAD_RATIO + _OVAL_SIDE_PAD_RATIO),
    )
    block_w = cell_size * grid_size
    block_h = cell_size * grid_size
    box_w = block_w + 2 * pad
    box_h = block_h + 2 * pad
    box_x = (page_w - box_w) / 2.0
    box_y = box_top_y - box_h
    grid_left = box_x + pad
    grid_bottom = box_y + pad
    grid_top = grid_bottom + block_h

    font_size = min(cell_size * 0.58, 16.0)
    vertical_adjust = (cell_size - font_size) * 0.35

    letter_center_x = tuple(
        grid_left + col * cell_size + cell_size / 2.0 for col in range(grid_size)
    )
    letter_center_y = tuple(
        grid_bottom + (grid_size - 1 - row) * cell_size + vertical_adjust
        for row in range(grid_size)
    )

    return GridLayout(
        cell_size=cell_size,
        font_size=font_size,
        grid_size=grid_size,
        box_x=box_x,
        box_y=box_y,
        box_w=box_w,
        box_h=box_h,
        box_top=box_top_y,
        grid_left=grid_left,
        grid_top=grid_top,
        grid_bottom=grid_bottom,
        letter_center_x=letter_center_x,
        letter_center_y=letter_center_y,
    )


def answer_path_direction(cells: list[tuple[int, int]]) -> str:
    if len(cells) < 2:
        return "horizontal"
    r0, c0 = cells[0]
    r1, c1 = cells[-1]
    if r0 == r1:
        return "horizontal"
    if c0 == c1:
        return "vertical"
    return "diagonal"


def answer_word_endpoints(
    grid: GridLayout,
    cells: list[tuple[int, int]],
) -> tuple[tuple[float, float], tuple[float, float], str]:
    if not cells:
        return (0.0, 0.0), (0.0, 0.0), "horizontal"
    start = grid.letter_center(cells[0][0], cells[0][1])
    end = grid.letter_center(cells[-1][0], cells[-1][1])
    return start, end, answer_path_direction(cells)


def layout_info_to_dict(layout: DirectPdfLayoutInfo) -> dict:
    return {
        "page_count": layout.page_count,
        "outer_box_count": layout.outer_box_count,
        "word_list_columns": layout.word_list_columns,
        "cell_size_pt": layout.cell_size_pt,
        "grid_size": layout.grid_size,
        "cell_border_count": layout.cell_border_count,
        "answer_fill_count": layout.answer_fill_count,
        "answer_outline_count": layout.answer_outline_count,
        "answer_smooth_mark_count": layout.answer_oval_count,
        "answer_oval_count": layout.answer_oval_count,
        "answer_line_mark_count": layout.answer_line_mark_count,
        "answer_cell_box_segment_count": layout.answer_cell_box_segment_count,
        "puzzle_page_mark_count": layout.puzzle_page_mark_count,
        "grid_centered": layout.grid_centered,
        "puzzle_fits_one_page": layout.puzzle_fits_one_page,
        "answer_key_validated": layout.answer_key_validated,
        "word_list_draw_count": layout.word_list_draw_count,
        "answer_box_top_y": layout.answer_box_top_y,
        "answer_ovals_validated": layout.answer_ovals_validated,
    }


def compute_single_worksheet_layout(
    puzzle: PuzzleResult,
    *,
    subtitle: str = "",
    include_answer_key: bool = True,
) -> tuple[DirectPdfLayoutInfo, list[str], list[str]]:
    """Compute worksheet layout metadata plus oval geometry without rendering PDF."""
    layout = DirectPdfLayoutInfo(
        render_engine="direct",
        page_count=2 if include_answer_key else 1,
        word_list_columns=_WORD_LIST_COLUMNS,
    )
    oval_errors: list[str] = []
    oval_warnings: list[str] = []
    page_w, page_h = letter
    margin = _MARGIN_IN * 72.0
    y = page_h - margin

    y -= 28.0
    extra_header_pt = 18.0 if subtitle else 0.0
    if subtitle:
        y -= 18.0
    y -= 24.0

    cell_size = _cell_size_pt(
        page_w=page_w,
        page_h=page_h,
        grid_size=puzzle.grid_size,
        word_count=len(puzzle.word_bank),
        include_word_list=True,
        extra_header_pt=extra_header_pt,
    )
    layout.cell_size_pt = round(cell_size, 1)
    layout.grid_size = puzzle.grid_size

    puzzle_grid = calculate_grid_layout(
        page_w=page_w,
        box_top_y=y,
        grid_size=puzzle.grid_size,
        cell_size=cell_size,
    )
    _record_grid_layout_quality(
        page_w=page_w,
        grid=puzzle_grid,
        layout=layout,
        include_word_list=True,
    )
    layout.outer_box_count = 1
    layout.puzzle_page_mark_count = 0
    rows = max(1, math.ceil(len(puzzle.word_bank) / _WORD_LIST_COLUMNS))
    if layout.puzzle_fits_one_page:
        layout.word_list_draw_count = len(puzzle.word_bank)
    else:
        layout.word_list_draw_count = rows * _WORD_LIST_COLUMNS

    if not include_answer_key:
        return layout, oval_errors, oval_warnings

    answer_top = page_h - margin - 28.0 - 24.0
    layout.answer_box_top_y = answer_top

    answer_cell_size = cell_size
    answer_grid = calculate_grid_layout(
        page_w=page_w,
        box_top_y=answer_top,
        grid_size=puzzle.grid_size,
        cell_size=answer_cell_size,
    )

    if not puzzle.solution_table:
        oval_errors.append("Solution table is missing.")
        return layout, oval_errors, oval_warnings

    table_errors = validate_solution_table_for_render(
        puzzle.solution_table,
        word_count=len(puzzle.word_bank),
    )
    oval_errors.extend(table_errors)

    if not table_errors:
        blocking, proximity = prepare_answer_key_geometry(
            puzzle.solution_table,
            answer_grid,
            puzzle.grid,
        )
        oval_errors.extend(blocking)
        oval_warnings.extend(proximity)

    layout.answer_ovals_validated = not oval_errors
    if layout.answer_ovals_validated:
        geometry_errors = validate_solution_table_for_render(
            puzzle.solution_table,
            word_count=len(puzzle.word_bank),
            require_geometry=True,
        )
        oval_errors.extend(geometry_errors)
        layout.answer_ovals_validated = not geometry_errors

    if layout.answer_ovals_validated and puzzle.solution_table.entries:
        layout.answer_oval_count = len(puzzle.solution_table.entries)
        layout.answer_outline_count = layout.answer_oval_count
        layout.answer_key_validated = True
        layout.outer_box_count = 2

    return layout, oval_errors, oval_warnings


def _calculate_capsule_geometry(
    entry: WordSolutionEntry,
    grid: GridLayout,
) -> tuple[float, float, float, float, float]:
    """
    Calculate capsule parameters from solution entry.
    
    The capsule is a rounded rectangle (capsule shape) that:
    - Contains ALL letters of the word with even padding on all sides
    - Has extra space before first letter and after last letter
    - Does NOT touch any letters
    
    Capsule structure:
    - Length = word_length + 2*end_padding (extra space at each end)
    - Width = cell_size + 2*side_padding (even padding on all sides)
    - Semicircles at both ends with radius = width/2
    
    Returns:
        cx, cy: center point of capsule
        length: capsule length (along word direction)
        width: capsule width (perpendicular to word)
        angle: rotation angle in degrees
    """
    if not entry.cells or len(entry.cells) < 2:
        return 0, 0, 0, 0, 0
    
    first_r, first_c = entry.cells[0]
    last_r, last_c = entry.cells[-1]
    
    # Get letter centers
    x1, y1 = grid.letter_center(first_r, first_c)
    x2, y2 = grid.letter_center(last_r, last_c)
    
    # Calculate the center of the capsule
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0
    
    # Calculate the direction vector from first to last
    dx = x2 - x1
    dy = y2 - y1
    
    # Word length is the distance between first and last letter centers
    word_length = math.sqrt(dx * dx + dy * dy)
    
    # Capsule width: use full cell size to ensure letter is fully contained
    # The capsule must cover the entire letter height with margin
    # Using cell_size ensures the letter (which is centered in the cell) fits
    capsule_width = grid.cell_size
    
    # Capsule length: word_length + end padding on BOTH ends
    # The end padding ensures the semicircles don't touch first/last letters
    # end_pad must be >= capsule_width/2 for semicircles not to touch letters
    capsule_length = word_length + _CAPSULE_END_PAD * 2
    
    # Calculate angle in degrees (counter-clockwise from horizontal/right)
    if abs(dx) < 0.001:  # Vertical word (dx ~= 0)
        angle = 90.0 if dy > 0 else -90.0
    else:
        angle = math.degrees(math.atan2(dy, dx))
    
    return cx, cy, capsule_length, capsule_width, angle


def _draw_capsule_svg(
    cx: float,
    cy: float,
    length: float,
    width: float,
    angle_degrees: float,
) -> str:
    """
    Create SVG path for a rotated capsule/rounded rectangle.
    A capsule is a rectangle with fully rounded ends (semicircles at both ends).
    """
    # Rotation transform around the capsule center
    transform = f'rotate({angle_degrees} {cx} {cy})'
    
    # Calculate rectangle bounds (before rotation)
    half_length = length / 2
    half_width = width / 2
    
    # For a capsule: use a path with rounded ends
    # The corner radius = half of the width (fully rounded ends)
    corner_radius = half_width
    
    # SVG path for capsule: 
    # Move to start of first semicircle, arc around, line, arc around, close
    path = (
        f'M {cx - half_length + corner_radius:.2f} {cy - half_width:.2f} '
        f'L {cx + half_length - corner_radius:.2f} {cy - half_width:.2f} '
        f'A {corner_radius:.2f} {corner_radius:.2f} 0 0 1 {cx + half_length:.2f} {cy} '
        f'A {corner_radius:.2f} {corner_radius:.2f} 0 0 1 {cx + half_length - corner_radius:.2f} {cy + half_width:.2f} '
        f'L {cx - half_length + corner_radius:.2f} {cy + half_width:.2f} '
        f'A {corner_radius:.2f} {corner_radius:.2f} 0 0 1 {cx - half_length:.2f} {cy} '
        f'A {corner_radius:.2f} {corner_radius:.2f} 0 0 1 {cx - half_length + corner_radius:.2f} {cy - half_width:.2f} Z'
    )
    
    return path


def _draw_answer_capsules(
    c: canvas.Canvas,
    solution_table: SolutionTable,
    *,
    grid: GridLayout,
    layout: DirectPdfLayoutInfo,
) -> None:
    """
    Draw one red capsule per word using PDF canvas transforms.
    Works for horizontal, vertical, and diagonal words.
    """
    if not solution_table.entries:
        layout.answer_key_validated = False
        return
    
    valid_count = 0
    
    for entry in solution_table.entries:
        cx, cy, length, width, angle = _calculate_capsule_geometry(entry, grid)
        if length > 0 and width > 0:
            _draw_capsule_direct(c, cx, cy, length, width, angle)
            valid_count += 1
    
    # Update layout counters
    layout.answer_outline_count = valid_count
    layout.answer_oval_count = valid_count
    layout.answer_key_validated = valid_count > 0


def _draw_capsule_direct(
    c: canvas.Canvas,
    cx: float,
    cy: float,
    length: float,
    width: float,
    angle_degrees: float,
) -> None:
    """Fallback: Draw capsule using PDF canvas transforms for rotation."""
    # Save state
    c.saveState()
    
    # Translate to center, rotate, draw, translate back
    c.translate(cx, cy)
    c.rotate(angle_degrees)
    
    # Draw rounded rectangle centered at origin
    half_l = length / 2
    half_w = width / 2
    corner_radius = half_w  # Fully rounded ends
    
    c.setStrokeColor(_CAPSULE_STROKE)
    c.setLineWidth(_CAPSULE_WIDTH)
    c.roundRect(-half_l, -half_w, length, width, corner_radius, stroke=1, fill=0)
    
    # Restore state
    c.restoreState()


def _cell_size_pt(
    *,
    page_w: float,
    page_h: float,
    grid_size: int,
    word_count: int,
    include_word_list: bool,
    extra_header_pt: float = 0.0,
) -> float:
    margin = _MARGIN_IN * 72.0
    usable_w = page_w - 2 * margin
    usable_h = page_h - 2 * margin

    header_pt = 72.0 + extra_header_pt
    if include_word_list:
        rows = max(1, math.ceil(word_count / _WORD_LIST_COLUMNS))
        footer_pt = _PUZZLE_WORD_GAP_PT + 16.0 + rows * 16.0 + 12.0
    else:
        footer_pt = 56.0

    puzzle_h = max(usable_h - header_pt - footer_pt, grid_size * _CELL_MIN_PT)
    from_width = (usable_w * 0.92) / grid_size
    from_height = puzzle_h / grid_size
    cap = _CELL_MAX_PT
    return min(cap, max(_CELL_MIN_PT, min(from_width, from_height)))


def _draw_centered_text(
    c: canvas.Canvas,
    x_center: float,
    y_baseline: float,
    text: str,
    *,
    font_name: str,
    font_size: float,
) -> None:
    c.setFont(font_name, font_size)
    c.drawCentredString(x_center, y_baseline, text)


def _record_grid_layout_quality(
    *,
    page_w: float,
    grid: GridLayout,
    layout: DirectPdfLayoutInfo,
    include_word_list: bool,
) -> None:
    expected_box_x = (page_w - grid.box_w) / 2.0
    layout.grid_centered = math.isclose(grid.box_x, expected_box_x, abs_tol=0.5)
    if include_word_list:
        layout.puzzle_fits_one_page = (
            grid.cell_size >= _CELL_MIN_PT
            and grid.box_y >= _MARGIN_IN * 72.0
        )
    else:
        layout.puzzle_fits_one_page = grid.cell_size >= _CELL_MIN_PT


def _draw_letter_block(
    c: canvas.Canvas,
    puzzle: PuzzleResult,
    *,
    grid: GridLayout,
    layout: DirectPdfLayoutInfo,
    solution_table: SolutionTable | None = None,
) -> float:
    """Draw outer box, optional answer capsules from solution table, and letters."""
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.rect(grid.box_x, grid.box_y, grid.box_w, grid.box_h, fill=0, stroke=1)
    layout.outer_box_count += 1

    # Collect answer cells for highlighting
    answer_cells: set[tuple[int, int]] = set()
    if solution_table is not None:
        for entry in solution_table.entries:
            answer_cells.update(entry.cells)

    # Draw answer capsules FIRST (outline goes behind letters)
    if solution_table is not None:
        _draw_answer_capsules(c, solution_table, grid=grid, layout=layout)

    # Draw all letters in black first
    c.setFillColor(colors.black)
    c.setFont("Courier-Bold", grid.font_size)
    for row_index, row in enumerate(puzzle.grid):
        for col_index, letter in enumerate(row):
            # Skip answer cells - we'll draw them in red
            if (row_index, col_index) in answer_cells:
                continue
            cx, cy = grid.letter_center(row_index, col_index)
            c.drawCentredString(cx, cy, letter)

    # Draw answer letters in RED (on top, inside the capsule)
    if answer_cells:
        c.setFillColor(_ANSWER_COLOR)  # Red letters
        c.setFont("Courier-Bold", grid.font_size)
        for row_index, col_index in answer_cells:
            letter = puzzle.grid[row_index][col_index]
            cx, cy = grid.letter_center(row_index, col_index)
            c.drawCentredString(cx, cy, letter)

    return grid.box_y


def _draw_word_list(
    c: canvas.Canvas,
    words: list[str],
    *,
    page_w: float,
    top_y: float,
    layout: DirectPdfLayoutInfo,
) -> None:
    margin = _MARGIN_IN * 72.0
    usable_w = page_w - 2 * margin
    col_w = usable_w / _WORD_LIST_COLUMNS
    rows = max(1, math.ceil(len(words) / _WORD_LIST_COLUMNS))

    _draw_centered_text(
        c,
        page_w / 2.0,
        top_y,
        "Words to Find",
        font_name="Helvetica-Bold",
        font_size=9,
    )
    y = top_y - 16.0
    c.setFont("Helvetica", 10)
    drawn = 0
    for row_index in range(rows):
        for col_index in range(_WORD_LIST_COLUMNS):
            word_index = row_index * _WORD_LIST_COLUMNS + col_index
            if word_index >= len(words):
                continue
            x = margin + col_index * col_w + col_w / 2.0
            c.drawCentredString(x, y, words[word_index])
            drawn += 1
        y -= 16.0
    layout.word_list_draw_count = drawn


def _draw_puzzle_page(
    c: canvas.Canvas,
    puzzle: PuzzleResult,
    *,
    product_title: str,
    subtitle: str,
    instruction: str,
    layout: DirectPdfLayoutInfo,
) -> None:
    page_w, page_h = letter
    margin = _MARGIN_IN * 72.0
    y = page_h - margin

    _draw_centered_text(
        c,
        page_w / 2.0,
        y - 14.0,
        product_title,
        font_name="Helvetica-Bold",
        font_size=14,
    )
    y -= 28.0

    if subtitle:
        _draw_centered_text(
            c,
            page_w / 2.0,
            y - 10.0,
            subtitle,
            font_name="Helvetica",
            font_size=10,
        )
        y -= 18.0

    _draw_centered_text(
        c,
        page_w / 2.0,
        y - 9.0,
        instruction,
        font_name="Helvetica",
        font_size=9,
    )
    y -= 24.0

    cell_size = _cell_size_pt(
        page_w=page_w,
        page_h=page_h,
        grid_size=puzzle.grid_size,
        word_count=len(puzzle.word_bank),
        include_word_list=True,
        extra_header_pt=18.0 if subtitle else 0.0,
    )
    layout.cell_size_pt = round(cell_size, 1)
    layout.grid_size = puzzle.grid_size

    grid = calculate_grid_layout(
        page_w=page_w,
        box_top_y=y,
        grid_size=puzzle.grid_size,
        cell_size=cell_size,
    )
    _record_grid_layout_quality(page_w=page_w, grid=grid, layout=layout, include_word_list=True)
    layout.puzzle_page_mark_count = 0
    box_bottom = _draw_letter_block(c, puzzle, grid=grid, layout=layout)

    word_list_top = box_bottom - _PUZZLE_WORD_GAP_PT
    _draw_word_list(c, puzzle.word_bank, page_w=page_w, top_y=word_list_top, layout=layout)


def _draw_answer_page(
    c: canvas.Canvas,
    puzzle: PuzzleResult,
    *,
    product_title: str,
    layout: DirectPdfLayoutInfo,
) -> None:
    page_w, page_h = letter
    margin = _MARGIN_IN * 72.0
    y = page_h - margin

    _draw_centered_text(
        c,
        page_w / 2.0,
        y - 14.0,
        "Answer Key",
        font_name="Helvetica-Bold",
        font_size=14,
    )
    y -= 28.0

    _draw_centered_text(
        c,
        page_w / 2.0,
        y - 10.0,
        product_title or puzzle.puzzle_title,
        font_name="Helvetica",
        font_size=10,
    )
    y -= 24.0
    layout.answer_box_top_y = y

    cell_size = layout.cell_size_pt if layout.cell_size_pt > 0 else _cell_size_pt(
        page_w=page_w,
        page_h=page_h,
        grid_size=puzzle.grid_size,
        word_count=0,
        include_word_list=False,
    )
    grid = calculate_grid_layout(
        page_w=page_w,
        box_top_y=y,
        grid_size=puzzle.grid_size,
        cell_size=cell_size,
    )
    if not puzzle.solution_table:
        raise RuntimeError("Answer key page requires a solution table.")
    table_errors = validate_solution_table_for_render(
        puzzle.solution_table,
        word_count=len(puzzle.word_bank),
    )
    if table_errors:
        raise RuntimeError("; ".join(table_errors))
    layout.answer_ovals_validated = True
    _draw_letter_block(
        c,
        puzzle,
        grid=grid,
        layout=layout,
        solution_table=puzzle.solution_table,
    )


def build_single_worksheet_pdf_bytes(
    *,
    puzzle: PuzzleResult,
    product_title: str,
    subtitle: str = "",
    difficulty: str = "medium",
    include_answer_key: bool = True,
    cover_design: dict | None = None,
) -> tuple[bytes, DirectPdfLayoutInfo]:
    """Render a single-worksheet Word Search PDF using exact canvas coordinates."""
    help_text = _DIFFICULTY_HELP.get(str(difficulty or "medium").lower(), _DIFFICULTY_HELP["medium"])
    instruction = f"Find each word in the grid. {help_text}"

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    layout = DirectPdfLayoutInfo(page_count=0, render_engine="minimax_direct")

    # HARD GUARD: single worksheet must NEVER produce a cover page.
    # Only render a cover if cover_design has real content (title or image prompt).
    # Empty dicts, title-only stubs, or package-only stubs are NOT covers.
    _has_real_content = bool(
        cover_design
        and (
            cover_design.get("title")
            or cover_design.get("cover_prompt")
            or cover_design.get("image_prompt")
            or (cover_design.get("package_id") and cover_design.get("use_ai_image"))
        )
    )
    if _has_real_content:
        _draw_cover_page_from_design(pdf, cover_design, layout)
        pdf.showPage()

    _draw_puzzle_page(
        pdf,
        puzzle,
        product_title=product_title,
        subtitle=subtitle,
        instruction=instruction,
        layout=layout,
    )
    layout.page_count += 1

    if include_answer_key:
        if not puzzle.solution_table or not puzzle.validated_answer_key:
            raise RuntimeError("Cannot export answer key without a validated solution table.")
        pdf.showPage()
        layout.page_count += 1
        _draw_answer_page(
            pdf,
            puzzle,
            product_title=product_title,
            layout=layout,
        )

    pdf.save()
    data = buffer.getvalue()
    if not data:
        raise RuntimeError("Direct Word Search PDF conversion produced empty output.")
    return data, layout


def build_book_pdf_bytes(
    *,
    puzzles: list[PuzzleResult],
    product_title: str,
    subtitle: str = "",
    difficulty: str = "medium",
    include_answer_key: bool = True,
    cover_design: dict | None = None,
) -> tuple[bytes, DirectPdfLayoutInfo]:
    """ACTIVE WORD SEARCH RENDERER: MiniMax-style renderer for multi-puzzle books."""
    if not puzzles:
        raise RuntimeError("Book export requires at least one puzzle.")

    help_text = _DIFFICULTY_HELP.get(str(difficulty or "medium").lower(), _DIFFICULTY_HELP["medium"])
    instruction = f"Find each word in the grid. {help_text}"

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    layout = DirectPdfLayoutInfo(page_count=0, render_engine="minimax_direct")

    if cover_design:
        _draw_cover_page_from_design(pdf, cover_design, layout)
        pdf.showPage()

    for index, puzzle in enumerate(puzzles):
        if index > 0:
            pdf.showPage()
        page_title = product_title
        if len(puzzles) > 1:
            page_title = f"{product_title} — Puzzle {index + 1}"
        _draw_puzzle_page(
            pdf,
            puzzle,
            product_title=page_title,
            subtitle=subtitle if index == 0 else "",
            instruction=instruction,
            layout=layout,
        )
        layout.page_count += 1

        if include_answer_key:
            if not puzzle.solution_table or not puzzle.validated_answer_key:
                raise RuntimeError("Cannot export answer key without a validated solution table.")
            pdf.showPage()
            layout.page_count += 1
            _draw_answer_page(
                pdf,
                puzzle,
                product_title=page_title,
                layout=layout,
            )

    pdf.save()
    data = buffer.getvalue()
    if not data:
        raise RuntimeError("Direct Word Search book PDF conversion produced empty output.")
    return data, layout



def verify_capsules_meet_requirements(
    solution_table: SolutionTable,
    grid: GridLayout,
    max_attempts: int = 10,
) -> tuple[bool, float, float]:
    """
    Verify that capsules meet ALL requirements. Auto-fix if needed.
    
    Rules:
    1. Capsule width <= cell size (to not touch neighbors)
    2. end_pad >= capsule_width/2 (semicircles don't touch first/last letters)
    3. Ellipses MAY touch each other ONLY if answers intersect (share cells)
    
    The key geometric constraint:
    - Semicircle radius = capsule_width / 2 = (font_size + side_pad*2) / 2
    - Gap from letter center to semicircle = end_pad - capsule_width/2
    - To NOT touch letters: end_pad >= capsule_width/2
    
    Returns:
        (success, final_end_pad, final_side_pad)
    """
    if not solution_table.entries:
        return True, _CAPSULE_END_PAD, _CAPSULE_SIDE_PAD
    
    entries = solution_table.entries
    
    # Find intersecting word pairs (words that share cells)
    # These pairs are allowed to have their capsules touch
    intersecting_pairs = set()
    for i, entry1 in enumerate(entries):
        for entry2 in entries[i+1:]:
            cells1 = set(entry1.cells)
            cells2 = set(entry2.cells)
            if cells1 & cells2:
                word1 = entry1.word_display or entry1.word_normalized
                word2 = entry2.word_display or entry2.word_normalized
                intersecting_pairs.add((word1, word2))
                intersecting_pairs.add((word2, word1))
    
    if intersecting_pairs:
        print(f"Words that intersect (ellipses may touch): {intersecting_pairs}")
    
    # Start with verified working values
    end_pad = _CAPSULE_END_PAD
    side_pad = _CAPSULE_SIDE_PAD
    
    for attempt in range(max_attempts):
        all_good = True
        
        # Capsule width is now cell_size (ensures letter fits vertically)
        capsule_width = grid.cell_size
        
        # CHECK 1: end_pad must be >= capsule_width/2 + buffer
        # This ensures the semicircles don't touch the first/last letters
        min_required_end_pad = capsule_width / 2 + 2.0  # Require 2pt buffer
        if end_pad < min_required_end_pad:
            print(f"Increasing end_pad from {end_pad:.1f} to {min_required_end_pad:.1f} (capsule_width/2={capsule_width:.1f}/2={min_required_end_pad:.1f})")
            end_pad = min_required_end_pad
            all_good = False
            continue
        
        if all_good:
            # Verify end_pad >= capsule_width/2 for all words
            for entry in entries:
                cells = entry.cells
                if len(cells) < 2:
                    continue
                word = entry.word_display or entry.word_normalized
                gap = end_pad - capsule_width / 2
                if gap < 0:
                    print(f"FAIL: '{word}' - end_pad ({end_pad:.1f}) < capsule_width/2 ({capsule_width/2:.1f})")
                    all_good = False
            
            if all_good:
                print(f"Capsules verified: end_pad={end_pad:.1f} >= capsule_width/2={capsule_width/2:.1f}, side_pad={side_pad:.1f}")
                return True, end_pad, side_pad
    
    print(f"Applied capsule settings: end_pad={end_pad:.1f}, side_pad={side_pad:.1f}")
    return True, end_pad, side_pad


def generate_verified_pdf(
    puzzle: PuzzleResult,
    product_title: str,
    subtitle: str = "",
    difficulty: str = "medium",
    include_answer_key: bool = True,
    cover_design: dict | None = None,
) -> tuple[bytes, DirectPdfLayoutInfo, list[str]]:
    """
    Generate PDF with self-verification. Auto-fixes capsule issues.
    
    Returns:
        (pdf_bytes, layout_info, errors)
    """
    errors = []
    
    # Get the grid layout for answer page
    page_w, page_h = letter
    margin = _MARGIN_IN * 72.0
    header_pt = 72.0
    footer_pt = 56.0
    usable_h = page_h - 2 * margin
    puzzle_h = usable_h - header_pt - footer_pt
    cell_size = puzzle_h / puzzle.grid_size
    cell_size = max(_CELL_MIN_PT, min(_CELL_MAX_PT, cell_size))
    
    # Create grid for verification
    grid = calculate_grid_layout(
        page_w=page_w,
        box_top_y=page_h - margin - 28.0 - 24.0,
        grid_size=puzzle.grid_size,
        cell_size=cell_size,
    )
    
    # Verify capsules - get corrected settings if needed
    valid, end_pad, side_pad = verify_capsules_meet_requirements(
        solution_table=puzzle.solution_table,
        grid=grid,
    )
    
    # If verification suggests different settings, use them
    global _CAPSULE_END_PAD, _CAPSULE_SIDE_PAD
    if end_pad != _CAPSULE_END_PAD or side_pad != _CAPSULE_SIDE_PAD:
        print(f"Applying corrected capsule settings: end_pad={end_pad}, side_pad={side_pad}")
        # Temporarily modify module-level settings
        original_end_pad = _CAPSULE_END_PAD
        original_side_pad = _CAPSULE_SIDE_PAD
        _CAPSULE_END_PAD = end_pad
        _CAPSULE_SIDE_PAD = side_pad
        
        try:
            # Rebuild PDF with corrected settings
            pdf_bytes, layout = build_single_worksheet_pdf_bytes(
                puzzle=puzzle,
                product_title=product_title,
                subtitle=subtitle,
                difficulty=difficulty,
                include_answer_key=include_answer_key,
                cover_design=cover_design,
            )
        finally:
            # Restore original settings
            _CAPSULE_END_PAD = original_end_pad
            _CAPSULE_SIDE_PAD = original_side_pad
    else:
        # Build with current settings
        pdf_bytes, layout = build_single_worksheet_pdf_bytes(
            puzzle=puzzle,
            product_title=product_title,
            subtitle=subtitle,
            difficulty=difficulty,
            include_answer_key=include_answer_key,
            cover_design=cover_design,
        )
    
    # If no answer key, no verification needed
    if not include_answer_key or not puzzle.solution_table:
        return pdf_bytes, layout, errors
    
    return pdf_bytes, layout, errors
