"""Guided Cover step resolver. Zero paid/external calls.

Isolated projects only except read-only #4249 open/refresh immutability.
"""
from __future__ import annotations

import copy
import hashlib
import io
import os
import shutil
import subprocess
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
from services.ebook_design_workspace import approve_visuals_local, stage_photo_cover  # noqa: E402
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript  # noqa: E402
from services.ebook_photo_cover import (  # noqa: E402
    GUIDED_STEP_APPROVED,
    GUIDED_STEP_CHOOSE_ANOTHER,
    GUIDED_STEP_CHOOSE_COVER,
    GUIDED_STEP_CHOOSE_PHOTO,
    GUIDED_STEP_REVIEW,
    INCOMPLETE_SELECTION_RECOVERY,
    MISSING_STEP_RECOVERY,
    attach_upload,
    cover_guided_recovery_action,
    resolve_cover_guided_step,
    select_layout,
)
from services.ebook_project_workspace import (  # noqa: E402
    approve_stage,
    build_acceptance_project_data,
    manuscript_digest,
    set_stage_status,
    workspace_public_view,
)


def _png_bytes(w: int = 1200, h: int = 1800, color=(40, 80, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


def _fingerprint(data: dict) -> dict:
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    src = cover.get("source") if isinstance(cover.get("source"), dict) else {}
    ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
    ledger = ws.get("paid_call_ledger") if isinstance(ws.get("paid_call_ledger"), dict) else {}
    rail = ws.get("rail") if isinstance(ws.get("rail"), dict) else {}
    variants = cover.get("variants") if isinstance(cover.get("variants"), dict) else {}
    return {
        "title": data.get("title"),
        "subtitle": data.get("subtitle"),
        "author": data.get("author_brand") or ws.get("author"),
        "content": data.get("content"),
        "ebook": data.get("ebook"),
        "md": manuscript_digest(data),
        "sha256": src.get("sha256"),
        "filename": src.get("filename"),
        "selected_layout": cover.get("selected_layout"),
        "cover_digest": cover.get("cover_digest"),
        "image_digest": cover.get("image_digest"),
        "variant_digests": {
            lid: (row or {}).get("digest")
            for lid, row in variants.items()
            if isinstance(row, dict)
        },
        "spent": ledger.get("spent_usd"),
        "remaining": ledger.get("remaining_usd"),
        "paid_calls": ledger.get("paid_calls"),
        "cover_status": (rail.get("cover") or {}).get("status"),
        "artifact_state": data.get("artifact_state"),
        "artifact_revision": data.get("artifact_revision"),
        "package_id": data.get("package_id"),
        "ebook_cover_digest": data.get("ebook_cover_digest"),
    }


class CoverGuidedStepTests(unittest.TestCase):
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

    def _project(self, *, user_saved: bool = False) -> tuple[int, dict]:
        data = build_acceptance_project_data()
        data["acceptance_marker"] = None
        pkg = f"ebook-guided-{uuid.uuid4().hex[:16]}"
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
            "Cover Guided Step Project",
            "ebook",
            data,
            user_saved=user_saved,
            system_test=not user_saved,
            temporary=not user_saved,
        )
        pid = project["id"]
        data["_project_id"] = pid
        database.update_project(pid, None, data)
        return pid, dict(database.get_project(pid)["data"])

    def _photo(self, resp) -> dict:
        return (((resp.get_json() or {}).get("workspace") or {}).get("design") or {}).get("cover") or {}

    def _open(self, pid: int):
        return self.client.get(f"/ebook-workspace/{pid}")

    def test_01_resolver_facts_not_guesses(self):
        self.assertEqual(
            resolve_cover_guided_step(has_valid_photo=False, passing_count=0),
            GUIDED_STEP_CHOOSE_PHOTO,
        )
        self.assertEqual(
            resolve_cover_guided_step(has_valid_photo=True, passing_count=0),
            GUIDED_STEP_CHOOSE_ANOTHER,
        )
        self.assertEqual(
            resolve_cover_guided_step(
                has_valid_photo=True, passing_count=3, selected_layout="", selected_is_passing=False
            ),
            GUIDED_STEP_CHOOSE_COVER,
        )
        self.assertEqual(
            resolve_cover_guided_step(
                has_valid_photo=True,
                passing_count=3,
                selected_layout="full_bleed_editorial",
                selected_is_passing=False,
            ),
            GUIDED_STEP_CHOOSE_COVER,
        )
        self.assertEqual(
            resolve_cover_guided_step(
                has_valid_photo=True,
                passing_count=3,
                selected_layout="full_bleed_editorial",
                selected_is_passing=True,
            ),
            GUIDED_STEP_REVIEW,
        )
        self.assertEqual(
            resolve_cover_guided_step(
                has_valid_photo=True,
                passing_count=3,
                selected_layout="full_bleed_editorial",
                selected_is_passing=True,
                cover_approved=True,
            ),
            GUIDED_STEP_APPROVED,
        )
        self.assertEqual(
            cover_guided_recovery_action(
                GUIDED_STEP_CHOOSE_COVER,
                selected_layout="full_bleed_editorial",
                selected_is_passing=False,
            ),
            INCOMPLETE_SELECTION_RECOVERY,
        )
        self.assertEqual(cover_guided_recovery_action("legacy-missing"), MISSING_STEP_RECOVERY)

    def test_02_saved_projects_open_and_refresh_steps(self):
        pid, _data = self._project(user_saved=True)
        opened = self.client.get(f"/projects/{pid}")
        self.assertEqual(opened.status_code, 200)
        self.assertEqual(int(opened.get_json()["id"]), pid)

        first = self._open(pid)
        self.assertEqual(first.status_code, 200, first.get_data(as_text=True))
        ws = first.get_json()["workspace"]
        cover = (ws.get("design") or {}).get("cover") or {}
        photo = cover.get("photo") or {}
        self.assertEqual(photo.get("workflow_step"), GUIDED_STEP_CHOOSE_PHOTO)
        self.assertEqual(ws.get("cover_guided_step"), GUIDED_STEP_CHOOSE_PHOTO)
        self.assertEqual(cover.get("guided_step_id"), GUIDED_STEP_CHOOSE_PHOTO)
        self.assertEqual(cover.get("guided_step"), 1)
        refresh = self._open(pid)
        self.assertEqual(refresh.status_code, 200)
        self.assertEqual(
            refresh.get_json()["workspace"]["cover_guided_step"], GUIDED_STEP_CHOOSE_PHOTO
        )

        up = self.client.post(
            f"/ebook-workspace/{pid}/cover-image",
            data={
                "license_note": "Owned photograph.",
                "i_own_this": "1",
                "file": (io.BytesIO(_png_bytes()), "guided-open.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(up.status_code, 200, up.get_data(as_text=True))
        photo = self._photo(up).get("photo") or {}
        self.assertGreater(photo.get("passing_count") or 0, 0)
        self.assertFalse(photo.get("selected_layout"))
        self.assertEqual(photo.get("workflow_step"), GUIDED_STEP_CHOOSE_COVER)
        self.assertEqual(self._photo(self._open(pid)).get("photo", {}).get("workflow_step"), GUIDED_STEP_CHOOSE_COVER)

        chosen = next(row["layout_id"] for row in photo["variants"] if row.get("quality_pass"))
        selected = self.client.post(
            f"/ebook-workspace/{pid}/cover",
            json={"action": "select", "layout_id": chosen},
        )
        self.assertEqual(selected.status_code, 200, selected.get_data(as_text=True))
        photo = self._photo(selected).get("photo") or {}
        self.assertEqual(photo.get("workflow_step"), GUIDED_STEP_REVIEW)
        self.assertEqual(photo.get("selected_layout"), chosen)
        self.assertTrue(photo.get("approvable"))
        self.assertEqual(self._photo(self._open(pid)).get("photo", {}).get("workflow_step"), GUIDED_STEP_REVIEW)

        approved = self.client.post(f"/ebook-workspace/{pid}/approve", json={"stage": "cover"})
        self.assertEqual(approved.status_code, 200, approved.get_data(as_text=True))
        photo = self._photo(approved).get("photo") or {}
        self.assertEqual(photo.get("workflow_step"), GUIDED_STEP_APPROVED)
        self.assertTrue(photo.get("cover_approved"))
        self.assertFalse(photo.get("approvable"))
        reopened = self._open(pid)
        self.assertEqual(reopened.status_code, 200)
        ws = reopened.get_json()["workspace"]
        self.assertEqual(ws.get("cover_guided_step"), GUIDED_STEP_APPROVED)
        self.assertEqual(((ws.get("design") or {}).get("cover") or {}).get("guided_step_id"), GUIDED_STEP_APPROVED)

    def test_03_reopen_photo_without_selection_is_step_two(self):
        pid, data = self._project()
        data = attach_upload(
            data, _png_bytes(), filename="no-select.png", license_note="Owned.", project_id=pid, owned=True
        )
        data = stage_photo_cover(data, project_id=pid)
        data["cover_design"]["selected_layout"] = ""
        database.update_project(pid, None, data)
        ws = self._open(pid).get_json()["workspace"]
        photo = ((ws.get("design") or {}).get("cover") or {}).get("photo") or {}
        self.assertGreater(photo.get("passing_count") or 0, 0)
        self.assertFalse(photo.get("selected_layout"))
        self.assertEqual(photo.get("workflow_step"), GUIDED_STEP_CHOOSE_COVER)
        self.assertEqual(ws.get("cover_guided_step"), GUIDED_STEP_CHOOSE_COVER)

    def test_04_reopen_selected_unapproved_is_step_three(self):
        pid, data = self._project()
        data = attach_upload(
            data, _png_bytes(), filename="selected.png", license_note="Owned.", project_id=pid, owned=True
        )
        data = select_layout(data, "full_bleed_editorial", project_id=pid)
        database.update_project(pid, None, data)
        photo = self._photo(self._open(pid)).get("photo") or {}
        self.assertEqual(photo.get("selected_layout"), "full_bleed_editorial")
        self.assertEqual(photo.get("workflow_step"), GUIDED_STEP_REVIEW)
        self.assertTrue(photo.get("approvable"))
        self.assertFalse(photo.get("cover_approved"))

    def test_05_legacy_and_incomplete_metadata_nearest_safe_step(self):
        pid, data = self._project()
        data = attach_upload(
            data, _png_bytes(), filename="legacy.png", license_note="Owned.", project_id=pid, owned=True
        )
        data["cover_design"]["selected_layout"] = "not_a_real_layout"
        data["cover_design"]["workflow_step"] = "review"
        database.update_project(pid, None, data)
        ws = workspace_public_view(database.get_project(pid))
        photo = ((ws.get("design") or {}).get("cover") or {}).get("photo") or {}
        self.assertEqual(photo.get("workflow_step"), GUIDED_STEP_CHOOSE_COVER)
        self.assertEqual(photo.get("recovery_action"), INCOMPLETE_SELECTION_RECOVERY)
        self.assertFalse(photo.get("approvable"))

        empty = resolve_cover_guided_step(has_valid_photo=False, passing_count=0, selected_layout="")
        self.assertEqual(empty, GUIDED_STEP_CHOOSE_PHOTO)

    def test_06_js_has_no_out_of_scope_step_and_saved_projects_open_path(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn("resolveCoverGuidedStep", js)
        self.assertIn("deriveCoverGuidedStep", js)
        self.assertIn("let coverGuidedStep = \"\"", js)
        self.assertIn('if (coverGuidedStep === "review")', js)
        self.assertNotIn("let step = String(photo.workflow_step", js)
        self.assertIn("openEbookWorkspace(p.id)", js)
        self.assertIn('data-ws-cover-guided-host', html)
        self.assertIn("This cover step could not be shown", js)
        start = js.find("function showEbookWorkspaceStage(")
        end = js.find("async function postEbookWorkspaceAction(")
        self.assertGreater(start, 0)
        self.assertGreater(end, start)
        body = js[start:end]
        self.assertIn("let coverGuidedStep = \"\"", body)
        self.assertIn("resolveCoverGuidedStep", body)
        self.assertNotRegex(body, r"(?m)^\s*if \(step === \"review\"\)")
        declare = body.find("let coverGuidedStep")
        use = body.find('if (coverGuidedStep === "review")')
        self.assertGreater(declare, 0)
        self.assertGreater(use, declare)

        node = shutil.which("node")
        self.assertIsNotNone(node, "Node.js is required to prove the guided-step script does not throw")
        snippet = r"""
const COVER_GUIDED_STEPS = ["choose_photo", "choose_cover", "review", "choose_another_photo", "approved"];
function deriveCoverGuidedStep(photo, opts) {
  photo = photo || {};
  opts = opts || {};
  const hasSource = !!(photo.source && (photo.source.preview_url || photo.source.sha256));
  const variants = Array.isArray(photo.variants) ? photo.variants : [];
  const passing = variants.filter((v) => v && v.quality_pass && v.full_url && v.thumb_url);
  const selected = String(photo.selected_layout || "");
  const selectedPassing = !!(selected && passing.some((v) => v.layout_id === selected));
  const coverApproved = opts.coverApproved === true || photo.cover_approved === true;
  if (coverApproved && selected && selectedPassing) return "approved";
  if (!hasSource) return "choose_photo";
  if (passing.length <= 0) return "choose_another_photo";
  if (!selected || !selectedPassing) return "choose_cover";
  return "review";
}
function resolveCoverGuidedStep(photo, opts) {
  photo = photo || {};
  opts = opts || {};
  if (opts.choosingPhoto) return "choose_photo";
  const derived = deriveCoverGuidedStep(photo, opts);
  const provided = String(photo.workflow_step || "");
  if (COVER_GUIDED_STEPS.indexOf(provided) >= 0 && provided === derived) return provided;
  return derived;
}
function showStage(stageId, photo) {
  let coverGuidedStep = "";
  if (stageId === "cover") {
    coverGuidedStep = resolveCoverGuidedStep(photo, {});
  }
  if (coverGuidedStep === "review") return "review-bind";
  return coverGuidedStep || "ok";
}
const photo = {
  source: { sha256: "abc", preview_url: "/p" },
  variants: [
    { layout_id: "full_bleed_editorial", quality_pass: true, full_url: "/f", thumb_url: "/t" },
    { layout_id: "split_studio", quality_pass: true, full_url: "/f2", thumb_url: "/t2" },
    { layout_id: "printed_moment", quality_pass: true, full_url: "/f3", thumb_url: "/t3" }
  ],
  workflow_step: "review"
};
const results = [
  showStage("cover", photo),
  showStage("manuscript", photo),
  showStage("cover", { ...photo, selected_layout: "full_bleed_editorial", workflow_step: "review" }),
  showStage("cover", { workflow_step: "review" })
];
if (results[0] !== "choose_cover") throw new Error("stale review must not invent selection: " + results[0]);
if (results[1] !== "ok") throw new Error("non-cover stage must not throw: " + results[1]);
if (results[2] !== "review-bind") throw new Error("persisted selection must bind review: " + results[2]);
if (results[3] !== "choose_photo") throw new Error("legacy missing photo must be step 1: " + results[3]);
console.log("GUIDED_STEP_JS_OK");
"""
        completed = subprocess.run(
            [node, "-e", snippet],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
        self.assertIn("GUIDED_STEP_JS_OK", completed.stdout)

    def test_07_draft_approved_locked_still_protect_cover(self):
        pid, data = self._project()
        photo_ok = _png_bytes(color=(48, 48, 160))
        sha_ok = hashlib.sha256(photo_ok).hexdigest()
        data = attach_upload(
            data, photo_ok, filename="keep.png", license_note="Owned photograph.", project_id=pid, owned=True
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

    def test_08_live_4249_open_refresh_unchanged_step_two(self):
        live = database.get_project(4249)
        self.assertIsNotNone(live, "project 4249 not present")
        before = _fingerprint(copy.deepcopy(live["data"]))
        self.assertEqual(before["sha256"], "465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd")
        self.assertEqual(before["selected_layout"], "full_bleed_editorial")
        self.assertEqual(before["cover_status"], "approved")
        opened = self._open(4249)
        self.assertEqual(opened.status_code, 200, opened.get_data(as_text=True))
        ws = opened.get_json()["workspace"]
        photo = ((ws.get("design") or {}).get("cover") or {}).get("photo") or {}
        self.assertTrue(photo.get("source", {}).get("sha256"))
        self.assertEqual(photo.get("selected_layout") or before["selected_layout"], "full_bleed_editorial")
        self.assertEqual(photo.get("workflow_step"), GUIDED_STEP_APPROVED)
        self.assertEqual(ws.get("cover_guided_step"), GUIDED_STEP_APPROVED)
        self.assertEqual(ws.get("cover_guided_step_label"), "Cover approved")
        refreshed = self._open(4249)
        self.assertEqual(refreshed.status_code, 200)
        self.assertEqual(refreshed.get_json()["workspace"]["cover_guided_step"], GUIDED_STEP_APPROVED)
        after = _fingerprint(database.get_project(4249)["data"])
        self.assertEqual(after, before)
        self.assertAlmostEqual(float(after["spent"] or 0), 1.8, places=3)


if __name__ == "__main__":
    unittest.main()
