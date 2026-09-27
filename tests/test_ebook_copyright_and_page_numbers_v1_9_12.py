"""v1.9.12: a tight copyright page and larger, near-black page numbers.

Checked on the rendered PDF, not the CSS: xhtml2pdf 0.2.17 ignored the CSS
that asked for a darker number, so only the printed result proves it.
"""
import io
import unittest

from services.ebook_book_layout import render_designed_ebook_html
from services.ebook_design_spec import EbookDesign
from services.ebook_design_system import PAGE_NUMBER_SIZE_PT, get_theme
from services.ebook_design_export import _html_to_pdf

THEMES = [
    "studio_clean", "editorial_professional", "bold_creator",
    "bright_workbook", "modern_practical", "warm_wellness",
]
TITLE = "Container Gardening for Beginners"
PARA = "Container gardening lets you grow food in small spaces. " * 30
MD = f"# {TITLE}\n\n" + "".join(f"## Chapter {i}: Topic {i}\n\n{PARA}\n\n{PARA}\n\n" for i in range(1, 3))


def _luminance(rgb_int: int) -> float:
    r, g, b = (rgb_int >> 16) & 255, (rgb_int >> 8) & 255, rgb_int & 255
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255


class CopyrightAndPageNumbers(unittest.TestCase):
    def _render(self, theme_id):
        html = render_designed_ebook_html(
            title=TITLE, subtitle="", author="Lonnie Brown", manuscript_md=MD,
            design=EbookDesign(theme_id=theme_id), include_title_page=False,
        )
        return html, _html_to_pdf(html, title=TITLE, author="Lonnie Brown", subtitle="")

    def test_copyright_block_is_conventional_and_tight(self):
        html, _ = self._render("studio_clean")
        self.assertIn('class="legal-page"', html)
        self.assertIn("Copyright &#169;", html)
        self.assertIn("Lonnie Brown. All rights reserved.", html)
        self.assertNotIn("Title: ", html)

    def test_page_number_is_larger_and_near_black_on_every_template(self):
        import fitz
        for theme_id in THEMES:
            with self.subTest(theme=theme_id):
                _, pdf = self._render(theme_id)
                doc = fitz.open(stream=pdf, filetype="pdf")
                page = doc[2]
                spans = [
                    sp for bl in page.get_text("dict")["blocks"] for ln in bl.get("lines", [])
                    for sp in ln["spans"] if sp["bbox"][1] > 700 and sp["text"].strip().isdigit()
                ]
                self.assertTrue(spans, "no page number printed")
                num = spans[-1]
                self.assertGreaterEqual(round(num["size"], 1), PAGE_NUMBER_SIZE_PT)
                self.assertLess(_luminance(num["color"]), 0.2, hex(num["color"]))
                footer_size = get_theme(theme_id).footer_size_pt
                self.assertGreater(num["size"], footer_size)


if __name__ == "__main__":
    unittest.main()
