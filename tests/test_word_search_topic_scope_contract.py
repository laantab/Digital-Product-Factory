"""WORD SEARCH TOPIC ROUTE REPAIR (2026-09-11).

Regression test for the customer-facing Word Search Topic-mode route,
``services.product._resolve_word_search_words`` /
``_word_search_pdf_payload``. See SESSION_HANDOFF_2026-09-11.md, "Word
Search regression: root cause", for the full audit this repairs.

The bug (three stacked defects, all in services/product.py):

  1. ``_resolve_word_search_words`` called ``suggest_words_from_topic``
     only as a yes/no pre-check and threw the real, local, on-topic words
     away, then asked OpenAI for a fresh list.
  2. When that AI call failed (no key on the host, Safe Mode, network,
     quota -- exactly what Render has), the ``except Exception`` silently
     substituted a hard-coded ten-word placeholder ("apple, banana,
     cherry, dragon, energy, forest, garden, harbor, island, jungle")
     that has nothing to do with the customer's topic.
  3. ``_word_search_pdf_payload`` always passed ``mode="custom_word_list"``
     to the PDF builder, even in Topic mode, so the topic-relevance QA
     gate (which only inspects words when ``mode == "topic"``) never ran.

A live customer request for "Flower Parts" produced exactly that
placeholder list. The fix mirrors the already-working sister function
``_resolve_crossword_words``/``_crossword_pdf_payload`` in the same file:
resolve locally from the shared topic engine (and the older per-product
packs it falls through to), raise a clear error when nothing matches,
and pass the real mode so QA actually inspects the words. No AI/API call
is made anywhere in this file, and no product/database code beyond the
functions under test is touched.

This also proves the secondary scope gap the same audit flagged: before
this repair's accompanying data/topic_vocabulary_packs.json addition,
"Flower Parts" phrase-matched the broader, older ``plant_parts`` pack
(alias "flower") and returned generic whole-plant vocabulary (LEAF, ROOT,
XYLEM, SOIL, ...) instead of flower-anatomy words. The new shared-engine
``flower_parts`` category is checked first and wins for that exact
phrase, so "Flower Parts" no longer silently broadens to "Plant Parts".
"""
from __future__ import annotations

import inspect
import unittest

from services.factory.topic_vocabulary import resolve_topic_vocabulary
from services.product import _word_search_pdf_payload
import services.product as product_module

# The exact placeholder string the regression shipped -- must never exist
# in the source again, under any topic.
_RETIRED_PLACEHOLDER = (
    "apple\nbanana\ncherry\ndragon\nenergy\nforest\ngarden\nharbor\nisland\njungle"
)

_ORDINARY_TOPICS = ["Flower Parts", "Ocean Animals", "Computer Parts", "American Automobiles"]


def _blow_up_if_called(*_args, **_kwargs):
    raise AssertionError(
        "services.product.chat (the paid AI word generator) must never be "
        "called while resolving Word Search Topic-mode words."
    )


def _fields(theme: str, **overrides) -> dict:
    fields = {
        "book_title": theme,
        "theme": theme,
        "creation_mode": "Topic (AI generates words)",
        "custom_words": "",
        "output_format": "Single page",
        "puzzles": "1",
        "difficulty": "Easy",
        "audience": "adults",
    }
    fields.update(overrides)
    return fields


class RetiredPlaceholderIsGone(unittest.TestCase):
    def test_placeholder_string_no_longer_exists_in_product_py(self):
        source = inspect.getsource(product_module)
        self.assertNotIn(
            _RETIRED_PLACEHOLDER, source,
            "The hard-coded ten-word placeholder must be fully removed, not just unreachable.",
        )
        self.assertNotIn("apple\\nbanana", source)


class WordSearchNeverCallsAI(unittest.TestCase):
    def setUp(self):
        self._original_chat = product_module.chat
        product_module.chat = _blow_up_if_called
        self.addCleanup(setattr, product_module, "chat", self._original_chat)

    def test_ordinary_topics_never_reach_the_ai_client(self):
        for theme in _ORDINARY_TOPICS:
            with self.subTest(theme=theme):
                payload = _word_search_pdf_payload(_fields(theme))
                self.assertTrue(payload["pdf_bytes"])
                self.assertTrue(payload.get("qa_report", {}).get("passed"))

    def test_unknown_topic_raises_a_clear_error_and_builds_no_pdf(self):
        # Matches no shared-engine category and no legacy pack; the AI is
        # never consulted to decide that, and no placeholder ships.
        with self.assertRaises(ValueError) as ctx:
            _word_search_pdf_payload(_fields("Purple Marmalade Bicycle Umbrella"))
        self.assertIn("does not match any known vocabulary pack", str(ctx.exception))

    def test_too_short_nonsense_topic_also_raises_a_clear_error(self):
        with self.assertRaises(ValueError):
            _word_search_pdf_payload(_fields("Zxqv"))


class TopicControlsVocabulary(unittest.TestCase):
    """The customer's exact subject controls the vocabulary -- no silent
    broadening to a more generic topic, and no generic filler words."""

    def setUp(self):
        self._original_chat = product_module.chat
        product_module.chat = _blow_up_if_called
        self.addCleanup(setattr, product_module, "chat", self._original_chat)

    def test_flower_parts_returns_flower_anatomy_not_generic_plant_words(self):
        expected = set(resolve_topic_vocabulary("Flower Parts", 40).words)
        self.assertTrue(expected, "flower_parts pack must resolve via the shared engine.")

        payload = _word_search_pdf_payload(_fields("Flower Parts"))
        produced = {w.strip().upper() for w in payload["custom_words"].splitlines() if w.strip()}

        self.assertTrue(produced, "Flower Parts must produce a non-empty word list.")
        self.assertTrue(
            produced <= expected,
            f"Flower Parts must only use flower-anatomy words, got extras: {produced - expected}",
        )
        # The topic must not have silently broadened to the older, generic
        # whole-plant pack (LEAF, ROOT, XYLEM, SOIL, ... are not flower parts).
        self.assertNotIn("LEAF", produced)
        self.assertNotIn("ROOT", produced)
        self.assertNotIn("XYLEM", produced)
        self.assertNotIn("SOIL", produced)
        # And obviously never the retired placeholder vocabulary.
        self.assertFalse(produced & {"APPLE", "BANANA", "CHERRY", "DRAGON", "JUNGLE"})

    def test_every_ordinary_topic_stays_inside_its_resolved_pack_and_passes_qa(self):
        # NOTE ON GENERIC_FALLBACK_WORDS: a curated, relevance-verified pack
        # may legitimately contain a word that looks generic out of context
        # (e.g. CHARGER for "American Automobiles" -- the Dodge Charger; see
        # services.word_search.qa_agent._check_topic_relevance's own
        # docstring). That check already trusts a matched pack's words
        # regardless of blocklist overlap, so this test asserts the same
        # thing the real QA gate does -- qa_report.passed -- rather than a
        # stricter, wrong rule of its own.
        for theme in _ORDINARY_TOPICS:
            with self.subTest(theme=theme):
                expected = set(resolve_topic_vocabulary(theme, 60).words)
                payload = _word_search_pdf_payload(_fields(theme))
                produced = {
                    w.strip().upper() for w in payload["custom_words"].splitlines() if w.strip()
                }
                self.assertTrue(produced)
                if expected:
                    # Matched the shared engine directly -- every produced word
                    # must come from that exact pack, nothing else blended in.
                    self.assertTrue(produced <= expected, (theme, produced - expected))
                self.assertTrue(payload.get("qa_report", {}).get("passed"), theme)


class TopicModeIsPassedToTheBuilder(unittest.TestCase):
    """The QA topic-relevance gate only inspects words when mode == 'topic'
    (services.word_search.qa_agent._check_topic_relevance) -- prove the
    PDF request actually carries that mode now, not the hard-coded
    'custom_word_list' that disabled the gate."""

    def test_topic_mode_reaches_the_pdf_request(self):
        captured = {}
        original_builder = product_module.build_word_search_pdf

        def spy(request):
            captured["mode"] = request.mode
            return original_builder(request)

        product_module.build_word_search_pdf = spy
        try:
            _word_search_pdf_payload(_fields("Flower Parts"))
        finally:
            product_module.build_word_search_pdf = original_builder

        self.assertEqual(captured.get("mode"), "topic")

    def test_custom_word_list_mode_is_unchanged(self):
        captured = {}
        original_builder = product_module.build_word_search_pdf

        def spy(request):
            captured["mode"] = request.mode
            return original_builder(request)

        product_module.build_word_search_pdf = spy
        try:
            fields = _fields(
                "Whatever Theme",
                creation_mode="Custom word list",
                custom_words="ROBOT\nGALAXY\nCOMET\nORBIT\nPLANET\nMETEOR\nASTEROID\nNEBULA\nSATELLITE\nROCKET",
            )
            _word_search_pdf_payload(fields)
        finally:
            product_module.build_word_search_pdf = original_builder

        self.assertEqual(captured.get("mode"), "custom_word_list")


if __name__ == "__main__":
    unittest.main()
