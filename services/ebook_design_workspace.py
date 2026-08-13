"""Ebook Project rail actions for Visuals → Cover → Design → Preview → Preflight → Export.

Server-authoritative. UI cannot invent PASS or Export Ready. Zero paid calls.
"""
from __future__ import annotations

from typing import Any

from services.ebook_design_export import (
    generate_workspace_cover,
    render_designed_bundle,
    select_theme,
    theme_catalog_payload,
    visual_manifest_from_manuscript,
)
from services.ebook_design_preflight import PREFLIGHT_PASS, run_design_preflight, verify_export_bytes
from services.ebook_design_spec import design_is_stale
from services.ebook_manuscript_engine import QUALITY_PASS, validate_manuscript_quality
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript
from services.ebook_project_workspace import (
    RAIL_LABELS,
    STATUS_APPROVED,
    STATUS_AWAITING,
    STATUS_NEEDS_CORRECTION,
    STATUS_NOT_STARTED,
    _append_history,
    _recompute_next_action,
    approve_stage,
    assert_can_run_stage,
    build_acceptance_project_data,
    invalidate_after,
    is_approved,
    manuscript_digest,
    set_stage_status,
    stage_status,
    sync_document_from_workspace,
)


def _ws(data: dict) -> dict:
    from services.ebook_project_workspace import ensure_workspace

    data = ensure_workspace(data)
    return data["ebook_workspace"]


def _require_quality(data: dict) -> None:
    md = str(data.get("content") or data.get("ebook") or "")
    quality = validate_manuscript_quality(data, manuscript_md=md)
    if quality.status != QUALITY_PASS:
        raise ValueError("Only a manuscript-quality PASS may enter design, cover, preview, or export.")


def approve_visuals_local(data: dict) -> dict:
    """Approve manuscript-derived visual slots. No paid image generation."""
    ws = _ws(data)
    assert_can_run_stage(ws, "visuals")
    _require_quality(data)
    if not is_approved(ws, "manuscript"):
        raise ValueError("Approve the manuscript before visuals.")
    md = str(data.get("content") or data.get("ebook") or "")
    manifest = visual_manifest_from_manuscript(md)
    data["ebook_visual_manifest"] = manifest
    data["ebook_visual_manifest_digest"] = manifest["digest"]
    set_stage_status(ws, "visuals", STATUS_APPROVED, note="Manuscript-derived visuals; no paid images")
    _append_history(ws, "approve", stage="visuals", paid_images=False)
    _recompute_next_action(ws)
    return sync_document_from_workspace(data)


def generate_and_stage_cover(data: dict) -> dict:
    ws = _ws(data)
    assert_can_run_stage(ws, "cover")
    _require_quality(data)
    if not is_approved(ws, "visuals"):
        raise ValueError("Approve visuals before generating a cover.")
    data = generate_workspace_cover(data)
    data["ebook_design"] = None
    data["ebook_design_digest"] = ""
    data["ebook_preview_html"] = ""
    data["ebook_export_identity"] = None
    data["ebook_design_preflight"] = None
    data["export_ready"] = False
    set_stage_status(ws, "cover", STATUS_AWAITING, note="Local cover generated; awaiting approval")
    invalidate_after(ws, "cover", reason="Cover regenerated")
    _append_history(ws, "generate_cover", local=True)
    _recompute_next_action(ws)
    return sync_document_from_workspace(data)


def reject_cover(data: dict) -> dict:
    ws = _ws(data)
    data["cover_design"] = None
    data["ebook_cover_digest"] = ""
    set_stage_status(ws, "cover", STATUS_NEEDS_CORRECTION, note="Cover rejected")
    invalidate_after(ws, "cover", reason="Cover rejected")
    _append_history(ws, "reject_cover")
    _recompute_next_action(ws)
    return sync_document_from_workspace(data)


def select_and_stage_theme(data: dict, theme_id: str) -> dict:
    ws = _ws(data)
    assert_can_run_stage(ws, "design")
    _require_quality(data)
    if not is_approved(ws, "cover"):
        raise ValueError("Approve the cover before selecting a design theme.")
    data = select_theme(data, theme_id)
    set_stage_status(ws, "design", STATUS_AWAITING, note=f"Theme {theme_id} selected")
    cleared = invalidate_after(ws, "design", reason="Theme selected")
    data = _clear_export_fields(data, cleared)
    _append_history(ws, "select_theme", theme_id=theme_id)
    _recompute_next_action(ws)
    return sync_document_from_workspace(data)


def _clear_export_fields(data: dict, cleared: list[str]) -> dict:
    if "preview" in cleared or "preflight" in cleared or "export" in cleared:
        data["ebook_preview_html"] = ""
        data["ebook_export_identity"] = None
        data["ebook_design_preflight"] = None
        data["export_ready"] = False
        data["release_status"] = ""
    if "design" in cleared:
        data["ebook_design"] = None
        data["ebook_design_digest"] = ""
    return data


def build_preview(data: dict) -> dict:
    ws = _ws(data)
    assert_can_run_stage(ws, "preview")
    _require_quality(data)
    if not is_approved(ws, "design"):
        raise ValueError("Approve the design before building preview.")
    bundle = render_designed_bundle(data)
    set_stage_status(ws, "preview", STATUS_AWAITING, note="Preview rendered from approved manuscript")
    _append_history(ws, "preview", pdf_sha256=(bundle.get("identity") or {}).get("pdf_sha256"))
    _recompute_next_action(ws)
    data["_preview_page_count"] = bundle.get("preflight", {}).get("page_count")
    return sync_document_from_workspace(data)


def run_preflight_stage(data: dict) -> dict:
    ws = _ws(data)
    assert_can_run_stage(ws, "preflight")
    _require_quality(data)
    if not is_approved(ws, "preview"):
        raise ValueError("Approve preview before preflight.")
    html = str(data.get("ebook_preview_html") or data.get("preview_html") or "")
    report = run_design_preflight(
        data,
        html=html,
        design=data.get("ebook_design"),
        preview_digest=str((data.get("ebook_export_identity") or {}).get("preview_digest") or ""),
        pdf_bytes=b"",
    )
    # Re-render so PDF/ZIP identity is included
    bundle = render_designed_bundle(data)
    report_dict = bundle["preflight"]
    data["ebook_design_preflight"] = report_dict
    if report_dict.get("status") == PREFLIGHT_PASS:
        set_stage_status(ws, "preflight", STATUS_AWAITING, note="Preflight PASS")
    else:
        set_stage_status(
            ws,
            "preflight",
            STATUS_NEEDS_CORRECTION,
            note=f"Preflight {report_dict.get('status')}",
        )
        data["export_ready"] = False
    _append_history(ws, "preflight", status=report_dict.get("status"))
    _recompute_next_action(ws)
    return sync_document_from_workspace(data)


def rewind_to_stage(data: dict, stage: str) -> dict:
    """Open an earlier stage without discarding approved manuscript bytes."""
    from services.ebook_project_workspace import RAIL_STAGES, ensure_workspace

    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    if stage not in RAIL_STAGES:
        raise ValueError(f"Unknown stage: {stage}")
    md_before = str(data.get("content") or data.get("ebook") or "")
    digest_before = manuscript_digest(data)
    ws["current_stage"] = stage
    _append_history(ws, "rewind", stage=stage)
    _recompute_next_action(ws)
    if str(data.get("content") or data.get("ebook") or "") != md_before:
        raise RuntimeError("Rewind mutated manuscript content.")
    if manuscript_digest(data) != digest_before:
        raise RuntimeError("Rewind mutated manuscript digest.")
    return sync_document_from_workspace(data)


def build_design_ready_fixture_data() -> dict[str, Any]:
    """Isolated quality-PASS fixture with local cover + Studio Clean design. Not project #2472."""
    data = build_acceptance_project_data()
    data["acceptance_marker"] = "ebook_design_fixture_pass_b"
    ws = data["ebook_workspace"]
    ws["marker"] = "ebook_design_fixture_pass_b"
    md = build_event_photo_strong_manuscript()
    data["content"] = md
    data["ebook"] = md
    set_stage_status(ws, "manuscript", STATUS_AWAITING)
    data = approve_stage(data, "manuscript")
    data = approve_visuals_local(data)
    data = generate_and_stage_cover(data)
    data = approve_stage(data, "cover")
    data = select_and_stage_theme(data, "studio_clean")
    data = approve_stage(data, "design")
    data = build_preview(data)
    data = approve_stage(data, "preview")
    data = run_preflight_stage(data)
    if stage_status(data["ebook_workspace"], "preflight") == STATUS_AWAITING:
        data = approve_stage(data, "preflight")
    return data


def design_public_view(data: dict) -> dict[str, Any]:
    catalog = theme_catalog_payload()
    pre = data.get("ebook_design_preflight") if isinstance(data.get("ebook_design_preflight"), dict) else {}
    identity = data.get("ebook_export_identity") if isinstance(data.get("ebook_export_identity"), dict) else {}
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    design = data.get("ebook_design") if isinstance(data.get("ebook_design"), dict) else {}
    return {
        "themes": catalog["themes"],
        "theme_samples": catalog["samples"],
        "selected_theme": design.get("theme_id") or "",
        "design_digest": design.get("digest") or "",
        "cover": {
            "title": cover.get("title"),
            "subtitle": cover.get("subtitle"),
            "author": cover.get("author"),
            "theme": cover.get("theme"),
            "digest": cover.get("cover_digest"),
            "image_path": cover.get("image_path"),
            "local_generated": cover.get("local_generated") is True,
        },
        "visual_manifest": data.get("ebook_visual_manifest") or {},
        "preflight": pre,
        "identity": identity,
        "export_ready": data.get("export_ready") is True and str(pre.get("status") or "").upper() == PREFLIGHT_PASS,
        "preview_available": bool(data.get("ebook_preview_html") or data.get("preview_html")),
        "stale_design": design_is_stale(design, manuscript_digest=manuscript_digest(data)),
        "paid_calls": False,
    }
