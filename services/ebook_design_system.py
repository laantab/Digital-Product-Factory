"""Reusable ebook design themes (typography, spacing, page roles).

Themes control fonts, sizes, line-height, margins, headers/footers, palette,
tables, callouts, chapter openers. CSS must never set letter-spacing for PDF
(xhtml2pdf glyph advance bug).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EbookTheme:
    theme_id: str
    version: str
    display_name: str
    font_body: str
    font_heading: str
    color_primary: str
    color_accent: str
    color_text: str
    color_muted: str
    color_rule: str
    body_size_pt: float
    line_height: float
    h1_size_pt: float
    h2_size_pt: float
    h3_size_pt: float
    margin_in: float
    paragraph_spacing_em: float
    chapter_opener: str  # stacked_label | rule_under | minimal | band_accent
    table_header_bg: str
    callout_bg: str
    min_font_pt: float = 9.0
    footer_size_pt: float = 9.0
    page_bg: str = "#ffffff"
    summary: str = ""
    # --- Template-engine fields (generic; defaults reproduce the pre-existing
    # look for every theme above, so nothing about them changes). ---
    #: Topics this template is intended for. Drives "Let the Factory Choose".
    topics: tuple[str, ...] = ()
    #: A second accent used only where a theme wants genuine multi-hue color
    #: (an infographic-card rail, a TOC rule) without touching color_accent,
    #: which the rest of the CSS already keys many things off of.
    color_accent_2: str = ""
    #: Give photographs a coordinated frame (thin colored border + padding)
    #: instead of the plain 1pt neutral rule every theme uses today.
    photo_frame: bool = False
    #: Give the TOC a subtle decorative rule/accent beyond the plain list.
    toc_accent: bool = False
    #: Richer TOC treatment, additive to toc_accent (kept for the one theme
    #: it already shipped on): plain | numeral_column | rule_ladder |
    #: chip_row | tab_style. See _shared_book_css's toc_style_css.
    toc_style: str = "plain"
    #: One customer-facing sentence: what kind of book this suits. Shown on
    #: the template-chooser card, never a theme_id.
    best_for: str = ""

    # --- v1.9.0 structural template fields ---------------------------------
    #: Each defaults to "classic", which emits no extra CSS at all, so every
    #: theme that does not set them renders exactly as it did in 1.8.x. A
    #: template is a STRUCTURE, not a palette: these are the parts that make
    #: two books look genuinely different on the page.
    heading_style: str = "classic"       # sans_bold_left | heavy_numbered | rounded_colour | uppercase_display | serif_small_caps | decimal_numbered
    callout_style: str = "classic"       # grey_quiet | accent_bar_label | tinted_rounded | solid_block | hairline_frame | definition_box
    checklist_style: str = "classic"     # square_boxes | numbered_steps | round_circles | bold_ticks | dash_list | review_questions
    quote_style: str = "classic"         # indented_rule | pull_quote | centered_italic | oversized_marks | drop_cap | block_citation
    caption_style: str = "classic"       # small_italic_left | caps_label_above | centered_soft | bold_strip | figure_number
    image_style: str = "classic"         # full_width | rounded | framed | edge_block | numbered_figure
    table_style: str = "classic"         # hairline_rows | banded | thick_header | minimal | full_grid
    page_furniture: str = "classic"      # title_left | chapter_right_bar | centered_soft | number_tab | small_caps_centered | section_split
    # --- Structured-visual (diagram) design tokens. Empty means "use the
    # renderer's own long-standing default colors" -- see _pal() in
    # ebook_visual_pipeline.py -- so a theme that does not set these renders
    # exactly as it always has. Only RGB triplets ("R,G,B", 0-255 each), not
    # CSS hex, because these feed PIL drawing calls directly.
    diagram_primary_rgb: str = ""
    diagram_accent_rgb: str = ""
    diagram_secondary_rgb: str = ""
    diagram_text_rgb: str = ""

    def css_vars(self) -> str:
        return f"""
:root {{
  --ebook-font-body: {self.font_body};
  --ebook-font-heading: {self.font_heading};
  --ebook-primary: {self.color_primary};
  --ebook-accent: {self.color_accent};
  --ebook-text: {self.color_text};
  --ebook-muted: {self.color_muted};
  --ebook-rule: {self.color_rule};
  --ebook-body-size: {self.body_size_pt}pt;
  --ebook-line-height: {self.line_height};
  --ebook-h1: {self.h1_size_pt}pt;
  --ebook-h2: {self.h2_size_pt}pt;
  --ebook-h3: {self.h3_size_pt}pt;
  --ebook-margin: {self.margin_in}in;
  --ebook-para-gap: {self.paragraph_spacing_em}em;
  --ebook-table-head: {self.table_header_bg};
  --ebook-callout: {self.callout_bg};
}}
"""

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme_id": self.theme_id,
            "version": self.version,
            "display_name": self.display_name,
            "font_body": self.font_body,
            "font_heading": self.font_heading,
            "color_primary": self.color_primary,
            "color_accent": self.color_accent,
            "body_size_pt": self.body_size_pt,
            "line_height": self.line_height,
            "margin_in": self.margin_in,
            "chapter_opener": self.chapter_opener,
            "min_font_pt": self.min_font_pt,
            "summary": self.summary,
            "best_for": self.best_for,
        }


PAGE_ROLES = (
    "cover",
    "title_page",
    "copyright_disclaimer",
    "toc",
    "chapter_opener",
    "body",
    "table_chart",
    "exercise_action",
    "summary",
    "author_resources",
)


THEMES: dict[str, EbookTheme] = {
    # Internal id kept for backward compatibility with saved projects that
    # already reference "studio_clean" -- the customer now sees "Minimal
    # Professional" (list_professional_themes()/to_dict() surface
    # display_name, never theme_id).
    "studio_clean": EbookTheme(
        theme_id="studio_clean",
        version="studio-v6",
        display_name="Minimal Professional",
        font_body="LiberationSerif, Georgia, serif",
        font_heading="LiberationSerif, Georgia, serif",
        color_primary="#0f766e",
        color_accent="#0d9488",
        color_text="#1e293b",
        color_muted="#64748b",
        color_rule="#99f6e4",
        body_size_pt=11.5,
        line_height=1.62,
        h1_size_pt=28.0,
        h2_size_pt=20.0,
        h3_size_pt=14.0,
        margin_in=0.85,
        paragraph_spacing_em=1.0,
        # A quiet small-caps label and a single hairline rule -- no band, no
        # frame, no second color. Distinctiveness here comes from restraint,
        # not decoration, which is the whole point of "minimal".
        chapter_opener="minimal_rule",
        toc_style="rule_ladder",
        table_header_bg="#f0fdfa",
        # Neutral zinc, not mint -- a colored callout would undercut the
        # "restraint, not decoration" identity this template is built on,
        # and #ecfdf5 collided with three other templates' callouts anyway
        # (see the distinctiveness gate).
        callout_bg="#f4f4f5",
        # Found while extending the distinctiveness gate to structured
        # diagrams: with no diagram_*_rgb set, this template and Elegant
        # Editorial both silently fell back to the same fixed
        # _DEFAULT_PALETTE teal -- the exact "one fixed palette regardless of
        # theme" defect this pass exists to fix, just missed on two of six.
        # Muted slate/teal, matching this template's own restrained palette.
        diagram_primary_rgb="15,118,110",
        diagram_accent_rgb="13,148,136",
        diagram_secondary_rgb="100,116,139",
        diagram_text_rgb="30,41,59",
        topics=("technical guide", "instructional", "how-to", "reference", "manual", "report", "documentation"),
        best_for="Technical guides, reports, and general nonfiction that need to read fast and clean.",
        summary="Clean, neutral, and efficient -- restrained styling, strong hierarchy, nothing decorative.",
        heading_style="sans_bold_left",
        callout_style="grey_quiet",
        checklist_style="square_boxes",
        quote_style="indented_rule",
        caption_style="small_italic_left",
        image_style="full_width",
        table_style="hairline_rows",
        page_furniture="title_left",
    ),
    "editorial_professional": EbookTheme(
        theme_id="editorial_professional",
        version="editorial-v5",
        display_name="Elegant Editorial",
        font_body="LiberationSerif, Georgia, serif",
        font_heading="LiberationSerif, Georgia, serif",
        color_primary="#1e3a5f",
        color_accent="#b45309",
        color_accent_2="#7c6a58",
        color_text="#1c1917",
        color_muted="#78716c",
        color_rule="#e7e5e4",
        body_size_pt=11.5,
        line_height=1.72,
        h1_size_pt=32.0,
        h2_size_pt=22.0,
        h3_size_pt=14.0,
        margin_in=1.0,
        paragraph_spacing_em=1.1,
        # A generous, magazine-style spread: wide margins, a centered
        # oversize title, a slim double rule -- a book-like opening, not a
        # form field with a label over it.
        chapter_opener="editorial_spread",
        toc_style="spread_list",
        photo_frame=True,
        table_header_bg="#fafaf9",
        # A muted parchment tint of its own -- #fffbeb collided with Bold
        # Creator's and Bright Workbook's callout backgrounds.
        callout_bg="#f1e7d6",
        # See Minimal Professional's comment above: this template also fell
        # back to the shared fixed-teal default before this fix. Deep navy
        # and brass, matching its own color_primary/color_accent.
        diagram_primary_rgb="30,58,95",
        diagram_accent_rgb="180,83,9",
        diagram_secondary_rgb="124,106,88",
        diagram_text_rgb="28,25,23",
        topics=("memoir", "essay", "essays", "premium nonfiction", "photography", "narrative nonfiction", "biography"),
        best_for="Memoir, essays, and premium nonfiction where the book itself should feel considered.",
        summary="Refined, spacious, book-like -- generous white space and an editorial chapter spread.",
        heading_style="serif_small_caps",
        callout_style="hairline_frame",
        checklist_style="dash_list",
        quote_style="drop_cap",
        caption_style="classic",
        image_style="framed",
        table_style="full_grid",
        page_furniture="small_caps_centered",
    ),
    "modern_practical": EbookTheme(
        theme_id="modern_practical",
        version="practical-v5",
        display_name="Modern Business",
        font_body="LiberationSans, Helvetica, sans-serif",
        font_heading="LiberationSans, Helvetica, sans-serif",
        color_primary="#1d4ed8",
        color_accent="#0369a1",
        color_accent_2="#0f172a",
        color_text="#0f172a",
        color_muted="#475569",
        color_rule="#bfdbfe",
        body_size_pt=11.5,
        line_height=1.6,
        h1_size_pt=26.0,
        h2_size_pt=18.0,
        h3_size_pt=13.5,
        margin_in=0.75,
        paragraph_spacing_em=0.95,
        # A large boxed chapter number beside a structured title block --
        # reads like a section of a report, not a storybook heading.
        chapter_opener="grid_number",
        toc_style="numeral_column",
        table_header_bg="#eff6ff",
        callout_bg="#f0f9ff",
        diagram_primary_rgb="29,78,216",
        diagram_accent_rgb="3,105,161",
        diagram_secondary_rgb="15,23,42",
        diagram_text_rgb="15,23,42",
        topics=("business", "marketing", "finance", "entrepreneurship", "consulting", "startup", "sales", "professional"),
        best_for="Business, marketing, and finance guides that need to look confident and structured.",
        summary="Clean, confident, structured -- a boxed chapter numeral and executive-style tables.",
        heading_style="heavy_numbered",
        callout_style="accent_bar_label",
        checklist_style="numbered_steps",
        quote_style="pull_quote",
        caption_style="caps_label_above",
        image_style="edge_block",
        table_style="banded",
        page_furniture="chapter_right_bar",
    ),
    "bold_creator": EbookTheme(
        theme_id="bold_creator",
        version="bold-creator-v4",
        display_name="Bold Creator",
        font_body="LiberationSans, Helvetica, sans-serif",
        font_heading="LiberationSans, Helvetica, sans-serif",
        color_primary="#0f172a",
        color_accent="#e11d48",
        color_accent_2="#f59e0b",
        color_text="#111827",
        color_muted="#57534e",
        color_rule="#fecdd3",
        body_size_pt=11.5,
        line_height=1.58,
        h1_size_pt=30.0,
        h2_size_pt=19.0,
        h3_size_pt=13.5,
        margin_in=0.7,
        paragraph_spacing_em=0.95,
        # A huge, near-full-height chapter numeral in the accent color behind
        # the title -- the most graphic, high-contrast opener of the six.
        chapter_opener="bold_numeral",
        toc_style="chip_row",
        photo_frame=True,
        table_header_bg="#fff1f2",
        # A stronger rose tint than the table header -- #fffbeb (amber) was
        # shared with Elegant Editorial and Bright Workbook's callouts.
        callout_bg="#ffe4e6",
        diagram_primary_rgb="17,24,39",
        diagram_accent_rgb="225,29,72",
        diagram_secondary_rgb="245,158,11",
        diagram_text_rgb="17,24,39",
        topics=("creator", "social media", "personal brand", "influencer", "content creator", "digital marketing", "youtube"),
        best_for="Creators, social media, and personal-brand guides that need energy and visual confidence.",
        summary="Energetic and high-impact -- a bold chapter numeral, rose-and-amber accents, dynamic cards.",
        heading_style="uppercase_display",
        callout_style="solid_block",
        checklist_style="bold_ticks",
        quote_style="oversized_marks",
        caption_style="bold_strip",
        image_style="classic",
        table_style="thick_header",
        page_furniture="number_tab",
    ),
    "bright_workbook": EbookTheme(
        theme_id="bright_workbook",
        version="bright-workbook-v4",
        display_name="Bright Workbook",
        font_body="LiberationSans, Helvetica, sans-serif",
        font_heading="LiberationSans, Helvetica, sans-serif",
        color_primary="#0d7a5f",
        color_accent="#f59e0b",
        color_accent_2="#2563eb",
        color_text="#1c1917",
        color_muted="#57534e",
        color_rule="#bbf7d0",
        body_size_pt=11.5,
        line_height=1.6,
        h1_size_pt=27.0,
        h2_size_pt=19.0,
        h3_size_pt=13.5,
        margin_in=0.75,
        paragraph_spacing_em=0.95,
        # A friendly rounded "tab" label rather than a plain line -- reads
        # like a course module header, inviting interaction.
        chapter_opener="stacked_label",
        toc_style="tab_style",
        table_header_bg="#ecfdf5",
        # Its own mint-green tint (freed up once Minimal Professional's
        # callout moved to neutral zinc) -- #fffbeb was shared with Elegant
        # Editorial and Bold Creator's callouts.
        callout_bg="#d1fae5",
        diagram_primary_rgb="13,122,95",
        diagram_accent_rgb="245,158,11",
        diagram_secondary_rgb="37,99,235",
        diagram_text_rgb="28,25,23",
        topics=("workbook", "course", "coaching", "education", "curriculum", "exercises", "planner", "guided"),
        best_for="Workbooks, courses, and coaching programs built around exercises and trackers.",
        summary="Friendly and action-oriented -- rounded tabs, bright accents, built for checklists and trackers.",
        heading_style="decimal_numbered",
        callout_style="definition_box",
        checklist_style="review_questions",
        quote_style="block_citation",
        caption_style="figure_number",
        image_style="numbered_figure",
        table_style="classic",
        page_furniture="section_split",
    ),
    "warm_wellness": EbookTheme(
        theme_id="warm_wellness",
        version="warm-wellness-v4",
        display_name="Warm Wellness",
        # LiberationSerif/LiberationSans are the only faces this Factory holds
        # a redistribution licence for (SIL OFL 1.1, see ebook_fonts.py). Warm
        # Wellness pairs them the other way round from Studio Clean -- serif
        # heading over sans body -- for a calmer, more editorial wellness feel
        # without introducing an unlicensed font file.
        font_body="LiberationSans, Helvetica, sans-serif",
        font_heading="LiberationSerif, Georgia, serif",
        color_primary="#0f5e56",   # deep teal
        color_accent="#c2603f",   # muted terracotta/coral
        color_accent_2="#8fb9a8",  # soft sage
        color_text="#2b2420",
        color_muted="#8a7f74",
        color_rule="#cfe7de",     # light aqua
        body_size_pt=11.5,
        line_height=1.64,
        h1_size_pt=28.0,
        h2_size_pt=21.0,
        h3_size_pt=14.0,
        margin_in=0.8,
        paragraph_spacing_em=1.0,
        chapter_opener="band_accent",
        table_header_bg="#f2ece2",  # warm cream
        callout_bg="#f6f1e7",
        page_bg="#fffdfa",
        photo_frame=True,
        toc_accent=True,
        toc_style="accent_bar",
        diagram_primary_rgb="15,94,86",
        diagram_accent_rgb="194,96,63",
        diagram_secondary_rgb="143,185,168",
        diagram_text_rgb="43,36,32",
        topics=("wellness", "mindfulness", "self-care", "self care", "meditation", "gentle lifestyle", "calm", "breathing"),
        best_for="Wellness, mindfulness, and self-care guides that should feel calm and welcoming.",
        summary="Calm, encouraging wellness palette: deep teal, sage, warm cream, terracotta accent.",
        heading_style="rounded_colour",
        callout_style="tinted_rounded",
        checklist_style="round_circles",
        quote_style="centered_italic",
        caption_style="centered_soft",
        image_style="rounded",
        table_style="minimal",
        page_furniture="centered_soft",
    ),
}

# Backward-compatible alias used by older factory packages.
THEMES["ink_editorial"] = THEMES["editorial_professional"]

#: Customer-facing catalog order: Warm Wellness first (the proven baseline),
#: then the two new templates, then the three redesigned legacy templates.
#: Internal ids are unchanged from before this catalog existed, so a saved
#: project's design_theme="studio_clean" keeps resolving exactly as it did --
#: only the customer-facing display_name changed (Minimal Professional /
#: Elegant Editorial / Modern Business).
PROFESSIONAL_THEME_IDS = (
    "warm_wellness",
    "modern_practical",
    "bold_creator",
    "editorial_professional",
    "bright_workbook",
    "studio_clean",
)


def recommend_theme(*, topic: str = "", title: str = "", audience: str = "") -> str:
    """'Let the Factory Choose': match a book's stated topic against each
    template's declared `topics`. Falls back to studio_clean ("Minimal
    Professional" to the customer), the existing general-purpose default --
    never guesses at a template that wasn't built for the book's subject.
    Returns an internal theme_id; callers show the customer display_name.
    """
    blob = f"{topic} {title} {audience}".lower()
    for tid in PROFESSIONAL_THEME_IDS:
        theme = THEMES[tid]
        if any(t in blob for t in theme.topics):
            return tid
    return "studio_clean"


def get_theme(theme_id: str | None) -> EbookTheme:
    if theme_id == "ink_editorial":
        return THEMES["editorial_professional"]
    return THEMES.get(theme_id or "", THEMES["studio_clean"])


def list_professional_themes() -> list[dict[str, Any]]:
    return [THEMES[tid].to_dict() for tid in PROFESSIONAL_THEME_IDS]


def theme_css(theme_id: str | None) -> str:
    """Return theme CSS fragment safe for HTML preview and PDF (no letter-spacing)."""
    t = get_theme(theme_id)
    return t.css_vars() + _shared_book_css(t) + _template_structure_css(t)


#: Where the running-footer frame begins, in inches from the top of a
#: letter page, and the clear space kept between the body frame and it.
FOOTER_TOP_IN = 10.05
FOOTER_GAP_IN = 0.10


def _shared_book_css(t: EbookTheme) -> str:
    accent2 = t.color_accent_2 or t.color_accent
    # v1.9.0. Ink that is measured against the fill it sits on, never assumed.
    # Warm Wellness's teal band and Bright Workbook's amber tab both shipped
    # white type; the amber one measured 2.15:1 and could not be read in print.
    ink_primary = readable_ink(t.color_primary, dark=t.color_text)
    ink_accent = readable_ink(t.color_accent, dark=t.color_text)
    # Small type keeps its hue but never drops below a readable ratio on the
    # page it is printed on (contents numerals, footers, captions, marks).
    page = t.page_bg or "#ffffff"
    small_accent = accessible_ink(t.color_accent, page)
    small_muted = accessible_ink(t.color_muted, page)
    small_primary = accessible_ink(t.color_primary, page)
    # v1.9.1. The body frame used the same margin on all four sides, so on
    # every template with a bottom margin under 0.95in it ran down to
    # 741pt while the footer frame starts at 723.6pt. The last line of a
    # full page printed through the page number. The bottom margin is now
    # derived from where the footer actually begins, so the two frames
    # cannot overlap whatever a template asks for.
    bottom_margin_in = round(max(float(t.margin_in), 11.0 - FOOTER_TOP_IN + FOOTER_GAP_IN), 3)
    # A card label sits on the callout fill, not on the page.
    card_label_ink = accessible_ink(t.color_primary, t.callout_bg or page)
    opener_h2 = {
        "stacked_label": f"border-bottom: 2pt solid {t.color_rule}; padding-bottom: 0.28em;",
        "rule_under": f"border-bottom: 1.5pt solid {t.color_primary}; padding-bottom: 0.32em;",
        "minimal": f"border-bottom: 1pt solid {t.color_rule}; padding-bottom: 0.22em;",
        # band_accent puts its color on the wrapping .chapter-opener-block
        # instead (a real coordinated band, not just a rule under the title),
        # so the title itself only needs breathing room here.
        "band_accent": "padding-bottom: 0.15em;",
        # A single hairline, nothing else -- restraint is the whole design.
        "minimal_rule": f"border-bottom: 0.75pt solid {t.color_rule}; padding-bottom: 0.3em;",
        # Centered inside its own block below; the h2 itself just needs a
        # slim rule under the centered text, not a left-aligned border.
        "editorial_spread": f"border-bottom: 1pt solid {t.color_rule}; padding-bottom: 0.35em; display: inline-block;",
        # The title sits beside the boxed numeral; a bottom rule would run
        # under empty space next to the box, so none here -- the box carries
        # the visual weight instead.
        "grid_number": "padding-bottom: 0.1em;",
        "bold_numeral": "padding-bottom: 0.1em;",
        "friendly_tab": f"border-bottom: 1pt solid {t.color_rule}; padding-bottom: 0.3em;",
    }.get(t.chapter_opener, f"border-bottom: 2pt solid {t.color_rule}; padding-bottom: 0.28em;")

    chapter_band_css = {
        # xhtml2pdf/reportlab's CSS support does not include linear-gradient()
        # -- an earlier version of this block used one and it silently
        # produced NO background at all, leaving white chapter-num/title text
        # invisible on the white page (caught by rendering an actual chapter
        # opener and looking at it, not by reading the CSS). Solid background
        # + a second-color accent stripe gets the coordinated two-tone look
        # every renderer here supports. Warm Wellness only -- untouched by
        # this file's other five chapter-opener treatments.
        "band_accent": f"""
.chapter-opener-block {{
  display: block;
  background: {t.callout_bg};
  border-bottom: 5pt solid {t.color_primary};
  color: {t.color_text};
  padding: 16pt 18pt 13pt;
  margin: 0 0 16pt;
  page-break-inside: avoid;
  page-break-after: avoid;
}}
.chapter-opener-block .chapter-num {{
  color: {small_primary};
  background: {t.callout_bg};
  margin: 0 0 6pt;
  padding: 0 0 2pt;
  font-weight: 700;
}}
.chapter-opener-block .chapter-title, .chapter-opener-block h2 {{
  color: {t.color_primary};
  background: {t.callout_bg};
  border-bottom: none !important;
  margin: 0;
  padding: 0;
}}
""",
        # Minimal Professional: no box, no color block -- a quiet uppercase
        # label and generous top space, nothing to distract from the title.
        "minimal_rule": f"""
.chapter-opener-block {{
  display: block;
  padding: 22pt 0 6pt;
  margin: 0 0 14pt;
  page-break-inside: avoid;
  page-break-after: avoid;
}}
.chapter-opener-block .chapter-num {{
  color: {small_muted};
  font-weight: 400;
}}
""",
        # Elegant Editorial: a centered, magazine-style spread -- the
        # chapter number sits above a centered title with room to breathe,
        # framed by a hairline top rule.
        "editorial_spread": f"""
.chapter-opener-block {{
  display: block;
  text-align: center;
  border-top: 1pt solid {t.color_rule};
  padding: 26pt 20pt 18pt;
  margin: 0 0 20pt;
  page-break-inside: avoid;
  page-break-after: avoid;
}}
.chapter-opener-block .chapter-num {{
  color: {small_accent};
  text-align: center;
}}
.chapter-opener-block .chapter-title, .chapter-opener-block h2 {{
  text-align: center;
}}
""",
        # Modern Business: a boxed chapter numeral beside a structured title
        # block -- reads like a report section, not a storybook heading.
        # xhtml2pdf has no reliable flexbox/grid, so the "grid" is a bordered
        # number box the title sits under, not a true side-by-side column.
        "grid_number": f"""
.chapter-opener-block {{
  display: block;
  padding: 0 0 10pt;
  margin: 0 0 16pt;
  border-bottom: 1.5pt solid {t.color_rule};
  page-break-inside: avoid;
  page-break-after: avoid;
}}
.chapter-opener-block .chapter-num {{
  display: block;
  color: {small_primary};
  background: {t.callout_bg};
  border: 1.5pt solid {t.color_primary};
  padding: 4pt 10pt;
  margin: 0 0 10pt;
  width: 1.1in;
  text-align: center;
}}
""",
        # Bold Creator: the chapter number as a huge graphic numeral in the
        # accent color -- the most high-contrast, poster-like opener of the
        # six.
        "bold_numeral": f"""
.chapter-opener-block {{
  display: block;
  padding: 4pt 0 8pt;
  margin: 0 0 14pt;
  page-break-inside: avoid;
  page-break-after: avoid;
}}
.chapter-opener-block .chapter-num {{
  display: block;
  color: {small_accent};
  font-size: 46pt;
  font-weight: 700;
  line-height: 1;
  margin: 0 0 4pt;
  text-transform: none;
}}
""",
        # Bright Workbook: a rounded, colored "tab" label -- reads like a
        # course-module header, inviting rather than a plain rule.
        "friendly_tab": f"""
.chapter-opener-block {{
  display: block;
  padding: 0 0 8pt;
  margin: 0 0 14pt;
  page-break-inside: avoid;
  page-break-after: avoid;
}}
.chapter-opener-block .chapter-num {{
  display: block;
  color: {small_accent};
  background: {t.callout_bg};
  border: 1pt solid {t.color_accent};
  padding: 5pt 12pt;
  margin: 0 0 10pt;
  width: 1.6in;
  text-align: center;
}}
""",
    }.get(t.chapter_opener, """
.chapter-opener-block { display: block; }
""")
    photo_frame_css = (
        f"""
/* xhtml2pdf/reportlab does not support CSS outline -- an earlier version of
   this rule used outline for the frame's inner line and it silently drew
   nothing, so photographs had no visible frame at all (caught the same way
   as the gradient bug: by rendering an actual photo page and looking at
   it). border is the one of the two this renderer actually paints. */
.ebook-figure.ebook-figure-photo img {{
  /* A full content-width photo plus this theme's chapter-opener band can
     together run past the page before the next `page-break-inside:avoid`
     block is allowed to break -- leaving the running footer overlapping the
     last line of body text (caught on Project 351's chapter 2, whose
     photograph is a near-square-ratio full-bleed image right under the
     band). Capping the photo's own height leaves the band, the caption and
     at least a paragraph of body text room on the same page. */
  max-height: 4.1in;
  width: auto;
  max-width: 100%;
}}
.ebook-figure.ebook-figure-photo figcaption {{
  padding: 0 4pt;
}}
"""
        if t.photo_frame
        else ""
    )
    toc_accent_css = (
        f"""
.toc-page h2 {{
  border-bottom: 2.5pt solid {t.color_accent};
  padding-bottom: 0.2em;
  display: inline-block;
}}
.toc-row {{
  border-left: 3pt solid {accent2};
  padding-left: 10pt;
}}
"""
        if t.toc_accent
        else ""
    )
    toc_style_css = {
        # Minimal Professional: one hairline under every entry -- a plain
        # ladder of rules, nothing more.
        "rule_ladder": f"""
.toc-row {{
  border-bottom: 0.75pt solid {t.color_rule};
  padding: 5pt 0;
}}
""",
        # Elegant Editorial: found while extending the distinctiveness gate
        # to a zoomed render -- xhtml2pdf does not draw a border on a block
        # once around all its children; it replicates the parent's
        # border-top/border-bottom onto every child flowable, so the
        # originally-intended "framed top and bottom, no per-row rule" design
        # silently rendered as a rule under every single row (indistinguishable
        # from rule_ladder/numeral_column). No border at all -- open,
        # generously spaced, muted serif numerals -- is what this renderer can
        # actually deliver, and reads even more like an unadorned book
        # contents page than the originally-drawn frame would have.
        "spread_list": f"""
.toc-list {{
  padding: 6pt 0;
}}
.toc-row {{
  padding: 8pt 0;
}}
.toc-row .toc-num {{
  color: {small_muted};
  font-weight: 400;
}}
""",
        # Modern Business: each number in its own small bordered column,
        # like a report's numbered section list.
        "numeral_column": f"""
.toc-row {{
  padding: 6pt 0;
  border-bottom: 0.75pt solid {t.color_rule};
}}
.toc-row .toc-num {{
  display: inline-block;
  color: {small_primary};
  border-left: 3pt solid {t.color_primary};
  padding: 1pt 8pt 1pt 6pt;
  margin-right: 6pt;
  font-weight: 700;
}}
""",
        # Bold Creator: the number as a small colored chip ahead of the
        # title, matching the poster-like chapter numeral.
        "chip_row": f"""
.toc-row {{
  padding: 6pt 0;
}}
.toc-row .toc-num {{
  display: inline-block;
  color: #ffffff;
  background: {t.color_accent};
  padding: 1pt 8pt;
  margin-right: 8pt;
}}
""",
        # Bright Workbook: each row on a soft tinted background -- reads
        # like a friendly list of course modules.
        "tab_style": f"""
.toc-row {{
  background: {t.callout_bg};
  padding: 7pt 10pt;
  margin-bottom: 4pt;
}}
.toc-row .toc-num {{
  color: {small_accent};
}}
""",
    }.get(t.toc_style, "")
    para_gap = max(float(t.paragraph_spacing_em), 1.15)
    line_h = max(float(t.line_height), 1.64)
    return f"""
/* The design spec has always declared footer_mode "page_number" and
   header_mode "running_title", but nothing rendered them, so every designed
   ebook shipped with no page numbers at all while its own contents page quoted
   them. The static frame below is what makes the footer real (v1.4.1).
   Keep comments OUTSIDE the @page block: xhtml2pdf's at-rule parser drops the
   whole rule, frame included, if it meets one inside. */
@page {{
  size: letter;
  margin: {t.margin_in}in {t.margin_in}in {bottom_margin_in}in {t.margin_in}in;
  @frame footer_frame {{
    -pdf-frame-content: page-footer;
    left: {t.margin_in}in;
    top: {FOOTER_TOP_IN}in;
    width: {8.5 - 2 * float(t.margin_in)}in;
    height: 0.35in;
  }}
}}
#page-footer {{
  font-family: {t.font_body};
  font-size: {t.footer_size_pt}pt;
  color: {small_muted};
  border-top: 0.5pt solid {t.color_rule};
  padding-top: 4pt;
}}
#page-footer .foot-title, #page-footer .foot-sep, #page-footer .foot-num {{
  font-size: {t.footer_size_pt}pt; color: {small_muted};
}}
/* xhtml2pdf treats unspecified display as inline; force real book blocks. */
section, article, header, footer, nav, div, p, h1, h2, h3, h4, h5, h6,
ul, ol, blockquote, pre, figure, figcaption {{
  display: block;
}}
li {{
  display: block;
}}
body {{
  display: block;
  font-family: {t.font_body};
  color: {t.color_text};
  font-size: {t.body_size_pt}pt;
  line-height: {line_h};
  background: {t.page_bg};
}}
h1, h2, h3, h4, .chapter-title, .book-title, .chapter-num, .section-heading {{
  display: block;
  font-family: {t.font_heading};
  color: {t.color_primary};
  page-break-after: avoid;
  page-break-inside: avoid;
}}
h1, .book-title {{ font-size: {t.h1_size_pt}pt; margin: 0 0 0.55em; line-height: 1.2; }}
h2, .chapter-title {{
  font-size: {t.h2_size_pt}pt;
  margin: 0 0 0.85em;
  line-height: 1.28;
  {opener_h2}
}}
h3, .section-heading {{
  font-size: {t.h3_size_pt}pt;
  margin: 1.35em 0 0.55em;
  line-height: 1.3;
  page-break-after: avoid;
}}
h4 {{ font-size: 12pt; margin: 1.2em 0 0.45em; color: {small_accent}; page-break-after: avoid; }}
p {{
  display: block;
  margin: 0 0 {para_gap}em;
  orphans: 3;
  widows: 3;
}}
.title-sub, .title-author, .caption {{
  display: block;
}}
.chapter-num {{
  display: block;
  font-size: 10pt;
  font-weight: 700;
  text-transform: uppercase;
  color: {small_accent};
  margin: 0 0 10pt;
}}
.back-matter-label {{
  font-size: 9.5pt;
  font-weight: 700;
  text-transform: uppercase;
  color: {small_muted};
  margin: 0 0 6pt;
}}
table, .ebook-table, .va-table {{
  display: table;
  border-collapse: collapse;
  width: 100%;
  table-layout: fixed;
  margin: 14pt 0 18pt;
}}
thead {{ display: table-header-group; }}
tbody {{ display: table-row-group; }}
tr {{ display: table-row; page-break-inside: avoid; }}
th, td {{
  display: table-cell;
  border: 1pt solid {t.color_rule};
  padding: 8pt 10pt;
  text-align: left;
  font-size: 9.5pt;
  vertical-align: top;
  word-wrap: break-word;
  overflow-wrap: break-word;
}}
th {{
  background: {t.table_header_bg};
  color: {t.color_primary};
  font-weight: 700;
}}
.ebook-table-wide th, .ebook-table-wide td {{
  font-size: 9.5pt;
  padding: 7pt 8pt;
}}
.ebook-comparison {{
  display: block;
  margin: 14pt 0 18pt;
}}
table.ebook-card {{
  display: table;
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
  margin: 0 0 14pt;
  background: {t.callout_bg};
}}
table.ebook-card th, table.ebook-card td {{
  /* A template's table-header fill must never reach a card cell. A wide table
     is rebuilt as a two-column card whose left cell is a <th>, so the
     thick_header rule -- table th {{ background: color_primary }} -- painted the
     card's own brand-coloured label onto a brand-coloured block and the label
     vanished at 1.00:1. Naming the fill here outranks that rule on the cards
     alone and leaves ordinary tables untouched. */
  background: {t.callout_bg};
  font-size: 9.5pt;
  line-height: 1.4;
  vertical-align: top;
  text-align: left;
  padding: 5pt 8pt;
  border: none;
  border-bottom: 1pt solid {t.color_rule};
}}
table.ebook-card tr:last-child th, table.ebook-card tr:last-child td {{
  border-bottom: none;
}}
table.ebook-card th.ebook-card-label, .ebook-card-label {{
  width: 36%;
  color: {card_label_ink};
  font-weight: 700;
}}
table.ebook-card td.ebook-card-value {{
  width: 66%;
  font-weight: 400;
}}
ul, ol {{
  display: block;
  margin: 0 0 14pt 0;
  padding: 0 0 0 4pt;
}}
ul li {{
  display: block;
  margin: 0 0 7pt;
  list-style-type: disc;
}}
ol li {{
  display: block;
  margin: 0 0 7pt;
  list-style-type: decimal;
}}
ul.checklist, .checklist {{
  display: block;
  list-style: none;
  margin: 10pt 0 16pt 0;
  padding: 8pt 10pt;
  background: {t.callout_bg};
  page-break-inside: avoid;
}}
ul.checklist li, .checklist li {{
  display: block;
  margin: 0 0 8pt;
  padding: 4pt 4pt 4pt 4pt;
  border-left: 3pt solid {t.color_accent};
  padding-left: 12pt;
  page-break-inside: avoid;
}}
ul.checklist li .check-box, .checklist li .check-box {{
  font-family: {t.font_body};
  color: {small_accent};
  font-weight: 700;
}}
ol.workflow, .workflow {{
  display: block;
  margin: 10pt 0 16pt 18pt;
  padding: 0;
  page-break-inside: avoid;
}}
ol.workflow li, .workflow li {{
  /* v1.9.0. list-style: none arrived with a change that printed each step as a
     paragraph carrying its own typed numeral. That change was reverted -- rows
     are list items again -- but the rule stayed, and four of the six templates
     fell back to a bullet, so a numbered procedure printed as bullets while the
     release notes claimed otherwise. The renderer draws the numeral; ask it for
     one. */
  display: block;
  margin: 0 0 8pt;
  list-style-type: decimal;
}}
.callout, .example-callout, .visual-aid {{
  background: {t.callout_bg};
  border-left: 3pt solid {t.color_accent};
  padding: 10pt 12pt;
  margin: 12pt 0;
  page-break-inside: avoid;
}}
.caption, figcaption, .va-caption {{
  font-size: 9pt;
  color: {small_muted};
  font-style: italic;
  margin: 4pt 0 12pt;
}}
.ebook-figure {{
  display: block;
  margin: 14pt 0 16pt;
  page-break-inside: avoid;
  text-align: center;
}}
.ebook-figure img {{
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto 6pt;
}}
.ebook-figure-table {{
  text-align: left;
}}
.ebook-figure .va-title {{
  display: block;
  font-weight: 700;
  text-align: left;
  margin: 0 0 6pt;
  color: {t.color_primary};
}}
.ebook-figure table {{
  display: table;
  width: 100%;
  border-collapse: collapse;
  font-size: 10pt;
  text-align: left;
  margin: 0 0 6pt;
}}
.ebook-figure th, .ebook-figure td {{
  display: table-cell;
  border: 1pt solid {t.color_rule};
  padding: 6pt 8pt;
  vertical-align: top;
}}
.ebook-figure th {{
  background: {t.color_rule};
  color: {t.color_primary};
  font-weight: 700;
}}
.sources-list, .source-ref {{
  font-size: 9.5pt;
  color: {small_muted};
}}
/* A source URL is one long unbreakable token. These rules break it in the
   HTML preview, which a browser renders. They do NOT help in the PDF: the
   print renderer honours neither word-break nor overflow-wrap, so a long URL
   ran off the page there and failed a real book's preflight as clipped text.
   That is fixed where it has to be, in the text itself -- see
   printable_source_url() in services/ebook_book_layout.py. */
.sources-list li, .source-ref {{
  margin: 4pt 0;
  word-break: break-all;
  overflow-wrap: anywhere;
  word-wrap: break-word;
}}
.sources-list a, .source-ref a {{
  color: {t.color_primary};
  text-decoration: underline;
  word-break: break-all;
  overflow-wrap: anywhere;
  word-wrap: break-word;
}}
.page-foot, .running-footer {{
  color: {small_muted};
  font-size: 9pt;
  margin-top: 18pt;
  border-top: 1pt solid {t.color_rule};
  padding-top: 6pt;
}}
.title-page {{ display: block; text-align: center; padding-top: 1.35in; }}
.title-page p {{ margin: 0 0 10pt; }}
.title-sub {{ margin: 0 0 10pt; font-size: 12.5pt; color: {small_muted}; }}
.title-author {{ margin: 0 0 12pt; font-size: 12pt; }}
.title-page .caption {{ margin: 16pt 0 0; }}
.legal-page, .toc-page, .chapter-page, .back-matter-page {{ display: block; }}
.heading-keep {{
  display: block;
  page-break-inside: avoid;
}}
.chapter-last-block {{
  display: block;
  page-break-inside: avoid !important;
}}
.chapter-last-block p, .chapter-last-block li, .chapter-last-block ul, .chapter-last-block ol {{
  page-break-inside: avoid !important;
  page-break-after: avoid;
  -pdf-keep-with-next: true;
  orphans: 4;
  widows: 4;
}}
table.toc-list {{
  display: table;
  list-style: none;
  margin: 8pt 0 0;
  padding: 0;
  width: 100%;
  border-collapse: collapse;
  table-layout: auto;
}}
ol.toc-list, ul.toc-list {{
  display: block;
  list-style: none;
  margin: 8pt 0 0;
  padding: 0;
  width: 100%;
}}
table.toc-list tr {{
  display: table-row;
}}
table.toc-list td {{
  display: table-cell;
  border: none;
  border-bottom: 1pt solid {t.color_rule};
  padding: 9pt 8pt;
  font-size: 11.5pt;
  vertical-align: bottom;
}}
.toc-list li {{
  display: block;
  padding: 9pt 0;
  border-bottom: 1pt solid {t.color_rule};
  font-size: 11.5pt;
}}
.toc-num {{
  color: {small_accent};
  font-weight: 700;
}}
.toc-page-num {{
  color: {small_muted};
  font-weight: 400;
}}
.toc-list a {{ color: {t.color_primary}; text-decoration: none; font-weight: 700; }}
.back-matter-page h2 {{
  border-bottom: 2pt solid {t.color_accent};
  padding-bottom: 0.22em;
  display: inline-block;
  margin-bottom: 14pt;
}}
.back-matter-page {{ padding-top: 4pt; }}
{chapter_band_css}
{photo_frame_css}
{toc_accent_css}
{toc_style_css}
"""


LAYOUT_GUARDS = {
    "no_letter_spacing": True,
    "min_font_pt": 9.0,
    "measured_pagination": True,
    "orphan_heading_guard": True,
    "safe_margins_in": 0.6,
}


def _luminance(hex_color: str) -> float:
    h = (hex_color or "#000000").lstrip("#")
    if len(h) != 6:
        return 0.0
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))

    def ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast between two hex colours. Used as a guard, not decoration."""
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def readable_ink(background: str, *, dark: str = "#111111", light: str = "#ffffff") -> str:
    """Ink that can actually be read on this background.

    v1.9.0. Two templates shipped white type on a mid-tone brand colour --
    2.1:1, invisible in print -- because the ink was hardcoded next to a theme
    colour nobody had measured. Every place a template paints type on a filled
    panel now asks this function instead of assuming white.
    """
    return light if contrast_ratio(background, light) >= contrast_ratio(background, dark) else dark


def accessible_ink(colour: str, background: str = "#ffffff", *, min_ratio: float = 4.5) -> str:
    """The same colour, darkened only as far as it must be to be readable.

    v1.9.0. Small type in a brand colour -- a contents numeral, a footer, a
    caption -- repeatedly landed between 1.9:1 and 3.9:1 against the page.
    This keeps the template's hue and takes it to a ratio a reader can
    actually see, rather than replacing it with black.
    """
    base = (colour or "#000000").lstrip("#")
    if len(base) != 6:
        return colour
    r, g, b = (int(base[i:i + 2], 16) for i in (0, 2, 4))
    for _ in range(24):
        candidate = f"#{r:02x}{g:02x}{b:02x}"
        if contrast_ratio(candidate, background) >= min_ratio:
            return candidate
        r, g, b = int(r * 0.88), int(g * 0.88), int(b * 0.88)
    return "#111111"


def _template_structure_css(t: EbookTheme) -> str:
    """The CSS that makes two templates different BOOKS, not different palettes.

    v1.9.0. Every rule here was checked against a rendered PDF, not against
    what CSS says it should do. This renderer (xhtml2pdf/reportlab) silently
    ignores text-transform, small-caps, :nth-child, CSS borders on table
    cells, and text-align inside the running-footer frame; it also replicates
    a block's background and borders onto each of its children. Anything in
    that list is absent below -- a style that does not draw is not a template,
    it is a promise the book cannot keep.

    Fields default to "classic", which emits nothing, so a theme that declares
    no structure renders exactly as it did in 1.8.x.
    """
    accent2 = t.color_accent_2 or t.color_accent
    page = t.page_bg or "#ffffff"
    small_primary = accessible_ink(t.color_primary, page)
    out: list[str] = []

    heading = {
        "sans_bold_left": f"h2 {{ font-weight: 700; text-align: left; }}\n"
                          f"h3 {{ color: {t.color_primary}; font-weight: 700; font-size: {t.h3_size_pt + 0.5:.1f}pt; }}",
        "heavy_numbered": f"h2 {{ font-weight: 800; }}\n"
                          f"h3 {{ border-left: 4pt solid {t.color_accent}; padding-left: 8pt; font-weight: 700; "
                          f"font-size: {t.h3_size_pt + 1:.1f}pt; }}",
        "rounded_colour": f"h2 {{ color: {t.color_primary}; font-weight: 700; }}\n"
                          f"h3 {{ color: {t.color_primary}; font-weight: 700; font-size: {t.h3_size_pt + 1.5:.1f}pt; }}",
        "uppercase_display": f"h2 {{ font-weight: 800; font-size: {t.h2_size_pt + 2:.1f}pt; }}\n"
                             f"h3 {{ color: {t.color_accent}; font-weight: 800; font-size: {t.h3_size_pt + 2:.1f}pt; }}",
        "serif_small_caps": f"h2 {{ text-align: center; }}\n"
                            f"h3 {{ text-align: center; color: {t.color_primary}; font-weight: 700; "
                            f"font-size: {t.h3_size_pt + 1:.1f}pt; }}",
        "decimal_numbered": f"h2 {{ border-bottom: 1pt solid {t.color_rule}; padding-bottom: 4pt; }}\n"
                            f"h3 {{ color: {t.color_primary}; font-weight: 700; "
                            f"font-size: {t.h3_size_pt + 1.5:.1f}pt; border-bottom: 0.75pt solid {t.color_rule}; }}",
    }.get(t.heading_style)
    if heading:
        out.append(heading)

    # Callouts: a single filled block whose ink is measured against its fill.
    callout_ink = readable_ink(t.color_primary, dark=t.color_text)
    callout = {
        "grey_quiet": f".callout, .example-callout, .visual-aid {{ background: #f4f4f5; border-left: none; "
                      f"border-top: 1pt solid {t.color_rule}; border-bottom: 1pt solid {t.color_rule}; "
                      f"padding: 10pt 12pt; color: {t.color_text}; }}",
        "accent_bar_label": f".callout, .example-callout, .visual-aid {{ background: #ffffff; "
                            f"border-left: 6pt solid {t.color_accent}; border-top: none; border-bottom: none; "
                            f"padding: 8pt 12pt; color: {t.color_text}; }}",
        "tinted_rounded": f".callout, .example-callout, .visual-aid {{ background: {t.callout_bg}; border-left: none; "
                          f"border-top: 1pt solid {t.color_rule}; border-bottom: 1pt solid {t.color_rule}; "
                          f"padding: 12pt 14pt; color: {t.color_text}; }}",
        "solid_block": f".callout, .example-callout, .visual-aid {{ background: {t.color_primary}; "
                       f"color: {callout_ink}; border-left: none; padding: 12pt 14pt; }}",
        "hairline_frame": f".callout, .example-callout, .visual-aid {{ background: #ffffff; "
                          f"border-left: 1pt solid {t.color_accent}; border-top: 1pt solid {t.color_accent}; "
                          f"border-bottom: 1pt solid {t.color_accent}; padding: 12pt 16pt; color: {t.color_text}; }}",
        "definition_box": f".callout, .example-callout, .visual-aid {{ background: {t.callout_bg}; border-left: none; "
                          f"border-top: 3pt solid {t.color_primary}; border-bottom: none; padding: 10pt 12pt; "
                          f"color: {t.color_text}; }}",
    }.get(t.callout_style)
    if callout:
        out.append(callout)

    # Checklists: styled per item, never on the list. This renderer copies a
    # list's background and borders onto every child, so a "panel" declared on
    # <ul> prints as one strip per line with white gaps -- and a tall one runs
    # over the running footer. One item, one treatment, is what draws.
    checklist = {
        "square_boxes": f"ul.checklist, .checklist {{ background: #ffffff; padding: 2pt 0; }}\n"
                        f"ul.checklist li, .checklist li, .check-row {{ border-left: none; border: 1pt solid {t.color_rule}; "
                        f"padding: 6pt 8pt; margin: 0 0 6pt; }}",
        "numbered_steps": f"ul.checklist, .checklist {{ background: #ffffff; padding: 2pt 0; }}\n"
                          f"ul.checklist li, .checklist li, .check-row {{ border-left: 4pt solid {accent2}; "
                          f"padding: 5pt 4pt 5pt 10pt; margin: 0 0 7pt; }}",
        "round_circles": f"ul.checklist, .checklist {{ background: #ffffff; padding: 2pt 0; }}\n"
                         f"ul.checklist li, .checklist li, .check-row {{ border-left: none; "
                         f"border-bottom: 0.75pt solid {t.color_rule}; padding: 7pt 2pt 6pt 12pt; "
                         f"margin: 0 0 4pt; }}",
        "bold_ticks": f"ul.checklist, .checklist {{ background: #ffffff; padding: 2pt 0; }}\n"
                      f"ul.checklist li, .checklist li, .check-row {{ border-left: none; "
                      f"border-top: 2pt solid {t.color_accent}; padding: 6pt 2pt; margin: 0 0 6pt; }}",
        "dash_list": f"ul.checklist, .checklist {{ background: #ffffff; padding: 0; }}\n"
                     f"ul.checklist li, .checklist li, .check-row {{ border-left: none; padding: 3pt 0 3pt 2pt; margin: 0 0 4pt; }}",
        "review_questions": f"ul.checklist, .checklist {{ background: #ffffff; padding: 2pt 0; }}\n"
                            f"ul.checklist li, .checklist li, .check-row {{ border-left: none; "
                            f"border-top: 1pt solid {t.color_rule}; padding: 7pt 2pt; margin: 0 0 5pt; }}",
    }.get(t.checklist_style)
    if checklist:
        out.append(checklist)

    quote = {
        "indented_rule": f"blockquote {{ border-left: 2pt solid {t.color_rule}; padding-left: 14pt; "
                         f"margin: 12pt 0 12pt 10pt; color: {t.color_text}; font-style: normal; }}",
        "pull_quote": f"blockquote {{ border-left: none; border-top: 2pt solid {t.color_accent}; "
                      f"border-bottom: 2pt solid {t.color_accent}; padding: 10pt 0; margin: 16pt 0; "
                      f"font-size: {t.body_size_pt + 2:.1f}pt; color: {t.color_primary}; font-weight: 700; "
                      f"font-style: normal; }}",
        "centered_italic": f"blockquote {{ border-left: none; text-align: center; font-style: italic; "
                           f"color: {t.color_primary}; margin: 16pt 24pt; "
                           f"font-size: {t.body_size_pt + 0.5:.1f}pt; }}",
        "oversized_marks": f"blockquote {{ border-left: none; background: {t.callout_bg}; padding: 14pt 16pt; "
                           f"font-size: {t.body_size_pt + 2:.1f}pt; font-weight: 700; color: {t.color_primary}; "
                           f"font-style: normal; margin: 16pt 0; }}",
        "drop_cap": f"blockquote {{ border-left: none; border-top: 1pt solid {t.color_rule}; "
                    f"border-bottom: 1pt solid {t.color_rule}; font-style: italic; text-align: left; "
                    f"color: {t.color_text}; margin: 18pt 0; padding: 10pt 0 10pt 22pt; }}",
        "block_citation": f"blockquote {{ border-left: 3pt solid {t.color_muted}; background: #fafafa; "
                          f"padding: 8pt 12pt; font-size: {max(t.min_font_pt, t.body_size_pt - 1):.1f}pt; "
                          f"font-style: normal; }}",
    }.get(t.quote_style)
    if quote:
        out.append(quote)

    # Captions: figure captions only. `.caption` is also the title page's
    # audience line and the copyright notice -- a filled caption style applied
    # to that class turned a copyright page into a full-width black bar.
    strip_ink = readable_ink(t.color_primary, dark=t.color_text)
    caption = {
        "small_italic_left": f"figcaption, .va-caption {{ text-align: left; "
                             f"font-size: {max(t.min_font_pt, 9.0):.1f}pt; }}",
        "caps_label_above": f"figcaption, .va-caption {{ font-style: normal; font-weight: 700; "
                            f"font-size: {max(t.min_font_pt, 9.0):.1f}pt; color: {t.color_primary}; }}",
        "centered_soft": f"figcaption, .va-caption {{ text-align: center; "
                         f"color: {accessible_ink(t.color_muted, page)}; font-style: italic; }}",
        "bold_strip": f"figcaption, .va-caption {{ font-style: normal; font-weight: 700; color: {strip_ink}; "
                      f"background: {t.color_primary}; padding: 4pt 6pt; }}",
        "figure_number": f"figcaption, .va-caption {{ font-style: normal; "
                         f"font-size: {max(t.min_font_pt, 9.0):.1f}pt; color: {t.color_text}; "
                         f"border-top: 1pt solid {t.color_rule}; padding-top: 3pt; }}",
    }.get(t.caption_style)
    if caption:
        out.append(caption)

    # Pictures: the frame goes on the figure block, which draws. A border on
    # the <img> itself is not drawn by this renderer at all.
    image = {
        "full_width": ".ebook-figure { text-align: center; margin: 18pt 0 20pt; padding: 0; }",
        "rounded": ".ebook-figure { text-align: center; margin: 14pt 0 22pt; padding: 0 22pt; }",
        "framed": f".ebook-figure {{ border-top: 1pt solid {t.color_rule}; "
                  f"border-bottom: 1pt solid {t.color_rule}; padding: 12pt 0; "
                  f"text-align: center; margin: 22pt 0 24pt; }}",
        "edge_block": ".ebook-figure { text-align: left; margin: 14pt 0 18pt; padding: 0 60pt 0 0; }",
        "numbered_figure": ".ebook-figure { text-align: left; margin: 12pt 0 20pt; padding: 0 0 0 10pt; }",
    }.get(t.image_style)
    if image:
        out.append(image)

    # Tables: the visible grid is drawn from HTML attributes in
    # ebook_book_layout (this renderer ignores CSS borders on cells). CSS here
    # only carries the header fill, whose ink is measured.
    header_ink = readable_ink(t.color_primary, dark=t.color_text)
    table = {
        "hairline_rows": f"table th {{ background: {t.table_header_bg}; color: {small_primary}; }}",
        "banded": f"table th {{ background: {t.callout_bg}; color: {t.color_text}; font-weight: 800; }}",
        "thick_header": f"table th {{ background: {t.color_primary}; color: {header_ink}; font-weight: 800; }}",
        "minimal": f"table th {{ background: {t.callout_bg}; color: {t.color_text}; }}",
        "full_grid": f"table th {{ background: {t.callout_bg}; color: {t.color_text}; }}",
    }.get(t.table_style)
    if table:
        out.append(table)

    # Running footer: this renderer ignores text-align inside the footer frame
    # and the id rule outranks a class rule, so only colour and weight -- set
    # at the same specificity -- actually reach the page.
    furniture = {
        "title_left": f"#page-footer .foot-title {{ color: {t.color_muted}; font-weight: 400; }}\n"
                      f"#page-footer .foot-num {{ color: {t.color_text}; font-weight: 400; }}",
        "chapter_right_bar": f"#page-footer .foot-title {{ color: {t.color_muted}; font-weight: 400; }}\n"
                             f"#page-footer .foot-num {{ color: {t.color_accent}; font-weight: 700; }}",
        "centered_soft": f"#page-footer .foot-title {{ color: {t.color_muted}; font-style: italic; }}\n"
                         f"#page-footer .foot-sep {{ color: {t.color_rule}; }}",
        "number_tab": f"#page-footer .foot-num {{ color: {t.color_primary}; font-weight: 800; }}\n"
                      f"#page-footer .foot-title {{ color: {t.color_muted}; }}",
        "small_caps_centered": f"#page-footer .foot-title {{ color: {t.color_primary}; font-style: italic; }}\n"
                               f"#page-footer .foot-num {{ color: {t.color_muted}; font-style: italic; }}",
        "section_split": f"#page-footer .foot-title {{ color: {t.color_primary}; font-weight: 700; }}\n"
                         f"#page-footer .foot-sep {{ color: {t.color_accent}; }}\n"
                         f"#page-footer .foot-num {{ color: {t.color_text}; font-weight: 700; }}",
    }.get(t.page_furniture)
    if furniture:
        out.append(furniture)

    if not out:
        return ""
    return "\n/* --- template structure (v1.9.0) --- */\n" + "\n".join(out) + "\n"


def theme_sample_html(theme_id: str | None) -> str:
    """Local theme preview snippet. No paid calls. Does not use live manuscript text."""
    t = get_theme(theme_id)
    css = theme_css(t.theme_id)
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><style>{css}</style></head>'
        "<body>"
        '<section class="title-page">'
        f'<p class="chapter-num">{t.display_name}</p>'
        '<h1 class="book-title">Theme preview</h1>'
        f"<p>Body text at {t.body_size_pt}pt with line-height {t.line_height}. "
        "Headings, tables, checklists, workflows, and callouts share this palette.</p>"
        "</section><section>"
        '<div class="chapter-opener-block">'
        '<p class="chapter-num">Chapter 1</p>'
        '<h2 class="chapter-title">Chapter opening</h2>'
        "</div>"
        "<p>The first paragraph stays with the heading so openings are not isolated titles.</p>"
        '<table class="ebook-table"><thead><tr><th>Item</th><th>Notes</th></tr></thead>'
        "<tbody><tr><td>Sample row</td><td>Styled table</td></tr></tbody></table>"
        '<p class="caption">Table caption in muted type.</p>'
        '<ul class="checklist"><li>Checklist item one</li><li>Checklist item two</li></ul>'
        "<ol class=\"workflow\"><li>Numbered workflow step</li><li>Next controlled step</li></ol>"
        '<div class="callout">Callout box with restrained accent.</div>'
        # v1.9.0. A quotation and a figure so the chooser preview shows every
        # part a template actually changes -- a customer comparing two cards
        # should see the difference, not be told about it. The figure uses a
        # tiny inline SVG: no file, no download, no paid call.
        "<blockquote>A short quotation, styled the way this template treats "
        "quotations.</blockquote>"
        '<figure class="ebook-figure">'
        '<img alt="Picture placement example" src="data:image/svg+xml;utf8,'
        "%3Csvg xmlns='http://www.w3.org/2000/svg' width='320' height='150'%3E"
        "%3Crect width='320' height='150' fill='%23dddddd'/%3E%3C/svg%3E\" />"
        '<figcaption>How this template places and captions a picture.</figcaption>'
        "</figure>"
        "</section></body></html>"
    )
