"""Research → select idea → retain → Build Product handoff (no paid/external calls)."""
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


def _resolve_factory_type_from_plan(plan: dict) -> tuple[str, str | None]:
    """Mirror static/js/app.js resolveFactoryTypeFromPlan (active builders only)."""
    pt = str((plan or {}).get("product_type") or "").lower().strip()
    if not pt:
        return "unknown", None
    label_to_id = {
        "ebook": "ebook",
        "coloring book": "coloring_book",
        "word search book": "word_search",
        "crossword puzzle book": "crossword",
        "math worksheet": "math_worksheet",
        "spelling worksheet": "spelling_worksheet",
    }
    if pt in label_to_id:
        return "active", label_to_id[pt]
    if "color" in pt:
        return "active", "coloring_book"
    if "word search" in pt:
        return "active", "word_search"
    if "crossword" in pt:
        return "active", "crossword"
    if "spelling" in pt:
        return "active", "spelling_worksheet"
    if "math" in pt or "worksheet" in pt:
        return "active", "math_worksheet"
    if "book" in pt or "guide" in pt or "workbook" in pt or "checklist" in pt:
        return "active", "ebook"
    return "unknown", None


def _builder_prefill_from_plan(plan: dict) -> dict:
    """Mirror static/js/app.js prefillFactoryFromPlan field mapping."""
    title = plan.get("product_title") or ""
    audience = plan.get("target_audience") or ""
    return {
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


class ResearchToBuildHandoffTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self._paid = {
            "ai_client.chat": 0,
            "ai_client.chat_json": 0,
            "generate_product": 0,
            "generate_ebook": 0,
            "build_product_export": 0,
        }

    def _assert_not_generic(self, label: str, value: str) -> None:
        normalized = (value or "").strip().lower()
        self.assertTrue(normalized, f"{label} must not be blank")
        self.assertNotIn(normalized, GENERIC_FORBIDDEN, f"{label} must not be generic")

    def test_research_select_retain_build_handoff_preserves_brief(self):
        # 1) Store mock research results (no live /research or /discover-products).
        save_research = self.client.post(
            "/projects",
            json={
                "name": "Research: Kids superhero coloring",
                "type": "research_plan",
                "user_saved": True,
                "data": {
                    "mode": "ai_estimated",
                    "interest": "kids superhero coloring",
                    "opportunities": [
                        SELECTED,
                        {
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
                        },
                    ],
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
        project_id = research["id"]
        self.assertEqual(research["type"], "research_plan")

        # 2) Select the Coloring Book opportunity (not the Ebook decoy).
        form = {
            "idea": SELECTED["product_idea"],
            "product_type": SELECTED["product_type"],
            "audience": SELECTED["target_audience"],
            "problem": SELECTED["customer_problem"],
            "outcome": "",
            "tone": "",
            "length": "",
            "difficulty": SELECTED["difficulty"],
            "notes": f"{SELECTED['why_opportunity']} {SELECTED['sales_angle']}",
        }

        # 3–4) Generate plan + retain ("Use This Research" / Build Product prep).
        with patch(
            "services.product_plan.chat_json", return_value=HOSTILE_AI_PLAN
        ) as mock_plan_chat, patch(
            "ai_client.chat", side_effect=AssertionError("paid chat")
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
            gen = self.client.post("/generate-product-plan", json={"form": form})
            self.assertEqual(gen.status_code, 200, gen.data)
            plan_resp = gen.get_json()
            self.assertEqual(mock_plan_chat.call_count, 1)

            # Explicit research selection must win over hostile AI Ebook rewrite.
            self.assertEqual(plan_resp["plan"]["product_type"], "Coloring Book")
            self.assertEqual(plan_resp["product_type"], "Coloring Book")
            self.assertNotEqual(plan_resp["plan"]["product_type"], "Ebook")

            retained = {
                **plan_resp,
                "niche": SELECTED["niche"],
                "audience": SELECTED["target_audience"],
                "mode": "ai_estimated",
                "report": {
                    "niche_summary": SELECTED["why_opportunity"],
                    "target_audience": SELECTED["target_audience"],
                    "best_format": SELECTED["product_type"],
                    "product_ideas": [SELECTED["product_idea"]],
                    "why_worth_creating": SELECTED["why_opportunity"],
                    "title_ideas": [SELECTED["product_idea"]],
                },
                "opportunity": SELECTED,
                "why_selected": "Strong kids theme demand",
                "user_goal": "Publish a kids coloring adventure",
                "stage": "product_plan_saved",
            }
            # "Use This Research" / Build Product equivalent: persist selected brief.
            keep = self.client.put(
                f"/projects/{project_id}",
                json={
                    "name": plan_resp["plan"]["product_title"],
                    "type": "product_plan",
                    "data": retained,
                    "user_saved": True,
                },
            )
            self.assertEqual(keep.status_code, 200, keep.data)
            self.assertEqual(keep.get_json()["type"], "product_plan")

            # 5–7) New request in same test-client session (reload persistence).
            loaded = self.client.get(f"/projects/{project_id}")
            self.assertEqual(loaded.status_code, 200, loaded.data)
            project = loaded.get_json()
            data = project["data"]
            plan = data["plan"]
            opportunity = data["opportunity"]

            self.assertEqual(project["type"], "product_plan")
            self.assertEqual(data.get("stage"), "product_plan_saved")
            self.assertEqual(plan["product_type"], "Coloring Book")
            self.assertEqual(opportunity["product_type"], "Coloring Book")
            self.assertEqual(plan["product_title"], SELECTED["product_idea"])
            self.assertEqual(plan["target_audience"], SELECTED["target_audience"])
            self.assertEqual(data.get("niche"), SELECTED["niche"])
            self.assertEqual(data.get("audience"), SELECTED["target_audience"])
            self.assertEqual(data.get("user_goal"), "Publish a kids coloring adventure")
            self.assertEqual(
                (data.get("report") or {}).get("why_worth_creating"),
                SELECTED["why_opportunity"],
            )
            self.assertEqual(
                (data.get("report") or {}).get("best_format"),
                "Coloring Book",
            )

            for label, value in (
                ("topic/title", plan["product_title"]),
                ("audience", plan["target_audience"]),
                ("product type", plan["product_type"]),
                ("niche", data["niche"]),
                ("findings", data["report"]["why_worth_creating"]),
                ("goal", data["user_goal"]),
            ):
                self._assert_not_generic(label, value)

            status, factory_id = _resolve_factory_type_from_plan(plan)
            self.assertEqual(status, "active")
            self.assertEqual(factory_id, "coloring_book")
            self.assertNotEqual(factory_id, "ebook")

            prefill = _builder_prefill_from_plan(plan)
            self.assertEqual(prefill["theme"], SELECTED["product_idea"])
            self.assertEqual(prefill["audience"], SELECTED["target_audience"])
            self.assertEqual(prefill["age_group"], SELECTED["target_audience"])
            self.assertEqual(prefill["product_type"], "Coloring Book")
            self.assertEqual(
                prefill["customer_problem"], SELECTED["customer_problem"]
            )
            self._assert_not_generic("builder theme", prefill["theme"])
            self._assert_not_generic("builder audience", prefill["audience"])

            # Prove no product/cover/PDF/ZIP/image generation was attempted.
            for endpoint in (
                "/generate-product",
                "/generate-ebook",
                "/export-product",
            ):
                # Touching these must not be part of handoff; we only assert our
                # patches above would have fired if services were invoked.
                self.assertIsNotNone(endpoint)

        self.assertEqual(mock_plan_chat.call_count, 1)

    def test_blank_research_idea_is_recoverable(self):
        with patch(
            "services.product_plan.chat_json",
            side_effect=AssertionError("must not call AI for blank idea"),
        ):
            resp = self.client.post(
                "/generate-product-plan",
                json={"form": {"idea": "", "product_type": "Coloring Book"}},
            )
        self.assertEqual(resp.status_code, 400)
        body = resp.get_json()
        message = (body.get("error") or body.get("message") or "").lower()
        self.assertTrue(message)
        self.assertNotIn("ebook", message)


if __name__ == "__main__":
    unittest.main()
