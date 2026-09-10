"""Planner design system: themes, cover engine, image slot, and design gate.

The planner engine renders through a theme (tokens) and a component library.
This suite protects the customer-facing promises of that system:

  * five faith themes plus the Budget Planner's house theme, each selectable
    by key with no code edit, each rendering a complete planner that passes
    the Editor-in-Chief;
  * four cover styles, an image slot that accepts a supplied photograph, and
    a procedural cover that never depends on an outside service;
  * the design checks fail a planner whose chrome, page numbers, margins,
    theme colours or cover artwork are wrong, and flag a visually plain
    planner as needing improvement rather than passing it.

Zero paid/external calls. FACTORY_TEST_MODE via environment.
"""
from __future__ import annotations

import copy
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FACTORY_TEST_MODE", "1")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("TAVILY_API_KEY", "")
os.environ.setdefault("PEXELS_API_KEY", "")

import fitz  # noqa: E402

from services.editor_in_chief import VERDICT_PASS  # noqa: E402
from services.editor_in_chief_planner import (  # noqa: E402
    check_planner_cover_artwork,
    check_planner_design_richness,
    check_planner_page_furniture,
    check_planner_print_safety,
    check_planner_render_notes,
    check_planner_theme_consistency,
    collect_planner_candidate,
    review_planner,
)
from services.planner import (  # noqa: E402
    BUDGET,
    COVER_STYLES,
    DEFAULT_THEME,
    FAITH,
    THEMES,
    PlannerPdfRequest,
    PlannerRequest,
    build_planner_pdf,
    build_planner_plan,
    resolve_theme,
    theme_choices,
)
from services.planner.cover import build_cover_art, load_slot_image  # noqa: E402
from services.planner.themes import normalize_cover_style  # noqa: E402

FAITH_THEME_KEYS = ("warm_grace", "modern_minimal", "floral_devotion",
                    "family_heritage", "joyful_light")


def _render(exports_dir: str, **kw) -> tuple[object, list[str], dict]:
    """Build one planner, render its pages, and collect the reviewer's candidate."""
    os.environ["FLASK_EXPORTS_DIR"] = exports_dir
    import importlib

    import services.planner.pdf_builder as pb

    importlib.reload(pb)
    req = pb.PlannerPdfRequest(**{"planner_type": FAITH, "pages": 24,
                                  "author": "Digital Product Factory", **kw})
    result = pb.build_planner_pdf(req)
    assert not result.errors, result.errors
    page_dir = os.path.join(exports_dir, "pages_" + (req.package_id or "x"))
    os.makedirs(page_dir, exist_ok=True)
    images: list[str] = []
    doc = fitz.open(result.pdf_path)
    for i, page in enumerate(doc):
        path = os.path.join(page_dir, f"p{i + 1:03d}.png")
        page.get_pixmap(dpi=72).save(path)
        images.append(path)
    doc.close()
    candidate = collect_planner_candidate(
        result.plan, pdf_path=result.pdf_path, package_dir=result.package_dir,
        page_images=images, author="Digital Product Factory",
        layout_info=result.layout_info)
    return result, images, candidate


class ThemeRegistryTests(unittest.TestCase):
    def test_five_faith_themes_are_offered_by_key(self):
        offered = dict(theme_choices(FAITH))
        for key in FAITH_THEME_KEYS:
            self.assertIn(key, offered, key)
        self.assertEqual(theme_choices(FAITH)[0][0], DEFAULT_THEME[FAITH])
        self.assertNotIn("ledger", offered, "the budget house style is not a faith theme")

    def test_every_theme_defines_the_full_token_set(self):
        for key, t in THEMES.items():
            with self.subTest(theme=key):
                for token in ("paper", "ink", "muted", "primary", "accent", "accent_soft",
                              "band", "rule", "cover_bg", "cover_text", "cover_accent"):
                    value = getattr(t, token)
                    self.assertRegex(value, r"^#[0-9A-Fa-f]{6}$", f"{key}.{token}")
                self.assertIn(t.header_style, ("band", "rule", "soft"))
                self.assertIn(t.ornament, ("diamond", "line", "leaf", "chevron", "sun"))
                self.assertIn(t.line_style, ("ruled", "dotted"))
                self.assertIn(t.cover_style_default, COVER_STYLES)
                fonts = t.fonts()
                self.assertTrue(all([fonts.display, fonts.display_italic, fonts.body,
                                     fonts.body_bold, fonts.label]))

    def test_theme_keys_labels_and_aliases_resolve(self):
        for value, expected in (("warm_grace", "warm_grace"), ("Warm Grace", "warm_grace"),
                                ("Modern Minimal Faith", "modern_minimal"),
                                ("floral", "floral_devotion"), ("Family Heritage", "family_heritage"),
                                ("JOYFUL LIGHT", "joyful_light"), ("", DEFAULT_THEME[FAITH])):
            with self.subTest(value=value):
                theme, warning = resolve_theme(value, FAITH)
                self.assertEqual(theme.key, expected)
                self.assertEqual(warning, "")

    def test_unknown_theme_falls_back_with_a_warning_not_an_error(self):
        theme, warning = resolve_theme("neon_disco", FAITH)
        self.assertEqual(theme.key, DEFAULT_THEME[FAITH])
        self.assertIn("neon_disco", warning)
        plan = build_planner_plan(PlannerRequest(planner_type=FAITH, pages=24,
                                                 design_theme="neon_disco"))
        self.assertEqual(plan.design_theme, DEFAULT_THEME[FAITH])
        self.assertTrue(any("neon_disco" in w for w in plan.warnings))

    def test_a_faith_theme_is_refused_for_the_budget_planner(self):
        theme, warning = resolve_theme("floral_devotion", BUDGET)
        self.assertEqual(theme.key, DEFAULT_THEME[BUDGET])
        self.assertTrue(warning)

    def test_cover_style_choices_normalise_from_ui_labels(self):
        theme = THEMES["warm_grace"]
        for label, expected in (("Full photo", "full_photo"), ("Photo + text panel", "photo_panel"),
                                ("Soft image with overlay", "soft_overlay"),
                                ("Elegant minimal", "minimal_texture"),
                                ("Theme default", theme.cover_style_default), ("", theme.cover_style_default)):
            with self.subTest(label=label):
                style, warning = normalize_cover_style(label, theme)
                self.assertEqual(style, expected)
                self.assertEqual(warning, "")
        style, warning = normalize_cover_style("hologram", theme)
        self.assertEqual(style, theme.cover_style_default)
        self.assertTrue(warning)


class CoverEngineTests(unittest.TestCase):
    def test_every_theme_paints_every_cover_style_locally(self):
        letter = (612.0, 792.0)
        for key, theme in THEMES.items():
            for style in COVER_STYLES:
                with self.subTest(theme=key, style=style):
                    art = build_cover_art(theme, letter, style=style, dpi=60)
                    self.assertEqual(art.style, style)
                    self.assertEqual(art.source, "procedural")
                    self.assertGreaterEqual(art.image.width, 600)
                    self.assertEqual(art.notes, [])
                    # Art must reach the trim as ink: no near-white edge rows.
                    px = list(art.image.convert("L").resize((40, 52)).getdata())
                    self.assertLess(max(px), 247, "cover artwork must not read as a white border")

    def test_the_image_slot_accepts_a_supplied_photograph(self):
        from PIL import Image

        tmp = tempfile.mkdtemp(prefix="planner_slot_")
        try:
            photo = os.path.join(tmp, "hero.jpg")
            Image.new("RGB", (1400, 2000), (90, 120, 160)).save(photo, quality=85)
            theme = THEMES["joyful_light"]
            for style in COVER_STYLES:
                with self.subTest(style=style):
                    art = build_cover_art(theme, (612.0, 792.0), style=style,
                                          image_path=photo, dpi=60)
                    self.assertEqual(art.source, "file")
                    self.assertEqual(art.notes, [])
            fitted, note = load_slot_image(photo, (600, 800))
            self.assertIsNotNone(fitted)
            self.assertEqual(fitted.size, (600, 800))
            self.assertEqual(note, "")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_a_missing_or_tiny_image_falls_back_to_the_painted_cover_and_says_so(self):
        from PIL import Image

        tmp = tempfile.mkdtemp(prefix="planner_slot_")
        try:
            tiny = os.path.join(tmp, "tiny.png")
            Image.new("RGB", (200, 200), (10, 10, 10)).save(tiny)
            theme = THEMES["warm_grace"]
            art = build_cover_art(theme, (612.0, 792.0), image_path=tiny, dpi=60)
            self.assertEqual(art.source, "procedural")
            self.assertTrue(any("too small" in n for n in art.notes))
            art = build_cover_art(theme, (612.0, 792.0),
                                  image_path=os.path.join(tmp, "gone.jpg"), dpi=60)
            self.assertEqual(art.source, "procedural")
            self.assertTrue(any("not found" in n for n in art.notes))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_pexels_sourcing_is_opt_in_and_fails_closed_in_test_mode(self):
        tmp = tempfile.mkdtemp(prefix="planner_pexels_")
        try:
            os.environ["FLASK_EXPORTS_DIR"] = tmp
            result = build_planner_pdf(PlannerPdfRequest(
                planner_type=FAITH, pages=12, design_theme="warm_grace",
                cover_image_source="pexels", package_id="pexels_opt_in"))
            self.assertFalse(result.errors)
            self.assertEqual(result.layout_info["cover_image_source"], "procedural")
            self.assertTrue(any("Pexels cover photo not used" in w for w in result.warnings))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class ThemedPlannerRenderTests(unittest.TestCase):
    """Every theme produces a complete planner the Editor-in-Chief passes."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="planner_themes_")
        cls._prev = os.environ.get("FLASK_EXPORTS_DIR")
        cls.rendered = {}
        for key in FAITH_THEME_KEYS:
            cls.rendered[key] = _render(cls.tmp, design_theme=key, package_id=f"theme_{key}",
                                        title="Family Faith Planner", audience="For busy households")
        cls.rendered["ledger"] = _render(cls.tmp, planner_type=BUDGET, package_id="theme_ledger")

    @classmethod
    def tearDownClass(cls):
        if cls._prev is None:
            os.environ.pop("FLASK_EXPORTS_DIR", None)
        else:
            os.environ["FLASK_EXPORTS_DIR"] = cls._prev
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_theme_selection_reaches_the_pdf_and_the_package_metadata(self):
        for key, (result, _images, candidate) in self.rendered.items():
            with self.subTest(theme=key):
                self.assertEqual(result.plan.design_theme, key)
                self.assertEqual(result.layout_info["design_theme"], key)
                self.assertEqual(result.layout_info["design_theme_label"], THEMES[key].label)
                self.assertEqual(candidate["design_theme"], key)
                self.assertIn(result.layout_info["cover_style"], COVER_STYLES)
                self.assertEqual(result.layout_info["cover_image_source"], "procedural")
                self.assertGreaterEqual(result.layout_info["cover_image_dpi"], 150)

    def test_nothing_was_truncated_in_any_theme(self):
        for key, (result, _images, _candidate) in self.rendered.items():
            with self.subTest(theme=key):
                self.assertEqual(result.layout_info["render_notes"], [])

    def test_every_theme_passes_the_editor_in_chief(self):
        for key, (_result, _images, candidate) in self.rendered.items():
            with self.subTest(theme=key):
                report = review_planner(candidate)
                self.assertEqual(
                    report.verdict, VERDICT_PASS,
                    f"{key} blocked by {[(f.code, f.location, f.detail) for f in report.findings]}")
                for fi in report.findings:
                    self.assertTrue(fi.code.startswith("DESIGN_"), (key, fi.code, fi.detail))
                    self.assertEqual(fi.severity, "minor")
                self.assertEqual(report.evidence["design_quality"], "premium")
                # Painted covers are premium, never exceptional.
                self.assertIn(report.evidence["design_rating"], (8, 9), report.evidence["design_deductions"])
                for check in ("page_furniture", "print_safety", "render_notes",
                              "image_resolution", "theme_consistency", "design_richness"):
                    self.assertIn(check, report.checks_run)

    def test_cover_carries_title_subtitle_and_page_count_as_real_text(self):
        for key, (result, _images, candidate) in self.rendered.items():
            with self.subTest(theme=key):
                cover = candidate["page_texts"][0]
                self.assertIn(result.plan.title, cover)
                self.assertIn(result.plan.subtitle.split(",")[0], cover)
                self.assertIn(f"{result.plan.page_count} PAGES", cover)

    def test_every_interior_page_has_chrome_and_writing_room(self):
        from services.editor_in_chief import analyse_rendered_pages

        for key, (result, images, candidate) in self.rendered.items():
            with self.subTest(theme=key):
                stats = analyse_rendered_pages(images)["pages"]
                self.assertGreater(min(s["ink_pct"] for s in stats), 6.0)
                for i, foot in enumerate(candidate["footer_texts"][1:], start=2):
                    self.assertTrue(foot.split() and foot.split()[-1] == str(i),
                                    f"page {i} footer {foot!r}")

    def test_the_five_faith_themes_look_different_from_each_other(self):
        from PIL import Image

        from services.planner.themes import hex_to_rgb255

        # The tokens must differ, and the rendered covers must show it.
        keys = list(FAITH_THEME_KEYS)
        means = {}
        for key in keys:
            _result, images, _candidate = self.rendered[key]
            with Image.open(images[0]) as im:
                small = list(im.convert("RGB").resize((8, 8)).getdata())
            means[key] = small
        for a in range(len(keys)):
            for b in range(a + 1, len(keys)):
                ta, tb = THEMES[keys[a]], THEMES[keys[b]]
                token_dist = sum(abs(x - y) for x, y in zip(hex_to_rgb255(ta.primary), hex_to_rgb255(tb.primary)))
                token_dist += sum(abs(x - y) for x, y in zip(hex_to_rgb255(ta.cover_bg), hex_to_rgb255(tb.cover_bg)))
                self.assertGreater(token_dist, 60, f"{keys[a]} vs {keys[b]}: theme tokens too alike")
                px_dist = sum(sum(abs(p[c] - q[c]) for c in range(3))
                              for p, q in zip(means[keys[a]], means[keys[b]])) / 64.0
                self.assertGreater(px_dist, 12, f"{keys[a]} vs {keys[b]}: rendered covers too alike")


class DesignGateTests(unittest.TestCase):
    """The design checks must fail what they exist to catch."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="planner_gate_")
        cls._prev = os.environ.get("FLASK_EXPORTS_DIR")
        cls.result, cls.images, cls.candidate = _render(
            cls.tmp, design_theme="warm_grace", package_id="gate")

    @classmethod
    def tearDownClass(cls):
        if cls._prev is None:
            os.environ.pop("FLASK_EXPORTS_DIR", None)
        else:
            os.environ["FLASK_EXPORTS_DIR"] = cls._prev
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _codes(self, mutate):
        c = copy.deepcopy(self.candidate)
        mutate(c)
        report = review_planner(c)
        return [f.code for f in report.findings], report

    def test_a_missing_page_heading_is_blocked(self):
        def mutate(c):
            c["header_texts"][5] = "Something else entirely"
        codes, report = self._codes(mutate)
        self.assertIn("PLAN_HEADER_MISSING", codes)
        self.assertNotEqual(report.verdict, VERDICT_PASS)

    def test_a_wrong_page_number_is_blocked(self):
        def mutate(c):
            c["footer_texts"][7] = "FAMILY FAITH PLANNER 99"
        codes, report = self._codes(mutate)
        self.assertIn("PLAN_PAGE_NUMBER_WRONG", codes)
        self.assertNotEqual(report.verdict, VERDICT_PASS)

    def test_text_inside_the_trim_safe_margin_is_blocked(self):
        def mutate(c):
            w, h = c["page_rects"][4]
            c["text_boxes"][4].append((2.0, h / 2, 80.0, h / 2 + 10))
        codes, _report = self._codes(mutate)
        self.assertIn("PLAN_TEXT_NEAR_TRIM", codes)

    def test_text_running_off_the_page_is_critical(self):
        def mutate(c):
            w, h = c["page_rects"][4]
            c["text_boxes"][4].append((w - 20, 300.0, w + 40, 312.0))
        codes, report = self._codes(mutate)
        self.assertIn("PLAN_TEXT_CLIPPED", codes)
        self.assertNotEqual(report.verdict, VERDICT_PASS)

    def test_dropped_content_reported_by_the_renderer_is_blocked(self):
        codes, report = self._codes(
            lambda c: c.update(render_notes=["Prayer Log: 3 prose section(s) did not fit"]))
        self.assertIn("PLAN_CONTENT_TRUNCATED", codes)
        self.assertNotEqual(report.verdict, VERDICT_PASS)

    def test_a_flat_or_low_resolution_cover_is_blocked(self):
        codes, _r = self._codes(lambda c: c.update(cover_images=[]))
        self.assertIn("PLAN_COVER_FLAT", codes)
        codes, _r = self._codes(
            lambda c: c.update(cover_images=[{"px_w": 300, "px_h": 400, "pt_w": 612, "pt_h": 792}]))
        self.assertIn("PLAN_COVER_IMAGE_LOW_RES", codes)

    def test_pages_in_a_foreign_colour_are_reported_as_theme_drift(self):
        from PIL import Image

        # Paint page 6 teal-and-white: a hue Warm Grace does not own.
        with Image.open(self.images[5]) as im:
            w, h = im.size
            fake = Image.new("RGB", (w, h), (255, 255, 255))
            fake.paste(Image.new("RGB", (w, h // 3), (20, 140, 130)), (0, 0))
            path = os.path.join(self.tmp, "drift.png")
            fake.save(path)

        def mutate(c):
            c["page_images"] = list(c["page_images"])
            c["page_images"][5] = path
        codes, _r = self._codes(mutate)
        self.assertIn("PLAN_THEME_DRIFT", codes)

    def test_a_visually_plain_planner_is_flagged_as_needing_improvement(self):
        from PIL import Image, ImageDraw

        # Black text-like marks on white, no tint, no colour: a bare form.
        plain_paths = []
        with Image.open(self.images[5]) as im:
            w, h = im.size
        for k in range(len(self.images) - 1):
            fake = Image.new("RGB", (w, h), (255, 255, 255))
            d = ImageDraw.Draw(fake)
            for y in range(40, h - 40, 14):
                d.line([(40, y), (w - 40, y)], fill=(40, 40, 40), width=2)
            p = os.path.join(self.tmp, f"plain_{k}.png")
            fake.save(p)
            plain_paths.append(p)

        def mutate(c):
            c["page_images"] = [c["page_images"][0]] + plain_paths
        codes, report = self._codes(mutate)
        self.assertIn("PLAN_DESIGN_PLAIN", codes)
        self.assertEqual(report.evidence["design_quality"], "needs improvement")
        self.assertNotEqual(report.verdict, VERDICT_PASS)

    def test_direct_checks_return_nothing_on_the_real_artifact(self):
        c = self.candidate
        self.assertEqual(check_planner_page_furniture(
            c["page_kinds"], c["page_titles"], c["page_texts"], c["header_texts"],
            c["footer_texts"], c["title"]), [])
        self.assertEqual(check_planner_print_safety(c["page_kinds"], c["text_boxes"], c["page_rects"]), [])
        self.assertEqual(check_planner_render_notes(c["render_notes"]), [])
        self.assertEqual(check_planner_cover_artwork(c["page_kinds"], c["cover_images"]), [])
        self.assertEqual(check_planner_theme_consistency([], c["page_kinds"], "warm_grace"), [])
        self.assertEqual(check_planner_design_richness([], [], c["page_kinds"]), [])


class ProductWiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="planner_wire_")
        self._prev = os.environ.get("FLASK_EXPORTS_DIR")
        os.environ["FLASK_EXPORTS_DIR"] = self.tmp

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("FLASK_EXPORTS_DIR", None)
        else:
            os.environ["FLASK_EXPORTS_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_generate_product_honours_the_theme_and_cover_style_fields(self):
        from services.product import generate_product

        out = generate_product("faith_planner", {
            "pages": "24", "theme": "Family", "design_theme": "Floral Devotion",
            "cover_style": "Elegant minimal"})
        self.assertEqual(out["design_theme"], "floral_devotion")
        self.assertEqual(out["design_theme_label"], "Floral Devotion")
        self.assertEqual(out["cover_style"], "minimal_texture")
        self.assertEqual(out["fields"]["design_theme"], "floral_devotion")
        self.assertEqual(out["layout_info"]["design_theme"], "floral_devotion")
        self.assertEqual(out["title"], "Family Faith Planner")

    def test_the_builder_form_offers_the_themes_and_cover_styles(self):
        source = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        block = source.split('id: "faith_planner"', 1)[1].split('id: "budget_planner"', 1)[0]
        self.assertIn('name: "design_theme"', block)
        self.assertIn('name: "cover_style"', block)
        for label in ("Warm Grace", "Modern Minimal Faith", "Floral Devotion",
                      "Family Heritage", "Joyful Light"):
            self.assertIn(label, block)

    def test_the_budget_planner_keeps_its_house_theme_by_default(self):
        from services.product import generate_product

        out = generate_product("budget_planner", {"pages": "24"})
        self.assertEqual(out["design_theme"], "ledger")


if __name__ == "__main__":
    unittest.main()
