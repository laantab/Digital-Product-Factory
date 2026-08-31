"""Factory Ebook visual/cover glue.

Routes the three-step Product Factory Ebook form onto the existing Pexels and
photo-cover services used by workspace ebooks. Does not implement a second
Pexels client. Never auto-approves cover or visuals.
"""
from __future__ import annotations

import json
import io
import os
import re
import shutil
from typing import Any

from services.ebook_pexels import (
    PexelsError,
    chapter_pexels_queries,
    cover_pexels_queries,
    download_pexels_original,
    is_garden_topic,
    pexels_public_status,
    pexels_status_label,
    public_photos,
    search_pexels,
    topic_pexels_query,
)
from services.ebook_visual_match import (
    MATCH_PASS,
    MATCH_REJECT,
    apply_match_report,
    build_visual_brief,
    candidate_search_queries,
    garden_photo_usable,
    rank_pexels_candidates,
    score_photo_against_brief,
)
from services.ebook_visual_pipeline import (
    EXPORTS_DIR,
    is_photo_aid,
    photo_file_is_valid,
    stamp_photo_aid_metadata,
    store_interior_photo,
)

PHOTO_TYPES = {"photo", "stock photo"}
LOCAL_INFOGRAPHIC_TYPES = {
    "chart",
    "comparison",
    "table",
    "checklist",
    "diagram",
    "timeline",
    "workflow",
}

NEXT_CHOOSE_COVER = "Choose cover photo"
NEXT_REVIEW_VISUALS = "Review visuals"
NEXT_RETRY_IMAGE = "Retry missing image"
NEXT_BUILD_PDF = "Build PDF"
NEXT_CORRECT_PREFLIGHT = "Correct failed preflight item"

PROGRESS_PLANNING = "Planning chapter visuals"
PROGRESS_LOCAL = "Creating Factory graphics"
PROGRESS_STOCK = "Searching professional stock photos"
PROGRESS_AI = "Creating missing custom artwork"
PROGRESS_QA = "Checking visual quality"
PROGRESS_REVIEW = "Preparing your visual review"

AI_VISUAL_UNIT_USD = 0.04
AI_VISUAL_MAX_ATTEMPTS = 2
_AUTOMATIC_VALUES = {
    "yes",
    "true",
    "1",
    "on",
    "automatic",
    "automatic professional visuals",
    "automatic professional visuals — recommended",
}
_NO_VISUAL_VALUES = {"no", "false", "0", "off", "none", "no visuals"}


def images_requested(fields: dict | None) -> bool:
    payload = fields if isinstance(fields, dict) else {}
    raw = str(payload.get("include_images") or payload.get("visual_mode") or "").strip().lower()
    if raw in _NO_VISUAL_VALUES:
        return False
    return raw in _AUTOMATIC_VALUES


def automatic_visuals_requested(fields: dict | None) -> bool:
    return images_requested(fields)


def prefers_local_medium(aid: dict | None) -> bool:
    kind = str((aid or {}).get("type") or "").strip().lower()
    return kind in LOCAL_INFOGRAPHIC_TYPES


def estimate_max_visual_generation_cost_usd(
    chapter_count: int = 6,
    *,
    photo_count: int | None = None,
) -> float:
    """Maximum paid AI visual cost for the displayed authorization cap.

    Local graphics and Pexels searches are $0. Each missing photograph may use
    one AI generation plus one controlled retry.
    """
    n = int(photo_count) if photo_count is not None else max(0, int(chapter_count or 0))
    n = max(0, n)
    return round(n * AI_VISUAL_UNIT_USD * AI_VISUAL_MAX_ATTEMPTS, 4)


def set_visual_progress(data: dict | None, phase: str) -> dict:
    payload = data if isinstance(data, dict) else {}
    payload["visual_progress"] = phase
    payload["visual_progress_message"] = phase
    return payload


def remaining_visual_budget_usd(data: dict | None = None, fields: dict | None = None) -> float:
    payload = data if isinstance(data, dict) else {}
    fields = fields if isinstance(fields, dict) else (
        payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    )
    ws = payload.get("ebook_workspace") if isinstance(payload.get("ebook_workspace"), dict) else {}
    ledger = ws.get("paid_call_ledger") if isinstance(ws.get("paid_call_ledger"), dict) else {}
    ledger_remaining = None
    if ledger:
        ledger_remaining = max(0.0, round(float(ledger.get("remaining_usd") or 0), 4))
    authorized = str(fields.get("visuals_authorized") or payload.get("visuals_authorized") or "").strip().lower()
    cap = float(fields.get("visual_budget_cap_usd") or payload.get("visual_budget_cap_usd") or 0)
    spent = float(payload.get("visual_ai_spend_usd") or 0)
    cap_remaining = None
    if authorized in {"1", "true", "yes", "on"} or cap > 0:
        cap_remaining = max(0.0, round(cap - spent, 4))
    if ledger_remaining is not None and cap_remaining is not None:
        return min(ledger_remaining, cap_remaining)
    if cap_remaining is not None:
        return cap_remaining
    if ledger_remaining is not None:
        return ledger_remaining
    return 0.0


def visual_ai_authorized(data: dict | None = None, fields: dict | None = None) -> bool:
    payload = data if isinstance(data, dict) else {}
    fields = fields if isinstance(fields, dict) else (
        payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    )
    if not automatic_visuals_requested(fields) and not automatic_visuals_requested(payload):
        return False
    authorized = str(fields.get("visuals_authorized") or payload.get("visuals_authorized") or "").strip().lower()
    cap = float(fields.get("visual_budget_cap_usd") or payload.get("visual_budget_cap_usd") or 0)
    if authorized not in {"1", "true", "yes", "on"} and cap <= 0:
        return False
    return remaining_visual_budget_usd(payload, fields) + 1e-9 >= AI_VISUAL_UNIT_USD


def charge_visual_ai_call(
    data: dict | None,
    fields: dict | None = None,
    *,
    amount: float = AI_VISUAL_UNIT_USD,
    purpose: str = "ebook_visual_ai",
) -> bool:
    """Record one paid visual-generation attempt. Never exceeds the remaining cap."""
    payload = data if isinstance(data, dict) else {}
    fields = fields if isinstance(fields, dict) else (
        payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    )
    charge = round(float(amount), 4)
    remaining = remaining_visual_budget_usd(payload, fields)
    if charge <= 0 or remaining + 1e-9 < charge:
        return False
    payload["visual_ai_spend_usd"] = round(float(payload.get("visual_ai_spend_usd") or 0) + charge, 4)
    ws = payload.get("ebook_workspace") if isinstance(payload.get("ebook_workspace"), dict) else None
    if ws is not None and isinstance(ws.get("paid_call_ledger"), dict):
        ledger = ws["paid_call_ledger"]
        cap = round(float(ledger.get("budget_cap_usd") or 0), 4)
        spent = round(float(ledger.get("spent_usd") or 0) + charge, 4)
        if spent - cap > 1e-9:
            payload["visual_ai_spend_usd"] = round(float(payload.get("visual_ai_spend_usd") or 0) - charge, 4)
            return False
        ledger["spent_usd"] = spent
        ledger["remaining_usd"] = round(cap - spent, 4)
        ledger["paid_calls"] = int(ledger.get("paid_calls") or 0) + 1
        ledger.setdefault("calls", []).append(
            {
                "provider": "openai",
                "purpose": purpose,
                "estimated_cost_usd": charge,
            }
        )
    return True


def unresolved_visual_customer_message(aid: dict | None) -> str:
    row = aid if isinstance(aid, dict) else {}
    idx = row.get("chapter_index") or ""
    title = str(row.get("chapter") or "this chapter").strip() or "this chapter"
    chapter_bit = f"Chapter {idx}: {title}" if idx else title
    return (
        f"We could not finish a visual for {chapter_bit}. "
        "Your other visuals were kept. You can retry automatically or edit this visual."
    )


def budget_visual_customer_message() -> str:
    return (
        "A custom image is needed, but this project does not have remaining authorized "
        "budget for image generation. You can retry with stock photos or add authorized budget."
    )


def factory_img_path(package_id: str, visual_id: str) -> str:
    return os.path.join(EXPORTS_DIR, str(package_id or ""), f"img_{visual_id}.png")


def publish_factory_photo(aid: dict[str, Any], package_id: str) -> dict[str, Any]:
    """Copy a stored interior photograph into the factory preview/PDF slot."""
    vid = str(aid.get("visual_id") or "").strip()
    src = str(aid.get("asset_path") or "").strip()
    if not vid or not package_id or not src or not os.path.isfile(src):
        return aid
    dest = factory_img_path(package_id, vid)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copyfile(src, dest)
    aid["factory_asset_path"] = dest
    aid["has_file"] = True
    aid["rendered"] = True
    return aid


def publish_plan_photos(visual_plan: dict | None, *, package_id: str) -> dict[str, Any]:
    """Ensure every photo aid in a plan occupies its canonical package slot.

    The browser preview resolves a chapter image purely by convention --
    ``/download/<package_id>/img_<visual_id>.png`` (see factory_img_path) --
    so an aid whose photograph lives anywhere else renders as a broken image
    even though the file exists and the PDF embeds it fine. fill_photo_aid_*
    publishes each photo as it is acquired, but a plan assembled from
    already-acquired assets (a repair, a re-package, a restored draft) never
    passes through that step. Walking the finished plan here makes the
    canonical slot a property of the package rather than of one code path.
    """
    plan = visual_plan if isinstance(visual_plan, dict) else {"chapters": []}
    published, missing = 0, []
    for ch in list(plan.get("chapters") or []):
        if not isinstance(ch, dict):
            continue
        for aid in list(ch.get("aids") or []):
            if not isinstance(aid, dict) or not is_photo_aid(aid):
                continue
            vid = str(aid.get("visual_id") or "").strip()
            src = str(aid.get("asset_path") or "").strip()
            if not vid:
                continue
            dest = factory_img_path(package_id, vid)
            if src and os.path.isfile(src):
                if not (os.path.isfile(dest) and os.path.getsize(dest) == os.path.getsize(src)):
                    publish_factory_photo(aid, package_id)
                else:
                    aid["factory_asset_path"] = dest
                    aid["has_file"] = True
                    aid["rendered"] = True
                published += 1
            elif not os.path.isfile(dest):
                missing.append(vid)
    return {"published": published, "missing": missing}


def publish_cover_image(cover_design: dict | None, *, package_id: str) -> str:
    """Copy the selected cover into the package's canonical img_cover.png slot.

    Same convention problem as publish_plan_photos: the preview builds the
    cover URL as ``/download/<package_id>/img_cover.png`` regardless of where
    the rendered cover actually sits.
    """
    cover = cover_design if isinstance(cover_design, dict) else {}
    src = str(cover.get("image_path") or "").strip()
    if not src or not os.path.isfile(src) or not package_id:
        return ""
    dest = os.path.join(EXPORTS_DIR, str(package_id), "img_cover.png")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if os.path.abspath(src) != os.path.abspath(dest):
        shutil.copyfile(src, dest)
    cover["cover_asset"] = "img_cover.png"
    cover["cover_asset_url"] = f"/download/{package_id}/img_cover.png"
    return dest


def _fill_photo_aid_fixture(aid: dict[str, Any], *, package_id: str, chapter: str = "") -> dict[str, Any]:
    """Local JPEG for isolated customer-path tests. Never calls Pexels or paid AI."""
    from PIL import Image, ImageDraw

    out = dict(aid or {})
    if not out.get("visual_id"):
        out["visual_id"] = "v_fixture"
    img = Image.new("RGB", (1400, 1000), (48, 110, 62))
    draw = ImageDraw.Draw(img)
    draw.rectangle((80, 80, 1320, 420), fill=(210, 180, 90))
    draw.ellipse((420, 360, 980, 900), fill=(30, 70, 40))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    filled = store_interior_photo(out, buf.getvalue(), package_id=package_id)
    filled["type"] = str(out.get("type") or "stock photo")
    filled["source"] = "local_fixture"
    filled["attribution"] = "Local fixture photograph"
    filled["photographer"] = "Fixture Studio"
    filled["page_url"] = ""
    filled["source_url"] = ""
    filled["photo_id"] = "fixture"
    filled["alt"] = str(out.get("caption") or out.get("title") or chapter)
    filled["pexels_query"] = str(out.get("keywords") or chapter or "container garden")
    filled["license_note"] = "Deterministic local fixture photograph. Not for sale."
    filled["approved"] = False
    filled["match_status"] = MATCH_PASS
    filled["status"] = "resolved"
    filled["retryable"] = False
    filled["error"] = ""
    filled["rendered"] = True
    filled["has_file"] = True
    return publish_factory_photo(filled, package_id)


def fill_photo_aid_from_pexels(
    aid: dict[str, Any],
    *,
    package_id: str,
    title: str = "",
    topic: str = "",
    audience: str = "",
    chapter: str = "",
) -> dict[str, Any]:
    """Retrieve one stock-photo slot via the shared Pexels service and store it locally.

    Candidates are scored against a structured visual brief. A rejected image is
    never reused. Metadata cannot mark a photo ready for approval.
    """
    out = dict(aid or {})
    brief = build_visual_brief(out, chapter=chapter or str(out.get("chapter") or ""), title=title, topic=topic)
    failed_queries = list(out.get("failed_queries") or [])
    rejected_ids = {str(x) for x in (out.get("rejected_photo_ids") or []) if str(x).strip()}
    queries = candidate_search_queries(brief, failed_queries=failed_queries)
    extra = chapter_pexels_queries(
        chapter=chapter or str(out.get("chapter") or ""),
        title=title,
        topic=topic,
        caption=str(out.get("caption") or out.get("title") or ""),
        keywords=out.get("keywords"),
    )
    queries = extra + [q for q in queries if q not in extra]
    fallback = topic_pexels_query(
        title=title,
        topic=topic,
        audience=audience,
        chapter=chapter or str(out.get("chapter") or ""),
        caption=str(out.get("caption") or out.get("title") or ""),
        keywords=out.get("keywords") if not str(out.get("caption") or "").lower().startswith("a relevant") else None,
    )
    queries = [
        q for q in queries
        if q and "relevant photograph" not in q.lower() and not q.lower().startswith("a relevant")
    ]
    if fallback and fallback not in queries:
        queries.append(fallback)
    out["visual_brief"] = brief.as_dict()
    out["type"] = str(out.get("type") or "stock photo")
    out["pexels_query"] = queries[0] if queries else fallback
    if str(os.environ.get("EBOOK_CUSTOMER_PATH_FIXTURE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return _fill_photo_aid_fixture(out, package_id=package_id, chapter=chapter)
    last_error = "No matching photograph was found."
    try:
        for query in queries:
            out["pexels_query"] = query
            photos: list[dict[str, Any]] = []
            for orientation in ("landscape", "portrait"):
                result = search_pexels(query, orientation=orientation, per_page=12)
                photos = list(result.get("photos") or [])
                if photos:
                    break
            if not photos:
                failed_queries.append(query)
                continue
            ranked, skipped = rank_pexels_candidates(brief, photos, rejected_ids=rejected_ids)
            for row in skipped:
                pid = str(row.get("photo_id") or "")
                if pid:
                    rejected_ids.add(pid)
            if not ranked:
                failed_queries.append(query)
                last_error = (
                    (skipped[0].get("rejection_reason") if skipped else "")
                    or "Every Pexels result failed the visual brief."
                )
                continue
            filled = None
            for photo in ranked[:5]:
                raw = download_pexels_original(photo)
                inspected = score_photo_against_brief(
                    brief,
                    alt=str(photo.get("alt") or ""),
                    page_url=str(photo.get("page_url") or ""),
                    filename=str(photo.get("photo_id") or ""),
                    image_bytes=raw,
                    planned_caption=str(out.get("caption") or out.get("title") or ""),
                )
                if inspected.status == MATCH_REJECT:
                    pid = str(photo.get("photo_id") or "")
                    if pid:
                        rejected_ids.add(pid)
                    last_error = inspected.rejection_reason or last_error
                    continue
                if is_garden_topic(title=title, topic=topic, chapter=chapter, caption=str(out.get("caption") or "")):
                    if not garden_photo_usable(photo):
                        pid = str(photo.get("photo_id") or "")
                        if pid:
                            rejected_ids.add(pid)
                        last_error = "Photograph is not a container-garden scene."
                        continue
                filled = store_interior_photo(out, raw, package_id=package_id)
                filled["_inspected"] = inspected
                filled["_photo"] = photo
                filled["_query"] = query
                if inspected.status == MATCH_PASS:
                    break
            if filled is None:
                failed_queries.append(query)
                continue
            inspected = filled.pop("_inspected")
            photo = filled.pop("_photo")
            query = filled.pop("_query")
            filled["type"] = str(out.get("type") or "stock photo")
            filled["source"] = "pexels"
            filled["attribution"] = str(photo.get("attribution") or "")
            filled["photographer"] = str(photo.get("photographer") or "")
            filled["page_url"] = str(photo.get("page_url") or photo.get("photographer_url") or "")
            filled["source_url"] = str(photo.get("page_url") or "")
            filled["photo_id"] = str(photo.get("photo_id") or "")
            filled["alt"] = str(photo.get("alt") or "")
            filled["pexels_query"] = query
            filled["license_note"] = str(photo.get("license_note") or "")
            filled["failed_queries"] = list(dict.fromkeys(failed_queries))
            filled["rejected_photo_ids"] = sorted(rejected_ids)
            filled["approved"] = False
            filled = apply_match_report(filled, inspected)
            filled["status"] = "resolved"
            filled["retryable"] = filled.get("match_status") != "pass"
            filled["error"] = "" if filled.get("match_status") != "reject" else inspected.rejection_reason
            filled["rendered"] = True
            filled["has_file"] = True
            filled = publish_factory_photo(filled, package_id)
            local = str(filled.get("asset_path") or "")
            factory = str(filled.get("factory_asset_path") or "")
            if not photo_file_is_valid(local) and not photo_file_is_valid(factory):
                return stamp_photo_aid_metadata(
                    out,
                    status="missing",
                    error="Stored photograph could not be opened.",
                )
            try:
                from PIL import Image

                for path in (local, factory):
                    if path and os.path.isfile(path):
                        with Image.open(path) as img:
                            img.verify()
            except Exception:
                return stamp_photo_aid_metadata(
                    out,
                    status="missing",
                    error="Stored photograph could not be opened.",
                )
            return filled
        out["failed_queries"] = list(dict.fromkeys(failed_queries))
        out["rejected_photo_ids"] = sorted(rejected_ids)
        return stamp_photo_aid_metadata(out, status="missing", error=last_error)
    except PexelsError as exc:
        from services.ebook_pexels import customer_pexels_message

        msg = customer_pexels_message(exc)
        missing = stamp_photo_aid_metadata(out, status="missing", error=msg)
        missing["customer_message"] = customer_pexels_message(exc)
        missing["error_code"] = getattr(exc, "code", "request_failed")
        return missing


def _photo_already_stored(aid: dict[str, Any]) -> bool:
    path = str(aid.get("asset_path") or aid.get("factory_asset_path") or "")
    return bool(path and photo_file_is_valid(path) and str(aid.get("sha256") or "").strip())


def _ai_prompt_from_brief(brief, *, extra: str = "", style_spec: dict | None = None) -> str:
    from services.ebook_visual_brief_common import style_spec_prompt_suffix

    objects = ", ".join(list(brief.required_objects or [])[:4])
    prompt = (
        f"Photorealistic professional instructional photograph showing {brief.required_subject} "
        f"{brief.required_action} in {brief.required_setting}. "
        f"Visible: {objects}. {brief.business_purpose} "
        "No text, no watermark, no logos, no advertisements."
    )
    suffix = style_spec_prompt_suffix(style_spec)
    if suffix:
        prompt = f"{prompt} {suffix}"
    if extra:
        prompt = f"{prompt} {extra}"
    return " ".join(prompt.split())


def fill_photo_aid_with_ai(
    aid: dict[str, Any],
    *,
    package_id: str,
    data: dict | None = None,
    fields: dict | None = None,
    chapter: str = "",
    title: str = "",
    topic: str = "",
) -> dict[str, Any]:
    """Generate one missing photograph after stock search failed. Respects the project cap."""
    from pathlib import Path

    from services.ebook_package import authorize_paid_image_generation, generate_visual_image

    out = dict(aid or {})
    payload = data if isinstance(data, dict) else {}
    fields = fields if isinstance(fields, dict) else (
        payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    )
    brief = build_visual_brief(out, chapter=chapter or str(out.get("chapter") or ""), title=title, topic=topic)
    out["visual_brief"] = brief.as_dict()
    if not visual_ai_authorized(payload, fields):
        missing = stamp_photo_aid_metadata(out, status="missing", error=budget_visual_customer_message())
        missing["customer_message"] = unresolved_visual_customer_message(out)
        missing["budget_message"] = budget_visual_customer_message()
        return missing
    # One style spec per project, cached on the payload so every generated
    # image in this book (cover included) repeats the same audience/tone/
    # environment description -- the closest thing to visual consistency
    # this provider allows without native reference-image support.
    from services.ebook_visual_brief_common import build_visual_style_spec

    style_spec = payload.get("_visual_style_spec") if isinstance(payload.get("_visual_style_spec"), dict) else None
    if style_spec is None:
        style_spec = build_visual_style_spec(
            title=title, topic=topic, audience=str(fields.get("audience") or "")
        )
        payload["_visual_style_spec"] = style_spec
    vid = str(out.get("visual_id") or "visual")
    dest_dir = os.path.join(EXPORTS_DIR, str(package_id or "ebook-visuals-local"))
    os.makedirs(dest_dir, exist_ok=True)
    extras = ("", "Natural documentary lighting, real-world setting, no collage.")
    last_error = budget_visual_customer_message()
    for attempt, extra in enumerate(extras[:AI_VISUAL_MAX_ATTEMPTS]):
        if not charge_visual_ai_call(payload, fields, purpose="ebook_visual_ai"):
            last_error = budget_visual_customer_message()
            break
        tmp = os.path.join(dest_dir, f"{vid}.ai-try.png")
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        prompt = _ai_prompt_from_brief(brief, extra=extra, style_spec=style_spec)
        try:
            with authorize_paid_image_generation("ebook_automatic_visual"):
                ok = generate_visual_image(
                    prompt,
                    tmp,
                    size="1024x1024",
                    user_authorized=True,
                    quality="medium",
                    package_id=str(package_id or ""),
                )
        except Exception as exc:  # noqa: BLE001 — never retry indefinitely
            last_error = unresolved_visual_customer_message(out)
            out["error_detail"] = str(exc)[:200]
            continue
        if not ok or not os.path.isfile(tmp):
            last_error = unresolved_visual_customer_message(out)
            continue
        raw = Path(tmp).read_bytes()
        labels = list(brief.subject_tokens or []) + list(brief.action_tokens or []) + list(brief.setting_tokens or [])
        # Do NOT score against the raw generation prompt as "alt text": the
        # prompt is full of negative instructions to the image model ("no
        # watermark", "no logos", ...) that would trip the very forbidden-
        # token check meant to catch a real watermark/logo in the image.
        # content_labels carries the positive subject/action/setting signal
        # instead -- an AI image has no independent alt text to inspect.
        inspected = score_photo_against_brief(
            brief,
            alt="",
            filename=tmp,
            image_bytes=raw,
            planned_caption=str(out.get("caption") or out.get("title") or ""),
            content_labels=labels,
        )
        try:
            os.remove(tmp)
        except OSError:
            pass
        if inspected.status == MATCH_REJECT and attempt + 1 < AI_VISUAL_MAX_ATTEMPTS:
            last_error = unresolved_visual_customer_message(out)
            continue
        if inspected.status == MATCH_REJECT:
            last_error = unresolved_visual_customer_message(out)
            break
        filled = store_interior_photo(out, raw, package_id=package_id)
        filled["type"] = str(out.get("type") or "photo")
        filled["source"] = "ai_generated"
        filled["attribution"] = "AI-created image"
        filled["photographer"] = "Factory"
        filled["page_url"] = ""
        filled["source_url"] = ""
        filled["photo_id"] = ""
        filled["alt"] = prompt[:180]
        filled["approved"] = False
        filled["user_accepted"] = False
        filled = apply_match_report(filled, inspected)
        filled["status"] = "resolved"
        filled["retryable"] = filled.get("match_status") != MATCH_PASS
        filled["error"] = "" if filled.get("match_status") != MATCH_REJECT else inspected.rejection_reason
        filled["rendered"] = True
        filled["has_file"] = True
        filled = publish_factory_photo(filled, package_id)
        if not photo_file_is_valid(str(filled.get("asset_path") or "")):
            last_error = unresolved_visual_customer_message(out)
            continue
        return filled
    missing = stamp_photo_aid_metadata(out, status="missing", error=last_error)
    missing["customer_message"] = unresolved_visual_customer_message(out)
    if not visual_ai_authorized(payload, fields):
        missing["budget_message"] = budget_visual_customer_message()
    return missing


def fill_photo_aid_automatic(
    aid: dict[str, Any],
    *,
    package_id: str,
    title: str = "",
    topic: str = "",
    audience: str = "",
    chapter: str = "",
    data: dict | None = None,
    fields: dict | None = None,
    allow_ai: bool = True,
) -> dict[str, Any]:
    """Stock-photo search first; AI only when stock cannot satisfy the brief and budget remains."""
    out = dict(aid or {})
    if prefers_local_medium(out):
        return out
    if _photo_already_stored(out) and str(out.get("match_status") or "") == MATCH_PASS:
        return out
    stock = fill_photo_aid_from_pexels(
        out,
        package_id=package_id,
        title=title,
        topic=topic,
        audience=audience,
        chapter=chapter,
    )
    if _photo_already_stored(stock) and str(stock.get("match_status") or "") != MATCH_REJECT:
        return stock
    if not allow_ai:
        stock["customer_message"] = unresolved_visual_customer_message(stock)
        return stock
    payload = data if isinstance(data, dict) else {}
    fields = fields if isinstance(fields, dict) else (
        payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    )
    if not visual_ai_authorized(payload, fields):
        stock["customer_message"] = unresolved_visual_customer_message(stock)
        stock["budget_message"] = budget_visual_customer_message()
        stock["error"] = stock.get("error") or budget_visual_customer_message()
        return stock
    return fill_photo_aid_with_ai(
        stock,
        package_id=package_id,
        data=payload,
        fields=fields,
        chapter=chapter,
        title=title,
        topic=topic,
    )


def fill_plan_photos_automatic(
    visual_plan: dict[str, Any],
    *,
    package_id: str,
    title: str = "",
    topic: str = "",
    audience: str = "",
    data: dict | None = None,
    fields: dict | None = None,
    allow_ai: bool = True,
) -> dict[str, Any]:
    """Fill missing photographs. Successful assets are never regenerated or deleted."""
    plan = visual_plan if isinstance(visual_plan, dict) else {"chapters": []}
    payload = data if isinstance(data, dict) else {}
    set_visual_progress(payload, PROGRESS_STOCK)
    chapters = list(plan.get("chapters") or [])
    unresolved: list[dict[str, Any]] = []
    budget_block = False
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        chapter = str(ch.get("chapter") or "")
        aids = list(ch.get("aids") or [])
        for i, aid in enumerate(aids):
            if not isinstance(aid, dict) or not is_photo_aid(aid):
                continue
            if prefers_local_medium(aid):
                continue
            if _photo_already_stored(aid) and str(aid.get("match_status") or "") == MATCH_PASS:
                continue
            filled = fill_photo_aid_automatic(
                aid,
                package_id=package_id,
                title=title,
                topic=topic,
                audience=audience,
                chapter=chapter,
                data=payload,
                fields=fields,
                allow_ai=allow_ai,
            )
            aids[i] = filled
            if not _photo_already_stored(filled) or str(filled.get("match_status") or "") == MATCH_REJECT:
                unresolved.append(filled)
                if filled.get("budget_message"):
                    budget_block = True
        ch["aids"] = aids
    plan["chapters"] = chapters
    if unresolved:
        plan["visuals_blocked"] = True
        first = unresolved[0]
        plan["customer_visual_message"] = first.get("customer_message") or unresolved_visual_customer_message(first)
        if budget_block:
            plan["customer_budget_message"] = budget_visual_customer_message()
    else:
        plan["visuals_blocked"] = False
        plan["customer_visual_message"] = ""
        plan["customer_budget_message"] = ""
    set_visual_progress(payload, PROGRESS_QA)
    return plan


def fill_plan_photos_from_pexels(
    visual_plan: dict[str, Any],
    *,
    package_id: str,
    title: str = "",
    topic: str = "",
    audience: str = "",
) -> dict[str, Any]:
    """Stock-only fill. Does not spend paid AI budget."""
    return fill_plan_photos_automatic(
        visual_plan,
        package_id=package_id,
        title=title,
        topic=topic,
        audience=audience,
        allow_ai=False,
    )


def strip_photo_aids(visual_plan: dict[str, Any]) -> dict[str, Any]:
    plan = visual_plan if isinstance(visual_plan, dict) else {"chapters": []}
    for ch in list(plan.get("chapters") or []):
        if not isinstance(ch, dict):
            continue
        ch["aids"] = [
            aid
            for aid in list(ch.get("aids") or [])
            if isinstance(aid, dict) and not is_photo_aid(aid)
        ]
    return plan


def stamp_plan_render_flags(visual_plan: dict[str, Any], *, package_id: str) -> dict[str, Any]:
    plan = visual_plan if isinstance(visual_plan, dict) else {"chapters": []}
    for ch in list(plan.get("chapters") or []):
        if not isinstance(ch, dict):
            continue
        for aid in list(ch.get("aids") or []):
            if not isinstance(aid, dict):
                continue
            if is_photo_aid(aid):
                path = str(aid.get("asset_path") or aid.get("factory_asset_path") or "")
                factory = factory_img_path(package_id, str(aid.get("visual_id") or ""))
                ok = photo_file_is_valid(path) or photo_file_is_valid(factory)
                aid["has_file"] = bool(ok)
                aid["rendered"] = bool(ok)
                if not ok:
                    aid["status"] = str(aid.get("status") or "missing")
                    aid["retryable"] = True
            else:
                aid["rendered"] = True
                aid.setdefault("has_file", False)
    return plan


def stage_factory_photo_cover(
    *,
    title: str,
    subtitle: str = "",
    author: str = "",
    fields: dict | None = None,
    package_id: str = "",
    search_photos: bool = True,
) -> dict[str, Any]:
    """Pending photo-cover record. Searches Pexels candidates; does not select or approve."""
    fields = fields or {}
    queries = cover_pexels_queries(
        title=title,
        topic=str(fields.get("topic") or title),
        audience=str(fields.get("audience") or ""),
    )
    query = queries[0] if queries else topic_pexels_query(
        title=title,
        topic=str(fields.get("topic") or title),
        audience=str(fields.get("audience") or ""),
    )
    status = pexels_public_status()
    photos: list[dict[str, Any]] = []
    error = ""
    if search_photos:
        try:
            from services.ebook_visual_match import score_cover_photo

            seen: set[str] = set()
            ranked: list[tuple[float, dict[str, Any]]] = []
            for item in queries[:5]:
                result = search_pexels(item, orientation="portrait", per_page=12)
                for photo in public_photos(result.get("photos")):
                    pid = str(photo.get("photo_id") or "")
                    if not pid or pid in seen:
                        continue
                    seen.add(pid)
                    score = score_cover_photo(photo, title=title, topic=str(fields.get("topic") or title))
                    if score > 0:
                        ranked.append((score, photo))
                if ranked:
                    photos = [row[1] for row in sorted(ranked, key=lambda r: r[0], reverse=True)[:12]]
                    query = item
                    break
            if not status.get("configured"):
                error = str((result.get("message") if 'result' in locals() else "") or "Pexels not configured")
            elif not photos:
                error = "No matching cover photograph was found."
        except PexelsError as exc:
            error = str(exc)
    return {
        "workflow": "photo_backed",
        "photo_backed": True,
        "title": title,
        "subtitle": subtitle,
        "author": author,
        "package_id": package_id,
        "product_type": "ebook",
        "selected_layout": None,
        "source": None,
        "variants": {},
        "cover_digest": "",
        "approved": False,
        "use_ai_image": False,
        "image_prompt": "",
        "cover_prompt": "",
        "cover_search_query": query,
        "next_action": NEXT_CHOOSE_COVER,
        "pexels": {
            **status,
            "query": query,
            "photos": photos,
            "page": 1,
            "error": error,
        },
    }


def count_visuals(visual_plan: dict | None) -> dict[str, int]:
    chapters = list((visual_plan or {}).get("chapters") or []) if isinstance(visual_plan, dict) else []
    required = 0
    rendered = 0
    missing_photos = 0
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        for aid in list(ch.get("aids") or []):
            if not isinstance(aid, dict):
                continue
            required += 1
            if is_photo_aid(aid):
                if aid.get("rendered") and aid.get("has_file"):
                    rendered += 1
                else:
                    missing_photos += 1
            else:
                rendered += 1
    return {
        "required_visual_count": required,
        "rendered_visual_count": rendered,
        "missing_photo_count": missing_photos,
    }


STATUS_NEEDS_CORRECTION = "Needs correction."
STATUS_EBOOK_READY = "Ebook ready"
STATUS_PROJECT_COMPLETED = "Project completed."

READINESS_FIELDS = (
    "required_visual_count",
    "rendered_visual_count",
    "missing_photo_count",
    "ebook_ready",
    "export_ready",
    "pdf_available",
    "zip_available",
    "cover_ready",
    "completion_blockers",
    "next_action",
    "status_label",
    "visual_status_message",
    "pdf_enabled",
    "zip_enabled",
    "draft_files_only",
    "manuscript_quality_failures",
    "pexels_status",
    "package_id",
    "required_instructional_count",
    "verified_instructional_count",
    "supporting_component_count",
    "decorative_component_count",
    "rejected_or_missing_count",
    "unresolved_visual_requirements",
    "visual_requirements_met",
    "chapter_visual_requirements",
)


def is_factory_ebook(data: dict | None, *, project_type: str = "") -> bool:
    if str(project_type or "").strip().lower() == "ebook":
        return True
    if not isinstance(data, dict):
        return False
    return str(data.get("product_type") or "").strip().lower() == "ebook"


def visual_progress_message(counts: dict | None, typed: dict | None = None) -> str:
    counts = counts if isinstance(counts, dict) else {}
    required = int(counts.get("required_visual_count") or 0)
    rendered = int(counts.get("rendered_visual_count") or 0)
    missing = int(counts.get("missing_photo_count") or 0)
    noun = "visual" if required == 1 else "visuals"
    msg = f"{rendered} of {required} {noun} stored on disk"
    if missing:
        photo_noun = "photograph" if missing == 1 else "photographs"
        verb = "needs" if missing == 1 else "need"
        msg += f" · {missing} {photo_noun} still {verb} retrieval."

    unresolved = (typed or {}).get("unresolved_visual_requirements") or []
    if unresolved:
        # Override the raw file-count message with the honest, specific
        # picture: a checklist/table/callout can inflate "rendered" without
        # ever satisfying a chapter's real demonstration/comparison/data
        # requirement, so surface exactly what's still unresolved instead of
        # letting a full file count read as "done".
        req_total = int((typed or {}).get("required_instructional_count") or 0)
        verified = int((typed or {}).get("verified_instructional_count") or 0)
        names = ", ".join(u.get("chapter", "") for u in unresolved[:3] if u.get("chapter"))
        more = f" (+{len(unresolved) - 3} more)" if len(unresolved) > 3 else ""
        if req_total:
            msg = f"{verified} of {req_total} required demonstrations verified"
        else:
            msg = "Required visuals not yet verified"
        if names:
            msg += f" · still needed: {names}{more}."
        else:
            msg += "."
    return msg


def _phrase_excerpt(manuscript: str, phrase: str) -> str:
    needle = str(phrase or "").strip()
    text = str(manuscript or "")
    if not needle or not text:
        return ""
    pattern = rf"(?<![A-Za-z0-9]){re.escape(needle)}(?![A-Za-z0-9])"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return ""
    start = max(0, match.start() - 70)
    end = min(len(text), match.end() + 70)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def manuscript_quality_failures(manuscript: str, quality_result: Any = None) -> list[dict[str, str]]:
    """Return quality claims only when the manuscript actually contains them."""
    from services.ebook_quality_agent import _find_forbidden_marketing

    del quality_result  # Readiness never invents a claim from a stale QA blob.
    text = str(manuscript or "")
    # Strip markdown emphasis so "not **guaranteed**" / "**not guaranteed**" stay disclaimers.
    plain = re.sub(r"[*_`]+", " ", text)
    failures: list[dict[str, str]] = []
    seen: set[str] = set()
    for phrase in list(_find_forbidden_marketing(plain) or []):
        key = phrase.lower()
        if key in seen:
            continue
        excerpt = _phrase_excerpt(text, phrase)
        if not excerpt:
            continue
        seen.add(key)
        failures.append(
            {
                "phrase": phrase,
                "excerpt": excerpt,
                "message": f"Manuscript contains “{phrase}”.",
            }
        )
    return failures


def _resolve_pdf_path(data: dict) -> str:
    explicit = str(data.get("_pdf_path") or data.get("pdf_path") or "")
    if explicit:
        return explicit
    files = data.get("export_files") if isinstance(data.get("export_files"), dict) else {}
    for key in ("ebook.pdf", "pdf"):
        path = str(files.get(key) or "")
        if path:
            return path
    pkg = str(data.get("package_id") or "")
    if pkg:
        return os.path.join(EXPORTS_DIR, pkg, "ebook.pdf")
    return ""


def replace_visual_aid(visual_plan: dict | None, visual_id: str, filled: dict) -> dict:
    plan = visual_plan if isinstance(visual_plan, dict) else {"chapters": []}
    vid = str(visual_id or "").strip()
    chapters = list(plan.get("chapters") or [])
    found = False
    for ch in chapters:
        if not isinstance(ch, dict):
            continue
        aids = list(ch.get("aids") or [])
        for i, aid in enumerate(aids):
            if isinstance(aid, dict) and str(aid.get("visual_id") or "") == vid:
                aids[i] = filled
                found = True
        ch["aids"] = aids
    if not found and vid:
        if not chapters:
            chapters = [{"chapter": str(filled.get("chapter") or ""), "aids": []}]
        chapters[0].setdefault("aids", []).append(filled)
    plan["chapters"] = chapters
    return plan


def ebook_project_readiness(data: dict | None) -> dict[str, Any]:
    """Authoritative factory-ebook status. Used by every label, download, and export control."""
    data = data if isinstance(data, dict) else {}
    package_id = str(data.get("package_id") or "")
    plan = data.get("visual_plan")
    if isinstance(plan, dict):
        plan = json.loads(json.dumps(plan))
        if package_id:
            stamp_plan_render_flags(plan, package_id=package_id)
    else:
        plan = {"chapters": []}
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    export_files = data.get("export_files") if isinstance(data.get("export_files"), dict) else {}
    pdf_path = _resolve_pdf_path(data)
    counts = count_visuals(plan)

    # Typed, honest visual-requirement validation (additive to the legacy
    # counters above): distinguishes a real photograph/illustration/diagram/
    # chart from a checklist/callout/decorative element, and derives what
    # each chapter actually needs shown from its own content instead of
    # trusting "a file was rendered" as proof a requirement was met.
    from services.ebook_visual_requirements import validate_visual_plan_typed

    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    typed = validate_visual_plan_typed(
        plan,
        content_md=str(data.get("content") or data.get("ebook") or ""),
        title=str(data.get("title") or ""),
        topic=str(fields.get("topic") or data.get("title") or ""),
    )

    blockers: list[str] = []
    source = cover.get("source") if isinstance(cover.get("source"), dict) else {}
    selected = str(cover.get("selected_layout") or "").strip()
    cover_file = str(cover.get("image_path") or cover.get("local_cover_pdf") or "")
    prompt_only = bool(str(cover.get("image_prompt") or cover.get("cover_prompt") or "").strip()) and not (
        source.get("sha256") and selected and cover_file and os.path.isfile(cover_file)
    )
    cover_ready = bool(source.get("sha256") and selected and not prompt_only)
    approved_cover = bool(cover.get("approved")) or cover_ready

    unresolved_requirements = list(typed.get("unresolved_visual_requirements") or [])
    # A specific, honest per-chapter label ("Deadlift demonstration: missing")
    # instead of a generic "review visuals" -- this is what actually caught
    # the case the legacy counters missed: a chapter whose only aid is a
    # checklist/callout has no photo aid to report as "missing", so
    # missing_photo_count stayed 0 while the chapter had no real photograph.
    unresolved_requirement_label = ""
    if unresolved_requirements:
        first = unresolved_requirements[0]
        kind_label = {
            "demonstration": "demonstration",
            "comparison": "comparison visual",
            "data": "data visual",
        }.get(first.get("requirement_kind"), "visual")
        unresolved_requirement_label = f"{first.get('chapter')}: {kind_label} missing"

    if counts["missing_photo_count"]:
        blockers.append(NEXT_RETRY_IMAGE)
    elif counts["required_visual_count"] and counts["rendered_visual_count"] < counts["required_visual_count"]:
        blockers.append(NEXT_REVIEW_VISUALS)
    elif unresolved_requirement_label:
        blockers.append(unresolved_requirement_label)
    if cover.get("workflow") != "photo_backed" or not source.get("sha256") or prompt_only or not selected:
        blockers.append(NEXT_CHOOSE_COVER)

    pdf_ok = bool(pdf_path and os.path.isfile(pdf_path) and os.path.getsize(pdf_path) > 8)
    if pdf_ok:
        try:
            with open(pdf_path, "rb") as fh:
                pdf_ok = fh.read(5).startswith(b"%PDF")
        except OSError:
            pdf_ok = False
    if not pdf_ok:
        blockers.append(NEXT_BUILD_PDF)
    if data.get("ebook_pdf_qa_passed") is False or (
        isinstance(data.get("ebook_pdf_qa_errors"), list) and data.get("ebook_pdf_qa_errors")
    ):
        blockers.append("Repair PDF quality defects before Ready")

    zip_path = str(export_files.get("package.zip") or "")
    if zip_path and os.path.isfile(zip_path):
        pass
    elif pdf_ok and not blockers:
        blockers.append(NEXT_CORRECT_PREFLIGHT)

    unique: list[str] = []
    for item in blockers:
        if item not in unique:
            unique.append(item)
    missing_required = bool(
        counts["missing_photo_count"]
        or not approved_cover
        or not pdf_ok
        or unresolved_requirements
    )
    ready = (not unique) and (not missing_required)
    next_action = unique[0] if unique else ""
    if counts["missing_photo_count"]:
        next_action = NEXT_RETRY_IMAGE
    elif unresolved_requirement_label and (
        not counts["required_visual_count"] or counts["rendered_visual_count"] >= counts["required_visual_count"]
    ):
        next_action = unresolved_requirement_label
    elif not approved_cover:
        next_action = NEXT_CHOOSE_COVER
    manuscript = str(data.get("content") or data.get("ebook") or "")
    failures = manuscript_quality_failures(manuscript, data.get("quality_result"))
    status_label = STATUS_EBOOK_READY if ready else STATUS_NEEDS_CORRECTION
    return {
        **counts,
        "ebook_ready": ready,
        "export_ready": ready,
        "pdf_available": bool(pdf_ok) and ready,
        "zip_available": ready,
        "cover_ready": cover_ready,
        "completion_blockers": unique,
        "next_action": next_action,
        "status_label": status_label,
        "visual_status_message": visual_progress_message(counts, typed),
        "pdf_enabled": ready,
        "zip_enabled": ready,
        "draft_files_only": not ready,
        # Typed visual-requirement contract (Visual Review UI): required
        # instructional visuals vs. verified ones, kept separate from
        # supporting/decorative component counts and from placeholder/
        # rejected assets, instead of one misleading combined total.
        "required_instructional_count": typed.get("required_instructional_count", 0),
        "verified_instructional_count": typed.get("verified_instructional_count", 0),
        "supporting_component_count": typed.get("supporting_component_count", 0),
        "decorative_component_count": typed.get("decorative_component_count", 0),
        "rejected_or_missing_count": typed.get("rejected_or_missing_count", 0),
        "unresolved_visual_requirements": unresolved_requirements,
        "visual_requirements_met": typed.get("visual_requirements_met", True),
        "chapter_visual_requirements": typed.get("chapter_requirements", []),
        "manuscript_quality_failures": failures,
        "pexels_status": pexels_status_label(),
        "package_id": package_id,
    }


def apply_ebook_readiness(data: dict | None, *, project_type: str = "") -> dict[str, Any]:
    """Stamp readiness onto project/package data. Does not rewrite the manuscript."""
    data = data if isinstance(data, dict) else {}
    if not is_factory_ebook(data, project_type=project_type):
        return data
    package_id = str(data.get("package_id") or "")
    if isinstance(data.get("visual_plan"), dict) and package_id:
        stamp_plan_render_flags(data["visual_plan"], package_id=package_id)
    state = ebook_project_readiness(data)
    for key in READINESS_FIELDS:
        data[key] = state.get(key)
    data["readiness"] = state
    for export_key in ("exports", "product_exports"):
        exports = data.get(export_key) if isinstance(data.get(export_key), dict) else None
        if exports is None:
            continue
        files = dict(exports.get("files") or {})
        keep_existing = data.get("customer_keep") is True
        if not keep_existing and not state.get("zip_enabled"):
            files.pop("zip", None)
        if not keep_existing and not state.get("pdf_enabled"):
            files.pop("pdf", None)
        exports = dict(exports)
        exports["files"] = files
        exports["pdf_available"] = bool(state.get("pdf_available"))
        if not state.get("pdf_available"):
            exports["pdf_message"] = (
                f"PDF is not available. {state.get('next_action') or NEXT_RETRY_IMAGE}"
            )
        data[export_key] = exports
    return data


def factory_ebook_completion_state(
    *,
    visual_plan: dict | None,
    cover_design: dict | None,
    package_id: str = "",
    pdf_path: str = "",
    export_files: dict | None = None,
    content: str = "",
    quality_result: Any = None,
) -> dict[str, Any]:
    """Honest factory completion. Never claims Ebook ready when assets or PDF are missing."""
    return ebook_project_readiness(
        {
            "product_type": "ebook",
            "visual_plan": visual_plan,
            "cover_design": cover_design,
            "package_id": package_id,
            "export_files": export_files or {},
            "_pdf_path": pdf_path,
            "content": content,
            "quality_result": quality_result,
        }
    )
