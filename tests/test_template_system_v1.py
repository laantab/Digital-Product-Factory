"""Ebook Template System V1 completion pass.

WHAT SHIPPED, WHAT THIS GUARDS
-------------------------------
A visual acceptance review found Template System V1 not ready: two of six
planned templates did not exist, the three pre-existing themes shared one
recolored chapter-opener/TOC skeleton (a genuine "Warm Wellness but
different colors" failure, just happening between two OTHER templates), every
generated diagram (steps, timelines, trackers) drew in one fixed teal palette
regardless of the selected theme, and no customer-facing template chooser
existed -- the only picker was the internal admin rail screen, which also
printed a raw design digest and theme_id.

This file locks in the fixes: six templates with genuinely distinct chapter-
opener/TOC design tokens, a shared _pal()-driven diagram palette any theme
can override, the customer-facing catalog (display_name/best_for, never
theme_id), the wired-up recommendation, and the DRAFT-safe identity contract
a template switch must uphold: manuscript/title/author/cover/photo hashes
frozen, a generated diagram's OWN stored hash allowed to be whatever it was
when visuals were approved (rendering it in a different theme's colors does
not touch that record -- see figure_html's palette parameter).

No external call is made by any test here.
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
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("TAVILY_API_KEY", "")
os.environ.setdefault("PEXELS_API_KEY", "")

from services.ebook_design_system import (  # noqa: E402
    PROFESSIONAL_THEME_IDS,
    THEMES,
    get_theme,
    list_professional_themes,
    recommend_theme,
    theme_css,
    theme_sample_html,
)
from services.ebook_visual_pipeline import (  # noqa: E402
    _DEFAULT_PALETTE,
    _RenderPalette,
    _pal,
    render_aid_png,
    theme_diagram_palette,
)

CUSTOMER_NAMES = {
    "warm_wellness": "Warm Wellness",
    "modern_practical": "Modern Business",
    "bold_creator": "Bold Creator",
    "editorial_professional": "Elegant Editorial",
    "bright_workbook": "Bright Workbook",
    "studio_clean": "Minimal Professional",
}


class SixTemplatesExistTests(unittest.TestCase):
    def test_all_six_internal_ids_are_registered(self):
        for tid in CUSTOMER_NAMES:
            self.assertIn(tid, THEMES, f"missing internal theme: {tid}")
            self.assertIn(tid, PROFESSIONAL_THEME_IDS)

    def test_bold_creator_and_bright_workbook_exist(self):
        self.assertIn("bold_creator", THEMES)
        self.assertIn("bright_workbook", THEMES)
        self.assertEqual(THEMES["bold_creator"].display_name, "Bold Creator")
        self.assertEqual(THEMES["bright_workbook"].display_name, "Bright Workbook")

    def test_customer_facing_names_match_the_planned_catalog(self):
        rows = {r["theme_id"]: r for r in list_professional_themes()}
        for tid, expected_name in CUSTOMER_NAMES.items():
            self.assertEqual(rows[tid]["display_name"], expected_name)

    def test_internal_ids_still_resolve_for_backward_compatibility(self):
        """A saved project referencing the old internal id must keep working
        -- only the customer-facing label changed."""
        for tid in ("studio_clean", "editorial_professional", "modern_practical"):
            t = get_theme(tid)
            self.assertEqual(t.theme_id, tid)
            self.assertTrue(theme_css(tid))

    def test_every_theme_carries_a_customer_facing_best_for_sentence(self):
        for tid in CUSTOMER_NAMES:
            self.assertTrue(THEMES[tid].best_for, f"{tid} has no best_for sentence")
            self.assertNotIn(tid, THEMES[tid].best_for)


class DistinctivenessGateTests(unittest.TestCase):
    """Step 16: prove the six templates cannot collapse back into one
    recolored skeleton. This does not judge beauty -- it judges that the
    component-family design tokens actually differ."""

    def test_chapter_opener_treatments_are_all_different(self):
        openers = [THEMES[tid].chapter_opener for tid in CUSTOMER_NAMES]
        self.assertEqual(len(openers), len(set(openers)),
                          f"two templates share a chapter_opener value: {openers}")

    def test_toc_treatments_are_meaningfully_distinct(self):
        # toc_style plus the toc_accent flag together describe the TOC
        # treatment; warm_wellness's is toc_accent + toc_style="accent_bar",
        # every other template must not collide with it or each other.
        signatures = [
            (THEMES[tid].toc_style, THEMES[tid].toc_accent) for tid in CUSTOMER_NAMES
        ]
        self.assertEqual(len(signatures), len(set(signatures)),
                          f"two templates share a TOC treatment: {signatures}")

    def test_no_two_templates_share_a_full_color_and_font_bundle(self):
        bundles = [
            (THEMES[tid].color_primary, THEMES[tid].color_accent, THEMES[tid].font_heading, THEMES[tid].font_body)
            for tid in CUSTOMER_NAMES
        ]
        self.assertEqual(len(bundles), len(set(bundles)))

    def test_warm_wellness_chapter_opener_is_unchanged_from_the_accepted_baseline(self):
        """Step 3: Warm Wellness is the regression baseline. Its successful
        band/frame/accent treatment must not be touched by this pass."""
        t = THEMES["warm_wellness"]
        self.assertEqual(t.chapter_opener, "band_accent")
        self.assertTrue(t.photo_frame)
        self.assertTrue(t.toc_accent)
        self.assertEqual(t.color_primary, "#0f5e56")
        self.assertEqual(t.color_accent, "#c2603f")

    def test_callout_and_checklist_backgrounds_are_all_different(self):
        """Found while extending this gate to the full Step 13 component
        list: three of six templates (Elegant Editorial, Bold Creator,
        Bright Workbook) shared the exact same #fffbeb callout/checklist
        background -- callouts and checklists both render with
        `background: {t.callout_bg}` (services/ebook_design_system.py), so
        those three templates' callout and checklist boxes would have been
        pixel-identical regardless of every other design token. Fixed by
        giving each template its own callout tint."""
        backgrounds = [THEMES[tid].callout_bg for tid in CUSTOMER_NAMES]
        self.assertEqual(len(backgrounds), len(set(backgrounds)),
                          f"two templates share a callout/checklist background: {backgrounds}")

    def test_table_header_backgrounds_are_all_different(self):
        backgrounds = [THEMES[tid].table_header_bg for tid in CUSTOMER_NAMES]
        self.assertEqual(len(backgrounds), len(set(backgrounds)),
                          f"two templates share a table-header background: {backgrounds}")

    def test_photo_frame_is_not_uniform_across_all_six(self):
        """Step 13's 'photo' component family: photo_frame must be a real
        per-template decision, not a blanket True/False that makes every
        photo look the same regardless of template."""
        flags = {THEMES[tid].photo_frame for tid in CUSTOMER_NAMES}
        self.assertIn(True, flags)
        self.assertIn(False, flags)

    def test_spread_list_toc_does_not_draw_a_line_under_every_row(self):
        """Found while visually zooming into a rendered TOC page: xhtml2pdf
        does not draw a border once around a block's children -- it
        replicates the parent's border-top/border-bottom onto every child
        flowable. `.toc-list`'s intended one-time top/bottom frame for
        Elegant Editorial's spread_list therefore rendered as a rule under
        EVERY row, making it visually indistinguishable from rule_ladder /
        numeral_column despite having its own toc_style value. Fixed by
        dropping the (non-functional, misleading) frame border rather than
        fighting the renderer; the gate below counts actual stroked lines on
        a rendered TOC page rather than trusting the CSS source."""
        import fitz

        from tests.test_warm_wellness_template import _render_pdf

        _html, pdf_bytes, _titles = _render_pdf("editorial_professional")
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        toc_page = doc[2]
        strokes = [d for d in toc_page.get_drawings() if d.get("type") == "s"]
        # One hairline is the page footer rule every theme draws; a per-row
        # frame bug would add one more stroke per TOC entry (2, for this
        # fixture's two chapters).
        self.assertLessEqual(len(strokes), 1,
                              f"spread_list drew {len(strokes)} lines on the TOC page, expected at most the footer rule")

    def test_structured_visual_diagram_palettes_are_all_different(self):
        """Step 13's comparison-table/timeline/tracker/steps families: every
        template's generated-diagram palette (services.ebook_visual_pipeline.
        theme_diagram_palette) must be its own, not a shared fixed teal."""
        palettes = [
            tuple(sorted(theme_diagram_palette(THEMES[tid]).items()))
            for tid in CUSTOMER_NAMES
        ]
        self.assertEqual(len(palettes), len(set(palettes)),
                          f"two templates share a diagram palette: {palettes}")


class RecommendationWiringTests(unittest.TestCase):
    def test_recommendation_covers_all_six_categories(self):
        cases = {
            "a mindfulness and self-care guide": "warm_wellness",
            "a business and finance guide for entrepreneurs": "modern_practical",
            "a guide for social media creators and personal brands": "bold_creator",
            "a memoir and collection of essays": "editorial_professional",
            "a coaching workbook with guided exercises": "bright_workbook",
            "a technical instructional reference guide": "studio_clean",
        }
        for topic, expected in cases.items():
            self.assertEqual(recommend_theme(topic=topic), expected, topic)

    def test_recommendation_is_a_theme_id_not_a_customer_facing_name(self):
        result = recommend_theme(topic="a mindfulness guide")
        self.assertIn(result, THEMES)
        self.assertNotIn(" ", result)  # theme_ids are snake_case, names have spaces

    def test_design_public_view_wires_a_recommendation_in(self):
        from services.ebook_design_workspace import design_public_view

        data = {"title": "A Calm Mind", "topic": "mindfulness and meditation", "fields": {}}
        view = design_public_view(data)
        self.assertEqual(view.get("recommended_theme_id"), "warm_wellness")

    def test_recommendation_is_a_suggestion_not_a_forced_choice(self):
        """All six themes must still be selectable regardless of the
        recommendation -- the catalog is not filtered down to one."""
        from services.ebook_design_workspace import design_public_view

        data = {"title": "A Calm Mind", "topic": "mindfulness", "fields": {}}
        view = design_public_view(data)
        ids = {t["theme_id"] for t in view["themes"]}
        self.assertEqual(ids, set(CUSTOMER_NAMES))


class ThemeAwareStructuredVisualsTests(unittest.TestCase):
    """Step 7: structured visuals must inherit the selected template's
    colors without changing the underlying semantic content."""

    def test_pal_falls_back_to_the_original_fixed_colors_with_no_palette(self):
        self.assertEqual(_pal("primary"), _DEFAULT_PALETTE["primary"])
        self.assertEqual(_pal("accent"), _DEFAULT_PALETTE["accent"])

    def test_theme_diagram_palette_reflects_each_themes_own_tokens(self):
        warm = theme_diagram_palette(THEMES["warm_wellness"])
        bold = theme_diagram_palette(THEMES["bold_creator"])
        business = theme_diagram_palette(THEMES["modern_practical"])
        self.assertNotEqual(warm, bold)
        self.assertNotEqual(warm, business)
        self.assertNotEqual(bold, business)
        self.assertEqual(warm["primary"], (15, 94, 86))
        self.assertEqual(bold["accent"], (225, 29, 72))
        self.assertEqual(business["primary"], (29, 78, 216))

    def test_a_habit_loop_diagram_renders_different_pixels_per_theme(self):
        """Same semantic content (the same node labels), different colors --
        exactly the acceptance example: 'A habit-loop diagram should contain
        the same information in every template' but look different."""
        aid = {
            "type": "loop",
            "title": "The Habit Loop",
            "nodes": ["Cue", "Practice", "Track", "Repeat"],
        }
        with _RenderPalette(theme_diagram_palette(THEMES["warm_wellness"])):
            warm_img = render_aid_png(aid)
        with _RenderPalette(theme_diagram_palette(THEMES["bold_creator"])):
            bold_img = render_aid_png(aid)
        self.assertEqual(warm_img.size, bold_img.size)
        self.assertNotEqual(list(warm_img.getdata()), list(bold_img.getdata()),
                             "the same diagram rendered identically in two different themes")

    def test_figure_html_never_changes_the_stored_asset_identity(self):
        """The approved visual record (asset_path/sha256) must be untouched
        by a theme-aware re-render -- only what this render of the PDF shows
        changes. See figure_html's docstring."""
        from services.ebook_visual_pipeline import figure_html

        aid = {
            "type": "loop",
            "visual_id": "v_ch7",
            "title": "The Habit Loop",
            "caption": "Cue, practice, track, repeat.",
            "nodes": ["Cue", "Practice", "Track", "Repeat"],
            "asset_path": "",  # deliberately missing/stale: must not be read
            "sha256": "deadbeef" * 8,
        }
        html = figure_html(aid, palette=theme_diagram_palette(THEMES["bold_creator"]))
        self.assertIn('data-sha="deadbeef', html)  # identity string unchanged
        self.assertIn("<img", html)  # still rendered something real
        self.assertEqual(aid["sha256"], "deadbeef" * 8)  # aid dict itself untouched
        self.assertEqual(aid["asset_path"], "")


class ThemeSampleAndCatalogTests(unittest.TestCase):
    def test_theme_sample_html_wraps_the_chapter_opener_block(self):
        """Step 10 (Preview): the sample must actually show the chapter-
        opener treatment, not raw unwrapped heading tags that skip every
        theme's chapter_opener CSS entirely."""
        for tid in CUSTOMER_NAMES:
            sample = theme_sample_html(tid)
            self.assertIn('class="chapter-opener-block"', sample, tid)

    def test_theme_sample_html_is_project_independent(self):
        """Preview must not require live manuscript text or a live project
        (Step 10: 'safe and deterministic')."""
        a = theme_sample_html("bold_creator")
        b = theme_sample_html("bold_creator")
        self.assertEqual(a, b)


class NoInternalLeakageTests(unittest.TestCase):
    """Step 12: the customer-facing screen must not print a design digest or
    a raw theme_id."""

    def test_design_stage_screen_does_not_render_the_design_digest(self):
        src = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        start = src.index('stageId === "design"')
        end = src.index("} else if (stageId ===", start)
        block = src[start:end]
        self.assertNotIn("Design digest", block)
        self.assertNotIn("d.design_digest", block)

    def test_design_stage_screen_uses_use_this_template_language(self):
        src = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        start = src.index('stageId === "design"')
        end = src.index("} else if (stageId ===", start)
        block = src[start:end]
        self.assertIn("Use This Template", block)
        self.assertIn("Preview", block)
        self.assertIn("Recommended for Your Ebook", block)
        self.assertNotIn("Approve design</button>", block)


class AllSixTemplatesRenderRegressionTests(unittest.TestCase):
    """Step 17 checklist: every one of the six templates must render a real
    project's manuscript end-to-end, with zero external/paid calls, and
    without letting a chapter's own Markdown heading print twice (the exact
    Project 351 defect from the prior repair, now checked across all six
    designs rather than just Warm Wellness)."""

    def test_all_six_templates_render_a_project_351_like_fixture(self):
        from unittest.mock import patch

        from tests.test_warm_wellness_template import _render_pdf

        with patch(
            "services.ebook_pexels._http_get",
            side_effect=AssertionError("no network calls rendering any template"),
        ):
            for theme_id in CUSTOMER_NAMES:
                with self.subTest(theme=theme_id):
                    html, pdf_bytes, titles = _render_pdf(theme_id)
                    self.assertTrue(pdf_bytes.startswith(b"%PDF"))
                    self.assertEqual(len(titles), 2)

    def test_no_theme_prints_a_chapters_own_markdown_heading_twice(self):
        """A regression of the raw-Markdown-leak defect (Project 351 Ch.2/5)
        would show the chapter's own '## Title' heading surviving into the
        body text on top of the designed chapter-opener heading. Guard it on
        every template, not only the one it was first found on."""
        from tests.test_warm_wellness_template import _render_pdf

        for theme_id in CUSTOMER_NAMES:
            with self.subTest(theme=theme_id):
                _html, pdf_bytes, titles = _render_pdf(theme_id)
                import fitz

                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
                text = "\n".join(p.get_text("text") for p in doc)
                self.assertNotIn("##", text, f"raw Markdown heading leaked into {theme_id}")
                for title in titles:
                    # The opener prints the title once as a designed heading;
                    # it must never also survive as a literal "## Title" body
                    # line immediately under it.
                    self.assertNotIn(f"## {title}", text)


class LifecyclePreservationTests(unittest.TestCase):
    """Step 17 checklist: the stale-export fix's DRAFT-vs-APPROVED/LOCKED
    branch (services.ebook_revision_identity.workspace_export_action) must
    preserve an accepted package under BOTH accepted lifecycle states, not
    only APPROVED. See tests/test_export_revision_identity.py for the
    APPROVED case and the DRAFT-rebuilds case this mirrors."""

    def test_a_locked_packages_digest_is_preserved_like_an_approved_ones(self):
        import hashlib
        import tempfile
        from pathlib import Path as _Path

        import services.ebook_package as pkg
        from services.ebook_revision_identity import (
            certified_pdf_sha256,
            stamp_current_revision,
            workspace_export_action,
        )

        pdf_bytes = b"%PDF-1.4\n% a small but real-looking file\n%%EOF\n"
        zip_bytes = b"PK\x03\x04" + b"\x00" * 40
        root = _Path(tempfile.mkdtemp(prefix="revid_locked_"))
        old_exports = pkg.EXPORTS_DIR
        pkg.EXPORTS_DIR = str(root)
        self.addCleanup(setattr, pkg, "EXPORTS_DIR", old_exports)
        package_id = "revision-identity-locked-fixture"
        pkg_dir = root / package_id
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "ebook.pdf").write_bytes(pdf_bytes)
        (pkg_dir / "package.zip").write_bytes(zip_bytes)

        certified = hashlib.sha256(pdf_bytes).hexdigest()
        data = {
            "export_package_id": package_id,
            "artifact_revision": 3,
            "artifact_state": "LOCKED",
            "ebook_export_identity": {
                "pdf_sha256": certified,
                "zip_sha256": hashlib.sha256(zip_bytes).hexdigest(),
                "preview_digest": certified,
            },
        }
        # A later verification re-render produced different bytes on disk.
        (pkg_dir / "ebook.pdf").write_bytes(pdf_bytes + b"\n")
        stamp_current_revision(data)
        self.assertEqual(data["ebook_export_identity"]["pdf_sha256"], certified,
                          "a LOCKED package's certified digest must not move")
        self.assertEqual(certified_pdf_sha256(data), certified)
        self.assertEqual(workspace_export_action(data), "keep_existing")


if __name__ == "__main__":
    unittest.main()
