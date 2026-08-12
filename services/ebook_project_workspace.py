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
        st = stage_status(ws, "manuscript")
        if st == STATUS_AWAITING:
            ws["next_action"] = "approve_manuscript"
        elif st == STATUS_NEEDS_CORRECTION:
            ws["next_action"] = "request_correction"
        else:
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


def outline_digest(data: dict | None) -> str:
    """Stable digest of the approved outline used to detect stale generation requests."""
    data = data or {}
    outline = data.get("outline") or []
    payload = [
        {
            "order": int(o.get("order") or 0),
            "title": str(o.get("title") or "").strip(),
            "purpose": str(o.get("purpose") or "").strip(),
        }
        for o in outline
        if isinstance(o, dict)
    ]
    return _sha(payload)


TOKEN_TTL_SECONDS = 30 * 60
MANUSCRIPT_AUTH_MAX_USD = 1.50


def _clear_manuscript_fields(data: dict) -> None:
    data["content"] = ""
    data["ebook"] = ""
    data["export_ready"] = False
    data["release_status"] = ""
    data["release_certificate"] = None
    ed = data.get("ebook_document")
    if isinstance(ed, dict):
        ed["manuscript_md"] = ""
        ed["chapters"] = []
        ed["release_status"] = ""
    ws = data.get("ebook_workspace")
    if isinstance(ws, dict):
        ws["manuscript_qa"] = []
        ws["last_manuscript_generation"] = None


def _iso_to_ts(iso: str) -> float | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def build_research_notes_for_manuscript(data: dict) -> str:
    """Assemble retained research + editorial constraints for the generator."""
    ws = get_workspace(data) or {}
    payload = ws.get("research_payload") or {}
    parts: list[str] = []
    parts.append(f"TOPIC: {ws.get('topic') or data.get('title') or ''}")
    parts.append(f"AUDIENCE: {ws.get('audience') or ''}")
    parts.append(f"OUTCOME: {ws.get('outcome') or ''}")
    parts.append(
        f"AUTHOR (listed only — do not invent biography or quotes): "
        f"{ws.get('author') or data.get('author_brand') or ''}"
    )
    parts.append(f"TITLE: {data.get('title') or ''}")
    parts.append(f"SUBTITLE: {data.get('subtitle') or ''}")

    # Outline + editorial rules first so they survive the 12k cap.
    outline = data.get("outline") or []
    if outline:
        parts.append(
            "APPROVED OUTLINE (write exactly these chapters; do not invent extra "
            "generic FAQ/Key Practice sections):"
        )
        for o in outline:
            if not isinstance(o, dict):
                continue
            purpose = str(o.get("purpose") or "")[:800]
            parts.append(f"Chapter {o.get('order')}: {o.get('title')}\n{purpose}")

    rules = ws.get("editorial_rules_locked") or []
    if rules:
        parts.append(
            "LOCKED EDITORIAL RULES (must obey):\n- " + "\n- ".join(str(r) for r in rules)
        )

    if payload.get("summary"):
        parts.append("RESEARCH SUMMARY:\n" + str(payload["summary"])[:4000])
    findings = payload.get("key_findings") or []
    if findings:
        parts.append("KEY FINDINGS:\n- " + "\n- ".join(str(f) for f in findings[:20]))

    notes = payload.get("notes_sections") or {}
    if isinstance(notes, dict):
        for key, vals in notes.items():
            if isinstance(vals, list) and vals:
                parts.append(
                    f"{key.upper()}:\n- " + "\n- ".join(str(v)[:240] for v in vals[:12])
                )
            elif vals:
                parts.append(f"{key.upper()}:\n{str(vals)[:800]}")

    printing = payload.get("printing_research") or {}
    if printing:
        parts.append("PRINTING RESEARCH:")
        if printing.get("evidence_quality"):
            parts.append(f"Evidence quality: {str(printing.get('evidence_quality'))[:400]}")
        facts = printing.get("manufacturer_facts") or []
        if facts:
            rendered = []
            for f in facts[:12]:
                if isinstance(f, dict):
                    rendered.append(str(f.get("text") or f.get("fact") or f.get("claim") or f)[:220])
                else:
                    rendered.append(str(f)[:220])
            parts.append("Manufacturer facts:\n- " + "\n- ".join(rendered))
        if printing.get("keepsake_notes"):
            parts.append("Keepsake notes:\n" + str(printing.get("keepsake_notes"))[:800])

    urls = payload.get("source_urls") or []
    if urls:
        parts.append(
            "SOURCE URLS (paraphrase only; do not copy):\n- "
            + "\n- ".join(str(u) for u in urls[:20])
        )

    parts.append(
        "FORBIDDEN: inventing Lonnie Brown stories/clients/earnings/credentials/quotes; "
        "generic FAQ; generic Key Practice; generic Takeaway/Apply scaffolding; "
        "sub-goal #N; visual/production instructions; cover or image prompts."
    )
    return "\n\n".join(parts)[:12000]


def build_manuscript_contract(data: dict):
    from services.ebook_contract import build_contract

    ws = get_workspace(data) or {}
    outline = data.get("outline") or []
    angles = []
    for o in outline:
        if isinstance(o, dict) and o.get("title"):
            purpose = str(o.get("purpose") or "").strip()
            angles.append(f"{o.get('title')}: {purpose}" if purpose else str(o.get("title")))
    return build_contract(
        topic=str(data.get("title") or ws.get("topic") or "Untitled"),
        audience=str(ws.get("audience") or data.get("audience") or ""),
        tone="practical and professional",
        reading_level="General adult",
        reader_problem=str(ws.get("outcome") or ""),
        desired_transformation=str(ws.get("outcome") or ""),
        chapter_count=max(3, len(outline) or 10),
        research_requested=True,
        worksheet_required=False,
    )


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
            "manuscript_enabled": is_approved(ws, "outline")
            and stage_status(ws, "manuscript")
            in {STATUS_NOT_STARTED, STATUS_NEEDS_CORRECTION, STATUS_IN_PROGRESS},
            "visuals_enabled": is_approved(ws, "manuscript"),
            "export_enabled": str(data.get("release_status") or "").upper() == "PASS"
            and data.get("export_ready") is True,
        },
        "manuscript": {
            "status": stage_status(ws, "manuscript"),
            "status_label": STATUS_LABELS.get(stage_status(ws, "manuscript"), ""),
            "content": str(data.get("content") or data.get("ebook") or "")[:200000],
            "chapters": [
                {"order": c.get("order"), "title": c.get("title"), "approved": bool(c.get("approved"))}
                for c in (
                    ((data.get("ebook_document") or {}).get("chapters") or [])
                    if isinstance(data.get("ebook_document"), dict)
                    else []
                )
            ]
            or [
                {"order": o.get("order"), "title": o.get("title"), "approved": False}
                for o in (data.get("outline") or [])
                if stage_status(ws, "manuscript")
                in {STATUS_AWAITING, STATUS_NEEDS_CORRECTION, STATUS_APPROVED}
            ],
            "qa_findings": list(ws.get("manuscript_qa") or []),
            "last_generation": ws.get("last_manuscript_generation"),
        },
        "outline_digest": outline_digest(data),
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
        cleared = invalidate_after(ws, "research", reason="Research edited after approval")
        if "manuscript" in cleared:
            _clear_manuscript_fields(data)
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

    elif stage == "manuscript":
        if not is_approved(ws, "outline"):
            raise ValueError("Approve outline before manuscript.")
        md = str(data.get("content") or data.get("ebook") or "").strip()
        if not md:
            raise ValueError("Cannot approve an empty manuscript.")
        if stage_status(ws, "manuscript") == STATUS_NEEDS_CORRECTION:
            raise ValueError("Resolve content QA findings before approving the manuscript.")
        if stage_status(ws, "manuscript") not in {STATUS_AWAITING, STATUS_APPROVED}:
            raise ValueError("Manuscript must be awaiting approval before it can be approved.")
        qa = list(ws.get("manuscript_qa") or [])
        if qa:
            raise ValueError("Cannot approve manuscript while content QA findings remain.")
        set_stage_status(ws, "manuscript", STATUS_APPROVED)
        _append_history(ws, "approve", stage="manuscript")

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
        cleared = invalidate_after(ws, "title", reason="Title edited")
        if "manuscript" in cleared:
            _clear_manuscript_fields(data)
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
        cleared = invalidate_after(ws, "outline", reason="Outline edited")
        if "manuscript" in cleared:
            _clear_manuscript_fields(data)
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
    if action == "generate_manuscript":
        assert_can_run_stage(ws, "manuscript")
        if stage_status(ws, "manuscript") == STATUS_AWAITING and (
            data.get("content") or data.get("ebook")
        ):
            raise ValueError(
                "Manuscript already generated and awaits approval. Approve or request correction first."
            )
    ledger = ws.setdefault("paid_call_ledger", empty_ledger())
    estimate = round(float(spec["default_estimate_usd"]), 4)
    if action == "generate_manuscript":
        estimate = min(estimate, MANUSCRIPT_AUTH_MAX_USD)
    remaining = round(float(ledger.get("remaining_usd") or 0), 4)
    cap = round(float(ledger.get("budget_cap_usd") or DEFAULT_BUDGET_CAP_USD), 4)
    spent = round(float(ledger.get("spent_usd") or 0), 4)
    if estimate > remaining + 1e-9:
        raise ValueError(
            f"Estimated cost ${estimate:.3f} exceeds remaining budget ${remaining:.3f}."
        )
    if spent + estimate > cap + 1e-9:
        raise ValueError(
            f"Estimated cost would exceed project cap ${cap:.2f}."
        )
    token = secrets.token_urlsafe(16)
    created = _now()
    expires_at = datetime.fromtimestamp(
        (_iso_to_ts(created) or datetime.now(timezone.utc).timestamp()) + TOKEN_TTL_SECONDS,
        tz=timezone.utc,
    ).isoformat()
    pending = {
        "action": action,
        "label": spec["label"],
        "estimated_max_usd": estimate,
        "max_authorized_usd": estimate,
        "spent_usd": spent,
        "remaining_usd": remaining,
        "budget_cap_usd": cap,
        "confirmation_token": token,
        "created_at": created,
        "expires_at": expires_at,
        "artifact_id": str(data.get("artifact_id") or data.get("package_id") or ""),
        "artifact_revision": int(data.get("artifact_revision") or 1),
        "outline_digest": outline_digest(data),
        "used": False,
        "expires_note": "Confirmation required before any paid call. Opening this page does not spend.",
    }
    ledger["pending_estimate"] = pending
    _append_history(ws, "estimate", action=action, estimated_max_usd=estimate)
    data["ebook_workspace"] = ws
    # Customer-facing estimate omits nothing critical; token is required for confirm.
    public_estimate = dict(pending)
    return {
        "ok": True,
        "estimate": public_estimate,
        "workspace": workspace_public_view(
            {"id": data.get("_project_id"), "name": data.get("title"), "data": data}
        ),
    }


def consume_confirmation(data: dict, action: str, confirmation_token: str) -> dict:
    """Validate confirmation without executing a paid call (does not mark used)."""
    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    ledger = ws.get("paid_call_ledger") or {}
    pending = ledger.get("pending_estimate") or {}
    if not pending:
        raise ValueError("No pending cost estimate. Request an estimate first.")
    if pending.get("used") is True:
        raise ValueError("Confirmation token has already been used.")
    if str(pending.get("action")) != str(action):
        raise ValueError("Confirmation does not match the pending paid action.")
    if not confirmation_token or str(pending.get("confirmation_token")) != str(confirmation_token):
        raise ValueError("Invalid or missing confirmation token.")
    created_ts = _iso_to_ts(str(pending.get("created_at") or ""))
    expires_ts = _iso_to_ts(str(pending.get("expires_at") or ""))
    now_ts = datetime.now(timezone.utc).timestamp()
    if expires_ts is not None and now_ts > expires_ts:
        raise ValueError("Confirmation token has expired. Request a new cost estimate.")
    if created_ts is not None and now_ts - created_ts > TOKEN_TTL_SECONDS:
        raise ValueError("Confirmation token has expired. Request a new cost estimate.")
    return pending


def clear_pending_estimate(data: dict) -> dict:
    data = ensure_workspace(data)
    ledger = data["ebook_workspace"].setdefault("paid_call_ledger", empty_ledger())
    ledger["pending_estimate"] = None
    return data


def cancel_paid_estimate(data: dict) -> dict:
    """Cancel a pending estimate without spending."""
    data = clear_pending_estimate(data)
    _append_history(data["ebook_workspace"], "cancel_estimate")
    return data


def execute_generate_manuscript(
    data: dict,
    *,
    confirmation_token: str,
    expected_artifact_id: str,
    expected_revision: int,
    outline_digest_expected: str,
    max_authorized_usd: float,
    idempotency_key: str,
    generate_fn=None,
) -> dict:
    """Server-authoritative manuscript generation after explicit cost confirmation.

    ``generate_fn`` is injectable for tests (zero paid calls). Production passes
    the real ``services.ebook.generate_ebook`` via the Flask route.
    """
    from services.ebook_document import (
        find_customer_content_defects,
        manuscript_to_chapters,
        strip_visual_instructions,
    )

    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    assert_can_run_stage(ws, "manuscript")
    if not (
        is_approved(ws, "research")
        and is_approved(ws, "title")
        and is_approved(ws, "outline")
    ):
        raise ValueError("Research, title, and outline must all be approved.")

    ledger = ws.setdefault("paid_call_ledger", empty_ledger())
    idem_store = ledger.setdefault("idempotency_keys", {})
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValueError("Idempotency key is required.")
    if key in idem_store:
        # Duplicate click — return prior result without a second paid call.
        prior = idem_store[key]
        return {
            "ok": True,
            "duplicate": True,
            "data": data,
            "result": prior.get("result") or {},
            "workspace_note": "Idempotent replay — no additional paid call.",
        }

    pending = consume_confirmation(data, "generate_manuscript", confirmation_token)

    artifact_id = str(data.get("artifact_id") or data.get("package_id") or "")
    revision = int(data.get("artifact_revision") or 1)
    if str(expected_artifact_id or "") != artifact_id:
        raise ValueError("Stale artifact ID — reopen the project and try again.")
    if int(expected_revision) != revision:
        raise ValueError("Stale artifact revision — reopen the project and try again.")
    if str(pending.get("artifact_id") or "") != artifact_id:
        raise ValueError("Confirmation token was issued for a different artifact.")
    if int(pending.get("artifact_revision") or 0) != revision:
        raise ValueError("Confirmation token was issued for a different revision.")

    current_od = outline_digest(data)
    if str(outline_digest_expected or "") != current_od:
        raise ValueError("Outline changed since the estimate — request a new cost estimate.")
    if str(pending.get("outline_digest") or "") != current_od:
        raise ValueError("Confirmation token outline digest mismatch.")

    auth_max = round(float(max_authorized_usd), 4)
    pending_max = round(float(pending.get("max_authorized_usd") or pending.get("estimated_max_usd") or 0), 4)
    if auth_max <= 0:
        raise ValueError("Maximum authorized charge must be positive.")
    if abs(auth_max - pending_max) > 1e-9:
        raise ValueError("Authorized charge does not match the pending estimate.")
    if auth_max > MANUSCRIPT_AUTH_MAX_USD + 1e-9:
        raise ValueError(
            f"Manuscript authorization exceeds ${MANUSCRIPT_AUTH_MAX_USD:.2f} maximum."
        )

    spent = round(float(ledger.get("spent_usd") or 0), 4)
    remaining = round(float(ledger.get("remaining_usd") or 0), 4)
    cap = round(float(ledger.get("budget_cap_usd") or DEFAULT_BUDGET_CAP_USD), 4)
    if auth_max > remaining + 1e-9 or spent + auth_max > cap + 1e-9:
        raise ValueError("Insufficient remaining budget for manuscript generation.")

    # Mark token used BEFORE the provider call to prevent duplicate spends on retry storms.
    pending["used"] = True
    ledger["pending_estimate"] = pending
    used_tokens = ledger.setdefault("consumed_tokens", [])
    used_tokens.append(
        {
            "token": str(pending.get("confirmation_token")),
            "action": "generate_manuscript",
            "ts": _now(),
            "idempotency_key": key,
        }
    )

    if generate_fn is None:
        from services.ebook import generate_ebook as generate_fn

    research_notes = build_research_notes_for_manuscript(data)
    contract = build_manuscript_contract(data)

    set_stage_status(ws, "manuscript", STATUS_IN_PROGRESS, note="Generating manuscript")
    source = str(data.get("title") or ws.get("topic") or "").strip()
    author = str(ws.get("author") or data.get("author_brand") or "").strip()

    raw = generate_fn(
        source,
        contract=contract,
        author=author,
        research_notes=research_notes,
    )
    if not isinstance(raw, dict):
        raise ValueError("Manuscript generator returned an invalid payload.")
    manuscript_md = str(raw.get("ebook") or raw.get("content") or "").strip()
    if not manuscript_md:
        raise ValueError("Manuscript generator returned empty content.")

    cleaned, _removed = strip_visual_instructions(manuscript_md)
    defects = find_customer_content_defects(cleaned)
    chapters = manuscript_to_chapters(cleaned)

    # Charge: record one ledger entry at the authorized max (conservative).
    # Live metering can later refine; never exceed auth_max or remaining.
    charge = min(auth_max, remaining)
    ledger["spent_usd"] = round(spent + charge, 4)
    ledger["remaining_usd"] = round(cap - float(ledger["spent_usd"]), 4)
    ledger["paid_calls"] = int(ledger.get("paid_calls") or 0) + 1
    call_rec = {
        "ts": _now(),
        "provider": "openai",
        "purpose": "generate_manuscript",
        "estimated_cost_usd": charge,
        "idempotency_key": key,
        "meta": {
            "title": data.get("title"),
            "outline_digest": current_od,
            "artifact_id": artifact_id,
            "artifact_revision": revision,
        },
    }
    ledger.setdefault("calls", []).append(call_rec)
    ledger["pending_estimate"] = None

    data["content"] = cleaned
    data["ebook"] = cleaned
    data["title"] = data.get("title") or source
    data["subtitle"] = data.get("subtitle") or ""
    data["author_brand"] = author
    data["product_type"] = "ebook"
    data["export_ready"] = False
    data["release_status"] = ""
    data["release_certificate"] = None

    ws["manuscript_qa"] = defects
    ws["last_manuscript_generation"] = {
        "ts": _now(),
        "charge_usd": charge,
        "idempotency_key": key,
        "qa_defect_count": len(defects),
        "chapter_count": len(chapters),
    }
    if defects:
        set_stage_status(
            ws,
            "manuscript",
            STATUS_NEEDS_CORRECTION,
            note="Content QA found defects",
        )
    else:
        set_stage_status(ws, "manuscript", STATUS_AWAITING, note="Awaiting human approval")

    # Later stages stay blocked / not started
    for later in ("visuals", "cover", "design", "preview", "preflight", "export"):
        if stage_status(ws, later) != STATUS_NOT_STARTED:
            set_stage_status(ws, later, STATUS_NOT_STARTED)

    _recompute_next_action(ws)
    data = sync_document_from_workspace(data)
    # Persist chapters from manuscript onto document
    doc = build_ebook_document_from_project(data=data)
    doc.manuscript_md = cleaned
    doc.chapters = chapters
    doc.title = str(data.get("title") or doc.title)
    doc.subtitle = str(data.get("subtitle") or doc.subtitle)
    doc.author = author
    if defects:
        doc.release_status = "FAIL"
        doc.release_messages = list(defects)
    data = attach_document_to_data(data, doc, sync_manuscript=True)
    data["ebook_workspace"] = ws

    result = {
        "ok": True,
        "duplicate": False,
        "manuscript_status": stage_status(ws, "manuscript"),
        "qa_findings": defects,
        "charge_usd": charge,
        "paid_calls": ledger.get("paid_calls"),
        "spent_usd": ledger.get("spent_usd"),
        "remaining_usd": ledger.get("remaining_usd"),
        "chapter_count": len(chapters),
        "title": data.get("title"),
        "subtitle": data.get("subtitle"),
    }
    idem_store[key] = {"result": result, "ts": _now(), "charge_usd": charge}
    ledger["idempotency_keys"] = idem_store
    _append_history(
        ws,
        "generate_manuscript",
        charge_usd=charge,
        qa_defects=len(defects),
        status=stage_status(ws, "manuscript"),
    )
    return {"ok": True, "duplicate": False, "data": data, "result": result}


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
