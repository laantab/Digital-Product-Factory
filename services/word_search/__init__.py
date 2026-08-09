"""Word Search Book Builder — deterministic puzzle engine (Phase 1)."""
from .book import build_word_search_puzzles
from .builder import (
    build_puzzle_from_custom_list,
    build_puzzle_from_topic,
)
from .pdf_builder import (
    WordSearchPdfRequest,
    WordSearchPdfResult,
    build_word_search_pdf,
    html_to_pdf_bytes,
    save_word_search_pdf,
)
from .renderer import render_word_search_document_html
from .word_lists import parse_custom_word_list, suggest_words_from_topic

__all__ = [
    "build_puzzle_from_custom_list",
    "build_puzzle_from_topic",
    "build_word_search_pdf",
    "build_word_search_puzzles",
    "html_to_pdf_bytes",
    "parse_custom_word_list",
    "render_word_search_document_html",
    "save_word_search_pdf",
    "suggest_words_from_topic",
    "WordSearchPdfRequest",
    "WordSearchPdfResult",
]
