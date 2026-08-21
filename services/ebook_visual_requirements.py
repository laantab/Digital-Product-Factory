"""Typed visual requirement model and asset validation for ebooks.

Historically ``count_visuals()`` (services/ebook_factory_pipeline.py) treated
ANY non-photo aid as an automatically "rendered" completed visual, with no
regard for what the chapter actually needed shown. A chapter about a physical
movement could be marked visually complete by a styled bullet-list checklist,
because nothing distinguished "a real photograph of the deadlift" from "a
checklist about the deadlift" -- both just counted as one rendered visual.

This module adds that distinction. It classifies every planned visual aid
into a semantic category (photo, instructional illustration, diagram, data
chart, comparison table, checklist, callout, decorative, or placeholder),
derives what each chapter actually needs from its own structure/content (not
a closed keyword allowlist alone), and reports which chapters' requirements
are genuinely satisfied versus still unresolved.

It is additive: services.ebook_factory_pipeline.count_visuals() and its
existing return keys (required_visual_count/rendered_visual_count/
missing_photo_count) are unchanged, so every existing caller and test that
depends on that legacy shape keeps working. This module's output is layered
on top by services.ebook_factory_pipeline.ebook_project_readiness() to
compute the *honest* completion gate and to feed a proper Visual Review data
contract (separate required/verified/supporting/decorative/rejected counts
instead of one misleading total).
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Semantic asset categories
# ---------------------------------------------------------------------------
CATEGORY_PHOTO = "photo"
CATEGORY_ILLUSTRATION = "instructional_illustration"
CATEGORY_DIAGRAM = "diagram"
CATEGORY_DATA_CHART = "data_chart"
CATEGORY_COMPARISON_TABLE = "comparison_table"
CATEGORY_CHECKLIST = "checklist"
CATEGORY_CALLOUT = "callout"
CATEGORY_DECORATIVE = "decorative"
CATEGORY_PLACEHOLDER = "placeholder"

ALL_CATEGORIES = frozenset(
    {
        CATEGORY_PHOTO,
        CATEGORY_ILLUSTRATION,
        CATEGORY_DIAGRAM,
        CATEGORY_DATA_CHART,
        CATEGORY_COMPARISON_TABLE,
        CATEGORY_CHECKLIST,
        CATEGORY_CALLOUT,
        CATEGORY_DECORATIVE,
        CATEGORY_PLACEHOLDER,
    }
)

# A reader can look at these and see the real subject performed/shown.
DEMONSTRATION_CATEGORIES = frozenset({CATEGORY_PHOTO, CATEGORY_ILLUSTRATION})
# Real numeric evidence.
DATA_CATEGORIES = frozenset({CATEGORY_DATA_CHART})
# Side-by-side comparison of options.
COMPARISON_CATEGORIES = frozenset({CATEGORY_COMPARISON_TABLE, CATEGORY_DATA_CHART})
# Improves scanning/readability but is not a demonstration, data, or
# comparison visual. Never satisfies those requirement kinds.
SUPPORTING_CATEGORIES = frozenset({CATEGORY_CHECKLIST, CATEGORY_CALLOUT})
DECORATIVE_CATEGORIES = frozenset({CATEGORY_DECORATIVE})

# Maps the literal aid["type"] strings used across the existing planners
# (services.ebook_package._norm_type, services.ebook_local_package,
# services.ebook_visual_pipeline._choose_aid) to a semantic category.
_TYPE_TO_CATEGORY = {
    "stock photo": CATEGORY_PHOTO,
    "photo": CATEGORY_PHOTO,
    "illustration": CATEGORY_ILLUSTRATION,
    "instructional_illustration": CATEGORY_ILLUSTRATION,
    "infographic": CATEGORY_ILLUSTRATION,
    "diagram": CATEGORY_DIAGRAM,
    "workflow": CATEGORY_DIAGRAM,
    "timeline": CATEGORY_DIAGRAM,
    "chart": CATEGORY_DATA_CHART,
    "graph": CATEGORY_DATA_CHART,
    "data_chart": CATEGORY_DATA_CHART,
    "table": CATEGORY_COMPARISON_TABLE,
    "comparison": CATEGORY_COMPARISON_TABLE,
    "comparison_table": CATEGORY_COMPARISON_TABLE,
    "checklist": CATEGORY_CHECKLIST,
    "worksheet box": CATEGORY_CHECKLIST,
    "action step box": CATEGORY_CHECKLIST,
    "tip box": CATEGORY_CALLOUT,
    "callout": CATEGORY_CALLOUT,
    "youtube resource box": CATEGORY_CALLOUT,
    "divider": CATEGORY_DECORATIVE,
    "decorative": CATEGORY_DECORATIVE,
    "ornament": CATEGORY_DECORATIVE,
}


def classify_aid_category(aid: dict | None) -> str:
    """Map a visual-aid dict's declared type to a semantic taxonomy category.

    Falls back to CATEGORY_PLACEHOLDER for anything that isn't a dict, and to
    CATEGORY_CALLOUT (never a demonstration/data/comparison substitute) for
    an unrecognized type string -- an unknown aid type must never silently
    satisfy a photograph/illustration/diagram/chart requirement.
    """
    if not isinstance(aid, dict):
        return CATEGORY_PLACEHOLDER
    raw = str(aid.get("type") or "").strip().lower()
    category = _TYPE_TO_CATEGORY.get(raw, CATEGORY_CALLOUT)
    if aid_is_placeholder(aid, category=category):
        return CATEGORY_PLACEHOLDER
    return category


def aid_is_placeholder(aid: dict | None, *, category: str | None = None) -> bool:
    """True when an aid has no real, verified content yet.

    A file "existing on disk" is not enough on its own for photo/illustration
    categories -- it must have actually been verified (has_file / a resolved
    local asset reference), not merely proposed or rejected in matching.
    """
    if not isinstance(aid, dict):
        return True
    if category is None:
        category = _TYPE_TO_CATEGORY.get(str(aid.get("type") or "").strip().lower(), CATEGORY_CALLOUT)

    if category in DEMONSTRATION_CATEGORIES:
        if str(aid.get("match_status") or "") == "reject":
            return True
        if aid.get("rendered") is False:
            return True
        verified = bool(
            aid.get("has_file")
            or aid.get("asset_path")
            or aid.get("factory_asset_path")
            or aid.get("local_asset_sha256")
        )
        return not verified

    if category == CATEGORY_DATA_CHART:
        data = aid.get("chart_data") or {}
        labels = data.get("labels") if isinstance(data, dict) else None
        values = data.get("values") if isinstance(data, dict) else None
        return not (labels and values)

    if category == CATEGORY_COMPARISON_TABLE:
        table = aid.get("table") or {}
        headers = table.get("headers") if isinstance(table, dict) else None
        rows = table.get("rows") if isinstance(table, dict) else None
        return not (headers and rows)

    if category == CATEGORY_CHECKLIST:
        items = aid.get("items") or []
        return len(items) < 1

    if category == CATEGORY_DIAGRAM:
        return not (
            str(aid.get("mermaid") or "").strip()
            or aid.get("items")
            or aid.get("has_file")
        )

    if category == CATEGORY_CALLOUT:
        return not (
            str(aid.get("body") or "").strip()
            or str(aid.get("caption") or "").strip()
            or str(aid.get("title") or "").strip()
        )

    return False


# ---------------------------------------------------------------------------
# Per-chapter requirement derivation
#
# Keyword hits are supporting evidence, combined with structural signals
# (does the chapter contain a real markdown table? numeric figures? language
# describing a physical technique/position?) rather than being the sole
# decision, per-chapter rather than a single book-wide guess.
# ---------------------------------------------------------------------------
REQUIREMENT_DEMONSTRATION = "demonstration"
REQUIREMENT_COMPARISON = "comparison"
REQUIREMENT_DATA = "data"
REQUIREMENT_SUPPORTING_ONLY = "supporting_only"

_DEMONSTRATION_SIGNALS = re.compile(
    r"\b(form|technique|position|posture|stance|grip|movement|demonstrat\w*"
    r"|step[- ]by[- ]step|how to (?:do|perform)|proper (?:form|technique)"
    r"|starting position|finishing position|set ?up|regression|common mistakes?)\b",
    re.I,
)
_COMPARISON_SIGNALS = re.compile(r"\b(compare|comparison|versus|vs\.?|options?|alternatives?)\b", re.I)
_NUMERIC_SIGNAL = re.compile(r"\$\d|\d+\s?%")
_TABLE_SIGNAL = re.compile(r"(?m)^\|.+\|\s*\n\|[-:\s|]+\|")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def derive_chapter_requirement(
    chapter_name: str,
    chapter_body: str,
    *,
    book_demonstration_led: bool,
) -> dict[str, Any]:
    """Decide what a single chapter needs the reader to SEE, from its own
    content -- not merely whether the book-level topic hit a keyword list.
    """
    body = str(chapter_body or "")
    name = str(chapter_name or "")
    blob = f"{name}\n{body[:2000]}"

    demo_hits = len(_DEMONSTRATION_SIGNALS.findall(blob))
    compare_hits = len(_COMPARISON_SIGNALS.findall(blob))
    has_table = bool(_TABLE_SIGNAL.search(body))
    numeric_hits = len(_NUMERIC_SIGNAL.findall(body))

    if demo_hits and book_demonstration_led:
        return {
            "chapter": name,
            "requirement_kind": REQUIREMENT_DEMONSTRATION,
            "allowed_categories": sorted(DEMONSTRATION_CATEGORIES),
            "required": True,
            "reason": (
                "Chapter describes a physical technique or position the "
                "reader must see performed correctly; text alone cannot "
                "substitute for a demonstration."
            ),
        }
    if compare_hits and has_table:
        return {
            "chapter": name,
            "requirement_kind": REQUIREMENT_COMPARISON,
            "allowed_categories": sorted(COMPARISON_CATEGORIES),
            "required": True,
            "reason": "Chapter compares options; a table or chart communicates this better than prose alone.",
        }
    if numeric_hits >= 2:
        return {
            "chapter": name,
            "requirement_kind": REQUIREMENT_DATA,
            "allowed_categories": sorted(DATA_CATEGORIES | COMPARISON_CATEGORIES),
            "required": True,
            "reason": "Chapter presents numeric figures that benefit from a chart or table.",
        }
    if book_demonstration_led:
        # The book overall is demonstration-led (fitness, craft, gardening,
        # cooking, repair, ...) but this specific chapter had no strong
        # structural signal of its own. Still expect a real visual rather
        # than none, without over-claiming exactly what it must depict.
        return {
            "chapter": name,
            "requirement_kind": REQUIREMENT_DEMONSTRATION,
            "allowed_categories": sorted(DEMONSTRATION_CATEGORIES),
            "required": True,
            "reason": "Book-level subject is demonstration-led; every chapter should show, not just tell.",
        }
    return {
        "chapter": name,
        "requirement_kind": REQUIREMENT_SUPPORTING_ONLY,
        "allowed_categories": sorted(ALL_CATEGORIES - {CATEGORY_PLACEHOLDER}),
        "required": False,
        "reason": "No demonstration, comparison, or data signal found; a supporting visual is optional here, not required.",
    }


# ---------------------------------------------------------------------------
# Whole-plan validation
# ---------------------------------------------------------------------------
def validate_visual_plan_typed(
    visual_plan: dict | None,
    *,
    content_md: str = "",
    title: str = "",
    topic: str = "",
) -> dict[str, Any]:
    """Typed, honest visual-completion assessment for an ebook's visual_plan.

    Returns per-chapter requirement + resolution status, plus rollup counts
    that keep REQUIRED instructional visuals separate from merely-supporting
    text components and decorative elements -- so a checklist, callout,
    comparison table, or decorative element can never be reported as having
    satisfied a required photograph/illustration/diagram/chart.
    """
    from services.ebook_visual_match import is_photo_led_subject

    plan = visual_plan if isinstance(visual_plan, dict) else {}
    chapters = list(plan.get("chapters") or [])

    book_demo_led = is_photo_led_subject(title=title, topic=topic, content=content_md)

    body_by_title: dict[str, str] = {}
    if content_md:
        try:
            from services.ebook_package import _split_chapters

            _, split = _split_chapters(content_md)
            for name, body in split:
                body_by_title[_norm(name)] = body
        except Exception:
            body_by_title = {}

    chapter_reports: list[dict[str, Any]] = []
    required_instructional = 0
    verified_instructional = 0
    supporting_count = 0
    decorative_count = 0
    rejected_or_missing_count = 0
    unresolved: list[dict[str, Any]] = []

    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        name = str(ch.get("chapter") or "")
        body = body_by_title.get(_norm(name), "")
        req = derive_chapter_requirement(name, body, book_demonstration_led=book_demo_led)
        aids = list(ch.get("aids") or [])
        categories = [classify_aid_category(a) for a in aids]

        satisfied = False
        allowed = set(req["allowed_categories"])
        if req["required"]:
            for cat in categories:
                if cat in allowed and cat != CATEGORY_PLACEHOLDER:
                    satisfied = True
                    break
            if req["requirement_kind"] == REQUIREMENT_DEMONSTRATION:
                required_instructional += 1
                if satisfied:
                    verified_instructional += 1

        for cat in categories:
            if cat in SUPPORTING_CATEGORIES:
                supporting_count += 1
            elif cat in DECORATIVE_CATEGORIES:
                decorative_count += 1
            elif cat == CATEGORY_PLACEHOLDER:
                rejected_or_missing_count += 1

        status = "satisfied" if (not req["required"] or satisfied) else "missing"
        chapter_reports.append({**req, "status": status, "asset_categories_present": categories})
        if req["required"] and not satisfied:
            unresolved.append(
                {
                    "chapter": name,
                    "requirement_kind": req["requirement_kind"],
                    "allowed_categories": req["allowed_categories"],
                    "status": "missing",
                    "reason": req["reason"],
                }
            )

    return {
        "chapter_requirements": chapter_reports,
        "required_instructional_count": required_instructional,
        "verified_instructional_count": verified_instructional,
        "supporting_component_count": supporting_count,
        "decorative_component_count": decorative_count,
        "rejected_or_missing_count": rejected_or_missing_count,
        "unresolved_visual_requirements": unresolved,
        "visual_requirements_met": not unresolved,
    }
