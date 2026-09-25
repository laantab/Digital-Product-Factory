"""Free image sources after Pexels: Unsplash and Pixabay (Factory 1.9.6).

ORDER. Pexels stays first (services/ebook_pexels.py is unchanged). When Pexels
cannot fill a chapter picture, Unsplash is tried, then Pixabay. Paid AI is
never reached from here; ebook_factory_pipeline only considers it after every
free source has failed AND the owner has authorized it AND budget remains.

EACH PROVIDER HAS ITS OWN RULES. They are NOT the same and are encoded
separately (read 2026-09-24 from the official pages):

Unsplash -- https://help.unsplash.com/en/articles/2511245-unsplash-api-guidelines
  * Use the image URLs the API returns under photo.urls for every use
    (hotlinking). The review screen shows photo.urls directly; the book file
    is fetched from photo.urls, never from a re-hosted or guessed URL.
  * When a picture is actually chosen (the "download"-like event), send one
    authorized request to photo.links.download_location, keeping its query
    string (ixid). Candidates that are only inspected are NOT counted.
  * Credit the photographer AND Unsplash, linking to both, with
    ?utm_source=<app name>&utm_medium=referral on every link.
  * The Access Key stays on the server (Client-ID header, never in a URL
    shown to anyone). Demo apps get 50 requests/hour until approved.

Pixabay -- https://pixabay.com/api/docs/
  * Search responses must be cached for 24 hours. Every search goes through
    a 24-hour cache (memory + disk) keyed on the query without the API key.
  * Returned URLs may only be shown temporarily in search results; permanent
    hotlinking is not allowed, so a chosen picture is downloaded and stored
    by the Factory. largeImageURL (max 1280 px) is used unless the account
    has full API access (fullHDURL / imageURL).
  * The API is for real human requests; no bulk automated querying. The
    automatic path makes at most AUTOMATIC_QUERY_LIMIT searches per missing
    picture, and only after Pexels and Unsplash have failed for it.
  * Show users where images come from when results are displayed.
  * The key is a query parameter, so a request URL is never logged or put in
    an error message.

Either provider is optional: without its key it is simply skipped. Live HTTP
is blocked in FACTORY_TEST_MODE, exactly like Pexels.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dotenv import load_dotenv

_FLASK_APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_FLASK_APP_DIR, ".env"))

PROVIDER_PEXELS = "pexels"
PROVIDER_UNSPLASH = "unsplash"
PROVIDER_PIXABAY = "pixabay"
#: The fixed order for automatic selection. Pexels is always first.
PROVIDER_ORDER = (PROVIDER_PEXELS, PROVIDER_UNSPLASH, PROVIDER_PIXABAY)
PROVIDER_LABELS = {
    PROVIDER_PEXELS: "Pexels",
    PROVIDER_UNSPLASH: "Unsplash",
    PROVIDER_PIXABAY: "Pixabay",
}

UNSPLASH_SEARCH_URL = "https://api.unsplash.com/search/photos"
UNSPLASH_DEFAULT_APP_NAME = "digital_product_factory"
PIXABAY_SEARCH_URL = "https://pixabay.com/api/"
PIXABAY_CACHE_SECONDS = 24 * 60 * 60

#: Searches per missing picture per provider on the AUTOMATIC path. Keeps
#: Pixabay's "real human requests" rule and Unsplash's demo limit intact.
AUTOMATIC_QUERY_LIMIT = 3

UNSPLASH_LICENSE_NOTE = (
    "Unsplash License: free to use; photographer and Unsplash credited as the "
    "Unsplash API requires. Download recorded with Unsplash when chosen."
)
PIXABAY_LICENSE_NOTE = (
    "Pixabay Content License: free to use; the file is stored by the Factory "
    "(Pixabay does not allow permanent hotlinking). Source credited."
)


class ImageSourceError(ValueError):
    """A provider failed. The message never contains an API key or a request URL."""

    def __init__(self, message: str, code: str = "request_failed", provider: str = ""):
        self.code = str(code or "request_failed")
        self.provider = str(provider or "")
        super().__init__(_scrub(str(message or "Image source request failed.")))


# ---------------------------------------------------------------------------
# Keys and status (never expose a key)
# ---------------------------------------------------------------------------

def _clean_key(raw: str | None) -> str:
    return str(raw or "").strip().strip("\"'").strip()


def unsplash_access_key() -> str:
    return _clean_key(os.environ.get("UNSPLASH_ACCESS_KEY"))


def unsplash_app_name() -> str:
    raw = _clean_key(os.environ.get("UNSPLASH_APP_NAME")) or UNSPLASH_DEFAULT_APP_NAME
    return re.sub(r"[^A-Za-z0-9_\-]", "_", raw)[:60] or UNSPLASH_DEFAULT_APP_NAME


def pixabay_api_key() -> str:
    return _clean_key(os.environ.get("PIXABAY_API_KEY"))


def provider_configured(provider: str) -> bool:
    p = str(provider or "").lower()
    if p == PROVIDER_PEXELS:
        from services.ebook_pexels import pexels_configured

        return pexels_configured()
    if p == PROVIDER_UNSPLASH:
        return bool(unsplash_access_key())
    if p == PROVIDER_PIXABAY:
        return bool(pixabay_api_key())
    return False


def configured_providers() -> tuple[str, ...]:
    """Configured providers in the fixed automatic order (Pexels first)."""
    return tuple(p for p in PROVIDER_ORDER if provider_configured(p))


def image_sources_status() -> list[dict[str, Any]]:
    """Safe status for the UI. Booleans and labels only -- never a key."""
    return [
        {
            "provider": p,
            "label": PROVIDER_LABELS[p],
            "configured": provider_configured(p),
            "order": i + 1,
        }
        for i, p in enumerate(PROVIDER_ORDER)
    ]


def _scrub(message: str) -> str:
    text = str(message or "")
    for key in (unsplash_access_key(), pixabay_api_key()):
        if key and key in text:
            text = text.replace(key, "[redacted]")
    # A Pixabay request URL carries the key; never let one through.
    text = re.sub(r"https?://pixabay\.com/api/\S*", "[pixabay request]", text)
    text = re.sub(r"(?i)(client-id|client_id|key)=\S+", r"\1=[redacted]", text)
    return text


# ---------------------------------------------------------------------------
# HTTP (tests patch _http_get; live calls are blocked in test mode)
# ---------------------------------------------------------------------------

def _http_get(url: str, headers: dict[str, str], *, provider: str, binary: bool = False) -> Any:
    if str(os.environ.get("FACTORY_TEST_MODE") or "") == "1":
        raise ImageSourceError("Live image-source calls are blocked in test mode.",
                               code="test_blocked", provider=provider)
    import requests

    try:
        resp = requests.get(url, headers=headers, timeout=20)
    except Exception:                                  # noqa: BLE001
        raise ImageSourceError(f"{PROVIDER_LABELS.get(provider, provider)} could not be reached.",
                               code="network", provider=provider) from None
    if resp.status_code in (401, 403):
        raise ImageSourceError(f"{PROVIDER_LABELS.get(provider, provider)} could not authenticate.",
                               code="unauthorized", provider=provider)
    if resp.status_code == 429:
        raise ImageSourceError(f"{PROVIDER_LABELS.get(provider, provider)} rate limit reached.",
                               code="rate_limit", provider=provider)
    if resp.status_code >= 400:
        raise ImageSourceError(f"{PROVIDER_LABELS.get(provider, provider)} request failed.",
                               code="request_failed", provider=provider)
    if binary:
        return resp.content
    try:
        return resp.json()
    except Exception:                                  # noqa: BLE001
        raise ImageSourceError(f"{PROVIDER_LABELS.get(provider, provider)} returned an invalid response.",
                               code="invalid_response", provider=provider) from None


def _with_utm(url: str) -> str:
    """Add the Unsplash-required referral parameters to a link back to Unsplash."""
    if not url:
        return ""
    parts = urlparse(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["utm_source"] = unsplash_app_name()
    query["utm_medium"] = "referral"
    return urlunparse(parts._replace(query=urlencode(query)))


# ---------------------------------------------------------------------------
# Unsplash
# ---------------------------------------------------------------------------

def _unsplash_headers() -> dict[str, str]:
    key = unsplash_access_key()
    if not key:
        raise ImageSourceError("Unsplash is not configured.", code="missing_config",
                               provider=PROVIDER_UNSPLASH)
    return {"Authorization": f"Client-ID {key}", "Accept-Version": "v1"}


def normalize_unsplash_photo(raw: dict) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    pid = str(raw.get("id") or "").strip()
    urls = raw.get("urls") if isinstance(raw.get("urls"), dict) else {}
    links = raw.get("links") if isinstance(raw.get("links"), dict) else {}
    user = raw.get("user") if isinstance(raw.get("user"), dict) else {}
    user_links = user.get("links") if isinstance(user.get("links"), dict) else {}
    # The API's own photo.urls, used as returned (hotlinking rule). "full" is
    # the large print-quality rendition; "small" is for the review screen.
    original = str(urls.get("full") or urls.get("regular") or "").strip()
    preview = str(urls.get("small") or urls.get("regular") or "").strip()
    download_location = str(links.get("download_location") or "").strip()
    if not pid or not original or not download_location:
        return None
    name = str(user.get("name") or user.get("username") or "Unknown photographer").strip()
    width = int(raw.get("width") or 0)
    height = int(raw.get("height") or 0)
    alt = " ".join(
        str(x or "").strip() for x in (raw.get("alt_description"), raw.get("description")) if x
    ).strip()
    tags = [str(t.get("title") or "") for t in (raw.get("tags") or []) if isinstance(t, dict)]
    return {
        "provider": PROVIDER_UNSPLASH,
        "photo_id": f"{PROVIDER_UNSPLASH}:{pid}",
        "provider_photo_id": pid,
        "photographer": name,
        "photographer_url": _with_utm(str(user_links.get("html") or "")),
        "page_url": _with_utm(str(links.get("html") or "")),
        "provider_home_url": _with_utm("https://unsplash.com/"),
        "preview_url": preview,
        "original_url": original,
        "download_location": download_location,
        "width": width,
        "height": height,
        "orientation": "portrait" if height >= width else "landscape",
        "alt": alt,
        "tags": [t for t in tags if t],
        "attribution": f"Photo by {name} on Unsplash",
        "license_note": UNSPLASH_LICENSE_NOTE,
    }


def search_unsplash(query: str, *, orientation: str = "landscape", per_page: int = 12,
                    page: int = 1) -> dict[str, Any]:
    q = str(query or "").strip()
    if not unsplash_access_key() or not q:
        return {"provider": PROVIDER_UNSPLASH, "configured": bool(unsplash_access_key()),
                "query": q, "photos": []}
    ori = str(orientation or "").lower()
    ori = {"square": "squarish"}.get(ori, ori)
    params = {
        "query": q,
        "per_page": max(1, min(int(per_page or 12), 30)),
        "page": max(1, int(page or 1)),
        "content_filter": "high",
    }
    if ori in {"landscape", "portrait", "squarish"}:
        params["orientation"] = ori
    payload = _http_get(f"{UNSPLASH_SEARCH_URL}?{urlencode(params)}", _unsplash_headers(),
                        provider=PROVIDER_UNSPLASH)
    photos = [p for p in (normalize_unsplash_photo(r) for r in (payload or {}).get("results") or []) if p]
    return {"provider": PROVIDER_UNSPLASH, "configured": True, "query": q, "photos": photos}


def track_unsplash_download(photo: dict[str, Any]) -> bool:
    """Tell Unsplash this picture was chosen. Called once, only for the chosen picture.

    Uses photo.links.download_location exactly as returned (its ixid query
    parameter included), authorized with the Access Key.
    """
    url = str((photo or {}).get("download_location") or "").strip()
    host = urlparse(url).netloc.lower()
    if not url or host != "api.unsplash.com":
        raise ImageSourceError("Unsplash download link is missing.", code="invalid_response",
                               provider=PROVIDER_UNSPLASH)
    _http_get(url, _unsplash_headers(), provider=PROVIDER_UNSPLASH)
    return True


def download_unsplash_image(photo: dict[str, Any]) -> bytes:
    """Fetch the picture from the photo.urls address the API returned."""
    url = str((photo or {}).get("original_url") or "").strip()
    host = urlparse(url).netloc.lower()
    if not url or not host.endswith("unsplash.com"):
        raise ImageSourceError("Unsplash image address is missing.", code="invalid_response",
                               provider=PROVIDER_UNSPLASH)
    body = _http_get(url, {}, provider=PROVIDER_UNSPLASH, binary=True)
    if not body or len(body) < 1024:
        raise ImageSourceError("Unsplash image download was empty.", code="invalid_response",
                               provider=PROVIDER_UNSPLASH)
    return body


# ---------------------------------------------------------------------------
# Pixabay (24-hour search cache)
# ---------------------------------------------------------------------------

_PIXABAY_MEMORY_CACHE: dict[str, tuple[float, dict]] = {}


def _cache_dir() -> Path:
    base = os.environ.get("FACTORY_IMAGE_SOURCE_CACHE_DIR") or os.path.join(
        _FLASK_APP_DIR, "data", "cache", "pixabay")
    return Path(base)


def _pixabay_cache_key(params: dict[str, Any]) -> str:
    safe = {k: v for k, v in params.items() if k != "key"}
    return hashlib.sha256(json.dumps(safe, sort_keys=True).encode("utf-8")).hexdigest()


def _pixabay_cache_get(key: str) -> dict | None:
    now = time.time()
    hit = _PIXABAY_MEMORY_CACHE.get(key)
    if hit and now - hit[0] < PIXABAY_CACHE_SECONDS:
        return hit[1]
    path = _cache_dir() / f"{key}.json"
    try:
        if path.is_file() and now - path.stat().st_mtime < PIXABAY_CACHE_SECONDS:
            payload = json.loads(path.read_text(encoding="utf-8"))
            _PIXABAY_MEMORY_CACHE[key] = (path.stat().st_mtime, payload)
            return payload
    except (OSError, ValueError):
        return None
    return None


def _pixabay_cache_put(key: str, payload: dict) -> None:
    _PIXABAY_MEMORY_CACHE[key] = (time.time(), payload)
    try:
        folder = _cache_dir()
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{key}.json").write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass  # memory cache still holds it for this process


def clear_pixabay_memory_cache() -> None:
    _PIXABAY_MEMORY_CACHE.clear()


def normalize_pixabay_hit(raw: dict) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    pid = str(raw.get("id") or "").strip()
    # Largest rendition this account may use; stored by the Factory, never hotlinked.
    original = str(raw.get("imageURL") or raw.get("fullHDURL") or raw.get("largeImageURL") or "").strip()
    preview = str(raw.get("webformatURL") or raw.get("previewURL") or "").strip()
    if not pid or not original:
        return None
    user = str(raw.get("user") or "Pixabay contributor").strip()
    user_id = str(raw.get("user_id") or "").strip()
    profile = f"https://pixabay.com/users/{user}-{user_id}/" if user and user_id else ""
    width = int(raw.get("imageWidth") or 0)
    height = int(raw.get("imageHeight") or 0)
    tags = [t.strip() for t in str(raw.get("tags") or "").split(",") if t.strip()]
    return {
        "provider": PROVIDER_PIXABAY,
        "photo_id": f"{PROVIDER_PIXABAY}:{pid}",
        "provider_photo_id": pid,
        "photographer": user,
        "photographer_url": profile,
        "page_url": str(raw.get("pageURL") or ""),
        "provider_home_url": "https://pixabay.com/",
        # Temporary display of a search result only (allowed by Pixabay).
        "preview_url": preview,
        "original_url": original,
        "width": width,
        "height": height,
        "orientation": "portrait" if height >= width else "landscape",
        "alt": ", ".join(tags),
        "tags": tags,
        "attribution": f"Image by {user} from Pixabay",
        "license_note": PIXABAY_LICENSE_NOTE,
    }


def search_pixabay(query: str, *, orientation: str = "landscape", per_page: int = 12,
                   page: int = 1) -> dict[str, Any]:
    q = str(query or "").strip()[:100]
    key = pixabay_api_key()
    if not key or not q:
        return {"provider": PROVIDER_PIXABAY, "configured": bool(key), "query": q, "photos": []}
    ori = {"landscape": "horizontal", "portrait": "vertical"}.get(str(orientation or "").lower(), "all")
    params = {
        "key": key,
        "q": q,
        "image_type": "photo",
        "orientation": ori,
        "safesearch": "true",
        "per_page": max(3, min(int(per_page or 12), 200)),
        "page": max(1, int(page or 1)),
    }
    cache_key = _pixabay_cache_key(params)
    payload = _pixabay_cache_get(cache_key)
    cached = payload is not None
    if payload is None:
        payload = _http_get(f"{PIXABAY_SEARCH_URL}?{urlencode(params)}", {}, provider=PROVIDER_PIXABAY)
        if isinstance(payload, dict):
            _pixabay_cache_put(cache_key, payload)
    photos = [p for p in (normalize_pixabay_hit(r) for r in (payload or {}).get("hits") or []) if p]
    return {"provider": PROVIDER_PIXABAY, "configured": True, "query": q, "photos": photos,
            "cached": cached}


def download_pixabay_image(photo: dict[str, Any]) -> bytes:
    url = str((photo or {}).get("original_url") or "").strip()
    host = urlparse(url).netloc.lower()
    if not url or not host.endswith("pixabay.com"):
        raise ImageSourceError("Pixabay image address is missing.", code="invalid_response",
                               provider=PROVIDER_PIXABAY)
    body = _http_get(url, {}, provider=PROVIDER_PIXABAY, binary=True)
    if not body or len(body) < 1024:
        raise ImageSourceError("Pixabay image download was empty.", code="invalid_response",
                               provider=PROVIDER_PIXABAY)
    return body


# ---------------------------------------------------------------------------
# One interface for the pipeline
# ---------------------------------------------------------------------------

def search_provider(provider: str, query: str, *, orientation: str = "landscape",
                    per_page: int = 12) -> dict[str, Any]:
    p = str(provider or "").lower()
    if p == PROVIDER_UNSPLASH:
        return search_unsplash(query, orientation=orientation, per_page=per_page)
    if p == PROVIDER_PIXABAY:
        return search_pixabay(query, orientation=orientation, per_page=per_page)
    raise ImageSourceError("Unknown image source.", code="request_failed", provider=p)


def download_provider_image(photo: dict[str, Any]) -> bytes:
    p = str((photo or {}).get("provider") or "").lower()
    if p == PROVIDER_UNSPLASH:
        return download_unsplash_image(photo)
    if p == PROVIDER_PIXABAY:
        return download_pixabay_image(photo)
    raise ImageSourceError("Unknown image source.", code="request_failed", provider=p)


def record_chosen(photo: dict[str, Any]) -> dict[str, Any]:
    """Provider duties once a picture is chosen. Returns fields to store on the aid."""
    p = str((photo or {}).get("provider") or "").lower()
    out: dict[str, Any] = {}
    if p == PROVIDER_UNSPLASH:
        try:
            out["download_tracked"] = track_unsplash_download(photo)
        except ImageSourceError as exc:
            out["download_tracked"] = False
            out["download_tracking_error"] = exc.code
    return out


def credit_for(aid: dict[str, Any] | None) -> dict[str, Any]:
    """Source + photographer credit for the review screen. No keys, no request URLs."""
    row = aid if isinstance(aid, dict) else {}
    source = str(row.get("source") or row.get("provider") or "").lower()
    label = PROVIDER_LABELS.get(source, "")
    if not label:
        return {}
    page = str(row.get("page_url") or row.get("source_url") or "")
    home = str(row.get("provider_home_url") or "")
    if source == PROVIDER_PEXELS:
        home = home or "https://www.pexels.com/"
    elif source == PROVIDER_UNSPLASH:
        home = _with_utm(home or "https://unsplash.com/")
        page = _with_utm(page) if page else ""
    elif source == PROVIDER_PIXABAY:
        home = home or "https://pixabay.com/"
    return {
        "provider": source,
        "provider_label": label,
        "photographer": str(row.get("photographer") or ""),
        "photographer_url": str(row.get("photographer_url") or ""),
        "page_url": page,
        "provider_url": home,
        # Unsplash must be DISPLAYED from its own URL; the others show the
        # Factory's stored copy (Pixabay forbids permanent hotlinking).
        "hotlink_preview_url": str(row.get("preview_url") or "") if source == PROVIDER_UNSPLASH else "",
    }
