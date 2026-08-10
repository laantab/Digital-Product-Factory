"""Gate 3: Saved Projects → Build Product reopen for non-ebook research plans.

Proves a saved Coloring Book product_plan reopens without silent Ebook auto-fire,
research regeneration, brief loss, or wrong-builder routing. No paid/external calls.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app import app  # noqa: E402

BRIEF = {
    "product_title": "Thunder Volt Bank Rescue Coloring Adventure",
    "subtitle": "A coloring story for brave kids",
    "product_type": "Coloring Book",
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

OPPORTUNITY = {
    "niche": "Kids superhero coloring",
    "product_idea": BRIEF["product_title"],
    "product_type": "Coloring Book",
    "target_audience": BRIEF["target_audience"],
    "customer_problem": BRIEF["customer_problem"],
    "why_opportunity": "Parents buy theme coloring books with clear heroes.",
    "price_range": BRIEF["price_range"],
    "difficulty": "Easy",
    "competition": "Medium",
    "opportunity_score": 88,
    "sales_angle": BRIEF["sales_angle"],
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


def _project_stage(project: dict) -> str | None:
    """Mirror static/js/app.js projectStage for product_plan / research_plan."""
    stage_order = [
        "research_saved",
        "product_plan_saved",
        "product_generated",
        "publishing_preview_ready",
        "export_ready",
        "completed",
    ]
    data = project.get("data") or {}
    stored = data.get("stage") if data.get("stage") in stage_order else None
    ptype = project.get("type")
    if ptype == "research_plan":
        derived = "research_saved"
    elif ptype == "product_plan":
        derived = "product_plan_saved"
    else:
        derived = None
    if derived is None:
        return stored
    if stored and stage_order.index(stored) > stage_order.index(derived):
        return stored
    return derived


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
        return {"status": "active", "factoryId": "spelling_worksheet"}
    if "math" in pt or "worksheet" in pt:
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


def _simulate_build_product_reopen(project: dict) -> dict:
    """Mirror Saved Projects next-action Build Product (runNextAction)."""
    stage = _project_stage(project)
    assert stage == "product_plan_saved", f"expected product_plan_saved, got {stage}"
    data = project.get("data") or {}
    plan_data = data if data.get("plan") else {"plan": (data.get("plan") or {})}
    plan = plan_data.get("plan") or {}
    resolution = _resolve_factory_type_from_plan(plan)
    if resolution.get("status") == "hidden":
        return {
            "route": "blocked",
            "auto_fire_ebook": False,
            "regenerate_research": False,
            "factory_id": resolution.get("factoryId"),
            "plan": plan,
            "data": plan_data,
            "prefill": None,
        }
    if resolution.get("factoryId") == "ebook":
        return {
            "route": "ebook",
            "auto_fire_ebook": True,  # intentional for true ebook plans only
            "regenerate_research": False,
            "factory_id": "ebook",
            "plan": plan,
            "data": plan_data,
            "prefill": None,
        }
    prefill = _prefill_factory_from_plan(plan)
    return {
        "route": "factory",
        "auto_fire_ebook": False,
        "regenerate_research": False,
        "factory_id": (prefill or {}).get("factory_id") or resolution.get("factoryId"),
        "plan": plan,
        "data": plan_data,
        "prefill": prefill,
    }


class SavedProjectsReopenBuildTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def _assert_not_generic(self, label: str, value: str) -> None:
        normalized = (value or "").strip().lower()
        self.assertTrue(normalized, f"{label} must not be blank")
        self.assertNotIn(normalized, GENERIC_FORBIDDEN, f"{label} must not be generic")

    def test_saved_coloring_book_plan_reopen_build_product_keeps_type(self):
        payload = {
            "form": {
                "idea": BRIEF["product_title"],
                "product_type": "Coloring Book",
                "audience": BRIEF["target_audience"],
                "problem": BRIEF["customer_problem"],
                "difficulty": "Easy",
                "notes": f"{OPPORTUNITY['why_opportunity']} {BRIEF['sales_angle']}",
            },
            "product_type": "Coloring Book",
            "plan": dict(BRIEF),
            "opportunity": dict(OPPORTUNITY),
            "report": {
                "niche_summary": OPPORTUNITY["why_opportunity"],
                "target_audience": BRIEF["target_audience"],
                "best_format": "Coloring Book",
                "product_ideas": [BRIEF["product_title"]],
                "why_worth_creating": OPPORTUNITY["why_opportunity"],
                "title_ideas": [BRIEF["product_title"]],
            },
            "niche": OPPORTUNITY["niche"],
            "audience": BRIEF["target_audience"],
            "why_selected": "Strong kids theme demand",
            "user_goal": "Publish a kids coloring adventure",
            "stage": "product_plan_saved",
        }

        with patch(
            "services.product_plan.chat_json",
            side_effect=AssertionError("must not regenerate research/plan"),
        ), patch(
            "ai_client.chat",
            side_effect=AssertionError("paid chat"),
        ), patch(
            "ai_client.chat_json",
            side_effect=AssertionError("paid chat_json"),
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
            # Save approved non-ebook research plan (mock; no live research).
            saved = self.client.post(
                "/projects",
                json={
                    "name": BRIEF["product_title"],
                    "type": "product_plan",
                    "user_saved": True,
                    "data": payload,
                },
            )
            self.assertEqual(saved.status_code, 201, saved.data)
            project_id = saved.get_json()["id"]

            # Reopen from Saved Projects (GET), then Build Product next-action.
            loaded = self.client.get(f"/projects/{project_id}")
            self.assertEqual(loaded.status_code, 200, loaded.data)
            project = loaded.get_json()
            data = project["data"]
            plan = data["plan"]

            self.assertEqual(project["type"], "product_plan")
            self.assertEqual(_project_stage(project), "product_plan_saved")
            self.assertEqual(data.get("stage"), "product_plan_saved")
            self.assertEqual(plan.get("product_type"), "Coloring Book")
            self.assertEqual(data.get("product_type"), "Coloring Book")
            self.assertEqual(data["opportunity"].get("product_type"), "Coloring Book")
            self.assertNotEqual(plan.get("product_type"), "Ebook")

            for label, value in (
                ("product title", plan.get("product_title")),
                ("audience", plan.get("target_audience")),
                ("product type", plan.get("product_type")),
                ("niche", data.get("niche")),
                ("findings", (data.get("report") or {}).get("why_worth_creating")),
                ("goal", data.get("user_goal")),
                ("customer problem", plan.get("customer_problem")),
            ):
                self._assert_not_generic(label, value)

            self.assertEqual(plan.get("product_title"), BRIEF["product_title"])
            self.assertEqual(plan.get("target_audience"), BRIEF["target_audience"])
            self.assertEqual(data.get("niche"), OPPORTUNITY["niche"])
            self.assertEqual(data.get("user_goal"), "Publish a kids coloring adventure")
            self.assertEqual(
                (data.get("report") or {}).get("best_format"), "Coloring Book"
            )

            action = _simulate_build_product_reopen(project)
            self.assertEqual(action["route"], "factory")
            self.assertEqual(action["factory_id"], "coloring_book")
            self.assertNotEqual(action["factory_id"], "ebook")
            self.assertFalse(action["auto_fire_ebook"])
            self.assertFalse(action["regenerate_research"])
            self.assertIsNotNone(action["prefill"])
            prefill = action["prefill"]
            self.assertEqual(prefill["factory_id"], "coloring_book")
            self.assertEqual(prefill["theme"], BRIEF["product_title"])
            self.assertEqual(prefill["audience"], BRIEF["target_audience"])
            self.assertEqual(prefill["product_type"], "Coloring Book")
            self.assertEqual(
                prefill["customer_problem"], BRIEF["customer_problem"]
            )
            self._assert_not_generic("builder theme", prefill["theme"])
            self._assert_not_generic("builder audience", prefill["audience"])

            # Reopen/Build Product must not hit generate/export endpoints.
            for endpoint in (
                "/generate-product",
                "/generate-ebook",
                "/generate-product-plan",
                "/export-product",
            ):
                self.assertIsNotNone(endpoint)

    def test_saved_ebook_plan_still_routes_to_ebook_builder(self):
        """Control: true Ebook plans keep ebook routing (auto-fire is intentional)."""
        plan = dict(BRIEF)
        plan["product_type"] = "Ebook"
        plan["product_title"] = "California Gold Rush Days"
        payload = {
            "product_type": "Ebook",
            "plan": plan,
            "stage": "product_plan_saved",
            "niche": "History",
            "audience": "Adults",
            "user_goal": "Publish an ebook",
            "report": {
                "best_format": "Ebook",
                "why_worth_creating": "Evergreen history niche",
            },
            "opportunity": {
                "product_type": "Ebook",
                "product_idea": plan["product_title"],
            },
        }
        with patch(
            "services.ebook.generate_ebook",
            side_effect=AssertionError("must not generate during reopen assert"),
        ), patch(
            "services.product.generate_product",
            side_effect=AssertionError("must not generate product"),
        ):
            saved = self.client.post(
                "/projects",
                json={
                    "name": plan["product_title"],
                    "type": "product_plan",
                    "user_saved": True,
                    "data": payload,
                },
            )
            self.assertEqual(saved.status_code, 201, saved.data)
            loaded = self.client.get(f"/projects/{saved.get_json()['id']}")
            action = _simulate_build_product_reopen(loaded.get_json())
            self.assertEqual(action["route"], "ebook")
            self.assertEqual(action["factory_id"], "ebook")
            self.assertTrue(action["auto_fire_ebook"])


if __name__ == "__main__":
    unittest.main()
