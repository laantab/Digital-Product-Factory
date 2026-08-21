"""Extract supporting-panel content (correct form, common mistakes, regression,
practice step, readiness note) from a manuscript chapter's own text.

Generic, structure-based extraction -- not tied to any topic. Many
instructional manuscripts already write this content in prose (as this
Factory's own manuscript generator does); this module locates it so the
Factory can build local supporting graphics FROM the book's own words
instead of inventing generic filler. Every extractor degrades gracefully:
a chapter that doesn't follow the expected structure simply yields fewer
panels, never fabricated ones.
"""
from __future__ import annotations

import re
from typing import Any

_CHECKLIST_HEADING_RE = re.compile(
    r"(?im)^#{2,4}\s*(?:[^\n]*\b(?:setup check|checklist|before you begin|getting ready|organize these points)\b[^\n]*)\s*\n"
    r"(?:^(?!\s*(?:\d+\.|-)\s).*\n)*"  # optional non-list lead-in paragraph
    r"((?:^\s*(?:\d+\.|-)\s+.+\n?)+)",
)
_MISTAKES_RE = re.compile(
    r"(?is)\b(?:two common (?:errors|mistakes)|a frequent mistake|common mistakes?|common errors?)\b[^.]*\.\s*(.+?)(?:\n\n|\Z)"
)
_REGRESSION_RE = re.compile(
    r"(?is)\b(?:a useful regression|an easier (?:option|version)|regression(?:s)?(?: is| are)?"
    r"|start with progressions?|progressions? for)\b[^.]*?[:.]?\s*(.+?)(?:\n\n|\Z)"
)
_PRACTICE_HEADING_RE = re.compile(
    r"(?im)^#{2,4}\s*(?:[^\n]*\b(?:practice|session|script)\b[^\n]*)\s*\n"
    r"(?:^(?!\s*(?:\d+\.|-)\s).*\n)*"
    r"((?:^\s*(?:\d+\.|-)\s+.+\n?)+)"
)
# Instructional manuscripts close a chapter with a bolded progress marker, but
# the label wording varies a lot ("readiness note", "skill marker", "closing
# cue", "finishing point", "carry-forward note"). Matching only a couple of
# those wordings silently dropped real guidance the author had written, so the
# vocabulary below stays deliberately broad.
_READINESS_LABEL_WORDS = (
    "readiness", "progression", "reminder", "marker", "cue", "note",
    "point", "takeaway", "checkpoint",
)
_READINESS_RE = re.compile(
    r"(?ims)^\*\*([^*:]*(?:"
    + "|".join(_READINESS_LABEL_WORDS)
    + r")[^*:]*):\*\*\s*(.+?)(?:\n\n|\Z)"
)
_SAFETY_RE = re.compile(
    r"(?is)\b(safety note|caution|before you (?:try|attempt) this|stop if)\b[:\s]*(.+?)(?:\n\n|\Z)"
)


def _first_group(pattern: re.Pattern, text: str, group: int = 1) -> str:
    m = pattern.search(text)
    if not m:
        return ""
    return re.sub(r"\s+", " ", m.group(group)).strip()


def _list_items(pattern: re.Pattern, text: str) -> list[str]:
    m = pattern.search(text)
    if not m:
        return []
    block = m.group(1)
    items = re.findall(r"(?m)^\s*(?:\d+\.|-)\s+(.+)$", block)
    return [re.sub(r"\s+", " ", i).strip() for i in items if i.strip()]


def extract_chapter_panels(chapter_body: str) -> dict[str, Any]:
    """Pull real supporting content out of one chapter's own manuscript text.

    Returns a dict with any of: setup_checklist (list[str]), common_mistakes
    (str), regression (str), practice_steps (list[str]), readiness_note
    (str), safety_note (str). Missing keys mean that chapter's prose didn't
    contain that kind of content -- callers must not invent a replacement.
    """
    text = str(chapter_body or "")
    out: dict[str, Any] = {}
    checklist = _list_items(_CHECKLIST_HEADING_RE, text)
    if checklist:
        out["setup_checklist"] = checklist
    mistakes = _first_group(_MISTAKES_RE, text)
    if mistakes:
        out["common_mistakes"] = mistakes
    regression = _first_group(_REGRESSION_RE, text)
    if regression and len(regression) >= 40:
        out["regression"] = regression
    practice = _list_items(_PRACTICE_HEADING_RE, text)
    if practice:
        out["practice_steps"] = practice
    readiness_m = _READINESS_RE.search(text)
    if readiness_m:
        out["readiness_note"] = re.sub(r"\s+", " ", readiness_m.group(2)).strip()
    safety = _first_group(_SAFETY_RE, text)
    if safety:
        out["safety_note"] = safety
    return out
