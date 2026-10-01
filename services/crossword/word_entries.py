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
    """Score complete keyword tokens/phrases, never character fragments."""
    score = 0
    topic_tokens = topic_lower.split()
    topic_set = set(topic_tokens)
    for keyword in keywords:
        kw_tokens = re.findall(r"[a-z0-9]+", str(keyword or "").lower())
        if not kw_tokens:
            continue
        if len(kw_tokens) == 1 and kw_tokens[0] in topic_set:
            score += 3
        elif len(kw_tokens) > 1 and any(
            topic_tokens[index:index + len(kw_tokens)] == kw_tokens
            for index in range(len(topic_tokens) - len(kw_tokens) + 1)
        ):
            score += 3 * len(kw_tokens)
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


def _custom_list_error(message: str) -> str:
    text = str(message or "").strip()
    if "custom word list" in text.lower():
        return text
    return (text + " Please provide a custom word list.").strip()


def _free_words_with_specific_clues(topic: str, raw_words: list[str], *, max_words: int) -> list[str]:
    """Keep free-source answers only when local clue generation is specific.

    The free word endpoint supplies vocabulary, not licensed-to-republish
    definitions. Crossword exports use the Factory's own clue library and
    rules; if those produce a generic/repeated clue, the candidate is
    discarded and the customer gets a custom-list request instead.
    """
    from services.crossword.clues import simple_clue
    from services.factory.topic_intelligence import is_placeholder_phrase

    output: list[str] = []
    seen_clues: set[str] = set()
    topic_stub = re.sub(r"\s+", " ", str(topic or "").strip()).casefold()
    generic_markers = ("related to ", "common word:", "common everyday word:",
                       "word meaning:", "crossword answer (", "a common word:")
    for word in _clean_crossword_words(raw_words, max_words=max_words):
        clue = re.sub(r"\s+", " ", simple_clue(word, theme=topic)).strip()
        clue_key = clue.casefold()
        if (not clue or is_placeholder_phrase(clue)
                or any(marker in clue_key for marker in generic_markers)
                or (topic_stub and clue_key == f"related to {topic_stub}.")
                or clue_key in seen_clues):
            continue
        seen_clues.add(clue_key)
        output.append(word)
    return output


def suggest_crossword_words_from_topic(topic: str, *, max_words: int = 40) -> tuple[list[str], list[str], list[str]]:
    """Curated vocabulary first, then topic-aware legacy packs and free lookup.

    When the JSON pack has fewer than 50 words and a crossword fallback pack exists
    for the same topic, supplements with fallback words to ensure enough vocabulary for
    a full multi-puzzle book. A free-source answer is accepted only when the
    Factory can supply specific, non-repeated clues from its own library or
    local rules. No paid AI call is made here.
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

    max_words = max(6, int(max_words or 10))

    # UNIVERSAL TOPIC PUZZLE ENGINE: try the shared, high-confidence topic
    # pack first (services.factory.topic_vocabulary) -- real, curated,
    # topic-relevant words for both Crossword and Word Search, matched by
    # exact/phrase alias rather than the looser keyword-scoring below (see
    # topic_vocabulary.py's own docstring for the false-positive matches
    # that scoring produced, e.g. "Dog training" -> business_training).
    # Falls through UNCHANGED to the existing logic when no shared pack
    # matches, so no previously-working topic can regress.
    from services.factory.topic_vocabulary import resolve_topic_vocabulary

    shared = resolve_topic_vocabulary(topic_clean, max_words)
    if shared.matched:
        warnings.extend(shared.warnings)
        # Grid-aware filtering (Step 14): a crossword cell only ever holds
        # a single A-Z letter, so a pack word containing a digit or other
        # non-letter character (e.g. "OMEGA3") gets silently truncated by
        # the grid parser downstream (to "OMEGA") -- and that truncated
        # form then no longer matches the pack's own clue dictionary key,
        # falling through to the generic "Related to <topic>." clue. Word
        # Search tolerates such characters fine (no clue lookup involved),
        # so this filter is Crossword-specific, applied here rather than
        # in the shared resolver itself.
        letters_only = [w for w in shared.words if re.fullmatch(r"[A-Za-z]+", w or "")]
        # Grid-aware filtering (Step 14), continued: a word longer than 9
        # letters occasionally triggers a pre-existing clue-numbering
        # defect in the grid renderer (services.crossword.engine) once
        # placed on the customer's grid (11x11 to 21x21, 15x15 default) --
        # reproduced directly: a curated word list including 10-13 letter
        # compound terms (e.g. "BASEBALLCAP", "WORLDSERIES") failed
        # Crossword's own "Duplicate clue numbers detected on the grid"
        # QA check in roughly 1 of every 6 builds; the same list capped at
        # 9 letters passed 40/40. Every category still keeps at least 14
        # words after this cap (see the pack audit in this task's work
        # log), so this never starves a puzzle -- it only removes the
        # handful of words too long to place reliably.
        safe_length = [w for w in letters_only if len(w) <= 9]
        return safe_length[:max_words], warnings, errors

    data = _load_topics_data()
    topic_lower = topic_clean.lower()

    best_score = 0
    best_words: list[str] = []
    best_id = ""

    for entry in data.get("topics", []):
        score = _score_topic_match(topic_lower, entry.get("keywords", []))
        if score > best_score:
            best_score = score
            best_words = list(entry.get("words", []))
            best_id = str(entry.get("id", ""))

    # Require complete-token keyword matches and a topic-to-vocabulary check.
    # The old substring shortcut let "Beekeeping" become a generic insect pack.
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
        use_pack = _semantic_relevance(best_words, topic_lower)
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
            from services.factory.topic_word_source import lookup_topic_words

            free_result = lookup_topic_words(topic_clean, max_words, crossword=True)
            free_words = _free_words_with_specific_clues(topic_clean, free_result.words, max_words=max_words)
            if len(free_words) >= 8:
                words = _clean_crossword_words(list(dict.fromkeys(words + free_words)), max_words=max_words)
                warnings.extend(free_result.warnings)
                warnings.append(f'Used free vocabulary source for "{topic_clean}".')
            else:
                errors.append(_custom_list_error(
                    free_result.errors[0] if free_result.errors else
                    f'The topic "{topic_clean}" has too few relevant words and clues.'
                ))
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

        # No local curated or named fallback pack matched. Try the free
        # semantic word source, requiring real dictionary definitions so
        # the crossword never exports placeholder clues.
        from services.factory.topic_word_source import lookup_topic_words

        free_result = lookup_topic_words(topic_clean, max_words, crossword=True)
        free_words = _free_words_with_specific_clues(topic_clean, free_result.words, max_words=max_words)
        if len(free_words) >= 8:
            warnings.extend(free_result.warnings)
            warnings.append(f'Used free vocabulary source for "{topic_clean}".')
            return free_words, warnings, errors

        # Fail closed for unmatched specific topics. Do not invent household /
        # everyday vocabulary or pretend title tokens are a real word list.
        errors.append(_custom_list_error(
            free_result.errors[0] if free_result.errors else
            "Crossword could not find enough topic-relevant words and clues for this theme. "
            "Please correct the theme."
        ))
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
