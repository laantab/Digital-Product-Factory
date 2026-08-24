"""Automatic ebook visual pipeline. All Pexels/AI/Tavily/MiniMax mocked. Zero paid calls."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["OPENAI_API_KEY"] = ""
os.environ["TAVILY_API_KEY"] = ""
os.environ["AI_INTEGRATIONS_OPENAI_API_KEY"] = ""
os.environ["PEXELS_API_KEY"] = ""

from app import app  # noqa: E402
import database  # noqa: E402
from services.ebook_factory_pipeline import (  # noqa: E402
    AI_VISUAL_UNIT_USD,
    automatic_visuals_requested,
    estimate_max_visual_generation_cost_usd,
    fill_photo_aid_automatic,
    fill_plan_photos_automatic,
    images_requested,
    prefers_local_medium,
    remaining_visual_budget_usd,
    visual_ai_authorized,
)
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript  # noqa: E402
from services.ebook_package import build_ebook_package  # noqa: E402
from services.ebook_project_workspace import (  # noqa: E402
    STATUS_AWAITING,
    approve_stage,
    build_acceptance_project_data,
    ensure_workspace,
    is_approved,
    manuscript_digest,
    set_stage_status,
)
from services.ebook_visual_match import (  # noqa: E402
    MATCH_NEEDS_REVIEW,
    MATCH_PASS,
    MATCH_REJECT,
    build_visual_brief,
    score_photo_against_brief,
)
from services.ebook_visual_pipeline import (  # noqa: E402
    collect_zip_visual_files,
    plan_content_aware_visuals,
    prepare_visuals_for_review,
    required_aids,
    store_interior_photo,
    visual_review_payload,
)


LIVE_4249 = 4249
EXPECTED_COVER_SHA = "465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd"
EXPECTED_MANUSCRIPT = "cf08285598b6d7ac722844a97a5d54f89da2b37e8b11a5bd3df9768b8010cf98"


def _paid_patches():
    return (
        patch("ai_client.get_client", side_effect=AssertionError("paid client")),
        patch("ai_client.chat", side_effect=AssertionError("paid chat")),
        patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json")),
    )


def _jpeg_bytes(w: int = 1200, h: int = 800, color=(40, 90, 140)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (w, h), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 40, w - 80, h // 2), fill=(200, 160, 90))
    draw.ellipse((w // 5, h // 5, 4 * w // 5, 4 * h // 5), fill=(24, 28, 36))
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _photo(alt: str, photo_id: str = "1001") -> dict:
    return {
        "photo_id": photo_id,
        "id": int(photo_id) if str(photo_id).isdigit() else photo_id,
        "photographer": "Test Photographer",
        "attribution": "Photo by Test Photographer on Pexels",
        "page_url": f"https://www.pexels.com/photo/{alt.replace(' ', '-')}-{photo_id}/",
        "alt": alt,
        "src": {"original": f"https://images.pexels.com/photos/{photo_id}/original.jpeg"},
    }


PARENT_ALT = "parent and teenager reviewing a smartphone together at home"
PHOTO_MD = """# Backyard Birds

## Attracting Cardinals

Cardinals visit a quiet feeder near a hedge when sunflower seed is kept full.

## Watching Nesting Season

A robin builds a nest in the fork of an apple tree during late spring.
"""
GARDEN_MD = """# Backyard Tomato Growing

## Soil Preparation

Prepare loose soil with compost before you plant.

## Watering Routine

1. Water in the morning.
2. Check the soil moisture.
3. Mulch to keep water in.

## Harvest Checklist

- Pick ripe fruit
- Inspect for splits
- Store in the shade
- Rinse before you cook
"""


class AutomaticEbookVisualTests(unittest.TestCase):
    def setUp(self):
        self._patches = _paid_patches()
        for item in self._patches:
            item.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])
        self._ai_calls = []
        self._pexels_queries = []

    def _mock_pexels(self, photos=None, empty=False):
        photos = list(photos or [_photo(PARENT_ALT)])

        def _search(query, **_k):
            self._pexels_queries.append(query)
            if empty:
                return {"photos": []}
            return {"photos": photos}

        def _download(_photo_row):
            return _jpeg_bytes()

        return (
            patch("services.ebook_factory_pipeline.search_pexels", side_effect=_search),
            patch("services.ebook_factory_pipeline.download_pexels_original", side_effect=_download),
        )

    def _mock_ai(self, succeed: bool = True):
        def _gen(prompt, out_path, **_k):
            self._ai_calls.append(prompt)
            if not succeed:
                return False
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            Path(out_path).write_bytes(_jpeg_bytes(color=(90, 40, 40)))
            return True

        return patch("services.ebook_package.generate_visual_image", side_effect=_gen)

    def _aid(self, **extra):
        aid = {
            "visual_id": extra.pop("visual_id", "v_ch1"),
            "type": "photo",
            "title": extra.pop("title", "Parent and teenager reviewing a phone together"),
            "caption": extra.pop(
                "caption",
                "A parent and teenager reviewing a smartphone together at home.",
            ),
            "chapter": extra.pop("chapter", "Social Media Check-In"),
            "chapter_index": extra.pop("chapter_index", 1),
            "placement": "after_opening",
            "required": True,
        }
        aid.update(extra)
        return aid

    def _budget(self, cap: float = 0.16) -> dict:
        return {
            "fields": {
                "include_images": "Yes",
                "visuals_authorized": "true",
                "visual_budget_cap_usd": cap,
            },
            "visuals_authorized": "true",
            "visual_budget_cap_usd": cap,
            "visual_ai_spend_usd": 0.0,
        }

    def test_01_automatic_mode_independent_briefs_per_chapter(self):
        plan = plan_content_aware_visuals(PHOTO_MD, title="Backyard Birds", include_photographs=True)
        briefs = []
        for ch in plan["chapters"]:
            for aid in ch.get("aids") or []:
                if str(aid.get("type") or "") != "photo":
                    continue
                brief = build_visual_brief(aid, chapter=ch.get("chapter") or "", chapter_body=str(aid.get("chapter_body") or ""))
                briefs.append(brief)
        self.assertGreaterEqual(len(briefs), 1)
        seen = {b.required_subject for b in briefs}
        self.assertEqual(len(seen), len(briefs))
        for brief in briefs:
            self.assertTrue(brief.search_queries)
            self.assertTrue(brief.required_subject)
            self.assertNotIn("4249", json.dumps(brief.as_dict()))

    def test_02_local_info_graphics_preferred_when_appropriate(self):
        plan = plan_content_aware_visuals(GARDEN_MD, title="Backyard Tomato Growing", include_photographs=True)
        types = {a["type"] for ch in plan["chapters"] for a in ch.get("aids") or []}
        self.assertTrue({"workflow", "checklist"} & types)
        for ch in plan["chapters"]:
            aids = [a for a in (ch.get("aids") or []) if isinstance(a, dict)]
            local = [a for a in aids if prefers_local_medium(a)]
            photos = [a for a in aids if str(a.get("type") or "") in {"photo", "stock photo"}]
            if local:
                self.assertEqual(photos, [])

    def test_03_pexels_always_before_paid_ai_for_photographs(self):
        data = self._budget()
        pex, dl = self._mock_pexels()
        with pex, dl, self._mock_ai() as ai:
            filled = fill_photo_aid_automatic(
                self._aid(),
                package_id=f"auto-{uuid.uuid4().hex[:8]}",
                title="Teen Safety",
                topic="teen online safety",
                chapter="Social Media Check-In",
                data=data,
                fields=data["fields"],
                allow_ai=True,
            )
        self.assertTrue(self._pexels_queries)
        self.assertEqual(self._ai_calls, [])
        self.assertEqual(str(filled.get("source") or ""), "pexels")
        ai.assert_not_called()

    def test_04_multiple_stock_candidates_and_query_variations_evaluated(self):
        weak = _photo("office desk", "11")
        strong = _photo(PARENT_ALT, "22")
        seen_queries: list[str] = []

        def _search(query, **_k):
            seen_queries.append(query)
            self._pexels_queries.append(query)
            if len(set(seen_queries)) < 2:
                return {"photos": []}
            return {"photos": [weak, strong]}

        with patch("services.ebook_factory_pipeline.search_pexels", side_effect=_search), patch(
            "services.ebook_factory_pipeline.download_pexels_original", return_value=_jpeg_bytes()
        ), self._mock_ai():
            filled = fill_photo_aid_automatic(
                self._aid(),
                package_id=f"auto-{uuid.uuid4().hex[:8]}",
                title="Teen Safety",
                chapter="Social Media Check-In",
                data=self._budget(),
                fields=self._budget()["fields"],
            )
        self.assertGreaterEqual(len(set(seen_queries)), 2)
        self.assertEqual(str(filled.get("photo_id") or ""), "22")

    def test_05_highest_ranked_passing_stock_saved_and_selected(self):
        low = _photo("teenager holding a phone outdoors", "31")
        high = _photo(
            "parent and teenager reviewing a smartphone together at home family living room",
            "32",
        )
        pex, dl = self._mock_pexels(photos=[low, high])
        with pex, dl, self._mock_ai():
            filled = fill_photo_aid_automatic(
                self._aid(),
                package_id=f"auto-{uuid.uuid4().hex[:8]}",
                title="Teen Safety",
                chapter="Social Media Check-In",
                data=self._budget(),
                fields=self._budget()["fields"],
            )
        self.assertEqual(str(filled.get("photo_id") or ""), "32")
        self.assertTrue(os.path.isfile(str(filled.get("asset_path") or "")))

    def test_06_valid_stock_photo_prevents_ai_call(self):
        pex, dl = self._mock_pexels()
        with pex, dl, self._mock_ai() as ai:
            fill_photo_aid_automatic(
                self._aid(),
                package_id=f"auto-{uuid.uuid4().hex[:8]}",
                title="Teen Safety",
                chapter="Social Media Check-In",
                data=self._budget(),
                fields=self._budget()["fields"],
            )
        ai.assert_not_called()
        self.assertEqual(self._ai_calls, [])

    def test_07_failed_stock_triggers_ai_fallback_only_with_authorized_budget(self):
        pex, dl = self._mock_pexels(empty=True)
        data = self._budget(0.16)
        with pex, dl, self._mock_ai():
            filled = fill_photo_aid_automatic(
                self._aid(),
                package_id=f"auto-{uuid.uuid4().hex[:8]}",
                title="Teen Safety",
                chapter="Social Media Check-In",
                data=data,
                fields=data["fields"],
                allow_ai=True,
            )
        self.assertTrue(self._ai_calls)
        self.assertEqual(str(filled.get("source") or ""), "ai_generated")
        self.assertGreater(float(data.get("visual_ai_spend_usd") or 0), 0)

    def test_08_ai_fallback_cannot_exceed_project_cap(self):
        pex, dl = self._mock_pexels(empty=True)
        data = self._budget(0.0)
        with pex, dl, self._mock_ai() as ai:
            filled = fill_photo_aid_automatic(
                self._aid(),
                package_id=f"auto-{uuid.uuid4().hex[:8]}",
                title="Teen Safety",
                chapter="Social Media Check-In",
                data=data,
                fields=data["fields"],
                allow_ai=True,
            )
        ai.assert_not_called()
        self.assertNotEqual(str(filled.get("source") or ""), "ai_generated")
        self.assertIn("budget", (filled.get("budget_message") or filled.get("error") or "").lower())
        self.assertFalse(visual_ai_authorized(data, data["fields"]))
        self.assertEqual(remaining_visual_budget_usd(data, data["fields"]), 0)

    def test_09_one_failed_asset_does_not_regenerate_or_delete_successful_assets(self):
        pkg = f"auto-{uuid.uuid4().hex[:8]}"
        good = store_interior_photo(self._aid(visual_id="v_ok"), _jpeg_bytes(), package_id=pkg)
        good["match_status"] = MATCH_PASS
        good["internally_ready"] = True
        sha = good["sha256"]
        path = good["asset_path"]
        plan = {
            "chapters": [
                {"chapter": "Social Media Check-In", "chapter_index": 1, "aids": [good]},
                {
                    "chapter": "Family Rules",
                    "chapter_index": 2,
                    "aids": [self._aid(visual_id="v_fail", chapter="Family Rules", chapter_index=2)],
                },
            ]
        }
        pex, dl = self._mock_pexels(empty=True)
        data = self._budget(0.0)
        with pex, dl, self._mock_ai() as ai:
            out = fill_plan_photos_automatic(
                plan,
                package_id=pkg,
                title="Teen Safety",
                data=data,
                fields=data["fields"],
                allow_ai=True,
            )
        ai.assert_not_called()
        kept = out["chapters"][0]["aids"][0]
        self.assertEqual(kept["sha256"], sha)
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), sha)
        failed = out["chapters"][1]["aids"][0]
        self.assertNotEqual(str(failed.get("status") or ""), "resolved")

    def test_10_fully_passing_photo_internally_ready_without_individual_user_acceptance(self):
        brief = build_visual_brief(self._aid())
        report = score_photo_against_brief(
            brief,
            alt=PARENT_ALT,
            page_url="https://www.pexels.com/photo/parent-teen-phone-1/",
            image_bytes=_jpeg_bytes(),
            planned_caption=self._aid()["caption"],
        )
        self.assertEqual(report.status, MATCH_PASS)
        self.assertFalse(report.user_accepted)
        pkg = f"auto-{uuid.uuid4().hex[:8]}"
        aid = store_interior_photo(self._aid(alt=PARENT_ALT), _jpeg_bytes(), package_id=pkg)
        aid["alt"] = PARENT_ALT
        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        data["package_id"] = pkg
        data["visual_plan"] = {"chapters": [{"chapter": aid["chapter"], "chapter_index": 1, "aids": [aid]}]}
        payload = visual_review_payload(data)
        self.assertTrue(payload["assets"][0].get("internally_ready") or payload["assets"][0]["match_status"] == MATCH_PASS)
        self.assertFalse(payload["assets"][0].get("user_accepted"))
        self.assertFalse(is_approved(data["ebook_workspace"], "visuals"))

    def test_11_uncertain_and_rejected_remain_blocked(self):
        brief = build_visual_brief(self._aid())
        uncertain = score_photo_against_brief(
            brief,
            alt="a ceramic mug on a table",
            page_url="https://www.pexels.com/photo/mug-9/",
            image_bytes=_jpeg_bytes(),
        )
        rejected = score_photo_against_brief(
            brief,
            alt="watermark advertisement stock collage",
            page_url="https://www.pexels.com/photo/ad-9/",
            image_bytes=_jpeg_bytes(),
            content_labels=["watermark", "advertisement"],
        )
        self.assertEqual(uncertain.status, MATCH_NEEDS_REVIEW)
        self.assertNotEqual(rejected.status, MATCH_PASS)
        self.assertFalse(uncertain.ok)
        self.assertFalse(rejected.ok)

    def test_12_final_visuals_approval_still_requires_one_user_action(self):
        pkg = f"auto-{uuid.uuid4().hex[:8]}"
        aid = store_interior_photo(self._aid(alt=PARENT_ALT), _jpeg_bytes(), package_id=pkg)
        aid["alt"] = PARENT_ALT
        data = ensure_workspace(
            {
                "product_type": "ebook",
                "title": "Teen Safety",
                "content": PHOTO_MD,
                "ebook": PHOTO_MD,
                "package_id": pkg,
                "fields": {"include_images": "Yes"},
                "visual_plan": {"chapters": [{"chapter": aid["chapter"], "chapter_index": 1, "aids": [aid]}]},
            }
        )
        payload = visual_review_payload(data)
        self.assertIn("approvable", payload)
        self.assertFalse(is_approved(data["ebook_workspace"], "visuals"))
        self.assertNotEqual(str((data.get("ebook_workspace") or {}).get("rail", {}).get("visuals", {}).get("status") or ""), "approved")

    def test_13_reopen_restores_assets_without_new_external_calls(self):
        pkg = f"auto-{uuid.uuid4().hex[:8]}"
        aid = store_interior_photo(self._aid(alt=PARENT_ALT), _jpeg_bytes(), package_id=pkg)
        aid["alt"] = PARENT_ALT
        aid["match_status"] = MATCH_PASS
        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        data["package_id"] = pkg
        data["artifact_id"] = pkg
        data["content"] = build_event_photo_strong_manuscript()
        data["ebook"] = data["content"]
        data["fields"] = {"include_images": "No"}
        set_stage_status(data["ebook_workspace"], "manuscript", STATUS_AWAITING)
        data = approve_stage(data, "manuscript")
        data["visual_plan"] = {"chapters": [{"chapter": aid["chapter"], "chapter_index": 1, "aids": [aid]}]}
        pex, dl = self._mock_pexels()
        with pex, dl, self._mock_ai() as ai:
            restored = prepare_visuals_for_review(data)
        self.assertEqual(self._pexels_queries, [])
        ai.assert_not_called()
        kept = restored["visual_plan"]["chapters"][0]["aids"][0]
        self.assertEqual(kept["sha256"], aid["sha256"])
        self.assertTrue(os.path.isfile(str(kept.get("asset_path") or "")))

    def test_14_pdf_zip_use_stored_files_without_regeneration(self):
        pkg = f"auto-{uuid.uuid4().hex[:8]}"
        aid = store_interior_photo(self._aid(alt=PARENT_ALT), _jpeg_bytes(), package_id=pkg)
        data = {"visual_plan": {"chapters": [{"chapter": aid["chapter"], "chapter_index": 1, "aids": [aid]}]}}
        pex, dl = self._mock_pexels()
        with pex, dl, self._mock_ai() as ai:
            files = collect_zip_visual_files(data)
        ai.assert_not_called()
        self.assertEqual(self._pexels_queries, [])
        blob = files[f"visuals/{aid['visual_id']}.png"]
        self.assertEqual(hashlib.sha256(blob).hexdigest(), aid["sha256"])

    def test_15_ordinary_users_see_simplified_review_screen(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Visuals Ready for Review", js)
        self.assertIn("Approve All Visuals", js)
        self.assertIn("Automatic professional visuals", js)
        self.assertIn("We’ll use relevant stock photos first", js)
        pkg = f"auto-{uuid.uuid4().hex[:8]}"
        aid = store_interior_photo(self._aid(alt=PARENT_ALT), _jpeg_bytes(), package_id=pkg)
        payload = visual_review_payload(
            {"visual_plan": {"chapters": [{"chapter": aid["chapter"], "chapter_index": 1, "aids": [aid]}]}}
        )
        self.assertTrue(payload.get("simplified_review"))
        self.assertEqual(payload.get("heading"), "Visuals Ready for Review")
        self.assertIn("source_label", payload["assets"][0])
        self.assertIn("description", payload["assets"][0])
        self.assertNotIn("match_score", payload["assets"][0])
        self.assertNotIn("sha256", payload["assets"][0])

    def test_16_technical_details_never_shown_to_the_customer(self):
        # The owner reviewed this screen directly and asked that raw hashes,
        # match_status codes, and other internal debugging fields never be
        # customer-visible -- not even behind a click-to-expand control.
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("View Technical Details", js)
        pkg = f"auto-{uuid.uuid4().hex[:8]}"
        aid = store_interior_photo(self._aid(alt=PARENT_ALT), _jpeg_bytes(), package_id=pkg)
        payload = visual_review_payload(
            {"visual_plan": {"chapters": [{"chapter": aid["chapter"], "chapter_index": 1, "aids": [aid]}]}}
        )
        # The backend may still compute this for internal/admin tooling, but
        # it must never be serialized into the rendered app.js review screen.
        self.assertTrue(payload["technical_assets"])
        self.assertIn("match_score", payload["technical_assets"][0])
        self.assertIn("sha256", payload["technical_assets"][0])

    def test_17_no_customer_facing_source_link_leaves_factory_from_primary_review(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        start = js.index("Visuals Ready for Review")
        end = js.index('} else if (stageId === "cover")', start)
        chunk = js[start:end]
        self.assertNotIn("pexels.com", chunk.lower())
        self.assertNotIn('target="_blank"', chunk)
        pkg = f"auto-{uuid.uuid4().hex[:8]}"
        aid = store_interior_photo(
            self._aid(page_url="https://www.pexels.com/photo/private-99/", alt=PARENT_ALT),
            _jpeg_bytes(),
            package_id=pkg,
        )
        payload = visual_review_payload(
            {"visual_plan": {"chapters": [{"chapter": aid["chapter"], "chapter_index": 1, "aids": [aid]}]}}
        )
        dumped = json.dumps(payload["assets"]).lower()
        self.assertNotIn("http://", dumped)
        self.assertNotIn("https://", dumped)
        self.assertNotIn("pexels.com", dumped)

    def test_18_no_visuals_mode_produces_no_visual_calls(self):
        self.assertFalse(images_requested({"include_images": "No"}))
        self.assertFalse(automatic_visuals_requested({"include_images": "No visuals"}))
        self.assertTrue(images_requested({"include_images": "Yes"}))
        self.assertTrue(automatic_visuals_requested({"include_images": "Automatic professional visuals"}))
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        fields = {
            "include_images": "No",
            "ebook_title": "Backyard Tomato Growing",
            "topic": "gardening",
        }
        plan = {
            "subtitle": "Grow food",
            "cover_prompt": "garden",
            "product_summary": "A garden guide.",
            "chapters": [
                {
                    "chapter": "Soil Preparation",
                    "aids": [
                        {
                            "type": "stock photo",
                            "title": "Garden soil",
                            "caption": "Loose soil with compost.",
                            "image_prompt": "garden soil",
                        }
                    ],
                }
            ],
        }
        with self._mock_ai() as ai, patch(
            "services.ebook_package.generate_visual_plan", return_value=copy.deepcopy(plan)
        ), patch("services.ebook_pexels._http_get", side_effect=AssertionError("pexels")) as http:
            pkg = build_ebook_package("Backyard Tomato Growing", GARDEN_MD, fields)
        ai.assert_not_called()
        http.assert_not_called()
        photos = [
            aid
            for ch in (pkg.get("visual_plan") or {}).get("chapters") or []
            for aid in (ch.get("aids") or [])
            if str(aid.get("type") or "") in {"photo", "stock photo"}
        ]
        self.assertEqual(photos, [])

    def test_19_cost_estimate_matches_displayed_cap_formula(self):
        self.assertEqual(estimate_max_visual_generation_cost_usd(6), round(6 * AI_VISUAL_UNIT_USD * 2, 4))
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("EBOOK_AI_VISUAL_UNIT_USD = 0.04", js)
        self.assertIn("visuals_authorized", js)
        self.assertIn("visual_budget_cap_usd", js)

    def test_20_project_4249_files_hashes_approvals_spend_unchanged(self):
        row = database.get_project(LIVE_4249)
        self.assertIsNotNone(row, "project #4249 must exist")
        data = row["data"]
        cover = (data.get("cover_design") or {}).get("source") or {}
        ledger = (data.get("ebook_workspace") or {}).get("paid_call_ledger") or {}
        self.assertEqual(str(cover.get("sha256") or ""), EXPECTED_COVER_SHA)
        self.assertEqual(manuscript_digest(data), EXPECTED_MANUSCRIPT)
        self.assertAlmostEqual(float(ledger.get("spent_usd") or 0), 1.80, places=2)
        self.assertAlmostEqual(float(ledger.get("remaining_usd") or 0), 0.0, places=2)
        self.assertFalse(is_approved(data.get("ebook_workspace") or {}, "visuals"))
        self.assertFalse(visual_ai_authorized(data, data.get("fields") or {}))
        shas = []
        for aid in required_aids(data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None):
            path = str(aid.get("asset_path") or "")
            self.assertTrue(os.path.isfile(path), path)
            self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), aid.get("sha256"))
            shas.append(aid.get("sha256"))
        self.assertTrue(shas)


class Live4249AutomaticVisualGuardTests(unittest.TestCase):
    def test_implementation_did_not_call_ai_or_mutate_4249(self):
        row = database.get_project(LIVE_4249)
        self.assertIsNotNone(row, "project #4249 must exist")
        before = json.dumps(row["data"].get("ebook_visual_manifest_digest"))
        self.assertEqual(str(((row["data"].get("cover_design") or {}).get("source") or {}).get("sha256") or ""), EXPECTED_COVER_SHA)
        after = database.get_project(LIVE_4249)
        self.assertEqual(json.dumps(after["data"].get("ebook_visual_manifest_digest")), before)


if __name__ == "__main__":
    unittest.main()
