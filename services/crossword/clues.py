"""Crossword clue helpers — separate from Word Search."""
from __future__ import annotations

import json
import os
import re

from services.factory.topic_intelligence import (
    build_local_clue,
    generate_local_clues_for_words,
    is_placeholder_phrase,
)
from services.crossword.crossword_fallback import _ALL_PACKS, get_fallback_words_and_clues

# ---------------------------------------------------------------------------
# Crossword fallback library — cached lookup for verified real clues.
# Used as the last resort before generating a rule-based clue.
# Loaded lazily on first use.
# ---------------------------------------------------------------------------
_FALLBACK_CACHE: dict[str, str] | None = None


def _get_fallback_clue_map() -> dict[str, str]:
    """Load ALL words+clues from every crossword fallback pack (one-time cost).

    Loads from all 8 packs: everyday_life, children, food, nature, technology,
    activities, places, seasons.  Previously only loaded everyday_life, causing
    HIKING/JOGGING/CLIMBING/CAMPING to miss the cache and fall through to
    _topic_aware_clue, which produced the generic 'related to daily.' clue.
    """
    global _FALLBACK_CACHE
    if _FALLBACK_CACHE is not None:
        return _FALLBACK_CACHE
    cache: dict[str, str] = {}
    for pack_key, pack in _ALL_PACKS.items():
        for word, clue in pack:
            # Normalize: remove spaces AND hyphens so FORTY-NINER and FORTYNINER map to the same key
            normalized = re.sub(r"[\s-]+", "", str(word)).upper()
            if normalized and normalized not in cache:
                cache[normalized] = clue
    _FALLBACK_CACHE = cache
    return _FALLBACK_CACHE

_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "crossword_clues.json")
_CLUE_PACKS: dict[str, dict[str, str]] | None = None


def _load_clue_packs() -> dict[str, dict[str, str]]:
    global _CLUE_PACKS
    if _CLUE_PACKS is not None:
        return _CLUE_PACKS
    _CLUE_PACKS = {}
    try:
        with open(_DATA_PATH, encoding="utf-8") as handle:
            raw = json.load(handle)
        if isinstance(raw, dict):
            for pack_name, entries in raw.items():
                if isinstance(entries, dict):
                    _CLUE_PACKS[str(pack_name)] = {
                        str(word).upper(): str(clue) for word, clue in entries.items()
                    }
    except (OSError, json.JSONDecodeError):
        pass
    return _CLUE_PACKS


def _theme_pack_key(theme: str) -> str | None:
    lowered = str(theme or "").strip().lower()
    if not lowered:
        return None
    # Map theme keywords to clue pack names
    if "black history" in lowered or "african american" in lowered:
        return "black_history"
    if "animal" in lowered or "animals" in lowered:
        return "animals"
    if lowered in {"food", "foods"}:
        return "food"
    if lowered in {"sport", "sports"}:
        return "sports"
    if "plant" in lowered or "botany" in lowered or "photosynthesis" in lowered:
        return "plant_parts"
    if "human body" in lowered or "anatomy" in lowered or lowered in {"organs", "skeleton", "muscles"}:
        return "human_body"
    if "ecolog" in lowered or "ecosystem" in lowered or "environment" in lowered or "habitat" in lowered:
        return "ecology"
    if "dinosaur" in lowered or "fossil" in lowered or "prehistoric" in lowered:
        return "dinosaurs"
    if "electric" in lowered or "circuit" in lowered or "magnet" in lowered:
        return "electricity"
    if "chemist" in lowered or "atom" in lowered or "molecule" in lowered or "periodic table" in lowered:
        return "chemistry"
    if "solar system" in lowered or lowered in {"planets", "planet", "galaxy", "astronomy", "space"}:
        return "solar_system"
    if "weather" in lowered or "meteor" in lowered:
        return "weather"
    if "scien" in lowered or lowered == "science":
        return "science"
    if "geo" in lowered or lowered in {"country", "countries", "state", "states"}:
        return "geography"
    if lowered in {"history", "historical"}:
        return "history"
    if "music" in lowered or "musical" in lowered:
        return "music"
    if "nature" in lowered or "natural" in lowered or lowered in {"rainforest", "forest", "ocean", "river"}:
        return "nature"
    if "computer" in lowered or "laptop" in lowered or "desktop" in lowered or "hardware" in lowered:
        return "computer_parts"
    if "fruit" in lowered:
        return "fruits"
    if "school supply" in lowered or "stationery" in lowered:
        return "school_supplies"
    if "math" in lowered or "arithmetic" in lowered or "geometry" in lowered or "algebra" in lowered:
        return "math_terms"
    if "body part" in lowered and "human body" not in lowered:
        return "body_parts"
    if "transport" in lowered or "vehicle" in lowered or "car" in lowered or "bus" in lowered:
        return "transportation"
    if "community helper" in lowered or "occupation" in lowered or "professions" in lowered or "jobs" in lowered:
        return "community_helpers"
    if "classroom" in lowered or "education" in lowered:
        return "classroom_vocabulary"
    if "farm" in lowered or "harvest" in lowered or "agriculture" in lowered or "orchard" in lowered:
        return "farm_products"
    if "ocean animal" in lowered or "sea animal" in lowered or "marine" in lowered:
        return "ocean_animals"
    if "insect" in lowered or "bug" in lowered or "creepy" in lowered:
        return "insects_bugs"
    return None


def lookup_clue(answer: str, *, theme: str = "") -> str | None:
    answer = re.sub(r"\s+", "", answer).upper()
    if not answer:
        return None
    packs = _load_clue_packs()
    pack_key = _theme_pack_key(theme)
    if pack_key and pack_key in packs:
        clue = packs[pack_key].get(answer)
        if clue:
            return clue
    general = packs.get("general") or {}
    found = general.get(answer)
    if found:
        return found
    # Check all packs in case the word exists in another theme pack
    theme_lower = str(theme or "").strip().lower()
    for pkey, entries in packs.items():
        if pkey != "general" and pkey != pack_key:
            if theme_lower and pkey in theme_lower:
                continue  # skip the theme pack (already checked)
            clue = entries.get(answer)
            if clue:
                return clue
    return None


def simple_clue(answer: str, theme: str = "") -> str:
    """Deterministic real clue — no placeholder phrases, no OpenAI.

    Priority:
      1. Clue from the theme-matched crossword fallback pack (e.g. gold_rush),
         so Gold Rush words never receive generic geography/nature clues.
      2. Clue from the theme-matched pack (crossword_clues.json).
      3. Clue from the crossword fallback library (any pack).
      4. Rule-based clue builder — natural description, never placeholders.
    """
    from services.crossword.crossword_fallback import _normalize_theme

    answer_key = re.sub(r"[^A-Z0-9]", "", str(answer or "").strip().upper())
    theme_pack = _normalize_theme(theme)
    if theme_pack and theme_pack in _ALL_PACKS:
        for word, clue in _ALL_PACKS[theme_pack]:
            if re.sub(r"[^A-Z0-9]", "", str(word).upper()) == answer_key and clue:
                return clue

    found = lookup_clue(answer, theme=theme)
    if found:
        return found
    fb = _get_fallback_clue_map()
    fb_clue = fb.get(answer_key)
    if fb_clue:
        return fb_clue
    return build_local_clue(answer, topic=theme)


def generate_clues_for_words(words: list[str], *, theme: str = "") -> dict[str, str]:
    """Build a clue map for crossword answers using local real clue generation."""
    clues: dict[str, str] = {}
    for word in words:
        answer = re.sub(r"\s+", "", word).upper()
        if not answer:
            continue
        clues[answer] = simple_clue(answer, theme=theme)
    return clues


def generate_clues_from_ai(words: list[str], *, theme: str) -> dict[str, str]:
    """Generate short crossword clues via the shared AI client."""
    from ai_client import chat

    answers = [re.sub(r"\s+", "", w).upper() for w in words if w]
    if not answers:
        return {}

    baseline = generate_clues_for_words(answers, theme=theme)
    numbered = "\n".join(f"{idx + 1}. {ans}" for idx, ans in enumerate(answers))
    system = "You write concise crossword clues. Return JSON only: {\"WORD\": \"clue text\", ...}"
    user = (
        f"Theme: {theme}\n"
        f"Write one clear crossword clue per answer:\n{numbered}\n"
        "Clues should be short (under 14 words), educational, and match the theme."
    )
    try:
        raw = chat(system=system, user=user, max_completion_tokens=1200)
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.lstrip().lower().startswith("json"):
                text = text.lstrip()[4:]
        data = json.loads(text.strip())
        if isinstance(data, dict):
            merged = dict(baseline)
            for key, value in data.items():
                clue = str(value or "").strip()
                if clue:
                    merged[str(key).upper()] = clue
            return merged
    except Exception:
        pass
    return baseline
