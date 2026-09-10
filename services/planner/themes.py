"""Design themes for the planner engine.

A theme is a set of *tokens* -- colours, type faces, header style, ornament,
line style -- that every page component reads from. The renderer never picks a
colour or a font itself; it asks the theme. That is what lets five very
different-looking planners come out of one code path, and what stops copy-paste
drift between page kinds: change a token and every page moves together.

Themes are selected by key (``design_theme`` on the request) without a code
edit. Unknown keys fall back to the planner type's default and record a warning
rather than failing the build.

Colours are hex strings so a theme reads like a style sheet. ``rgb()`` turns a
token into a ReportLab colour; ``rgb255()`` gives the PIL tuple the cover-art
engine wants.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache

from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from services.math_worksheet.pdf_fonts import ensure_math_fonts

FAITH = "faith_planner"
BUDGET = "budget_planner"

HEADER_STYLES = ("band", "rule", "soft")
ORNAMENTS = ("diamond", "line", "leaf", "chevron", "sun")
LINE_STYLES = ("ruled", "dotted")
COVER_STYLES = ("full_photo", "photo_panel", "soft_overlay", "minimal_texture")


# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #
_SERIF = "PlannerSerif"
_SERIF_BOLD = "PlannerSerif-Bold"
_SERIF_ITALIC = "PlannerSerif-Italic"
_SERIF_BOLD_ITALIC = "PlannerSerif-BoldItalic"


def _fonts_dir() -> str:
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fonts")


@lru_cache(maxsize=1)
def ensure_planner_fonts() -> dict[str, str]:
    """Register the redistributable Liberation family once.

    Returns a map of role -> registered font name. Liberation Serif and Sans are
    SIL OFL 1.1 (see ``services/fonts/FONT-PROVENANCE.md``), so both may be
    embedded in a product that is sold. If the serif files are missing the
    serif roles fall back to the sans faces rather than to a non-embeddable
    system font.
    """
    sans, sans_bold, sans_italic = ensure_math_fonts()
    registered = set(pdfmetrics.getRegisteredFontNames())
    fdir = _fonts_dir()
    files = {
        _SERIF: "LiberationSerif-Regular.ttf",
        _SERIF_BOLD: "LiberationSerif-Bold.ttf",
        _SERIF_ITALIC: "LiberationSerif-Italic.ttf",
        _SERIF_BOLD_ITALIC: "LiberationSerif-BoldItalic.ttf",
    }
    for name, fname in files.items():
        path = os.path.join(fdir, fname)
        if name not in registered and os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont(name, path))
            except Exception:  # noqa: BLE001
                pass
    registered = set(pdfmetrics.getRegisteredFontNames())

    def pick(name: str, fallback: str) -> str:
        return name if name in registered else fallback

    return {
        "sans": sans,
        "sans_bold": sans_bold,
        "sans_italic": sans_italic,
        "serif": pick(_SERIF, sans),
        "serif_bold": pick(_SERIF_BOLD, sans_bold),
        "serif_italic": pick(_SERIF_ITALIC, sans_italic),
        "serif_bold_italic": pick(_SERIF_BOLD_ITALIC, sans_bold),
    }


def font_file_for(role: str) -> str:
    """Path of the TTF behind a role, for the PIL cover-art engine."""
    fdir = _fonts_dir()
    mapping = {
        "sans": "LiberationSans-Regular.ttf",
        "sans_bold": "LiberationSans-Bold.ttf",
        "sans_italic": "LiberationSans-Italic.ttf",
        "serif": "LiberationSerif-Regular.ttf",
        "serif_bold": "LiberationSerif-Bold.ttf",
        "serif_italic": "LiberationSerif-Italic.ttf",
        "serif_bold_italic": "LiberationSerif-BoldItalic.ttf",
    }
    return os.path.join(fdir, mapping.get(role, "LiberationSans-Regular.ttf"))


@dataclass(frozen=True)
class ThemeFonts:
    display: str          # headings, cover title
    display_italic: str   # subtitles, reflective prompts
    body: str             # running text
    body_bold: str        # labels, table headers
    body_italic: str      # captions
    label: str            # small caps labels (bold sans reads best small)


# --------------------------------------------------------------------------- #
# Theme tokens
# --------------------------------------------------------------------------- #
def hex_to_rgb01(value: str) -> tuple[float, float, float]:
    v = str(value or "").strip().lstrip("#")
    if len(v) != 6:
        return (0.0, 0.0, 0.0)
    return tuple(int(v[i:i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def hex_to_rgb255(value: str) -> tuple[int, int, int]:
    r, g, b = hex_to_rgb01(value)
    return (round(r * 255), round(g * 255), round(b * 255))


def luminance(value: str) -> float:
    r, g, b = hex_to_rgb01(value)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


@dataclass(frozen=True)
class PlannerTheme:
    key: str
    label: str
    tagline: str
    planner_types: tuple[str, ...]

    # Paper and text
    paper: str
    ink: str
    muted: str
    # Brand colours
    primary: str        # headings, header band, page numbers
    accent: str         # ornaments, rules of emphasis, badges
    accent_soft: str    # tinted panels
    band: str           # zebra rows, soft header band
    rule: str           # hairlines, table grid
    # Cover
    cover_bg: str
    cover_text: str
    cover_accent: str
    cover_art: str      # procedural art recipe when no photo is supplied
    cover_style_default: str = "soft_overlay"
    pexels_queries: tuple[str, ...] = ()

    # Type and furniture
    display_face: str = "serif"     # "serif" | "sans"
    body_face: str = "sans"
    header_style: str = "band"      # "band" | "rule" | "soft"
    ornament: str = "diamond"
    line_style: str = "ruled"
    corner_radius: float = 6.0

    def fonts(self) -> ThemeFonts:
        f = ensure_planner_fonts()
        if self.display_face == "serif":
            display, display_italic = f["serif_bold"], f["serif_italic"]
        else:
            display, display_italic = f["sans_bold"], f["sans_italic"]
        if self.body_face == "serif":
            body, body_bold, body_italic = f["serif"], f["serif_bold"], f["serif_italic"]
        else:
            body, body_bold, body_italic = f["sans"], f["sans_bold"], f["sans_italic"]
        return ThemeFonts(display, display_italic, body, body_bold, body_italic, f["sans_bold"])

    def rgb(self, token: str) -> colors.Color:
        return colors.Color(*hex_to_rgb01(getattr(self, token)))

    def rgb255(self, token: str) -> tuple[int, int, int]:
        return hex_to_rgb255(getattr(self, token))

    @property
    def cover_is_dark(self) -> bool:
        return luminance(self.cover_bg) < 0.45

    @property
    def is_neutral(self) -> bool:
        """True when the brand colours are greys and taupes rather than hues."""
        r, g, b = hex_to_rgb01(self.primary)
        r2, g2, b2 = hex_to_rgb01(self.accent)
        return (max(r, g, b) - min(r, g, b)) < 0.12 and (max(r2, g2, b2) - min(r2, g2, b2)) < 0.16

    def palette_hex(self) -> list[str]:
        return [self.primary, self.accent, self.accent_soft, self.band, self.rule,
                self.cover_bg, self.cover_accent, self.muted]

    def as_dict(self) -> dict:
        return {
            "key": self.key, "label": self.label, "tagline": self.tagline,
            "header_style": self.header_style, "ornament": self.ornament,
            "display_face": self.display_face, "body_face": self.body_face,
            "line_style": self.line_style, "cover_style_default": self.cover_style_default,
            "colors": {
                "paper": self.paper, "ink": self.ink, "muted": self.muted,
                "primary": self.primary, "accent": self.accent,
                "accent_soft": self.accent_soft, "band": self.band, "rule": self.rule,
                "cover_bg": self.cover_bg, "cover_text": self.cover_text,
                "cover_accent": self.cover_accent,
            },
        }


WARM_GRACE = PlannerTheme(
    key="warm_grace", label="Warm Grace",
    tagline="Soft neutrals, warm burgundy, muted gold. Classic devotional warmth.",
    planner_types=(FAITH,),
    paper="#FFFDF9", ink="#2B2321", muted="#7B6F69",
    primary="#762F3B", accent="#C6A15B", accent_soft="#F5EBDD",
    band="#F5EBDF", rule="#DCCAB4",
    cover_bg="#6B2734", cover_text="#FBF4EA", cover_accent="#D9B56C",
    cover_art="claret_glow", cover_style_default="soft_overlay",
    pexels_queries=("open bible warm light linen", "candle light soft warm still life",
                    "morning light window calm"),
    display_face="serif", body_face="sans", header_style="band",
    ornament="diamond", line_style="ruled",
)

MODERN_MINIMAL = PlannerTheme(
    key="modern_minimal", label="Modern Minimal Faith",
    tagline="Black, grey and soft taupe. Spacious, modern, premium.",
    planner_types=(FAITH,),
    paper="#FFFFFF", ink="#1E1E1E", muted="#6E6A66",
    primary="#2A2826", accent="#A99E8F", accent_soft="#F2EFEA",
    band="#F1EDE7", rule="#C9C2B9",
    cover_bg="#EFEBE5", cover_text="#1E1E1E", cover_accent="#8E8477",
    cover_art="taupe_paper", cover_style_default="minimal_texture",
    pexels_queries=("minimal neutral linen texture", "white stone architecture light",
                    "open notebook neutral desk"),
    display_face="sans", body_face="sans", header_style="rule",
    ornament="line", line_style="dotted", corner_radius=3.0,
)

FLORAL_DEVOTION = PlannerTheme(
    key="floral_devotion", label="Floral Devotion",
    tagline="Soft botanicals, blush and sage. Gentle and uplifting.",
    planner_types=(FAITH,),
    paper="#FFFDFC", ink="#3B2F35", muted="#8B7B82",
    primary="#9A5A6F", accent="#7D9B80", accent_soft="#F8EDF0",
    band="#F6EAEE", rule="#E5D0D7",
    cover_bg="#F3DFE4", cover_text="#4A3239", cover_accent="#7D9B80",
    cover_art="blush_botanical", cover_style_default="photo_panel",
    pexels_queries=("soft pink flowers pastel", "eucalyptus botanical flat lay",
                    "wildflowers soft light meadow"),
    display_face="serif", body_face="sans", header_style="soft",
    ornament="leaf", line_style="ruled", corner_radius=8.0,
)

FAMILY_HERITAGE = PlannerTheme(
    key="family_heritage", label="Family Heritage",
    tagline="Rich earth tones. Grounded, mature, made for a household.",
    planner_types=(FAITH,),
    paper="#FFFCF7", ink="#2D2520", muted="#756A5F",
    primary="#5A3A2A", accent="#B5822F", accent_soft="#F1E7D7",
    band="#F2E8D9", rule="#D9C9B3",
    cover_bg="#3B2A20", cover_text="#F6EFE4", cover_accent="#C9944A",
    cover_art="walnut_grain", cover_style_default="photo_panel",
    pexels_queries=("family hands together warm", "wooden table bible coffee",
                    "autumn field golden hour"),
    display_face="serif", body_face="sans", header_style="band",
    ornament="chevron", line_style="ruled", corner_radius=4.0,
)

JOYFUL_LIGHT = PlannerTheme(
    key="joyful_light", label="Joyful Light",
    tagline="Bright, hopeful and airy. Cheerful without being childish.",
    planner_types=(FAITH,),
    paper="#FFFFFF", ink="#25303B", muted="#6C7987",
    primary="#2C6D9C", accent="#F0B646", accent_soft="#EAF4FB",
    band="#E8F1F8", rule="#B9D0E0",
    cover_bg="#D8E9F5", cover_text="#1D3A52", cover_accent="#F0B646",
    cover_art="sunrise_sky", cover_style_default="full_photo",
    pexels_queries=("sunrise sky soft clouds", "sunflowers blue sky bright",
                    "light through trees hopeful"),
    display_face="sans", body_face="sans", header_style="soft",
    ornament="sun", line_style="dotted", corner_radius=8.0,
)

# The Budget Planner keeps its established teal-and-brass identity, now drawn
# through the same component system. It is not a faith theme and is never
# offered for the Faith Planner.
LEDGER = PlannerTheme(
    key="ledger", label="Ledger",
    tagline="Deep teal and brass. The Budget Planner's house style.",
    planner_types=(BUDGET,),
    paper="#FFFFFF", ink="#1F2624", muted="#66716E",
    primary="#0B3C37", accent="#D7BC5C", accent_soft="#EEF5F2",
    band="#E9F2EE", rule="#BFD3CD",
    cover_bg="#0B3C37", cover_text="#F4F7F6", cover_accent="#E8C967",
    cover_art="teal_ledger", cover_style_default="minimal_texture",
    display_face="sans", body_face="sans", header_style="band",
    ornament="line", line_style="ruled", corner_radius=4.0,
)

THEMES: dict[str, PlannerTheme] = {
    t.key: t for t in (WARM_GRACE, MODERN_MINIMAL, FLORAL_DEVOTION,
                       FAMILY_HERITAGE, JOYFUL_LIGHT, LEDGER)
}

DEFAULT_THEME = {FAITH: WARM_GRACE.key, BUDGET: LEDGER.key}

_ALIASES = {
    "warm grace": "warm_grace", "grace": "warm_grace", "classic": "warm_grace",
    "modern minimal faith": "modern_minimal", "modern minimal": "modern_minimal",
    "minimal": "modern_minimal", "modern": "modern_minimal",
    "floral devotion": "floral_devotion", "floral": "floral_devotion",
    "botanical": "floral_devotion",
    "family heritage": "family_heritage", "heritage": "family_heritage",
    "earth": "family_heritage",
    "joyful light": "joyful_light", "joyful": "joyful_light", "light": "joyful_light",
    "bright": "joyful_light",
    "ledger": "ledger", "budget": "ledger",
}


def normalize_theme_key(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    if raw in THEMES:
        return raw
    if raw in _ALIASES:
        return _ALIASES[raw]
    collapsed = raw.replace("-", "_").replace(" ", "_")
    if collapsed in THEMES:
        return collapsed
    return raw


def resolve_theme(value: str, planner_type: str) -> tuple[PlannerTheme, str]:
    """Return (theme, warning). Never raises: a bad key falls back to the
    planner type's default and says so, because a customer-facing build must
    not fail over a spelling."""
    default_key = DEFAULT_THEME.get(planner_type, WARM_GRACE.key)
    key = normalize_theme_key(value)
    if not key:
        return THEMES[default_key], ""
    theme = THEMES.get(key)
    if theme is None:
        return THEMES[default_key], (
            f"Unknown design theme {value!r}; used {THEMES[default_key].label}.")
    if planner_type not in theme.planner_types:
        return THEMES[default_key], (
            f"Design theme {theme.label!r} is not offered for {planner_type}; "
            f"used {THEMES[default_key].label}.")
    return theme, ""


def theme_choices(planner_type: str) -> list[tuple[str, str]]:
    """(key, label) pairs offered for a planner type, default first."""
    default_key = DEFAULT_THEME.get(planner_type, "")
    out = [(t.key, t.label) for t in THEMES.values() if planner_type in t.planner_types]
    out.sort(key=lambda kv: (kv[0] != default_key, kv[1]))
    return out


def normalize_cover_style(value: str, theme: PlannerTheme) -> tuple[str, str]:
    raw = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "photo": "full_photo", "full": "full_photo", "full_photo_cover": "full_photo",
        "panel": "photo_panel", "photo_+_text_panel": "photo_panel",
        "photo_and_text_panel": "photo_panel", "photo_text_panel": "photo_panel",
        "overlay": "soft_overlay", "soft_image_with_overlay": "soft_overlay",
        "soft": "soft_overlay",
        "minimal": "minimal_texture", "texture": "minimal_texture",
        "elegant_minimal": "minimal_texture", "elegant_minimal_cover": "minimal_texture",
    }
    raw = aliases.get(raw, raw)
    if raw in ("theme_default", "default", "auto"):
        raw = ""
    if not raw:
        return theme.cover_style_default, ""
    if raw not in COVER_STYLES:
        return theme.cover_style_default, (
            f"Unknown cover style {value!r}; used {theme.cover_style_default}.")
    return raw, ""


# Shared spacing rules -- one place, so every page agrees.
@dataclass(frozen=True)
class Spacing:
    margin: float = 0.62 * 72.0        # side margins
    top_inset: float = 0.30 * 72.0     # where the header chrome begins
    footer_h: float = 0.42 * 72.0      # footer zone height
    gutter: float = 14.0               # between columns / cards
    line: float = 20.0                 # writing-line pitch
    line_tight: float = 18.0
    section_gap: float = 16.0
    card_pad: float = 12.0


SPACING = Spacing()
