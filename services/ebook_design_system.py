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
        version="studio-v3",
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
    ),
    "editorial_professional": EbookTheme(
        theme_id="editorial_professional",
        version="editorial-v2",
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
    ),
    "modern_practical": EbookTheme(
        theme_id="modern_practical",
        version="practical-v2",
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
    ),
    "bold_creator": EbookTheme(
        theme_id="bold_creator",
        version="bold-creator-v1",
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
    ),
    "bright_workbook": EbookTheme(
        theme_id="bright_workbook",
        version="bright-workbook-v1",
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
        chapter_opener="friendly_tab",
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
    ),
    "warm_wellness": EbookTheme(
        theme_id="warm_wellness",
        version="warm-wellness-v1",
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
    return t.css_vars() + _shared_book_css(t)


def _shared_book_css(t: EbookTheme) -> str:
    accent2 = t.color_accent_2 or t.color_accent
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
  background: {t.color_primary};
  border-bottom: 5pt solid {accent2};
  color: #ffffff;
  padding: 16pt 18pt 13pt;
  margin: 0 0 16pt;
  page-break-inside: avoid;
  page-break-after: avoid;
}}
.chapter-opener-block .chapter-num {{ color: #ffffff; opacity: 0.9; margin-bottom: 6pt; }}
.chapter-opener-block .chapter-title, .chapter-opener-block h2 {{
  color: #ffffff;
  border-bottom: none !important;
  margin: 0;
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
  color: {t.color_muted};
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
  color: {t.color_accent};
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
  color: #ffffff;
  background: {t.color_primary};
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
  color: {t.color_accent};
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
  color: #ffffff;
  background: {t.color_accent};
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
  border: 3pt solid {t.color_accent};
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
  color: {t.color_muted};
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
  color: #ffffff;
  background: {t.color_primary};
  padding: 1pt 7pt;
  margin-right: 6pt;
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
  color: {t.color_accent};
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
  margin: {t.margin_in}in;
  @frame footer_frame {{
    -pdf-frame-content: page-footer;
    left: {t.margin_in}in;
    top: 10.05in;
    width: {8.5 - 2 * float(t.margin_in)}in;
    height: 0.35in;
  }}
}}
#page-footer {{
  font-family: {t.font_body};
  font-size: {t.footer_size_pt}pt;
  color: {t.color_muted};
  border-top: 0.5pt solid {t.color_rule};
  padding-top: 4pt;
}}
#page-footer .foot-title, #page-footer .foot-sep, #page-footer .foot-num {{
  font-size: {t.footer_size_pt}pt; color: {t.color_muted};
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
h4 {{ font-size: 12pt; margin: 1.2em 0 0.45em; color: {t.color_accent}; page-break-after: avoid; }}
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
  color: {t.color_accent};
  margin: 0 0 10pt;
}}
.back-matter-label {{
  font-size: 9.5pt;
  font-weight: 700;
  text-transform: uppercase;
  color: {t.color_muted};
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
  color: {t.color_primary};
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
ul li, ol li {{
  display: block;
  margin: 0 0 7pt;
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
  color: {t.color_accent};
  font-weight: 700;
}}
ol.workflow, .workflow {{
  display: block;
  margin: 10pt 0 16pt 18pt;
  padding: 0;
  page-break-inside: avoid;
}}
ol.workflow li, .workflow li {{
  display: block;
  margin: 0 0 8pt;
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
  color: {t.color_muted};
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
  border: 1pt solid {t.color_rule};
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
  color: {t.color_muted};
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
  color: {t.color_muted};
  font-size: 9pt;
  margin-top: 18pt;
  border-top: 1pt solid {t.color_rule};
  padding-top: 6pt;
}}
.title-page {{ display: block; text-align: center; padding-top: 1.35in; }}
.title-page p {{ margin: 0 0 10pt; }}
.title-sub {{ margin: 0 0 10pt; font-size: 12.5pt; color: {t.color_muted}; }}
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
  color: {t.color_accent};
  font-weight: 700;
}}
.toc-page-num {{
  color: {t.color_muted};
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
        "</section></body></html>"
    )
