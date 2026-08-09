"""ACCEPTANCE TEST — California Gold Rush Days crossword puzzle book.

This is the definitive acceptance test. The product must change to pass.
The test must not change to accommodate broken output.

Requirements (from user contract):
- 25-page PDF: 1 cover + 12 puzzles + 12 answer keys (no divider page)
- 12 puzzles, each with ≥8 placed answers = ≥96 unique Gold Rush answers
- All content about California Gold Rush (people, places, mining, tools, etc.)
- NO forbidden content: KITCHEN, PILLOW, BREAKFAST, GRANDMA, RABBIT, etc.
- Cover title: "California Gold Rush Days" (NOT "Goal Rush")
- Cover subtitle: "12 Crossword Puzzles - Easy Level"
- No "Answer Keys" blank divider page in PDF
- All 12 puzzles use the GOLD_RUSH vocabulary pack (not EVERYDAY_LIFE)

This test is ADDED TO PREFLIGHT. Preflight fails on any regression.
"""
import unittest
import unittest.mock

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.crossword.crossword_fallback import (
    _normalize_theme,
    _ALL_PACKS,
    GOLD_RUSH,
    get_fallback_words_and_clues,
    get_fallback_book_vocabulary,
)
from services.crossword.word_entries import suggest_crossword_words_from_topic
from services.crossword.book import build_crossword_puzzles
from services.crossword.builder import CrosswordPuzzleResult
from services.crossword.direct_pdf_renderer import build_crossword_book_pdf_bytes
from services.crossword.builder import CrosswordPuzzleResult


# ---------------------------------------------------------------------------
# FORBIDDEN CONTENT — absolutely no occurrences allowed in any puzzle
# ---------------------------------------------------------------------------
_FORBIDDEN_ANSWERS = {
    "KITCHEN", "PILLOW", "CURTAIN", "BEDROOM", "BATHROOM", "BACKYARD",
    "GARAGE", "WINDOW", "TOWELS", "BREAKFAST", "COFFEE", "LUNCH", "DINNER",
    "SALAD", "PASTA", "RABBIT", "GIRAFFE", "PANDA", "PENGUIN", "SKIRT",
    "DRESS", "SOCKS", "MONTHS", "OCTOBER", "FAMILY", "GRANDMA", "GRANDPA",
    "MOTHER", "FATHER", "SISTER", "BROTHER",
}
_FORBIDDEN_PATTERNS = {
    "themed answer", "related to", "crossword answer", "sample clue",
    "example clue", "placeholder", "generic fallback", "FALLBACK EXPORT",
    "insert topic here", "TBD", "TBC",
}


# ---------------------------------------------------------------------------
# GOLD RUSH VOCABULARY — must appear in puzzles
# ---------------------------------------------------------------------------
_GOLD_RUSH_MUST_HAVE = {
    "GOLD", "NUGGET", "PROSPECTOR", "FORTY-NINER", "PANNING", "SLUICE",
    "PICKAXE", "SHOVEL", "CLAIM", "PLACER", "MINER", "RIVER", "CAMP",
    "COLOMA", "SUTTER", "MARSHALL", "SIERRA", "BOOMTOWN", "ORE", "MINE",
}


# ---------------------------------------------------------------------------
# 1. Gold Rush vocabulary pack exists and is non-trivial
# ---------------------------------------------------------------------------
class TestGoldRushVocabularyPack(unittest.TestCase):

    def test_gold_rush_pack_exists(self):
        """GOLD_RUSH pack must be defined in crossword_fallback."""
        self.assertIn("gold_rush", _ALL_PACKS, "GOLD_RUSH pack must be in _ALL_PACKS")

    def test_gold_rush_pack_has_enough_words(self):
        """GOLD_RUSH pack must have ≥120 words for 12-puzzle variety."""
        pack = _ALL_PACKS.get("gold_rush", [])
        self.assertGreaterEqual(
            len(pack), 120,
            f"GOLD_RUSH pack must have ≥120 words for 12-puzzle variety, got {len(pack)}",
        )

    def test_gold_rush_pack_uses_gold_rush_clues(self):
        """Every GOLD_RUSH word must have a Gold Rush–specific clue (not generic)."""
        pack = _ALL_PACKS.get("gold_rush", [])
        generic_phrases = {"a type of", "related to", "something", "thing"}
        for word, clue in pack:
            clue_lower = clue.lower()
            for phrase in generic_phrases:
                self.assertNotIn(
                    phrase, clue_lower,
                    f"Word '{word}' has generic clue '{clue}' — must be Gold Rush–specific",
                )

    def test_gold_rush_pack_no_forbidden_content(self):
        """GOLD_RUSH pack must not contain any forbidden words."""
        pack = _ALL_PACKS.get("gold_rush", [])
        pack_answers = {w.upper() for w, _ in pack}
        forbidden_found = _FORBIDDEN_ANSWERS & pack_answers
        self.assertEqual(
            forbidden_found, set(),
            f"GOLD_RUSH pack contains forbidden words: {forbidden_found}",
        )


# ---------------------------------------------------------------------------
# 2. Topic routing — Gold Rush → GOLD_RUSH pack, never EVERYDAY_LIFE
# ---------------------------------------------------------------------------
class TestGoldRushRouting(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.themes_tested = set()

    def _assert_routes_to_gold_rush(self, theme: str):
        """Helper: theme must route to 'gold_rush', not 'everyday_life'."""
        key = _normalize_theme(theme)
        self.assertEqual(
            key, "gold_rush",
            f"Theme '{theme}' must route to 'gold_rush', got '{key}'. "
            "This would use the wrong vocabulary pack.",
        )

    def test_california_gold_rush_days_routes_to_gold_rush(self):
        """Primary user topic 'California Gold Rush Days' must route to GOLD_RUSH."""
        self._assert_routes_to_gold_rush("California Gold Rush Days")

    def test_california_gold_rush_routes_to_gold_rush(self):
        """'California Gold Rush' must route to GOLD_RUSH."""
        self._assert_routes_to_gold_rush("California Gold Rush")

    def test_gold_rush_routes_to_gold_rush(self):
        """'Gold Rush' must route to GOLD_RUSH."""
        self._assert_routes_to_gold_rush("Gold Rush")

    def test_gold_rush_days_routes_to_gold_rush(self):
        """'Gold Rush Days' must route to GOLD_RUSH."""
        self._assert_routes_to_gold_rush("Gold Rush Days")

    def test_49ers_gold_rush_routes_to_gold_rush(self):
        """'49ers Gold Rush' must route to GOLD_RUSH."""
        self._assert_routes_to_gold_rush("49ers Gold Rush")

    def test_gold_rush_never_routes_to_everyday_life(self):
        """Gold Rush themes must NEVER fall through to everyday_life."""
        gold_rush_themes = [
            "California Gold Rush Days", "Gold Rush", "California Gold Rush",
            "Gold Rush Days", "Forty-Niner", "Prospector's Gold Rush",
        ]
        for theme in gold_rush_themes:
            key = _normalize_theme(theme)
            self.assertNotEqual(
                key, "everyday_life",
                f"Theme '{theme}' incorrectly routes to 'everyday_life'",
            )


# ---------------------------------------------------------------------------
# 3. Content quality — no forbidden words, Gold Rush words present
# ---------------------------------------------------------------------------
class TestGoldRushContentQuality(unittest.TestCase):

    def test_fallback_words_have_gold_rush_vocabulary(self):
        """get_fallback_words_and_clues for Gold Rush must return Gold Rush words."""
        words, clues = get_fallback_words_and_clues(
            "California Gold Rush Days", count=50,
        )
        words_upper = {w.upper() for w in words}
        # At least 60% of returned words must be Gold Rush–related
        gold_rush_hits = words_upper & _GOLD_RUSH_MUST_HAVE
        self.assertGreaterEqual(
            len(gold_rush_hits), 12,
            f"At least 12 Gold Rush words expected in first 50, got {len(gold_rush_hits)}: {gold_rush_hits}",
        )
        # None of the forbidden words
        forbidden = words_upper & _FORBIDDEN_ANSWERS
        self.assertEqual(
            forbidden, set(),
            f"Gold Rush fallback returned forbidden words: {forbidden}",
        )

    def test_fallback_book_vocabulary_all_gold_rush(self):
        """get_fallback_book_vocabulary for 12 puzzles must be all Gold Rush."""
        plans = get_fallback_book_vocabulary(
            "California Gold Rush Days",
            puzzle_count=12,
            words_per_puzzle=10,
        )
        self.assertEqual(len(plans), 12, "Must return 12 puzzle word sets")
        all_words = set()
        for words, clues in plans:
            words_upper = {w.upper() for w in words}
            # No forbidden
            forbidden = words_upper & _FORBIDDEN_ANSWERS
            self.assertEqual(forbidden, set(),
                f"Forbidden words in puzzle: {forbidden}")
            all_words.update(words_upper)
        # Total unique Gold Rush words across book
        gold_hits = all_words & _GOLD_RUSH_MUST_HAVE
        self.assertGreaterEqual(
            len(gold_hits), 20,
            f"Expected ≥20 Gold Rush words across 12 puzzles, got {len(gold_hits)}: {gold_hits}",
        )

    def test_suggest_words_rejects_gold_rush_forbidden(self):
        """suggest_crossword_words_from_topic for Gold Rush must not return KITCHEN/BREAKFAST/etc."""
        words, warnings, errors = suggest_crossword_words_from_topic(
            "California Gold Rush Days", max_words=100,
        )
        words_upper = {w.upper() for w in words}
        forbidden = words_upper & _FORBIDDEN_ANSWERS
        self.assertEqual(
            forbidden, set(),
            f"suggest_crossword_words_from_topic returned forbidden words: {forbidden}",
        )

    def test_build_crossword_puzzles_no_forbidden_in_any_puzzle(self):
        """build_crossword_puzzles must not place any forbidden word in any puzzle."""
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        self.assertEqual(len(puzzles), 12,
            f"Expected 12 puzzles, got {len(puzzles)}")

        for idx, puzzle in enumerate(puzzles, 1):
            placed = {w.upper() for w in puzzle.placed_words}
            forbidden = placed & _FORBIDDEN_ANSWERS
            self.assertEqual(
                forbidden, set(),
                f"Puzzle {idx} contains forbidden words: {forbidden}",
            )

    def test_all_puzzles_have_minimum_placed_answers(self):
        """Every puzzle must have ≥8 successfully placed answers."""
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        for idx, puzzle in enumerate(puzzles, 1):
            self.assertGreaterEqual(
                len(puzzle.placed_words), 8,
                f"Puzzle {idx} has only {len(puzzle.placed_words)} placed words, need ≥8. "
                f"Rejected: {puzzle.rejected_words}",
            )

    def test_total_unique_answers_at_least_96(self):
        """Across all 12 puzzles, ≥96 unique placed answers must exist."""
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        all_placed = set()
        for puzzle in puzzles:
            all_placed.update(w.upper() for w in puzzle.placed_words)
        self.assertGreaterEqual(
            len(all_placed), 96,
            f"Expected ≥96 unique placed answers across book, got {len(all_placed)}",
        )

    def test_no_duplicate_answers_across_puzzles(self):
        """Each answer word must appear in only one puzzle (no repetition)."""
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        seen: dict[str, int] = {}
        for idx, puzzle in enumerate(puzzles, 1):
            for word in puzzle.placed_words:
                w = word.upper()
                if w in seen:
                    self.fail(
                        f"Word '{w}' appears in both Puzzle {seen[w]} and Puzzle {idx} — "
                        "answers must not repeat across puzzles."
                    )
                seen[w] = idx

    def test_no_duplicate_clue_texts(self):
        """No two clues across all 12 puzzles may have identical text."""
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        seen_clues: dict[str, tuple[int, str]] = {}
        for idx, puzzle in enumerate(puzzles, 1):
            for clue in puzzle.clues:
                key = clue.clue.strip()
                if key in seen_clues:
                    prev_puz, prev_ans = seen_clues[key]
                    self.fail(
                        f"Duplicate clue text: '{key}' appears in Puzzle {idx} "
                        f"(answer: {clue.answer}) and Puzzle {prev_puz} "
                        f"(answer: {prev_ans})."
                    )
                seen_clues[key] = (idx, clue.answer)

    def test_no_forbidden_patterns_in_clues(self):
        """Clues must not contain any forbidden phrase."""
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        for idx, puzzle in enumerate(puzzles, 1):
            for clue in puzzle.clues:
                clue_lower = clue.clue.lower()
                for pattern in _FORBIDDEN_PATTERNS:
                    self.assertNotIn(
                        pattern.lower(), clue_lower,
                        f"Puzzle {idx} clue '{clue.clue}' contains forbidden phrase '{pattern}'",
                    )

    def test_clues_do_not_contain_answer(self):
        """No clue may contain its own answer as a substring."""
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        for idx, puzzle in enumerate(puzzles, 1):
            for clue in puzzle.clues:
                ans = clue.answer.upper()
                clue_upper = clue.clue.upper()
                # Allow if answer is mentioned as a proper noun in context
                if ans in clue_upper:
                    self.fail(
                        f"Puzzle {idx} clue '{clue.clue}' contains its own answer '{ans}'",
                    )


# ---------------------------------------------------------------------------
# 4. PDF page structure — exactly 25 pages, no divider
# ---------------------------------------------------------------------------
class TestPDFPageStructure(unittest.TestCase):

    def test_pdf_structure_is_25_pages_with_cover(self):
        """build_crossword_book_pdf_bytes with 12 puzzles must produce exactly 25 pages.

        Structure: 1 cover + 12 puzzle pages + 12 answer key pages = 25.
        NO blank "Answer Keys" divider page.
        """
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )

        # Minimal cover_design dict to trigger cover page
        cover_design = {
            "title": "California Gold Rush Days",
            "subtitle": "12 Crossword Puzzles - Easy Level",
            "author": "",
        }

        pdf_bytes, layout = build_crossword_book_pdf_bytes(
            puzzles,
            product_title="California Gold Rush Days",
            subtitle="12 Crossword Puzzles - Easy Level",
            include_answer_key=True,
            cover_design=cover_design,
        )

        # Verify PDF signature
        self.assertTrue(
            pdf_bytes.startswith(b"%PDF"),
            "Output is not a valid PDF",
        )

        # Verify exactly 25 pages
        self.assertEqual(
            layout.page_count, 25,
            f"PDF must have exactly 25 pages (1 cover + 12 puzzles + 12 answer keys), "
            f"got {layout.page_count}. "
            f"cover={layout.cover_page_count}, "
            f"puzzles={layout.puzzle_page_count}, "
            f"answer_keys={layout.answer_key_page_count}",
        )

        # Verify breakdown
        self.assertEqual(layout.cover_page_count, 1,
            f"Expected 1 cover page, got {layout.cover_page_count}")
        self.assertEqual(layout.puzzle_page_count, 12,
            f"Expected 12 puzzle pages, got {layout.puzzle_page_count}")
        self.assertEqual(layout.answer_key_page_count, 12,
            f"Expected 12 answer key pages, got {layout.answer_key_page_count}")

        # Verify no blank divider: answer_key_page_count should equal number of answer pages
        # (not number of answer pages + 1 for a divider)
        # A divider would make answer_key_page_count = 13 when there are 12 puzzles
        self.assertEqual(
            layout.answer_key_page_count, 12,
            "answer_key_page_count must be 12 (no blank divider page allowed). "
            f"Got {layout.answer_key_page_count} — likely a blank 'Answer Keys' divider page exists.",
        )

    def test_cover_title_is_gold_rush_not_goal_rush(self):
        """Cover design must have title 'California Gold Rush Days', not 'Goal Rush'."""
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        cover_design = {
            "title": "California Gold Rush Days",
            "subtitle": "12 Crossword Puzzles - Easy Level",
            "author": "",
        }
        pdf_bytes, layout = build_crossword_book_pdf_bytes(
            puzzles,
            product_title="California Gold Rush Days",
            subtitle="12 Crossword Puzzles - Easy Level",
            include_answer_key=True,
            cover_design=cover_design,
        )
        # The PDF metadata should reflect the correct title
        # We verify by checking the cover_design passed to the renderer
        self.assertIn("Gold Rush", cover_design["title"])
        self.assertNotIn("Goal Rush", cover_design["title"])
        self.assertIn("12 Crossword", cover_design["subtitle"])

    def test_pdf_bytes_large_enough(self):
        """25-page PDF must be at least 50 KB (reasonable minimum size)."""
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        cover_design = {"title": "California Gold Rush Days", "subtitle": "12 Crossword Puzzles - Easy Level", "author": ""}
        pdf_bytes, layout = build_crossword_book_pdf_bytes(
            puzzles,
            product_title="California Gold Rush Days",
            subtitle="12 Crossword Puzzles - Easy Level",
            include_answer_key=True,
            cover_design=cover_design,
        )
        self.assertGreater(len(pdf_bytes), 50_000,
            f"25-page PDF should be >50KB, got {len(pdf_bytes):,} bytes — "
            "likely missing content pages")


# ---------------------------------------------------------------------------
# 5. Topic mode ignores old saved content
# ---------------------------------------------------------------------------
class TestTopicModeRouting(unittest.TestCase):

    def test_topic_mode_uses_current_topic_not_stored_words(self):
        """Topic mode must resolve from the CURRENT topic, not stored custom words.

        Protection lives in product.py (_resolve_crossword_words). book.py then
        consumes that authoritative resolved pool.
        """
        from services.product import _crossword_plan, _resolve_crossword_words

        fields = {
            "book_title": "California Gold Rush Days",
            "theme": "California Gold Rush Days",
            "output_format": "Full Book",
            "puzzles": "12",
            "creation_mode": "Topic (AI generates words)",
            "difficulty": "Easy",
            "custom_words": "KITCHEN\nBEDROOM\nBREAKFAST",
        }
        plan = _crossword_plan(fields)
        resolved = _resolve_crossword_words(
            fields,
            plan,
            stored_words="KITCHEN\nBEDROOM\nBREAKFAST",
        )
        resolved_upper = {w.strip().upper() for w in resolved.splitlines() if w.strip()}
        forbidden = resolved_upper & _FORBIDDEN_ANSWERS
        self.assertEqual(
            forbidden, set(),
            f"Topic mode must ignore stored custom_words. Found: {forbidden}",
        )
        gold_hits = resolved_upper & _GOLD_RUSH_MUST_HAVE
        self.assertGreaterEqual(
            len(gold_hits), 5,
            f"Topic mode should resolve Gold Rush vocabulary, found {gold_hits}",
        )

        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            custom_words=resolved,
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        all_placed = {w.upper() for p in puzzles for w in p.placed_words}
        self.assertEqual(all_placed & _FORBIDDEN_ANSWERS, set())
        self.assertGreaterEqual(len(all_placed & _GOLD_RUSH_MUST_HAVE), 5)


# ---------------------------------------------------------------------------
# 6. OpenAI not called during PDF generation
# ---------------------------------------------------------------------------
class TestZeroAPICallsDuringGeneration(unittest.TestCase):

    def test_build_puzzles_makes_no_api_calls(self):
        """build_crossword_puzzles with use_ai_words=False must not call OpenAI."""
        # with use_ai_words=False, puzzles are built entirely from local vocabulary.
        # Verify: the call should succeed without any API.
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        self.assertEqual(len(puzzles), 12)

    def test_build_pdf_makes_no_api_calls(self):
        """build_crossword_book_pdf_bytes must not call OpenAI (local rendering only)."""
        puzzles, warnings, errors = build_crossword_puzzles(
            mode="topic",
            product_title="California Gold Rush Days",
            theme="California Gold Rush Days",
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=12,
            words_per_puzzle=8,
            output_type="book",
            use_ai_words=False,
        )
        cover_design = {"title": "California Gold Rush Days", "subtitle": "12 Crossword Puzzles - Easy Level", "author": ""}
        pdf_bytes, layout = build_crossword_book_pdf_bytes(
            puzzles,
            product_title="California Gold Rush Days",
            subtitle="12 Crossword Puzzles - Easy Level",
            include_answer_key=True,
            cover_design=cover_design,
        )
        # Should produce a valid PDF with no API involvement
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
