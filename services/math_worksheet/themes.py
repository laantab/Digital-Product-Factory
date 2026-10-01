"""Printable Math Worksheet themes.

Themes are intentionally small and product-owned: each resolves typography,
ink, accents and the alternating problem-row fill. The default preserves the
long-standing worksheet appearance for old saved projects.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from services.math_worksheet.pdf_fonts import ensure_math_fonts


@dataclass(frozen=True)
class MathWorksheetTheme:
    key: str
    label: str
    regular_font: str
    bold_font: str
    italic_font: str
    ink: str
    muted: str
    accent: str
    secondary: str
    row_fill: str
    rule: str
    cover_fill: str
    problem_row_height: float
    problem_font_size: float
    heading_font_size: float


@lru_cache(maxsize=1)
def _serif_fonts() -> tuple[str, str, str]:
    """Register the bundled SIL OFL Liberation Serif faces; never use OS fonts."""
    base = Path(__file__).resolve().parents[1] / "fonts"
    names = ("MathWorksheetSerif", "MathWorksheetSerif-Bold", "MathWorksheetSerif-Italic")
    files = ("LiberationSerif-Regular.ttf", "LiberationSerif-Bold.ttf", "LiberationSerif-Italic.ttf")
    sans = ensure_math_fonts()
    for name, filename in zip(names, files):
        if name not in pdfmetrics.getRegisteredFontNames():
            path = base / filename
            if not path.is_file():
                return sans
            pdfmetrics.registerFont(TTFont(name, str(path)))
    return names


def resolve_math_worksheet_theme(value: str | None) -> MathWorksheetTheme:
    """Normalize customer labels/keys and safely default old records to Classic."""
    raw = str(value or "classic_classroom").strip().casefold().replace("-", " ").replace("_", " ")
    if raw in {"calm focus", "calmfocus"}:
        key = "calm_focus"
    elif raw in {"bright practice", "brightpractice"}:
        key = "bright_practice"
    else:
        key = "classic_classroom"

    sans, sans_bold, sans_italic = ensure_math_fonts()
    if key == "calm_focus":
        return MathWorksheetTheme(
            key, "Calm Focus", sans, sans_bold, sans_italic,
            "#183B56", "#435B6C", "#147D92", "#3A8D83",
            "#EEF6F8", "#A8C7D0", "#E7F2F4",
            48.0, 12.0, 17.0,
        )
    if key == "bright_practice":
        serif, serif_bold, serif_italic = _serif_fonts()
        return MathWorksheetTheme(
            key, "Bright Practice", serif, serif_bold, serif_italic,
            "#30271E", "#625443", "#A84C12", "#497345",
            "#FFF7E8", "#D6B87A", "#FFF3D7",
            48.0, 12.0, 18.0,
        )
    return MathWorksheetTheme(
        "classic_classroom", "Classic Classroom", sans, sans_bold, sans_italic,
        "#374151", "#4B5563", "#374151", "#059669",
        "#F9FAFB", "#D1D5DB", "#F3F4F6",
        36.0, 11.0, 16.0,
    )


def math_worksheet_theme_choices() -> list[tuple[str, str]]:
    return [
        ("classic_classroom", "Classic Classroom"),
        ("calm_focus", "Calm Focus"),
        ("bright_practice", "Bright Practice"),
    ]
