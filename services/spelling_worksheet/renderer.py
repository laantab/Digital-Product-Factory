"""PDF renderer for Spelling Worksheet — ReportLab-based layout.

Student-facing practice pages show NO answers on question lines.
All spelling words appear in a word bank at the bottom of each practice page.
The Answer Key page shows correct answers.
"""
from __future__ import annotations

import io
import os
from dataclasses import dataclass

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services.spelling_worksheet.builder import SpellingSection, SpellingWord, SpellingWorksheetResult

_MARGIN = 0.5 * 72.0
_HEADER_H = 60


@dataclass
class SpellingWorksheetLayoutInfo:
    render_engine: str = "spelling_worksheet_direct"
    practice_pages: int = 0
    dictation_pages: int = 0
    answer_key_pages: int = 0
    cover_page_count: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# Colour palette
# ─────────────────────────────────────────────────────────────────────────────
_C_GRAY_600 = colors.HexColor("#374151")
_C_GRAY_500 = colors.HexColor("#6B7280")
_C_GRAY_400 = colors.HexColor("#9CA3AF")
_C_GRAY_200 = colors.HexColor("#D1D5DB")
_C_GRAY_100 = colors.HexColor("#F3F4F6")
_C_BLUE_700 = colors.HexColor("#1D4ED8")    # scrambled word clue
_C_AMBER_600 = colors.HexColor("#B45309")   # missing-letters clue
_C_PINK_100 = colors.HexColor("#FDF2F8")   # word bank background


def _paint_white(pdf: canvas.Canvas) -> None:
    page_w, page_h = letter
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)


# ─────────────────────────────────────────────────────────────────────────────
# Word bank — drawn at bottom of each practice page
# ─────────────────────────────────────────────────────────────────────────────
def _draw_word_bank(
    pdf: canvas.Canvas,
    all_words: list[str],
    page_w: float,
    page_h: float,
) -> None:
    """Draw the spelling word bank at the bottom of a practice page.

    Words appear in a lightly-shaded box in columns.
    Students use this to find the correct spelling for each activity.
    """
    BANK_H = 70.0       # height reserved for word bank
    BOTTOM_Y = _MARGIN
    x_left = _MARGIN
    x_right = page_w - _MARGIN

    # Shaded background for the bank
    pdf.setFillColor(_C_PINK_100)
    pdf.rect(x_left, BOTTOM_Y, x_right - x_left, BANK_H, fill=1, stroke=0)

    # Label
    pdf.setFillColor(_C_GRAY_500)
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawString(x_left + 4, BOTTOM_Y + BANK_H - 12, "WORD BANK:")

    # Two columns of words
    words = [w.upper() for w in all_words if w]
    mid = len(words) // 2
    col_a = words[:mid]
    col_b = words[mid:]

    col_w = (x_right - x_left) / 2.0
    row_h = 13
    start_y = BOTTOM_Y + BANK_H - 26

    pdf.setFont("Helvetica", 8)
    pdf.setFillColor(colors.black)

    for i, word in enumerate(col_a):
        row = i
        x = x_left + 4
        y = start_y - row * row_h
        if y < BOTTOM_Y + 4:
            break
        pdf.drawString(x, y, word)

    for i, word in enumerate(col_b):
        row = i
        x = x_left + col_w + 4
        y = start_y - row * row_h
        if y < BOTTOM_Y + 4:
            break
        pdf.drawString(x, y, word)


# ─────────────────────────────────────────────────────────────────────────────
# Single practice row — NO answer on the line
# ─────────────────────────────────────────────────────────────────────────────
def _draw_word_row(
    pdf: canvas.Canvas,
    word: SpellingWord,
    row_num: int,
    y: float,
    x_left: float,
    x_right: float,
    activity_type: str,
) -> float:
    """Draw one numbered activity row WITHOUT the answer.

    Shows only the prompt/clue/blank for the student to work from.
    The word bank at the bottom of the page provides the word list.
    """
    row_h = 54

    # Alternating background
    if row_num % 2 == 0:
        pdf.setFillColor(_C_GRAY_100)
        pdf.rect(x_left, y - row_h + 4, x_right - x_left, row_h - 4, fill=1, stroke=0)

    # ── Number ────────────────────────────────────────────────────────────────
    pdf.setFont("Helvetica-Bold", 10)
    pdf.setFillColor(_C_GRAY_600)
    pdf.drawString(x_left + 4, y - 14, f"{row_num}.")

    WRITE_LINE_Y = y - 18   # the student's writing line

    # ── Prompt / clue (never the answer) ─────────────────────────────────────
    if activity_type == "unscramble":
        # Show only the scrambled clue
        clue = (word.scrambled or "").upper() or "?????"
        pdf.setFont("Helvetica-Bold", 12)
        pdf.setFillColor(_C_BLUE_700)
        pdf.drawString(x_left + 28, y - 14, clue)

    elif activity_type == "missing letters":
        # Show only the missing-letter clue
        clue = word.scrambled or "???_???"
        pdf.setFont("Helvetica-Bold", 12)
        pdf.setFillColor(_C_AMBER_600)
        pdf.drawString(x_left + 28, y - 14, clue)

    elif activity_type == "fill in the blank":
        # Show sentence with blank (the blank is the answer)
        sentence = word.sentence or f"Fill in the blank for: {word.word}"
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.setFillColor(_C_GRAY_600)
        pdf.drawString(x_left + 28, y - 10, sentence[:100])

    elif activity_type == "alphabetical order":
        # Do NOT show the word on the question line — students use the word bank at the bottom
        # Show just a short instruction
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.setFillColor(_C_GRAY_400)
        pdf.drawString(x_left + 28, y - 14, "Write the word in alphabetical order:")

    else:
        # "word list" / "write each word" / "mixed practice"
        # Show just the instruction line — no word visible
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.setFillColor(_C_GRAY_400)
        pdf.drawString(x_left + 28, y - 14, "Write the word correctly:")

    # ── Student writing line ────────────────────────────────────────────────────
    pdf.setStrokeColor(_C_GRAY_200)
    pdf.setLineWidth(0.5)
    pdf.line(x_left + 28, WRITE_LINE_Y, x_right - 4, WRITE_LINE_Y)

    return y - row_h


# ─────────────────────────────────────────────────────────────────────────────
# Practice page — questions, then word bank at the bottom
# ─────────────────────────────────────────────────────────────────────────────
def _draw_practice_page(
    pdf: canvas.Canvas,
    section: SpellingSection,
    all_words: list[str],
    section_num: int,
    page_num: int,
    total_pages: int,
    title: str,
) -> None:
    """Draw one vocabulary practice page with NO answers on question lines."""
    page_w, page_h = letter
    _paint_white(pdf)

    # ── Header ────────────────────────────────────────────────────────────────
    pdf.setFont("Helvetica-Bold", 14)
    pdf.setFillColor(colors.black)
    pdf.drawCentredString(page_w / 2.0, page_h - _MARGIN - 16, f"Spelling Practice — {title[:60]}")

    pdf.setFont("Helvetica", 9)
    pdf.setFillColor(_C_GRAY_500)
    page_label = f"Section {section_num}: {section.label}"
    if total_pages > 1:
        page_label += f"  (page {page_num} of {total_pages})"
    pdf.drawCentredString(page_w / 2.0, page_h - _MARGIN - 30, page_label)

    pdf.setStrokeColor(_C_GRAY_200)
    pdf.setLineWidth(0.5)
    pdf.line(_MARGIN, page_h - _MARGIN - 38, page_w - _MARGIN, page_h - _MARGIN - 38)

    # ── Instructions ────────────────────────────────────────────────────────
    if section.instruction:
        pdf.setFont("Helvetica-Oblique", 9)
        pdf.setFillColor(_C_GRAY_600)
        pdf.drawString(_MARGIN, page_h - _MARGIN - 52, section.instruction[:120])

    # ── Word rows ─────────────────────────────────────────────────────────────
    BANK_H = 70.0
    WORD_BANK_CUTOFF = _MARGIN + BANK_H + 6   # stop drawing rows before word bank

    top_y = page_h - _MARGIN - _HEADER_H
    x_right = page_w - _MARGIN

    for i, word in enumerate(section.words):
        top_y = _draw_word_row(
            pdf, word, i + 1,
            y=top_y,
            x_left=_MARGIN, x_right=x_right,
            activity_type=section.activity_type,
        )
        if top_y < WORD_BANK_CUTOFF:
            break

    # ── Word bank at bottom ────────────────────────────────────────────────────
    if all_words:
        _draw_word_bank(pdf, all_words, page_w, page_h)


# ─────────────────────────────────────────────────────────────────────────────
# Answer Key page — shows correct answers per activity type
# ─────────────────────────────────────────────────────────────────────────────
def _draw_answer_key_page(
    pdf: canvas.Canvas,
    section: SpellingSection,
    title: str,
) -> None:
    """Draw the answer key page with correct spellings for each activity."""
    page_w, page_h = letter
    _paint_white(pdf)

    pdf.setFont("Helvetica-Bold", 14)
    pdf.setFillColor(colors.black)
    pdf.drawCentredString(page_w / 2.0, page_h - _MARGIN - 16, f"Spelling Answer Key — {title[:60]}")

    pdf.setStrokeColor(_C_GRAY_200)
    pdf.setLineWidth(0.5)
    pdf.line(_MARGIN, page_h - _MARGIN - 26, page_w - _MARGIN, page_h - _MARGIN - 26)

    top_y = page_h - _MARGIN - _HEADER_H
    row_h = 22
    x_left = _MARGIN
    x_right = page_w - _MARGIN
    bottom_limit = _MARGIN + 20

    activity = section.activity_type

    for i, word in enumerate(section.words):
        if top_y - row_h < bottom_limit:
            break

        # Number
        pdf.setFont("Helvetica-Bold", 10)
        pdf.setFillColor(_C_GRAY_600)
        pdf.drawString(x_left + 4, top_y - 14, f"{i + 1}.")

        if activity == "unscramble":
            # Show scrambled → correct
            clue = (word.scrambled or "????").upper()
            correct = word.word.upper()
            pdf.setFont("Helvetica-Oblique", 9)
            pdf.setFillColor(_C_BLUE_700)
            pdf.drawString(x_left + 28, top_y - 10, f"({clue})  →  {correct}")

        elif activity == "missing letters":
            # Show missing → correct
            clue = word.scrambled or "???_???"
            correct = word.word.upper()
            pdf.setFont("Helvetica-Oblique", 9)
            pdf.setFillColor(_C_AMBER_600)
            pdf.drawString(x_left + 28, top_y - 10, f"({clue})  →  {correct}")

        elif activity == "fill in the blank":
            # Show sentence → correct word
            correct = word.word.upper()
            pdf.setFont("Helvetica-Oblique", 9)
            pdf.setFillColor(_C_GRAY_500)
            sentence = (word.sentence or "").replace("________", correct)
            pdf.drawString(x_left + 28, top_y - 10, sentence[:90])

        else:
            # word list / write each word / alphabetical / mixed
            pdf.setFont("Helvetica", 10)
            pdf.setFillColor(colors.black)
            correct = word.word.upper()
            pdf.drawString(x_left + 28, top_y - 14, correct if activity != "alphabetical order" else word.word.upper())

        top_y -= row_h


# ─────────────────────────────────────────────────────────────────────────────
# Dictation page
# ─────────────────────────────────────────────────────────────────────────────
def _draw_dictation_page(
    pdf: canvas.Canvas,
    sentences: list[str],
    title: str,
    page_num: int = 1,
    total_pages: int = 1,
) -> None:
    """Draw a dictation / test page."""
    page_w, page_h = letter
    _paint_white(pdf)

    pdf.setFont("Helvetica-Bold", 14)
    pdf.setFillColor(colors.black)
    pdf.drawCentredString(page_w / 2.0, page_h - _MARGIN - 16, f"Dictation Practice — {title[:60]}")

    pdf.setStrokeColor(_C_GRAY_200)
    pdf.setLineWidth(0.5)
    pdf.line(_MARGIN, page_h - _MARGIN - 26, page_w - _MARGIN, page_h - _MARGIN - 26)

    pdf.setFont("Helvetica-Oblique", 9)
    pdf.setFillColor(_C_GRAY_600)
    pdf.drawString(
        _MARGIN, page_h - _MARGIN - 40,
        "Listen to each sentence and write it. Check your spelling carefully."
    )

    top_y = page_h - _MARGIN - _HEADER_H
    bottom_limit = _MARGIN + 50
    line_h = 48

    for i, sentence in enumerate(sentences):
        if top_y - line_h < bottom_limit:
            break

        pdf.setFont("Helvetica-Bold", 9)
        pdf.setFillColor(_C_GRAY_600)
        pdf.drawString(_MARGIN, top_y - 12, f"{i + 1}.")

        pdf.setStrokeColor(_C_GRAY_200)
        pdf.line(_MARGIN + 20, top_y - 16, page_w - _MARGIN, top_y - 16)
        pdf.line(_MARGIN + 20, top_y - 34, page_w - _MARGIN, top_y - 34)

        top_y -= line_h


# ─────────────────────────────────────────────────────────────────────────────
# Main render entry point
# ─────────────────────────────────────────────────────────────────────────────
def build_spelling_worksheet_pdf_bytes(
    result: SpellingWorksheetResult,
    *,
    include_answer_key: bool | str = True,
    cover_image_path: str = "",
) -> tuple[bytes, SpellingWorksheetLayoutInfo]:
    """Render a spelling worksheet PDF from SpellingWorksheetResult.

    Student pages show NO answers. Word bank at bottom of each practice page.
    Answer key page shows correct spellings.
    """
    # Normalize: handle both bool and string ("True"/"False") from _yes() function
    _include_ak = bool(include_answer_key) if isinstance(include_answer_key, bool) else str(include_answer_key or "").lower() in ("yes", "true", "1")
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    """Render a spelling worksheet PDF from SpellingWorksheetResult.

    Student pages show NO answers. Word bank at bottom of each practice page.
    Answer key page shows correct spellings.
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    layout = SpellingWorksheetLayoutInfo()
    page_w, page_h = letter

    # ── Cover ─────────────────────────────────────────────────────────────────
    if cover_image_path and os.path.isfile(cover_image_path):
        try:
            pdf.drawImage(
                cover_image_path, 0, 0,
                width=page_w, height=page_h,
                preserveAspectRatio=False,
            )
        except Exception:  # noqa: BLE001
            _paint_white(pdf)
            pdf.setFont("Helvetica-Bold", 18)
            pdf.drawCentredString(page_w / 2.0, page_h / 2.0 + 20, result.title[:80])
        layout.cover_page_count = 1
        pdf.showPage()

    # ── Practice pages ────────────────────────────────────────────────────────
    WORDS_PER_PAGE = 12
    practice_page_count = 0

    for sec_idx, section in enumerate(result.sections):
        all_words = result.all_words  # pass full word list for word bank
        words = section.words
        pages_needed = max(1, (len(words) + WORDS_PER_PAGE - 1) // WORDS_PER_PAGE)

        for p in range(pages_needed):
            page_words = words[p * WORDS_PER_PAGE: (p + 1) * WORDS_PER_PAGE]
            sec_copy = SpellingSection(
                label=section.label,
                instruction=section.instruction,
                words=page_words,
                activity_type=section.activity_type,
            )
            _draw_practice_page(
                pdf, sec_copy, all_words,
                section_num=sec_idx + 1,
                page_num=p + 1,
                total_pages=pages_needed,
                title=result.title,
            )
            practice_page_count += 1
            pdf.showPage()

    layout.practice_pages = practice_page_count

    # ── Dictation page ────────────────────────────────────────────────────────
    if result.dictation_sentences:
        _draw_dictation_page(pdf, result.dictation_sentences, result.title)
        layout.dictation_pages = 1
        pdf.showPage()

    # ── Answer key ────────────────────────────────────────────────────────────
    if _include_ak and result.answer_key and result.sections:
        _draw_answer_key_page(pdf, result.sections[0], result.title)
        layout.answer_key_pages = 1
        pdf.showPage()

    pdf.save()
    return buffer.getvalue(), layout


def save_spelling_worksheet_pdf(
    result: SpellingWorksheetResult,
    output_dir: str,
    filename: str = "spelling_worksheet.pdf",
) -> tuple[bytes, SpellingWorksheetLayoutInfo]:
    pdf_bytes, layout = build_spelling_worksheet_pdf_bytes(result)
    path = os.path.join(output_dir, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)
    return pdf_bytes, layout
