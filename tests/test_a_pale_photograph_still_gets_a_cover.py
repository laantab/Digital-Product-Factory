"""A pale photograph must not lose every cover.

The regression this file exists to catch
----------------------------------------
v1.9.3 gave dark type its own veil, so that shading a bright photograph moves
away from the ink instead of towards it. On an ALREADY pale photograph that
veil pushed the picture past the thresholds `inspect_variant` uses to decide
`blank_white_area` and `not_full_bleed` -- it stopped looking like a
photograph at all.

Measured on a flat textured fixture, before this file existed:

    luma 242   390aaf8: all three layouts pass   branch: all three pass
    luma 244   390aaf8: all three layouts pass   branch: ALL THREE REFUSED
    luma 250   390aaf8: all three layouts pass   branch: ALL THREE REFUSED

Every refused cover was `blank_white_area, not_full_bleed`. With no layout
passing, the customer is sent to "choose another photo" for a photograph that
worked perfectly the release before -- a fog, a snow scene, an overcast sky, a
white studio backdrop or a pale flat-lay. That is worse than the defect the
release set out to fix.

The render loop now asks `photograph_is_bleached()` before accepting an
attempt, so a veil that washes the picture out is rejected and the other
direction is tried.

Everything here is generated in-process: no network, no Pexels, no paid call.
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
    LAYOUT_IDS,
    MAX_WHITE_FRACTION,
    MIN_TEXT_CONTRAST,
    bleach_report,
    default_editor,
    photograph_is_bleached,
    render_layout_with_qa,
)

IDENT = {
    "title": "Container Gardening - A Beginner's Guide",
    "subtitle": "Grow food in small spaces, on a balcony, a step or a windowsill",
    "author": "Lonnie Brown",
    "series": "",
}

#: 242 is the luma at which inspect_variant starts calling a pixel white, so
#: the interesting range is just above it. 236 is the control.
PALE_LEVELS = (236, 243, 244, 248, 250, 254)


def _pale(level: int) -> Image.Image:
    img = Image.new("RGB", (1200, 1600), (level, level - 2, level - 6))
    drawer = ImageDraw.Draw(img)
    faint = (level - 6, level - 8, level - 12)
    for y in range(0, 1600, 40):
        drawer.line([(0, y), (1200, y)], fill=faint, width=3)
    return img


class APalePhotographStillGetsACover(unittest.TestCase):
    def test_every_layout_survives_a_pale_photograph(self):
        editor = default_editor()
        for level in PALE_LEVELS:
            photo = _pale(level)
            for layout_id in LAYOUT_IDS:
                with self.subTest(luma=level, layout=layout_id):
                    _img, qa = render_layout_with_qa(
                        photo.copy(), layout_id, IDENT, editor
                    )
                    self.assertTrue(
                        qa.get("pass"),
                        f"luma {level}: {layout_id} was refused with "
                        f"{qa.get('findings')}",
                    )
                    self.assertNotIn("blank_white_area", qa.get("findings") or [])
                    self.assertNotIn("not_full_bleed", qa.get("findings") or [])

    def test_and_the_type_on_it_is_still_readable(self):
        """Surviving by going back to unreadable white type would be no fix."""
        editor = default_editor()
        for level in PALE_LEVELS:
            photo = _pale(level)
            for layout_id in LAYOUT_IDS:
                with self.subTest(luma=level, layout=layout_id):
                    _img, qa = render_layout_with_qa(
                        photo.copy(), layout_id, IDENT, editor
                    )
                    contrast = qa.get("contrast") or {}
                    self.assertGreaterEqual(
                        contrast.get("typical", 0.0),
                        MIN_TEXT_CONTRAST,
                        f"luma {level}: {layout_id} passed at "
                        f"{contrast.get('typical', 0.0):.2f}:1",
                    )

    def test_the_rendered_cover_is_not_washed_out(self):
        editor = default_editor()
        for level in (244, 250, 254):
            img, _qa = render_layout_with_qa(
                _pale(level).copy(), "full_bleed_editorial", IDENT, editor
            )
            with self.subTest(luma=level):
                self.assertFalse(photograph_is_bleached(img))


class TheBleachTestMatchesTheGate(unittest.TestCase):
    """bleach_report must use the same thresholds inspect_variant does, or the
    render loop will accept an attempt the gate then rejects."""

    def test_a_white_page_is_bleached(self):
        self.assertTrue(photograph_is_bleached(Image.new("RGB", (1275, 1650), (255, 255, 255))))

    def test_a_photograph_is_not(self):
        self.assertFalse(photograph_is_bleached(_pale(236)))

    def test_the_fraction_is_reported_not_guessed(self):
        report = bleach_report(Image.new("RGB", (1275, 1650), (255, 255, 255)))
        self.assertAlmostEqual(float(report["white_fraction"]), 1.0, places=2)
        self.assertGreater(float(report["white_fraction"]), MAX_WHITE_FRACTION)
        self.assertTrue(report["corner_white"])

    def test_it_agrees_with_the_gates_own_counting(self):
        """The gate counts white pixels with a Python loop over the same
        thumbnail. This asserts the fast C-level mask gives the same answer."""
        for level in (200, 236, 243, 244, 250, 255):
            small = _pale(level).resize((318, 412), Image.Resampling.LANCZOS)
            pixels = small.load()
            by_hand = sum(
                1
                for y in range(small.height)
                for x in range(small.width)
                if pixels[x, y][0] > 242 and pixels[x, y][1] > 242 and pixels[x, y][2] > 238
            )
            by_mask = float(bleach_report(_pale(level))["white_fraction"]) * (
                small.width * small.height
            )
            with self.subTest(luma=level):
                self.assertAlmostEqual(by_mask, by_hand, delta=2)


if __name__ == "__main__":
    unittest.main()
