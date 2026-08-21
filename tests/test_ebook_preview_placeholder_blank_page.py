"""Regression: URL placeholders, blank pages, stale preview, open-before-approve.

Zero paid/external calls. Isolated projects only except read-only #4249 checks.
"""
from __future__ import annotations

import copy
import os
import re
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from app import app  # noqa: E402
import database  # noqa: E402
from services.ebook_book_layout import (  # noqa: E402
    collapse_consecutive_page_breaks,
    render_designed_ebook_html,
    rewrite_bracketed_website_placeholders,
    unresolved_placeholders,
)
from services.ebook_design_preflight import run_design_preflight  # noqa: E402
from services.ebook_design_spec import build_ebook_design  # noqa: E402
from services.ebook_design_workspace import (  # noqa: E402
    apply_url_placeholder_manuscript_repair,
    approve_visuals_local,
    build_preview,
    select_and_stage_theme,
)
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript  # noqa: E402
from services.ebook_project_workspace import (  # noqa: E402
    STATUS_APPROVED,
    STATUS_AWAITING,
    approve_stage,
    build_acceptance_project_data,
    current_preview_digest,
    is_approved,
    manuscript_digest,
    preview_opened_matches_current,
    record_preview_opened,
    revoke_unviewed_preview_approval,
    set_stage_status,
    stage_status,
    workspace_public_view,
)

BEFORE_ONE = (
    "Research summarized by sources such as [startcosts.com](https://startcosts.com) "
    "and [photographylaunchpad.com](https://photographylaunchpad.com) points to two common starting lanes:"
)
AFTER_ONE = (
    "Research summarized by independent photography-startup cost guides such as startcosts.com and photographylaunchpad.com points to two common starting lanes:"
)
BEFORE_TWO = (
    "Research cited by [photographylaunchpad.com](https://photographylaunchpad.com) "
    "and [startcosts.com](https://startcosts.com) shows wide pricing variation, which is exactly why guesswork is risky."
)
AFTER_TWO = (
    "Independent photography-startup cost research from startcosts.com and photographylaunchpad.com shows wide pricing variation, which is exactly why guesswork is risky."
)

LIVE_4249 = 4249
EXPECTED_COVER_SHA = "465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd"
EXPECTED_COVER_DIGEST = "55567b21e03e3d5734ff5c355c3f4771b4771480d88566ebbdabcbd0d970d016"


def _inject_url_placeholder_sentences(md: str) -> str:
    block = f"{BEFORE_ONE}\n\n{BEFORE_TWO}\n\n"
    if BEFORE_ONE in md:
        return md
    return block + md


def _paid_patches():
    return (
        patch("ai_client.get_client", side_effect=AssertionError("paid client")),
        patch("ai_client.chat", side_effect=AssertionError("paid chat")),
        patch("ai_client.chat_json", side_effect=AssertionError("paid chat_json")),
    )


class UrlPlaceholderAndBlankPageTests(unittest.TestCase):
    def test_photo_token_still_fails_but_domain_is_url_placeholder(self):
        md = (
            "Keep [photo] as a visual token. "
            "Rewrite [photographylaunchpad.com] as a URL placeholder. "
            "Do not flag [inquiry-to-booking scenario] or [ ] checkboxes."
        )
        found = unresolved_placeholders(md)
        self.assertIn("[photo]", found)
        self.assertIn("[photographylaunchpad.com]", found)
        self.assertNotIn("[inquiry-to-booking scenario]", found)
        self.assertFalse(any(item.strip() in {"[", "]", "[ ]"} for item in found))

    def test_rewrite_only_affected_sentences(self):
        md = f"Intro.\n\n{BEFORE_ONE}\n\nMiddle.\n\n{BEFORE_TWO}\n\nTail [inquiry-to-booking scenario].\n"
        out, replacements = rewrite_bracketed_website_placeholders(md)
        self.assertEqual(len(replacements), 2)
        self.assertEqual(replacements[0]["after"], AFTER_ONE)
        self.assertEqual(replacements[1]["after"], AFTER_TWO)
        self.assertIn(AFTER_ONE, out)
        self.assertIn(AFTER_TWO, out)
        self.assertNotIn("[photographylaunchpad.com]", out)
        self.assertNotIn("[startcosts.com]", out)
        self.assertIn("[inquiry-to-booking scenario]", out)
        self.assertIn("Intro.", out)
        self.assertIn("Middle.", out)

    def test_consecutive_page_breaks_collapse(self):
        html = "<section>a</section><pdf:nextpage /><pdf:nextpage />\n<pdf:nextpage /><section>b</section>"
        collapsed = collapse_consecutive_page_breaks(html)
        self.assertEqual(collapsed.count("<pdf:nextpage"), 1)
        self.assertIn("<section>a</section>", collapsed)
        self.assertIn("<section>b</section>", collapsed)

    def test_renderer_marks_last_block_and_does_not_double_break(self):
        md = "## Chapter 1\n\nBody paragraph one.\n\nLast paragraph stays with the chapter.\n"
        design = build_ebook_design(theme_id="modern_practical", manuscript_digest="abc")
        html = render_designed_ebook_html(
            title="T",
            subtitle="S",
            author="A",
            manuscript_md=md,
            design=design,
        )
        self.assertIn("chapter-last-block", html)
        self.assertNotIn("chapter-last-keep", html)
        self.assertNotIn("<table class=\"chapter-last-keep\">", html)
        self.assertNotRegex(html, r"<table[^>]*chapter-last-block")
        self.assertIsNone(re.search(r"<pdf:nextpage\s*/>\s*<pdf:nextpage\s*/>", html, re.I))
        self.assertNotIn("[photographylaunchpad.com]", html)

    def test_preflight_flags_url_placeholder_not_scenario_brackets(self):
        data = build_acceptance_project_data()
        data["content"] = BEFORE_ONE
        data["ebook"] = BEFORE_ONE
        report = run_design_preflight(data, html="<p>[photographylaunchpad.com]</p>", pdf_bytes=b"")
        self.assertTrue(any(f.code == "unresolved_placeholder" for f in report.findings))
        data2 = build_acceptance_project_data()
        data2["content"] = "Use the [inquiry-to-booking scenario] as a walkthrough."
        data2["ebook"] = data2["content"]
        report2 = run_design_preflight(data2, html="<p>Use the inquiry-to-booking scenario as a walkthrough.</p>", pdf_bytes=b"")
        self.assertFalse(any(f.code == "unresolved_placeholder" for f in report2.findings))


class PreviewOpenAndInvalidationTests(unittest.TestCase):
    def setUp(self):
        self._patches = _paid_patches()
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def _preview_awaiting(self) -> dict:
        from services.ebook_photo_cover import attach_licensed, select_layout

        data = build_acceptance_project_data()
        data["acceptance_marker"] = "ebook_preview_open_isolated"
        data["artifact_id"] = f"ebook-preview-open-{uuid.uuid4().hex[:12]}"
        md = _inject_url_placeholder_sentences(build_event_photo_strong_manuscript())
        data["content"] = md
        data["ebook"] = md
        ws = data["ebook_workspace"]
        set_stage_status(ws, "manuscript", STATUS_AWAITING)
        data = approve_stage(data, "manuscript")
        data = approve_visuals_local(data)
        data = attach_licensed(data, "event_reception_night", project_id=None)
        data = select_layout(data, "printed_moment", project_id=None)
        data = approve_stage(data, "cover")
        data = select_and_stage_theme(data, "modern_practical")
        data = approve_stage(data, "design")
        data = build_preview(data)
        return data

    def test_approval_blocked_until_current_preview_opened(self):
        data = self._preview_awaiting()
        self.assertEqual(stage_status(data["ebook_workspace"], "preview"), STATUS_AWAITING)
        self.assertFalse(preview_opened_matches_current(data))
        with self.assertRaises(ValueError) as ctx:
            approve_stage(data, "preview")
        self.assertIn("Open the full preview", str(ctx.exception))
        opened = record_preview_opened(copy.deepcopy(data))
        self.assertTrue(preview_opened_matches_current(opened))
        approved = approve_stage(opened, "preview")
        self.assertTrue(is_approved(approved["ebook_workspace"], "preview"))

    def test_stale_preview_invalidation_and_unviewed_revoke(self):
        data = self._preview_awaiting()
        cover_digest = str((data.get("cover_design") or {}).get("cover_digest") or "")
        theme = str((data.get("ebook_design") or {}).get("theme_id") or "")
        visual = str(data.get("ebook_visual_manifest_digest") or "")
        old_digest = current_preview_digest(data)
        data = record_preview_opened(data)
        self.assertTrue(preview_opened_matches_current(data))

        set_stage_status(data["ebook_workspace"], "preview", STATUS_APPROVED)
        data["ebook_workspace"]["preview_opened"] = {"digest": "stale-digest"}
        data = revoke_unviewed_preview_approval(data)
        self.assertFalse(is_approved(data["ebook_workspace"], "preview"))
        self.assertEqual(stage_status(data["ebook_workspace"], "preview"), STATUS_AWAITING)

        repaired = apply_url_placeholder_manuscript_repair(copy.deepcopy(data))
        self.assertNotIn("[photographylaunchpad.com]", str(repaired.get("content") or ""))
        self.assertIn(AFTER_ONE, str(repaired.get("content") or ""))
        self.assertIn(AFTER_TWO, str(repaired.get("content") or ""))
        self.assertFalse(repaired.get("ebook_preview_html"))
        self.assertFalse(repaired.get("export_ready"))
        self.assertTrue(is_approved(repaired["ebook_workspace"], "design"))
        self.assertTrue(is_approved(repaired["ebook_workspace"], "cover"))
        self.assertFalse(is_approved(repaired["ebook_workspace"], "preview"))
        self.assertFalse(is_approved(repaired["ebook_workspace"], "preflight"))
        self.assertEqual(str((repaired.get("cover_design") or {}).get("cover_digest") or ""), cover_digest)
        self.assertEqual(str((repaired.get("ebook_design") or {}).get("theme_id") or ""), theme)
        self.assertEqual(str(repaired.get("ebook_visual_manifest_digest") or ""), visual)
        self.assertNotEqual(manuscript_digest(repaired), manuscript_digest(data))
        self.assertFalse(preview_opened_matches_current(repaired))
        with self.assertRaises(ValueError):
            approve_stage(repaired, "preview")
        rebuilt = build_preview(repaired)
        self.assertEqual(stage_status(rebuilt["ebook_workspace"], "preview"), STATUS_AWAITING)
        self.assertNotEqual(current_preview_digest(rebuilt), old_digest)
        self.assertFalse(rebuilt.get("export_ready"))
        view = workspace_public_view({"id": 9004249, "name": "iso", "data": rebuilt})
        self.assertTrue(view["design"]["preview_available"])
        self.assertFalse(view["design"]["preview_opened"])
        self.assertFalse(view["gates"]["approve_preview_enabled"])
        self.assertFalse(view["gates"]["export_enabled"])
        self.assertIn("/full-preview", view["design"]["preview_open_url"])


class FullPreviewRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        app.config["TESTING"] = True
        self._patches = _paid_patches()
        for p in self._patches:
            p.start()

    def tearDown(self):
        for p in self._patches:
            p.stop()

    def test_full_preview_route_records_opened_and_enables_approve(self):
        from services.ebook_photo_cover import attach_licensed, select_layout

        data = build_acceptance_project_data()
        data["artifact_id"] = f"ebook-full-preview-{uuid.uuid4().hex[:12]}"
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
        data = build_preview(data)
        project = database.create_project(
            "Full Preview Isolated",
            "ebook",
            data,
            user_saved=False,
            system_test=True,
            temporary=True,
        )
        pid = int(project["id"])
        blocked = self.client.post(f"/ebook-workspace/{pid}/approve", json={"stage": "preview"})
        self.assertEqual(blocked.status_code, 400)
        digest = current_preview_digest(data)
        opened = self.client.get(f"/ebook-workspace/{pid}/full-preview?digest={digest}")
        self.assertEqual(opened.status_code, 200, opened.get_data(as_text=True)[:400])
        self.assertIn("text/html", opened.headers.get("Content-Type", ""))
        self.assertIn("From First Booking", opened.get_data(as_text=True))
        self.assertIn('href="#chapter-1"', opened.get_data(as_text=True))
        self.assertNotIn("about:srcdoc", opened.get_data(as_text=True))
        self.assertNotIn("srcdoc=", opened.get_data(as_text=True))
        ws = self.client.get(f"/ebook-workspace/{pid}").get_json()["workspace"]
        self.assertTrue(ws["design"]["preview_opened"])
        self.assertTrue(ws["gates"]["approve_preview_enabled"])
        approved = self.client.post(f"/ebook-workspace/{pid}/approve", json={"stage": "preview"})
        self.assertEqual(approved.status_code, 200, approved.get_data(as_text=True)[:400])

    def test_js_requires_open_full_preview(self):
        js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("Open Full Preview", js)
        self.assertIn("data-ws-open-full-preview", js)
        self.assertIn("/preview-opened", js)
        self.assertIn("data-ws-approve-preview ${previewOpened ? \"\" : \"disabled\"}", js)


class Live4249ReadOnlyTests(unittest.TestCase):
    def test_live_4249_identity_and_stop_state(self):
        row = database.get_project(LIVE_4249)
        self.assertIsNotNone(row, "project #4249 must exist")
        data = row["data"]
        md = str(data.get("content") or data.get("ebook") or "")
        html = str(data.get("ebook_preview_html") or data.get("preview_html") or "")
        cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
        src = cover.get("source") if isinstance(cover.get("source"), dict) else {}
        design = data.get("ebook_design") if isinstance(data.get("ebook_design"), dict) else {}
        ws = data.get("ebook_workspace") or {}
        self.assertNotIn("[photographylaunchpad.com]", md)
        self.assertNotIn("[photographylaunchpad.com]", html)
        self.assertFalse(unresolved_placeholders(md))
        self.assertEqual(str(src.get("sha256") or ""), EXPECTED_COVER_SHA)
        self.assertEqual(str(cover.get("cover_digest") or ""), EXPECTED_COVER_DIGEST)
        self.assertEqual(str(design.get("theme_id") or data.get("design_theme") or ""), "modern_practical")
        self.assertEqual(str(cover.get("selected_layout") or ""), "full_bleed_editorial")
        self.assertEqual(str(data.get("title") or ""), "From First Booking to On-Site Prints")
        self.assertTrue(html.strip())
        self.assertEqual(stage_status(ws, "preview"), STATUS_AWAITING)
        self.assertFalse(is_approved(ws, "preview"))
        self.assertFalse(is_approved(ws, "preflight"))
        self.assertFalse(data.get("export_ready"))
        self.assertNotIn("MANDATORY DELIVERABLE", md)
        self.assertNotIn("$2.50 for writing and refinement stages", md)
        self.assertNotIn("chapter-last-keep", html)
        self.assertNotIn("This interior is typeset from the approved manuscript", html)
        self.assertEqual(html.lower().count(">copyright"), 1)
        self.assertNotIn("Unnumbered", html)
        self.assertEqual(len(re.findall(r"For beginner and intermediate photographers", html, re.I)), 1)
        view = workspace_public_view(row)
        self.assertTrue(view["design"]["preview_available"])
        self.assertIn("/full-preview", view["design"]["preview_open_url"] or "")
        self.assertFalse(view["gates"]["export_enabled"])
        ident = data.get("ebook_export_identity") or {}
        self.assertEqual(ident.get("preview_digest"), ident.get("pdf_sha256"))
        self.assertEqual(ident.get("manuscript_digest"), manuscript_digest(data))
        self.assertEqual(ident.get("design_digest"), design.get("digest"))
        self.assertEqual(ident.get("cover_digest"), cover.get("cover_digest"))

    def test_live_4249_in_memory_repair_does_not_mutate_cover(self):
        row = database.get_project(LIVE_4249)
        self.assertIsNotNone(row, "project #4249 must exist")
        original = copy.deepcopy(row["data"])
        md = str(original.get("content") or "")
        cover_before = str((original.get("cover_design") or {}).get("cover_digest") or "")
        sha_before = str(((original.get("cover_design") or {}).get("source") or {}).get("sha256") or "")
        theme_before = str((original.get("ebook_design") or {}).get("theme_id") or "")
        if "[photographylaunchpad.com]" in md:
            repaired = apply_url_placeholder_manuscript_repair(copy.deepcopy(original))
            self.assertEqual(str((repaired.get("cover_design") or {}).get("cover_digest") or ""), cover_before)
            self.assertEqual(
                str(((repaired.get("cover_design") or {}).get("source") or {}).get("sha256") or ""),
                sha_before,
            )
            self.assertEqual(str((repaired.get("ebook_design") or {}).get("theme_id") or ""), theme_before)
            live_after = database.get_project(LIVE_4249)["data"]
            self.assertEqual(str(live_after.get("content") or ""), md)
            return
        self.assertEqual(cover_before, EXPECTED_COVER_DIGEST)
        self.assertEqual(sha_before, EXPECTED_COVER_SHA)
        self.assertEqual(theme_before, "modern_practical")
        self.assertNotIn("[photographylaunchpad.com]", md)


if __name__ == "__main__":
    unittest.main()
