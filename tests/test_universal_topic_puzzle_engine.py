"""UNIVERSAL TOPIC PUZZLE ENGINE — Crossword + Word Search first-attempt
customer success (2026-09-08).

Formal regression coverage for the shared, zero-cost topic-vocabulary
resolver (services.factory.topic_vocabulary) and its wiring into both
Crossword (services.crossword.word_entries / services.crossword.clues /
services.crossword.book) and Word Search (services.word_search.word_lists /
services.word_search.book).

Mission under test: a customer can type almost any reasonable topic and
click Generate for EITHER product on the FIRST attempt, with zero paid AI
calls, no custom word list, and no custom clues -- the Factory does the
vocabulary/clue work. Custom words and custom clues, when supplied, must
still work.

This file is part of the Factory Golden Customer-Path Smoke Suite: any
future change to shared topic-vocabulary logic must keep every test in
this file green for BOTH product types (see Step 24 of the mission spec --
"Universal Topic Puzzle Engine" work log).
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from services.crossword.clues import simple_clue
from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf
from services.crossword.word_entries import suggest_crossword_words_from_topic
from services.factory.topic_vocabulary import (
    get_category_clues,
    get_category_words,
    resolve_topic_category,
    resolve_topic_vocabulary,
)
from services.word_search.pdf_builder import WordSearchPdfRequest, build_word_search_pdf
from services.word_search.word_lists import suggest_words_from_topic

# The 12 topics Step 17 requires, verbatim.
GOLDEN_TOPICS = [
    "American automobiles",
    "Container gardening",
    "Dog training",
    "Space exploration",
    "Healthy eating",
    "Photography",
    "Baseball",
    "Dinosaurs",
    "Personal finance",
    "World geography",
    "Camping",
    "Baking",
]

NONSENSE_TOPIC = "zxqv nebula spoons 9382"

# A real, representative custom word/clue set for American Automobiles --
# the same shape of list a customer would paste in (car makes, models, and
# hand-written clues), used to protect Steps 11/22 (custom word list and
# custom clues must keep working once topic-mode word selection changed).
CUSTOM_AUTO_WORD_CLUES = {
    "FORD": "American automaker founded by Henry Ford in 1903",
    "CHEVROLET": 'GM division nicknamed "Chevy"',
    "CADILLAC": "GM's flagship luxury vehicle brand",
    "JEEP": "Brand famous for off-road SUVs like the Wrangler",
    "TESLA": "Electric automaker founded in 2003",
    "MUSTANG": "Ford's iconic pony car, launched in 1964",
    "CORVETTE": "Chevrolet's iconic sports car",
    "RANGER": "Ford's compact pickup truck",
    "WRANGLER": "Jeep's iconic off-road 4x4",
    "SILVERADO": "Chevrolet's full-size pickup truck",
    "EXPLORER": "Ford's popular midsize SUV",
    "CAMARO": "Chevrolet's answer to the Mustang",
}


def _no_ai_patches():
    return patch("ai_client.chat"), patch("ai_client.chat_json")


class TopicVocabularyResolverTests(unittest.TestCase):
    """Steps 3-8: the shared resolver itself."""

    def test_all_12_golden_topics_resolve_to_a_real_local_category(self):
        for topic in GOLDEN_TOPICS:
            with self.subTest(topic=topic):
                result = resolve_topic_vocabulary(topic, target_count=40)
                self.assertTrue(result.matched, f"{topic!r} did not resolve")
                self.assertGreaterEqual(len(result.words), 15, topic)
                self.assertEqual(result.fallback_path, "shared_pack")

    def test_nonsense_topic_does_not_resolve(self):
        result = resolve_topic_vocabulary(NONSENSE_TOPIC, target_count=40)
        self.assertFalse(result.matched)
        self.assertIsNone(result.category)
        self.assertEqual(result.words, [])

    def test_no_false_positive_pack_match_for_dog_training(self):
        # Regression: crude keyword scoring previously matched "Dog
        # training" to "business_training" via the shared token "training".
        category, _confidence = resolve_topic_category("Dog training")
        self.assertEqual(category, "dog_training")
        words = get_category_words("dog_training")
        self.assertIn("SIT", [w.upper() for w in words])
        self.assertNotIn("BUDGET", [w.upper() for w in words])

    def test_no_false_positive_pack_match_for_baseball(self):
        # Regression: "Baseball" previously matched "chemistry" (ATOM,
        # MOLECULE) via crude keyword overlap.
        category, _confidence = resolve_topic_category("Baseball")
        self.assertEqual(category, "baseball")
        words = [w.upper() for w in get_category_words("baseball")]
        self.assertIn("PITCHER", words)
        self.assertNotIn("MOLECULE", words)

    def test_target_count_trims_but_never_pads(self):
        result = resolve_topic_vocabulary("American automobiles", target_count=5)
        self.assertTrue(result.matched)
        self.assertEqual(len(result.words), 5)
        # A category with fewer real words than requested must return
        # exactly what it has -- never fabricate/pad to hit target_count.
        full = resolve_topic_vocabulary("Camping", target_count=10_000)
        self.assertTrue(full.matched)
        self.assertEqual(full.words, get_category_words("camping"))

    def test_deduplicates_words_within_a_category(self):
        for topic in GOLDEN_TOPICS:
            with self.subTest(topic=topic):
                words = get_category_words(resolve_topic_category(topic)[0])
                normalized = [w.strip().upper() for w in words]
                self.assertEqual(len(normalized), len(set(normalized)), topic)


class ClueResolverTests(unittest.TestCase):
    """Steps 9-10: real, distinct, non-placeholder clues."""

    def test_curated_clues_are_never_the_generic_placeholder(self):
        for topic in GOLDEN_TOPICS:
            category, _ = resolve_topic_category(topic)
            self.assertIsNotNone(category, topic)
            clues = get_category_clues(category)
            self.assertTrue(clues, topic)
            for word, clue in clues.items():
                with self.subTest(topic=topic, word=word):
                    self.assertNotEqual(clue.strip().rstrip("."), f"Related to {topic}")
                    self.assertGreater(len(clue.strip()), 8)

    def test_simple_clue_uses_shared_pack_for_covered_topics(self):
        clue = simple_clue("MUSTANG", theme="American Automobiles")
        self.assertNotIn("Related to", clue)
        self.assertIn("pony car", clue.lower())

    def test_all_clues_in_a_category_are_distinct(self):
        for topic in GOLDEN_TOPICS:
            category, _ = resolve_topic_category(topic)
            clues = list(get_category_clues(category).values())
            with self.subTest(topic=topic):
                self.assertEqual(len(clues), len(set(clues)), topic)


class GoldenAcceptanceSuiteTests(unittest.TestCase):
    """Step 17: first-attempt success, no custom words, for all 12 topics,
    for BOTH Crossword and Word Search, at the default Full Book size.
    """

    def test_crossword_first_attempt_success_for_all_12_topics(self):
        for topic in GOLDEN_TOPICS:
            with self.subTest(topic=topic):
                req = CrosswordPdfRequest(
                    product_title=topic, theme=topic, mode="topic",
                    number_of_puzzles=12, output_type="book",
                    include_answer_key=True, include_cover=False,
                )
                result = build_crossword_pdf(req)
                self.assertTrue(result.pdf_bytes, f"{topic}: {result.errors}")
                self.assertFalse(result.errors, topic)
                valid = [p for p in result.puzzles if not p.errors and p.clues]
                self.assertGreaterEqual(len(valid), 1, topic)
                for puzzle in valid:
                    clue_texts = [entry.clue.strip() for entry in puzzle.clues]
                    self.assertEqual(
                        len(clue_texts), len(set(clue_texts)),
                        f"{topic}: duplicate clues in one puzzle",
                    )
                    for clue_text in clue_texts:
                        self.assertNotIn("Related to", clue_text)

    def test_word_search_first_attempt_success_for_all_12_topics(self):
        for topic in GOLDEN_TOPICS:
            with self.subTest(topic=topic):
                req = WordSearchPdfRequest(
                    product_title=topic, theme=topic, mode="topic",
                    number_of_puzzles=10, output_type="book",
                    include_answer_key=True, include_cover=False,
                )
                result = build_word_search_pdf(req)
                self.assertTrue(result.pdf_bytes, f"{topic}: {result.errors}")
                self.assertFalse(result.errors, topic)
                self.assertGreaterEqual(len(result.puzzles), 1, topic)


class SmallPackRegressionTests(unittest.TestCase):
    """Step 18: a topic with a local pack too small on its own must expand
    locally and succeed -- protects the exact regression first seen with
    American Automobiles.
    """

    def test_american_automobiles_succeeds_without_custom_words(self):
        req = CrosswordPdfRequest(
            product_title="American Automobiles", theme="American Automobiles",
            mode="topic", number_of_puzzles=12, output_type="book",
            include_answer_key=True, include_cover=False,
        )
        result = build_crossword_pdf(req)
        self.assertTrue(result.pdf_bytes, result.errors)
        self.assertFalse(result.errors)
        self.assertEqual(len(result.puzzles), 12)

    def test_a_small_local_pack_expands_rather_than_rejecting(self):
        # Container Gardening / Dinosaurs / Camping all have real packs
        # comfortably under the old 50-word MIN_POOL_FOR_VARIETY threshold
        # that used to reject them outright.
        for topic in ("Container gardening", "Dinosaurs", "Camping"):
            with self.subTest(topic=topic):
                words, warnings, errors = suggest_crossword_words_from_topic(topic, max_words=200)
                self.assertTrue(words, f"{topic}: {errors}")
                self.assertFalse(errors, topic)
                self.assertLess(len(get_category_words(resolve_topic_category(topic)[0])), 50)


class NonsenseTopicSafeFailureTests(unittest.TestCase):
    """Step 19: unsupported nonsense fails safely with a friendly message
    -- never with random unrelated (junk) words.
    """

    def test_crossword_fails_safely_not_with_junk(self):
        words, warnings, errors = suggest_crossword_words_from_topic(NONSENSE_TOPIC, max_words=60)
        self.assertFalse(words)
        self.assertTrue(errors)

    def test_word_search_fails_safely_not_with_junk_tokens(self):
        words, warnings, errors, matched_pack_id = suggest_words_from_topic(NONSENSE_TOPIC, max_words=20)
        # The literal gibberish tokens must never become actual puzzle
        # words -- the friendly error message may echo the topic name
        # back (see Step 16's own example), which is not the same thing.
        self.assertFalse(words)
        self.assertTrue(errors)
        self.assertNotIn("internal", " ".join(errors).lower())
        self.assertNotIn("pack", " ".join(errors).lower())

    def test_word_search_full_book_fails_safely_for_nonsense_topic(self):
        req = WordSearchPdfRequest(
            product_title=NONSENSE_TOPIC, theme=NONSENSE_TOPIC, mode="topic",
            number_of_puzzles=6, output_type="book",
        )
        result = build_word_search_pdf(req)
        self.assertFalse(result.pdf_bytes)
        self.assertTrue(result.errors)


class CustomWordAndClueTests(unittest.TestCase):
    """Steps 11/22: custom word list and custom clues still work, locally,
    with zero paid calls.
    """

    def test_crossword_custom_word_list_without_custom_clues_resolves_locally(self):
        req = CrosswordPdfRequest(
            product_title="American Automobiles", theme="American Automobiles",
            mode="custom_word_list",
            custom_words="\n".join(CUSTOM_AUTO_WORD_CLUES.keys()),
            number_of_puzzles=1, output_type="book",
            include_answer_key=True, include_cover=False,
        )
        with _no_ai_patches()[0] as chat, _no_ai_patches()[1] as chat_json:
            result = build_crossword_pdf(req)
            self.assertFalse(chat.called)
            self.assertFalse(chat_json.called)
        self.assertTrue(result.pdf_bytes, result.errors)
        clue_texts = [entry.clue.strip() for p in result.puzzles for entry in p.clues]
        self.assertEqual(len(clue_texts), len(set(clue_texts)))

    def test_crossword_custom_words_plus_custom_clues_uses_exact_supplied_text(self):
        req = CrosswordPdfRequest(
            product_title="American Automobiles", theme="American Automobiles",
            mode="custom_word_list",
            custom_words="\n".join(CUSTOM_AUTO_WORD_CLUES.keys()),
            custom_clues=dict(CUSTOM_AUTO_WORD_CLUES),
            number_of_puzzles=1, output_type="book",
            include_answer_key=True, include_cover=False,
        )
        result = build_crossword_pdf(req)
        self.assertTrue(result.pdf_bytes, result.errors)
        used_clues = {
            entry.answer.upper(): entry.clue.strip()
            for p in result.puzzles
            for entry in p.clues
        }
        for word, expected_clue in CUSTOM_AUTO_WORD_CLUES.items():
            if word in used_clues:
                self.assertEqual(used_clues[word], expected_clue)

    def test_word_search_custom_word_list_uses_words_directly(self):
        req = WordSearchPdfRequest(
            product_title="American Automobiles", theme="American Automobiles",
            mode="custom_word_list",
            custom_words="\n".join(CUSTOM_AUTO_WORD_CLUES.keys()),
            number_of_puzzles=1, output_type="book",
            include_answer_key=True, include_cover=False,
        )
        with _no_ai_patches()[0] as chat, _no_ai_patches()[1] as chat_json:
            result = build_word_search_pdf(req)
            self.assertFalse(chat.called)
            self.assertFalse(chat_json.called)
        self.assertTrue(result.pdf_bytes, result.errors)


class PuzzleCountVariationTests(unittest.TestCase):
    """Step 20: Single Page, small, and large book sizes are all honored
    (or adaptively, honestly, shrunk -- never forced to 12)."""

    def test_single_page_crossword(self):
        req = CrosswordPdfRequest(
            product_title="American Automobiles", theme="American Automobiles",
            mode="topic", output_type="single_page", include_answer_key=False,
            include_cover=False,
        )
        result = build_crossword_pdf(req)
        self.assertTrue(result.pdf_bytes, result.errors)
        self.assertEqual(len(result.puzzles), 1)

    def test_three_and_six_puzzle_crossword_books(self):
        for count in (3, 6):
            with self.subTest(count=count):
                req = CrosswordPdfRequest(
                    product_title="American Automobiles", theme="American Automobiles",
                    mode="topic", number_of_puzzles=count, output_type="book",
                    include_answer_key=True, include_cover=False,
                )
                result = build_crossword_pdf(req)
                self.assertTrue(result.pdf_bytes, result.errors)
                self.assertEqual(len(result.puzzles), count)

    def test_twelve_puzzle_crossword_book_for_a_thin_topic_shrinks_honestly(self):
        req = CrosswordPdfRequest(
            product_title="Dinosaurs", theme="Dinosaurs",
            mode="topic", number_of_puzzles=12, output_type="book",
            include_answer_key=True, include_cover=False,
        )
        result = build_crossword_pdf(req)
        self.assertTrue(result.pdf_bytes, result.errors)
        self.assertLessEqual(len(result.puzzles), 12)
        self.assertGreaterEqual(len(result.puzzles), 1)


class ZeroCostTests(unittest.TestCase):
    """Step 25: default topic generation costs $0.00 -- no AI calls, for
    any of the 12 golden topics, in either product."""

    def test_no_ai_call_for_any_golden_topic_crossword(self):
        for topic in GOLDEN_TOPICS:
            with self.subTest(topic=topic):
                req = CrosswordPdfRequest(
                    product_title=topic, theme=topic, mode="topic",
                    number_of_puzzles=3, output_type="book",
                    include_answer_key=True, include_cover=False,
                )
                with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json:
                    result = build_crossword_pdf(req)
                    self.assertFalse(chat.called, topic)
                    self.assertFalse(chat_json.called, topic)
                self.assertTrue(result.pdf_bytes, f"{topic}: {result.errors}")

    def test_no_ai_call_for_any_golden_topic_word_search(self):
        for topic in GOLDEN_TOPICS:
            with self.subTest(topic=topic):
                req = WordSearchPdfRequest(
                    product_title=topic, theme=topic, mode="topic",
                    number_of_puzzles=3, output_type="book",
                    include_answer_key=True, include_cover=False,
                )
                with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json:
                    result = build_word_search_pdf(req)
                    self.assertFalse(chat.called, topic)
                    self.assertFalse(chat_json.called, topic)
                self.assertTrue(result.pdf_bytes, f"{topic}: {result.errors}")

    def test_no_ai_call_for_nonsense_topic_safe_failure(self):
        req = CrosswordPdfRequest(
            product_title=NONSENSE_TOPIC, theme=NONSENSE_TOPIC, mode="topic",
            number_of_puzzles=3, output_type="book",
        )
        with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json:
            build_crossword_pdf(req)
            self.assertFalse(chat.called)
            self.assertFalse(chat_json.called)


if __name__ == "__main__":
    unittest.main()
