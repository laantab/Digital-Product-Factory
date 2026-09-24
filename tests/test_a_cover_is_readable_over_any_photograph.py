"""COVER READABILITY -- the type must be readable over the customer's photograph.

What was wrong (measured 2026-09-23 on v1.9.1, over two real Pexels photographs)
-------------------------------------------------------------------------------
Over a dark photograph all three cover layouts read well. Over a bright one:

    full_bleed_editorial   subtitle  2.56:1
    printed_moment         title     3.61:1 and 4.14:1, subtitle 3.78:1
    split_studio           fine, about 12:1
    the author line        about 1.4:1 -- on every layout, on BOTH photographs

WCAG AA asks 4.5:1. The cover quality gate reported PASS on all six renders.

Two separate defects sat behind that.

1. The ink was chosen by one number. ``_contrast_fills`` switched to dark ink
   when the region's luma reached 150 and used white below it. The bright
   kitchen measured just under 150 in full_bleed_editorial's text box and took
   white type; the same photograph measured just over 150 in split_studio's
   box and took dark type. One photograph, two layouts, opposite outcomes from
   a coin flip. The author line inherited the body's ink even when it sat on a
   completely different part of the picture.

2. The gate could not fail. ``inspect_variant`` decided ``weak_contrast`` by
   counting pixels in the title band of the FINISHED cover: for light type it
   wanted at least 16 pixels brighter than luma 190 and at least 18 darker
   than 90. The white glyphs supplied the bright ones and the near-black drop
   shadow drawn behind every line supplied the dark ones. The check was
   reading the text against itself, so no photograph could ever fail it.

What is guaranteed here
-----------------------
The weakest line of type on a cover that PASSES measures at least
``MIN_TEXT_CONTRAST`` against the photograph underneath it, measured before
the type is painted, and the gate genuinely fails a cover that cannot be read.
A cover is allowed to fail -- what is not allowed is an unreadable cover
reported as fine.

Every fixture here is generated in-process. No Pexels call, no network, no
paid call.
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
    COVER_H,
    COVER_W,
    DARK_INK,
    LAYOUT_IDS,
    LIGHT_INK,
    MIN_TEXT_CONTRAST,
    MIN_WORST_PATCH_CONTRAST,
    default_editor,
    ink_contrast,
    inspect_variant,
    measure_plan_contrast,
    render_layout_with_qa,
)

IDENT = {
    "title": "Container Gardening - A Beginner's Guide",
    "subtitle": "Grow food in small spaces, on a balcony, a step or a windowsill",
    "author": "Lonnie Brown",
    "series": "",
}


def _textured(rgb: tuple[int, int, int]) -> Image.Image:
    """A flat tone with enough texture to be a photograph rather than a blank.

    A truly flat field trips the separate blank_white_area finding, which is
    not what any test here is about.
    """
    img = Image.new("RGB", (1200, 1600), rgb)
    draw = ImageDraw.Draw(img)
    darker = tuple(max(0, c - 6) for c in rgb)
    for y in range(0, 1600, 40):
        draw.line([(0, y), (1200, y)], fill=darker, width=3)
    return img


def _bright_over_dark() -> Image.Image:
    """Bright where a title sits, dark where a by-line falls."""
    img = _textured((232, 228, 220))
    ImageDraw.Draw(img).rectangle((0, 1000, 1200, 1600), fill=(18, 20, 26))
    return img


class EveryLayoutIsReadableOverAnyPhotograph(unittest.TestCase):
    """The end-to-end contract, through the real render path."""

    def _assert_readable(self, photo: Image.Image, label: str) -> None:
        editor = default_editor()
        passed_any = False
        for layout_id in LAYOUT_IDS:
            with self.subTest(photo=label, layout=layout_id):
                _img, qa = render_layout_with_qa(photo.copy(), layout_id, IDENT, editor)
                contrast = qa.get("contrast") or {}
                self.assertTrue(
                    contrast.get("roles"),
                    "the cover was never measured against its photograph",
                )
                if not qa.get("pass"):
                    # Allowed -- but then it must be because it really is
                    # unreadable, not for some unrelated reason.
                    self.assertIn("weak_contrast", qa.get("findings") or [])
                    continue
                passed_any = True
                weakest = contrast["weakest_role"]
                self.assertGreaterEqual(
                    contrast["typical"],
                    MIN_TEXT_CONTRAST,
                    f"{label}/{layout_id}: the {weakest} passed the gate at "
                    f"{contrast['typical']:.2f}:1 against the photograph",
                )
                self.assertGreaterEqual(contrast["worst"], MIN_WORST_PATCH_CONTRAST)
        self.assertTrue(passed_any, f"{label}: no layout produced a usable cover")

    def test_a_bright_photograph(self):
        """The case that failed for real: white type on a pale picture."""
        self._assert_readable(_textured((208, 200, 188)), "bright beige")

    def test_a_very_bright_photograph(self):
        self._assert_readable(_textured((244, 240, 232)), "near white")

    def test_a_mid_tone_photograph(self):
        """The hardest tone: it fights white type and dark type equally."""
        self._assert_readable(_textured((140, 138, 132)), "mid grey")

    def test_a_dark_photograph(self):
        """This one already worked. It must keep working."""
        self._assert_readable(_textured((28, 32, 30)), "dark")

    def test_the_author_line_gets_its_own_reading(self):
        """The by-line sits somewhere else on the picture, so it reads the
        pixels it will actually sit on."""
        photo = _bright_over_dark()
        editor = default_editor()
        checked = 0
        for layout_id in LAYOUT_IDS:
            _img, qa = render_layout_with_qa(photo.copy(), layout_id, IDENT, editor)
            if not qa.get("pass"):
                continue
            author = ((qa.get("contrast") or {}).get("roles") or {}).get("author")
            if not author:
                continue
            checked += 1
            self.assertGreaterEqual(
                author["typical"],
                MIN_TEXT_CONTRAST,
                f"{layout_id}: the author line passed at {author['typical']:.2f}:1",
            )
        self.assertTrue(checked, "no layout produced a cover with an author line")


class TheGateCanActuallyFail(unittest.TestCase):
    """A gate that cannot fail proves nothing."""

    def test_an_unreadable_plan_is_refused(self):
        white_page = Image.new("RGB", (COVER_W, COVER_H), (250, 249, 246))
        plan = {
            "pass": True,
            "findings": [],
            "sizes": {"title": 96, "author": 40},
            "blocks": [
                {
                    "role": "title",
                    "lines": ["A Title Nobody Can Read"],
                    "font": None,
                    "size": 96,
                    "x": 100, "y": 200, "w": 900, "h": 120,
                    "gap": 0,
                    "box": (100, 200, 1000, 320),
                    "fill": (255, 255, 255),
                },
                {
                    "role": "author",
                    "lines": ["Lonnie Brown"],
                    "font": None,
                    "size": 40,
                    "x": 100, "y": 1500, "w": 300, "h": 46,
                    "gap": 0,
                    "box": (100, 1500, 400, 1546),
                    "fill": (255, 255, 255),
                },
            ],
        }
        plan["contrast"] = measure_plan_contrast(white_page, plan)
        self.assertLess(plan["contrast"]["typical"], MIN_TEXT_CONTRAST)
        qa = inspect_variant(white_page, "full_bleed_editorial", IDENT, plan=plan)
        self.assertIn(
            "weak_contrast",
            qa.get("findings") or [],
            "white type on a white page was reported as fine",
        )
        self.assertFalse(qa.get("pass"))

    def test_a_plan_that_was_never_measured_is_refused(self):
        """A missing measurement must not read as a pass. Skipping the check
        is exactly how six unreadable covers got through."""
        page = Image.new("RGB", (COVER_W, COVER_H), (120, 120, 120))
        plan = {
            "pass": True,
            "findings": [],
            "sizes": {"title": 96},
            "blocks": [
                {
                    "role": "title", "lines": ["Unmeasured"], "font": None, "size": 96,
                    "x": 100, "y": 200, "w": 900, "h": 120, "gap": 0,
                    "box": (100, 200, 1000, 320), "fill": (255, 255, 255),
                }
            ],
        }
        qa = inspect_variant(page, "full_bleed_editorial", IDENT, plan=plan)
        self.assertIn("weak_contrast", qa.get("findings") or [])


class TheMeasurementIsTheRealThing(unittest.TestCase):
    def test_contrast_matches_the_wcag_formula(self):
        white_on_white = ink_contrast((255, 255, 255), [1.0] * 40)
        self.assertAlmostEqual(white_on_white["typical"], 1.0, places=2)
        black_on_white = ink_contrast((0, 0, 0), [1.0] * 40)
        self.assertAlmostEqual(black_on_white["typical"], 21.0, places=1)

    def test_the_worst_patch_is_not_the_average(self):
        """Half black, half white: the average flatters, the worst patch tells
        the truth about the half of a title that vanishes."""
        split = sorted([0.0] * 50 + [1.0] * 50)
        light = ink_contrast((255, 255, 255), split)
        self.assertGreater(light["typical"], light["worst"])
        self.assertAlmostEqual(light["worst"], 1.0, places=2)

    def test_the_two_ink_palettes_are_opposites(self):
        """Guards against an edit that quietly makes both palettes light."""
        dark = ink_contrast(DARK_INK["title"], [1.0] * 40)["typical"]
        light = ink_contrast(LIGHT_INK["title"], [1.0] * 40)["typical"]
        self.assertGreater(dark, 15.0)
        self.assertLess(light, 1.5)


if __name__ == "__main__":
    unittest.main()
