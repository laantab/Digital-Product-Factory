"""PDF renderer for Math Worksheet — ReportLab-based layout."""
from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services.math_worksheet.builder import MathProblem, MathWorksheetResult
from services.math_worksheet.pdf_fonts import ascii_pdf_text, ensure_math_fonts
from services.math_worksheet.themes import MathWorksheetTheme, resolve_math_worksheet_theme

_MARGIN = 0.5 * 72.0  # 0.5 inch
_HEADER_H = 60  # space for title block
_PROBLEM_H = 36  # space per problem row
_COLS = 2  # two-column problem layout
_INSTRUCTION = (
    "Solve each problem. Show your work. Write your final answer in the answer blank."
)


@dataclass
class MathWorksheetLayoutInfo:
    render_engine: str = "math_worksheet_direct"
    worksheet_pages: int = 0
    answer_key_pages: int = 0
    cover_page_count: int = 0


def _fonts() -> tuple[str, str, str]:
    return ensure_math_fonts()


def _format_grade_display(grade: str) -> str:
    """Ensure header shows 'Grade 6', never 'Grade Grade 6'."""
    raw = str(grade or "").strip()
    if not raw:
        return ""
    stripped = re.sub(r"(?i)^grades?\s*", "", raw).strip()
    return f"Grade {stripped}" if stripped else ""


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
    """Whole-string draw with character/word spacing cleared."""
    safe = ascii_pdf_text(text)
    pdf.saveState()
    try:
        pdf.setFillColor(fill if fill is not None else colors.black)
        pdf.setFont(font_name, font_size)
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


def _draw_page_counter(
    pdf: canvas.Canvas,
    page_w: float,
    page_h: float,
    label: str,
    *,
    font_bold: str,
    heading: str,
    heading_font: str,
    heading_size: float,
    heading_baseline: float,
) -> None:
    """v1.9.13. "Page N of M" in the Factory page-number standard.

    Same place as before (top right, inside the margin), now 10 pt bold
    near-black instead of 8 pt light grey. A long centred heading can reach the
    right-hand side; when it would, the counter moves up just far enough to
    clear the heading's tallest letters, so the two can never overlap.
    """
    from reportlab.pdfbase.pdfmetrics import getAscent, getDescent

    from services.page_number_style import PAGE_NUMBER_SIZE_PT, PAGE_NUMBER_INK

    size = PAGE_NUMBER_SIZE_PT
    safe = ascii_pdf_text(label)
    right = page_w - _MARGIN
    left = right - pdf.stringWidth(safe, font_bold, size)
    baseline = page_h - _MARGIN - 8
    head = ascii_pdf_text(heading)
    head_w = pdf.stringWidth(head, heading_font, heading_size)
    head_right = page_w / 2.0 + head_w / 2.0
    if head_right > left - 6:
        head_top = heading_baseline + getAscent(heading_font, heading_size)
        # getDescent is negative: the counter's lowest point sits above the heading.
        baseline = max(baseline, head_top + 1.5 - getDescent(font_bold, size))
    _draw_text(
        pdf, right, baseline, label,
        font_name=font_bold, font_size=size, align="right",
        fill=colors.HexColor(PAGE_NUMBER_INK),
    )


def _draw_header(
    pdf: canvas.Canvas,
    title: str,
    subtitle: str,
    grade: str,
    topic: str,
    difficulty: str,
    page_num: int,
    total_pages: int,
    theme: MathWorksheetTheme | None = None,
) -> float:
    """Draw worksheet header once and return the y position below it."""
    page_w, page_h = letter
    theme = theme or resolve_math_worksheet_theme("classic_classroom")
    font, font_bold, font_italic = theme.regular_font, theme.bold_font, theme.italic_font

    _draw_text(
        pdf, page_w / 2.0, page_h - _MARGIN - 18, title[:80],
        font_name=font_bold, font_size=theme.heading_font_size, align="center",
    )

    meta_parts = []
    grade_label = _format_grade_display(grade)
    if grade_label:
        meta_parts.append(grade_label)
    if topic:
        meta_parts.append(str(topic))
    if difficulty:
        meta_parts.append(str(difficulty))
    meta = "  |  ".join(meta_parts)
    _draw_text(
        pdf, page_w / 2.0, page_h - _MARGIN - 32, meta,
        font_name=font, font_size=9, align="center",
        fill=colors.HexColor(theme.muted),
    )

    pdf.setStrokeColor(colors.HexColor(theme.rule))
    pdf.setLineWidth(0.75 if theme.key != "classic_classroom" else 0.5)
    y_line = page_h - _MARGIN - 42
    pdf.line(_MARGIN, y_line, page_w - _MARGIN, y_line)
    if theme.key != "classic_classroom":
        pdf.setStrokeColor(colors.HexColor(theme.accent))
        pdf.setLineWidth(2.0)
        pdf.line(_MARGIN, y_line, _MARGIN + 46, y_line)

    _draw_page_counter(
        pdf, page_w, page_h, f"Page {page_num} of {total_pages}",
        font_bold=font_bold, heading=title[:80], heading_font=font_bold,
        heading_size=theme.heading_font_size, heading_baseline=page_h - _MARGIN - 18,
    )

    # Single instruction line — never redrawn elsewhere on this page.
    _draw_text(
        pdf, _MARGIN, y_line - 14, _INSTRUCTION,
        font_name=font_italic, font_size=9,
        fill=colors.HexColor(theme.ink),
    )

    return y_line - 30


def _draw_problem_grid(
    pdf: canvas.Canvas,
    problems: list[MathProblem],
    *,
    left_x: float,
    right_x: float,
    top_y: float,
    bottom_y: float,
    theme: MathWorksheetTheme | None = None,
) -> float:
    """Draw problems in two columns. Returns the y after the last problem."""
    theme = theme or resolve_math_worksheet_theme("classic_classroom")
    font, font_bold = theme.regular_font, theme.bold_font
    col_width = (right_x - left_x) / _COLS
    row_h = theme.problem_row_height

    y = top_y
    for i, problem in enumerate(problems):
        col = i % _COLS
        row = i // _COLS
        x = left_x + col * col_width
        y = top_y - row * row_h

        if y - row_h < bottom_y:
            break

        if row % 2 == 0:
            pdf.setFillColor(colors.HexColor(theme.row_fill))
            pdf.rect(x, y - row_h + 2, col_width - 4, row_h - 4, fill=1, stroke=0)

        _draw_text(
            pdf, x + 2, y - 12, f"{problem.number}.",
            font_name=font_bold, font_size=theme.problem_font_size - 2,
            fill=colors.HexColor(theme.ink),
        )
        _draw_text(
            pdf, x + 22, y - 12, problem.expression[:30],
            font_name=font, font_size=theme.problem_font_size,
        )

        pdf.setStrokeColor(colors.HexColor(theme.rule if theme.key != "classic_classroom" else "#9CA3AF"))
        pdf.setLineWidth(0.5)
        pdf.line(x + 22, y - 16, x + col_width - 8, y - 16)

    return y - row_h


def _draw_answer_key_page(
    pdf: canvas.Canvas,
    problems: list[MathProblem],
    title: str,
    *,
    page_num: int = 1,
    total_pages: int = 1,
    section_label: str = "Main",
    theme: MathWorksheetTheme | None = None,
) -> None:
    """Draw one answer key page with two clearly separated columns."""
    page_w, page_h = letter
    theme = theme or resolve_math_worksheet_theme("classic_classroom")
    font, font_bold = theme.regular_font, theme.bold_font

    _paint_white(pdf)

    section_suffix = f" - {section_label} Section" if section_label and section_label != "Main" else ""
    heading = f"Answer Key{section_suffix} - {title[:60]}"
    _draw_text(
        pdf, page_w / 2.0, page_h - _MARGIN - 16, heading,
        font_name=font_bold, font_size=14, align="center",
    )

    pdf.setStrokeColor(colors.HexColor(theme.rule))
    pdf.setLineWidth(0.75 if theme.key != "classic_classroom" else 0.5)
    pdf.line(_MARGIN, page_h - _MARGIN - 26, page_w - _MARGIN, page_h - _MARGIN - 26)

    _draw_page_counter(
        pdf, page_w, page_h, f"Page {page_num} of {total_pages}",
        font_bold=font_bold, heading=heading, heading_font=font_bold,
        heading_size=14, heading_baseline=page_h - _MARGIN - 16,
    )

    # Two independent columns with equal gutters and per-column headers.
    col_gap = 18.0
    usable_w = page_w - (2 * _MARGIN) - col_gap
    col_w = usable_w / 2.0
    top_y = page_h - _MARGIN - 40
    row_h = 16.0
    num_w = 22.0
    ans_w = 48.0
    expr_x_off = num_w + 4.0
    ans_x_off = col_w - ans_w

    for col_idx in range(2):
        x0 = _MARGIN + col_idx * (col_w + col_gap)
        _draw_text(
            pdf, x0, top_y, "#",
            font_name=font_bold, font_size=9,
            fill=colors.HexColor(theme.accent),
        )
        _draw_text(
            pdf, x0 + expr_x_off, top_y, "Problem",
            font_name=font_bold, font_size=9,
            fill=colors.HexColor(theme.ink),
        )
        _draw_text(
            pdf, x0 + ans_x_off, top_y, "Answer",
            font_name=font_bold, font_size=9,
            fill=colors.HexColor(theme.accent),
        )

    pdf.setStrokeColor(colors.HexColor(theme.rule))
    pdf.line(_MARGIN, top_y - 4, page_w - _MARGIN, top_y - 4)

    y_base = top_y - 18
    for i, problem in enumerate(problems):
        col = i % 2
        row = i // 2
        x0 = _MARGIN + col * (col_w + col_gap)
        y = y_base - row * row_h

        if y < _MARGIN + 12:
            break

        _draw_text(
            pdf, x0, y, f"{problem.number}.",
            font_name=font, font_size=8,
        )
        expr_max = max(8, int((ans_x_off - expr_x_off - 6) / 4.2))
        _draw_text(
            pdf, x0 + expr_x_off, y, problem.expression[:expr_max],
            font_name=font, font_size=8,
        )
        _draw_text(
            pdf, x0 + ans_x_off, y, str(problem.answer)[:12],
            font_name=font_bold, font_size=8,
            fill=colors.HexColor(theme.secondary),
        )


def _paint_white(pdf: canvas.Canvas) -> None:
    page_w, page_h = letter
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)


def build_math_worksheet_pdf_bytes(
    result: MathWorksheetResult,
    *,
    include_answer_key: bool = True,
    include_cover: bool = False,
    cover_image_path: str = "",
    design_theme: str = "classic_classroom",
) -> tuple[bytes, MathWorksheetLayoutInfo]:
    """Render a math worksheet PDF from MathWorksheetResult.

    include_cover: Math Worksheet has no AI-image cover pipeline (unlike
    Crossword/Word Search's generate_cover_from_payload) -- when True and no
    cover_image_path is available (the normal case: zero-cost generation
    never calls a paid image API), a plain text-only cover page is drawn
    instead, reusing the same _paint_white + _draw_text primitives already
    used for the image-failure fallback below. Previously this parameter
    did not exist at all: only a truthy cover_image_path (which nothing
    ever set) could produce a cover, so Include Cover was a no-op for every
    Math Worksheet regardless of selection. See MATH_WORKSHEET_COVER_
    SELECTION_LOCKED_STATE.md.
    """
    ensure_math_fonts()
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    layout = MathWorksheetLayoutInfo()
    page_w, page_h = letter
    font, font_bold, _font_italic = _fonts()
    theme = resolve_math_worksheet_theme(design_theme)
    font, font_bold, _font_italic = theme.regular_font, theme.bold_font, theme.italic_font

    # Cover page
    if include_cover:
        if cover_image_path and os.path.isfile(cover_image_path):
            try:
                pdf.drawImage(cover_image_path, 0, 0, width=page_w, height=page_h, preserveAspectRatio=False)
            except Exception:  # noqa: BLE001
                _paint_white(pdf)
                _draw_text(
                    pdf, page_w / 2.0, page_h / 2.0 + 20, result.title[:80],
                    font_name=font_bold, font_size=20, align="center",
                )
        else:
            _paint_white(pdf)
            if theme.key != "classic_classroom":
                pdf.setFillColor(colors.HexColor(theme.cover_fill))
                pdf.rect(0, page_h * 0.52, page_w, page_h * 0.20, fill=1, stroke=0)
                pdf.setFillColor(colors.HexColor(theme.accent))
                pdf.rect(0, page_h * 0.52, 8, page_h * 0.20, fill=1, stroke=0)
            _draw_text(
                pdf, page_w / 2.0, page_h / 2.0 + 20, result.title[:80],
                font_name=font_bold, font_size=20, align="center",
            )
            cover_meta = "  |  ".join(
                p for p in (_format_grade_display(result.grade), str(result.math_topic or "")) if p
            )
            if cover_meta:
                _draw_text(
                    pdf, page_w / 2.0, page_h / 2.0 - 10, cover_meta,
                    font_name=font, font_size=13, align="center",
                    fill=colors.HexColor("#4B5563"),
                )
        layout.cover_page_count = 1
        pdf.showPage()

    PROBLEMS_PER_PAGE = 20
    problems_per_page = min(PROBLEMS_PER_PAGE, max(1, len(result.problems)))
    ws_page_count = max(1, (len(result.problems) + problems_per_page - 1) // problems_per_page)

    has_challenge = bool(result.challenge_problems)
    challenge_page_count = 1 if has_challenge else 0

    answers_per_page = 40
    ak_page_count = 0
    if include_answer_key and result.problems:
        ak_page_count = max(1, (len(result.problems) + answers_per_page - 1) // answers_per_page)

    challenge_ak_count = 1 if (include_answer_key and has_challenge) else 0
    total_ws_pages = ws_page_count + challenge_page_count
    total_pages = total_ws_pages + ak_page_count + challenge_ak_count

    problems = result.problems
    problems_left = len(problems)

    for page_idx in range(ws_page_count):
        _paint_white(pdf)
        page_num = page_idx + 1
        top_y = _draw_header(
            pdf,
            result.title,
            result.subtitle,
            result.grade,
            result.math_topic,
            result.difficulty,
            page_num,
            total_pages,
            theme,
        )

        left_x = _MARGIN
        right_x = page_w - _MARGIN
        bottom_y = _MARGIN + 30

        on_this_page = min(problems_per_page, problems_left)
        page_problems = problems[page_idx * problems_per_page: page_idx * problems_per_page + on_this_page]
        problems_left -= on_this_page

        _draw_problem_grid(
            pdf, page_problems,
            left_x=left_x, right_x=right_x,
            top_y=top_y, bottom_y=bottom_y,
            theme=theme,
        )

        layout.worksheet_pages += 1
        pdf.showPage()

    if has_challenge:
        _paint_white(pdf)
        top_y = _draw_header(
            pdf,
            f"{result.title} - Challenge",
            "Bonus problems for advanced learners",
            result.grade, result.math_topic, result.difficulty,
            ws_page_count + 1, total_pages,
            theme,
        )
        _draw_problem_grid(
            pdf, result.challenge_problems,
            left_x=_MARGIN, right_x=page_w - _MARGIN,
            top_y=top_y, bottom_y=_MARGIN + 30,
            theme=theme,
        )
        layout.worksheet_pages += 1
        pdf.showPage()

    if include_answer_key and result.problems:
        main_answers = list(result.problems)
        challenge_answers = list(result.challenge_problems) if result.challenge_problems else []

        for ak_page_idx in range(ak_page_count):
            page_num = total_ws_pages + ak_page_idx + 1
            _draw_answer_key_page(
                pdf,
                main_answers[ak_page_idx * answers_per_page: (ak_page_idx + 1) * answers_per_page],
                result.title,
                page_num=page_num,
                total_pages=total_pages,
                section_label="Main",
                theme=theme,
            )
            layout.answer_key_pages += 1
            pdf.showPage()

        if challenge_answers:
            page_num = total_ws_pages + ak_page_count + 1
            _draw_answer_key_page(
                pdf,
                challenge_answers,
                result.title,
                page_num=page_num,
                total_pages=total_pages,
                section_label="Challenge",
                theme=theme,
            )
            layout.answer_key_pages += 1
            pdf.showPage()

    pdf.save()
    return buffer.getvalue(), layout


def save_math_worksheet_pdf(
    result: MathWorksheetResult,
    output_dir: str,
    filename: str = "math_worksheet.pdf",
    *,
    design_theme: str = "classic_classroom",
) -> tuple[bytes, MathWorksheetLayoutInfo]:
    pdf_bytes, layout = build_math_worksheet_pdf_bytes(result, design_theme=design_theme)
    path = os.path.join(output_dir, filename)
    os.makedirs(os.path.dirname(path) or output_dir, exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)
    return pdf_bytes, layout
