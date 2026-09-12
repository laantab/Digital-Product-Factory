"""COLORING BOOK INTERIOR NO-TEXT CONTRACT REPAIR (2026-09-12).

Regression test for a real, reproduced defect: a live customer path
(Coloring Book, Single Sheet, "Include captions?" = No, theme "Sea
Creatures in the Reef") failed QA -- even after the QA agent's one
automatic correction attempt -- with:

    Coloring Book QA failed after auto-correction: PDF still violates
    contract. Violations: header_detected: page has text at top;
    text_when_captions_no: found text='Sea Creatures in the Reef';
    title_on_page: title phrase='sea creatures'

Root cause, confirmed by calling the real renderer directly and reading
back the actual PDF text: ``services.coloring_book.renderer._draw_generic_
scene`` printed the page's topic as a visible "Topic label" via
``pdf.drawCentredString(...)``, completely unconditionally -- no check of
``include_captions``, ``single_sheet``, or any instruction-contract field
at all. ``_draw_generic_scene`` is the one illustration branch (of
superhero / fantasy / animal / vehicle / mandala / generic) that
``_draw_line_art`` falls through to whenever a theme matches none of the
specific keyword sets -- "Sea Creatures in the Reef" matches none of them
(no "fish", "ocean", "sea turtle", "animal", etc. as an exact substring).
Every sibling illustration branch already drew zero text; only this one
did not. This is not new -- the offending line has existed, unchanged,
since the very first Git baseline (444e88f, 2026-08-09); it was never
previously fixed, so it cannot have regressed.

Auto-correction could not fix this: it correctly forces
``include_captions``/``captions`` off and rebuilds through the real
pipeline, but that pipeline calls the exact same buggy drawing function
either way, so the defect reproduced identically on the corrected retry.

Fix: delete the unconditional topic-label draw from ``_draw_generic_
scene``, matching every other illustration branch and the documented
contract already stated in ``_draw_coloring_page``'s own docstring ("no
product title / topic / long prompt headers").

No external/paid API call is made by any test in this file.
"""
from __future__ import annotations

import base64
import io
import unittest

import fitz
from reportlab.pdfgen import canvas

import services.coloring_book.renderer as renderer

# Representative topics for each illustration branch _draw_line_art
# classifies to, so this bug class ("only one branch draws text") cannot
# come back hidden inside a different branch.
_BRANCH_TOPICS = {
    "superhero": "A brave superhero flying over the city",
    # NOTE: deliberately avoids "dragon" and "castle"/"knight" -- both of
    # _draw_fantasy's own sub-branches have separate, pre-existing crash
    # bugs unrelated to this file's no-text contract (pdf.curve() is not a
    # reportlab Canvas method; pdf.arc() does not accept stroke=/fill=).
    # Flagged separately; not fixed here to keep this change to its
    # approved scope. "unicorn" hits neither sub-branch.
    "fantasy": "A gentle unicorn in an enchanted meadow",
    "animal": "A curious fox exploring the forest",
    "vehicle": "A fast race car speeding down the track",
    "mandala": "An intricate geometric mandala pattern",
    # Matches none of _draw_line_art's keyword sets -- falls to the
    # generic branch. This is the exact customer theme that failed live.
    "generic": "Sea Creatures in the Reef",
}


def _render_topic_to_text(topic: str) -> str:
    """Render one interior page's illustration and return its extracted
    PDF text -- exactly what the QA agent inspects."""
    out = io.BytesIO()
    pdf = canvas.Canvas(out, pagesize=(612, 792))
    renderer._draw_line_art(
        pdf,
        topic=topic,
        line_art_prompt="A detailed line-art coloring page.",
        box_x=50,
        box_y=50,
        box_w=400,
        box_h=500,
        age_group="Children ages 8-12",
        art_style="Cartoon comic-book",
    )
    pdf.showPage()
    pdf.save()
    doc = fitz.open(stream=out.getvalue(), filetype="pdf")
    text = doc[0].get_text()
    doc.close()
    return text


class GenericSceneDrawsNoTextTests(unittest.TestCase):
    """The exact reported regression: a generic-branch theme must render
    with zero visible text, matching every other illustration branch."""

    def test_the_exact_customer_theme_renders_no_text(self):
        text = _render_topic_to_text("Sea Creatures in the Reef")
        self.assertEqual(
            text.strip(), "",
            "The generic-scene fallback must never print the topic as visible "
            "text -- this is exactly the live regression (QA failed after "
            "auto-correction with text_when_captions_no / title_on_page).",
        )

    def test_every_illustration_branch_renders_no_text(self):
        for branch, topic in _BRANCH_TOPICS.items():
            with self.subTest(branch=branch, topic=topic):
                text = _render_topic_to_text(topic)
                self.assertEqual(
                    text.strip(), "",
                    f"{branch} branch (topic={topic!r}) drew visible text; only "
                    f"the generic branch was ever known to do this, but this "
                    f"check exists so the bug class cannot reappear in a "
                    f"different branch unnoticed.",
                )


class EndToEndSingleSheetCaptionsOffTests(unittest.TestCase):
    """Drive the real customer path -- product.py's actual generation
    function -- for the exact failing product, zero cost."""

    def test_generic_theme_single_sheet_no_captions_passes_qa_with_no_text(self):
        from services.product import _generate_coloring_book_pdf

        fields = {
            "coloring_title": "Sea Creatures in the Reef",
            "theme": "Sea Creatures in the Reef",
            "output_format": "Single Sheet",
            "quality_mode": "Basic Test Fallback",
            "art_style": "Cartoon comic-book",
            "age_group": "Children ages 8-12",
            "pages": "1",
            "include_captions": "No",
        }
        result = _generate_coloring_book_pdf(fields)

        self.assertTrue(result.get("qa_passed"), result.get("errors"))
        self.assertFalse(
            result.get("qa_corrected"),
            "This theme must pass QA on the first attempt -- no auto-correction "
            "should be needed for a clean generic-branch render.",
        )
        pdf_bytes = base64.b64decode(result["pdf_bytes"])
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        self.assertEqual(doc.page_count, 1)
        page_text = doc[0].get_text().strip()
        doc.close()
        self.assertEqual(
            page_text, "",
            f"Single Sheet, captions=No must render with zero visible text; "
            f"found: {page_text!r}",
        )


if __name__ == "__main__":
    unittest.main()
