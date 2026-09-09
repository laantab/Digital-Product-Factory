"""CROSSWORD CONTENT-SCOPE + ANSWER-KEY + ZIP PACKAGE REPAIR (2026-09-09).

Discovered via a real customer product (project #362, "American
Automobiles", Single page, Include Answer Key: Yes, Include Cover: No):

  1. TOPIC SCOPE -- the crossword's clues included automotive PARTS
     ("Protective bar at the front or back of a vehicle" / BUMPER, "A
     vehicle's underlying structural frame" / CHASSIS) even though the
     customer asked for "American Automobiles", not car parts.
  2. ANSWER KEY -- the customer selected Include Answer Key: Yes and
     received a 1-page PDF with no solution page at all.
  3. ZIP PACKAGE -- audited separately; see the writeup in the Feature
     Stability Matrix for what was found (the 3-file contract was
     confirmed intentional, not a defect -- no code change needed there).

No external/paid API call is made by any test in this file.
"""
from __future__ import annotations

import base64
import unittest

from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf
from services.factory.topic_vocabulary import resolve_topic_vocabulary
from services.product import _crossword_pdf_payload

# The exact customer product this file repairs.
AMERICAN_AUTOMOBILES_SINGLE_PAGE_FIELDS = {
    "audience": "adults",
    "book_title": "American Automobiles",
    "clue_style": "Easy",
    "creation_mode": "Topic (AI generates words)",
    "custom_words": "",
    "difficulty": "Easy",
    "include_answer_key": "Yes",
    "include_cover": "No",
    "output_format": "Single page",
    "puzzles": "1",
    "theme": "American Automobiles",
}

AUTOMOTIVE_PART_WORDS = {
    "BUMPER", "CHASSIS", "RADIATOR", "PISTON", "ALTERNATOR", "TRANSMISSION",
    "MUFFLER", "AXLE", "SPARKPLUG", "CARBURETOR", "WINDSHIELD", "SUSPENSION",
    "DASHBOARD", "ENGINE", "FENDER", "HUBCAP", "IGNITION", "ODOMETER",
    "SPEEDOMETER", "HORSEPOWER",
}
BASEBALL_EQUIPMENT_WORDS = {
    "GLOVE", "BASEBALLCAP", "BATTINGCAGE", "BULLPEN", "MOUND", "DUGOUT",
    "STADIUM", "SCOREBOARD",
}


def _page_count(pdf_bytes: bytes) -> int:
    from pypdf import PdfReader
    import io
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


class TopicScopeRegressionTests(unittest.TestCase):
    """PART 1: American Automobiles must return brands/models/manufacturers,
    never automotive parts -- unless the customer actually asked for parts."""

    def test_american_automobiles_excludes_automotive_parts(self):
        result = resolve_topic_vocabulary("American Automobiles", 40)
        self.assertTrue(result.matched)
        contamination = AUTOMOTIVE_PART_WORDS & set(result.words)
        self.assertFalse(
            contamination,
            f"American Automobiles vocabulary contained parts: {contamination}",
        )

    def test_the_real_customer_product_had_no_part_clues(self):
        # Reproduces project #362 exactly.
        result = _crossword_pdf_payload(dict(AMERICAN_AUTOMOBILES_SINGLE_PAGE_FIELDS))
        self.assertIsNone(result.get("errors"))
        pdf_bytes = base64.b64decode(result["pdf_bytes"])
        # A crude but effective content check: none of the reported bad
        # clue phrases (or their answers) may appear in the rendered PDF.
        from pypdf import PdfReader
        import io
        text = "".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_bytes)).pages).upper()
        for bad_phrase in ("PROTECTIVE BAR AT THE FRONT", "UNDERLYING STRUCTURAL FRAME"):
            self.assertNotIn(bad_phrase, text)
        for bad_word in AUTOMOTIVE_PART_WORDS:
            self.assertNotIn(bad_word, text)

    def test_car_parts_topic_still_returns_real_parts_vocabulary(self):
        # The final, critical test: automotive parts are not globally
        # banned -- a customer who actually asks for them still gets them.
        result = resolve_topic_vocabulary("Car Parts", 40)
        self.assertTrue(result.matched)
        self.assertTrue(set(result.words) & AUTOMOTIVE_PART_WORDS)
        # And Car Parts must not return brand/model names instead.
        self.assertNotIn("MUSTANG", result.words)
        self.assertNotIn("FORD", result.words)


class CrossTopicScopeGenericityTests(unittest.TestCase):
    """Prove the fix is a generic mechanism, not an American-Automobiles-
    only patch. Each topic either (a) doesn't match the shared engine at
    all, in which case no contamination is possible, or (b) matches and
    must stay within the requested scope."""

    def test_ocean_animals_returns_animals_not_equipment(self):
        result = resolve_topic_vocabulary("Ocean Animals", 40)
        self.assertTrue(result.matched)
        equipment = {"ANCHOR", "SAILOR", "LIGHTHOUSE", "HARBOR", "VOYAGE"}
        self.assertFalse(equipment & set(result.words))

    def test_dog_breeds_is_safe_whether_or_not_it_matches(self):
        result = resolve_topic_vocabulary("Dog Breeds", 40)
        equipment = {"LEASH", "KENNEL", "CRATE", "COLLAR"}
        self.assertFalse(equipment & set(result.words))

    def test_baseball_players_returns_players_not_equipment(self):
        result = resolve_topic_vocabulary("Baseball Players", 40)
        self.assertTrue(result.matched)
        self.assertFalse(BASEBALL_EQUIPMENT_WORDS & set(result.words))
        self.assertTrue(set(result.words) & {"BATTER", "CATCHER", "PITCHER"})

    def test_baseball_general_topic_keeps_its_full_varied_pool(self):
        # Regression guard: narrowing "Baseball Players" must not also
        # narrow the general "Baseball" topic required by Step 17's
        # 12-topic acceptance sweep (services/factory/topic_vocabulary.py
        # Phase 1) -- that one still needs real variety to build puzzles.
        result = resolve_topic_vocabulary("Baseball", 40)
        self.assertTrue(result.matched)
        self.assertGreaterEqual(len(result.words), 25)
        self.assertTrue(set(result.words) & BASEBALL_EQUIPMENT_WORDS)

    def test_garden_vegetables_is_safe_whether_or_not_it_matches(self):
        result = resolve_topic_vocabulary("Garden Vegetables", 40)
        tools = {"TROWEL", "SHOVEL", "RAKE", "HOSE", "WATERINGCAN"}
        self.assertFalse(tools & set(result.words))


class AnswerKeyContractTests(unittest.TestCase):
    """PART 2: Include Answer Key = Yes must produce a real solution page,
    for every Crossword output format, including "Single page"."""

    def test_the_real_customer_product_now_gets_its_answer_key(self):
        result = _crossword_pdf_payload(dict(AMERICAN_AUTOMOBILES_SINGLE_PAGE_FIELDS))
        self.assertIsNone(result.get("errors"))
        pdf_bytes = base64.b64decode(result["pdf_bytes"])
        self.assertGreaterEqual(_page_count(pdf_bytes), 2, "no answer-key page was added")

    def test_single_page_answer_key_yes_includes_a_solved_grid(self):
        req = CrosswordPdfRequest(
            product_title="Test", theme="American Automobiles", mode="topic",
            output_type="single_page", include_answer_key=True, include_cover=False,
        )
        result = build_crossword_pdf(req)
        self.assertFalse(result.errors, result.errors)
        self.assertGreaterEqual(_page_count(result.pdf_bytes), 2)
        self.assertGreaterEqual(result.layout_info.get("answer_key_page_count", 0), 1)

    def test_single_page_answer_key_no_stays_one_page(self):
        req = CrosswordPdfRequest(
            product_title="Test", theme="American Automobiles", mode="topic",
            output_type="single_page", include_answer_key=False, include_cover=False,
        )
        result = build_crossword_pdf(req)
        self.assertFalse(result.errors, result.errors)
        self.assertEqual(_page_count(result.pdf_bytes), 1)

    def test_full_book_gets_one_solution_page_per_puzzle(self):
        req = CrosswordPdfRequest(
            product_title="Test", theme="American Automobiles", mode="topic",
            output_type="book", number_of_puzzles=3, include_answer_key=True,
            include_cover=False,
        )
        result = build_crossword_pdf(req)
        self.assertFalse(result.errors, result.errors)
        valid = [p for p in result.puzzles if not p.errors and p.clues]
        self.assertGreaterEqual(len(valid), 1)
        self.assertEqual(_page_count(result.pdf_bytes), len(valid) * 2)


if __name__ == "__main__":
    unittest.main()
