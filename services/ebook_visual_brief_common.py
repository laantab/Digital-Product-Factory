"""Shared, topic-agnostic building blocks for visual search planning.

Used by services.ebook_pexels (query construction), services.ebook_visual_match
(visual briefs / hard-rejection scoring), and services.ebook_customer_path
(cover title/subtitle/author identity resolution). Nothing here references
any specific book, project, or topic string -- every list below is a general
vocabulary or pattern meant to generalize across future ebooks.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Filler / non-visual phrase stripping
#
# Chapter and section titles are written to read well in a table of contents
# ("Learning to Hinge Without Guessing"), not as image-search text. None of
# these phrases describe anything a photograph could show; left in, they
# crowd out the words that actually matter (the equipment, the action) when
# a search query is built from a short, fixed-length token budget.
# ---------------------------------------------------------------------------
FILLER_PHRASES = (
    "without guessing", "turning power into", "building confidence",
    "learning to", "why it matters", "common mistakes", "better positioning",
    "instead of", "turning", "into a controlled", "building depth",
    "balance and bracing", "using the", "everyday strength",
    "confidence-building", "confidence building", "the six essential",
    "a form-first guide", "a practical guide", "a beginner's guide",
    "step by step", "step-by-step", "the complete guide", "the ultimate guide",
    "getting started with", "everything you need to know",
)

# Single-word stop tokens that are grammatically necessary but never
# describe anything visible in a photograph.
_FILLER_WORDS = frozenset(
    {
        "without", "guessing", "instead", "yanking", "turning", "into",
        "controlled", "confidence", "essential", "foundational", "learning",
        "understanding", "mastering", "improving", "building", "using",
    }
)


def strip_filler(text: str) -> str:
    """Remove known non-visual filler phrases/words from a title/chapter string."""
    out = str(text or "")
    for phrase in FILLER_PHRASES:
        out = re.sub(re.escape(phrase), " ", out, flags=re.I)
    out = re.sub(r"[:\-–—]", " ", out)
    words = [w for w in re.split(r"\s+", out) if w and w.lower() not in _FILLER_WORDS]
    return " ".join(words).strip()


# ---------------------------------------------------------------------------
# Equipment / implement vocabulary
#
# A generic list of common named physical-instruction implements. Not tied
# to any one book: it exists so that (a) the book's own defining implement
# can be detected and kept in every chapter query for that book, and (b)
# the OTHER implements in this same list become hard-rejection terms for
# that book, since a photo of the wrong implement is definitionally wrong
# regardless of how well its metadata otherwise matches.
# ---------------------------------------------------------------------------
EQUIPMENT_VOCABULARY = (
    "kettlebell", "dumbbell", "barbell", "resistance band", "medicine ball",
    "jump rope", "pull-up bar", "yoga mat", "foam roller", "cable machine",
    "treadmill", "stationary bike", "rowing machine", "sandbag",
    "trx strap", "suspension trainer", "weight plate", "smith machine",
    "leg press machine",
)


def detect_equipment_terms(*texts: str) -> list[str]:
    """Which known implements are named in the given text(s), in vocabulary order."""
    blob = " ".join(str(t or "") for t in texts).lower()
    return [term for term in EQUIPMENT_VOCABULARY if term in blob]


def excluded_equipment_terms(required: list[str]) -> list[str]:
    """The rest of the equipment vocabulary, to hard-reject as wrong-implement."""
    required_set = set(required)
    return [term for term in EQUIPMENT_VOCABULARY if term not in required_set]


# ---------------------------------------------------------------------------
# Audience / age-representation terms
# ---------------------------------------------------------------------------
_AUDIENCE_PATTERNS = (
    (re.compile(r"\bover\s*50\b|\b50\s*\+|\bafter\s*50\b", re.I), ["adults over 50", "older adult", "mature adult", "senior fitness"]),
    (re.compile(r"\bover\s*60\b|\b60\s*\+|\bsenior[s]?\b", re.I), ["senior", "older adult", "mature adult"]),
    (re.compile(r"\bbeginner[s]?\b|\bnew(comer)?\b", re.I), ["beginner"]),
    (re.compile(r"\bkids?\b|\bchild(ren)?\b|\byoung\b", re.I), ["child", "kids"]),
    (re.compile(r"\bteen(ager)?s?\b", re.I), ["teen"]),
)


def detect_audience_terms(*texts: str) -> list[str]:
    blob = " ".join(str(t or "") for t in texts)
    out: list[str] = []
    for pattern, terms in _AUDIENCE_PATTERNS:
        if pattern.search(blob):
            for t in terms:
                if t not in out:
                    out.append(t)
    return out


# ---------------------------------------------------------------------------
# Title / subtitle / author identity resolution
#
# A stored "title" field is sometimes actually a raw topic/product
# description (a full descriptive sentence used to brief the manuscript
# generator), never meant to be typeset on a cover. The manuscript's own H1
# heading is the authored, reader-facing title. This resolver prefers an
# already-short, already-distinct stored title; otherwise it falls back to
# parsing the manuscript H1 (and, if present, an author byline just below
# it) rather than inventing or regenerating anything.
# ---------------------------------------------------------------------------
_H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_BYLINE_RE = re.compile(r"^\*?\s*by\s+([A-Z][\w.'\-]*(?:\s+[A-Z][\w.'\-]*){0,3})\s*\*?\s*$", re.MULTILINE | re.I)

_MAX_COVER_TITLE_WORDS = 12


def _looks_like_raw_description(title: str, topic: str) -> bool:
    title = str(title or "").strip()
    topic = str(topic or "").strip()
    if not title:
        return True
    if topic and title.lower() == topic.lower():
        # The title field is literally the same string used to brief content
        # generation -- a description, not an authored cover title.
        return True
    if len(title.split()) > _MAX_COVER_TITLE_WORDS:
        return True
    return False


GENERIC_AI_QUALITY_EXCLUSIONS = (
    "no extra or missing fingers", "no merged hands or equipment", "no distorted or "
    "broken-looking equipment", "no impossible or unsafe body positions", "no watermark",
    "no logos", "no generated text or lettering", "realistic anatomy", "realistic hands",
)


def build_visual_style_spec(
    *,
    title: str = "",
    topic: str = "",
    audience: str = "",
    tone: str = "",
) -> dict[str, Any]:
    """A reusable style specification for one project's AI-generated visuals.

    Not tied to any topic: every field is derived from this project's own
    editorial context. Kept on the project (not regenerated per image) and
    repeated in every AI prompt for that project so the generated set reads
    as one consistent visual production, per the provider's lack of native
    reference-image/character-consistency support here.
    """
    equipment = detect_equipment_terms(title, topic)
    audience_terms = detect_audience_terms(audience, title, topic)
    tone_words = [t.strip() for t in re.split(r"[,;]", tone) if t.strip()] or [
        "safe", "encouraging", "professional", "approachable", "credible",
    ]
    return {
        "equipment": equipment,
        "audience": audience_terms,
        "tone": tone_words,
        "environment": "clean, uncluttered, professionally lit indoor setting",
        "consistency_note": (
            "Use the same model age range, clothing style, and environment "
            "across every image generated for this project."
        ),
        "exclusions": list(GENERIC_AI_QUALITY_EXCLUSIONS) + list(excluded_equipment_terms(equipment) if equipment else []),
    }


def style_spec_prompt_suffix(spec: dict[str, Any] | None) -> str:
    """Render a style spec into a short prompt suffix, repeated on every call."""
    spec = spec if isinstance(spec, dict) else {}
    parts: list[str] = []
    audience = spec.get("audience") or []
    if audience:
        parts.append(f"Model should read as {', '.join(audience[:2])}.")
    tone = spec.get("tone") or []
    if tone:
        parts.append(f"Tone: {', '.join(tone[:4])}.")
    env = spec.get("environment") or ""
    if env:
        parts.append(f"Setting: {env}.")
    parts.append(str(spec.get("consistency_note") or ""))
    exclusions = spec.get("exclusions") or []
    if exclusions:
        parts.append("Avoid: " + ", ".join(exclusions[:12]) + ".")
    return " ".join(p for p in parts if p).strip()


def resolve_cover_identity(
    *,
    stored_title: str = "",
    stored_subtitle: str = "",
    stored_author: str = "",
    topic: str = "",
    content_md: str = "",
) -> dict[str, str]:
    """Return the {title, subtitle, author} that should be typeset on the cover.

    Never invents a title: prefers a stored title that isn't just the raw
    topic/description, otherwise parses the manuscript's own H1 (splitting
    "Title: Subtitle" on the first colon, matching how this codebase already
    derives subtitles from manuscript content elsewhere), and only fills
    author from a manuscript byline when nothing was already stored.
    """
    title = str(stored_title or "").strip()
    subtitle = str(stored_subtitle or "").strip()
    author = str(stored_author or "").strip()

    if _looks_like_raw_description(title, topic):
        h1_match = _H1_RE.search(str(content_md or ""))
        if h1_match:
            h1 = h1_match.group(1).strip()
            colon_split = re.match(r"^([^:]+):\s*(.+)$", h1)
            if colon_split:
                title = colon_split.group(1).strip()
                if not subtitle:
                    subtitle = colon_split.group(2).strip()
            else:
                title = h1

    if not author:
        byline_match = _BYLINE_RE.search(str(content_md or ""))
        if byline_match:
            author = byline_match.group(1).strip()

    return {"title": title, "subtitle": subtitle, "author": author}
