"""Typed visual requirement model and honest completion gating.

Zero paid/external calls. Proves:
  1. Six checklists cannot satisfy six required photographs.
  2. A table cannot satisfy a photograph requirement.
  3. A decorative image cannot satisfy an instructional requirement.
  4. A placeholder cannot satisfy anything.
  5. A verified photo can satisfy a photo requirement.
  6. An approved instructional illustration can satisfy a requirement that
     explicitly allows either a photo or an illustration.
  7. A business book is not forced to include irrelevant people photographs.
  8. A physical-instruction book cannot complete without demonstrations.
  9. Approved/locked ebook projects are not mutated by this layer (covered by
     the existing services.ebook_local_package mutation-policy test; this
     file adds a direct confirmation for the new typed layer specifically).
  10. The local no-network fallback remains available but reports missing
      photo requirements honestly instead of falsely claiming completion.
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""
os.environ["PEXELS_API_KEY"] = ""

from services.ebook_visual_requirements import (  # noqa: E402
    CATEGORY_CALLOUT,
    CATEGORY_CHECKLIST,
    CATEGORY_COMPARISON_TABLE,
    CATEGORY_DECORATIVE,
    CATEGORY_ILLUSTRATION,
    CATEGORY_PHOTO,
    CATEGORY_PLACEHOLDER,
    classify_aid_category,
    validate_visual_plan_typed,
)
from services.ebook_factory_pipeline import (  # noqa: E402
    ebook_project_readiness,
    visual_progress_message,
)


def _movement_chapter(name: str) -> str:
    """A chapter with clear physical-instruction structure (form/technique/
    common mistakes language), matching what a real fitness-instruction
    manuscript looks like -- not tied to any specific book or topic string.
    """
    return (
        f"## {name}\n\n"
        f"### Purpose\nWhy this movement matters.\n\n"
        f"### Setup and starting position\nHow to set up your stance and grip before you begin.\n\n"
        f"### Step-by-step form\n1. Hinge at the hips.\n2. Keep a neutral spine.\n3. Drive through the heels.\n\n"
        f"### Common mistakes\n- Rounding the back\n- Rushing the setup\n\n"
        f"### Regressions\nAn easier version of this position for beginners.\n"
    )


def _plain_chapter(name: str, body: str = "") -> str:
    return f"## {name}\n\n{body or 'General narrative content with no special structure.'}\n"


def _checklist_aid(chapter: str) -> dict:
    return {
        "type": "checklist",
        "title": f"{chapter} checklist",
        "caption": "Actions from this chapter.",
        "items": ["Step one", "Step two", "Step three"],
    }


def _table_aid() -> dict:
    return {
        "type": "table",
        "title": "Reference table",
        "caption": "A table.",
        "table": {"headers": ["A", "B"], "rows": [["1", "2"], ["3", "4"]]},
    }


def _decorative_aid() -> dict:
    return {"type": "decorative", "title": "Divider", "caption": ""}


def _placeholder_photo_aid() -> dict:
    # A photo-type aid with no verified local file -- the exact shape a
    # rejected/unresolved Pexels search or a bare image_prompt leaves behind.
    return {"type": "stock photo", "title": "Unresolved photo", "match_status": "reject", "has_file": False}


def _verified_photo_aid() -> dict:
    return {
        "type": "stock photo",
        "title": "Verified photo",
        "has_file": True,
        "rendered": True,
        "match_status": "pass",
        "asset_path": "exports/pkg/visuals/v0.jpg",
    }


def _verified_illustration_aid() -> dict:
    return {
        "type": "infographic",
        "title": "Verified illustration",
        "has_file": True,
        "rendered": True,
        "asset_path": "exports/pkg/visuals/illustration.png",
    }


class TestVisualTaxonomyClassification(unittest.TestCase):
    def test_01_six_checklists_do_not_satisfy_six_photo_requirements(self):
        content = "".join(_movement_chapter(f"Movement {i}") for i in range(1, 7))
        visual_plan = {
            "chapters": [
                {"chapter": f"Movement {i}", "aids": [_checklist_aid(f"Movement {i}")]}
                for i in range(1, 7)
            ]
        }
        typed = validate_visual_plan_typed(
            visual_plan, content_md=content, title="Six Movements", topic="strength training"
        )
        self.assertEqual(typed["required_instructional_count"], 6)
        self.assertEqual(typed["verified_instructional_count"], 0)
        self.assertEqual(len(typed["unresolved_visual_requirements"]), 6)
        self.assertFalse(typed["visual_requirements_met"])

    def test_02_table_does_not_satisfy_photo_requirement(self):
        self.assertEqual(classify_aid_category(_table_aid()), CATEGORY_COMPARISON_TABLE)
        content = _movement_chapter("The Deadlift")
        plan = {"chapters": [{"chapter": "The Deadlift", "aids": [_table_aid()]}]}
        typed = validate_visual_plan_typed(plan, content_md=content, title="Kettlebell Basics", topic="kettlebell")
        self.assertEqual(len(typed["unresolved_visual_requirements"]), 1)
        self.assertEqual(typed["unresolved_visual_requirements"][0]["chapter"], "The Deadlift")

    def test_03_decorative_does_not_satisfy_instructional_requirement(self):
        self.assertEqual(classify_aid_category(_decorative_aid()), CATEGORY_DECORATIVE)
        content = _movement_chapter("The Swing")
        plan = {"chapters": [{"chapter": "The Swing", "aids": [_decorative_aid()]}]}
        typed = validate_visual_plan_typed(plan, content_md=content, title="Kettlebell Basics", topic="kettlebell")
        self.assertEqual(len(typed["unresolved_visual_requirements"]), 1)
        self.assertEqual(typed["decorative_component_count"], 1)

    def test_04_placeholder_satisfies_nothing(self):
        self.assertEqual(classify_aid_category(_placeholder_photo_aid()), CATEGORY_PLACEHOLDER)
        self.assertEqual(classify_aid_category({}), CATEGORY_PLACEHOLDER)
        self.assertEqual(classify_aid_category(None), CATEGORY_PLACEHOLDER)
        content = _movement_chapter("The Press")
        plan = {"chapters": [{"chapter": "The Press", "aids": [_placeholder_photo_aid()]}]}
        typed = validate_visual_plan_typed(plan, content_md=content, title="Kettlebell Basics", topic="kettlebell")
        self.assertEqual(len(typed["unresolved_visual_requirements"]), 1)
        self.assertEqual(typed["rejected_or_missing_count"], 1)

    def test_05_verified_photo_satisfies_photo_requirement(self):
        self.assertEqual(classify_aid_category(_verified_photo_aid()), CATEGORY_PHOTO)
        content = _movement_chapter("The Row")
        plan = {"chapters": [{"chapter": "The Row", "aids": [_verified_photo_aid()]}]}
        typed = validate_visual_plan_typed(plan, content_md=content, title="Kettlebell Basics", topic="kettlebell")
        self.assertEqual(typed["unresolved_visual_requirements"], [])
        self.assertEqual(typed["verified_instructional_count"], 1)
        self.assertTrue(typed["visual_requirements_met"])

    def test_06_verified_illustration_satisfies_demonstration_requirement(self):
        self.assertEqual(classify_aid_category(_verified_illustration_aid()), CATEGORY_ILLUSTRATION)
        content = _movement_chapter("The Carry")
        plan = {"chapters": [{"chapter": "The Carry", "aids": [_verified_illustration_aid()]}]}
        typed = validate_visual_plan_typed(plan, content_md=content, title="Kettlebell Basics", topic="kettlebell")
        self.assertEqual(typed["unresolved_visual_requirements"], [])
        self.assertEqual(typed["verified_instructional_count"], 1)

    def test_07_business_book_not_forced_into_people_photographs(self):
        content = (
            _plain_chapter("Pricing Your Services", "Compare hourly versus flat-rate pricing options.")
            + _plain_chapter("Invoicing Workflow", "A repeatable monthly invoicing workflow.")
        )
        plan = {
            "chapters": [
                {"chapter": "Pricing Your Services", "aids": [_table_aid()]},
                {"chapter": "Invoicing Workflow", "aids": [_checklist_aid("Invoicing Workflow")]},
            ]
        }
        typed = validate_visual_plan_typed(
            plan, content_md=content, title="Freelance Budgeting Systems", topic="business budgeting"
        )
        # No demonstration requirement should ever be raised for a business
        # book -- a checklist is a legitimate, complete choice here.
        kinds = {c["requirement_kind"] for c in typed["chapter_requirements"]}
        self.assertNotIn("demonstration", kinds)
        # The pricing comparison chapter's table requirement is satisfied.
        self.assertEqual(typed["unresolved_visual_requirements"], [])

    def test_08_physical_instruction_book_cannot_complete_without_demonstrations(self):
        content = "".join(_movement_chapter(f"Movement {i}") for i in range(1, 4))
        plan = {
            "chapters": [
                {"chapter": f"Movement {i}", "aids": [_checklist_aid(f"Movement {i}")]}
                for i in range(1, 4)
            ]
        }
        data = {
            "product_type": "ebook",
            "title": "Bodyweight Strength Basics",
            "content": content,
            "fields": {"topic": "bodyweight strength training"},
            "visual_plan": plan,
            "cover_design": {
                "workflow": "photo_backed",
                "selected_layout": "cover-a",
                "source": {"sha256": "a" * 64},
            },
            "package_id": "unit-test-pkg",
        }
        state = ebook_project_readiness(data)
        self.assertFalse(state["ebook_ready"])
        self.assertFalse(state["visual_requirements_met"])
        self.assertGreater(len(state["unresolved_visual_requirements"]), 0)
        # The message must name the specific unresolved chapter, not just a
        # raw "N of N visuals stored on disk" file count.
        self.assertIn("required demonstrations verified", state["visual_status_message"])

    def test_09_readiness_computation_does_not_mutate_input_plan(self):
        # This layer is read-only over the project dict; the existing
        # services.ebook_local_package mutation-policy tests already prove
        # APPROVED/LOCKED ebooks reject ensure_ebook_visual_package() writes
        # (test_final_automated_customer_flow_pass3.py::test_09_...). Here we
        # confirm ebook_project_readiness() itself never mutates its input.
        content = _movement_chapter("The Goblet Squat")
        plan = {"chapters": [{"chapter": "The Goblet Squat", "aids": [_checklist_aid("The Goblet Squat")]}]}
        data = {
            "product_type": "ebook",
            "title": "Kettlebell Basics",
            "content": content,
            "fields": {"topic": "kettlebell"},
            "visual_plan": plan,
            "cover_design": {},
            "package_id": "unit-test-pkg-2",
        }
        import copy

        before = copy.deepcopy(data)
        ebook_project_readiness(data)
        self.assertEqual(data, before)

    def test_10_local_fallback_reports_missing_photos_honestly(self):
        from services.ebook_local_package import build_local_ebook_package

        content = "".join(_movement_chapter(f"Movement {i}") for i in range(1, 4))
        built = build_local_ebook_package("Bodyweight Basics", content, {"topic": "bodyweight training"})
        # The zero-paid-API fallback is still allowed to run (no network
        # calls) -- it just must not be reported as visually complete when
        # it only produced text-derived aids for a demonstration-led book.
        data = {
            "product_type": "ebook",
            "title": built["title"],
            "content": built["content"],
            "fields": built["fields"],
            "visual_plan": built["visual_plan"],
            "cover_design": built["cover_design"],
            "package_id": built["package_id"],
        }
        state = ebook_project_readiness(data)
        self.assertFalse(state["ebook_ready"])
        self.assertFalse(state.get("visual_requirements_met", True))

    def test_11_message_backward_compatible_without_typed_arg(self):
        # visual_progress_message(counts) with no typed argument keeps its
        # original behavior for any caller/test that hasn't been updated.
        msg = visual_progress_message(
            {"required_visual_count": 22, "rendered_visual_count": 21, "missing_photo_count": 1}
        )
        self.assertEqual(msg, "21 of 22 visuals stored on disk · 1 photograph still needs retrieval.")


if __name__ == "__main__":
    unittest.main()
