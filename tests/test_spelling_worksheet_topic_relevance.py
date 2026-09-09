"""SPELLING WORKSHEET — COMPLETE, CERTIFY, AND RELEASE (2026-09-09).

Step 3 regression: reproduce the real, observed defect BEFORE any fix.

Topic "Ocean Animals" returned safari/zoo vocabulary (elephant, giraffe,
tiger, lion, zebra...) instead of ocean vocabulary. Root cause: the local
`_match_topic_bank()` in services/spelling_worksheet/builder.py does an
unordered substring scan over `_TOPIC_BANKS` -- the generic "animals" key
(safari words) is a substring match for "ocean animals" and happens to be
defined earlier in the dict than the real "ocean" bank, so it wins by
iteration order, not relevance. This is the same class of defect already
fixed for Crossword and Word Search by the Universal Topic Vocabulary
Engine (services/factory/topic_vocabulary.py).

This test MUST fail against the pre-fix implementation.
"""
from __future__ import annotations

import unittest

from services.spelling_worksheet.builder import build_spelling_worksheet

_OCEAN_WORDS = {
    "dolphin", "whale", "shark", "octopus", "seal", "crab", "lobster",
    "coral", "tuna", "squid", "starfish", "jellyfish", "seahorse",
    "reef", "tide", "current", "anchor", "sailor", "krill", "eel",
    "clam", "oyster", "shell", "harbor", "lighthouse", "voyage",
}
_SAFARI_WORDS = {"elephant", "giraffe", "tiger", "lion", "zebra", "monkey"}


class OceanAnimalsTopicRelevanceRegressionTests(unittest.TestCase):
    def test_ocean_animals_returns_ocean_vocabulary_not_safari(self):
        result = build_spelling_worksheet(theme="Ocean Animals", grade="3", word_count=10)
        words = {w.lower() for w in result.all_words}
        self.assertTrue(words, "no words were produced at all")
        safari_hits = words & _SAFARI_WORDS
        self.assertFalse(
            safari_hits,
            f"'Ocean Animals' produced safari/zoo words instead of ocean words: {safari_hits}",
        )
        ocean_hits = words & _OCEAN_WORDS
        self.assertTrue(
            ocean_hits,
            f"'Ocean Animals' produced no recognizable ocean vocabulary at all: {words}",
        )


if __name__ == "__main__":
    unittest.main()
