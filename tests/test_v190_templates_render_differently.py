"""v1.9.0 -- the templates are judged on the page, not in the stylesheet.

The first version of this gate asserted on CSS strings, passed in 0.13s, and
was wrong: three of the ten declared dimensions drew nothing at all in the
PDF, two templates printed type at 2.1:1 contrast, and one printed an
illegible page number on every page. CSS that the renderer ignores is not a
design. Every test here renders a real book with the real engine and looks at
what was actually drawn.
"""
from __future__ import annotations

import itertools

import pytest

fitz = pytest.importorskip("fitz")

from services.ebook_book_layout import render_designed_ebook_html
from services.ebook_design_spec import EbookDesign
from services.ebook_design_system import (
    PROFESSIONAL_THEME_IDS,
    THEMES,
    contrast_ratio,
)
from services.pdf_export import _html_to_pdf_xhtml2pdf

#: A real picture on disk, placed through the real visual plan, so the sample
#: book genuinely contains an illustration. Markdown images are stripped by
#: the pipeline -- pictures reach a book only this way -- and a test about how
#: pictures are framed passes for free if the book has none.
def _picture_plan(tmp: str) -> dict:
    import os

    from PIL import Image

    path = os.path.join(tmp, "figure.png")
    if not os.path.isfile(path):
        # Tall on purpose: a height-capped photograph renders narrower than
        # the text column, which is the only shape in which an empty frame
        # around the figure box is visible. A column-width picture hides it.
        Image.new("RGB", (300, 900), (120, 140, 130)).save(path)
    return {
        "chapters": [
            {
                "chapter_index": 1,
                "chapter": "First chapter",
                "aids": [
                    {
                        "visual_id": "v_ch1",
                        "type": "photograph",
                        "asset_path": path,
                        "caption": "How this template places and captions a picture.",
                        "match_status": "pass",
                    }
                ],
            }
        ]
    }


SAMPLE = """## 1. First chapter

An opening paragraph so the chapter has body text above its first section.

### A section heading

- [ ] Checklist item one
- [ ] Checklist item two
- [ ] Checklist item three

1. Numbered workflow step one
2. Numbered workflow step two
3. Numbered workflow step three

> A short quotation, styled the way this template treats quotations.

| Item | Notes |
| --- | --- |
| Row one | Styled table row |
| Row two | Second row here |
"""


def _render(theme_id: str, tmp: str) -> bytes:
    design = EbookDesign.from_dict({"theme_id": theme_id, "manuscript_digest": "v190"})
    html = render_designed_ebook_html(
        title="Rendered Template Test", subtitle="Sub", author="Author",
        manuscript_md=SAMPLE, design=design, include_title_page=False,
        visual_plan=_picture_plan(tmp),
    )
    return _html_to_pdf_xhtml2pdf(html)


@pytest.fixture(scope="module")
def books(tmp_path_factory) -> dict[str, bytes]:
    tmp = str(tmp_path_factory.mktemp("v190"))
    rendered = {tid: _render(tid, tmp) for tid in PROFESSIONAL_THEME_IDS}
    for tid, pdf in rendered.items():
        doc = fitz.open(stream=pdf, filetype="pdf")
        pictures = sum(len(page.get_image_info(xrefs=False)) for page in doc)
        assert pictures >= 1, f"{tid}: the sample book has no picture, so picture tests prove nothing"
    return rendered


def _ink(pdf: bytes) -> dict:
    doc = fitz.open(stream=pdf, filetype="pdf")
    fills, strokes, spans, text = [], [], [], []
    for number, page in enumerate(doc):
        for d in page.get_drawings():
            if d.get("fill") is not None:
                fills.append((tuple(round(c, 3) for c in d["fill"]), tuple(round(v) for v in d["rect"]), number))
            if d.get("color") is not None:
                strokes.append((tuple(round(c, 3) for c in d["color"]), tuple(round(v) for v in d["rect"]), number))
        raw = page.get_text("dict")
        for block in raw.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    if span.get("text", "").strip():
                        spans.append({**span, "page": number})
        text.append(page.get_text())
    return {"fills": fills, "strokes": strokes, "spans": spans,
            "text": "\n".join(text), "pages": len(doc)}


def _rgb_hex(value: int | float | tuple) -> str:
    if isinstance(value, (tuple, list)):
        r, g, b = (int(round(c * 255)) for c in value[:3])
    else:
        v = int(value)
        r, g, b = (v >> 16) & 255, (v >> 8) & 255, v & 255
    return f"#{r:02x}{g:02x}{b:02x}"


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_a_book_renders_and_carries_its_furniture(theme_id, books):
    ink = _ink(books[theme_id])
    assert ink["pages"] >= 2
    assert "First chapter" in ink["text"]
    # One marker per row, and it is the list item's own: this renderer draws a
    # bullet or numeral on a list item whatever the CSS says, so anything the
    # Factory adds becomes a second marker on the page.
    assert "Checklist item one" in ink["text"], "a checklist row went missing"
    assert "Numbered workflow step one" in ink["text"], "a procedure step went missing"


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_every_book_draws_a_visible_table(theme_id, books):
    """A table must have visible structure: ruled cells, or a filled header.

    Three treatments used to draw neither, so two books printed what looked
    like loose columns of text.
    """
    ink = _ink(books[theme_id])
    ruled = len(ink["strokes"]) >= 10
    wide_fills = [f for f in ink["fills"] if (f[1][2] - f[1][0]) > 300 and (f[1][3] - f[1][1]) < 40]
    assert ruled or wide_fills, (
        f"{theme_id}: no ruled cells and no header band -- the table has no visible structure"
    )


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_no_text_is_printed_too_small_to_read(theme_id, books):
    floor = THEMES[theme_id].min_font_pt - 0.01
    small = [(s["size"], s["text"][:30]) for s in _ink(books[theme_id])["spans"] if s["size"] < floor]
    assert not small, f"{theme_id}: text below {floor}pt: {small[:3]}"


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_every_word_can_be_read_against_what_is_painted_behind_it(theme_id, books):
    """Two templates shipped white type on a mid-tone fill at ~2.1:1."""
    ink = _ink(books[theme_id])
    failures = []
    for span in ink["spans"]:
        ink_hex = _rgb_hex(span.get("color", 0))
        sx0, sy0, sx1, sy1 = span["bbox"]
        behind = "#ffffff"
        for fill, rect, page_number in ink["fills"]:
            if page_number != span["page"]:
                continue          # a fill on another page is not behind this word
            fx0, fy0, fx1, fy1 = rect
            if fx0 <= sx0 and fy0 <= sy0 and fx1 >= sx1 and fy1 >= sy1:
                behind = _rgb_hex(fill)
        ratio = contrast_ratio(ink_hex, behind)
        needed = 3.0 if span["size"] >= 14 else 4.5
        if ratio < needed:
            failures.append((span["text"][:24], ink_hex, behind, round(ratio, 2), needed))
    assert not failures, f"{theme_id}: unreadable text: {failures[:4]}"


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_nothing_is_printed_over_the_running_footer(theme_id, books):
    """A tinted checklist used to print across the footer rule and page number."""
    doc = fitz.open(stream=books[theme_id], filetype="pdf")
    for i, page in enumerate(doc):
        footer_top = page.rect.height - 40
        for d in page.get_drawings():
            if d.get("fill") is None:
                continue
            r = d["rect"]
            if r.y1 > footer_top and r.y0 < footer_top and r.width > 200:
                raise AssertionError(f"{theme_id}: page {i + 1} paints {r} across the footer band")


def _signature(pdf: bytes) -> tuple:
    ink = _ink(pdf)
    fills = sorted({f[0] for f in ink["fills"]})
    sizes = sorted({round(s["size"], 1) for s in ink["spans"]})
    colours = sorted({_rgb_hex(s.get("color", 0)) for s in ink["spans"]})
    return (tuple(fills), tuple(sizes), tuple(colours), len(ink["strokes"]))


@pytest.mark.parametrize("a,b", list(itertools.combinations(PROFESSIONAL_THEME_IDS, 2)))
def test_two_books_never_come_out_looking_the_same(a, b, books):
    sig_a, sig_b = _signature(books[a]), _signature(books[b])
    differing = sum(1 for x, y in zip(sig_a, sig_b) if x != y)
    assert differing >= 3, (
        f"{a} and {b} render nearly identically: only {differing} of 4 ink "
        f"characteristics differ"
    )


def test_every_template_paints_something_of_its_own(books):
    """No two books share their exact set of painted colours."""
    palettes = {tid: tuple(sorted({f[0] for f in _ink(pdf)["fills"]})) for tid, pdf in books.items()}
    assert len(set(palettes.values())) == len(PROFESSIONAL_THEME_IDS)

# --- the blind spots that let real defects through an earlier gate ---------


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_no_row_carries_two_markers(theme_id, books):
    """"• [ ] item" and "1. 1. step" both shipped past a green gate once."""
    text = _ink(books[theme_id])["text"]
    for bad in ("\u2022 [ ]", "\u2022 1.", "1. 1.", "2. 2.", "3. 3.", "[ ] [ ]", "[ ] Checklist"):
        assert bad not in text, f"{theme_id}: doubled marker {bad!r} on the page"


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_nothing_is_drawn_across_the_running_footer(theme_id, books):
    """Strokes too: a 2pt rule under a checklist row struck through the page number."""
    doc = fitz.open(stream=books[theme_id], filetype="pdf")
    for i, page in enumerate(doc):
        band_top = page.rect.height - 40
        for d in page.get_drawings():
            r = d["rect"]
            if r.width > 150 and r.y1 > band_top and r.y0 < band_top:
                raise AssertionError(
                    f"{theme_id}: page {i + 1} draws {d.get('type')} {r} through the footer band"
                )


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_every_rule_belongs_to_the_template(theme_id, books):
    """A black grid in a teal book is not that book's design."""
    theme = THEMES[theme_id]
    allowed = {
        theme.color_rule.lower(), theme.color_primary.lower(), theme.color_accent.lower(),
        (theme.color_accent_2 or theme.color_accent).lower(), theme.color_muted.lower(),
        theme.color_text.lower(), "#ffffff",
    }
    strays: list[str] = []
    for colour, rect, _page in _ink(books[theme_id])["strokes"]:
        hexed = _rgb_hex(colour).lower()
        if hexed in allowed:
            continue
        # a rule may be drawn slightly off by colour conversion; allow near hits
        if min(contrast_ratio(hexed, a) for a in allowed) < 1.15:
            continue
        strays.append(hexed)
    assert not strays, f"{theme_id}: rules drawn in colours the template never declared: {sorted(set(strays))[:5]}"


@pytest.mark.parametrize("a,b", list(itertools.combinations(PROFESSIONAL_THEME_IDS, 2)))
def test_two_chapter_openers_are_not_the_same_object_in_two_colours(a, b, books):
    """Hue is not a design: two openers must differ in how they are built."""

    def opener(pdf: bytes):
        doc = fitz.open(stream=pdf, filetype="pdf")
        for page in doc:
            if "First chapter" not in page.get_text():
                continue
            shapes = []
            for d in page.get_drawings():
                r = d["rect"]
                if r.y0 < 200 and r.width > 100:
                    shapes.append((d.get("type"), round(r.width), round(r.height), round(r.y0)))
            return tuple(sorted(shapes))
        return ()

    sig_a, sig_b = opener(books[a]), opener(books[b])
    if not sig_a and not sig_b:
        pytest.skip("neither template draws a chapter opener")
    assert sig_a != sig_b, (
        f"{a} and {b} build the same chapter opener ({sig_a}) and differ only in colour"
    )


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_no_empty_frame_is_drawn_around_a_picture(theme_id, books):
    """A frame must hug the picture, never box the column it sits in.

    A border declared on a figure is drawn by this renderer around the whole
    figure box, so an illustration narrower than the text column printed
    inside an empty rectangle with blank space beside it -- on every
    illustrated page of every template.
    """
    doc = fitz.open(stream=books[theme_id], filetype="pdf")
    for i, page in enumerate(doc):
        for info in page.get_image_info(xrefs=False):
            image = fitz.Rect(info["bbox"])
            for d in page.get_drawings():
                if d.get("color") is None:
                    continue          # a background fill is not a frame
                r = d["rect"]
                frames_it = (
                    abs(r.y0 - image.y0) < 12 and abs(r.y1 - image.y1) < 12
                    and r.width > image.width + 24
                )
                if frames_it:
                    raise AssertionError(
                        f"{theme_id}: page {i + 1} draws {r} ({r.width:.0f}pt) around a "
                        f"{image.width:.0f}pt picture -- an empty frame beside the image"
                    )


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_no_template_declares_a_border_around_the_figure_box(theme_id):
    """The rule that caused it, kept out at the source as well as on the page."""
    from services.ebook_design_system import theme_css

    import re

    css = theme_css(theme_id)
    for block in css.split("}"):
        if "{" not in block:
            continue
        selectors, declarations = block.rsplit("{", 1)
        selector_list = [s.strip() for s in selectors.split("\n")[-1].split(",")]
        # the figure box itself -- not a cell inside it, not its caption
        if not any(re.fullmatch(r"\.ebook-figure(\.[\w-]+)?", sel) for sel in selector_list):
            continue
        for edge in ("border:", "border-left:", "border-right:"):
            assert edge not in declarations, (
                f"{theme_id}: {edge.strip(':')} on the figure box draws a rectangle "
                f"around the whole column: {' '.join(declarations.split())[:90]}"
            )


@pytest.mark.parametrize("theme_id", PROFESSIONAL_THEME_IDS)
def test_captions_are_dark_enough_to_read(theme_id, books):
    """A caption is small type; small type needs 4.5:1 against its page."""
    ink = _ink(books[theme_id])
    page_bg = THEMES[theme_id].page_bg or "#ffffff"
    for span in ink["spans"]:
        if span["size"] > 10.5:
            continue
        colour = _rgb_hex(span.get("color", 0))
        behind = page_bg
        for fill, rect, page_number in ink["fills"]:
            if page_number != span["page"]:
                continue
            fx0, fy0, fx1, fy1 = rect
            sx0, sy0, sx1, sy1 = span["bbox"]
            if fx0 <= sx0 and fy0 <= sy0 and fx1 >= sx1 and fy1 >= sy1:
                behind = _rgb_hex(fill)
        ratio = contrast_ratio(colour, behind)
        assert ratio >= 4.5, (
            f"{theme_id}: small text {span['text'][:24]!r} at {ratio:.2f}:1 "
            f"({colour} on {behind})"
        )
