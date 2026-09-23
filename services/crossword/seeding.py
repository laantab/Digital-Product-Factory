"""A crossword book must not depend on what time it was built.

The defect this file exists to close
------------------------------------
Until v1.9.2, ``services/product.py`` built every ``CrosswordPdfRequest``
without passing ``seed``. ``CrosswordPdfRequest.seed`` defaults to ``None``,
``services/crossword/book.py`` forwards that ``None`` down to
``services/crossword/engine.py``, and the engine does ``random.Random(seed)``.
``random.Random(None)`` seeds itself from the operating system, so every build
started from a different random stream.

Measured on the customer path at 53a41c9: the same saved book, rebuilt three
times with no field changed, produced three different sets of grids and three
different clue numberings. The word list was identical every time -- topic
vocabulary resolution was never the problem -- so a customer who rebuilt after
fixing a typo in the subtitle got a book of different puzzles from the one
they had already proof-read.

The fix
-------
Derive the seed from the things that decide what the puzzles are. The same
saved book with the same settings hashes to the same seed and therefore
rebuilds to the same puzzles; change the theme, the difficulty, the grid size,
the puzzle count or the word list and the seed moves with it, so an edited
book gets puzzles that match its new settings.

Deliberately NOT part of the seed:

* ``package_id`` -- ``services/product.py`` falls back to a fresh
  ``uuid.uuid4().hex`` when no package id is supplied, which would put a random
  value straight back into the seed.
* the title's capitalisation and surrounding whitespace, and blank lines in the
  word list -- these do not change a single square of a grid, so they must not
  change the puzzles either.

``hashlib.sha256`` rather than ``hash()``: Python randomises ``hash()`` per
process unless ``PYTHONHASHSEED`` is set, which is exactly the kind of hidden
clock dependency this module exists to remove.
"""
from __future__ import annotations

import hashlib

# The engine adds small offsets to the seed per puzzle and per retry attempt
# (see services/crossword/book.py). Keeping the base seed well inside the
# signed 32-bit range leaves room for those offsets on every platform.
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
    """The word list as the engine will actually see it.

    Blank lines and per-line whitespace do not reach the grid, so they must not
    reach the seed either -- otherwise re-saving a project through a form that
    normalises line endings would silently reshuffle the customer's puzzles.
    """
    lines = [line.strip().casefold() for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line)


def stable_crossword_seed(
    *,
    product_title: object,
    theme: object,
    sub_topic: object,
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
        _normalise_text(sub_topic),
        _normalise_text(difficulty),
        _normalise_number(grid_size),
        _normalise_number(number_of_puzzles),
        _normalise_number(words_per_puzzle),
        _normalise_text(mode),
        _normalise_word_list(custom_words),
    )
    digest = hashlib.sha256(_FIELD_SEPARATOR.join(parts).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % SEED_MODULUS
