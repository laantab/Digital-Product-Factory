"""SPELLING WORKSHEET — COMPLETE, CERTIFY, AND RELEASE (2026-09-09).

Formal release-readiness coverage: shared Universal Topic Vocabulary
Engine integration, grade-appropriate filtering, word-count honoring,
nonsense-topic safe failure, custom words, the answer-key contract fix,
the word-bank clipping fix, and zero external calls anywhere.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from services.spelling_worksheet.builder import build_spelling_worksheet
from services.spelling_worksheet.pdf_builder import SpellingWorksheetPdfRequest, build_spelling_worksheet_pdf
from services.product import _spelling_worksheet_pdf_payload

GOLDEN_TOPICS = [
    "Ocean Animals", "American Automobiles", "Container Gardening", "Dog Training",
    "Space Exploration", "Healthy Eating", "Photography", "Baseball", "Dinosaurs",
    "Personal Finance", "World Geography", "Baking",
]
NONSENSE_TOPIC = "zxqv nebula spoons 9382"


class GoldenTopicAcceptanceTests(unittest.TestCase):
    """Step 11: all 12 required topics succeed on the first attempt, with
    zero external calls, and produce a real, requested-size word list."""

    def test_all_topics_produce_a_full_relevant_word_list(self):
        for topic in GOLDEN_TOPICS:
            with self.subTest(topic=topic):
                with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json:
                    result = build_spelling_worksheet(theme=topic, grade="4", word_count=10)
                    self.assertFalse(chat.called, topic)
                    self.assertFalse(chat_json.called, topic)
                self.assertFalse(result.errors, f"{topic}: {result.errors}")
                self.assertEqual(len(result.all_words), 10, topic)
                self.assertEqual(len(set(result.all_words)), 10, f"{topic}: duplicate words")


class NonsenseTopicSafeFailureTests(unittest.TestCase):
    """Step 12: a genuinely nonsense topic fails safely -- never random or
    generic grade-level words pretending to relate to it."""

    def test_nonsense_topic_produces_no_words_and_a_friendly_error(self):
        with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json:
            result = build_spelling_worksheet(theme=NONSENSE_TOPIC, grade="3", word_count=10)
            self.assertFalse(chat.called)
            self.assertFalse(chat_json.called)
        self.assertEqual(result.all_words, [])
        self.assertTrue(result.errors)
        self.assertNotIn("internal", " ".join(result.errors).lower())
        self.assertNotIn("pack", " ".join(result.errors).lower())

    def test_a_real_but_uncovered_topic_still_gets_a_worksheet(self):
        # A genuine (if niche) topic that matches no pack must keep the
        # existing graceful grade-level fallback -- this guard is narrow,
        # not a general "unknown topic" blocker.
        result = build_spelling_worksheet(theme="Medieval History", grade="5", word_count=8)
        self.assertFalse(result.errors)
        self.assertEqual(len(result.all_words), 8)


class GradeBehaviorTests(unittest.TestCase):
    """Step 7: grade selection must materially affect topic-pack output."""

    def test_lower_grades_get_shorter_words_than_higher_grades(self):
        low = build_spelling_worksheet(theme="Ocean Animals", grade="1", word_count=10)
        high = build_spelling_worksheet(theme="Ocean Animals", grade="8", word_count=10)
        self.assertTrue(low.all_words)
        self.assertTrue(high.all_words)
        self.assertLessEqual(max(len(w) for w in low.all_words), 6)
        self.assertGreaterEqual(max(len(w) for w in high.all_words), max(len(w) for w in low.all_words))

    def test_grade_filtering_never_starves_a_real_topic(self):
        # Even at the strictest grade band, a real topic pack must still
        # return a usable worksheet rather than an empty one.
        result = build_spelling_worksheet(theme="Dinosaurs", grade="1", word_count=10)
        self.assertFalse(result.errors)
        self.assertGreaterEqual(len(result.all_words), 4)


class WordCountHonoredTests(unittest.TestCase):
    """Step 8: the requested word count is honored; never padded with
    unrelated words when a topic pool is smaller than requested."""

    def test_requested_counts_are_honored_up_to_pool_size(self):
        for wc in (5, 10, 20):
            with self.subTest(word_count=wc):
                result = build_spelling_worksheet(theme="Ocean Animals", grade="6", word_count=wc)
                self.assertEqual(len(result.all_words), wc)

    def test_a_small_pool_returns_fewer_words_rather_than_padding(self):
        result = build_spelling_worksheet(theme="Ocean Animals", grade="6", word_count=1000)
        self.assertLessEqual(len(result.all_words), 30)  # the ocean_animals pack's real size
        self.assertTrue(result.all_words)


class CustomWordsTests(unittest.TestCase):
    """Step 9: custom words take precedence over topic/grade resolution."""

    def test_custom_words_are_used_verbatim_and_take_priority(self):
        result = build_spelling_worksheet(
            theme="Ocean Animals", grade="3", word_count=5,
            custom_words="Narwhal\nKelp\nTsunami",
        )
        self.assertEqual([w.lower() for w in result.all_words], ["narwhal", "kelp", "tsunami"])


class WorksheetContentContractTests(unittest.TestCase):
    """Step 13/17: the actual Golden Contract this product promises."""

    def test_pdf_is_valid_and_word_bank_answer_key_are_consistent(self):
        req = SpellingWorksheetPdfRequest(
            theme="Ocean Animals", grade="3", word_count=10,
            include_answer_key=True, output_type="single_worksheet",
        )
        result = build_spelling_worksheet_pdf(req)
        self.assertFalse(result.errors)
        self.assertTrue(result.pdf_bytes.startswith(b"%PDF"))
        self.assertEqual(result.layout_info.get("answer_key_pages"), 1)
        self.assertEqual(len(result.words), 10)

    def test_customer_path_honors_the_customers_answer_key_choice(self):
        # Regression: safe_fix_plan used to silently strip
        # include_answer_key=Yes for spelling_worksheet's single-worksheet
        # output, even though its renderer genuinely supports a separate
        # answer-key page (services/factory/product_qa_agent.py
        # _SINGLE_PAGE_ANSWER_KEY_SUPPORTED).
        fields = {
            "worksheet_title": "Ocean Animals Spelling Practice",
            "creation_mode": "Themed (AI generates words)",
            "theme": "Ocean Animals",
            "grade": "Grade 3",
            "word_count": "10",
            "activity_type": "Word List",
            "difficulty": "Medium",
            "include_answer_key": "Yes",
        }
        result = _spelling_worksheet_pdf_payload(fields)
        self.assertIsNone(result.get("errors"))
        self.assertEqual(result["qa_report"]["answer_key_requested"], True)
        self.assertEqual(result["qa_report"]["answer_key_included"], True)
        self.assertEqual(result["layout_info"]["answer_key_pages"], 1)

    def test_word_bank_shows_every_word_not_just_the_first_few(self):
        # Regression: a fixed-height word-bank box silently dropped words
        # past ~8 (4 rows x 2 columns) even though the practice rows and
        # answer key still covered the full requested count.
        from services.spelling_worksheet.renderer import _word_bank_height
        for word_count in (8, 10, 20):
            with self.subTest(word_count=word_count):
                rows_needed = -(-word_count // 2)
                needed_h = 26.0 + rows_needed * 13.0 + 6.0
                self.assertGreaterEqual(_word_bank_height(word_count), needed_h - 0.01)


class ZeroCostTests(unittest.TestCase):
    """Step 24 / core principle: zero paid calls anywhere in this product."""

    def test_full_customer_path_makes_no_external_calls(self):
        fields = {
            "worksheet_title": "Baseball Spelling Practice",
            "creation_mode": "Themed (AI generates words)",
            "theme": "Baseball",
            "grade": "Grade 5",
            "word_count": "10",
            "activity_type": "Word List",
            "difficulty": "Medium",
            "include_answer_key": "Yes",
        }
        with patch("ai_client.chat") as chat, patch("ai_client.chat_json") as chat_json:
            result = _spelling_worksheet_pdf_payload(fields)
            self.assertFalse(chat.called)
            self.assertFalse(chat_json.called)
        self.assertIsNone(result.get("errors"))
        self.assertTrue(result.get("pdf_bytes"))


if __name__ == "__main__":
    unittest.main()
