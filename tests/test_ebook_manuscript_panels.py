"""Manuscript-derived supporting-panel extraction. Zero external calls."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"

from services.ebook_manuscript_panels import extract_chapter_panels  # noqa: E402

_SAMPLE_CHAPTER = """The Deadlift: Learning to Hinge Without Guessing

### A simple setup check for safer reps

Use this checklist before your first set:

1. Stand with your feet about hip-width apart.
2. Push your hips back as if closing a car door behind you.
3. Keep your chest open and your neck neutral.

Two common errors show up early. The first is squatting the deadlift by
dropping too low. The second is reaching for the bell by rounding the spine.

A useful regression is elevating the kettlebell on yoga blocks or a low
step, which shortens the range of motion so the hinge can be learned safely.

### Your first 10-minute deadlift practice

- 2 minutes: bodyweight hip hinges
- 3 sets of 5 elevated kettlebell deadlifts

**Deadlift readiness note:** If you can feel the difference between bending
at the hips and collapsing through the back, you are building the right
foundation.
"""


class TestManuscriptPanels(unittest.TestCase):
    def test_01_extracts_real_checklist_from_manuscript_text(self):
        panels = extract_chapter_panels(_SAMPLE_CHAPTER)
        self.assertIn("setup_checklist", panels)
        self.assertGreaterEqual(len(panels["setup_checklist"]), 3)
        self.assertIn("hip-width", panels["setup_checklist"][0])

    def test_02_extracts_common_mistakes_verbatim(self):
        panels = extract_chapter_panels(_SAMPLE_CHAPTER)
        self.assertIn("common_mistakes", panels)
        self.assertIn("squatting the deadlift", panels["common_mistakes"])

    def test_03_extracts_regression(self):
        panels = extract_chapter_panels(_SAMPLE_CHAPTER)
        self.assertIn("regression", panels)
        self.assertIn("yoga blocks", panels["regression"])

    def test_04_extracts_practice_steps(self):
        panels = extract_chapter_panels(_SAMPLE_CHAPTER)
        self.assertIn("practice_steps", panels)
        self.assertTrue(any("hip hinges" in s for s in panels["practice_steps"]))

    def test_05_extracts_readiness_note(self):
        panels = extract_chapter_panels(_SAMPLE_CHAPTER)
        self.assertIn("readiness_note", panels)
        self.assertIn("right foundation", panels["readiness_note"])

    def test_06_degrades_gracefully_on_unstructured_text(self):
        panels = extract_chapter_panels("Just a plain paragraph with no structure at all.")
        self.assertEqual(panels, {})

    def test_07_empty_input_does_not_raise(self):
        self.assertEqual(extract_chapter_panels(""), {})
        self.assertEqual(extract_chapter_panels(None), {})

    def test_08_short_regression_fragments_are_filtered(self):
        text = "### Notes\n\nregression: too short\n\n"
        panels = extract_chapter_panels(text)
        self.assertNotIn("regression", panels)


if __name__ == "__main__":
    unittest.main()
