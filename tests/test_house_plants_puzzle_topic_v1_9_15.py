"""v1.9.15: "House plants" makes real house-plant puzzles in both products.

Before: the shared topic resolver (services/factory/topic_vocabulary.py) had
no house-plant pack, so both engines fell through to their own older keyword
scoring, which matched the word "plants" to the plant_parts anatomy pack.
Word Search then shipped LEAF, PETAL, SEPAL, POLLEN, CHLOROPHYLL -- flower
anatomy, not house plants -- and Crossword refused the topic outright
("matched a small local vocabulary pack (12 words) ...").

Now a curated house_plants pack resolves the topic for both products, from
the same data, with no paid call.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf
from services.crossword.word_entries import suggest_crossword_words_from_topic
import json
import os

from services.factory.topic_vocabulary import resolve_topic_category
from services.word_search.pdf_builder import WordSearchPdfRequest, build_word_search_pdf
from services.word_search.word_lists import suggest_words_from_topic

_PACKS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "topic_vocabulary_packs.json")


def load_topic_packs_for_tests():
    with open(_PACKS, encoding="utf-8") as fh:
        return json.load(fh)


TOPICS = ["House plants", "House Plants", "Houseplants", "Indoor plants", "Potted plants",
          "house plant care"]
PLANT_PARTS_ANATOMY = {"PETAL", "SEPAL", "POLLEN", "CHLOROPHYLL", "STAMEN", "PISTIL"}


def _norm(words):
    return {str(w).upper().replace(" ", "") for w in words}


class HousePlantsResolvesToHousePlants(unittest.TestCase):
    def test_every_phrasing_resolves_to_the_house_plants_pack(self):
        for topic in TOPICS:
            with self.subTest(topic=topic):
                self.assertEqual(resolve_topic_category(topic)[0], "house_plants")

    def test_word_search_words_are_house_plants_not_flower_anatomy(self):
        pack = _norm(load_topic_packs_for_tests()["house_plants"]["entries"])
        for topic in TOPICS:
            with self.subTest(topic=topic):
                words, _warnings, errors, _pack_id = suggest_words_from_topic(topic, "", max_words=12)
                self.assertFalse(errors, topic)
                got = _norm(words)
                self.assertGreaterEqual(len(got), 10)
                self.assertTrue(got <= pack, f"{topic}: words outside the house-plant pack: {got - pack}")
                self.assertFalse(got & PLANT_PARTS_ANATOMY)

    def test_crossword_words_are_house_plants(self):
        pack = _norm(load_topic_packs_for_tests()["house_plants"]["entries"])
        for topic in TOPICS:
            with self.subTest(topic=topic):
                words, _warnings, errors = suggest_crossword_words_from_topic(topic, max_words=12)
                self.assertFalse(errors, topic)
                self.assertTrue(_norm(words) <= pack)


class HousePlantsCustomerPathPdfs(unittest.TestCase):
    """The customer's default request, first attempt, no custom words, no AI."""

    def test_crossword_book(self):
        with patch("services.crossword.word_entries.fetch_crossword_words_from_ai",
                   side_effect=AssertionError("no AI call")):
            result = build_crossword_pdf(CrosswordPdfRequest(
                product_title="House Plants", theme="House plants", mode="topic",
                number_of_puzzles=6, output_type="book",
                include_answer_key=True, include_cover=False))
        self.assertTrue(result.pdf_bytes, result.errors)
        self.assertFalse(result.errors)
        pack = _norm(load_topic_packs_for_tests()["house_plants"]["entries"])
        valid = [p for p in result.puzzles if not p.errors and p.clues]
        self.assertGreaterEqual(len(valid), 1)
        for puzzle in valid:
            answers = {c.answer.upper() for c in puzzle.clues}
            self.assertTrue(answers <= pack, f"non house-plant answers: {answers - pack}")
            clues = [c.clue.strip() for c in puzzle.clues]
            self.assertEqual(len(clues), len(set(clues)))
            self.assertTrue(all("Related to" not in c for c in clues))

    def test_word_search_book(self):
        result = build_word_search_pdf(WordSearchPdfRequest(
            product_title="House Plants", theme="House plants", mode="topic",
            number_of_puzzles=6, output_type="book",
            include_answer_key=True, include_cover=False))
        self.assertTrue(result.pdf_bytes, result.errors)
        self.assertFalse(result.errors)
        pack = _norm(load_topic_packs_for_tests()["house_plants"]["entries"])
        for puzzle in result.puzzles:
            bank = _norm(getattr(puzzle, "word_bank", []) or [])
            self.assertTrue(bank <= pack, f"non house-plant words: {bank - pack}")
            self.assertFalse(bank & PLANT_PARTS_ANATOMY)


if __name__ == "__main__":
    unittest.main()
