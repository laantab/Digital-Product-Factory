"""Persisted EbookDesign specification.

Design never rewrites manuscript content. Any manuscript digest change
invalidates Design, Preview, Preflight, and Export.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from services.ebook_design_system import THEMES, get_theme


DESIGN_SPEC_VERSION = 1

TRIM_LETTER = {"name": "letter", "width_in": 8.5, "height_in": 11.0}

UNNUMBERED_BACK_MATTER = ("disclaimer", "sources", "sources / references", "references")


def _sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class TypographyScale:
    body_pt: float = 11.0
    h1_pt: float = 26.0
    h2_pt: float = 20.0
    h3_pt: float = 14.0
    caption_pt: float = 9.0
    footer_pt: float = 9.0
    line_height: float = 1.55
    paragraph_spacing_em: float = 0.85
    min_font_pt: float = 9.0


@dataclass
class PageGeometry:
    trim_name: str = "letter"
    width_in: float = 8.5
    height_in: float = 11.0
    margin_in: float = 0.75
    content_width_in: float = 7.0
    header_in: float = 0.45
    footer_in: float = 0.45


@dataclass
class MatterRules:
    include_title_page: bool = True
    include_copyright: bool = True
    include_toc: bool = True
    clickable_toc: bool = True
    unnumbered_disclaimer: bool = True
    unnumbered_sources: bool = True
    chapter_opener: str = "stacked_label"
    header_mode: str = "running_title"
    footer_mode: str = "page_number"
    page_numbers: str = "arabic_after_front_matter"


@dataclass
class EbookDesign:
    """Authoritative design spec bound to an approved EbookDocument."""

    spec_version: int = DESIGN_SPEC_VERSION
    revision: int = 1
    theme_id: str = "studio_clean"
    theme_version: str = ""
    manuscript_digest: str = ""
    document_identity: str = ""
    cover_digest: str = ""
    visual_manifest_digest: str = ""
    typography: TypographyScale = field(default_factory=TypographyScale)
    geometry: PageGeometry = field(default_factory=PageGeometry)
    matter: MatterRules = field(default_factory=MatterRules)
    styles: dict[str, Any] = field(default_factory=dict)
    visual_slot_placements: list[dict[str, Any]] = field(default_factory=list)
    cover_identity: dict[str, Any] = field(default_factory=dict)
    digest: str = ""

    def recompute_digest(self) -> str:
        payload = asdict(self)
        payload.pop("digest", None)
        self.digest = _sha(payload)
        return self.digest

    def to_dict(self) -> dict[str, Any]:
        if not self.digest:
            self.recompute_digest()
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict | None) -> "EbookDesign":
        raw = dict(raw or {})
        typo = raw.get("typography") or {}
        geo = raw.get("geometry") or {}
        matter = raw.get("matter") or {}
        design = cls(
            spec_version=int(raw.get("spec_version") or DESIGN_SPEC_VERSION),
            revision=int(raw.get("revision") or 1),
            theme_id=str(raw.get("theme_id") or "studio_clean"),
            theme_version=str(raw.get("theme_version") or ""),
            manuscript_digest=str(raw.get("manuscript_digest") or ""),
            document_identity=str(raw.get("document_identity") or ""),
            cover_digest=str(raw.get("cover_digest") or ""),
            visual_manifest_digest=str(raw.get("visual_manifest_digest") or ""),
            typography=TypographyScale(
                **{k: v for k, v in typo.items() if k in TypographyScale.__dataclass_fields__}
            )
            if isinstance(typo, dict)
            else TypographyScale(),
            geometry=PageGeometry(
                **{k: v for k, v in geo.items() if k in PageGeometry.__dataclass_fields__}
            )
            if isinstance(geo, dict)
            else PageGeometry(),
            matter=MatterRules(
                **{k: v for k, v in matter.items() if k in MatterRules.__dataclass_fields__}
            )
            if isinstance(matter, dict)
            else MatterRules(),
            styles=dict(raw.get("styles") or {}),
            visual_slot_placements=list(raw.get("visual_slot_placements") or []),
            cover_identity=dict(raw.get("cover_identity") or {}),
            digest=str(raw.get("digest") or ""),
        )
        design.recompute_digest()
        return design


def is_unnumbered_back_matter_title(title: str) -> bool:
    norm = " ".join(str(title or "").strip().lower().split())
    norm = norm.replace(":", "").strip()
    return any(norm == item or norm.startswith(item + " ") for item in UNNUMBERED_BACK_MATTER)


def design_styles_for_theme(theme_id: str) -> dict[str, Any]:
    theme = get_theme(theme_id)
    return {
        "body": {"font": theme.font_body, "size_pt": theme.body_size_pt, "color": theme.color_text},
        "heading": {"font": theme.font_heading, "color": theme.color_primary},
        "caption": {"size_pt": 9.0, "color": theme.color_muted, "style": "italic"},
        "table": {"header_bg": theme.table_header_bg, "rule": theme.color_rule, "header_color": theme.color_primary},
        "checklist": {"marker": "square", "accent": theme.color_accent},
        "callout": {"bg": theme.callout_bg, "accent": theme.color_accent},
        "source": {"size_pt": 9.5, "color": theme.color_muted},
        "palette": {
            "primary": theme.color_primary,
            "accent": theme.color_accent,
            "text": theme.color_text,
            "muted": theme.color_muted,
            "rule": theme.color_rule,
        },
    }


def build_ebook_design(
    *,
    theme_id: str,
    manuscript_digest: str,
    document_identity: str = "",
    cover_digest: str = "",
    visual_manifest_digest: str = "",
    visual_slot_placements: list[dict[str, Any]] | None = None,
    cover_identity: dict[str, Any] | None = None,
    revision: int = 1,
) -> EbookDesign:
    if theme_id not in THEMES and theme_id != "ink_editorial":
        raise ValueError(f"Unknown ebook theme: {theme_id}")
    theme = get_theme(theme_id)
    geo = PageGeometry(
        trim_name=TRIM_LETTER["name"],
        width_in=TRIM_LETTER["width_in"],
        height_in=TRIM_LETTER["height_in"],
        margin_in=float(theme.margin_in),
        content_width_in=round(TRIM_LETTER["width_in"] - (2 * float(theme.margin_in)), 2),
    )
    design = EbookDesign(
        revision=revision,
        theme_id=theme.theme_id,
        theme_version=theme.version,
        manuscript_digest=str(manuscript_digest or ""),
        document_identity=str(document_identity or ""),
        cover_digest=str(cover_digest or ""),
        visual_manifest_digest=str(visual_manifest_digest or ""),
        typography=TypographyScale(
            body_pt=theme.body_size_pt,
            h1_pt=theme.h1_size_pt,
            h2_pt=theme.h2_size_pt,
            h3_pt=theme.h3_size_pt,
            line_height=theme.line_height,
            paragraph_spacing_em=theme.paragraph_spacing_em,
            min_font_pt=theme.min_font_pt,
        ),
        geometry=geo,
        matter=MatterRules(chapter_opener=theme.chapter_opener),
        styles=design_styles_for_theme(theme.theme_id),
        visual_slot_placements=list(visual_slot_placements or []),
        cover_identity=dict(cover_identity or {}),
    )
    design.recompute_digest()
    return design


def design_is_stale(design: EbookDesign | dict | None, *, manuscript_digest: str) -> bool:
    if not design:
        return True
    if isinstance(design, dict):
        bound = str(design.get("manuscript_digest") or "")
        digest = str(design.get("digest") or "")
    else:
        bound = design.manuscript_digest
        digest = design.digest or design.recompute_digest()
    if not bound or bound != str(manuscript_digest or ""):
        return True
    if not digest:
        return True
    return False
