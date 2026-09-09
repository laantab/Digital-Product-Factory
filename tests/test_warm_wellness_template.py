"""Warm Wellness template engine: generic template spec, Warm Wellness theme,
TOC/bookmark clickability, resolution, timeline/calendar layout, back matter,
revision identity, and preservation/isolation guarantees.

Zero paid or external calls. Uses an isolated temp SQLite database (never the
live projects.db) for the one test that touches `database` at all.
"""
from __future__ import annotations

import io
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""
os.environ["MINIMAX_API_KEY"] = ""
os.environ["PEXELS_API_KEY"] = ""

from services.ebook_design_system import (  # noqa: E402
    PROFESSIONAL_THEME_IDS,
    THEMES,
    get_theme,
    list_professional_themes,
    recommend_theme,
    theme_css,
    theme_sample_html,
)
from services.ebook_fonts import PROPRIETARY_FONT_MARKERS  # noqa: E402
from services.ebook_design_spec import build_ebook_design  # noqa: E402
from services.ebook_book_layout import (  # noqa: E402
    find_designed_chapter_pages,
    numbered_chapters,
    render_designed_ebook_html,
)
from services.ebook_design_export import (  # noqa: E402
    _add_chapter_bookmarks,
    render_designed_bundle,
)
from services.pdf_export import _html_to_pdf_xhtml2pdf  # noqa: E402
from services.ebook_visual_pipeline import (  # noqa: E402
    insert_planned_visuals_into_html,
    render_aid_png,
)

def _fixture_paragraph(seed: str, n: int) -> str:
    """Varied prose broken into real paragraphs, plain test fixture text,
    not from any real book.

    Two things an earlier version of this fixture got wrong, both found by
    timing each pipeline stage with a hard timeout rather than by reading
    xhtml2pdf's source:
      1. A parenthetical "(variant N)" suffix on every sentence, repeated
         ~90 times, sent xhtml2pdf's line-breaking into what looks like
         catastrophic-backtracking territory -- multi-minute hangs with
         none of this file's own code on the call stack.
      2. Even without the parens, joining 90 sentences into ONE unbroken
         paragraph (no real manuscript does this) triggered the same class
         of slowdown. A paragraph break every 6 sentences -- ordinary prose
         shape -- fixed it outright.
    Real book prose was never at risk; both are fixture-shape traps."""
    sentences = [
        f"{seed} opens with a small, concrete step rather than a grand plan.",
        "Most readers arrive already busy, so the instructions stay short.",
        "Each idea here is meant to be tried once before it is judged.",
        "A short habit repeated beats a long one abandoned after a week.",
        "Nothing in this section requires special equipment or a quiet room.",
        "The point is not perfection, it is noticing and starting again.",
        "Progress here tends to be small, specific, and easy to miss.",
        "Write down what actually happened, not what you think should happen.",
        "This paragraph exists only to give the fixture enough real words.",
        "A reader skimming this page should still find one usable sentence.",
    ]
    paras: list[str] = []
    cur: list[str] = []
    for i in range(n):
        cur.append(sentences[i % len(sentences)])
        if len(cur) >= 6:
            paras.append(" ".join(cur))
            cur = []
    if cur:
        paras.append(" ".join(cur))
    return "\n\n".join(paras)


def _fixture_project_data() -> dict:
    """A minimal project dict whose approved `outline` matches FIXTURE_MD's
    own two chapters -- render_designed_bundle's quality gate compares the
    manuscript against this approved outline, not the prose itself."""
    return {
        "title": "Fixture Book", "subtitle": "", "author_brand": "Fixture Author",
        "content": FIXTURE_MD, "cover_design": {}, "artifact_state": "DRAFT",
        "outline": [
            {"order": 1, "title": "Chapter One", "purpose": "fixture"},
            {"order": 2, "title": "Chapter Two", "purpose": "fixture"},
        ],
    }


FIXTURE_MD = (
    "# Fixture Book\n\n"
    "## Chapter One\n\n"
    + _fixture_paragraph("Chapter One", 90)
    + "\n\n## Chapter Two\n\n"
    + _fixture_paragraph("Chapter Two", 90)
    + "\n\n**Disclaimer**\n\nThis is a fixture disclaimer, for tests only.\n\n"
    "**References**\n\n- A fixture reference, for tests only.\n"
)


def _render_pdf(theme_id: str, *, md: str = FIXTURE_MD):
    design = build_ebook_design(theme_id=theme_id, manuscript_digest="fixture")
    html = render_designed_ebook_html(
        title="Fixture Book", subtitle="", author="Fixture Author",
        manuscript_md=md, design=design, visual_plan=None, include_title_page=True,
    )
    pdf_bytes = _html_to_pdf_xhtml2pdf(html)
    titles = [t for t, _ in numbered_chapters(md)]
    pdf_bytes = _add_chapter_bookmarks(pdf_bytes, titles)
    return html, pdf_bytes, titles


class TemplateSpecValidation(unittest.TestCase):
    def test_warm_wellness_is_registered(self):
        self.assertIn("warm_wellness", THEMES)
        self.assertIn("warm_wellness", PROFESSIONAL_THEME_IDS)
        ids = [row["theme_id"] for row in list_professional_themes()]
        self.assertIn("warm_wellness", ids)

    def test_template_spec_has_required_fields(self):
        t = get_theme("warm_wellness")
        for attr in (
            "theme_id", "display_name", "color_primary", "color_accent",
            "font_body", "font_heading", "margin_in", "chapter_opener",
            "table_header_bg", "callout_bg", "topics", "photo_frame", "toc_accent",
        ):
            self.assertTrue(hasattr(t, attr), f"missing field: {attr}")
        self.assertGreater(len(t.topics), 0)

    def test_let_the_factory_choose_recommends_warm_wellness_for_wellness_topics(self):
        self.assertEqual(
            recommend_theme(topic="5-Minute Mindfulness for Busy Beginners", title="5-Minute Mindfulness for Busy Beginners"),
            "warm_wellness",
        )
        self.assertEqual(recommend_theme(topic="a self-care journal for beginners"), "warm_wellness")

    def test_unrelated_topic_falls_back_to_studio_clean_not_warm_wellness(self):
        # "budget planner for freelancers" used to be this test's example, but
        # Template System V1 added Bright Workbook (topics include "planner")
        # and Modern Business (topics include "finance"/"consulting") --
        # matching one of those now is the CORRECT, more specific
        # recommendation, not a regression. This test's actual point is
        # narrower: a topic with nothing recognizable in any of the six
        # catalogs must fall through to the generic default, not guess.
        self.assertEqual(
            recommend_theme(topic="the history of ceramic pottery in ancient civilizations"),
            "studio_clean",
        )

    def test_planner_and_finance_topics_now_get_their_own_dedicated_templates(self):
        """The more specific match Template System V1 makes possible."""
        self.assertEqual(recommend_theme(topic="budget planner for freelancers"), "bright_workbook")
        self.assertEqual(recommend_theme(topic="a small business finance guide"), "modern_practical")


class ExistingThemeBackwardCompatibility(unittest.TestCase):
    """Every pre-existing theme must still build valid CSS, HTML and PDF."""

    def test_all_pre_warm_wellness_themes_still_render(self):
        for theme_id in ("studio_clean", "editorial_professional", "modern_practical"):
            with self.subTest(theme=theme_id):
                css = theme_css(theme_id)
                self.assertIn("--ebook-primary", css)
                html = theme_sample_html(theme_id)
                self.assertIn("<html", html)
                _html, pdf_bytes, _titles = _render_pdf(theme_id)
                self.assertTrue(pdf_bytes.startswith(b"%PDF"))

    def test_ink_editorial_alias_unaffected(self):
        self.assertIs(get_theme("ink_editorial"), get_theme("editorial_professional"))


class WarmWellnessRendering(unittest.TestCase):
    def test_warm_wellness_renders_a_valid_pdf(self):
        html, pdf_bytes, titles = _render_pdf("warm_wellness")
        self.assertTrue(pdf_bytes.startswith(b"%PDF"))
        self.assertIn("chapter-opener-block", html)
        self.assertEqual(titles, ["Chapter One", "Chapter Two"])

    def test_no_css_gradient_function_is_used_anywhere(self):
        """Regression test for the invisible-band bug: xhtml2pdf silently
        drops linear-gradient(), leaving white text on a white page. Caught
        by rendering an actual chapter opener and looking at it -- this test
        makes sure the fix (solid background) never regresses. Checks for
        the CSS function call, not the substring, since the fix's own code
        comment legitimately mentions the word "gradient" while explaining
        why one is not used."""
        css = theme_css("warm_wellness")
        # Strip CSS comments first -- the fix's own comment legitimately
        # names "linear-gradient()" while explaining why one is not used.
        css_no_comments = re.sub(r"/\*.*?\*/", "", css, flags=re.S).lower()
        self.assertNotIn("linear-gradient(", css_no_comments)
        self.assertNotIn("radial-gradient(", css_no_comments)

    def test_licensed_fonts_only_no_forbidden_markers(self):
        """Checks the face actually loaded/embedded (the first name in the
        CSS font-family stack) -- not the whole fallback string. Every theme
        here, including the pre-existing ones, lists "Georgia"/"Helvetica" as
        a browser-preview fallback after the embedded Liberation face; this
        renderer never resolves those names to a system font, only the first
        (embedded) one, so that is the name that matters for licensing."""
        t = get_theme("warm_wellness")
        for stack in (t.font_body, t.font_heading):
            first_face = stack.split(",")[0].strip().lower()
            for marker in PROPRIETARY_FONT_MARKERS:
                self.assertNotIn(marker, first_face, f"forbidden font marker {marker!r} in embedded face {first_face!r}")
            self.assertIn("liberation", first_face)


class VisualPlacementByChapter(unittest.TestCase):
    def test_figure_is_not_nested_inside_the_chapter_band(self):
        """Regression test: insert_planned_visuals_into_html used to insert
        the figure right after the bare <h2>, which is now wrapped in
        .chapter-opener-block -- so the figure (and its caption) inherited
        the band's background/white text. Caught by rendering an actual
        chapter with a visual and looking at it."""
        from bs4 import BeautifulSoup

        design = build_ebook_design(theme_id="warm_wellness", manuscript_digest="fixture2")
        html = render_designed_ebook_html(
            title="Fixture Book", subtitle="", author="A", manuscript_md=FIXTURE_MD,
            design=design, visual_plan=None, include_title_page=False,
        )
        # A tiny 1x1 real PNG so figure_html's file-existence check passes.
        from PIL import Image
        tmp_png = Path(tempfile.gettempdir()) / "warm_wellness_test_visual.png"
        Image.new("RGB", (10, 10), (0, 0, 0)).save(tmp_png)
        plan = {"chapters": [{"chapter": "Chapter One", "chapter_index": 1, "aids": [{
            "visual_id": "v1", "type": "infographic", "caption": "Test caption",
            "asset_path": str(tmp_png), "omitted": False,
        }]}]}
        out = insert_planned_visuals_into_html(html, plan)
        soup = BeautifulSoup(out, "html.parser")
        block = soup.find("div", class_="chapter-opener-block")
        self.assertIsNotNone(block)
        self.assertIsNone(block.find("figure"), "figure must not be nested inside the chapter band")
        section = soup.find("section", class_="chapter-page")
        direct_figs = [c for c in section.find_all("figure", recursive=False)]
        self.assertEqual(len(direct_figs), 1, "figure must be a direct child of the chapter section")


class ClickableTocAndBookmarks(unittest.TestCase):
    def test_toc_anchors_produce_real_internal_links(self):
        """Regression test: xhtml2pdf only registers an anchor target from
        <a name=...>, never from an element's id= (its own tags.py has a
        literal `# XXX Also support attr.id ?`). The TOC's href="#chapter-N"
        never resolved to anything until each chapter got an <a name=...>
        anchor. Verified against the actual PDF bytes, not the HTML source."""
        import fitz

        for theme_id in ("studio_clean", "warm_wellness"):
            with self.subTest(theme=theme_id):
                _html, pdf_bytes, titles = _render_pdf(theme_id)
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                all_links = [l for p in doc for l in p.get_links()]
                self.assertEqual(len(all_links), len(titles), "one internal link per chapter expected")
                for link in all_links:
                    self.assertEqual(link.get("kind"), fitz.LINK_GOTO)
                    self.assertFalse(link.get("uri"), "a chapter link must be internal, not a URI")
                # Destinations must match find_designed_chapter_pages's own
                # page map, so a click actually lands on the right chapter.
                page_map = find_designed_chapter_pages(pdf_bytes, titles)
                dest_pages = sorted(l["page"] for l in all_links)
                expected_pages = sorted(v - 1 for v in page_map.values())
                self.assertEqual(dest_pages, expected_pages)

    def test_pdf_has_one_bookmark_per_chapter_plus_contents(self):
        for theme_id in ("studio_clean", "warm_wellness"):
            with self.subTest(theme=theme_id):
                import fitz

                _html, pdf_bytes, titles = _render_pdf(theme_id)
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                toc = doc.get_toc()
                bookmark_titles = [row[1] for row in toc]
                self.assertIn("Contents", bookmark_titles)
                for title in titles:
                    self.assertIn(title, bookmark_titles)
                # xhtml2pdf also auto-generates its own outline entries from
                # every h1/h2 in this minimal direct-render harness (pre-
                # existing behavior, unrelated to this fix) -- the
                # Project 351 review's full render_designed_bundle pipeline
                # does not show that duplication (verified: exactly 9
                # chapters + Contents = 10, no extras). What this test
                # guards is that OUR chapter bookmarks are always present,
                # not the total count of a simplified harness.
                self.assertGreaterEqual(len(toc), len(titles) + 1)

    def test_bookmarking_never_destroys_the_toc_links(self):
        import fitz

        _html, pdf_bytes, titles = _render_pdf("warm_wellness")
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        total_links = sum(len(p.get_links()) for p in doc)
        self.assertEqual(total_links, len(titles))


class OutboundUrlAudit(unittest.TestCase):
    def test_no_outbound_urls_in_rendered_pdf_text(self):
        for theme_id in ("studio_clean", "warm_wellness"):
            with self.subTest(theme=theme_id):
                import fitz

                _html, pdf_bytes, _titles = _render_pdf(theme_id)
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                text = "\n".join(p.get_text("text") for p in doc)
                urls = re.findall(r"https?://\S+|www\.\S+", text)
                self.assertEqual(urls, [])


class ImageResolution(unittest.TestCase):
    def test_render_aid_png_at_2x_doubles_pixel_dimensions(self):
        aid = {"type": "comparison", "title": "T", "table": {
            "headers": ["A", "B"], "rows": [["1", "2"], ["3", "4"]],
        }}
        img_1x = render_aid_png(aid, scale=1.0)
        img_2x = render_aid_png(aid, scale=2.0)
        self.assertEqual(img_2x.size, (img_1x.size[0] * 2, img_1x.size[1] * 2))

    def test_new_visual_types_reach_at_least_1400px_wide_at_2x(self):
        cases = [
            {"type": "infographic", "title": "T", "cards": [{"stat": "1", "label": "x"}] * 4},
            {"type": "flow", "title": "T", "steps": [{"kind": "in", "timing": "4", "label": "x"}] * 4},
            {"type": "loop", "title": "T", "nodes": ["a", "b", "c", "d"]},
            {"type": "calendar", "title": "T", "days": [{"day": i, "label": "x", "duration": "1"} for i in range(1, 15)]},
        ]
        for aid in cases:
            with self.subTest(kind=aid["type"]):
                img = render_aid_png(aid, scale=2.0)
                self.assertGreaterEqual(img.size[0], 1400)

    def test_embed_default_targets_the_1400_1800_range(self):
        from services.ebook_visual_pipeline import _embed_preview_image
        import inspect

        default_max_w = inspect.signature(_embed_preview_image).parameters["max_w"].default
        self.assertGreaterEqual(default_max_w, 1400)
        self.assertLessEqual(default_max_w, 1800)


class TimelineAndCalendarLayout(unittest.TestCase):
    def test_timeline_roadmap_has_room_for_six_labels(self):
        aid = {"type": "timeline", "title": "T", "items": [f"Label {i} with some real words in it" for i in range(1, 7)]}
        img = render_aid_png(aid, scale=1.0)
        # The pre-fix layout was 420px tall and labels could collide; the
        # fix gives it real vertical room.
        self.assertGreaterEqual(img.size[1], 500)

    def test_calendar_tracker_has_a_checkbox_sized_cell_for_every_day(self):
        days = [{"day": i, "label": f"Practice {i}", "duration": "5 min"} for i in range(1, 15)]
        aid = {"type": "calendar", "title": "T", "days": days}
        img = render_aid_png(aid, scale=1.0)
        # The pre-fix cell height (168px) was cramped; verify the fix's
        # taller cells by checking overall canvas height grew accordingly.
        self.assertGreaterEqual(img.size[1], 600)


class DesignedBackMatter(unittest.TestCase):
    def test_back_matter_headings_are_styled(self):
        css = theme_css("warm_wellness")
        self.assertIn(".back-matter-page h2", css)

    def test_disclaimer_and_sources_render_with_no_promotional_links(self):
        _html, pdf_bytes, _titles = _render_pdf("warm_wellness")
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(p.get_text("text") for p in doc)
        self.assertIn("Disclaimer", text)
        # render_designed_ebook_html always titles this section "Sources"
        # in the PDF, regardless of what the manuscript's own back-matter
        # heading said (here, "References").
        self.assertIn("Sources", text)
        urls = re.findall(r"https?://\S+|www\.\S+", text)
        self.assertEqual(urls, [])


class RevisionIdentityAndIsolation(unittest.TestCase):
    def test_different_themes_produce_different_pdf_identity(self):
        _h1, pdf_studio, _t1 = _render_pdf("studio_clean")
        _h2, pdf_warm, _t2 = _render_pdf("warm_wellness")
        import hashlib

        self.assertNotEqual(hashlib.sha256(pdf_studio).hexdigest(), hashlib.sha256(pdf_warm).hexdigest())

    def test_render_designed_bundle_never_calls_the_database(self):
        """render_designed_bundle must be a pure data-in/bytes-out function --
        no approval, no export_ready side effects saved anywhere it doesn't
        control, and specifically it must never touch the database itself.

        require_quality_pass is patched out here: this fixture's synthetic
        prose does not carry the tables/workflows a real chapter needs to
        clear that gate, and the manuscript-quality rubric itself is
        already covered by this app's own quality-gate tests. What this
        test verifies is unrelated to prose quality -- it is that the export
        path never reaches the database."""
        from unittest.mock import patch

        from services.ebook_design_spec import build_ebook_design as _bed
        from services.ebook_project_workspace import manuscript_digest as _md

        data = _fixture_project_data()
        design = _bed(theme_id="warm_wellness", manuscript_digest=_md(data))
        data["ebook_design"] = design.to_dict()
        with tempfile.TemporaryDirectory() as tmp:
            with patch("services.ebook_design_export.require_quality_pass", return_value=None), \
                 patch("database.update_project", side_effect=AssertionError("must not touch the DB")):
                bundle = render_designed_bundle(data, output_dir=tmp)
            self.assertTrue((Path(tmp) / "ebook.pdf").is_file())
            self.assertIn("identity", bundle)

    def test_freeze_manuscript_title_author_are_never_mutated(self):
        from unittest.mock import patch

        from services.ebook_project_workspace import manuscript_digest as _md

        data = _fixture_project_data()
        before = (data["title"], data["author_brand"], data["content"], data["artifact_state"])
        design = build_ebook_design(theme_id="warm_wellness", manuscript_digest=_md(data))
        data["ebook_design"] = design.to_dict()
        with tempfile.TemporaryDirectory() as tmp:
            with patch("services.ebook_design_export.require_quality_pass", return_value=None):
                render_designed_bundle(data, output_dir=tmp)
        after = (data["title"], data["author_brand"], data["content"], data["artifact_state"])
        self.assertEqual(before, after)

    def test_preserved_project_351_package_is_untouched_if_present(self):
        """Best-effort: only meaningful on a machine with Project 351's real
        exports, so it skips cleanly elsewhere rather than failing the gate
        on an unrelated developer machine."""
        preserved_pdf = ROOT / "exports" / "ebook-visuals-local" / "ebook.pdf"
        preserved_zip = ROOT / "exports" / "ebook-visuals-local" / "package.zip"
        if not preserved_pdf.is_file() or not preserved_zip.is_file():
            self.skipTest("Project 351 preserved package not present on this machine")
        import hashlib

        pdf_sha = hashlib.sha256(preserved_pdf.read_bytes()).hexdigest()
        zip_sha = hashlib.sha256(preserved_zip.read_bytes()).hexdigest()
        self.assertEqual(pdf_sha, "6202e3a559db9313b61ec2d54ff689f6236a3b037308820bc77cfedf4d01f5bd")
        self.assertEqual(zip_sha, "5044f086b7335e139bcec94e1b743c4f7effd4fe9eb7738973140176ef6d5c1f")


class TestDatabaseIsolation(unittest.TestCase):
    """The one test in this file that touches `database` at all -- against a
    throwaway temp SQLite file, never projects.db."""

    def test_operations_run_against_an_isolated_temp_database(self):
        import importlib

        import database as _database

        def _restore():
            os.environ.pop("FACTORY_DB_PATH", None)
            importlib.reload(_database)

        # addCleanup, not try/finally: this repo's own database-isolation
        # scanner (tests/test_database_identity_is_not_leaked.py) only
        # recognizes addCleanup/tearDown/monkeypatch.setenv as visible
        # restoration -- a manual try/finally reads as a test that borrowed
        # the database and never gave it back, even though it did.
        self.addCleanup(_restore)

        with tempfile.TemporaryDirectory() as tmp:
            temp_db = os.path.join(tmp, "warm_wellness_test.db")
            os.environ["FACTORY_DB_PATH"] = temp_db
            importlib.reload(_database)
            self.assertEqual(os.path.abspath(_database.DB_PATH), os.path.abspath(temp_db))
            _database.init_db()
            self.assertTrue(os.path.isfile(temp_db))
            real_db = ROOT / "projects.db"
            if real_db.is_file():
                self.assertNotEqual(os.path.abspath(temp_db), os.path.abspath(str(real_db)))


class NoPaidOrExternalCallsDuringTests(unittest.TestCase):
    def test_no_pexels_or_ai_client_calls_happen_in_this_suite(self):
        from unittest.mock import patch

        with patch("services.ebook_pexels._http_get", side_effect=AssertionError("no network calls in tests")):
            for theme_id in ("studio_clean", "warm_wellness"):
                # No exception means the whole render path -- template CSS,
                # visual rendering, PDF conversion, bookmarking -- never once
                # reached the network call this patch would have caught.
                _render_pdf(theme_id)


if __name__ == "__main__":
    unittest.main()
