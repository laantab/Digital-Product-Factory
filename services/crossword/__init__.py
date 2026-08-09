"""Crossword puzzle book component — separate from Word Search."""
from services.crossword.builder import (
    CrosswordPuzzleResult,
    build_crossword_from_custom_list,
    build_crossword_from_entries,
    build_crossword_from_topic,
)
from services.crossword.clues import generate_clues_for_words, generate_clues_from_ai
from services.crossword.engine import (
    CrosswordBuildResult,
    CrosswordClueEntry,
    build_crossword_grid,
    normalize_grid_size,
)
from services.crossword.pdf_builder import (
    CrosswordPdfRequest,
    CrosswordPdfResult,
    build_crossword_pdf,
    save_crossword_pdf,
)
from services.crossword.word_entries import (
    CrosswordEntry,
    fetch_crossword_words_from_ai,
    parse_crossword_word_list,
    suggest_crossword_words_from_topic,
)
from services.crossword.book import build_crossword_puzzles

__all__ = [
    "CrosswordPuzzleResult",
    "CrosswordBuildResult",
    "CrosswordClueEntry",
    "CrosswordEntry",
    "CrosswordPdfRequest",
    "CrosswordPdfResult",
    "build_crossword_from_custom_list",
    "build_crossword_from_entries",
    "build_crossword_from_topic",
    "build_crossword_grid",
    "build_crossword_pdf",
    "build_crossword_puzzles",
    "generate_clues_for_words",
    "generate_clues_from_ai",
    "normalize_grid_size",
    "parse_crossword_word_list",
    "save_crossword_pdf",
    "suggest_crossword_words_from_topic",
    "fetch_crossword_words_from_ai",
]
