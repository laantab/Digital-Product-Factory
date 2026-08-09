"""Word list parsing and local topic vocabulary (no API calls)."""
from __future__ import annotations

import json
import math
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
class WordEntry:
    """Display form for word bank; grid form for puzzle placement."""

    display: str
    grid: str


@dataclass
class ParsedWordList:
    entries: list[WordEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def _load_topics_data() -> dict:
    with open(_DATA_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def _display_cleanup(raw: str) -> str:
    cleaned = _NON_LETTER_RE.sub("", raw.strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _to_grid_form(display: str) -> str:
    return re.sub(r"\s+", "", display).upper()


def _is_valid_display(display: str) -> bool:
    letters = re.sub(r"\s+", "", display)
    return len(letters) >= 2 and letters.isalpha()


def parse_custom_word_list(raw: str, *, grid_size: int) -> ParsedWordList:
    """
    Parse pasted or uploaded word lists.

    - Trims spaces
    - Removes duplicates (case/spacing insensitive)
    - Keeps readable phrases in the word bank
    - Uses space-stripped uppercase forms for grid placement
    - Rejects words longer than grid_size with clear warnings
    """
    result = ParsedWordList()
    if not str(raw or "").strip():
        result.errors.append("Word list is empty. Paste at least one word or phrase.")
        return result

    seen: set[str] = set()
    for piece in _SPLIT_RE.split(str(raw)):
        display = _display_cleanup(piece)
        if not display:
            continue

        if not _is_valid_display(display):
            result.warnings.append(f'Skipped invalid entry: "{piece.strip()}" (use letters only).')
            result.rejected.append(piece.strip())
            continue

        grid = _to_grid_form(display)
        key = grid
        if key in seen:
            result.warnings.append(f'Duplicate removed: "{display}".')
            continue
        seen.add(key)

        if len(grid) > grid_size:
            result.warnings.append(
                f'"{display}" is too long for a {grid_size}x{grid_size} grid '
                f"({len(grid)} letters; maximum is {grid_size})."
            )
            result.rejected.append(display)
            continue

        result.entries.append(WordEntry(display=display, grid=grid))

    if not result.entries and not result.errors:
        result.errors.append("No usable words found after cleaning the list.")

    return result


def word_list_fetch_target(required: int) -> int:
    """Return how many words to request so filtering still leaves enough."""
    required = max(1, int(required))
    return required + max(10, int(math.ceil(required * 0.15)))


def _entries_from_display_words(
    words: list[str],
    *,
    grid_size: int,
    seen: set[str],
) -> list[WordEntry]:
    added: list[WordEntry] = []
    for word in words:
        parsed = parse_custom_word_list(str(word), grid_size=grid_size)
        for entry in parsed.entries:
            if entry.grid in seen:
                continue
            seen.add(entry.grid)
            added.append(entry)
    return added


def supplement_entries_to_count(
    entries: list[WordEntry],
    target: int,
    *,
    grid_size: int,
    topic: str = "",
    matched_pack_id: str = "",
) -> tuple[list[WordEntry], list[str]]:
    """Fill a short word list using ONLY the matched topic pack or generic fallback.

    NEVER cross-supplement with unrelated topic packs.
    """
    warnings: list[str] = []
    target = max(1, int(target))
    if len(entries) >= target:
        return list(entries), warnings

    seen = {entry.grid for entry in entries}
    expanded = list(entries)
    starting_count = len(expanded)

    topic_clean = str(topic or "").strip()
    if topic_clean and matched_pack_id:
        # Only try to re-fetch the same matched pack — no cross-pack supplementation
        suggested, topic_warnings, _, _ = suggest_words_from_topic(
            topic_clean,
            max_words=word_list_fetch_target(target - starting_count),
        )
        warnings.extend(topic_warnings)
        for entry in _entries_from_display_words(suggested, grid_size=grid_size, seen=seen):
            expanded.append(entry)
            if len(expanded) >= target:
                break

    # Only use generic_fallback — NEVER pull from unrelated topic packs
    if len(expanded) < target:
        data = _load_topics_data()
        pool: list[str] = list(data.get("generic_fallback", []))
        # If we have a matched pack, also allow words from that pack
        if matched_pack_id:
            for pack in data.get("topics", []):
                if str(pack.get("id", "")) == matched_pack_id:
                    pool.extend(pack.get("words", []))
                    break
        for entry in _entries_from_display_words(pool, grid_size=grid_size, seen=seen):
            expanded.append(entry)
            if len(expanded) >= target:
                break

    added = len(expanded) - starting_count
    if added > 0:
        warnings.append(f"Added {added} extra word(s) to reach the requested worksheet count.")

    return expanded, warnings


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


def suggest_words_from_topic(
    topic: str,
    audience: str = "",
    *,
    max_words: int = 12,
) -> tuple[list[str], list[str], list[str], str]:
    """
    Local topic vocabulary lookup only — no OpenAI/Tavily.

    Returns (suggested_display_words, warnings, errors, matched_pack_id).
    matched_pack_id is "" when no topic pack matched (fallback used).
    """
    warnings: list[str] = []
    errors: list[str] = []

    topic_clean = str(topic or "").strip()
    if not topic_clean:
        errors.append("Topic is required for Create From Topic mode.")
        return [], warnings, errors, ""

    data = _load_topics_data()
    topic_lower = topic_clean.lower()
    audience_note = str(audience or "").strip()

    best_score = 0
    best_words: list[str] = []
    best_id = ""

    for entry in data.get("topics", []):
        score = _score_topic_match(topic_lower, entry.get("keywords", []))
        if score > best_score:
            best_score = score
            best_words = list(entry.get("words", []))
            best_id = str(entry.get("id", ""))

    # Require minimum score of 2 to use a matched pack (prevents false-positive
    # matches like "plant_parts" for "computer parts" where only "parts" matched).
    # Score of 2 means: 2 partial token overlaps, or 1 full keyword hit.
    _MIN_SCORE = 2

    def _semantic_relevance(pack_words: list[str], topic_l: str) -> bool:
        """Return True if >= 50% of topic words appear in the matched pack's word list.

        Checks topic words against the actual PACK WORDS (e.g. "Goals"/"Metric" for
        business_training), not the keyword list. This catches false positives like
        "Purple Moon Business Ideas" matching business_training: "business" hits the
        keyword list, but none of the pack words (Goals/Metric/etc.) relate to the
        specific topic "Purple Moon Business Ideas".
        """
        topic_words = {t.lower() for t in re.split(r"[^A-Za-z0-9]+", topic_l) if len(t) >= 3}
        if not topic_words:
            return False
        # Collect all pack words (deduplicated) for the matched pack
        for entry in data.get("topics", []):
            if str(entry.get("id", "")) == best_id:
                all_pack_words = [w.lower() for w in entry.get("words", [])]
                match_count = sum(
                    1 for tw in topic_words
                    if any(tw in pw or pw in tw for pw in all_pack_words)
                )
                return match_count >= max(1, int(len(topic_words) * 0.50))
        return False

    # Use pack when score >= _MIN_SCORE AND (score >= 5 (two+ strong keyword hits, trust it)
    # OR score == 4 AND the topic is primarily about the pack domain
    # OR semantic relevance passes for score 2-3).
    #
    # Score of 4 from a single keyword hit needs extra scrutiny:
    # - "science" (1 topic word) → "science" in science_general keywords → 1/1=100% → PASS
    # - "computer parts" (2 words) → "computer" in keywords, "parts" not → 1/2=50% → PASS
    # - "Purple Moon Business Ideas" (4 words) → only "business" matches → 1/4=25% → FAIL
    #
    # Also covers: "business_training" topic → "business"+"training" both in keywords → 2/2=100% → PASS.
    confident_match = best_score >= 5
    single_strong_kw_ok = False
    if best_score == 4:
        for entry in data.get("topics", []):
            if str(entry.get("id", "")) == best_id:
                pack_keywords = {kw.lower() for kw in entry.get("keywords", [])}
                topic_significant = {
                    t for t in re.split(r"[^A-Za-z0-9]+", topic_lower) if len(t) >= 3
                }
                topic_kw_hits = sum(1 for tw in topic_significant if tw in pack_keywords)
                threshold = max(1, int(len(topic_significant) * 0.50))
                single_strong_kw_ok = topic_kw_hits >= threshold
                break
    weak_match_ok = best_score >= _MIN_SCORE and (
        _semantic_relevance(best_words, topic_lower) or single_strong_kw_ok
    )

    words: list[str] = []
    if confident_match or weak_match_ok:
        words = best_words[:max_words]
        warnings.append(f'Used local vocabulary pack "{best_id}" for topic "{topic_clean}".')
    else:
        # No confident match — use only the topic tokens themselves.
        # NEVER pull from unrelated topic packs; that caused
        # "computer parts" to get "apple, banana, cherry" from cross-pack supplementation.
        tokens = [t for t in re.split(r"[^A-Za-z0-9]+", topic_clean) if len(t) >= 3]
        words = []
        for token in tokens:
            word = token.upper()
            if word not in words:
                words.append(word)
        warnings.append(
            f'No exact local pack matched "{topic_clean}". '
            "Topic tokens used as starter words; supplementation restricted."
        )
        # Clear the matched pack id so supplement uses generic_fallback only
        best_id = ""

    if audience_note:
        warnings.append(f'Audience note "{audience_note}" recorded; word list is not API-filtered in Phase 1.')

    display_words = []
    for word in words[:max_words]:
        if word.isupper() and " " not in word:
            display_words.append(word.title() if len(word) > 3 else word)
        else:
            display_words.append(word)

    if not display_words:
        errors.append("Could not build a word list from the topic.")

    # Return the matched pack id so callers know whether to allow supplementation
    return display_words, warnings, errors, best_id
