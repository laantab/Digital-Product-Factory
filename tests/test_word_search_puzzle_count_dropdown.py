"""Word Search "Number of puzzles" dropdown.

User-requested addition (chat, 2026-09-08): mirrors the identical,
already-shipped Crossword pattern (CROSSWORD_BOOK_PUZZLE_COUNTS /
_crosswordSetupForm). Unlike Crossword, services.product._word_search_plan
never hardcoded a fixed count -- nothing in the backend needed unlocking,
this is a pure customer-facing UX restoration from a free-text number
field (default "5") to a curated dropdown.

No external/paid API call is made by any test in this file.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from services.factory.puzzle_plan import WORD_SEARCH_BOOK_PUZZLE_COUNTS  # noqa: E402
from services.product import _word_search_pdf_payload  # noqa: E402

_BASE_WORDS = [
    "apple", "banana", "cherry", "dragon", "energy", "forest", "garden", "harbor", "island", "jungle",
    "kitten", "ladder", "meadow", "napkin", "ocean", "pencil", "quartz", "rabbit", "silver", "temple",
    "umbrella", "violet", "walnut", "yellow", "zephyr", "anchor", "bridge", "candle", "desert", "eagle",
    "feather", "granite", "hammer", "igloo", "jacket", "kettle", "lantern", "marble", "needle", "orange",
    "pebble", "quiver", "ribbon", "saddle", "turtle", "unicorn", "velvet", "willow", "xylophone", "yogurt",
    "zebra", "blossom", "canyon", "diamond", "engine", "falcon", "glacier", "harvest", "ivory", "jasmine",
]
SIXTY_WORDS = "\n".join(_BASE_WORDS)
# 20 puzzles x 10 words/puzzle can need up to 200 words -- letters-only
# suffixes (not digits, which the grid parser strips) keep every entry a
# distinct, real-looking word instead of collapsing into duplicates.
_SUFFIXES = ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t"]
TWO_HUNDRED_WORDS = "\n".join(f"{w}{suf}" for suf in _SUFFIXES for w in _BASE_WORDS[:10])


def _field_block() -> str:
    src = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    start = src.index('id: "word_search"')
    end = src.index('\n  {\n    id: "', start)
    return src[start:end]


class DropdownExistsTests(unittest.TestCase):
    def test_puzzles_field_is_a_select_not_a_number_input(self):
        block = _field_block()
        p_start = block.index('name: "puzzles"')
        p_block = block[p_start:block.index("},", p_start)]
        self.assertIn('type: "select"', p_block)
        self.assertNotIn('type: "number"', p_block)

    def test_dropdown_options_match_the_backend_curated_set(self):
        block = _field_block()
        p_start = block.index('name: "puzzles"')
        p_block = block[p_start:block.index("},", p_start)]
        for n in WORD_SEARCH_BOOK_PUZZLE_COUNTS:
            self.assertIn(f'"{n}"', p_block)

    def test_puzzles_field_is_hidden_and_shown_by_output_format(self):
        src = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        fn_start = src.index("function _wordSearchSetupForm")
        fn_body = src[fn_start:src.index("\n}", fn_start)]
        self.assertIn("puzzlesWrap", fn_body)
        self.assertIn('classList.toggle("hidden"', fn_body)


class BackendHonorsEachCurratedCountTests(unittest.TestCase):
    def test_full_book_honors_every_allowed_puzzle_count(self):
        for n in WORD_SEARCH_BOOK_PUZZLE_COUNTS:
            with self.subTest(count=n):
                result = _word_search_pdf_payload({
                    "topic": "Test", "output_format": "Full Book", "puzzles": str(n),
                    "words_per_puzzle": "10", "difficulty": "Easy",
                    "creation_mode": "Custom word list", "custom_words": TWO_HUNDRED_WORDS,
                    "include_answer_key": "No", "include_cover": "No",
                })
                self.assertTrue(result.get("pdf_bytes"))


if __name__ == "__main__":
    unittest.main()
