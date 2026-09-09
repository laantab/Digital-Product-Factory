"""Shared, deterministic topic-vocabulary resolver — Crossword and Word Search.

UNIVERSAL TOPIC PUZZLE ENGINE (2026-09-08)
--------------------------------------------
Before this file existed, Crossword and Word Search each ran their own
topic-matching logic against their own, differently-shaped local data files
(data/word_search_topics.json for words, data/crossword_clues.json for
clues) with independently-written keyword-scoring code. That duplication
had two concrete failure modes, found while investigating a real customer
report ("American Automobiles" produced nothing):

  1. A topic could match a *genuinely relevant* pack that was simply small
     (e.g. Crossword's own MIN_POOL_FOR_VARIETY = 50 rule rejected a
     22-word "Container gardening" match outright, even though 22 relevant
     words is enough to build a real puzzle).
  2. Worse, the same crude substring/token scoring produced *wrong* matches
     for other topics that share no real subject with the pack they hit:
     "Dog training" scored highest against "business_training" (matched on
     the word "training" alone; the pack's own words -- GOALS, METRIC,
     CLIENT, BUDGET -- have nothing to do with dogs), and "Baseball" scored
     highest against "chemistry" (ATOM, MOLECULE, ELEMENT). Neither engine
     shipped these wrong matches to a customer (a downstream relevance/size
     gate happened to reject both), but only by accident, not by design --
     and the accident was a hard failure, not a working puzzle.

This module is the shared fix: a small, explicit, HIGH-CONFIDENCE alias
table (data/topic_vocabulary_packs.json) checked first by both engines, in
place of loose keyword-substring scoring, for the topic families it
covers. "High confidence" here means exact/near-exact phrase or single-
word alias matching only -- no fuzzy scoring, no partial-token guessing
(see resolve_topic_category). When a topic matches, the resolver returns
real, curated, hand-written words and (for Crossword) clues -- the same
data for both products, so a topic is never differently supported between
Word Search and Crossword. When nothing matches, resolve_topic_vocabulary
returns an empty result and both engines fall through UNCHANGED to their
own existing, previously-working matching logic -- this module never
overrides or removes prior behavior, it only wins when it has a real
answer, so no topic that already worked before this file existed can
regress.

No paid/network call is made anywhere in this module.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field

_DATA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "topic_vocabulary_packs.json",
)

_PACKS_CACHE: dict[str, dict] | None = None


def _load_packs() -> dict[str, dict]:
    global _PACKS_CACHE
    if _PACKS_CACHE is not None:
        return _PACKS_CACHE
    try:
        with open(_DATA_PATH, encoding="utf-8") as handle:
            _PACKS_CACHE = json.load(handle)
    except (OSError, json.JSONDecodeError):
        _PACKS_CACHE = {}
    return _PACKS_CACHE


def normalize_topic_text(topic: str) -> str:
    """Deterministic, local normalization -- no NLP model, no API.

    lowercase -> strip punctuation -> collapse whitespace -> drop a small
    set of leading/trailing filler words that carry no topic meaning
    ("a topic about X", "X ideas", "X puzzle"). Kept intentionally simple
    per the task's own instruction not to attempt uncontrolled NLP
    complexity -- this is enough to make "American Automobiles",
    "american automobiles", "American Automobiles!", and "  american
    automobiles  " resolve identically, and to strip a few common wrapper
    words customers actually type.
    """
    text = str(topic or "").strip().lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Filler words stripped from EITHER end of the normalized topic before
# alias matching -- these never carry topic meaning on their own.
_EDGE_FILLER = {
    "a", "an", "the", "about", "topic", "theme", "puzzle", "ideas",
    "words", "vocabulary", "list", "for", "on",
}


def _strip_edge_filler(tokens: list[str]) -> list[str]:
    start, end = 0, len(tokens)
    while start < end and tokens[start] in _EDGE_FILLER:
        start += 1
    while end > start and tokens[end - 1] in _EDGE_FILLER:
        end -= 1
    return tokens[start:end]


def _match_alias(topic: str) -> tuple[str | None, str, str | None]:
    """High-confidence category+alias match. Returns (category_key,
    confidence, matched_alias_normalized).

    confidence is "exact" (normalized topic equals an alias exactly, after
    filler-stripping) or "phrase" (the normalized topic contains a
    multi-word alias as a contiguous phrase, or a single-word alias as a
    whole token) or "" when nothing matched.

    Deliberately does NOT do partial-substring or single-shared-token
    scoring (e.g. "training" alone must never match "dog_training" for the
    topic "business training") -- that crude scoring is exactly what
    produced the wrong Dog training -> business_training and
    Baseball -> chemistry matches this module exists to avoid. Every
    alias is a real phrase or word a customer would plausibly type for
    that category; matching requires the actual phrase/word to be present,
    not a fragment of it.

    The matched alias is returned (not just the category) so callers can
    tell a broad request ("American Automobiles") apart from a narrower
    one that happens to share the same category (e.g. "Car Parts") --
    see SEMANTIC SCOPE below.
    """
    normalized = normalize_topic_text(topic)
    if not normalized:
        return None, "", None

    tokens = _strip_edge_filler(normalized.split())
    if not tokens:
        return None, "", None
    trimmed = " ".join(tokens)

    packs = _load_packs()

    # Exact match (after filler-stripping) beats everything.
    for category, pack in packs.items():
        for alias in pack.get("aliases", []):
            alias_norm = normalize_topic_text(alias)
            if trimmed == alias_norm:
                return category, "exact", alias_norm

    # Phrase containment: the alias appears as a contiguous run of tokens
    # inside the topic (multi-word aliases), or as a whole token (single-
    # word aliases) -- never as a bare substring of a longer, unrelated
    # word ("car" must not match inside "scary").
    token_set = set(tokens)
    best_category = None
    best_alias = None
    best_len = 0
    for category, pack in packs.items():
        for alias in pack.get("aliases", []):
            alias_norm = normalize_topic_text(alias)
            alias_tokens = alias_norm.split()
            if not alias_tokens:
                continue
            if len(alias_tokens) == 1:
                matched = alias_tokens[0] in token_set
            else:
                matched = f" {alias_norm} " in f" {trimmed} "
            if matched and len(alias_norm) > best_len:
                best_category, best_alias, best_len = category, alias_norm, len(alias_norm)

    if best_category:
        return best_category, "phrase", best_alias
    return None, "", None


def resolve_topic_category(topic: str) -> tuple[str | None, str]:
    """High-confidence category match only. Returns (category_key, confidence).

    See _match_alias for the matching rules. This wrapper drops the
    matched-alias detail that only services.factory.topic_vocabulary's own
    scope resolution needs -- existing callers (Crossword, Word Search,
    Spelling Worksheet) only ever needed the category.
    """
    category, confidence, _alias = _match_alias(topic)
    return category, confidence


def _entry_clue(entry) -> str:
    """An entry is either a plain clue string (every category before
    SEMANTIC SCOPE support), or {"clue": str, "scope": str} (categories
    that distinguish subcategories -- see SEMANTIC SCOPE). Either shape
    yields the clue text."""
    if isinstance(entry, dict):
        return str(entry.get("clue") or "")
    return str(entry or "")


def _entry_scope(entry) -> str | None:
    if isinstance(entry, dict):
        scope = entry.get("scope")
        return str(scope) if scope else None
    return None


def get_category_words(category: str) -> list[str]:
    packs = _load_packs()
    pack = packs.get(category) or {}
    return list((pack.get("entries") or {}).keys())


def get_category_clues(category: str) -> dict[str, str]:
    """All words -> clue text for a category, regardless of scope. Used
    for clue lookup on an already-selected word (see
    services.crossword.clues.simple_clue) -- selection-time scope
    narrowing happens in resolve_topic_vocabulary, not here."""
    packs = _load_packs()
    pack = packs.get(category) or {}
    entries = pack.get("entries") or {}
    return {word: _entry_clue(entry) for word, entry in entries.items()}


# ---------------------------------------------------------------------------
# SEMANTIC SCOPE (2026-09-09)
# ---------------------------------------------------------------------------
# A topic FAMILY (e.g. "automobiles") can cover more than one customer-
# requested SCOPE. "American Automobiles" means brands/models/manufacturers;
# "Car Parts" means mechanical components -- flattening both into one
# vocabulary pool let a crossword built for "American Automobiles" surface
# clues like "A vehicle's underlying structural frame" (CHASSIS) next to
# "Ford's iconic pony car" (MUSTANG), which is not what the customer asked
# for.
#
# A category opts into scope narrowing by giving its entries a "scope" tag
# (see _entry_scope) and declaring which alias implies which scope via
# "default_scope" (what the family's own broad name means) and
# "scope_by_alias" (aliases that ask for a specific narrower scope). A
# category that does neither (every other category today) is entirely
# unaffected: _category_scope_for_alias returns None, and no filtering
# happens -- this is purely additive.
def _category_scope_for_alias(category: str, matched_alias: str | None) -> str | None:
    packs = _load_packs()
    pack = packs.get(category) or {}
    scope_by_alias = pack.get("scope_by_alias") or {}
    if matched_alias and matched_alias in scope_by_alias:
        return str(scope_by_alias[matched_alias])
    return pack.get("default_scope")


@dataclass
class TopicVocabularyResult:
    normalized_topic: str
    category: str | None
    words: list[str] = field(default_factory=list)
    clues: dict[str, str] = field(default_factory=dict)
    confidence: str = ""  # "exact" | "phrase" | ""
    fallback_path: str = "none"  # "shared_pack" | "none"
    warnings: list[str] = field(default_factory=list)

    @property
    def matched(self) -> bool:
        return bool(self.category and self.words)


def resolve_topic_vocabulary(
    topic: str,
    target_count: int = 40,
    *,
    difficulty: str | None = None,
    age_group: str | None = None,
) -> TopicVocabularyResult:
    """Resolve a customer topic to real, curated words (+ clues, for
    Crossword) from the shared local pack file. Returns an empty,
    unmatched result (category=None) when nothing in the shared packs
    applies -- callers are expected to fall through to their own existing
    topic logic in that case, not to treat an empty result as failure.

    target_count only trims the returned word list; it never pads with
    unrelated words to reach a count (see Step 4's "do not pad with
    unrelated random vocabulary" -- a category that legitimately has
    fewer than target_count words simply returns fewer words, and the
    caller's own adaptive-sizing is expected to shrink the product
    accordingly rather than fail).

    SEMANTIC SCOPE (see the block above this function): a category whose
    entries carry a "scope" tag is narrowed to the scope implied by the
    *matched alias* -- "American Automobiles" (the family's default
    scope, BRAND_MODEL) never returns PART-scoped words like CHASSIS or
    BUMPER; "Car Parts" (an alias explicitly mapped to PART) returns only
    those. This never applies to a category without scope data (every
    category except automobiles, today) -- those behave exactly as
    before, unfiltered.
    """
    warnings: list[str] = []
    normalized = normalize_topic_text(topic)
    category, confidence, matched_alias = _match_alias(topic)
    if not category:
        return TopicVocabularyResult(normalized_topic=normalized, category=None)

    packs = _load_packs()
    entries = (packs.get(category) or {}).get("entries") or {}
    scope = _category_scope_for_alias(category, matched_alias)

    if scope:
        scoped_entries = {
            w: e for w, e in entries.items() if _entry_scope(e) == scope
        }
        # A scope with zero matching entries would be a data-authoring
        # mistake, not a customer-facing failure -- fall back to the full
        # pool rather than return nothing for a topic that DID match.
        if scoped_entries:
            entries = scoped_entries
        else:
            warnings.append(
                f'No "{scope}"-scoped entries found for "{category}"; using the full pack.'
            )

    clues = {w: _entry_clue(e) for w, e in entries.items()}
    words = list(clues.keys())
    target = max(1, int(target_count or 40))
    if len(words) > target:
        words = words[:target]
        clue_subset = {w: clues[w] for w in words}
    else:
        clue_subset = clues
        if len(words) < target:
            warnings.append(
                f'Using {len(words)} local "{category}" words (fewer than the {target} requested).'
            )

    warnings.append(f'Matched local topic pack "{category}" for "{topic}" ({confidence} match).')
    return TopicVocabularyResult(
        normalized_topic=normalized,
        category=category,
        words=words,
        clues=clue_subset,
        confidence=confidence,
        fallback_path="shared_pack",
        warnings=warnings,
    )
