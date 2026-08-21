"""Factory Ebook form uses shared Pexels/photo-cover services. Zero live/paid calls."""
from __future__ import annotations

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
from services.cover_agent import build_image_prompt  # noqa: E402
from services.ebook_cover_local import (  # noqa: E402
    generic_or_mismatched_cover_reason,
    proposed_cover_prompt,
)
from services.ebook_factory_pipeline import (  # noqa: E402
    STATUS_EBOOK_READY,
    STATUS_NEEDS_CORRECTION,
    STATUS_PROJECT_COMPLETED,
    apply_ebook_readiness,
    ebook_project_readiness,
    factory_ebook_completion_state,
    fill_photo_aid_from_pexels,
    images_requested,
    manuscript_quality_failures,
    stamp_plan_render_flags,
    visual_progress_message,
)
from services.ebook_package import build_ebook_package  # noqa: E402
from services.ebook_pexels import PexelsError, pexels_status_label  # noqa: E402
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript  # noqa: E402
from services.ebook_photo_cover import attach_upload, select_layout  # noqa: E402
from services.ebook_project_workspace import (  # noqa: E402
    approve_stage,
    build_acceptance_project_data,
    set_stage_status,
)
from services.ebook_design_workspace import approve_visuals_local  # noqa: E402
from services.ebook_visual_pipeline import is_photo_aid  # noqa: E402

TEEN_TITLE = "How to Keep Your Teen Safe Online"
TEEN_MD = """# How to Keep Your Teen Safe Online

## Social Media Check-In

Parents and teens should review privacy settings together.

## Family Rules

Write clear household rules for phones and apps.
"""
TEEN_FIELDS = {
    "ebook_title": TEEN_TITLE,
    "topic": "teen online safety",
    "audience": "Parents of teenagers",
    "include_images": "Yes",
    "author_brand": "Lonnie Brown",
    "chapters": "2",
}
BH_TITLE = "Black History Word Search Book"
EVENT_TITLE = "From First Booking to On-Site Prints"

MOCK_PLAN = {
    "subtitle": "A short handbook for families",
    "cover_prompt": "Never render BLACK HISTORY as visible lettering on a teen safety cover.",
    "product_summary": "Practical online safety habits for families.",
    "chapters": [
        {
            "chapter": "Social Media Check-In",
            "aids": [
                {
                    "type": "stock photo",
                    "title": "Stock Photo — Parent-Teen Social Media Check-In",
                    "caption": "A parent and teen review social media settings together.",
                    "image_prompt": "photorealistic parent and teenager looking at a smartphone",
                    "keywords": "parent teen smartphone social media",
                },
                {
                    "type": "tip box",
                    "title": "Family check-in tip",
                    "caption": "Keep the conversation calm.",
                    "body": "Sit together and review privacy settings once a week.",
                },
                {
                    "type": "worksheet box",
                    "title": "Privacy checklist",
                    "caption": "Check each setting.",
                    "items": ["Private account", "Location off", "Unknown DMs blocked"],
                },
            ],
        }
    ],
}

MOCK_PEXELS_PHOTO = {
    "id": 1462601,
    "photographer": "Safety Photographer",
    "photographer_url": "https://www.pexels.com/@safety",
    "url": "https://www.pexels.com/photo/teen-1462601",
    "width": 2000,
    "height": 1400,
    "src": {
        "original": "https://images.pexels.com/photos/1462601/original.jpeg",
        "large": "https://images.pexels.com/photos/1462601/large.jpeg",
        "tiny": "https://images.pexels.com/photos/1462601/tiny.jpeg",
    },
}


def _png_bytes(w: int = 1200, h: int = 800, color=(40, 90, 140)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (w, h), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle((40, 40, w - 40, h // 2), fill=(200, 160, 90))
    draw.ellipse((w // 3, h // 3, w - 80, h - 60), fill=(30, 40, 50))
    img.save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_bytes(w: int = 1600, h: int = 2200, color=(40, 90, 140)) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (w, h), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle((60, 80, w - 60, h // 2), fill=(210, 170, 110))
    draw.ellipse((w // 4, h // 4, 3 * w // 4, 3 * h // 4), fill=(20, 30, 40))
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _mock_pexels_http(url, headers, *, binary=False):
    blob = str(url or "") + str(headers or {})
    if "sk-" in blob or "PEXELS_API_KEY" in blob:
        raise AssertionError("Pexels API key leaked into HTTP mock inputs")
    if binary:
        return _jpeg_bytes()
    if "/v1/photos/" in str(url):
        return dict(MOCK_PEXELS_PHOTO)
    return {"photos": [dict(MOCK_PEXELS_PHOTO)]}


def _paid_patches():
    plan = json.loads(json.dumps(MOCK_PLAN))
    return (
        patch("ai_client.get_client", side_effect=AssertionError("paid client")),
        patch("ai_client.chat", side_effect=AssertionError("paid chat")),
        patch("services.product.chat", side_effect=AssertionError("paid chat")),
        patch("ai_client.chat_json", return_value=plan),
        patch("services.ebook_package.chat_json", return_value=plan),
    )


class FactoryEbookPexelsRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self._patches = _paid_patches()
        for item in self._patches:
            item.start()

    def tearDown(self):
        for item in self._patches:
            item.stop()
        os.environ["PEXELS_API_KEY"] = ""

    def test_01_pexels_status_detected_by_running_flask_app(self):
        os.environ["PEXELS_API_KEY"] = ""
        r = self.client.get("/pexels-status")
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        body = r.get_json()
        self.assertEqual(body["status"], "Pexels not configured")
        self.assertFalse(body["configured"])
        text = r.get_data(as_text=True)
        self.assertNotIn("PEXELS_API_KEY", text)
        self.assertNotIn("sk-", text)
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        r = self.client.get("/pexels-status")
        self.assertEqual(r.get_json()["status"], "Pexels connected")
        self.assertNotIn("test-pexels-key-not-live", r.get_data(as_text=True))
        self.assertEqual(pexels_status_label(), "Pexels connected")

    def test_02_simple_ebook_form_reaches_shared_pexels_service(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        with patch("services.product.chat", return_value=TEEN_MD), patch(
            "services.ebook_pexels._http_get", side_effect=_mock_pexels_http
        ) as http:
            gen = self.client.post(
                "/generate-product",
                json={"product_type": "ebook", "fields": TEEN_FIELDS},
            )
            self.assertEqual(gen.status_code, 200, gen.get_data(as_text=True))
            product = gen.get_json()
            enh = self.client.post(
                "/enhance-ebook",
                json={
                    "title": product.get("title") or TEEN_TITLE,
                    "content": product.get("content") or TEEN_MD,
                    "fields": TEEN_FIELDS,
                },
            )
            self.assertEqual(enh.status_code, 200, enh.get_data(as_text=True))
            self.assertTrue(http.called)
            urls = [str(c.args[0]) for c in http.call_args_list]
            self.assertTrue(any("api.pexels.com/v1/search" in u for u in urls))
            payload = enh.get_json()
            self.assertEqual(payload.get("cover_design", {}).get("workflow"), "photo_backed")
            self.assertTrue(payload.get("cover_design", {}).get("selected_layout"))

    def test_03_include_visuals_no_makes_zero_pexels_requests(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        fields = dict(TEEN_FIELDS)
        fields["include_images"] = "No"
        self.assertFalse(images_requested(fields))
        with patch("services.ebook_pexels._http_get", side_effect=AssertionError("pexels")) as http:
            pkg = build_ebook_package(TEEN_TITLE, TEEN_MD, fields)
        http.assert_not_called()
        chapters = (pkg.get("visual_plan") or {}).get("chapters") or []
        photos = [
            aid
            for ch in chapters
            for aid in (ch.get("aids") or [])
            if is_photo_aid(aid)
        ]
        self.assertEqual(photos, [])

    def test_04_include_visuals_yes_stores_local_photo_files(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        with patch("services.ebook_pexels._http_get", side_effect=_mock_pexels_http):
            pkg = build_ebook_package(TEEN_TITLE, TEEN_MD, TEEN_FIELDS)
        photo = None
        for ch in (pkg.get("visual_plan") or {}).get("chapters") or []:
            for aid in ch.get("aids") or []:
                if is_photo_aid(aid):
                    photo = aid
        self.assertIsNotNone(photo)
        self.assertTrue(photo.get("has_file"))
        self.assertTrue(os.path.isfile(str(photo.get("asset_path") or "")))
        with Image.open(photo["asset_path"]) as img:
            img.verify()
        factory = photo.get("factory_asset_path")
        self.assertTrue(factory and os.path.isfile(factory))

    def test_05_missing_local_image_cannot_be_labeled_rendered(self):
        plan = {
            "chapters": [
                {
                    "chapter": "Social Media Check-In",
                    "aids": [
                        {
                            "type": "stock photo",
                            "visual_id": "v0_0",
                            "title": "Stock Photo — Parent-Teen Social Media Check-In",
                            "caption": "Check-in",
                            "status": "resolved",
                            "rendered": True,
                            "has_file": True,
                        }
                    ],
                }
            ]
        }
        stamped = stamp_plan_render_flags(plan, package_id="missing-pkg")
        aid = stamped["chapters"][0]["aids"][0]
        self.assertFalse(aid.get("rendered"))
        self.assertFalse(aid.get("has_file"))
        state = factory_ebook_completion_state(
            visual_plan=stamped,
            cover_design={"workflow": "photo_backed", "source": None},
        )
        self.assertGreater(state["missing_photo_count"], 0)
        self.assertNotEqual(state["rendered_visual_count"], state["required_visual_count"])

    def test_06_pexels_errors_create_visible_retry_state(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"

        def _boom(*_a, **_k):
            raise PexelsError("Pexels request failed.")

        with patch("services.ebook_pexels._http_get", side_effect=_boom):
            aid = fill_photo_aid_from_pexels(
                {
                    "type": "stock photo",
                    "visual_id": "v0_0",
                    "title": "Stock Photo — Parent-Teen Social Media Check-In",
                    "caption": "A parent and teen review social media settings together.",
                },
                package_id="retry-pkg",
                title=TEEN_TITLE,
                topic="teen online safety",
                audience="Parents of teenagers",
                chapter="Social Media Check-In",
            )
        self.assertEqual(aid.get("status"), "missing")
        self.assertTrue(aid.get("retryable"))
        self.assertFalse(aid.get("rendered"))
        self.assertTrue(str(aid.get("error") or aid.get("customer_message") or "").strip())
        self.assertNotIn("401", str(aid.get("error") or ""))
        self.assertNotIn("api.pexels.com", str(aid.get("error") or "").lower())

    def test_07_stock_photo_record_contains_attribution(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        with patch("services.ebook_pexels._http_get", side_effect=_mock_pexels_http):
            pkg = build_ebook_package(TEEN_TITLE, TEEN_MD, TEEN_FIELDS)
        photo = next(
            aid
            for ch in (pkg.get("visual_plan") or {}).get("chapters") or []
            for aid in ch.get("aids") or []
            if is_photo_aid(aid)
        )
        self.assertTrue(photo.get("attribution"))
        self.assertTrue(photo.get("photographer"))
        self.assertTrue(photo.get("page_url"))
        self.assertTrue(photo.get("photo_id"))
        self.assertTrue(photo.get("pexels_query"))
        self.assertIn("pexels", str(photo.get("source") or "").lower())
        blob = json.dumps(photo).lower()
        self.assertNotIn("test-pexels-key-not-live", blob)

    def test_08_generic_prompt_only_covers_fail_qa(self):
        prompt_cover = {
            "title": TEEN_TITLE,
            "author": "Lonnie Brown",
            "use_ai_image": True,
            "image_prompt": "Create a generic blue gradient cover with no photograph.",
            "cover_prompt": "Never render BLACK HISTORY.",
        }
        self.assertEqual(
            generic_or_mismatched_cover_reason(
                prompt_cover, title=TEEN_TITLE, author="Lonnie Brown", topic="teen online safety"
            ),
            "prompt_only_cover",
        )
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        with patch("services.ebook_pexels._http_get", side_effect=_mock_pexels_http):
            pkg = build_ebook_package(TEEN_TITLE, TEEN_MD, TEEN_FIELDS)
        self.assertFalse(pkg.get("ebook_ready"))
        self.assertFalse(pkg.get("cover_ready"))
        self.assertIn("Choose cover photo", pkg.get("next_action") or "")
        self.assertFalse(pkg.get("cover_prompt"))
        cover_txt = Path(pkg["export_files"]["cover_prompt.txt"]).read_text(encoding="utf-8")
        self.assertNotIn("BLACK HISTORY", cover_txt.upper())

    def test_09_cross_topic_prompt_contamination_fails_qa(self):
        teen_prompt = proposed_cover_prompt(
            title=TEEN_TITLE, topic="teen online safety", audience="Parents of teenagers"
        )
        event_prompt = proposed_cover_prompt(
            title=EVENT_TITLE, topic=EVENT_TITLE, audience="new event photographers"
        )
        self.assertNotIn("BLACK HISTORY", teen_prompt.upper())
        self.assertNotIn("BLACK HISTORY", event_prompt.upper())
        self.assertNotIn(EVENT_TITLE.lower(), teen_prompt.lower())
        self.assertNotIn(TEEN_TITLE.lower(), event_prompt.lower())
        analysis = {"style_mode": "photo_realistic", "product_type": "ebook"}
        leaked = build_image_prompt(
            title=TEEN_TITLE,
            subtitle="A practical family guide",
            author="Lonnie Brown",
            cover_prompt="Never render BLACK HISTORY as visible lettering.",
            analysis=analysis,
            style="modern_business",
        )
        self.assertNotIn("BLACK HISTORY", leaked.upper())
        self.assertEqual(
            generic_or_mismatched_cover_reason(
                {
                    "title": TEEN_TITLE,
                    "author": "Lonnie Brown",
                    "cover_prompt": "BLACK HISTORY WORD SEARCH BOOK background",
                    "qa_marker": "Heritage",
                },
                title=TEEN_TITLE,
                author="Lonnie Brown",
                topic="teen online safety",
            ),
            "cross_topic_prompt_contamination",
        )
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        with patch("services.ebook_pexels._http_get", side_effect=_mock_pexels_http):
            teen_pkg = build_ebook_package(TEEN_TITLE, TEEN_MD, TEEN_FIELDS)
            event_pkg = build_ebook_package(
                EVENT_TITLE,
                "# From First Booking to On-Site Prints\n\n## First Booking\nBook the job.\n",
                {
                    "ebook_title": EVENT_TITLE,
                    "topic": EVENT_TITLE,
                    "audience": "new event photographers",
                    "include_images": "Yes",
                    "author_brand": "Lonnie Brown",
                },
            )
        teen_q = str(teen_pkg.get("cover_search_query") or "").lower()
        event_q = str(event_pkg.get("cover_search_query") or "").lower()
        self.assertNotIn("black history", teen_q)
        self.assertNotIn("black history", event_q)
        self.assertNotIn("first booking", teen_q)
        self.assertNotIn("teen safe", event_q)
        teen_cover = json.dumps(teen_pkg.get("cover_design") or {}, default=str).lower()
        event_cover = json.dumps(event_pkg.get("cover_design") or {}, default=str).lower()
        self.assertNotIn("black history", teen_cover)
        self.assertNotIn(EVENT_TITLE.lower(), teen_cover)
        self.assertNotIn(TEEN_TITLE.lower(), event_cover)

    def test_10_changed_source_photo_sha_clears_cover_selection(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        pkg = f"sha-clear-{uuid.uuid4().hex[:12]}"
        data["package_id"] = pkg
        data["artifact_id"] = pkg
        md = build_event_photo_strong_manuscript()
        data["content"] = md
        data["ebook"] = md
        set_stage_status(data["ebook_workspace"], "manuscript", "awaiting_approval")
        data = approve_stage(data, "manuscript")
        data = approve_visuals_local(data)
        first = _jpeg_bytes(color=(20, 40, 80))
        second = _jpeg_bytes(color=(180, 30, 30))
        data = attach_upload(
            data,
            first,
            filename="one.jpg",
            license_note="Author-owned photograph.",
            owned=True,
            project_id=None,
        )
        passing = [
            lid
            for lid, row in (data["cover_design"].get("variants") or {}).items()
            if ((row or {}).get("quality") or {}).get("pass")
        ]
        self.assertTrue(passing)
        data = select_layout(data, passing[0], project_id=None)
        self.assertTrue(data["cover_design"].get("selected_layout"))
        sha_a = data["cover_design"]["source"]["sha256"]
        data = attach_upload(
            data,
            second,
            filename="two.jpg",
            license_note="Author-owned photograph.",
            owned=True,
            project_id=None,
        )
        self.assertFalse(data["cover_design"].get("selected_layout"))
        self.assertNotEqual(data["cover_design"]["source"]["sha256"], sha_a)

    def test_11_approved_cover_identity_matches_export_slots(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        pkg = f"ident-{uuid.uuid4().hex[:12]}"
        data["package_id"] = pkg
        data["artifact_id"] = pkg
        md = build_event_photo_strong_manuscript()
        data["content"] = md
        data["ebook"] = md
        set_stage_status(data["ebook_workspace"], "manuscript", "awaiting_approval")
        data = approve_stage(data, "manuscript")
        data = approve_visuals_local(data)
        data = attach_upload(
            data,
            _jpeg_bytes(),
            filename="cover.jpg",
            license_note="Author-owned photograph.",
            owned=True,
            project_id=None,
        )
        passing = [
            lid
            for lid, row in (data["cover_design"].get("variants") or {}).items()
            if ((row or {}).get("quality") or {}).get("pass")
        ]
        self.assertTrue(passing)
        data = select_layout(data, passing[0], project_id=None)
        cover = data["cover_design"]
        sha = cover["source"]["sha256"]
        digest = cover["cover_digest"]
        selected = cover["selected_layout"]
        row = cover["variants"][selected]
        self.assertEqual(row.get("source_sha256"), sha)
        self.assertEqual(row.get("digest"), digest)
        self.assertTrue(os.path.isfile(str(row.get("png_path") or "")))
        self.assertTrue(os.path.isfile(str(row.get("pdf_path") or "")))
        self.assertEqual(hashlib.sha256(Path(row["pdf_path"]).read_bytes()).hexdigest(), digest)
        self.assertEqual(hashlib.sha256(Path(row["png_path"]).read_bytes()).hexdigest(), row.get("png_digest"))

    def test_12_ebook_ready_impossible_when_pdf_unavailable(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        with patch("services.ebook_pexels._http_get", side_effect=_mock_pexels_http):
            pkg = build_ebook_package(TEEN_TITLE, TEEN_MD, TEEN_FIELDS)
        self.assertFalse(pkg.get("pdf_available"))
        self.assertFalse(pkg.get("ebook_ready"))
        self.assertFalse(pkg.get("export_ready"))
        self.assertIn("Choose cover photo", pkg.get("next_action") or "")
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Needs correction", js)
        self.assertIn("ebook_ready === true && d.export_ready === true && d.pdf_available === true", js)
        self.assertNotIn("Image will appear once generated.", js)

    def test_13_project_4249_identities_unchanged(self):
        expected_photo = "465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd"
        expected_cover = "55567b21e03e3d5734ff5c355c3f4771b4771480d88566ebbdabcbd0d970d016"
        expected_preview = "b853a69507da0c3a3e5d350f1160bb7675ac6ae076314ed76711de9cadf14126"
        row = database.get_project(4249)
        self.assertIsNotNone(row, "project #4249 must exist")
        data = row.get("data") or {}
        cover = data.get("cover_design") or {}
        source = cover.get("source") or {}
        ident = data.get("ebook_export_identity") or {}
        self.assertEqual(str(data.get("title") or ""), EVENT_TITLE)
        self.assertEqual(str(source.get("sha256") or ""), expected_photo)
        self.assertEqual(str(cover.get("cover_digest") or ""), expected_cover)
        self.assertEqual(str(ident.get("preview_digest") or data.get("ebook_preview_digest") or ""), expected_preview)


def _incomplete_teen_data(*, missing=True) -> dict:
    aid = {
        "type": "stock photo",
        "visual_id": "v0_0",
        "title": "Stock Photo — Parent-Teen Social Media Check-In",
        "caption": "A parent and teen review social media settings together.",
        "status": "missing" if missing else "resolved",
        "rendered": not missing,
        "has_file": not missing,
        "approved": False,
    }
    extras = [
        {"type": "tip box", "title": "Tip", "caption": "Tip", "rendered": True},
        {"type": "worksheet box", "title": "Sheet", "caption": "Sheet", "rendered": True},
    ]
    return {
        "product_type": "ebook",
        "title": TEEN_TITLE,
        "content": TEEN_MD,
        "ebook": TEEN_MD,
        "package_id": "teen-ready-pkg",
        "visual_plan": {
            "chapters": [
                {"chapter": "Social Media Check-In", "aids": [aid, *extras]},
            ]
        },
        "cover_design": {"workflow": "photo_backed", "source": None, "approved": False},
        "exports": {
            "pdf_available": True,
            "files": {
                "html": {"name": "ebook.html", "url": "/download/teen-ready-pkg/ebook.html"},
                "txt": {"name": "ebook.txt", "url": "/download/teen-ready-pkg/ebook.txt"},
                "zip": {"name": "package.zip", "url": "/download/teen-ready-pkg/package.zip"},
                "pdf": {"name": "ebook.pdf", "url": "/download/teen-ready-pkg/ebook.pdf"},
            },
        },
        "quality_result": {"errors": ["Forever-forbidden marketing claims found: ['guaranteed']"]},
    }


class FactoryEbookReadinessTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self._patches = _paid_patches()
        for item in self._patches:
            item.start()

    def tearDown(self):
        for item in self._patches:
            item.stop()
        os.environ["PEXELS_API_KEY"] = ""

    def test_14_contradictory_labels_impossible_when_assets_missing(self):
        data = apply_ebook_readiness(_incomplete_teen_data())
        self.assertEqual(data["status_label"], STATUS_NEEDS_CORRECTION)
        self.assertNotEqual(data["status_label"], STATUS_EBOOK_READY)
        self.assertNotEqual(data["status_label"], STATUS_PROJECT_COMPLETED)
        self.assertFalse(data["ebook_ready"])
        self.assertFalse(data["export_ready"])
        self.assertFalse(data["pdf_available"])
        self.assertFalse(data["zip_available"])
        self.assertEqual(data["next_action"], "Retry missing image")
        ready_and_blocked = data["ebook_ready"] and data["missing_photo_count"]
        self.assertFalse(ready_and_blocked)
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("factoryEbookReady", js)
        self.assertIn("d.status_label", js)
        self.assertNotRegex(js, r"still need retrieval")

    def test_15_no_active_zip_pdf_when_assets_missing(self):
        data = apply_ebook_readiness(_incomplete_teen_data())
        files = (data.get("exports") or {}).get("files") or {}
        self.assertNotIn("zip", files)
        self.assertNotIn("pdf", files)
        self.assertIn("html", files)
        self.assertIn("txt", files)
        self.assertFalse(data["pdf_enabled"])
        self.assertFalse(data["zip_enabled"])
        self.assertTrue(data["draft_files_only"])
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Draft files.", js)
        self.assertIn("ebookLocked", js)
        self.assertIn('dl(f.zip, "Download ZIP Package")', js)

    def test_16_ebook_ready_impossible_without_photo_cover_and_pdf(self):
        state = ebook_project_readiness(_incomplete_teen_data())
        self.assertGreater(state["missing_photo_count"], 0)
        self.assertFalse(state["cover_ready"])
        self.assertFalse(state["ebook_ready"])
        self.assertFalse(state["pdf_available"])
        with patch("services.ebook_pexels._http_get", side_effect=_mock_pexels_http):
            pkg = build_ebook_package(TEEN_TITLE, TEEN_MD, TEEN_FIELDS)
        self.assertFalse(pkg.get("ebook_ready"))
        self.assertFalse(pkg.get("pdf_available"))
        self.assertNotIn("zip", ((pkg.get("exports") or {}).get("files") or {}))
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("ebook_ready === true && d.export_ready === true && d.pdf_available === true", js)

    def test_17_grammar_one_photograph_still_needs_retrieval(self):
        msg = visual_progress_message(
            {"required_visual_count": 22, "rendered_visual_count": 21, "missing_photo_count": 1}
        )
        self.assertEqual(msg, "21 of 22 visuals stored on disk · 1 photograph still needs retrieval.")
        plural = visual_progress_message(
            {"required_visual_count": 22, "rendered_visual_count": 20, "missing_photo_count": 2}
        )
        self.assertIn("2 photographs still need retrieval", plural)
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('missingPhotos === 1 ? "needs" : "need"', js)
        self.assertIn("visual_status_message", js)

    def test_18_guaranteed_warning_requires_manuscript_match(self):
        none = manuscript_quality_failures(
            TEEN_MD,
            {"errors": ["Forever-forbidden marketing claims found: ['guaranteed']"]},
        )
        self.assertEqual(none, [])
        hits = manuscript_quality_failures(
            TEEN_MD + "\n\nThis method is guaranteed to work for every family.\n"
        )
        self.assertTrue(any(row.get("phrase") == "guaranteed" for row in hits))
        self.assertTrue(any("guaranteed" in (row.get("excerpt") or "") for row in hits))
        disclaimer = manuscript_quality_failures(
            "Compounding is not instant, and it is not guaranteed. Nothing is guaranteed."
        )
        self.assertFalse(any(row.get("phrase") == "guaranteed" for row in disclaimer))
        md_neg = manuscript_quality_failures(
            "Earnings and booking volume are **not guaranteed**, and this guide will not claim otherwise."
        )
        self.assertFalse(any(row.get("phrase") == "guaranteed" for row in md_neg))
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("manuscript_quality_failures", js)
        self.assertIn("guaranteedHit", js)

    def test_19_mocked_retry_stores_photo_choose_cover_unapproved(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        pkg = f"retry-teen-{uuid.uuid4().hex[:12]}"
        data = _incomplete_teen_data()
        data["package_id"] = pkg
        project = database.create_project(
            "Readiness Retry Teen Photo",
            "ebook",
            data,
            user_saved=False,
            system_test=True,
            temporary=True,
        )
        pid = project["id"]
        manuscript_before = data["content"]
        with patch("services.ebook_pexels._http_get", side_effect=_mock_pexels_http):
            res = self.client.post(
                "/retry-ebook-visual",
                json={
                    "project_id": pid,
                    "package_id": pkg,
                    "visual_id": "v0_0",
                    "aid": data["visual_plan"]["chapters"][0]["aids"][0],
                    "title": TEEN_TITLE,
                    "fields": TEEN_FIELDS,
                    "chapter": "Social Media Check-In",
                    "cover_design": data["cover_design"],
                    "visual_plan": data["visual_plan"],
                },
            )
        self.assertEqual(res.status_code, 200, res.get_data(as_text=True))
        body = res.get_json()
        self.assertTrue(body.get("ok"))
        aid = body.get("aid") or {}
        self.assertTrue(aid.get("has_file"))
        self.assertTrue(aid.get("rendered"))
        self.assertFalse(aid.get("approved"))
        self.assertTrue(aid.get("attribution"))
        self.assertIn("Pexels", str(aid.get("attribution") or ""))
        self.assertEqual(str(aid.get("photographer") or ""), "Safety Photographer")
        local = str(aid.get("asset_path") or aid.get("factory_asset_path") or "")
        self.assertTrue(local and os.path.isfile(local))
        with Image.open(local) as img:
            img.verify()
        self.assertEqual(body.get("next_action"), "Choose cover photo")
        self.assertFalse(body.get("ebook_ready"))
        self.assertEqual(body.get("status_label"), STATUS_NEEDS_CORRECTION)
        stored = database.get_project(pid)
        stored_data = stored.get("data") or {}
        self.assertEqual(stored_data.get("content"), manuscript_before)
        self.assertEqual(stored_data.get("ebook"), manuscript_before)
        photo = stored_data["visual_plan"]["chapters"][0]["aids"][0]
        self.assertTrue(photo.get("has_file"))
        self.assertFalse(photo.get("approved"))
        self.assertIn("Parent-Teen Social Media Check-In", str(photo.get("title") or ""))
        cover = stored_data.get("cover_design") or {}
        self.assertFalse(cover.get("approved"))
        self.assertFalse(cover.get("selected_layout"))
        row_4249 = database.get_project(4249)
        cover_4249 = (row_4249.get("data") or {}).get("cover_design") or {}
        self.assertEqual(
            str((cover_4249.get("source") or {}).get("sha256") or ""),
            "465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd",
        )


if __name__ == "__main__":
    unittest.main()
