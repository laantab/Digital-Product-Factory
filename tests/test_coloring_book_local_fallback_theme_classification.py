"""FACTORY STABILITY AUDIT (2026-09-09) — regression test for a real,
reproduced defect in the Coloring Book local vector fallback renderer.

Root cause: services.coloring_book.renderer._draw_line_art classified the
page's illustration template (superhero / fantasy / animal / vehicle /
mandala / generic) by scanning the ENTIRE line_art_prompt string, not just
the customer's actual topic. Every prompt this Factory builds carries the
same fixed negative-constraints boilerplate ("No superheroes... No Thunder
Volt... villains, guns, or crime scenes unless the user theme explicitly
asks for them"), and a plain substring check matched "hero" inside
"superheroes", plus "volt"/"thunder"/"villain" inside that same
boilerplate, on every single theme -- so the superhero branch fired first
regardless of what the customer asked for.

Reproduced live via the real customer path (Product Factory -> Coloring
Book -> "Quick test layout only" -> theme "Cute ocean animals for kids
ages 4-8"): every interior page rendered a generic stick-figure hero
standing in front of a city skyline, and the local-fallback cover also
showed a generic "HERO" placeholder -- nothing about ocean animals.

This path is used both by the zero-cost "Basic Test Fallback" quality
mode AND as the emergency fallback for any single page whose paid AI
image failed to generate -- so a real, paying customer's sellable book
could silently receive a wrong-theme page if one image call failed.

Fix: classify using topic_lower alone. A genuine superhero theme (e.g.
Thunder Volt) still classifies correctly because the customer's own theme
text says so; the boilerplate prompt noise no longer participates.
"""
from __future__ import annotations

import io
import unittest

from reportlab.pdfgen import canvas

import services.coloring_book.renderer as renderer


# The exact negative-constraints boilerplate this Factory embeds in every
# generated line_art_prompt, regardless of the customer's actual theme.
NEGATIVE_CONSTRAINTS_BOILERPLATE = (
    "NEGATIVE CONSTRAINTS (must obey):\n"
    "- No superheroes, bank robbers, bandits, villains, guns, or crime "
    "scenes unless the user theme explicitly asks for them\n"
    "- No Thunder Volt, Marvel, DC, or other copyrighted characters\n"
)


class ColoringBookLocalFallbackThemeClassificationTests(unittest.TestCase):
    def _classify(self, *, topic: str, prompt: str, age_group: str = "Children ages 8-12",
                  art_style: str = "Cartoon comic-book") -> str:
        """Return which template function _draw_line_art picked, without
        actually needing valid canvas geometry for every branch."""
        pdf = canvas.Canvas(io.BytesIO())
        picked: dict[str, bool] = {}

        originals = {}
        for name in ("_draw_superhero", "_draw_fantasy", "_draw_animal", "_draw_vehicle",
                     "_draw_mandala", "_draw_generic_scene"):
            originals[name] = getattr(renderer, name)
            setattr(renderer, name, (lambda label: lambda *a, **k: picked.setdefault(label, True))(name))
        try:
            renderer._draw_line_art(
                pdf, topic=topic, line_art_prompt=prompt,
                box_x=0, box_y=0, box_w=400, box_h=500,
                age_group=age_group, art_style=art_style,
            )
        finally:
            for name, fn in originals.items():
                setattr(renderer, name, fn)

        self.assertEqual(len(picked), 1, f"expected exactly one template, got {picked}")
        return next(iter(picked))

    def test_non_superhero_theme_is_not_derailed_by_prompt_boilerplate(self):
        # Regression: the raw bug -- ocean animals theme, with the always-
        # present negative-constraints boilerplate in the prompt, used to
        # render the superhero template on every page.
        picked = self._classify(
            topic="Cute ocean animals for kids ages 4-8 in the Rainforest",
            prompt=(
                "Create a professional Bold Easy Kawaii Coloring Page featuring "
                "Cute ocean animals for kids ages 4-8 in the Rainforest.\n"
                + NEGATIVE_CONSTRAINTS_BOILERPLATE
            ),
        )
        self.assertEqual(picked, "_draw_animal")

    def test_a_genuine_superhero_theme_still_classifies_as_superhero(self):
        # A real Thunder Volt-style request must still route correctly --
        # the fix must not blind the classifier to real superhero themes.
        picked = self._classify(
            topic="Thunder Volt is a Black superhero stopping a robbery in New York City",
            prompt="Create a coloring page.\n" + NEGATIVE_CONSTRAINTS_BOILERPLATE,
        )
        self.assertEqual(picked, "_draw_superhero")

    def test_various_non_superhero_themes_avoid_the_superhero_template(self):
        cases = [
            ("Dragons and wizards in an enchanted castle", "_draw_fantasy"),
            ("Farm animals and a big red barn", "_draw_animal"),
            ("Race cars and monster trucks", "_draw_vehicle"),
            ("Intricate mandala patterns for adults", "_draw_mandala"),
        ]
        for topic, expected in cases:
            with self.subTest(topic=topic):
                picked = self._classify(
                    topic=topic,
                    prompt=f"Create a coloring page featuring {topic}.\n" + NEGATIVE_CONSTRAINTS_BOILERPLATE,
                )
                self.assertEqual(picked, expected)


if __name__ == "__main__":
    unittest.main()
