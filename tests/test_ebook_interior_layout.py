"""Focused ebook PDF interior layout tests. Zero paid/external calls."""
from __future__ import annotations

import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from services.ebook_book_layout import (  # noqa: E402
    _decorate_structured_html,
    render_designed_ebook_html,
)
from services.ebook_design_spec import build_ebook_design  # noqa: E402
from services.ebook_design_system import theme_css  # noqa: E402
from services.pdf_export import _html_to_pdf_xhtml2pdf  # noqa: E402
from tests._test_paths import resolve_test_exports_root  # noqa: E402

LAYOUT_MD = """# Layout Sample

## What This Business Actually Looks Like

An event photography business serves moments that happen live.

### How on-site prints change the offer

On-site prints change the business from later delivery to something guests can hold.

**Checklist: Insurance and certificate of insurance**
- [ ] Confirm registration matches the operating name
- [ ] Purchase active business insurance
- [ ] Ask each venue whether a COI is required

How on-site prints change the offerOn-site prints also change staffing.

## Startup Reality Check: Budget, Legal Basics, and Insurance

Legal basics required before event oneVenues ask for proof of insurance.

Checklist items in a paragraph: [ ] Confirm registration [ ] Purchase insurance [ ] Ask each venue
"""


def _pdf_text(html: str) -> str:
    import fitz

    pdf = _html_to_pdf_xhtml2pdf(html)
    doc = fitz.open(stream=pdf, filetype="pdf")
    try:
        return "\n".join(doc.load_page(i).get_text("text") or "" for i in range(doc.page_count))
    finally:
        doc.close()


class EbookInteriorLayoutTests(unittest.TestCase):
    def setUp(self):
        self._client = patch("ai_client.get_client", side_effect=AssertionError("paid OpenAI client"))
        self._tavily = patch(
            "services.market_research._tavily_context",
            side_effect=AssertionError("Tavily"),
        )
        self._client.start()
        self._tavily.start()
        self.design = build_ebook_design(theme_id="modern_practical", manuscript_digest="layout-test")

    def tearDown(self):
        self._tavily.stop()
        self._client.stop()

    def _html(self, md: str = LAYOUT_MD) -> str:
        return render_designed_ebook_html(
            title="From First Booking to On-Site Prints",
            subtitle="A Practical Guide",
            author="Lonnie Brown",
            manuscript_md=md,
            design=self.design,
            visual_plan=None,
        )

    def test_css_forces_block_layout(self):
        css = theme_css("modern_practical")
        self.assertIn("display: block", css)
        self.assertIn("ol.toc-list", css)
        self.assertIn("heading-keep", css)
        self.assertNotRegex(css, r"letter-spacing\s*:")

    def test_chapter_heading_not_concatenated(self):
        html = self._html()
        soup = BeautifulSoup(html, "html.parser")
        num = soup.select_one(".chapter-num")
        title = soup.select_one(".chapter-title")
        self.assertIsNotNone(num)
        self.assertIsNotNone(title)
        self.assertEqual(num.get_text(" ", strip=True), "Chapter 1")
        self.assertEqual(title.get_text(" ", strip=True), "What This Business Actually Looks Like")
        self.assertNotIn("Chapter 1What", html.replace("\n", ""))
        pdf_text = _pdf_text(html)
        self.assertNotRegex(pdf_text, r"Chapter\s+1What")
        self.assertRegex(pdf_text, r"Chapter\s+1\s+What This Business")

    def test_toc_items_on_separate_lines(self):
        html = self._html()
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("ol.toc-list li")
        self.assertGreaterEqual(len(rows), 2)
        titles = [li.get_text(" ", strip=True) for li in rows]
        self.assertTrue(any("What This Business Actually Looks Like" in t for t in titles))
        self.assertTrue(any("Startup Reality Check" in t for t in titles))
        pdf_text = _pdf_text(html)
        toc_chunk = pdf_text.split("Chapter 1")[0]
        self.assertNotIn(
            "ContentsWhat This Business Actually Looks LikeStartup",
            re.sub(r"[\t ]+", "", toc_chunk),
        )
        lines = [ln.strip() for ln in toc_chunk.splitlines() if ln.strip()]
        toc_lines_with_titles = [
            ln for ln in lines if "What This Business" in ln or "Startup Reality Check" in ln
        ]
        self.assertGreaterEqual(len(toc_lines_with_titles), 2)

    def test_checklist_items_not_jammed(self):
        html = self._html()
        soup = BeautifulSoup(html, "html.parser")
        items = [li.get_text(" ", strip=True) for li in soup.select("ul.checklist li")]
        self.assertGreaterEqual(len(items), 3)
        for item in items:
            self.assertNotIn("[ ]", item)
        pdf_text = _pdf_text(html)
        self.assertNotIn("[ ] Confirm registration [ ] Purchase", pdf_text)
        self.assertIn("Confirm registration", pdf_text)
        self.assertIn("Purchase active business insurance", pdf_text)

    def test_checkbox_not_inside_paragraphs(self):
        html = self._html()
        soup = BeautifulSoup(html, "html.parser")
        for p in soup.find_all("p"):
            text = p.get_text(" ", strip=True)
            self.assertNotIn("[ ]", text)
            self.assertNotRegex(text, r"\[\s*[xX ]?\s*\]")
        jammed = _decorate_structured_html(
            "<p>Bring these: [ ] Confirm registration [ ] Purchase insurance [ ] Ask each venue</p>"
        )
        soup2 = BeautifulSoup(jammed, "html.parser")
        self.assertTrue(soup2.select("ul.checklist li"))
        self.assertFalse(any("[ ]" in p.get_text(" ", strip=True) for p in soup2.find_all("p")))

    def test_section_headings_are_real_headings(self):
        html = self._html()
        soup = BeautifulSoup(html, "html.parser")
        headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h3", "h4"])]
        self.assertTrue(any("How on-site prints change the offer" in h for h in headings))
        self.assertTrue(any("Checklist: Insurance" in h for h in headings))
        pdf_text = _pdf_text(html)
        self.assertNotIn("offerOn-site", pdf_text)
        self.assertNotIn("oneVenues", pdf_text)

    def test_no_openai_or_tavily_during_layout_render(self):
        html = self._html()
        self.assertIn("What This Business Actually Looks Like", html)
        self.assertNotIn("<img", html.lower())

    def test_restored_visuals_do_not_jam_chapter_heading(self):
        from PIL import Image

        vis = resolve_test_exports_root() / "_layout_visual_test"
        vis.mkdir(parents=True, exist_ok=True)
        png = vis / "v_ch1.png"
        Image.new("RGB", (120, 80), (20, 80, 80)).save(png, "PNG")
        plan = {
            "chapters": [
                {
                    "chapter": "What This Business Actually Looks Like",
                    "chapter_index": 1,
                    "aids": [
                        {
                            "type": "photo",
                            "visual_id": "v_ch1",
                            "title": "Event photographer",
                            "caption": "A working photographer covering a live celebration.",
                            "asset_path": str(png),
                            "sha256": "abc",
                            "required": True,
                        }
                    ],
                }
            ]
        }
        html = render_designed_ebook_html(
            title="From First Booking to On-Site Prints",
            subtitle="A Practical Guide",
            author="Lonnie Brown",
            manuscript_md=LAYOUT_MD,
            design=self.design,
            visual_plan=plan,
        )
        self.assertIn("ebook-figure", html)
        self.assertIn('data-visual-id="v_ch1"', html)
        self.assertIn("<img", html.lower())
        self.assertNotIn("Chapter 1What", html.replace("\n", ""))
        pdf_text = _pdf_text(html)
        self.assertNotRegex(pdf_text, r"Chapter\s+1What")
        self.assertRegex(pdf_text, r"Chapter\s+1\s+What This Business")


if __name__ == "__main__":
    unittest.main()
