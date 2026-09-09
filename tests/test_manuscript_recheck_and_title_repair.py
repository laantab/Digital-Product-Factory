"""A paid manuscript must never be stranded by a rule that was wrong.

Reported live on 2026-09-01 (project 21312, "Budget Meal Prep for Nurses"):
the customer confirmed Generate Manuscript, $1.20 of provider spend produced a
complete 11,197-word, 8-chapter manuscript, every chapter graded PASS by the
quality engine — and the stage was still demoted to Needs correction. The whole
reason was two grocery items:

    duplicate_checklist:frozen vegetables
    duplicate_checklist:peanut butter

They appeared as bullets in three or four *different* chapters (starter list,
weekly plan, 30-day plan) — never three times inside one chapter. The only
control the workspace then offered was another *paid* correction.

Three defects are covered here:
  1. the duplicate-checklist rule counted book-wide instead of per chapter;
  2. there was no free way to re-check an already-paid manuscript;
  3. derived outline titles pasted whole research sentences into title slots,
     and those titles were then sent into the paid manuscript prompt.

Zero paid/external calls. FACTORY_TEST_MODE via conftest.
"""
from __future__ import annotations

import contextlib
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"

from app import app  # noqa: E402
from services.ebook_document import find_customer_content_defects  # noqa: E402
from services.ebook_manuscript_engine import QUALITY_PASS  # noqa: E402
from services.ebook_project_workspace import (  # noqa: E402
    STATUS_APPROVED,
    STATUS_AWAITING,
    STATUS_NEEDS_CORRECTION,
    _clean_outline_title,
    _title_phrase,
    derive_draft_outline,
    ensure_workspace,
    new_workspace,
    recheck_manuscript_quality,
    set_stage_status,
    stage_status,
)

APP_JS = ROOT / "static" / "js" / "app.js"


@contextlib.contextmanager
def _passing_depth_and_structure():
    """Hold chapter depth and outline fidelity at PASS.

    These tests are about the *content* layer. Writing an 8x500-word fixture
    just to reach it would test the prose generator, not the rule under test,
    so depth and structure are pinned and asserted separately (unpatched) in
    ``test_a_recheck_still_blocks_a_manuscript_the_quality_engine_rejects``.
    """
    quality = SimpleNamespace(
        status=QUALITY_PASS,
        finding_messages=[],
        as_dict=lambda: {"status": QUALITY_PASS, "findings": []},
    )
    with patch(
        "services.ebook_manuscript_engine.validate_manuscript_quality",
        return_value=quality,
    ), patch(
        "services.ebook_manuscript_engine.apply_quality_to_workspace",
        lambda *a, **k: None,
    ), patch(
        "services.ebook_outline_fidelity.validate_manuscript_outline_fidelity",
        return_value={"ok": True, "findings": []},
    ):
        yield


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


class DuplicateChecklistScopeTests(unittest.TestCase):
    """Repetition across chapters is book structure; inside one chapter it is padding."""

    def test_an_item_recurring_across_chapters_is_not_a_defect(self):
        md = (
            _chapter("Getting Oriented", ["frozen vegetables", "rolled oats"])
            + _chapter("Your First Week", ["frozen vegetables", "brown rice"])
            + _chapter("Your 30-Day Plan", ["frozen vegetables", "peanut butter"])
        )
        self.assertEqual(
            [d for d in find_customer_content_defects(md) if d.startswith("duplicate_checklist")],
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

    def test_short_items_and_unchaptered_text_still_behave(self):
        self.assertEqual(find_customer_content_defects(""), [])
        short = "- eggs\n- eggs\n- eggs\n"
        self.assertEqual(
            [d for d in find_customer_content_defects(short) if d.startswith("duplicate_checklist")],
            [],
            "very short items stay exempt, as before",
        )
        long_item = "buy the large bag of frozen vegetables"
        flat = f"- {long_item}\n- {long_item}\n- {long_item}\n"
        self.assertIn(
            f"duplicate_checklist:{long_item[:60]}",
            find_customer_content_defects(flat),
            "text with no chapters is still checked as one section",
        )


class FreeManuscriptRecheckTests(unittest.TestCase):
    """Re-checking an already-paid manuscript must be free and must be possible."""

    def _workspace_with_manuscript(self, md: str, outline_titles: list[str]) -> dict:
        data = ensure_workspace(
            {
                "title": "Budget Meal Prep for Nurses",
                "subtitle": "Affordable 2-Hour Weekly Prep Plans",
                "author_brand": "A Nurse",
                "content": md,
                "ebook": md,
                "outline": [
                    {"order": i + 1, "title": t, "purpose": "", "approved": True}
                    for i, t in enumerate(outline_titles)
                ],
            }
        )
        ws = data["ebook_workspace"]
        for stage in ("research", "title", "outline"):
            set_stage_status(ws, stage, STATUS_APPROVED)
        ws["paid_call_ledger"] = {
            "budget_cap_usd": 3.5,
            "spent_usd": 1.2,
            "remaining_usd": 2.3,
            "paid_calls": 8,
            "calls": [],
            "pending_estimate": None,
        }
        set_stage_status(ws, "manuscript", STATUS_NEEDS_CORRECTION)
        return data

    def test_a_recheck_never_spends_and_never_calls_a_provider(self):
        titles = ["Getting Oriented", "Your First Week", "Your 30-Day Plan"]
        md = (
            _chapter(titles[0], ["frozen vegetables", "rolled oats"])
            + _chapter(titles[1], ["frozen vegetables", "brown rice"])
            + _chapter(titles[2], ["frozen vegetables", "peanut butter"])
        )
        data = self._workspace_with_manuscript(md, titles)
        before = dict(data["ebook_workspace"]["paid_call_ledger"])
        out = recheck_manuscript_quality(data)
        after = data["ebook_workspace"]["paid_call_ledger"]
        self.assertEqual(after["spent_usd"], before["spent_usd"])
        self.assertEqual(after["paid_calls"], before["paid_calls"])
        self.assertEqual(after["remaining_usd"], before["remaining_usd"])
        self.assertEqual(out["result"]["cost_usd"], 0.0)

    def test_a_recheck_releases_a_manuscript_that_was_never_defective(self):
        """The reported case: chapter depth and structure are fine, and the only
        thing standing between the customer and Approve was the checklist rule."""
        titles = ["Getting Oriented", "Your First Week", "Your 30-Day Plan"]
        md = (
            _chapter(titles[0], ["frozen vegetables", "rolled oats"])
            + _chapter(titles[1], ["frozen vegetables", "brown rice"])
            + _chapter(titles[2], ["frozen vegetables", "peanut butter"])
        )
        data = self._workspace_with_manuscript(md, titles)
        with _passing_depth_and_structure():
            out = recheck_manuscript_quality(data)
        self.assertTrue(out["result"]["cleared"])
        self.assertEqual(out["result"]["findings"], [])
        self.assertEqual(out["result"]["status_before"], STATUS_NEEDS_CORRECTION)
        self.assertEqual(stage_status(data["ebook_workspace"], "manuscript"), STATUS_AWAITING)
        self.assertEqual(data["ebook_workspace"]["next_action"], "approve_manuscript")

    def test_a_recheck_still_blocks_a_manuscript_the_quality_engine_rejects(self):
        """Nothing here weakens the real gate: thin chapters still fail, unpatched."""
        titles = ["Getting Oriented", "Your First Week"]
        md = _chapter(titles[0], ["rolled oats"]) + _chapter(titles[1], ["brown rice"])
        data = self._workspace_with_manuscript(md, titles)
        out = recheck_manuscript_quality(data)
        self.assertFalse(out["result"]["cleared"])
        self.assertTrue(
            any("THIN_CHAPTER" in f for f in out["result"]["findings"]),
            out["result"]["findings"],
        )
        self.assertEqual(
            stage_status(data["ebook_workspace"], "manuscript"), STATUS_NEEDS_CORRECTION
        )

    def test_a_recheck_leaves_the_manuscript_text_untouched(self):
        titles = ["Getting Oriented", "Your First Week"]
        md = _chapter(titles[0], ["rolled oats"]) + _chapter(titles[1], ["brown rice"])
        data = self._workspace_with_manuscript(md, titles)
        recheck_manuscript_quality(data)
        self.assertEqual(data["content"], md)
        self.assertEqual(data["ebook"], md)

    def test_a_recheck_keeps_a_padded_checklist_blocked(self):
        """Depth and structure held constant, the content rule must still bite."""
        titles = ["Your Shopping List"]
        md = _chapter(
            titles[0],
            ["buy the large bag of frozen vegetables"] * 3 + ["rolled oats"],
        )
        data = self._workspace_with_manuscript(md, titles)
        with _passing_depth_and_structure():
            out = recheck_manuscript_quality(data)
        self.assertFalse(out["result"]["cleared"])
        self.assertIn(
            "duplicate_checklist:buy the large bag of frozen vegetables",
            out["result"]["findings"],
        )
        self.assertEqual(
            stage_status(data["ebook_workspace"], "manuscript"), STATUS_NEEDS_CORRECTION
        )

    def test_a_recheck_refuses_when_there_is_nothing_to_check(self):
        data = ensure_workspace({"title": "Empty"})
        with self.assertRaises(ValueError):
            recheck_manuscript_quality(data)

    def test_a_recheck_will_not_touch_an_approved_manuscript(self):
        titles = ["Getting Oriented"]
        md = _chapter(titles[0], ["rolled oats"])
        data = self._workspace_with_manuscript(md, titles)
        set_stage_status(data["ebook_workspace"], "manuscript", STATUS_APPROVED)
        with self.assertRaises(ValueError):
            recheck_manuscript_quality(data)

    def test_the_blocked_message_names_the_real_reason(self):
        """It used to say "structural FAIL findings remain" whatever the cause.

        The live report was a manuscript whose structure findings were empty --
        the block was a content finding -- so the customer went looking for a
        structural problem that did not exist. The panel now goes further and
        names the chapter and the problem in plain words; see
        tests/test_manuscript_panel_plain_language.py for the full contract.
        """
        js = APP_JS.read_text(encoding="utf-8")
        self.assertNotIn("structural FAIL findings remain", js)
        panel = js.split("function manuscriptStagePanelHtml(", 1)[1].split(
            "// ---------- one-click build ----------", 1)[0]
        self.assertIn("plainManuscriptIssues(m)", panel)
        self.assertIn("Chapter ${ch.order}", js)

    def test_the_route_exists_and_is_wired_to_a_free_button(self):
        rules = {r.rule for r in app.url_map.iter_rules()}
        self.assertIn("/ebook-workspace/<int:project_id>/recheck-manuscript", rules)
        js = APP_JS.read_text(encoding="utf-8")
        self.assertIn("recheckManuscriptQuality", js)
        self.assertIn("/recheck-manuscript", js)
        # Offered in plain words, and free-ness stated on the control itself.
        self.assertIn("Check again first (free)", js)
        handler = js.split("async function recheckManuscriptQuality(", 1)[1].split(
            "async function approveEbookStage(", 1)[0]
        # A free action must not route through the paid estimate/confirm flow.
        self.assertNotIn("estimate-cost", handler)
        self.assertNotIn("confirmation_token", handler)


class OutlineTitleRepairTests(unittest.TestCase):
    """A research sentence must never be pasted into a chapter title.

    The live outline produced: "The Core Method: Steps to They need practical
    meal-planning help tailored to long shifts and limited time." — and that
    title was sent verbatim into the paid manuscript prompt.
    """

    SENTENCE = "They need practical meal-planning help tailored to long shifts and limited time."

    def test_a_research_sentence_is_reduced_to_a_title_phrase(self):
        self.assertEqual(_title_phrase(self.SENTENCE, 6), "Practical meal-planning help")

    def test_a_phrase_never_ends_on_dangling_punctuation(self):
        for probe in (self.SENTENCE, "Busy parents who want dinner sorted, without a big shop", "x, y"):
            with self.subTest(probe=probe[:32]):
                out = _title_phrase(probe, 6)
                self.assertFalse(out.endswith((",", ".", ";", ":", "-", " ")), out)

    def test_empty_and_short_input_survive_untouched(self):
        self.assertEqual(_title_phrase(""), "")
        self.assertEqual(_title_phrase(None), "")
        self.assertEqual(_title_phrase("Beginner watercolor"), "Beginner watercolor")

    def test_a_title_with_a_sentence_buried_in_it_is_repaired(self):
        repaired = _clean_outline_title(f"The Core Method: Steps to {self.SENTENCE}")
        self.assertEqual(repaired, "The Core Method: Steps to practical meal-planning help")
        self.assertNotIn("They need", repaired)

    def test_a_good_title_is_left_alone(self):
        for good in (
            "Common Pitfalls and How to Avoid Them",
            "Chapter 4: Your Plan",
            "Tools, Templates, and Checklists You Can Use",
        ):
            with self.subTest(good=good):
                self.assertEqual(_clean_outline_title(good), good)

    def test_the_derived_outline_never_contains_a_research_sentence(self):
        data = {
            "title": "Meal Prep Guide for Busy Nurses",
            "ebook_workspace": new_workspace(
                topic="Meal Prep Guide for Busy Nurses",
                audience="Nurses with demanding schedules",
                outcome=self.SENTENCE,
            ),
        }
        titles = [c["title"] for c in derive_draft_outline(data)["chapters"]]
        self.assertEqual(len(titles), 8)
        for title in titles:
            with self.subTest(title=title):
                self.assertNotIn("They need", title)
                self.assertFalse(title.endswith("."), title)
                self.assertTrue(title.strip())
        self.assertEqual(titles[0], "Welcome: What This Guide Covers")

    def test_a_short_audience_still_personalises_the_action_plan(self):
        data = {
            "title": "Budgeting",
            "ebook_workspace": new_workspace(
                topic="Budgeting",
                audience="new parents",
                outcome="a simple monthly system",
            ),
        }
        titles = [c["title"] for c in derive_draft_outline(data)["chapters"]]
        self.assertEqual(titles[-1], "Your 30-Day Action Plan for New parents")
        self.assertEqual(titles[1], "Getting Oriented: Your Starting Point with Budgeting")


if __name__ == "__main__":
    unittest.main()
