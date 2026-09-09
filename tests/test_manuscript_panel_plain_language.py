"""The manuscript stage must read like a product, not like a test report.

Reported live on 2026-09-01: the panel opened with a per-chapter
PASS / NEEDS_CORRECTION list with word counts, a raw engine code
("Ch 7 ...: PURPOSE_MISALIGN — Chapter body does not cover the approved
purpose for this title"), a monospace dump of the raw markdown, and two
competing action boxes -- one free, one paid. Lonnie's note: "I don't think the
user needs to see all of this information... Let's not scare off the user."

FACTORY_BLUEPRINT.md §3 already required this: plain friendly language, one
clear recommendation and one obvious next action, and advanced evidence kept
behind expandable sections.

Nothing was deleted. These tests pin both halves of that: the calm default view,
and the same technical evidence still being present one disclosure away.

Zero paid/external calls.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"

APP_JS = ROOT / "static" / "js" / "app.js"


def _panel_source() -> str:
    js = APP_JS.read_text(encoding="utf-8")
    return js.split("function manuscriptStagePanelHtml(", 1)[1].split(
        "// ---------- one-click build ----------", 1
    )[0]


class PlainLanguageTests(unittest.TestCase):
    def setUp(self):
        self.js = APP_JS.read_text(encoding="utf-8")
        self.panel = _panel_source()

    def test_raw_engine_codes_are_translated_for_the_customer(self):
        table = self.js.split("const MANUSCRIPT_FINDING_PLAIN = {", 1)[1].split("};", 1)[0]
        # The code the customer actually hit, plus the other common ones.
        for code in (
            "PURPOSE_MISALIGN",
            "THIN_CHAPTER",
            "GENERIC_FILLER",
            "MISSING_REQUIRED_EXAMPLE",
            "PLACEHOLDER",
        ):
            with self.subTest(code=code):
                self.assertIn(code, table)
        self.assertIn("drifts from what its title promises", table)

    def test_an_unmapped_code_still_says_something_readable(self):
        helper = self.js.split("function plainManuscriptFinding(", 1)[1].split(
            "// \"Chapter 7", 1
        )[0]
        # Falls back to the engine's own message rather than showing nothing.
        self.assertIn("fallback", helper)

    def test_the_default_view_leads_with_a_plain_sentence(self):
        self.assertIn("Your draft is written and saved", self.panel)
        self.assertIn("passed every quality check", self.panel)
        self.assertIn("needs a small fix before you approve it", self.panel)

    def test_the_default_view_does_not_shout_raw_status_words(self):
        # The bare engine verdicts and the old scolding copy must not appear in
        # the always-visible part of the panel.
        visible = self.panel.split("Technical details", 1)[0]
        for noisy in (
            "NEEDS_CORRECTION",
            "Approve Manuscript is disabled until quality is PASS",
            "Chapter-level / QA findings",
            "Generated chapter list",
            "Preserved draft (preview)",
        ):
            with self.subTest(noisy=noisy):
                self.assertNotIn(noisy, visible)

    def test_the_raw_markdown_dump_is_gone_from_the_default_view(self):
        self.assertNotIn("font-mono", self.panel)
        self.assertNotIn("whitespace-pre-wrap", self.panel)
        # The draft is still readable, rendered, and folded away.
        self.assertIn("Read your draft", self.panel)
        self.assertIn("md(String(m.content)", self.panel)


class OneObviousNextActionTests(unittest.TestCase):
    def setUp(self):
        self.panel = _panel_source()
        self.js = APP_JS.read_text(encoding="utf-8")

    def test_the_panel_never_offers_two_competing_primary_actions(self):
        # Exactly two primaries exist in the whole panel -- Approve and Fix --
        # and they render in mutually exclusive branches, so the customer only
        # ever sees one.
        primaries = re.findall(r'class="btn-primary[^"]*"[^>]*>([^<]+)<', self.panel)
        self.assertEqual(
            sorted(p.strip() for p in primaries),
            ["Approve Manuscript", "Fix This For Me…"],
            primaries,
        )

    def test_the_free_recheck_stays_available_but_secondary(self):
        self.assertIn("Check again first (free)", self.panel)
        self.assertIn("data-ws-recheck-manuscript", self.panel)
        recheck_line = next(
            line for line in self.panel.splitlines() if "data-ws-recheck-manuscript" in line
        )
        self.assertNotIn("btn-primary", recheck_line)

    def test_the_top_ribbon_matches_the_panel(self):
        ribbon = self.js.split("Or step by step:", 1)[1].split(
            "data-ws-stage-panel", 1
        )[0]
        self.assertIn("Fix This For Me", ribbon)
        self.assertNotIn("Re-check Quality (free)", ribbon)

    def test_cost_is_still_stated_before_any_paid_action(self):
        self.assertIn("You will see the cost before anything is spent", self.panel)
        self.assertIn("budget left", self.panel)
        self.assertIn("Your draft is kept exactly as it is", self.panel)

    def test_approve_and_fix_render_in_mutually_exclusive_branches(self):
        approve_line = next(
            line for line in self.panel.splitlines() if "data-ws-approve-manuscript" in line
        )
        fix_line = next(
            line for line in self.panel.splitlines() if "Fix This For Me" in line
        )
        self.assertNotIn("Fix This For Me", approve_line)
        self.assertNotIn("Approve Manuscript", fix_line)
        # ...gated on canApprove and needsCorrection respectively.
        self.assertIn("canApprove", self.panel)
        self.assertIn("needsCorrection", self.panel)


class TechnicalEvidenceStillAvailableTests(unittest.TestCase):
    """Hidden by default is not the same as deleted."""

    def setUp(self):
        self.panel = _panel_source()

    def test_the_chapter_list_and_codes_live_behind_a_disclosure(self):
        details = self.panel.split("Technical details", 1)[1]
        self.assertIn("Generated chapter list", details)
        self.assertIn("Chapter-level / QA findings", details)
        self.assertIn("quality_status", details)
        self.assertIn("techChapters", details)
        self.assertIn("techFindings", details)
        # ...and those still carry the per-chapter numbers and the raw codes.
        self.assertIn("word_count", self.panel)
        self.assertIn("f.code", self.panel)

    def test_both_disclosures_are_closed_by_default(self):
        for block in re.findall(r"<details[^>]*>", self.panel):
            with self.subTest(block=block):
                self.assertNotIn("open", block)

    def test_the_panel_is_rendered_through_one_named_function(self):
        js = APP_JS.read_text(encoding="utf-8")
        self.assertIn("body = manuscriptStagePanelHtml(ws, stage);", js)
        self.assertEqual(js.count("function manuscriptStagePanelHtml("), 1)


if __name__ == "__main__":
    unittest.main()
