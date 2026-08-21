"""Canonical factory ebook customer-path repairs. Zero paid/external calls."""
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
from services.ebook_contamination import (  # noqa: E402
    detect_contamination,
    gate_ebook_output,
    normalize_author,
    normalize_book_title,
    sanitize_manuscript,
)
from services.ebook_customer_path import (  # noqa: E402
    SAVE_SUCCESS,
    complete_factory_ebook,
    container_gardening_manuscript,
    regenerate_factory_cover,
    save_factory_ebook,
)
from services.ebook_pexels import PexelsError, pexels_health  # noqa: E402

TEEN_TITLE = "How to Keep Your Teen Safe Online"
TEEN_MD = """# How to Keep Your Teen Safe Online

## Social Media Check-In

Parents and teens should review privacy settings together.

## Family Rules

Write clear household rules for phones and apps.
"""
TEEN_FIELDS = {
    "ebook_title": ": How to Keep Your Teen Safe Online",
    "topic": "teen online safety",
    "audience": "Parents of teenagers",
    "include_images": "Yes",
    "author_brand": "Lonnie Brown",
    "chapters": "2",
    "visuals_authorized": "true",
    "visual_budget_cap_usd": "0.16",
}

MOCK_PLAN = {
    "subtitle": "A short handbook for families",
    "cover_prompt": "Parent and teen at home with a phone, no lettering.",
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
                    "type": "table",
                    "title": "Check-in steps",
                    "caption": "A short family plan.",
                    "table": {
                        "headers": ["Step", "What to do", "Why"],
                        "rows": [["1", "Sit together", "Keeps the talk calm"]],
                    },
                },
            ],
        },
        {
            "chapter": "Family Rules",
            "aids": [
                {
                    "type": "worksheet box",
                    "title": "House rules",
                    "caption": "Write the rules down.",
                    "items": ["Private accounts", "No unknown DMs"],
                },
                {
                    "type": "tip box",
                    "title": "Keep it short",
                    "caption": "One rule at a time.",
                    "body": "Review one app setting together.",
                },
            ],
        },
    ],
}

MOCK_PEXELS_PHOTO = {
    "id": 1462601,
    "photographer": "Safety Photographer",
    "photographer_url": "https://www.pexels.com/@safety",
    "url": "https://www.pexels.com/photo/teen-1462601",
    "width": 2000,
    "height": 2800,
    "src": {
        "original": "https://images.pexels.com/photos/1462601/original.jpeg",
        "large": "https://images.pexels.com/photos/1462601/large.jpeg",
    },
}


def _jpeg_bytes(w=1600, h=2200, color=(40, 90, 140)):
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
        patch("services.product.chat", return_value=TEEN_MD),
        patch("ai_client.chat_json", return_value=plan),
        patch("services.ebook_package.chat_json", return_value=plan),
    )


class EbookCustomerPathTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        os.environ["FACTORY_TEST_MODE"] = "1"
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        self._created_ids: list[int] = []
        self._patches = _paid_patches()
        for item in self._patches:
            item.start()
        self._http = patch("services.ebook_pexels._http_get", side_effect=_mock_pexels_http)
        self._http.start()

    def tearDown(self):
        for pid in self._created_ids:
            try:
                database.delete_project(int(pid))
            except Exception:
                pass
        self._http.stop()
        for item in self._patches:
            item.stop()
        os.environ["PEXELS_API_KEY"] = ""

    def test_title_leading_colon_is_stripped(self):
        self.assertEqual(
            normalize_book_title(": Beginner’s Guide to Container Gardening"),
            "Beginner's Guide to Container Gardening",
        )
        from services.ebook_pexels import _sanitize_installed_key

        self.assertEqual(
            _sanitize_installed_key("KeyABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"),
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890",
        )
        md = sanitize_manuscript(
            "# Book\n\n## A practical, beginner-friendly handbook for growing vegetables and herbs in pots, tubs, and small spaces\n\n## Why Pots Work\nPots help.\n",
            title="Beginner's Guide to Container Gardening",
        )
        self.assertNotIn("handbook for growing", md.split("##")[1] if "##" in md else "")
        self.assertIn("Why Pots Work", md)

    def test_contamination_blocks_pexels_error_and_factory_brand(self):
        dirty = "401 Client Error: Unauthorized for url: https://api.pexels.com/v1/search Retry missing image. Digital Product Factory"
        hits = detect_contamination(dirty)
        codes = {row["code"] for row in hits}
        self.assertIn("http_error", codes)
        self.assertIn("retry_missing_image", codes)
        self.assertIn("factory_brand", codes)
        self.assertIn("provider_url", codes)

    def test_generate_product_completes_cover_and_omits_errors(self):
        gen = self.client.post("/generate-product", json={"product_type": "ebook", "fields": TEEN_FIELDS})
        self.assertEqual(gen.status_code, 200, gen.get_data(as_text=True))
        payload = gen.get_json()
        self.assertEqual(payload.get("title"), TEEN_TITLE)
        self.assertEqual(payload.get("author_brand"), "Lonnie Brown")
        html = payload.get("preview_html") or ""
        self.assertNotIn("401 Client", html)
        self.assertNotIn("Unauthorized", html)
        self.assertNotIn("Retry missing image", html)
        self.assertNotIn("Digital Product Factory", html)
        self.assertNotIn("127.0.0.1", html)
        self.assertTrue((payload.get("cover_design") or {}).get("selected_layout"))
        self.assertTrue(payload.get("ebook_ready"), payload.get("next_action") or payload.get("contamination"))
        findings = gate_ebook_output(
            title=payload.get("title") or "",
            author=payload.get("author") or payload.get("author_brand") or "",
            manuscript=TEEN_MD,
            html=html,
        )
        self.assertFalse(any(row["code"] in {"http_error", "factory_brand", "retry_missing_image"} for row in findings), findings)

    def test_pexels_health_never_leaks_key(self):
        r = self.client.get("/pexels-status")
        self.assertEqual(r.status_code, 200)
        text = r.get_data(as_text=True)
        self.assertNotIn("test-pexels-key-not-live", text)
        self.assertNotIn("PEXELS_API_KEY", text)
        health = pexels_health(live_auth=False)
        self.assertTrue(health.get("configured"))
        self.assertNotIn("test-pexels-key-not-live", json.dumps(health))

    def test_save_is_idempotent_and_reopen_does_not_generate(self):
        gen = self.client.post("/generate-product", json={"product_type": "ebook", "fields": TEEN_FIELDS})
        data = gen.get_json()
        first = self.client.post("/ebook/save", json={"name": data["title"], "data": data})
        self.assertEqual(first.status_code, 200, first.get_data(as_text=True))
        body = first.get_json()
        self.assertEqual(body.get("message"), SAVE_SUCCESS)
        pid = body.get("project_id") or body.get("id")
        self.assertIsNotNone(pid)
        self._created_ids.append(int(pid))
        second = self.client.post("/ebook/save", json={"name": data["title"], "project_id": pid, "data": data})
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.get_json().get("project_id") or second.get_json().get("id"), pid)
        opened = self.client.get(f"/projects/{pid}")
        self.assertEqual(opened.status_code, 200)
        stored = opened.get_json()
        self.assertEqual(stored.get("type"), "ebook")
        self.assertEqual((stored.get("data") or {}).get("title"), TEEN_TITLE)
        row = database.get_project(int(pid))
        self.assertTrue(
            database.is_customer_saved_product(row),
            "Saved ebook must appear on the customer Saved Projects list",
        )

    def test_regenerate_cover_keeps_prior_on_failure(self):
        gen = self.client.post("/generate-product", json={"product_type": "ebook", "fields": TEEN_FIELDS})
        data = gen.get_json()
        saved = self.client.post("/ebook/save", json={"name": data["title"], "data": data}).get_json()
        pid = saved.get("project_id") or saved.get("id")
        self._created_ids.append(int(pid))
        prior = ((saved.get("project") or {}).get("data") or data).get("cover_design")
        fail = self.client.post("/ebook/regenerate-cover", json={"project_id": pid, "simulate_failure": True})
        self.assertEqual(fail.status_code, 200, fail.get_data(as_text=True))
        self.assertFalse(fail.get_json().get("cover_regenerated"))
        self.assertIn("kept", (fail.get_json().get("message") or "").lower())
        stored = database.get_project(int(pid))
        self.assertEqual(
            str(((stored.get("data") or {}).get("cover_design") or {}).get("selected_layout") or ""),
            str((prior or {}).get("selected_layout") or ""),
        )

    def test_container_fixture_has_author_and_real_chapters(self):
        md = container_gardening_manuscript()
        self.assertIn("Lonnie Brown", CONTAINER_AUTHOR := "Lonnie Brown")
        self.assertIn("Why Container Gardening Works for Beginners", md)
        self.assertNotIn("Digital Product Factory", md)
        self.assertFalse(md.lstrip().startswith(":"))

    def test_4249_cover_hash_unchanged(self):
        row = database.get_project(4249)
        self.assertIsNotNone(row)
        cover = (row.get("data") or {}).get("cover_design") or {}
        self.assertEqual(
            str((cover.get("source") or {}).get("sha256") or ""),
            "465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd",
        )

    def test_visual_noun_phrase_not_sentence(self):
        from services.ebook_pexels import chapter_pexels_queries, cover_pexels_queries, topic_pexels_query

        query = topic_pexels_query(
            title="Beginner's Guide to Container Gardening",
            topic="How beginners can grow vegetables and herbs in containers, including choosing pots, soil, plants, watering, sunlight, pest control, and harvesting.",
        )
        self.assertNotIn("including", query.lower())
        self.assertNotIn("portrait", query.lower())
        self.assertNotIn("book cover", query.lower())
        self.assertLessEqual(len(query.split()), 6)
        covers = cover_pexels_queries(
            title="Beginner's Guide to Container Gardening",
            topic="How beginners can grow vegetables and herbs in containers, including choosing pots",
        )
        self.assertIn("container vegetable garden patio", covers)
        self.assertTrue(all(len(item.split()) <= 8 for item in covers))
        chapters = chapter_pexels_queries(
            chapter="Water, Sun, and Daily Care",
            title="Beginner's Guide to Container Gardening",
            topic="container gardening",
        )
        self.assertTrue(any("watering" in item for item in chapters))

    def test_photo_led_subject_classification(self):
        from services.ebook_visual_match import INFORMATION_LED, PHOTO_LED, classify_ebook_subject

        self.assertEqual(
            classify_ebook_subject(title="Beginner's Guide to Container Gardening", topic="vegetables in pots"),
            PHOTO_LED,
        )
        self.assertEqual(
            classify_ebook_subject(title="How to Keep Your Teen Safe Online", topic="teen online safety"),
            INFORMATION_LED,
        )

    def test_cover_candidate_selection_ranks_garden_scene(self):
        from services.ebook_visual_match import score_cover_photo

        garden = {
            "photo_id": "1",
            "alt": "Tomatoes and herbs growing in pots on a sunny patio",
            "page_url": "https://www.pexels.com/photo/tomato-pots-patio",
            "width": 2000,
            "height": 2800,
        }
        office = {
            "photo_id": "2",
            "alt": "Person typing on a laptop in an office",
            "page_url": "https://www.pexels.com/photo/office-laptop",
            "width": 2000,
            "height": 2800,
        }
        title = "Beginner's Guide to Container Gardening"
        self.assertGreater(
            score_cover_photo(garden, title=title, topic="container gardening"),
            score_cover_photo(office, title=title, topic="container gardening"),
        )
        self.assertEqual(score_cover_photo(office, title=title, topic="container gardening"), 0.0)

    def test_photo_led_plan_has_one_photo_per_chapter(self):
        from services.ebook_package import generate_visual_plan
        from services.ebook_customer_path import container_gardening_manuscript

        plan = generate_visual_plan(
            "Beginner's Guide to Container Gardening",
            container_gardening_manuscript(),
            {"topic": "container gardening", "subtitle": "Grow vegetables in pots"},
        )
        chapters = plan.get("chapters") or []
        self.assertGreaterEqual(len(chapters), 6)
        photo_chapters = 0
        boxes = 0
        for ch in chapters:
            self.assertNotEqual((ch.get("chapter") or "").lower(), "table of contents")
            types = [str(a.get("type") or "").lower() for a in (ch.get("aids") or [])]
            if any("photo" in t for t in types):
                photo_chapters += 1
            boxes += sum(1 for t in types if "photo" not in t)
        self.assertGreaterEqual(photo_chapters, 6)
        self.assertLessEqual(boxes, photo_chapters + 1)


if __name__ == "__main__":
    unittest.main()
