"""LEGACY HTML renderer for Word Search worksheet and book PDFs.

Not connected to Word Search Builder exports.
ACTIVE WORD SEARCH RENDERER: services/word_search/direct_pdf_renderer.py (MiniMax-style)
"""
from __future__ import annotations

import html
from typing import Iterable

from .builder import PuzzleResult

_DIFFICULTY_HELP = {
    "easy": "Words may appear horizontally or vertically.",
    "medium": "Words may appear horizontally, vertically, or diagonally.",
    "hard": "Words may appear in any direction, including backward.",
}

# Letter portrait — points (72 pt = 1 in)
_LETTER_WIDTH_PT = 612.0
_LETTER_HEIGHT_PT = 792.0
_PAGE_MARGIN_IN = 0.45
_WORKSHEET_HEADER_RESERVE_PT = 72.0
_WORKSHEET_WORD_LIST_RESERVE_PT = 88.0
_WORKSHEET_ANSWER_HEADER_RESERVE_PT = 48.0
_GRID_WORD_GAP_PT = 24.0
_ANSWER_HIT_COLOR = "#fde68a"
_WORD_LIST_COLUMNS = 3
_CELL_SIZE_MIN_PT = 21.0
_CELL_SIZE_MAX_PT = 28.0


def _e(value: object) -> str:
    return html.escape(str(value or ""))


def _stylesheet() -> str:
    return """
@page { size: letter; margin: 0.45in; }
* { box-sizing: border-box; }
body {
  margin: 0;
  padding: 0;
  font-family: Helvetica, Arial, sans-serif;
  color: #1e293b;
  background: #ffffff;
}
.ws-doc { width: 100%; }
.ws-page {
  page-break-after: always;
  padding: 0.1in 0.05in 0.2in;
}
.ws-page:last-child { page-break-after: auto; }
.ws-frame {
  border: 2px solid #334155;
  border-radius: 14px;
  padding: 22px 24px;
  background: #ffffff;
}
.ws-cover-frame {
  min-height: 9in;
  text-align: center;
  background: linear-gradient(165deg, #f8fafc 0%, #e2e8f0 55%, #6366f1 160%);
  color: #0f172a;
  padding-top: 1.2in;
}
.ws-badge {
  display: inline-block;
  font-size: 9pt;
  text-transform: uppercase;
  font-weight: 700;
  background: #4338ca;
  color: #ffffff;
  padding: 8px 16px;
  border-radius: 999px;
  margin-bottom: 18px;
}
.ws-cover-title {
  font-size: 26pt;
  line-height: 1.12;
  font-weight: 800;
  margin: 0 auto 10px;
  max-width: 6.2in;
}
.ws-cover-subtitle {
  font-size: 13pt;
  line-height: 1.35;
  margin: 0 auto 14px;
  max-width: 5.8in;
  color: #334155;
}
.ws-cover-meta {
  margin: 18px auto 0;
  max-width: 4.8in;
  font-size: 10pt;
  color: #475569;
}
.ws-cover-meta p { margin: 6px 0; }
.ws-heading {
  font-size: 20pt;
  font-weight: 800;
  margin: 0 0 8px;
  text-align: center;
}
.ws-subheading {
  font-size: 11pt;
  color: #64748b;
  text-align: center;
  margin: 0 0 18px;
}
.ws-section-label {
  font-size: 9pt;
  text-transform: uppercase;
  font-weight: 800;
  color: #4338ca;
  margin: 0 0 8px;
}
.ws-instructions {
  font-size: 11pt;
  line-height: 1.55;
  margin: 0 0 12px;
  color: #334155;
}
.ws-instructions li { margin: 6px 0; }
.ws-word-bank {
  border: 1.5px solid #334155;
  border-radius: 10px;
  background: #f8fafc;
  padding: 12px 14px;
  margin: 0 0 16px;
}
.ws-word-bank-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 6px;
}
.ws-word-bank-cell {
  width: 33%;
  vertical-align: top;
  text-align: center;
}
.ws-word-chip {
  display: block;
  border: 1px solid #94a3b8;
  border-radius: 8px;
  background: #ffffff;
  padding: 6px 8px;
  font-size: 10pt;
  font-weight: 700;
}
.ws-grid-wrap {
  text-align: center;
  margin: 8px auto 0;
}
.ws-grid {
  border-collapse: collapse;
  margin: 0 auto;
  table-layout: fixed;
}
.ws-cell {
  border: 1.5px solid #334155;
  text-align: center;
  vertical-align: middle;
  font-family: "Courier New", Courier, monospace;
  font-weight: 700;
  background: #ffffff;
  color: #0f172a;
  padding: 0;
}
.ws-cell-size-12 { width: 28px; height: 28px; font-size: 13pt; }
.ws-cell-size-15 { width: 24px; height: 24px; font-size: 11pt; }
.ws-cell-size-18 { width: 21px; height: 21px; font-size: 10pt; }
.ws-cell-size-20 { width: 19px; height: 19px; font-size: 9pt; }
.ws-cell-size-default { width: 22px; height: 22px; font-size: 10pt; }
.ws-answer-hit { background: #fde68a; }
.ws-answer-title {
  font-size: 12pt;
  font-weight: 800;
  margin: 0 0 8px;
  text-align: center;
}
.ws-answer-block { margin: 0 0 18px; }
.ws-answer-grid-wrap { text-align: center; }
.ws-mini-cell {
  border: 1px solid #64748b;
  text-align: center;
  vertical-align: middle;
  font-family: "Courier New", Courier, monospace;
  font-size: 7pt;
  font-weight: 700;
  width: 14px;
  height: 14px;
  padding: 0;
}
.ws-mini-hit { background: #fcd34d; }
.ws-footer-note {
  font-size: 8.5pt;
  color: #64748b;
  text-align: center;
  margin-top: 10px;
}
/* Single worksheet — published puzzle-book interior pages */
.ws-worksheet-page {
  page-break-after: auto;
  padding: 0;
}
.ws-worksheet-answer-page {
  page-break-after: auto;
  page-break-before: auto;
  padding: 0;
}
.ws-worksheet-title {
  font-size: 14pt;
  line-height: 1.2;
  font-weight: 700;
  margin: 0 0 4px;
  text-align: center;
  color: #000000;
}
.ws-worksheet-subtitle {
  font-size: 10pt;
  line-height: 1.3;
  color: #333333;
  text-align: center;
  margin: 0 0 4px;
}
.ws-worksheet-instruction {
  font-size: 9pt;
  line-height: 1.35;
  color: #333333;
  text-align: center;
  margin: 0 0 10px;
}
.ws-worksheet-letter-wrap {
  margin: 0;
  padding: 0;
  page-break-inside: avoid;
}
.ws-grid-list-gap {
  height: 24pt;
  margin: 0;
  padding: 0;
  border: 0;
  font-size: 1pt;
  line-height: 24pt;
}
.ws-letter-outer-box {
  border: 1px solid #000000;
  border-collapse: collapse;
  margin: 0 auto;
}
.ws-letter-outer-box td {
  border: none;
  padding: 6pt;
}
.ws-letter-grid {
  border: none;
  border-collapse: collapse;
  table-layout: fixed;
  margin: 0 auto;
}
.ws-letter-cell {
  border: none;
  text-align: center;
  vertical-align: middle;
  font-family: "Courier New", Courier, monospace;
  font-weight: 700;
  color: #000000;
  background: transparent;
  padding: 0;
  margin: 0;
  line-height: 1;
}
.ws-letter-hit {
  background-color: #fde68a;
}
.ws-word-list {
  margin: 0 auto;
  padding: 0;
  width: 100%;
}
.ws-word-list-label {
  font-size: 9pt;
  font-weight: 700;
  text-transform: uppercase;
  color: #000000;
  text-align: center;
  margin: 0 0 8px;
}
.ws-word-list-table {
  width: 100%;
  border: none;
  border-collapse: collapse;
  table-layout: fixed;
  margin: 0 auto;
}
.ws-list-word {
  width: 33%;
  text-align: center;
  vertical-align: middle;
  font-size: 10pt;
  font-weight: 400;
  color: #000000;
  padding: 3px 10px;
  white-space: nowrap;
  border: none;
  background: transparent;
}
.ws-list-empty {
  color: transparent;
}
.ws-answer-heading {
  font-size: 14pt;
  font-weight: 700;
  margin: 0 0 6px;
  text-align: center;
  color: #000000;
}
.ws-worksheet-answer-subtitle {
  font-size: 10pt;
  color: #333333;
  text-align: center;
  margin: 0 0 12px;
}
"""


def _cell_class(grid_size: int) -> str:
    if grid_size <= 12:
        return "ws-cell-size-12"
    if grid_size <= 15:
        return "ws-cell-size-15"
    if grid_size <= 18:
        return "ws-cell-size-18"
    if grid_size <= 20:
        return "ws-cell-size-20"
    return "ws-cell-size-default"


def _worksheet_printable_width_pt() -> float:
    margins = _PAGE_MARGIN_IN * 72.0 * 2
    return _LETTER_WIDTH_PT - margins


def _word_list_columns(word_count: int) -> int:
    _ = word_count
    return _WORD_LIST_COLUMNS


def _word_list_reserved_pt(word_count: int) -> float:
    if word_count <= 0:
        return _WORKSHEET_WORD_LIST_RESERVE_PT
    columns = _WORD_LIST_COLUMNS
    rows = (word_count + columns - 1) // columns
    label_pt = 16.0
    row_pt = 14.0
    return _GRID_WORD_GAP_PT + label_pt + rows * row_pt + 4.0


def _worksheet_printable_height_pt(*, include_word_list: bool, word_count: int = 0) -> float:
    margins = _PAGE_MARGIN_IN * 72.0 * 2
    header = _WORKSHEET_HEADER_RESERVE_PT
    if include_word_list:
        footer = _word_list_reserved_pt(word_count)
    else:
        footer = _WORKSHEET_ANSWER_HEADER_RESERVE_PT
    return _LETTER_HEIGHT_PT - margins - header - footer


def worksheet_grid_metrics(
    grid_size: int,
    *,
    include_word_list: bool = True,
    word_count: int = 0,
) -> dict[str, float]:
    """Square invisible-border cells (28–32 px / 21–28 pt) sized to fit one page."""
    size = max(1, int(grid_size))
    printable_w = _worksheet_printable_width_pt()
    printable_h = _worksheet_printable_height_pt(
        include_word_list=include_word_list,
        word_count=word_count,
    )
    cell_from_width = (printable_w * 0.96) / size
    cell_from_height = printable_h / size
    cell_pt = min(
        _CELL_SIZE_MAX_PT,
        max(_CELL_SIZE_MIN_PT, min(cell_from_width, cell_from_height)),
    )
    font_pt = max(10.0, min(cell_pt * 0.62, cell_pt - 3.0))
    block_width_pt = round(cell_pt * size, 1)
    return {
        "cell_pt": round(cell_pt, 1),
        "font_pt": round(font_pt, 1),
        "line_height_pt": round(cell_pt, 1),
        "col_width_pt": round(cell_pt, 1),
        "block_width_pt": block_width_pt,
        "grid_width_pt": block_width_pt,
    }


def _chunk_word_bank(words: Iterable[str], columns: int = 3) -> list[list[str]]:
    items = list(words)
    if not items:
        return []
    rows: list[list[str]] = []
    for index in range(0, len(items), columns):
        row = items[index : index + columns]
        while len(row) < columns:
            row.append("")
        rows.append(row)
    return rows


def _answer_hit_set(puzzle: PuzzleResult) -> set[tuple[int, int]]:
    hits: set[tuple[int, int]] = set()
    for item in puzzle.answer_key:
        for cell in item.get("cells") or []:
            if isinstance(cell, (list, tuple)) and len(cell) == 2:
                hits.add((int(cell[0]), int(cell[1])))
    return hits


def _word_list_html(words: Iterable[str]) -> str:
    items = list(words)
    columns = _WORD_LIST_COLUMNS
    rows = _chunk_word_bank(items, columns=columns)
    body = ""
    for row in rows:
        cells = ""
        for word in row:
            if word:
                cells += (
                    f'<td class="ws-list-word" width="33%" '
                    f'style="width:33%;border:none;padding:3px 10px;">{_e(word)}</td>'
                )
            else:
                cells += (
                    '<td class="ws-list-word ws-list-empty" width="33%" '
                    'style="width:33%;border:none;padding:3px 10px;">&nbsp;</td>'
                )
        body += f"<tr>{cells}</tr>"
    return f"""
<div class="ws-word-list">
  <div class="ws-word-list-label">Words to Find</div>
  <table class="ws-word-list-table" border="0" cellpadding="0" cellspacing="0"
         width="100%" style="border:none;border-collapse:collapse;">{body}</table>
</div>
"""


def _worksheet_letter_block_html(
    puzzle: PuzzleResult,
    metrics: dict[str, float],
    *,
    highlight: set[tuple[int, int]] | None = None,
) -> str:
    cell_pt = metrics["cell_pt"]
    font_pt = metrics["font_pt"]
    block_w = metrics["block_width_pt"]
    td_base = (
        f"width:{cell_pt}pt;height:{cell_pt}pt;font-size:{font_pt}pt;"
        f"border:none;padding:0;margin:0;text-align:center;vertical-align:middle;"
    )
    rows = ""
    for row_index, row in enumerate(puzzle.grid):
        cells = ""
        for col_index, letter in enumerate(row):
            is_hit = bool(highlight and (row_index, col_index) in highlight)
            extra = " ws-letter-hit" if is_hit else ""
            bg = f"background-color:{_ANSWER_HIT_COLOR};" if is_hit else ""
            cells += (
                f'<td class="ws-letter-cell{extra}" '
                f'style="{td_base}{bg}">{_e(letter)}</td>'
            )
        rows += f"<tr>{cells}</tr>"
    letter_table = (
        f'<table class="ws-letter-grid" border="0" cellpadding="0" cellspacing="0" '
        f'width="{block_w}" '
        f'style="width:{block_w}pt;border:none;border-collapse:collapse;'
        f'table-layout:fixed;">'
        f"{rows}</table>"
    )
    outer_box = (
        f'<table class="ws-letter-outer-box" border="0" cellpadding="0" cellspacing="0" '
        f'align="center" style="border:1px solid #000000;border-collapse:collapse;">'
        f'<tr><td style="border:none;padding:6pt;">{letter_table}</td></tr>'
        f"</table>"
    )
    return (
        f'<table border="0" cellpadding="0" cellspacing="0" width="100%" '
        f'style="border:none;">'
        f'<tr><td align="center" style="border:none;">{outer_box}</td></tr>'
        f"</table>"
    )


def _grid_table_html(puzzle: PuzzleResult, cell_class: str, *, highlight: set[tuple[int, int]] | None = None) -> str:
    rows = ""
    for row_index, row in enumerate(puzzle.grid):
        cells = ""
        for col_index, letter in enumerate(row):
            extra = ""
            if highlight and (row_index, col_index) in highlight:
                extra = " ws-mini-hit"
            cells += f'<td class="ws-cell {cell_class}{extra}">{_e(letter)}</td>'
        rows += f"<tr>{cells}</tr>"
    return f'<table class="ws-grid">{rows}</table>'


def render_single_worksheet_page(
    puzzle: PuzzleResult,
    *,
    product_title: str,
    subtitle: str = "",
    difficulty: str = "medium",
) -> str:
    """Clean standalone puzzle page: title, instruction, grid, spaced word list."""
    help_text = _DIFFICULTY_HELP.get(str(difficulty or "medium").lower(), _DIFFICULTY_HELP["medium"])
    word_count = len(puzzle.word_bank)
    metrics = worksheet_grid_metrics(
        puzzle.grid_size,
        include_word_list=True,
        word_count=word_count,
    )
    grid_html = _worksheet_letter_block_html(puzzle, metrics)
    word_list_html = _word_list_html(puzzle.word_bank)

    subtitle_html = f'<p class="ws-worksheet-subtitle">{_e(subtitle)}</p>' if subtitle else ""
    return f"""
<section class="ws-page ws-worksheet-page">
  <h1 class="ws-worksheet-title">{_e(product_title)}</h1>
  {subtitle_html}
  <p class="ws-worksheet-instruction">Find each word in the grid. {help_text}</p>
  <div class="ws-worksheet-letter-wrap">
    {grid_html}
  </div>
  <div class="ws-grid-list-gap">&nbsp;</div>
  {word_list_html}
</section>
"""


def render_single_worksheet_answer_page(puzzle: PuzzleResult, *, product_title: str = "") -> str:
    """Answer key page: title and large centered solved grid only."""
    hits = _answer_hit_set(puzzle)
    metrics = worksheet_grid_metrics(puzzle.grid_size, include_word_list=False)
    grid_html = _worksheet_letter_block_html(puzzle, metrics, highlight=hits)
    puzzle_label = product_title or puzzle.puzzle_title
    return f"""
<pdf:nextpage />
<section class="ws-page ws-worksheet-answer-page ws-answer-page">
  <h2 class="ws-answer-heading">Answer Key</h2>
  <p class="ws-worksheet-answer-subtitle">{_e(puzzle_label)}</p>
  <div class="ws-worksheet-letter-wrap">
    {grid_html}
  </div>
</section>
"""


def render_cover_page(
    *,
    product_title: str,
    subtitle: str = "",
    audience: str = "",
    theme: str = "",
) -> str:
    meta_parts = []
    if audience:
        meta_parts.append(f"<p><strong>Audience:</strong> {_e(audience)}</p>")
    if theme:
        meta_parts.append(f"<p><strong>Theme:</strong> {_e(theme)}</p>")
    meta_html = "".join(meta_parts)
    return f"""
<section class="ws-page ws-cover-page">
  <div class="ws-frame ws-cover-frame">
    <div class="ws-badge">Word Search</div>
    <h1 class="ws-cover-title">{_e(product_title)}</h1>
    {f'<p class="ws-cover-subtitle">{_e(subtitle)}</p>' if subtitle else ''}
    <div class="ws-cover-meta">{meta_html}</div>
  </div>
</section>
"""


def render_instructions_page(*, difficulty: str) -> str:
    help_text = _DIFFICULTY_HELP.get(str(difficulty or "medium").lower(), _DIFFICULTY_HELP["medium"])
    return f"""
<section class="ws-page ws-instructions-page">
  <div class="ws-frame">
    <h2 class="ws-heading">How to Play</h2>
    <p class="ws-subheading">Find every word hidden in the letter grid.</p>
    <ul class="ws-instructions">
      <li>Read the word bank for the puzzle.</li>
      <li>Search for each word in the grid. {help_text}</li>
      <li>Cross off or circle each word when you find it.</li>
      <li>Answer keys appear at the end of the book when that option is selected.</li>
    </ul>
  </div>
</section>
"""


def render_puzzle_page(puzzle: PuzzleResult) -> str:
    cell_class = _cell_class(puzzle.grid_size)
    bank_rows = _chunk_word_bank(puzzle.word_bank)
    bank_html = ""
    for row in bank_rows:
        cells = "".join(
            f'<td class="ws-word-bank-cell"><span class="ws-word-chip">{_e(word)}</span></td>'
            if word
            else '<td class="ws-word-bank-cell"></td>'
            for word in row
        )
        bank_html += f"<tr>{cells}</tr>"

    grid_rows = ""
    for row in puzzle.grid:
        cells = "".join(f'<td class="ws-cell {cell_class}">{_e(letter)}</td>' for letter in row)
        grid_rows += f"<tr>{cells}</tr>"

    return f"""
<section class="ws-page ws-puzzle-page">
  <div class="ws-frame">
    <h2 class="ws-heading">{_e(puzzle.puzzle_title)}</h2>
    <p class="ws-subheading">Find the words listed below.</p>
    <div class="ws-word-bank">
      <div class="ws-section-label">Word Bank</div>
      <table class="ws-word-bank-table">{bank_html}</table>
    </div>
    <div class="ws-grid-wrap">
      <table class="ws-grid">{grid_rows}</table>
    </div>
  </div>
</section>
"""


def render_answer_page(puzzles: list[PuzzleResult]) -> str:
    blocks = ""
    for puzzle in puzzles:
        hits = _answer_hit_set(puzzle)
        rows = ""
        for row_index, row in enumerate(puzzle.grid):
            cells = ""
            for col_index, letter in enumerate(row):
                css = "ws-mini-cell ws-mini-hit" if (row_index, col_index) in hits else "ws-mini-cell"
                cells += f'<td class="{css}">{_e(letter)}</td>'
            rows += f"<tr>{cells}</tr>"
        blocks += f"""
<div class="ws-answer-block">
  <div class="ws-answer-title">{_e(puzzle.puzzle_title)} — Answer Key</div>
  <div class="ws-answer-grid-wrap"><table class="ws-grid">{rows}</table></div>
</div>
"""
    return f"""
<section class="ws-page ws-answer-page">
  <div class="ws-frame">
    <h2 class="ws-heading">Answer Key</h2>
    {blocks}
  </div>
</section>
"""


def render_word_search_document_html(
    *,
    product_title: str,
    subtitle: str = "",
    audience: str = "",
    theme: str = "",
    difficulty: str = "medium",
    puzzles: list[PuzzleResult],
    include_cover: bool = True,
    include_instructions: bool = False,
    include_answer_key: bool = True,
    output_type: str = "book",
) -> str:
    parts: list[str] = []
    is_worksheet = str(output_type or "").strip().lower() == "single_worksheet" and len(puzzles) == 1

    if is_worksheet:
        puzzle = puzzles[0]
        parts.append(
            render_single_worksheet_page(
                puzzle,
                product_title=product_title,
                subtitle=subtitle,
                difficulty=difficulty,
            )
        )
        if include_answer_key:
            parts.append(render_single_worksheet_answer_page(puzzle, product_title=product_title))
    else:
        if include_cover:
            parts.append(
                render_cover_page(
                    product_title=product_title,
                    subtitle=subtitle,
                    audience=audience,
                    theme=theme,
                )
            )
        if include_instructions:
            parts.append(render_instructions_page(difficulty=difficulty))
        for puzzle in puzzles:
            parts.append(render_puzzle_page(puzzle))
        if include_answer_key and puzzles:
            per_page = 2
            for index in range(0, len(puzzles), per_page):
                parts.append(render_answer_page(puzzles[index : index + per_page]))
    body = "\n".join(parts)
    return f"""<!DOCTYPE html>
<html lang="en" xmlns:pdf="http://www.xhtml2pdf.com/ns/">
<head>
<meta charset="utf-8">
<title>{_e(product_title)}</title>
<style>{_stylesheet()}</style>
</head>
<body>
<div class="ws-doc">
{body}
</div>
</body>
</html>
"""
