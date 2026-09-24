"""WORD SEARCH REPRODUCIBILITY -- the same saved book must rebuild identically.

The defect (measured on the customer path at 390aaf8, v1.9.2)
--------------------------------------------------------------
``services.product._word_search_pdf_payload`` built every
``WordSearchPdfRequest`` with an explicit ``seed=None``.
``services/word_search/book.py`` forwards that ``None`` to
``services/word_search/engine.py``, which calls ``random.Random(seed)``, and
``random.Random(None)`` seeds itself from the operating system.

One saved book built three times, nothing changed, produced three different
sets of grids: ``afead480f1d2``, ``3eb314f3be75``, ``9d00dc852a15`` over the
rendered text. This is the same defect Crossword had, fixed there in v1.9.2;
it was recorded in docs/CROSSWORD_REPRODUCIBILITY.md at the time precisely so
it would not be lost.

What is guaranteed here
-----------------------
The *puzzles* are reproducible, not the PDF file's bytes: a PDF carries a
creation timestamp, so two builds of one book are the same book, not the same
file. The assertions are on the rendered text -- which carries the word lists,
the grids' letters and the answer key.

No external or paid API call is made by any test in this file: every build
runs in topic mode against the local vocabulary.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from pypdf import PdfReader  # noqa: E402

from services import product as product_module  # noqa: E402
from services.word_search.seeding import stable_word_search_seed  # noqa: E402

BOOK_FIELDS = {
    "title": "Garden Birds Word Search",
    "theme": "garden birds",
    "audience": "adults",
    "difficulty": "medium",
    "grid_size": "15",
    "output_type": "book",
    "worksheets": "2",
    "words_per_puzzle": "12",
    "include_answer_key": "yes",
    "word_source": "topic",
    "include_cover": "no",
}

SEED_INPUTS = {
    "product_title": "Garden Birds Word Search",
    "theme": "garden birds",
    "audience": "adults",
    "difficulty": "medium",
    "grid_size": 15,
    "number_of_puzzles": 2,
    "words_per_puzzle": 12,
    "mode": "topic",
    "custom_words": "ROBIN\nWREN\nFINCH\nSWIFT\n",
}


def _rendered_fingerprint(payload: dict) -> str:
    pdf = base64.b64decode(payload["pdf_bytes"])
    pages = PdfReader(io.BytesIO(pdf)).pages
    text = "\n".join((page.extract_text() or "") for page in pages)
    assert text.strip(), "the word search PDF produced no extractable text"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TheSameBookRebuildsIdentically(unittest.TestCase):
    def test_one_saved_book_built_twice_gives_the_same_puzzles(self):
        first = product_module._word_search_pdf_payload(
            dict(BOOK_FIELDS), package_id="ws_reproducibility"
        )
        second = product_module._word_search_pdf_payload(
            dict(BOOK_FIELDS), package_id="ws_reproducibility"
        )
        self.assertEqual(
            _rendered_fingerprint(first),
            _rendered_fingerprint(second),
            "the same saved book rebuilt to a different set of puzzles -- the "
            "word search engine is being seeded from the clock again",
        )

    def test_saving_then_reopening_then_rebuilding_gives_the_same_book(self):
        """The path a customer actually takes, through the Saved Projects
        rebuild entry point."""
        first = product_module._word_search_pdf_payload(
            dict(BOOK_FIELDS), package_id="ws_saved_book"
        )
        saved = {
            "product_type": "word_search",
            "fields": first["fields"],
            "custom_words": first.get("custom_words") or "",
            "cover_design": first.get("cover_design"),
            "package_id": first["package_id"],
        }
        reopened = product_module.rebuild_word_search_pdf_from_data(saved)
        self.assertEqual(
            _rendered_fingerprint(first),
            _rendered_fingerprint(reopened),
            "reopening a saved word search and rebuilding it produced a "
            "different book from the one that was saved",
        )

    def test_the_answer_key_survives_reproducibility(self):
        payload = product_module._word_search_pdf_payload(
            dict(BOOK_FIELDS), package_id="ws_reproducibility"
        )
        pdf = base64.b64decode(payload["pdf_bytes"])
        text = "\n".join(
            (page.extract_text() or "") for page in PdfReader(io.BytesIO(pdf)).pages
        )
        self.assertIn("ANSWER", text.upper())


class TheCustomerPathSuppliesASeed(unittest.TestCase):
    def _captured_request(self, fields):
        captured = {}
        real = product_module.build_word_search_pdf

        def spy(request):
            captured["request"] = request
            return real(request)

        product_module.build_word_search_pdf = spy
        try:
            product_module._word_search_pdf_payload(dict(fields), package_id="ws_spy")
        finally:
            product_module.build_word_search_pdf = real
        return captured["request"]

    def test_the_request_carries_a_seed(self):
        request = self._captured_request(BOOK_FIELDS)
        self.assertIsNotNone(
            request.seed,
            "WordSearchPdfRequest.seed was left at None, so the engine will "
            "seed itself from the clock",
        )

    def test_a_different_difficulty_asks_for_different_puzzles(self):
        medium = self._captured_request(BOOK_FIELDS)
        hard = self._captured_request({**BOOK_FIELDS, "difficulty": "hard"})
        self.assertNotEqual(medium.seed, hard.seed)

    def test_an_explicit_seed_field_wins(self):
        request = self._captured_request({**BOOK_FIELDS, "word_search_seed": "24680"})
        self.assertEqual(request.seed, 24680)


class TheSeedDependsOnlyOnTheSettings(unittest.TestCase):
    def test_the_same_settings_give_the_same_seed(self):
        self.assertEqual(
            stable_word_search_seed(**SEED_INPUTS),
            stable_word_search_seed(**SEED_INPUTS),
        )

    def test_cosmetic_differences_do_not_move_the_seed(self):
        cosmetic = dict(SEED_INPUTS)
        cosmetic["product_title"] = "  garden BIRDS   word search "
        cosmetic["custom_words"] = "robin\n\n  wren  \nFINCH\nswift\n\n"
        self.assertEqual(
            stable_word_search_seed(**SEED_INPUTS),
            stable_word_search_seed(**cosmetic),
        )

    def test_every_puzzle_shaping_setting_moves_the_seed(self):
        base = stable_word_search_seed(**SEED_INPUTS)
        for field, value in (
            ("theme", "garden insects"),
            ("audience", "children"),
            ("difficulty", "hard"),
            ("grid_size", 17),
            ("number_of_puzzles", 3),
            ("words_per_puzzle", 14),
            ("mode", "custom_word_list"),
            ("custom_words", "ROBIN\nWREN\nFINCH\nHERON\n"),
        ):
            with self.subTest(field=field):
                self.assertNotEqual(
                    base, stable_word_search_seed(**{**SEED_INPUTS, field: value})
                )

    def test_the_seed_is_the_same_in_every_process(self):
        """A recorded value, so a silent change to the derivation is caught."""
        self.assertEqual(stable_word_search_seed(**SEED_INPUTS), 1579049514)

    def test_the_seed_stays_inside_the_engines_range(self):
        for puzzles in (1, 12, 60):
            with self.subTest(puzzles=puzzles):
                seed = stable_word_search_seed(
                    **{**SEED_INPUTS, "number_of_puzzles": puzzles}
                )
                self.assertGreaterEqual(seed, 0)
                # book.py offsets by index + attempt * 97
                self.assertLess(seed + puzzles + (97 * 12), 2 ** 31)


if __name__ == "__main__":
    unittest.main()
