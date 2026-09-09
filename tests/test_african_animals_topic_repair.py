"""AFRICAN ANIMALS TOPIC REPAIR (2026-09-09).

CUSTOMER-REPORTED DEFECT
-------------------------
A customer asked for "African Animals in the Wild" and, depending on the
product, either got nothing or got RABBIT, SQUIRREL, DEER, WOLF, FOX, OWL,
FALCON, TIGER mixed in with real African animals -- the same class of
defect already fixed for "Ocean Animals" (safari words) and "American
Automobiles" (car-parts words), just never caught for this topic because no
shared category existed for it at all.

ROOT CAUSE
----------
Neither product had ANY dedicated coverage for "African Animals" in the
Universal Topic Vocabulary Engine (services/factory/topic_vocabulary.py).
Both Word Search (services/word_search/word_lists.py) and Crossword
(services/crossword/word_entries.py) fall through to a shared LEGACY data
file, data/word_search_topics.json, whose id="animals" pack is keyed by the
generic keywords "animals" / "animal" / "wild animals" / "zoo animals" /
"mammals" -- with NO region distinction at all. Its word list mixes real
African animals (LION, ELEPHANT, GIRAFFE, ZEBRA) with North American /
European woodland animals (RABBIT, SQUIRREL, DEER, WOLF, FOX, OWL,
FALCON, BEAR), an Asian animal (TIGER), and others -- so "African Animals"
matched via the "wild animals" keyword and got the whole undifferentiated
mix. Crossword's own downstream size/relevance gate then rejected the
15-word usable subset as "too small with no relevant fallback" and refused
to build a puzzle at all (a safe failure, but still a first-attempt
failure for an extremely common, reasonable topic). Word Search and
Spelling Worksheet (which has its own, separately-broken local "animals"
bank -- see tests/test_spelling_worksheet_topic_relevance.py for the
sibling "Ocean Animals" defect this class of bug also caused there) both
shipped the wrong-region words directly to the customer.

FIX
---
Added a new "african_animals" category (30 curated, real African animals
and birds -- no ocean, arctic, Australian, Asian, or generic backyard
fauna) to data/topic_vocabulary_packs.json, with aliases covering the
reasonable ways a customer phrases this topic: "african animals",
"african animals in the wild", "african wildlife", "wild animals of
africa", "safari animals", "african savanna animals", "animals of
africa", "african safari", "safari". Since all three products
(Crossword, Word Search, Spelling Worksheet) already check the shared
resolver FIRST, this one addition fixes all three at once -- no
product-specific code changed.

Plain, unqualified "Animals" (no region specified) is deliberately left
alone: it still falls through to the old generic mixed pack, matching the
precedent already set for "Baseball" (the broad topic keeps its full
varied pool) vs. "Baseball Players" (a narrower phrase gets a narrower
scope) in tests/test_spelling_worksheet_semantic_scope.py and
tests/test_crossword_scope_answerkey_zip_repair.py. This file is not
about making "Animals" itself African -- only about making the
customer's own more specific phrase resolve correctly.

No external/paid API call is made by any test in this file.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from services.factory.topic_vocabulary import resolve_topic_vocabulary
from services.crossword.word_entries import suggest_crossword_words_from_topic
from services.word_search.word_lists import suggest_words_from_topic
from services.spelling_worksheet.builder import build_spelling_worksheet

# Real animals that must NEVER appear for an "African Animals" request:
# North American/European woodland fauna, an Asian big cat, Antarctic,
# Australian, and ocean animals -- exactly what the legacy "animals" pack
# mixed in.
_WRONG_REGION_WORDS = {
    "rabbit", "squirrel", "deer", "wolf", "fox", "owl", "falcon", "bear",
    "tiger", "panda", "koala", "penguin", "whale", "dolphin", "shark",
    "monkey", "tortoise",
}

_REQUEST_PHRASINGS = [
    "African Animals",
    "African Animals in the Wild",
    "African Wildlife",
    "Wild Animals of Africa",
    "Safari Animals",
    "African Savanna Animals",
    "Safari",
]


class SharedResolverTests(unittest.TestCase):
    def test_every_phrasing_matches_and_excludes_wrong_region_animals(self):
        for topic in _REQUEST_PHRASINGS:
            with self.subTest(topic=topic):
                result = resolve_topic_vocabulary(topic, 20)
                self.assertTrue(result.matched, f"{topic!r} did not match any shared category")
                words = {w.lower() for w in result.words}
                self.assertTrue(words)
                bad = words & _WRONG_REGION_WORDS
                self.assertFalse(bad, f"{topic!r} produced wrong-region animals: {bad}")


class CrosswordTests(unittest.TestCase):
    def test_african_animals_produces_a_real_relevant_word_list(self):
        words, warnings, errors = suggest_crossword_words_from_topic("African Animals", max_words=15)
        self.assertFalse(errors, f"Crossword refused a common, reasonable topic: {errors}")
        self.assertTrue(words)
        bad = {w.lower() for w in words} & _WRONG_REGION_WORDS
        self.assertFalse(bad, f"Crossword produced wrong-region animals: {bad}")

    def test_the_previously_reported_phrasing_also_works(self):
        words, warnings, errors = suggest_crossword_words_from_topic(
            "African Animals in the Wild", max_words=12
        )
        self.assertFalse(errors)
        self.assertGreaterEqual(len(words), 10)


class WordSearchTests(unittest.TestCase):
    def test_african_animals_resolves_to_the_new_shared_category(self):
        words, warnings, errors, source = suggest_words_from_topic("African Animals", max_words=15)
        self.assertFalse(errors)
        self.assertEqual(source, "african_animals")
        bad = {w.lower() for w in words} & _WRONG_REGION_WORDS
        self.assertFalse(bad, f"Word Search produced wrong-region animals: {bad}")

    def test_plain_animals_topic_is_left_alone_deliberately(self):
        # Not a target of this repair -- a bare, unqualified "Animals"
        # request is not region-specific, so it keeps its existing broad
        # (if generic) behavior rather than being forced into the African
        # category. This just proves the addition didn't accidentally
        # hijack the unrelated bare topic.
        words, warnings, errors, source = suggest_words_from_topic("Animals", max_words=10)
        self.assertFalse(errors)
        self.assertTrue(words)
        self.assertNotEqual(source, "african_animals")


class SpellingWorksheetTests(unittest.TestCase):
    def test_african_animals_returns_real_african_vocabulary(self):
        result = build_spelling_worksheet(theme="African Animals in the Wild", grade="4", word_count=10)
        self.assertFalse(result.errors)
        words = {w.lower() for w in result.all_words}
        self.assertEqual(len(words), 10)
        bad = words & _WRONG_REGION_WORDS
        self.assertFalse(bad, f"Spelling Worksheet produced wrong-region animals: {bad}")


class NoExternalCallTests(unittest.TestCase):
    def test_african_animals_resolution_makes_no_external_call(self):
        with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json:
            suggest_crossword_words_from_topic("African Animals", max_words=15)
            suggest_words_from_topic("African Animals", max_words=15)
            build_spelling_worksheet(theme="African Animals", grade="4", word_count=10)
            self.assertFalse(chat.called)
            self.assertFalse(chat_json.called)


if __name__ == "__main__":
    unittest.main()
