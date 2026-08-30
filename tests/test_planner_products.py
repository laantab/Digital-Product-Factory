"""Faith Planner and Budget Planner: build, render, and Editor-in-Chief gate.

The negative cases matter more than the positive ones here. A reviewer that
passes a good planner but cannot fail a bad one is worse than no reviewer,
because it produces a verdict people trust. Every blocking rule in
`editor_in_chief_planner` therefore has a test that breaks the artifact and
asserts the block.
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
import tempfile
import unittest

import fitz

from services.editor_in_chief import VERDICT_PASS
from services.editor_in_chief_planner import (
    PLANNER_CATEGORIES,
    REVIEWER_ID,
    collect_planner_candidate,
    review_planner,
)
from services.planner import (
    BUDGET,
    FAITH,
    PlannerPdfRequest,
    PlannerRequest,
    build_planner_pdf,
    build_planner_plan,
    clamp_pages,
    toc_entries,
)

PLANNERS = (FAITH, BUDGET)


class PlannerPlanTests(unittest.TestCase):
    """The page plan is deterministic and structurally complete."""

    def test_same_request_produces_the_same_plan(self):
        for pt in PLANNERS:
            with self.subTest(planner=pt):
                a = build_planner_plan(PlannerRequest(planner_type=pt, pages=60))
                b = build_planner_plan(PlannerRequest(planner_type=pt, pages=60))
                self.assertEqual(
                    [(p.kind, p.title) for p in a.pages],
                    [(p.kind, p.title) for p in b.pages],
                )

    def test_unknown_planner_type_is_rejected(self):
        with self.assertRaises(ValueError):
            build_planner_plan(PlannerRequest(planner_type="astrology_planner"))

    def test_page_count_is_clamped_to_a_sane_range(self):
        self.assertEqual(clamp_pages(2, FAITH), 12)
        self.assertEqual(clamp_pages(9999, FAITH), 200)
        self.assertEqual(clamp_pages("not a number", BUDGET), 60)
        self.assertEqual(clamp_pages("48", BUDGET), 48)

    def test_plan_contains_cover_contents_and_working_pages(self):
        for pt in PLANNERS:
            with self.subTest(planner=pt):
                plan = build_planner_plan(PlannerRequest(planner_type=pt, pages=60))
                kinds = [p.kind for p in plan.pages]
                self.assertEqual(kinds[0], "cover")
                self.assertIn("toc", kinds)
                self.assertIn("prose", kinds)
                self.assertTrue(
                    set(kinds) & {"open_table", "labeled_table", "faith_daily"},
                    "planner must contain pages the customer can write on",
                )

    def test_cover_advertises_the_real_page_count(self):
        for pt in PLANNERS:
            for requested in (24, 60, 90):
                with self.subTest(planner=pt, pages=requested):
                    plan = build_planner_plan(
                        PlannerRequest(planner_type=pt, pages=requested))
                    caption = plan.pages[0].spec.get("caption") or ""
                    claimed = int(re.search(r"(\d+)\s*PAGES", caption).group(1))
                    self.assertEqual(claimed, len(plan.pages))

    def test_contents_entries_point_inside_the_book(self):
        for pt in PLANNERS:
            with self.subTest(planner=pt):
                plan = build_planner_plan(PlannerRequest(planner_type=pt, pages=60))
                entries = toc_entries(plan.pages)
                self.assertTrue(entries)
                for _label, number in entries:
                    self.assertGreaterEqual(number, 1)
                    self.assertLessEqual(number, len(plan.pages))

    def test_cover_can_be_switched_off(self):
        plan = build_planner_plan(
            PlannerRequest(planner_type=FAITH, pages=40, include_cover=False))
        self.assertNotIn("cover", [p.kind for p in plan.pages])

    def test_budget_planner_carries_a_not_advice_statement(self):
        plan = build_planner_plan(PlannerRequest(planner_type=BUDGET, pages=60))
        front = " ".join(
            str(p.spec.get("disclaimer") or "") for p in plan.pages[:4]
        ).lower()
        self.assertIn("does not provide personalised financial", front)
        self.assertIn("qualified professional", front)


class _RenderedPlanner:
    """Build one planner and render its pages once, for reuse across tests."""

    def __init__(self, planner_type: str, exports_dir: str, pages: int = 60):
        os.environ["FLASK_EXPORTS_DIR"] = exports_dir
        import importlib

        import services.planner.pdf_builder as pb

        importlib.reload(pb)
        self.result = pb.build_planner_pdf(pb.PlannerPdfRequest(
            planner_type=planner_type, pages=pages,
            author="Digital Product Factory",
            package_id=f"test_{planner_type}",
        ))
        assert not self.result.errors, self.result.errors
        self.page_dir = os.path.join(exports_dir, f"pages_{planner_type}")
        os.makedirs(self.page_dir, exist_ok=True)
        self.images: list[str] = []
        doc = fitz.open(self.result.pdf_path)
        for i, page in enumerate(doc):
            path = os.path.join(self.page_dir, f"p{i + 1:03d}.png")
            page.get_pixmap(dpi=72).save(path)
            self.images.append(path)
        doc.close()
        self.candidate = collect_planner_candidate(
            self.result.plan, pdf_path=self.result.pdf_path,
            package_dir=self.result.package_dir, page_images=self.images,
            author="Digital Product Factory",
        )


class PlannerPdfTests(unittest.TestCase):
    """The rendered PDF matches what the plan promised."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="planner_pdf_")
        cls._prev_exports = os.environ.get("FLASK_EXPORTS_DIR")
        cls.rendered = {pt: _RenderedPlanner(pt, cls.tmp) for pt in PLANNERS}

    @classmethod
    def tearDownClass(cls):
        if cls._prev_exports is None:
            os.environ.pop("FLASK_EXPORTS_DIR", None)
        else:
            os.environ["FLASK_EXPORTS_DIR"] = cls._prev_exports
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_pdf_page_count_matches_the_plan(self):
        for pt, r in self.rendered.items():
            with self.subTest(planner=pt):
                self.assertEqual(r.candidate["pdf_pages"], r.result.plan.page_count)

    def test_pdf_metadata_carries_the_title(self):
        for pt, r in self.rendered.items():
            with self.subTest(planner=pt):
                self.assertEqual(
                    r.candidate["pdf_meta"]["Title"], r.result.plan.title)

    def test_no_page_is_blank_or_nearly_blank(self):
        from services.editor_in_chief import analyse_rendered_pages

        for pt, r in self.rendered.items():
            with self.subTest(planner=pt):
                stats = analyse_rendered_pages(r.images)["pages"]
                self.assertEqual(len(stats), r.result.plan.page_count)
                worst = min(s["ink_pct"] for s in stats)
                self.assertGreater(
                    worst, 6.0,
                    f"{pt} has a page at {worst}% ink; planner pages must not "
                    "render as empty sheets",
                )

    def test_cover_reaches_the_trim_edge(self):
        from services.editor_in_chief import check_cover_page

        for pt, r in self.rendered.items():
            with self.subTest(planner=pt):
                self.assertEqual(check_cover_page(r.images[0]), [])

    def test_no_placeholder_text_reaches_the_customer(self):
        for pt, r in self.rendered.items():
            with self.subTest(planner=pt):
                blob = r.candidate["full_text"].lower()
                for bad in ("lorem ipsum", "todo", "tbd", "placeholder",
                            "coming soon", "your name here"):
                    self.assertNotIn(bad, blob)


class PlannerEditorInChiefTests(unittest.TestCase):
    """The gate passes a good planner and blocks each way it can go wrong."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="planner_eic_")
        cls._prev_exports = os.environ.get("FLASK_EXPORTS_DIR")
        cls.rendered = {pt: _RenderedPlanner(pt, cls.tmp) for pt in PLANNERS}

    @classmethod
    def tearDownClass(cls):
        if cls._prev_exports is None:
            os.environ.pop("FLASK_EXPORTS_DIR", None)
        else:
            os.environ["FLASK_EXPORTS_DIR"] = cls._prev_exports
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def _review(self, planner_type: str, mutate=None):
        candidate = copy.deepcopy(self.rendered[planner_type].candidate)
        if mutate is not None:
            mutate(candidate)
        return review_planner(candidate)

    # -- positive ---------------------------------------------------------
    def test_shipped_planners_pass(self):
        for pt in PLANNERS:
            with self.subTest(planner=pt):
                report = self._review(pt)
                self.assertEqual(
                    report.verdict, VERDICT_PASS,
                    f"{pt} blocked by {[f.code for f in report.findings]}")
                self.assertEqual(report.findings, [])
                self.assertGreaterEqual(report.overall, 9.0)

    def test_only_applicable_categories_are_scored(self):
        report = self._review(FAITH)
        self.assertEqual(sorted(report.scores), sorted(PLANNER_CATEGORIES))
        # Categories with nothing to measure must be absent, not scored 10.
        self.assertNotIn("image_resolution", report.scores)
        self.assertNotIn("visual_quality", report.scores)

    def test_skipped_checks_are_declared_with_a_reason(self):
        report = self._review(BUDGET)
        for key in ("image_resolution", "photo_cover_verification",
                    "external_plagiarism", "accessibility"):
            self.assertIn(key, report.checks_skipped)
            self.assertTrue(report.checks_skipped[key].strip())

    def test_repeated_worksheet_pages_are_not_reported_as_duplication(self):
        # Seven identical monthly expense-log pages is the design, not a defect.
        report = self._review(BUDGET)
        self.assertNotIn(
            "ORIG_DUP_PARAGRAPH", [f.code for f in report.findings])
        self.assertIn("worksheet_self_duplication", report.checks_skipped)

    def test_producer_may_not_review_its_own_output(self):
        from services.editor_in_chief import SelfApprovalError

        candidate = copy.deepcopy(self.rendered[FAITH].candidate)
        # The default producer is a different component, so this is fine.
        self.assertEqual(review_planner(candidate).verdict, VERDICT_PASS)
        # Naming the reviewer as the producer is self-approval, and is refused.
        with self.assertRaises(SelfApprovalError):
            review_planner(candidate, produced_by=REVIEWER_ID)

    # -- negative ---------------------------------------------------------
    def _assert_blocked(self, planner_type, mutate, expected_code):
        report = self._review(planner_type, mutate)
        codes = [f.code for f in report.findings]
        self.assertIn(expected_code, codes)
        self.assertNotEqual(report.verdict, VERDICT_PASS)

    def test_blank_forms_with_no_instruction_are_blocked(self):
        self._assert_blocked(
            FAITH,
            lambda c: c.update(prose_sections=[], prose_pages=[]),
            "PLAN_NO_INSTRUCTION")

    def test_money_planner_without_a_disclaimer_is_blocked(self):
        def strip(c):
            c["page_texts"] = [
                t.replace("does not provide personalised financial",
                          "tells you what to do with")
                for t in c["page_texts"]
            ]

        self._assert_blocked(BUDGET, strip, "PLAN_NO_ADVICE_DISCLAIMER")

    def test_cover_claiming_the_wrong_page_count_is_blocked(self):
        def lie(c):
            c["page_texts"][0] = c["page_texts"][0].replace("60 PAGES", "180 PAGES")

        self._assert_blocked(FAITH, lie, "PLAN_COVER_PAGE_CLAIM")

    def test_contents_entry_past_the_end_is_blocked(self):
        self._assert_blocked(
            BUDGET,
            lambda c: c.update(toc=c["toc"][:1] + [("Nowhere", 9999)]),
            "PLAN_TOC_OUT_OF_RANGE")

    def test_contents_entry_pointing_at_the_wrong_page_is_blocked(self):
        self._assert_blocked(
            BUDGET,
            lambda c: c.update(toc=[(c["toc"][0][0], 7)]),
            "PLAN_TOC_MISMATCH")

    def test_planner_with_no_worksheet_pages_is_blocked(self):
        self._assert_blocked(
            FAITH,
            lambda c: c.update(page_kinds=["cover", "toc", "prose"]),
            "PLAN_NO_WORKING_PAGES")

    def test_placeholder_leak_is_blocked(self):
        self._assert_blocked(
            FAITH,
            lambda c: c.update(full_text=c["full_text"] + "\n\nTODO finish this"),
            "EDIT_PLACEHOLDER")

    def test_missing_registered_pdf_is_blocked(self):
        self._assert_blocked(
            BUDGET,
            lambda c: c.update(pdf_path=os.path.join(self.tmp, "gone.pdf")),
            "PKG_PDF_MISSING")

    def test_page_count_drift_between_plan_and_pdf_is_blocked(self):
        self._assert_blocked(
            FAITH,
            lambda c: c.update(pdf_pages=41),
            "META_PAGECOUNT_MISMATCH")


class PlannerFactoryWiringTests(unittest.TestCase):
    """The planners are reachable as real Factory product types."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="planner_wiring_")
        self._prev = os.environ.get("FLASK_EXPORTS_DIR")
        os.environ["FLASK_EXPORTS_DIR"] = self.tmp

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("FLASK_EXPORTS_DIR", None)
        else:
            os.environ["FLASK_EXPORTS_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_generate_product_builds_both_planners(self):
        from services.product import PRODUCT_LABELS, generate_product

        for pt, label in (("faith_planner", "Faith Planner"),
                          ("budget_planner", "Budget Planner")):
            with self.subTest(planner=pt):
                self.assertEqual(PRODUCT_LABELS[pt], label)
                out = generate_product(pt, {"pages": "36", "page_size": "US Letter"})
                self.assertTrue(out["is_pdf"])
                self.assertEqual(out["product_type"], pt)
                self.assertEqual(out["product_label"], label)
                self.assertTrue(out["pdf_bytes"])
                self.assertEqual(out["declared_pages"], out["layout_info"]["total_pages"])

    def test_theme_becomes_part_of_the_title(self):
        from services.product import generate_product

        out = generate_product("faith_planner", {"theme": "Family", "pages": "24"})
        self.assertEqual(out["title"], "Family Faith Planner")

    def test_planners_are_not_in_the_hidden_product_set(self):
        import app as flask_app

        source = open(flask_app.__file__, encoding="utf-8").read()
        hidden_block = source.split("_HIDDEN_PRODUCT_TYPES = {", 1)[1].split("}", 1)[0]
        self.assertNotIn("faith_planner", hidden_block)
        self.assertNotIn("budget_planner", hidden_block)

    def test_cover_is_allowed_for_a_full_length_planner(self):
        from services.quality.cover_eligibility_agent import determine_cover_eligibility

        for pt in ("faith_planner", "budget_planner"):
            with self.subTest(planner=pt):
                ok = determine_cover_eligibility(
                    product_type=pt, fields={}, planned_page_count=60,
                    product_mode="book")
                self.assertTrue(ok.cover_allowed)
                self.assertNotIn("Unknown product type", ok.reason)
                thin = determine_cover_eligibility(
                    product_type=pt, fields={}, planned_page_count=3,
                    product_mode="book")
                self.assertFalse(thin.cover_allowed)

    def test_market_advantage_routes_planner_requests_to_the_new_builders(self):
        from services.factory_advantage import resolve_factory_builder

        self.assertEqual(
            resolve_factory_builder("Faith Planner"),
            {"status": "active", "factory_id": "faith_planner", "label": "Faith Planner"})
        self.assertEqual(
            resolve_factory_builder("Budget Planner"),
            {"status": "active", "factory_id": "budget_planner", "label": "Budget Planner"})
        # The generic planner stays hidden.
        self.assertEqual(resolve_factory_builder("Planner")["status"], "hidden")

    def test_product_picker_lists_both_planners(self):
        js_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "static", "js", "app.js")
        source = open(js_path, encoding="utf-8").read()
        for pid in ('id: "faith_planner"', 'id: "budget_planner"'):
            self.assertIn(pid, source)
        # Neither may carry the hidden flag that keeps a type out of the picker.
        for pid in ("faith_planner", "budget_planner"):
            block = source.split(f'id: "{pid}"', 1)[1].split("fields:", 1)[0]
            self.assertNotIn("hidden: true", block)


class PlannerExportPackageTests(unittest.TestCase):
    """The customer must receive the planner, not a generic fallback.

    Regression: `build_product_export` had no planner branch, so the generic
    ebook path rendered a PDF from `data["content"]` — which a planner
    deliberately leaves empty — and the download pointer landed on a near-blank
    `ebook.pdf`. The Editor-in-Chief caught it as a page-count mismatch; these
    tests keep it caught at the packaging layer.
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="planner_pkg_")
        self._prev = os.environ.get("FLASK_EXPORTS_DIR")
        os.environ["FLASK_EXPORTS_DIR"] = self.tmp

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("FLASK_EXPORTS_DIR", None)
        else:
            os.environ["FLASK_EXPORTS_DIR"] = self._prev
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _export(self, planner_type: str):
        from services.packaging import EXPORTS_DIR, build_product_export
        from services.product import generate_product

        data = generate_product(planner_type, {"pages": "24", "author": "Pkg Test"})
        project = {"id": 1, "name": data["title"], "type": "product", "data": data}
        result = build_product_export(project)
        return data, result, EXPORTS_DIR

    def test_the_package_carries_the_planner_pdf(self):
        for pt in ("faith_planner", "budget_planner"):
            with self.subTest(planner=pt):
                data, result, exports_dir = self._export(pt)
                pdf = (result["exports"]["files"] or {})["pdf"]
                self.assertTrue(pdf["url"].endswith(data["filename"]))
                path = os.path.join(
                    exports_dir, result["package_id"], data["filename"])
                self.assertTrue(os.path.isfile(path))
                with fitz.open(path) as doc:
                    self.assertEqual(doc.page_count, data["declared_pages"])

    def test_the_package_never_falls_back_to_ebook_files(self):
        for pt in ("faith_planner", "budget_planner"):
            with self.subTest(planner=pt):
                _data, result, exports_dir = self._export(pt)
                names = set(os.listdir(
                    os.path.join(exports_dir, result["package_id"])))
                self.assertFalse(names & {"ebook.pdf", "ebook.html", "ebook.txt"})

    def test_packaging_does_not_mutate_project_data(self):
        # Mutating `data` here trips the artifact-immutability guard on the
        # save that follows, which failed the whole export with a confusing
        # "cannot rewrite asset_manifest_digest" error.
        from services.packaging import build_product_export
        from services.product import generate_product

        data = generate_product("faith_planner", {"pages": "24"})
        before = dict(data)
        project = {"id": 1, "name": data["title"], "type": "product", "data": data}
        build_product_export(project)
        for key in ("pdf_path", "_pdf_path", "package_id"):
            self.assertEqual(
                data.get(key), before.get(key),
                f"packaging must not rewrite data[{key!r}]")

    def test_the_zip_includes_printing_guidance_and_metadata(self):
        import zipfile

        _data, result, exports_dir = self._export("budget_planner")
        zip_path = os.path.join(exports_dir, result["package_id"], "package.zip")
        self.assertTrue(os.path.isfile(zip_path))
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            self.assertIn("metadata.json", names)
            self.assertIn("PRINTING.txt", names)
            meta = json.loads(zf.read("metadata.json"))
        self.assertEqual(meta["product_type"], "budget_planner")
        self.assertEqual(meta["render_engine"], "planner_direct")


if __name__ == "__main__":
    unittest.main()
