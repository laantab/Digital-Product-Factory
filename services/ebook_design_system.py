"""Reusable ebook design themes (typography, spacing, page roles).

Themes control fonts, sizes, line-height, margins, headers/footers, palette,
tables, callouts, chapter openers. CSS must never set letter-spacing for PDF
(xhtml2pdf glyph advance bug).
"""
from __future__ import annotations

from dataclasses import dataclass, field
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
        version="studio-v1",
        display_name="Studio Clean",
        font_body="EbookSans, Georgia, serif",
        font_heading="EbookSans, Georgia, serif",
        color_primary="#0f766e",
        color_accent="#0d9488",
        color_text="#1e293b",
        color_muted="#64748b",
        color_rule="#ccfbf1",
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
    ),
    "ink_editorial": EbookTheme(
        theme_id="ink_editorial",
        version="studio-v1",
        display_name="Ink Editorial",
        font_body="EbookSans, Georgia, serif",
        font_heading="EbookSans, Georgia, serif",
        color_primary="#1e3a5f",
        color_accent="#b45309",
        color_text="#1c1917",
        color_muted="#78716c",
        color_rule="#e7e5e4",
        body_size_pt=11.0,
        line_height=1.6,
        h1_size_pt=30.0,
        h2_size_pt=21.0,
        h3_size_pt=14.0,
        margin_in=0.8,
        paragraph_spacing_em=0.9,
        chapter_opener="rule_under",
        table_header_bg="#fafaf9",
        callout_bg="#fffbeb",
    ),
}


def get_theme(theme_id: str | None) -> EbookTheme:
    return THEMES.get(theme_id or "", THEMES["studio_clean"])


def theme_css(theme_id: str | None) -> str:
    """Return theme CSS fragment safe for HTML preview and PDF (no letter-spacing)."""
    t = get_theme(theme_id)
    return t.css_vars() + f"""
body {{
  font-family: {t.font_body};
  color: {t.color_text};
  font-size: {t.body_size_pt}pt;
  line-height: {t.line_height};
}}
h1, h2, h3, .chapter-title {{
  font-family: {t.font_heading};
  color: {t.color_primary};
}}
h1 {{ font-size: {t.h1_size_pt}pt; margin: 0 0 0.4em; }}
h2, .chapter-title {{
  font-size: {t.h2_size_pt}pt;
  margin: 0 0 0.75em;
  border-bottom: 2px solid {t.color_rule};
  padding-bottom: 0.35em;
}}
h3 {{ font-size: {t.h3_size_pt}pt; margin: 1.1em 0 0.45em; }}
p {{ margin: 0 0 {t.paragraph_spacing_em}em; }}
.chapter-num {{
  font-size: 10pt;
  font-weight: 700;
  text-transform: uppercase;
  color: {t.color_accent};
  margin: 0 0 6pt;
}}
.va-table th {{ background: {t.table_header_bg}; }}
.callout, .visual-aid {{
  background: {t.callout_bg};
  border-left: 3px solid {t.color_accent};
  padding: 10pt 12pt;
  margin: 12pt 0;
}}
.page-foot {{
  color: {t.color_muted};
  font-size: 9pt;
  margin-top: 24pt;
  border-top: 1px solid {t.color_rule};
  padding-top: 6pt;
}}
"""


LAYOUT_GUARDS = {
    "no_letter_spacing": True,
    "min_font_pt": 9.0,
    "measured_pagination": True,  # prefer rendered measurement over char estimates
    "orphan_heading_guard": True,
    "safe_margins_in": 0.6,
}
