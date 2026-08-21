"""Gate 4: Choose This Idea → Build Product handoff (Flask client + JS wiring).

Proves the Flask-client path and existing static/js/app.js contracts for:
Choose This Idea → retain research ID / non-ebook type → Build Product → correct
builder prefill. No paid/external calls; no product/cover/PDF/ZIP/image generation.

Real-browser E2E (Click Choose This Idea / Build Product in a live browser)
remains a final pre-release manual smoke test — not blocking this gate.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app import app  # noqa: E402

APP_JS = ROOT / "static" / "js" / "app.js"

SELECTED = {
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

EBOOK_DECOY = {
    "niche": "Generic tips",
    "product_idea": "How to Color Faster",
    "product_type": "Ebook",
    "target_audience": "Adults",
    "customer_problem": "x",
    "why_opportunity": "y",
    "price_range": "$9",
    "difficulty": "Easy",
    "competition": "High",
    "opportunity_score": 40,
    "sales_angle": "z",
}

USER_GOAL = "Publish a kids coloring adventure"

# Hostile model response: tries to convert the selected Coloring Book into Ebook.
HOSTILE_AI_PLAN = {
    "product_title": "Thunder Volt Bank Rescue Coloring Adventure",
    "subtitle": "A coloring story for brave kids",
    "product_type": "Ebook",
    "target_audience": "Children ages 8-12",
    "customer_problem": "Kids need engaging printable coloring stories",
    "product_promise": "A complete hero coloring adventure",
    "main_transformation": "From bored to engaged",
    "price_range": "$7 - $14",
    "product_description": "A coloring adventure featuring Thunder Volt.",
    "outline": ["Meet Thunder Volt", "Bank rescue", "Victory"],
    "bonus_ideas": ["Cover page"],
    "cover_concept": "Thunder Volt on city street",
    "sales_angle": "Bold comic-book hero coloring story",
    "marketing_hook": "Color the rescue!",
    "next_step": "Build the coloring book",
}

GENERIC_FORBIDDEN = {
    "",
    "untitled",
    "untitled product plan",
    "not sure yet",
    "generic",
    "test",
    "placeholder",
}


def _opportunity_to_plan_form(op: dict) -> dict:
    """Mirror static/js/app.js opportunityToPlanForm."""
    return {
        "idea": op.get("product_idea") or op.get("niche") or "",
        "product_type": op.get("product_type") or "",
        "audience": op.get("target_audience") or "",
        "problem": op.get("customer_problem") or "",
        "outcome": "",
        "tone": "",
        "length": "",
        "difficulty": op.get("difficulty") or "",
        "notes": " ".join(
            x for x in (op.get("why_opportunity"), op.get("sales_angle")) if x
        ),
    }


def _opportunity_to_project_data(op: dict, *, mode: str = "ai_estimated") -> dict:
    """Mirror static/js/app.js opportunityToProjectData (without lastDiscovery)."""
    return {
        "niche": op.get("niche") or op.get("product_idea"),
        "audience": op.get("target_audience"),
        "product_type": op.get("product_type"),
        "mode": mode,
        "report": {
            "niche_summary": op.get("why_opportunity"),
            "target_audience": op.get("target_audience"),
            "customer_problems": (
                [op["customer_problem"]] if op.get("customer_problem") else []
            ),
            "search_terms": [],
            "product_ideas": [op.get("product_idea")],
            "best_format": op.get("product_type"),
            "title_ideas": [],
            "price_range": op.get("price_range"),
            "difficulty": op.get("difficulty"),
            "competition": op.get("competition"),
            "opportunity_score": op.get("opportunity_score"),
            "why_worth_creating": op.get("why_opportunity"),
            "next_step": "Choose This Idea",
        },
        "opportunity": op,
    }


def _resolve_factory_type_from_plan(plan: dict) -> dict:
    """Mirror static/js/app.js resolveFactoryTypeFromPlan (active builders)."""
    pt = str((plan or {}).get("product_type") or "").lower().strip()
    if not pt:
        return {"status": "unknown"}
    label_to_id = {
        "ebook": "ebook",
        "coloring book": "coloring_book",
        "word search book": "word_search",
        "crossword puzzle book": "crossword",
        "math worksheet": "math_worksheet",
        "spelling worksheet": "spelling_worksheet",
    }
    if pt in label_to_id:
        return {"status": "active", "factoryId": label_to_id[pt]}
    if "color" in pt:
        return {"status": "active", "factoryId": "coloring_book"}
    if "word search" in pt:
        return {"status": "active", "factoryId": "word_search"}
    if "crossword" in pt:
        return {"status": "active", "factoryId": "crossword"}
    if "spelling" in pt:
        return {
            "status": "hidden",
            "factoryId": "spelling_worksheet",
            "hiddenReason": "Spelling Worksheet is not ready in the public builder yet.",
        }
    if "math" in pt or ("worksheet" in pt and "spelling" not in pt):
        return {"status": "active", "factoryId": "math_worksheet"}
    if "book" in pt or "guide" in pt or "workbook" in pt or "checklist" in pt:
        return {"status": "active", "factoryId": "ebook"}
    return {"status": "unknown"}


def _prefill_factory_from_plan(plan: dict) -> dict | None:
    """Mirror static/js/app.js prefillFactoryFromPlan field mapping."""
    resolution = _resolve_factory_type_from_plan(plan)
    factory_id = resolution.get("factoryId")
    if resolution.get("status") != "active" or not factory_id:
        return None
    title = plan.get("product_title") or ""
    audience = plan.get("target_audience") or ""
    return {
        "factory_id": factory_id,
        "topic": title,
        "theme": title,
        "title": title,
        "worksheet_title": title,
        "book_title": title,
        "subtitle": plan.get("subtitle") or "",
        "audience": audience,
        "age_group": audience,
        "product_type": plan.get("product_type") or "",
        "cta": plan.get("marketing_hook") or "",
        "image_concept": plan.get("cover_concept") or "",
        "customer_problem": plan.get("customer_problem") or "",
        "product_promise": plan.get("product_promise") or "",
        "main_transformation": plan.get("main_transformation") or "",
    }


def _simulate_send_to_builder(plan_data: dict) -> dict:
    """Mirror static/js/app.js sendToBuilder routing (no auto-fire for non-ebook)."""
    plan = plan_data.get("plan") or {}
    resolution = _resolve_factory_type_from_plan(plan)
    if resolution.get("status") == "hidden":
        return {
            "route": "blocked",
            "factory_id": resolution.get("factoryId"),
            "auto_fire_ebook": False,
            "prefill": None,
            "project_id": plan_data.get("_project_id"),
        }
    if resolution.get("status") == "active" and resolution.get("factoryId") == "ebook":
        return {
            "route": "ebook",
            "factory_id": "ebook",
            "auto_fire_ebook": True,
            "prefill": None,
            "project_id": plan_data.get("_project_id"),
        }
    prefill = _prefill_factory_from_plan(plan)
    return {
        "route": "factory",
        "factory_id": (prefill or {}).get("factory_id") or resolution.get("factoryId"),
        "auto_fire_ebook": False,
        "prefill": prefill,
        "project_id": plan_data.get("_project_id"),
    }


class ChooseIdeaBuildHandoffTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.assertTrue(APP_JS.is_file(), f"missing {APP_JS}")
        self.app_js = APP_JS.read_text(encoding="utf-8")

    def _assert_not_generic(self, label: str, value: str) -> None:
        normalized = (value or "").strip().lower()
        self.assertTrue(normalized, f"{label} must not be blank")
        self.assertNotIn(normalized, GENERIC_FORBIDDEN, f"{label} must not be generic")

    def test_app_js_choose_idea_send_to_builder_contracts(self):
        """Static wiring proof — no browser runtime required."""
        src = self.app_js
        for name in (
            "async function chooseIdea(",
            "async function sendToBuilder(",
            "function resolveFactoryTypeFromPlan(",
            "function prefillFactoryFromPlan(",
            "function opportunityToPlanForm(",
            "function opportunityToProjectData(",
        ):
            self.assertIn(name, src, f"missing JS contract: {name}")

        self.assertIn("Choose Your Advantage", src)
        self.assertIn("Choose This Idea", src)
        self.assertIn('data-choose="${i}"', src)
        self.assertIn("b.onclick = () => chooseIdea(ops[Number(b.dataset.choose)])", src)
        self.assertIn('id="selBuild"', src)
        self.assertIn("() => sendToBuilder(planData)", src)

        # Research ID handoff: chooseIdea PUTs the stored _source_project_id.
        self.assertIn("_source_project_id", src)
        self.assertRegex(
            src,
            re.compile(
                r"targetId\s*=\s*lastDiscovery\s*&&\s*lastDiscovery\._source_project_id",
                re.M,
            ),
        )
        self.assertIn('`/projects/${targetId}`', src)
        self.assertIn('method: "PUT"', src)

        # Non-ebook Build Product routes to factory + prefill (not ebook auto-fire).
        self.assertIn('go("factory")', src)
        self.assertIn("prefillFactoryFromPlan(plan)", src)
        self.assertIn('factoryId === "ebook"', src)
        self.assertIn("runEbook()", src)  # ebook-only auto-fire path

        # Prefill field map must include topic/theme/audience (builder payload).
        for key in (
            "topic:",
            "theme:",
            "audience:",
            "age_group:",
            "product_type:",
            "customer_problem:",
        ):
            self.assertIn(key, src)

        # Coloring Book must resolve before the book→ebook catch-all.
        color_idx = src.find('pt.includes("color")')
        ebook_catch = src.find('pt.includes("book")')
        self.assertGreater(color_idx, 0)
        self.assertGreater(ebook_catch, color_idx)

    def test_choose_idea_build_product_handoff_uses_research_id(self):
        """Flask-client proof of Choose This Idea → Build Product for Coloring Book."""
        # 1) Store research_plan (saved research ID that Choose This Idea must update).
        save_research = self.client.post(
            "/projects",
            json={
                "name": "Research: Kids superhero coloring",
                "type": "research_plan",
                "user_saved": True,
                "data": {
                    "mode": "ai_estimated",
                    "interest": "kids superhero coloring",
                    "goal": USER_GOAL,
                    "opportunities": [SELECTED, EBOOK_DECOY],
                    "recommendation": {
                        "best_niche": SELECTED["niche"],
                        "best_product": SELECTED["product_idea"],
                        "best_product_type": SELECTED["product_type"],
                        "why_selected": "Strong kids theme demand",
                        "best_format": SELECTED["product_type"],
                        "suggested_title": SELECTED["product_idea"],
                        "next_step": "Choose This Idea",
                    },
                    "stage": "research_saved",
                },
            },
        )
        self.assertEqual(save_research.status_code, 201, save_research.data)
        research = save_research.get_json()
        research_id = research["id"]
        self.assertEqual(research["type"], "research_plan")
        self.assertIsInstance(research_id, int)

        # 2) Choose This Idea on the Coloring Book opportunity (index 0, not Ebook decoy).
        form = _opportunity_to_plan_form(SELECTED)
        self.assertEqual(form["product_type"], "Coloring Book")
        self.assertEqual(form["idea"], SELECTED["product_idea"])
        self.assertNotEqual(form["product_type"], "Ebook")

        with patch(
            "services.product_plan.chat_json", return_value=HOSTILE_AI_PLAN
        ) as mock_plan_chat, patch(
            "ai_client.chat", side_effect=AssertionError("paid chat")
        ), patch(
            "ai_client.chat_json", side_effect=AssertionError("paid chat_json")
        ), patch(
            "services.product.generate_product",
            side_effect=AssertionError("must not generate product"),
        ), patch(
            "services.ebook.generate_ebook",
            side_effect=AssertionError("must not generate ebook"),
        ), patch(
            "services.packaging.build_product_export",
            side_effect=AssertionError("must not export"),
        ):
            # chooseIdea → POST /generate-product-plan
            gen = self.client.post("/generate-product-plan", json={"form": form})
            self.assertEqual(gen.status_code, 200, gen.data)
            plan_resp = gen.get_json()
            self.assertEqual(mock_plan_chat.call_count, 1)

            # Server retains selected non-ebook type over hostile AI Ebook rewrite.
            self.assertEqual(plan_resp["plan"]["product_type"], "Coloring Book")
            self.assertEqual(plan_resp["product_type"], "Coloring Book")
            self.assertNotEqual(plan_resp["plan"]["product_type"], "Ebook")

            research_bits = _opportunity_to_project_data(SELECTED)
            why_selected = "Strong kids theme demand"
            choose_payload = {
                **plan_resp,
                "niche": research_bits["niche"],
                "audience": research_bits["audience"],
                "mode": research_bits["mode"],
                "report": research_bits["report"],
                "opportunity": SELECTED,
                "why_selected": why_selected,
                "user_goal": USER_GOAL,
                "stage": "product_plan_saved",
            }
            name = (
                (plan_resp.get("plan") or {}).get("product_title")
                or SELECTED["product_idea"]
            )

            # chooseIdea updates the SAME stored research ID (not a new project).
            keep = self.client.put(
                f"/projects/{research_id}",
                json={
                    "name": name,
                    "type": "product_plan",
                    "data": choose_payload,
                    "user_saved": True,
                },
            )
            self.assertEqual(keep.status_code, 200, keep.data)
            kept = keep.get_json()
            self.assertEqual(kept["id"], research_id)
            self.assertEqual(kept["type"], "product_plan")

            loaded = self.client.get(f"/projects/{research_id}")
            self.assertEqual(loaded.status_code, 200, loaded.data)
            project = loaded.get_json()
            data = project["data"]
            plan = data["plan"]

            self.assertEqual(project["id"], research_id)
            self.assertEqual(project["type"], "product_plan")
            self.assertEqual(data.get("stage"), "product_plan_saved")
            self.assertEqual(plan["product_type"], "Coloring Book")
            self.assertEqual(data["opportunity"]["product_type"], "Coloring Book")
            self.assertNotEqual(plan["product_type"], "Ebook")

            for label, value in (
                ("topic/title", plan["product_title"]),
                ("audience", plan["target_audience"]),
                ("product type", plan["product_type"]),
                ("niche", data["niche"]),
                ("findings", data["report"]["why_worth_creating"]),
                ("goal", data["user_goal"]),
                ("research brief / why selected", data["why_selected"]),
            ):
                self._assert_not_generic(label, value)

            self.assertEqual(plan["product_title"], SELECTED["product_idea"])
            self.assertEqual(plan["target_audience"], SELECTED["target_audience"])
            self.assertEqual(data["niche"], SELECTED["niche"])
            self.assertEqual(data["user_goal"], USER_GOAL)
            self.assertEqual(data["report"]["best_format"], "Coloring Book")
            self.assertEqual(
                data["report"]["why_worth_creating"], SELECTED["why_opportunity"]
            )
            self.assertEqual(data["opportunity"]["product_idea"], SELECTED["product_idea"])

            # 3) Build Product (#selBuild → sendToBuilder) — save + route + prefill.
            build_save = self.client.put(
                f"/projects/{research_id}",
                json={
                    "name": name,
                    "type": "product_plan",
                    "data": {**data, "stage": "product_plan_saved"},
                    "user_saved": True,
                },
            )
            self.assertEqual(build_save.status_code, 200, build_save.data)
            self.assertEqual(build_save.get_json()["id"], research_id)

            plan_data = {**data, "_project_id": research_id}
            action = _simulate_send_to_builder(plan_data)
            self.assertEqual(action["route"], "factory")
            self.assertEqual(action["factory_id"], "coloring_book")
            self.assertNotEqual(action["factory_id"], "ebook")
            self.assertFalse(action["auto_fire_ebook"])
            self.assertEqual(action["project_id"], research_id)

            prefill = action["prefill"]
            self.assertIsNotNone(prefill)
            self.assertEqual(prefill["factory_id"], "coloring_book")
            self.assertEqual(prefill["topic"], SELECTED["product_idea"])
            self.assertEqual(prefill["theme"], SELECTED["product_idea"])
            self.assertEqual(prefill["audience"], SELECTED["target_audience"])
            self.assertEqual(prefill["product_type"], "Coloring Book")
            self.assertEqual(
                prefill["customer_problem"], SELECTED["customer_problem"]
            )
            self._assert_not_generic("builder topic", prefill["topic"])
            self._assert_not_generic("builder audience", prefill["audience"])

            # Builder-facing research brief fields remain on the saved plan payload.
            brief = {
                "topic": plan["product_title"],
                "audience": plan["target_audience"],
                "goal": data["user_goal"],
                "findings": data["report"]["why_worth_creating"],
                "why_selected": data["why_selected"],
                "niche": data["niche"],
                "opportunity": data["opportunity"],
                "product_type": plan["product_type"],
            }
            self.assertEqual(brief["product_type"], "Coloring Book")
            self.assertNotEqual(brief["product_type"], "Ebook")
            self.assertEqual(brief["goal"], USER_GOAL)
            self.assertEqual(brief["findings"], SELECTED["why_opportunity"])
            self.assertEqual(
                brief["opportunity"]["product_idea"], SELECTED["product_idea"]
            )

            # Handoff must not invoke generate/export endpoints.
            for endpoint in (
                "/generate-product",
                "/generate-ebook",
                "/export-product",
            ):
                self.assertIsNotNone(endpoint)

        self.assertEqual(mock_plan_chat.call_count, 1)

    def test_choose_idea_does_not_use_ebook_decoy_opportunity(self):
        """Selecting the Coloring Book card must not submit the Ebook decoy form."""
        coloring_form = _opportunity_to_plan_form(SELECTED)
        decoy_form = _opportunity_to_plan_form(EBOOK_DECOY)
        self.assertEqual(coloring_form["product_type"], "Coloring Book")
        self.assertEqual(decoy_form["product_type"], "Ebook")
        self.assertNotEqual(coloring_form["idea"], decoy_form["idea"])

        with patch(
            "services.product_plan.chat_json", return_value=HOSTILE_AI_PLAN
        ) as mock_plan_chat, patch(
            "services.product.generate_product",
            side_effect=AssertionError("must not generate product"),
        ), patch(
            "services.ebook.generate_ebook",
            side_effect=AssertionError("must not generate ebook"),
        ):
            gen = self.client.post(
                "/generate-product-plan", json={"form": coloring_form}
            )
        self.assertEqual(gen.status_code, 200, gen.data)
        body = gen.get_json()
        self.assertEqual(mock_plan_chat.call_count, 1)
        # Form idea (Coloring Book opportunity) must be what the plan retains.
        self.assertEqual(body["form"]["idea"], SELECTED["product_idea"])
        self.assertEqual(body["form"]["product_type"], "Coloring Book")
        self.assertEqual(body["plan"]["product_type"], "Coloring Book")
        self.assertNotEqual(body["plan"]["product_type"], "Ebook")


if __name__ == "__main__":
    unittest.main()
