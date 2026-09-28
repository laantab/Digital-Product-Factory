"""v1.9.13: every page number the Factory prints meets one print standard.

Checked on the rendered PDF, never on CSS or source strings: in 1.9.12 the
stylesheet asked for a darker number and xhtml2pdf ignored it, so only the
printed result is evidence.

For every path that prints page numbers (designed ebooks in all six templates,
planners in all six themes, coloring books, math worksheets, spelling
worksheets and Publishing Studio PDFs) this checks that each number is:

* about 10 pt (9.5-10.5 pt) at 100% scale, which is its size on paper,
* set in a bold face,
* near-black (relative luminance at most 0.2),
* inside the page, clear of the edge, and not overlapping any other text,
  picture or caption,

and that the page size and the numbering sequence are exactly what each
product already printed.
"""
from __future__ import annotations

import re
import unittest

import fitz

from services.page_number_style import (
    MAX_PAGE_NUMBER_LUMINANCE,
    PAGE_NUMBER_SIZE_PT,
    luminance,
)

LETTER = (612.0, 792.0)
EBOOK_THEMES = [
    "studio_clean", "editorial_professional", "bold_creator",
    "bright_workbook", "modern_practical", "warm_wellness",
]
TITLE = "Container Gardening for Beginners"


def _spans(page):
    return [
        s for b in page.get_text("dict")["blocks"] for ln in b.get("lines", [])
        for s in ln["spans"] if s["text"].strip()
    ]


def _is_number(text: str) -> bool:
    t = text.strip()
    return bool(re.fullmatch(r"\(?page \d+ of \d+\)?", t, re.I) or re.fullmatch(r"\d{1,3}", t))


def _page_numbers(page, *, edge_pt: float = 72.0):
    """Page-number spans: digits, "Page N of M" or "(page N of M)" in the top or bottom band."""
    h = page.rect.height
    return [
        s for s in _spans(page)
        if (s["bbox"][1] > h - edge_pt or s["bbox"][3] < edge_pt) and _is_number(s["text"])
    ]


def _overlaps(a, b) -> bool:
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


class _Checks(unittest.TestCase):
    def assert_print_standard(self, pdf_bytes: bytes, *, label: str, expect_pages=None,
                              page_size=LETTER, edge_pt: float = 72.0, min_numbers: int = 1):
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if expect_pages is not None:
            self.assertEqual(len(doc), expect_pages, f"{label}: page count changed")
        seen = 0
        for pno, page in enumerate(doc):
            self.assertEqual((round(page.rect.width, 2), round(page.rect.height, 2)),
                             (round(page_size[0], 2), round(page_size[1], 2)),
                             f"{label}: page {pno + 1} size changed")
            others = _spans(page)
            pictures = [fitz.Rect(i["bbox"]) for i in page.get_image_info()
                        if fitz.Rect(i["bbox"]).width < page.rect.width * 0.95]
            for num in _page_numbers(page, edge_pt=edge_pt):
                seen += 1
                where = f"{label}: page {pno + 1} number {num['text']!r}"
                self.assertGreaterEqual(num["size"], PAGE_NUMBER_SIZE_PT - 0.5, where)
                self.assertLessEqual(num["size"], PAGE_NUMBER_SIZE_PT + 0.5, where)
                self.assertIn("bold", num["font"].lower(), where)
                self.assertLessEqual(luminance(f"#{num['color']:06x}"), MAX_PAGE_NUMBER_LUMINANCE,
                                     f"{where} colour #{num['color']:06x}")
                # Inside the page and clear of the trim edge (digits sit on the baseline).
                self.assertGreater(num["bbox"][1], 18, where)
                self.assertLess(num["origin"][1], page.rect.height - 18, where)
                for other in others:
                    if other is num or other["bbox"] == num["bbox"]:
                        continue
                    same_line = abs(other["origin"][1] - num["origin"][1]) < 1.0
                    if same_line and other["bbox"][2] <= num["bbox"][0] + 0.5:
                        continue            # the running title / label that leads into the number
                    self.assertFalse(_overlaps(num["bbox"], other["bbox"]),
                                     f"{where} overlaps {other['text'][:40]!r}")
                for pic in pictures:
                    self.assertFalse(_overlaps(num["bbox"], tuple(pic)), f"{where} overlaps a picture")
        self.assertGreaterEqual(seen, min_numbers, f"{label}: no page numbers printed")
        return doc


class DesignedEbookAllSixTemplates(_Checks):
    """The running footer of a designed ebook, in each of the six templates."""

    def _render(self, theme_id):
        from services.ebook_book_layout import render_designed_ebook_html
        from services.ebook_design_export import _html_to_pdf
        from services.ebook_design_spec import EbookDesign

        para = "Container gardening lets you grow food in small spaces. " * 30
        md = f"# {TITLE}\n\n" + "".join(
            f"## Chapter {i}: Topic {i}\n\n" + (para + "\n\n") * 6 for i in range(1, 4))
        html = render_designed_ebook_html(
            title=TITLE, subtitle="", author="Lonnie Brown", manuscript_md=md,
            design=EbookDesign(theme_id=theme_id), include_title_page=False)
        return _html_to_pdf(html, title=TITLE, author="Lonnie Brown", subtitle="")

    def test_every_template_prints_the_standard_number_on_every_page_in_order(self):
        for theme_id in EBOOK_THEMES:
            with self.subTest(theme=theme_id):
                doc = self.assert_print_standard(self._render(theme_id), label=theme_id)
                # Numbering rule unchanged: every interior page is numbered, 1..N.
                numbers = [int(_page_numbers(p)[-1]["text"]) for p in doc]
                self.assertEqual(numbers, list(range(1, len(doc) + 1)), theme_id)


class PlannerAllSixThemes(_Checks):
    def test_every_theme_and_page_size(self):
        from services.planner.builder import BUDGET, FAITH, PlannerRequest, build_planner_plan
        from services.planner.renderer import PAGE_SIZES, build_planner_pdf_bytes
        from services.planner.themes import SPACING, THEMES

        for key in THEMES:
            for size_name in ("US Letter", "A4", "6x9"):
                with self.subTest(theme=key, size=size_name):
                    ptype = BUDGET if key == "ledger" else FAITH
                    plan = build_planner_plan(PlannerRequest(
                        planner_type=ptype, title="Test Planner", pages=12, seed=7,
                        design_theme=key, page_size=size_name))
                    pdf, _info = build_planner_pdf_bytes(plan, page_size=size_name, theme=key)
                    # Only the footer band: tables run close to it (a week "52"
                    # cell is a table entry, not a page number).
                    self.assert_print_standard(pdf, label=f"planner {key} {size_name}",
                                               page_size=PAGE_SIZES[size_name.lower()],
                                               edge_pt=SPACING.footer_h + 8)


class ColoringBookPageNumbers(_Checks):
    def _book(self, caption: str):
        from services.coloring_book.builder import ColoringBookResult, ColoringPageResult

        pages = [ColoringPageResult(page_number=i, topic=f"Happy Turtle {i}",
                                    line_art_prompt="a happy turtle, simple line art",
                                    caption=caption) for i in range(1, 6)]
        return ColoringBookResult(product_title="Sea Friends", subtitle="", pages=pages)

    def test_book_mode_numbers_with_and_without_captions(self):
        from services.coloring_book.renderer import build_coloring_book_pdf_bytes

        for caption in ("", "Color the happy turtle swimming in the sea"):
            with self.subTest(caption=bool(caption)):
                pdf, _ = build_coloring_book_pdf_bytes(self._book(caption))
                doc = self.assert_print_standard(pdf, label=f"coloring caption={bool(caption)}",
                                                 min_numbers=5)
                printed = [s["text"].strip() for p in doc for s in _page_numbers(p)]
                self.assertEqual(printed, [str(i) for i in range(1, 6)])

    def test_single_sheet_still_has_no_page_number(self):
        from services.coloring_book.renderer import build_coloring_book_pdf_bytes

        pdf, _ = build_coloring_book_pdf_bytes(self._book(""), single_sheet=True)
        doc = fitz.open(stream=pdf, filetype="pdf")
        self.assertEqual([s["text"] for p in doc for s in _page_numbers(p)], [])


class WorksheetPageCounters(_Checks):
    def test_math_worksheet_counter_including_a_very_long_title(self):
        from services.math_worksheet.builder import build_math_worksheet
        from services.math_worksheet.renderer import build_math_worksheet_pdf_bytes

        for title in ("Math Worksheet",
                      "Addition and Subtraction Practice for Busy Third Graders Weekly Review"):
            with self.subTest(title=title):
                ws = build_math_worksheet(worksheet_title=title, grade="3", problem_count=40)
                pdf, _ = build_math_worksheet_pdf_bytes(ws, include_answer_key=True)
                doc = self.assert_print_standard(pdf, label=f"math {title[:20]}")
                counters = [s["text"] for p in doc for s in _page_numbers(p)]
                self.assertTrue(all(c.startswith("Page ") for c in counters), counters)

    def test_spelling_worksheet_counter_on_multi_page_sections(self):
        from services.spelling_worksheet.builder import build_spelling_worksheet
        from services.spelling_worksheet.renderer import build_spelling_worksheet_pdf_bytes

        ws = build_spelling_worksheet(theme="ocean animals", grade="3", word_count=40)
        pdf, _ = build_spelling_worksheet_pdf_bytes(ws, include_answer_key=True)
        doc = fitz.open(stream=pdf, filetype="pdf")
        # 40 words always need more than one page per section, so the counter
        # must be there; its absence is a failure, never a skip.
        self.assertTrue(any(_page_numbers(p) for p in doc), "no page counter printed")
        self.assert_print_standard(pdf, label="spelling")


class PublishingStudioPdf(_Checks):
    def test_every_publishing_template(self):
        from services import publishing as P
        from services.pdf_export import _html_to_pdf_xhtml2pdf, build_pdf_html

        para = "Container gardening lets you grow food in small spaces. " * 12
        book = {"title": TITLE, "subtitle": "A guide", "summary": "Short.", "key_takeaways": ["One"],
                "chapters": [{"title": f"Chapter {i}", "paragraphs": [para, para],
                              "tip": "Water early.", "action_steps": ["Pick a pot."]} for i in (1, 2)]}
        project = {"name": TITLE, "type": "ebook", "data": {"title": TITLE, "content": f"# {TITLE}\n\nText."}}
        for key in P.TEMPLATES:
            with self.subTest(template=key):
                details = P._clean_details({"author_brand": "Lonnie Brown"}, P.default_details(project))
                html = P._render_html(book, key, details, [], {}, "")
                doc_html = build_pdf_html(doc_html=html, title=TITLE, template_key=key,
                                          preview_source="publishing")
                pdf = _html_to_pdf_xhtml2pdf(doc_html)
                # The Studio prints its number at the end of each section, not in
                # a fixed footer band, so every digit-only span is checked.
                self.assert_print_standard(pdf, label=f"publishing {key}", edge_pt=10_000)


if __name__ == "__main__":
    unittest.main()
