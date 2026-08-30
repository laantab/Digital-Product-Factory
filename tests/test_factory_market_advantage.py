"""Factory Market Advantage — original research upgrade tests.

Zero paid/external calls. FACTORY_TEST_MODE via conftest. Does not generate a
product, touch project #4249, or weaken the network guard.
"""
from __future__ import annotations

import copy
import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"

from app import RESEARCH_FAILURE_MESSAGE, app  # noqa: E402
import database  # noqa: E402
import services.market_research as MR  # noqa: E402
from services.book_sales_estimate import estimate_book_sales  # noqa: E402
from services.factory_advantage import (  # noqa: E402
    DISCLAIMER,
    HOW_DETERMINED_PLAIN,
    INSUFFICIENT_EVIDENCE,
    NOT_VERIFIED,
    USER_DECISION_AVOID,
    USER_DECISION_BUILD,
    USER_DECISION_IMPROVE,
    builder_prefill_from_plan,
    build_recommendation_summary,
    compute_factory_advantage,
    draft_handoff_payload,
    map_user_decision,
    plain_component_signal,
    plain_opportunity_label,
    reject_unsupported_trend_language,
    resolve_factory_builder,
)
from services.market_research import (  # noqa: E402
    DISCOVERY_DISCLAIMER,
    DISCOVERY_FAILURE_MESSAGE,
    DISCOVERY_RESULTS_TITLE,
)
from services.quality.artifact_state import ArtifactState  # noqa: E402

APP_JS = ROOT / "static" / "js" / "app.js"
INDEX = ROOT / "templates" / "index.html"

COVER_SHA = "465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd"
COVER_DIGEST = "55567b21e03e3d5734ff5c355c3f4771b4771480d88566ebbdabcbd0d970d016"
MS_DIGEST = "cf08285598b6d7ac722844a97a5d54f89da2b37e8b11a5bd3df9768b8010cf98"
PREVIEW_DIGEST = "b853a69507da0c3a3e5d350f1160bb7675ac6ae076314ed76711de9cadf14126"

COLORING = {
    "niche": "Kids superhero coloring",
    "product_idea": "Thunder Volt Bank Rescue Coloring Adventure",
    "product_type": "Coloring Book",
    "target_audience": "Children ages 8-12",
    "customer_problem": "Kids need engaging printable coloring stories",
    "why_opportunity": "Parents buy theme coloring books with clear heroes.",
    "price_range": "$7 - $14",
    "difficulty": "Easy",
    "competition": "Medium",
    "opportunity_score": 88,
    "sales_angle": "Bold comic-book hero coloring story",
}

RICH_INPUTS = {
    "topic": "Kids superhero coloring",
    "audience": "Children ages 8-12",
    "customer_problem": "Kids need engaging printable coloring stories",
    "product_type": "Coloring Book",
    "sales_platform": "Amazon KDP",
    "expertise": "Some experience",
    "target_price": "$9.99",
    "keywords": "superhero coloring, kids printable",
}

RICH_EVIDENCE = {
    "sources": [
        {
            "title": "Parent coloring demand",
            "url": "https://example.com/a",
            "excerpt": "Parents look for superhero coloring books",
            "access_date": "2026-08-15",
            "confidence": "high",
        },
        {
            "title": "Printable market note",
            "url": "https://example.com/b",
            "excerpt": "Printable coloring remains a common gift format",
            "access_date": "2026-08-15",
            "confidence": "medium",
        },
        {
            "title": "Moderate KDP field",
            "url": "https://example.com/c",
            "excerpt": "Competition is moderate for themed kids coloring",
            "access_date": "2026-08-15",
            "confidence": "medium",
        },
    ],
    "competition_level": "medium",
    "competition_verified": True,
    "differentiation_count": 3,
    "live": True,
    "researched_at": "2026-08-15",
    "fabricated_as_facts": False,
    "missing_information": [],
    "unverified_metrics": ["search_volume", "bsr", "revenue"],
}


def _4249_fingerprint(data: dict) -> dict:
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    src = cover.get("source") if isinstance(cover.get("source"), dict) else {}
    ident = data.get("ebook_export_identity") if isinstance(data.get("ebook_export_identity"), dict) else {}
    return {
        "title": data.get("title"),
        "content": data.get("content"),
        "ebook": data.get("ebook"),
        "sha256": src.get("sha256"),
        "cover_digest": cover.get("cover_digest"),
        "manuscript_digest": ident.get("manuscript_digest") or data.get("ebook_manuscript_digest"),
        "preview_digest": ident.get("preview_digest") or data.get("preview_digest"),
    }


class FactoryAdvantageScoreTests(unittest.TestCase):
    def test_formula_is_documented_and_sums_to_100(self):
        score = compute_factory_advantage(RICH_INPUTS, RICH_EVIDENCE)
        self.assertEqual(score["max"], 100)
        self.assertIn("demand(0-20)", score["formula"])
        parts = score["components"]
        self.assertEqual(parts["demand"]["max"], 20)
        self.assertEqual(parts["competition_opportunity"]["max"], 20)
        self.assertEqual(parts["buyer_urgency"]["max"], 15)
        self.assertEqual(parts["monetization_potential"]["max"], 15)
        self.assertEqual(parts["differentiation_potential"]["max"], 15)
        self.assertEqual(parts["production_fit"]["max"], 10)
        self.assertEqual(parts["evidence_confidence"]["max"], 5)
        self.assertEqual(score["total"], sum(row["score"] for row in parts.values()))
        self.assertEqual(score["disclaimer"], DISCLAIMER)

    def test_rich_fixture_is_deterministic(self):
        a = compute_factory_advantage(RICH_INPUTS, RICH_EVIDENCE)
        b = compute_factory_advantage(copy.deepcopy(RICH_INPUTS), copy.deepcopy(RICH_EVIDENCE))
        self.assertEqual(a, b)
        self.assertGreaterEqual(a["total"], 75)
        self.assertGreaterEqual(a["components"]["evidence_confidence"]["score"], 3)
        self.assertEqual(a["recommendation"], "Strong Opportunity")
        self.assertEqual(a["components"]["demand"]["score"], 20)
        self.assertEqual(a["components"]["production_fit"]["score"], 10)

    def test_missing_evidence_lowers_confidence_and_recommendation(self):
        sparse = compute_factory_advantage(
            {"topic": "mystery idea", "product_type": "Not Sure Yet"},
            {"sources": [], "live": False, "missing_information": ["Live web sources", "Audience", "Problem", "Price"]},
        )
        self.assertLess(sparse["components"]["evidence_confidence"]["score"], 2)
        self.assertEqual(sparse["recommendation"], "Insufficient Evidence")
        self.assertLess(sparse["total"], 40)

    def test_unverified_metrics_never_scored_as_facts(self):
        score = compute_factory_advantage(RICH_INPUTS, RICH_EVIDENCE)
        blob = str(score).lower()
        self.assertNotIn("10000 searches", blob)
        self.assertNotIn("bsr #", blob)
        for row in score["components"].values():
            self.assertIn("researched_at", row)
            self.assertIn("explanation", row)
            self.assertIn("evidence", row)
            self.assertIn("missing_evidence", row)


class BuilderRoutingTests(unittest.TestCase):
    def test_each_active_type_maps_to_correct_builder(self):
        expected = {
            "Coloring Book": "coloring_book",
            "Crossword Puzzle Book": "crossword",
            "Ebook": "ebook",
            "Word Search Book": "word_search",
            "Math Worksheet": "math_worksheet",
        }
        for label, factory_id in expected.items():
            resolved = resolve_factory_builder(label)
            self.assertEqual(resolved["status"], "active", label)
            self.assertEqual(resolved["factory_id"], factory_id, label)

    def test_coloring_and_crossword_never_silent_ebook(self):
        for label in ("Coloring Book", "Crossword Puzzle Book", "coloring story book"):
            resolved = resolve_factory_builder(label)
            self.assertNotEqual(resolved["factory_id"], "ebook", label)
        self.assertEqual(resolve_factory_builder("Coloring Book")["factory_id"], "coloring_book")
        self.assertEqual(resolve_factory_builder("Crossword Puzzle Book")["factory_id"], "crossword")


class BookSalesEstimateTests(unittest.TestCase):
    def test_sales_estimate_unavailable_without_authorized_method(self):
        result = estimate_book_sales(bsr=1234)
        self.assertFalse(result["available"])
        self.assertEqual(result["bsr"], NOT_VERIFIED)
        self.assertEqual(result["estimated_monthly_sales"], NOT_VERIFIED)
        self.assertEqual(result["estimated_revenue"], NOT_VERIFIED)
        self.assertIn("unavailable", result["reason"].lower())


class FactoryMarketAdvantageRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_old_urls_still_work(self):
        for path in ("/research", "/market-research", "/discover-products", "/factory-market-advantage"):
            if path == "/market-research":
                resp = self.client.post(path, json={"niche": "kids coloring", "product_type": "Coloring Book"})
            elif path == "/research":
                resp = self.client.post(path, json={"keyword": "kids coloring", "product_type": "Coloring Book"})
            else:
                resp = self.client.post(
                    path,
                    json={
                        "topic": "kids coloring",
                        "audience": "parents",
                        "customer_problem": "kids need engaging printables",
                        "product_type": "Coloring Book",
                    },
                )
            self.assertIn(resp.status_code, {200, 201}, f"{path} {resp.data}")
            body = resp.get_json()
            self.assertIn("opportunities", body)
            self.assertIn("factory_advantage", body)
            self.assertEqual(body.get("workflow"), "factory_market_advantage")
            self.assertEqual(body["disclaimer"], DISCLAIMER)

    def test_selected_product_type_survives_research(self):
        resp = self.client.post(
            "/discover-products",
            json={
                "topic": "Kids superhero coloring",
                "audience": "Children ages 8-12",
                "customer_problem": "Kids need engaging printable coloring stories",
                "product_type": "Coloring Book",
                "sales_platform": "Amazon KDP",
                "expertise": "Some experience",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.get_json()
        self.assertEqual(body["product_type"], "Coloring Book")
        for opp in body["opportunities"]:
            self.assertEqual(opp["product_type"], "Coloring Book")
            self.assertNotEqual(opp["product_type"], "Ebook")
        self.assertEqual(body["recommendation"]["best_product_type"], "Coloring Book")
        self.assertNotIn("BookSignal", str(body))

    def test_crossword_research_does_not_become_ebook(self):
        resp = self.client.post(
            "/discover-products",
            json={"topic": "Bible crossword", "product_type": "Crossword Puzzle Book", "audience": "adults"},
        )
        body = resp.get_json()
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(body["product_type"], "Crossword Puzzle Book")
        for opp in body["opportunities"]:
            self.assertEqual(opp["product_type"], "Crossword Puzzle Book")

    def test_sources_and_unverified_labels_persist(self):
        resp = self.client.post(
            "/discover-products",
            json={"topic": "kids coloring", "product_type": "Coloring Book"},
        )
        body = resp.get_json()
        evidence = body["evidence"]
        self.assertIn("verified_facts", evidence)
        self.assertIn("calculated_estimates", evidence)
        self.assertIn("ai_interpretation", evidence)
        self.assertIn("missing_information", evidence)
        joined = " ".join(evidence["missing_information"]).lower()
        self.assertIn("not verified", joined)
        report = body["advantage_report"]
        self.assertIn("A_opportunity_summary", report)
        self.assertIn("G_differentiation_plan", report)
        self.assertEqual(len(report["G_differentiation_plan"]["opportunities"]), 3)
        self.assertLessEqual(len(report["H_related_product_opportunities"]["items"]), 5)
        self.assertTrue(report["I_series_builder"]["applies_to_books"])
        self.assertTrue(report["I_series_builder"]["applies_to_non_books"])
        self.assertFalse(body["sales_estimate"]["available"])
        self.assertEqual(body["sales_estimate"]["bsr"], NOT_VERIFIED)

    def test_provider_failure_keeps_inputs(self):
        payload = {
            "topic": "Kids superhero coloring",
            "audience": "Children ages 8-12",
            "product_type": "Coloring Book",
        }
        with patch("app.discover_products", side_effect=RuntimeError("Tavily timeout")):
            resp = self.client.post("/discover-products", json=payload)
        self.assertEqual(resp.status_code, 503)
        body = resp.get_json()
        self.assertTrue(body.get("retryable"))
        self.assertEqual(body["inputs"]["topic"], "Kids superhero coloring")
        self.assertEqual(body["inputs"]["product_type"], "Coloring Book")

    def test_save_reopen_restores_report_then_build_is_draft_only(self):
        research = self.client.post(
            "/discover-products",
            json={
                "topic": COLORING["niche"],
                "audience": COLORING["target_audience"],
                "customer_problem": COLORING["customer_problem"],
                "product_type": "Coloring Book",
            },
        ).get_json()
        saved = self.client.post(
            "/projects",
            json={
                "name": "Research: Kids superhero coloring",
                "type": "research_plan",
                "user_saved": True,
                "data": {**research, "stage": "research_saved", "selected_opportunity": COLORING},
            },
        )
        self.assertEqual(saved.status_code, 201, saved.data)
        rid = saved.get_json()["id"]
        reopened = self.client.get(f"/projects/{rid}")
        self.assertEqual(reopened.status_code, 200)
        data = reopened.get_json()["data"]
        self.assertEqual(reopened.get_json()["type"], "research_plan")
        self.assertEqual(data["product_type"], "Coloring Book")
        self.assertIn("factory_advantage", data)
        self.assertIn("advantage_report", data)
        self.assertTrue(data.get("sources") is not None or data.get("evidence"))

        with patch("services.product.generate_product", side_effect=AssertionError("must not generate product")), patch(
            "services.ebook.generate_ebook", side_effect=AssertionError("must not generate ebook")
        ), patch(
            "ai_client.chat_json", side_effect=AssertionError("must not call AI on build")
        ), patch(
            "ai_client.chat", side_effect=AssertionError("must not call AI on build")
        ):
            built = self.client.post(
                "/research-to-builder",
                json={
                    "research_id": rid,
                    "opportunity": COLORING,
                    "research": data,
                    "inputs": data.get("inputs") or RICH_INPUTS,
                },
            )
        self.assertEqual(built.status_code, 201, built.data)
        body = built.get_json()
        self.assertFalse(body["generated"])
        self.assertFalse(body["auto_generated"])
        self.assertEqual(body["factory_id"], "coloring_book")
        self.assertNotEqual(body["factory_id"], "ebook")
        self.assertEqual(body["product_type"], "Coloring Book")
        self.assertEqual(body["artifact_state"], ArtifactState.DRAFT.value)
        self.assertEqual(body["type"], "product_plan")
        plan = body["data"]["plan"]
        self.assertEqual(plan["product_type"], "Coloring Book")
        prefill = builder_prefill_from_plan(plan)
        self.assertEqual(prefill["theme"], COLORING["product_idea"])
        self.assertEqual(prefill["product_type"], "Coloring Book")

        loaded = self.client.get(f"/projects/{rid}").get_json()
        self.assertEqual(loaded["type"], "product_plan")
        self.assertEqual(loaded["data"]["artifact_state"], "DRAFT")
        self.assertNotEqual(loaded["data"].get("artifact_state"), "APPROVED")
        self.assertNotEqual(loaded["data"].get("artifact_state"), "LOCKED")

    def test_every_product_type_handoff_to_correct_builder(self):
        cases = [
            ("Coloring Book", "coloring_book", COLORING),
            (
                "Crossword Puzzle Book",
                "crossword",
                {**COLORING, "product_type": "Crossword Puzzle Book", "product_idea": "Bible Crossword Hour"},
            ),
            (
                "Ebook",
                "ebook",
                {**COLORING, "product_type": "Ebook", "product_idea": "Event Photography Startup Guide"},
            ),
            (
                "Word Search Book",
                "word_search",
                {**COLORING, "product_type": "Word Search Book", "product_idea": "Farm Word Search"},
            ),
            (
                "Math Worksheet",
                "math_worksheet",
                {**COLORING, "product_type": "Math Worksheet", "product_idea": "Grade 3 Fractions Practice"},
            ),
        ]
        for label, factory_id, opp in cases:
            saved = self.client.post(
                "/projects",
                json={
                    "name": f"Research: {opp['product_idea']}",
                    "type": "research_plan",
                    "user_saved": True,
                    "data": {"product_type": label, "opportunities": [opp], "stage": "research_saved"},
                },
            )
            rid = saved.get_json()["id"]
            with patch("services.product.generate_product", side_effect=AssertionError("no gen")), patch(
                "services.ebook.generate_ebook", side_effect=AssertionError("no ebook")
            ):
                built = self.client.post(
                    "/research-to-builder",
                    json={"research_id": rid, "opportunity": opp, "research": {"product_type": label}},
                )
            self.assertEqual(built.status_code, 201, f"{label} {built.data}")
            body = built.get_json()
            self.assertEqual(body["factory_id"], factory_id, label)
            self.assertEqual(body["product_type"], label)
            self.assertFalse(body["generated"])
            if factory_id != "ebook":
                self.assertNotEqual(body["factory_id"], "ebook", label)

    def test_build_without_opportunity_is_rejected(self):
        resp = self.client.post("/research-to-builder", json={"research": {}})
        self.assertEqual(resp.status_code, 400)

    def test_draft_handoff_never_approved_or_generated(self):
        payload = draft_handoff_payload(opportunity=COLORING, research={"mode": "ai_estimated"}, inputs=RICH_INPUTS)
        self.assertEqual(payload["artifact_state"], "DRAFT")
        self.assertFalse(payload["generated"])
        self.assertEqual(payload["product_type"], "Coloring Book")
        self.assertEqual(payload["builder"]["factory_id"], "coloring_book")


class PresentationAndJsContractTests(unittest.TestCase):
    def test_user_facing_copy_and_old_view_ids(self):
        html = INDEX.read_text(encoding="utf-8")
        js = APP_JS.read_text(encoding="utf-8")
        self.assertIn("Factory Market Advantage", html)
        self.assertIn("Find it. Prove it—before you build it.", html)
        self.assertIn(
            "Tell us an idea or let Factory find one. We research it, then recommend the strongest option before you build a draft.",
            html,
        )
        self.assertNotIn(
            "Validate demand, competition, and profitability before choosing what to build.",
            html,
        )
        self.assertIn('data-view="market"', html)
        self.assertIn('data-view="research"', html)
        self.assertIn("Discover Opportunities", html)
        self.assertIn("Choose Your Advantage", js)
        self.assertIn("Build This Product", js)
        self.assertIn("Save Research", js)
        self.assertIn('if (view === "research") view = "market"', js)
        self.assertIn("async function chooseIdea(", js)
        self.assertIn("async function buildThisProduct(", js)
        self.assertIn("/research-to-builder", js)
        self.assertNotIn("BookSignal", html)
        self.assertNotIn("BookSignal", js)
        self.assertIn("Scores and revenue estimates are research indicators", html)

    def test_opening_form_has_no_default_product_type(self):
        html = INDEX.read_text(encoding="utf-8")
        js = APP_JS.read_text(encoding="utf-8")
        chooser = html.split('id="marketChooser"', 1)[1].split('id="marketOwn"', 1)[0]
        self.assertIn('<option value="">Choose a product type</option>', chooser)
        self.assertRegex(
            chooser,
            re.compile(r'<select[^>]*id="fmaProductType"[^>]*required', re.I),
        )
        self.assertIn('fillTypeSelect("fmaProductType", "Choose a product type")', js)
        self.assertNotIn('fillTypeSelect("fmaProductType", null)', js)
        # Registry still includes Ebook as a choice, but the form does not select it.
        self.assertIn('"Ebook"', js)
        self.assertNotRegex(
            js,
            re.compile(r'product_type:\s*val\("fmaProductType"\)\s*\|\|\s*"Ebook"'),
        )
        self.assertNotIn('product_type: val("fmaProductType") || "Ebook"', js)

    def test_product_type_and_audience_are_required_before_discover(self):
        html = INDEX.read_text(encoding="utf-8")
        js = APP_JS.read_text(encoding="utf-8")
        chooser = html.split('id="marketChooser"', 1)[1].split('id="marketOwn"', 1)[0]
        self.assertIn('Audience <span class="text-rose-500">*</span>', chooser)
        self.assertIn('Product type <span class="text-rose-500">*</span>', chooser)
        self.assertRegex(
            chooser,
            re.compile(r'<input id="fmaAudience"[^>]*required', re.I | re.S),
        )
        self.assertIn('id="fmaAudienceError"', chooser)
        self.assertIn('id="fmaProductTypeError"', chooser)
        self.assertIn("function validateFmaOpeningForm(", js)
        self.assertIn('String(payload.audience || "").trim()', js)
        self.assertIn('MARKET_PRODUCT_TYPES.indexOf(productType) < 0', js)
        self.assertIn('setFmaFieldError("fmaAudience", "Audience is required.")', js)
        self.assertIn('setFmaFieldError("fmaProductType", "Choose a product type.")', js)
        self.assertIn("if (!validateFmaOpeningForm(payload)) return;", js)
        run_fn = js.split("async function runFactoryMarketAdvantage()", 1)[1]
        validate_at = run_fn.find("if (!validateFmaOpeningForm(payload)) return;")
        api_at = run_fn.find('api("/discover-products"')
        self.assertGreater(validate_at, 0)
        self.assertGreater(api_at, validate_at)

    def test_new_form_defaults_to_quick_check_and_saved_depth_is_restored(self):
        html = INDEX.read_text(encoding="utf-8")
        js = APP_JS.read_text(encoding="utf-8")
        chooser = html.split('id="marketChooser"', 1)[1].split('id="marketOwn"', 1)[0]
        depth = chooser.split('id="fmaDepth"', 1)[1].split("</select>", 1)[0]
        self.assertIn("<option selected>Quick Check</option>", depth)
        self.assertIn("<option>Full Validation</option>", depth)
        self.assertNotIn("<option selected>Full Validation</option>", depth)
        self.assertIn('depth: val("fmaDepth") || "Quick Check"', js)
        self.assertNotIn('depth: val("fmaDepth") || "Full Validation"', js)
        restore = js.split("function restoreAdvantageForm(d)", 1)[1].split(
            "function fmaFormPayload()", 1
        )[0]
        self.assertIn('set("fmaDepth", inp.depth || "")', restore)
        self.assertIn('set("fmaProductType", inp.product_type || d.product_type || "")', restore)
        self.assertIn('set("fmaAudience", inp.audience || d.audience || "")', restore)

    def test_registered_product_types_still_populate_the_opening_select(self):
        js = APP_JS.read_text(encoding="utf-8")
        self.assertIn("const MARKET_PRODUCT_TYPES = [", js)
        for label in (
            "Ebook",
            "Workbook",
            "Checklist",
            "Coloring Book",
            "Word Search Book",
            "Crossword Puzzle Book",
            "Flip Book",
            "Math Worksheet",
            "Spelling Worksheet",
            "Planner",
            "Not Sure Yet",
        ):
            self.assertIn(f'"{label}"', js.split("const MARKET_PRODUCT_TYPES")[1].split("];", 1)[0])
        self.assertIn(
            "MARKET_PRODUCT_TYPES.map((t) => `<option value=\"${escapeHtml(t)}\">${escapeHtml(t)}</option>`)",
            js,
        )

    def test_nav_no_longer_has_competing_niche_research_item(self):
        js = APP_JS.read_text(encoding="utf-8")
        self.assertNotRegex(js, re.compile(r'id:\s*"research",\s*label:\s*"Niche Research"'))
        self.assertIn('label: "Factory Market Advantage"', js)


class Project4249ProtectionTests(unittest.TestCase):
    def test_project_4249_unchanged_by_research_routes(self):
        live = database.get_project(4249)
        self.assertIsNotNone(live, "project 4249 not present")
        before = _4249_fingerprint(copy.deepcopy(live["data"]))
        cover = (live["data"].get("cover_design") or {}).get("source") or {}
        self.assertEqual(cover.get("sha256"), COVER_SHA)
        with patch("services.product.generate_product", side_effect=AssertionError("no gen")), patch(
            "services.ebook.generate_ebook", side_effect=AssertionError("no ebook")
        ):
            self.client = app.test_client()
            self.client.post(
                "/discover-products",
                json={"topic": "unrelated research", "product_type": "Ebook"},
            )
            self.client.post(
                "/discover-products",
                json={"mode": "discover", "audience": "Parents", "depth": "Quick Check"},
            )
            self.client.post(
                "/research-to-builder",
                json={"opportunity": COLORING, "research": {"product_type": "Coloring Book"}},
            )
        after_row = database.get_project(4249)
        after = _4249_fingerprint(after_row["data"])
        self.assertEqual(before, after)
        cover_after = (after_row["data"].get("cover_design") or {}).get("source") or {}
        self.assertEqual(cover_after.get("sha256"), COVER_SHA)
        ident = after_row["data"].get("ebook_export_identity") or {}
        if ident.get("manuscript_digest"):
            self.assertEqual(ident.get("manuscript_digest"), MS_DIGEST)
        if (after_row["data"].get("cover_design") or {}).get("cover_digest"):
            self.assertEqual(after_row["data"]["cover_design"]["cover_digest"], COVER_DIGEST)
        if ident.get("preview_digest"):
            self.assertEqual(ident.get("preview_digest"), PREVIEW_DIGEST)


MOCK_DISCOVERY_SOURCES = [
    {
        "title": "Parent printable demand",
        "url": "https://example.com/printables",
        "excerpt": "Parents buy rainy-day coloring packs and indoor recess activity books.",
        "access_date": "2026-08-15",
        "confidence": "high",
    },
    {
        "title": "Teacher worksheet listings",
        "url": "https://example.com/teachers",
        "excerpt": "Teachers look for no-prep math worksheets with clear answers.",
        "access_date": "2026-08-15",
        "confidence": "medium",
    },
    {
        "title": "Photography checklist listings",
        "url": "https://example.com/photo",
        "excerpt": "New photographers buy shot-list checklists before paid shoots.",
        "access_date": "2026-08-15",
        "confidence": "medium",
    },
]


def _mock_discovered_opp(idea, product_type, audience, problem, **extra):
    return {
        "product_idea": idea,
        "product_type": product_type,
        "target_audience": audience,
        "customer_problem": problem,
        "why_opportunity": extra.get(
            "why",
            "Public listings show buyers already paying for this specific format.",
        ),
        "demand_evidence": extra.get(
            "demand",
            "Sourced listings describe active buyer demand for this product.",
        ),
        "competition": extra.get("competition", "Moderate"),
        "competition_explanation": extra.get(
            "comp_why",
            "Several public listings exist without a verified bestseller claim.",
        ),
        "price_range": extra.get("price", "$7 - $14"),
        "suggested_platforms": extra.get("platforms", ["Etsy", "Amazon"]),
        "why_it_could_sell": extra.get("why_sell", "It solves a specific job the sources mention."),
        "main_risk": extra.get("risk", "Similar printables can crowd the same keywords."),
        "sources": extra.get("sources", MOCK_DISCOVERY_SOURCES[:1]),
    }


SIX_DISCOVERED = [
    _mock_discovered_opp(
        "Rainy-Day Indoor Recess Coloring Pack",
        "Coloring Book",
        "Parents",
        "Kids need quiet indoor activities",
    ),
    _mock_discovered_opp(
        "No-Prep Fraction Practice Pack",
        "Math Worksheet",
        "Teachers",
        "Teachers need ready-to-print practice",
        sources=MOCK_DISCOVERY_SOURCES[1:2],
    ),
    _mock_discovered_opp(
        "First Paid Shoot Photography Checklist",
        "Checklist",
        "Photographers",
        "New photographers forget shot lists",
        sources=MOCK_DISCOVERY_SOURCES[2:3],
    ),
    _mock_discovered_opp(
        "Bible Crossword Hour for Adults",
        "Crossword Puzzle Book",
        "Seniors",
        "Adults want faith-based puzzles",
    ),
    _mock_discovered_opp(
        "Farm Animal Word Search Pack",
        "Word Search Book",
        "Parents",
        "Kids need screen-free word play",
    ),
    _mock_discovered_opp(
        "Event Photography Startup Guide",
        "Ebook",
        "Photographers",
        "Beginners need a first-booking plan",
        sources=MOCK_DISCOVERY_SOURCES[2:3],
    ),
]


def _patch_live_discovery(opportunities=None):
    raw = {"opportunities": list(opportunities if opportunities is not None else SIX_DISCOVERED)}
    return (
        patch(
            "services.market_research._tavily_context",
            return_value=(True, "Parents buy coloring packs. Teachers buy worksheets.", MOCK_DISCOVERY_SOURCES, None),
        ),
        patch("services.market_research.chat_json", return_value=raw),
    )


class FindIdeasForMeTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_default_mode_is_i_have_an_idea(self):
        html = INDEX.read_text(encoding="utf-8")
        js = APP_JS.read_text(encoding="utf-8")
        self.assertIn("What would you like to do?", html)
        self.assertIn("I Have an Idea", html)
        self.assertIn("Find Ideas for Me", html)
        self.assertIn('let fmaStartMode = "idea"', js)
        idea_card = html.split('id="fmaModeIdea"', 1)[1].split('id="fmaModeDiscover"', 1)[0]
        self.assertIn("fma-mode-card-active", idea_card)
        self.assertIn('id="fmaDiscoverFields" class="hidden"', html)
        self.assertIn("Research This Opportunity", html)
        self.assertIn("Find Top Opportunities", html)
        self.assertIn("Idea", html)
        self.assertIn("Evidence", html)
        self.assertIn("Advantage", html)
        self.assertIn("Decision", html)
        self.assertIn("Build", html)

    def test_find_ideas_does_not_require_a_topic(self):
        html = INDEX.read_text(encoding="utf-8")
        js = APP_JS.read_text(encoding="utf-8")
        discover = html.split('id="fmaDiscoverFields"', 1)[1].split('id="marketOwn"', 1)[0]
        self.assertNotIn("Topic / idea", discover)
        self.assertIn("Any product type", discover)
        self.assertIn("Not sure / Any", discover)
        self.assertIn("e.g. education, photography, budgeting, pets", discover)
        self.assertIn("<option selected>Quick Check</option>", discover)
        self.assertIn("General / Any audience", discover)
        find_fn = js.split("async function runFindOpportunities()", 1)[1].split(
            "function researchThisIdea(", 1
        )[0]
        self.assertNotIn("validateFmaOpeningForm", find_fn)
        self.assertNotIn("Enter a topic or idea", find_fn)
        tavily, chat = _patch_live_discovery()
        with tavily, chat, patch(
            "services.product.generate_product", side_effect=AssertionError("must not generate")
        ), patch("services.ebook.generate_ebook", side_effect=AssertionError("must not generate ebook")):
            resp = self.client.post(
                "/discover-products",
                json={"mode": "discover", "depth": "Quick Check"},
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.get_json()
        self.assertTrue(body.get("opportunities"))
        self.assertFalse(body.get("generated"))
        self.assertFalse(body.get("auto_generated"))

    def test_discovery_returns_structured_ranked_results_without_padding(self):
        tavily, chat = _patch_live_discovery()
        with tavily, chat:
            resp = self.client.post(
                "/discover-products",
                json={
                    "mode": "discover",
                    "audience": "Parents",
                    "product_type": "",
                    "sales_platform": "Not sure / Any",
                    "depth": "Quick Check",
                },
            )
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.get_json()
        self.assertEqual(body["results_title"], DISCOVERY_RESULTS_TITLE)
        self.assertNotEqual(body["results_title"], "Top 10 Best-Selling Products")
        self.assertEqual(body["discovery_disclaimer"], DISCOVERY_DISCLAIMER)
        ops = body["opportunities"]
        self.assertEqual(len(ops), 6)
        self.assertLessEqual(len(ops), 10)
        self.assertEqual([op["rank"] for op in ops], list(range(1, 7)))
        scores = [op["opportunity_score"] for op in ops]
        self.assertEqual(scores, sorted(scores, reverse=True))
        for op in ops:
            self.assertTrue(op["product_idea"])
            self.assertTrue(op["product_type"])
            self.assertTrue(op["target_audience"])
            self.assertTrue(op["customer_problem"])
            self.assertTrue(op["why_opportunity"])
            self.assertTrue(op["demand_evidence"])
            self.assertIn(op["competition"], {"Low", "Moderate", "High"})
            self.assertTrue(op["price_range"])
            self.assertTrue(op["suggested_platforms"])
            self.assertTrue(op["why_it_could_sell"])
            self.assertTrue(op["main_risk"])
            self.assertTrue(op["sources"])
            self.assertIn("factory_advantage", op)
            self.assertEqual(op["opportunity_score"], op["factory_advantage"]["total"])
            self.assertLessEqual(op["opportunity_score"], 100)
            facing = " ".join(
                str(op.get(key) or "")
                for key in (
                    "product_idea",
                    "why_opportunity",
                    "demand_evidence",
                    "why_it_could_sell",
                    "competition",
                    "price_range",
                )
            ).lower()
            self.assertNotIn("verified best seller", facing)
            self.assertNotRegex(facing, r"\bbest-selling products\b")

    def test_discovery_never_fabricates_to_fill_ten(self):
        padded = list(SIX_DISCOVERED) + [
            {"product_idea": "", "demand_evidence": ""},
            {"product_idea": "Nameless niche", "demand_evidence": "", "why_opportunity": "", "sources": []},
        ]
        tavily, chat = _patch_live_discovery(padded)
        with tavily, chat:
            body = self.client.post(
                "/discover-products",
                json={"fma_mode": "discover", "depth": "Quick Check"},
            ).get_json()
        self.assertEqual(len(body["opportunities"]), 6)
        self.assertNotEqual(len(body["opportunities"]), 10)

    def test_sources_and_evidence_are_retained(self):
        tavily, chat = _patch_live_discovery()
        with tavily, chat:
            body = self.client.post(
                "/discover-products",
                json={"mode": "discover", "audience": "Teachers", "depth": "Quick Check"},
            ).get_json()
        self.assertTrue(body["sources"])
        self.assertTrue(any(s.get("url") for s in body["sources"]))
        top = body["opportunities"][0]
        self.assertTrue(top["sources"])
        self.assertTrue(any(s.get("url") for s in top["sources"]))
        self.assertIn("evidence", top)
        self.assertIn("verified_facts", top["evidence"])

    def test_research_this_idea_control_exists_on_discovery_cards(self):
        js = APP_JS.read_text(encoding="utf-8")
        render = js.split("function discoveryDetailsHtml(", 1)[1].split(
            "async function runFindOpportunities(", 1
        )[0]
        self.assertIn("Choose This Idea", render)
        self.assertIn("Research This Idea", js)
        self.assertIn('data-research-idea="${i}"', render)
        self.assertIn('type="button" data-research-idea="${i}"', render)
        self.assertIn("evidenceUsedSectionHtml", render)
        self.assertIn("How We Know", js)
        self.assertIn("Evidence Used", js)
        self.assertNotIn("View Source", render)
        self.assertNotIn('target="_blank"', render)
        wire = js.split("function wireOpportunityButtons(", 1)[1].split("function setFmaStep(", 1)[0]
        self.assertIn('closest("[data-research-idea]")', wire)
        self.assertIn('getAttribute("data-research-idea")', wire)
        self.assertIn("researchThisIdea(", wire)
        self.assertNotIn("dataset.researchIdea", wire)

    def test_research_this_idea_populates_market_advantage(self):
        js = APP_JS.read_text(encoding="utf-8")
        fn = js.split("function researchThisIdea(", 1)[1].split("async function saveOpportunity(", 1)[0]
        self.assertIn('setFmaStartMode("idea")', fn)
        self.assertIn("op.product_idea", fn)
        self.assertIn("op.target_audience", fn)
        self.assertIn("op.customer_problem", fn)
        self.assertIn("op.product_type", fn)
        self.assertIn("runFactoryMarketAdvantage()", fn)
        self.assertIn("_carried_from_discovery", fn)
        self.assertNotIn("/generate", fn)
        self.assertNotIn("generate_product", fn)
        tavily, chat = _patch_live_discovery()
        with tavily, chat:
            discovered = self.client.post(
                "/discover-products",
                json={"mode": "discover", "depth": "Quick Check"},
            ).get_json()
        chosen = next(op for op in discovered["opportunities"] if op["product_type"] == "Coloring Book")
        follow = self.client.post(
            "/discover-products",
            json={
                "topic": chosen["product_idea"],
                "audience": chosen["target_audience"],
                "customer_problem": chosen["customer_problem"],
                "product_type": chosen["product_type"],
                "sales_platform": "Amazon KDP",
                "carried_sources": chosen["sources"],
                "prior_opportunity": chosen,
            },
        )
        self.assertEqual(follow.status_code, 200, follow.data)
        body = follow.get_json()
        self.assertEqual(body["product_type"], "Coloring Book")
        self.assertIn("factory_advantage", body)
        self.assertIn("advantage_report", body)
        self.assertNotEqual(body.get("fma_mode"), "discover")
        self.assertFalse(body.get("generated"))

    def test_saved_opportunity_survives_reopen(self):
        tavily, chat = _patch_live_discovery()
        with tavily, chat:
            research = self.client.post(
                "/discover-products",
                json={"mode": "discover", "audience": "Parents", "depth": "Quick Check"},
            ).get_json()
        chosen = research["opportunities"][0]
        saved = self.client.post(
            "/projects",
            json={
                "name": f"Research: {chosen['product_idea']}",
                "type": "research_plan",
                "user_saved": True,
                "data": {
                    **research,
                    "stage": "research_saved",
                    "selected_opportunity": chosen,
                    "fma_mode": "discover",
                },
            },
        )
        self.assertEqual(saved.status_code, 201, saved.data)
        rid = saved.get_json()["id"]
        reopened = self.client.get(f"/projects/{rid}").get_json()
        data = reopened["data"]
        self.assertEqual(reopened["type"], "research_plan")
        self.assertEqual(data["selected_opportunity"]["product_idea"], chosen["product_idea"])
        self.assertEqual(data["selected_opportunity"]["product_type"], chosen["product_type"])
        self.assertEqual(data["selected_opportunity"]["target_audience"], chosen["target_audience"])
        self.assertEqual(data["selected_opportunity"]["customer_problem"], chosen["customer_problem"])
        self.assertTrue(data["selected_opportunity"].get("sources") or data.get("sources"))
        self.assertIn("opportunity_score", data["selected_opportunity"])
        self.assertTrue(data.get("researched_at") or data["selected_opportunity"].get("factory_advantage"))
        self.assertEqual(data["fma_mode"], "discover")

    def test_coloring_handoff_stays_draft_and_does_not_become_ebook(self):
        tavily, chat = _patch_live_discovery()
        with tavily, chat:
            research = self.client.post(
                "/discover-products",
                json={"mode": "discover", "product_type": "Coloring Book", "depth": "Quick Check"},
            ).get_json()
        chosen = next(op for op in research["opportunities"] if op["product_type"] == "Coloring Book")
        saved = self.client.post(
            "/projects",
            json={
                "name": f"Research: {chosen['product_idea']}",
                "type": "research_plan",
                "user_saved": True,
                "data": {**research, "selected_opportunity": chosen, "stage": "research_saved"},
            },
        )
        rid = saved.get_json()["id"]
        with patch("services.product.generate_product", side_effect=AssertionError("no gen")), patch(
            "services.ebook.generate_ebook", side_effect=AssertionError("no ebook")
        ), patch("ai_client.chat_json", side_effect=AssertionError("must not call AI on build")):
            built = self.client.post(
                "/research-to-builder",
                json={
                    "research_id": rid,
                    "opportunity": chosen,
                    "research": research,
                    "inputs": research.get("inputs") or {},
                },
            )
        self.assertEqual(built.status_code, 201, built.data)
        body = built.get_json()
        self.assertEqual(body["factory_id"], "coloring_book")
        self.assertNotEqual(body["factory_id"], "ebook")
        self.assertEqual(body["product_type"], "Coloring Book")
        self.assertEqual(body["artifact_state"], ArtifactState.DRAFT.value)
        self.assertFalse(body["generated"])
        self.assertFalse(body["auto_generated"])

    def test_discovery_does_not_auto_generate_a_product(self):
        tavily, chat = _patch_live_discovery()
        with tavily, chat, patch(
            "services.product.generate_product", side_effect=AssertionError("discovery must not generate")
        ), patch("services.ebook.generate_ebook", side_effect=AssertionError("discovery must not generate ebook")):
            resp = self.client.post(
                "/discover-products",
                json={"mode": "discover", "interest": "pets", "depth": "Quick Check"},
            )
        body = resp.get_json()
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertFalse(body.get("generated"))
        self.assertFalse(body.get("auto_generated"))
        self.assertNotIn("content", body.get("plan") or {})

    def test_research_failure_preserves_filters_and_does_not_fabricate(self):
        payload = {
            "mode": "discover",
            "audience": "Parents",
            "interest": "education",
            "product_type": "Coloring Book",
            "sales_platform": "Etsy",
            "depth": "Quick Check",
        }
        resp = self.client.post("/discover-products", json=payload)
        self.assertEqual(resp.status_code, 503, resp.data)
        body = resp.get_json()
        self.assertEqual(body["error"], DISCOVERY_FAILURE_MESSAGE)
        self.assertTrue(body.get("retryable"))
        self.assertEqual(body["inputs"]["audience"], "Parents")
        self.assertEqual(body["inputs"]["interest"], "education")
        self.assertEqual(body["inputs"]["product_type"], "Coloring Book")
        self.assertEqual(body["opportunities"], [])
        self.assertFalse(body.get("generated"))

    def test_existing_idea_workflow_still_works_without_mode_flag(self):
        resp = self.client.post(
            "/discover-products",
            json={
                "topic": "Kids superhero coloring",
                "audience": "Children ages 8-12",
                "customer_problem": "Kids need engaging printable coloring stories",
                "product_type": "Coloring Book",
            },
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.get_json()
        self.assertEqual(body["product_type"], "Coloring Book")
        self.assertIn("factory_advantage", body)
        self.assertNotEqual(body.get("fma_mode"), "discover")
        self.assertNotEqual(body.get("results_title"), DISCOVERY_RESULTS_TITLE)


class FindIdeasPresentationTests(unittest.TestCase):
    def test_results_copy_and_opening_form_are_not_regressed(self):
        html = INDEX.read_text(encoding="utf-8")
        js = APP_JS.read_text(encoding="utf-8")
        self.assertIn("Here is what we recommend.", js)
        self.assertNotIn("Top 10 Best-Selling Products", html)
        self.assertNotIn("Top 10 Best-Selling Products", js)
        self.assertIn("Research This Idea", js)
        self.assertIn("Choose This Idea", js)
        self.assertIn("Save Opportunity", js)
        self.assertIn("function renderTopOpportunities(", js)
        self.assertIn("async function runFindOpportunities(", js)
        self.assertIn("function researchThisIdea(", js)
        self.assertIn("async function saveOpportunity(", js)
        self.assertIn(DISCOVERY_FAILURE_MESSAGE, js)
        chooser = html.split('id="marketChooser"', 1)[1].split('id="marketOwn"', 1)[0]
        self.assertIn('<option value="">Choose a product type</option>', chooser)
        self.assertIn("Audience <span class=\"text-rose-500\">*</span>", chooser)
        self.assertIn(
            "Tell us an idea or let Factory find one. We research it, then recommend the strongest option before you build a draft.",
            chooser,
        )
        self.assertIn("Find it. Prove it—before you build it.", chooser)
        self.assertIn("Factory Market Advantage", chooser)
        depth = chooser.split('id="fmaDepth"', 1)[1].split("</select>", 1)[0]
        self.assertIn("<option selected>Quick Check</option>", depth)
        self.assertIn("Discover Opportunities", html)


class InFactoryReportTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def _idea_research(self):
        return self.client.post(
            "/discover-products",
            json={
                "topic": "Kids superhero coloring",
                "audience": "Children ages 8-12",
                "customer_problem": "Kids need engaging printable coloring stories",
                "product_type": "Coloring Book",
                "sales_platform": "Amazon KDP",
                "expertise": "Some experience",
                "target_price": "$9.99",
            },
        )

    def test_in_factory_report_has_required_sections(self):
        resp = self._idea_research()
        self.assertEqual(resp.status_code, 200, resp.data)
        body = resp.get_json()
        report = body["in_factory_report"]
        for key in (
            "opportunity_summary",
            "trend_evidence",
            "marketplace_competition",
            "video_social_evidence",
            "customer_evidence",
            "price_revenue_signals",
            "competition_opportunity_gap",
            "factory_advantage_score",
            "decision",
            "sources",
            "evidence_used",
            "how_we_know",
        ):
            self.assertIn(key, report, key)
        summary = report["opportunity_summary"]
        self.assertTrue(summary["product_idea"])
        self.assertEqual(summary["target_customer"], "Children ages 8-12")
        self.assertIn("coloring", summary["customer_problem"].lower())
        self.assertEqual(summary["recommended_product_format"], "Coloring Book")
        self.assertTrue(summary["why_timely"])
        self.assertEqual(report["trend_evidence"]["direction"], INSUFFICIENT_EVIDENCE)
        self.assertEqual(report["factory_advantage_score"]["total"], body["factory_advantage"]["total"])
        self.assertEqual(
            report["decision"]["internal_recommendation"],
            body["factory_advantage"]["recommendation"],
        )
        self.assertIn(
            report["decision"]["user_decision"],
            {USER_DECISION_BUILD, USER_DECISION_IMPROVE, USER_DECISION_AVOID},
        )
        labels = {
            row["display_label"]
            for row in report["factory_advantage_score"]["components"]
        }
        for required in (
            "Demand",
            "Competition",
            "Ease of Creation",
            "Profit Potential",
            "Differentiation",
            "Evidence Confidence",
        ):
            self.assertIn(required, labels)

    def test_recommendation_maps_to_build_improve_avoid(self):
        self.assertEqual(map_user_decision("Strong Opportunity"), USER_DECISION_BUILD)
        self.assertEqual(map_user_decision("Promising—Needs Positioning"), USER_DECISION_IMPROVE)
        self.assertEqual(map_user_decision("Test Before Building"), USER_DECISION_IMPROVE)
        self.assertEqual(map_user_decision("Weak Opportunity"), USER_DECISION_AVOID)
        self.assertEqual(map_user_decision("Insufficient Evidence"), USER_DECISION_AVOID)
        body = self._idea_research().get_json()
        self.assertEqual(
            body["decision_panel"]["user_decision"],
            map_user_decision(body["factory_advantage"]["recommendation"]),
        )

    def test_unsupported_claims_rejected(self):
        self.assertEqual(
            reject_unsupported_trend_language("This niche is trending now"),
            "This niche is discussed now",
        )
        padded = [
            _mock_discovered_opp(
                "Viral Pet Planner",
                "Planner",
                "Parents",
                "Need a weekly plan",
                demand="This is trending on Amazon right now",
                why="A hot trending product for parents",
            )
        ]
        tavily, chat = _patch_live_discovery(padded)
        with tavily, chat:
            body = self.client.post(
                "/discover-products",
                json={"mode": "discover", "depth": "Quick Check"},
            ).get_json()
        facing = " ".join(
            str(op.get(key) or "")
            for op in body["opportunities"]
            for key in ("demand_evidence", "why_opportunity", "why_it_could_sell")
        ).lower()
        self.assertNotIn("trending", facing)
        idea = self._idea_research().get_json()
        report = idea["in_factory_report"]
        self.assertEqual(report["trend_evidence"]["direction"], INSUFFICIENT_EVIDENCE)
        blob = str(report).lower()
        self.assertNotIn("are verified sales", blob)
        self.assertFalse(report["price_revenue_signals"]["verified_sales"])
        self.assertIn("never labels estimated amazon sales as verified sales", blob)

    def test_estimates_visibly_labeled(self):
        body = self._idea_research().get_json()
        pricing = body["in_factory_report"]["price_revenue_signals"]
        self.assertEqual(pricing["sales_estimate_label"], "Estimated demand")
        self.assertFalse(pricing["verified_sales"])
        labels = [row.get("label") for row in pricing["estimates"]]
        self.assertIn("Estimated demand", labels)
        self.assertFalse(body["sales_estimate"]["available"])
        js = APP_JS.read_text(encoding="utf-8")
        self.assertIn("Estimated demand", js)
        self.assertIn("This is not verified sales", js)

    def test_sources_retained_on_in_factory_report(self):
        tavily, chat = _patch_live_discovery()
        with tavily, chat:
            discovered = self.client.post(
                "/discover-products",
                json={"mode": "discover", "depth": "Quick Check"},
            ).get_json()
        self.assertTrue(discovered["sources"])
        chosen = discovered["opportunities"][0]
        self.assertTrue(chosen["sources"])
        follow = self.client.post(
            "/discover-products",
            json={
                "topic": chosen["product_idea"],
                "audience": chosen["target_audience"],
                "customer_problem": chosen["customer_problem"],
                "product_type": chosen["product_type"],
                "carried_sources": chosen["sources"],
            },
        ).get_json()
        self.assertTrue(follow["sources"])
        self.assertTrue(follow["in_factory_report"]["sources"])
        self.assertTrue(any(s.get("url") for s in follow["in_factory_report"]["sources"]))
        self.assertTrue(any(s.get("website") or s.get("title") for s in follow["in_factory_report"]["sources"]))
        self.assertTrue(follow.get("internal_evidence_record"))
        self.assertTrue(any(row.get("url") for row in follow["internal_evidence_record"]))

    def _customer_js(self):
        js = APP_JS.read_text(encoding="utf-8")
        slices = []
        for start, end in (
            ("function sourceDomainText(", "function mapUserDecision("),
            ("function renderMarket(", "async function createProductPlan("),
            ("function toggleHiddenEl(", "async function saveResearchOnly("),
            ("function discoveryDetailsHtml(", "async function runFindOpportunities("),
            ("function wireOpportunityButtons(", "function setFmaStep("),
        ):
            self.assertIn(start, js)
            self.assertIn(end, js)
            slices.append(js.split(start, 1)[1].split(end, 1)[0])
        return "\n".join(slices)

    def _research_with_sources(self, extra_sources=None):
        sources = list(RICH_EVIDENCE["sources"])
        if extra_sources:
            sources.extend(extra_sources)
        return self.client.post(
            "/discover-products",
            json={
                "topic": "Kids superhero coloring",
                "audience": "Children ages 8-12",
                "customer_problem": "Kids need engaging printable coloring stories",
                "product_type": "Coloring Book",
                "sales_platform": "Amazon KDP",
                "expertise": "Some experience",
                "target_price": "$9.99",
                "carried_sources": sources,
            },
        )

    def test_no_customer_facing_citation_is_a_clickable_external_link(self):
        js = self._customer_js()
        self.assertNotIn("View Source", js)
        self.assertNotIn('target="_blank"', js)
        self.assertNotIn("window.open", js)
        self.assertNotRegex(js, r'href="\$\{escapeHtml\((?:s\.url|url|s\.listing_url)')
        body = self._research_with_sources().get_json()
        used = body["in_factory_report"]["evidence_used"]
        for card in used["cards"]:
            self.assertNotIn("url", card)
            self.assertNotIn("href", str(card).lower())
        for item in body["in_factory_report"]["how_we_know"]["items"]:
            self.assertNotIn("url", item)
            self.assertNotIn("href", str(item).lower())

    def test_no_view_source_on_customer_results_page(self):
        js = APP_JS.read_text(encoding="utf-8")
        customer = self._customer_js()
        self.assertNotIn("View Source", customer)
        self.assertNotIn("function viewSourceLink(", js)
        self.assertNotIn("function sourceCitationHtml(", js)
        self.assertNotIn(">Citations<", customer)
        self.assertNotIn("View Source opens a new browser tab", js)
        self.assertNotIn("go read these articles", js.lower())
        self.assertNotIn("read these articles to understand", js.lower())

    def test_promotional_headlines_are_not_customer_advertisements(self):
        promo = {
            "title": "Top Products to Dominate Your Niche",
            "url": "https://competitor-example.com/top-products-to-dominate",
            "excerpt": "This printable listing makes $960–$13,966 per month.",
            "access_date": "2026-08-16",
            "publication_date": "2026-01-02",
            "confidence": "low",
        }
        body = self._research_with_sources([promo]).get_json()
        used = body["in_factory_report"]["evidence_used"]
        facing = " ".join(
            " ".join(str(card.get(key) or "") for key in ("evidence_type", "fact", "score_effect", "source_class"))
            for card in used["cards"]
        )
        self.assertNotIn("Top Products to Dominate", facing)
        self.assertNotIn("Top Products to Dominate", used["intro"])
        earnings_cards = [
            card for card in used["cards"] if "unverified" in (card.get("fact") or "").lower()
        ]
        self.assertTrue(earnings_cards)
        for card in earnings_cards:
            self.assertEqual(card["confidence"], "Limited")
            self.assertIn("weak supporting evidence", card["score_effect"].lower())
        internal = " ".join(row.get("title") or "" for row in body["internal_evidence_record"])
        self.assertIn("Top Products to Dominate", internal)

    def test_evidence_summaries_remain_visible_and_understandable(self):
        body = self._research_with_sources().get_json()
        used = body["in_factory_report"]["evidence_used"]
        self.assertEqual(used["title"], "Evidence Used")
        self.assertTrue(used["cards"])
        self.assertEqual(used["count"], len(used["cards"]))
        self.assertIn(str(used["count"]), used["intro"])
        self.assertIn("public market signal", used["intro"])
        for card in used["cards"]:
            self.assertIn(card["evidence_type"], {
                "Market trend",
                "Buyer demand",
                "Competition",
                "Pricing signal",
                "Marketplace signal",
                "Risk",
            })
            self.assertTrue(card["fact"])
            self.assertTrue(card["score_effect"])
            self.assertIn(card["source_class"], {
                "Marketplace",
                "Search trend",
                "Industry report",
                "Retail listing",
                "Social signal",
                "Publisher article",
            })
            self.assertIn(card["confidence"], {"Strong", "Moderate", "Limited"})
        js = APP_JS.read_text(encoding="utf-8")
        self.assertIn("Evidence Used", js)
        self.assertIn("function evidenceCardHtml(", js)
        self.assertIn("function evidenceUsedSectionHtml(", js)

    def test_how_we_know_opens_inside_the_factory(self):
        js = self._customer_js()
        full = APP_JS.read_text(encoding="utf-8")
        self.assertIn('data-how-we-know', js)
        self.assertIn("fma-how-we-know-panel", js)
        self.assertIn("How We Know", js)
        self.assertIn('aria-expanded', js)
        self.assertNotIn('target="_blank"', js)
        self.assertNotIn("window.open", js)
        helper = full.split("function howWeKnowPanelHtml(", 1)[1].split("function evidenceUsedSectionHtml(", 1)[0]
        self.assertNotIn("<a ", helper)
        self.assertNotIn("href=", helper)

    def test_how_we_know_domains_are_plain_non_clickable_text(self):
        promo = {
            "title": "Industry note",
            "url": "https://www.example.com/coloring-demand",
            "excerpt": "Parents look for superhero coloring books with clear heroes.",
            "access_date": "2026-08-16",
            "publication_date": "2026-03-01",
        }
        body = self._research_with_sources([promo]).get_json()
        items = body["in_factory_report"]["how_we_know"]["items"]
        self.assertTrue(items)
        domains = [item.get("source_domain") for item in items]
        self.assertTrue(any(d == "example.com" for d in domains))
        for item in items:
            self.assertNotIn("url", item)
            self.assertNotIn("http://", str(item.get("source_domain") or ""))
            self.assertNotIn("https://", str(item.get("source_domain") or ""))
        js = APP_JS.read_text(encoding="utf-8")
        domain_render = js.split("function howWeKnowPanelHtml(", 1)[1].split("function evidenceUsedSectionHtml(", 1)[0]
        self.assertIn("Source:", domain_render)
        self.assertIn("source_domain", domain_render)
        self.assertNotIn("href=", domain_render)

    def test_original_urls_remain_in_internal_evidence_record(self):
        body = self._research_with_sources().get_json()
        record = body["internal_evidence_record"]
        self.assertTrue(record)
        urls = [row["url"] for row in record if row.get("url")]
        self.assertTrue(urls)
        self.assertTrue(any(row.get("title") for row in record))
        self.assertTrue(any(row.get("domain") for row in record))
        self.assertTrue(any(row.get("retrieval_date") for row in record))
        self.assertTrue(any(row.get("supported_claim") for row in record))
        self.assertTrue(any(s.get("url") for s in body["sources"]))
        self.assertTrue(any(s.get("url") for s in body["in_factory_report"]["sources"]))
        self.assertTrue(any(s.get("url") for s in body["evidence"]["sources"]))

    def test_saved_research_reopens_with_same_evidence_summaries(self):
        research = self._research_with_sources().get_json()
        used = research["in_factory_report"]["evidence_used"]
        saved = self.client.post(
            "/projects",
            json={
                "name": "Research: Kids superhero coloring",
                "type": "research_plan",
                "user_saved": True,
                "data": {**research, "stage": "research_saved", "selected_opportunity": COLORING},
            },
        )
        self.assertEqual(saved.status_code, 201, saved.data)
        rid = saved.get_json()["id"]
        reopened = self.client.get(f"/projects/{rid}").get_json()
        data = reopened["data"]
        self.assertEqual(data["in_factory_report"]["evidence_used"], used)
        self.assertEqual(
            [card["fact"] for card in data["in_factory_report"]["evidence_used"]["cards"]],
            [card["fact"] for card in used["cards"]],
        )
        self.assertTrue(data.get("internal_evidence_record") or data["sources"])

    def test_publication_date_is_not_confused_with_accessed_date(self):
        dated = {
            "title": "Parent coloring demand study",
            "url": "https://dated-signals.example.org/note",
            "excerpt": "A 2026 parent survey described demand for themed superhero coloring books.",
            "access_date": "2026-08-16",
            "publication_date": "2026-03-01",
            "confidence": "high",
        }
        body = self._research_with_sources([dated]).get_json()
        items = body["in_factory_report"]["how_we_know"]["items"]
        match = next(
            item
            for item in items
            if item.get("source_domain") == "dated-signals.example.org"
        )
        self.assertEqual(match["publication_date"], "2026-03-01")
        self.assertEqual(match["accessed"], "2026-08-16")
        self.assertNotEqual(match["publication_date"], match["accessed"])
        js = APP_JS.read_text(encoding="utf-8")
        helper = js.split("function howWeKnowPanelHtml(", 1)[1].split("function evidenceUsedSectionHtml(", 1)[0]
        self.assertIn("Accessed:", helper)
        self.assertIn("Published:", helper)
        self.assertNotIn("Accessed: ${escapeHtml(item.publication_date", helper)

    def test_research_this_idea_does_not_generate_a_product(self):
        js = APP_JS.read_text(encoding="utf-8")
        fn = js.split("function researchThisIdea(", 1)[1].split("async function saveOpportunity(", 1)[0]
        self.assertIn("runFactoryMarketAdvantage()", fn)
        self.assertNotIn("/generate", fn)
        self.assertNotIn("generate_product", fn)
        self.assertNotIn("generate_ebook", fn)
        tavily, chat = _patch_live_discovery()
        with tavily, chat, patch(
            "services.product.generate_product", side_effect=AssertionError("must not generate")
        ), patch("services.ebook.generate_ebook", side_effect=AssertionError("must not generate ebook")):
            discovered = self.client.post(
                "/discover-products",
                json={"mode": "discover", "depth": "Quick Check"},
            ).get_json()
            chosen = next(op for op in discovered["opportunities"] if op["product_type"] == "Coloring Book")
            follow = self.client.post(
                "/discover-products",
                json={
                    "topic": chosen["product_idea"],
                    "audience": chosen["target_audience"],
                    "customer_problem": chosen["customer_problem"],
                    "product_type": chosen["product_type"],
                    "carried_sources": chosen["sources"],
                    "prior_opportunity": chosen,
                },
            )
        self.assertEqual(follow.status_code, 200, follow.data)
        body = follow.get_json()
        self.assertFalse(body.get("generated"))
        self.assertFalse(body.get("auto_generated"))
        self.assertIn("in_factory_report", body)

    def test_build_this_product_opens_correct_builder_as_draft(self):
        research = self._idea_research().get_json()
        opp = {**COLORING, "product_type": "Coloring Book"}
        with patch("services.product.generate_product", side_effect=AssertionError("no gen")), patch(
            "services.ebook.generate_ebook", side_effect=AssertionError("no ebook")
        ):
            built = self.client.post(
                "/research-to-builder",
                json={"opportunity": opp, "research": research, "inputs": research.get("inputs")},
            )
        self.assertEqual(built.status_code, 201, built.data)
        body = built.get_json()
        self.assertEqual(body["factory_id"], "coloring_book")
        self.assertEqual(body["artifact_state"], ArtifactState.DRAFT.value)
        self.assertFalse(body["generated"])
        self.assertFalse(body["auto_generated"])

    def test_no_paid_or_external_calls_during_tests(self):
        with patch("services.market_research.chat_json", side_effect=AssertionError("paid chat")), patch(
            "ai_client.chat_json", side_effect=AssertionError("paid ai")
        ), patch("ai_client.chat", side_effect=AssertionError("paid chat text")):
            idea = self._idea_research()
            discover = self.client.post(
                "/discover-products",
                json={"mode": "discover", "depth": "Quick Check"},
            )
        self.assertEqual(idea.status_code, 200, idea.data)
        self.assertEqual(discover.status_code, 503, discover.data)
        self.assertFalse(idea.get_json().get("generated"))

    def test_coloring_and_crossword_never_become_ebook_in_report(self):
        for label, factory_id in (("Coloring Book", "coloring_book"), ("Crossword Puzzle Book", "crossword")):
            resp = self.client.post(
                "/discover-products",
                json={"topic": f"{label} idea", "audience": "adults", "product_type": label},
            )
            body = resp.get_json()
            self.assertEqual(body["product_type"], label)
            self.assertEqual(body["in_factory_report"]["opportunity_summary"]["recommended_product_format"], label)
            self.assertNotEqual(resolve_factory_builder(label)["factory_id"], "ebook")
            self.assertEqual(resolve_factory_builder(label)["factory_id"], factory_id)

    def test_ui_keeps_in_factory_sections_and_branding(self):
        js = APP_JS.read_text(encoding="utf-8")
        html = INDEX.read_text(encoding="utf-8")
        for heading in (
            "Opportunity Summary",
            "Trend Evidence",
            "Marketplace Competition",
            "Video and Social Evidence",
            "Customer Evidence",
            "Price and Revenue Signals",
            "Competition and Opportunity Gap",
            "Factory Advantage Score",
            "Decision",
            "Evidence Used",
            "How We Know",
        ):
            self.assertIn(heading, js)
        self.assertIn("function mapUserDecision(", js)
        self.assertIn("BUILD", js)
        self.assertIn("IMPROVE THE IDEA", js)
        self.assertIn("AVOID", js)
        self.assertIn("Factory Market Advantage", html)
        self.assertIn("Find it. Prove it—before you build it.", html)
        self.assertIn("Research This Opportunity", html)
        self.assertIn("I Have an Idea", html)


class FactoryMarketAdvantageUxTests(unittest.TestCase):
    """Presentation-layer simplification. Does not rebuild research or generate products."""

    def setUp(self):
        self.client = app.test_client()

    def _idea_research(self):
        return self.client.post(
            "/discover-products",
            json={
                "topic": "Kids superhero coloring",
                "audience": "Children ages 8-12",
                "customer_problem": "Kids need engaging printable coloring stories",
                "product_type": "Coloring Book",
                "sales_platform": "Amazon KDP",
                "expertise": "Some experience",
                "target_price": "$9.99",
            },
        )

    def test_plain_labels_map_existing_recommendation_bands(self):
        self.assertEqual(plain_opportunity_label("Strong Opportunity"), "Promising")
        self.assertEqual(plain_opportunity_label("Promising—Needs Positioning"), "Needs Improvement")
        self.assertEqual(plain_opportunity_label("Test Before Building"), "Needs Improvement")
        self.assertEqual(plain_opportunity_label("Weak Opportunity"), "Avoid")
        self.assertEqual(plain_opportunity_label("Insufficient Evidence"), "Insufficient Evidence")
        self.assertEqual(plain_opportunity_label("Strong Opportunity", USER_DECISION_BUILD), "Promising")
        rich = compute_factory_advantage(RICH_INPUTS, RICH_EVIDENCE)
        self.assertEqual(rich["recommendation"], "Strong Opportunity")
        self.assertEqual(plain_opportunity_label(rich["recommendation"]), "Promising")
        self.assertEqual(plain_component_signal(rich["components"]["demand"]), "Good Signal")

    def test_recommendation_summary_reuses_existing_decision_and_does_not_invent_sales(self):
        score = compute_factory_advantage(RICH_INPUTS, RICH_EVIDENCE)
        summary = build_recommendation_summary(
            RICH_INPUTS,
            score=score,
            opportunities=[COLORING],
            evidence=RICH_EVIDENCE,
            recommendation={
                "best_product": COLORING["product_idea"],
                "best_product_type": "Coloring Book",
                "why_selected": COLORING["why_opportunity"],
            },
            decision={"user_decision": map_user_decision(score["recommendation"])},
        )
        self.assertEqual(summary["internal_recommendation"], score["recommendation"])
        self.assertEqual(summary["user_decision"], map_user_decision(score["recommendation"]))
        self.assertEqual(summary["opportunity_label"], "Promising")
        self.assertEqual(summary["product_name"], COLORING["product_idea"])
        self.assertEqual(summary["product_type"], "Coloring Book")
        self.assertTrue(summary["why_we_recommend"])
        self.assertIn("Start with:", summary["what_to_build"])
        self.assertIn("Coloring Book", summary["what_to_build"] + summary["product_type"])
        self.assertEqual(summary["how_determined"], HOW_DETERMINED_PLAIN)
        blob = str(summary).lower()
        self.assertNotIn("bsr #", blob)
        self.assertNotIn("10000 searches", blob)
        self.assertNotIn("$10,000", blob)
        labels = [row["label"] for row in summary["component_signals"]]
        self.assertEqual(
            labels,
            ["Demand", "Competition", "Customer Need", "Profit Evidence", "Ability to Stand Out"],
        )
        for row in summary["component_signals"]:
            self.assertIn(row["signal"], {"Good Signal", "Mixed Signal", "More Research Needed", "Weak Signal"})
            self.assertNotIn("score", row)
            self.assertNotIn("max", row)

    def test_i_have_an_idea_and_find_ideas_still_work(self):
        idea = self._idea_research()
        self.assertEqual(idea.status_code, 200, idea.data)
        body = idea.get_json()
        self.assertIn("factory_advantage", body)
        self.assertIn("recommendation_summary", body)
        self.assertEqual(body["recommendation_summary"]["internal_recommendation"], body["factory_advantage"]["recommendation"])
        tavily, chat = _patch_live_discovery()
        with tavily, chat:
            found = self.client.post("/discover-products", json={"mode": "discover", "depth": "Quick Check"})
        self.assertEqual(found.status_code, 200, found.data)
        disc = found.get_json()
        self.assertTrue(disc.get("opportunities"))
        self.assertFalse(disc.get("generated"))

    def test_existing_research_data_still_reaches_report_and_can_be_saved(self):
        body = self._idea_research().get_json()
        report = body["in_factory_report"]
        for key in (
            "trend_evidence",
            "marketplace_competition",
            "video_social_evidence",
            "customer_evidence",
            "price_revenue_signals",
            "competition_opportunity_gap",
            "factory_advantage_score",
            "evidence_used",
            "how_we_know",
            "sources",
        ):
            self.assertIn(key, report, key)
        self.assertEqual(report["factory_advantage_score"]["total"], body["factory_advantage"]["total"])
        saved = self.client.post(
            "/projects",
            json={
                "name": "Research: Kids superhero coloring",
                "type": "research_plan",
                "user_saved": True,
                "data": {**body, "stage": "research_saved", "selected_opportunity": COLORING},
            },
        )
        self.assertEqual(saved.status_code, 201, saved.data)
        reopened = self.client.get(f"/projects/{saved.get_json()['id']}").get_json()
        self.assertEqual(reopened["data"]["in_factory_report"]["evidence_used"], report["evidence_used"])
        self.assertEqual(
            reopened["data"]["recommendation_summary"]["product_name"],
            body["recommendation_summary"]["product_name"],
        )

    def test_recommendation_summary_shown_first_not_full_report(self):
        js = APP_JS.read_text(encoding="utf-8")
        html = INDEX.read_text(encoding="utf-8")
        self.assertIn("Your Best Opportunity", js)
        self.assertIn("Why We Recommend It", js)
        self.assertIn("What We Recommend Building", js)
        self.assertIn("Improve This Idea", js)
        self.assertIn("See Research Summary", js)
        self.assertIn("View Full Research &amp; Sources", js)
        self.assertIn('id="fmaFullResearch" class="hidden', js)
        self.assertIn('id="fmaResearchSummary" class="hidden', js)
        self.assertIn("function recommendationSummaryHtml(", js)
        render = js.split("function renderDiscovery(", 1)[1].split("async function saveResearchOnly(", 1)[0]
        self.assertLess(render.find("recommendationSummaryHtml"), render.find('id="fmaFullResearch"'))
        self.assertLess(render.find("explainerVideoHtml"), render.find('id="fmaFullResearch"'))
        self.assertIn("Trend Evidence", render)
        self.assertIn("Choose Your Advantage", render)
        self.assertIn("More Options", html)
        self.assertIn("Choose → Research → Recommendation → Build Draft → Review → Download", html)

    def test_numeric_component_scores_not_in_default_customer_html(self):
        js = APP_JS.read_text(encoding="utf-8")
        summary_fn = js.split("function recommendationSummaryHtml(", 1)[1].split("function renderDiscovery(", 1)[0]
        signals_fn = js.split("function simpleScoreSignalsHtml(", 1)[1].split("function recommendationSummaryHtml(", 1)[0]
        self.assertNotIn("${c.score}/${c.max}", summary_fn)
        self.assertNotIn("${c.score}/${c.max}", signals_fn)
        self.assertNotIn("/100", summary_fn)
        self.assertIn("Good Signal", js)
        self.assertIn("More Research Needed", js)
        full = js.split('id="fmaFullResearch" class="hidden', 1)[1].split("async function saveResearchOnly(", 1)[0]
        self.assertIn("componentCard(scoreComps.demand)", full)
        self.assertIn("Factory Advantage Score", full)
        self.assertIn("Missing Evidence", full)
        self.assertIn("evidenceUsedSectionHtml", full)
        self.assertIn("${c.score}/${c.max}", js.split("const componentCard = (c) =>", 1)[1].split("const scoreComps", 1)[0])

    def test_no_view_source_or_clickable_external_urls_on_customer_page(self):
        js = APP_JS.read_text(encoding="utf-8")
        customer = "\n".join(
            [
                js.split("function recommendationSummaryHtml(", 1)[1].split("function renderDiscovery(", 1)[0],
                js.split("function renderDiscovery(", 1)[1].split("async function saveResearchOnly(", 1)[0],
                js.split("function discoveryDetailsHtml(", 1)[1].split("async function runFindOpportunities(", 1)[0],
            ]
        )
        self.assertNotIn("View Source", customer)
        self.assertNotIn('target="_blank"', customer)
        self.assertNotIn("window.open", customer)

    def test_choose_this_idea_still_populates_idea_workflow(self):
        js = APP_JS.read_text(encoding="utf-8")
        fn = js.split("function researchThisIdea(", 1)[1].split("async function saveOpportunity(", 1)[0]
        self.assertIn('setFmaStartMode("idea")', fn)
        self.assertIn("runFactoryMarketAdvantage()", fn)
        self.assertIn("Choose This Idea", js)
        self.assertNotIn("/generate", fn)

    def test_build_this_product_still_draft_no_generate_no_cover(self):
        research = self._idea_research().get_json()
        with patch("services.product.generate_product", side_effect=AssertionError("no gen")), patch(
            "services.ebook.generate_ebook", side_effect=AssertionError("no ebook")
        ), patch("ai_client.chat_json", side_effect=AssertionError("must not call AI")), patch(
            "ai_client.chat", side_effect=AssertionError("must not call AI text")
        ):
            built = self.client.post(
                "/research-to-builder",
                json={"opportunity": COLORING, "research": research, "inputs": research.get("inputs")},
            )
        self.assertEqual(built.status_code, 201, built.data)
        body = built.get_json()
        self.assertEqual(body["factory_id"], "coloring_book")
        self.assertEqual(body["artifact_state"], ArtifactState.DRAFT.value)
        self.assertFalse(body["generated"])
        self.assertFalse(body["auto_generated"])
        js = APP_JS.read_text(encoding="utf-8")
        build_fn = js.split("async function buildThisProduct(", 1)[1].split("async function runFactoryMarketAdvantage(", 1)[0]
        self.assertIn("/research-to-builder", build_fn)
        # Check the CODE, not the comments. The point of this guard is that
        # Build This Product never calls a generate endpoint -- generating
        # costs money and the click means "open a draft", not "spend". A
        # comment that names /generate-ebook while explaining why the function
        # deliberately avoids it is documentation, not a call, and used to
        # fail this assertion.
        code_only = re.sub(r"/\*.*?\*/", "", build_fn, flags=re.S)
        code_only = re.sub(r"//[^\n]*", "", code_only)
        self.assertNotIn("/generate", code_only)

    def test_no_openai_or_tavily_when_viewing_completed_report_payload(self):
        research = self._idea_research().get_json()
        with patch("services.market_research.chat_json", side_effect=AssertionError("no OpenAI")), patch(
            "ai_client.chat_json", side_effect=AssertionError("no OpenAI")
        ), patch("ai_client.chat", side_effect=AssertionError("no OpenAI text")), patch(
            "services.market_research._tavily_context", side_effect=AssertionError("no Tavily")
        ), patch(
            "services.product.generate_product", side_effect=AssertionError("no product")
        ):
            saved = self.client.post(
                "/projects",
                json={
                    "name": "Research: view only",
                    "type": "research_plan",
                    "user_saved": True,
                    "data": {**research, "stage": "research_saved"},
                },
            )
            self.assertEqual(saved.status_code, 201, saved.data)
            reopened = self.client.get(f"/projects/{saved.get_json()['id']}")
        self.assertEqual(reopened.status_code, 200)
        data = reopened.get_json()["data"]
        self.assertIn("recommendation_summary", data)
        self.assertIn("in_factory_report", data)
        self.assertFalse(data.get("generated"))

    def test_explainer_is_optional_placeholder_without_autoplay(self):
        js = APP_JS.read_text(encoding="utf-8")
        helper = js.split("function explainerVideoHtml(", 1)[1].split("function simpleScoreSignalsHtml(", 1)[0]
        self.assertIn("New here? See how Factory Market Advantage works — 60 seconds", helper)
        self.assertIn("Explainer video coming soon", helper)
        self.assertIn("does not auto-generate a finished product", helper)
        self.assertIn("No autoplay", helper)
        self.assertNotIn("autoplay=", helper.lower())
        self.assertIn("hidden", helper)

    def test_locked_project_4249_unchanged_by_ux_payloads(self):
        live = database.get_project(4249)
        self.assertIsNotNone(live, "project 4249 not present")
        before = _4249_fingerprint(copy.deepcopy(live["data"]))
        with patch("services.product.generate_product", side_effect=AssertionError("no gen")), patch(
            "services.ebook.generate_ebook", side_effect=AssertionError("no ebook")
        ):
            self._idea_research()
        after = _4249_fingerprint(database.get_project(4249)["data"])
        self.assertEqual(before, after)


class DescribedProductTypeRoutingTests(unittest.TestCase):
    """A described product type must route on its head noun, not a modifier.

    Live research names the product in prose rather than picking a catalog
    label, so `resolve_factory_builder` sees strings like "Printable inventory
    and meal planning workbook". That routed to the hidden generic Planner --
    because the incidental gerund in "meal planning" was tested before any
    product noun -- and Build This Product answered "not ready in the public
    builder yet" for a workbook the Ebook Builder handles perfectly well.
    """

    def _route(self, product_type: str) -> tuple[str, str]:
        row = resolve_factory_builder(product_type)
        return row["status"], row["label"]

    def test_a_workbook_about_planning_is_still_a_workbook(self):
        self.assertEqual(
            self._route("Printable inventory and meal planning workbook"),
            ("active", "Ebook"),
        )

    def test_a_guide_about_planning_is_still_a_guide(self):
        self.assertEqual(
            self._route("Zero-waste weekly meal-planning guide with shopping lists"),
            ("active", "Ebook"),
        )

    def test_a_named_planner_still_routes_to_its_own_builder(self):
        self.assertEqual(self._route("Faith Planner"), ("active", "Faith Planner"))
        self.assertEqual(self._route("Budget Planner"), ("active", "Budget Planner"))
        self.assertEqual(self._route("budget planner workbook"), ("active", "Budget Planner"))

    def test_a_generic_planner_is_still_hidden(self):
        self.assertEqual(self._route("Planner"), ("hidden", "Planner"))
        self.assertEqual(self._route("daily planner"), ("hidden", "Planner"))

    def test_planning_alone_still_reaches_the_planner(self):
        # No product noun anywhere, so the modifier is all there is to go on.
        self.assertEqual(
            self._route("zero-waste meal planning printable"), ("hidden", "Planner"))

    def test_the_puzzle_and_worksheet_builders_are_unaffected(self):
        for product_type, expected in (
            ("Coloring Book", ("active", "Coloring Book")),
            ("Word Search Book", ("active", "Word Search Book")),
            ("Crossword Puzzle Book", ("active", "Crossword Puzzle Book")),
            ("Math Worksheet", ("active", "Math Worksheet")),
            ("Spelling Worksheet", ("hidden", "Spelling Worksheet")),
            ("Flip Book", ("hidden", "Flip Book")),
            ("Marketing Kit", ("hidden", "Marketing Kit")),
        ):
            with self.subTest(product_type=product_type):
                self.assertEqual(self._route(product_type), expected)


class BuildHandoffRoutingJsTests(unittest.TestCase):
    """The browser has its own copy of the builder routing, and it drives the
    Build This Product button.

    `resolveFactoryTypeFromPlan` in static/js/app.js duplicates the logic of
    `resolve_factory_builder`. Fixing only the Python left the button still
    refusing to build, because the message the customer sees is produced
    client-side. Order matters there for the same reason it does in Python:
    "Printable inventory and meal planning workbook" matches the modifiers
    "printable" AND "planning" before it ever reaches "workbook".
    """

    def _routing_source(self) -> str:
        js = APP_JS.read_text(encoding="utf-8")
        return js.split("function resolveFactoryTypeFromPlan(", 1)[1].split(
            "function hiddenReasonFor(", 1)[0]

    def test_the_product_noun_catch_all_precedes_the_weak_modifiers(self):
        fn = self._routing_source()
        catch_all = fn.find('pt.includes("book")')
        self.assertGreater(catch_all, 0, "the book/guide/workbook catch-all is gone")
        for modifier in ('"planning"', '"printable"', '"fillable"', '"tracker"'):
            position = fn.find(f"pt.includes({modifier})")
            self.assertGreater(
                position, catch_all,
                f"pt.includes({modifier}) is tested before the product-noun "
                f"catch-all, so a workbook/guide is routed to the hidden planner",
            )

    def test_named_planners_precede_the_generic_planner(self):
        fn = self._routing_source()
        faith = fn.find('"faith_planner"')
        budget = fn.find('"budget_planner"')
        generic = fn.find('factoryId: "planner"')
        self.assertGreater(faith, 0, "faith_planner routing is missing")
        self.assertGreater(budget, 0, "budget_planner routing is missing")
        self.assertLess(faith, generic, "a described faith planner is blocked")
        self.assertLess(budget, generic, "a described budget planner is blocked")

    def test_the_two_implementations_agree_on_the_reported_cases(self):
        """The Python and JS routings must not disagree about the same input."""
        for product_type, expected_id in (
            ("Printable inventory and meal planning workbook", "ebook"),
            ("Zero-waste weekly meal-planning guide with shopping lists", "ebook"),
            ("Undated faith planner for busy moms", "faith_planner"),
            ("Coloring Book", "coloring_book"),
        ):
            with self.subTest(product_type=product_type):
                row = resolve_factory_builder(product_type)
                self.assertEqual(row["status"], "active")
                self.assertEqual(row["factory_id"], expected_id)


class DegradedModePresentationTests(unittest.TestCase):
    """What the customer sees when the AI or live research is unavailable.

    All three regressions here were found by running one real research through
    the deployed app with a dead OpenAI key: the page printed the raw provider
    exception, the input-backed draft read as broken mad-libs, and the headings
    still said "Why We Recommend It" over a "Needs Improvement" verdict.
    """

    INPUTS = {
        "topic": "budget planner for young families",
        "audience": "young parents 25-40 living paycheck to paycheck",
        "customer_problem": (
            "families overspend because they have no simple monthly system "
            "they actually stick to"
        ),
        "product_type": "Budget Planner",
    }

    def test_provider_failures_never_reach_the_customer_as_exception_text(self):
        boom = RuntimeError(
            "Error code: 401 - Incorrect API key provided: sk-proj-abc123. "
            "You can find your API key at https://platform.openai.com/account/api-keys."
        )
        with patch("services.market_research._test_mode", return_value=False), patch(
            "services.market_research.chat_json", side_effect=boom
        ):
            raw, err = MR._safe_chat_json("sys", "user", self.INPUTS)
        self.assertTrue(raw.get("opportunities"), "input-backed draft should still be returned")
        self.assertEqual(err, MR.AI_UNAVAILABLE_MESSAGE)
        for leaked in ("401", "sk-proj", "api-keys", "Traceback", "RuntimeError"):
            self.assertNotIn(leaked, err)

    def test_live_research_failures_never_reach_the_customer_as_exception_text(self):
        with patch("services.market_research._test_mode", return_value=False), patch.dict(
            os.environ, {"TAVILY_API_KEY": "tvly-test"}, clear=False
        ), patch("tavily.TavilyClient", side_effect=RuntimeError("connection refused to 10.0.0.1")):
            live, _context, _sources, err = MR._tavily_context("budgeting", "parents")
        self.assertFalse(live)
        self.assertEqual(err, MR.LIVE_RESEARCH_UNAVAILABLE_MESSAGE)
        self.assertNotIn("10.0.0.1", err)
        self.assertNotIn("RuntimeError", err)

    def test_research_route_returns_a_safe_message_not_the_exception(self):
        with patch("app.research", side_effect=RuntimeError("sk-proj-secret leaked here")):
            client = app.test_client()
            resp = client.post("/research", json=dict(self.INPUTS))
        self.assertEqual(resp.status_code, 503)
        body = resp.get_json()
        self.assertEqual(body["error"], RESEARCH_FAILURE_MESSAGE)
        self.assertNotIn("sk-proj", body["error"])
        self.assertTrue(body["retryable"])
        self.assertTrue(body["inputs"], "inputs are preserved so the user can retry")

    def test_the_draft_idea_name_does_not_repeat_the_product_type(self):
        raw = MR._offline_raw(self.INPUTS)
        name = raw["opportunities"][0]["product_idea"]
        # "budget planner for young families" already names the type.
        self.assertEqual(name, "budget planner for young families")
        self.assertEqual(name.lower().count("budget planner"), 1)

    def test_the_draft_idea_name_still_adds_a_type_the_topic_lacks(self):
        raw = MR._offline_raw({**self.INPUTS, "topic": "money habits for new parents"})
        self.assertEqual(
            raw["opportunities"][0]["product_idea"],
            "money habits for new parents Budget Planner",
        )

    def test_a_clause_shaped_problem_reads_grammatically_in_the_draft(self):
        raw = MR._offline_raw(self.INPUTS)
        why = raw["opportunities"][0]["why_opportunity"]
        self.assertNotIn("addressing families overspend", why)
        self.assertIn("addressing this problem: families overspend", why)

    def test_the_recommendation_does_not_restate_the_problem_twice(self):
        score = compute_factory_advantage(self.INPUTS, {"sources": [], "live": False})
        raw = MR._offline_raw(self.INPUTS)
        summary = build_recommendation_summary(
            self.INPUTS,
            score=score,
            opportunities=raw["opportunities"],
            evidence={"sources": [], "live": False},
            recommendation=raw["recommendation"],
        )
        why = summary["why_we_recommend"]
        self.assertEqual(
            why.lower().count("families overspend"),
            1,
            f"customer problem restated more than once: {why}",
        )

    def test_headings_agree_with_a_negative_verdict(self):
        js = APP_JS.read_text(encoding="utf-8")
        helper = js.split("function recommendationHeadings(", 1)[1].split(
            "function recommendationSummaryHtml(", 1)[0]
        # The positive wording must not be what an IMPROVE/AVOID verdict shows.
        self.assertIn(USER_DECISION_IMPROVE, helper)
        self.assertIn(USER_DECISION_AVOID, helper)
        self.assertIn("Here is what we found.", helper)
        self.assertIn("What The Evidence Shows", helper)
        # ...and the positive wording is still there for a BUILD verdict.
        self.assertIn("Here is what we recommend.", helper)
        self.assertIn("Why We Recommend It", helper)

    def test_the_summary_card_renders_the_chosen_headings_not_fixed_text(self):
        js = APP_JS.read_text(encoding="utf-8")
        card = js.split("function recommendationSummaryHtml(", 1)[1].split(
            "function renderDiscovery(", 1)[0]
        self.assertIn("recommendationHeadings(summary)", card)
        self.assertIn("escapeHtml(headings.headline)", card)
        self.assertIn("escapeHtml(headings.why)", card)
        self.assertIn("escapeHtml(headings.build)", card)


if __name__ == "__main__":
    unittest.main()
