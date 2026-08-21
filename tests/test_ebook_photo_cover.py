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

from PIL import Image, ImageDraw

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
    COVER_H,
    COVER_W,
    FORBIDDEN_LABELS,
    LAYOUT_IDS,
    MAX_UPLOAD_BYTES,
    PhotoCoverError,
    apply_editor,
    attach_licensed,
    attach_pexels,
    attach_upload,
    build_licensed_event_photo,
    cover_input_digest,
    default_editor,
    photo_cover_preflight_failures,
    render_layout,
    select_layout,
    _cover_crop,
    _open_rgb_bytes,
    _prepare_photo,
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

MOCK_PEXELS_PHOTO_B = {
    "id": 4249002,
    "photographer": "Second Photographer",
    "photographer_url": "https://www.pexels.com/@second",
    "url": "https://www.pexels.com/photo/event-4249002",
    "width": 1800,
    "height": 2700,
    "src": {
        "original": "https://images.pexels.com/photos/4249002/original.jpeg",
        "large": "https://images.pexels.com/photos/4249002/large.jpeg",
        "tiny": "https://images.pexels.com/photos/4249002/tiny.jpeg",
    },
}


def _png_bytes(w: int = 1200, h: int = 1800, color=(40, 80, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _jpeg_color_bytes(color=(180, 36, 36), w: int = 1200, h: int = 1800) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="JPEG", quality=90)
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
        if "4249002" in str(url):
            return _jpeg_color_bytes((200, 28, 28))
        return _event_jpeg_bytes()
    if "/v1/photos/" in str(url):
        if "4249002" in str(url):
            return dict(MOCK_PEXELS_PHOTO_B)
        return dict(MOCK_PEXELS_PHOTO)
    return {"photos": [dict(MOCK_PEXELS_PHOTO), dict(MOCK_PEXELS_PHOTO_B)]}


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
        self.assertIn("Search Free Photos", js)
        self.assertIn("Upload My Photo", js)
        self.assertIn("data-ws-cover-tab", js)
        self.assertIn("data-ws-cover-pexels-search", js)
        self.assertIn("data-ws-cover-pexels-select", js)
        self.assertIn("data-ws-cover-upload", js)
        self.assertIn("data-ws-cover-chosen", js)
        self.assertIn("data-ws-cover-file", js)
        self.assertIn('fd.append("file", file, file.name)', js)
        self.assertIn('fd.append("i_own_this", "1")', js)
        self.assertIn("credentials: \"same-origin\"", js)
        self.assertIn("Selected: ${chosen.name}", js)
        self.assertIn("Uploaded ${src.filename", js)
        self.assertIn("I own this image or have permission to use it commercially.", js)
        self.assertIn("Optional paid feature — not configured", js)
        self.assertIn("data-ws-cover-layout", js)
        self.assertIn("Select This Cover", js)
        self.assertIn("data-ws-cover-preview", js)
        self.assertIn("data-ws-cover-thumb", js)
        self.assertIn("data-ws-cover-source", js)
        self.assertIn("referrerpolicy=\"no-referrer\"", js)
        self.assertIn("Selected Photo", js)
        self.assertIn("Change Photo", js)
        self.assertIn("Choose Another Photo", js)
        self.assertIn("Change Cover", js)
        self.assertIn("Approve Cover", js)
        self.assertIn("data-ws-cover-advanced", js)
        self.assertIn("Advanced adjustments (optional)", js)
        self.assertIn("data-ws-cover-no-safe", js)
        self.assertIn("This photo does not leave enough room for readable cover text", js)
        self.assertIn("data-ws-approve-cover disabled", js)
        self.assertIn("if (!coverApprovable || !fullOk || !thumbOk) return", js)
        self.assertIn('coverGuidedStep === "review" ? `<p data-ws-cover-preview-error', js)
        self.assertIn('if (coverGuidedStep === "review")', js)
        self.assertNotIn("awaiting && step !== \"review\"", js)
        self.assertNotIn('if (step === "review")', js)
        self.assertNotIn("data-ws-generate-cover", js)
        self.assertNotIn("data-ws-cover-select-licensed", js)
        self.assertNotIn("data-ws-cover-failed", js)
        self.assertNotIn("No cover layout passed automatic quality checks.", js)
        adv = js.find("Advanced adjustments (optional)")
        fx = js.find("Focal X")
        self.assertGreater(adv, 0)
        self.assertGreater(fx, adv)
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
            self.assertIn(f"/ebook-workspace/{pid}/cover-photo?digest=", public.get("preview_url") or "")
            self.assertNotIn("images.pexels.com", public.get("preview_url") or "")
            src_img = self.client.get(
                f"/ebook-workspace/{pid}/cover-photo",
                query_string={"digest": cover["source"]["sha256"]},
            )
            self.assertEqual(src_img.status_code, 200)
            self.assertTrue(src_img.data[:2] == b"\xff\xd8" or src_img.data.startswith(b"\x89PNG"))
            self.assertGreater(len(src_img.data), 1024)
            pexels_rows = selected.get_json()["workspace"]["design"]["cover"]["photo"]["pexels"]["photos"]
            chosen = next(row for row in pexels_rows if str(row.get("photo_id")) == "4249001")
            self.assertTrue(chosen.get("selected"))
            self.assertEqual(chosen.get("preview_url"), public.get("preview_url"))
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
        src = up.get_json()["workspace"]["design"]["cover"]["photo"]["source"]
        self.assertIn(f"/ebook-workspace/{pid}/cover-photo?digest=", src.get("preview_url") or "")
        digest = str(src.get("sha256") or "")
        shown = self.client.get(
            f"/ebook-workspace/{pid}/cover-photo",
            query_string={"digest": digest},
        )
        self.assertEqual(shown.status_code, 200)
        self.assertTrue(shown.data.startswith(b"\x89PNG"))
        mismatch = self.client.get(
            f"/ebook-workspace/{pid}/cover-photo",
            query_string={"digest": "0" * 64},
        )
        self.assertEqual(mismatch.status_code, 404)

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

    def test_10_full_bleed_no_frames_or_white_panels(self):
        pid, data = self._project()
        data = attach_licensed(data, "event_reception_night", project_id=pid)
        for layout_id in LAYOUT_IDS:
            row = data["cover_design"]["variants"][layout_id]
            self.assertTrue(row["quality"]["pass"], (layout_id, row["quality"].get("findings")))
            img = Image.open(row["png_path"])
            self.assertEqual(img.size, (COVER_W, COVER_H))
            for xy in ((2, 2), (COVER_W - 3, 2), (2, COVER_H - 3), (COVER_W - 3, COVER_H - 3)):
                px = img.getpixel(xy)
                self.assertFalse(all(c > 240 for c in px[:3]), f"{layout_id} white corner {xy} {px}")
            findings = row["quality"].get("findings") or []
            self.assertNotIn("blank_white_area", findings)
            self.assertNotIn("not_full_bleed", findings)
            self.assertNotIn("print_border_missing", findings)

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
        self.assertEqual(photo.get("selected_layout") or (before.get("cover_design") or {}).get("selected_layout"), "full_bleed_editorial")
        src = photo.get("source") or {}
        self.assertEqual(src.get("sha256"), "465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd")
        if src.get("sha256"):
            self.assertIn("/ebook-workspace/4249/cover-photo?digest=", src.get("preview_url") or "")
            shown = self.client.get(
                "/ebook-workspace/4249/cover-photo",
                query_string={"digest": src["sha256"]},
            )
            self.assertEqual(shown.status_code, 200)
            self.assertGreater(len(shown.data), 1024)
            self.assertTrue(shown.data[:2] == b"\xff\xd8" or shown.data.startswith(b"\x89PNG"))
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
        self.assertEqual(after["ebook_workspace"]["rail"]["cover"]["status"], "approved")
        self.assertEqual(after["ebook_workspace"]["rail"]["manuscript"]["status"], "approved")
        self.assertIn(after["ebook_workspace"]["rail"]["visuals"]["status"], {"awaiting_approval", "needs_correction"})
        review = ((ws.get("design") or {}).get("visual_review") or {})
        self.assertGreaterEqual(len(review.get("assets") or []), 1)

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

    def test_18_exif_orientation_applied_before_crop(self):
        stored = Image.new("RGB", (1600, 900), (18, 48, 88))
        ImageDraw.Draw(stored).rectangle((0, 0, 1600, 80), fill=(230, 24, 24))
        buf = io.BytesIO()
        exif = Image.Exif()
        exif[0x0112] = 6
        stored.save(buf, format="JPEG", quality=95, exif=exif)
        opened = _open_rgb_bytes(buf.getvalue())
        self.assertEqual(opened.size, (900, 1600))
        right = opened.crop((opened.width - 12, 40, opened.width, opened.height - 40))
        pix = right.load()
        pixels = [pix[x, y] for y in range(right.height) for x in range(right.width)]
        n = max(len(pixels), 1)
        avg = tuple(sum(p[i] for p in pixels) / n for i in range(3))
        self.assertGreater(avg[0], 160)
        self.assertGreater(avg[0] - avg[2], 40)

    def test_19_letterbox_trimmed_then_crop_to_fill(self):
        photo = Image.new("RGB", (1800, 1100), (36, 92, 58))
        ImageDraw.Draw(photo).ellipse((650, 250, 1150, 750), fill=(200, 40, 40))
        canvas = Image.new("RGB", (1800, 2600), (255, 255, 255))
        canvas.paste(photo, (0, 720))
        trimmed = _prepare_photo(canvas)
        self.assertEqual(trimmed.size[0], 1800)
        self.assertLess(trimmed.size[1], 1300)
        self.assertGreater(trimmed.size[1], 900)
        cropped = _cover_crop(trimmed, {**default_editor(), "zoom": 1.0, "focal_x": 0.5, "focal_y": 0.5})
        self.assertEqual(cropped.size, (COVER_W, COVER_H))
        for xy in ((2, 2), (COVER_W - 3, 2), (2, COVER_H - 3), (COVER_W - 3, COVER_H - 3)):
            px = cropped.getpixel(xy)
            self.assertFalse(all(c > 240 for c in px[:3]), xy)

    def test_20_crop_to_fill_preserves_circle_aspect(self):
        im = Image.new("RGB", (2000, 1200), (22, 28, 36))
        ImageDraw.Draw(im).ellipse((700, 300, 1300, 900), fill=(210, 32, 32))
        cropped = _cover_crop(im, {**default_editor(), "zoom": 1.0, "focal_x": 0.5, "focal_y": 0.5})
        self.assertEqual(cropped.size, (COVER_W, COVER_H))
        pix = cropped.load()
        xs, ys = [], []
        for y in range(0, COVER_H, 2):
            for x in range(0, COVER_W, 2):
                r, g, b = pix[x, y]
                if r > 150 and r > g + 60 and r > b + 60:
                    xs.append(x)
                    ys.append(y)
        self.assertTrue(xs and ys)
        bw = max(xs) - min(xs)
        bh = max(ys) - min(ys)
        ratio = bw / max(bh, 1)
        self.assertGreater(ratio, 0.88)
        self.assertLess(ratio, 1.12)

    def test_21_three_type_variants_share_photo_no_forbidden_series_label(self):
        pid, data = self._project()
        data = attach_licensed(data, "event_reception_night", project_id=pid)
        ident = {
            "title": data["cover_design"]["title"],
            "subtitle": data["cover_design"]["subtitle"],
            "author": data["cover_design"]["author"],
        }
        self.assertNotIn("Event Photography Field Guide", ident["title"])
        self.assertNotIn("Event Photography Field Guide", ident["subtitle"])
        editor = default_editor()
        photo = build_licensed_event_photo()
        rendered = {lid: render_layout(photo, lid, ident, editor) for lid in LAYOUT_IDS}
        crops = [_cover_crop(_prepare_photo(photo), editor) for _ in LAYOUT_IDS]
        self.assertEqual(crops[0].tobytes(), crops[1].tobytes())
        self.assertEqual(crops[1].tobytes(), crops[2].tobytes())
        labels = [data["cover_design"]["variants"][lid]["label"] for lid in LAYOUT_IDS]
        self.assertTrue(all("Full Bleed" in label for label in labels))
        self.assertEqual(len(set(labels)), 3)
        for lid, img in rendered.items():
            self.assertEqual(img.size, (COVER_W, COVER_H))

    def _public_url_blob(self, photo: dict) -> str:
        parts = [
            str((photo.get("source") or {}).get("preview_url") or ""),
            str(photo.get("preview_url") or ""),
            str(photo.get("image_digest") or ""),
            str(photo.get("cover_input_digest") or ""),
        ]
        for row in list(photo.get("variants") or []) + list(photo.get("failed_variants") or []):
            parts.extend(
                [
                    str(row.get("full_url") or ""),
                    str(row.get("thumb_url") or ""),
                    str(row.get("digest") or ""),
                    str(row.get("cache_key") or ""),
                    str(row.get("source_sha256") or ""),
                ]
            )
        return " ".join(parts)

    def test_22_upload_replaces_pexels_source_and_regenerates_variants(self):
        os.environ["PEXELS_API_KEY"] = "test-pexels-key-not-live"
        pid, data = self._project()
        before_ms = manuscript_digest(data)
        before_spent = data["ebook_workspace"]["paid_call_ledger"]["spent_usd"]
        before_title = data.get("title")
        photo_b = _png_bytes(color=(96, 22, 22))
        sha_b = hashlib.sha256(photo_b).hexdigest()
        try:
            with patch("services.ebook_pexels._http_get", side_effect=_mock_pexels_http):
                search = self.client.post(
                    f"/ebook-workspace/{pid}/cover",
                    json={"action": "pexels-search", "query": "event photographer camera"},
                )
                self.assertEqual(search.status_code, 200, search.get_data(as_text=True))
                selected = self.client.post(
                    f"/ebook-workspace/{pid}/cover",
                    json={"action": "pexels-select", "photo_id": "4249001"},
                )
            self.assertEqual(selected.status_code, 200, selected.get_data(as_text=True))
            cover_a = database.get_project(pid)["data"]["cover_design"]
            sha_a = str(cover_a["source"]["sha256"])
            self.assertEqual(cover_a["source"]["source_type"], "pexels")
            self.assertTrue(os.path.isfile(cover_a["source"]["path"]))
            path_a = cover_a["source"]["path"]
            variants_a = {
                lid: str((row or {}).get("digest") or "")
                for lid, row in (cover_a.get("variants") or {}).items()
            }
            passing = [
                lid
                for lid, row in (cover_a.get("variants") or {}).items()
                if ((row or {}).get("quality") or {}).get("pass")
            ]
            self.assertTrue(passing)
            data = select_layout(database.get_project(pid)["data"], passing[0], project_id=pid)
            data = stage_photo_cover(data, project_id=pid)
            database.update_project(pid, None, data)
            self.assertEqual(database.get_project(pid)["data"]["cover_design"]["selected_layout"], passing[0])

            up = self.client.post(
                f"/ebook-workspace/{pid}/cover-image",
                data={
                    "license_note": "Author-owned studio photograph.",
                    "i_own_this": "1",
                    "file": (io.BytesIO(photo_b), "studio-reception.png"),
                },
                content_type="multipart/form-data",
            )
            self.assertEqual(up.status_code, 200, up.get_data(as_text=True))
            payload = up.get_json()
            self.assertIn("studio-reception.png", payload.get("message") or "")
            self.assertIn("upload", (payload.get("message") or "").lower())
            photo = payload["workspace"]["design"]["cover"]["photo"]
            src = photo["source"]
            self.assertEqual(src["source_type"], "upload")
            self.assertEqual(src["filename"], "studio-reception.png")
            self.assertEqual(src["sha256"], sha_b)
            self.assertNotEqual(sha_a, sha_b)
            self.assertEqual(photo["image_digest"], sha_b)
            self.assertTrue(photo.get("cover_input_digest"))
            stored = database.get_project(pid)["data"]
            from services.ebook_photo_cover import _approved_identity

            expected_input = cover_input_digest(
                source_sha=sha_b,
                ident=_approved_identity(stored),
                editor=stored["cover_design"].get("editor"),
            )
            self.assertEqual(stored["cover_design"]["source"]["sha256"], sha_b)
            self.assertIn(sha_b, stored["cover_design"]["source"]["path"])
            self.assertNotEqual(stored["cover_design"]["source"]["path"], path_a)
            self.assertTrue(os.path.isfile(path_a))
            self.assertTrue(os.path.isfile(stored["cover_design"]["source"]["path"]))
            self.assertEqual(stored["cover_design"]["image_digest"], sha_b)
            self.assertEqual(stored["cover_design"]["cover_input_digest"], expected_input)
            self.assertFalse(stored["cover_design"].get("selected_layout"))
            self.assertFalse(photo.get("selected_layout"))
            self.assertFalse(photo.get("approvable"))
            blob = self._public_url_blob(photo)
            self.assertNotIn(sha_a, blob)
            self.assertIn(sha_b, blob)
            shown = self.client.get(
                f"/ebook-workspace/{pid}/cover-photo",
                query_string={"digest": sha_b},
            )
            self.assertEqual(shown.status_code, 200)
            self.assertEqual(hashlib.sha256(shown.data).hexdigest(), sha_b)
            stale = self.client.get(
                f"/ebook-workspace/{pid}/cover-photo",
                query_string={"digest": sha_a},
            )
            self.assertEqual(stale.status_code, 404)
            for lid, row in stored["cover_design"]["variants"].items():
                if not (row.get("quality") or {}).get("pass"):
                    continue
                self.assertIn(expected_input, str(row.get("png_path") or ""))
                self.assertEqual(row.get("source_sha256"), sha_b)
                self.assertNotEqual(str(row.get("digest") or ""), variants_a.get(lid))
                img = Image.open(row["png_path"]).convert("RGB")
                sample = img.getpixel((COVER_W - 12, COVER_H // 2))
                self.assertGreater(sample[0], 40, (lid, sample))
                self.assertGreater(sample[0], sample[2], (lid, sample))
                full = self.client.get(
                    f"/ebook-workspace/{pid}/cover-variant",
                    query_string={
                        "layout": lid,
                        "size": "full",
                        "digest": row["digest"],
                        "src": sha_b,
                    },
                )
                thumb = self.client.get(
                    f"/ebook-workspace/{pid}/cover-variant",
                    query_string={
                        "layout": lid,
                        "size": "thumb",
                        "digest": row["digest"],
                        "src": sha_b,
                    },
                )
                self.assertEqual(full.status_code, 200)
                self.assertEqual(thumb.status_code, 200)
                wrong = self.client.get(
                    f"/ebook-workspace/{pid}/cover-variant",
                    query_string={
                        "layout": lid,
                        "size": "full",
                        "digest": row["digest"],
                        "src": sha_a,
                    },
                )
                self.assertEqual(wrong.status_code, 404)
            refreshed = self.client.get(f"/ebook-workspace/{pid}")
            self.assertEqual(refreshed.status_code, 200)
            again = refreshed.get_json()["workspace"]["design"]["cover"]["photo"]
            self.assertEqual(again["source"]["sha256"], sha_b)
            self.assertEqual(again["source"]["source_type"], "upload")
            self.assertFalse(again.get("selected_layout"))
            self.assertFalse(again.get("approvable"))
            self.assertNotIn(sha_a, self._public_url_blob(again))
            with patch("services.ebook_pexels._http_get", side_effect=_mock_pexels_http):
                search_only = self.client.post(
                    f"/ebook-workspace/{pid}/cover",
                    json={"action": "pexels-search", "query": "wedding event photography"},
                )
            self.assertEqual(search_only.status_code, 200, search_only.get_data(as_text=True))
            after_search = search_only.get_json()["workspace"]["design"]["cover"]["photo"]
            self.assertEqual(after_search["source"]["sha256"], sha_b)
            self.assertEqual(after_search["source"]["source_type"], "upload")
            self.assertFalse(any(row.get("selected") for row in after_search["pexels"]["photos"]))
            with patch("services.ebook_pexels._http_get", side_effect=_mock_pexels_http):
                replace = self.client.post(
                    f"/ebook-workspace/{pid}/cover",
                    json={"action": "pexels-select", "photo_id": "4249002"},
                )
            self.assertEqual(replace.status_code, 200, replace.get_data(as_text=True))
            pexels_b = replace.get_json()["workspace"]["design"]["cover"]["photo"]
            sha_c = pexels_b["source"]["sha256"]
            self.assertEqual(pexels_b["source"]["source_type"], "pexels")
            self.assertNotEqual(sha_c, sha_b)
            self.assertNotEqual(sha_c, sha_a)
            self.assertNotIn(sha_b, self._public_url_blob(pexels_b))
            self.assertFalse(pexels_b.get("selected_layout"))
            chosen = next(row for row in pexels_b["pexels"]["photos"] if str(row.get("photo_id")) == "4249002")
            self.assertTrue(chosen.get("selected"))
            after = database.get_project(pid)["data"]
            self.assertEqual(manuscript_digest(after), before_ms)
            self.assertEqual(after["ebook_workspace"]["paid_call_ledger"]["spent_usd"], before_spent)
            self.assertEqual(after.get("title"), before_title)
        finally:
            os.environ["PEXELS_API_KEY"] = ""

    def test_23_invalid_uploads_keep_last_valid_source(self):
        pid, data = self._project()
        photo_ok = _png_bytes(color=(36, 120, 64))
        sha_ok = hashlib.sha256(photo_ok).hexdigest()
        up = self.client.post(
            f"/ebook-workspace/{pid}/cover-image",
            data={
                "license_note": "Owned photograph.",
                "i_own_this": "1",
                "file": (io.BytesIO(photo_ok), "valid-source.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(up.status_code, 200, up.get_data(as_text=True))
        cases = [
            ({"license_note": "Owned photograph.", "i_own_this": "1", "file": (io.BytesIO(b"not-an-image"), "x.png")}, 400),
            ({"license_note": "Owned photograph.", "i_own_this": "1", "file": (io.BytesIO(_png_bytes(40, 40)), "tiny.png")}, 400),
            ({"license_note": "Owned photograph.", "i_own_this": "1", "file": (io.BytesIO(b"GIF89a" + b"\x00" * 80), "nope.gif")}, 400),
            (
                {
                    "license_note": "Owned photograph.",
                    "i_own_this": "1",
                    "file": (io.BytesIO(b"\xff\xd8" + b"\x00" * (MAX_UPLOAD_BYTES + 8)), "huge.jpg"),
                },
                400,
            ),
            ({"license_note": "Owned photograph.", "file": (io.BytesIO(_png_bytes()), "cover.png")}, 400),
        ]
        for body, status in cases:
            denied = self.client.post(
                f"/ebook-workspace/{pid}/cover-image",
                data=body,
                content_type="multipart/form-data",
            )
            self.assertEqual(denied.status_code, status, denied.get_data(as_text=True))
            stored = database.get_project(pid)["data"]
            self.assertEqual(stored["cover_design"]["source"]["sha256"], sha_ok)
            self.assertEqual(stored["cover_design"]["source"]["filename"], "valid-source.png")
            shown = self.client.get(
                f"/ebook-workspace/{pid}/cover-photo",
                query_string={"digest": sha_ok},
            )
            self.assertEqual(shown.status_code, 200)
            self.assertEqual(hashlib.sha256(shown.data).hexdigest(), sha_ok)

    def test_24_approved_and_locked_reject_cover_upload(self):
        pid, data = self._project()
        photo_ok = _png_bytes(color=(48, 48, 160))
        sha_ok = hashlib.sha256(photo_ok).hexdigest()
        data = attach_upload(
            data, photo_ok, filename="locked-keep.png", license_note="Owned photograph.", project_id=pid, owned=True
        )
        data = stage_photo_cover(data, project_id=pid)
        database.update_project(pid, None, data)
        replacement = _png_bytes(color=(200, 20, 20))

        def _attempt():
            return self.client.post(
                f"/ebook-workspace/{pid}/cover-image",
                data={
                    "license_note": "Owned photograph.",
                    "i_own_this": "1",
                    "file": (io.BytesIO(replacement), "should-fail.png"),
                },
                content_type="multipart/form-data",
            )

        approved = dict(database.get_project(pid)["data"])
        approved["artifact_state"] = "APPROVED"
        database.update_project(pid, None, approved)
        blocked = _attempt()
        self.assertEqual(blocked.status_code, 409, blocked.get_data(as_text=True))
        self.assertEqual(database.get_project(pid)["data"]["cover_design"]["source"]["sha256"], sha_ok)

        locked = dict(database.get_project(pid)["data"])
        locked["artifact_state"] = "LOCKED"
        locked["book_locked"] = True
        locked["lock_status"] = "LOCKED"
        database.update_project(pid, None, locked)
        blocked_lock = _attempt()
        self.assertEqual(blocked_lock.status_code, 409, blocked_lock.get_data(as_text=True))
        self.assertEqual(database.get_project(pid)["data"]["cover_design"]["source"]["sha256"], sha_ok)
        self.assertEqual(database.get_project(pid)["data"]["cover_design"]["source"]["filename"], "locked-keep.png")

    def test_25_guided_workflow_steps_and_approval_gate(self):
        pid, data = self._project()
        view = self.client.get(f"/ebook-workspace/{pid}")
        self.assertEqual(view.status_code, 200)
        photo = view.get_json()["workspace"]["design"]["cover"]["photo"]
        self.assertEqual(photo.get("workflow_step"), "choose_photo")
        self.assertFalse(photo.get("approvable"))
        up = self.client.post(
            f"/ebook-workspace/{pid}/cover-image",
            data={
                "license_note": "Owned photograph.",
                "i_own_this": "1",
                "file": (io.BytesIO(_png_bytes()), "guided.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(up.status_code, 200, up.get_data(as_text=True))
        photo = up.get_json()["workspace"]["design"]["cover"]["photo"]
        self.assertEqual(photo["source"]["filename"], "guided.png")
        self.assertIn("/ebook-workspace/", photo["source"].get("preview_url") or "")
        self.assertGreater(photo.get("passing_count") or 0, 0)
        self.assertEqual(photo.get("workflow_step"), "choose_cover")
        self.assertFalse(photo.get("approvable"))
        self.assertFalse(photo.get("selected_layout"))
        passing = [row for row in photo["variants"] if row.get("quality_pass")]
        self.assertTrue(passing)
        for row in passing:
            self.assertTrue(row.get("full_url"))
            self.assertTrue(row.get("thumb_url"))
            shown = self.client.get(row["full_url"])
            self.assertEqual(shown.status_code, 200, row["full_url"])
            self.assertGreater(len(shown.data), 1024)
            thumb = self.client.get(row["thumb_url"])
            self.assertEqual(thumb.status_code, 200, row["thumb_url"])
            self.assertGreater(len(thumb.data), 256)
        blocked = self.client.post(f"/ebook-workspace/{pid}/approve", json={"stage": "cover"})
        self.assertEqual(blocked.status_code, 400)
        chosen = passing[0]["layout_id"]
        selected = self.client.post(
            f"/ebook-workspace/{pid}/cover",
            json={"action": "select", "layout_id": chosen},
        )
        self.assertEqual(selected.status_code, 200, selected.get_data(as_text=True))
        photo = selected.get_json()["workspace"]["design"]["cover"]["photo"]
        self.assertEqual(photo.get("workflow_step"), "review")
        self.assertEqual(photo.get("selected_layout"), chosen)
        self.assertTrue(photo.get("approvable"))
        back = self.client.post(
            f"/ebook-workspace/{pid}/cover",
            json={"action": "deselect"},
        )
        self.assertEqual(back.status_code, 200, back.get_data(as_text=True))
        photo = back.get_json()["workspace"]["design"]["cover"]["photo"]
        self.assertEqual(photo.get("workflow_step"), "choose_cover")
        self.assertFalse(photo.get("selected_layout"))
        self.assertFalse(photo.get("approvable"))
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('coverGuidedStep === "choose_photo" ? chooserHtml', js)
        self.assertIn("resolveCoverGuidedStep", js)
        self.assertIn("_wsCoverChoosingPhoto", js)


if __name__ == "__main__":
    unittest.main()
