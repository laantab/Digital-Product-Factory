"""A refused cover must not be a dead end.

v1.9.3 made the cover gate able to fail. On a real bright photograph
(Pexels 34058722) it now refuses ``printed_moment`` and passes the other two.
A correct refusal is only half the job: the customer still has to reach a
finished book. This file pins what they see.

  * Some layouts pass  -> the refused one is simply not offered. The customer
    picks from the ones that work and the guided step stays "choose a cover".
  * No layout passes   -> the step becomes "choose another photo" and the
    message says so in words a customer can act on.
  * A refused layout can never be selected or approved, by any route.

No network, no paid call: the photograph fixtures are generated in-process.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ.setdefault("FACTORY_TEST_MODE", "1")

from PIL import Image, ImageDraw  # noqa: E402

from services.ebook_photo_cover import (  # noqa: E402
    GUIDED_STEP_CHOOSE_ANOTHER,
    GUIDED_STEP_CHOOSE_COVER,
    LAYOUT_IDS,
    NO_SAFE_COVER_MESSAGE,
    PhotoCoverError,
    attach_upload,
    photo_cover_public_fields,
    resolve_cover_guided_step,
    select_layout,
)

TITLE = "Container Gardening - A Beginner's Guide"
SUBTITLE = "Grow food in small spaces, on a balcony, a step or a windowsill"


def _photo_bytes(draw_on: Image.Image) -> bytes:
    import io

    buf = io.BytesIO()
    draw_on.save(buf, "JPEG", quality=92)
    return buf.getvalue()


def _hard_edged() -> Image.Image:
    """Bright above, dark below, with a razor edge across the middle.

    This is the shape that defeats a single ink: whichever colour the type
    takes, part of every line that crosses the edge is lost.
    """
    img = Image.new("RGB", (1200, 1600), (236, 232, 226))
    drawer = ImageDraw.Draw(img)
    for y in range(0, 1600, 36):
        drawer.line([(0, y), (1200, y)], fill=(224, 220, 214), width=2)
    drawer.rectangle((0, 520, 1200, 1080), fill=(16, 18, 24))
    return img


def _plain(rgb: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (1200, 1600), rgb)
    drawer = ImageDraw.Draw(img)
    for y in range(0, 1600, 40):
        drawer.line([(0, y), (1200, y)], fill=tuple(max(0, c - 6) for c in rgb), width=3)
    return img


def _built(photo: Image.Image, package_id: str) -> dict:
    data = {
        "title": TITLE,
        "subtitle": SUBTITLE,
        "author": "Lonnie Brown",
        "package_id": package_id,
    }
    return attach_upload(
        data,
        _photo_bytes(photo),
        filename="fixture.jpg",
        license_note="Generated test fixture.",
        project_id=None,
        owned=True,
    )


def _quality(data: dict) -> dict[str, bool]:
    variants = (data.get("cover_design") or {}).get("variants") or {}
    return {
        lid: bool(((variants.get(lid) or {}).get("quality") or {}).get("pass"))
        for lid in LAYOUT_IDS
    }


class WhenSomeLayoutsAreRefused(unittest.TestCase):
    def test_the_customer_is_offered_the_ones_that_work(self):
        data = _built(_hard_edged(), "refusal_mixed")
        quality = _quality(data)
        passing = [lid for lid, ok in quality.items() if ok]
        refused = [lid for lid, ok in quality.items() if not ok]
        if not refused:
            self.skipTest("this fixture no longer produces a refusal")
        self.assertTrue(passing, "every layout was refused on a fixture meant to split")

        public = photo_cover_public_fields(data, project_id=None)
        offered = [row["layout_id"] for row in public["variants"] if row.get("quality_pass")]
        self.assertEqual(sorted(offered), sorted(passing))
        for lid in refused:
            self.assertNotIn(lid, offered, "a refused cover was offered to the customer")
        self.assertEqual(public["passing_count"], len(passing))
        self.assertEqual(public["workflow_step"], GUIDED_STEP_CHOOSE_COVER)
        self.assertFalse(public["no_safe_cover"])
        self.assertIn("choose", public["user_status"].lower())

    def test_a_passing_layout_can_still_be_selected(self):
        data = _built(_hard_edged(), "refusal_select")
        passing = [lid for lid, ok in _quality(data).items() if ok]
        if not passing:
            self.skipTest("this fixture produced no passing layout")
        data = select_layout(data, passing[0], project_id=None)
        self.assertEqual(data["cover_design"]["selected_layout"], passing[0])
        self.assertTrue(data["cover_design"]["cover_digest"])

    def test_a_refused_layout_cannot_be_selected(self):
        data = _built(_hard_edged(), "refusal_reject")
        refused = [lid for lid, ok in _quality(data).items() if not ok]
        if not refused:
            self.skipTest("this fixture no longer produces a refusal")
        with self.assertRaises(PhotoCoverError) as caught:
            select_layout(data, refused[0], project_id=None)
        self.assertIn("choose another", str(caught.exception).lower())


class WhenEveryLayoutIsRefused(unittest.TestCase):
    """The resolver decides this, so it is pinned directly rather than by
    hunting for a photograph that defeats all three."""

    def test_the_step_becomes_choose_another_photo(self):
        step = resolve_cover_guided_step(
            has_valid_photo=True,
            passing_count=0,
            selected_layout="",
            selected_is_passing=False,
        )
        self.assertEqual(step, GUIDED_STEP_CHOOSE_ANOTHER)

    def test_the_message_tells_the_customer_what_to_do(self):
        self.assertIn("choose another photo", NO_SAFE_COVER_MESSAGE.lower())
        self.assertNotIn("contrast", NO_SAFE_COVER_MESSAGE.lower())
        self.assertNotIn("wcag", NO_SAFE_COVER_MESSAGE.lower())

    def test_one_passing_layout_is_enough_to_carry_on(self):
        step = resolve_cover_guided_step(
            has_valid_photo=True,
            passing_count=1,
            selected_layout="",
            selected_is_passing=False,
        )
        self.assertEqual(step, GUIDED_STEP_CHOOSE_COVER)

    def test_a_selection_that_stopped_passing_sends_the_customer_back(self):
        """A cover chosen before this release, refused on a rebuild, must not
        sit there looking approved."""
        step = resolve_cover_guided_step(
            has_valid_photo=True,
            passing_count=2,
            selected_layout="printed_moment",
            selected_is_passing=False,
        )
        self.assertEqual(step, GUIDED_STEP_CHOOSE_COVER)


class TheGoodPhotographPathIsUnchanged(unittest.TestCase):
    def test_a_plain_photograph_still_offers_every_layout(self):
        data = _built(_plain((30, 34, 32)), "refusal_dark_ok")
        self.assertEqual(sorted(lid for lid, ok in _quality(data).items() if ok), sorted(LAYOUT_IDS))
        public = photo_cover_public_fields(data, project_id=None)
        self.assertEqual(public["passing_count"], 3)
        self.assertEqual(public["workflow_step"], GUIDED_STEP_CHOOSE_COVER)


if __name__ == "__main__":
    unittest.main()
