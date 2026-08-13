"""Stock-photo / upload Ebook cover workflow. Zero paid/live Pexels calls.

Does not mutate live project #2472. Isolated projects only except read-only
#4249 generate-block / digest-immutability checks.
"""
from __future__ import annotations

import copy
import hashlib
import io
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ["FACTORY_TEST_MODE"] = "1"
os.environ["PEXELS_API_KEY"] = ""

import database  # noqa: E402
from app import app  # noqa: E402
from services.ebook_design_workspace import (  # noqa: E402
    approve_visuals_local,
    generate_and_stage_cover,
    stage_photo_cover,
)
from services.ebook_manuscript_engine import FROZEN_2472_SHA256, FROZEN_2472_SPENT_USD  # noqa: E402
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript  # noqa: E402
from services.ebook_pexels import (  # noqa: E402
    PEXELS_NOT_CONFIGURED,
    SUGGESTED_SEARCHES,
    PexelsError,
    download_pexels_original,
    search_pexels,
)
from services.ebook_photo_cover import (  # noqa: E402
    FORBIDDEN_LABELS,
    LAYOUT_IDS,
    PhotoCoverError,
    apply_editor,
    attach_licensed,
    attach_pexels,
    attach_upload,
    build_licensed_event_photo,
    photo_cover_preflight_failures,
    select_layout,
)
from services.ebook_project_workspace import (  # noqa: E402
    approve_stage,
    build_acceptance_project_data,
    manuscript_digest,
    set_stage_status,
    workspace_public_view,
)

MOCK_PEXELS_PHOTO = {
    "id": 4249001,
    "photographer": "Test Photographer",
    "photographer_url": "https://www.pexels.com/@test",
    "url": "https://www.pexels.com/photo/event-4249001",
    "width": 2000,
    "height": 3000,
    "src": {
        "original": "https://images.pexels.com/photos/4249001/original.jpeg",
        "large": "https://images.pexels.com/photos/4249001/large.jpeg",
        "tiny": "https://images.pexels.com/photos/4249001/tiny.jpeg",
    },
}


def _png_bytes(w: int = 1200, h: int = 1800, color=(40, 80, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _event_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    build_licensed_event_photo().save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _mock_pexels_http(url, headers, *, binary=False):
    blob = str(url or "") + str(headers or {})
    if "sk-" in blob or "PEXELS_API_KEY" in blob:
        raise AssertionError("Pexels API key leaked into HTTP mock inputs")
    if binary:
        return _event_jpeg_bytes()
    if "/v1/photos/" in str(url):
        return dict(MOCK_PEXELS_PHOTO)
    return {"photos": [dict(MOCK_PEXELS_PHOTO)]}


class PhotoCoverWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self._client_patch = patch("ai_client.get_client", side_effect=AssertionError("paid client"))
        self._chat_patch = patch("ai_client.chat", side_effect=AssertionError("paid chat"))
        self._json_patch = patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json"))
        self._client_patch.start()
        self._chat_patch.start()
        self._json_patch.start()

    def tearDown(self):
        self._client_patch.stop()
        self._chat_patch.stop()
        self._json_patch.stop()

    def _project(self) -> tuple[int, dict]:
        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        pkg = f"ebook-photo-{uuid.uuid4().hex[:16]}"
        data["artifact_id"] = pkg
        data["package_id"] = pkg
        md = build_event_photo_strong_manuscript()
        data["content"] = md
        data["ebook"] = md
        data["ebook_workspace"]["marker"] = None
        set_stage_status(data["ebook_workspace"], "manuscript", "awaiting_approval")
        data = approve_stage(data, "manuscript")
        data = approve_visuals_local(data)
        project = database.create_project(
            "Photo Cover Isolated",
            "ebook",
            data,
            user_saved=False,
            system_test=True,
            temporary=True,
        )
        pid = project["id"]
        data["_project_id"] = pid
        database.update_project(pid, None, data)
        return pid, dict(database.get_project(pid)["data"])

    def test_01_js_cover_panel_pexels_and_upload_choices(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("SEARCH PEXELS", js)
        self.assertIn("UPLOAD MY PHOTO", js)
        self.assertIn("data-ws-cover-pexels-search", js)
        self.assertIn("data-ws-cover-pexels-select", js)
        self.assertIn("data-ws-cover-upload", js)
        self.assertIn("I own this image or have permission to use it commercially.", js)
        self.assertIn("Optional paid feature — not configured", js)
        self.assertIn("data-ws-cover-layout", js)
        self.assertIn("data-ws-cover-preview", js)
        self.assertIn("data-ws-approve-cover disabled", js)
        self.assertIn("if (!coverApprovable) return", js)
        self.assertNotIn("data-ws-generate-cover", js)
        self.assertNotIn("data-ws-cover-select-licensed", js)
        example = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("PEXELS_API_KEY=", example)
        self.assertNotRegex(example.split("PEXELS_API_KEY=")[1].splitlines()[0], r"[A-Za-z0-9]{12,}")

    def test_02_missing_pexels_key_message_upload_still_available(self):
        os.environ["PEXELS_API_KEY"] = ""
        result = search_pexels("event photographer camera")
        self.assertEqual(result["message"], PEXELS_NOT_CONFIGURED)
        self.assertEqual(result["photos"], [])
        self.assertFalse(result["configured"])
        pid, data = self._project()
        r = self.client.post(
            f"/ebook-workspace/{pid}/cover",
            json={"action": "pexels-search", "query": "event photographer camera"},
        )
        self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
        photo = r.get_json()["workspace"]["design"]["cover"]["photo"]
        self.assertEqual(photo["pexels"]["message"], PEXELS_NOT_CONFIGURED)
        self.assertIn("data-ws-cover-upload", (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8"))

    def test_03_test_mode_never_calls_live_pexels(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        try:
            with self.assertRaises(PexelsError) as ctx:
                search_pexels("wedding event photography")
            self.assertIn("test mode", str(ctx.exception).lower())
            self.assertNotIn("test-pexels-key-not-live", str(ctx.exception))
        finally:
            os.environ["PEXELS_API_KEY"] = ""

    def test_04_mocked_search_has_attribution_and_no_key_leak(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        pid, data = self._project()
        try:
            with patch("services.ebook_pexels._http_get", side_effect=_mock_pexels_http) as http:
                r = self.client.post(
                    f"/ebook-workspace/{pid}/cover",
                    json={"action": "pexels-search", "query": "event photographer camera", "page": 1},
                )
                self.assertEqual(r.status_code, 200, r.get_data(as_text=True))
                self.assertTrue(http.called)
            body = r.get_data(as_text=True)
            self.assertNotIn("test-pexels-key-not-live", body)
            self.assertNotIn("original_url", body)
            ws = r.get_json()["workspace"]
            photos = ws["design"]["cover"]["photo"]["pexels"]["photos"]
            self.assertTrue(photos)
            row = photos[0]
            self.assertEqual(row["photographer"], "Test Photographer")
            self.assertIn("Pexels", row["attribution"])
            self.assertEqual(row["width"], 2000)
            self.assertEqual(row["height"], 3000)
            self.assertIn(row["photo_id"], {"4249001", 4249001, "4249001"})
            self.assertNotIn("original_url", row)
            stored = database.get_project(pid)["data"]
            self.assertEqual(manuscript_digest(stored), manuscript_digest(data))
            self.assertEqual(stored.get("ebook_cover_digest") or "", data.get("ebook_cover_digest") or "")
        finally:
            os.environ["PEXELS_API_KEY"] = ""

    def test_05_pexels_select_downloads_original_not_thumbnail(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        pid, data = self._project()
        try:
            with patch("services.ebook_pexels._http_get", side_effect=_mock_pexels_http):
                search = self.client.post(
                    f"/ebook-workspace/{pid}/cover",
                    json={"action": "pexels-search", "query": "photo printing event"},
                )
                self.assertEqual(search.status_code, 200)
                selected = self.client.post(
                    f"/ebook-workspace/{pid}/cover",
                    json={"action": "pexels-select", "photo_id": "4249001"},
                )
            self.assertEqual(selected.status_code, 200, selected.get_data(as_text=True))
            cover = database.get_project(pid)["data"]["cover_design"]
            rec = cover["source"]["pexels"]
            self.assertEqual(rec["provider"], "pexels")
            self.assertEqual(str(rec["photo_id"]), "4249001")
            self.assertEqual(rec["photographer"], "Test Photographer")
            self.assertTrue(rec["original_url"])
            self.assertNotEqual(rec["original_url"], rec.get("preview_url"))
            self.assertTrue(rec["timestamp"])
            self.assertTrue(rec["attribution"])
            self.assertTrue(rec["license_note"])
            self.assertEqual(rec["sha256"], cover["source"]["sha256"])
            self.assertEqual(rec["project_id"], pid)
            self.assertEqual(cover["source"]["source_type"], "pexels")
            self.assertTrue(os.path.isfile(cover["source"]["path"]))
            self.assertNotIn("thumb", os.path.basename(cover["source"]["path"]).lower())
            public = selected.get_json()["workspace"]["design"]["cover"]["photo"]["source"]
            self.assertNotIn("original_url", public)
        finally:
            os.environ["PEXELS_API_KEY"] = ""

    def test_06_refuse_thumbnail_as_final_source(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        try:
            with self.assertRaises(PexelsError) as ctx:
                download_pexels_original(
                    {
                        "original_url": "https://images.pexels.com/photos/1/large.jpeg",
                        "preview_url": "https://images.pexels.com/photos/1/large.jpeg",
                    }
                )
            self.assertIn("thumbnail", str(ctx.exception).lower())
        finally:
            os.environ["PEXELS_API_KEY"] = ""

    def test_07_upload_requires_ownership_and_rejects_bad_files(self):
        pid, data = self._project()
        with self.assertRaises(PhotoCoverError):
            attach_upload(data, _png_bytes(), filename="ok.png", license_note="note", project_id=pid, owned=False)
        with self.assertRaises(PhotoCoverError):
            attach_upload(data, _png_bytes(100, 100), filename="tiny.png", license_note="ok", project_id=pid, owned=True)
        with self.assertRaises(PhotoCoverError):
            attach_upload(data, b"not-an-image", filename="x.png", license_note="ok", project_id=pid, owned=True)
        denied = self.client.post(
            f"/ebook-workspace/{pid}/cover-image",
            data={"license_note": "Owned photo.", "file": (io.BytesIO(_png_bytes()), "cover.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(denied.status_code, 400)
        up = self.client.post(
            f"/ebook-workspace/{pid}/cover-image",
            data={
                "license_note": "Author-owned event photograph.",
                "i_own_this": "1",
                "file": (io.BytesIO(_png_bytes()), "cover.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(up.status_code, 200, up.get_data(as_text=True))

    def test_08_stale_cross_project_and_low_res_fail(self):
        pid, data = self._project()
        data = attach_upload(
            data, _png_bytes(), filename="ok.png", license_note="Owned photo.", project_id=pid, owned=True
        )
        data["cover_design"]["source"]["sha256"] = "0" * 64
        with self.assertRaises(PhotoCoverError):
            apply_editor(data, {}, project_id=pid)
        data["cover_design"]["source"]["sha256"] = hashlib.sha256(
            open(data["cover_design"]["source"]["path"], "rb").read()
        ).hexdigest()
        data["cover_design"]["source"]["project_id"] = pid + 99999
        with self.assertRaises(PhotoCoverError):
            apply_editor(data, {}, project_id=pid)

    def test_09_three_layouts_exact_text_no_forbidden_labels(self):
        pid, data = self._project()
        data = attach_licensed(data, "event_reception_night", project_id=pid)
        cover = data["cover_design"]
        self.assertEqual(cover["title"], "From First Booking to On-Site Prints")
        self.assertEqual(
            cover["subtitle"],
            "A Practical Guide to Equipment, Pricing, Client Workflow, Event-Day Operations, and Dye-Sublimation Printing",
        )
        self.assertEqual(cover["author"], "Lonnie Brown")
        self.assertEqual(set(cover["variants"]), set(LAYOUT_IDS))
        self.assertIn("Event Photography Field Guide", FORBIDDEN_LABELS)
        import fitz

        for layout_id in LAYOUT_IDS:
            row = cover["variants"][layout_id]
            self.assertTrue(os.path.isfile(row["png_path"]))
            self.assertTrue(os.path.isfile(row["thumb_path"]))
            self.assertTrue(os.path.isfile(row["pdf_path"]))
            text = fitz.open(stream=open(row["pdf_path"], "rb").read(), filetype="pdf")[0].get_text()
            for word in ("From", "First", "Booking", "On-Site", "Prints", "Lonnie", "Brown"):
                self.assertIn(word, text)
            for label in FORBIDDEN_LABELS:
                self.assertNotIn(label, text)

    def test_10_printed_moment_thumbnail_story(self):
        pid, data = self._project()
        data = attach_licensed(data, "event_reception_night", project_id=pid)
        story = data["cover_design"]["variants"]["printed_moment"]["quality"]
        self.assertTrue(story["pass"], story.get("findings"))

    def test_11_select_approval_blocked_until_layout(self):
        pid, data = self._project()
        data = attach_licensed(data, "event_reception_night", project_id=pid)
        data = stage_photo_cover(data, project_id=pid)
        with self.assertRaises(Exception):
            approve_stage(data, "cover")
        data = select_layout(data, "printed_moment", project_id=pid)
        data = stage_photo_cover(data, project_id=pid)
        approved = approve_stage(data, "cover")
        self.assertEqual(approved["ebook_workspace"]["rail"]["cover"]["status"], "approved")

    def test_12_refresh_does_not_regenerate_or_approve(self):
        pid, data = self._project()
        data = attach_licensed(data, "event_reception_night", project_id=pid)
        data = select_layout(data, "printed_moment", project_id=pid)
        data = stage_photo_cover(data, project_id=pid)
        database.update_project(pid, None, data)
        digest = data["cover_design"]["cover_digest"]
        with patch("services.ebook_photo_cover.render_photo_variants") as regen:
            again = self.client.get(f"/ebook-workspace/{pid}")
            regen.assert_not_called()
        self.assertEqual(again.status_code, 200)
        after = database.get_project(pid)["data"]
        self.assertEqual(after["cover_design"]["cover_digest"], digest)
        self.assertEqual(after["ebook_workspace"]["rail"]["cover"]["status"], "awaiting_approval")
        ws = again.get_json()["workspace"]
        self.assertEqual(ws["design"]["cover"]["photo"]["selected_layout"], "printed_moment")
        self.assertNotEqual(ws["rail"][next(i for i, r in enumerate(ws["rail"]) if r["id"] == "cover")]["status"], "approved")

    def test_13_http_variants_full_and_thumb_and_vector_blocked(self):
        pid, data = self._project()
        before_ms = manuscript_digest(data)
        before_spent = data["ebook_workspace"]["paid_call_ledger"]["spent_usd"]
        blocked = self.client.post(f"/ebook-workspace/{pid}/cover", json={"action": "generate"})
        self.assertEqual(blocked.status_code, 400)
        licensed = self.client.post(
            f"/ebook-workspace/{pid}/cover",
            json={"action": "licensed", "asset_id": "event_reception_night"},
        )
        self.assertEqual(licensed.status_code, 400)
        data = attach_licensed(data, "event_reception_night", project_id=pid)
        data = stage_photo_cover(data, project_id=pid)
        database.update_project(pid, None, data)
        variants = data["cover_design"]["variants"]
        for layout_id, row in variants.items():
            full = self.client.get(
                f"/ebook-workspace/{pid}/cover-variant",
                query_string={"layout": layout_id, "size": "full", "digest": row["digest"]},
            )
            thumb = self.client.get(
                f"/ebook-workspace/{pid}/cover-variant",
                query_string={"layout": layout_id, "size": "thumb", "digest": row["digest"]},
            )
            self.assertEqual(full.status_code, 200)
            self.assertEqual(thumb.status_code, 200)
            self.assertTrue(full.data.startswith(b"\x89PNG"))
            self.assertTrue(thumb.data.startswith(b"\x89PNG"))
            self.assertGreater(len(full.data), len(thumb.data))
        stored = database.get_project(pid)["data"]
        self.assertEqual(manuscript_digest(stored), before_ms)
        self.assertEqual(stored["ebook_workspace"]["paid_call_ledger"]["spent_usd"], before_spent)

    def test_14_cover_preflight_fail_list(self):
        pid, data = self._project()
        misses = photo_cover_preflight_failures(data, project_id=pid)
        self.assertTrue(any(code == "missing_cover_photograph" for code, _ in misses))
        data["cover_design"] = {"workflow": "vector", "title": data["title"]}
        vect = photo_cover_preflight_failures(data, project_id=pid)
        self.assertTrue(any(code == "vector_cover_rejected" for code, _ in vect))
        data = attach_licensed(database.get_project(pid)["data"], "event_reception_night", project_id=pid)
        unselected = photo_cover_preflight_failures(data, project_id=pid)
        self.assertTrue(any(code == "cover_layout_not_selected" for code, _ in unselected))
        joined = " ".join(msg.lower() for _, msg in unselected)
        self.assertNotIn("amazon approved", joined)
        self.assertNotIn("model release", joined)

    def test_15_ai_cover_disabled(self):
        pid, data = self._project()
        data = attach_licensed(data, "event_reception_night", project_id=pid)
        self.assertFalse(data["cover_design"]["ai_cover"]["enabled"])
        self.assertEqual(data["cover_design"]["ai_cover"]["label"], "Optional paid feature — not configured")

    def test_16_live_4249_untouched_and_choices_visible(self):
        live = database.get_project(4249)
        self.assertIsNotNone(live, "project 4249 not present")
        before = copy.deepcopy(live["data"])
        r = self.client.post("/ebook-workspace/4249/cover", json={"action": "generate"})
        self.assertEqual(r.status_code, 400)
        view = self.client.get("/ebook-workspace/4249")
        self.assertEqual(view.status_code, 200)
        ws = view.get_json()["workspace"]
        photo = ((ws.get("design") or {}).get("cover") or {}).get("photo") or {}
        self.assertEqual(photo.get("pexels", {}).get("suggested"), list(SUGGESTED_SEARCHES))
        self.assertFalse(photo.get("approvable"))
        after = database.get_project(4249)["data"]
        self.assertEqual(manuscript_digest(after), manuscript_digest(before))
        self.assertEqual(after.get("ebook_cover_digest"), before.get("ebook_cover_digest"))
        self.assertEqual(after.get("content"), before.get("content"))
        self.assertEqual(
            after["ebook_workspace"]["paid_call_ledger"]["spent_usd"],
            before["ebook_workspace"]["paid_call_ledger"]["spent_usd"],
        )
        self.assertAlmostEqual(float(after["ebook_workspace"]["paid_call_ledger"]["spent_usd"]), 1.8, places=3)
        self.assertAlmostEqual(float(after["ebook_workspace"]["paid_call_ledger"]["remaining_usd"]), 0.0, places=3)
        self.assertNotEqual(after["ebook_workspace"]["rail"]["cover"]["status"], "approved")
        self.assertEqual(after["ebook_workspace"]["rail"]["manuscript"]["status"], "approved")
        self.assertEqual(after["ebook_workspace"]["rail"]["visuals"]["status"], "approved")

    def test_17_project_2472_unchanged_and_vector_helper_disabled(self):
        live = database.get_project(2472)
        self.assertIsNotNone(live, "project 2472 not present")
        md = str(live["data"].get("content") or "")
        self.assertEqual(hashlib.sha256(md.encode("utf-8")).hexdigest(), FROZEN_2472_SHA256)
        self.assertAlmostEqual(
            float(live["data"]["ebook_workspace"]["paid_call_ledger"]["spent_usd"]),
            FROZEN_2472_SPENT_USD,
            places=3,
        )
        with self.assertRaises(ValueError):
            generate_and_stage_cover({})


if __name__ == "__main__":
    unittest.main()
