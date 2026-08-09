"""Farm / generic themes must never inherit Thunder Volt or bank-robber content."""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

FARM_THEME = (
    "A friendly farmer standing on the porch waving, with a friendly dog by his side. "
    "Inside pages are individual farm animal scenes."
)


class TestFarmThemeIsolation(unittest.TestCase):
    def test_not_bank_rescue_or_superhero(self):
        from services.coloring_book.prompt_engine import (
            is_bank_rescue_theme,
            is_farm_theme,
            is_superhero_narrative,
        )

        self.assertTrue(is_farm_theme(FARM_THEME))
        self.assertFalse(is_bank_rescue_theme(FARM_THEME))
        self.assertFalse(is_superhero_narrative(FARM_THEME, "", "Cartoon comic-book"))

    def test_cover_is_farmer_porch_dog_not_thunder_volt(self):
        from services.coloring_book.prompt_engine import (
            build_character_bible,
            build_cover_image_prompt,
            derive_cover_copy,
            validate_cover_prompt_lock,
            THUNDER_VOLT_CHARACTER_LOCK,
            ROBBER_ONE_LOCK,
        )

        bible = build_character_bible(FARM_THEME)
        copy = derive_cover_copy(FARM_THEME, product_title="Farm Friends")
        prompt = build_cover_image_prompt(bible=bible, cover=copy)
        low = prompt.lower()

        self.assertFalse(bible.is_bank_rescue)
        self.assertEqual(validate_cover_prompt_lock(prompt, FARM_THEME), [])
        self.assertIn("farmer", low)
        self.assertIn("porch", low)
        self.assertIn("dog", low)
        self.assertNotIn(THUNDER_VOLT_CHARACTER_LOCK, prompt)
        self.assertNotIn(ROBBER_ONE_LOCK, prompt)
        self.assertNotIn("stopping exactly two bank robbers", low)
        self.assertNotIn("yellow cape", low)

    def test_interiors_are_farm_animals_not_bandits(self):
        from services.coloring_book.prompt_engine import (
            build_local_story_pages,
            validate_locked_prompts,
        )

        pages, cover, bible, _ = build_local_story_pages(
            FARM_THEME,
            12,
            art_style="Cartoon comic-book",
            main_character="Farmer",
        )
        self.assertEqual(len(pages), 12)
        self.assertFalse(bible.is_bank_rescue)
        self.assertEqual(validate_locked_prompts(pages, FARM_THEME), [])

        topics = " ".join(p["topic"].lower() for p in pages)
        self.assertTrue(
            any(a in topics for a in ("cow", "pig", "chicken", "horse", "sheep", "duck")),
            topics,
        )
        from services.coloring_book.prompt_engine import (
            THUNDER_VOLT_CHARACTER_LOCK,
            ROBBER_ONE_LOCK,
        )

        for p in pages:
            prompt = p["line_art_prompt"]
            low = prompt.lower()
            self.assertNotIn(THUNDER_VOLT_CHARACTER_LOCK, prompt)
            self.assertNotIn(ROBBER_ONE_LOCK, prompt)
            self.assertFalse(p.get("includes_robbers"))
            # Interiors must be solo animal scenes — not the cover cast.
            self.assertIn("do not", low)
            self.assertTrue(
                "no farmer" in low or "do not draw the farmer" in low or "do not include the farmer" in low,
                prompt[:240],
            )
            self.assertIn("individual farm animal", low)

        self.assertNotIn(THUNDER_VOLT_CHARACTER_LOCK, cover)
        self.assertNotIn("stopping exactly two bank robbers", cover.lower())
        self.assertIn("farmer", cover.lower())
        self.assertIn("dog", cover.lower())

    def test_builder_local_pages_farm_path(self):
        from services.coloring_book.builder import _local_page_planner

        pages, cover = _local_page_planner(
            theme=FARM_THEME,
            page_count=8,
            age_group="Kids",
            art_style="Cartoon comic-book",
            include_captions=False,
            main_character="",
            setting="farm",
        )
        self.assertEqual(len(pages), 8)
        blob = cover + " ".join(p["line_art_prompt"] for p in pages)
        self.assertIn("farmer", blob.lower())
        self.assertNotIn("THUNDER VOLT CHARACTER LOCK", blob)
        self.assertNotIn("ROBBER ONE LOCK", blob)


class TestComicArtStyleDoesNotForceSuperhero(unittest.TestCase):
    def test_ocean_theme_with_comic_style(self):
        from services.coloring_book.prompt_engine import (
            is_superhero_narrative,
            build_cover_image_prompt,
            build_character_bible,
            derive_cover_copy,
        )

        theme = "Cute ocean animals for kids ages 4-8"
        self.assertFalse(is_superhero_narrative(theme, "", "Cartoon comic-book"))
        bible = build_character_bible(theme)
        prompt = build_cover_image_prompt(
            bible=bible, cover=derive_cover_copy(theme, product_title="Ocean Friends")
        )
        from services.coloring_book.prompt_engine import THUNDER_VOLT_CHARACTER_LOCK, ROBBER_ONE_LOCK

        self.assertNotIn(THUNDER_VOLT_CHARACTER_LOCK, prompt)
        self.assertNotIn(ROBBER_ONE_LOCK, prompt)
        self.assertNotIn("stopping exactly two bank robbers", prompt.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
