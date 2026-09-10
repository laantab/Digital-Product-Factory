"""Duplicate-checklist rule counts inside one chapter, not across the book.

Reported live on 2026-09-01 (project 21312, "Budget Meal Prep for Nurses"):
a complete 8-chapter manuscript, every chapter graded PASS by the quality
engine, was still demoted to Needs correction over two grocery items:

    duplicate_checklist:frozen vegetables
    duplicate_checklist:peanut butter

Each appeared once per chapter in three or four *different* chapters (starter
list, weekly plan, 30-day plan) - never three times inside one chapter. The
rule in ``find_customer_content_defects`` counted bullets book-wide, so normal
recurring structure read as padding.

Ported from the rescued ``onedrive-workspace-phase-a`` branch on 2026-09-09 as
its own small change. Zero paid/external calls: this is a pure-function test.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from services.ebook_document import find_customer_content_defects  # noqa: E402


def _chapter(title: str, items: list[str]) -> str:
    """One chapter with prose of its own, so the duplicate-*paragraph* rule
    (deliberately unchanged) does not fire on the fixture itself."""
    bullets = "\n".join(f"- {i}" for i in items)
    filler = (
        f"{title} is where the plan stops being theory. Nurses working long "
        f"shifts rarely have a spare hour to cook, so everything here is built "
        f"around one prep block that carries the week, and this section deals "
        f"with what {title.lower()} asks of a real schedule.\n\n"
    )
    return f"## {title}\n\n{filler}{bullets}\n\n"


def _checklist_defects(md: str) -> list[str]:
    return [d for d in find_customer_content_defects(md) if d.startswith("duplicate_checklist")]


class DuplicateChecklistScopeTests(unittest.TestCase):
    """Repetition across chapters is book structure; inside one chapter it is padding."""

    def test_an_item_recurring_across_chapters_is_not_a_defect(self):
        md = (
            _chapter("Getting Oriented", ["frozen vegetables", "rolled oats"])
            + _chapter("Your First Week", ["frozen vegetables", "brown rice"])
            + _chapter("Your 30-Day Plan", ["frozen vegetables", "peanut butter"])
        )
        self.assertEqual(
            _checklist_defects(md),
            [],
            "a staple listed once per chapter is normal in a meal-prep book",
        )

    def test_the_same_item_repeated_inside_one_chapter_is_still_a_defect(self):
        md = _chapter(
            "Your Shopping List",
            ["frozen vegetables", "frozen vegetables", "frozen vegetables", "rolled oats"],
        )
        self.assertIn(
            "duplicate_checklist:frozen vegetables",
            find_customer_content_defects(md),
            "three identical bullets in one chapter is padding and must still fail",
        )

    def test_a_padded_chapter_is_caught_even_when_other_chapters_are_clean(self):
        md = (
            _chapter("Getting Oriented", ["frozen vegetables", "rolled oats"])
            + _chapter(
                "Your Shopping List",
                ["peanut butter jars", "peanut butter jars", "peanut butter jars"],
            )
            + _chapter("Your 30-Day Plan", ["frozen vegetables", "brown rice"])
        )
        self.assertEqual(_checklist_defects(md), ["duplicate_checklist:peanut butter jars"])

    def test_the_exact_reported_distribution_no_longer_fails(self):
        # frozen vegetables: ch2 x1, ch4 x1, ch8 x2. peanut butter: ch2, ch4, ch7.
        md = (
            _chapter("Ch1", ["shift snacks"])
            + _chapter("Ch2", ["frozen vegetables", "peanut butter"])
            + _chapter("Ch3", ["batch cooking"])
            + _chapter("Ch4", ["frozen vegetables", "peanut butter"])
            + _chapter("Ch5", ["overnight oats"])
            + _chapter("Ch6", ["skipping breakfast"])
            + _chapter("Ch7", ["peanut butter", "storage containers"])
            + _chapter("Ch8", ["frozen vegetables", "frozen vegetables"])
        )
        self.assertEqual(find_customer_content_defects(md), [])

    def test_the_same_item_padded_in_two_chapters_is_reported_once(self):
        md = (
            _chapter("Week One", ["frozen vegetables"] * 3)
            + _chapter("Week Two", ["frozen vegetables"] * 3)
        )
        self.assertEqual(_checklist_defects(md), ["duplicate_checklist:frozen vegetables"])

    def test_short_items_and_unchaptered_text_still_behave(self):
        self.assertEqual(find_customer_content_defects(""), [])
        short = "- eggs\n- eggs\n- eggs\n"
        self.assertEqual(_checklist_defects(short), [], "very short items stay exempt, as before")
        long_item = "buy the large bag of frozen vegetables"
        flat = f"- {long_item}\n- {long_item}\n- {long_item}\n"
        self.assertIn(
            f"duplicate_checklist:{long_item[:60]}",
            find_customer_content_defects(flat),
            "text with no chapters is still checked as one section",
        )

    def test_front_matter_before_the_first_chapter_is_its_own_section(self):
        # Bullets before any "##" heading are checked as one section of their
        # own: padding there is still caught, and a front-matter item that also
        # appears once inside a chapter is not counted across the boundary.
        padded_front = "- pack the storage containers\n" * 3
        md = padded_front + "\n" + _chapter("Ch1", ["frozen vegetables"])
        self.assertEqual(_checklist_defects(md), ["duplicate_checklist:pack the storage containers"])
        md = "- frozen vegetables\n- frozen vegetables\n\n" + _chapter("Ch1", ["frozen vegetables"])
        self.assertEqual(_checklist_defects(md), [])


if __name__ == "__main__":
    unittest.main()
