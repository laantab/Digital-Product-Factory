"""The PDF QA gate must actually read PDFs and catch raw markdown leaks.

Root cause (found while shipping project 20090): the QA extractor tried
pdfplumber and PyPDF2 — neither installed — then crashed in its bytes/str
regex fallback, so every validate_ebook_pdf() call returned page_count=0 /
"Could not parse PDF". Callers treat QA as non-blocking logging, so the whole
PDF quality gate had been silently dead. The extractor now uses PyMuPDF (the
pinned production dependency) first, and the raw-bracket check also flags
markdown link syntax that once shipped on a customer title page.
"""

import fitz

from services.ebook_qa_validator import validate_ebook_pdf


def _make_pdf(pages: list[str]) -> bytes:
    doc = fitz.open()
    for body in pages:
        page = doc.new_page()
        page.insert_text((72, 100), body, fontsize=11)
    return doc.tobytes()


class TestQaExtractorReadsRealPdfs:
    def test_page_count_and_text_are_extracted(self):
        pdf = _make_pdf(["Alpha page one text.", "Beta page two text.", "Gamma page three."])
        result = validate_ebook_pdf(pdf)
        assert result.page_count == 3
        assert not any("Could not parse PDF" in e for e in result.errors)

    def test_garbage_bytes_do_not_raise(self):
        result = validate_ebook_pdf(b"this is not a pdf at all")
        assert result.page_count == 0  # graceful, not crashed


class TestRawMarkdownDetection:
    def test_markdown_anchor_links_fail_qa(self):
        pdf = _make_pdf([
            "Beginner's Guide",
            "1. [Getting Started](#getting-started) 2. [Choosing Soil](#choosing-soil)",
        ])
        result = validate_ebook_pdf(pdf)
        assert not result.passed
        assert any("Raw bracket tag" in e for e in result.errors)

    def test_clean_prose_passes_markdown_check(self):
        pdf = _make_pdf([
            "Beginner's Guide",
            "Container gardening is one of the easiest ways to grow food at home.",
        ])
        result = validate_ebook_pdf(pdf)
        assert not any("Raw bracket tag" in e for e in result.errors)
