"""Factory 1.8.10: the rendered-book heading check follows the release rule.

THE DEFECT THIS CLOSES
----------------------
Container Gardening for Beginners, 2026-09-22: every stage through preview
was approved, then preflight failed with duplicate heading "5. Water
deeply". The check stopped at its first hit; the book also has a
"Hypothetical planning example" section in eight chapters, each with its own
example. The release validator already treats a heading that recurs once
per chapter over different content as structure, not a duplicate
(tests/test_recurring_section_headings.py). The rendered check now applies
the same rule. Everything that rule treats as a defect still fails here.
"""
from __future__ import annotations

import unittest

from services.ebook_customer_facing import inspect_rendered_ebook

_TOPICS = [
    "choosing a sunny balcony corner for tomatoes and peppers",
    "mixing compost into potting soil for leafy greens",
    "grouping herbs by how much water each one needs",
    "rotating pots weekly so stems grow straight",
    "feeding fruiting plants every two weeks in summer",
    "moving containers indoors before the first frost",
]


def _book(*chapters, split_pages=False):
    parts = []
    for i, (title, sections) in enumerate(chapters, start=1):
        body = "".join(f"<{tag}>{text}</{tag}><p>{para}</p>" for tag, text, para in sections)
        cls = "pdf-page chapter-page" if split_pages else "chapter-page"
        parts.append(f'<section class="{cls}"><h2 class="chapter-title">{title}</h2>{body}</section>')
    return "<html><body>" + "".join(parts) + "</body></html>"


def _dups(html):
    return [f["message"] for f in inspect_rendered_ebook(html=html)
            if f.get("code") == "duplicate_heading"]


class RecurringSectionsWithDistinctContentPass(unittest.TestCase):

    def test_container_gardening_shape_passes(self):
        chapters = []
        for i, topic in enumerate(_TOPICS, start=1):
            chapters.append((f"Chapter {i}", [
                ("h3", "Hypothetical planning example", f"An example about {topic}."),
                ("h4", "5. Water deeply", f"Afterwards, water deeply when {topic} is done."),
            ]))
        self.assertEqual(_dups(_book(*chapters)), [])

    def test_the_old_rule_would_have_failed_this_book(self):
        # Guard against a vacuous pass: the same book with copied bodies fails.
        chapters = [(f"Chapter {i}", [("h3", "Hypothetical planning example",
                                       "Do the thing. Repeat the thing. Check the thing.")])
                    for i in range(1, 5)]
        self.assertEqual(_dups(_book(*chapters)), ["hypothetical planning example"])


class WrappedHeadingsAreCompared(unittest.TestCase):
    """The real layout wraps each heading in a keep-together box."""

    def _wrapped(self, bodies):
        parts = []
        for i, body in enumerate(bodies, start=1):
            parts.append(
                f'<section class="chapter-page"><div class="heading-keep">'
                f'<h2 class="chapter-title">Chapter {i}</h2></div>'
                f'<div class="heading-keep"><h3>Hypothetical planning example</h3></div>'
                f'<div class="ebook-body"><p>{body}</p></div></section>')
        return "".join(parts)

    def test_wrapped_distinct_sections_pass(self):
        self.assertEqual(_dups(self._wrapped(_TOPICS[:4])), [])

    def test_wrapped_copied_sections_fail(self):
        copied = ["Do the thing. Repeat the thing. Check the thing carefully."] * 4
        self.assertEqual(_dups(self._wrapped(copied)), ["hypothetical planning example"])


class DefectsStillFail(unittest.TestCase):

    def test_repeated_chapter_title(self):
        html = _book(("Getting Started", []), ("Getting Started", []))
        self.assertEqual(_dups(html), ["getting started"])

    def test_same_heading_twice_in_one_chapter(self):
        html = _book(("Planting", [("h4", "5. Water deeply", "first"),
                                   ("h4", "5. Water deeply", "second, different words")]))
        self.assertEqual(_dups(html), ["5. water deeply"])

    def test_same_heading_twice_in_a_chapter_split_across_pdf_pages(self):
        html = ('<section class="pdf-page chapter-page"><h2 class="chapter-title">Planting</h2>'
                '<h4>5. Water deeply</h4><p>alpha</p></section>'
                '<section class="pdf-page chapter-page"><h4>5. Water deeply</h4><p>beta</p></section>')
        self.assertEqual(_dups(html), ["5. water deeply"])

    def test_known_filler_label_repeated_across_chapters(self):
        html = _book(("One", [("h3", "Chapter Takeaway", "alpha beta gamma")]),
                     ("Two", [("h3", "Chapter Takeaway", "delta epsilon zeta")]))
        self.assertEqual(_dups(html), ["chapter takeaway"])

    def test_near_copy_sections_across_chapters(self):
        body = "Check drainage holes, add potting mix, water until it runs out the bottom."
        html = _book(("One", [("h3", "Key Steps", body)]), ("Two", [("h3", "Key Steps", body)]))
        self.assertEqual(_dups(html), ["key steps"])

    def test_empty_repeated_sections_are_not_silently_accepted_as_different(self):
        # A section with no words at all has nothing to compare; two such
        # repeats are not proven distinct, but they are also not near-copies
        # of real text. Headings over their sub-steps are compared WITH the
        # sub-steps, so a section's own h4 steps count as its content.
        html = _book(
            ("One", [("h3", "Planting steps", ""), ("h4", "1. Fill the pot", "soil and compost mix")]),
            ("Two", [("h3", "Planting steps", ""), ("h4", "1. Fill the pot", "soil and compost mix")]),
        )
        self.assertEqual(_dups(html), ["planting steps"])


if __name__ == "__main__":
    unittest.main()
