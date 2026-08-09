"""Crossword word parsing and topic vocabulary — separate from Word Search."""
from __future__ import annotations

import json
import os
import re

from dataclasses import dataclass, field

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "word_search_topics.json",
)

_SPLIT_RE = re.compile(r"[\n,;]+")
_NON_LETTER_RE = re.compile(r"[^A-Za-z\s]")


@dataclass
class CrosswordEntry:
    display: str
    answer: str


@dataclass
class ParsedCrosswordList:
    entries: list[CrosswordEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def _load_topics_data() -> dict:
    with open(_DATA_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _display_cleanup(raw: str) -> str:
    cleaned = _NON_LETTER_RE.sub("", raw.strip())
    return re.sub(r"\s+", " ", cleaned).strip()


def _to_answer(display: str) -> str:
    return re.sub(r"\s+", "", display).upper()


def _is_valid(display: str, *, max_len: int) -> bool:
    answer = _to_answer(display)
    return 2 <= len(answer) <= max_len and answer.isalpha()


def parse_crossword_word_list(raw: str, *, max_word_len: int = 15) -> ParsedCrosswordList:
    """Parse crossword answers — letters only, 2–max_word_len characters."""
    result = ParsedCrosswordList()
    if not str(raw or "").strip():
        result.errors.append("Word list is empty. Add at least one crossword answer.")
        return result

    seen: set[str] = set()
    for piece in _SPLIT_RE.split(str(raw)):
        display = _display_cleanup(piece)
        if not display:
            continue
        answer = _to_answer(display)
        if answer in seen:
            result.warnings.append(f'Skipped duplicate: "{display}".')
            continue
        if not _is_valid(display, max_len=max_word_len):
            result.warnings.append(
                f'Skipped "{piece.strip()}" — use {2}-{max_word_len} letters for crossword answers.'
            )
            result.rejected.append(piece.strip())
            continue
        seen.add(answer)
        result.entries.append(CrosswordEntry(display=display, answer=answer))

    if not result.entries:
        result.errors.append("No valid crossword answers found after parsing.")
    return result


def _score_topic_match(topic_lower: str, keywords: list[str]) -> int:
    score = 0
    for keyword in keywords:
        kw = keyword.lower().strip()
        if not kw:
            continue
        if kw in topic_lower or topic_lower in kw:
            score += 3
        for token in topic_lower.split():
            if token == kw or kw in token or token in kw:
                score += 1
    return score


def _clean_crossword_words(raw_words: list[str], *, max_words: int, max_len: int = 15) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in raw_words:
        display = _display_cleanup(str(raw))
        answer = _to_answer(display)
        if not _is_valid(display, max_len=max_len) or answer in seen:
            continue
        seen.add(answer)
        cleaned.append(answer)
        if len(cleaned) >= max_words:
            break
    return cleaned


def suggest_crossword_words_from_topic(topic: str, *, max_words: int = 40) -> tuple[list[str], list[str], list[str]]:
    """Local topic vocabulary — uses the same topic packs as Word Search (no API).

    When the JSON pack has fewer than 50 words and a crossword fallback pack exists
    for the same topic, supplements with fallback words to ensure enough vocabulary for
    a full multi-puzzle book.
    """
    from services.factory.topic_intelligence import is_instruction_fragment

    warnings: list[str] = []
    errors: list[str] = []
    topic_clean = str(topic or "").strip()
    if not topic_clean:
        errors.append("Theme is required to suggest crossword words.")
        return [], warnings, errors

    # Reject topics that look like user instructions or field-label leakage.
    # This prevents the entire user prompt from becoming a crossword clue or word list.
    if is_instruction_fragment(topic_clean):
        errors.append(
            f'The topic "{topic_clean[:60]}" looks like an instruction, not a subject. '
            "Please enter a clear topic noun or phrase (e.g. 'Garden Vegetables', "
            "'Family Reunion', 'Space Exploration') rather than a request or instruction."
        )
        return [], warnings, errors

    data = _load_topics_data()
    topic_lower = topic_clean.lower()
    max_words = max(6, int(max_words or 10))

    best_score = 0
    best_words: list[str] = []
    best_id = ""

    for entry in data.get("topics", []):
        score = _score_topic_match(topic_lower, entry.get("keywords", []))
        if score > best_score:
            best_score = score
            best_words = list(entry.get("words", []))
            best_id = str(entry.get("id", ""))

    # Require minimum score of 2 for a confident pack match.
    # Semantic relevance check is used as extra validation for marginal keyword
    # scores (score == 2) but BYPASSED for strong keyword matches (score >= 3).
    # The char-overlap heuristic fails for theme-word matches like
    # "activities" → activities_pack (share almost no chars) even though the
    # keyword match is perfect by definition.
    _MIN_SCORE = 2

    def _semantic_relevance(pack_words: list[str], topic_l: str) -> bool:
        """Return True if >= 30% of pack words share >= 3 chars with topic."""
        topic_chars = set(topic_l.replace(" ", ""))
        if not topic_chars:
            return False
        related_count = 0
        for w in pack_words[:max_words]:
            w_chars = set(w.lower().replace(" ", ""))
            if len(topic_chars & w_chars) >= 3:
                related_count += 1
        return related_count >= max(1, int(max_words * 0.30))

    words: list[str] = []
    if best_score >= _MIN_SCORE and best_words:
        # Strong keyword match (score >= 3): bypass semantic check.
        # Marginal match (score == 2): validate with semantic relevance.
        # (A 2-token overlap like "fun" <-> "software" gets score 3 but
        # semantic check correctly rejects the unrelated computer_parts pack.)
        use_pack = (best_score >= 3) or _semantic_relevance(best_words, topic_lower)
        if use_pack:
            words = _clean_crossword_words(best_words, max_words=max_words)
            if words:
                warnings.append(f'Used local vocabulary pack "{best_id}" for topic "{topic_clean}".')

    # If the JSON pack has fewer than 50 words, supplement from the crossword fallback
    # for the same topic so the book builder has enough vocabulary for variety.
    # This prevents "excessive word repetition" errors for small JSON packs like
    # business_training (16 words) that have no crossword clue coverage.
    # ONLY supplement if the fallback pack is semantically relevant to the topic
    # (shares at least one keyword). Never supplement with an unrelated generic pack.
    _MIN_POOL_FOR_VARIETY = 50
    if 0 < len(words) < _MIN_POOL_FOR_VARIETY:
        from services.crossword.crossword_fallback import get_fallback_words_and_clues, _normalize_theme

        fb_pack_key = _normalize_theme(topic_clean)
        fb_words, _ = get_fallback_words_and_clues(topic_clean, count=_MIN_POOL_FOR_VARIETY)

        # Check if the fallback pack is actually relevant to this topic.
        # Require at least one topic keyword to match a keyword associated with the fallback pack.
        # This prevents supplementing "Purple Moon Business Ideas" with everyday_life
        # just because the topic didn't match anything specifically.
        _PACK_KEYWORDS: dict[str, frozenset[str]] = {
            "everyday_life": frozenset({"home", "household", "kitchen", "bathroom", "bedroom",
                "daily", "morning", "evening", "family", "friend", "neighbor", "laundry",
                "cleaning", "cooking", "shopping", "gardening", "everyday"}),
            "children": frozenset({"child", "children", "kids", "baby", "young", "school",
                "classroom", "learn", "student", "kid", "toddler", "preschool"}),
            "food": frozenset({"food", "cooking", "recipe", "meal", "kitchen", "eat", "foods",
                "snack", "dessert", "bakery", "breakfast", "lunch", "dinner", "brunch"}),
            "nature": frozenset({"nature", "animal", "plant", "weather", "forest", "garden",
                "ocean", "river", "mountain", "outdoor", "bird", "fish", "wildlife"}),
            "technology": frozenset({"computer", "technology", "digital", "electronic", "phone",
                "internet", "software", "robot", "laptop", "tablet", "device", "gadget", "tech"}),
            "activities": frozenset({"sport", "game", "hobby", "activity", "exercise", "fitness",
                "dance", "music", "craft", "play", "outdoor", "indoor", "recreation"}),
            "office_supplies": frozenset({"office", "supply", "supplies", "stationery", "school",
                "desk", "paper", "pencil", "pen", "notebook", "marker", "stapler", "tape",
                "teacher", "classroom", "backpack", "textbook", "calculator", "folder"}),
            "places": frozenset({"place", "travel", "city", "building", "country", "vacation",
                "hotel", "airport", "restaurant", "museum", "park", "beach", "island"}),
            "seasons": frozenset({"season", "spring", "summer", "autumn", "winter", "holiday",
                "christmas", "halloween", "easter", "thanksgiving", "weather", "snow", "sun"}),
        }
        pack_kws = _PACK_KEYWORDS.get(fb_pack_key, frozenset())
        topic_tokens = set(re.split(r"[^A-Za-z0-9]+", topic_clean.lower()))
        overlap = topic_tokens & pack_kws if pack_kws else set()

        if len(fb_words) > len(words) and overlap:
            # Merge JSON words (topic-specific) with fallback words, deduplicate
            combined = list(dict.fromkeys(words + fb_words))  # preserve order, dedupe
            words = _clean_crossword_words(combined, max_words=max_words)
            warnings.append(f'Supplemented with {len(fb_words)} fallback words for variety.')
        elif len(fb_words) <= len(words) or not overlap:
            # Fallback pack is too small OR not relevant to this topic.
            # Block: insufficient topic-matched vocabulary.
            errors.append(
                f'The topic "{topic_clean}" matched a small local vocabulary pack '
                f'({len(words)} words) with no sufficient relevant fallback. '
                f"Please provide a custom word list for this topic."
            )
            return [], warnings, errors

    # No JSON pack matched (words == 0): check if _normalize_theme maps to a
    # specific fallback pack (not generic everyday_life). If so, use that pack
    # directly. This fixes Gold Rush and any future specific pack that has no
    # JSON counterpart.
    if not words:
        from services.crossword.crossword_fallback import get_fallback_words_and_clues, _normalize_theme

        fb_pack_key = _normalize_theme(topic_clean)
        # Only use a named pack — never silently fall through to everyday_life
        if fb_pack_key and fb_pack_key not in {"everyday_life", ""}:
            fb_words, _ = get_fallback_words_and_clues(topic_clean, count=max_words)
            if fb_words:
                words = fb_words
                warnings.append(
                    f'Used fallback pack "{fb_pack_key}" for topic "{topic_clean}".'
                )
                return words[:max_words], warnings, errors

        # Fail closed for unmatched specific topics. Do not invent household /
        # everyday vocabulary or pretend title tokens are a real word list.
        errors.append(
            "Crossword could not find enough topic-relevant words and clues for this theme. "
            "Please correct the theme or provide a custom word list."
        )
        return [], warnings, errors

    if len(words) < max_words:
        warnings.append(f"Using {len(words)} topic words (fewer than requested).")
    return words[:max_words], warnings, errors


def fetch_crossword_words_from_ai(topic: str, count: int) -> str:
    """Optional AI word list for crossword themes."""
    from ai_client import chat

    system = (
        "You generate crossword puzzle answers. Return only single words, one per line, "
        "letters A-Z only, 3-12 letters, no explanations, no JSON, no markdown, "
        "no bullets, no numbering."
    )
    user = (
        f"Generate {count} unique crossword answer words about: {topic}. "
        "Use proper nouns only when essential. One word per line."
    )
    raw = chat(system=system, user=user, max_completion_tokens=max(400, count * 14))
    return "\n".join(line.strip() for line in raw.splitlines() if line.strip())
