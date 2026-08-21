"""Pexels stock search for Ebook covers. Key stays server-side.

Tests must mock HTTP. FACTORY_TEST_MODE never performs a live Pexels call.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from dotenv import load_dotenv

_FLASK_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_FLASK_APP_DIR, ".env"))

PEXELS_NOT_CONFIGURED = (
    "Pexels is not configured. Add a Pexels API key or upload your own photograph."
)
PEXELS_CONNECTED = "Pexels connected"
PEXELS_NOT_CONFIGURED_STATUS = "Pexels not configured"
PEXELS_SEARCH_URL = "https://api.pexels.com/v1/search"
PEXELS_PHOTO_URL = "https://api.pexels.com/v1/photos/{photo_id}"
SUGGESTED_SEARCHES = (
    "event photographer camera",
    "photographer at celebration",
    "wedding event photography",
    "photo printing event",
    "professional camera celebration",
)
LICENSE_NOTE = (
    "Pexels License: free to use; photographer attribution recorded. "
    "This Factory does not certify model releases, trademark clearance, or Amazon approval."
)


class PexelsError(ValueError):
    """Structured Pexels workflow error. Must never include the API key."""

    def __init__(self, message: str, code: str = "request_failed"):
        self.code = str(code or "request_failed")
        super().__init__(_scrub(str(message or "Pexels request failed.")))


CUSTOMER_PEXELS_MESSAGES = {
    "missing_config": PEXELS_NOT_CONFIGURED,
    "unauthorized": "Stock photographs are unavailable right now.",
    "rate_limit": "Stock photographs are temporarily unavailable. Try again later.",
    "network": "Stock photographs could not be reached.",
    "invalid_response": "Stock photographs could not be loaded.",
    "no_match": "No matching photograph was found.",
    "test_blocked": "Pexels live calls are blocked in test mode.",
    "request_failed": "Stock photographs could not be loaded.",
}


def customer_pexels_message(exc: Exception | None = None, *, code: str = "") -> str:
    key = str(code or getattr(exc, "code", "") or "request_failed")
    return CUSTOMER_PEXELS_MESSAGES.get(key, CUSTOMER_PEXELS_MESSAGES["request_failed"])


def _sanitize_installed_key(raw: str) -> str:
    text = str(raw or "").strip().strip("\"'").strip()
    lowered = text.lower()
    for prefix in ("bearer ", "api key:", "api_key:", "key:", "key "):
        if lowered.startswith(prefix):
            text = text[len(prefix) :].strip().strip("\"'")
            lowered = text.lower()
    # Copied dashboard labels often glue "Key" onto the token with no space.
    glued = re.match(r"(?i)^key(?=[A-Za-z0-9]{20,})", text)
    if glued:
        text = text[glued.end() :].strip().strip("\"'")
    return text


def pexels_api_key() -> str:
    return _sanitize_installed_key(os.environ.get("PEXELS_API_KEY") or "")


def pexels_configured() -> bool:
    return bool(pexels_api_key())


def pexels_status_label() -> str:
    """Safe operator-facing status. Never includes the API key."""
    return PEXELS_CONNECTED if pexels_configured() else PEXELS_NOT_CONFIGURED_STATUS


def pexels_public_status() -> dict[str, Any]:
    configured = pexels_configured()
    return {
        "configured": configured,
        "status": pexels_status_label(),
        "code": "ok" if configured else "missing_config",
        "authenticated": None,
        "message": "" if configured else PEXELS_NOT_CONFIGURED,
        "suggested": list(SUGGESTED_SEARCHES),
        "attribution_required": True,
    }


def pexels_health(*, live_auth: bool = False) -> dict[str, Any]:
    """Safe health result. Never includes the API key."""
    status = pexels_public_status()
    if not status["configured"]:
        return {**status, "authenticated": False, "code": "missing_config"}
    if not live_auth or str(os.environ.get("FACTORY_TEST_MODE") or "") == "1":
        return status
    try:
        search_pexels("plant", per_page=1, orientation="portrait")
        return {
            **status,
            "authenticated": True,
            "code": "ok",
            "status": PEXELS_CONNECTED,
            "message": "",
        }
    except PexelsError as exc:
        return {
            **status,
            "configured": True,
            "authenticated": False,
            "code": exc.code,
            "status": "Pexels authentication failed",
            "message": customer_pexels_message(exc),
        }


_QUERY_STOP = {
    "a", "an", "the", "and", "or", "of", "for", "to", "your", "how", "with",
    "in", "on", "at", "from", "into", "keep", "this", "that", "why", "what",
    "when", "which", "who", "can", "could", "should", "including", "include",
    "choose", "choosing", "beginner", "beginners", "guide", "book", "ebook",
    "cover", "portrait", "landscape", "chapter", "practical", "ways", "simple",
    "grow", "growing", "make", "making", "learn", "learning", "using", "use",
    "about", "their", "them", "they", "you", "our", "its", "onto", "over",
    "under", "than", "also", "just", "very", "more", "most", "some", "any",
    "step", "steps", "tips", "complete", "introduction", "relevant", "photograph",
    "photographs", "image", "images", "visual", "caption", "scene",
}

_COVER_GARDEN_QUERIES = (
    "container vegetable garden patio",
    "tomatoes herbs pots garden",
    "balcony vegetable garden",
    "colorful vegetables growing containers",
    "container garden tomatoes lettuce herbs",
)

_CHAPTER_GARDEN_QUERIES = (
    (
        ("start", "beginner", "getting started", "works for"),
        ("beginner container garden", "balcony herb pots", "small patio vegetable pots"),
    ),
    (
        ("soil", "container", "potting", "choosing the right"),
        ("garden pots and potting soil", "potting mix vegetable container", "drainage pots garden"),
    ),
    (
        ("vegetable", "herb", "crop", "picking"),
        ("tomatoes peppers lettuce herbs containers", "potted tomatoes and herbs", "lettuce basil pepper pots"),
    ),
    (
        ("water", "sun", "care", "daily"),
        ("watering patio vegetables", "watering potted vegetables", "sunlight balcony vegetable pots"),
    ),
    (
        ("pest", "problem", "aphid", "disease"),
        ("garden pests damaged vegetable leaves", "aphids on potted plants", "yellowing tomato leaves container"),
    ),
    (
        ("harvest", "replant", "keeping"),
        ("harvesting tomatoes herbs from pots", "picking tomatoes from container garden", "harvesting basil patio pot"),
    ),
)


def _query_tokens(*values: Any, limit: int = 6) -> list[str]:
    seen: set[str] = set()
    words: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple)):
            parts = [str(v) for v in value if str(v).strip()]
        else:
            parts = [str(value or "")]
        for part in parts:
            text = re.sub(r"[^A-Za-z0-9\s\-]", " ", part)
            text = re.sub(r"\s+", " ", text).strip()
            for word in text.split():
                key = word.lower()
                if key in _QUERY_STOP or key in seen or len(key) < 3:
                    continue
                seen.add(key)
                words.append(word.lower())
                if len(words) >= limit:
                    return words
    return words


def visual_noun_phrase(*values: Any, limit: int = 5) -> str:
    """Short visual noun phrase for image search. Never a how-to sentence."""
    return " ".join(_query_tokens(*values, limit=limit)).strip()


def is_garden_topic(*, title: str = "", topic: str = "", chapter: str = "", caption: str = "") -> bool:
    blob = " ".join(str(v or "") for v in (title, topic, chapter, caption)).lower()
    return any(
        token in blob
        for token in (
            "garden", "vegetable", "herb", "tomato", "lettuce", "pepper",
            "container garden", "balcony", "patio", "potting", "planter",
        )
    )


def cover_pexels_queries(
    *,
    title: str = "",
    topic: str = "",
    audience: str = "",
    caption: str = "",
) -> list[str]:
    """Cover searches are short visual noun phrases. Orientation is an API param."""
    if is_garden_topic(title=title, topic=topic, caption=caption):
        return list(_COVER_GARDEN_QUERIES)
    phrase = visual_noun_phrase(caption, topic, title, audience, limit=5)
    out = [phrase] if phrase else []
    extra = visual_noun_phrase(topic, title, limit=4)
    if extra and extra not in out:
        out.append(extra)
    return out or ["nonfiction book photograph"]


def chapter_pexels_queries(
    *,
    chapter: str = "",
    title: str = "",
    topic: str = "",
    caption: str = "",
    keywords: Any = None,
    audience: str = "",
) -> list[str]:
    """Chapter searches matching the scene, not the full topic sentence.

    Builds a bounded query ladder: (1) exact action + book equipment +
    audience, (2) exact action + equipment, (3) equipment + a closely
    related action, (4) equipment + safe/general training + audience. Never
    broadens away the book's defining equipment just to get a hit -- if the
    book names a specific implement, every tier keeps it.
    """
    from services.ebook_visual_brief_common import (
        detect_audience_terms,
        detect_equipment_terms,
        strip_filler,
    )

    out: list[str] = []
    chapter_blob = f"{chapter} {caption}".lower()
    if is_garden_topic(title=title, topic=topic, chapter=chapter, caption=caption):
        matched = False
        for needles, queries in _CHAPTER_GARDEN_QUERIES:
            if any(n in chapter_blob for n in needles):
                out.extend(queries)
                matched = True
                break
        if not matched:
            out.extend(_CHAPTER_GARDEN_QUERIES[0][1])

    clean_chapter = strip_filler(chapter)
    equipment = detect_equipment_terms(title, topic, chapter)
    audience_terms = detect_audience_terms(audience, title, topic)
    equipment_term = equipment[0] if equipment else ""
    audience_term = audience_terms[0] if audience_terms else ""

    action_phrase = visual_noun_phrase(clean_chapter, limit=4)
    if equipment_term:
        # Tier 1: exact action + equipment + audience.
        if action_phrase and audience_term:
            out.append(f"{equipment_term} {action_phrase} {audience_term}")
        # Tier 2: exact action + equipment.
        if action_phrase:
            out.append(f"{equipment_term} {action_phrase}")
        # Tier 3: equipment + closely related action (chapter+keywords blend).
        kw_phrase = visual_noun_phrase(keywords, caption, limit=3)
        if kw_phrase:
            out.append(f"{equipment_term} {kw_phrase}")
        # Tier 4: equipment + safe/general training + audience -- broadest
        # tier, only used once the exact tiers are exhausted, and still
        # keeps the defining equipment term.
        out.append(f"{equipment_term} safe training {audience_term}".strip())
        out.append(equipment_term)

    kw_phrase = visual_noun_phrase(keywords, caption, clean_chapter, limit=5)
    if kw_phrase and kw_phrase not in out:
        out.append(kw_phrase)
    fallback = visual_noun_phrase(clean_chapter, topic, title, limit=5)
    if fallback and fallback not in out:
        out.append(fallback)
    seen: set[str] = set()
    clean: list[str] = []
    for query in out:
        key = " ".join(query.split())
        if not key or key in seen or len(key.split()) > 8:
            continue
        seen.add(key)
        clean.append(key)
    return clean or ["photograph"]


def topic_pexels_query(
    *,
    title: str = "",
    topic: str = "",
    audience: str = "",
    chapter: str = "",
    caption: str = "",
    keywords: Any = None,
) -> str:
    """Build a short visual noun-phrase query. Does not stuff orientation into the phrase."""
    queries = chapter_pexels_queries(
        chapter=chapter,
        title=title,
        topic=topic,
        caption=caption,
        keywords=keywords,
    ) if (chapter or caption or keywords) else cover_pexels_queries(
        title=title,
        topic=topic,
        audience=audience,
        caption=caption,
    )
    return queries[0] if queries else visual_noun_phrase(title, topic, audience) or "photograph"


def _scrub(message: str) -> str:
    key = pexels_api_key()
    text = str(message or "")
    if key:
        text = text.replace(key, "[redacted]")
    for token in ("Authorization", "Bearer", "PEXELS_API_KEY"):
        if token.lower() in text.lower() and key:
            text = "Pexels request failed."
            break
    return text


def _classify_http_error(exc: Exception) -> tuple[str, str]:
    text = _scrub(str(exc))
    low = text.lower()
    status = getattr(getattr(exc, "response", None), "status_code", None)
    try:
        status = int(status) if status is not None else None
    except (TypeError, ValueError):
        status = None
    if status == 401 or "401" in low or "unauthorized" in low:
        return "unauthorized", "Pexels could not authenticate."
    if status == 429 or "429" in low or "rate limit" in low:
        return "rate_limit", "Pexels rate limit reached."
    if status in {500, 502, 503} or "internal server" in low:
        return "invalid_response", "Pexels returned an invalid response."
    if "timeout" in low or "connection" in low or "network" in low:
        return "network", "Pexels could not be reached."
    if "json" in low or "invalid" in low:
        return "invalid_response", "Pexels returned an invalid response."
    return "request_failed", "Pexels request failed."


def _http_get(url: str, headers: dict[str, str], *, binary: bool = False) -> Any:
    """Live HTTP. Tests patch this. Blocked in FACTORY_TEST_MODE."""
    if str(os.environ.get("FACTORY_TEST_MODE") or "") == "1":
        raise PexelsError("Pexels live calls are blocked in test mode.", code="test_blocked")
    import requests

    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 401:
            raise PexelsError("Pexels could not authenticate.", code="unauthorized")
        if resp.status_code == 429:
            raise PexelsError("Pexels rate limit reached.", code="rate_limit")
        resp.raise_for_status()
        return resp.content if binary else resp.json()
    except PexelsError:
        raise
    except Exception as exc:  # noqa: BLE001
        code, message = _classify_http_error(exc)
        raise PexelsError(message, code=code) from None


def _auth_headers() -> dict[str, str]:
    key = pexels_api_key()
    if not key:
        raise PexelsError(PEXELS_NOT_CONFIGURED, code="missing_config")
    return {"Authorization": key}


def _normalize_photo(raw: dict) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    pid = raw.get("id")
    src = raw.get("src") if isinstance(raw.get("src"), dict) else {}
    original = str(src.get("original") or "").strip()
    preview = str(src.get("large") or src.get("medium") or src.get("tiny") or "").strip()
    if not pid or not original:
        return None
    photographer = str(raw.get("photographer") or "Unknown photographer").strip()
    photographer_url = str(raw.get("photographer_url") or raw.get("url") or "").strip()
    width = int(raw.get("width") or 0)
    height = int(raw.get("height") or 0)
    return {
        "provider": "pexels",
        "photo_id": str(pid),
        "photographer": photographer,
        "photographer_url": photographer_url,
        "page_url": str(raw.get("url") or photographer_url),
        "preview_url": preview,
        "original_url": original,
        "width": width,
        "height": height,
        "orientation": "portrait" if height >= width else "landscape",
        "alt": str(raw.get("alt") or raw.get("description") or "").strip(),
        "attribution": f"Photo by {photographer} on Pexels",
        "license_note": LICENSE_NOTE,
    }


def search_pexels(
    query: str,
    *,
    page: int = 1,
    per_page: int = 12,
    orientation: str = "portrait",
) -> dict[str, Any]:
    status = pexels_public_status()
    q = str(query or "").strip() or SUGGESTED_SEARCHES[0]
    page = max(1, int(page or 1))
    ori = str(orientation or "portrait").strip().lower()
    if ori not in {"portrait", "landscape", "square"}:
        ori = "portrait"
    if not status["configured"]:
        return {
            **status,
            "query": q,
            "page": page,
            "photos": [],
            "next_page": None,
        }
    params = urlencode(
        {
            "query": q,
            "orientation": ori,
            "per_page": max(1, min(int(per_page), 24)),
            "page": page,
        }
    )
    payload = _http_get(f"{PEXELS_SEARCH_URL}?{params}", _auth_headers())
    photos = []
    for row in list((payload or {}).get("photos") or []):
        item = _normalize_photo(row)
        if item:
            photos.append(item)
    next_page = page + 1 if photos and len(photos) >= per_page else None
    return {
        **status,
        "query": q,
        "page": page,
        "photos": photos,
        "next_page": next_page,
    }


def fetch_pexels_photo(photo_id: str) -> dict[str, Any]:
    if not pexels_configured():
        raise PexelsError(PEXELS_NOT_CONFIGURED)
    pid = str(photo_id or "").strip()
    if not pid.isdigit():
        raise PexelsError("Select a Pexels photograph from the search results.")
    payload = _http_get(PEXELS_PHOTO_URL.format(photo_id=pid), _auth_headers())
    item = _normalize_photo(payload if isinstance(payload, dict) else {})
    if not item:
        raise PexelsError("That Pexels photograph could not be loaded.")
    return item


def download_pexels_original(photo: dict[str, Any]) -> bytes:
    url = str((photo or {}).get("original_url") or "").strip()
    preview = str((photo or {}).get("preview_url") or "").strip()
    if not url:
        raise PexelsError("Pexels original image URL is missing.")
    if preview and url == preview and "original" not in url:
        raise PexelsError("Refusing to use a Pexels thumbnail as the cover source.")
    headers = _auth_headers()
    # Image CDN typically does not require the API key; still never log it.
    body = _http_get(url, {}, binary=True)
    if not body or len(body) < 1024:
        raise PexelsError("Pexels original download was empty.")
    return body


def public_photo(photo: dict[str, Any] | None) -> dict[str, Any]:
    """Search-result payload for the UI. Never includes original_url or the API key."""
    row = dict(photo or {})
    row.pop("original_url", None)
    return {
        "provider": "pexels",
        "photo_id": str(row.get("photo_id") or ""),
        "photographer": str(row.get("photographer") or ""),
        "photographer_url": str(row.get("photographer_url") or ""),
        "page_url": str(row.get("page_url") or ""),
        "preview_url": str(row.get("preview_url") or ""),
        "width": int(row.get("width") or 0),
        "height": int(row.get("height") or 0),
        "orientation": str(row.get("orientation") or ""),
        "alt": str(row.get("alt") or ""),
        "attribution": str(row.get("attribution") or ""),
        "license_note": LICENSE_NOTE,
    }


def public_photos(photos: list | None) -> list[dict[str, Any]]:
    return [public_photo(row) for row in list(photos or []) if isinstance(row, dict)]


def cache_record(photo: dict[str, Any], *, project_id: int | None, artifact_id: str, revision: int) -> dict[str, Any]:
    row = dict(photo or {})
    row["timestamp"] = datetime.now(timezone.utc).isoformat()
    row["project_id"] = project_id
    row["artifact_id"] = artifact_id
    row["artifact_revision"] = revision
    return row
