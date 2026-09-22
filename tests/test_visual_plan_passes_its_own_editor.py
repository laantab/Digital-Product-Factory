"""Factory 1.8.9: the visual planner produces a plan its own editor accepts.

THE DEFECT THIS CLOSES
----------------------
Container Gardening for Beginners, 2026-09-22: after its photos were
approved, the pictures step still refused to finish: "5 of 9 visuals are the
same kind (workflow). That repetition reads as a template." The planner had
met the photograph minimum (3 of 9) but let one kind of text box fill 56% of
the book, above the editor's 55% limit. Planning is deterministic, so every
rebuild produced the same rejected plan. The editor's rule is unchanged; the
planner now relieves an over-represented kind with the same free Pexels
commission it already uses for the photograph minimum.

Zero cost: no network; Pexels availability and the subject check are patched.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from services import ebook_visual_pipeline as vp
from services.ebook_visual_editorial import MAX_SINGLE_TYPE_SHARE


def _chapter(i, kind, lines=4):
    body = "\n".join(f"{n}. Step {n} for chapter {i}" for n in range(1, lines + 1))
    aid = {"type": kind, "visual_id": f"v_ch{i}", "chapter_index": i, "title": f"Ch {i}",
           "items": [f"Step {n}" for n in range(1, lines + 1)], "status": "resolved"}
    if kind == "photo":
        aid.update({"source": "pexels", "photo_id": str(1000 + i), "photographer": "P"})
    return {"chapter": f"Chapter {i}", "chapter_index": i, "aids": [aid], "chapter_body": body}


def _container_gardening_mix():
    kinds = ["photo", "workflow", "photo", "checklist", "workflow",
             "workflow", "workflow", "photo", "workflow"]
    return [_chapter(i, k, lines=4 + i % 3) for i, k in enumerate(kinds, start=1)]


def _kinds(chapters):
    return [str(c["aids"][0].get("type")) for c in chapters]


class _Supported(unittest.TestCase):
    def setUp(self):
        for target, value in (("services.ebook_pexels.pexels_configured", True),
                              ("services.ebook_visual_match.photography_supported_subject", True)):
            p = patch(target, return_value=value)
            p.start()
            self.addCleanup(p.stop)

    def mix(self, chapters, include=True):
        return vp._commission_media_mix(chapters, title="Container Gardening for Beginners",
                                        topic="container gardening", include_photographs=include)


class PlannerRespectsTheVarietyRule(_Supported):

    def test_container_gardening_mix_is_brought_under_the_limit(self):
        kinds = _kinds(self.mix(_container_gardening_mix()))
        total = len(kinds)
        for kind in set(kinds):
            self.assertLessEqual(kinds.count(kind) / total, MAX_SINGLE_TYPE_SHARE, (kind, kinds))
        self.assertEqual(kinds.count("workflow"), 4, kinds)
        self.assertEqual(kinds.count("photo"), 4, kinds)
        self.assertEqual(kinds.count("checklist"), 1, kinds)

    def test_existing_photographs_are_not_touched(self):
        before = _container_gardening_mix()
        ids = {c["chapter_index"]: c["aids"][0].get("photo_id") for c in before
               if c["aids"][0]["type"] == "photo"}
        after = self.mix(before)
        for c in after:
            if c["chapter_index"] in ids:
                self.assertEqual(c["aids"][0].get("photo_id"), ids[c["chapter_index"]])

    def test_the_new_photo_slot_is_a_free_pexels_commission(self):
        after = self.mix(_container_gardening_mix())
        new = [c["aids"][0] for c in after if c["aids"][0].get("commissioned") == "media_mix"]
        self.assertEqual(len(new), 1)
        self.assertEqual(new[0]["source"], "pexels")
        self.assertEqual(new[0]["status"], "missing")
        self.assertTrue(new[0]["chapter_body"])

    def test_a_balanced_book_is_left_exactly_as_it_was(self):
        kinds = ["photo", "workflow", "photo", "checklist", "workflow",
                 "key points", "workflow", "photo", "checklist"]
        chapters = [_chapter(i, k) for i, k in enumerate(kinds, start=1)]
        self.assertEqual(_kinds(self.mix(chapters)), kinds)

    def test_substantive_visuals_are_never_displaced(self):
        kinds = ["photo", "chart", "photo", "chart", "chart", "chart", "chart", "photo", "workflow"]
        chapters = [_chapter(i, k) for i, k in enumerate(kinds, start=1)]
        self.assertEqual(_kinds(self.mix(chapters)).count("chart"), 5)

    def test_nothing_changes_when_photographs_cannot_be_delivered(self):
        with patch("services.ebook_pexels.pexels_configured", return_value=False):
            kinds = _kinds(self.mix(_container_gardening_mix()))
        self.assertEqual(kinds.count("workflow"), 5)

    def test_photo_minimum_is_still_met_and_the_book_passes_the_variety_rule(self):
        kinds = ["workflow"] * 9
        chapters = [_chapter(i, k, lines=3 + i) for i, k in enumerate(kinds, start=1)]
        after = _kinds(self.mix(chapters))
        self.assertGreaterEqual(after.count("photo"), 3)
        self.assertLessEqual(after.count("workflow") / 9, MAX_SINGLE_TYPE_SHARE)


if __name__ == "__main__":
    unittest.main()
