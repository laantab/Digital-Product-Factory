"""Ebook visual pipeline: plan → assets → Visual Review → approval → HTML/PDF/ZIP.

Zero paid/external calls. Isolated projects except read-only #4249 identity checks.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import sys
import unittest
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image as PILImage
from PIL import ImageDraw as PILImageDraw

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
from services.ebook_book_layout import render_designed_ebook_html  # noqa: E402
from services.ebook_design_export import render_designed_bundle, select_theme  # noqa: E402
from services.ebook_design_workspace import (  # noqa: E402
    approve_visuals_local,
    build_preview,
    prepare_visuals_local,
)
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript  # noqa: E402
from services.ebook_project_workspace import (  # noqa: E402
    STATUS_APPROVED,
    STATUS_AWAITING,
    STATUS_NEEDS_CORRECTION,
    approve_stage,
    build_acceptance_project_data,
    is_approved,
    manuscript_digest,
    set_stage_status,
    stage_status,
    workspace_public_view,
)
from services.ebook_visual_pipeline import (  # noqa: E402
    materialize_visual_plan,
    plan_content_aware_visuals,
    reconcile_visuals_gate,
    render_aid_png,
    required_aids,
    store_interior_photo,
    validate_visual_readiness,
    visual_review_payload,
    visuals_are_ready,
)
from services.quality.artifact_state import ArtifactState, ArtifactStateError  # noqa: E402

LIVE_4249 = 4249
EXPECTED_PHOTO = "465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd"
EXPECTED_COVER = "55567b21e03e3d5734ff5c355c3f4771b4771480d88566ebbdabcbd0d970d016"
EXPECTED_PREVIEW = "b853a69507da0c3a3e5d350f1160bb7675ac6ae076314ed76711de9cadf14126"


def _paid_patches():
    return (
        patch("ai_client.get_client", side_effect=AssertionError("paid client")),
        patch("ai_client.chat", side_effect=AssertionError("paid chat")),
        patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json")),
    )


def _manuscript_ready() -> dict:
    data = build_acceptance_project_data()
    data["acceptance_marker"] = None
    pkg = f"ebook-vis-{uuid.uuid4().hex[:16]}"
    data["artifact_id"] = pkg
    data["package_id"] = pkg
    md = build_event_photo_strong_manuscript()
    data["content"] = md
    data["ebook"] = md
    ws = data["ebook_workspace"]
    ws["marker"] = None
    set_stage_status(ws, "manuscript", STATUS_AWAITING)
    return approve_stage(data, "manuscript")


class EbookVisualPipelineTests(unittest.TestCase):
    def setUp(self):
        self._patches = _paid_patches()
        for p in self._patches:
            p.start()
        self.addCleanup(lambda: [p.stop() for p in self._patches])

    def test_content_aware_plan_is_not_forced_eight(self):
        md = build_event_photo_strong_manuscript()
        plan = plan_content_aware_visuals(md, title="From First Booking to On-Site Prints")
        aids = required_aids(plan)
        self.assertGreaterEqual(len(aids), 4)
        self.assertLessEqual(len(aids), 10)
        self.assertEqual(len(plan["chapters"]), 10)
        types = {a["type"] for a in aids}
        self.assertTrue(types & {"chart", "comparison", "workflow", "timeline", "checklist"})

    def test_empty_manifest_cannot_approve(self):
        data = _manuscript_ready()
        data["visual_plan"] = {}
        data["ebook_visual_manifest"] = {"slots": [], "source": "manuscript_derived"}
        with patch(
            "services.ebook_visual_pipeline.plan_content_aware_visuals",
            return_value={"chapters": []},
        ):
            with self.assertRaises(ValueError) as ctx:
                approve_visuals_local(data)
        self.assertIn("cannot be approved", str(ctx.exception).lower())
        self.assertEqual(stage_status(data["ebook_workspace"], "visuals"), STATUS_NEEDS_CORRECTION)

    def test_missing_and_corrupt_file_block_approval(self):
        data = prepare_visuals_local(_manuscript_ready())
        self.assertTrue(visuals_are_ready(data))
        aid = required_aids(data["visual_plan"])[0]
        path = aid["asset_path"]
        os.remove(path)
        report = validate_visual_readiness(data)
        self.assertFalse(report.ok)
        self.assertTrue(any("no existing local asset" in f for f in report.findings))
        Path(path).write_bytes(b"not-a-png")
        report = validate_visual_readiness(data)
        self.assertFalse(report.ok)
        self.assertTrue(any("corrupt" in f for f in report.findings))
        with self.assertRaises(ValueError):
            approve_visuals_local(data)
        self.assertEqual(stage_status(data["ebook_workspace"], "visuals"), STATUS_NEEDS_CORRECTION)

    def test_approved_metadata_without_files_returns_needs_correction(self):
        data = _manuscript_ready()
        data["visual_plan"] = {"chapters": [{"chapter": "X", "aids": []}]}
        data["ebook_visual_manifest"] = {"source": "manuscript_derived", "slots": [{"chapter": 1}]}
        set_stage_status(data["ebook_workspace"], "visuals", STATUS_APPROVED, note="fake")
        data = reconcile_visuals_gate(data)
        self.assertEqual(stage_status(data["ebook_workspace"], "visuals"), STATUS_NEEDS_CORRECTION)
        self.assertFalse(is_approved(data["ebook_workspace"], "visuals"))

    def test_design_conversion_keeps_figures(self):
        from services.ebook_design_spec import EbookDesign

        data = approve_visuals_local(_manuscript_ready())
        aids = required_aids(data["visual_plan"])
        self.assertTrue(aids)
        data = select_theme(data, "modern_practical")
        html = render_designed_ebook_html(
            title=str(data.get("title") or "Book"),
            subtitle=str(data.get("subtitle") or ""),
            author="Lonnie Brown",
            manuscript_md=str(data.get("content") or ""),
            design=EbookDesign.from_dict(data["ebook_design"]),
            visual_plan=data["visual_plan"],
        )
        for aid in aids:
            self.assertIn(f'data-visual-id="{aid["visual_id"]}"', html)
            self.assertIn(aid["sha256"], html)
            self.assertIn("ebook-figure", html)

    def test_end_to_end_preview_pdf_zip_same_manifest(self):
        from services.ebook_photo_cover import attach_licensed, select_layout
        from services.ebook_design_workspace import select_and_stage_theme

        data = approve_visuals_local(_manuscript_ready())
        plan_before = copy.deepcopy(data["visual_plan"])
        shas = {a["visual_id"]: a["sha256"] for a in required_aids(plan_before)}
        captions = {a["visual_id"]: a["caption"] for a in required_aids(plan_before)}
        data = attach_licensed(data, "event_reception_night", project_id=None)
        data = select_layout(data, "printed_moment", project_id=None)
        data = approve_stage(data, "cover")
        data = select_and_stage_theme(data, "modern_practical")
        data = approve_stage(data, "design")
        data = build_preview(data)
        html = str(data.get("ebook_preview_html") or "")
        self.assertTrue(html)
        for vid, sha in shas.items():
            self.assertIn(f'data-visual-id="{vid}"', html)
            self.assertIn(sha, html)
            self.assertEqual(captions[vid], next(a["caption"] for a in required_aids(data["visual_plan"]) if a["visual_id"] == vid))
        bundle = render_designed_bundle(data)
        pdf = bundle["pdf_bytes"]
        self.assertTrue(pdf.startswith(b"%PDF"))
        with zipfile.ZipFile(io.BytesIO(bundle["zip_bytes"])) as zf:
            names = set(zf.namelist())
            self.assertIn("visual_plan.json", names)
            plan = json.loads(zf.read("visual_plan.json").decode("utf-8"))
            zip_shas = {a["visual_id"]: a["sha256"] for a in required_aids(plan)}
            self.assertEqual(zip_shas, shas)
            for aid in required_aids(plan):
                blob = zf.read(f"visuals/{aid['visual_id']}.png")
                self.assertEqual(hashlib.sha256(blob).hexdigest(), aid["sha256"])
            html_zip = zf.read("ebook.html").decode("utf-8")
            for vid, sha in shas.items():
                self.assertIn(vid, html_zip)
                self.assertIn(sha, html_zip)
        view = workspace_public_view({"id": 1, "name": "iso", "data": data})
        review = view["design"]["visual_review"]
        self.assertEqual(len(review["assets"]), len(shas))
        self.assertTrue(all(a.get("thumb_data_uri") for a in review["assets"]))

    def test_stale_preview_without_figures_blocks_preview_approval(self):
        data = approve_visuals_local(_manuscript_ready())
        data["ebook_preview_html"] = "<html><body><p>no figures</p></body></html>"
        data["preview_html"] = data["ebook_preview_html"]
        data["ebook_export_identity"] = {"preview_digest": "abc", "pdf_sha256": "abc"}
        set_stage_status(data["ebook_workspace"], "design", STATUS_APPROVED)
        with self.assertRaises(ValueError) as ctx:
            approve_stage(data, "preview")
        self.assertIn("visual", str(ctx.exception).lower())

    def test_locked_cannot_prepare_visuals(self):
        data = _manuscript_ready()
        data["artifact_state"] = ArtifactState.LOCKED.value
        data["lock_status"] = "LOCKED"
        with self.assertRaises(ArtifactStateError):
            prepare_visuals_local(data)

    def test_visual_review_payload_lists_every_planned_asset(self):
        data = prepare_visuals_local(_manuscript_ready())
        self.assertEqual(stage_status(data["ebook_workspace"], "visuals"), STATUS_AWAITING)
        self.assertFalse(is_approved(data["ebook_workspace"], "visuals"))
        view = workspace_public_view({"id": 2, "name": "iso", "data": data})
        assets = view["design"]["visual_review"]["assets"]
        self.assertEqual(len(assets), len(required_aids(data["visual_plan"])))
        self.assertTrue(view["design"]["visual_review"]["approvable"])
        self.assertFalse(view["gates"]["approve_preview_enabled"])
        self.assertFalse(view["gates"]["export_enabled"])

    def test_replacement_kinds_photo_chart_workflow_timeline(self):
        pkg = f"ebook-vis-kinds-{uuid.uuid4().hex[:12]}"
        photo_bytes = io.BytesIO()
        img = PILImage.new("RGB", (900, 620), (40, 70, 90))
        draw = PILImageDraw.Draw(img)
        draw.rectangle((40, 40, 500, 400), fill=(200, 150, 80))
        draw.ellipse((200, 120, 780, 560), fill=(20, 30, 40))
        img.save(photo_bytes, format="JPEG")
        photo_aid = store_interior_photo(
            {
                "visual_id": "v_ch1",
                "type": "photo",
                "title": "Event photographer at work",
                "caption": "A working photographer covering a live event.",
                "chapter": "What This Business Actually Looks Like",
                "chapter_index": 1,
                "placement": "after_opening",
                "source": "pexels",
                "attribution": "Photo by Test Photographer on Pexels",
                "photographer": "Test Photographer",
                "page_url": "https://www.pexels.com/photo/event-photographer-covering-celebration-1",
                "photo_id": "1",
                "alt": "event photographer covering a live celebration with a camera",
                "content_labels": [
                    "event photographer",
                    "covering a live celebration",
                    "camera",
                    "wedding reception",
                ],
                "user_accepted": True,
                "seen_full_size": True,
            },
            photo_bytes.getvalue(),
            package_id=pkg,
        )
        photo_sha = photo_aid["sha256"]
        plan = {
            "title": "kinds",
            "source": "replacement_kinds",
            "paid_images": False,
            "chapters": [
                {"chapter": "What This Business Actually Looks Like", "chapter_index": 1, "aids": [photo_aid]},
                {
                    "chapter": "Startup Reality Check",
                    "chapter_index": 2,
                    "aids": [{
                        "visual_id": "v_ch2",
                        "type": "chart",
                        "title": "Startup planning ranges",
                        "caption": "Lean vs event-focused startup ranges from the manuscript.",
                        "chapter": "Startup Reality Check",
                        "chapter_index": 2,
                        "placement": "after_opening",
                        "source": "local_manuscript_chart",
                        "chart_data": {
                            "kind": "bar",
                            "currency": True,
                            "labels": ["Lean startup", "Event-focused"],
                            "values": [3500, 17500],
                        },
                    }],
                },
                {
                    "chapter": "Finding Clients",
                    "chapter_index": 4,
                    "aids": [{
                        "visual_id": "v_ch4",
                        "type": "workflow",
                        "title": "Booking sequence",
                        "caption": "Inquiry to signed booking.",
                        "chapter": "Finding Clients",
                        "chapter_index": 4,
                        "placement": "after_opening",
                        "source": "local_manuscript_workflow",
                        "items": ["Receive inquiry", "Qualify event", "Send proposal", "Confirm booking"],
                    }],
                },
                {
                    "chapter": "30-Day Plan",
                    "chapter_index": 10,
                    "aids": [{
                        "visual_id": "v_ch10",
                        "type": "timeline",
                        "title": "30-day first paid event",
                        "caption": "Four-week roadmap to event one.",
                        "chapter": "30-Day Plan",
                        "chapter_index": 10,
                        "placement": "after_opening",
                        "source": "local_manuscript_timeline",
                        "items": ["Days 1-7 Offer", "Days 8-14 Gear", "Days 15-21 Marketing", "Days 22-30 Sell"],
                    }],
                },
            ],
        }
        materialized = materialize_visual_plan(plan, package_id=pkg)
        aids = {a["visual_id"]: a for a in required_aids(materialized)}
        self.assertEqual(aids["v_ch1"]["type"], "photo")
        self.assertEqual(aids["v_ch1"]["sha256"], photo_sha)
        self.assertEqual(aids["v_ch2"]["type"], "chart")
        self.assertEqual(aids["v_ch4"]["type"], "workflow")
        self.assertEqual(aids["v_ch10"]["type"], "timeline")
        for aid in aids.values():
            self.assertTrue(os.path.isfile(aid["asset_path"]))
            self.assertEqual(len(aid["sha256"]), 64)
        report = validate_visual_readiness({"visual_plan": materialized})
        self.assertTrue(report.ok, report.findings)
        chart_img = render_aid_png(aids["v_ch2"])
        workflow_img = render_aid_png(aids["v_ch4"])
        timeline_img = render_aid_png(aids["v_ch10"])
        self.assertGreater(chart_img.size[0], 200)
        self.assertLess(workflow_img.size[1], 700)
        self.assertLess(timeline_img.size[1], 700)
        with self.assertRaises(ValueError):
            render_aid_png({"type": "photo", "title": "nope"})
        missing_attr = json.loads(json.dumps(materialized))
        missing_attr["chapters"][0]["aids"][0]["attribution"] = ""
        blocked = validate_visual_readiness({"visual_plan": missing_attr})
        self.assertFalse(blocked.ok)
        self.assertTrue(any("attribution" in f for f in blocked.findings))

    def test_station_map_workflow_is_distinct_from_horizontal_booking(self):
        stages = [
            "Prepare equipment and supplies",
            "Capture or receive the photograph",
            "Take the guest's order and payment",
            "Add the order to the print queue",
            "Print the photograph",
            "Perform a quality check",
            "Package and deliver it at guest pickup",
        ]
        booking = {
            "type": "workflow",
            "title": "Inquiry to signed booking",
            "items": [
                "Receive inquiry",
                "Respond quickly",
                "Qualify event",
                "Send proposal",
                "Track follow-up",
                "Confirm booking",
            ],
        }
        station = {
            "type": "workflow",
            "layout": "station_map",
            "title": "Dye-sub production station",
            "items": stages,
        }
        booking_img = render_aid_png(booking)
        station_img = render_aid_png(station)
        self.assertEqual(booking_img.size, (1400, 460))
        self.assertEqual(station_img.size, (1400, 900))
        self.assertNotEqual(booking_img.tobytes(), station_img.tobytes())
        self.assertGreater(station_img.size[1], booking_img.size[1])
        bg = (250, 248, 244)
        w, h = station_img.size
        lower = station_img.crop((0, h // 2, w, h))
        solid = PILImage.new("RGB", lower.size, bg)
        self.assertNotEqual(lower.tobytes(), solid.tobytes())
        truncated = render_aid_png({**station, "layout": None, "items": stages})
        self.assertEqual(truncated.size[1], 460)
        self.assertEqual(len(stages), 7)

    def test_station_map_materialize_keeps_seven_stages(self):
        pkg = f"ebook-vis-station-{uuid.uuid4().hex[:12]}"
        stages = [
            "Prepare equipment and supplies",
            "Capture or receive the photograph",
            "Take the guest's order and payment",
            "Add the order to the print queue",
            "Print the photograph",
            "Perform a quality check",
            "Package and deliver it at guest pickup",
        ]
        plan = {
            "title": "station",
            "source": "local_test",
            "paid_images": False,
            "chapters": [{
                "chapter": "Dye-Sublimation Printing: Setup, Queue, Ordering, Payment, and Pickup",
                "chapter_index": 8,
                "aids": [{
                    "visual_id": "v_ch8",
                    "type": "workflow",
                    "layout": "station_map",
                    "title": "Dye-sub production station",
                    "caption": "Seven-station production line from equipment prep through guest pickup.",
                    "items": stages,
                    "chapter": "Dye-Sublimation Printing: Setup, Queue, Ordering, Payment, and Pickup",
                    "chapter_index": 8,
                    "placement": "after_opening",
                    "source": "local_manuscript_workflow",
                    "required": True,
                }],
            }],
        }
        materialized = materialize_visual_plan(plan, package_id=pkg)
        aid = required_aids(materialized)[0]
        self.assertEqual(aid["layout"], "station_map")
        self.assertEqual(aid["items"], stages)
        self.assertTrue(os.path.isfile(aid["asset_path"]))
        self.assertEqual(int(aid["width"]), 1400)
        self.assertEqual(int(aid["height"]), 900)
        report = validate_visual_readiness({"visual_plan": materialized})
        self.assertTrue(report.ok, report.findings)


class Live4249VisualStopTests(unittest.TestCase):
    def test_live_4249_visuals_awaiting_identities_preserved(self):
        row = database.get_project(LIVE_4249)
        self.assertIsNotNone(row, "project #4249 must exist")
        data = row["data"]
        ws = data.get("ebook_workspace") or {}
        cover = data.get("cover_design") or {}
        src = cover.get("source") or {}
        ident = data.get("ebook_export_identity") or {}
        md = str(data.get("content") or data.get("ebook") or "")
        self.assertEqual(str(src.get("sha256") or ""), EXPECTED_PHOTO)
        self.assertEqual(str(cover.get("cover_digest") or ""), EXPECTED_COVER)
        self.assertEqual(str(ident.get("preview_digest") or ""), EXPECTED_PREVIEW)
        self.assertEqual(str(data.get("title") or ""), "From First Booking to On-Site Prints")
        self.assertEqual(str(data.get("author_brand") or data.get("author") or ""), "Lonnie Brown")
        self.assertEqual(str((data.get("ebook_design") or {}).get("theme_id") or ""), "modern_practical")
        self.assertEqual(str(cover.get("selected_layout") or ""), "full_bleed_editorial")
        self.assertFalse(is_approved(ws, "visuals"))
        self.assertIn(stage_status(ws, "visuals"), {STATUS_AWAITING, STATUS_NEEDS_CORRECTION})
        self.assertFalse(is_approved(ws, "preview"))
        self.assertFalse(data.get("export_ready"))
        aids = required_aids(data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None)
        self.assertGreaterEqual(len(aids), 1)
        for aid in aids:
            self.assertTrue(os.path.isfile(str(aid.get("asset_path") or "")))
            self.assertEqual(len(str(aid.get("sha256") or "")), 64)
        html = str(data.get("ebook_preview_html") or data.get("preview_html") or "")
        self.assertTrue(html)
        self.assertEqual(ident.get("preview_digest"), EXPECTED_PREVIEW)
        self.assertEqual(manuscript_digest(data), ident.get("manuscript_digest") or manuscript_digest(data))

    def test_live_4249_ch8_station_map_not_ch4_reuse(self):
        # Synthetic, locally-rendered "TEST FIXTURE" placeholder image hashes
        # (tests/fixtures/frozen_4249_visuals/) — never real/licensed photos.
        ch4_sha = "32c38f7c729dd3612250d72c07d73431a6588f49c811889dc243a7502738b80f"
        old_ch8_sha = "729cacb7c30a071ddf14cd22a24a84abb37388a1c94aaa5af75efb028e9fab68"
        stages = [
            "Prepare equipment and supplies",
            "Capture or receive the photograph",
            "Take the guest's order and payment",
            "Add the order to the print queue",
            "Print the photograph",
            "Perform a quality check",
            "Package and deliver it at guest pickup",
        ]
        row = database.get_project(LIVE_4249)
        self.assertIsNotNone(row, "project #4249 must exist")
        data = row["data"]
        ws = data.get("ebook_workspace") or {}
        cover = ((data.get("cover_design") or {}).get("source") or {})
        ident = data.get("ebook_export_identity") or {}
        aids = {a["visual_id"]: a for a in required_aids(data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None)}
        ch4 = aids["v_ch4"]
        ch8 = aids["v_ch8"]
        ch4_path = Path(str(ch4.get("asset_path") or ""))
        ch8_path = Path(str(ch8.get("asset_path") or ""))
        self.assertTrue(ch4_path.is_file())
        self.assertTrue(ch8_path.is_file())
        disk4 = hashlib.sha256(ch4_path.read_bytes()).hexdigest()
        disk8 = hashlib.sha256(ch8_path.read_bytes()).hexdigest()
        self.assertEqual(disk4, ch4_sha)
        self.assertEqual(disk4, ch4.get("sha256"))
        self.assertEqual(tuple(ch4.get("items") or []), (
            "Receive inquiry",
            "Respond quickly",
            "Qualify event",
            "Send proposal",
            "Track follow-up",
            "Confirm booking",
        ))
        self.assertEqual(list(ch8.get("items") or []), stages)
        self.assertEqual(str(ch8.get("layout") or ""), "station_map")
        self.assertNotEqual(disk8, disk4)
        self.assertNotEqual(disk8, old_ch8_sha)
        self.assertEqual(disk8, ch8.get("sha256"))
        self.assertEqual(int(ch8.get("width") or 0), 1400)
        self.assertEqual(int(ch8.get("height") or 0), 900)
        self.assertNotEqual(int(ch4.get("height") or 0), int(ch8.get("height") or 0))
        self.assertFalse(is_approved(ws, "visuals"))
        self.assertEqual(str(cover.get("sha256") or ""), EXPECTED_PHOTO)
        self.assertEqual(str(ident.get("preview_digest") or ""), EXPECTED_PREVIEW)
        self.assertEqual(manuscript_digest(data), "cf08285598b6d7ac722844a97a5d54f89da2b37e8b11a5bd3df9768b8010cf98")

    def test_live_4249_independent_briefs_ch7_blocks_visual_approval(self):
        # Synthetic, locally-rendered "TEST FIXTURE" placeholder image hashes
        # (tests/fixtures/frozen_4249_visuals/) — never real/licensed photos.
        expected_files = {
            "v_ch1": "49c14382e35dbc576c06aa8a8f31bd2b321282df68083bec4b160caf8fac858d",
            "v_ch3": "a8cd631346ee7f525d5061aae11b8c630524b168bc1532eb15258800faee591e",
            "v_ch7": "edece74bc6a9da85fbe57f677b0c3e130f94eb2992895e87fcedc1b94a4d2306",
            "v_ch8": "2d7f74a8363b06b6a2103c31a03aea8a4c258d2e9bea41fcc3cd6c2dd60cd805",
            "v_ch9": "07cdb4940b61986d033dca1ed34a985ac32024cedf2e6d6946d478ba062e52a7",
        }
        row = database.get_project(LIVE_4249)
        self.assertIsNotNone(row, "project #4249 must exist")
        data = row["data"]
        ws = data.get("ebook_workspace") or {}
        aids = {a["visual_id"]: a for a in required_aids(data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None)}
        for vid, sha in expected_files.items():
            aid = aids[vid]
            path = Path(str(aid.get("asset_path") or ""))
            self.assertTrue(path.is_file(), vid)
            disk = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(disk, sha, vid)
            self.assertEqual(str(aid.get("sha256") or ""), sha, vid)
        ch1 = aids["v_ch1"]["visual_brief"]
        ch3 = aids["v_ch3"]["visual_brief"]
        ch7 = aids["v_ch7"]["visual_brief"]
        ch9 = aids["v_ch9"]["visual_brief"]
        self.assertIn("photographer", str(ch1.get("required_subject") or "").lower())
        self.assertNotIn("photographer", str(ch3.get("required_subject") or "").lower())
        self.assertIn("camera", str(ch3.get("required_subject") or "").lower())
        self.assertIn("printer", " ".join(ch7.get("required_objects") or []).lower())
        self.assertIn("keepsake", str(ch9.get("required_subject") or "").lower())
        self.assertNotIn("photo printer", str(aids["v_ch9"].get("required_scene") or "").lower())
        self.assertEqual(str(aids["v_ch7"].get("match_status") or ""), "reject")
        self.assertFalse(is_approved(ws, "visuals"))
        payload = visual_review_payload(copy.deepcopy(data))
        self.assertFalse(payload["approvable"])
        self.assertFalse(is_approved(ws, "visuals"))
        self.assertEqual(stage_status(ws, "visuals"), STATUS_AWAITING)


if __name__ == "__main__":
    unittest.main()
