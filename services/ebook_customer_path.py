"""Canonical customer Ebook path: details → generate → review → save → download.

Reuses existing Pexels, photo-cover, visual, and package services.
Zero paid calls unless the caller already authorized manuscript generation.
"""
from __future__ import annotations

import hashlib
import io
import os
import shutil
import zipfile
from typing import Any

from services.ebook_contamination import (
    DEFAULT_AUTHOR,
    gate_ebook_output,
    normalize_author,
    normalize_book_title,
    sanitize_manuscript,
)
from services.ebook_factory_pipeline import (
    apply_ebook_readiness,
    _resolve_pdf_path,
    AI_VISUAL_MAX_ATTEMPTS,
    charge_visual_ai_call,
    visual_ai_authorized,
)
from services.ebook_package import EXPORTS_DIR, build_ebook_package
from services.ebook_pexels import (
    PexelsError,
    customer_pexels_message,
    cover_pexels_queries,
    download_pexels_original,
    search_pexels,
    topic_pexels_query,
)
from services.ebook_photo_cover import (
    LAYOUT_IDS,
    PhotoCoverError,
    _store_source_bytes,
    _activate_source,
    select_layout,
)

FIXTURE_ENV = "EBOOK_CUSTOMER_PATH_FIXTURE"
CONTAINER_TITLE = "Beginner's Guide to Container Gardening"
CONTAINER_AUTHOR = "Lonnie Brown"
CONTAINER_SUBTITLE = "Grow vegetables and herbs in pots, tubs, and small spaces"
SAVE_SUCCESS = "Project saved successfully"


def fixture_mode() -> bool:
    """Deterministic test content is allowed only under BOTH safety switches.

    Previously this checked EBOOK_CUSTOMER_PATH_FIXTURE alone, so one stray
    environment variable could have served fixture content to a real customer.
    It now delegates to the shared dual gate. See services/external_calls.py.
    """
    from services.external_calls import ebook_fixture_mode

    return ebook_fixture_mode()


def container_gardening_manuscript() -> str:
    return f"""# {CONTAINER_TITLE}

{CONTAINER_SUBTITLE}

## Why Container Gardening Works for Beginners

Container gardening lets a beginner grow food on a balcony, patio, or steps without digging a yard. A pot is a complete growing system: soil, roots, water, and sunlight stay in one place you can actually reach.

A small start beats a sprawling plan. Two or three containers of herbs and one easy vegetable teach watering, light, and harvest faster than a dozen mixed pots.

| Goal | First containers | Why it works |
|---|---|---|
| Herbs for cooking | Two 10-inch pots | Fast harvest, small soil volume |
| Salad greens | One wide tub | Shallow roots and frequent picking |
| One fruiting crop | One 5-gallon pot | Enough soil for tomatoes or peppers |

## Choosing Containers That Help Plants Grow

Pick a pot with drainage holes. Size matters more than color. Herbs tolerate 8 to 10 inches. Leafy greens like a wide, shallow tub. Tomatoes and peppers need at least five gallons so roots stay cool and wet without drowning.

Plastic holds moisture. Clay breathes and dries faster. Fabric pots air-prune roots. Reused buckets work when you drill holes in the base and skip anything that held chemicals.

## Soil, Planting, and the Right Crops to Start With

Use potting mix, not garden dirt. Garden soil packs hard in a pot and starves roots of air. Mix in a slow fertilizer labeled for vegetables, then plant.

Start with basil, chives, lettuce, and cherry tomatoes if you have six hours of sun. In lower light, choose mint, parsley, and leafy greens. Plant at the depth on the seed packet or just above the original nursery soil line.

## Water, Sunlight, and Daily Plant Care

Pots dry from the sides as well as the top. Water when the top inch of mix is dry, and water until it leaves the drainage holes. Morning watering reduces overnight dampness.

Most edible crops want six hours of direct sun. If leaves stretch and stay pale, move the pot, do not add more fertilizer first.

## Handling Pests and Plant Problems Early

Look under leaves once a week. Aphids, whiteflies, and fungus gnats show up before a plant collapses. A strong spray of water, picking damaged leaves, and moving a sick pot away from others solve most beginner problems.

Yellow leaves with wet soil usually mean overwatering. Dry, crispy edges usually mean the pot baked in afternoon sun.

## Harvesting, Replanting, and Keeping the Garden Going

Pick herbs often so they stay bushy. Harvest lettuce leaves from the outside. Pick cherry tomatoes when they color fully and smell sweet.

When a crop finishes, empty tired mix into a garden bed or compost, wash the pot, and refill with fresh mix before the next planting.
"""


def fixture_visual_plan(title: str, content_md: str) -> dict[str, Any]:
    """Deterministic visual plan for isolated customer-path tests. No paid calls."""
    chapters = [
        {
            "chapter": "Why Container Gardening Works for Beginners",
            "aids": [
                {
                    "type": "table",
                    "title": "First containers that teach the basics",
                    "caption": "Start with two herbs and one easy vegetable.",
                    "table": {
                        "headers": ["Goal", "First containers", "Why it works"],
                        "rows": [
                            ["Herbs for cooking", "Two 10-inch pots", "Fast harvest, small soil volume"],
                            ["Salad greens", "One wide tub", "Shallow roots and frequent picking"],
                            ["One fruiting crop", "One 5-gallon pot", "Enough soil for tomatoes or peppers"],
                        ],
                    },
                },
                {
                    "type": "stock photo",
                    "title": "Balcony pots with herbs",
                    "caption": "A beginner balcony with a few well-spaced containers.",
                    "image_prompt": "photorealistic balcony herb pots in morning light, no text",
                    "keywords": "balcony herb pots beginner garden",
                },
            ],
        },
        {
            "chapter": "Choosing Containers That Help Plants Grow",
            "aids": [
                {
                    "type": "stock photo",
                    "title": "Garden pots and potting soil",
                    "caption": "Drainage holes and the right pot size matter more than color.",
                    "image_prompt": "photorealistic garden pots and potting soil, no text",
                    "keywords": "garden pots and potting soil",
                },
                {
                    "type": "worksheet box",
                    "title": "Pot checklist",
                    "caption": "Check drainage and size before you plant.",
                    "items": ["Drainage holes in the base", "At least eight inches for herbs", "Five gallons for tomatoes"],
                },
            ],
        },
        {
            "chapter": "Soil, Planting, and the Right Crops to Start With",
            "aids": [
                {
                    "type": "stock photo",
                    "title": "Potting mix in a tub",
                    "caption": "Loose potting mix, not garden dirt, fills the container.",
                    "image_prompt": "photorealistic hands filling a pot with potting mix, no text",
                    "keywords": "potting mix filling container vegetable",
                },
                {
                    "type": "action step box",
                    "title": "Planting order",
                    "caption": "Do these in one sitting.",
                    "items": ["Fill with potting mix", "Set the plant at the nursery soil line", "Water until it drains"],
                },
            ],
        },
        {
            "chapter": "Water, Sunlight, and Daily Plant Care",
            "aids": [
                {
                    "type": "stock photo",
                    "title": "Watering patio vegetables",
                    "caption": "Water until it leaves the drainage holes.",
                    "image_prompt": "photorealistic watering potted vegetables on a patio, no text",
                    "keywords": "watering patio vegetables",
                },
                {
                    "type": "tip box",
                    "title": "Water until it leaves the holes",
                    "caption": "Pots dry from the sides as well as the top.",
                    "body": "Water when the top inch of mix is dry, and stop only after water leaves the drainage holes.",
                },
            ],
        },
        {
            "chapter": "Handling Pests and Plant Problems Early",
            "aids": [
                {
                    "type": "stock photo",
                    "title": "Damaged vegetable leaves",
                    "caption": "Look under leaves once a week before a plant collapses.",
                    "image_prompt": "photorealistic damaged vegetable leaves on a potted plant, no text",
                    "keywords": "garden pests damaged vegetable leaves",
                },
                {
                    "type": "worksheet box",
                    "title": "What the leaves are telling you",
                    "caption": "Match the symptom before you add fertilizer.",
                    "items": ["Yellow leaves with wet soil: overwatering", "Dry crispy edges: afternoon bake"],
                },
            ],
        },
        {
            "chapter": "Harvesting, Replanting, and Keeping the Garden Going",
            "aids": [
                {
                    "type": "stock photo",
                    "title": "Harvesting basil from a pot",
                    "caption": "Pick herbs often so the plant stays bushy.",
                    "image_prompt": "photorealistic hands harvesting basil from a patio pot, no text",
                    "keywords": "harvesting basil container patio",
                },
                {
                    "type": "action step box",
                    "title": "Reset a finished pot",
                    "caption": "Empty, wash, and refill before the next crop.",
                    "items": ["Empty tired mix", "Wash the pot", "Refill with fresh mix"],
                },
            ],
        },
    ]
    return {
        "subtitle": CONTAINER_SUBTITLE,
        "cover_prompt": "Portrait photograph of vegetable pots on a sunny balcony, no lettering.",
        "product_summary": "A practical beginner handbook for growing vegetables and herbs in pots, tubs, and small spaces.",
        "chapters": chapters,
    }


def _fixture_jpeg(color: tuple[int, int, int], *, seed: str = "a") -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1600, 2200), color)
    draw = ImageDraw.Draw(img)
    draw.rectangle((80, 120, 1520, 1100), fill=(210, 180, 90))
    draw.ellipse((400, 700, 1200, 1700), fill=(40, 90, 50))
    draw.rectangle((200, 1800, 1400, 2100), fill=(30, 50, 40))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def normalize_ebook_fields(fields: dict | None, *, title: str = "", content: str = "") -> dict[str, Any]:
    payload = dict(fields or {})
    raw_title = (
        payload.get("ebook_title")
        or payload.get("title")
        or title
        or ""
    )
    author_raw = (
        payload.get("author_brand")
        or payload.get("author")
        or payload.get("author_name")
        or ""
    )
    # A stored "title" is sometimes the raw topic/product-description
    # sentence used to brief the manuscript, never meant for a cover (e.g.
    # "A form-focused kettlebell ebook teaching the six foundational
    # movements..."). Prefer it only when it looks like an authored title;
    # otherwise fall back to the manuscript's own H1 (and byline), never
    # inventing new text. See services.ebook_visual_brief_common.
    from services.ebook_visual_brief_common import resolve_cover_identity

    identity = resolve_cover_identity(
        stored_title=raw_title,
        stored_subtitle=str(payload.get("subtitle") or ""),
        stored_author=author_raw,
        topic=str(payload.get("topic") or ""),
        content_md=content,
    )
    clean_title = normalize_book_title(identity["title"] or raw_title) or "Untitled Ebook"
    if identity["subtitle"]:
        payload["subtitle"] = identity["subtitle"]
    author = normalize_author(identity["author"] or author_raw, "", "")
    payload["ebook_title"] = clean_title
    payload["title"] = clean_title
    payload["author_brand"] = author
    payload["author"] = author
    if not payload.get("topic"):
        payload["topic"] = clean_title
    # The canonical customer pipeline should use the established Pexels-aware
    # visual planner by default (photo-backed cover + relevant chapter
    # visuals) unless the caller explicitly opted out. Without this, requests
    # that never set include_images/visual_mode silently fall through
    # images_requested()'s conservative default of False, producing
    # local-only checklists and an unphotographed cover.
    if not str(payload.get("include_images") or "").strip() and not str(payload.get("visual_mode") or "").strip():
        payload.setdefault("include_images", "automatic")
    payload["_normalized_content"] = sanitize_manuscript(
        content,
        title=clean_title,
        subtitle=str(payload.get("subtitle") or ""),
        author=author,
    )
    return payload


def _first_passing_layout(cover: dict | None) -> str:
    variants = (cover or {}).get("variants") if isinstance(cover, dict) else {}
    if not isinstance(variants, dict):
        return ""
    for layout_id in LAYOUT_IDS:
        row = variants.get(layout_id) or {}
        qa = row.get("quality") or {}
        path = str(row.get("png_path") or "")
        if qa.get("pass") and path and os.path.isfile(path):
            return layout_id
    return ""


def _ai_cover_prompt(*, title: str, subtitle: str, fields: dict, style_spec: dict) -> str:
    from services.ebook_visual_brief_common import style_spec_prompt_suffix

    equipment = style_spec.get("equipment") or []
    subject = f"a person using {equipment[0]}" if equipment else "a person practicing the book's subject"
    prompt = (
        f'Premium commercial nonfiction book cover photograph for "{title}: {subtitle}". '
        f"Confident, healthy, realistic adult, {subject}, in a professional strength-training "
        "environment. Positive controlled energy, approachable strength, clear focal subject, "
        "portrait orientation with generous negative space reserved at the top and bottom for "
        "title and author typography. No barbell or unrelated equipment. No dark silhouette or "
        "gym-noir lighting. No crowded background. No visible brand names or logos. No text of "
        "any kind rendered in the image."
    )
    suffix = style_spec_prompt_suffix(style_spec)
    if suffix:
        prompt = f"{prompt} {suffix}"
    return " ".join(prompt.split())


def _generate_ai_cover_candidate(
    payload: dict,
    *,
    title: str,
    subtitle: str,
    fields: dict,
    package_id: str,
) -> str:
    """Original AI-generated cover candidate: the professional fallback when
    stock photography cannot fulfill the cover brief, not a lesser option.
    Bounded attempts, gated by the same project visual budget used for
    interior visuals. Returns the passing layout id, or "" if none passed
    within the attempt/budget limit -- callers must treat that as an honest,
    unresolved requirement, never a silent generic fallback.
    """
    if not visual_ai_authorized(payload, fields):
        return ""
    from pathlib import Path

    from services.ebook_package import authorize_paid_image_generation, generate_visual_image
    from services.ebook_visual_brief_common import build_visual_style_spec

    payload.setdefault("package_id", package_id)
    payload.setdefault("artifact_id", package_id)

    style_spec = payload.get("_visual_style_spec") if isinstance(payload.get("_visual_style_spec"), dict) else None
    if style_spec is None:
        style_spec = build_visual_style_spec(
            title=title, topic=str(fields.get("topic") or title), audience=str(fields.get("audience") or "")
        )
        payload["_visual_style_spec"] = style_spec

    dest_dir = os.path.join(EXPORTS_DIR, str(package_id or "ebook-cover-local"))
    os.makedirs(dest_dir, exist_ok=True)
    tmp = os.path.join(dest_dir, "cover.ai-try.png")
    # _activate_source() returns a rebuilt dict rather than mutating in
    # place, so each attempt works on its own local copy seeded from the
    # caller's payload; only a successful attempt is written back into the
    # caller's dict (once, at the end) -- an iteration that doesn't pan out
    # must never leave the caller holding a stripped-down dict.
    working = dict(payload)
    for attempt in range(AI_VISUAL_MAX_ATTEMPTS):
        if not charge_visual_ai_call(working, fields, purpose="ebook_cover_ai"):
            payload["visual_ai_spend_usd"] = working.get("visual_ai_spend_usd", payload.get("visual_ai_spend_usd", 0))
            return ""
        if os.path.isfile(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
        prompt = _ai_cover_prompt(title=title, subtitle=subtitle, fields=fields, style_spec=style_spec)
        try:
            with authorize_paid_image_generation("ebook_cover_ai"):
                ok = generate_visual_image(
                    prompt, tmp, size="1024x1536", user_authorized=True, quality="medium",
                    package_id=str(package_id or ""),
                )
        except Exception:  # noqa: BLE001 -- never retry indefinitely
            continue
        if not ok or not os.path.isfile(tmp):
            continue
        raw = Path(tmp).read_bytes()
        try:
            os.remove(tmp)
        except OSError:
            pass
        working.setdefault("package_id", package_id)
        working.setdefault("artifact_id", package_id)
        source = _store_source_bytes(
            working, raw, source_type="ai_generated", filename=f"cover-ai-{attempt}.png",
            license_note="Original AI-generated artwork. Not a stock photograph.",
            project_id=working.get("_project_id"),
        )
        source["ai_generated"] = True
        source["prompt"] = prompt[:400]
        working["cover_design"] = working.get("cover_design") or {}
        working = _activate_source(working, source, project_id=working.get("_project_id"))
        layout = _first_passing_layout(working.get("cover_design"))
        if layout:
            payload.clear()
            payload.update(working)
            return layout
    payload["visual_ai_spend_usd"] = working.get("visual_ai_spend_usd", payload.get("visual_ai_spend_usd", 0))
    return ""


def complete_photo_cover(
    data: dict,
    *,
    title: str,
    subtitle: str,
    author: str,
    fields: dict,
    package_id: str,
    keep_current: dict | None = None,
    force_new: bool = False,
) -> dict[str, Any]:
    """Select and render a professional photo cover. Keeps the current cover on failure."""
    previous = keep_current if isinstance(keep_current, dict) else None
    payload = dict(data or {})
    payload.setdefault("package_id", package_id)
    payload.setdefault("artifact_id", package_id)
    payload["title"] = title
    payload["subtitle"] = subtitle
    payload["author_brand"] = author
    payload["author"] = author
    payload["fields"] = fields
    payload["product_type"] = "ebook"
    queries = cover_pexels_queries(
        title=title,
        topic=str(fields.get("topic") or title),
        audience=str(fields.get("audience") or ""),
    )
    error = ""
    try:
        if fixture_mode():
            color = (36, 92, 48) if not force_new else (120, 40, 30)
            raw = _fixture_jpeg(color, seed="cover-b" if force_new else "cover-a")
            source = _store_source_bytes(
                payload,
                raw,
                source_type="pexels" if not fixture_mode() else "local_licensed",
                filename="cover-fixture.jpg",
                license_note="Deterministic local fixture photograph. Not for sale.",
                project_id=payload.get("_project_id"),
            )
            payload = _activate_source(payload, source, project_id=payload.get("_project_id"))
        else:
            from services.ebook_visual_match import score_cover_photo

            exclude = set()
            if force_new and isinstance(previous, dict):
                src = previous.get("source") if isinstance(previous.get("source"), dict) else {}
                pex = previous.get("pexels") if isinstance(previous.get("pexels"), dict) else {}
                for val in (src.get("photo_id"), pex.get("photo_id"), (src.get("pexels") or {}).get("photo_id") if isinstance(src.get("pexels"), dict) else ""):
                    if val:
                        exclude.add(str(val))
            ranked: list[tuple[float, dict[str, Any], str]] = []
            seen_ids: set[str] = set()
            for query in queries:
                result = search_pexels(query, orientation="portrait", per_page=12)
                for photo in list(result.get("photos") or []):
                    pid = str(photo.get("photo_id") or "")
                    if not pid or pid in exclude or pid in seen_ids:
                        continue
                    seen_ids.add(pid)
                    score = score_cover_photo(photo, title=title, topic=str(fields.get("topic") or title))
                    if score <= 0:
                        continue
                    ranked.append((score, photo, query))
                if ranked and ranked[0][0] >= 0.7:
                    break
            ranked.sort(key=lambda row: row[0], reverse=True)
            # Search acquisition and editorial/typography suitability are
            # deliberately decoupled here: the top-ranked candidate is not
            # presumed to be the final choice. Try a bounded number of the
            # best-ranked candidates in order, and keep the first one whose
            # rendered layout actually passes the safety/typography check --
            # instead of failing outright the moment candidate #1's layout
            # doesn't leave room for the title.
            layout = ""
            last_layout_error = "" if ranked else "No matching photograph was found."
            for score, photo, query in ranked[:4]:
                raw = download_pexels_original(photo)
                source = _store_source_bytes(
                    payload,
                    raw,
                    source_type="pexels",
                    filename=f"pexels-{photo.get('photo_id') or 'cover'}.jpg",
                    license_note=str(photo.get("license_note") or "Pexels License: free to use."),
                    project_id=payload.get("_project_id"),
                )
                source["pexels"] = {
                    "photo_id": str(photo.get("photo_id") or ""),
                    "photographer": str(photo.get("photographer") or ""),
                    "page_url": str(photo.get("page_url") or ""),
                    "sha256": source.get("sha256"),
                    "artifact_id": package_id,
                    "project_id": payload.get("_project_id"),
                    "query": query,
                }
                source["query"] = query
                payload = _activate_source(payload, source, project_id=payload.get("_project_id"))
                layout = _first_passing_layout(payload.get("cover_design"))
                if layout:
                    break
                last_layout_error = "No safe cover layout passed quality checks for this candidate."
            if not layout:
                # Stock photography could not fulfill the cover brief. Fall
                # back to an original AI-generated candidate -- the
                # professional fallback, not a lesser option -- gated by the
                # same project visual budget/authorization as interior
                # visuals, and screened by the same editorial scorer before
                # it's ever treated as a real candidate.
                ai_layout = _generate_ai_cover_candidate(
                    payload, title=title, subtitle=subtitle, fields=fields, package_id=package_id,
                )
                if ai_layout:
                    layout = ai_layout
                else:
                    raise PhotoCoverError(last_layout_error or "No safe cover layout passed quality checks.")
        if fixture_mode():
            layout = _first_passing_layout(payload.get("cover_design"))
            if not layout:
                raise PhotoCoverError("No safe cover layout passed quality checks.")
        payload = select_layout(payload, layout, project_id=payload.get("_project_id"))
        cover = dict(payload.get("cover_design") or {})
        cover["approved"] = False
        cover["next_action"] = ""
        cover["generic_template"] = False
        cover["plain_fallback"] = False
        cover["package_id"] = package_id
        cover["pexels_query"] = queries[0] if queries else ""
        cover["cover_search_query"] = queries[0] if queries else ""
        src = str(cover.get("image_path") or "")
        if src and os.path.isfile(src) and package_id:
            dest_dir = os.path.join(EXPORTS_DIR, package_id)
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, "img_cover.png")
            if os.path.abspath(src) != os.path.abspath(dest):
                shutil.copyfile(src, dest)
            if os.path.isfile(dest):
                cover["image_path"] = dest
        payload["cover_design"] = cover
        payload["cover_search_query"] = queries[0] if queries else ""
        return payload
    except Exception as exc:  # noqa: BLE001
        error = customer_pexels_message(exc) if isinstance(exc, PexelsError) else str(exc)
        if previous and (previous.get("selected_layout") or previous.get("source")):
            payload["cover_design"] = previous
            payload["cover_error"] = error
            return payload
        payload["cover_design"] = {
            "workflow": "photo_backed",
            "photo_backed": True,
            "title": title,
            "subtitle": subtitle,
            "author": author,
            "package_id": package_id,
            "selected_layout": None,
            "source": None,
            "approved": False,
            "generic_template": False,
            "plain_fallback": False,
            "error": error,
        }
        payload["cover_error"] = error
        return payload


def _write_sellable_pdf(result: dict, *, title: str, subtitle: str, author: str, content: str) -> dict:
    from services.pdf_export import generate_product_pdf, _sanitize_pdf_local_link_uris

    cover = result.get("cover_design") if isinstance(result.get("cover_design"), dict) else {}
    package_id = str(result.get("package_id") or "")
    pdir = str((result.get("export_files") or {}).get("dir") or os.path.join(EXPORTS_DIR, package_id))
    os.makedirs(pdir, exist_ok=True)
    html = str(result.get("preview_html") or "")
    try:
        pdf = generate_product_pdf(
            doc_html=html,
            title=title,
            subtitle=subtitle,
            author=author,
            content=content,
            summary=str(result.get("product_summary") or ""),
            visual_plan=result.get("visual_plan"),
            preview_source="visual",
            cover_design=cover,
            topic=str((result.get("fields") or {}).get("topic") or title),
        )
        pdf = _sanitize_pdf_local_link_uris(pdf)
        from services.ebook_qa_validator import validate_ebook_pdf

        qa = validate_ebook_pdf(pdf)
        result["ebook_pdf_qa_passed"] = bool(qa.passed)
        result["ebook_pdf_qa_errors"] = list(qa.errors or [])
        if not qa.passed:
            result["export_ready"] = False
            blockers = list(result.get("completion_blockers") or [])
            for err in qa.errors:
                if err not in blockers:
                    blockers.append(err)
            result["completion_blockers"] = blockers
    except Exception:
        result["pdf_error"] = "PDF could not be built from the saved manuscript and cover."
        return result
    pdf_path = os.path.join(pdir, "ebook.pdf")
    with open(pdf_path, "wb") as fh:
        fh.write(pdf)
    html_path = os.path.join(pdir, "ebook.html")
    if html:
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(html)
    zip_path = os.path.join(pdir, "package.zip")
    customer_names = {"ebook.pdf", "ebook.html", "ebook.txt", "product_summary.txt"}
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in os.listdir(pdir):
            if name == "package.zip":
                continue
            if name not in customer_names:
                continue
            zf.write(os.path.join(pdir, name), name)
    files = dict(result.get("export_files") or {})
    files["ebook.pdf"] = pdf_path
    files["ebook.html"] = html_path
    files["package.zip"] = zip_path
    files["dir"] = pdir
    result["export_files"] = files
    exports = dict(result.get("exports") or {})
    export_files = dict(exports.get("files") or {})
    export_files["pdf"] = {"name": "ebook.pdf", "url": f"/download/{package_id}/ebook.pdf"}
    export_files["zip"] = {"name": "package.zip", "url": f"/download/{package_id}/package.zip"}
    exports["files"] = export_files
    exports["pdf_available"] = True
    result["exports"] = exports
    result["pdf_path"] = pdf_path
    result["_pdf_path"] = pdf_path
    result["pdf_sha256"] = hashlib.sha256(pdf).hexdigest()
    return result


def complete_factory_ebook(
    title: str,
    content_md: str,
    fields: dict | None,
    *,
    keep_cover: dict | None = None,
    force_new_cover: bool = False,
) -> dict[str, Any]:
    """One shared production pipeline for every factory ebook entry point."""
    fields = normalize_ebook_fields(fields, title=title, content=content_md)
    title = fields["ebook_title"]
    author = fields["author_brand"]
    content = fields.pop("_normalized_content")
    if fixture_mode() and "container" in title.lower() and "garden" in title.lower():
        content = sanitize_manuscript(
            container_gardening_manuscript(),
            title=title,
            subtitle=CONTAINER_SUBTITLE,
            author=author,
        )
        fields["subtitle"] = CONTAINER_SUBTITLE
    result = build_ebook_package(title, content, fields)
    result["title"] = title
    result["author"] = author
    result["author_brand"] = author
    result["author_name"] = author
    result["fields"] = fields
    result["content"] = content
    result["ebook"] = content
    result["product_type"] = "ebook"
    result["product_label"] = "Ebook"
    package_id = str(result.get("package_id") or "")
    wrapped = complete_photo_cover(
        {
            "package_id": package_id,
            "artifact_id": package_id,
            "title": title,
            "subtitle": str(result.get("subtitle") or fields.get("subtitle") or ""),
            "author_brand": author,
            "author": author,
            "fields": fields,
            "cover_design": result.get("cover_design"),
        },
        title=title,
        subtitle=str(result.get("subtitle") or fields.get("subtitle") or ""),
        author=author,
        fields=fields,
        package_id=package_id,
        keep_current=keep_cover or result.get("cover_design"),
        force_new=force_new_cover,
    )
    if isinstance(wrapped.get("cover_design"), dict) and wrapped["cover_design"].get("selected_layout"):
        result["cover_design"] = wrapped["cover_design"]
    elif keep_cover:
        result["cover_design"] = keep_cover
    elif isinstance(wrapped.get("cover_design"), dict):
        # No prior cover to fall back to and the photo-backed attempt did not
        # produce a usable layout: surface the honest failure state instead of
        # silently keeping build_ebook_package()'s stale local/generic cover.
        result["cover_design"] = wrapped["cover_design"]
    result["cover_error"] = wrapped.get("cover_error") or ""
    from services.ebook_package import render_preview_html

    result["preview_html"] = render_preview_html(
        title,
        str(result.get("subtitle") or ""),
        content,
        list((result.get("visual_plan") or {}).get("chapters") or []),
        package_id,
        str(result.get("product_summary") or ""),
        result.get("cover_design"),
        topic=str(fields.get("topic") or ""),
    )
    findings = gate_ebook_output(
        title=title,
        author=author,
        manuscript=content,
        html=str(result.get("preview_html") or ""),
    )
    result["contamination"] = findings
    cover = result.get("cover_design") if isinstance(result.get("cover_design"), dict) else {}
    cover_ok = bool(cover.get("selected_layout") and cover.get("source"))
    if cover_ok and not findings:
        result = _write_sellable_pdf(
            result, title=title, subtitle=str(result.get("subtitle") or ""), author=author, content=content
        )
    apply_ebook_readiness(result)
    qr = result.get("quality_result")
    if qr is not None and not isinstance(qr, dict):
        result["quality_result"] = {
            "score": getattr(qr, "score", None),
            "passed": getattr(qr, "passed", None),
        }
    if findings or not cover_ok:
        result["ebook_ready"] = False
        result["export_ready"] = False
        result["pdf_available"] = False
        result["status_label"] = "Needs correction."
        if findings:
            result["next_action"] = "Fix content issues shown in Technical Details"
            result["completion_blockers"] = [row.get("code") for row in findings]
        elif not cover_ok:
            result["next_action"] = result.get("cover_error") or "A professional cover could not be created yet."
        result["customer_error"] = result.get("cover_error") or (
            findings[0]["message"] if findings else ""
        )
    else:
        result["status_label"] = "Ebook ready"
        result["next_action"] = ""
        result["stage"] = "product_generated"
        result["status"] = "export_ready"
        result["quality_blocking"] = False
    result["save_disabled_reason"] = ""
    if not str(title).strip():
        result["save_disabled_reason"] = "Save is unavailable until the title is valid."
    return result


def regenerate_factory_cover(data: dict) -> dict[str, Any]:
    payload = dict(data or {})
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    title = normalize_book_title(payload.get("title") or fields.get("ebook_title") or "")
    author = normalize_author(payload.get("author_brand"), payload.get("author"), fields.get("author_brand"))
    current = payload.get("cover_design") if isinstance(payload.get("cover_design"), dict) else None
    package_id = str(payload.get("package_id") or "")
    updated = complete_photo_cover(
        payload,
        title=title,
        subtitle=str(payload.get("subtitle") or ""),
        author=author,
        fields=fields,
        package_id=package_id,
        keep_current=current,
        force_new=True,
    )
    if updated.get("cover_design") and updated["cover_design"].get("selected_layout"):
        new_sha = str(((updated["cover_design"].get("source") or {}).get("sha256")) or "")
        old_sha = str(((current or {}).get("source") or {}).get("sha256") or "")
        if new_sha and new_sha == old_sha and fixture_mode():
            # Fixture second color path already used force_new; still accept.
            pass
        payload["cover_design"] = updated["cover_design"]
        payload["cover_approved"] = False
        payload["preview_html"] = ""
        from services.ebook_package import render_preview_html

        payload["preview_html"] = render_preview_html(
            title,
            str(payload.get("subtitle") or ""),
            str(payload.get("content") or payload.get("ebook") or ""),
            list((payload.get("visual_plan") or {}).get("chapters") or []),
            package_id,
            str(payload.get("product_summary") or ""),
            payload.get("cover_design"),
            topic=str(fields.get("topic") or ""),
        )
        payload = _write_sellable_pdf(
            payload,
            title=title,
            subtitle=str(payload.get("subtitle") or ""),
            author=author,
            content=str(payload.get("content") or payload.get("ebook") or ""),
        )
        apply_ebook_readiness(payload)
        payload["cover_regenerated"] = True
        payload["message"] = "A new cover candidate is ready for review."
    else:
        payload["cover_design"] = current
        payload["cover_regenerated"] = False
        payload["message"] = updated.get("cover_error") or "The current cover was kept."
    return payload


def save_factory_ebook(
    data: dict,
    *,
    name: str,
    project_id: int | None = None,
    user_confirmed: bool = True,
) -> dict[str, Any]:
    """Transactional idempotent Save. Does not regenerate content."""
    import database

    payload = dict(data or {})
    for key in list(payload.keys()):
        if str(key).startswith("_") and key not in {"_pdf_path"}:
            payload.pop(key, None)
    title = normalize_book_title(payload.get("title") or name)
    author = normalize_author(payload.get("author_brand"), payload.get("author"))
    payload["title"] = title
    payload["author"] = author
    payload["author_brand"] = author
    payload["product_type"] = "ebook"
    payload["user_confirmed_save"] = bool(user_confirmed)
    payload["stage"] = payload.get("stage") or "product_generated"
    if payload.get("ebook_ready"):
        payload["status"] = "export_ready"
        payload["quality_blocking"] = False
    findings = gate_ebook_output(
        title=title,
        author=author,
        manuscript=str(payload.get("content") or payload.get("ebook") or ""),
        html=str(payload.get("preview_html") or ""),
    )
    apply_ebook_readiness(payload)
    pdf_path = _resolve_pdf_path(payload)
    if pdf_path and os.path.isfile(pdf_path):
        payload["pdf_path"] = pdf_path
        payload["_pdf_path"] = pdf_path
        payload["pdf_available"] = True
    if payload.get("ebook_ready"):
        payload["status"] = "export_ready"
        payload["stage"] = payload.get("stage") or "product_generated"
        payload["quality_blocking"] = False
        payload["user_confirmed_save"] = bool(user_confirmed)
        payload["hidden_from_customer"] = False
    if findings:
        payload["contamination"] = findings
        payload["ebook_ready"] = False
        payload["export_ready"] = False
        raise ValueError(findings[0].get("message") or "Save is unavailable until content issues are fixed.")
    if not payload.get("ebook_ready"):
        raise ValueError(
            payload.get("save_disabled_reason")
            or payload.get("customer_error")
            or payload.get("next_action")
            or "Save is unavailable until the cover, visuals, and preview pass."
        )
    display_name = title or normalize_book_title(name) or "Ebook"
    if project_id:
        existing = database.get_project(int(project_id))
        if not existing:
            raise ValueError("Project not found.")
        saved = database.update_project(
            int(project_id),
            display_name,
            payload,
            user_saved=True,
            user_confirmed_save=user_confirmed,
        )
    else:
        saved = database.create_project(
            display_name,
            "ebook",
            payload,
            user_saved=True,
            system_test=False,
            temporary=False,
            user_confirmed_save=user_confirmed,
        )
    return {
        "ok": True,
        "message": SAVE_SUCCESS,
        "project": saved,
        "id": saved.get("id") if saved else None,
        "project_id": saved.get("id") if saved else None,
    }
