"""Free topic-word lookup shared by Word Search and Crossword.

Uses Datamuse's read-only ``/words`` endpoint. Only the topic text is sent;
customer names, titles, manuscript text, and other project fields are never
included. Results are cached in-process to avoid repeated requests during a
single book build. No paid or generative service is called here.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_ENDPOINT = "https://api.datamuse.com/words"
_TIMEOUT_SECONDS = 4.0
_CACHE_TTL_SECONDS = 6 * 60 * 60
_MAX_RESULTS = 100
_MAX_TOPIC_CHARS = 120
_MIN_WORD_LENGTH = 3
_MAX_WORD_LENGTH = 18
_STOP_WORDS = {
    "answer", "discover", "explore", "find", "fun", "game", "games",
    "grid", "letter", "letters", "list", "play", "puzzle", "search",
    "theme", "thing", "things", "topic", "word", "words",
}


@dataclass
class TopicWordResult:
    words: list[str] = field(default_factory=list)
    clues: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    source: str = ""


_cache: dict[tuple[str, bool], tuple[float, TopicWordResult]] = {}
_cache_lock = threading.Lock()


def _fetch_json(url: str) -> object:
    request = Request(
        url,
        headers={"Accept": "application/json", "User-Agent": "DigitalProductFactory/1.9.16"},
    )
    with urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
        if getattr(response, "status", 200) != 200:
            raise OSError(f"Topic word source returned HTTP {response.status}.")
        raw = response.read(1_000_000)
    return json.loads(raw.decode("utf-8"))


def _clean_word(raw: object, *, crossword: bool) -> str:
    word = re.sub(r"\s+", " ", str(raw or "").strip().lower())
    if not word or len(word) > 40 or not re.fullmatch(r"[a-z]+(?: [a-z]+)*", word):
        return ""
    letters = word.replace(" ", "")
    if not _MIN_WORD_LENGTH <= len(letters) <= _MAX_WORD_LENGTH:
        return ""
    if word in _STOP_WORDS or any(token in _STOP_WORDS for token in word.split()):
        return ""
    if crossword and (" " in word or not 3 <= len(letters) <= 9):
        return ""
    return word.title()


def lookup_topic_words(
    topic: str,
    target_count: int,
    *,
    crossword: bool = False,
    fetch_json=None,
    use_cache: bool = True,
) -> TopicWordResult:
    """Return relevant free words; crossword mode also requires real clues.

    ``fetch_json`` is injectable for deterministic tests. A failed or thin
    response returns no words and a clear error; it never inserts generic
    filler. The crossword path uses locally generated clues; it does not
    republish third-party dictionary definitions in a commercial PDF.
    """
    topic_clean = re.sub(r"\s+", " ", str(topic or "").strip())
    if not topic_clean:
        return TopicWordResult(errors=["Enter a topic before searching for words."])
    if len(topic_clean) > _MAX_TOPIC_CHARS:
        return TopicWordResult(
            errors=[f"Topic must be {_MAX_TOPIC_CHARS} characters or fewer for free word lookup."],
            source="datamuse",
        )
    if fetch_json is None and str(os.environ.get("FACTORY_TEST_MODE") or "") == "1":
        return TopicWordResult(
            warnings=["Free topic lookup is disabled in Factory test mode."],
            errors=["The free word source is unavailable in test mode. Add a custom word list."],
            source="datamuse",
        )
    try:
        target = max(1, min(int(target_count or 1), _MAX_RESULTS))
    except (TypeError, ValueError):
        target = 12
    key = (topic_clean.casefold(), bool(crossword))
    now = time.monotonic()
    if use_cache:
        with _cache_lock:
            cached = _cache.get(key)
            if cached and now - cached[0] < _CACHE_TTL_SECONDS:
                return TopicWordResult(
                    words=list(cached[1].words[:target]),
                    clues=dict(list(cached[1].clues.items())[:target]),
                    warnings=list(cached[1].warnings),
                    errors=list(cached[1].errors),
                    source=cached[1].source,
                )

    params = {"ml": topic_clean, "max": str(_MAX_RESULTS), "md": "p"}
    url = f"{_ENDPOINT}?{urlencode(params)}"
    fetch = fetch_json or _fetch_json
    try:
        payload = fetch(url)
    except Exception as exc:
        result = TopicWordResult(
            warnings=[f"Free topic lookup is unavailable ({type(exc).__name__})."],
            errors=["The free word source is unavailable right now. Add a custom word list and try again."],
            source="datamuse",
        )
        return result

    rows = payload if isinstance(payload, list) else []
    words: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        display = _clean_word(row.get("word"), crossword=crossword)
        normalized = display.replace(" ", "").casefold()
        if not display or normalized in seen:
            continue
        seen.add(normalized)
        words.append(display)

    minimum = 8 if crossword else 4
    result = TopicWordResult(
        words=words,
        clues={},
        warnings=[f"Found {len(words)} words from the free Datamuse vocabulary."],
        errors=[] if len(words) >= minimum else [
            f'The free word source found only {len(words)} usable words for "{topic_clean}". '
            "Add a custom word list or choose a broader topic."
        ],
        source="datamuse",
    )
    if use_cache:
        with _cache_lock:
            _cache[key] = (now, result)
    return TopicWordResult(
        words=list(result.words[:target]),
        clues={},
        warnings=list(result.warnings),
        errors=list(result.errors),
        source=result.source,
    )


def clear_topic_word_cache() -> None:
    """Clear process-local lookup data; exposed for tests and operations."""
    with _cache_lock:
        _cache.clear()
