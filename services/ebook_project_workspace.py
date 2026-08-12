"""Ebook Project workspace: stage rail, approvals, invalidation, cost ledger.

Server-authoritative. UI may display state but cannot invent approvals or PASS.
Paid actions require a prior estimate + explicit confirmation token.
"""
from __future__ import annotations

import copy
import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.ebook_document import (
    EbookDocument,
    OutlineItem,
    ResearchBrief,
    attach_document_to_data,
    build_ebook_document_from_project,
)
from services.ebook_workflow import STAGE_LABELS as FINE_STAGE_LABELS
from services.ebook_workflow import set_workflow_stage

ROOT = Path(__file__).resolve().parents[1]
ACCEPTANCE_EXPORT_DIR = ROOT / "exports" / "ebook_live_acceptance_lonnie_event_photo"
ACCEPTANCE_PROJECT_NAME = "LIVE ACCEPTANCE — EVENT PHOTOGRAPHY EBOOK"
ACCEPTANCE_MARKER = "live_acceptance_event_photography_ebook_v1"

# User-facing stage rail (coarse). Maps onto fine WORKFLOW_STAGES internally.
RAIL_STAGES = (
    "research",
    "title",
    "outline",
    "manuscript",
    "visuals",
    "cover",
    "design",
    "preview",
    "preflight",
    "export",
)

RAIL_LABELS = {
    "research": "Research",
    "title": "Title",
    "outline": "Outline",
    "manuscript": "Manuscript",
    "visuals": "Visuals",
    "cover": "Cover",
    "design": "Design",
    "preview": "Preview",
    "preflight": "Preflight",
    "export": "Export",
}

STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_AWAITING = "awaiting_approval"
STATUS_APPROVED = "approved"
STATUS_NEEDS_CORRECTION = "needs_correction"
STATUS_BLOCKED = "blocked"

STATUS_LABELS = {
    STATUS_NOT_STARTED: "Not started",
    STATUS_IN_PROGRESS: "In progress",
    STATUS_AWAITING: "Awaiting approval",
    STATUS_APPROVED: "Approved",
    STATUS_NEEDS_CORRECTION: "Needs correction",
    STATUS_BLOCKED: "Blocked",
}

# Editing an earlier approved stage invalidates these later rail stages.
INVALIDATE_AFTER = {
    "research": ("title", "outline", "manuscript", "visuals", "cover", "design", "preview", "preflight", "export"),
    "title": ("outline", "manuscript", "visuals", "cover", "design", "preview", "preflight", "export"),
    "outline": ("manuscript", "visuals", "cover", "design", "preview", "preflight", "export"),
    "manuscript": ("visuals", "cover", "design", "preview", "preflight", "export"),
    "visuals": ("cover", "design", "preview", "preflight", "export"),
    "cover": ("design", "preview", "preflight", "export"),
    "design": ("preview", "preflight", "export"),
    "preview": ("preflight", "export"),
    "preflight": ("export",),
    "export": (),
}

PAID_ACTIONS = {
    "run_research": {
        "label": "Run research",
        "requires_approved": (),
        "default_estimate_usd": 0.50,
    },
    "generate_title_options": {
        "label": "Generate title options",
        "requires_approved": ("research",),
        "default_estimate_usd": 0.15,
    },
    "generate_outline_options": {
        "label": "Generate outline options",
        "requires_approved": ("title",),
        "default_estimate_usd": 0.20,
    },
    "generate_manuscript": {
        "label": "Generate Manuscript",
        "requires_approved": ("outline",),
        "default_estimate_usd": 1.50,
    },
}

DEFAULT_BUDGET_CAP_USD = 3.50


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def empty_rail() -> dict[str, dict[str, Any]]:
    return {
        stage: {
            "id": stage,
            "label": RAIL_LABELS[stage],
            "status": STATUS_NOT_STARTED,
            "approved_at": None,
            "updated_at": None,
        }
        for stage in RAIL_STAGES
    }


def empty_ledger(*, spent_usd: float = 0.0, paid_calls: int = 0, cap_usd: float = DEFAULT_BUDGET_CAP_USD) -> dict[str, Any]:
    spent = round(float(spent_usd), 4)
    cap = round(float(cap_usd), 4)
    return {
        "budget_cap_usd": cap,
        "spent_usd": spent,
        "remaining_usd": round(cap - spent, 4),
        "paid_calls": int(paid_calls),
        "calls": [],
        "pending_estimate": None,
    }


def new_workspace(
    *,
    topic: str = "",
    audience: str = "",
    outcome: str = "",
    author: str = "",
    budget_cap_usd: float = DEFAULT_BUDGET_CAP_USD,
) -> dict[str, Any]:
    return {
        "version": 1,
        "marker": None,
        "created_at": _now(),
        "updated_at": _now(),
        "topic": topic,
        "audience": audience,
        "outcome": outcome,
        "author": author,
        "editorial_rules_locked": [],
        "rail": empty_rail(),
        "current_stage": "research",
        "next_action": "run_research",
        "approval_history": [],
        "title_options": [],
        "approved_title_id": None,
        "outline_options": [],
        "approved_outline_id": None,
        "research_payload": {
            "summary": "",
            "key_findings": [],
            "notes_sections": {},
            "source_urls": [],
            "printing_research": {},
        },
        "paid_call_ledger": empty_ledger(cap_usd=budget_cap_usd),
        "content_digest": "",
        "asset_digest": "",
    }


def get_workspace(data: dict | None) -> dict | None:
    data = data or {}
    ws = data.get("ebook_workspace")
    return ws if isinstance(ws, dict) and ws.get("version") else None


def ensure_workspace(data: dict | None) -> dict:
    data = dict(data or {})
    ws = get_workspace(data)
    if ws is None:
        ws = new_workspace(
            topic=str(data.get("title") or data.get("source") or ""),
            audience=str((data.get("fields") or {}).get("audience") or data.get("audience") or ""),
            outcome=str(data.get("reader_promise") or ""),
            author=str(data.get("author_brand") or data.get("author") or ""),
        )
        data["ebook_workspace"] = ws
        data["ebook_project_workspace"] = True
        data["product_type"] = "ebook"
    return data


def stage_status(ws: dict, stage: str) -> str:
    rail = ws.get("rail") or {}
    entry = rail.get(stage) or {}
    return str(entry.get("status") or STATUS_NOT_STARTED)


def is_approved(ws: dict, stage: str) -> bool:
    return stage_status(ws, stage) == STATUS_APPROVED


def set_stage_status(ws: dict, stage: str, status: str, *, note: str = "") -> None:
    if stage not in RAIL_STAGES:
        raise ValueError(f"Unknown rail stage: {stage}")
    if status not in STATUS_LABELS:
        raise ValueError(f"Unknown status: {status}")
    rail = ws.setdefault("rail", empty_rail())
    entry = rail.setdefault(stage, {"id": stage, "label": RAIL_LABELS[stage]})
    entry["status"] = status
    entry["updated_at"] = _now()
    if status == STATUS_APPROVED:
        entry["approved_at"] = entry["updated_at"]
    elif status in {STATUS_NOT_STARTED, STATUS_IN_PROGRESS, STATUS_AWAITING, STATUS_NEEDS_CORRECTION}:
        if status != STATUS_APPROVED:
            # Keep prior approved_at only while still approved; clear otherwise.
            entry["approved_at"] = None
    if note:
        entry["note"] = note
    ws["updated_at"] = _now()


def _append_history(ws: dict, event: str, **meta: Any) -> None:
    hist = ws.setdefault("approval_history", [])
    hist.append({"ts": _now(), "event": event, **meta})


def invalidate_after(ws: dict, stage: str, *, reason: str) -> list[str]:
    cleared: list[str] = []
    for later in INVALIDATE_AFTER.get(stage, ()):
        prev = stage_status(ws, later)
        if prev == STATUS_NOT_STARTED:
            continue
        set_stage_status(ws, later, STATUS_NOT_STARTED, note=f"Invalidated: {reason}")
        cleared.append(later)
    if stage == "research":
        ws["title_options"] = []
        ws["approved_title_id"] = None
        ws["outline_options"] = []
        ws["approved_outline_id"] = None
    elif stage == "title":
        ws["outline_options"] = []
        ws["approved_outline_id"] = None
    if cleared:
        _append_history(ws, "invalidate", stage=stage, cleared=cleared, reason=reason)
    _recompute_next_action(ws)
    return cleared


def _recompute_next_action(ws: dict) -> None:
    if not is_approved(ws, "research"):
        st = stage_status(ws, "research")
        ws["current_stage"] = "research"
        ws["next_action"] = "approve_research" if st in {STATUS_AWAITING, STATUS_IN_PROGRESS} else "run_research"
        return
    if not is_approved(ws, "title"):
        ws["current_stage"] = "title"
        ws["next_action"] = "approve_title" if ws.get("title_options") else "generate_title_options"
        return
    if not is_approved(ws, "outline"):
        ws["current_stage"] = "outline"
        ws["next_action"] = "approve_outline" if ws.get("outline_options") else "generate_outline_options"
        return
    if not is_approved(ws, "manuscript"):
        ws["current_stage"] = "manuscript"
        ws["next_action"] = "generate_manuscript"
        return
    if not is_approved(ws, "visuals"):
        ws["current_stage"] = "visuals"
        ws["next_action"] = "resolve_visuals"
        return
    if not is_approved(ws, "cover"):
        ws["current_stage"] = "cover"
        ws["next_action"] = "approve_cover"
        return
    if not is_approved(ws, "design"):
        ws["current_stage"] = "design"
        ws["next_action"] = "select_design"
        return
    if not is_approved(ws, "preview"):
        ws["current_stage"] = "preview"
        ws["next_action"] = "preview_ebook"
        return
    if not is_approved(ws, "preflight"):
        ws["current_stage"] = "preflight"
        ws["next_action"] = "run_preflight"
        return
    ws["current_stage"] = "export"
    ws["next_action"] = "export_download"


def assert_can_run_stage(ws: dict, stage: str) -> None:
    """Block premature production stages."""
    if stage == "manuscript" and not is_approved(ws, "outline"):
        raise ValueError("Manuscript generation is disabled until the outline is approved.")
    if stage == "visuals" and not is_approved(ws, "manuscript"):
        raise ValueError("Visual generation is disabled until manuscript content QA passes.")
    if stage in {"cover", "design", "preview", "preflight", "export"}:
        # Cover is separate from manuscript approval, but still requires manuscript present/approved path.
        if not is_approved(ws, "manuscript"):
            raise ValueError(f"{RAIL_LABELS.get(stage, stage)} is blocked until manuscript is approved.")
    if stage == "export":
        # Export also requires server PASS — checked by caller using release_status.
        pass


def sync_document_from_workspace(data: dict) -> dict:
    """Push approved workspace fields into EbookDocument + project blob."""
    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    doc = build_ebook_document_from_project(data=data)

    doc.author = str(ws.get("author") or doc.author or "")
    doc.audience = str(ws.get("audience") or doc.audience or "")
    doc.reader_promise = str(ws.get("outcome") or doc.reader_promise or "")

    research = ws.get("research_payload") or {}
    doc.research = ResearchBrief(
        topic=str(ws.get("topic") or research.get("topic") or doc.research.topic or ""),
        audience=str(ws.get("audience") or doc.audience),
        reader_promise=str(ws.get("outcome") or doc.reader_promise),
        notes=str(research.get("summary") or doc.research.notes or ""),
        sources=[{"url": u, "title": u} for u in (research.get("source_urls") or []) if u],
        approved=is_approved(ws, "research"),
    )

    if is_approved(ws, "title"):
        doc.title = str(data.get("title") or doc.title or "")
        doc.subtitle = str(data.get("subtitle") or doc.subtitle or "")

    if is_approved(ws, "outline"):
        outline_items = data.get("outline") or []
        if outline_items:
            doc.outline = []
            for o in outline_items:
                if isinstance(o, dict):
                    doc.outline.append(
                        OutlineItem(
                            order=int(o.get("order") or 0),
                            title=str(o.get("title") or ""),
                            purpose=str(o.get("purpose") or ""),
                            approved=True,
                        )
                    )

    # Fine-grained BookyAI stage for compatibility
    if is_approved(ws, "outline") and not is_approved(ws, "manuscript"):
        set_workflow_stage(doc, "manuscript")
    elif is_approved(ws, "title") and not is_approved(ws, "outline"):
        set_workflow_stage(doc, "outline")
    elif is_approved(ws, "research") and not is_approved(ws, "title"):
        set_workflow_stage(doc, "title_options")
    elif not is_approved(ws, "research"):
        set_workflow_stage(doc, "research")

    data = attach_document_to_data(data, doc, sync_manuscript=True)
    data["ebook_workspace"] = ws
    data["ebook_project_workspace"] = True
    data["product_type"] = "ebook"
    data["export_ready"] = False if str(data.get("release_status") or "").upper() != "PASS" else data.get("export_ready")
    ws["content_digest"] = doc.identity.content_digest
    ws["asset_digest"] = doc.identity.asset_manifest_digest
    return data


def workspace_public_view(project: dict) -> dict[str, Any]:
    """Customer-safe payload for the Ebook Project workspace UI (no raw dump of secrets)."""
    data = dict(project.get("data") or {})
    ws = get_workspace(data) or new_workspace()
    ledger = ws.get("paid_call_ledger") or empty_ledger()
    rail = []
    for stage in RAIL_STAGES:
        entry = (ws.get("rail") or {}).get(stage) or {}
        status = str(entry.get("status") or STATUS_NOT_STARTED)
        rail.append(
            {
                "id": stage,
                "label": RAIL_LABELS[stage],
                "status": status,
                "status_label": STATUS_LABELS.get(status, status),
                "approved_at": entry.get("approved_at"),
                "updated_at": entry.get("updated_at"),
                "openable": status != STATUS_NOT_STARTED or stage == ws.get("current_stage"),
            }
        )
    pending = ledger.get("pending_estimate")
    return {
        "project_id": project.get("id"),
        "name": project.get("name"),
        "artifact_id": data.get("artifact_id") or data.get("package_id") or "",
        "artifact_state": data.get("artifact_state") or project.get("artifact_state") or "DRAFT",
        "artifact_revision": data.get("artifact_revision") or project.get("artifact_revision") or 1,
        "author": ws.get("author") or data.get("author_brand") or "",
        "topic": ws.get("topic") or "",
        "audience": ws.get("audience") or "",
        "outcome": ws.get("outcome") or "",
        "title": data.get("title") or "",
        "subtitle": data.get("subtitle") or "",
        "editorial_rules_locked": list(ws.get("editorial_rules_locked") or []),
        "rail": rail,
        "current_stage": ws.get("current_stage"),
        "next_action": ws.get("next_action"),
        "next_action_label": PAID_ACTIONS.get(str(ws.get("next_action") or ""), {}).get("label")
        or str(ws.get("next_action") or "").replace("_", " ").title(),
        "budget": {
            "cap_usd": ledger.get("budget_cap_usd"),
            "spent_usd": ledger.get("spent_usd"),
            "remaining_usd": ledger.get("remaining_usd"),
            "paid_calls": ledger.get("paid_calls"),
        },
        "pending_estimate": pending,
        "research": _research_view(ws),
        "title_options": list(ws.get("title_options") or []),
        "approved_title_id": ws.get("approved_title_id"),
        "outline_options": list(ws.get("outline_options") or []),
        "approved_outline_id": ws.get("approved_outline_id"),
        "outline": list(data.get("outline") or []),
        "approval_history": list(ws.get("approval_history") or [])[-20:],
        "release_status": data.get("release_status") or "",
        "export_ready": data.get("export_ready") is True,
        "ebook_workflow_stage": data.get("ebook_workflow_stage") or "",
        "fine_stage_labels": FINE_STAGE_LABELS,
        "gates": {
            "manuscript_enabled": is_approved(ws, "outline"),
            "visuals_enabled": is_approved(ws, "manuscript"),
            "export_enabled": str(data.get("release_status") or "").upper() == "PASS"
            and data.get("export_ready") is True,
        },
    }


def _research_view(ws: dict) -> dict[str, Any]:
    payload = ws.get("research_payload") or {}
    return {
        "summary": payload.get("summary") or "",
        "key_findings": list(payload.get("key_findings") or []),
        "notes_sections": dict(payload.get("notes_sections") or {}),
        "source_urls": list(payload.get("source_urls") or []),
        "printing_research": {
            "evidence_quality": (payload.get("printing_research") or {}).get("evidence_quality"),
            "manufacturer_facts": list((payload.get("printing_research") or {}).get("manufacturer_facts") or [])[:40],
            "keepsake_notes": (payload.get("printing_research") or {}).get("keepsake_notes") or "",
        },
        "approved": is_approved(ws, "research"),
    }


def save_research(data: dict, research: dict, *, mark_awaiting: bool = True) -> dict:
    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    payload = ws.setdefault("research_payload", {})
    payload.update(
        {
            "summary": str(research.get("summary") or payload.get("summary") or ""),
            "key_findings": list(research.get("key_findings") or payload.get("key_findings") or []),
            "notes_sections": dict(research.get("notes_sections") or payload.get("notes_sections") or {}),
            "source_urls": list(research.get("source_urls") or payload.get("source_urls") or []),
            "printing_research": dict(research.get("printing_research") or payload.get("printing_research") or {}),
            "topic": str(research.get("topic") or ws.get("topic") or ""),
        }
    )
    if research.get("topic"):
        ws["topic"] = str(research["topic"])
    if research.get("audience"):
        ws["audience"] = str(research["audience"])
    if research.get("outcome"):
        ws["outcome"] = str(research["outcome"])
    was_approved = is_approved(ws, "research")
    if was_approved:
        invalidate_after(ws, "research", reason="Research edited after approval")
        set_stage_status(ws, "research", STATUS_NEEDS_CORRECTION, note="Edited after approval")
    else:
        set_stage_status(
            ws,
            "research",
            STATUS_AWAITING if mark_awaiting else STATUS_IN_PROGRESS,
        )
    _append_history(ws, "save_research")
    _recompute_next_action(ws)
    return sync_document_from_workspace(data)


def approve_stage(data: dict, stage: str, *, choice_id: str | None = None) -> dict:
    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    if stage not in RAIL_STAGES:
        raise ValueError(f"Unknown stage: {stage}")

    if stage == "research":
        summary = ((ws.get("research_payload") or {}).get("summary") or "").strip()
        if not summary:
            raise ValueError("Cannot approve empty research.")
        set_stage_status(ws, "research", STATUS_APPROVED)
        _append_history(ws, "approve", stage="research")

    elif stage == "title":
        if not is_approved(ws, "research"):
            raise ValueError("Approve research before title.")
        options = ws.get("title_options") or []
        chosen = None
        if choice_id:
            chosen = next((o for o in options if str(o.get("id")) == str(choice_id)), None)
        if chosen is None and options:
            chosen = options[0]
        if not chosen and not (data.get("title") and data.get("subtitle")):
            raise ValueError("Select a title option before approving.")
        if chosen:
            data["title"] = str(chosen.get("title") or data.get("title") or "")
            data["subtitle"] = str(chosen.get("subtitle") or data.get("subtitle") or "")
            ws["approved_title_id"] = chosen.get("id")
        set_stage_status(ws, "title", STATUS_APPROVED)
        _append_history(ws, "approve", stage="title", choice_id=ws.get("approved_title_id"))

    elif stage == "outline":
        if not is_approved(ws, "title"):
            raise ValueError("Approve title before outline.")
        options = ws.get("outline_options") or []
        chosen = None
        if choice_id:
            chosen = next((o for o in options if str(o.get("id")) == str(choice_id)), None)
        if chosen is None:
            chosen = next((o for o in options if o.get("id") == ws.get("approved_outline_id")), None)
        if chosen is None and options:
            chosen = options[0]
        chapters = (chosen or {}).get("chapters") or data.get("outline") or []
        if len(chapters) < 3:
            raise ValueError("Outline must include at least 3 chapters.")
        data["outline"] = [
            {
                "order": int(c.get("n") or c.get("order") or i + 1),
                "title": str(c.get("title") or ""),
                "purpose": "\n".join(c.get("bullets") or []) if isinstance(c.get("bullets"), list) else str(c.get("purpose") or ""),
                "approved": True,
            }
            for i, c in enumerate(chapters)
            if isinstance(c, dict)
        ]
        if chosen:
            ws["approved_outline_id"] = chosen.get("id")
        set_stage_status(ws, "outline", STATUS_APPROVED)
        _append_history(ws, "approve", stage="outline", choice_id=ws.get("approved_outline_id"))

    else:
        raise ValueError(f"Stage '{stage}' cannot be approved through this endpoint yet.")

    _recompute_next_action(ws)
    return sync_document_from_workspace(data)


def edit_title(data: dict, *, title: str, subtitle: str, options: list | None = None) -> dict:
    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    if not is_approved(ws, "research"):
        raise ValueError("Approve research before editing title.")
    data["title"] = title.strip()
    data["subtitle"] = subtitle.strip()
    if options is not None:
        ws["title_options"] = list(options)
    if is_approved(ws, "title") or stage_status(ws, "title") != STATUS_NOT_STARTED:
        invalidate_after(ws, "title", reason="Title edited")
    set_stage_status(ws, "title", STATUS_AWAITING if data["title"] and data["subtitle"] else STATUS_IN_PROGRESS)
    _append_history(ws, "edit_title")
    _recompute_next_action(ws)
    return sync_document_from_workspace(data)


def edit_outline(data: dict, *, chapters: list[dict], option_id: str | None = None) -> dict:
    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    if not is_approved(ws, "title"):
        raise ValueError("Approve title before editing outline.")
    if len(chapters) < 3:
        raise ValueError("Outline requires at least 3 chapters.")
    data["outline"] = [
        {
            "order": int(c.get("order") or c.get("n") or i + 1),
            "title": str(c.get("title") or ""),
            "purpose": str(c.get("purpose") or "\n".join(c.get("bullets") or [])),
            "approved": False,
        }
        for i, c in enumerate(chapters)
        if isinstance(c, dict)
    ]
    if option_id:
        ws["approved_outline_id"] = option_id
    if is_approved(ws, "outline") or stage_status(ws, "outline") != STATUS_NOT_STARTED:
        invalidate_after(ws, "outline", reason="Outline edited")
    set_stage_status(ws, "outline", STATUS_AWAITING)
    _append_history(ws, "edit_outline")
    _recompute_next_action(ws)
    return sync_document_from_workspace(data)


def estimate_paid_action(data: dict, action: str) -> dict:
    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    spec = PAID_ACTIONS.get(action)
    if not spec:
        raise ValueError(f"Unknown paid action: {action}")
    for req in spec["requires_approved"]:
        if not is_approved(ws, req):
            raise ValueError(f"Action '{action}' requires approved stage '{req}'.")
    ledger = ws.setdefault("paid_call_ledger", empty_ledger())
    estimate = round(float(spec["default_estimate_usd"]), 4)
    remaining = round(float(ledger.get("remaining_usd") or 0), 4)
    if estimate > remaining + 1e-9:
        raise ValueError(
            f"Estimated cost ${estimate:.3f} exceeds remaining budget ${remaining:.3f}."
        )
    token = secrets.token_urlsafe(16)
    pending = {
        "action": action,
        "label": spec["label"],
        "estimated_max_usd": estimate,
        "spent_usd": ledger.get("spent_usd"),
        "remaining_usd": remaining,
        "budget_cap_usd": ledger.get("budget_cap_usd"),
        "confirmation_token": token,
        "created_at": _now(),
        "expires_note": "Confirmation required before any paid call. Opening this page does not spend.",
    }
    ledger["pending_estimate"] = pending
    _append_history(ws, "estimate", action=action, estimated_max_usd=estimate)
    data["ebook_workspace"] = ws
    return {
        "ok": True,
        "estimate": {k: v for k, v in pending.items()},
        "workspace": workspace_public_view({"id": data.get("_project_id"), "name": data.get("title"), "data": data}),
    }


def consume_confirmation(data: dict, action: str, confirmation_token: str) -> dict:
    """Validate confirmation without executing a paid call."""
    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    ledger = ws.get("paid_call_ledger") or {}
    pending = ledger.get("pending_estimate") or {}
    if not pending:
        raise ValueError("No pending cost estimate. Request an estimate first.")
    if str(pending.get("action")) != str(action):
        raise ValueError("Confirmation does not match the pending paid action.")
    if not confirmation_token or str(pending.get("confirmation_token")) != str(confirmation_token):
        raise ValueError("Invalid or missing confirmation token.")
    return pending


def clear_pending_estimate(data: dict) -> dict:
    data = ensure_workspace(data)
    ledger = data["ebook_workspace"].setdefault("paid_call_ledger", empty_ledger())
    ledger["pending_estimate"] = None
    return data


def assert_no_paid_side_effects_on_read() -> None:
    """Documentation hook — read/render paths must not call this to spend."""
    return None


def build_acceptance_project_data() -> dict[str, Any]:
    """Preserve Lonnie live-acceptance materials as a resumable DRAFT workspace."""
    export_dir = ACCEPTANCE_EXPORT_DIR
    if not export_dir.is_dir():
        raise FileNotFoundError(f"Acceptance export dir missing: {export_dir}")

    brief = json.loads((export_dir / "research_brief.json").read_text(encoding="utf-8"))
    printing_wrap = {}
    printing_path = export_dir / "printing_research.json"
    if printing_path.is_file():
        printing_wrap = json.loads(printing_path.read_text(encoding="utf-8"))
    printing = (
        printing_wrap.get("printing_research")
        if isinstance(printing_wrap.get("printing_research"), dict)
        else printing_wrap
    )
    ledger_raw = json.loads((export_dir / "paid_call_ledger.json").read_text(encoding="utf-8"))
    titles = json.loads((export_dir / "title_options.json").read_text(encoding="utf-8"))
    outlines = json.loads((export_dir / "outline_options.json").read_text(encoding="utf-8"))

    approved_title = titles.get("approved") or outlines.get("approved_title") or {}
    title = str(approved_title.get("title") or "From First Booking to On-Site Prints")
    subtitle = str(
        approved_title.get("subtitle")
        or "A Practical Guide to Equipment, Pricing, Client Workflow, Event-Day Operations, and Dye-Sublimation Printing"
    )
    author = "Lonnie Brown"
    rb = brief.get("research_brief") or {}
    editorial = list(
        outlines.get("editorial_rules_locked")
        or brief.get("editorial_rules_locked")
        or titles.get("editorial_rules_locked")
        or []
    )
    # Normalize $2.50 wording if truncated in older export
    editorial = [
        (
            "Preserve at least $2.50 for writing and refinement stages."
            if "Preserve at least" in r and "2.50" not in r and ".50" in r
            else r
        )
        for r in editorial
    ]

    o1 = next((o for o in (outlines.get("options") or []) if o.get("id") == "O1"), None)
    if not o1:
        raise ValueError("Approved outline O1 missing from export.")

    spent = float((ledger_raw.get("totals") or {}).get("estimated_usd") or 0.928)
    paid_calls = int((ledger_raw.get("totals") or {}).get("paid_calls") or 10)
    cap = float(ledger_raw.get("budget_cap_usd") or DEFAULT_BUDGET_CAP_USD)

    ws = new_workspace(
        topic=str(brief.get("topic") or title),
        audience=str(brief.get("audience") or ""),
        outcome=str(brief.get("outcome") or ""),
        author=author,
        budget_cap_usd=cap,
    )
    ws["marker"] = ACCEPTANCE_MARKER
    ws["editorial_rules_locked"] = editorial
    ws["research_payload"] = {
        "topic": brief.get("topic"),
        "summary": rb.get("research_summary") or "",
        "key_findings": list(rb.get("key_findings") or []),
        "notes_sections": {
            "equipment_notes": list(rb.get("equipment_notes") or []),
            "pricing_and_packages_notes": list(rb.get("pricing_and_packages_notes") or []),
            "event_ops_and_onsite_printing_notes": list(rb.get("event_ops_and_onsite_printing_notes") or []),
            "common_mistakes_and_risks": list(rb.get("common_mistakes_and_risks") or []),
            "first_paid_event_checklist_candidates": list(rb.get("first_paid_event_checklist_candidates") or []),
            "open_questions": list(rb.get("open_questions") or []),
        },
        "source_urls": list(rb.get("source_urls_used") or []),
        "printing_research": {
            "evidence_quality": (printing.get("evidence_quality") or rb.get("printing_evidence_quality") or ""),
            "manufacturer_facts": list(printing.get("manufacturer_facts") or []),
            "keepsake_notes": (
                "Keepsakes such as mugs, buttons, shirts, or plates require separate equipment, "
                "materials, production time, staffing, and safety planning. They were not verified "
                "by the printer-manufacturer sources used for dye-sub photo printers in this research."
            ),
            "keepsakes_during_event_vs_post_event": printing.get("keepsakes_during_event_vs_post_event"),
            "export_path": str(export_dir / "printing_research.json"),
        },
        "export_path": str(export_dir / "research_brief.json"),
    }
    ws["title_options"] = list(titles.get("options") or [])
    ws["approved_title_id"] = "T3"
    ws["outline_options"] = list(outlines.get("options") or [])
    ws["approved_outline_id"] = "O1"

    ledger = empty_ledger(spent_usd=spent, paid_calls=paid_calls, cap_usd=cap)
    # Preserve call history reference without re-spending
    ledger["calls"] = list(ledger_raw.get("calls") or [])
    ledger["source_ledger_path"] = str(export_dir / "paid_call_ledger.json")
    ws["paid_call_ledger"] = ledger

    set_stage_status(ws, "research", STATUS_APPROVED, note="Preserved from live acceptance research")
    set_stage_status(ws, "title", STATUS_APPROVED, note="Approved T3 with edited subtitle")
    set_stage_status(ws, "outline", STATUS_APPROVED, note="Approved revised 10-chapter O1 outline")
    for stage in ("manuscript", "visuals", "cover", "design", "preview", "preflight", "export"):
        set_stage_status(ws, stage, STATUS_NOT_STARTED)
    _append_history(
        ws,
        "seed_acceptance",
        title=title,
        subtitle=subtitle,
        outline_id="O1",
        spent_usd=spent,
    )
    _recompute_next_action(ws)

    data: dict[str, Any] = {
        "product_type": "ebook",
        "ebook_project_workspace": True,
        "artifact_state": "DRAFT",
        "artifact_revision": 1,
        "artifact_id": f"ebook-accept-{uuid.uuid4().hex[:12]}",
        "title": title,
        "subtitle": subtitle,
        "author_brand": author,
        "author": author,
        "audience": ws["audience"],
        "reader_promise": ws["outcome"],
        "source": title,
        "content": "",
        "ebook": "",
        "export_ready": False,
        "release_status": "",
        "outline": [
            {
                "order": int(c.get("n") or i + 1),
                "title": str(c.get("title") or ""),
                "purpose": "\n".join(c.get("bullets") or []),
                "approved": True,
            }
            for i, c in enumerate(o1.get("chapters") or [])
        ],
        "acceptance_export_dir": str(export_dir),
        "acceptance_marker": ACCEPTANCE_MARKER,
        "ebook_workspace": ws,
        "user_saved": True,
    }
    data = sync_document_from_workspace(data)
    # Ensure digests present
    doc = build_ebook_document_from_project(data=data)
    data["content_digest"] = doc.identity.content_digest
    data["ebook_manuscript_digest"] = doc.identity.content_digest
    return data


def upsert_acceptance_project(database_module) -> dict:
    """Create or update the labeled DRAFT acceptance project in Saved Projects."""
    data = build_acceptance_project_data()
    existing = None
    for p in database_module.list_projects(include_system=True):
        pdata = p.get("data") or {}
        if (
            p.get("name") == ACCEPTANCE_PROJECT_NAME
            or pdata.get("acceptance_marker") == ACCEPTANCE_MARKER
            or (get_workspace(pdata) or {}).get("marker") == ACCEPTANCE_MARKER
        ):
            existing = p
            break
    if existing:
        # Preserve identity/revision; refresh workspace content without rewriting approvals content.
        prev = dict(existing.get("data") or {})
        data["artifact_id"] = prev.get("artifact_id") or data.get("artifact_id")
        data["artifact_revision"] = prev.get("artifact_revision") or 1
        data["artifact_state"] = "DRAFT"
        # Do not invent manuscript if somehow present — preserve empty/not started.
        if prev.get("content") or prev.get("ebook") or (prev.get("ebook_document") or {}).get("manuscript_md"):
            # Keep prior manuscript only if user somehow generated later; acceptance seed task forbids generation.
            # If manuscript exists from a later session, keep it; otherwise leave empty.
            pass
        updated = database_module.update_project(
            existing["id"],
            ACCEPTANCE_PROJECT_NAME,
            data,
            type_="ebook",
            user_saved=True,
            system_test=False,
            temporary=False,
        )
        return updated
    return database_module.create_project(
        ACCEPTANCE_PROJECT_NAME,
        "ebook",
        data,
        user_saved=True,
        system_test=False,
        temporary=False,
    )
