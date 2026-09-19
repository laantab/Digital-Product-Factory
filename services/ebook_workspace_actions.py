"""One copy of each step-by-step action — v1.8.1.

WHY THIS MODULE EXISTS
----------------------
Until v1.8.1 the work behind every button on the step-by-step ebook screen
lived inside a Flask route in `app.py`. That is why the website was still
writing books after v1.8.0 moved the one-click build to the builder: the
work was not reachable from anywhere except a web request.

Moving it here makes it callable from both machines. The route calls it in
inline mode; the builder calls it in workflow mode, having read what the
customer asked for off the durable job row. There is exactly ONE copy of
each action, which is what `CLAUDE.md` asks for -- "the same logic is
sometimes implemented twice (Python and JS); grep for the second copy" --
and it is why a fix to a visual action cannot now be applied on one machine
and forgotten on the other.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not change the ebook engine. Every function called below is the
same function the route called before, with the same arguments in the same
order. Stages, gates, attempt ceilings, spend caps, artifact-state checks
and checkpoints are untouched. v1.8.1 changes WHERE the work runs, not what
it does -- so a customer's book comes out identical, and the existing suites
pass unmodified.

It holds no Flask. No `request`, no `jsonify`, no `abort`. That is what lets
the builder -- which has no request context at all -- call it.

VALIDATION STAYS IN THE ROUTE
-----------------------------
The confirmation token, the spend authorisation, the expected artifact id
and revision, the outline digest and the artifact-state mutation check are
the customer's decision and the spend gate. They are checked in the route,
before anything is handed off, so an unauthorised or stale request is still
refused with exactly the error it gets today and never starts a task.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class UnknownAction(ValueError):
    """The recorded action is not one this module performs."""


# ---------------------------------------------------------------------------
# Visuals
# ---------------------------------------------------------------------------

def visuals(data: dict, payload: dict) -> tuple[dict, str]:
    """Prepare, replace, accept or approve the book's photographs.

    Moved verbatim from the `/ebook-workspace/<id>/visuals` route. The
    branches, their aliases and their messages are unchanged.
    """
    from services.ebook_design_workspace import approve_visuals_local, prepare_visuals_local
    from services.ebook_project_workspace import is_approved as _is_approved

    action = str(payload.get("action") or "prepare").strip().lower()

    if action == "approve":
        return approve_visuals_local(data), "Visuals approved."

    if action in {"replace", "replace-photo"}:
        from services.ebook_visual_pipeline import replace_photo_aid

        data = replace_photo_aid(
            data,
            str(payload.get("visual_id") or ""),
            local_path=str(payload.get("local_path") or ""),
            mode=str(payload.get("mode") or ""),
        )
        return data, "Replacement photograph staged for review. Visuals are not approved."

    if action in {"generate-ai", "ai-alternative"}:
        from services.ebook_visual_pipeline import replace_photo_aid

        data = replace_photo_aid(data, str(payload.get("visual_id") or ""), mode="ai")
        return data, "A custom image was prepared for review. Visuals are not approved."

    if action == "retry-automatic":
        ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
        try:
            preserve = (_is_approved(ws, "cover") or _is_approved(ws, "design")
                        or _is_approved(ws, "preview"))
        except Exception:                              # noqa: BLE001
            preserve = False
        data = prepare_visuals_local(data, preserve_downstream=preserve)
        return data, "Automatic visual retry finished. Visuals are not approved."

    if action in {"accept-photo", "accept"}:
        from services.ebook_visual_pipeline import accept_photo_aid

        data = accept_photo_aid(data, str(payload.get("visual_id") or ""))
        return data, "Photograph accepted for this brief. Visuals are not approved."

    if action in {"view-full-size", "seen-full-size"}:
        from services.ebook_visual_pipeline import mark_photo_full_size_viewed

        data = mark_photo_full_size_viewed(data, str(payload.get("visual_id") or ""))
        return data, "Full-size preview recorded."

    ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
    preserve = (_is_approved(ws, "cover") or _is_approved(ws, "design")
                or _is_approved(ws, "preview"))
    data = prepare_visuals_local(data, preserve_downstream=preserve)
    return data, "Visuals ready for review."


#: Visual actions that only record a decision. They are instant and make no
#: paid call, so they run in the web process even in workflow mode: sending
#: "I have looked at this photograph" to a builder would mean starting an
#: instance to write one boolean, and the customer waiting for it.
VISUAL_LIGHT_ACTIONS = frozenset({
    "approve", "accept", "accept-photo", "view-full-size", "seen-full-size",
})


# ---------------------------------------------------------------------------
# Cover
# ---------------------------------------------------------------------------

def cover(data: dict, payload: dict, *, project_id: int) -> tuple[dict, str]:
    """Photo-backed cover actions. Moved verbatim from the cover route."""
    from services.ebook_design_workspace import reject_cover, stage_photo_cover
    from services.ebook_pexels import search_pexels
    from services.ebook_photo_cover import (
        PhotoCoverError,
        apply_editor,
        attach_pexels,
        clear_layout_selection,
        select_layout,
    )

    action = str(payload.get("action") or "").strip().lower()

    if action == "fixture":
        from services.external_calls import ebook_fixture_mode

        if not ebook_fixture_mode():
            raise UnknownAction("This action is not available.")
        from services.ebook_customer_path import _first_passing_layout, _fixture_jpeg
        from services.ebook_photo_cover import _activate_source, _store_source_bytes

        raw = _fixture_jpeg((36, 92, 48), seed=str(payload.get("seed") or "cover-a"))
        source = _store_source_bytes(
            data, raw, source_type="local_licensed", filename="cover-fixture.jpg",
            license_note="Deterministic local fixture photograph. Not for sale.",
            project_id=project_id,
        )
        data = _activate_source(data, source, project_id=project_id)
        layout = _first_passing_layout(data.get("cover_design"))
        if not layout:
            raise PhotoCoverError("No safe cover layout passed quality checks.")
        data = select_layout(data, layout, project_id=project_id)
        return stage_photo_cover(data, project_id=project_id), "Cover staged."

    if action == "reject":
        return reject_cover(data), "Cover rejected."

    if action == "pexels-search":
        prior_cover = data.get("cover_design")
        result = search_pexels(str(payload.get("query") or ""),
                               page=int(payload.get("page") or 1))
        ws = data.setdefault("ebook_workspace", {})
        ws["pexels_cache"] = {
            "query": result.get("query"), "page": result.get("page"),
            "photos": result.get("photos"), "next_page": result.get("next_page"),
        }
        if prior_cover is not None:
            data["cover_design"] = prior_cover
        return data, "Photograph choices ready."

    if action == "pexels-select":
        data = attach_pexels(data, str(payload.get("photo_id") or ""), project_id=project_id)
        return stage_photo_cover(data, project_id=project_id), "Cover staged."

    if action == "editor":
        data = apply_editor(data, dict(payload.get("editor") or {}), project_id=project_id)
        return stage_photo_cover(data, project_id=project_id), "Cover staged."

    if action == "select":
        data = select_layout(data, str(payload.get("layout_id") or ""), project_id=project_id)
        return stage_photo_cover(data, project_id=project_id), "Cover staged."

    if action == "deselect":
        return clear_layout_selection(data), "Layout cleared."

    if action in {"generate", "licensed"}:
        raise UnknownAction(
            "Vector covers are disabled. Search Pexels or upload your own photograph.")

    raise UnknownAction("Unknown cover action.")


#: Cover actions that only record a decision, as above.
COVER_LIGHT_ACTIONS = frozenset({"reject", "deselect"})


def cover_image(data: dict, payload: dict, *, project_id: int) -> tuple[dict, str]:
    """Attach an uploaded cover photograph and re-render the layouts.

    THE BYTES TRAVEL THROUGH STORAGE, NOT THE DISK (v1.8.1). The upload
    arrives at the website; the work happens on the builder; the two share no
    filesystem. The route puts the raw image in the storage driver and
    records its key, and this reads it back from there. Passing a local path
    would be a file the builder cannot open.
    """
    from services.ebook_design_workspace import stage_photo_cover
    from services.ebook_photo_cover import attach_upload

    raw = payload.get("_raw_bytes")
    if raw is None:
        key = str(payload.get("storage_key") or "")
        if not key:
            raise UnknownAction("No uploaded image was recorded.")
        from services.storage import get_storage

        raw = get_storage().get(key)

    data = attach_upload(
        data, raw,
        filename=str(payload.get("filename") or "upload.png"),
        license_note=str(payload.get("license_note") or ""),
        project_id=project_id,
        owned=bool(payload.get("owned")),
    )
    data = stage_photo_cover(data, project_id=project_id)
    source = ((data.get("cover_design") or {}).get("source") or {})
    filename = str(source.get("filename") or payload.get("filename") or "photograph")
    return data, f"Uploaded {filename}. Creating cover choices."


# ---------------------------------------------------------------------------
# Design, preview, preflight
# ---------------------------------------------------------------------------

def design(data: dict, payload: dict) -> tuple[dict, str]:
    from services.ebook_design_workspace import select_and_stage_theme

    return select_and_stage_theme(data, str(payload.get("theme_id") or "").strip()), "Design ready."


def preview(data: dict, payload: dict) -> tuple[dict, str]:
    from services.ebook_design_workspace import build_preview

    return build_preview(data), "Preview ready."


def preflight(data: dict, payload: dict) -> tuple[dict, str]:
    from services.ebook_design_workspace import run_preflight_stage

    return run_preflight_stage(data), "Quality check finished."


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

#: route path -> callable. Manuscript generation and correction are NOT here:
#: they are stages the orchestrator already owns (`_run_manuscript`), so the
#: builder runs them by advancing the build rather than by calling a function
#: of its own. Two ways to write a chapter is exactly the duplication this
#: module exists to remove.
_HANDLERS = {
    "/ebook-workspace/<int:project_id>/visuals":
        lambda d, p, pid: visuals(d, p),
    "/ebook-workspace/<int:project_id>/cover":
        lambda d, p, pid: cover(d, p, project_id=pid),
    "/ebook-workspace/<int:project_id>/cover-image":
        lambda d, p, pid: cover_image(d, p, project_id=pid),
    "/ebook-workspace/<int:project_id>/design":
        lambda d, p, pid: design(d, p),
    "/ebook-workspace/<int:project_id>/preview":
        lambda d, p, pid: preview(d, p),
    "/ebook-workspace/<int:project_id>/preflight":
        lambda d, p, pid: preflight(d, p),
}


def handles(route: str) -> bool:
    """Whether this module can perform the action recorded for `route`."""
    return str(route) in _HANDLERS


def perform(data: dict, *, project_id: int, route: str,
            payload: dict | None = None) -> tuple[dict, str]:
    """Run one recorded workspace action. Returns (data, customer message)."""
    handler = _HANDLERS.get(str(route))
    if handler is None:
        raise UnknownAction(f"no handler for {route}")
    data = dict(data)
    data["_project_id"] = int(project_id)
    return handler(data, dict(payload or {}), int(project_id))


def is_light(route: str, action: str) -> bool:
    """Whether this particular request is bookkeeping rather than real work.

    A heavy ROUTE can carry a light REQUEST. Approving visuals the customer
    has already looked at writes one field; starting an instance for it would
    make the screen slower than it is today for no benefit. Classifying the
    route by its worst case (see services/jobs/route_registry.py) is what
    keeps the dangerous cases safe; this is what keeps the harmless ones fast.
    """
    action = str(action or "").strip().lower()
    route = str(route)
    if route.endswith("/visuals"):
        return action in VISUAL_LIGHT_ACTIONS
    if route.endswith("/cover"):
        return action in COVER_LIGHT_ACTIONS
    return False
