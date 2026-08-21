"""Cover Design Agent — style decisions, HTML covers, image prompts, PDF parity."""
from __future__ import annotations

import base64
import html
import os
import re
from datetime import datetime, timezone
from typing import Any

from bs4 import BeautifulSoup

EXPORTS_DIR = os.environ.get("FACTORY_EXPORTS_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "exports"
)


def _e(value: Any) -> str:
    return html.escape(str(value or ""))


def _download_url(package_id: str, name: str) -> str:
    return f"/download/{package_id}/{name}"

COVER_VERSION = 21
COVER_IMAGE_SIZE = "1024x1536"

DEFAULT_TEXT_POSITION = {"x": 50.0, "y": 81.0, "align": "center"}

USER_STYLES = (
    "photo_realistic",
    "modern_business",
    "minimal",
    "bold",
    "elegant",
    "illustrated",
    "graphic_icon",
)

LAYOUTS = (
    "image_top_title_bottom",
    "title_top_image_center",
    "full_bleed_image",
    "split_layout",
    "clean_business",
    "large_title_visual_panel",
)

FONT_STYLES = ("modern_sans", "elegant_serif", "bold_display")

_PHOTO_KEYWORDS = (
    "business", "health", "fitness", "food", "cooking", "recipe", "travel", "lifestyle",
    "self-help", "self help", "photography", "family", "children", "parenting", "beauty",
    "wellness", "finance", "marketing", "sales", "etsy", "shopify", "amazon", "marketplace",
    "listing", "ecommerce", "e-commerce", "guide", "how to", "how-to", "startup",
    "entrepreneur", "productivity", "mindset", "coach", "real estate", "garden", "pet",
)

_GRAPHIC_KEYWORDS = (
    "worksheet", "math", "technical manual", "spreadsheet", "checklist template",
    "data report", "chart report", "abstract training", "worksheet pack", "formula sheet",
    "reference card", "flash card", "diagram only", "icon set",
)

_PALETTES: dict[str, dict[str, str]] = {
    "professional_blue": {
        "primary": "#1e3a5f", "secondary": "#2563eb", "accent": "#0ea5e9",
        "text": "#ffffff", "muted": "#cbd5e1", "panel": "#f8fafc",
    },
    "warm_orange": {
        "primary": "#7c2d12", "secondary": "#ea580c", "accent": "#fbbf24",
        "text": "#ffffff", "muted": "#fed7aa", "panel": "#fff7ed",
    },
    "black_gold": {
        "primary": "#0a0a0a", "secondary": "#1c1917", "accent": "#d4af37",
        "text": "#fafaf9", "muted": "#a8a29e", "panel": "#292524",
    },
    "clean_white": {
        "primary": "#ffffff", "secondary": "#f1f5f9", "accent": "#2563eb",
        "text": "#0f172a", "muted": "#64748b", "panel": "#f8fafc",
    },
    "purple_modern": {
        "primary": "#312e81", "secondary": "#7c3aed", "accent": "#059669",
        "text": "#ffffff", "muted": "#c7d2fe", "panel": "#ffffff",
    },
    "earth_tones": {
        "primary": "#44403c", "secondary": "#78716c", "accent": "#a16207",
        "text": "#fafaf9", "muted": "#d6d3d1", "panel": "#fafaf9",
    },
    # Legacy preset ids (backward compatible with saved projects)
    "modern_business": {
        "primary": "#1e3a5f", "secondary": "#2563eb", "accent": "#0ea5e9",
        "text": "#ffffff", "muted": "#cbd5e1", "panel": "#f8fafc",
    },
    "marketplace": {
        "primary": "#312e81", "secondary": "#7c3aed", "accent": "#059669",
        "text": "#ffffff", "muted": "#c7d2fe", "panel": "#ffffff",
    },
    "minimal": {
        "primary": "#0f172a", "secondary": "#475569", "accent": "#64748b",
        "text": "#ffffff", "muted": "#94a3b8", "panel": "#f1f5f9",
    },
    "bold": {
        "primary": "#7c2d12", "secondary": "#ea580c", "accent": "#fbbf24",
        "text": "#ffffff", "muted": "#fed7aa", "panel": "#fff7ed",
    },
    "elegant": {
        "primary": "#1c1917", "secondary": "#78716c", "accent": "#d6d3d1",
        "text": "#fafaf9", "muted": "#d6d3d1", "panel": "#fafaf9",
    },
    "photo_realistic": {
        "primary": "#1e293b", "secondary": "#334155", "accent": "#38bdf8",
        "text": "#ffffff", "muted": "#cbd5e1", "panel": "#f8fafc",
    },
    "graphic_icon": {
        "primary": "#3730a3", "secondary": "#6366f1", "accent": "#a5b4fc",
        "text": "#ffffff", "muted": "#c7d2fe", "panel": "#eef2ff",
    },
    "illustrated": {
        "primary": "#134e4a", "secondary": "#0d9488", "accent": "#5eead4",
        "text": "#ffffff", "muted": "#99f6e4", "panel": "#f0fdfa",
    },
}

_PALETTE_ALIASES: dict[str, str] = {
    "marketplace": "purple_modern",
    "modern_business": "professional_blue",
    "bold": "warm_orange",
    "custom": "custom",
}


def _normalize_palette_preset(preset: str) -> str:
    p = str(preset or "").strip()
    if not p or p == "custom":
        return p
    return _PALETTE_ALIASES.get(p, p)


def _default_palette_preset(title: str, style: str) -> str:
    if any(k in _norm(title) for k in ("etsy", "marketplace", "listing", "ecommerce")):
        return "purple_modern"
    if style == "graphic_icon":
        return "graphic_icon"
    if style in _PALETTES:
        alias = _normalize_palette_preset(style)
        if alias in _PALETTES:
            return alias
    return "professional_blue"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def build_word_search_cover_brief(*args, **kwargs):
    """Re-export — Word Search briefs live in the shared product cover agent."""
    from services.product_cover_agent import build_word_search_cover_brief as _brief

    return _brief(*args, **kwargs)


def project_cover_inputs(project: dict) -> dict[str, Any]:
    """Re-export — project adapters live in the shared product cover agent."""
    from services.product_cover_agent import project_cover_inputs as _inputs

    return _inputs(project)


def analyze_cover_style(
    *,
    title: str,
    content: str = "",
    fields: dict | None = None,
    product_type: str = "",
    product_summary: str = "",
) -> dict[str, Any]:
    """Decide photo-realistic vs graphic/icon cover approach."""
    fields = fields or {}
    puzzle_engine_types = {"word_search_book", "crossword_puzzle_book"}
    if str(product_type or "").strip() in puzzle_engine_types:
        style = str((fields or {}).get("style_preference") or "modern_business")
        if style not in USER_STYLES:
            style = "modern_business"
        label = "Word search" if product_type == "word_search_book" else "Crossword"
        return {
            "style_mode": "photo_realistic",
            "recommended_style": style,
            "recommended_layout": "full_bleed_image",
            "photo_score": 1,
            "graphic_score": 0,
            "reason": f"{label} book cover via the shared product cover agent.",
            "product_type": product_type,
        }

    blob = _norm(
        " ".join(
            [
                title,
                product_type,
                product_summary,
                str(fields.get("audience") or ""),
                str(fields.get("niche") or ""),
                str(fields.get("goal") or ""),
                (content or "")[:4000],
            ]
        )
    )
    photo_score = sum(1 for kw in _PHOTO_KEYWORDS if kw in blob)
    graphic_score = sum(1 for kw in _GRAPHIC_KEYWORDS if kw in blob)
    if graphic_score > photo_score + 1:
        mode = "graphic_icon"
        reason = "Topic reads as instructional/worksheet/report content where clean graphics work best."
    else:
        mode = "photo_realistic"
        reason = "Topic suits a polished, marketplace-ready visual with realistic or photographic appeal."

    style = "graphic_icon" if mode == "graphic_icon" else "modern_business"
    if any(k in blob for k in ("etsy", "marketplace", "listing", "ecommerce", "shop")):
        style = "modern_business"
    if "minimal" in blob or "simple guide" in blob:
        style = "minimal"

    layout = "clean_business" if mode == "photo_realistic" else "split_layout"
    if any(k in blob for k in ("etsy", "listing", "marketplace")):
        layout = "clean_business"

    return {
        "style_mode": mode,
        "recommended_style": style,
        "recommended_layout": layout,
        "photo_score": photo_score,
        "graphic_score": graphic_score,
        "reason": reason,
    }


def _palette_for_style(style: str) -> dict[str, str]:
    if style in _PALETTES:
        return dict(_PALETTES[style])
    return dict(_PALETTES["modern_business"])


def _resolve_palette(style: str, title: str, overrides: dict | None = None) -> dict[str, str]:
    """Pick palette from preset, Etsy/marketplace topic, style, then custom color overrides."""
    overrides = overrides or {}
    preset = _normalize_palette_preset(overrides.get("palette_preset") or overrides.get("palette") or "")
    if preset and preset != "custom" and preset in _PALETTES:
        base = dict(_PALETTES[preset])
    elif any(k in _norm(title) for k in ("etsy", "marketplace", "listing", "ecommerce")):
        base = dict(_PALETTES["purple_modern"])
    else:
        base = _palette_for_style(style)
    custom = overrides.get("color_palette")
    if isinstance(custom, dict):
        base = {**base, **{k: v for k, v in custom.items() if v}}
    return base


_STYLE_MOODS: dict[str, str] = {
    "photo_realistic": "photorealistic, premium editorial ebook cover, soft professional lighting",
    "modern_business": "polished modern business ebook cover, marketplace-ready, trustworthy",
    "minimal": "minimal clean ebook cover, elegant whitespace, refined typography",
    "bold": "bold high-contrast ebook cover, strong hierarchy, energetic",
    "elegant": "elegant refined ebook cover, sophisticated palette, luxury feel",
    "graphic_icon": "modern flat graphic ebook cover with simple icons (not a diagram or flowchart)",
}


_BAKED_TEXT_MARKERS = (
    "render all typography",
    "render typography",
    "typography inside the image",
    "large readable title",
    "title typography",
    "legible professional",
    "title (large",
    "subtitle directly",
    "author or brand at the bottom",
    "with the title",
    "show the title",
    "title on the cover",
    "text on the cover",
    "include the title",
    "display the title",
    "words on the cover",
    "lettering on the cover",
    "readable title",
    "book title lettering",
)

# Appended to every AI cover image request — readable text is HTML overlay only.
AI_BACKGROUND_NEGATIVE_RULES = (
    "STRICT RULES — BACKGROUND ARTWORK ONLY: "
    "No text. No title. No subtitle. No author name. No book title lettering. "
    "No readable words. No typography. No captions. No logos. No watermarks. "
    "No banners with text. No letters, numbers, alphabets, or words anywhere in the image. "
    "Do not spell out the book topic as visible lettering. "
    "Leave clean open space in the lower third for app-added editable text layers. "
    "All cover text (title, subtitle, author) is added separately by the app — never inside the artwork."
)

COVER_IMAGE_COLOR_RULES = (
    "Vibrant full color; rich contrast; no grayscale, monochrome, or faded tones."
)

AI_BACKGROUND_RULES_COMPACT = (
    "BACKGROUND ONLY — no text, letters, signs, posters, banners, logos, or readable words. "
    "Never render the book title, subtitle, author, or topic as visible lettering. "
    "App adds all typography as editable overlay. Lower third clear; no faces in lower third."
)

COVER_NO_LETTERING_RULES = (
    "Never spell the book topic or title as visible lettering."
)

WORD_SEARCH_COVER_FINAL_DIRECTION = (
    "FINAL production Word Search cover — premium Designrr-quality photo-realistic heritage "
    "portrait. Historically appropriate Black History subject matter; Black subjects only. "
    "2-4 people max, 1-2 main waist-up subjects, calm closed-mouth, polished editorial light, "
    "natural skin, crisp uncluttered faces. Clean lower third for overlay — no faces in text zone. "
    "Never painterly. Zero readable words, letters, signs, or baked typography in artwork. "
    "This is a WORD SEARCH book — not a crossword puzzle."
)

BLACK_HISTORY_WORD_SEARCH_IMAGE_PROMPT = (
    "Create a professional full-page portrait background image for a BLACK HISTORY WORD SEARCH BOOK. "
    "This is not a crossword puzzle. Use respectful Black History educational imagery with a subtle "
    "word-search letter-grid texture or puzzle-book feel. Do not include crossword grids, crossword "
    "clues, numbered squares, or the word crossword. Do not include readable text, signs, slogans, "
    "logos, title text, subtitle text, or author name. Leave clean lower-third space for editable "
    "cover text."
)

WORD_SEARCH_COVER_VISUAL_RULES = (
    "WORD SEARCH BOOK cover — not a crossword. Subtle letter-grid or word-search texture OK; "
    "circled or highlighted hidden words OK. NO crossword grids, clue boxes, numbered squares, "
    "black-white blocked grids, or crossword references."
)

_BLACK_HISTORY_TOPIC_MARKERS = (
    "black history",
    "african american history",
    "african american",
    "african-american",
    "civil rights",
    "black leaders",
    "black leader",
    "black culture",
    "black heritage",
    "black inventors",
    "black scientists",
    "harriet tubman",
    "martin luther king",
    "rosa parks",
    "juneteenth",
    "malcolm x",
    "black history month",
)

COVER_PORTRAIT_SUBJECT_RULES = (
    "PORTRAIT: max 4 people, 1-2 heroes, waist-up, calm closed-mouth — no wide smiles/teeth/tiny faces."
)

COVER_FACIAL_QUALITY_RULES = (
    "FACE QC: sharp eyes/lips/skin — no pixelation, warped teeth, malformed mouths, melted faces."
)

BLACK_HISTORY_WORD_SEARCH_CREATIVE = (
    "Premium Designrr-quality photo-realistic heritage portrait — 2-4 Black subjects max, "
    "polished editorial lighting, natural skin, crisp detail, clean lower third for app typography."
)

BLACK_HISTORY_COVER_SAFETY_RULES = (
    "Heritage theme: photo-realistic Black subjects only — no white focal figures. "
    "Pure commercial photography — never painterly; never render words as visible art."
)

BLACK_HISTORY_VISUAL_STYLE = (
    "Broad heritage collage — culture, leaders, innovation; not protest-only."
)

BLACK_HISTORY_COMPOSITION_RULES = (
    "Open lower third for editable title — no faces below."
)

PHOTO_REALISTIC_STYLE_RULES = (
    "PHOTO-REALISTIC: Premium editorial photo — natural skin, polished commercial finish, "
    "no painterly/illustrated look, no grain/noise/blur/artifacts, no props on faces."
)

COVER_FRAMING_RULES = (
    "Full figures in frame with safe margins — no cropped heads, limbs, or bodies at edges."
)

COVER_COMPOSITION_INTEGRITY_RULES = (
    "Faces clear — no props, instruments, or collage layers spilling onto faces."
)

_ILLUSTRATION_STYLE_MARKERS = (
    "painterly",
    "painted",
    "pastel",
    "watercolor",
    "sketch",
    "illustrated",
    "illustration",
    "cartoon",
    "anime",
    "posterized",
    "hand-drawn",
    "drawing",
    "artistic rendering",
)


def cover_topic_blob(source: dict | str) -> str:
    """Normalized topic text from a cover dict or raw string."""
    if isinstance(source, str):
        return _norm(source)
    analysis = source.get("topic_analysis") if isinstance(source.get("topic_analysis"), dict) else {}
    fields = source.get("fields") if isinstance(source.get("fields"), dict) else {}
    return _norm(
        " ".join(
            [
                str(source.get("title") or ""),
                str(source.get("subtitle") or ""),
                str(source.get("cover_prompt") or ""),
                str(source.get("image_direction") or ""),
                str(analysis.get("topic") or ""),
                str(analysis.get("reason") or ""),
                str(fields.get("theme") or ""),
            ]
        )
    )


def is_black_history_topic(source: dict | str) -> bool:
    """True when the product topic is Black-history-related."""
    blob = cover_topic_blob(source)
    return any(marker in blob for marker in _BLACK_HISTORY_TOPIC_MARKERS)


def cover_engine_product_type(source: dict | str) -> str:
    """Normalized engine product type from a cover dict or raw string."""
    if isinstance(source, str):
        return str(source or "").strip()
    return str(
        source.get("product_type")
        or (source.get("topic_analysis") or {}).get("product_type")
        or ""
    ).strip()


def is_word_search_book_cover(source: dict | str) -> bool:
    """True when the cover belongs to a Word Search book (not crossword)."""
    return cover_engine_product_type(source) == "word_search_book"


def is_crossword_book_cover(source: dict | str) -> bool:
    """True when the cover belongs to a Crossword puzzle book."""
    return cover_engine_product_type(source) == "crossword_puzzle_book"


def is_photo_realistic_cover(cover: dict | str) -> bool:
    """True when the cover should use photo-realistic AI artwork."""
    if isinstance(cover, str):
        return False
    mode = str(
        cover.get("style_mode")
        or (cover.get("topic_analysis") or {}).get("style_mode")
        or "photo_realistic"
    )
    if mode == "photo_realistic" and str(cover.get("style") or "") != "graphic_icon":
        return True
    product_type = str(
        cover.get("product_type") or (cover.get("topic_analysis") or {}).get("product_type") or ""
    )
    return product_type in {"word_search_book", "crossword_puzzle_book"}


def is_puzzle_photo_cover(cover: dict | str) -> bool:
    """True for Word Search / Crossword covers using photo-realistic AI backgrounds."""
    if isinstance(cover, str):
        return False
    return cover_engine_product_type(cover) in {"word_search_book", "crossword_puzzle_book"} and is_photo_realistic_cover(cover)


def is_word_search_photo_cover(cover: dict | str) -> bool:
    """True for Word Search covers using photo-realistic AI backgrounds."""
    if isinstance(cover, str):
        return False
    return is_word_search_book_cover(cover) and is_photo_realistic_cover(cover)


def _prompt_references_crossword(text: str) -> bool:
    return "crossword" in _norm(text)


def _enforce_word_search_prompt_language(text: str) -> str:
    """Fix positive crossword mislabels in Word Search prompts — keep negative guard rules."""
    out = str(text or "")
    out = re.sub(r"(?i)\bcrossword\s+puzzle\s+book\b", "word search puzzle book", out)
    out = re.sub(r"(?i)\bfor\s+a\s+crossword\b", "for a word search", out)
    out = re.sub(
        r"(?i)\bprofessional\s+puzzle\s+book\b(?!\s+cover)",
        "professional word search book",
        out,
    )
    return re.sub(r"\s+", " ", out).strip()


def _word_search_prompt_mislabels_crossword(text: str) -> bool:
    """True when text treats the product as a crossword (not negative guard wording)."""
    lower = _norm(text)
    positive = (
        "crossword puzzle book",
        "crossword book cover",
        "crossword puzzles ·",
        "portrait background artwork for a crossword",
        "for a crossword puzzle",
    )
    return any(p in lower for p in positive)


def _enforce_photo_realistic_creative(text: str) -> str:
    """Strip illustration-style language when photo-realistic output is required."""
    out = str(text or "")
    for marker in _ILLUSTRATION_STYLE_MARKERS:
        out = re.sub(rf"(?i)\b{re.escape(marker)}\b[^.!?]*[.!?]?", " ", out)
    return re.sub(r"\s+", " ", out).strip(" ,.;")


def _prompt_requests_baked_text(text: str) -> bool:
    t = _norm(text)
    return any(marker in t for marker in _BAKED_TEXT_MARKERS)


def _default_background_creative(title: str, *, product_type: str = "", mood: str = "") -> str:
    mood = mood or "high-resolution, polished marketplace quality"
    if str(product_type or "") == "word_search_book":
        return (
            "Portrait background artwork for a professional word search puzzle book — "
            f"not a crossword. {mood}. Topic-matched full-page hero imagery, KDP-quality composition."
        )
    if str(product_type or "") == "crossword_puzzle_book":
        return (
            "Portrait background artwork for a professional crossword puzzle book. "
            f"{mood}. Topic-matched full-page hero imagery, KDP-quality composition."
        )
    return (
        f"Professional portrait ebook cover background art. {mood}."
    )


def _redact_cover_text_from_prompt(
    text: str,
    *,
    title: str = "",
    subtitle: str = "",
    author: str = "",
    product_type: str = "",
) -> str:
    """Remove exact title/subtitle/author strings so the image model does not render them."""
    out = str(text or "")
    for phrase in (title, subtitle, author):
        p = str(phrase or "").strip()
        if len(p) >= 3:
            out = re.sub(re.escape(p), "the book topic", out, flags=re.IGNORECASE)
    out = re.sub(
        r"\b\d+\s+word\s+search\s+puzzles?\b[^.]*",
        "the word search book",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(
        r"\b\d+\s+crossword\s+puzzles?\b[^.]*",
        "the word search book" if product_type == "word_search_book" else "the puzzle book",
        out,
        flags=re.IGNORECASE,
    )
    out = re.sub(r"\b(easy|medium|hard)\s+level\b", "", out, flags=re.IGNORECASE)
    out = re.sub(r"\babout\s+['\"][^'\"]+['\"]", "about the book topic", out, flags=re.IGNORECASE)
    out = re.sub(r"\bfor\s+['\"][^'\"]+['\"]", "for this book topic", out, flags=re.IGNORECASE)
    redact_phrases = (
        "BLACK HISTORY",
        "Black History",
        "black history",
        "puzzle book",
    )
    if product_type != "word_search_book":
        redact_phrases = (*redact_phrases, "word search", "Word Search")
    for phrase in redact_phrases:
        out = re.sub(re.escape(phrase), "heritage theme", out, flags=re.IGNORECASE)
    if product_type == "word_search_book":
        out = _enforce_word_search_prompt_language(out)
    return re.sub(r"\s+", " ", out).strip()


def _sanitize_creative_prompt(
    text: str,
    *,
    title: str,
    subtitle: str = "",
    author: str = "",
    product_type: str = "",
    mood: str = "",
) -> str:
    """Remove typography instructions — title/subtitle/author are HTML overlays."""
    raw = re.sub(r"\s+", " ", str(text or "").strip())
    if not raw:
        return _default_background_creative(title, product_type=product_type, mood=mood)
    if _prompt_requests_baked_text(raw):
        sentences = re.split(r"(?<=[.!?])\s+", raw)
        kept = [s for s in sentences if s and not _prompt_requests_baked_text(s)]
        raw = " ".join(kept).strip()
    raw = re.sub(
        r"(?i)\b(large readable title[^.]*\.?|balanced centered composition[^.]*\.?|"
        r"sellable kdp-quality cover[^.]*\.?|kdp-quality cover[^.]*\.?)",
        "",
        raw,
    ).strip(" ,.;")
    if len(raw) < 40 or _prompt_requests_baked_text(raw):
        return _default_background_creative(title, product_type=product_type, mood=mood)
    return _redact_cover_text_from_prompt(
        raw, title=title, subtitle=subtitle, author=author, product_type=product_type
    )


def _normalize_image_direction(value: str, *, title: str, product_type: str = "") -> str:
    """User art direction only — not a stored full image prompt with baked text."""
    v = str(value or "").strip()
    if not v:
        return ""
    if _prompt_requests_baked_text(v) or len(v) > 420:
        return ""
    return v


def build_image_prompt(
    *,
    title: str,
    subtitle: str,
    author: str = "",
    cover_prompt: str,
    analysis: dict,
    style: str,
    image_direction: str = "",
) -> str:
    """Build a prompt for portrait cover background art (typography added as HTML overlay)."""
    title = (title or "Untitled").strip()
    mode = analysis.get("style_mode") or "photo_realistic"
    product_type = str(analysis.get("product_type") or "")
    mood = _STYLE_MOODS.get(style) or _STYLE_MOODS.get(mode) or _STYLE_MOODS["modern_business"]

    direction = _normalize_image_direction(image_direction, title=title, product_type=product_type)
    cp = str(cover_prompt or "").strip()
    if direction and not _looks_like_prompt_leak(direction):
        creative = _sanitize_creative_prompt(
            direction,
            title=title,
            subtitle=subtitle,
            author=author,
            product_type=product_type,
            mood=mood,
        )
    elif cp and not _looks_like_prompt_leak(cp):
        creative = _sanitize_creative_prompt(
            cp,
            title=title,
            subtitle=subtitle,
            author=author,
            product_type=product_type,
            mood=mood,
        )
    else:
        creative = _default_background_creative(title, product_type=product_type, mood=mood)

    creative = _redact_cover_text_from_prompt(
        creative, title=title, subtitle=subtitle, author=author, product_type=product_type
    )
    if mode == "photo_realistic" and style != "graphic_icon":
        creative = _enforce_photo_realistic_creative(creative)
        if len(creative) < 40:
            creative = _default_background_creative(
                title,
                product_type=product_type,
                mood=_STYLE_MOODS.get("photo_realistic") or mood,
            )

    topic_blob = cover_topic_blob(
        {"title": title, "subtitle": subtitle, "cover_prompt": cp, "topic_analysis": analysis}
    )
    is_bh = is_black_history_topic(topic_blob)
    is_word_search = product_type == "word_search_book"
    is_crossword = product_type == "crossword_puzzle_book"
    is_puzzle = is_word_search or is_crossword
    is_puzzle_photo = is_puzzle and mode == "photo_realistic" and style != "graphic_icon"

    if is_word_search and is_bh and is_puzzle_photo:
        if len(creative) < 80 or "portrait background artwork" in creative.lower():
            creative = BLACK_HISTORY_WORD_SEARCH_IMAGE_PROMPT
    elif is_bh and is_puzzle_photo:
        if len(creative) < 80 or "portrait background artwork" in creative.lower():
            creative = BLACK_HISTORY_WORD_SEARCH_CREATIVE

    portrait_rules = ""
    if is_puzzle_photo:
        portrait_rules = f" {COVER_PORTRAIT_SUBJECT_RULES} {COVER_FACIAL_QUALITY_RULES}"
    style_rules = ""
    if is_bh:
        style_rules = (
            " PHOTO-REALISTIC: premium polished editorial photo, sharp faces, "
            "no painterly look, no grain/artifacts."
        )
    elif mode == "photo_realistic" and style != "graphic_icon":
        style_rules = (
            f" {PHOTO_REALISTIC_STYLE_RULES} {COVER_FRAMING_RULES} {COVER_COMPOSITION_INTEGRITY_RULES}"
        )
    topic_rules = ""
    if is_bh:
        topic_rules = (
            f" {BLACK_HISTORY_COVER_SAFETY_RULES} {BLACK_HISTORY_VISUAL_STYLE}"
            f" {BLACK_HISTORY_COMPOSITION_RULES}"
        )

    if is_bh and mode == "photo_realistic" and style != "graphic_icon":
        if is_word_search:
            visual = (
                " Word-search book background — photoreal hero art only, not a crossword, "
                "no worksheet or readable text."
            )
        else:
            visual = (
                " Puzzle workbook background — photoreal hero art only, no worksheet or readable text."
            )
        layout_rules = (
            f" Portrait {COVER_IMAGE_SIZE}. Professional cover background. No mockup or device."
        )
    else:
        visual = (
            " Background artwork ONLY — pure illustration/photography with zero readable content."
        )

        if mode == "graphic_icon" or style == "graphic_icon":
            visual += (
                " Flat modern graphic style — not a diagram, flowchart, or wireframe. "
                "Use color blocks and thematic visuals without any lettering."
            )
        else:
            visual += (
                " Premium photorealistic KDP cover photography — smooth natural photo finish, "
                "ultra-clean detail, rich color, zero film grain, speckle, or AI noise texture. "
                "Strong contrast in lower third for text overlay readability. "
                "Avoid diagram, wireframe, instructional chart, or dull flat faded aesthetics."
            )

        layout_rules = (
            f" Portrait orientation {COVER_IMAGE_SIZE}. Single complete cover background. "
            "Professional full-page book-cover artwork. "
            "Strong visual interest in upper and middle areas; calm lower area for text overlay. "
            "No mockup frame, no device, no worksheet."
        )
        if mode == "photo_realistic" and style != "graphic_icon":
            layout_rules += (
                " Center subjects with breathing room — entire figures visible, nothing clipped at edges."
            )
        if is_bh:
            layout_rules += (
                " Word-search workbook cover background. "
                "Do not place important faces or bodies in the lower third text zone."
            )

    topic_blob = _norm(f"{title} {subtitle} {cp}")
    if any(k in topic_blob for k in ("etsy", "listing", "marketplace")):
        visual += (
            " Warm handmade marketplace mood: craft materials, product styling — "
            "still artwork only, no text."
        )

    if is_word_search:
        visual += f" {WORD_SEARCH_COVER_VISUAL_RULES}"
    elif is_crossword:
        visual += (
            " Crossword puzzle book cover background — topic-matched hero art, not an interior "
            "worksheet. No answer keys, no device frames, no readable text anywhere."
        )

    if len(creative) > 360:
        creative = creative[:360].rsplit(" ", 1)[0]
    if is_bh and len(creative) > 200:
        max_creative = 420 if is_word_search else 200
        if len(creative) > max_creative:
            creative = creative[:max_creative].rsplit(" ", 1)[0]

    if is_word_search and is_bh and is_puzzle_photo:
        prompt = (
            "BACKGROUND ONLY — Never render BLACK HISTORY as visible lettering; no text in artwork; "
            "app adds all typography as editable overlay; open lower third clear. "
            f"{BLACK_HISTORY_WORD_SEARCH_IMAGE_PROMPT} "
            "Heritage theme: Black subjects only, Broad heritage — not protest-only, "
            "never painterly, photo-realistic. "
            "PORTRAIT: max 4, 1-2 waist-up heroes, calm closed-mouth. "
            "FACE QC: sharp eyes/lips, no warped teeth or melted faces. "
            f"{COVER_IMAGE_COLOR_RULES} Portrait {COVER_IMAGE_SIZE}."
        )
        return _enforce_word_search_prompt_language(prompt)[:1000]

    strict_rules = (
        AI_BACKGROUND_RULES_COMPACT
        if (mode == "photo_realistic" and style != "graphic_icon") or is_bh
        else AI_BACKGROUND_NEGATIVE_RULES
    )

    if is_bh:
        prompt = (
            f"{strict_rules} {topic_rules}{creative}{portrait_rules}{COVER_IMAGE_COLOR_RULES}"
            f"{style_rules}{visual}{layout_rules}"
        )
    else:
        prompt = (
            f"{strict_rules} {COVER_IMAGE_COLOR_RULES}{portrait_rules}{style_rules} {topic_rules}"
            f"{creative}{visual}{layout_rules} "
            "Reminder: zero readable text in the generated image."
        )
    if is_word_search:
        prompt = _enforce_word_search_prompt_language(prompt)
    if not is_bh:
        prompt = re.sub(r"(?i)black history", "the book topic", prompt)
    return prompt[:1000]


def _looks_like_prompt_leak(text: str) -> bool:
    t = str(text or "").strip().lower()
    if len(t) > 200 and t.startswith(("create ", "design ", "generate ", "make ")):
        return True
    return False


def _font_stack(font_style: str) -> str:
    if font_style == "elegant_serif":
        return "Georgia, 'Times New Roman', serif"
    if font_style == "bold_display":
        return "Helvetica, Arial Black, Arial, sans-serif"
    return "Helvetica, Arial, sans-serif"


def _cover_image_path(package_id: str) -> str:
    if not package_id:
        return ""
    return os.path.join(EXPORTS_DIR, package_id, "img_cover.png")


def _has_cover_image(package_id: str) -> bool:
    path = _cover_image_path(package_id)
    return bool(path and os.path.isfile(path))


def _sync_cover_asset_fields(cover: dict, package_id: str) -> None:
    """Record whether a generated cover PNG is on disk (preview + PDF parity)."""
    pkg = package_id or cover.get("package_id") or ""
    has_img = _has_cover_image(pkg)
    cover["has_cover_image"] = has_img
    cover["cover_asset"] = "img_cover.png" if has_img else ""
    cover["cover_asset_url"] = _download_url(pkg, "img_cover.png") if has_img and pkg else ""
    cover["cover_image_size"] = COVER_IMAGE_SIZE if has_img else ""


def _uses_full_page_cover(cover: dict) -> bool:
    return bool(cover.get("use_ai_image", True))


def _full_page_cover_css() -> str:
    return """
.cda-cover-full-page { background:#fff; padding:0; margin:0; overflow:hidden; border:none;
  box-shadow:none; text-align:center; line-height:0; }
.cda-cover-full-page .cda-cover-full-img { display:block; width:100%; height:auto; margin:0 auto;
  object-fit:contain; object-position:center top; max-height:720px; }
.cda-cover-full-page.cda-cover-pending { padding:48px 24px; line-height:1.5; color:#64748b;
  font-family:Helvetica,Arial,sans-serif; font-size:14px; background:#f8fafc; }
"""


def normalize_text_position(source: dict | None) -> dict[str, float | str]:
    """Clamp and normalize editable cover text placement (percentages)."""
    source = source or {}
    raw = source.get("text_position") if isinstance(source.get("text_position"), dict) else {}
    try:
        x = float(raw.get("x", source.get("text_position_x", DEFAULT_TEXT_POSITION["x"])))
        y = float(raw.get("y", source.get("text_position_y", DEFAULT_TEXT_POSITION["y"])))
    except (TypeError, ValueError):
        x, y = DEFAULT_TEXT_POSITION["x"], DEFAULT_TEXT_POSITION["y"]
    align = str(raw.get("align") or source.get("text_align") or DEFAULT_TEXT_POSITION["align"]).lower()
    if align not in {"left", "center", "right"}:
        align = "center"
    return {
        "x": max(8.0, min(92.0, x)),
        "y": max(12.0, min(92.0, y)),
        "align": align,
    }


def text_layer_position_css(cover: dict) -> str:
    """Absolute placement for composited / template cover text blocks."""
    pos = normalize_text_position(cover)
    x, y, align = pos["x"], pos["y"], pos["align"]
    if align == "left":
        transform = "translate(0,-50%)"
        items = "flex-start"
    elif align == "right":
        transform = "translate(-100%,-50%)"
        items = "flex-end"
    else:
        transform = "translate(-50%,-50%)"
        items = "center"
    return (
        f"position:absolute;z-index:2;left:{x}%;top:{y}%;transform:{transform};"
        f"width:88%;min-height:auto;max-width:92%;display:flex;flex-direction:column;"
        f"align-items:{items};text-align:{align};padding:0;box-sizing:border-box;"
    )


def _pdf_text_anchor_y(page_h: float, cover: dict) -> float:
    """ReportLab Y coordinate (from bottom) for the title baseline."""
    pos = normalize_text_position(cover)
    return page_h * (1.0 - float(pos["y"]) / 100.0)


def _pdf_text_anchor_x(page_w: float, cover: dict) -> float:
    pos = normalize_text_position(cover)
    return page_w * (float(pos["x"]) / 100.0)


def _pdf_draw_aligned_string(pdf, x: float, y: float, text: str, *, align: str) -> None:
    if align == "left":
        pdf.drawString(x, y, text)
    elif align == "right":
        pdf.drawRightString(x, y, text)
    else:
        pdf.drawCentredString(x, y, text)


def _uses_text_overlay(cover: dict) -> bool:
    """Editable HTML typography over AI artwork (default when AI cover is enabled)."""
    if not bool(cover.get("use_ai_image", True)):
        return False
    return cover.get("text_overlay", True) is not False


def _composited_cover_text_layer_html(cover: dict, *, pdf: bool = False) -> str:
    """Editable title / subtitle / author block composited over cover artwork."""
    title = str(cover.get("title") or "Untitled")
    subtitle = str(cover.get("subtitle") or "")
    author = str(cover.get("author") or "")
    style = cover.get("style") or "modern_business"
    palette = cover.get("color_palette") or _palette_for_style(style)
    font = _font_stack(cover.get("font_style") or "bold_display")
    text_color = palette.get("text") or "#ffffff"
    sub_color = palette.get("muted") or "#e2e8f0"
    title_px = cover_title_font_px(cover)
    sub_px = cover_subtitle_font_px(cover)
    auth_px = cover_author_font_px(cover)

    if pdf:
        title_pt = cover_title_font_pt(cover)
        sub_pt = cover_subtitle_font_pt(cover)
        auth_pt = cover_author_font_pt(cover)
        pos = normalize_text_position(cover)
        align = str(pos["align"])
        sub = (
            f'<p style="margin:8pt 0 0;font-size:{sub_pt}pt;color:{sub_color};text-align:{align};'
            f'line-height:1.35;font-weight:400;opacity:0.92;">{_e(subtitle)}</p>'
            if subtitle
            else ""
        )
        auth = (
            f'<p style="margin:10pt 0 0;font-size:{auth_pt}pt;color:{sub_color};text-align:{align};'
            f'letter-spacing:0.03em;font-weight:400;opacity:0.82;">{_e(author)}</p>'
            if author
            else ""
        )
        inner = (
            f'<h1 style="margin:0;font-size:{title_pt}pt;font-weight:bold;color:{text_color};'
            f'line-height:1.1;max-width:100%;text-shadow:0 1pt 3pt rgba(0,0,0,0.65);">{_e(title)}</h1>'
            f"{sub}{auth}"
        )
        return (
            f'<div style="{text_layer_position_css(cover)}font-family:{font};">'
            f'<div class="cda-text-panel" style="{_composited_text_panel_style(cover, pdf=True)}">{inner}</div></div>'
        )

    sub = f'<p class="cda-comp-sub">{_e(subtitle)}</p>' if subtitle else ""
    auth = f'<p class="cda-comp-author">{_e(author)}</p>' if author else ""
    size_class = _title_size_class(title)
    classes = " ".join(c for c in ("cda-comp-title", size_class) if c)
    pos = normalize_text_position(cover)
    inner = f'<h1 class="{classes}">{_e(title)}</h1>{sub}{auth}'
    return (
        f'<div class="cda-text-layer" data-editable-cover-text="1" '
        f'data-text-x="{pos["x"]}" data-text-y="{pos["y"]}" data-text-align="{pos["align"]}">'
        f'<div class="cda-text-panel">{inner}</div></div>'
    )


def _composited_cover_preview_css(cover: dict) -> str:
    style = cover.get("style") or "modern_business"
    palette = cover.get("color_palette") or _palette_for_style(style)
    font = _font_stack(cover.get("font_style") or "bold_display")
    text_color = palette.get("text") or "#ffffff"
    sub_color = palette.get("muted") or "#e2e8f0"
    title = str(cover.get("title") or "")
    size_class = _title_size_class(title)
    title_px = cover_title_font_px(cover)
    sub_px = cover_subtitle_font_px(cover)
    auth_px = cover_author_font_px(cover)
    panel_style = _composited_text_panel_style(cover, pdf=False)
    return f"""
.cda-cover-composite {{ position:relative; min-height:720px; width:100%; margin:0; padding:0;
  overflow:hidden; border:none; box-shadow:none; box-sizing:border-box; }}
.cda-cover-composite .cda-bg-img {{ position:absolute; inset:0; width:100%; height:100%;
  object-fit:cover; object-position:center; display:block; }}
.cda-cover-composite .cda-bg-scrim {{ position:absolute; inset:0; pointer-events:none;
  background:linear-gradient(180deg, rgba(0,0,0,0.02) 0%, rgba(0,0,0,0.06) 58%, rgba(0,0,0,0.26) 100%); }}
.cda-cover-composite .cda-text-layer {{ {text_layer_position_css(cover)} font-family:{font}; }}
.cda-cover-composite .cda-text-panel {{ {panel_style} }}
.cda-cover-composite .cda-comp-title {{ margin:0; color:{text_color}; font-weight:700;
  line-height:1.06; letter-spacing:-0.015em; max-width:100%; text-wrap:balance;
  font-size:{title_px}; text-shadow:0 1px 3px rgba(0,0,0,0.75), 0 0 12px rgba(0,0,0,0.25); }}
.cda-cover-composite .cda-comp-title.cda-title-xs {{ font-size:28px; }}
.cda-cover-composite .cda-comp-title.cda-title-sm {{ font-size:36px; }}
.cda-cover-composite .cda-comp-title.cda-title-md {{ font-size:40px; }}
.cda-cover-composite .cda-comp-sub {{ margin:10px 0 0; color:{sub_color}; font-size:{sub_px};
  line-height:1.35; max-width:100%; font-weight:400; opacity:0.92;
  text-shadow:0 1px 4px rgba(0,0,0,0.45); }}
.cda-cover-composite .cda-comp-author {{ margin:12px 0 0; color:{sub_color}; font-size:{auth_px};
  letter-spacing:0.03em; font-weight:400; opacity:0.82;
  text-shadow:0 1px 4px rgba(0,0,0,0.4); }}
"""


def _composited_full_page_cover_preview_html(cover: dict, package_id: str) -> str:
    img_url = _download_url(package_id, "img_cover.png")
    path = _cover_image_path(package_id)
    if path and os.path.isfile(path):
        try:
            img_url = f"{img_url}?v={int(os.path.getmtime(path))}"
        except OSError:
            pass
    text_layer = _composited_cover_text_layer_html(cover, pdf=False)
    return (
        f'<section class="sheet cover cda-cover-composite cda-cover-full-page" '
        f'data-cover-version="{COVER_VERSION}" data-cover-text-overlay="1">'
        f"<style>{_composited_cover_preview_css(cover)}</style>"
        f'<img class="cda-bg-img" data-vid="cover" alt="" src="{_e(img_url)}" />'
        f'<div class="cda-bg-scrim"></div>{text_layer}</section>'
    )


def _composited_full_page_cover_pdf_html(cover: dict, package_id: str) -> str:
    img_src = _pdf_cover_image_src(package_id)
    if not img_src:
        return _full_page_cover_pdf_html(package_id, pending=True)
    text_layer = _composited_cover_text_layer_html(cover, pdf=True)
    return (
        '<section class="pdf-page cover-page cda-pdf-cover-composite">'
        '<table width="100%" cellpadding="0" cellspacing="0" style="width:100%;">'
        '<tr><td style="padding:0;line-height:0;position:relative;">'
        f'<img class="cda-pdf-cover-full-img" src="{img_src}" alt="" width="468" '
        'style="display:block;width:100%;max-width:468pt;height:auto;max-height:7in;" />'
        f"{text_layer}"
        "</td></tr></table></section>"
    )


def _full_page_cover_preview_html(package_id: str, *, pending: bool = False) -> str:
    if pending or not _has_cover_image(package_id):
        return (
            f'<section class="sheet cover cda-cover-full-page cda-cover-pending" '
            f'data-cover-version="{COVER_VERSION}">'
            f"<style>{_full_page_cover_css()}</style>"
            "<p><strong>Cover image not generated yet.</strong></p>"
            "<p>Save or click Regenerate Image to create your full-page cover.</p>"
            "</section>"
        )
    img_url = _download_url(package_id, "img_cover.png")
    path = _cover_image_path(package_id)
    if path and os.path.isfile(path):
        try:
            img_url = f"{img_url}?v={int(os.path.getmtime(path))}"
        except OSError:
            pass
    return (
        f'<section class="sheet cover cda-cover-full-page" data-cover-version="{COVER_VERSION}">'
        f"<style>{_full_page_cover_css()}</style>"
        f'<img class="cda-cover-full-img" data-vid="cover" alt="" src="{_e(img_url)}" />'
        "</section>"
    )


def _full_page_cover_pdf_html(package_id: str, *, pending: bool = False) -> str:
    if pending or not _has_cover_image(package_id):
        return (
            '<section class="pdf-page cover-page cda-pdf-cover-full cda-pdf-cover-pending">'
            '<p style="text-align:center;color:#64748b;padding:72pt 24pt;font-size:11pt;">'
            "Cover image not available. Regenerate the cover image from Edit Cover.</p>"
            "</section>"
        )
    img_src = _pdf_cover_image_src(package_id)
    if not img_src:
        return _full_page_cover_pdf_html(package_id, pending=True)
    return (
        '<section class="pdf-page cover-page cda-pdf-cover-full">'
        '<table width="100%" cellpadding="0" cellspacing="0">'
        '<tr><td align="center" valign="top" style="padding:0;margin:0;">'
        f'<img class="cda-pdf-cover-full-img" src="{img_src}" alt="" width="468" '
        'style="display:block;width:100%;max-width:468pt;height:auto;max-height:9.25in;'
        'margin:0 auto;" />'
        "</td></tr></table></section>"
    )


def _graphic_area_html(
    *,
    layout: str,
    palette: dict[str, str],
    package_id: str,
    use_ai_image: bool,
    style_mode: str,
    title: str,
) -> str:
    mock = _css_mock_visual(palette, style_mode, title)
    img_url = _download_url(package_id, "img_cover.png") if package_id else ""
    has_file = _has_cover_image(package_id)
    if use_ai_image and img_url and has_file:
        return (
            f'<div class="cda-cover-img"><img data-vid="cover" alt="" src="{_e(img_url)}" '
            'class="cda-cover-photo" style="display:block;" '
            'onerror="this.style.display=\'none\';var n=this.nextElementSibling;if(n)n.style.display=\'block\';" />'
            f'<div class="cda-cover-img-fallback" style="display:none;">{mock}</div></div>'
        )
    return f'<div class="cda-cover-visual">{mock}</div>'


def _css_mock_visual(palette: dict[str, str], style_mode: str, title: str) -> str:
    t = _norm(title)
    if style_mode == "graphic_icon":
        return (
            '<table width="100%" cellpadding="8" cellspacing="6">'
            "<tr>"
            f'<td bgcolor="{palette["panel"]}" style="border:1pt solid {palette["accent"]};border-radius:8pt;text-align:center;">'
            '<div style="font-size:22pt;">📊</div><div style="font-size:8pt;color:#475569;">Strategy</div></td>'
            f'<td bgcolor="{palette["panel"]}" style="border:1pt solid {palette["accent"]};border-radius:8pt;text-align:center;">'
            '<div style="font-size:22pt;">✓</div><div style="font-size:8pt;color:#475569;">Steps</div></td>'
            f'<td bgcolor="{palette["panel"]}" style="border:1pt solid {palette["accent"]};border-radius:8pt;text-align:center;">'
            '<div style="font-size:22pt;">★</div><div style="font-size:8pt;color:#475569;">Results</div></td>'
            "</tr></table>"
        )
    if any(k in t for k in ("etsy", "listing", "marketplace", "optimization")):
        return (
            '<table width="100%" cellpadding="0" cellspacing="0" '
            f'style="background:{palette["panel"]};border-radius:10pt;border:1pt solid #e2e8f0;">'
            '<tr><td style="padding:10pt 12pt;font-size:8pt;color:#64748b;">🔍 Search listings...</td></tr>'
            "<tr><td style=\"padding:0 10pt 10pt;\">"
            '<table width="100%" cellpadding="4" cellspacing="4"><tr>'
            f'<td width="33%" bgcolor="#fafafa" style="border:1pt solid #e2e8f0;border-radius:6pt;padding:6pt;">'
            '<div style="background:#ddd6fe;height:28pt;border-radius:4pt;margin-bottom:4pt;"></div>'
            '<div style="font-size:7pt;font-weight:bold;color:#312e81;">Top Seller</div></td>'
            f'<td width="33%" bgcolor="#fafafa" style="border:1pt solid #e2e8f0;border-radius:6pt;padding:6pt;">'
            '<div style="background:#ddd6fe;height:28pt;border-radius:4pt;margin-bottom:4pt;"></div>'
            '<div style="font-size:7pt;font-weight:bold;color:#312e81;">Trending</div></td>'
            f'<td width="33%" bgcolor="#fafafa" style="border:1pt solid #e2e8f0;border-radius:6pt;padding:6pt;">'
            '<div style="background:#ddd6fe;height:28pt;border-radius:4pt;margin-bottom:4pt;"></div>'
            '<div style="font-size:7pt;font-weight:bold;color:#312e81;">Optimized</div></td>'
            "</tr></table></td></tr></table>"
        )
    return (
        f'<div style="height:120pt;background:linear-gradient(135deg,{palette["secondary"]},{palette["accent"]});'
        'border-radius:10pt;opacity:0.85;"></div>'
    )


def _title_size_class(title: str) -> str:
    """Pick a title scale so long titles wrap instead of clipping."""
    n = len(str(title or ""))
    if n > 72:
        return "cda-title-xs"
    if n > 52:
        return "cda-title-sm"
    if n > 36:
        return "cda-title-md"
    return ""


_TITLE_FONT_PX = {"sm": 32, "md": 38, "lg": 44, "xl": 52}
_SUBTITLE_FONT_PX = {"sm": 12, "md": 14, "lg": 17, "xl": 20}
_TITLE_FONT_PT = {"sm": 22, "md": 26, "lg": 30, "xl": 34}
_SUBTITLE_FONT_PT = {"sm": 9, "md": 10, "lg": 12, "xl": 14}
_AUTHOR_FONT_PX = 12
_AUTHOR_FONT_PT = 9
_TEXT_PANEL_ALPHA = 0.26
_TEXT_PANEL_ALPHA_PUZZLE = 0.28
_TEXT_PANEL_PADDING_PX = "16px 22px"
_TEXT_PANEL_RADIUS_PX = "10px"
_TEXT_PANEL_BORDER = "border:1px solid rgba(255,255,255,0.14);"


def cover_title_font_px(cover: dict) -> str:
    preset = str(cover.get("title_font_size") or "auto").strip().lower()
    if preset in _TITLE_FONT_PX:
        return f'{_TITLE_FONT_PX[preset]}px'
    size_class = _title_size_class(str(cover.get("title") or ""))
    return {"cda-title-xs": "28px", "cda-title-sm": "36px", "cda-title-md": "40px"}.get(size_class, "46px")


def cover_subtitle_font_px(cover: dict) -> str:
    preset = str(cover.get("subtitle_font_size") or "auto").strip().lower()
    if preset in _SUBTITLE_FONT_PX:
        return f'{_SUBTITLE_FONT_PX[preset]}px'
    return "14px"


def cover_title_font_pt(cover: dict) -> int:
    preset = str(cover.get("title_font_size") or "auto").strip().lower()
    if preset in _TITLE_FONT_PT:
        return _TITLE_FONT_PT[preset]
    size_class = _title_size_class(str(cover.get("title") or ""))
    return {"cda-title-xs": 15, "cda-title-sm": 18, "cda-title-md": 22}.get(size_class, 28)


def cover_subtitle_font_pt(cover: dict) -> int:
    preset = str(cover.get("subtitle_font_size") or "auto").strip().lower()
    if preset in _SUBTITLE_FONT_PT:
        return _SUBTITLE_FONT_PT[preset]
    return 10


def cover_author_font_px(cover: dict) -> str:
    preset = str(cover.get("author_font_size") or "auto").strip().lower()
    if preset in _SUBTITLE_FONT_PX:
        return f"{_SUBTITLE_FONT_PX[preset]}px"
    return f"{_AUTHOR_FONT_PX}px"


def cover_author_font_pt(cover: dict) -> int:
    preset = str(cover.get("author_font_size") or "auto").strip().lower()
    if preset in _SUBTITLE_FONT_PT:
        return _SUBTITLE_FONT_PT[preset]
    return _AUTHOR_FONT_PT


def _is_word_search_book_cover(cover: dict) -> bool:
    return is_word_search_book_cover(cover)


def _is_puzzle_book_cover(cover: dict) -> bool:
    """Word Search books only — subtle letter-grid text panel (not crossword styling)."""
    return _is_word_search_book_cover(cover)


def _composited_text_panel_style(cover: dict, *, pdf: bool = False) -> str:
    """Semi-transparent panel behind editable cover text (HTML overlay only)."""
    alpha = _TEXT_PANEL_ALPHA_PUZZLE if _is_puzzle_book_cover(cover) else _TEXT_PANEL_ALPHA
    grid_line = "rgba(255,255,255,0.05)"
    if _is_puzzle_book_cover(cover):
        puzzle_grid = (
            f"background-color:rgba(0,0,0,{alpha});background-image:"
            f"linear-gradient({grid_line} 1px, transparent 1px),"
            f"linear-gradient(90deg, {grid_line} 1px, transparent 1px);"
            "background-size:12px 12px;"
        )
    else:
        puzzle_grid = f"background:rgba(0,0,0,{alpha});"
    if pdf:
        bg = (
            f"background-color:rgba(0,0,0,{alpha});background-image:"
            f"linear-gradient({grid_line} 1px, transparent 1px),"
            f"linear-gradient(90deg, {grid_line} 1px, transparent 1px);"
            "background-size:12px 12px;"
            if _is_puzzle_book_cover(cover)
            else f"background:rgba(0,0,0,{alpha});"
        )
        return (
            f"display:inline-block;max-width:90%;padding:14pt 18pt;border-radius:8pt;"
            f"{bg}{_TEXT_PANEL_BORDER}box-sizing:border-box;"
        )
    return (
        f"display:inline-block;max-width:92%;padding:{_TEXT_PANEL_PADDING_PX};"
        f"border-radius:{_TEXT_PANEL_RADIUS_PX};{_TEXT_PANEL_BORDER}{puzzle_grid}"
        "box-sizing:border-box;backdrop-filter:blur(2px);"
    )


def _cover_text_block(title: str, subtitle: str, title_extra_class: str = "") -> str:
    size = _title_size_class(title)
    classes = " ".join(c for c in ("cda-title", size, title_extra_class) if c)
    sub = f'<p class="cda-sub">{_e(subtitle)}</p>' if subtitle else ""
    return f'<div class="cda-text-block"><h1 class="{classes}">{_e(title)}</h1>{sub}</div>'


def render_cover_preview_html(cover: dict, package_id: str = "") -> str:
    """Preview sheet HTML — AI full-page image or premium template fallback."""
    from services.cover_template_fallback import (
        render_template_cover_preview_html,
        should_use_template_cover,
    )

    pkg = package_id or cover.get("package_id") or ""
    if pkg and _has_cover_image(pkg):
        if _uses_text_overlay(cover):
            return _composited_full_page_cover_preview_html(cover, pkg)
        return _full_page_cover_preview_html(pkg, pending=False)
    if should_use_template_cover(cover, pkg):
        return render_template_cover_preview_html(cover)

    title = cover.get("title") or "Untitled"
    subtitle = cover.get("subtitle") or ""
    author = cover.get("author") or ""
    style = cover.get("style") or "modern_business"
    layout = cover.get("layout") or "clean_business"
    palette = cover.get("color_palette") or _palette_for_style(style)
    font = _font_stack(cover.get("font_style") or "modern_sans")
    mode = cover.get("style_mode") or "photo_realistic"
    use_img = bool(cover.get("use_ai_image", True))

    visual = _graphic_area_html(
        layout=layout, palette=palette, package_id=pkg,
        use_ai_image=use_img, style_mode=mode, title=title,
    )
    auth = f'<p class="cda-author">{_e(author)}</p>' if author else ""
    text_block = _cover_text_block(title, subtitle)
    body_order = f'{text_block}<div class="cda-visual-wrap">{visual}</div>{auth}'

    return (
        f'<section class="sheet cover cda-cover cda-{html.escape(style, quote=True)}" '
        f'data-cover-version="{COVER_VERSION}">'
        f'<style>{_preview_cover_css(palette, font, title)}</style>'
        f'<div class="cda-inner">{body_order}</div></section>'
    )


def _pdf_cover_image_src(package_id: str) -> str:
    """Embed cover PNG as a data URI so xhtml2pdf can render it (file:// fails on Windows)."""
    path = _cover_image_path(package_id)
    if not path or not os.path.isfile(path):
        return ""
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        if not raw:
            return ""
        encoded = base64.b64encode(raw).decode("ascii")
        return f"data:image/png;base64,{encoded}"
    except OSError:
        return ""


def _pdf_cover_visual_cell(
    *,
    cover: dict,
    package_id: str,
    palette: dict[str, str],
    mode: str,
    title: str,
) -> str:
    """PDF visual area — generated PNG when available, wireframe mock only as fallback."""
    use_img = bool(cover.get("use_ai_image", True))
    pkg = package_id or cover.get("package_id") or ""
    img_src = _pdf_cover_image_src(pkg) if use_img and _has_cover_image(pkg) else ""
    if img_src:
        return (
            '<table class="cda-pdf-cover-img-wrap" width="100%" cellpadding="0" cellspacing="0" '
            'style="margin:10pt auto 12pt;">'
            '<tr><td align="center" valign="middle" style="padding:0 6pt;text-align:center;">'
            f'<img class="cda-pdf-cover-photo" src="{img_src}" alt="" width="420" '
            'style="display:block;margin:0 auto;max-width:100%;height:auto;max-height:3.4in;" />'
            "</td></tr></table>"
        )
    return (
        '<table width="100%" cellpadding="8" cellspacing="0" '
        f'style="background-color:{palette["panel"]};border:1pt solid #e2e8f0;border-radius:8pt;margin-bottom:12pt;">'
        f'<tr><td align="center" style="padding:14pt;">'
        + _css_mock_visual(palette, mode, title)
        + "</td></tr></table>"
    )


def render_cover_pdf_html(cover: dict, package_id: str = "") -> str:
    """PDF page-1 HTML — AI full-page image or premium template fallback."""
    from services.cover_template_fallback import (
        render_template_cover_pdf_html,
        should_use_template_cover,
    )

    pkg = package_id or cover.get("package_id") or ""
    if pkg and _has_cover_image(pkg):
        if _uses_text_overlay(cover):
            return _composited_full_page_cover_pdf_html(cover, pkg)
        return _full_page_cover_pdf_html(pkg, pending=False)
    if should_use_template_cover(cover, pkg):
        return render_template_cover_pdf_html(cover)

    title = cover.get("title") or "Untitled"
    subtitle = cover.get("subtitle") or ""
    author = cover.get("author") or ""
    style = cover.get("style") or "modern_business"
    palette = cover.get("color_palette") or _palette_for_style(style)
    mode = cover.get("style_mode") or "photo_realistic"

    visual_cell = _pdf_cover_visual_cell(
        cover=cover,
        package_id=pkg,
        palette=palette,
        mode=mode,
        title=title,
    )

    sub = f'<p class="cda-pdf-sub">{_e(subtitle)}</p>' if subtitle else ""
    auth = f'<p class="cda-pdf-author">{_e(author)}</p>' if author else ""
    title_class = _title_size_class(title)
    # Production polish (2026-07-30): bumped title from 24/20/17/14pt to 44/36/30/24pt
    # so the cover title is actually readable at thumbnail and on-page. The
    # previous sizes were calibrated for a small CTA card, not a real book cover.
    title_style = "font-size:44pt;"
    if title_class == "cda-title-md":
        title_style = "font-size:36pt;"
    elif title_class == "cda-title-sm":
        title_style = "font-size:30pt;"
    elif title_class == "cda-title-xs":
        title_style = "font-size:24pt;"
    # Kicker line above the title — a small uppercase label that gives the cover
    # a more deliberate, branded feel (e.g. "A Practical Guide" or the topic
    # category). Falls back to the title's first word as a heuristic when the
    # subtitle is missing, otherwise we just show the subtitle as the kicker.
    kicker_text = ""
    if subtitle:
        # Use the first sentence of the subtitle as a kicker (capped).
        first_phrase = subtitle.split(".")[0].split(",")[0].strip()
        if 4 <= len(first_phrase) <= 60:
            kicker_text = first_phrase.upper()
    kicker = f'<div class="cda-pdf-kicker">{_e(kicker_text)}</div>' if kicker_text else ""

    # Divider rule between title and subtitle for a more deliberate, branded
    # composition. Short rule, centered, in the muted palette color.
    title_divider = (
        f'<div class="cda-pdf-title-divider"></div>' if sub else ""
    )

    return (
        '<section class="pdf-page cover-page cda-pdf-cover">'
        '<table class="cover-shell" width="100%" cellpadding="0" cellspacing="0">'
        f'<tr><td bgcolor="{palette["primary"]}" style="color:{palette["text"]};padding:54pt 36pt 40pt;">'
        f'{kicker}'
        f'<h1 style="{title_style}font-weight:bold;text-align:center;margin:0 0 14pt;'
        f'max-width:92%;margin-left:auto;margin-right:auto;line-height:1.08;color:{palette["text"]};'
        f'letter-spacing:-0.5px;">'
        f"{_e(title)}</h1>"
        f'{title_divider}'
        f"{sub}"
        f"{visual_cell}"
        f"{auth}"
        "</td></tr></table></section>"
    )


def _preview_cover_css(palette: dict, font: str, title: str = "") -> str:
    return f"""
.cda-cover {{ background: linear-gradient(145deg, {palette["primary"]}, {palette["secondary"]});
  color: {palette["text"]}; text-align: center; padding: 36px 28px 40px; position: relative;
  overflow: hidden; min-height: 0; box-sizing: border-box; }}
.cda-cover::before {{ content:""; position:absolute; width:240px; height:240px; border-radius:50%;
  background:rgba(255,255,255,.08); top:-60px; right:-60px; pointer-events:none; }}
.cda-inner {{ position:relative; z-index:2; font-family:{font}; max-width:100%; margin:0 auto;
  padding-top:4px; box-sizing:border-box; }}
.cda-text-block {{ margin:0 auto 16px; max-width:94%; padding:0 6px; }}
.cda-title {{ font-size:32px; line-height:1.22; margin:0; font-weight:800; word-wrap:break-word;
  overflow-wrap:break-word; hyphens:auto; padding-top:2px; }}
.cda-title-md {{ font-size:30px; }}
.cda-title-sm {{ font-size:26px; }}
.cda-title-xs {{ font-size:22px; line-height:1.25; }}
.cda-title-large {{ font-size:42px; line-height:1.12; letter-spacing:-0.02em; }}
.cda-visual-wrap, .cda-visual-panel {{ margin:12px auto 0; max-width:100%; }}
.cda-visual-panel {{ border-radius:14px; overflow:hidden;
  box-shadow:0 20px 48px rgba(0,0,0,.28); border:1px solid rgba(255,255,255,.2); }}
.cda-sub {{ font-size:16px; opacity:.92; max-width:100%; margin:8px auto 0; line-height:1.4; }}
.cda-author {{ font-size:13px; opacity:.8; margin-top:14px; }}
.cda-cover-visual, .cda-cover-img {{ margin:0 auto; max-width:100%; }}
.cda-cover-img img, .cda-cover-img img.cda-cover-photo {{ width:100%; max-width:100%; max-height:280px;
  object-fit:contain; object-position:center; border-radius:10px;
  box-shadow:0 12px 32px rgba(0,0,0,.25); display:block; margin:0 auto; }}
.cda-badge {{ width:56px; height:56px; border-radius:14px; background:rgba(255,255,255,.14);
  border:2px solid rgba(255,255,255,.45); display:flex; align-items:center; justify-content:center;
  font-size:24px; font-weight:800; margin:0 auto 10px; }}
.cda-kicker {{ font-size:10px; letter-spacing:.2em; text-transform:uppercase; opacity:.88;
  font-weight:700; margin-bottom:10px; }}
.cda-overlay {{ margin-top:-80px; padding:80px 12px 16px;
  background:linear-gradient(transparent,rgba(0,0,0,.55)); border-radius:12px; }}
.cda-pdf-sub {{ font-size:16pt; color:{palette["muted"]}; text-align:center; margin:14pt auto 18pt;
  max-width:86%; line-height:1.35; font-weight:500; }}
.cda-pdf-kicker {{ font-size:9pt; color:{palette["text"]}; text-align:center; letter-spacing:.22em;
  font-weight:700; opacity:.82; margin:0 auto 18pt; text-transform:uppercase; }}
.cda-pdf-title-divider {{ width:54pt; height:2pt; background:{palette["text"]}; opacity:.55;
  margin:0 auto 6pt; }}
.cda-pdf-author {{ font-size:10pt; color:{palette["muted"]}; text-align:center; margin:14pt 0 0; }}
"""


def create_cover_design(
    *,
    title: str,
    subtitle: str = "",
    author: str = "",
    content_md: str = "",
    fields: dict | None = None,
    product_type: str = "ebook",
    product_summary: str = "",
    cover_prompt: str = "",
    package_id: str = "",
    overrides: dict | None = None,
) -> dict[str, Any]:
    """Build a complete cover_design record."""
    overrides = overrides or {}
    analysis = analyze_cover_style(
        title=title,
        content=content_md,
        fields=fields,
        product_type=product_type,
        product_summary=product_summary,
    )
    analysis["product_type"] = product_type
    style = overrides.get("style") or analysis["recommended_style"]
    if style not in USER_STYLES:
        style = analysis["recommended_style"]
    layout = overrides.get("layout") or analysis["recommended_layout"]
    if layout not in LAYOUTS:
        layout = analysis["recommended_layout"]
    font_style = overrides.get("font_style") or "modern_sans"
    if font_style not in FONT_STYLES:
        font_style = "modern_sans"

    palette = _resolve_palette(style, title, overrides)
    preset = _normalize_palette_preset(
        overrides.get("palette_preset") or overrides.get("palette") or ""
    ) or _default_palette_preset(title, style)
    mode = "graphic_icon" if style == "graphic_icon" else analysis["style_mode"]
    use_ai = overrides.get(
        "use_ai_image",
        True
        if str(product_type or "") in {"word_search_book", "crossword_puzzle_book"}
        else mode == "photo_realistic",
    )

    image_direction = _normalize_image_direction(
        str(overrides.get("image_direction") or ""),
        title=title,
        product_type=str(product_type or ""),
    )
    image_prompt = build_image_prompt(
        title=title,
        subtitle=subtitle,
        author=overrides.get("author") if "author" in overrides else author,
        cover_prompt=cover_prompt,
        analysis=analysis,
        style=style,
        image_direction=image_direction,
    )

    cover: dict[str, Any] = {
        "version": COVER_VERSION,
        "title": overrides.get("title") or title,
        "subtitle": overrides.get("subtitle") if "subtitle" in overrides else subtitle,
        "author": overrides.get("author") if "author" in overrides else author,
        "style": style,
        "style_mode": mode,
        "layout": "full_bleed_image" if use_ai else layout,
        "font_style": font_style,
        "palette_preset": preset,
        "color_palette": palette,
        "use_ai_image": use_ai,
        "text_overlay": True if use_ai else overrides.get("text_overlay", True),
        "text_position": normalize_text_position(overrides),
        "image_prompt": image_prompt,
        "image_direction": image_direction,
        "package_id": package_id,
        "topic_analysis": analysis,
        "cover_prompt": cover_prompt,
        "saved_at": datetime.now(timezone.utc).isoformat(),
    }
    cover["preview_html"] = render_cover_preview_html(cover, package_id)
    cover["pdf_html"] = render_cover_pdf_html(cover, package_id)
    _sync_cover_asset_fields(cover, package_id)
    return cover


def update_cover_design(cover: dict, overrides: dict, package_id: str = "") -> dict[str, Any]:
    """Apply user edits and re-render HTML without changing unrelated fields."""
    merged = {**cover, **{k: v for k, v in overrides.items() if v is not None and k not in {"color_palette", "text_position"}}}
    if overrides.get("text_position") is not None:
        merged["text_position"] = normalize_text_position(
            {**merged, "text_position": overrides.get("text_position") or {}}
        )
    elif "text_position" not in merged:
        merged["text_position"] = normalize_text_position(merged)
    pkg = package_id or merged.get("package_id") or ""
    merged["package_id"] = pkg
    style = merged.get("style") or "modern_business"
    merged["color_palette"] = _resolve_palette(style, merged.get("title") or "", overrides)
    if overrides.get("palette_preset") or overrides.get("palette"):
        merged["palette_preset"] = _normalize_palette_preset(
            overrides.get("palette_preset") or overrides.get("palette") or ""
        ) or merged.get("palette_preset")
    analysis = merged.get("topic_analysis") or {}
    engine_type = str(analysis.get("product_type") or "")
    merged["image_direction"] = _normalize_image_direction(
        str(
            overrides.get("image_direction")
            if "image_direction" in overrides
            else merged.get("image_direction") or ""
        ),
        title=str(merged.get("title") or ""),
        product_type=engine_type,
    )
    merged["image_prompt"] = build_image_prompt(
        title=merged.get("title") or "",
        subtitle=merged.get("subtitle") or "",
        author=merged.get("author") or "",
        cover_prompt=merged.get("cover_prompt") or "",
        analysis=analysis if isinstance(analysis, dict) else {},
        style=merged.get("style") or "modern_business",
        image_direction=merged["image_direction"],
    )
    if merged.get("use_ai_image", True):
        merged["layout"] = "full_bleed_image"
        merged["text_overlay"] = True
    merged["preview_html"] = render_cover_preview_html(merged, pkg)
    merged["pdf_html"] = render_cover_pdf_html(merged, pkg)
    merged["saved_at"] = datetime.now(timezone.utc).isoformat()
    merged["version"] = COVER_VERSION
    _sync_cover_asset_fields(merged, pkg)
    return merged


def preview_cover_design(project: dict, overrides: dict | None = None) -> dict[str, Any]:
    """Render cover HTML from editor fields without persisting to the project."""
    from services.product_cover_agent import preview_cover

    return preview_cover(project, overrides)


def apply_cover_to_preview(preview_html: str, cover: dict) -> str:
    """Replace the first cover sheet in preview HTML with the agent cover."""
    sheet = cover.get("preview_html") or render_cover_preview_html(cover)
    if not preview_html or not sheet:
        return preview_html
    soup = BeautifulSoup(preview_html, "html.parser")
    existing = soup.select_one("section.sheet.cover")
    new_tag = BeautifulSoup(sheet, "html.parser").select_one("section.sheet.cover")
    if existing and new_tag:
        existing.replace_with(new_tag)
    elif new_tag:
        book = soup.select_one(".book")
        if book:
            book.insert(0, new_tag)
    return str(soup)


def cover_image_job(cover: dict) -> dict | None:
    """Image job dict for setupVisualImages when AI cover is enabled."""
    if not cover.get("use_ai_image"):
        return None
    prompt = (cover.get("image_prompt") or "").strip()
    if not prompt:
        return None
    return {
        "visual_id": "cover",
        "prompt": prompt,
        "chapter": "Cover",
        "title": "Cover",
    }


def ensure_cover_design(project: dict) -> dict | None:
    """Build cover_design from saved project data if missing."""
    data = project.get("data") or {}
    existing = data.get("cover_design")
    if isinstance(existing, dict) and existing.get("preview_html"):
        pkg = str(data.get("package_id") or existing.get("package_id") or "")
        if pkg:
            existing["package_id"] = pkg
        return sync_cover_html_if_needed(existing, pkg)
    ctx = project_cover_inputs(project)
    if ctx.get("product_type") in {"word_search_book", "crossword_puzzle_book"}:
        if not ctx.get("title"):
            return None
    elif not ctx.get("content_md"):
        return None
    return create_cover_design(
        title=ctx["title"],
        subtitle=ctx.get("subtitle") or "",
        author=ctx.get("author") or "",
        content_md=ctx.get("content_md") or "",
        fields=ctx.get("fields") or {},
        product_type=ctx.get("product_type") or "ebook",
        product_summary=ctx.get("product_summary") or "",
        cover_prompt=ctx.get("cover_prompt") or "",
        package_id=ctx.get("package_id") or "",
    )


def _cover_html_needs_image_sync(cover: dict, package_id: str) -> bool:
    """True when cover HTML should be rebuilt from the on-disk PNG."""
    if int(cover.get("version") or 0) < COVER_VERSION:
        return True
    if _prompt_requests_baked_text(str(cover.get("image_prompt") or "")):
        return True
    if not bool(cover.get("use_ai_image", True)):
        return False
    pdf_html = cover.get("pdf_html") or ""
    preview_html = cover.get("preview_html") or ""
    if _has_cover_image(package_id):
        if _uses_text_overlay(cover):
            title = _norm(str(cover.get("title") or ""))[:24]
            preview_ok = (
                "data-cover-text-overlay" in preview_html
                and (title in _norm(preview_html) if title else True)
            )
            pdf_ok = "cda-pdf-cover-composite" in pdf_html
            return not (pdf_ok and preview_ok)
        pdf_ok = "cda-pdf-cover-full" in pdf_html and "data:image/png;base64," in pdf_html
        preview_ok = "cda-cover-full-page" in preview_html and "cda-cover-full-img" in preview_html
        return not (pdf_ok and preview_ok)
    return "cda-cover-full-page" not in preview_html


def sync_cover_html_if_needed(cover: dict, package_id: str = "") -> dict:
    """Re-render preview/pdf HTML from saved settings + on-disk PNG (no AI regen)."""
    pkg = package_id or cover.get("package_id") or ""
    _sync_cover_asset_fields(cover, pkg)
    if _cover_html_needs_image_sync(cover, pkg):
        return update_cover_design(cover, {}, package_id=pkg)
    return cover


def resolve_cover_pdf_html(cover: dict, package_id: str = "") -> str:
    """PDF page-1 HTML — prefers saved embed; refreshes from disk PNG when stale."""
    pkg = package_id or cover.get("package_id") or ""
    synced = sync_cover_html_if_needed(cover, pkg)
    if synced.get("pdf_html"):
        return str(synced["pdf_html"])
    return render_cover_pdf_html(synced, pkg)


_BLACK_HISTORY_MAX_REGEN = 4
_PHOTO_REALISTIC_MAX_REGEN = 4


def _cover_image_regen_attempts(cover: dict) -> int:
    if is_black_history_topic(cover) or is_photo_realistic_cover(cover):
        return _BLACK_HISTORY_MAX_REGEN
    return 1


def regenerate_cover_image(cover: dict, package_id: str) -> tuple[dict, str | None]:
    """Generate cover PNG and refresh HTML. Returns (updated_cover, asset_url)."""
    from services.cover_quality_agent import evaluate_cover_image_vision_qc

    from services.ebook_package import render_visual_image

    pkg = package_id or cover.get("package_id") or ""
    max_attempts = _cover_image_regen_attempts(cover)
    url: str | None = None

    for attempt in range(max_attempts):
        extra: dict[str, Any] = {"use_ai_image": True, "text_overlay": True}
        if is_word_search_photo_cover(cover) and is_black_history_topic(cover):
            extra["image_direction"] = BLACK_HISTORY_WORD_SEARCH_IMAGE_PROMPT
        if attempt:
            retry_rules = []
            if is_black_history_topic(cover):
                retry_rules.append(
                    f"{BLACK_HISTORY_COVER_SAFETY_RULES} {BLACK_HISTORY_VISUAL_STYLE} "
                    f"{BLACK_HISTORY_COMPOSITION_RULES}"
                )
            if is_photo_realistic_cover(cover):
                retry_rules.append(
                    f"{PHOTO_REALISTIC_STYLE_RULES} {COVER_FRAMING_RULES} "
                    f"{COVER_COMPOSITION_INTEGRITY_RULES}"
                )
            if is_puzzle_photo_cover(cover):
                retry_rules.append(f"{COVER_PORTRAIT_SUBJECT_RULES} {COVER_FACIAL_QUALITY_RULES}")
            prev_qc = cover.get("cover_image_qc") if isinstance(cover.get("cover_image_qc"), dict) else {}
            if prev_qc and is_black_history_topic(cover):
                if not prev_qc.get("no_readable_text", True) or not prev_qc.get(
                    "no_topic_title_lettering", True
                ):
                    retry_rules.append(
                        "No readable words, letters, signs, or typography — never render "
                        "BLACK HISTORY or title text in the artwork."
                    )
                if not prev_qc.get("lower_third_clear", True):
                    retry_rules.append(
                        "Keep the lower third completely open for the editable title box — "
                        "no faces, bodies, or busy detail."
                    )
                if not prev_qc.get("broad_black_history_theme", True):
                    retry_rules.append(
                        "Broad Black History theme — culture, leaders, innovation, heritage — "
                        "not protest-only imagery."
                    )
                if not prev_qc.get("central_subject_black", True) or not prev_qc.get(
                    "main_subjects_black", True
                ):
                    retry_rules.append(
                        "Black people centered respectfully as main subjects — no white focal figures."
                    )
            if prev_qc and (
                not prev_qc.get("smooth_natural_photo", True)
                or not prev_qc.get("sharp_clean_not_grainy", True)
                or not prev_qc.get("looks_photo_realistic", True)
            ):
                retry_rules.append(
                    "Must look like a smooth real editorial photograph — no grain, speckle, "
                    "waxy AI texture, or noise."
                )
            if prev_qc and is_puzzle_photo_cover(cover):
                if not prev_qc.get("eyes_clear_no_artifacts", True) or not prev_qc.get(
                    "faces_not_melted_or_blurred", True
                ):
                    retry_rules.append(
                        "Regenerate with sharp natural eyes and crisp facial features — "
                        "no pixelation, melting, or blur."
                    )
                if not prev_qc.get("teeth_mouth_natural", True):
                    retry_rules.append(
                        "Calm mostly closed-mouth expressions — no wide smiles, shouting, "
                        "or visible distorted teeth."
                    )
                if not prev_qc.get("no_distorted_small_background_faces", True) or not prev_qc.get(
                    "subject_count_acceptable", True
                ):
                    retry_rules.append(
                        "Use 2-4 people maximum with only 1-2 main waist-up subjects — "
                        "no tiny background faces."
                    )
                if not prev_qc.get("lower_third_faces_clear", True):
                    retry_rules.append(
                        "Keep the lower third completely clear for the editable title box — "
                        "no faces in the bottom third."
                    )
            if prev_qc and is_word_search_book_cover(cover):
                if not prev_qc.get("no_crossword_style_grids", True) or not prev_qc.get(
                    "matches_word_search_book", True
                ):
                    retry_rules.append(
                        "WORD SEARCH BOOK only — not a crossword. No crossword grids, clue boxes, "
                        "numbered squares, or blocked crossword-style grids. Subtle letter-grid OK."
                    )
            if is_black_history_topic(cover):
                regen_suffix = (
                    f" Regeneration attempt {attempt + 1}: background only — no lettering, "
                    "no BLACK HISTORY text, 2-4 Black subjects, clean faces, open lower third."
                )
            elif is_puzzle_photo_cover(cover):
                regen_suffix = (
                    f" Regeneration attempt {attempt + 1}: portrait facial quality — "
                    "waist-up, calm closed-mouth, sharp eyes, no facial artifacts."
                )
            else:
                regen_suffix = (
                    f" Regeneration attempt {attempt + 1}: smooth natural photo realism — "
                    "faces clear, full figures in frame, no grain."
                )
            extra["image_direction"] = (
                (extra.get("image_direction") or "") + " " + " ".join(retry_rules) + regen_suffix
            ).strip()
        cover = update_cover_design(cover, extra, package_id=pkg)
        prompt = (cover.get("image_prompt") or "").strip()
        url = render_visual_image(pkg, "cover", prompt, size=COVER_IMAGE_SIZE) if pkg and prompt else None
        cover = update_cover_design(cover, {"use_ai_image": True, "text_overlay": True}, package_id=pkg)

        if not url or max_attempts == 1:
            break
        qc = evaluate_cover_image_vision_qc(cover)
        if qc is None or qc.get("skipped") or qc.get("passed"):
            if qc and not qc.get("skipped"):
                cover["cover_image_qc"] = qc
            break
        cover["cover_image_qc"] = qc

    return cover, url
