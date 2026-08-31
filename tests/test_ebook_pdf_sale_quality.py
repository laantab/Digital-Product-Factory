"""Universal ebook PDF sale-quality gates. Zero paid/external calls."""
from __future__ import annotations

import io
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from PIL import Image


def _solid_png(path: Path, color=(20, 80, 40), size=(400, 520)) -> Path:
    Image.new("RGB", size, color).save(path)
    return path


class EbookPdfSaleQualityTests(unittest.TestCase):
    def test_01_css_has_no_letter_spacing_and_12pt_body(self):
        from services import pdf_export

        self.assertIsNone(re.search(r"letter-spacing\s*:", pdf_export._PDF_CSS, flags=re.I))
        self.assertRegex(pdf_export._PDF_CSS, r"font-size:\s*12pt")
        self.assertIn("#111827", pdf_export._PDF_CSS)

    def test_02_keep_cells_override_table_9pt(self):
        from services import pdf_export

        self.assertRegex(pdf_export._PDF_CSS, r"td\.pdf-p-cell\s*\{[^}]*font-size:\s*12pt")
        self.assertRegex(pdf_export._PDF_CSS, r"td\.pdf-li-cell\s*\{[^}]*font-size:\s*12pt")

    def test_03_fonts_embed_as_ebooksans_not_helvetica(self):
        import fitz
        from services.pdf_export import _html_to_pdf_xhtml2pdf, _wrap_pdf_document

        html = _wrap_pdf_document(
            "Font Gate",
            '<section class="pdf-page chapter-page"><p>Container gardening keeps soil in a pot.</p></section>',
        )
        pdf = _html_to_pdf_xhtml2pdf(html)
        doc = fitz.open(stream=pdf, filetype="pdf")
        fonts = set()
        for page in doc:
            for block in page.get_text("dict").get("blocks") or []:
                for line in block.get("lines") or []:
                    for span in line.get("spans") or []:
                        fonts.add(span.get("font"))
        doc.close()
        self.assertTrue(fonts, "no text spans")
        joined = " ".join(fonts)
        self.assertTrue(
            any(
                token in joined
                for token in ("EbookSans", "Arial", "DejaVu", "Vera", "Bitstream")
            ),
            f"expected embedded TTF, got {fonts}",
        )
        self.assertFalse(fonts <= {"Helvetica", "Helvetica-Bold", "Helvetica-Oblique"})

    def test_04_markdown_links_stripped_from_summary(self):
        from services.pdf_export import _looks_like_markdown_source, _summary_page_html

        raw = "1. [Getting Started](#getting-started)\n2. [Soil](#soil)"
        self.assertTrue(_looks_like_markdown_source(raw))
        self.assertEqual(_summary_page_html(raw), "")

    def test_05_title_page_rejects_markdown_summary(self):
        from services.pdf_export import _inside_title_page_html

        html = _inside_title_page_html(
            "Guide",
            "Sub",
            "1. [Getting Started With Container Gardening](#getting-started)",
            "Author",
        )
        self.assertNotIn("](#", html)
        self.assertNotIn("getting-started", html)

    def test_06_duplicate_caption_omitted(self):
        from services.pdf_export import _pdf_visual_block_html

        html = _pdf_visual_block_html(
            "Sowing a seed in a small starter pot",
            "<p>photo</p>",
            "Sowing a seed in a small starter pot",
        )
        self.assertEqual(html.lower().count("sowing a seed in a small starter pot"), 1)

    def test_07_photo_aid_uses_caption_not_duplicate_title(self):
        from services.ebook_package import render_aid_html

        html = render_aid_html(
            {
                "type": "stock photo",
                "title": "Sowing a seed in a small starter pot",
                "caption": "Sowing a seed in a small starter pot",
                "body": "",
            }
        )
        self.assertEqual(html.lower().count("sowing a seed in a small starter pot"), 1)
        self.assertNotIn("va-title", html)

    def test_08_cover_full_bleed_has_no_white_corners(self):
        import fitz
        from services.ebook_pdf_images import full_bleed_cover_pdf_bytes

        tmp = ROOT / "test-results" / "ebook_pdf_sale_quality"
        tmp.mkdir(parents=True, exist_ok=True)
        src = _solid_png(tmp / "cover_src.png", (18, 42, 22), (800, 1035))
        pdf = full_bleed_cover_pdf_bytes(str(src))
        doc = fitz.open(stream=pdf, filetype="pdf")
        pix = doc[0].get_pixmap(alpha=False)
        doc.close()
        w, h = pix.width, pix.height
        for x, y in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0)):
            r, g, b = pix.pixel(x, y)[:3]
            self.assertLess(r, 80, f"white/light cover edge at {(x, y)} rgb={(r, g, b)}")

    def test_09_near_duplicate_photos_skipped(self):
        from services.ebook_pdf_images import average_hash, is_near_duplicate, jpeg_data_uri_from_path
        from services.pdf_export import _PDF_IMAGE_HASHES, _embed_local_pdf_image, _reset_pdf_image_dedupe

        tmp = ROOT / "test-results" / "ebook_pdf_sale_quality"
        tmp.mkdir(parents=True, exist_ok=True)
        a = _solid_png(tmp / "pot_a.png", (220, 90, 30), (200, 140))
        b = _solid_png(tmp / "pot_b.png", (218, 88, 28), (200, 140))
        _reset_pdf_image_dedupe()
        first = _embed_local_pdf_image(str(a))
        second = _embed_local_pdf_image(str(b))
        self.assertTrue(first.startswith("data:image/jpeg"))
        self.assertEqual(second, "")
        uri, phash, _ = jpeg_data_uri_from_path(str(a))
        self.assertTrue(is_near_duplicate(phash, [average_hash(Image.open(b))]))

    def test_10_compressed_jpeg_is_smaller_than_png(self):
        from services.ebook_pdf_images import jpeg_bytes

        tmp = ROOT / "test-results" / "ebook_pdf_sale_quality"
        tmp.mkdir(parents=True, exist_ok=True)
        path = tmp / "big.png"
        Image.new("RGB", (1600, 1067), (30, 90, 40)).save(path)
        png_size = path.stat().st_size
        jpg = jpeg_bytes(Image.open(path), quality=78, max_px=1100)
        self.assertLess(len(jpg), png_size)
        self.assertLess(len(jpg), 200_000)

    def test_11_qa_fails_raw_markdown(self):
        import fitz
        from services.ebook_qa_validator import validate_ebook_pdf

        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 100), "1. [Getting Started](#getting-started)", fontsize=12)
        pdf = doc.tobytes()
        result = validate_ebook_pdf(pdf)
        self.assertFalse(result.passed)
        self.assertTrue(any("Raw bracket" in e for e in result.errors))

    def test_12_qa_fails_white_cover_perimeter(self):
        import fitz
        from services.ebook_qa_validator import validate_ebook_pdf

        tmp = ROOT / "test-results" / "ebook_pdf_sale_quality"
        tmp.mkdir(parents=True, exist_ok=True)
        inner = _solid_png(tmp / "inner.png", (10, 40, 20), (200, 260))
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        page.draw_rect(page.rect, color=(1, 1, 1), fill=(1, 1, 1))
        page.insert_image(fitz.Rect(48, 48, 564, 744), filename=str(inner))
        pdf = doc.tobytes()
        result = validate_ebook_pdf(pdf)
        self.assertTrue(any("white perimeter" in e.lower() for e in result.errors))

    def test_13_qa_fails_sparse_interior_page(self):
        import fitz
        from services.ebook_qa_validator import validate_ebook_pdf

        doc = fitz.open()
        p0 = doc.new_page()
        p0.insert_text((72, 100), "Cover title block here with enough words", fontsize=14)
        doc.new_page()  # blank interior
        p2 = doc.new_page()
        p2.insert_text((72, 100), "Chapter body text that is long enough to count as content.", fontsize=12)
        result = validate_ebook_pdf(doc.tobytes())
        self.assertTrue(any("blank interior" in e.lower() for e in result.errors))

    def test_14_running_headers_stamped(self):
        import fitz
        from services.ebook_pdf_images import stamp_running_matter

        doc = fitz.open()
        doc.new_page()
        page = doc.new_page()
        page.insert_text((72, 200), "Chapter body", fontsize=12)
        stamped = stamp_running_matter(doc.tobytes(), title="Beginner Guide", author="Lonnie Brown")
        out = fitz.open(stream=stamped, filetype="pdf")
        text = out[1].get_text("text")
        fonts = set()
        d = out[1].get_text("dict")
        for block in d.get("blocks") or []:
            for line in block.get("lines") or []:
                for span in line.get("spans") or []:
                    fonts.add(str(span.get("font") or ""))
        out.close()
        self.assertIn("Beginner", text)
        self.assertIn("2", text)
        joined = " ".join(fonts)
        self.assertTrue(
            any(token in joined for token in ("EbookSans", "Arial", "DejaVu", "Vera", "Bitstream")),
            f"running header should use embedded body font, got {fonts}",
        )

    def test_15_legal_sheet_not_skipped(self):
        from bs4 import BeautifulSoup
        from services.pdf_export import _extract_structured_visual_pages

        soup = BeautifulSoup(
            """
            <div class="book">
              <section class="sheet cover"></section>
              <section class="sheet title-page"><h1>Title</h1></section>
              <section class="sheet legal"><h2>Copyright &amp; Disclaimer</h2>
                <p>Copyright 2026. All rights reserved. Educational use only.</p></section>
              <section class="sheet toc"><h2>Table of Contents</h2>
                <ul class="toc-list"><li><a href="#c1">One</a></li></ul></section>
              <section class="sheet chapter" id="c1"><h2>One</h2><p>Body paragraph for the chapter.</p></section>
            </div>
            """,
            "html.parser",
        )
        book = soup.select_one(".book")
        html, _ = _extract_structured_visual_pages(
            book, title="Title", subtitle="Sub", author="A", summary=None, cover_design=None
        )
        self.assertIn("legal-page", html)
        self.assertIn("All rights reserved", html)
        self.assertNotIn("](#", html)

    def test_18_duplicate_summary_skipped_legal_kept(self):
        from bs4 import BeautifulSoup
        from services.pdf_export import _extract_structured_visual_pages, _PDF_CSS

        opening = "Container gardening is one of the easiest ways to grow food at home."
        soup = BeautifulSoup(
            f"""
            <div class="book">
              <section class="sheet title-page"><h1>Title</h1></section>
              <section class="sheet legal"><h2>Copyright &amp; Disclaimer</h2>
                <p>Copyright 2026. All rights reserved. Educational use only.</p></section>
              <section class="sheet toc"><h2>Table of Contents</h2>
                <ul class="toc-list"><li><a href="#c1">One</a></li></ul></section>
              <section class="sheet chapter" id="c1"><h2>One</h2>
                <p>{opening} More chapter text here for a full opener.</p></section>
              <section class="sheet summary"><h2>Summary</h2><p>{opening}</p></section>
            </div>
            """,
            "html.parser",
        )
        book = soup.select_one(".book")
        html, _ = _extract_structured_visual_pages(
            book, title="Title", subtitle="Sub", author="A", summary=opening, cover_design=None
        )
        self.assertIn("legal-page", html)
        self.assertIn("toc-page", html)
        self.assertNotIn("summary-page", html)
        self.assertRegex(_PDF_CSS, r"\.toc-page\s*\{[^}]*page-break-after:\s*always")
        self.assertRegex(_PDF_CSS, r"\.legal-page\s*\{[^}]*page-break-after:\s*always")

    def test_19_stripped_cover_keeps_main_page_template(self):
        from services.pdf_export import (
            _MAIN_TEMPLATE_SWITCH,
            _apply_full_bleed_cover_template,
            _PDF_CSS,
        )

        body = (
            '<section class="pdf-page cover-page cda-cover-full-page">cover</section>'
            '<section class="pdf-page chapter-page"><p>Chapter body.</p></section>'
        )
        css, html = _apply_full_bleed_cover_template(_PDF_CSS, body)
        self.assertIn(_MAIN_TEMPLATE_SWITCH, html)
        wrapped = (
            "<!DOCTYPE html><html><head><style>" + css + "</style></head><body>"
            + html
            + "</body></html>"
        )
        from bs4 import BeautifulSoup
        import re as _re

        soup = BeautifulSoup(wrapped, "html.parser")
        for sec in soup.select("section.cover-page, section.cda-cover-full-page"):
            sec.decompose()
        text = str(soup).replace(_MAIN_TEMPLATE_SWITCH, "")
        text = _re.sub(r"(<body[^>]*>)", r"\1" + _MAIN_TEMPLATE_SWITCH, text, count=1)
        self.assertIn(_MAIN_TEMPLATE_SWITCH, text)
        self.assertNotIn("cda-cover-full-page", text)

    def test_16_readiness_blocks_on_qa_errors(self):
        from services.ebook_factory_pipeline import ebook_project_readiness

        data = {
            "product_type": "ebook",
            "title": "Test",
            "content": "# T\n\n## Chapter One\n\n" + ("Useful guidance. " * 40),
            "cover_design": {
                "workflow": "photo_backed",
                "selected_layout": "full_bleed_editorial",
                "source": {"sha256": "abc"},
                "image_path": str(ROOT / "services" / "ebook_fonts.py"),
            },
            "visual_plan": {"chapters": []},
            "ebook_pdf_qa_passed": False,
            "ebook_pdf_qa_errors": ["Cover photograph has a white perimeter instead of full bleed."],
        }
        state = ebook_project_readiness(data)
        self.assertFalse(state["ebook_ready"])
        self.assertFalse(state["export_ready"])
        self.assertTrue(any("PDF quality" in b for b in state["completion_blockers"]))

    def test_17_zip_pdf_identity_helper_customer_files_only(self):
        src = (ROOT / "services" / "ebook_customer_path.py").read_text(encoding="utf-8")
        self.assertIn('customer_names = {"ebook.pdf"', src)
        self.assertIn("ebook.html", src)

    def test_20_heading_css_requests_bold_family(self):
        from services import pdf_export

        self.assertIn("EbookSans-Bold", pdf_export._PDF_CSS)
        self.assertRegex(
            pdf_export._PDF_CSS,
            r"\.chapter-title[^}]*font-weight:\s*bold",
        )

    def test_21_short_chapter_tail_kept_together(self):
        from bs4 import BeautifulSoup
        from services.pdf_export import _keep_short_chapter_tails

        paras = "".join(
            f"<p>Paragraph {i} about pots, drainage holes, and potting mix for beginners.</p>"
            for i in range(6)
        )
        html = (
            '<section class="pdf-page chapter-page">'
            "<h2>Choosing the Right Containers and Soil</h2>"
            "<h3>Filling Containers the Right Way</h3>"
            f"{paras}"
            "<p>When you match the pot size to the plant, you remove several common beginner problems before they start.</p>"
            "</section>"
        )
        soup = BeautifulSoup(html, "html.parser")
        _keep_short_chapter_tails(soup)
        tail = soup.select_one("table.pdf-chapter-tail")
        self.assertIsNotNone(tail)
        text = tail.get_text(" ", strip=True)
        self.assertIn("When you match the pot size", text)
        self.assertIn("Filling Containers the Right Way", text)

    def test_22_headings_render_bold_face(self):
        import fitz
        from services.pdf_export import _html_to_pdf_xhtml2pdf, _wrap_pdf_document

        html = _wrap_pdf_document(
            "Font Gate",
            '<section class="pdf-page chapter-page">'
            '<h2 class="chapter-title">Choosing the Right Containers</h2>'
            "<p>Container gardening keeps soil in a pot with drainage holes.</p>"
            "</section>",
        )
        pdf = _html_to_pdf_xhtml2pdf(html)
        doc = fitz.open(stream=pdf, filetype="pdf")
        heading_fonts = set()
        for page in doc:
            for block in page.get_text("dict").get("blocks") or []:
                for line in block.get("lines") or []:
                    for span in line.get("spans") or []:
                        if float(span.get("size") or 0) >= 18:
                            heading_fonts.add(str(span.get("font") or ""))
        doc.close()
        self.assertTrue(heading_fonts, "no heading spans")
        joined = " ".join(heading_fonts)
        self.assertTrue(
            any(token in joined for token in ("Bold", "EbookSans-Bold")),
            f"expected bold heading face, got {heading_fonts}",
        )


if __name__ == "__main__":
    unittest.main()
