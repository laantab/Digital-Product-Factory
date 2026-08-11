"""Activity-book versus low-content classification (KDP Pass 1).

Source:
https://kdp.amazon.com/help/topic/GGE5T76TWKA85DJM

Amazon definition (paraphrase of Help Center):
- Low-content: minimal or no interior content; generally repetitive; designed
  to be filled in by the user (notebooks, planners, journals, logs, etc.).
- Not generally low-content: activity books such as puzzle books or coloring
  books, which generally do not feature repetitive content on each page.

This module maps Factory product families conservatively. Unknown types are
classified as UNKNOWN — never forced to low-content.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from services.kdp.sources import KDP_LOW_CONTENT_BOOKS


class ContentClass(str, Enum):
    LOW_CONTENT = "low_content"
    ACTIVITY = "activity"
    STANDARD = "standard"  # novels / nonfiction / other non-low-content
    UNKNOWN = "unknown"


# Factory product_type → KDP content class (conservative)
_FACTORY_PRODUCT_CLASS: dict[str, ContentClass] = {
    # Explicitly activity / puzzle / coloring per Amazon examples
    "coloring_book": ContentClass.ACTIVITY,
    "word_search": ContentClass.ACTIVITY,
    "crossword": ContentClass.ACTIVITY,
    "math_worksheet": ContentClass.ACTIVITY,
    "spelling_worksheet": ContentClass.ACTIVITY,
    # Narrative / standard content — not low-content
    "ebook": ContentClass.STANDARD,
}

# Explicit low-content labels a caller may set (not Factory generators today)
_LOW_CONTENT_LABELS = frozenset(
    {
        "low_content",
        "low-content",
        "notebook",
        "planner",
        "journal",
        "diary",
        "log_book",
        "logbook",
        "prompt_journal",
        "coupon_book",
        "score_card",
        "crafting_template",
        "blank_sheet_music",
    }
)

_ACTIVITY_LABELS = frozenset(
    {
        "activity",
        "activity_book",
        "puzzle",
        "puzzle_book",
        "coloring",
        "coloring_book",
        "word_search",
        "crossword",
        "math_worksheet",
        "spelling_worksheet",
    }
)


@dataclass(frozen=True)
class ClassificationResult:
    content_class: ContentClass
    product_type: str | None
    low_content_checkbox_required: bool
    free_kdp_isbn_eligible: bool
    notes: tuple[str, ...]
    source: str = KDP_LOW_CONTENT_BOOKS

    def as_dict(self) -> dict[str, Any]:
        return {
            "content_class": self.content_class.value,
            "product_type": self.product_type,
            "low_content_checkbox_required": self.low_content_checkbox_required,
            "free_kdp_isbn_eligible": self.free_kdp_isbn_eligible,
            "notes": list(self.notes),
            "source": self.source,
        }


def classify_content(
    *,
    product_type: str | None = None,
    explicit_class: str | None = None,
) -> ClassificationResult:
    """Classify activity vs low-content vs standard.

    Rules:
    - Explicit low-content / activity labels win when provided.
    - Known Factory activity products → ACTIVITY (not low-content).
    - ebook → STANDARD.
    - Anything else → UNKNOWN (do not invent low-content).
    """
    notes: list[str] = []
    pt = (product_type or "").strip().lower() or None
    explicit = (explicit_class or "").strip().lower().replace(" ", "_") or None

    content_class: ContentClass

    if explicit in _LOW_CONTENT_LABELS or explicit == ContentClass.LOW_CONTENT.value:
        content_class = ContentClass.LOW_CONTENT
        notes.append("Explicit low-content classification supplied by caller")
    elif explicit in _ACTIVITY_LABELS or explicit == ContentClass.ACTIVITY.value:
        content_class = ContentClass.ACTIVITY
        notes.append("Explicit activity classification supplied by caller")
    elif explicit == ContentClass.STANDARD.value:
        content_class = ContentClass.STANDARD
    elif explicit == ContentClass.UNKNOWN.value:
        content_class = ContentClass.UNKNOWN
    elif pt and pt in _FACTORY_PRODUCT_CLASS:
        content_class = _FACTORY_PRODUCT_CLASS[pt]
        if content_class is ContentClass.ACTIVITY:
            notes.append(
                "Factory product mapped to activity book (puzzle/coloring family); "
                "Amazon states these are not generally low-content"
            )
    elif pt:
        content_class = ContentClass.UNKNOWN
        notes.append(
            f"No verified KDP mapping for product_type={pt!r}; classified UNKNOWN"
        )
    else:
        content_class = ContentClass.UNKNOWN
        notes.append("Missing product_type/explicit_class; classified UNKNOWN")

    low_content = content_class is ContentClass.LOW_CONTENT
    # Free KDP ISBN: not available for low-content (GGE5T76TWKA85DJM / GTJ8LBXL6Z4WV5QX).
    # UNKNOWN is treated as not-yet-eligible rather than assumed eligible.
    free_eligible = content_class in (ContentClass.ACTIVITY, ContentClass.STANDARD)

    return ClassificationResult(
        content_class=content_class,
        product_type=pt,
        low_content_checkbox_required=low_content,
        free_kdp_isbn_eligible=free_eligible,
        notes=tuple(notes),
    )
