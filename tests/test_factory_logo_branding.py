"""The Digital Product Factory logo is served locally on every customer page.

Recovered from the rescued ``onedrive-workspace-phase-a`` branch on 2026-09-09.
The branch had placed the logo but never ran a test or a browser against it;
this file is the customer-path protection for the current templates.

Covers:
  * the asset lives under ``static/`` and is a real PNG the app serves itself
    (no outside URL, so the logo works offline and never phones home);
  * the home page, the two standalone builder pages and the cover editor all
    carry the logo with the accessible name "Digital Product Factory";
  * the page chrome those templates already had is still there (title,
    navigation, back links, the mobile nav), so the logo only adds branding.

Zero paid/external calls. FACTORY_TEST_MODE via environment.
"""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("FACTORY_TEST_MODE", "1")
os.environ.setdefault("OPENAI_API_KEY", "")
os.environ.setdefault("TAVILY_API_KEY", "")

from flask import render_template  # noqa: E402

from app import app  # noqa: E402

LOGO_PATH = "/static/images/branding/digital_product_factory_logo.png"
LOGO_FILE = ROOT / "static" / "images" / "branding" / "digital_product_factory_logo.png"
TEMPLATES = ROOT / "templates"
IMG_RE = re.compile(r"<img\b[^>]*>", re.I | re.S)


def _logo_tags(html: str) -> list[str]:
    return [t for t in IMG_RE.findall(html) if LOGO_PATH in t]


class LogoAssetTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_the_logo_file_is_a_real_png_in_static(self):
        self.assertTrue(LOGO_FILE.is_file(), LOGO_FILE)
        with LOGO_FILE.open("rb") as fh:
            head = fh.read(8)
        self.assertEqual(head, b"\x89PNG\r\n\x1a\n", "asset must be a PNG")
        self.assertLess(LOGO_FILE.stat().st_size, 600_000, "keep the header asset light")

    def test_the_app_serves_the_logo_itself(self):
        resp = self.client.get(LOGO_PATH)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.mimetype, "image/png")
        self.assertEqual(resp.data[:8], b"\x89PNG\r\n\x1a\n")

    def test_no_template_loads_the_logo_from_an_outside_url(self):
        for tpl in TEMPLATES.glob("*.html"):
            html = tpl.read_text(encoding="utf-8", errors="replace")
            for tag in IMG_RE.findall(html):
                if "digital_product_factory_logo" not in tag:
                    continue
                self.assertIn("url_for('static'", tag, f"{tpl.name}: logo must come from static/")
                self.assertNotRegex(tag, r"src=\"https?://", f"{tpl.name}: logo must not be remote")


class LogoOnEveryCustomerPageTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def _assert_logo(self, html: str, page: str, expected_count: int | None = None):
        tags = _logo_tags(html)
        self.assertTrue(tags, f"{page}: logo <img> missing")
        if expected_count is not None:
            self.assertEqual(len(tags), expected_count, f"{page}: unexpected logo count")
        for tag in tags:
            self.assertIn('alt="Digital Product Factory"', tag, f"{page}: logo needs its accessible name")
            self.assertIn(f'src="{LOGO_PATH}"', tag, f"{page}: logo must be the local static file")

    def test_home_page_shows_the_logo_in_sidebar_and_mobile_header(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self._assert_logo(html, "home", expected_count=2)
        sidebar, header = _logo_tags(html)
        self.assertIn("w-full", sidebar, "sidebar logo fills the white brand card")
        self.assertIn("md:hidden", header, "header copy only appears when the sidebar is hidden")
        # The old placeholder mark is gone; the chrome the SPA relies on is intact.
        self.assertNotIn(">DP<", html)
        for anchor in ('id="nav"', 'id="mobileNav"', 'id="pageTitle"', 'id="mainScroll"'):
            self.assertIn(anchor, html, f"home page lost {anchor}")

    def test_crossword_builder_page_shows_the_logo(self):
        resp = self.client.get("/crossword-builder/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self._assert_logo(html, "crossword builder", expected_count=1)
        self.assertIn("<h1 class=\"text-xl font-bold text-slate-900\">Crossword Builder</h1>", html)
        self.assertIn("Back to Dashboard", html)
        self.assertIn('id="cwForm"', html)

    def test_word_search_builder_page_shows_the_logo(self):
        resp = self.client.get("/word-search-builder/")
        self.assertEqual(resp.status_code, 200)
        html = resp.get_data(as_text=True)
        self._assert_logo(html, "word search builder", expected_count=1)
        self.assertIn("<h1 class=\"text-xl font-bold text-slate-900\">Word Search Builder</h1>", html)
        self.assertIn("Back to Dashboard", html)
        self.assertIn('id="wsForm"', html)

    def test_cover_editor_page_shows_the_logo(self):
        # Rendered directly so the test needs no saved project and generates nothing.
        with app.test_request_context("/cover-editor?project_id=1"):
            html = render_template(
                "cover_editor.html",
                project_id=1,
                cover_json={},
                product_type="crossword",
                package_id="",
            )
        self._assert_logo(html, "cover editor", expected_count=1)
        self.assertIn('id="btnBackFactory"', html)
        self.assertIn("<h1>Cover Editor</h1>", html)
        self.assertIn('id="coverFrame"', html)


if __name__ == "__main__":
    unittest.main()
