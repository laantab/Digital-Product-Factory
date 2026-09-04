"""The Build button's browser routing, without needing a browser.

ROOT CAUSE THIS GUARDS
----------------------
runProduct() posted /generate-product and handed the reply to renderProduct().
Once the ebook build moved onto the workspace orchestrator that reply became a
build envelope -- no preview, no cover, no actions -- so a customer who clicked
Build on the ebook form landed on a blank screen. The full release gate caught
it through the real-browser test; these checks catch it in seconds, and they
also pin the parts of the contract the browser test cannot see.

No external call is made by any test here.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FACTORY_TEST_MODE", "1")

APP_JS = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
INDEX_HTML = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")


def _strip_comments(src: str) -> str:
    """Drop // and /* */ comments so assertions test code, not prose."""
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return "\n".join(re.sub(r"//.*$", "", line) for line in src.splitlines())


def _function_body(src: str, name: str) -> str:
    start = src.index(name)
    depth = 0
    seen = False
    for i in range(start, len(src)):
        if src[i] == "{":
            depth += 1
            seen = True
        elif src[i] == "}":
            depth -= 1
            if seen and depth == 0:
                return src[start : i + 1]
    raise AssertionError(f"could not bound {name}")


class EbookBuildRoutingTests(unittest.TestCase):
    def test_ebook_never_reaches_render_product(self):
        body = _function_body(APP_JS, "async function runProduct()")
        ebook_branch = _function_body(
            body[body.index('if (factoryType === "ebook")') :],
            'if (factoryType === "ebook")',
        )
        # Assert on code, not on the comment that explains the defect.
        code = _strip_comments(ebook_branch)
        self.assertIn("startEbookBuild(fields)", code)
        self.assertNotIn("renderProduct", code)
        self.assertNotIn("/generate-product", code)
        # And it returns, so nothing below it can run for an ebook.
        self.assertIn("return startEbookBuild(fields);", ebook_branch)

    def test_other_product_types_keep_the_original_path(self):
        """The unchanged path must still exist for every other builder."""
        body = _function_body(APP_JS, "async function runProduct()")
        self.assertIn('api("/generate-product"', body)
        self.assertIn("renderProduct(data)", body)
        # The ebook branch returns before it, so only other types get there.
        self.assertLess(
            body.index("startEbookBuild(fields)"),
            body.index('api("/generate-product"'),
        )

    def test_build_uses_the_canonical_endpoints(self):
        body = _function_body(APP_JS, "async function startEbookBuild(fields)")
        self.assertIn('api("/ebook/build"', body)
        self.assertIn('go("ebook-build")', body)
        loop = _function_body(APP_JS, "async function _ebookBuildLoop(projectId, runToken)")
        self.assertIn("/advance", loop)
        reopen = _function_body(APP_JS, "async function openEbookBuild(projectId)")
        self.assertIn("/status", reopen)
        self.assertNotIn('api("/ebook/build"', reopen, "reopening must never start a new build")

    def test_advance_requests_cannot_overlap(self):
        loop = _function_body(APP_JS, "async function _ebookBuildLoop(projectId, runToken)")
        self.assertIn("if (_ebookBuildBusy) return;", loop)
        self.assertIn("_ebookBuildBusy = true;", loop)
        self.assertIn("_ebookBuildBusy = false;", loop)
        self.assertIn("finally", loop)

    def test_loop_stops_on_finish_failure_and_navigation(self):
        loop = _function_body(APP_JS, "async function _ebookBuildLoop(projectId, runToken)")
        self.assertIn("status.finished", loop)
        self.assertIn("status.failed", loop)
        self.assertIn("runToken !== _ebookBuildRun", loop)
        # A recoverable wait must pause rather than hammer the stage.
        self.assertIn("status.retrying", loop)
        self.assertIn("EBOOK_RETRY_WAIT_MS", loop)

    def test_refresh_resumes_the_same_project(self):
        self.assertIn("EBOOK_BUILD_KEY", APP_JS)
        self.assertIn("sessionStorage", APP_JS)
        self.assertIn("_ebookBuildRemembered()", APP_JS)
        self.assertIn("await openEbookBuild(resumeBuild)", APP_JS)

    def test_the_build_view_exists_and_is_hidden_by_default(self):
        self.assertIn('data-view="ebook-build"', INDEX_HTML)
        self.assertIn('id="ebookBuildRoot"', INDEX_HTML)
        section = INDEX_HTML[INDEX_HTML.index('data-view="ebook-build"') :][:200]
        self.assertIn("hidden", section)
        self.assertIn('"ebook-build": "Your Ebook"', APP_JS)

    def test_finished_screen_offers_the_five_customer_actions(self):
        render = _function_body(APP_JS, "function renderEbookBuild(status)")
        for marker, label in (
            ("data-ebook-open", "Open Product"),
            ("data-ebook-dl-pdf", "Download PDF"),
            ("data-ebook-dl-zip", "Download ZIP"),
            ("data-ebook-changes", "Make Changes"),
            ("data-ebook-approve", "Approve Product"),
        ):
            self.assertIn(marker, render)
            self.assertIn(label, render)

    def test_customer_screen_shows_no_internal_language(self):
        render = _function_body(APP_JS, "function renderEbookBuild(status)")
        for banned in (
            "Confirm paid action",
            "Confirmation token",
            "Maximum total",
            "Per-chapter maximum",
            "OpenAI",
            "Ollama",
            "Qwen",
            "Pexels",
            "Tavily",
            "Traceback",
            "Approve & Save",
            "JSON.stringify(status",
        ):
            self.assertNotIn(banned, render, f"customer screen leaks {banned!r}")
        # One progress bar, and the plain-language headline.
        self.assertEqual(render.count("data-ebook-build-bar"), 0)
        self.assertIn("_ebookBuildBar", render)
        self.assertIn("Preparing your ebook", render)

    def test_reopening_a_one_click_build_avoids_the_stage_rail(self):
        self.assertIn("if (d.ebook_build) {\n      openEbookBuild(p.id);", APP_JS)
        self.assertIn("if (_isEbookProject(p) && d0.ebook_build) {", APP_JS)

    def test_ebook_button_is_named_for_what_it_does(self):
        self.assertIn('id === "ebook" ? "Build My Ebook" : "Generate Product"', APP_JS)


class BuildStatusContractTests(unittest.TestCase):
    """The payload the screen renders must carry no internal detail."""

    def test_status_payload_is_customer_safe(self):
        from services.ebook_build_orchestrator import status_payload

        data = {
            "title": "A Book",
            "artifact_state": "DRAFT",
            "ebook_preview_html": "<html>x</html>",
            "exports": {"files": {"pdf": {"url": "/download/p/ebook.pdf"},
                                  "zip": {"url": "/download/p/package.zip"}}},
            "ebook_build": {
                "stages": {"research": {"status": "FAILED_RECOVERABLE", "attempts": 1,
                                        "error": "Traceback: OpenAI refused"}},
                "customer_message": "Researching your topic",
                "failed": False,
            },
        }
        payload = status_payload(data, 7)
        blob = json.dumps(payload)
        for banned in ("Traceback", "OpenAI", "Ollama", "Qwen", "Pexels", "Tavily",
                       "token", "usd", "attempts\":"):
            self.assertNotIn(banned, blob, f"status payload leaks {banned!r}")
        self.assertEqual(payload["project_id"], 7)
        self.assertEqual(payload["artifact_state"], "DRAFT")
        self.assertEqual(payload["preview_url"], "/ebook-workspace/7/full-preview")

    def test_recoverable_wait_is_distinguishable_from_failure(self):
        from services.ebook_build_orchestrator import status_payload

        data = {
            "ebook_build": {
                "stages": {"research": {"status": "FAILED_RECOVERABLE", "attempts": 1}},
                "failed": False,
            }
        }
        payload = status_payload(data, 1)
        self.assertTrue(payload["retrying"])
        self.assertFalse(payload["failed"])
        self.assertFalse(payload["finished"])
        self.assertEqual(payload["attempts_left"], 2)

    def test_a_repeat_start_attaches_to_the_same_build(self):
        from services.ebook_build_orchestrator import idempotency_key_for

        fields = {"ebook_title": "T", "topic": "x", "author_brand": "A"}
        self.assertEqual(
            idempotency_key_for(fields, "local"),
            idempotency_key_for(dict(fields), "local"),
        )
        other = dict(fields, ebook_title="Different")
        self.assertNotEqual(
            idempotency_key_for(fields, "local"), idempotency_key_for(other, "local")
        )

    def test_the_resume_list_says_which_builds_are_one_click(self):
        src = (ROOT / "database.py").read_text(encoding="utf-8")
        self.assertIn('"one_click": bool(data.get("ebook_build"))', src)


class RuntimeFontProvenanceTests(unittest.TestCase):
    """Materialized fonts are generated artifacts and must stay untracked."""

    def test_materialized_fonts_are_ignored(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("services/fonts/*.ttf", ignore)

    def test_bundled_fonts_are_only_a_last_resort(self):
        src = (ROOT / "services" / "ebook_fonts.py").read_text(encoding="utf-8")
        block = src[src.index('"regular": _first_existing') :]
        block = block[: block.index("]")]
        # EbookSans is the copy target, so it must rank last among candidates.
        self.assertIn("EbookSans-regular.ttf", block)
        self.assertLess(block.index("arial.ttf"), block.index("EbookSans-regular.ttf"))


if __name__ == "__main__":
    unittest.main()
