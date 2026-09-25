"""Factory 1.9.7 -- a missing chapter photograph is never replaced by a drawn card.

A "stock photo" slot with no picture used to be drawn by the diagram renderer
as a card showing its own title, stamped status "resolved" and source
"local_render". That is a placeholder standing in for a missing photograph,
which a finished book must never contain. Zero cost: no search, no paid call.
"""
from __future__ import annotations

import io
import os
import shutil
import unittest
from pathlib import Path

os.environ["FACTORY_TEST_MODE"] = "1"

from PIL import Image  # noqa: E402

from services.ebook_visual_pipeline import materialize_visual_plan, visuals_dir  # noqa: E402

PKG = "v197-missing-photo-test"


def _plan(kind="stock photo", **extra):
    aid = {"visual_id": "v_soil_photo", "chapter": "Soil", "chapter_index": 1, "type": kind,
           "title": "Soil: what this looks like in practice", "caption": "Potting soil in a pot.",
           "required": True}
    aid.update(extra)
    return {"chapters": [{"chapter": "Soil", "chapter_index": 1, "aids": [aid]}]}


class MissingPhotoIsNeverDrawn(unittest.TestCase):
    def setUp(self):
        self.addCleanup(lambda: shutil.rmtree(visuals_dir(PKG).parent, ignore_errors=True))

    def test_missing_stock_photo_stays_missing(self):
        aid = materialize_visual_plan(_plan(), package_id=PKG)["chapters"][0]["aids"][0]
        self.assertEqual(aid.get("status"), "missing")
        self.assertNotEqual(aid.get("source"), "local_render")
        self.assertFalse(Path(visuals_dir(PKG) / "v_soil_photo.png").is_file(),
                         "a card was drawn in place of the missing photograph")

    def test_missing_photo_type_still_stays_missing(self):
        aid = materialize_visual_plan(_plan("photo"), package_id=PKG)["chapters"][0]["aids"][0]
        self.assertEqual(aid.get("status"), "missing")

    def test_a_stored_stock_photo_is_kept_not_redrawn(self):
        src = Path(visuals_dir(PKG).parent / "incoming.png")
        src.parent.mkdir(parents=True, exist_ok=True)
        buf = io.BytesIO(); Image.new("RGB", (1200, 800), (40, 120, 60)).save(buf, "PNG")
        src.write_bytes(buf.getvalue())
        aid = materialize_visual_plan(_plan(asset_path=str(src), source="pexels"),
                                      package_id=PKG)["chapters"][0]["aids"][0]
        self.assertEqual(aid.get("source"), "pexels")
        out = Path(visuals_dir(PKG) / "v_soil_photo.png")
        self.assertTrue(out.is_file())
        self.assertEqual(out.read_bytes(), src.read_bytes(), "the real photograph was redrawn")

    def test_diagrams_are_still_drawn(self):
        plan = {"chapters": [{"chapter": "Soil", "chapter_index": 1, "aids": [{
            "visual_id": "v_soil_check", "chapter": "Soil", "chapter_index": 1, "type": "checklist",
            "title": "Soil checklist", "caption": "Before you plant.", "items": ["Drainage", "Mix", "Water"]}]}]}
        aid = materialize_visual_plan(plan, package_id=PKG)["chapters"][0]["aids"][0]
        self.assertTrue(Path(str(aid.get("asset_path"))).is_file())


if __name__ == "__main__":
    unittest.main()
