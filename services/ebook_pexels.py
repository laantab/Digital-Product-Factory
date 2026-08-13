"""Pexels stock search for Ebook covers. Key stays server-side.

Tests must mock HTTP. FACTORY_TEST_MODE never performs a live Pexels call.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

from dotenv import load_dotenv

load_dotenv()

PEXELS_NOT_CONFIGURED = (
    "Pexels is not configured. Add PEXELS_API_KEY or upload your own photograph."
)
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
    """User-facing Pexels workflow error. Must never include the API key."""


def pexels_api_key() -> str:
    return (os.environ.get("PEXELS_API_KEY") or "").strip()


def pexels_configured() -> bool:
    return bool(pexels_api_key())


def pexels_public_status() -> dict[str, Any]:
    configured = pexels_configured()
    return {
        "configured": configured,
        "message": "" if configured else PEXELS_NOT_CONFIGURED,
        "suggested": list(SUGGESTED_SEARCHES),
        "attribution_required": True,
    }


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


def _http_get(url: str, headers: dict[str, str], *, binary: bool = False) -> Any:
    """Live HTTP. Tests patch this. Blocked in FACTORY_TEST_MODE."""
    if str(os.environ.get("FACTORY_TEST_MODE") or "") == "1":
        raise PexelsError("Pexels live calls are blocked in test mode.")
    import requests

    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.raise_for_status()
        return resp.content if binary else resp.json()
    except Exception as exc:  # noqa: BLE001
        raise PexelsError(_scrub(str(exc))) from None


def _auth_headers() -> dict[str, str]:
    key = pexels_api_key()
    if not key:
        raise PexelsError(PEXELS_NOT_CONFIGURED)
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
        "attribution": f"Photo by {photographer} on Pexels",
        "license_note": LICENSE_NOTE,
    }


def search_pexels(query: str, *, page: int = 1, per_page: int = 12) -> dict[str, Any]:
    status = pexels_public_status()
    q = str(query or "").strip() or SUGGESTED_SEARCHES[0]
    page = max(1, int(page or 1))
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
            "orientation": "portrait",
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
