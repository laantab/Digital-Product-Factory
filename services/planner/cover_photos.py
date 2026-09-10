"""Cover photographs for planners, sourced through the Factory's Pexels service.

This is the beginner-facing side of the planner cover image slot:

  * ``build_cover_query`` turns the planner's title, type and theme into a
    sensible search phrase, so a customer never has to think about keywords.
  * ``search_cover_photos`` returns a small contact sheet of portrait photos.
  * ``select_cover_photo`` downloads one chosen photograph into the planner
    photo store and returns an *asset id* the project can keep. Rebuilds use
    the asset id, never a browser-supplied path, so the customer's later
    rebuilds are deterministic and no path from outside ever reaches the disk.
  * ``auto_cover_photo`` is "let the Factory choose": the first good result
    for the theme's own query.

Every network call goes through ``assert_external_call_allowed``. Under
``FACTORY_TEST_MODE`` these functions fail closed with a customer-readable
message, and the planner falls back to its painted artwork.
"""
from __future__ import annotations

import os
import re
from typing import Any

from services.planner.pdf_builder import EXPORTS_DIR
from services.planner.themes import PlannerTheme, resolve_theme

PHOTO_DIR = os.path.join(EXPORTS_DIR, "planner_cover_photos")
_ASSET_RE = re.compile(r"^pexels-(\d{1,12})$")
_STOP = {
    "planner", "planners", "faith", "budget", "edition", "the", "a", "an", "for",
    "and", "of", "my", "our", "your", "daily", "weekly", "monthly", "undated",
    "journal", "devotional", "book", "workbook",
}

NOT_AVAILABLE = (
    "Free photo search is not available right now, so the Factory painted a "
    "themed cover instead. You can try again later or keep the artwork."
)


def _theme(design_theme: str, planner_type: str) -> PlannerTheme:
    theme, _w = resolve_theme(design_theme, planner_type)
    return theme


def build_cover_query(title: str, planner_type: str, design_theme: str, *,
                      user_query: str = "") -> str:
    """A search phrase from what the customer already typed. No product name is
    hard-coded here: the words come from the title and the theme."""
    if str(user_query or "").strip():
        return " ".join(str(user_query).split())[:80]
    theme = _theme(design_theme, planner_type)
    base = theme.pexels_queries[0] if theme.pexels_queries else "soft light still life"
    words = [w for w in re.findall(r"[A-Za-z']+", str(title or "").lower()) if w not in _STOP]
    lead = " ".join(words[:2])
    context = "devotional" if planner_type == "faith_planner" else "calm desk"
    phrase = " ".join(p for p in (lead, base, context) if p)
    return " ".join(phrase.split())[:80]


def suggested_queries(title: str, planner_type: str, design_theme: str) -> list[str]:
    theme = _theme(design_theme, planner_type)
    out = [build_cover_query(title, planner_type, design_theme)]
    for q in theme.pexels_queries:
        if q not in out:
            out.append(q)
    return out[:4]


def photo_service_status() -> dict[str, Any]:
    """Configured or not, in customer words, without touching the network."""
    try:
        from services.ebook_pexels import pexels_public_status
        from services.external_calls import external_calls_blocked

        status = dict(pexels_public_status())
        if external_calls_blocked():
            status["configured"] = False
            status["message"] = "Free photo search is switched off in Safe Mode."
        return status
    except Exception as exc:  # noqa: BLE001
        return {"configured": False, "message": f"Free photo search is unavailable ({type(exc).__name__})."}


def search_cover_photos(*, title: str = "", planner_type: str = "faith_planner",
                        design_theme: str = "", query: str = "", page: int = 1,
                        per_page: int = 6) -> dict[str, Any]:
    """A contact sheet of portrait photographs for the cover. Never raises for
    an unavailable service: the answer says so and carries no photos."""
    from services.ebook_pexels import public_photos, search_pexels
    from services.external_calls import assert_external_call_allowed

    q = build_cover_query(title, planner_type, design_theme, user_query=query)
    out: dict[str, Any] = {
        "query": q,
        "suggested": suggested_queries(title, planner_type, design_theme),
        "photos": [],
        "next_page": None,
        "configured": False,
        "message": "",
    }
    try:
        assert_external_call_allowed("pexels")
        found = search_pexels(q, page=max(1, int(page or 1)), per_page=max(1, min(int(per_page), 12)),
                              orientation="portrait")
    except Exception as exc:  # noqa: BLE001
        out["message"] = NOT_AVAILABLE
        out["error"] = type(exc).__name__
        return out
    out["configured"] = bool(found.get("configured"))
    out["photos"] = public_photos(found.get("photos") or [])
    out["_raw_photos"] = list(found.get("photos") or [])
    out["next_page"] = found.get("next_page")
    if not out["configured"]:
        out["message"] = str(found.get("message") or NOT_AVAILABLE)
    elif not out["photos"]:
        out["message"] = "No photographs matched that phrase. Try one of the suggestions."
    return out


def _asset_path(asset_id: str) -> str:
    return os.path.join(PHOTO_DIR, f"{asset_id}.jpg")


def resolve_cover_asset(asset_id: str) -> str:
    """Path of a stored cover photograph, or "" when the id is not one of ours.
    The id is validated against a strict pattern and the path is built here,
    so nothing the browser sends can name a file outside the photo store."""
    aid = str(asset_id or "").strip()
    if not _ASSET_RE.match(aid):
        return ""
    path = _asset_path(aid)
    return path if os.path.isfile(path) else ""


def select_cover_photo(photo_id: str, *, photo: dict[str, Any] | None = None) -> dict[str, Any]:
    """Download one chosen photograph into the planner photo store.

    Returns ``{"asset_id", "path", "attribution", "photographer", "page_url",
    "license_note", "width", "height"}``. Raises on failure; the route turns
    that into a customer message and the planner keeps its painted cover.
    """
    from PIL import Image

    from services.ebook_pexels import (
        PexelsError,
        download_pexels_original,
        fetch_pexels_photo,
    )
    from services.external_calls import assert_external_call_allowed

    pid = str(photo_id or "").strip()
    if not pid.isdigit():
        raise PexelsError("Choose a photograph from the contact sheet first.")
    assert_external_call_allowed("pexels")
    row = dict(photo or {})
    if not str(row.get("original_url") or "").strip():
        row = fetch_pexels_photo(pid)
    raw = download_pexels_original(row)
    os.makedirs(PHOTO_DIR, exist_ok=True)
    asset_id = f"pexels-{pid}"
    path = _asset_path(asset_id)
    with open(path, "wb") as fh:
        fh.write(raw)
    with Image.open(path) as im:
        width, height = im.size
    # Removed only after the image handle is closed: Windows refuses to delete
    # an open file, which would leave a rejected photo behind.
    if min(width, height) < 900:
        os.remove(path)
        raise PexelsError("That photograph is too small to print well. Please pick another.")
    photographer = str(row.get("photographer") or row.get("attribution") or "").strip()
    return {
        "asset_id": asset_id,
        "path": path,
        "photographer": photographer,
        "attribution": f"Photo by {photographer} on Pexels" if photographer else "Photo from Pexels",
        "page_url": str(row.get("page_url") or ""),
        "license_note": str(row.get("license_note") or "Pexels License"),
        "width": width,
        "height": height,
    }


def auto_cover_photo(*, title: str, planner_type: str, design_theme: str) -> dict[str, Any] | None:
    """"Let the Factory choose": first good result for the theme's own phrase.
    Returns the stored asset record, or None when photos are unavailable."""
    found = search_cover_photos(title=title, planner_type=planner_type,
                                design_theme=design_theme, per_page=6)
    for row in found.get("_raw_photos") or []:
        try:
            return select_cover_photo(str(row.get("photo_id") or ""), photo=row)
        except Exception:  # noqa: BLE001
            continue
    return None
