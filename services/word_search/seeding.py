"""A word search book must not depend on what time it was built.

The same defect Crossword had, in the sibling generator
-------------------------------------------------------
``services/product.py`` built every ``WordSearchPdfRequest`` with an explicit
``seed=None``. ``services/word_search/book.py`` forwards that ``None`` down to
``services/word_search/engine.py``, which does ``random.Random(seed)``, and
``random.Random(None)`` seeds itself from the operating system.

Measured on the customer path at 390aaf8: one saved book, built three times
with nothing changed, produced three different sets of grids
(``afead480f1d2``, ``3eb314f3be75``, ``9d00dc852a15`` over the rendered text).
A customer who reopened a saved book and rebuilt it got different puzzles from
the ones they had proof-read, and an answer key that no longer described them.

Crossword's fix shipped in v1.9.2 as ``services/crossword/seeding.py``. This is
the same idea for Word Search, deliberately written as its own module rather
than shared: Crossword is a separately LOCKED function, and importing across
the two would mean unlocking both every time either changed. The duplication
is four small functions and is the cheaper of the two costs.

Deliberately NOT part of the seed, for the same reasons as Crossword:
``package_id`` (``services/product.py`` falls back to a fresh ``uuid4``), and
capitalisation, padding and blank lines, which do not move a single letter in a
grid.
"""
from __future__ import annotations

import hashlib

#: The engine adds per-puzzle and per-attempt offsets to the seed (see
#: services/word_search/book.py, which uses index + attempt * 97), so the base
#: seed stays well inside the signed 32-bit range on every platform.
SEED_MODULUS = 2 ** 31 - 1_000_000

_FIELD_SEPARATOR = "\x1f"


def _normalise_text(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def _normalise_number(value: object) -> str:
    try:
        return str(int(str(value).strip()))
    except (TypeError, ValueError):
        return _normalise_text(value)


def _normalise_word_list(value: object) -> str:
    lines = [line.strip().casefold() for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line)


def stable_word_search_seed(
    *,
    product_title: object,
    theme: object,
    audience: object,
    difficulty: object,
    grid_size: object,
    number_of_puzzles: object,
    words_per_puzzle: object,
    mode: object,
    custom_words: object,
) -> int:
    """A seed that depends only on what the puzzles are made of.

    Same inputs -> same integer, in this process, in the next one, and on the
    builder. Different inputs -> a different integer.
    """
    parts = (
        _normalise_text(product_title),
        _normalise_text(theme),
        _normalise_text(audience),
        _normalise_text(difficulty),
        _normalise_number(grid_size),
        _normalise_number(number_of_puzzles),
        _normalise_number(words_per_puzzle),
        _normalise_text(mode),
        _normalise_word_list(custom_words),
    )
    digest = hashlib.sha256(_FIELD_SEPARATOR.join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % SEED_MODULUS
