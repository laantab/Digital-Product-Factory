"""Factory 1.8.8: the website can accept and approve photos it can only read
from storage.

THE DEFECT THIS CLOSES
----------------------
Container Gardening for Beginners, 2026-09-22: after a builder run had
published all nine pictures to storage, the review screen showed every
thumbnail, but "accept this photograph" answered "Photograph file is
missing" for all three photos that needed review. Accept and approve are
light actions that run on the website; unlike work sent to the builder,
they never fetched the pictures from storage first, so they looked for the
builder's own file path on a disk that never held it.

Zero cost: in-memory storage, fixture pictures, no photograph downloaded,
no paid call.
"""
from __future__ import annotations

import os
import shutil
import tempfile

from tests.test_builder_pictures_reach_the_website import _StorageCase

from services import ebook_workspace_actions as wsa
from services.ebook_visual_pipeline import is_photo_aid, required_aids


class WebsiteAcceptsStoredPhotos(_StorageCase):

    def _website_copy(self):
        data = self._build_on_builder()
        # The builder's temporary disk is gone when its task ends.
        shutil.rmtree(self.builder_root)
        data["_project_id"] = self.pid
        return data

    def _photo(self, data):
        photos = [a for a in required_aids(data["visual_plan"]) if is_photo_aid(a)]
        if photos:
            return photos[0]
        # The zero-cost fixture renders only local graphics. Treat one stored
        # picture as a stock photograph awaiting review -- exactly the state
        # of Container Gardening for Beginners' Chapter 3 photo. Its bytes are
        # the real stored picture, so the storage path is the one under test.
        aid = next(a for a in required_aids(data["visual_plan"]) if a.get("asset_path"))
        aid.update({"type": "photo", "source": "pexels", "match_status": "needs_user_review",
                    "photographer": "Test Photographer", "photo_id": "1",
                    "pexels": {"photo_id": "1", "photographer": "Test Photographer"}})
        self.assertTrue(is_photo_aid(aid))
        return aid

    def test_accept_photo_works_when_the_file_is_only_in_storage(self):
        data = self._website_copy()
        vid = str(self._photo(data)["visual_id"])
        with self._on(self.website_root):
            data, msg = wsa.visuals(data, {"action": "accept-photo", "visual_id": vid})
        aid = next(a for a in required_aids(data["visual_plan"]) if a.get("visual_id") == vid)
        self.assertTrue(aid.get("user_accepted"))
        self.assertTrue(str(aid["asset_path"]).startswith(self.website_root), aid["asset_path"])
        self.assertTrue(os.path.isfile(aid["asset_path"]))
        self.assertIn("accepted", msg.lower())

    def test_every_light_action_fetches_from_storage_first(self):
        for action in sorted(wsa.VISUAL_LIGHT_ACTIONS - {"approve"}):
            with self.subTest(action=action):
                root = tempfile.mkdtemp(prefix="website-")
                self.addCleanup(shutil.rmtree, root, True)
                self.builder_root = tempfile.mkdtemp(prefix="builder-exports-")
                data = self._website_copy()
                vid = str(self._photo(data)["visual_id"])
                with self._on(root):
                    data, _ = wsa.visuals(data, {"action": action, "visual_id": vid})
                aid = next(a for a in required_aids(data["visual_plan"])
                           if a.get("visual_id") == vid)
                self.assertTrue(os.path.isfile(aid["asset_path"]), (action, aid["asset_path"]))

    def test_approve_reads_stored_pictures_instead_of_calling_them_missing(self):
        data = self._website_copy()
        with self._on(self.website_root):
            try:
                wsa.visuals(data, {"action": "approve"})
            except ValueError as exc:
                self.assertNotIn("no existing local asset", str(exc).lower())
                self.assertNotIn("file is missing", str(exc).lower())
        for aid in required_aids(data["visual_plan"]):
            path = str(aid.get("asset_path") or "")
            if path:
                self.assertTrue(os.path.isfile(path), path)

    def test_before_the_fix_this_is_exactly_the_live_failure(self):
        # Proves the tests above are not vacuous: skipping the storage fetch
        # reproduces the production error message.
        from services.ebook_visual_pipeline import accept_photo_aid

        data = self._website_copy()
        vid = str(self._photo(data)["visual_id"])
        with self._on(self.website_root):
            with self.assertRaisesRegex(ValueError, "Photograph file is missing"):
                accept_photo_aid(data, vid)

    def test_a_photo_storage_cannot_supply_still_fails_honestly(self):
        data = self._website_copy()
        self.driver.objects.clear()
        vid = str(self._photo(data)["visual_id"])
        with self._on(self.website_root):
            with self.assertRaisesRegex(ValueError, "Photograph file is missing"):
                wsa.visuals(data, {"action": "accept-photo", "visual_id": vid})

    def test_no_paid_call_and_no_ledger_change(self):
        data = self._website_copy()
        ws = data.setdefault("ebook_workspace", {})
        ws["paid_call_ledger"] = {"budget_cap_usd": 7.0, "spent_usd": 4.1,
                                  "remaining_usd": 2.9, "paid_calls": 26}
        vid = str(self._photo(data)["visual_id"])
        with self._on(self.website_root):
            data, _ = wsa.visuals(data, {"action": "accept-photo", "visual_id": vid})
        led = data["ebook_workspace"]["paid_call_ledger"]
        self.assertEqual((led["spent_usd"], led["remaining_usd"], led["paid_calls"]), (4.1, 2.9, 26))
        self.assertFalse(data.get("visual_ai_spend_usd"))
