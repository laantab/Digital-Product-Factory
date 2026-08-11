"""AI-generated / AI-assisted disclosure records (KDP Pass 1).

Source:
https://kdp.amazon.com/help/topic/G200672390

Amazon distinguishes:
- AI-generated: text, images, or translations created by an AI-based tool
  (even if substantially edited afterward) — must be disclosed to KDP.
- AI-assisted: human-created content refined/edited/brainstormed with AI —
  disclosure not required.

Hard rule for this Factory module:
- Provenance ``unknown`` is never coerced to ``none``.
- Records are pure data; this pass does not wire export-blocking UI.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping

from services.kdp.sources import KDP_CONTENT_GUIDELINES_AI


class AiProvenance(str, Enum):
    """Per-asset or aggregate provenance."""

    NONE = "none"  # human-created; no AI involvement asserted
    AI_ASSISTED = "ai_assisted"
    AI_GENERATED = "ai_generated"
    UNKNOWN = "unknown"


class AiContentKind(str, Enum):
    TEXT = "text"
    IMAGES = "images"
    TRANSLATIONS = "translations"


class AiDisclosureError(ValueError):
    """Invalid AI disclosure record."""


@dataclass(frozen=True)
class AiAssetDisclosure:
    kind: AiContentKind
    provenance: AiProvenance
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "provenance": self.provenance.value,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class AiDisclosureRecord:
    """Structured disclosure ready for a future KDP preflight pass."""

    text: AiProvenance
    images: AiProvenance
    translations: AiProvenance
    requires_kdp_ai_generated_disclosure: bool
    has_unknown_provenance: bool
    assert_no_ai: bool
    assets: tuple[AiAssetDisclosure, ...]
    source: str = KDP_CONTENT_GUIDELINES_AI
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "text": self.text.value,
            "images": self.images.value,
            "translations": self.translations.value,
            "requires_kdp_ai_generated_disclosure": self.requires_kdp_ai_generated_disclosure,
            "has_unknown_provenance": self.has_unknown_provenance,
            "assert_no_ai": self.assert_no_ai,
            "assets": [a.as_dict() for a in self.assets],
            "source": self.source,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


_PROVENANCE_ALIASES = {
    "none": AiProvenance.NONE,
    "human": AiProvenance.NONE,
    "no_ai": AiProvenance.NONE,
    "ai_assisted": AiProvenance.AI_ASSISTED,
    "assisted": AiProvenance.AI_ASSISTED,
    "ai-assisted": AiProvenance.AI_ASSISTED,
    "ai_generated": AiProvenance.AI_GENERATED,
    "generated": AiProvenance.AI_GENERATED,
    "ai-generated": AiProvenance.AI_GENERATED,
    "unknown": AiProvenance.UNKNOWN,
    "": AiProvenance.UNKNOWN,
    None: AiProvenance.UNKNOWN,
}


def parse_provenance(value: Any) -> AiProvenance:
    if isinstance(value, AiProvenance):
        return value
    if value is None:
        return AiProvenance.UNKNOWN
    key = str(value).strip().lower().replace(" ", "_")
    if key in _PROVENANCE_ALIASES:
        return _PROVENANCE_ALIASES[key]
    raise AiDisclosureError(f"Invalid AI provenance: {value!r}")


def _parse_kind(value: Any) -> AiContentKind:
    if isinstance(value, AiContentKind):
        return value
    key = str(value).strip().lower()
    try:
        return AiContentKind(key)
    except ValueError as exc:
        raise AiDisclosureError(f"Invalid AI content kind: {value!r}") from exc


def build_ai_disclosure(data: Mapping[str, Any] | None = None) -> AiDisclosureRecord:
    """Build an AI disclosure record from a mapping.

    Accepted keys:
    - text / images / translations: provenance strings
    - assets: optional list of {kind, provenance, notes}
    - assert_no_ai: bool — only valid when every channel is explicitly ``none``

    Missing channels default to ``unknown`` (never ``none``).
    """
    raw = dict(data or {})
    errors: list[str] = []
    warnings: list[str] = []

    text = parse_provenance(raw["text"]) if "text" in raw else AiProvenance.UNKNOWN
    images = parse_provenance(raw["images"]) if "images" in raw else AiProvenance.UNKNOWN
    translations = (
        parse_provenance(raw["translations"])
        if "translations" in raw
        else AiProvenance.UNKNOWN
    )

    assets: list[AiAssetDisclosure] = []
    for item in raw.get("assets") or []:
        if not isinstance(item, Mapping):
            errors.append("assets entries must be objects")
            continue
        try:
            assets.append(
                AiAssetDisclosure(
                    kind=_parse_kind(item.get("kind")),
                    provenance=parse_provenance(item.get("provenance")),
                    notes=str(item.get("notes") or ""),
                )
            )
        except AiDisclosureError as exc:
            errors.append(str(exc))

    # Asset-level generated/unknown elevates channel status conservatively
    for asset in assets:
        channel = asset.kind.value
        current = {"text": text, "images": images, "translations": translations}[channel]
        if asset.provenance is AiProvenance.AI_GENERATED:
            if channel == "text":
                text = AiProvenance.AI_GENERATED
            elif channel == "images":
                images = AiProvenance.AI_GENERATED
            else:
                translations = AiProvenance.AI_GENERATED
        elif asset.provenance is AiProvenance.UNKNOWN and current is AiProvenance.NONE:
            # Never let asset unknown collapse into channel none
            if channel == "text":
                text = AiProvenance.UNKNOWN
            elif channel == "images":
                images = AiProvenance.UNKNOWN
            else:
                translations = AiProvenance.UNKNOWN
            warnings.append(
                f"{channel} provenance elevated from none to unknown due to asset record"
            )

    channels = (text, images, translations)
    has_unknown = any(p is AiProvenance.UNKNOWN for p in channels) or any(
        a.provenance is AiProvenance.UNKNOWN for a in assets
    )
    requires_disclosure = any(p is AiProvenance.AI_GENERATED for p in channels) or any(
        a.provenance is AiProvenance.AI_GENERATED for a in assets
    )

    assert_no_ai = bool(raw.get("assert_no_ai"))
    if assert_no_ai:
        if has_unknown:
            errors.append(
                "assert_no_ai is invalid while any provenance is unknown "
                "(unknown must not be treated as none)"
            )
        if requires_disclosure:
            errors.append("assert_no_ai is invalid when AI-generated content is recorded")
        if any(p is AiProvenance.AI_ASSISTED for p in channels):
            warnings.append(
                "AI-assisted content does not require KDP disclosure, but assert_no_ai "
                "is inconsistent with recorded AI assistance"
            )
            errors.append("assert_no_ai requires all channels to be none")
        if not all(p is AiProvenance.NONE for p in channels):
            if not has_unknown and not requires_disclosure:
                errors.append("assert_no_ai requires text/images/translations = none")

    if has_unknown:
        warnings.append(
            "One or more AI provenance fields are unknown; KDP disclosure cannot be "
            "auto-answered as 'no AI-generated content'"
        )

    return AiDisclosureRecord(
        text=text,
        images=images,
        translations=translations,
        requires_kdp_ai_generated_disclosure=requires_disclosure,
        has_unknown_provenance=has_unknown,
        assert_no_ai=assert_no_ai and not errors,
        assets=tuple(assets),
        errors=tuple(errors),
        warnings=tuple(warnings),
    )
