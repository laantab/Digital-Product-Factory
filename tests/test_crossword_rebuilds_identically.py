"""CROSSWORD REPRODUCIBILITY -- the same saved book must rebuild identically.

The defect (measured on the customer path at 53a41c9, v1.9.1)
-------------------------------------------------------------
``services.product._crossword_pdf_payload`` built every ``CrosswordPdfRequest``
without passing ``seed``. The field defaults to ``None``,
``services/crossword/book.py`` forwards that ``None`` to
``services/crossword/engine.py``, and the engine calls ``random.Random(None)``,
which seeds itself from the operating system.

Building one unchanged book three times produced three different sets of grids
and three different clue numberings. The resolved word list was byte-identical
every time, so topic vocabulary was never the cause -- only the missing seed
was. A customer who reopened a saved book and rebuilt it after correcting a
subtitle got a different book of puzzles from the one they had proof-read, and
the answer key they had already checked no longer described their puzzles.

What is guaranteed here
-----------------------
The *puzzles* are reproducible, not the PDF file's bytes. Two builds of one
book render the same grids, the same clues and the same answer key, but the
PDF container still carries a fresh creation timestamp and document id, so the
files are not byte-identical and are not asserted to be. The customer-visible
promise is "the same book", not "the same bytes".

No external or paid API call is made by any test in this file: every build runs
in topic mode with ``use_ai_words=False``.
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
from services.crossword.seeding import stable_crossword_seed  # noqa: E402

BOOK_FIELDS = {
    "title": "Garden Birds Crossword",
    "theme": "garden birds",
    "sub_topic": "garden birds",
    "difficulty": "medium",
    "grid_size": "15",
    "output_type": "book",
    "worksheets": "2",
    "words_per_puzzle": "10",
    "include_answer_key": "yes",
    "word_source": "topic",
    "include_cover": "no",
}

SEED_INPUTS = {
    "product_title": "Garden Birds Crossword",
    "theme": "garden birds",
    "sub_topic": "garden birds",
    "difficulty": "medium",
    "grid_size": 15,
    "number_of_puzzles": 2,
    "words_per_puzzle": 10,
    "mode": "topic",
    "custom_words": "ROBIN\nWREN\nFINCH\nSWIFT\n",
}


def _rendered_fingerprint(payload: dict) -> str:
    """Everything the customer can actually read, as one digest.

    Extracted text covers the clue lists, the numbering and the answer key --
    the three things that moved between builds while the defect was live.
    """
    pdf = base64.b64decode(payload["pdf_bytes"])
    pages = PdfReader(io.BytesIO(pdf)).pages
    text = "\n".join((page.extract_text() or "") for page in pages)
    assert text.strip(), "the crossword PDF produced no extractable text"
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TheSameBookRebuildsIdentically(unittest.TestCase):
    """The end-to-end contract, through the real customer payload builder."""

    def test_one_saved_book_built_twice_gives_the_same_puzzles(self):
        first = product_module._crossword_pdf_payload(
            dict(BOOK_FIELDS), package_id="reproducibility_fixture"
        )
        second = product_module._crossword_pdf_payload(
            dict(BOOK_FIELDS), package_id="reproducibility_fixture"
        )
        self.assertEqual(
            _rendered_fingerprint(first),
            _rendered_fingerprint(second),
            "the same saved book rebuilt to a different set of puzzles -- the "
            "crossword engine is being seeded from the clock again",
        )

    def test_saving_then_reopening_then_rebuilding_gives_the_same_book(self):
        """The path a customer actually takes: build, save, reopen, rebuild.

        ``rebuild_crossword_pdf_from_data`` is what the Saved Projects screen
        calls. It replays the saved fields and the saved word list, so it must
        land on the same seed and therefore the same book.
        """
        first = product_module._crossword_pdf_payload(
            dict(BOOK_FIELDS), package_id="saved_book"
        )
        saved = {
            "product_type": "crossword",
            "fields": first["fields"],
            "custom_words": first["custom_words"],
            "cover_design": first.get("cover_design"),
            "package_id": first["package_id"],
            "crossword_meta": first["crossword_meta"],
        }
        reopened = product_module.rebuild_crossword_pdf_from_data(saved)
        self.assertEqual(
            _rendered_fingerprint(first),
            _rendered_fingerprint(reopened),
            "reopening a saved crossword and rebuilding it produced a "
            "different book from the one that was saved",
        )

    def test_the_answer_key_survives_reproducibility(self):
        """Determinism must not have been bought by dropping the answer key."""
        payload = product_module._crossword_pdf_payload(
            dict(BOOK_FIELDS), package_id="reproducibility_fixture"
        )
        pdf = base64.b64decode(payload["pdf_bytes"])
        text = "\n".join(
            (page.extract_text() or "") for page in PdfReader(io.BytesIO(pdf)).pages
        )
        self.assertIn("ANSWER", text.upper())
        placed = (payload.get("word_placement") or {}).get("placed_words") or []
        self.assertGreaterEqual(
            len(placed), 4, "a usable crossword must place at least four words"
        )


class TheCustomerPathSuppliesASeed(unittest.TestCase):
    """The precise defect, pinned without paying for a full build."""

    def _captured_request(self, fields):
        captured = {}
        real = product_module.build_crossword_pdf

        def spy(request):
            captured["request"] = request
            return real(request)

        product_module.build_crossword_pdf = spy
        try:
            product_module._crossword_pdf_payload(dict(fields), package_id="spy_pkg")
        finally:
            product_module.build_crossword_pdf = real
        return captured["request"]

    def test_the_request_carries_a_seed(self):
        request = self._captured_request(BOOK_FIELDS)
        self.assertIsNotNone(
            request.seed,
            "CrosswordPdfRequest.seed was left at None, so the engine will "
            "seed itself from the clock",
        )

    def test_a_different_difficulty_asks_for_different_puzzles(self):
        medium = self._captured_request(BOOK_FIELDS)
        hard = self._captured_request({**BOOK_FIELDS, "difficulty": "hard"})
        self.assertNotEqual(medium.seed, hard.seed)

    def test_an_explicit_seed_field_wins(self):
        request = self._captured_request({**BOOK_FIELDS, "crossword_seed": "12345"})
        self.assertEqual(request.seed, 12345)


class TheSeedDependsOnlyOnTheSettings(unittest.TestCase):
    def test_the_same_settings_give_the_same_seed(self):
        self.assertEqual(
            stable_crossword_seed(**SEED_INPUTS), stable_crossword_seed(**SEED_INPUTS)
        )

    def test_cosmetic_differences_do_not_move_the_seed(self):
        cosmetic = dict(SEED_INPUTS)
        cosmetic["product_title"] = "  garden BIRDS   crossword "
        cosmetic["custom_words"] = "robin\n\n  wren  \nFINCH\nswift\n\n"
        self.assertEqual(
            stable_crossword_seed(**SEED_INPUTS), stable_crossword_seed(**cosmetic)
        )

    def test_every_puzzle_shaping_setting_moves_the_seed(self):
        base = stable_crossword_seed(**SEED_INPUTS)
        for field, value in (
            ("theme", "garden insects"),
            ("difficulty", "hard"),
            ("grid_size", 17),
            ("number_of_puzzles", 3),
            ("words_per_puzzle", 12),
            ("mode", "custom_word_list"),
            ("custom_words", "ROBIN\nWREN\nFINCH\nHERON\n"),
        ):
            with self.subTest(field=field):
                self.assertNotEqual(
                    base, stable_crossword_seed(**{**SEED_INPUTS, field: value})
                )

    def test_the_seed_is_the_same_in_every_process(self):
        """A recorded value, so a silent change to the derivation is caught.

        If this ever has to move, every already-built book changes with it --
        that is the decision this assertion forces someone to make on purpose.
        """
        self.assertEqual(stable_crossword_seed(**SEED_INPUTS), 392364394)

    def test_the_seed_stays_inside_the_engines_range(self):
        for puzzles in (1, 12, 60):
            with self.subTest(puzzles=puzzles):
                seed = stable_crossword_seed(
                    **{**SEED_INPUTS, "number_of_puzzles": puzzles}
                )
                self.assertGreaterEqual(seed, 0)
                self.assertLess(seed + (puzzles * 31) + 1000, 2 ** 31)


if __name__ == "__main__":
    unittest.main()
