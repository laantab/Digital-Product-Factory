"""Rendered-PDF checks for legible Word Search solution paths."""
from __future__ import annotations

import fitz

from services.word_search.book import build_word_search_puzzles
from services.word_search.direct_pdf_renderer import build_single_worksheet_pdf_bytes
from services.word_search.layout_attempt import _prepare_solution_data


EXPECTED_OUTLINE_COLORS = {
    tuple(round(channel / 255, 6) for channel in rgb)
    for rgb in (
        (29, 78, 216),
        (4, 120, 87),
        (180, 83, 9),
        (126, 34, 206),
        (190, 18, 60),
        (15, 118, 110),
        (67, 56, 202),
        (77, 124, 15),
    )
}


def _house_plants_answer_pdf():
    puzzles, _warnings, errors = build_word_search_puzzles(
        mode="topic",
        topic="House Plants",
        theme="House Plants",
        product_title="House Plants",
        difficulty="medium",
        grid_size=12,
        number_of_puzzles=1,
        words_per_puzzle=10,
        output_type="single_worksheet",
        seed=417,
    )
    assert not errors, errors
    puzzle = puzzles[0]
    assert not _prepare_solution_data(puzzle)
    pdf_bytes, layout = build_single_worksheet_pdf_bytes(
        puzzle=puzzle,
        product_title="House Plants",
        difficulty="medium",
        include_answer_key=True,
    )
    return puzzle, pdf_bytes, layout


def test_answer_key_explains_color_coding_and_draws_one_outline_per_answer():
    puzzle, pdf_bytes, layout = _house_plants_answer_pdf()
    document = fitz.open(stream=pdf_bytes, filetype="pdf")
    answer_page = document[1]

    assert "Each answer has its own colored outline; answer letters are red." in answer_page.get_text()
    assert layout.answer_oval_count == len(puzzle.word_bank)

    drawings = answer_page.get_drawings()
    colored_marks = [
        drawing
        for drawing in drawings
        if drawing.get("color") is not None
        and tuple(round(channel, 6) for channel in drawing["color"]) in EXPECTED_OUTLINE_COLORS
    ]
    assert len(colored_marks) == len(puzzle.word_bank)
    assert len({tuple(round(channel, 6) for channel in mark["color"]) for mark in colored_marks}) > 1


def test_answer_key_keeps_the_same_pages_and_grid_after_visibility_change():
    puzzle, pdf_bytes, layout = _house_plants_answer_pdf()
    document = fitz.open(stream=pdf_bytes, filetype="pdf")

    assert document.page_count == 2
    assert tuple(document[0].rect) == tuple(document[1].rect)
    assert layout.grid_size == 12
    assert layout.answer_oval_count == len(puzzle.word_bank)
