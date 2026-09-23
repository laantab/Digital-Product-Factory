"""v1.9.0 -- six templates that are different books, not six palettes.

Through 1.8.x the six themes shared one CSS skeleton: they differed in colour,
chapter opener and table of contents, but a callout, a checklist, a quotation,
a caption, a picture, a table and the page furniture looked the same in all
six. A customer choosing a template could not see what they were choosing.

These tests hold the line on four things: every template declares a complete
structure; no two are near-copies; the structure really reaches the CSS the
book is rendered with; and a theme that declares nothing still renders exactly
as it did before.
"""
from __future__ import annotations

import itertools

import pytest

from services.ebook_design_system import (
    PROFESSIONAL_THEME_IDS,
    THEMES,
    EbookTheme,
    _template_structure_css,
    get_theme,
    list_professional_themes,
    recommend_theme,
    theme_css,
    theme_sample_html,
)

#: Everything that makes two templates different on the page.
STRUCTURAL_FIELDS = (
    "heading_style", "callout_style", "checklist_style", "quote_style",
    "caption_style", "image_style", "table_style", "page_furniture",
    "chapter_opener", "toc_style",
)
MIN_DIFFERENCES = 8


def test_there_are_six_templates():
    assert len(PROFESSIONAL_THEME_IDS) == 6
    assert len(set(PROFESSIONAL_THEME_IDS)) == 6


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_every_template_declares_a_complete_structure(theme_id):
    t = THEMES[theme_id]
    for field in STRUCTURAL_FIELDS:
        value = str(getattr(t, field) or "")
        assert value, f"{theme_id}: {field} is empty"
    # A template may fall back to the classic treatment for at most two parts;
    # more than that and it is not really a design of its own.
    classic = [f for f in STRUCTURAL_FIELDS if str(getattr(t, f)) in ("classic", "plain")]
    assert len(classic) <= 2, f"{theme_id} leaves too much undesigned: {classic}"


@pytest.mark.parametrize("a,b", list(itertools.combinations(PROFESSIONAL_THEME_IDS, 2)))
def test_no_two_templates_are_near_copies(a, b):
    ta, tb = THEMES[a], THEMES[b]
    differences = [f for f in STRUCTURAL_FIELDS if getattr(ta, f) != getattr(tb, f)]
    assert len(differences) >= MIN_DIFFERENCES, (
        f"{a} and {b} differ in only {len(differences)} of "
        f"{len(STRUCTURAL_FIELDS)} structural parts: {differences}"
    )


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_the_structure_reaches_the_rendered_css(theme_id):
    css = theme_css(theme_id)
    assert "template structure (v1.9.0)" in css
    # the parts a reader actually sees
    for selector in (".callout", ".checklist", "blockquote", "figcaption",
                     ".ebook-figure", "table", ".foot-"):
        assert selector in css, f"{theme_id}: {selector} never styled"


def test_two_templates_do_not_produce_the_same_stylesheet():
    sheets = {tid: theme_css(tid) for tid in PROFESSIONAL_THEME_IDS}
    assert len(set(sheets.values())) == 6


def test_a_template_that_declares_nothing_is_untouched():
    """Backward compatibility: the 1.8.x look is the default, not a special case."""
    plain = EbookTheme(
        theme_id="plain_test", version="1", display_name="Plain",
        font_body="LiberationSerif", font_heading="LiberationSerif",
        color_primary="#1f2937", color_accent="#2563eb", color_text="#111827",
        color_muted="#6b7280", color_rule="#d1d5db", body_size_pt=11.0,
        line_height=1.5, h1_size_pt=26.0, h2_size_pt=18.0, h3_size_pt=13.0,
        margin_in=0.8, paragraph_spacing_em=0.6, chapter_opener="minimal",
        table_header_bg="#f3f4f6", callout_bg="#f9fafb",
    )
    assert _template_structure_css(plain) == ""


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_the_chooser_card_speaks_plain_language(theme_id):
    card = {c["theme_id"]: c for c in list_professional_themes()}[theme_id]
    assert card["display_name"] and not card["display_name"].islower()
    text = f"{card.get('summary') or ''} {card.get('best_for') or ''}".strip()
    assert len(text) > 20, f"{theme_id}: nothing a beginner could read"
    assert theme_id not in text, f"{theme_id}: internal id leaked onto the card"
    for jargon in ("css", "px", "pt ", "theme_id", "font-family", "render"):
        assert jargon not in text.lower(), f"{theme_id}: jargon on the card: {jargon}"


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_the_preview_shows_every_part_a_template_changes(theme_id):
    html = theme_sample_html(theme_id)
    for part in ("chapter-opener-block", "checklist", "callout", "blockquote",
                 "ebook-figure", "figcaption", "<table", "caption"):
        assert part in html, f"{theme_id}: preview hides {part}"
    # Nothing is fetched: the only URL in the page is the SVG namespace, which
    # is an identifier, not an address the renderer visits.
    assert 'src="http' not in html and "url(http" not in html
    assert 'href="http' not in html


def test_the_factory_can_suggest_a_template_without_forcing_one():
    suggested = recommend_theme(topic="Container gardening for beginners", title="", audience="adults")
    assert suggested in PROFESSIONAL_THEME_IDS
    assert recommend_theme(topic="", title="", audience="") in PROFESSIONAL_THEME_IDS


def test_a_saved_book_keeps_resolving_its_template():
    for theme_id in PROFESSIONAL_THEME_IDS:
        assert get_theme(theme_id).theme_id == theme_id
    # retired id from earlier releases still resolves, and never crashes
    assert get_theme("ink_editorial").theme_id == "editorial_professional"
    assert get_theme("").theme_id in PROFESSIONAL_THEME_IDS
    assert get_theme(None).theme_id in PROFESSIONAL_THEME_IDS


def test_no_template_uses_letter_spacing_which_the_pdf_engine_drops():
    for theme_id in PROFESSIONAL_THEME_IDS:
        assert "letter-spacing" not in theme_css(theme_id)
