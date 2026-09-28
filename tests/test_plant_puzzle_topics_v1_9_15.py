"""v1.9.15: plant topics make real plant puzzles in Crossword and Word Search.

Before this release:

* "House plants" had no curated word list. Word Search fell back to the old
  keyword scoring, matched the word "plants" to the plant_parts anatomy pack
  and printed PETAL, SEPAL, POLLEN, CHLOROPHYLL; Crossword refused the topic.
* "Herb Garden" and "Garden Plants" went the same way in both products
  (LEAF, ROOT, STEM, PETAL, SEPAL ...), because "garden" and "plants" are
  keywords of the anatomy pack.
* A Create From Topic word-search book that was short of topic words was
  padded with generic puzzle words (WORD, FIND, PUZZLE, FUN, EXPLORE), and
  a book whose words-per-puzzle had been reduced then failed its own QA
  ("has 8 word(s) but 10 were requested").
* A crossword book that needed recovery was rebuilt from a broad fallback
  pack: a 12-puzzle "Garden Plants" book came back full of ELEPHANT,
  TORNADO and WHALE.

Now each topic resolves to its own curated pack (words and clues) in
data/topic_vocabulary_packs.json, shared by both products; topic books are
never padded with generic or unrelated words, and are made smaller instead.
No paid or AI call is made anywhere in this file.
"""
from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from services.crossword.crossword_fallback import get_fallback_words_and_clues, select_fallback_pack
from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf
from services.crossword.word_entries import suggest_crossword_words_from_topic
from services.factory.topic_vocabulary import resolve_topic_category
from services.word_search.pdf_builder import WordSearchPdfRequest, build_word_search_pdf
from services.word_search.word_lists import (
    parse_custom_word_list, suggest_words_from_topic, supplement_entries_to_count,
)

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load(name):
    with open(os.path.join(_ROOT, "data", name), encoding="utf-8") as fh:
        return json.load(fh)


PACKS = _load("topic_vocabulary_packs.json")
GENERIC = {w.upper() for w in _load("word_search_topics.json")["generic_fallback"]}
ANATOMY = {"PETAL", "SEPAL", "POLLEN", "CHLOROPHYLL", "STAMEN", "PISTIL", "XYLEM", "PHLOEM",
           "STOMATA", "COTYLEDON", "PETIOLE"}

# Each topic in every way a customer types it: capitalization, extra
# spaces, hyphens, run together.
TOPICS = {
    "house_plants": ["House Plants", "house plants", "HOUSE PLANTS", "  House   Plants ",
                     "House-Plants", "house-plants", "Houseplants", "HousePlants",
                     "Indoor plants", "house plant care"],
    "herb_garden": ["Herb Garden", "herb garden", "HERB GARDEN", "  Herb   Garden ",
                    "Herb-Garden", "herb-garden", "Herbgarden", "HerbGarden",
                    "Herb gardening", "Kitchen herb garden"],
    "garden_plants": ["Garden Plants", "garden plants", "GARDEN PLANTS", "  Garden   Plants ",
                      "Garden-Plants", "garden-plants", "Gardenplants", "GardenPlants",
                      "Plants for the garden", "Garden flowers"],
}
BOOK_THEME = {"house_plants": "House Plants", "herb_garden": "Herb Garden",
              "garden_plants": "Garden Plants"}


def _norm(words):
    return {str(w).upper().replace(" ", "") for w in words}


def _pack(category):
    return set(PACKS[category]["entries"])


def _clue(category, answer):
    entry = PACKS[category]["entries"][answer]
    return entry if isinstance(entry, str) else entry["clue"]


def _no_ai():
    return patch("services.crossword.word_entries.fetch_crossword_words_from_ai",
                 side_effect=AssertionError("no AI call"))


class PacksAreRealAndClean(unittest.TestCase):
    def test_each_plant_pack_has_enough_distinct_relevant_entries(self):
        for category in TOPICS:
            with self.subTest(category=category):
                entries = PACKS[category]["entries"]
                self.assertGreaterEqual(len(entries), 45)
                # Crossword places words of at most 9 letters.
                self.assertGreaterEqual(len([w for w in entries if len(w) <= 9]), 40)
                clues = [_clue(category, w) for w in entries]
                self.assertEqual(len(clues), len(set(clues)), "every clue is different")
                self.assertFalse(set(entries) & GENERIC, "no generic puzzle words")
                self.assertFalse(set(entries) & ANATOMY, "no flower-anatomy words")
                for word in entries:
                    self.assertRegex(word, r"^[A-Z]{3,15}$")
                    self.assertFalse([o for o in entries if o != word and word in o],
                                     f"{word} hides inside another word")


class EveryPhrasingResolves(unittest.TestCase):
    def test_every_phrasing_resolves_to_its_own_pack(self):
        for category, phrasings in TOPICS.items():
            for topic in phrasings:
                with self.subTest(topic=topic):
                    self.assertEqual(resolve_topic_category(topic)[0], category)

    def test_word_search_words_come_only_from_the_topic_pack(self):
        for category, phrasings in TOPICS.items():
            for topic in phrasings:
                with self.subTest(topic=topic):
                    words, _w, errors, pack_id = suggest_words_from_topic(topic, "", max_words=40)
                    self.assertFalse(errors)
                    self.assertEqual(pack_id, category)
                    got = _norm(words)
                    self.assertGreaterEqual(len(got), 40)
                    self.assertTrue(got <= _pack(category), got - _pack(category))

    def test_crossword_words_come_only_from_the_topic_pack(self):
        for category, phrasings in TOPICS.items():
            for topic in phrasings:
                with self.subTest(topic=topic), _no_ai():
                    words, _w, errors = suggest_crossword_words_from_topic(topic, max_words=60)
                    self.assertFalse(errors)
                    got = _norm(words)
                    self.assertGreaterEqual(len(got), 40)
                    self.assertTrue(got <= _pack(category), got - _pack(category))

    def test_no_broad_fallback_pack_for_a_curated_topic(self):
        for category, phrasings in TOPICS.items():
            for topic in phrasings:
                with self.subTest(topic=topic):
                    self.assertEqual(select_fallback_pack(topic), "")
                    self.assertEqual(get_fallback_words_and_clues(topic, count=20), ([], {}))


class WordSearchBooks(unittest.TestCase):
    """The customer's defaults: 10 words per puzzle, from the topic only."""

    def _book(self, theme, puzzles):
        return build_word_search_pdf(WordSearchPdfRequest(
            product_title=theme, theme=theme, mode="topic", number_of_puzzles=puzzles,
            words_per_puzzle=10, output_type="book", include_answer_key=True, include_cover=False))

    def test_each_topic_book_uses_only_its_own_words(self):
        for category, theme in BOOK_THEME.items():
            for puzzles in (6, 10):
                with self.subTest(topic=theme, puzzles=puzzles):
                    result = self._book(theme, puzzles)
                    self.assertFalse(result.errors)
                    self.assertTrue(result.pdf_bytes)
                    banks = [_norm(p.word_bank) for p in result.puzzles]
                    every = set().union(*banks)
                    self.assertTrue(every <= _pack(category), every - _pack(category))
                    self.assertFalse(every & GENERIC)
                    self.assertEqual(sum(len(b) for b in banks), len(every), "a word repeats")

    def test_a_short_topic_book_is_made_smaller_not_padded(self):
        result = self._book("Herb Garden", 20)
        self.assertFalse(result.errors)
        self.assertTrue(result.pdf_bytes)
        self.assertLess(len(result.puzzles), 20)
        every = set().union(*[_norm(p.word_bank) for p in result.puzzles])
        self.assertTrue(every <= _pack("herb_garden"))

    def test_topic_top_up_never_adds_generic_words(self):
        entries = parse_custom_word_list("Basil\nThyme\nSage\nMint", grid_size=15).entries
        topped, _w = supplement_entries_to_count(entries, 20, grid_size=15, topic="Herb Garden",
                                                 matched_pack_id="herb_garden", allow_generic=False)
        self.assertFalse(_norm(e.display for e in topped) & GENERIC)


class CrosswordBooks(unittest.TestCase):
    def _book(self, theme, puzzles):
        with _no_ai():
            return build_crossword_pdf(CrosswordPdfRequest(
                product_title=theme, theme=theme, mode="topic", number_of_puzzles=puzzles,
                output_type="book", include_answer_key=True, include_cover=False))

    def _assert_topic_only(self, result, category):
        self.assertFalse(result.errors)
        self.assertTrue(result.pdf_bytes)
        valid = [p for p in result.puzzles if not p.errors and p.clues]
        self.assertGreaterEqual(len(valid), 1)
        for puzzle in valid:
            answers = [c.answer.upper() for c in puzzle.clues]
            self.assertTrue(set(answers) <= _pack(category), set(answers) - _pack(category))
            for c in puzzle.clues:
                self.assertEqual(c.clue.strip(), _clue(category, c.answer.upper()))
        return valid

    def test_each_topic_book_uses_its_own_words_and_clues(self):
        for category, theme in BOOK_THEME.items():
            with self.subTest(topic=theme):
                valid = self._assert_topic_only(self._book(theme, 6), category)
                self.assertGreaterEqual(len(valid), 5)

    def test_a_book_that_needs_recovery_is_never_filled_from_another_pack(self):
        """12 puzzles of "Garden Plants" needed recovery and came back as
        NATURE_PACK words (ELEPHANT, TORNADO, WHALE)."""
        self._assert_topic_only(self._book("Garden Plants", 12), "garden_plants")


if __name__ == "__main__":
    unittest.main()
