"""Product summaries must never leak raw markdown TOC links into customer output.

Root cause (project 20090): the fallback summary derivation took the manuscript's
first paragraph, which for generated ebooks is the markdown table of contents,
then truncated it mid-word at 400 chars. That block was printed verbatim on the
PDF title page and again on a trailing Summary page.

These tests cover the reusable repairs:
  - clean_product_summary(): render-time cleaning so already-polluted saved
    projects heal without record rewrites;
  - derive_product_summary(): prose-aware fallback derivation;
  - build_pdf_html() / render_preview_html(): no raw markdown links reach the
    customer-facing documents even when the stored summary is polluted.
"""

from services.ebook_package import (
    clean_product_summary,
    derive_product_summary,
    render_preview_html,
)
from services.pdf_export import build_pdf_html

# Mirrors the exact stored pollution found in project 20090, including the
# 400-char truncation cutting the last anchor mid-word.
POLLUTED_SUMMARY = (
    "1. [Getting Started With Container Gardening](#getting-started-with-container-gardening)\n"
    "2. [Choosing the Right Containers and Soil](#choosing-the-right-containers-and-soil)\n"
    "3. [Picking Vegetables and Herbs That Grow Well in Pots](#picking-vegetables-and-herbs-that-grow-well-in-pots)\n"
    "4. [Water, Sun, and Daily Care](#water-sun-and-daily-care)\n"
    "5. [Handling Pests and Plant Problems](#handling-pests-a"
)

MANUSCRIPT_WITH_LEADING_TOC = (
    "# Beginner's Guide to Container Gardening\n\n"
    "1. [Getting Started](#getting-started)\n"
    "2. [Choosing Containers](#choosing-containers)\n\n"
    "## Getting Started\n\n"
    "Container gardening is one of the easiest ways to grow food at home. "
    "You do not need a large yard. You can grow herbs on a porch or balcony.\n\n"
    "More prose follows here.\n"
)


class TestCleanProductSummary:
    def test_pure_toc_pollution_becomes_empty(self):
        assert clean_product_summary(POLLUTED_SUMMARY) == ""

    def test_plain_prose_passes_through_unchanged(self):
        prose = "A practical handbook for growing vegetables in pots."
        assert clean_product_summary(prose) == prose

    def test_inline_markdown_link_reduced_to_text(self):
        cleaned = clean_product_summary("Learn more in [Chapter 2](#ch2) today.")
        assert cleaned == "Learn more in Chapter 2 today."
        assert "](" not in cleaned

    def test_truncated_link_without_closing_paren_is_removed(self):
        cleaned = clean_product_summary("See [Handling Pests](#handling-pests-a")
        assert "](#" not in cleaned

    def test_empty_and_none_are_safe(self):
        assert clean_product_summary("") == ""
        assert clean_product_summary(None) == ""


class TestDeriveProductSummary:
    def test_skips_leading_markdown_toc_and_headings(self):
        derived = derive_product_summary(MANUSCRIPT_WITH_LEADING_TOC)
        assert derived.startswith("Container gardening is one of the easiest ways")
        assert "](#" not in derived

    def test_cuts_on_sentence_boundary_not_mid_word(self):
        long_prose = ("This is a full sentence about gardening that ends cleanly. " * 20).strip()
        derived = derive_product_summary("# Title\n\n" + long_prose)
        assert len(derived) <= 400
        assert derived.endswith(".")

    def test_empty_manuscript_yields_empty(self):
        assert derive_product_summary("") == ""


class TestRenderersRejectPollutedSummaries:
    def test_build_pdf_html_never_prints_raw_toc_links(self):
        html = build_pdf_html(
            doc_html="",
            title="Beginner's Guide to Container Gardening",
            subtitle="A practical guide",
            author="Lonnie Brown",
            content="",
            summary=POLLUTED_SUMMARY,
        )
        assert "](#" not in html
        assert "[Getting Started" not in html

    def test_build_pdf_html_keeps_clean_summaries(self):
        html = build_pdf_html(
            doc_html="",
            title="T",
            subtitle="S",
            author="A",
            content="",
            summary="A practical handbook for growing vegetables in pots.",
        )
        assert "A practical handbook for growing vegetables in pots." in html

    def test_render_preview_html_never_prints_raw_toc_links(self):
        html = render_preview_html(
            "Beginner's Guide to Container Gardening",
            "A practical guide",
            "## Chapter One\n\nSome prose about gardening.",
            [],
            "pkg-test-summary-hygiene",
            POLLUTED_SUMMARY,
            None,
        )
        assert "](#" not in html
        assert "[Getting Started" not in html
