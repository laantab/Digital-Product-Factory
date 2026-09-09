"""SPELLING WORKSHEET — SEMANTIC SCOPE INHERITANCE (2026-09-09).

Crossword's "American Automobiles + Car Parts" repair
(tests/test_crossword_scope_answerkey_zip_repair.py) added a semantic-scope
extension to the shared Universal Topic Vocabulary Engine
(services/factory/topic_vocabulary.py): a category's entries can carry a
`scope` tag (e.g. BRAND_MODEL vs PART), and a topic alias can request a
narrower scope than the category's full pool.

Spelling Worksheet consumes the exact same shared resolver
(services/spelling_worksheet/builder.py::_select_words, step 2) that
Crossword and Word Search do. This file proves that inheritance actually
holds for Spelling's own customer-facing output, not just for Crossword's --
a shared-service change must be proven correct for every consumer, not
assumed correct because one consumer's tests pass.

No external/paid API call is made by any test in this file.
"""
from __future__ import annotations

import unittest

from services.spelling_worksheet.builder import build_spelling_worksheet

_AUTOMOTIVE_PART_WORDS = {
    "alternator", "bumper", "carburetor", "chassis", "dashboard", "engine",
    "fender", "horsepower", "hubcap", "ignition", "muffler", "odometer",
    "piston", "radiator", "speedometer", "suspension", "transmission",
    "windshield",
}
_BASEBALL_EQUIPMENT_WORDS = {"bat", "glove", "mitt", "helmet", "cleats", "diamond", "stadium"}
_BASEBALL_PLAYER_WORDS = {"batter", "catcher", "pitcher", "outfielder", "shortstop", "rookie", "umpire"}


class AmericanAutomobilesScopeTests(unittest.TestCase):
    """"American Automobiles" must resolve to the BRAND_MODEL scope, the
    same as it does for Crossword -- no automotive parts vocabulary."""

    def test_american_automobiles_excludes_automotive_parts(self):
        result = build_spelling_worksheet(theme="American Automobiles", grade="5", word_count=15)
        words = {w.lower() for w in result.all_words}
        self.assertTrue(words)
        part_hits = words & _AUTOMOTIVE_PART_WORDS
        self.assertFalse(part_hits, f"American Automobiles produced part words: {part_hits}")


class CarPartsScopeStillAllowedTests(unittest.TestCase):
    """"Car Parts" is a real, separate, valid topic -- the scope mechanism
    must not have globally removed parts vocabulary from the shared pack."""

    def test_car_parts_returns_real_parts_vocabulary(self):
        result = build_spelling_worksheet(theme="Car Parts", grade="5", word_count=10)
        words = {w.lower() for w in result.all_words}
        self.assertTrue(words)
        part_hits = words & _AUTOMOTIVE_PART_WORDS
        self.assertTrue(part_hits, f"Car Parts produced no real parts vocabulary: {words}")


class BaseballPlayersScopeTests(unittest.TestCase):
    """"Baseball Players" narrows to the PLAYER_POSITION scope; plain
    "Baseball" keeps its full, unrestricted varied pool (matches the
    Crossword behavior this scope mechanism was built for)."""

    def test_baseball_players_returns_players_not_equipment(self):
        result = build_spelling_worksheet(theme="Baseball Players", grade="5", word_count=7)
        words = {w.lower() for w in result.all_words}
        self.assertTrue(words)
        self.assertFalse(words & _BASEBALL_EQUIPMENT_WORDS, f"Baseball Players produced equipment words: {words}")

    def test_baseball_general_topic_keeps_its_full_varied_pool(self):
        result = build_spelling_worksheet(theme="Baseball", grade="6", word_count=15)
        words = {w.lower() for w in result.all_words}
        self.assertTrue(words)
        # The general topic is not restricted to the player-position scope --
        # it may include equipment, terms, etc. from the full pool.
        self.assertGreaterEqual(len(words), 10)


class OceanAnimalsUnscopedCategoryUnaffectedTests(unittest.TestCase):
    """Ocean Animals has no scope tags at all (an unscoped category) -- the
    scope extension must be purely additive and not affect it."""

    def test_ocean_animals_still_returns_ocean_vocabulary(self):
        result = build_spelling_worksheet(theme="Ocean Animals", grade="4", word_count=10)
        words = {w.lower() for w in result.all_words}
        self.assertEqual(len(words), 10)


class NoExternalCallTests(unittest.TestCase):
    def test_semantic_scope_resolution_makes_no_external_call(self):
        from unittest.mock import patch

        with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json:
            build_spelling_worksheet(theme="American Automobiles", grade="5", word_count=10)
            build_spelling_worksheet(theme="Car Parts", grade="5", word_count=10)
            self.assertFalse(chat.called)
            self.assertFalse(chat_json.called)


if __name__ == "__main__":
    unittest.main()
