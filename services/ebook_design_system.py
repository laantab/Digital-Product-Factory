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
    chapter_opener: str  # stacked_label | rule_under | minimal
    table_header_bg: str
    callout_bg: str
    min_font_pt: float = 9.0
    page_bg: str = "#ffffff"
    summary: str = ""

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
    "studio_clean": EbookTheme(
        theme_id="studio_clean",
        version="studio-v2",
        display_name="Studio Clean",
        font_body="EbookSans, Georgia, 'Times New Roman', serif",
        font_heading="EbookSans, Georgia, 'Times New Roman', serif",
        color_primary="#0f766e",
        color_accent="#0d9488",
        color_text="#1e293b",
        color_muted="#64748b",
        color_rule="#99f6e4",
        body_size_pt=11.0,
        line_height=1.55,
        h1_size_pt=28.0,
        h2_size_pt=20.0,
        h3_size_pt=14.0,
        margin_in=0.75,
        paragraph_spacing_em=0.85,
        chapter_opener="stacked_label",
        table_header_bg="#f0fdfa",
        callout_bg="#ecfdf5",
        summary="Calm teal studio look with clear hierarchy and open tables.",
    ),
    "editorial_professional": EbookTheme(
        theme_id="editorial_professional",
        version="editorial-v1",
        display_name="Editorial Professional",
        font_body="EbookSans, Georgia, 'Times New Roman', serif",
        font_heading="EbookSans, Georgia, 'Times New Roman', serif",
        color_primary="#1e3a5f",
        color_accent="#b45309",
        color_text="#1c1917",
        color_muted="#78716c",
        color_rule="#e7e5e4",
        body_size_pt=11.0,
        line_height=1.62,
        h1_size_pt=30.0,
        h2_size_pt=21.0,
        h3_size_pt=14.0,
        margin_in=0.8,
        paragraph_spacing_em=0.9,
        chapter_opener="rule_under",
        table_header_bg="#fafaf9",
        callout_bg="#fffbeb",
        summary="Ink-and-paper editorial palette with ruled chapter openings.",
    ),
    "modern_practical": EbookTheme(
        theme_id="modern_practical",
        version="practical-v1",
        display_name="Modern Practical Guide",
        font_body="EbookSans, Calibri, Arial, sans-serif",
        font_heading="EbookSans, Calibri, Arial, sans-serif",
        color_primary="#1d4ed8",
        color_accent="#0369a1",
        color_text="#0f172a",
        color_muted="#475569",
        color_rule="#bfdbfe",
        body_size_pt=11.0,
        line_height=1.52,
        h1_size_pt=26.0,
        h2_size_pt=18.0,
        h3_size_pt=13.5,
        margin_in=0.7,
        paragraph_spacing_em=0.8,
        chapter_opener="minimal",
        table_header_bg="#eff6ff",
        callout_bg="#f0f9ff",
        summary="Practical field-guide spacing with blue rules and dense-but-readable tables.",
    ),
}

# Backward-compatible alias used by older factory packages.
THEMES["ink_editorial"] = THEMES["editorial_professional"]

PROFESSIONAL_THEME_IDS = ("studio_clean", "editorial_professional", "modern_practical")


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
    opener_h2 = {
        "stacked_label": f"border-bottom: 2pt solid {t.color_rule}; padding-bottom: 0.28em;",
        "rule_under": f"border-bottom: 1.5pt solid {t.color_primary}; padding-bottom: 0.32em;",
        "minimal": "border-bottom: none; padding-bottom: 0.12em;",
    }.get(t.chapter_opener, f"border-bottom: 2pt solid {t.color_rule}; padding-bottom: 0.28em;")
    return f"""
@page {{
  size: letter;
  margin: {t.margin_in}in;
}}
body {{
  font-family: {t.font_body};
  color: {t.color_text};
  font-size: {t.body_size_pt}pt;
  line-height: {t.line_height};
  background: {t.page_bg};
}}
h1, h2, h3, h4, .chapter-title, .book-title {{
  font-family: {t.font_heading};
  color: {t.color_primary};
  page-break-after: avoid;
}}
h1, .book-title {{ font-size: {t.h1_size_pt}pt; margin: 0 0 0.4em; line-height: 1.2; }}
h2, .chapter-title {{
  font-size: {t.h2_size_pt}pt;
  margin: 0 0 0.55em;
  line-height: 1.25;
  {opener_h2}
}}
h3 {{ font-size: {t.h3_size_pt}pt; margin: 1.05em 0 0.4em; }}
h4 {{ font-size: 12pt; margin: 0.9em 0 0.35em; color: {t.color_accent}; }}
p {{ margin: 0 0 {t.paragraph_spacing_em}em; }}
.chapter-num {{
  font-size: 9.5pt;
  font-weight: 700;
  text-transform: uppercase;
  color: {t.color_accent};
  margin: 0 0 6pt;
}}
.back-matter-label {{
  font-size: 9.5pt;
  font-weight: 700;
  text-transform: uppercase;
  color: {t.color_muted};
  margin: 0 0 6pt;
}}
table, .ebook-table, .va-table {{
  border-collapse: collapse;
  width: 100%;
  margin: 10pt 0 14pt;
  page-break-inside: avoid;
}}
th, td {{
  border: 1pt solid {t.color_rule};
  padding: 6pt 8pt;
  text-align: left;
  font-size: 9.5pt;
  vertical-align: top;
}}
th {{
  background: {t.table_header_bg};
  color: {t.color_primary};
  font-weight: 700;
}}
ul.checklist, .checklist {{
  list-style: none;
  margin: 8pt 0 14pt 0;
  padding: 0;
}}
ul.checklist li, .checklist li {{
  margin: 5pt 0;
  padding-left: 16pt;
  border-left: 3pt solid {t.color_accent};
}}
ol.workflow, .workflow {{
  margin: 8pt 0 14pt 18pt;
  padding: 0;
}}
ol.workflow li, .workflow li {{
  margin: 6pt 0;
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
.sources-list, .source-ref {{
  font-size: 9.5pt;
  color: {t.color_muted};
}}
.sources-list li {{ margin: 4pt 0; }}
.page-foot, .running-footer {{
  color: {t.color_muted};
  font-size: 9pt;
  margin-top: 18pt;
  border-top: 1pt solid {t.color_rule};
  padding-top: 6pt;
}}
.title-page {{ page-break-after: always; text-align: center; padding-top: 1.4in; }}
.legal-page {{ page-break-after: always; }}
.toc-page {{ page-break-after: always; }}
.chapter-page {{ page-break-before: always; -pdf-page-break: before; }}
.back-matter-page {{ page-break-before: always; -pdf-page-break: before; }}
.toc-list {{ list-style: none; margin: 0; padding: 0; }}
.toc-list li {{ padding: 7pt 0; border-bottom: 1pt solid {t.color_rule}; }}
.toc-list a {{ color: {t.color_primary}; text-decoration: none; font-weight: 700; }}
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
        '<p class="chapter-num">Chapter 1</p>'
        '<h2 class="chapter-title">Chapter opening</h2>'
        "<p>The first paragraph stays with the heading so openings are not isolated titles.</p>"
        '<table class="ebook-table"><thead><tr><th>Item</th><th>Notes</th></tr></thead>'
        "<tbody><tr><td>Sample row</td><td>Styled table</td></tr></tbody></table>"
        '<p class="caption">Table caption in muted type.</p>'
        '<ul class="checklist"><li>Checklist item one</li><li>Checklist item two</li></ul>'
        "<ol class=\"workflow\"><li>Numbered workflow step</li><li>Next controlled step</li></ol>"
        '<div class="callout">Callout box with restrained accent.</div>'
        "</section></body></html>"
    )
