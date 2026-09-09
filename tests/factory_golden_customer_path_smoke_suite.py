"""FACTORY GOLDEN CUSTOMER-PATH SMOKE SUITE.

Answers one question, fast: CAN A CUSTOMER STILL USE THE FACTORY?

Not "do all internal functions still unit-test" -- this file is
deliberately small and calls each mature generator's own real request/
result dataclasses directly (the same objects services/product.py builds
from a customer's form submission), so it stays fast enough to run after
every meaningful Factory change, per FACTORY_STABILITY_RULES.md Rule 7.

One representative, deterministic, zero-cost path per product. No paid
API calls anywhere in this file -- every product covered here is a local/
procedural generator by design (Crossword, Word Search, Math Worksheet,
Faith Planner, Budget Planner, Spelling Worksheet). Coloring Book (which
can involve paid AI artwork) and Ebook (heavier, multi-stage) are covered
by their own existing fast customer-path tests instead of being
duplicated here -- see FACTORY_STABILITY_RULES.md and the Feature
Stability Matrix for the full list this suite is paired with.

Run directly: pytest tests/factory_golden_customer_path_smoke_suite.py -q
"""
from __future__ import annotations

import unittest

from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf
from services.math_worksheet.pdf_builder import MathWorksheetPdfRequest, build_math_worksheet_pdf
from services.planner.pdf_builder import PlannerPdfRequest, build_planner_pdf
from services.spelling_worksheet.pdf_builder import SpellingWorksheetPdfRequest, build_spelling_worksheet_pdf
from services.word_search.pdf_builder import WordSearchPdfRequest, build_word_search_pdf


class CrosswordGoldenPathTests(unittest.TestCase):
    def test_topic_mode_full_book_first_attempt(self):
        req = CrosswordPdfRequest(
            product_title="American Automobiles", theme="American Automobiles",
            mode="topic", number_of_puzzles=6, output_type="book",
            include_answer_key=True, include_cover=False,
        )
        result = build_crossword_pdf(req)
        self.assertTrue(result.pdf_bytes, result.errors)
        self.assertFalse(result.errors)
        self.assertGreaterEqual(len(result.puzzles), 1)


class WordSearchGoldenPathTests(unittest.TestCase):
    def test_topic_mode_full_book_first_attempt(self):
        req = WordSearchPdfRequest(
            product_title="American Automobiles", theme="American Automobiles",
            mode="topic", number_of_puzzles=6, output_type="book",
            include_answer_key=True, include_cover=False,
        )
        result = build_word_search_pdf(req)
        self.assertTrue(result.pdf_bytes, result.errors)
        self.assertFalse(result.errors)


class MathWorksheetGoldenPathTests(unittest.TestCase):
    def test_full_workbook_first_attempt(self):
        req = MathWorksheetPdfRequest(
            worksheet_title="Multiplication Practice", grade="1",
            math_topic="Multiplication", difficulty="Easy",
            problem_count=10, include_answer_key=True,
            output_type="book",
        )
        result = build_math_worksheet_pdf(req)
        self.assertTrue(result.pdf_bytes, result.errors)
        self.assertFalse(result.errors)


class FaithPlannerGoldenPathTests(unittest.TestCase):
    def test_default_planner_first_attempt(self):
        req = PlannerPdfRequest(planner_type="faith_planner", title="Faith Planner", pages=12)
        result = build_planner_pdf(req)
        self.assertTrue(result.pdf_bytes, result.errors)
        self.assertFalse(result.errors)


class BudgetPlannerGoldenPathTests(unittest.TestCase):
    def test_default_planner_first_attempt(self):
        req = PlannerPdfRequest(planner_type="budget_planner", title="Budget Planner", pages=12)
        result = build_planner_pdf(req)
        self.assertTrue(result.pdf_bytes, result.errors)
        self.assertFalse(result.errors)


class SpellingWorksheetGoldenPathTests(unittest.TestCase):
    """Released 2026-09-09. Regression specimen: "Ocean Animals" -- the
    exact topic that used to return safari vocabulary before this product
    adopted the shared Universal Topic Vocabulary Engine. See
    tests/test_spelling_worksheet_release_readiness.py for deeper
    coverage (grade filtering, word count, nonsense topics, custom
    words, the answer-key contract fix, the word-bank clipping fix)."""

    def test_topic_mode_first_attempt(self):
        req = SpellingWorksheetPdfRequest(
            theme="Ocean Animals", grade="3", word_count=10,
            include_answer_key=True, output_type="single_worksheet",
        )
        result = build_spelling_worksheet_pdf(req)
        self.assertTrue(result.pdf_bytes, result.errors)
        self.assertFalse(result.errors)
        self.assertEqual(len(result.words), 10)
        safari_words = {"elephant", "giraffe", "tiger", "lion", "zebra", "monkey"}
        self.assertFalse(safari_words & {w.lower() for w in result.words})
        self.assertEqual(result.layout_info.get("answer_key_pages"), 1)


if __name__ == "__main__":
    unittest.main()
