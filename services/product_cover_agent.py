"""Shared product cover agent — single master cover engine for all product types.

The ebook cover generator in ``cover_agent`` remains the rendering source of truth.
This module normalizes product inputs, adapts per product type, and exposes one API
for preview, regenerate, save, and apply-to-PDF workflows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from services.cover_agent import (
    BLACK_HISTORY_WORD_SEARCH_IMAGE_PROMPT,
    WORD_SEARCH_COVER_VISUAL_RULES,
    apply_cover_to_preview,
    cover_image_job,
    create_cover_design,
    ensure_cover_design,
    regenerate_cover_image,
    sync_cover_html_if_needed,
    update_cover_design,
)
from services.cover_quality_agent import ensure_professional_cover, evaluate_cover_quality

ENGINE_EBOOK = "ebook"
ENGINE_WORD_SEARCH = "word_search_book"
ENGINE_CROSSWORD = "crossword_puzzle_book"
ENGINE_COLORING_BOOK = "coloring_book"

SUPPORTED_ENGINE_TYPES = frozenset(
    {ENGINE_EBOOK, ENGINE_WORD_SEARCH, ENGINE_CROSSWORD, ENGINE_COLORING_BOOK}
)


@dataclass
class ProductCoverPayload:
    """Normalized cover payload consumed by the shared cover engine."""

    product_type: str
    title: str
    subtitle: str = ""
    author_brand: str = ""
    topic: str = ""
    audience: str = ""
    cover_style: str = ""
    color_palette: dict[str, str] = field(default_factory=dict)
    layout: str = ""
    font_style: str = ""
    image_prompt: str = ""
    use_ai_cover_image: bool | None = None
    content_md: str = ""
    product_summary: str = ""
    package_id: str = ""
    fields: dict[str, Any] = field(default_factory=dict)
    engine_product_type: str = ENGINE_EBOOK

    def to_overrides(self) -> dict[str, Any]:
        overrides: dict[str, Any] = {}
        if self.cover_style:
            overrides["style"] = self.cover_style
        if self.layout:
            overrides["layout"] = self.layout
        if self.font_style:
            overrides["font_style"] = self.font_style
        if self.image_prompt:
            overrides["image_direction"] = self.image_prompt
        if self.use_ai_cover_image is not None:
            overrides["use_ai_image"] = self.use_ai_cover_image
        if self.color_palette:
            overrides["color_palette"] = self.color_palette
        if self.engine_product_type == ENGINE_COLORING_BOOK:
            clean = self.layout == "full_bleed_clean_title" or self.cover_style == "clean_title"
            if clean:
                overrides["author"] = ""
            elif self.author_brand:
                overrides["author"] = self.author_brand
            overrides["text_overlay"] = True
            overrides["text_position"] = {"x": 50.0, "y": 81.0, "align": "center"}
            overrides["product_type"] = ENGINE_COLORING_BOOK
        elif self.author_brand:
            overrides["author"] = self.author_brand
        return overrides

    def to_legacy_context(self) -> dict[str, Any]:
        """Backward-compatible context dict for existing cover routes."""
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "author": self.author_brand,
            "content_md": self.content_md,
            "fields": self.fields,
            "product_type": self.engine_product_type,
            "product_summary": self.product_summary,
            "cover_prompt": self.image_prompt,
            "package_id": self.package_id,
        }


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").lower()).strip()


def _field(fields: dict, key: str, default: str = "") -> str:
    return str(fields.get(key, default) or default).strip()


def _word_search_topic_guide(blob: str) -> dict[str, str]:
    if any(k in blob for k in ("bible", "faith", "scripture", "church", "gospel", "prayer")):
        return {
            "style": "elegant",
            "tone": "calm and reverent",
            "visual_direction": "Clean faith-based puzzle book look with soft light and refined typography.",
            "reason": "Faith-based word search book styling.",
        }
    if any(k in blob for k in ("christmas", "holiday", "halloween", "thanksgiving", "easter", "seasonal")):
        return {
            "style": "bold",
            "tone": "festive and warm",
            "visual_direction": "Seasonal holiday puzzle book cover with thematic colors and celebratory mood.",
            "reason": "Holiday word search book styling.",
        }
    if any(k in blob for k in ("kid", "child", "children", "family", "elementary", "classroom")):
        return {
            "style": "illustrated",
            "tone": "playful and bright",
            "visual_direction": "Colorful kids activity-book cover with friendly illustrated topic visuals.",
            "reason": "Kids word search activity book styling.",
        }
    if any(k in blob for k in ("senior", "adult", "brain", "memory", "large print")):
        return {
            "style": "minimal",
            "tone": "calm and clear",
            "visual_direction": "Calm adult puzzle book cover with high contrast and large readable title treatment.",
            "reason": "Senior-friendly puzzle book styling.",
        }
    if any(k in blob for k in ("black history", "african american", "civil rights", "harriet tubman", "mlk")):
        return {
            "style": "modern_business",
            "tone": "respectful and educational",
            "visual_direction": (
                "Premium Designrr-quality photo-realistic heritage portrait — 2-4 Black subjects max, "
                "waist-up, calm closed-mouth, polished editorial lighting, clean lower third. "
                "Broad theme not protest-only. Black subject matter only. "
                "No visible lettering in the artwork."
            ),
            "reason": "Black History educational word search styling.",
        }
    if any(k in blob for k in ("sport", "sports", "football", "basketball", "baseball", "soccer", "athletic")):
        return {
            "style": "bold",
            "tone": "energetic and dynamic",
            "visual_direction": (
                "Dynamic sports-themed background with action imagery and bold atmosphere — "
                "background art only, no text."
            ),
            "reason": "Sports-themed word search styling.",
        }
    if any(k in blob for k in ("gold rush", "goldrush", "california", "history", "historic", "heritage")):
        return {
            "style": "elegant",
            "tone": "educational and classic",
            "visual_direction": "Historical educational workbook cover with period-appropriate topic imagery.",
            "reason": "History-themed educational word search styling.",
        }
    if any(k in blob for k in ("brain game", "challenge", "puzzle master", "logic")):
        return {
            "style": "bold",
            "tone": "energetic and confident",
            "visual_direction": "Bold adult puzzle-book cover with strong contrast and dynamic topic visuals.",
            "reason": "Adult brain-game puzzle book styling.",
        }
    return {
        "style": "modern_business",
        "tone": "professional and inviting",
        "visual_direction": "Polished topic-matching puzzle book background with hero art supporting the theme.",
        "reason": "General word search book styling.",
    }


def build_word_search_cover_brief(
    fields: dict | None,
    *,
    title: str,
    puzzle_count: int = 10,
) -> dict[str, Any]:
    """Word Search adapter — maps form fields to shared cover brief metadata."""
    fields = fields or {}
    topic = _field(fields, "theme") or title or "Word Search"
    audience = _field(fields, "age_group") or _field(fields, "audience") or "General readers"
    difficulty = _field(fields, "difficulty", "Medium")
    style_pref = _field(fields, "design_style") or _field(fields, "style") or ""
    tone = _field(fields, "tone") or "professional and inviting"
    count = max(1, int(puzzle_count or 1))
    subtitle = _field(fields, "subtitle") or f"{count} Word Search Puzzles · {difficulty} Level"

    blob = _norm(" ".join([topic, audience, style_pref, tone]))
    topic_guide = _word_search_topic_guide(blob)
    style = style_pref or topic_guide["style"]
    tone = topic_guide.get("tone") or tone
    is_black_history = any(
        k in blob
        for k in ("black history", "african american", "civil rights", "harriet tubman", "mlk")
    )

    if is_black_history:
        cover_prompt = (
            f"{BLACK_HISTORY_WORD_SEARCH_IMAGE_PROMPT} "
            f"{topic_guide['visual_direction']} "
            "Premium saturated color with luminous lighting — never dull, flat, or faded. "
            "Full vibrant color — no grayscale or monochrome toning. "
            "KDP portrait 6x9 composition, lower third clear for text overlay. "
            "Do NOT show crossword grids, clue boxes, numbered squares, answer keys, "
            "device mockups, or rows of tiny clip-art icons."
        )
    else:
        cover_prompt = (
            f"Portrait background artwork for a WORD SEARCH puzzle book about '{topic}'. "
            f"This is NOT a crossword puzzle. Audience: {audience}. Mood: {tone}. "
            f"{topic_guide['visual_direction']} "
            f"{WORD_SEARCH_COVER_VISUAL_RULES} "
            "Premium saturated color with luminous lighting — never dull, flat, or faded. "
            "Full vibrant color — no grayscale or monochrome toning. "
            "Background art ONLY — no text, letters, logos, or watermarks. "
            "Topic-relevant hero imagery, KDP portrait 6x9 composition, lower third clear for text overlay. "
            "May include subtle word-search letter-grid texture. "
            "Do NOT show crossword grids, clue boxes, numbered squares, answer keys, "
            "device mockups, or rows of tiny clip-art icons."
        )

    summary = (
        f"Word search book — {topic}. {count} puzzles, {difficulty} difficulty. "
        f"Audience: {audience}. Style: {style}. {topic_guide['reason']}"
    )

    return {
        "product_type": ENGINE_WORD_SEARCH,
        "title": title,
        "subtitle": subtitle,
        "topic": topic,
        "audience": audience,
        "style_preference": style,
        "tone": tone,
        "puzzle_count": count,
        "cover_prompt": cover_prompt,
        "summary_text": summary,
        "topic_guide": topic_guide,
    }


def build_crossword_cover_brief(
    fields: dict | None,
    *,
    title: str,
    puzzle_count: int = 5,
) -> dict[str, Any]:
    """Crossword adapter — maps form fields to shared cover brief metadata."""
    fields = fields or {}
    topic = _field(fields, "theme") or title or "Crossword Puzzles"
    audience = _field(fields, "age_group") or "General readers"
    difficulty = _field(fields, "difficulty", "Medium")
    count = max(1, int(puzzle_count or 1))
    # ASCII hyphen only — unicode middle-dots render with broken letter spacing in PDF.
    subtitle = _field(fields, "subtitle") or f"{count} Crossword Puzzles - {difficulty} Level"

    # Topic-specific visual direction (Gold Rush only — not every California topic)
    topic_lower = topic.lower()
    if any(k in topic_lower for k in ("gold rush", "goal rush", "forty-niner", "49er", "prospector")):
        visual_direction = (
            "Historical educational workbook cover with period-appropriate California Gold Rush imagery: "
            "Sierra Nevada landscape, nineteenth-century mining camp, gold pan, gold nuggets, wooden sluice, "
            "pickaxe and shovel, period-appropriate prospectors, river or stream used for panning. "
            "Warm gold, brown, blue, and natural earth tones. "
            "Professional KDP paperback quality — no modern machinery, no modern clothing, "
            "no unrelated imagery. Background art only — no text or lettering in the artwork."
        )
        cover_style = "elegant"
    else:
        visual_direction = (
            "Professional crossword book cover — may include subtle grid texture. "
            "Full vibrant color — no grayscale or monochrome toning. "
            "Background art ONLY — no text, letters, logos, or watermarks. "
            "Topic-relevant hero imagery, KDP portrait composition, lower third clear for text overlay. "
            "Do NOT show answer keys, interior worksheets, or readable title lettering."
        )
        cover_style = "modern_business"

    cover_prompt = (
        f"Portrait background artwork for a CROSSWORD PUZZLE BOOK about '{topic}'. "
        f"Audience: {audience}. "
        f"{visual_direction} "
        "Do NOT show answer keys, interior worksheets, or readable title lettering."
    )
    summary = f"Crossword puzzle book — {topic}. {count} puzzles, {difficulty} difficulty."

    return {
        "product_type": ENGINE_CROSSWORD,
        "title": title,
        "subtitle": subtitle,
        "topic": topic,
        "audience": audience,
        "cover_prompt": cover_prompt,
        "summary_text": summary,
        "style_preference": cover_style,
    }


def build_crossword_payload_from_fields(
    fields: dict,
    *,
    title: str,
    puzzle_count: int,
    package_id: str = "",
) -> ProductCoverPayload:
    brief = build_crossword_cover_brief(fields, title=title, puzzle_count=puzzle_count)
    return ProductCoverPayload(
        product_type="crossword",
        engine_product_type=ENGINE_CROSSWORD,
        title=brief["title"],
        subtitle=brief["subtitle"],
        author_brand=_field(fields, "brand"),
        topic=brief["topic"],
        audience=brief["audience"],
        cover_style=brief.get("style_preference") or "modern_business",
        layout="full_bleed_image",
        image_prompt=brief["cover_prompt"],
        use_ai_cover_image=True,
        content_md=brief["summary_text"],
        product_summary=brief["summary_text"],
        package_id=package_id,
        fields={**fields, "puzzle_count": puzzle_count},
    )


def build_word_search_payload_from_fields(
    fields: dict,
    *,
    title: str,
    puzzle_count: int,
    package_id: str = "",
) -> ProductCoverPayload:
    brief = build_word_search_cover_brief(fields, title=title, puzzle_count=puzzle_count)
    guide = brief.get("topic_guide") or {}
    return ProductCoverPayload(
        product_type="word_search",
        engine_product_type=ENGINE_WORD_SEARCH,
        title=brief["title"],
        subtitle=brief["subtitle"],
        author_brand=_field(fields, "brand"),
        topic=brief["topic"],
        audience=brief["audience"],
        cover_style=brief.get("style_preference") or guide.get("style") or "modern_business",
        layout="full_bleed_image",
        image_prompt=brief["cover_prompt"],
        use_ai_cover_image=True,
        content_md=brief["summary_text"],
        product_summary=brief["summary_text"],
        package_id=package_id,
        fields={**fields, "puzzle_count": puzzle_count},
    )


def _adapt_ebook(data: dict, project: dict) -> ProductCoverPayload:
    title = (data.get("title") or project.get("name") or "Untitled Product").strip()
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    content = (data.get("content") or data.get("ebook") or "").strip()
    return ProductCoverPayload(
        product_type=str(data.get("product_type") or ENGINE_EBOOK),
        engine_product_type=ENGINE_EBOOK,
        title=title,
        subtitle=(data.get("subtitle") or "").strip(),
        author_brand=(data.get("author_brand") or "").strip(),
        topic=_field(fields, "niche") or _field(fields, "topic") or title,
        audience=_field(fields, "audience"),
        image_prompt=(data.get("cover_prompt") or "").strip(),
        content_md=content,
        product_summary=(data.get("product_summary") or "").strip(),
        package_id=str(data.get("package_id") or ""),
        fields=fields,
    )


def _adapt_word_search(data: dict, project: dict) -> ProductCoverPayload:
    from services.product import normalize_word_search_project_data

    data = normalize_word_search_project_data(data)
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    title = (data.get("title") or project.get("name") or "Word Search").strip()
    meta = data.get("word_search_meta") if isinstance(data.get("word_search_meta"), dict) else {}
    puzzle_count = int(meta.get("worksheets") or data.get("puzzle_count") or 1)
    existing = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    package_id = str(data.get("package_id") or existing.get("package_id") or "")
    payload = build_word_search_payload_from_fields(fields, title=title, puzzle_count=puzzle_count, package_id=package_id)
    payload.author_brand = _field(fields, "brand") or str(data.get("author_brand") or "").strip()
    return payload


def _adapt_crossword(data: dict, project: dict) -> ProductCoverPayload:
    from services.product import normalize_crossword_project_data

    data = normalize_crossword_project_data(data)
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    title = (data.get("title") or _field(fields, "theme") or project.get("name") or "Crossword Book").strip()
    meta = data.get("crossword_meta") if isinstance(data.get("crossword_meta"), dict) else {}
    puzzle_count = int(meta.get("worksheets") or data.get("puzzle_count") or _field(fields, "puzzles", "5") or 5)
    existing = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    package_id = str(data.get("package_id") or existing.get("package_id") or "")
    payload = build_crossword_payload_from_fields(fields, title=title, puzzle_count=puzzle_count, package_id=package_id)
    payload.author_brand = _field(fields, "brand") or str(data.get("author_brand") or "").strip()
    return payload


def build_coloring_book_cover_brief(
    fields: dict,
    *,
    title: str = "",
    theme: str = "",
) -> dict[str, str]:
    """Cover brief for coloring books — full-color art, title via layout overlay."""
    from services.coloring_book.prompt_engine import (
        build_character_bible,
        build_cover_image_prompt,
        derive_cover_copy,
    )

    theme_text = theme or _field(fields, "theme") or title
    copy = derive_cover_copy(
        theme_text,
        product_title=title or _field(fields, "coloring_title"),
        subtitle=_field(fields, "subtitle"),
    )
    bible = build_character_bible(theme_text)
    prompt = build_cover_image_prompt(bible=bible, cover=copy)
    clean = str(copy.overlay_style or "") == "clean_title"
    return {
        "title": copy.title,
        "subtitle": copy.subtitle,
        "badge": copy.badge,
        "overlay_style": copy.overlay_style,
        "topic": theme_text,
        "cover_prompt": prompt,
        "style_preference": "clean_title" if clean else "retail_jumbo",
    }


def _adapt_coloring_book(data: dict, project: dict) -> ProductCoverPayload:
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    existing = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    package_id = str(data.get("package_id") or existing.get("package_id") or "")
    theme = _field(fields, "theme") or str(data.get("title") or "")
    brief = build_coloring_book_cover_brief(
        fields,
        title=str(data.get("title") or existing.get("title") or ""),
        theme=theme,
    )
    # Coloring-book covers: title/subtitle via layout; author on retail overlays only.
    from services.coloring_book.prompt_engine import resolve_coloring_book_author

    clean = str(brief.get("overlay_style") or "") == "clean_title"
    author = "" if clean else resolve_coloring_book_author(
        _field(fields, "author_brand"),
        _field(fields, "author"),
        data.get("author_brand"),
        data.get("author"),
        existing.get("author"),
    )
    return ProductCoverPayload(
        product_type="coloring_book",
        engine_product_type=ENGINE_COLORING_BOOK,
        title=brief["title"],
        subtitle=brief["subtitle"],
        author_brand=author,
        topic=brief["topic"],
        audience=_field(fields, "age_group"),
        cover_style="clean_title" if clean else "retail_jumbo",
        layout="full_bleed_clean_title" if clean else "full_bleed_retail_jumbo",
        image_prompt=brief["cover_prompt"] or str(data.get("cover_prompt") or existing.get("image_prompt") or ""),
        use_ai_cover_image=True,
        product_summary=str(data.get("product_summary") or ""),
        package_id=package_id,
        fields=fields,
        # Minimal content so validate_cover_project does not require ebook body
        content_md=f"Coloring book: {brief['title']}. Theme: {theme}",
    )


def build_cover_payload_from_project(project: dict) -> ProductCoverPayload:
    """Route saved project data through the correct product adapter."""
    data = project.get("data") or {}
    product_type = str(data.get("product_type") or ENGINE_EBOOK).strip()
    if product_type in ("word_search", "word_search_book") and data.get("is_pdf"):
        return _adapt_word_search(data, project)
    if product_type in ("crossword", "crossword_puzzle_book") and data.get("is_pdf"):
        return _adapt_crossword(data, project)
    if product_type == "crossword":
        return _adapt_crossword(data, project)
    if product_type == "coloring_book":
        return _adapt_coloring_book(data, project)
    return _adapt_ebook(data, project)


def project_cover_inputs(project: dict) -> dict[str, Any]:
    """Legacy helper — returns adapter context for existing cover routes."""
    return build_cover_payload_from_project(project).to_legacy_context()


def generate_cover_from_payload(
    payload: ProductCoverPayload,
    *,
    overrides: dict | None = None,
) -> dict[str, Any]:
    """Create a cover_design record from a normalized payload."""
    merged = {**payload.to_overrides(), **(overrides or {})}

    def _recreate(extra: dict[str, Any]) -> dict[str, Any]:
        return create_cover_design(
            title=payload.title,
            subtitle=payload.subtitle,
            author=payload.author_brand,
            content_md=payload.content_md,
            fields=payload.fields,
            product_type=payload.engine_product_type,
            product_summary=payload.product_summary,
            cover_prompt=payload.image_prompt,
            package_id=payload.package_id,
            overrides={**merged, **extra},
        )

    cover = _recreate({})
    cover, _qa = ensure_professional_cover(cover, recreate=_recreate)
    return cover


def generate_cover(project: dict, overrides: dict | None = None) -> dict[str, Any]:
    """Generate cover for any saved product project."""
    payload = build_cover_payload_from_project(project)
    return generate_cover_from_payload(payload, overrides=overrides)


def preview_cover(project: dict, overrides: dict | None = None) -> dict[str, Any]:
    """Preview cover edits without persisting."""
    overrides = overrides or {}
    payload = build_cover_payload_from_project(project)
    existing = (project.get("data") or {}).get("cover_design")
    existing = existing if isinstance(existing, dict) else {}
    package_id = payload.package_id or ""
    if existing:
        cover = update_cover_design(existing, {**payload.to_overrides(), **overrides}, package_id=package_id)
    else:
        cover = generate_cover_from_payload(payload, overrides=overrides)
    cover, _qa = ensure_professional_cover(cover)
    return cover


def save_cover(existing: dict, overrides: dict, *, package_id: str = "") -> dict[str, Any]:
    """Save user cover edits, run quality gate, and self-correct if needed."""
    cover = update_cover_design(existing, overrides, package_id=package_id)
    cover, _qa = ensure_professional_cover(cover)
    return cover


def regenerate_cover_image_for_cover(cover: dict, package_id: str) -> tuple[dict[str, Any], str | None]:
    """Regenerate AI cover PNG, refresh HTML, and run quality self-correction."""
    cover, asset_url = regenerate_cover_image(cover, package_id)
    cover, _qa = ensure_professional_cover(cover)
    return cover, asset_url


def finalize_word_search_production_cover(project: dict) -> dict[str, Any]:
    """Single production pass: lock typography, QC existing PNG, regen only if QC fails.

    Gated by shared content-mutation policy: DRAFT only; APPROVED requires
    Create Draft Revision; LOCKED blocked. Successful DRAFT edits invalidate
    stale export package references for the current revision.
    """
    from services.cover_agent import (
        WORD_SEARCH_COVER_FINAL_DIRECTION,
        _has_cover_image,
        regenerate_cover_image,
        sync_cover_html_if_needed,
        update_cover_design,
    )
    from services.cover_quality_agent import ensure_professional_cover, evaluate_cover_image_vision_qc
    from services.product import apply_word_search_cover_to_saved_data, normalize_word_search_project_data
    from services.quality.artifact_state import (
        assert_content_mutation_allowed,
        invalidate_draft_export_references,
    )

    data = dict(project.get("data") or {})
    assert_content_mutation_allowed(data, action="finalize word search cover")
    existing = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    package_id = str(data.get("package_id") or existing.get("package_id") or "")
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    meta = data.get("word_search_meta") if isinstance(data.get("word_search_meta"), dict) else {}
    puzzle_count = int(meta.get("worksheets") or data.get("puzzle_count") or fields.get("puzzle_count") or 10)
    brief = build_word_search_cover_brief(
        fields,
        title=str(data.get("title") or existing.get("title") or "Black History"),
        puzzle_count=puzzle_count,
    )

    overrides: dict[str, Any] = {
        "title": "Black History",
        "subtitle": "10 Word Search Puzzles · Easy Level",
        "author": str(fields.get("brand") or data.get("author_brand") or existing.get("author") or "Lonnie Brown"),
        "font_style": "bold_display",
        "style": "modern_business",
        "layout": "full_bleed_image",
        "use_ai_image": True,
        "text_overlay": True,
        "text_position": {"x": 50.0, "y": 81.0, "align": "center"},
        "image_direction": WORD_SEARCH_COVER_FINAL_DIRECTION,
        "cover_prompt": brief["cover_prompt"],
        "cover_finalized": True,
        "product_type": "word_search_book",
        "topic_analysis": {
            "product_type": "word_search_book",
            "style_mode": "photo_realistic",
            "topic": brief.get("topic") or "Black History",
            "puzzle_count": puzzle_count,
        },
    }

    cover = update_cover_design(existing, overrides, package_id=package_id)
    regen_needed = not (package_id and _has_cover_image(package_id))

    if package_id and _has_cover_image(package_id):
        qc = evaluate_cover_image_vision_qc(cover)
        if qc and not qc.get("skipped"):
            cover["cover_image_qc"] = qc
            if qc.get("black_history") or qc.get("photo_realistic"):
                cover["black_history_cover_qc"] = qc
            regen_needed = not qc.get("passed")
        elif qc and qc.get("skipped"):
            regen_needed = False

    asset_url: str | None = None
    if regen_needed and package_id:
        cover, asset_url = regenerate_cover_image(cover, package_id)

    cover, qa = ensure_professional_cover(cover)
    cover = sync_cover_html_if_needed(cover, package_id)

    data["cover_design"] = cover
    if cover.get("image_prompt"):
        data["cover_prompt"] = cover["image_prompt"]

    if data.get("product_type") == "word_search":
        data = normalize_word_search_project_data(data)
        if data.get("is_pdf"):
            try:
                data = apply_word_search_cover_to_saved_data(data, cover)
            except RuntimeError:
                pass

    invalidate_draft_export_references(data)

    return {
        "cover_design": cover,
        "data": data,
        "quality": qa.as_dict(),
        "preview_html": cover.get("preview_html") or "",
        "pdf_bytes": data.get("pdf_bytes") or "",
        "asset_url": asset_url or cover.get("cover_asset_url"),
        "regenerated_image": bool(regen_needed and asset_url),
    }


def validate_cover_project(project: dict) -> None:
    """Raise ValueError when project lacks required cover inputs."""
    payload = build_cover_payload_from_project(project)
    if payload.engine_product_type in {
        ENGINE_WORD_SEARCH,
        ENGINE_CROSSWORD,
        ENGINE_COLORING_BOOK,
    }:
        if not payload.title:
            raise ValueError("Project has no product title.")
        return
    if not payload.content_md:
        raise ValueError("Project has no ebook content.")


def cover_result(cover_design: dict, *, preview_html: str = "", pdf_bytes: str = "", image_job: dict | None = None) -> dict[str, Any]:
    """Uniform API response shape for all cover operations."""
    return {
        "cover_design": cover_design,
        "preview_html": preview_html or cover_design.get("preview_html") or "",
        "pdf_bytes": pdf_bytes,
        "image_job": image_job or cover_image_job(cover_design),
    }


# ---------------------------------------------------------------------------
# Cover request fingerprint — cost protection against duplicate generations
# ---------------------------------------------------------------------------

import hashlib

_IMAGE_MODEL_VERSION = "gpt-image-2"
_PROMPT_VERSION = "v1"  # Increment when prompt format changes to invalidate old fingerprints


def compute_cover_fingerprint(
    *,
    topic: str,
    title: str,
    subtitle: str,
    product_type: str,
    audience: str = "",
    difficulty: str = "",
    style: str = "",
) -> str:
    """Create a deterministic hash from cover generation inputs.

    Used to detect when a regeneration request would produce the same image
    already generated for this project — preventing redundant API calls and charges.

    The fingerprint is stored in the cover_design dict as ``cover_fingerprint``.
    Before calling ``regenerate_cover_image``, check whether the new fingerprint
    matches the stored one; if so, skip regeneration.
    """
    components = [
        _IMAGE_MODEL_VERSION,
        _PROMPT_VERSION,
        str(product_type).strip().lower(),
        str(topic).strip().lower(),
        str(title).strip().lower(),
        str(subtitle).strip().lower(),
        str(audience).strip().lower(),
        str(difficulty).strip().lower(),
        str(style).strip().lower(),
    ]
    raw = "|".join(components).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:32]
