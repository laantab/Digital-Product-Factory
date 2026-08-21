"""Full Preview review chrome: approve from the viewer, never by opening.

Zero paid/external calls. Isolated projects only — do not hard-code live IDs.
"""
from __future__ import annotations

import copy
import os
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app import app  # noqa: E402
import database  # noqa: E402
from services.ebook_design_workspace import (  # noqa: E402
    approve_visuals_local,
    build_preview,
    select_and_stage_theme,
)
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript  # noqa: E402
from services.ebook_preview_review import (  # noqa: E402
    APPROVE_CONFIRM_PROMPT,
    APPROVE_SUCCESS_NOTICE,
    CHANGE_CATEGORIES,
    REQUEST_CHANGES_NOTICE,
    REVIEW_BAR_HELP,
    REVIEW_BAR_TITLE,
    STALE_PREVIEW_MESSAGE,
    wrap_preview_review_document,
    workspace_return_url,
)
from services.ebook_project_workspace import (  # noqa: E402
    STATUS_AWAITING,
    approve_stage,
    build_acceptance_project_data,
    current_preview_digest,
    is_approved,
    preview_opened_matches_current,
    set_stage_status,
    stage_status,
)
from services.quality.artifact_state import ArtifactStateError  # noqa: E402


def _paid_patches():
    return (
        patch("ai_client.get_client", side_effect=AssertionError("paid client")),
        patch("ai_client.chat", side_effect=AssertionError("paid chat")),
        patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json")),
    )


def _preview_ready_data():
    from services.ebook_photo_cover import attach_licensed, select_layout

    data = build_acceptance_project_data()
    data["artifact_id"] = f"ebook-preview-review-{uuid.uuid4().hex[:12]}"
    md = build_event_photo_strong_manuscript()
    data["content"] = md
    data["ebook"] = md
    set_stage_status(data["ebook_workspace"], "manuscript", STATUS_AWAITING)
    data = approve_stage(data, "manuscript")
    data = approve_visuals_local(data)
    data = attach_licensed(data, "event_reception_night", project_id=None)
    data = select_layout(data, "printed_moment", project_id=None)
    data = approve_stage(data, "cover")
    data = select_and_stage_theme(data, "modern_practical")
    data = approve_stage(data, "design")
    return build_preview(data)


class WrapPreviewReviewDocumentTests(unittest.TestCase):
    def test_controls_and_confirmation_are_injected_once(self):
        book = (
            "<!doctype html><html><head></head><body>"
            "<h1>Sample Book</h1>"
            '<section id="sources">Sources</section>'
            "</body></html>"
        )
        wrapped = wrap_preview_review_document(
            book,
            title="Sample Book",
            project_id=99,
            digest="abc123digest",
            can_approve=True,
        )
        soup = BeautifulSoup(wrapped, "html.parser")
        bar = soup.select_one(".ebook-preview-review-bar")
        self.assertIsNotNone(bar)
        self.assertIn(REVIEW_BAR_TITLE, bar.get_text(" ", strip=True))
        self.assertIn("Sample Book", bar.get_text(" ", strip=True))
        self.assertIn(REVIEW_BAR_HELP, bar.get_text(" ", strip=True))
        self.assertNotIn("abc123digest", bar.get_text(" ", strip=True))
        self.assertEqual(len(soup.select("[data-ebook-review-back]")), 2)
        self.assertEqual(len(soup.select("[data-ebook-review-changes]")), 2)
        self.assertEqual(len(soup.select("[data-ebook-review-approve]")), 2)
        self.assertIn("Back to Project", wrapped)
        self.assertIn("Request Changes", wrapped)
        self.assertIn("Approve Preview", wrapped)
        self.assertIn(APPROVE_CONFIRM_PROMPT, wrapped)
        self.assertIn("Cancel", wrapped)
        self.assertIn("Approve and Continue", wrapped)
        self.assertIn('position: fixed', wrapped)
        self.assertIn("min-height: 44px", wrapped)
        self.assertIn("@media (max-width: 768px)", wrapped)
        self.assertIn("@media (max-width: 320px)", wrapped)
        self.assertIn("padding: 160px 16px 28px", wrapped)
        self.assertIn("paddingTop", wrapped)
        self.assertIn("ebook-preview-viewer", wrapped)
        self.assertIn("ebook-preview-stage", wrapped)
        self.assertIn("ebook-preview-frame", wrapped)
        self.assertIn('name="viewport"', wrapped)
        self.assertNotIn("100vw", wrapped)
        footer = soup.select_one(".ebook-preview-review-footer")
        self.assertIsNotNone(footer)
        sources = soup.select_one("#sources")
        self.assertIsNotNone(sources)
        self.assertLess(
            wrapped.find('<section id="sources">'),
            wrapped.find('<footer class="ebook-preview-review-footer"'),
        )
        back = workspace_return_url(99, stage="preview")
        changes = workspace_return_url(99, stage="preview", review="changes")
        preflight = workspace_return_url(99, stage="preflight", notice="preview-approved")
        self.assertIn("view=ebook-workspace", back)
        self.assertIn("stage=preview", back)
        self.assertNotIn("review=changes", back)
        self.assertIn("review=changes", changes)
        self.assertIn("stage=preflight", preflight)
        self.assertIn("notice=preview-approved", preflight)
        self.assertIn("showModal", wrapped)
        self.assertIn('preview_digest', wrapped)
        self.assertEqual(wrapped.count('class="ebook-preview-review-bar"'), 1)
        again = wrap_preview_review_document(
            wrapped, title="Sample Book", project_id=99, digest="abc123digest", can_approve=True
        )
        self.assertEqual(again.count('class="ebook-preview-review-bar"'), 1)

    def test_opening_wrapper_does_not_post_approve(self):
        wrapped = wrap_preview_review_document(
            "<html><head></head><body>book</body></html>",
            title="T",
            project_id=7,
            digest="d",
            can_approve=True,
        )
        approve_handler = wrapped[
            wrapped.find('querySelectorAll("[data-ebook-review-approve]")') : wrapped.find("var confirmBtn")
        ]
        self.assertIn("openDialog()", approve_handler)
        self.assertNotIn("fetch(", approve_handler)
        self.assertIn("fetch(cfg.approveUrl", wrapped)
        self.assertIn("confirmBtn.addEventListener", wrapped)


class FullPreviewReviewRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self._patches = _paid_patches()
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def _create_isolated(self):
        data = _preview_ready_data()
        project = database.create_project(
            "Full Preview Review Isolated",
            "ebook",
            data,
            user_saved=False,
            system_test=True,
            temporary=True,
        )
        return int(project["id"]), current_preview_digest(data), data

    def test_controls_appear_in_served_preview_not_stored_html(self):
        pid, digest, _data = self._create_isolated()
        opened = self.client.get(f"/ebook-workspace/{pid}/full-preview?digest={digest}")
        self.assertEqual(opened.status_code, 200, opened.get_data(as_text=True)[:400])
        html = opened.get_data(as_text=True)
        self.assertIn(REVIEW_BAR_TITLE, html)
        self.assertIn("Approve Preview", html)
        self.assertIn("Back to Project", html)
        self.assertIn("Request Changes", html)
        self.assertIn(APPROVE_CONFIRM_PROMPT, html)
        self.assertIn('href="#chapter-1"', html)
        self.assertNotIn("about:srcdoc", html)
        stored = str((database.get_project(pid)["data"] or {}).get("ebook_preview_html") or "")
        self.assertNotIn("Approve Preview", stored)
        self.assertNotIn("ebook-preview-review-bar", stored)
        self.assertNotIn(REVIEW_BAR_TITLE, stored)
        self.assertIn("<pdf:nextpage", stored)
        self.assertNotIn("<pdf:nextpage", html)
        self.assertIn("ebook-preview-page-break", html)
        self.assertIn("ebook-preview-stage", html)

    def test_opening_preview_does_not_approve(self):
        pid, digest, _data = self._create_isolated()
        opened = self.client.get(f"/ebook-workspace/{pid}/full-preview?digest={digest}")
        self.assertEqual(opened.status_code, 200)
        row = database.get_project(pid)
        data = row["data"]
        self.assertTrue(preview_opened_matches_current(data))
        self.assertFalse(is_approved(data["ebook_workspace"], "preview"))
        self.assertEqual(stage_status(data["ebook_workspace"], "preview"), STATUS_AWAITING)
        self.assertFalse(data.get("export_ready"))

    def test_approve_from_viewer_requires_matching_digest_and_goes_to_preflight(self):
        pid, digest, _data = self._create_isolated()
        opened = self.client.get(f"/ebook-workspace/{pid}/full-preview?digest={digest}")
        self.assertEqual(opened.status_code, 200)
        html = opened.get_data(as_text=True)
        self.assertIn("data-ebook-review-confirm", html)
        self.assertIn("Approve and Continue", html)
        stale = self.client.post(
            f"/ebook-workspace/{pid}/approve",
            json={"stage": "preview", "preview_digest": "not-the-current-digest"},
        )
        self.assertEqual(stale.status_code, 400)
        self.assertEqual(stale.get_json().get("error"), STALE_PREVIEW_MESSAGE)
        still = database.get_project(pid)["data"]
        self.assertFalse(is_approved(still["ebook_workspace"], "preview"))
        approved = self.client.post(
            f"/ebook-workspace/{pid}/approve",
            json={"stage": "preview", "preview_digest": digest},
        )
        self.assertEqual(approved.status_code, 200, approved.get_data(as_text=True)[:400])
        ws = approved.get_json()["workspace"]
        self.assertEqual(ws["current_stage"], "preflight")
        self.assertTrue(ws["gates"]["preflight_enabled"])
        self.assertFalse(ws["gates"]["export_enabled"])
        live = database.get_project(pid)["data"]
        self.assertTrue(is_approved(live["ebook_workspace"], "preview"))
        self.assertFalse(is_approved(live["ebook_workspace"], "preflight"))

    def test_confirmation_copy_and_success_return_urls(self):
        pid, digest, _data = self._create_isolated()
        html = self.client.get(f"/ebook-workspace/{pid}/full-preview?digest={digest}").get_data(as_text=True)
        self.assertIn(APPROVE_CONFIRM_PROMPT, html)
        self.assertIn(workspace_return_url(pid, stage="preflight", notice="preview-approved"), html)
        self.assertIn(workspace_return_url(pid, stage="preview"), html)
        self.assertIn(workspace_return_url(pid, stage="preview", review="changes"), html)
        self.assertIn(APPROVE_SUCCESS_NOTICE, html)

    def test_request_changes_and_back_urls_preserve_digest(self):
        pid, digest, _data = self._create_isolated()
        self.client.get(f"/ebook-workspace/{pid}/full-preview?digest={digest}")
        html = self.client.get(f"/ebook-workspace/{pid}/full-preview?digest={digest}").get_data(as_text=True)
        self.assertIn("review=changes", html)
        after = database.get_project(pid)["data"]
        self.assertEqual(current_preview_digest(after), digest)
        self.assertTrue(preview_opened_matches_current(after))
        self.assertFalse(is_approved(after["ebook_workspace"], "preview"))
        self.assertFalse(after.get("export_ready"))
        ws = self.client.get(f"/ebook-workspace/{pid}").get_json()["workspace"]
        self.assertTrue(ws["design"]["preview_opened"])
        self.assertEqual(ws["design"]["preview_digest"], digest)

    def test_stale_digest_cannot_be_approved_after_open(self):
        pid, digest, _data = self._create_isolated()
        self.client.get(f"/ebook-workspace/{pid}/full-preview?digest={digest}")
        resp = self.client.post(
            f"/ebook-workspace/{pid}/approve",
            json={"stage": "preview", "preview_digest": digest[:-1] + ("0" if digest[-1] != "0" else "1")},
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.get_json().get("error"), STALE_PREVIEW_MESSAGE)
        self.assertFalse(is_approved(database.get_project(pid)["data"]["ebook_workspace"], "preview"))

    def test_locked_project_rejects_preview_approval(self):
        data = _preview_ready_data()
        from services.ebook_project_workspace import record_preview_opened

        data = record_preview_opened(data)
        locked = copy.deepcopy(data)
        locked["artifact_state"] = "LOCKED"
        digest = current_preview_digest(locked)
        with self.assertRaises((ValueError, ArtifactStateError)) as ctx:
            approve_stage(locked, "preview", preview_digest=digest)
        self.assertIn("LOCKED", str(ctx.exception))
        self.assertFalse(is_approved(locked["ebook_workspace"], "preview"))

    def test_failed_approval_leaves_preview_awaiting(self):
        pid, digest, _data = self._create_isolated()
        self.client.get(f"/ebook-workspace/{pid}/full-preview?digest={digest}")
        failed = self.client.post(
            f"/ebook-workspace/{pid}/approve",
            json={"stage": "preview", "preview_digest": "stale"},
        )
        self.assertEqual(failed.status_code, 400)
        html = self.client.get(f"/ebook-workspace/{pid}/full-preview?digest={digest}").get_data(as_text=True)
        self.assertIn("Approve Preview", html)
        self.assertFalse(is_approved(database.get_project(pid)["data"]["ebook_workspace"], "preview"))


class FullPreviewReviewBrowserWiringTests(unittest.TestCase):
    def test_spa_return_and_mobile_controls(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn('view === "ebook-workspace"', js)
        self.assertIn("openEbookWorkspace(pid", js)
        self.assertIn("replaceState", js)
        boot = js[js.find("async function bootFromQuery") :]
        ebook_branch = boot.split("if (view === \"ebook-workspace\" && pid)")[1].split("if (view) go(view)")[0]
        self.assertIn("return;", ebook_branch)
        self.assertNotIn("replaceState", ebook_branch)
        self.assertIn("window.location.assign(url)", js)
        self.assertNotIn('window.open(url, "_blank", "noopener")', js)
        self.assertIn(REQUEST_CHANGES_NOTICE, js)
        self.assertIn(APPROVE_SUCCESS_NOTICE, js)
        for label in CHANGE_CATEGORIES:
            self.assertIn(label, js)
        self.assertIn("data-ws-change-category", js)
        self.assertIn("data-ws-preview-changes", js)
        self.assertNotIn("estimate-cost", js[js.find("data-ws-change-category") : js.find("data-ws-change-category") + 800])
        wrap_js = (ROOT / "services" / "ebook_preview_review.py").read_text(encoding="utf-8")
        self.assertIn("min-height: 44px", wrap_js)
        self.assertIn("@media (max-width: 768px)", wrap_js)
        self.assertIn("@media (max-width: 320px)", wrap_js)
        self.assertIn("@media (max-width: 1365px)", wrap_js)
        self.assertIn("aria-label", wrap_js)
        self.assertIn(STALE_PREVIEW_MESSAGE, wrap_js)
        self.assertIn("cfg.staleMessage", wrap_js)
        self.assertIn("box-sizing: border-box", wrap_js)
        self.assertIn("overflow-x: hidden", wrap_js)
        self.assertIn("justify-content: center", wrap_js)
        self.assertIn("flex-direction: column", wrap_js)
        self.assertNotIn("100vw", wrap_js)

    def test_index_serves_workspace_view(self):
        html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
        self.assertIn("ebook-workspace", html)
        self.assertIn("ebookWorkspaceRoot", html)


class FullPreviewViewerShellTests(unittest.TestCase):
    def test_viewer_css_prevents_overflow_at_required_widths(self):
        from services.ebook_preview_review import VIEWER_BREAKPOINTS, _REVIEW_CSS

        self.assertEqual(VIEWER_BREAKPOINTS, (320, 768, 1366, 1920))
        css = _REVIEW_CSS
        self.assertNotIn("100vw", css)
        self.assertNotIn("margin-left:-", css.replace(" ", ""))
        self.assertNotIn("margin-left: -", css)
        self.assertIn("box-sizing: border-box", css)
        self.assertIn("overflow-x: hidden", css)
        self.assertIn("justify-content: center", css)
        self.assertIn("max-width: 8.5in", css)
        self.assertIn("flex-wrap: wrap", css)
        self.assertIn("flex-shrink: 0", css)
        self.assertIn("flex-direction: column", css)
        self.assertIn("@media (max-width: 320px)", css)
        self.assertIn("@media (max-width: 768px)", css)
        self.assertIn("@media (max-width: 1365px)", css)
        self.assertIn(".ebook-preview-stage", css)
        self.assertIn(".ebook-preview-frame", css)
        self.assertIn("paddingTop", (ROOT / "services" / "ebook_preview_review.py").read_text(encoding="utf-8"))

    def test_wrap_injects_centered_page_shell_without_touching_book_copy(self):
        book = (
            '<!doctype html><html lang="en"><head><meta charset="utf-8"/></head><body>'
            '<section class="legal-page" id="copyright"><h2>Copyright</h2><p>All rights reserved.</p></section>'
            '<section class="toc-page" id="toc"><h2>Contents</h2><ol class="toc-list">'
            "<li>First chapter title</li></ol></section>"
            "</body></html>"
        )
        wrapped = wrap_preview_review_document(
            book, title="Shell Proof", project_id=12, digest="shell-digest", can_approve=True
        )
        soup = BeautifulSoup(wrapped, "html.parser")
        html_el = soup.find("html")
        self.assertIsNotNone(html_el)
        self.assertIn("ebook-preview-viewer", html_el.get("class", []))
        self.assertIsNotNone(soup.select_one('meta[name="viewport"]'))
        self.assertIsNotNone(soup.select_one(".ebook-preview-stage"))
        self.assertIsNotNone(soup.select_one(".ebook-preview-frame"))
        book_el = soup.select_one(".ebook-preview-book")
        self.assertIsNotNone(book_el)
        self.assertIn("Copyright", book_el.get_text(" ", strip=True))
        self.assertIn("First chapter title", book_el.get_text(" ", strip=True))
        nested = (
            '<html><head></head><body>'
            '<section class="title-page">Title</section>'
            "<pdf:nextpage />"
            '<section class="legal-page" id="copyright"><h2>Copyright</h2></section>'
            "</body></html>"
        )
        served = wrap_preview_review_document(
            nested, title="N", project_id=3, digest="d", can_approve=True
        )
        self.assertNotIn("<pdf:nextpage", served.lower())
        self.assertIn("ebook-preview-page-break", served)
        self.assertIn("legal-page", served)
        self.assertIn("Approve Preview", wrapped)
        self.assertIn("showModal", wrapped)
        self.assertIn(workspace_return_url(12, stage="preview"), wrapped)
        self.assertIn(workspace_return_url(12, stage="preview", review="changes"), wrapped)
        self.assertNotIn("shell-digest", soup.select_one(".ebook-preview-review-bar").get_text())


if __name__ == "__main__":
    unittest.main()
