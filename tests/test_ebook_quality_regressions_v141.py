"""Generic protection for the defect classes found in the v1.4.1 quality review.

Every test here is written against behaviour, not against one project, one topic
or one book. None of them mention project 351. Each maps to a defect that
actually shipped in a customer product.

Run: python -m pytest tests/test_ebook_quality_regressions_v141.py
"""
from __future__ import annotations

import re
import unittest


# --------------------------------------------------------------------------
# 1. Topic-contaminated disclaimers
# --------------------------------------------------------------------------
class DisclaimerMatchesTopicTests(unittest.TestCase):
    """A mindfulness book shipped a disclaimer about business registration,
    insurance, margins and printer specifications, because the disclaimer was a
    hardcoded constant applied to every book."""

    def test_health_topic_gets_health_disclaimer_not_business(self):
        from services.ebook_manuscript_engine import build_topic_disclaimer

        text = build_topic_disclaimer("5-Minute Mindfulness for Busy Beginners", "busy adults")
        self.assertIn("mental-health", text.lower())
        for wrong in ("business registration", "insurance selection", "printer", "margin", "tax"):
            self.assertNotIn(wrong, text.lower(), f"health book disclaimer mentions {wrong!r}")

    def test_business_topic_gets_business_disclaimer_not_medical(self):
        from services.ebook_manuscript_engine import build_topic_disclaimer

        text = build_topic_disclaimer("Start a Photography Business", "pricing and client contracts")
        self.assertIn("tax", text.lower())
        self.assertNotIn("dietitian", text.lower())
        self.assertNotIn("crisis line", text.lower())

    def test_neutral_topic_gets_no_specialist_clauses(self):
        from services.ebook_manuscript_engine import build_topic_disclaimer

        text = build_topic_disclaimer("How to Choose a Houseplant", "beginners")
        for clause in ("tax", "dietitian", "printer", "crisis line", "insurance"):
            self.assertNotIn(clause, text.lower())

    def test_disclaimer_is_never_the_old_hardcoded_constant(self):
        from services.ebook_manuscript_engine import build_topic_disclaimer

        for topic in ("Mindfulness", "Meal Prep", "Woodworking", "Budgeting"):
            text = build_topic_disclaimer(topic)
            self.assertNotIn(
                "Printer specifications must be verified", text,
                "the removed hardcoded business/printing disclaimer is back",
            )


# --------------------------------------------------------------------------
# 2. Contents page: duplicate numbering, page numbers, one line per chapter
# --------------------------------------------------------------------------
class ContentsPageTests(unittest.TestCase):
    """The contents page rendered as an <ol> whose items also carried their own
    number, so every line read "1. 1 Chapter". Switching to <ul> only traded the
    stacked number for a bullet, because xhtml2pdf ignores list-style:none."""

    def _toc_html(self) -> str:
        from services.ebook_book_layout import render_designed_ebook_html
        from services.ebook_design_spec import build_ebook_design

        md = (
            "# Test Book\n\n*A subtitle*\n\n"
            "## First Chapter\n\nBody text for the first chapter.\n\n"
            "## Second Chapter\n\nBody text for the second chapter.\n\n"
            "## Third Chapter\n\nBody text for the third chapter.\n"
        )
        design = build_ebook_design(theme_id="studio_clean", manuscript_digest="d" * 64)
        return render_designed_ebook_html(
            title="Test Book", subtitle="A subtitle", author="A Author",
            manuscript_md=md, design=design,
            toc_page_numbers={"First Chapter": 3, "Second Chapter": 5, "Third Chapter": 7},
        )

    def test_contents_is_not_a_list_element(self):
        html = self._toc_html()
        block = html[html.index('class="toc-list"'):]
        block = block[: block.index("</section>")]
        self.assertNotIn("<li", block, "a list element re-numbers or bullets every contents row")
        self.assertNotIn("<ol", block)
        self.assertNotIn("<ul", block)

    def test_each_chapter_appears_exactly_once_with_one_number(self):
        html = self._toc_html()
        block = html[html.index('class="toc-list"'):]
        block = block[: block.index("</section>")]
        for title in ("First Chapter", "Second Chapter", "Third Chapter"):
            self.assertEqual(block.count(title), 1, f"{title} listed more than once")
        nums = re.findall(r'class="toc-num">(\d+)</span>', block)
        self.assertEqual(nums, ["1", "2", "3"])

    def test_contents_carries_the_supplied_page_numbers(self):
        html = self._toc_html()
        for page in ("3", "5", "7"):
            self.assertIn(f'class="toc-page-num">{page}</span>', html)


# --------------------------------------------------------------------------
# 3. Contents page numbers must match the printed page numbers
# --------------------------------------------------------------------------
class ContentsMatchesPrintedPagesTests(unittest.TestCase):
    """find_designed_chapter_pages counts the merged document, which includes the
    prepended cover; the running footer counts only the interior. Uncorrected,
    the contents page was ahead of every printed page number by the cover
    length, so "page 4" landed the reader on the wrong chapter."""

    def test_cover_offset_is_applied_to_contents_numbers(self):
        import inspect

        from services import ebook_design_export

        src = inspect.getsource(ebook_design_export.render_designed_bundle)
        self.assertIn("cover_offset", src, "contents numbers are not corrected for the cover")
        self.assertRegex(
            src, r"int\(page\)\s*-\s*cover_offset",
            "the cover page count is not subtracted from the contents numbers",
        )

    def test_offset_lookup_does_not_depend_on_a_shadowed_import(self):
        """The function does its own 'import io' further down, which makes the
        name local for the whole body. Using bare `io` above that point raises
        UnboundLocalError and silently zeroed the offset."""
        import inspect

        from services import ebook_design_export

        src = inspect.getsource(ebook_design_export.render_designed_bundle)
        head = src[: src.index("cover_offset = len(") + 40] if "cover_offset = len(" in src else src
        self.assertNotIn("io.BytesIO(cover_pdf)", head, "uses the function-shadowed `io` name")
        self.assertIn("_io.BytesIO(cover_pdf)", src)


# --------------------------------------------------------------------------
# 4. Running footer / page numbers exist at all
# --------------------------------------------------------------------------
class RunningFooterTests(unittest.TestCase):
    """The design spec declared footer_mode "page_number" and header_mode
    "running_title" while the renderer emitted neither, so books shipped with no
    page numbers."""

    def test_theme_css_declares_a_footer_frame(self):
        from services.ebook_design_system import theme_css

        css = theme_css("studio_clean")
        self.assertIn("@frame footer_frame", css)
        self.assertIn("-pdf-frame-content: page-footer", css)

    def test_no_css_comment_inside_the_page_rule(self):
        """xhtml2pdf's at-rule parser drops the whole @page rule, frame included,
        if it meets a comment inside it."""
        from services.ebook_design_system import theme_css

        css = theme_css("studio_clean")
        start = css.index("@page {")
        end = css.index("}", css.index("@frame footer_frame"))
        self.assertNotIn("/*", css[start:end], "a comment inside @page silently kills the footer")

    def test_rendered_book_emits_footer_content_with_a_page_number(self):
        from services.ebook_book_layout import render_designed_ebook_html
        from services.ebook_design_spec import build_ebook_design

        design = build_ebook_design(theme_id="studio_clean", manuscript_digest="e" * 64)
        html = render_designed_ebook_html(
            title="Test Book", subtitle="Sub", author="A Author",
            manuscript_md="# Test Book\n\n## Only Chapter\n\nBody.\n", design=design,
        )
        self.assertIn('id="page-footer"', html)
        self.assertIn("<pdf:pagenumber", html)

    def test_footer_separates_title_from_number(self):
        """Without a separator the footer printed as "Book Title12"."""
        from services.ebook_book_layout import render_designed_ebook_html
        from services.ebook_design_spec import build_ebook_design

        design = build_ebook_design(theme_id="studio_clean", manuscript_digest="f" * 64)
        html = render_designed_ebook_html(
            title="Test Book", subtitle="Sub", author="A Author",
            manuscript_md="# Test Book\n\n## Only Chapter\n\nBody.\n", design=design,
        )
        footer = html[html.index('id="page-footer"'):]
        footer = footer[: footer.index("</div>")]
        self.assertIn("foot-sep", footer, "nothing separates the running title from the page number")


# --------------------------------------------------------------------------
# 5. Visual cards must not carry truncated text
# --------------------------------------------------------------------------
class VisualTextIsCompleteTests(unittest.TestCase):
    """Key-point cards accepted sentences up to 150 chars while the label
    cleaner truncated at 78, so cards shipped ending in an ellipsis."""

    def test_key_point_items_are_never_truncated(self):
        from services.ebook_visual_pipeline import _key_point_items

        body = (
            "Mindfulness is not about clearing the mind of every thought that arrives, "
            "because a mind that produces thoughts is a mind that is working exactly as "
            "it should be at all times. "
            "Attention is a skill you practise rather than a mood you achieve. "
            "The return is the whole exercise and it means noticing where you went. "
            "Discomfort is information rather than a verdict on your ability. "
            "Consistency helps more than the length of any single session does."
        )
        for item in _key_point_items(body, chapter_title="Mindfulness Made Simple"):
            self.assertNotIn("…", item, f"truncated fragment on a card: {item!r}")
            self.assertFalse(item.endswith(("...", ",", ";")), f"clipped item: {item!r}")

    def test_label_bound_cannot_exceed_the_cleaner_limit(self):
        import inspect

        from services import ebook_visual_pipeline as vp

        src = inspect.getsource(vp._key_point_items)
        self.assertIn("_LABEL_LIMIT", src, "the length bound is not tied to the truncation limit")
        self.assertNotIn("<= 150", src, "the bound is wider than the cleaner, so cards will clip")

    def test_clean_sentence_still_truncates_when_asked(self):
        """The guard above must not be achieved by disabling truncation itself."""
        from services.ebook_visual_pipeline import _clean_sentence

        long = "word " * 60
        self.assertTrue(_clean_sentence(long).endswith("…"))


# --------------------------------------------------------------------------
# 6. Visuals must not duplicate a table the chapter already prints
# --------------------------------------------------------------------------
class VisualDoesNotDuplicateChapterTableTests(unittest.TestCase):
    """The interior typesets markdown tables itself, so drawing the same table as
    a PNG put it on the page twice — once as small unselectable image text and
    again as the real table directly below."""

    CHAPTER_WITH_TABLE = (
        "Intro paragraph for the chapter that sets up the comparison below.\n\n"
        "| The belief | What is actually true |\n"
        "|---|---|\n"
        "| I must clear my mind. | A busy mind is normal. |\n"
        "| I need silence. | Noise is workable. |\n"
        "| I need twenty minutes. | Short and frequent wins. |\n\n"
        "Closing paragraph. You can practise standing, walking or sitting today.\n"
    )

    def test_chapter_that_prints_a_table_does_not_also_get_a_table_graphic(self):
        from services.ebook_visual_pipeline import _choose_aid

        aid = _choose_aid(1, "Drop the Myths", self.CHAPTER_WITH_TABLE)
        if aid is not None:
            self.assertNotEqual(
                aid.get("source"), "local_manuscript_comparison",
                "the chapter's own table is being redrawn as a duplicate graphic",
            )

    def test_chapter_without_a_printed_table_may_still_use_a_comparison(self):
        from services.ebook_visual_pipeline import _choose_aid

        prose = (
            "Attention is a skill you practise rather than a mood you achieve.\n\n"
            "The return is the whole exercise and it means noticing where you went.\n\n"
            "Discomfort is information rather than a verdict on your ability.\n\n"
            "Consistency helps more than the length of any single session does.\n"
        )
        aid = _choose_aid(1, "Mindfulness Made Simple", prose)
        if aid is not None:
            self.assertNotIn("|", str(aid.get("title") or ""))


# --------------------------------------------------------------------------
# 7. Sequence tables render in order, and long sequences stay complete
# --------------------------------------------------------------------------
class SequenceTableTests(unittest.TestCase):
    def test_day_column_is_recognised_as_a_sequence(self):
        from services.ebook_visual_pipeline import _table_is_sequential

        table = {
            "headers": ["Day", "Practice"],
            "rows": [["1", "Feet on the floor"], ["2", "Five senses"], ["3", "Box breathing"]],
        }
        self.assertTrue(_table_is_sequential(table))

    def test_comparison_table_is_not_treated_as_a_sequence(self):
        from services.ebook_visual_pipeline import _table_is_sequential

        table = {
            "headers": ["The belief", "What is actually true"],
            "rows": [["A", "B"], ["C", "D"], ["E", "F"]],
        }
        self.assertFalse(_table_is_sequential(table))

    def test_a_split_plan_is_merged_rather_than_half_shown(self):
        """A fourteen-day plan authored as "Week one" + "Week two" tables must not
        be drawn as a seven-day graphic under a fourteen-day title."""
        from services.ebook_visual_pipeline import _merge_like_tables

        week1 = {"headers": ["Day", "Practice"], "rows": [[str(i), "x"] for i in range(1, 8)]}
        week2 = {"headers": ["Day", "Practice"], "rows": [[str(i), "y"] for i in range(8, 15)]}
        merged = _merge_like_tables([week1, week2])
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]["rows"]), 14)

    def test_tables_with_different_headers_are_not_merged(self):
        from services.ebook_visual_pipeline import _merge_like_tables

        a = {"headers": ["Day", "Practice"], "rows": [["1", "x"]]}
        b = {"headers": ["Cue", "Habit"], "rows": [["kettle", "breathe"]]}
        self.assertEqual(len(_merge_like_tables([a, b])), 2)


# --------------------------------------------------------------------------
# 8. Template residue and placeholder headers
# --------------------------------------------------------------------------
class TemplateResidueTests(unittest.TestCase):
    """A chapter shipped a table headed "Column A | Column B"."""

    GENERIC_HEADERS = ("column a", "column b", "column 1", "row 1", "header 1", "field 1", "tbd", "lorem ipsum")

    def test_generic_table_headers_are_rejected_as_unreadable(self):
        from services.ebook_book_layout import portrait_table_is_readable

        self.assertFalse(
            portrait_table_is_readable(["Column A", "Column B"]),
            "a placeholder-headed table is being accepted as a finished table",
        )

    def test_real_headers_are_accepted(self):
        from services.ebook_book_layout import portrait_table_is_readable

        self.assertTrue(portrait_table_is_readable(["The belief", "What is actually true"]))

    def test_chapter_prompt_forbids_generic_headers(self):
        """The instruction that stops a model emitting them in the first place."""
        import inspect

        from services import ebook_manuscript_engine as eng

        src = inspect.getsource(eng)
        self.assertIn("Column A", src)
        self.assertIn("placeholder headers", src.lower())


# --------------------------------------------------------------------------
# 9. Back matter: references recognised, disclaimer separated
# --------------------------------------------------------------------------
class BackMatterTests(unittest.TestCase):
    """Only the word "Sources" was recognised, so a correctly-formed
    "References" list was glued onto the end of the disclaimer and rendered as
    legal text, and the quality gate reported the sources as missing."""

    def test_references_heading_is_peeled_as_back_matter(self):
        from services.ebook_book_layout import peel_back_matter

        md = (
            "# Book\n\n## Chapter One\n\nBody.\n\n"
            "**Disclaimer** This is the disclaimer text.\n\n"
            "**References**\n\n- Some Organisation. A Title. 2024.\n"
        )
        body, disclaimer, sources = peel_back_matter(md)
        self.assertIn("Some Organisation", sources)
        self.assertNotIn("Some Organisation", disclaimer)
        self.assertIn("disclaimer text", disclaimer)
        self.assertNotIn("Disclaimer", body)

    def test_sources_heading_still_works(self):
        from services.ebook_book_layout import peel_back_matter

        md = "# B\n\n## C\n\nBody.\n\n**Disclaimer** D.\n\n**Sources**\n\n- A source.\n"
        _body, disclaimer, sources = peel_back_matter(md)
        self.assertIn("A source", sources)
        self.assertEqual(disclaimer.strip(), "D.")

    def test_references_are_not_treated_as_a_numbered_chapter(self):
        from services.ebook_book_layout import numbered_chapters

        md = (
            "# Book\n\n## Real Chapter\n\nBody.\n\n"
            "**Disclaimer** D.\n\n**References**\n\n- A source.\n"
        )
        titles = [t for t, _ in numbered_chapters(md)]
        self.assertEqual(titles, ["Real Chapter"])


# --------------------------------------------------------------------------
# 10. A worked example is content, not vocabulary
# --------------------------------------------------------------------------
class WorkedExampleDetectionTests(unittest.TestCase):
    """The check accepted any chapter containing the word "example" and rejected
    every chapter without it, so a chapter carrying a full worked scenario failed
    while one saying "for example, you might..." passed."""

    def test_named_scenario_counts_as_an_example(self):
        from services.ebook_manuscript_engine import has_worked_example

        body = (
            "Tom believed he needed silence to practise at all.\n\n"
            "Tom lives above a busy road. He tried practising late at night and "
            "he found he was too tired. He decided the flat was the problem.\n\n"
            "What changed for Tom was one instruction. He now practises with the "
            "window open and he told a friend it was the noise he listens to.\n"
        )
        self.assertTrue(has_worked_example(body))

    def test_cue_words_still_count(self):
        from services.ebook_manuscript_engine import has_worked_example

        self.assertTrue(has_worked_example("For example, you might pause before replying."))

    def test_abstract_prose_is_still_rejected(self):
        from services.ebook_manuscript_engine import has_worked_example

        for text in (
            "Attention is a capacity developed over time. Regular training strengthens "
            "the ability to notice drift. Repetition matters more than duration.",
            "Sit upright with both feet flat. Breathe in for four counts. Hold for four "
            "counts. Breathe out for four counts. Repeat until the timer sounds.",
            "Keep sessions short. Attach them to something you already do. Track only "
            "whether you showed up. Restart quickly after a missed day.",
        ):
            self.assertFalse(has_worked_example(text), f"false positive on: {text[:50]}")

    def test_capitalised_jargon_is_not_mistaken_for_a_person(self):
        from services.ebook_manuscript_engine import has_worked_example

        text = (
            "The NHS and NICE both publish guidance on this. Mindfulness-Based "
            "Cognitive Therapy is one structured programme. Reviews have appeared "
            "in JAMA Internal Medicine and elsewhere."
        )
        self.assertFalse(has_worked_example(text))


# --------------------------------------------------------------------------
# 11. Source quality
# --------------------------------------------------------------------------
class SourceQualityTests(unittest.TestCase):
    """A health guide cited Quora, Goodreads and two competitors' marketing blogs."""

    def test_user_generated_and_vendor_domains_are_flagged(self):
        from services.ebook_manuscript_engine import _non_authoritative_sources

        back = (
            "**Sources**\n"
            "- https://www.quora.com/What-are-the-best-practices\n"
            "- https://www.goodreads.com/book/show/12345\n"
            "- https://www.nccih.nih.gov/health/meditation\n"
        )
        flagged = _non_authoritative_sources(back)
        self.assertIn("quora.com", flagged)
        self.assertIn("goodreads.com", flagged)
        self.assertNotIn("nccih.nih.gov", flagged)

    def test_authoritative_sources_are_not_flagged(self):
        from services.ebook_manuscript_engine import _non_authoritative_sources

        back = (
            "**References**\n"
            "- National Center for Complementary and Integrative Health. nccih.nih.gov\n"
            "- Goyal M, et al. JAMA Internal Medicine, 2014;174(3):357-368.\n"
            "- National Health Service (United Kingdom). Mindfulness. nhs.uk\n"
        )
        self.assertEqual(_non_authoritative_sources(back), set())

    def test_long_urls_do_not_reach_the_customer_page(self):
        """A 300-character tracking URL ran past the page edge and failed preflight."""
        from services.ebook_book_layout import printable_source_url

        long_url = "https://www.example.com/" + "a" * 120
        printed = printable_source_url(long_url)
        self.assertLessEqual(len(printed), 80, "an overlong URL will run off the printed page")

    def test_tracking_parameters_are_dropped(self):
        from services.ebook_book_layout import printable_source_url

        printed = printable_source_url("https://www.example.com/book?pd_rd_i=123&ref=abc#frag")
        self.assertNotIn("?", printed)
        self.assertNotIn("#", printed)

    def test_no_invisible_characters_are_inserted(self):
        """Zero-width spaces added as break hints printed as rows of black boxes."""
        from services.ebook_book_layout import printable_source_url

        printed = printable_source_url("https://www.example.com/" + "b" * 120)
        for invisible in ("​", "‌", "‍", "﻿", "­"):
            self.assertNotIn(invisible, printed)


# --------------------------------------------------------------------------
# 12. Fonts embedded in a sold product must be redistributable
# --------------------------------------------------------------------------
class EmbeddedFontTests(unittest.TestCase):
    """Themes named Georgia and Calibri, neither of which is embedded, so every
    designed book silently fell back to base-14 Times."""

    def test_every_theme_requests_an_embedded_family_first(self):
        from services.ebook_design_system import THEMES

        for theme_id, theme in THEMES.items():
            for slot in (theme.font_body, theme.font_heading):
                first = slot.split(",")[0].strip().strip("'\"")
                self.assertTrue(
                    first.startswith("Liberation"),
                    f"{theme_id} asks for {first!r} first, which is not embedded",
                )

    def test_serif_family_is_registered(self):
        from services.ebook_fonts import ensure_ebook_serif

        for name in ensure_ebook_serif():
            self.assertTrue(name.startswith("LiberationSerif"), f"serif fell back to {name}")

    def test_serif_face_css_is_emitted(self):
        from services.ebook_fonts import ebook_serif_face_css

        self.assertIn("@font-face", ebook_serif_face_css())
        self.assertIn("LiberationSerif", ebook_serif_face_css())


if __name__ == "__main__":
    unittest.main()
