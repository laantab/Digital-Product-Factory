"""Structured visual-brief matching. Zero paid/external calls. Pexels mocked."""
from __future__ import annotations

import io
import json
import os
import sys
import unittest
import uuid
import zipfile
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

from services.ebook_design_workspace import prepare_visuals_local  # noqa: E402
from services.ebook_project_workspace import (  # noqa: E402
    STATUS_AWAITING,
    approve_stage,
    build_acceptance_project_data,
    is_approved,
    set_stage_status,
    stage_status,
)
from services.ebook_visual_match import (  # noqa: E402
    MATCH_NEEDS_REVIEW,
    MATCH_PASS,
    MATCH_REJECT,
    build_visual_brief,
    contains_customer_source_url,
    customer_safe_visual_plan,
    event_print_brief,
    score_photo_against_brief,
    stamp_plan_photo_matches,
)
from services.ebook_visual_pipeline import (  # noqa: E402
    accept_photo_aid,
    collect_zip_visual_files,
    figure_html,
    materialize_visual_plan,
    render_aid_png,
    store_interior_photo,
    validate_visual_readiness,
    visual_review_payload,
)
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript  # noqa: E402


def _paid_patches():
    return (
        patch("ai_client.get_client", side_effect=AssertionError("paid client")),
        patch("ai_client.chat", side_effect=AssertionError("paid chat")),
        patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json")),
    )


def _noisy_jpeg(w: int = 1200, h: int = 800) -> bytes:
    img = Image.new("RGB", (w, h), (48, 72, 96))
    draw = ImageDraw.Draw(img)
    draw.rectangle((30, 30, w - 80, h // 2), fill=(210, 170, 90))
    draw.ellipse((w // 5, h // 5, 4 * w // 5, 4 * h // 5), fill=(24, 28, 36))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _photo_aid(**extra):
    aid = {
        "visual_id": extra.pop("visual_id", "v_ch7"),
        "type": "photo",
        "title": extra.pop("title", "Compact event photo printer with prints in the tray"),
        "caption": extra.pop(
            "caption",
            "A compact photo printer with bordered photographs emerging from the tray—"
            "the capture-to-print-to-guest-delivery station this chapter describes.",
        ),
        "chapter": extra.pop("chapter", "Event-Day Operations: From Photograph to Guest Delivery"),
        "chapter_index": extra.pop("chapter_index", 7),
        "placement": "after_opening",
        "source": "pexels",
        "attribution": "Photo by Test on Pexels",
        "photographer": "Test",
        "page_url": extra.pop("page_url", "https://www.pexels.com/photo/demo-1"),
        "photo_id": extra.pop("photo_id", "1"),
        "required": True,
    }
    aid.update(extra)
    return aid


class EbookVisualMatchTests(unittest.TestCase):
    def setUp(self):
        self._patches = _paid_patches()
        for item in self._patches:
            item.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    def test_01_home_office_printer_fails_event_printing_brief(self):
        brief = event_print_brief()
        report = score_photo_against_brief(
            brief,
            alt="woman printing photos on paper while working at home",
            page_url="https://www.pexels.com/photo/woman-printing-photos-on-paper-while-forking-at-home-7014397/",
            image_bytes=_noisy_jpeg(),
            planned_caption=brief.business_purpose,
            content_labels=["home office", "woman using printer", "desktop inkjet"],
        )
        self.assertEqual(report.status, MATCH_REJECT)
        self.assertIn("setting conflict", report.rejection_reason.lower())
        self.assertLess(report.match_score, brief.min_match_score)
        self.assertFalse(report.ok)

    def test_02_generic_printer_word_does_not_pass(self):
        brief = event_print_brief()
        report = score_photo_against_brief(
            brief,
            alt="printer",
            page_url="https://www.pexels.com/photo/printer-23534017/",
            image_bytes=_noisy_jpeg(),
            content_labels=["printer"],
        )
        self.assertEqual(report.status, MATCH_REJECT)
        self.assertNotEqual(report.status, MATCH_PASS)
        blob = (report.rejection_reason + " " + " ".join(report.missing_requirements)).lower()
        self.assertTrue("printer" in blob or "workflow" in blob or "setting" in blob or "subject" in blob)

    def test_03_missing_critical_setting_or_action_rejects(self):
        brief = event_print_brief()
        report = score_photo_against_brief(
            brief,
            alt="compact photo printer with bordered photographs",
            page_url="https://www.pexels.com/photo/photo-printer-17536002/",
            image_bytes=_noisy_jpeg(),
            content_labels=["compact photo printer", "bordered photographs"],
        )
        self.assertEqual(report.status, MATCH_REJECT)
        self.assertTrue(
            "required setting" in report.missing_requirements
            or "required action" in report.missing_requirements
            or "required subject" in report.missing_requirements
        )

    def test_04_local_asset_must_exist_before_approval(self):
        data = {
            "visual_plan": {
                "chapters": [
                    {
                        "chapter": "Event-Day Operations",
                        "chapter_index": 7,
                        "aids": [_photo_aid(asset_path="C:/missing/v_ch7.png", sha256="abc")],
                    }
                ]
            }
        }
        report = validate_visual_readiness(data)
        self.assertFalse(report.ok)
        self.assertTrue(any("no existing local asset" in f.lower() for f in report.findings))
        payload = visual_review_payload(data)
        self.assertFalse(payload["approvable"])

    def test_05_rejected_photos_keep_approve_visuals_disabled(self):
        pkg = f"vis-match-{uuid.uuid4().hex[:12]}"
        aid = store_interior_photo(
            _photo_aid(
                page_url="https://www.pexels.com/photo/woman-printing-photos-on-paper-while-forking-at-home-7014397/",
                alt="woman printing photos at home",
                content_labels=["home office", "woman using printer"],
            ),
            _noisy_jpeg(),
            package_id=pkg,
        )
        plan = {"chapters": [{"chapter": aid["chapter"], "chapter_index": 7, "aids": [aid]}]}
        stamp_plan_photo_matches(plan)
        data = {"visual_plan": plan}
        payload = visual_review_payload(data)
        self.assertFalse(payload["approvable"])
        self.assertEqual(payload["assets"][0]["match_status"], MATCH_REJECT)
        self.assertTrue(payload["technical_assets"][0]["page_url"])
        self.assertIn("pexels.com", payload["technical_assets"][0]["page_url"])
        self.assertFalse(payload["assets"][0].get("page_url"))
        report = validate_visual_readiness(data)
        self.assertFalse(report.ok)

    def test_06_needs_user_review_keeps_approval_disabled(self):
        pkg = f"vis-review-{uuid.uuid4().hex[:12]}"
        aid = store_interior_photo(
            _photo_aid(
                page_url="https://www.pexels.com/photo/event-photo-station-9",
                alt="",
            ),
            _noisy_jpeg(),
            package_id=pkg,
        )
        plan = {"chapters": [{"chapter": aid["chapter"], "chapter_index": 7, "aids": [aid]}]}
        stamp_plan_photo_matches(plan)
        data = {"visual_plan": plan}
        payload = visual_review_payload(data)
        self.assertIn(payload["assets"][0]["match_status"], {MATCH_NEEDS_REVIEW, MATCH_REJECT})
        self.assertFalse(payload["approvable"])
        self.assertTrue(any("NEEDS USER REVIEW" in f or "failed" in f.lower() or "conflict" in f.lower() for f in payload["findings"]) or payload["assets"][0]["match_status"] != MATCH_PASS)

    def test_07_pexels_links_available_in_private_review(self):
        pkg = f"vis-link-{uuid.uuid4().hex[:12]}"
        aid = store_interior_photo(
            _photo_aid(page_url="https://www.pexels.com/photo/private-review-99/"),
            _noisy_jpeg(),
            package_id=pkg,
        )
        payload = visual_review_payload(
            {"visual_plan": {"chapters": [{"chapter": aid["chapter"], "chapter_index": 7, "aids": [aid]}]}}
        )
        self.assertTrue(payload.get("private_review"))
        self.assertIn("https://www.pexels.com/", payload["technical_assets"][0]["page_url"])
        self.assertTrue(payload["technical_assets"][0].get("required_scene"))
        self.assertIn("appears_to_show", payload["technical_assets"][0])
        self.assertIn("match_score", payload["technical_assets"][0])
        self.assertIn("passed_requirements", payload["technical_assets"][0])
        self.assertIn("missing_requirements", payload["technical_assets"][0])
        self.assertIn("rejection_reason", payload["technical_assets"][0])
        self.assertFalse(payload["assets"][0].get("page_url"))
        self.assertNotIn("match_score", payload["assets"][0])
        self.assertTrue(payload["assets"][0].get("replace_enabled"))
        self.assertTrue(payload["assets"][0].get("thumb_data_uri"))
        # A full-size preview_data_uri per photo was pure dead weight -- app.js
        # only ever rendered thumb_data_uri here -- and made this payload big
        # enough to freeze the browser tab while rendering a full chapter set.
        self.assertNotIn("preview_data_uri", payload["assets"][0])
        self.assertTrue(payload.get("simplified_review"))

    def test_08_pexels_links_absent_from_customer_pdf_and_zip(self):
        pkg = f"vis-zip-{uuid.uuid4().hex[:12]}"
        aid = store_interior_photo(
            _photo_aid(
                page_url="https://www.pexels.com/photo/woman-printing-photos-on-paper-while-forking-at-home-7014397/",
                caption="A compact photo printer with bordered photographs emerging from the tray.",
            ),
            _noisy_jpeg(),
            package_id=pkg,
        )
        data = {"visual_plan": {"chapters": [{"chapter": aid["chapter"], "chapter_index": 7, "aids": [aid]}]}}
        html = figure_html(aid)
        self.assertNotIn("pexels.com", html.lower())
        self.assertNotIn("https://", html.lower())
        files = collect_zip_visual_files(data)
        plan_txt = files["visual_plan.json"].decode("utf-8").lower()
        self.assertNotIn("pexels.com", plan_txt)
        self.assertNotIn("page_url", plan_txt)
        safe = customer_safe_visual_plan(data["visual_plan"])
        dumped = json.dumps(safe).lower()
        self.assertNotIn("pexels.com", dumped)
        self.assertFalse(contains_customer_source_url(html))
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w") as zf:
            for name, blob in files.items():
                zf.writestr(name, blob)
        with zipfile.ZipFile(io.BytesIO(zbuf.getvalue())) as zf:
            for name in zf.namelist():
                if name.endswith(".png"):
                    continue
                text = zf.read(name).decode("utf-8", errors="ignore").lower()
                self.assertNotIn("pexels.com", text, name)

    def test_09_charts_workflows_timelines_still_render(self):
        chart = render_aid_png(
            {
                "type": "chart",
                "title": "Startup planning ranges",
                "chart_data": {"kind": "bar", "labels": ["Lean", "Event"], "values": [3500, 17500]},
            }
        )
        workflow = render_aid_png(
            {
                "type": "workflow",
                "title": "Inquiry to signed booking",
                "items": ["Receive inquiry", "Qualify event", "Send proposal", "Confirm booking"],
            }
        )
        timeline = render_aid_png(
            {
                "type": "timeline",
                "title": "30-day first paid event",
                "items": ["Days 1-7 Offer", "Days 8-14 Gear", "Days 15-21 Marketing", "Days 22-30 Sell"],
            }
        )
        self.assertGreater(chart.size[0], 200)
        self.assertGreater(workflow.size[0], 200)
        self.assertGreater(timeline.size[0], 200)
        md = build_event_photo_strong_manuscript()
        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        pkg = f"ebook-vis-{uuid.uuid4().hex[:16]}"
        data["artifact_id"] = pkg
        data["package_id"] = pkg
        data["content"] = md
        data["ebook"] = md
        set_stage_status(data["ebook_workspace"], "manuscript", STATUS_AWAITING)
        data = approve_stage(data, "manuscript")
        prepared = prepare_visuals_local(data)
        types = {a["type"] for ch in prepared["visual_plan"]["chapters"] for a in ch.get("aids") or []}
        self.assertTrue(types & {"chart", "comparison", "workflow", "timeline", "checklist"})
        self.assertFalse(is_approved(prepared["ebook_workspace"], "visuals"))

    def test_10_no_unrelated_generator_or_stage_approval(self):
        self.assertFalse(os.environ.get("OPENAI_API_KEY"))
        self.assertEqual(os.environ.get("FACTORY_TEST_MODE"), "1")
        src = Path("services/ebook_visual_match.py").read_text(encoding="utf-8")
        self.assertNotIn("openai", src.lower())
        self.assertNotIn("tavily", src.lower())
        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        pkg = f"ebook-vis-{uuid.uuid4().hex[:16]}"
        data["artifact_id"] = pkg
        data["package_id"] = pkg
        data["content"] = build_event_photo_strong_manuscript()
        data["ebook"] = data["content"]
        set_stage_status(data["ebook_workspace"], "manuscript", STATUS_AWAITING)
        data = approve_stage(data, "manuscript")
        prepared = prepare_visuals_local(data)
        self.assertNotEqual(stage_status(prepared["ebook_workspace"], "visuals"), "approved")
        self.assertFalse(is_approved(prepared["ebook_workspace"], "cover"))
        self.assertFalse(is_approved(prepared["ebook_workspace"], "design"))

    def test_user_accept_does_not_approve_visuals_stage(self):
        pkg = f"vis-accept-{uuid.uuid4().hex[:12]}"
        aid = store_interior_photo(_photo_aid(), _noisy_jpeg(), package_id=pkg)
        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        data["artifact_id"] = pkg
        data["package_id"] = pkg
        data["content"] = build_event_photo_strong_manuscript()
        data["ebook"] = data["content"]
        set_stage_status(data["ebook_workspace"], "manuscript", STATUS_AWAITING)
        data = approve_stage(data, "manuscript")
        data["visual_plan"] = {"chapters": [{"chapter": aid["chapter"], "chapter_index": 7, "aids": [aid]}]}
        data = accept_photo_aid(data, "v_ch7")
        self.assertTrue(data["visual_plan"]["chapters"][0]["aids"][0].get("user_accepted"))
        self.assertFalse(is_approved(data["ebook_workspace"], "visuals"))

    def test_brief_built_before_search_fields(self):
        brief = build_visual_brief(_photo_aid())
        self.assertEqual(brief.chapter_number, 7)
        self.assertTrue(brief.required_subject)
        self.assertTrue(brief.required_action)
        self.assertTrue(brief.required_setting)
        self.assertTrue(brief.required_objects)
        self.assertTrue(brief.forbidden_settings)
        self.assertTrue(brief.business_purpose)
        self.assertGreaterEqual(brief.min_match_score, 0.7)
        self.assertIn("on-site event photo printing station", brief.search_queries)


class IndependentVisualBriefTests(unittest.TestCase):
    def setUp(self):
        self._patches = _paid_patches()
        for item in self._patches:
            item.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    def _equipment_aid(self, **extra):
        aid = {
            "visual_id": extra.pop("visual_id", "v_equip"),
            "type": "photo",
            "title": extra.pop("title", "Core camera kit laid out for event work"),
            "caption": extra.pop(
                "caption",
                "A professional camera body, lenses, and support gear staged as an event kit.",
            ),
            "chapter": extra.pop(
                "chapter",
                "Core Camera Kit, Printing Equipment, and Backup Gear",
            ),
            "chapter_index": extra.pop("chapter_index", 3),
        }
        aid.update(extra)
        return aid

    def _keepsake_aid(self, **extra):
        aid = {
            "visual_id": extra.pop("visual_id", "v_keep"),
            "type": "photo",
            "title": extra.pop("title", "Ceramic mug with a photograph applied"),
            "caption": extra.pop(
                "caption",
                "A ceramic mug with a photographic image visibly printed on the surface — "
                "a keepsake that needs separate equipment and workflow from dye-sub prints.",
            ),
            "chapter": extra.pop(
                "chapter",
                "Keepsakes Beyond Photo Prints: Separate Equipment and Workflow",
            ),
            "chapter_index": extra.pop("chapter_index", 9),
        }
        aid.update(extra)
        return aid

    def _live_aid(self, **extra):
        aid = {
            "visual_id": extra.pop("visual_id", "v_live"),
            "type": "photo",
            "title": extra.pop("title", "Event photographer covering a live celebration"),
            "caption": extra.pop(
                "caption",
                "A working photographer covering a wedding reception — the on-site business this guide describes.",
            ),
            "chapter": extra.pop("chapter", "What This Business Actually Looks Like"),
            "chapter_index": extra.pop("chapter_index", 1),
        }
        aid.update(extra)
        return aid

    def test_01_every_visual_gets_independent_structured_brief(self):
        live = build_visual_brief(self._live_aid())
        equip = build_visual_brief(self._equipment_aid())
        printer = build_visual_brief(_photo_aid())
        keep = build_visual_brief(self._keepsake_aid())
        purposes = {live.purpose, equip.purpose, printer.purpose, keep.purpose}
        self.assertEqual(len(purposes), 4)
        self.assertNotEqual(live.required_subject, equip.required_subject)
        self.assertNotEqual(printer.required_objects, keep.required_objects)
        live.required_objects.append("leaked-from-live")
        self.assertNotIn("leaked-from-live", equip.required_objects)
        self.assertNotIn("leaked-from-live", printer.required_objects)

    def test_02_requirements_cannot_leak_between_adjacent_chapters(self):
        plan = {
            "chapters": [
                {"chapter": self._equipment_aid()["chapter"], "chapter_index": 3, "aids": [self._equipment_aid()]},
                {"chapter": _photo_aid()["chapter"], "chapter_index": 7, "aids": [_photo_aid()]},
                {"chapter": self._keepsake_aid()["chapter"], "chapter_index": 9, "aids": [self._keepsake_aid()]},
            ]
        }
        stamp_plan_photo_matches(plan)
        equip = plan["chapters"][0]["aids"][0]
        printer = plan["chapters"][1]["aids"][0]
        keep = plan["chapters"][2]["aids"][0]
        self.assertIn("camera", str(equip.get("visual_brief", {}).get("required_subject") or "").lower())
        self.assertNotIn("photographer", str(equip.get("visual_brief", {}).get("required_subject") or "").lower())
        self.assertIn("printer", str(printer.get("visual_brief", {}).get("required_objects") or "").lower())
        self.assertIn("keepsake", str(keep.get("visual_brief", {}).get("required_subject") or "").lower())
        self.assertNotIn("photo printer", str(keep.get("required_scene") or "").lower())
        self.assertNotIn("working event photographer", str(equip.get("required_scene") or "").lower())
        printer["visual_brief"]["required_objects"].append("mutated-print-object")
        self.assertNotIn("mutated-print-object", equip.get("visual_brief", {}).get("required_objects") or [])
        self.assertNotIn("mutated-print-object", keep.get("visual_brief", {}).get("required_objects") or [])

    def test_03_equipment_chapter_validates_without_person_or_event(self):
        brief = build_visual_brief(self._equipment_aid())
        self.assertNotIn("photographer", brief.required_subject.lower())
        self.assertNotIn("wedding", brief.required_setting.lower())
        self.assertNotIn("celebration", brief.required_setting.lower())
        report = score_photo_against_brief(
            brief,
            alt="camera and photography equipment on a table",
            page_url="https://www.pexels.com/photo/camera-and-photography-equipment-on-a-table-13654279/",
            image_bytes=_noisy_jpeg(),
            content_labels=["camera body", "photography equipment", "lenses", "kit on a table"],
        )
        self.assertNotIn("required subject", report.missing_requirements)
        self.assertNotIn("required setting", report.missing_requirements)
        self.assertNotEqual(report.status, MATCH_REJECT)
        blob = (report.required_scene + " " + report.rejection_reason).lower()
        self.assertNotIn("working event photographer", blob)
        self.assertNotIn("live event", brief.required_action.lower())

    def test_04_keepsake_chapter_validates_mug_without_printer_or_bordered_print(self):
        brief = build_visual_brief(self._keepsake_aid())
        scene = brief.required_scene().lower()
        self.assertNotIn("photo printer", scene)
        self.assertNotIn("bordered photograph", scene)
        self.assertNotIn("guest pickup", scene)
        report = score_photo_against_brief(
            brief,
            alt="ceramic mug with a photograph printed on the surface",
            page_url="https://www.pexels.com/photo/ceramic-mug-with-photograph-applied-5656143/",
            image_bytes=_noisy_jpeg(),
            content_labels=["ceramic mug", "photograph applied", "photo on mug"],
        )
        self.assertNotIn("photo printer", report.missing_requirements)
        self.assertNotIn("bordered photograph", report.missing_requirements)
        self.assertNotEqual(report.status, MATCH_REJECT)

    def test_05_onsite_printing_chapter_rejects_generic_at_home_printer(self):
        brief = build_visual_brief(_photo_aid())
        report = score_photo_against_brief(
            brief,
            alt="woman printing photos on paper while working at home",
            page_url="https://www.pexels.com/photo/woman-printing-photos-on-paper-while-forking-at-home-7014397/",
            image_bytes=_noisy_jpeg(),
            content_labels=["home office", "woman using printer", "desktop inkjet"],
        )
        self.assertEqual(report.status, MATCH_REJECT)
        self.assertFalse(report.ok)

    def test_06_complete_scene_cannot_fail_honest_match_without_named_claim(self):
        brief = build_visual_brief(self._live_aid())
        report = score_photo_against_brief(
            brief,
            alt="photographer captures wedding moment on camera",
            page_url="https://www.pexels.com/photo/photographer-captures-wedding-moment-on-camera-33072063/",
            image_bytes=_noisy_jpeg(),
            planned_caption=self._live_aid()["caption"],
            content_labels=["photographer", "capturing", "wedding", "camera"],
        )
        self.assertNotIn("honest scene match", report.missing_requirements)
        self.assertNotEqual(report.status, MATCH_REJECT)
        self.assertIn("required subject", report.passed_requirements)
        self.assertIn("required action", report.passed_requirements)
        self.assertIn("required setting", report.passed_requirements)

    def test_07_unsupported_or_uncertain_needs_user_review(self):
        brief = build_visual_brief(self._keepsake_aid())
        report = score_photo_against_brief(
            brief,
            alt="a white and blue ceramic mug on surface with brown leaves",
            page_url="https://www.pexels.com/photo/a-white-and-blue-ceramic-mug-on-surface-with-brown-leaves-5656143/",
            image_bytes=_noisy_jpeg(),
        )
        self.assertEqual(report.status, MATCH_NEEDS_REVIEW)
        self.assertIn("NEEDS USER REVIEW", report.rejection_reason)
        self.assertNotEqual(report.status, MATCH_PASS)

    def test_08_reopening_saved_project_preserves_correct_brief_per_visual(self):
        plan = {
            "chapters": [
                {"chapter": self._live_aid()["chapter"], "chapter_index": 1, "aids": [self._live_aid()]},
                {"chapter": self._equipment_aid()["chapter"], "chapter_index": 3, "aids": [self._equipment_aid()]},
                {"chapter": _photo_aid()["chapter"], "chapter_index": 7, "aids": [_photo_aid()]},
                {"chapter": self._keepsake_aid()["chapter"], "chapter_index": 9, "aids": [self._keepsake_aid()]},
            ]
        }
        stamp_plan_photo_matches(plan)
        roundtrip = json.loads(json.dumps(plan))
        stamp_plan_photo_matches(roundtrip)
        first = [ch["aids"][0]["visual_brief"]["purpose"] for ch in plan["chapters"]]
        again = [ch["aids"][0]["visual_brief"]["purpose"] for ch in roundtrip["chapters"]]
        self.assertEqual(first, again)
        self.assertEqual(again, ["live_capture", "equipment_kit", "onsite_print_delivery", "keepsake_product"])
        stale = self._keepsake_aid()
        stale["visual_brief"] = event_print_brief(chapter_number=9, chapter_title=stale["chapter"]).as_dict()
        rebuilt = build_visual_brief(stale)
        self.assertEqual(rebuilt.purpose, "keepsake_product")
        self.assertNotIn("photo printer", rebuilt.required_scene().lower())

    def test_replaced_photo_clears_previous_acceptance(self):
        pkg = f"vis-replace-{uuid.uuid4().hex[:12]}"
        aid = store_interior_photo(self._keepsake_aid(), _noisy_jpeg(), package_id=pkg)
        aid["user_accepted"] = True
        aid["content_labels"] = ["stale labels from previous photo"]
        data = {
            "package_id": pkg,
            "visual_plan": {"chapters": [{"chapter": aid["chapter"], "chapter_index": 9, "aids": [aid]}]},
        }
        from services.ebook_visual_pipeline import replace_photo_aid

        data = replace_photo_aid(data, "v_keep", local_path=str(aid["asset_path"]))
        updated = data["visual_plan"]["chapters"][0]["aids"][0]
        self.assertFalse(updated.get("user_accepted"))
        self.assertNotIn("stale labels from previous photo", updated.get("content_labels") or [])


if __name__ == "__main__":
    unittest.main()
