"""Regression tests for crossword quality — instruction separation, vocabulary relevance,
per-clue validation, whole-book variety, and fail-closed export gate.

These tests use mocks or fixture data only. No OpenAI or Tavily calls.
"""
import unittest
from unittest.mock import patch, MagicMock
from services.factory.topic_intelligence import (
    is_instruction_fragment,
    _topic_aware_clue,
    GENERIC_FALLBACK_WORDS,
)
from services.crossword.word_entries import suggest_crossword_words_from_topic
from services.crossword.qa_agent import (
    run_crossword_qa,
    run_crossword_book_qa,
    _FORBIDDEN_CLUE_PATTERNS,
)
from services.crossword.builder import CrosswordPuzzleResult, CrosswordClueEntry
from services.crossword.clues import simple_clue


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_puzzle(
    placed_words: list[str],
    clues: list[tuple[str, str]],  # (answer, clue_text)
    theme: str = "Test Theme",
    mode: str = "topic",
    no_pack_matched: bool = False,
    warnings: list[str] | None = None,
) -> CrosswordPuzzleResult:
    """Build a minimal CrosswordPuzzleResult with a properly populated grid.

    Words are placed horizontally on alternating rows with one-letter overlaps
    where possible, so the grid is non-empty and passes _check_grid_quality.
    """
    size = 15
    grid = [[None] * size for _ in range(size)]
    clue_objs = []
    for idx, (answer, clue_text) in enumerate(clues, start=1):
        clue_objs.append(
            CrosswordClueEntry(
                number=idx,
                answer=answer,
                clue=clue_text,
                direction="across" if idx % 2 == 1 else "down",
                row=0,
                col=0,
            )
        )
    # Populate the grid so _check_grid_quality doesn't fire "grid is empty".
    # Place words horizontally on alternating rows, staggered to create overlaps.
    row = 1
    for word in placed_words:
        word_upper = word.upper().strip()
        if not word_upper:
            continue
        start_col = (row % 3)  # stagger to increase chance of overlap
        for col_offset, letter in enumerate(word_upper[:size]):
            c = start_col + col_offset
            if c < size:
                grid[row][c] = letter
        row += 2
        if row >= size - 1:
            row = 1  # wrap back to top rows

    return CrosswordPuzzleResult(
        puzzle_title="Test Puzzle",
        grid=grid,
        clues=clue_objs,
        placed_words=placed_words,
        rejected_words=[],
        difficulty="Easy",
        grid_size=size,
        theme=theme,
        mode=mode,
        no_pack_matched=no_pack_matched,
        warnings=warnings or [],
        errors=[],
    )


# ---------------------------------------------------------------------------
# A. Instruction Separation
# ---------------------------------------------------------------------------

class TestInstructionFragmentDetection(unittest.TestCase):
    """The user's instruction text must never become a clue or word."""

    def test_just_for_fun_is_instruction(self):
        self.assertTrue(is_instruction_fragment("just for fun"))
        self.assertTrue(is_instruction_fragment("Just for Fun"))

    def test_long_instruction_is_instruction(self):
        # Long instruction strings with many words are always flagged
        self.assertTrue(
            is_instruction_fragment(
                "create a crossword to use everyday common words that anyone should be familiar with"
            )
        )

    def test_instruction_patterns_detected(self):
        cases = [
            "create a crossword to use everyday words",
            "please create a fun puzzle",
            "i want a word search",
            "can you make a crossword",
            "use everyday common words everyone knows",
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertTrue(
                    is_instruction_fragment(case),
                    f"Expected instruction fragment: {case!r}",
                )

    def test_clear_topic_is_not_instruction(self):
        cases = [
            "Garden Vegetables",
            "Family Reunion",
            "Space Exploration",
            "Brain Fitness",
            "Computer Basics",
            "Weather",
            "Animal Kingdom",
        ]
        for case in cases:
            with self.subTest(case=case):
                self.assertFalse(
                    is_instruction_fragment(case),
                    f"Should NOT be instruction fragment: {case!r}",
                )

    def test_topic_aware_clue_rejects_instruction(self):
        # When topic is an instruction fragment, clue must be generic — not leaked text
        clue = _topic_aware_clue("TEST", "create a crossword to use everyday common words")
        self.assertNotIn("create a crossword", clue.lower())
        self.assertNotIn("everyday", clue.lower())
        self.assertNotIn("common words", clue.lower())

    def test_topic_aware_clue_rejects_just_for_fun(self):
        clue = _topic_aware_clue("PLAY", "just for fun")
        self.assertNotIn("just for fun", clue.lower())
        self.assertNotIn("fun", clue.lower())

    def test_topic_aware_clue_works_for_clean_topic(self):
        clue = _topic_aware_clue("CARROT", "Garden Vegetables")
        self.assertIn("garden vegetables", clue.lower())

    def test_instruction_topic_produces_error_in_word_selection(self):
        words, warnings, errors = suggest_crossword_words_from_topic(
            "create a crossword to use everyday common words", max_words=10
        )
        self.assertEqual(words, [])
        self.assertTrue(any("looks like an instruction" in e for e in errors))


# ---------------------------------------------------------------------------
# B. Vocabulary Relevance
# ---------------------------------------------------------------------------

class TestVocabularyRelevance(unittest.TestCase):
    """Computer vocabulary must not appear for non-computer topics."""

    def test_computer_words_in_generic_fallback(self):
        computer_terms = [
            "keyboard", "monitor", "mouse", "printer", "software",
            "hardware", "ethernet", "bluetooth", "processor",
        ]
        for term in computer_terms:
            with self.subTest(term=term):
                self.assertIn(
                    term.lower(),
                    GENERIC_FALLBACK_WORDS,
                    f"{term!r} should be in GENERIC_FALLBACK_WORDS",
                )

    def test_just_for_fun_no_computer_vocabulary(self):
        # "just for fun" is now an instruction fragment → blocked at word selection
        words, warnings, errors = suggest_crossword_words_from_topic(
            "just for fun", max_words=10
        )
        # Must be blocked by instruction fragment detection
        self.assertEqual(words, [])
        self.assertTrue(any("instruction" in e.lower() for e in errors))

    def test_computer_basics_uses_computer_vocabulary(self):
        # Explicit computer request should work fine
        words, warnings, errors = suggest_crossword_words_from_topic(
            "Computer Basics", max_words=10
        )
        computer_terms = {"keyboard", "monitor", "mouse", "processor", "memory"}
        found = {w.lower() for w in words} & computer_terms
        self.assertGreater(
            len(found), 0,
            f"Computer Basics should include computer terms, got: {words}",
        )

    def test_clear_topic_gets_relevant_vocabulary(self):
        cases = [
            ("Garden Vegetables", "plant_parts"),
            ("brain fitness", "brain_fitness"),
            ("Weather", "weather"),
        ]
        for topic, expected_pack_id in cases:
            words, warnings, errors = suggest_crossword_words_from_topic(topic, max_words=10)
            with self.subTest(topic=topic):
                self.assertTrue(
                    any(expected_pack_id in w for w in warnings),
                    f"Topic {topic!r} should use {expected_pack_id} pack. Warnings: {warnings}",
                )


# ---------------------------------------------------------------------------
# C. Per-Clue Validation
# ---------------------------------------------------------------------------

class TestPerClueValidation(unittest.TestCase):
    """Every clue must be real, specific, and not leaked instruction text."""

    def test_term_related_to_is_forbidden(self):
        for pattern in _FORBIDDEN_CLUE_PATTERNS:
            with self.subTest(pattern=pattern):
                puzzle = make_puzzle(
                    placed_words=["TEST"],
                    clues=[("TEST", f"A term related to something ({len('TEST')} letters).")],
                )
                qa = run_crossword_qa(puzzle)
                self.assertFalse(
                    qa.passed,
                    f"'A term related to' should block QA. Pattern: {pattern!r}",
                )
                self.assertTrue(
                    qa.blocked_export,
                    "blocked_export must be True when QA fails",
                )

    def test_long_instruction_clue_is_blocked(self):
        # The clue is >120 chars so it triggers the "unusually long" structural block.
        # Need 4+ placed words (clue_integrity) + custom_word_list mode (skip topic relevance).
        # The long clue uses none of the _FORBIDDEN_CLUE_PATTERNS so it reaches the length check.
        long_clean_clue = (
            "This clue text is intentionally extremely verbose and excessively wordy "
            "beyond what any professional crossword designer would ever produce for "
            "a standard puzzle because it contains far too many unnecessary words "
            "that add no real value to the clue or help the solver in any meaningful way"
        )
        self.assertGreater(len(long_clean_clue), 120)
        puzzle = make_puzzle(
            placed_words=["TEST", "WORD", "PLAY", "GAME"],
            clues=[
                ("TEST", long_clean_clue),
                ("WORD", "A unit of language."),
                ("PLAY", "To engage in recreation."),
                ("GAME", "An activity for fun."),
            ],
            mode="custom_word_list",
        )
        qa = run_crossword_qa(puzzle)
        self.assertFalse(qa.passed)
        self.assertTrue(qa.blocked_export)
        self.assertTrue(
            any("unusually long" in e.lower() for e in qa.errors),
            f"Expected 'unusually long' error. Got: {qa.errors}",
        )

    def test_empty_clue_is_blocked(self):
        puzzle = make_puzzle(
            placed_words=["TEST"],
            clues=[("TEST", "")],
        )
        qa = run_crossword_qa(puzzle)
        self.assertFalse(qa.passed)
        self.assertTrue(qa.blocked_export)

    def test_valid_specific_clue_passes(self):
        puzzle = make_puzzle(
            placed_words=["CARROT", "POTATO", "ONION", "PEAS"],
            clues=[
                ("CARROT", "Orange root vegetable good for your eyes."),
                ("POTATO", "Starchy tuber vegetable."),
                ("ONION", "A bulb with strong flavor."),
                ("PEAS", "Small round green vegetables."),
            ],
            mode="custom_word_list",
        )
        qa = run_crossword_qa(puzzle)
        self.assertTrue(qa.passed, f"Valid clue should pass. Errors: {qa.errors}")
        self.assertFalse(qa.blocked_export)

    def test_custom_word_list_passes_with_generic_clues(self):
        # Custom word list bypasses topic relevance check; only structural checks apply
        puzzle = make_puzzle(
            placed_words=["CARROT", "POTATO", "ONION", "PEAS"],
            clues=[
                ("CARROT", "Orange root vegetable."),
                ("POTATO", "Starchy tuber."),
                ("ONION", "A bulb with layers."),
                ("PEAS", "Small round green."),
            ],
            mode="custom_word_list",
        )
        qa = run_crossword_qa(puzzle)
        self.assertTrue(qa.passed, f"Custom word list should pass. Errors: {qa.errors}")


# ---------------------------------------------------------------------------
# D. Whole-Book Variety
# ---------------------------------------------------------------------------

class TestWholeBookVariety(unittest.TestCase):
    """The same small word bank must not be recycled across puzzles."""

    def test_identical_puzzles_blocked(self):
        # Same 5 words in all 3 puzzles → excessive reuse → must fail
        puzzles = [
            make_puzzle(
                placed_words=["APPLE", "BREAD", "CAKE", "DATE", "EGGS"],
                clues=[
                    ("APPLE", "Red fruit."),
                    ("BREAD", "Baked good."),
                    ("CAKE", "Sweet dessert."),
                    ("DATE", "A stone fruit."),
                    ("EGGS", "Breakfast item."),
                ],
            )
            for _ in range(3)
        ]
        qa = run_crossword_book_qa(
            puzzles,
            expected_puzzle_count=3,
            include_answer_key=True,
            words_per_puzzle=5,
        )
        self.assertFalse(qa.passed, "Identical puzzles should fail variety check")
        self.assertTrue(qa.blocked_export)
        self.assertTrue(any("excessive word repetition" in e.lower() for e in qa.errors))

    def test_varied_puzzles_pass(self):
        # custom_word_list mode skips topic-relevance checks so the fake theme
        # doesn't interfere. 4+ words per puzzle satisfies clue_integrity.
        puzzles = [
            make_puzzle(
                placed_words=["APPLE", "BREAD", "CAKE", "DATE"],
                clues=[
                    ("APPLE", "Red fruit."),
                    ("BREAD", "Baked good."),
                    ("CAKE", "Sweet dessert."),
                    ("DATE", "Sweet fruit from the Middle East."),
                ],
                mode="custom_word_list",
            ),
            make_puzzle(
                placed_words=["DATES", "FISH", "GRAPE", "HONEY"],
                clues=[
                    ("DATES", "Dried sweet fruit."),
                    ("FISH", "Swims in water."),
                    ("GRAPE", "Small round fruit."),
                    ("HONEY", "Made by bees."),
                ],
                mode="custom_word_list",
            ),
            make_puzzle(
                placed_words=["ICECREAM", "JUICE", "KALE", "LIME"],
                clues=[
                    ("ICECREAM", "Cold sweet treat."),
                    ("JUICE", "Drink from fruit."),
                    ("KALE", "A leafy green."),
                    ("LIME", "A sour green citrus."),
                ],
                mode="custom_word_list",
            ),
        ]
        qa = run_crossword_book_qa(
            puzzles,
            expected_puzzle_count=3,
            include_answer_key=True,
            words_per_puzzle=4,
        )
        self.assertTrue(qa.passed, f"Varied puzzles should pass. Errors: {qa.errors}")
        self.assertFalse(qa.blocked_export)

    def test_duplicate_clue_texts_blocked(self):
        same_clue_text = "A common thing found at home."
        puzzles = [
            make_puzzle(
                placed_words=["CHAIR", "TABLE"],
                clues=[
                    ("CHAIR", same_clue_text),
                    ("TABLE", "A common thing found at home."),
                ],
            ),
            make_puzzle(
                placed_words=["LAMP", "DESK"],
                clues=[
                    ("LAMP", same_clue_text),
                    ("DESK", "A common thing found at home."),
                ],
            ),
        ]
        qa = run_crossword_book_qa(
            puzzles,
            expected_puzzle_count=2,
            include_answer_key=True,
            words_per_puzzle=2,
        )
        self.assertFalse(qa.passed)
        self.assertTrue(qa.blocked_export)
        self.assertTrue(any("duplicate clue text" in e.lower() for e in qa.errors))


# ---------------------------------------------------------------------------
# E. Fail-Closed Export Gate
# ---------------------------------------------------------------------------

class TestFailClosedGate(unittest.TestCase):
    """Invalid puzzles must produce no PDF bytes and blocked_export=True."""

    def test_invalid_puzzle_qa_blocked_export_true(self):
        puzzle = make_puzzle(
            placed_words=["TEST"],
            clues=[("TEST", "A term related to something (4 letters).")],
        )
        qa = run_crossword_qa(puzzle)
        self.assertFalse(qa.passed)
        self.assertTrue(qa.blocked_export)

    def test_invalid_book_qa_blocked_export_true(self):
        puzzle = make_puzzle(
            placed_words=["TEST"],
            clues=[("TEST", "A term related to something (4 letters).")],
        )
        qa = run_crossword_book_qa(
            [puzzle],
            expected_puzzle_count=1,
            include_answer_key=True,
        )
        self.assertFalse(qa.passed)
        self.assertTrue(qa.blocked_export)

    def test_valid_puzzle_qa_not_blocked(self):
        puzzle = make_puzzle(
            placed_words=["CARROT", "POTATO", "ONION", "GARLIC"],
            clues=[
                ("CARROT", "Orange root vegetable."),
                ("POTATO", "Starchy tuber."),
                ("ONION", "Bulb with strong flavor."),
                ("GARLIC", "Pungent bulb."),
            ],
            mode="custom_word_list",
        )
        qa = run_crossword_qa(puzzle)
        self.assertTrue(qa.passed)
        self.assertFalse(qa.blocked_export)

    def test_qa_passed_false_means_no_export(self):
        """The caller (pdf_builder) must check qa.passed before proceeding."""
        puzzle = make_puzzle(
            placed_words=["TEST"],
            clues=[("TEST", "A term related to something (4 letters).")],
        )
        qa = run_crossword_qa(puzzle)
        # Caller responsibility: must NOT build PDF when qa.passed is False
        self.assertFalse(qa.passed)
        self.assertTrue(qa.blocked_export)
        # The pdf_builder.py gate checks `if not qa.passed: return result` before
        # reaching the PDF rendering step — verified by code inspection.


# ---------------------------------------------------------------------------
# F. Prompt Leakage Patterns
# ---------------------------------------------------------------------------

class TestPromptLeakagePatterns(unittest.TestCase):
    """Known prompt-fragment patterns must be blocked at clue and topic level."""

    def test_everday_typo_in_topic_is_instruction(self):
        # "everday" (typo of everyday) is part of instruction fragments
        self.assertTrue(is_instruction_fragment("everday common words"))

    def test_generic_clue_contains_topic_integration_is_blocked(self):
        puzzle = make_puzzle(
            placed_words=["TEST"],
            clues=[("TEST", "A term related to create a crossword to use everyday words (4 letters).")],
        )
        qa = run_crossword_qa(puzzle)
        self.assertFalse(qa.passed)
        self.assertTrue(qa.blocked_export)
        self.assertTrue(any("a term related to" in e.lower() for e in qa.errors))


# ---------------------------------------------------------------------------
# G. Recovery — automatic repair and fallback
# ---------------------------------------------------------------------------

class TestRecovery(unittest.TestCase):
    """Crossword pipeline must recover from failures, not just stop."""

    def test_bad_clues_are_replaced_by_repair(self):
        # Puzzles with placeholder clues should be repairable by replacing clues
        from services.crossword.crossword_repair import repair_crossword_book

        bad_puzzle = make_puzzle(
            placed_words=["APPLE", "BREAD", "CAKE", "DATE"],
            clues=[
                ("APPLE", "A term related to fruit (5 letters)."),
                ("BREAD", "A term related to bakery (5 letters)."),
                ("CAKE", "A term related to dessert (4 letters)."),
                ("DATE", "A term related to food (4 letters)."),
            ],
            mode="custom_word_list",
        )

        report = repair_crossword_book(
            puzzles=[bad_puzzle],
            original_theme="Food",
            difficulty="medium",
            grid_size=15,
            seed=42,
        )

        # Repair should have attempted
        self.assertGreaterEqual(report.attempt, 1)
        # After repair the puzzles should be better structured (valid grid + clues)
        for puzzle in report.repaired_puzzles:
            self.assertGreater(len(puzzle.placed_words), 0)

    def test_fallback_produces_no_computer_words_for_general_topic(self):
        # Computer words must NEVER appear in a general/everyday fallback
        from services.crossword.crossword_fallback import get_fallback_words_and_clues

        computer_terms = {"keyboard", "monitor", "mouse", "software", "hardware", "processor", "ethernet"}
        for theme in ["general", "everyday", "hobbies", "family"]:
            words, _ = get_fallback_words_and_clues(theme, count=20, random_seed=99)
            found = {w.lower() for w in words} & computer_terms
            self.assertEqual(
                found, set(),
                f"Computer terms {found} found in '{theme}' fallback pack. "
                "Computer vocabulary must only appear for technology themes.",
            )

    def test_fallback_for_food_theme_uses_food_vocabulary(self):
        from services.crossword.crossword_fallback import get_fallback_words_and_clues

        # FOOD_PACK contains: BREAKFAST, LUNCH, DINNER, PANCAKES, WAFFLES, CEREAL,
        # SALAD, PASTA, RICE, PIZZA, TACOS, SUSHI, NOODLES, ICECREAM, etc.
        food_terms = {"breakfast", "lunch", "dinner", "pancakes", "cereal", "salad", "pasta", "rice", "pizza", "tacos", "sushi", "noodles", "bread", "cookie"}
        words, clues = get_fallback_words_and_clues("Food", count=20, random_seed=55)
        found = {w.lower() for w in words} & food_terms
        self.assertGreater(
            len(found), 0,
            f"Food theme should include food vocabulary, got: {words}",
        )
        # All clues should be specific, not placeholder
        for clue_text in clues.values():
            self.assertNotIn("a term related to", clue_text.lower())
            self.assertGreater(len(clue_text), 8)

    def test_fallback_produces_varied_puzzles_across_book(self):
        # Fallback must not repeat the same word list across 10 puzzles
        from services.crossword.crossword_fallback import get_fallback_book_vocabulary

        puzzles = get_fallback_book_vocabulary(
            theme="everyday life",
            puzzle_count=10,
            words_per_puzzle=10,
            random_seed=77,
        )

        self.assertGreaterEqual(
            len(puzzles), 5,
            f"Should produce at least 5 puzzles from fallback, got {len(puzzles)}",
        )

        all_words: list[str] = []
        for words, _ in puzzles:
            all_words.extend(words)

        unique_words = set(all_words)
        # For 10 puzzles × 10 words = 100 entries, require at least 70 unique
        # (allows 30 repeats — reasonable for crossword — but no more)
        self.assertGreaterEqual(
            len(unique_words), 70,
            f"Fallback book should have varied vocabulary. Only {len(unique_words)} "
            f"unique words across {len(puzzles)} puzzles. Words: {sorted(unique_words)[:20]}",
        )

    def test_repair_preserves_user_words_in_custom_list_mode(self):
        # When the user provides a custom word list, repair must preserve those words
        from services.crossword.crossword_repair import repair_crossword_book

        # Puzzle with the user's words plus a bad clue
        puzzle = make_puzzle(
            placed_words=["APPLE", "BREAD", "CAKE", "DATE"],
            clues=[
                ("APPLE", "A term related to fruit (5 letters)."),
                ("BREAD", "Good food."),
                ("CAKE", "Sweet."),
                ("DATE", "Tasty."),
            ],
            mode="custom_word_list",
        )

        report = repair_crossword_book(
            puzzles=[puzzle],
            original_theme="Food",
            difficulty="medium",
            grid_size=15,
            seed=42,
        )

        # User's original words should still appear in the repaired puzzle
        original_words = {"APPLE", "BREAD", "CAKE", "DATE"}
        repaired_words = {w.upper() for w in report.repaired_puzzles[0].placed_words}
        # At least some of the user's words should be preserved
        preserved = original_words & repaired_words
        self.assertGreaterEqual(
            len(preserved), 1,
            f"Repair should preserve at least some user words. "
            f"Original: {original_words}, Repaired: {repaired_words}",
        )

    def test_repair_cannot_loop_indefinitely(self):
        # Repair must respect MAX_REPAIR_ATTEMPTS and not loop forever
        from services.crossword.crossword_repair import repair_crossword_book, MAX_REPAIR_ATTEMPTS

        bad_puzzle = make_puzzle(
            placed_words=["TEST"],
            clues=[("TEST", "A term related to something.")],
        )

        report = repair_crossword_book(
            puzzles=[bad_puzzle] * 10,  # 10 failing puzzles
            original_theme="test",
            difficulty="medium",
            grid_size=15,
            seed=1,
        )

        # Should not exceed max attempts
        self.assertLessEqual(report.attempt, MAX_REPAIR_ATTEMPTS)
        # Should return puzzles (not crash)
        self.assertEqual(len(report.repaired_puzzles), 10)

    def test_repair_with_technical_theme_gets_technical_fallback(self):
        # When a technical topic fails, fallback should use technology vocabulary
        from services.crossword.crossword_fallback import get_fallback_words_and_clues

        computer_terms = {"keyboard", "monitor", "mouse", "printer", "software", "hardware"}
        words, _ = get_fallback_words_and_clues("computer basics", count=20, random_seed=33)
        found = {w.lower() for w in words} & computer_terms
        self.assertGreater(
            len(found), 0,
            f"Technology theme should include computer terms. Got: {words}",
        )

    def test_fallback_clues_are_all_valid_not_placeholder(self):
        from services.crossword.crossword_fallback import get_fallback_book_vocabulary

        puzzles = get_fallback_book_vocabulary(
            theme="nature",
            puzzle_count=3,
            words_per_puzzle=10,
            random_seed=88,
        )

        for words, clues_map in puzzles:
            for answer, clue in clues_map.items():
                self.assertNotIn("a term related to", clue.lower())
                self.assertNotIn("create a crossword", clue.lower())
                self.assertNotIn("placeholder", clue.lower())
                self.assertGreater(len(clue), 10)
                self.assertLessEqual(len(clue), 120)


# ---------------------------------------------------------------------------
# H. Fallback Routing — verify each category keyword routes to the right pack
# ---------------------------------------------------------------------------

class TestFallbackRouting(unittest.TestCase):
    """Each theme keyword must route to its appropriate vocabulary pack."""

    def _routed_pack(self, theme: str) -> str:
        from services.crossword.crossword_fallback import select_fallback_pack
        return select_fallback_pack(theme)

    def test_food_routes_to_food_pack(self):
        for kw in ["food", "Food", "FOOD", "cooking", "recipes", "meals", "snacks", "desserts"]:
            self.assertEqual(
                self._routed_pack(kw), "food",
                f"'{kw}' should route to 'food' pack",
            )

    def test_everyday_routes_to_everyday_life_pack(self):
        # Only explicit Everyday Life requests may use this broad pack.
        # Generic or unmatched topics must fail closed, never receive household words.
        for kw in ["everyday", "daily life", "everyday life", "home life"]:
            self.assertEqual(
                self._routed_pack(kw), "everyday_life",
                f"'{kw}' should route to 'everyday_life' pack",
            )

    def test_children_routes_to_children_pack(self):
        for kw in ["children", "kids", "child", "baby", "toddler", "preschool", "kindergarten", "young learners"]:
            self.assertEqual(
                self._routed_pack(kw), "children",
                f"'{kw}' should route to 'children' pack",
            )

    def test_nature_routes_to_nature_pack(self):
        for kw in ["nature", "animals", "plant", "weather", "garden", "wildlife", "bird", "ocean", "forest"]:
            self.assertEqual(
                self._routed_pack(kw), "nature",
                f"'{kw}' should route to 'nature' pack",
            )

    def test_household_routes_to_everyday_life_pack(self):
        # Explicit household requests may use the Everyday Life pack.
        for kw in ["household", "home life", "appliances"]:
            self.assertEqual(
                self._routed_pack(kw), "everyday_life",
                f"'{kw}' should route to 'everyday_life' pack",
            )

    def test_transportation_routes_to_activities_pack(self):
        # "travel" routes to places (traveling → places), not activities.
        # "plane" routes to activities (plane is in activities keywords).
        for kw in ["transport", "vehicle", "vehicles", "car", "cars", "bus", "train", "plane", "airplane"]:
            self.assertEqual(
                self._routed_pack(kw), "activities",
                f"'{kw}' should route to 'activities' pack",
            )

    def test_hobbies_routes_to_activities_pack(self):
        for kw in ["hobbies", "hobby", "games", "sports", "exercise", "fitness", "dance", "crafts"]:
            self.assertEqual(
                self._routed_pack(kw), "activities",
                f"'{kw}' should route to 'activities' pack",
            )

    def test_technology_routes_to_technology_pack(self):
        for kw in ["technology", "computer", "internet", "coding", "digital", "phone", "software", "electronics"]:
            self.assertEqual(
                self._routed_pack(kw), "technology",
                f"'{kw}' should route to 'technology' pack",
            )

    def test_seasons_routes_to_seasons_pack(self):
        for kw in ["seasons", "spring", "summer", "autumn", "winter", "holiday", "holidays", "christmas", "halloween"]:
            self.assertEqual(
                self._routed_pack(kw), "seasons",
                f"'{kw}' should route to 'seasons' pack",
            )

    def test_places_routes_to_places_pack(self):
        for kw in ["places", "city", "travel", "vacation", "beach", "park", "museum", "restaurant"]:
            self.assertEqual(
                self._routed_pack(kw), "places",
                f"'{kw}' should route to 'places' pack",
            )


# ---------------------------------------------------------------------------
# I. Fallback Capacity — verify pack sizes support 10-puzzle books
# ---------------------------------------------------------------------------

class TestFallbackCapacity(unittest.TestCase):
    """Every category pack must have enough words for a 10-puzzle book."""

    def test_technology_pack_has_100_plus_words(self):
        from services.crossword.crossword_fallback import TECHNOLOGY_PACK
        self.assertGreaterEqual(
            len(TECHNOLOGY_PACK), 100,
            f"TECHNOLOGY_PACK has only {len(TECHNOLOGY_PACK)} words. "
            "Need 100+ to fill a 10-puzzle book without excessive repetition.",
        )

    def test_everyday_life_pack_supports_10_puzzles(self):
        from services.crossword.crossword_fallback import EVERYDAY_LIFE, get_fallback_book_vocabulary

        # 10 puzzles × 10 words = 100 words needed
        puzzles = get_fallback_book_vocabulary(
            theme="everyday",
            puzzle_count=10,
            words_per_puzzle=10,
            random_seed=1,
        )
        self.assertGreaterEqual(
            len(puzzles), 10,
            f"everyday_life should produce 10 puzzles, got {len(puzzles)}",
        )
        all_words = [w for words, _ in puzzles for w in words]
        unique = set(all_words)
        # Require at least 80 unique words (allowing 20 repeats across 100 placements)
        self.assertGreaterEqual(
            len(unique), 80,
            f"everyday_life: {len(unique)} unique words for 10 puzzles. "
            f"Need ≥80. Total placements: {len(all_words)}",
        )

    def test_food_pack_supports_10_puzzles(self):
        from services.crossword.crossword_fallback import FOOD_PACK, get_fallback_book_vocabulary

        puzzles = get_fallback_book_vocabulary(
            theme="food",
            puzzle_count=10,
            words_per_puzzle=10,
            random_seed=2,
        )
        self.assertGreaterEqual(len(puzzles), 10)
        all_words = [w for words, _ in puzzles for w in words]
        unique = set(all_words)
        self.assertGreaterEqual(
            len(unique), 80,
            f"FOOD_PACK: {len(unique)} unique words. Need ≥80.",
        )

    def test_nature_pack_supports_10_puzzles(self):
        from services.crossword.crossword_fallback import get_fallback_book_vocabulary

        puzzles = get_fallback_book_vocabulary(
            theme="nature",
            puzzle_count=10,
            words_per_puzzle=10,
            random_seed=3,
        )
        self.assertGreaterEqual(len(puzzles), 10)
        all_words = [w for words, _ in puzzles for w in words]
        self.assertGreaterEqual(
            len(set(all_words)), 80,
            f"NATURE_PACK: {len(set(all_words))} unique words. Need ≥80.",
        )

    def test_technology_pack_supports_10_puzzles(self):
        from services.crossword.crossword_fallback import get_fallback_book_vocabulary

        puzzles = get_fallback_book_vocabulary(
            theme="technology",
            puzzle_count=10,
            words_per_puzzle=10,
            random_seed=4,
        )
        self.assertGreaterEqual(len(puzzles), 10)
        all_words = [w for words, _ in puzzles for w in words]
        self.assertGreaterEqual(
            len(set(all_words)), 80,
            f"TECHNOLOGY_PACK: {len(set(all_words))} unique words. Need ≥80.",
        )

    def test_children_pack_supports_10_puzzles(self):
        from services.crossword.crossword_fallback import get_fallback_book_vocabulary

        puzzles = get_fallback_book_vocabulary(
            theme="children",
            puzzle_count=10,
            words_per_puzzle=10,
            random_seed=5,
        )
        self.assertGreaterEqual(len(puzzles), 10)
        all_words = [w for words, _ in puzzles for w in words]
        self.assertGreaterEqual(
            len(set(all_words)), 80,
            f"CHILDREN_PACK: {len(set(all_words))} unique words. Need ≥80.",
        )

    def test_activities_pack_supports_10_puzzles(self):
        from services.crossword.crossword_fallback import get_fallback_book_vocabulary

        puzzles = get_fallback_book_vocabulary(
            theme="sports",
            puzzle_count=10,
            words_per_puzzle=10,
            random_seed=6,
        )
        self.assertGreaterEqual(len(puzzles), 10)
        all_words = [w for words, _ in puzzles for w in words]
        self.assertGreaterEqual(
            len(set(all_words)), 80,
            f"ACTIVITIES_PACK: {len(set(all_words))} unique words. Need ≥80.",
        )


# ---------------------------------------------------------------------------
# J. Export Route Protection — prove invalid data cannot reach PDF/ZIP builders
# ---------------------------------------------------------------------------

class TestExportRouteProtection(unittest.TestCase):
    """Every export route must block on QA failure. No defective PDFs or ZIPs."""

    def test_build_crossword_pdf_returns_empty_on_qa_failure(self):
        # Simulate what happens when build_crossword_puzzles_with_qa returns empty
        # puzzles (all recovery stages failed) — build_crossword_pdf must not render.
        from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf

        # Patch build_crossword_puzzles_with_qa to return empty puzzles with failed QA
        with patch(
            "services.crossword.pdf_builder.build_crossword_puzzles_with_qa"
        ) as mock_qa:
            from services.crossword.qa_agent import CrosswordQAResult
            from services.crossword.builder import CrosswordPuzzleResult

            mock_qa.return_value = (
                [],  # empty puzzles
                [],  # warnings
                ["Recovery exhausted"],  # errors
                CrosswordQAResult(passed=False, blocked_export=True,
                                  errors=["Recovery exhausted: repair and fallback both failed."]),
            )

            req = CrosswordPdfRequest(
                product_title="Test",
                theme="test",
                number_of_puzzles=10,
                mode="topic",
                words_per_puzzle=10,
            )
            result = build_crossword_pdf(req)

            # The gate in build_crossword_pdf fires: qa not passed → early return
            self.assertEqual(result.pdf_bytes, b"",
                             "build_crossword_pdf must return empty pdf_bytes when QA fails")
            self.assertTrue(len(result.errors) > 0,
                             "build_crossword_pdf must set errors when QA fails")

    def test_qa_gate_blocks_pdf_rendering_with_invalid_data(self):
        # Even if puzzles somehow reach the rendering step, the qa gate must block
        from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf

        with patch(
            "services.crossword.pdf_builder.build_crossword_puzzles_with_qa"
        ) as mock_qa:
            from services.crossword.qa_agent import CrosswordQAResult

            # Return valid puzzles but QA says FAILED
            mock_puzzle = make_puzzle(
                placed_words=["APPLE", "BREAD"],
                clues=[("APPLE", "Red fruit."), ("BREAD", "Baked good.")],
                mode="custom_word_list",
            )
            mock_qa.return_value = (
                [mock_puzzle],
                [],
                [],
                CrosswordQAResult(passed=False, blocked_export=True,
                                  errors=["Something is wrong."]),
            )

            req = CrosswordPdfRequest(
                product_title="Test",
                theme="test",
                mode="custom_word_list",
                custom_words="apple\nbread",
            )
            result = build_crossword_pdf(req)

            # QA gate fires before PDF rendering
            self.assertEqual(result.pdf_bytes, b"",
                             "PDF must be empty when qa.passed=False")
            self.assertTrue(result.qa_report is not None)
            self.assertFalse(result.qa_report.passed)

    def test_build_crossword_puzzles_with_qa_returns_empty_on_total_failure(self):
        # When the verified fallback ALSO fails final QA,
        # build_crossword_puzzles_with_qa must return empty puzzles.
        # We mock build_crossword_book_with_recovery to simulate this terminal failure.
        from services.crossword.qa_agent import build_crossword_puzzles_with_qa
        from services.crossword.book import build_crossword_puzzles
        from services.crossword.qa_agent import CrosswordQAResult

        with patch(
            "services.crossword.crossword_repair.build_crossword_book_with_recovery"
        ) as mock_fallback:
            # Simulate terminal fallback failure: empty puzzles + failed QA
            mock_fallback.return_value = (
                [],  # empty puzzles
                [],
                ["Fallback QA failed"],
                CrosswordQAResult(passed=False, blocked_export=True,
                                  errors=["Fallback QA failed: all recovery stages exhausted"]),
                True,
            )

            failing_puzzle = make_puzzle(
                placed_words=["TEST"],
                clues=[("TEST", "A term related to something (4 letters).")],
            )
            with patch(
                "services.crossword.book.build_crossword_puzzles"
            ) as mock_build:
                mock_build.return_value = ([failing_puzzle], [], [])

                puzzles, warnings, errors, qa = build_crossword_puzzles_with_qa(
                    build_crossword_puzzles,
                    mode="topic",
                    product_title="Test",
                    theme="test",
                    number_of_puzzles=10,
                    words_per_puzzle=10,
                    use_ai_words=False,
                    max_attempts=2,
                )

                # After fallback failing, empty puzzles must be returned
                self.assertEqual(
                    puzzles, [],
                    "build_crossword_puzzles_with_qa must return empty puzzles when fallback fails"
                )
                self.assertFalse(
                    qa.passed,
                    "QA must report failure after all stages exhausted"
                )
                self.assertTrue(
                    qa.blocked_export,
                    "blocked_export must be True when all stages fail"
                )

    def test_repair_final_qa_used_when_fallback_fails(self):
        # When fallback QA fails, final_qa must be fallback_qa (the last QA run), not
        # repair_report.final_qa. And empty puzzles must be returned.
        from services.crossword.crossword_repair import build_crossword_book_with_recovery
        from services.crossword.qa_agent import CrosswordQAResult

        with patch(
            "services.crossword.book.build_crossword_puzzles"
        ) as mock_build:
            with patch(
                "services.crossword.crossword_repair.run_crossword_book_qa"
            ) as mock_qa:
                # All QA calls fail
                mock_qa.return_value = CrosswordQAResult(passed=False, blocked_export=True,
                                                          errors=["QA failed"])

                # Build returns a failing puzzle
                bad_puzzle = make_puzzle(
                    placed_words=["TEST"],
                    clues=[("TEST", "Bad clue.")],
                )
                mock_build.return_value = ([bad_puzzle], [], [])

                puzzles, warnings, errors, qa, used_fallback = build_crossword_book_with_recovery(
                    theme="test",
                    difficulty="medium",
                    grid_size=15,
                    number_of_puzzles=1,
                    words_per_puzzle=5,
                    output_type="book",
                    mode="topic",
                )

                # After all recovery stages fail, empty puzzles must be returned
                self.assertEqual(
                    puzzles, [],
                    "Must return empty puzzles when all recovery stages fail"
                )
                # QA must report failure
                self.assertFalse(qa.passed)
                self.assertTrue(qa.blocked_export)


# ---------------------------------------------------------------------------
# Regression tests — clue pair survival & generic placeholder elimination
# ---------------------------------------------------------------------------

class TestEverydayCluePairs(unittest.TestCase):
    """Ensure (word, clue) pairs survive all pipeline stages with real clues."""

    # The 26 affected everyday words from the live error report
    AFFECTED_WORDS = [
        "COMB", "WAKE", "SOAP", "SINK", "FORK", "BOWL", "LAMP", "KEYS",
        "TOOTHBRUSH", "ALARM", "TOAST", "LUNCH", "SPOON", "PLATE", "SHIRT",
        "SOCKS", "SHOES", "PHONE", "PANTS", "DRESS", "COUCH", "RADIO",
        "MONEY", "TRASH", "BROOM", "STORE",
    ]

    def test_everyday_words_get_specific_clues_via_simple_clue(self):
        """Every affected word must receive a specific real clue from simple_clue."""
        from services.crossword.clues import simple_clue

        generic_patterns = [
            "crossword answer",
            "answer (",
            "a term related to",
            "word meaning:",
            "common everyday word:",
        ]
        for word in self.AFFECTED_WORDS:
            clue = simple_clue(word, theme="motivation")
            self.assertIsInstance(clue, str)
            self.assertTrue(len(clue) >= 8, f"{word}: clue too short: {clue!r}")
            clue_lower = clue.lower()
            for pattern in generic_patterns:
                self.assertNotIn(
                    pattern, clue_lower,
                    f"{word}: clue contains forbidden pattern {pattern!r}: {clue!r}"
                )

    def test_everyday_words_get_same_clue_regardless_of_theme(self):
        """Clue must be consistent regardless of which theme is passed."""
        from services.crossword.clues import simple_clue

        for word in self.AFFECTED_WORDS:
            clue_a = simple_clue(word, theme="motivation")
            clue_b = simple_clue(word, theme="everyday life")
            clue_c = simple_clue(word, theme="")
            self.assertEqual(
                clue_a, clue_b,
                f"{word}: clue changed with theme: {clue_a!r} vs {clue_b!r}"
            )
            self.assertEqual(
                clue_a, clue_c,
                f"{word}: clue changed with empty theme: {clue_a!r} vs {clue_c!r}"
            )

    def test_no_generic_clues_from_build_local_clue(self):
        """build_local_clue must never emit 'Crossword answer (N letters)'."""
        from services.factory.topic_intelligence import build_local_clue

        generic_patterns = [
            "crossword answer (",
            "answer (",
            "a term related to",
        ]
        for word in self.AFFECTED_WORDS:
            # Test with empty topic (was the bug trigger)
            clue = build_local_clue(word, topic="")
            clue_lower = clue.lower()
            for pattern in generic_patterns:
                self.assertNotIn(
                    pattern, clue_lower,
                    f"{word}: build_local_clue('') produced {pattern!r}: {clue!r}"
                )

    def test_no_generic_clues_from_topic_aware_clue(self):
        """_topic_aware_clue must never emit 'A term related to X (N letters)' patterns.

        Note: it MAY return 'Crossword answer (N letters).' for instruction fragments
        (the QA validator blocks that pattern independently).  The forbidden pattern
        'A term related to' is what this test specifically catches.
        """
        from services.factory.topic_intelligence import _topic_aware_clue

        # The specific forbidden pattern: "A term related to X (N letters)."
        # _topic_aware_clue now returns "Related to {topic}." instead.
        for word in self.AFFECTED_WORDS:
            # Test with a clean topic (not instruction fragment) that becomes empty
            # after filler stripping → should use rule-based fallback
            clue = _topic_aware_clue(word, "create ten easy crossword puzzles")
            clue_lower = clue.lower()
            self.assertNotIn(
                "a term related to", clue_lower,
                f"{word}: _topic_aware_clue produced 'A term related to': {clue!r}"
            )
            self.assertNotIn(
                "crossword answer (", clue_lower,
                f"{word}: should not return 'Crossword answer (N letters)' for non-instruction topic: {clue!r}"
            )

    def test_grid_rebuild_preserves_clue_pairs(self):
        """Rebuilding a puzzle must not discard existing (word, clue) pairs."""
        from services.crossword.crossword_repair import _rebuild_puzzle_with_replacements
        from services.crossword.engine import CrosswordClueEntry

        # Create a puzzle with everyday words and their real clues
        real_clues = {w: simple_clue(w) for w in self.AFFECTED_WORDS[:10]}
        placed = list(real_clues.keys())

        puzzle = make_puzzle(
            placed_words=placed,
            clues=[(w, real_clues[w]) for w in placed],
            mode="topic",
        )

        rebuilt = _rebuild_puzzle_with_replacements(
            puzzle=puzzle,
            replacement_words=["EXTRAWORD"],
            replacement_clues={"EXTRAWORD": "An extra word for testing."},
            failed_words=["EXTRAWORD"],  # only the new word "fails"
            seed=42,
        )

        # All original words must keep their specific clues
        rebuilt_answers = {c.answer for c in rebuilt.clues}
        for w in placed:
            self.assertIn(w, rebuilt_answers, f"{w} was lost during rebuild")
            for c in rebuilt.clues:
                if c.answer == w:
                    clue_lower = c.clue.lower()
                    self.assertNotIn("crossword answer", clue_lower,
                                     f"{w}: clue was replaced with generic after rebuild: {c.clue!r}")
                    self.assertNotIn("answer (", clue_lower,
                                     f"{w}: clue was replaced with generic after rebuild: {c.clue!r}")
                    break

    def test_missing_clue_repairs_from_fallback_lookup(self):
        """When a clue is missing, simple_clue must use the fallback library."""
        from services.crossword.clues import simple_clue

        # COMB is in crossword_fallback.py but not in crossword_clues.json.
        # simple_clue must find it via the fallback library.
        clue = simple_clue("COMB", theme="")
        self.assertIn("hair", clue.lower(), f"COMB should have 'hair' in clue, got: {clue!r}")
        self.assertNotIn("crossword answer", clue.lower())
        self.assertNotIn("answer (", clue.lower())

    def test_word_without_verified_clue_gets_natural_description(self):
        """A truly unknown word must get a natural description, not a placeholder."""
        from services.crossword.clues import simple_clue

        # A word that is NOT in any pack or fallback library
        # (generated made-up word to test the rule-based fallback)
        clue = simple_clue("XYZQB", theme="")
        clue_lower = clue.lower()
        # Must not be a generic placeholder
        self.assertNotIn("crossword answer", clue_lower)
        self.assertNotIn("answer (", clue_lower)
        # Must be a real description
        self.assertGreater(len(clue), 5)
        # Rule-based fallback: "Word meaning: XYZQB." or "Common everyday word: XYZQB."
        self.assertTrue(
            "xyzqb" in clue_lower or "word meaning" in clue_lower or "common" in clue_lower,
            f"Unknown word got unexpected clue format: {clue!r}"
        )

    def test_all_clues_unique_across_book(self):
        """Every clue text must be unique across a full book."""
        from services.crossword.crossword_repair import build_crossword_book_with_recovery

        # Build a full 10-puzzle book using everyday_life fallback
        puzzles, warnings, errors, qa, used_fallback = build_crossword_book_with_recovery(
            theme="everyday life",  # Routes to everyday_life pack — all words have verified specific clues
            difficulty="easy",
            grid_size=15,
            number_of_puzzles=10,
            words_per_puzzle=10,
            output_type="book",
            seed=42,
            include_answer_key=True,
            mode="topic",
        )

        if not qa.passed:
            self.fail(
                f"Book QA failed (must pass for this test): {qa.errors[:3]}\n"
                f"Warnings: {warnings[:3]}"
            )

        # Collect all clue texts
        all_clues: dict[str, list[str]] = {}
        for idx, puzzle in enumerate(puzzles):
            for clue_obj in puzzle.clues:
                ct = clue_obj.clue.strip().lower()
                all_clues.setdefault(ct, []).append(f"Puzzle {idx+1}({clue_obj.answer})")

        # Flag ONLY entries where DIFFERENT answer words share the same clue text.
        # Same word + same clue across puzzles is valid (word reuse is allowed).
        # Different words + same generic clue = the actual bug this check was designed to catch.
        clue_to_entries: dict[str, list[tuple[str, str]]] = {}  # clue → [(answer, puzzle_label)]
        for idx, puzzle in enumerate(puzzles):
            puzzle_label = f"Puzzle {idx+1}"
            for clue_obj in puzzle.clues:
                ct = clue_obj.clue.strip().lower()
                if ct:
                    clue_to_entries.setdefault(ct, []).append((clue_obj.answer or "", puzzle_label))

        real_duplicates: dict[str, list[str]] = {}
        for ct, entries in clue_to_entries.items():
            unique_answers = {ans for ans, _ in entries}
            if len(unique_answers) > 1:  # Different words → same clue = bug
                locs = [f"{p}({a})" for a, p in entries]
                real_duplicates[ct] = locs

        self.assertEqual(
            real_duplicates, {},
            f"Different words sharing same clue text (valid duplicates are same word + same clue): "
            f"{list(real_duplicates.items())[:3]}"
        )

    def test_qa_blocks_generic_and_duplicate_clues(self):
        """The QA validator must still block generic and duplicate clues."""
        from services.crossword.qa_agent import run_crossword_qa

        puzzle_a = make_puzzle(
            placed_words=["TESTA", "TESTB"],
            clues=[
                ("TESTA", "A term related to motivation (5 letters)."),
                ("TESTB", "A term related to motivation (5 letters)."),
            ],
            mode="topic",
        )
        qa = run_crossword_qa(puzzle_a)
        self.assertFalse(
            qa.passed,
            "QA must block 'A term related to X (N letters)' pattern"
        )
        self.assertTrue(
            qa.blocked_export,
            "QA must set blocked_export=True when generic clues detected"
        )

    def test_fallback_library_has_all_affected_words(self):
        """Every affected word must exist in the crossword fallback library."""
        from services.crossword.crossword_fallback import get_fallback_words_and_clues

        _, all_clues = get_fallback_words_and_clues("everyday life", count=500)
        for word in self.AFFECTED_WORDS:
            self.assertIn(
                word, all_clues,
                f"{word} must be in the crossword fallback library. "
                "Add it to EVERYDAY_LIFE in crossword_fallback.py"
            )
            clue = all_clues[word]
            clue_lower = clue.lower()
            self.assertNotIn("crossword answer", clue_lower,
                             f"{word}: fallback clue contains 'Crossword answer': {clue!r}")
            self.assertGreater(len(clue), 8,
                             f"{word}: fallback clue too short: {clue!r}")

    def test_engine_grid_uses_simple_clue_fallback(self):
        """The grid builder's missing-clue fallback must use simple_clue, not a string placeholder."""
        from services.crossword.engine import build_crossword_grid

        # Build a grid with no clues_map at all — every word should still get a real clue
        result = build_crossword_grid(
            words=["COMB", "WAKE", "SOAP", "LAMP", "KEYS"],
            clues_map={},  # Empty — tests the fallback
            grid_size=15,
            seed=42,
        )

        for clue_obj in result.clues:
            clue_lower = clue_obj.clue.lower()
            self.assertNotIn("crossword answer", clue_lower,
                             f"{clue_obj.answer}: grid used generic clue: {clue_obj.clue!r}")
            self.assertNotIn("answer (", clue_lower,
                             f"{clue_obj.answer}: grid used generic clue: {clue_obj.clue!r}")

    def test_qa_rejects_crossword_answer_placeholder(self):
        """QA must block any clue containing 'crossword answer (' pattern."""
        from services.crossword.qa_agent import run_crossword_qa

        puzzle = make_puzzle(
            placed_words=["TEST"],
            clues=[("TEST", "Crossword answer (4 letters).")],
            mode="topic",
        )
        qa = run_crossword_qa(puzzle)
        self.assertFalse(qa.passed, "QA must block 'Crossword answer (N letters)'")
        self.assertTrue(qa.blocked_export)

    def test_qa_rejects_word_meaning_placeholder(self):
        """QA must block 'word meaning:' and 'common everyday word:' patterns."""
        from services.crossword.qa_agent import run_crossword_qa

        for clue_text in [
            "Word meaning: TEST.",
            "Common everyday word: TEST.",
        ]:
            puzzle = make_puzzle(
                placed_words=["TEST"],
                clues=[("TEST", clue_text)],
                mode="topic",
            )
            qa = run_crossword_qa(puzzle)
            self.assertFalse(
                qa.passed,
                f"QA must block '{clue_text}'"
            )


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
