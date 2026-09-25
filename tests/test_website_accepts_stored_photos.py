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
        self._store_a_real_photo(data)
        # The builder's temporary disk is gone when its task ends.
        shutil.rmtree(self.builder_root)
        data["_project_id"] = self.pid
        return data

    def _store_a_real_photo(self, data):
        """v1.9.7: give the book one genuine, text-free photograph in storage.

        The zero-cost fixture renders only local graphics, which are full of
        printed words. Relabelling one of those as a photograph (the old
        fixture) made the picture checker refuse it for its text, so the test
        measured the checker, not storage. Here a new text-free photograph is
        written on the builder and published exactly as the builder publishes
        a Pexels picture, so the test exercises what it names.
        """
        import hashlib
        import io
        import random
        from PIL import Image, ImageDraw, ImageFilter
        from services.ebook_visual_pipeline import _publish_visual
        from services.ebook_visual_pipeline import publishing_for_project as _scope

        aid = next(a for a in required_aids(data["visual_plan"]) if a.get("asset_path"))
        rnd = random.Random(7)
        w, h = 1600, 1067
        # Soft, smooth shapes only: sharp random noise reads as "text" to OCR.
        img = Image.new("RGB", (w, h), (118, 150, 96))
        d = ImageDraw.Draw(img)
        for _ in range(14):
            cx, cy, r = rnd.randint(0, w), rnd.randint(0, h), rnd.randint(120, 380)
            d.ellipse((cx - r, cy - r, cx + r, cy + r),
                      fill=(40 + rnd.randint(0, 60), 90 + rnd.randint(0, 80), 30 + rnd.randint(0, 40)))
        img = img.filter(ImageFilter.GaussianBlur(40))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        raw = buf.getvalue()
        path = os.path.join(os.path.dirname(str(aid["asset_path"])), "v_stored_real_photo.png")
        with open(path, "wb") as fh:
            fh.write(raw)
        aid.update({"type": "photo", "source": "pexels", "match_status": "needs_user_review",
                    "photographer": "Test Photographer", "photo_id": "1",
                    "attribution": "Photo by Test Photographer on Pexels",
                    "page_url": "https://www.pexels.com/photo/1/",
                    "pexels": {"photo_id": "1", "photographer": "Test Photographer"},
                    "asset_path": path, "sha256": hashlib.sha256(raw).hexdigest(),
                    "width": w, "height": h,
                    # The photograph's own description matches its brief, as a
                    # well-chosen Pexels picture's does.
                    "alt": " ".join(str(aid.get(k) or "") for k in ("title", "caption", "brief")).strip()})
        with self._on(self.builder_root), _scope(self.pid):
            _publish_visual(aid, path)

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


class AcceptSaysWhenAPictureCannotBeUsed(WebsiteAcceptsStoredPhotos):
    """v1.9.7: accepting a refused picture must not report success."""

    def test_refused_picture_is_not_reported_as_accepted(self):
        data = self._build_on_builder()
        data["_project_id"] = self.pid
        # A picture far too small to print, labelled as a photograph. Refused
        # on every machine -- unlike printed-text detection, this does not
        # depend on an OCR engine being installed (Windows PCs have none).
        from PIL import Image

        aid = next(a for a in required_aids(data["visual_plan"]) if a.get("asset_path"))
        tiny = os.path.join(os.path.dirname(str(aid["asset_path"])), "v_tiny_photo.png")
        Image.new("RGB", (160, 107), (90, 140, 70)).save(tiny, "PNG")
        aid["asset_path"] = tiny
        aid["width"], aid["height"] = 160, 107
        aid.update({"type": "photo", "source": "pexels", "match_status": "needs_user_review",
                    "photographer": "T", "photo_id": "2", "attribution": "Photo by T on Pexels",
                    "page_url": "https://www.pexels.com/photo/2/",
                    "pexels": {"photo_id": "2", "photographer": "T"}})
        with self._on(self.builder_root):
            data, msg = wsa.visuals(data, {"action": "accept-photo", "visual_id": aid["visual_id"]})
        after = next(a for a in required_aids(data["visual_plan"]) if a["visual_id"] == aid["visual_id"])
        self.assertFalse(after.get("user_accepted"))
        self.assertNotIn("accepted", msg.lower())
        self.assertIn("replace", msg.lower())

    # Inherited tests already run in the parent class.
    test_accept_photo_works_when_the_file_is_only_in_storage = None
    test_every_light_action_fetches_from_storage_first = None
    test_approve_reads_stored_pictures_instead_of_calling_them_missing = None
    test_before_the_fix_this_is_exactly_the_live_failure = None
    test_a_photo_storage_cannot_supply_still_fails_honestly = None
    test_no_paid_call_and_no_ledger_change = None
