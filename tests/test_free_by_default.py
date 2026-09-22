"""Factory 1.8.7: pictures and covers are free by default.

Paid picture and cover AI must not run because of settings saved when a book
was created. It needs a separate, explicit, capped owner grant, and even then
the free options (Pexels, an approved chapter photo) are tried first.
No network: Pexels and image generation are patched; nothing is billed.
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from services import ebook_customer_path as ecp  # noqa: E402
from services.ebook_factory_pipeline import (  # noqa: E402
    AI_VISUAL_UNIT_USD,
    charge_visual_ai_call,
    fill_photo_aid_with_ai,
    grant_paid_visual_ai,
    paid_visual_ai_grant,
    paid_visual_grant_remaining_usd,
    remaining_visual_budget_usd,
    revoke_paid_visual_ai,
    visual_ai_authorized,
)

OWNER = "owner@example.com"


def _project5_like() -> dict:
    """Same shape as Container Gardening for Beginners on 2026-09-21."""
    return {
        "fields": {"include_images": "Yes", "visuals_authorized": "true",
                   "visual_budget_cap_usd": "0.48", "topic": "container gardening"},
        "ebook_workspace": {"paid_call_ledger": {
            "budget_cap_usd": 7.0, "spent_usd": 4.1, "remaining_usd": 2.9, "paid_calls": 26,
            "calls": [{"purpose": "generate_manuscript", "provider": "openai"}]}},
    }


def _aid() -> dict:
    return {"type": "stock photo", "title": "Pots on a balcony", "chapter": "Choosing Containers",
            "chapter_index": 3, "visual_id": "v3_0"}


class CreationSettingsAloneNeverSpend(unittest.TestCase):

    def test_project5_settings_do_not_authorize_paid_pictures(self):
        data = _project5_like()
        self.assertFalse(visual_ai_authorized(data, data["fields"]))
        self.assertEqual(remaining_visual_budget_usd(data, data["fields"]), 0.0)

    def test_charge_is_refused_and_ledger_untouched(self):
        data = _project5_like()
        before = dict(data["ebook_workspace"]["paid_call_ledger"])
        self.assertFalse(charge_visual_ai_call(data, data["fields"]))
        led = data["ebook_workspace"]["paid_call_ledger"]
        self.assertEqual(led["spent_usd"], before["spent_usd"])
        self.assertEqual(led["remaining_usd"], before["remaining_usd"])
        self.assertEqual(led["paid_calls"], before["paid_calls"])
        self.assertFalse(data.get("visual_ai_spend_usd"))

    def test_missing_picture_is_not_generated(self):
        data = _project5_like()
        with patch("services.ebook_package.generate_visual_image") as gen:
            out = fill_photo_aid_with_ai(_aid(), package_id="free-1", data=data,
                                         fields=data["fields"], title="t", topic="t")
        gen.assert_not_called()
        self.assertNotEqual(out.get("source"), "ai_generated")


class ExplicitGrant(unittest.TestCase):

    def test_grant_enables_and_is_capped_by_its_own_maximum(self):
        data = grant_paid_visual_ai(_project5_like(), max_usd=AI_VISUAL_UNIT_USD, granted_by=OWNER)
        self.assertTrue(visual_ai_authorized(data, data["fields"]))
        self.assertTrue(charge_visual_ai_call(data, data["fields"]))
        self.assertFalse(charge_visual_ai_call(data, data["fields"]))  # grant used up
        self.assertEqual(paid_visual_grant_remaining_usd(data), 0.0)

    def test_grant_does_not_reset_cost_history(self):
        data = grant_paid_visual_ai(_project5_like(), max_usd=0.2, granted_by=OWNER)
        led = data["ebook_workspace"]["paid_call_ledger"]
        self.assertEqual((led["spent_usd"], led["remaining_usd"], led["paid_calls"]), (4.1, 2.9, 26))
        charge_visual_ai_call(data, data["fields"])
        self.assertAlmostEqual(led["spent_usd"], 4.1 + AI_VISUAL_UNIT_USD, places=4)

    def test_grant_needs_a_name_and_a_positive_amount_within_budget(self):
        with self.assertRaises(ValueError):
            grant_paid_visual_ai(_project5_like(), max_usd=0.2, granted_by="")
        for bad in (0, -1, "x"):
            with self.assertRaises(ValueError):
                grant_paid_visual_ai(_project5_like(), max_usd=bad, granted_by=OWNER)
        with self.assertRaises(ValueError):
            grant_paid_visual_ai(_project5_like(), max_usd=3.0, granted_by=OWNER)  # > $2.90 left

    def test_revoke_turns_it_off_and_keeps_history(self):
        data = grant_paid_visual_ai(_project5_like(), max_usd=0.2, granted_by=OWNER)
        charge_visual_ai_call(data, data["fields"])
        spent = data["visual_ai_spend_usd"]
        revoke_paid_visual_ai(data, revoked_by=OWNER)
        self.assertIsNone(paid_visual_ai_grant(data))
        self.assertFalse(visual_ai_authorized(data, data["fields"]))
        self.assertEqual(data["visual_ai_spend_usd"], spent)

    def test_malformed_grant_counts_as_no_grant(self):
        for bad in ({"max_usd": 1}, {"granted_by": OWNER}, {"max_usd": "x", "granted_by": OWNER}, "yes"):
            data = _project5_like()
            data["paid_visual_ai_grant"] = bad
            self.assertFalse(visual_ai_authorized(data, data["fields"]), bad)


class CoverTriesFreeOptionsFirst(unittest.TestCase):

    def setUp(self):
        fd, self.photo = tempfile.mkstemp(suffix=".jpg")
        os.close(fd)
        self.addCleanup(lambda: os.path.exists(self.photo) and os.unlink(self.photo))

    def _with_interior_photo(self, data: dict) -> dict:
        data["visual_plan"] = {"chapters": [{"aids": [
            {"type": "photo", "asset_path": self.photo, "match_status": "pass"}]}]}
        return data

    def _run_cover(self, data):
        ai = MagicMock(return_value="")
        with patch.object(ecp, "search_pexels", return_value={"photos": []}), \
             patch.object(ecp, "fixture_mode", return_value=False), \
             patch.object(ecp, "_generate_ai_cover_candidate", ai):
            out = ecp.complete_photo_cover(data, title="Container Gardening for Beginners",
                                           subtitle="", author="", fields=data["fields"],
                                           package_id="free-cover")
        return out, ai

    def test_approved_chapter_photo_is_used_before_any_ai_even_with_a_grant(self):
        data = self._with_interior_photo(
            grant_paid_visual_ai(_project5_like(), max_usd=0.2, granted_by=OWNER))
        self.assertTrue(ecp.has_approved_interior_photo(data))
        _, ai = self._run_cover(data)
        ai.assert_not_called()

    def test_ai_is_only_reached_when_no_free_option_is_left(self):
        # Proves the test above is not vacuous: with a grant and nothing free
        # left, the (patched) AI step is reached.
        data = grant_paid_visual_ai(_project5_like(), max_usd=0.2, granted_by=OWNER)
        self.assertFalse(ecp.has_approved_interior_photo(data))
        _, ai = self._run_cover(data)
        ai.assert_called_once()

    def test_without_a_grant_the_real_ai_cover_step_generates_nothing(self):
        data = _project5_like()
        with patch("services.ebook_package.generate_visual_image") as gen:
            layout = ecp._generate_ai_cover_candidate(
                data, title="t", subtitle="", fields=data["fields"], package_id="free-cover-2")
        gen.assert_not_called()
        self.assertEqual(layout, "")

    def test_unapproved_or_missing_photos_do_not_count(self):
        for aid in ({"type": "photo", "asset_path": self.photo, "match_status": "needs_user_review"},
                    {"type": "photo", "asset_path": "/nonexistent.jpg", "match_status": "pass"},
                    {"type": "workflow", "asset_path": self.photo, "match_status": "pass"}):
            self.assertFalse(ecp.has_approved_interior_photo({"visual_plan": {"chapters": [{"aids": [aid]}]}}))


if __name__ == "__main__":
    unittest.main()
