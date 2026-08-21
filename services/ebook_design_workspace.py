"""Ebook Project rail actions for Visuals → Cover → Design → Preview → Preflight → Export.

Server-authoritative. UI cannot invent PASS or Export Ready. Zero paid calls.
"""
from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Any

from services.ebook_design_export import (
    generate_workspace_cover,
    render_designed_bundle,
    select_theme,
    theme_catalog_payload,
)
from services.ebook_design_preflight import PREFLIGHT_PASS, run_design_preflight, verify_export_bytes
from services.ebook_design_spec import EbookDesign, design_is_stale
from services.ebook_manuscript_engine import QUALITY_PASS, validate_manuscript_quality
from services.ebook_manuscript_fixtures import build_event_photo_strong_manuscript
from services.ebook_book_layout import rewrite_bracketed_website_placeholders
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
    preview_opened_matches_current,
    record_preview_opened,
    revoke_unviewed_preview_approval,
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
    """Approve a content-aware visual plan only when local assets are valid."""
    from services.ebook_visual_pipeline import approve_visual_plan

    return approve_visual_plan(data)


def prepare_visuals_local(data: dict, *, preserve_downstream: bool = False) -> dict:
    """Generate or recover local visual assets and leave Visuals awaiting approval."""
    from services.ebook_visual_pipeline import prepare_visuals_for_review

    return prepare_visuals_for_review(data, preserve_downstream=preserve_downstream)


def generate_and_stage_cover(data: dict) -> dict:
    raise ValueError(
        "Vector covers are disabled. Search Pexels or upload your own photograph."
    )


def stage_photo_cover(data: dict, *, project_id: int | None = None) -> dict:
    """Keep the Cover rail awaiting after a photo-backed render. Does not approve."""
    from services.ebook_photo_cover import PhotoCoverError

    ws = _ws(data)
    assert_can_run_stage(ws, "cover")
    _require_quality(data)
    if not is_approved(ws, "visuals"):
        raise ValueError("Approve visuals before generating a cover.")
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None
    if not cover or cover.get("workflow") != "photo_backed":
        raise PhotoCoverError("Search Pexels or upload your own photograph.")
    data["ebook_design"] = None
    data["ebook_design_digest"] = ""
    data["ebook_preview_html"] = ""
    data["ebook_export_identity"] = None
    data["ebook_design_preflight"] = None
    data["export_ready"] = False
    set_stage_status(ws, "cover", STATUS_AWAITING, note="Photo-backed cover awaiting selection")
    invalidate_after(ws, "cover", reason="Cover photograph updated")
    _append_history(ws, "photo_cover", local=True, paid=False)
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


COVER_PREVIEW_UNAVAILABLE = "Cover preview unavailable — approval blocked"
_COVER_DIGEST_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class CoverPreviewUnavailable(ValueError):
    """Read-only cover preview cannot be served."""

    def __init__(self, message: str = COVER_PREVIEW_UNAVAILABLE, status_code: int = 404):
        super().__init__(message)
        self.status_code = int(status_code)


def _cover_file_under_package(path: str, package_id: str) -> str | None:
    from services.ebook_package import EXPORTS_DIR

    if not path or not package_id or not os.path.isfile(path):
        return None
    try:
        real = Path(path).resolve()
        pkg_root = (Path(EXPORTS_DIR) / str(package_id)).resolve()
        real.relative_to(pkg_root)
    except (OSError, ValueError):
        return None
    return str(real)


def verified_cover_preview_asset(
    data: dict,
    *,
    project_id: int | None,
    digest: str,
    render_png: bool = False,
) -> dict[str, Any]:
    """Return stored cover bytes only when project + digest match. Never generates."""
    requested = str(digest or "").strip().lower()
    if not _COVER_DIGEST_RE.match(requested):
        raise CoverPreviewUnavailable(COVER_PREVIEW_UNAVAILABLE, status_code=400)
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None
    if not cover:
        raise CoverPreviewUnavailable()
    stored = str(cover.get("cover_digest") or data.get("ebook_cover_digest") or "").strip().lower()
    if stored != requested:
        raise CoverPreviewUnavailable()
    pkg = str(data.get("package_id") or data.get("artifact_id") or "").strip()
    cover_pkg = str(cover.get("package_id") or "").strip()
    if not pkg or (cover_pkg and cover_pkg != pkg):
        raise CoverPreviewUnavailable()
    pdf_path = _cover_file_under_package(str(cover.get("local_cover_pdf") or ""), pkg)
    if not pdf_path:
        raise CoverPreviewUnavailable()
    with open(pdf_path, "rb") as fh:
        pdf_bytes = fh.read()
    if hashlib.sha256(pdf_bytes).hexdigest() != stored:
        raise CoverPreviewUnavailable()
    png_path = _cover_file_under_package(str(cover.get("image_path") or ""), pkg)
    png_bytes = b""
    if render_png:
        try:
            import fitz

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            try:
                pix = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
                png_bytes = pix.tobytes("png")
            finally:
                doc.close()
        except Exception:
            png_bytes = b""
        if not png_bytes and png_path:
            with open(png_path, "rb") as fh:
                png_bytes = fh.read()
        if not png_bytes:
            raise CoverPreviewUnavailable()
    return {
        "project_id": project_id,
        "digest": stored,
        "package_id": pkg,
        "pdf_path": pdf_path,
        "pdf_bytes": pdf_bytes,
        "png_path": png_path or "",
        "png_bytes": png_bytes,
        "paid_call": False,
        "generated": False,
    }


def cover_preview_public_fields(data: dict, *, project_id: int | None) -> dict[str, Any]:
    """Cheap verification for the workspace JSON. Does not rasterize or generate."""
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    digest = str(cover.get("cover_digest") or "").strip()
    pid = project_id if project_id is not None else data.get("_project_id")
    preview_url = ""
    preview_verified = False
    if pid and digest:
        try:
            verified_cover_preview_asset(
                data, project_id=int(pid), digest=digest, render_png=False
            )
            preview_verified = True
            preview_url = f"/ebook-workspace/{int(pid)}/cover-preview?digest={digest}"
        except (CoverPreviewUnavailable, TypeError, ValueError):
            preview_verified = False
    return {
        "preview_url": preview_url,
        "preview_download_url": f"{preview_url}&download=1" if preview_url else "",
        "preview_verified": preview_verified,
    }


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
        ws = data.get("ebook_workspace")
        if isinstance(ws, dict):
            ws.pop("preview_opened", None)
    if "design" in cleared:
        data["ebook_design"] = None
        data["ebook_design_digest"] = ""
    return data


def rebind_design_to_current_manuscript(data: dict) -> dict:
    """Keep the selected theme and cover binding; update only the manuscript digest."""
    raw = data.get("ebook_design") if isinstance(data.get("ebook_design"), dict) else None
    if not raw:
        raise ValueError("Select a theme before rebinding design to the manuscript.")
    theme_before = str(raw.get("theme_id") or "")
    visual_before = str(raw.get("visual_manifest_digest") or data.get("ebook_visual_manifest_digest") or "")
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    cover_digest = str(cover.get("cover_digest") or raw.get("cover_digest") or "")
    design = EbookDesign.from_dict(raw)
    if str(design.theme_id or "") != theme_before:
        raise RuntimeError("Design rebind must not change the selected theme.")
    design.manuscript_digest = manuscript_digest(data)
    design.cover_digest = cover_digest
    design.visual_manifest_digest = visual_before or design.visual_manifest_digest
    design.recompute_digest()
    if str(design.theme_id or "") != theme_before:
        raise RuntimeError("Design rebind changed the theme.")
    data["ebook_design"] = design.to_dict()
    data["ebook_design_digest"] = design.digest
    data["design_theme"] = design.theme_id
    return data


def apply_url_placeholder_manuscript_repair(data: dict) -> dict:
    """Rewrite bracketed website placeholders and invalidate preview/preflight/export only."""
    from services.quality.artifact_state import assert_content_mutation_allowed

    assert_content_mutation_allowed(data, action="repair unresolved URL placeholders")
    ws = _ws(data)
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    cover_digest_before = str(cover.get("cover_digest") or "")
    photo_sha_before = str((cover.get("source") or {}).get("sha256") or cover.get("image_digest") or "")
    theme_before = str((data.get("ebook_design") or {}).get("theme_id") or data.get("design_theme") or "")
    visual_before = str(data.get("ebook_visual_manifest_digest") or "")
    title_before = (
        str(data.get("title") or ""),
        str(data.get("subtitle") or ""),
        str(data.get("author_brand") or ws.get("author") or ""),
    )
    spent_before = (ws.get("paid_call_ledger") or {}).get("spent_usd")
    layout_before = str(cover.get("selected_layout") or "")

    md = str(data.get("content") or data.get("ebook") or "")
    new_md, replacements = rewrite_bracketed_website_placeholders(md)
    if not replacements:
        raise ValueError("No bracketed website placeholder sentences were found to rewrite.")
    data["content"] = new_md
    data["ebook"] = new_md
    if isinstance(data.get("ebook_document"), dict):
        data["ebook_document"]["manuscript_md"] = new_md
    data["_placeholder_sentence_rewrites"] = replacements

    data = revoke_unviewed_preview_approval(data)
    ws = _ws(data)
    ws.pop("preview_opened", None)
    cleared = invalidate_after(
        ws, "design", reason="Manuscript URL-placeholder and blank-page correction"
    )
    data = _clear_export_fields(data, cleared or ["preview", "preflight", "export"])
    data["export_ready"] = False
    data["release_status"] = ""
    data = sync_document_from_workspace(data)
    data = rebind_design_to_current_manuscript(data)

    cover_after = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    if str(cover_after.get("cover_digest") or "") != cover_digest_before:
        raise RuntimeError("Placeholder repair mutated the approved cover digest.")
    if str((cover_after.get("source") or {}).get("sha256") or cover_after.get("image_digest") or "") != photo_sha_before:
        raise RuntimeError("Placeholder repair mutated the selected photograph.")
    if str((data.get("ebook_design") or {}).get("theme_id") or "") != theme_before:
        raise RuntimeError("Placeholder repair mutated the selected design theme.")
    if str(data.get("ebook_visual_manifest_digest") or "") != visual_before:
        raise RuntimeError("Placeholder repair mutated the visual manifest.")
    if (
        str(data.get("title") or ""),
        str(data.get("subtitle") or ""),
        str(data.get("author_brand") or (_ws(data).get("author") or "")),
    ) != title_before:
        raise RuntimeError("Placeholder repair mutated title, subtitle, or author.")
    if str(cover_after.get("selected_layout") or "") != layout_before:
        raise RuntimeError("Placeholder repair mutated the selected cover layout.")
    if (_ws(data).get("paid_call_ledger") or {}).get("spent_usd") != spent_before:
        raise RuntimeError("Placeholder repair mutated spend.")
    return data


def apply_customer_facing_manuscript_repair(data: dict) -> dict:
    """Sanitize leaked production language and invalidate preview/preflight/export only."""
    from services.ebook_customer_facing import sanitize_customer_manuscript
    from services.quality.artifact_state import assert_content_mutation_allowed

    assert_content_mutation_allowed(data, action="repair customer-facing manuscript defects")
    ws = _ws(data)
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    cover_digest_before = str(cover.get("cover_digest") or "")
    photo_sha_before = str((cover.get("source") or {}).get("sha256") or cover.get("image_digest") or "")
    theme_before = str((data.get("ebook_design") or {}).get("theme_id") or data.get("design_theme") or "")
    visual_before = str(data.get("ebook_visual_manifest_digest") or "")
    title_before = (
        str(data.get("title") or ""),
        str(data.get("subtitle") or ""),
        str(data.get("author_brand") or ws.get("author") or ""),
    )
    spent_before = (ws.get("paid_call_ledger") or {}).get("spent_usd")
    layout_before = str(cover.get("selected_layout") or "")

    md = str(data.get("content") or data.get("ebook") or "")
    new_md, ph_replacements = rewrite_bracketed_website_placeholders(md)
    new_md, report = sanitize_customer_manuscript(new_md)
    data["content"] = new_md
    data["ebook"] = new_md
    if isinstance(data.get("ebook_document"), dict):
        data["ebook_document"]["manuscript_md"] = new_md
    data["_customer_facing_repair"] = report
    if ph_replacements:
        data["_placeholder_sentence_rewrites"] = ph_replacements

    data = revoke_unviewed_preview_approval(data)
    ws = _ws(data)
    ws.pop("preview_opened", None)
    cleared = invalidate_after(
        ws, "design", reason="Customer-facing manuscript and renderer correction"
    )
    data = _clear_export_fields(data, cleared or ["preview", "preflight", "export"])
    data["export_ready"] = False
    data["release_status"] = ""
    data = sync_document_from_workspace(data)
    data = rebind_design_to_current_manuscript(data)

    cover_after = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    if str(cover_after.get("cover_digest") or "") != cover_digest_before:
        raise RuntimeError("Customer-facing repair mutated the approved cover digest.")
    if str((cover_after.get("source") or {}).get("sha256") or cover_after.get("image_digest") or "") != photo_sha_before:
        raise RuntimeError("Customer-facing repair mutated the selected photograph.")
    if str((data.get("ebook_design") or {}).get("theme_id") or "") != theme_before:
        raise RuntimeError("Customer-facing repair mutated the selected design theme.")
    if str(data.get("ebook_visual_manifest_digest") or "") != visual_before:
        raise RuntimeError("Customer-facing repair mutated the visual manifest.")
    if (
        str(data.get("title") or ""),
        str(data.get("subtitle") or ""),
        str(data.get("author_brand") or (_ws(data).get("author") or "")),
    ) != title_before:
        raise RuntimeError("Customer-facing repair mutated title, subtitle, or author.")
    if str(cover_after.get("selected_layout") or "") != layout_before:
        raise RuntimeError("Customer-facing repair mutated the selected cover layout.")
    if (_ws(data).get("paid_call_ledger") or {}).get("spent_usd") != spent_before:
        raise RuntimeError("Customer-facing repair mutated spend.")
    return data


def repair_and_rebuild_preview_for_customer_facing(data: dict) -> dict:
    """Sanitize customer-facing defects, then rebuild preview without approving it."""
    data = apply_customer_facing_manuscript_repair(data)
    data = build_preview(data)
    data["export_ready"] = False
    return data


def repair_and_rebuild_preview_for_url_placeholders(data: dict) -> dict:
    """Apply the placeholder rewrite, then rebuild preview without approving it."""
    data = apply_url_placeholder_manuscript_repair(data)
    data = build_preview(data)
    data["export_ready"] = False
    return data


def build_preview(data: dict) -> dict:
    ws = _ws(data)
    assert_can_run_stage(ws, "preview")
    _require_quality(data)
    if not is_approved(ws, "design"):
        raise ValueError("Approve the design before building preview.")
    from services.ebook_visual_pipeline import visuals_are_ready

    if not is_approved(ws, "visuals") or not visuals_are_ready(data):
        raise ValueError("Approve visuals with valid local assets before building preview.")
    ws.pop("preview_opened", None)
    plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None
    manifest = data.get("ebook_visual_manifest") if isinstance(data.get("ebook_visual_manifest"), dict) else None
    contact = data.get("ebook_visual_contact_sheet")
    bundle = render_designed_bundle(data)
    set_stage_status(ws, "preview", STATUS_AWAITING, note="Preview rendered from approved manuscript")
    _append_history(ws, "preview", pdf_sha256=(bundle.get("identity") or {}).get("pdf_sha256"))
    _recompute_next_action(ws)
    data["_preview_page_count"] = bundle.get("preflight", {}).get("page_count")
    data["export_ready"] = False
    data = sync_document_from_workspace(data)
    if isinstance(plan, dict):
        data["visual_plan"] = plan
    if isinstance(manifest, dict):
        data["ebook_visual_manifest"] = manifest
        data["ebook_visual_manifest_digest"] = manifest.get("digest") or data.get("ebook_visual_manifest_digest")
    if contact:
        data["ebook_visual_contact_sheet"] = contact
    return data


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
    from services.ebook_photo_cover import attach_licensed, select_layout

    data = attach_licensed(data, "event_reception_night", project_id=None)
    data = select_layout(data, "printed_moment", project_id=None)
    data = approve_stage(data, "cover")
    data = select_and_stage_theme(data, "studio_clean")
    data = approve_stage(data, "design")
    data = build_preview(data)
    data = record_preview_opened(data)
    data = approve_stage(data, "preview")
    data = run_preflight_stage(data)
    if stage_status(data["ebook_workspace"], "preflight") == STATUS_AWAITING:
        data = approve_stage(data, "preflight")
    return data


def _visual_review_view(data: dict) -> dict[str, Any]:
    from services.ebook_visual_pipeline import visual_review_payload

    try:
        return visual_review_payload(data)
    except Exception:
        return {"assets": [], "findings": [], "approvable": False, "paid_images": False}


def design_public_view(data: dict, *, project_id: int | None = None) -> dict[str, Any]:
    catalog = theme_catalog_payload()
    pre = data.get("ebook_design_preflight") if isinstance(data.get("ebook_design_preflight"), dict) else {}
    identity = data.get("ebook_export_identity") if isinstance(data.get("ebook_export_identity"), dict) else {}
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    design = data.get("ebook_design") if isinstance(data.get("ebook_design"), dict) else {}
    preview = cover_preview_public_fields(data, project_id=project_id)
    from services.ebook_photo_cover import photo_cover_public_fields

    photo = photo_cover_public_fields(data, project_id=project_id)
    digest = str(identity.get("preview_digest") or identity.get("pdf_sha256") or "")
    opened = preview_opened_matches_current(data)
    preview_open_url = ""
    if project_id and digest:
        preview_open_url = f"/ebook-workspace/{int(project_id)}/full-preview?digest={digest}"
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
            "preview_url": preview["preview_url"] or photo.get("preview_url") or "",
            "preview_download_url": preview["preview_download_url"],
            "preview_verified": preview["preview_verified"] or bool(photo.get("approvable")),
            "photo": photo,
            "approvable": photo.get("approvable") is True,
            "workflow": photo.get("workflow") or "",
        },
        "visual_manifest": data.get("ebook_visual_manifest") or {},
        "visual_review": _visual_review_view(data),
        "preflight": pre,
        "identity": identity,
        "export_ready": data.get("export_ready") is True and str(pre.get("status") or "").upper() == PREFLIGHT_PASS,
        "preview_available": bool(data.get("ebook_preview_html") or data.get("preview_html")),
        "preview_digest": digest,
        "preview_opened": opened,
        "preview_open_url": preview_open_url,
        "stale_design": design_is_stale(design, manuscript_digest=manuscript_digest(data)),
        "paid_calls": False,
    }
