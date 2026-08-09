"""PDF renderer for Math Worksheet — ReportLab-based layout."""
from __future__ import annotations

import io
import os
from dataclasses import dataclass

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services.math_worksheet.builder import MathProblem, MathWorksheetResult

_MARGIN = 0.5 * 72.0  # 0.5 inch
_HEADER_H = 60  # space for title block
_ANSWER_LINE_H = 24
_PROBLEM_H = 36  # space per problem row
_COLS = 2  # two-column problem layout


@dataclass
class MathWorksheetLayoutInfo:
    render_engine: str = "math_worksheet_direct"
    worksheet_pages: int = 0
    answer_key_pages: int = 0
    cover_page_count: int = 0


def _draw_header(
    pdf: canvas.Canvas,
    title: str,
    subtitle: str,
    grade: str,
    topic: str,
    difficulty: str,
    page_num: int,
    total_pages: int,
) -> float:
    """Draw worksheet header and return the y position below the header."""
    page_w, page_h = letter

    # Title
    pdf.setFont("Helvetica-Bold", 16)
    pdf.setFillColor(colors.black)
    pdf.drawCentredString(page_w / 2.0, page_h - _MARGIN - 18, title[:80])

    # Metadata line
    meta_parts = []
    if grade:
        meta_parts.append(f"Grade {grade}")
    if topic:
        meta_parts.append(topic)
    if difficulty:
        meta_parts.append(difficulty)
    meta = "  |  ".join(meta_parts)
    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(colors.HexColor("#4B5563"))
    pdf.drawCentredString(page_w / 2.0, page_h - _MARGIN - 32, meta)

    # Divider line
    pdf.setStrokeColor(colors.HexColor("#D1D5DB"))
    pdf.setLineWidth(0.5)
    y_line = page_h - _MARGIN - 42
    pdf.line(_MARGIN, y_line, page_w - _MARGIN, y_line)

    # Page number
    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(colors.HexColor("#9CA3AF"))
    pdf.drawRightString(page_w - _MARGIN, page_h - _MARGIN - 8, f"Page {page_num} of {total_pages}")

    # Instructions
    pdf.setFont("Helvetica-Oblique", 9)
    pdf.setFillColor(colors.HexColor("#374151"))
    pdf.drawString(_MARGIN, y_line - 14, f"Solve each problem. Show your work. Write your final answer in the answer blank.")

    return y_line - 30  # return top_y for problem area


def _draw_problem_grid(
    pdf: canvas.Canvas,
    problems: list[MathProblem],
    *,
    left_x: float,
    right_x: float,
    top_y: float,
    bottom_y: float,
) -> float:
    """Draw problems in two columns. Returns the y after the last problem."""
    col_width = (right_x - left_x) / _COLS
    row_h = _PROBLEM_H

    y = top_y
    for i, problem in enumerate(problems):
        col = i % _COLS
        row = i // _COLS
        x = left_x + col * col_width
        y = top_y - row * row_h

        if y - row_h < bottom_y:
            break  # ran out of space

        # Row background (alternating)
        if row % 2 == 0:
            pdf.setFillColor(colors.HexColor("#F9FAFB"))
            pdf.rect(x, y - row_h + 2, col_width - 4, row_h - 4, fill=1, stroke=0)

        # Problem number
        pdf.setFont("Helvetica-Bold", 9)
        pdf.setFillColor(colors.HexColor("#374151"))
        num_text = f"{problem.number}."
        pdf.drawString(x + 2, y - 12, num_text)

        # Expression
        pdf.setFont("Helvetica", 11)
        pdf.setFillColor(colors.black)
        # Fit expression to column width
        expr = problem.expression[:30]
        pdf.drawString(x + 22, y - 12, expr)

        # Answer blank line
        pdf.setStrokeColor(colors.HexColor("#9CA3AF"))
        pdf.setLineWidth(0.5)
        pdf.line(x + 22, y - 16, x + col_width - 8, y - 16)

        # Answer (only in key pages)
        # (Answers shown in answer key section)

    return y - row_h


def _draw_answer_key_page(
    pdf: canvas.Canvas,
    problems: list[MathProblem],
    title: str,
    *,
    page_num: int = 1,
    total_pages: int = 1,
    section_label: str = "Main",
) -> None:
    """Draw one answer key page."""
    page_w, page_h = letter

    _paint_white(pdf)

    # Header
    section_suffix = f" — {section_label} Section" if section_label and section_label != "Main" else ""
    pdf.setFont("Helvetica-Bold", 14)
    pdf.setFillColor(colors.black)
    pdf.drawCentredString(page_w / 2.0, page_h - _MARGIN - 16, f"Answer Key{section_suffix} — {title[:60]}")

    pdf.setStrokeColor(colors.HexColor("#D1D5DB"))
    pdf.setLineWidth(0.5)
    pdf.line(_MARGIN, page_h - _MARGIN - 26, page_w - _MARGIN, page_h - _MARGIN - 26)

    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(colors.HexColor("#9CA3AF"))
    pdf.drawRightString(page_w - _MARGIN, page_h - _MARGIN - 8, f"Page {page_num} of {total_pages}")

    # Answer table header
    top_y = page_h - _MARGIN - 36
    pdf.setFont("Helvetica-Bold", 9)
    pdf.setFillColor(colors.HexColor("#374151"))
    pdf.drawString(_MARGIN, top_y, "#")
    pdf.drawString(_MARGIN + 30, top_y, "Problem")
    pdf.drawString(_MARGIN + 260, top_y, "Answer")

    pdf.setStrokeColor(colors.HexColor("#D1D5DB"))
    pdf.line(_MARGIN, top_y - 2, page_w - _MARGIN, top_y - 2)

    # Answers in 2-column table
    col_w = (page_w - 2 * _MARGIN) / 2.0
    y = top_y - 16
    row_h = 14
    for i, problem in enumerate(problems):
        col = i % 2
        row = i // 2
        x = _MARGIN + col * col_w
        y = top_y - 16 - row * row_h

        if y - row_h < _MARGIN + 10:
            break

        pdf.setFont("Helvetica", 8)
        pdf.setFillColor(colors.black)
        pdf.drawString(x, y, f"{problem.number}.")
        pdf.drawString(x + 20, y, problem.expression[:28])
        pdf.setFont("Helvetica-Bold", 8)
        pdf.setFillColor(colors.HexColor("#059669"))
        pdf.drawString(x + 230, y, str(problem.answer)[:12])


def _paint_white(pdf: canvas.Canvas) -> None:
    page_w, page_h = letter
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)


def build_math_worksheet_pdf_bytes(
    result: MathWorksheetResult,
    *,
    include_answer_key: bool = True,
    cover_image_path: str = "",
) -> tuple[bytes, MathWorksheetLayoutInfo]:
    """Render a math worksheet PDF from MathWorksheetResult."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    layout = MathWorksheetLayoutInfo()
    page_w, page_h = letter

    # Cover page
    if cover_image_path and os.path.isfile(cover_image_path):
        try:
            pdf.drawImage(cover_image_path, 0, 0, width=page_w, height=page_h, preserveAspectRatio=False)
        except Exception:  # noqa: BLE001
            _paint_white(pdf)
            pdf.setFont("Helvetica-Bold", 20)
            pdf.drawCentredString(page_w / 2.0, page_h / 2.0 + 20, result.title[:80])
        layout.cover_page_count = 1
        pdf.showPage()

    # Determine total worksheet pages needed (2 cols × ~20 rows per page)
    PROBLEMS_PER_PAGE = 20
    ws_pages_needed = max(1, (len(result.problems) + _COLS - 1) // _COLS)
    # But also cap per page
    problems_per_page = min(PROBLEMS_PER_PAGE, len(result.problems))
    ws_page_count = max(1, (len(result.problems) + problems_per_page - 1) // problems_per_page)

    # Challenge page (if any)
    has_challenge = bool(result.challenge_problems)
    challenge_page_count = 1 if has_challenge else 0

    # Answer key pages
    answers_per_page = 40
    ak_page_count = 0
    if include_answer_key and result.problems:
        ak_page_count = max(1, (len(result.problems) + answers_per_page - 1) // answers_per_page)

    total_ws_pages = ws_page_count + challenge_page_count
    total_ak_pages = ak_page_count
    total_non_cover = total_ws_pages + total_ak_pages

    # Worksheet pages
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
            total_ws_pages,
        )

        left_x = _MARGIN
        right_x = page_w - _MARGIN
        bottom_y = _MARGIN + 30

        # How many problems on this page?
        on_this_page = min(problems_per_page, problems_left)
        page_problems = problems[page_idx * problems_per_page: page_idx * problems_per_page + on_this_page]

        _draw_problem_grid(
            pdf, page_problems,
            left_x=left_x, right_x=right_x,
            top_y=top_y, bottom_y=bottom_y,
        )

        layout.worksheet_pages += 1
        pdf.showPage()

    # Challenge page
    if has_challenge:
        _paint_white(pdf)
        _draw_header(
            pdf,
            f"{result.title} — Challenge",
            "Bonus problems for advanced learners",
            result.grade, result.math_topic, result.difficulty,
            ws_page_count + 1, total_ws_pages,
        )
        top_y = page_h - _MARGIN - _HEADER_H - 10
        _draw_problem_grid(
            pdf, result.challenge_problems,
            left_x=_MARGIN, right_x=page_w - _MARGIN,
            top_y=top_y, bottom_y=_MARGIN + 30,
        )
        layout.worksheet_pages += 1
        pdf.showPage()

    # Answer key pages
    if include_answer_key and result.problems:
        # Compute the list of (label, problem) pairs so we can include both
        # main problems and challenge problems (with their own section header)
        # in the answer key.
        main_answers = list(result.problems)
        challenge_answers = list(result.challenge_problems) if result.challenge_problems else []

        # Render main answer-key pages first
        for ak_page_idx in range(ak_page_count):
            _draw_answer_key_page(
                pdf,
                main_answers[ak_page_idx * answers_per_page: (ak_page_idx + 1) * answers_per_page],
                result.title,
                page_num=ak_page_idx + 1,
                total_pages=ak_page_count,
                section_label="Main",
            )
            layout.answer_key_pages += 1
            pdf.showPage()

        # Render a separate answer-key page for the challenge section if there
        # are challenge problems. This guarantees the customer sees the
        # challenge answer alongside the bonus problems on the worksheet.
        if challenge_answers:
            _draw_answer_key_page(
                pdf,
                challenge_answers,
                result.title,
                page_num=1,
                total_pages=1,
                section_label="Challenge",
            )
            layout.answer_key_pages += 1
            pdf.showPage()

    pdf.save()
    return buffer.getvalue(), layout


def save_math_worksheet_pdf(
    result: MathWorksheetResult,
    output_dir: str,
    filename: str = "math_worksheet.pdf",
) -> tuple[bytes, MathWorksheetLayoutInfo]:
    pdf_bytes, layout = build_math_worksheet_pdf_bytes(result)
    path = os.path.join(output_dir, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)
    return pdf_bytes, layout
