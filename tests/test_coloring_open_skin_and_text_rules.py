"""Deterministic regression: open Thunder Volt skin + no text/symbols in interiors."""
from __future__ import annotations

import tempfile
import unittest

from PIL import Image, ImageDraw, ImageFont

from services.coloring_book.line_art_cleanup import (
    THUNDER_VOLT_OPEN_SKIN_RULE,
    cleanup_thunder_volt_interior,
    detect_prohibited_text_marks,
    measure_open_skin_score,
)
from services.coloring_book.prompt_engine import THUNDER_VOLT_OPEN_SKIN_INTERIOR_RULE


class TestOpenSkinAndTextRules(unittest.TestCase):
    def test_rule_constants_present(self):
        self.assertIn("unfilled white", THUNDER_VOLT_OPEN_SKIN_RULE.lower())
        self.assertIn("pure white open coloring", THUNDER_VOLT_OPEN_SKIN_INTERIOR_RULE.lower())

    def test_skin_stipple_cleared_preserves_outline(self):
        im = Image.new("RGB", (400, 600), "white")
        d = ImageDraw.Draw(im)
        # Face oval outline
        d.ellipse([120, 60, 280, 240], outline="black", width=3)
        # Eyes / nose / mouth
        d.ellipse([155, 120, 175, 140], outline="black", width=2)
        d.ellipse([225, 120, 245, 140], outline="black", width=2)
        d.line([200, 150, 200, 180], fill="black", width=2)
        d.arc([170, 180, 230, 210], 20, 160, fill="black", width=2)
        # Gray stipple fill inside face (must be removed)
        for y in range(90, 220, 3):
            for x in range(140, 260, 3):
                im.putpixel((x, y), (190, 190, 190))
        # Chest lightning outline (must remain)
        d.polygon([(200, 300), (230, 360), (210, 360), (240, 430), (170, 370), (195, 370)], outline="black")

        out, report = cleanup_thunder_volt_interior(im, page_number=1)
        self.assertTrue(report.skin_fill_removed)
        score = measure_open_skin_score(out)
        self.assertTrue(score["open_skin_ok"], score)
        # Outline / feature ink still present inside face band
        px = out.load()
        blacks = sum(
            1
            for y in range(60, 240)
            for x in range(120, 280)
            if px[x, y][0] < 40
        )
        self.assertGreater(blacks, 50)

    def test_dollar_sign_on_open_region_removed(self):
        import numpy as np

        from services.coloring_book.line_art_cleanup import (
            _get_templates,
            remove_dollar_and_text_marks,
        )

        # Pure-white field with an embedded `$` template glyph.
        arr = np.full((700, 500), 255, dtype=np.uint8)
        templ = next(t for t in _get_templates() if 40 <= t.shape[0] <= 90)
        th, tw = templ.shape
        y0, x0 = 300, 200
        roi = arr[y0 : y0 + th, x0 : x0 + tw]
        roi[templ > 0] = 0
        arr[y0 : y0 + th, x0 : x0 + tw] = roi

        cleaned, n = remove_dollar_and_text_marks(arr)
        self.assertGreaterEqual(n, 1)
        self.assertGreater(float(cleaned[y0 : y0 + th, x0 : x0 + tw].mean()), 240.0)
        # Full cleanup path should not re-introduce the mark.
        im = Image.fromarray(cleaned, mode="L").convert("RGB")
        out, report = cleanup_thunder_volt_interior(im, page_number=2)
        self.assertEqual(detect_prohibited_text_marks(out), [])
        self.assertTrue(report.text_symbols_removed or n >= 1)

    def test_bible_includes_open_skin_rule(self):
        from services.coloring_book.prompt_engine import build_character_bible

        theme = (
            "Thunder Volt is a Black superhero. "
            "He is stopping two adult men from robbing a bank and getting away in New York City."
        )
        bible = build_character_bible(theme)
        block = bible.as_prompt_block()
        self.assertIn("INTERIOR SKIN COLORING RULE", block)
        self.assertIn("unfilled white", block.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
