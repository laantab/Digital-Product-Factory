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
    "correct_manuscript": {
        "label": "Request Correction",
        "requires_approved": ("outline",),
        "default_estimate_usd": 0.75,
    },
}

# Authoritative revised O1 chapter titles (user-approved). Seed/export early O1
# headings must never override these once the revised outline is the project outline.
REVISED_ACCEPTANCE_OUTLINE_TITLES = [
    "What This Business Actually Looks Like",
    "Startup Reality Check: Budget, Legal Basics, and Insurance",
    "Core Camera Kit, Printing Equipment, and Backup Gear",
    "Finding Clients and Turning Inquiries into Signed Bookings",
    "Packages and Pricing Scenarios That Protect Your Margin",
    "Planning the Event: Contracts, Timelines, Space, Power, and Staffing",
    "Event-Day Operations: From Photograph to Guest Delivery",
    "Dye-Sublimation Printing: Setup, Queue, Ordering, Payment, and Pickup",
    "Keepsakes Beyond Photo Prints: Separate Equipment and Workflow",
    "Common Mistakes and Your 30-Day First Paid Event Plan",
]

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
    if stage == "cover" and not is_approved(ws, "visuals"):
        raise ValueError("Cover is blocked until visuals are approved.")
    if stage == "design" and not is_approved(ws, "cover"):
        raise ValueError("Design is blocked until the cover is approved.")
    if stage == "preview" and not is_approved(ws, "design"):
        raise ValueError("Preview is blocked until design is approved.")
    if stage == "preflight" and not is_approved(ws, "preview"):
        raise ValueError("Preflight is blocked until preview is approved.")
    if stage == "export":
        if not is_approved(ws, "preflight"):
            raise ValueError("Export is blocked until design preflight is approved.")


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


def manuscript_digest(data: dict | None) -> str:
    """Digest of the preserved manuscript bytes (content/ebook)."""
    data = data or {}
    text = str(data.get("content") or data.get("ebook") or "")
    return _sha({"manuscript": text})


def structural_findings_digest(data: dict | None) -> str:
    """Digest of manuscript structural/QA findings used to bind correction tokens."""
    data = data or {}
    ws = get_workspace(data) or {}
    findings = list(ws.get("manuscript_structure_findings") or ws.get("manuscript_qa") or [])
    return _sha({"findings": [str(f) for f in findings]})


def normalize_paid_action(action: str) -> str:
    """Map UI synonyms to the canonical paid-action registry key."""
    raw = str(action or "").strip()
    aliases = {
        "request_correction": "correct_manuscript",
        "correct": "correct_manuscript",
        "correction": "correct_manuscript",
    }
    return aliases.get(raw, raw)


TOKEN_TTL_SECONDS = 30 * 60
MANUSCRIPT_AUTH_MAX_USD = 1.50
CORRECTION_AUTH_MAX_USD = 0.75


def authoritative_approved_outline(data: dict) -> list[dict]:
    """Return the stored approved outline chapters (order/title/purpose)."""
    from services.ebook_outline_fidelity import approved_outline_chapters

    return approved_outline_chapters(data)


def prompt_outline_titles_from_notes(research_notes: str) -> list[str]:
    """Extract chapter titles from the APPROVED OUTLINE block in research notes."""
    notes = research_notes or ""
    titles: list[str] = []
    in_block = False
    for line in notes.splitlines():
        if line.startswith("APPROVED OUTLINE"):
            in_block = True
            continue
        if in_block:
            if line.startswith("LOCKED EDITORIAL") or line.startswith("RESEARCH SUMMARY"):
                break
            if line.startswith("Chapter "):
                # Chapter N: Title
                part = line.split(":", 1)
                if len(part) == 2:
                    titles.append(part[1].strip())
            elif line.strip() and not line.startswith(" ") and titles:
                # Next top-level section
                if line.endswith(":") and line.upper() == line:
                    break
    return titles


def _clear_manuscript_fields(data: dict) -> None:
    data["content"] = ""
    data["ebook"] = ""
    data["export_ready"] = False
    data["release_status"] = ""
    data["release_certificate"] = None
    data["ebook_design"] = None
    data["ebook_design_digest"] = ""
    data["ebook_preview_html"] = ""
    data["ebook_export_identity"] = None
    data["ebook_design_preflight"] = None
    data["cover_design"] = None
    data["ebook_visual_manifest"] = None
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
    outline = authoritative_approved_outline(data)
    if outline:
        parts.append(
            "APPROVED OUTLINE (write exactly these chapters as ## H2 headings in this "
            "exact order and wording; do not invent, rename, merge, split, reorder, or "
            "add Conclusion/Disclaimer/Sources as chapters unless listed here):"
        )
        for o in outline:
            purpose = str(o.get("purpose") or "")[:800]
            parts.append(f"Chapter {o.get('order')}: {o.get('title')}\n{purpose}")
        try:
            from services.ebook_manuscript_engine import build_book_contract

            book = build_book_contract(data)
            parts.append("CHAPTER CONTRACTS (authoritative):")
            for ch in book.chapters:
                parts.append(
                    f"Ch {ch.order} {ch.title}: min {ch.min_useful_words} words; "
                    f"table={ch.required_table or '-'}; workflow={ch.required_workflow or '-'}; "
                    f"checklist={ch.required_checklist or '-'}; "
                    f"facts={', '.join(ch.required_facts[:8])}"
                )
        except Exception:
            pass
        parts.append(
            "BACK MATTER RULE: If a disclaimer or sources list is required, place it "
            "AFTER the approved chapters using plain paragraphs or **Disclaimer** / "
            "**Sources** labels — never as ## numbered chapters unless those titles "
            "appear in the approved outline above."
        )

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
    outline = authoritative_approved_outline(data)
    angles = []
    for o in outline:
        purpose = str(o.get("purpose") or "").strip()
        angles.append(f"{o.get('title')}: {purpose}" if purpose else str(o.get("title")))
    contract = build_contract(
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
    contract.required_chapter_angles = angles
    try:
        from services.ebook_manuscript_engine import build_book_contract

        book = build_book_contract(data)
        contract.chapter_count = len(book.chapters) or contract.chapter_count
        setattr(contract, "book_contract_digest", book.digest())
        setattr(contract, "chapter_contracts", book.chapters)
    except Exception:
        pass
    return contract


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
    from services.ebook_manuscript_engine import QUALITY_PASS, validate_manuscript_quality

    md_now = str(data.get("content") or data.get("ebook") or "")
    quality_status = ""
    quality_findings: list[str] = []
    chapter_quality: list[dict] = []
    quality_view = None
    if md_now and is_approved(ws, "outline"):
        quality = validate_manuscript_quality(data, manuscript_md=md_now)
        quality_view = quality.as_dict()
        quality_status = quality.status
        quality_findings = quality.finding_messages
        chapter_quality = quality.chapter_results
    can_approve = (
        stage_status(ws, "manuscript") == STATUS_AWAITING
        and quality_status == QUALITY_PASS
    )
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
        "next_action_label": (
            PAID_ACTIONS.get(str(ws.get("next_action") or ""), {}).get("label")
            or (
                "Request Correction"
                if ws.get("next_action") == "request_correction"
                else None
            )
            or str(ws.get("next_action") or "").replace("_", " ").title()
        ),
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
            in {STATUS_NOT_STARTED, STATUS_IN_PROGRESS}
            and not (data.get("content") or data.get("ebook")),
            "correction_enabled": is_approved(ws, "outline")
            and stage_status(ws, "manuscript") == STATUS_NEEDS_CORRECTION
            and bool(data.get("content") or data.get("ebook")),
            "approve_manuscript_enabled": can_approve,
            "visuals_enabled": is_approved(ws, "manuscript"),
            "cover_enabled": is_approved(ws, "visuals"),
            "design_enabled": is_approved(ws, "cover") and quality_status == QUALITY_PASS,
            "preview_enabled": is_approved(ws, "design"),
            "preflight_enabled": is_approved(ws, "preview"),
            "export_enabled": str(data.get("release_status") or "").upper() == "PASS"
            and data.get("export_ready") is True
            and str((data.get("ebook_design_preflight") or {}).get("status") or "").upper() == "PASS"
            and is_approved(ws, "preflight"),
        },
        "manuscript": {
            "status": stage_status(ws, "manuscript"),
            "status_label": STATUS_LABELS.get(stage_status(ws, "manuscript"), ""),
            "content": str(data.get("content") or data.get("ebook") or "")[:200000],
            "chapters": _manuscript_chapter_view(data, ws, chapter_quality=chapter_quality),
            "qa_findings": quality_findings or list(ws.get("manuscript_qa") or []),
            "structure_findings": list(ws.get("manuscript_structure_findings") or []),
            "quality_status": quality_status,
            "quality": quality_view,
            "chapter_findings": chapter_quality,
            "last_generation": ws.get("last_manuscript_generation"),
            "can_approve": can_approve,
            "correction_estimate_usd": CORRECTION_AUTH_MAX_USD,
            "remaining_usd": ledger.get("remaining_usd"),
        },
        "outline_digest": outline_digest(data),
        "design": _design_view(data),
    }


def _design_view(data: dict) -> dict:
    from services.ebook_design_workspace import design_public_view

    try:
        return design_public_view(data)
    except Exception:
        return {
            "themes": [],
            "export_ready": False,
            "paid_calls": False,
        }


def _manuscript_chapter_view(data: dict, ws: dict, chapter_quality: list | None = None) -> list[dict]:
    """Prefer generated manuscript H2 chapters; fall back to approved outline."""
    quality_by_order = {
        int(r.get("order") or 0): r for r in (chapter_quality or []) if isinstance(r, dict)
    }

    def _attach(row: dict) -> dict:
        q = quality_by_order.get(int(row.get("order") or 0)) or {}
        row = dict(row)
        if q:
            row["quality_status"] = q.get("status")
            row["word_count"] = q.get("words")
            row["findings"] = q.get("findings") or []
        return row

    ed = data.get("ebook_document") if isinstance(data.get("ebook_document"), dict) else {}
    chapters = list(ed.get("chapters") or [])
    if chapters:
        return [
            _attach(
                {
                    "order": c.get("order"),
                    "title": c.get("title"),
                    "approved": bool(c.get("approved")),
                }
            )
            for c in chapters
            if isinstance(c, dict)
        ]
    md = str(data.get("content") or data.get("ebook") or "")
    if md and stage_status(ws, "manuscript") in {
        STATUS_AWAITING,
        STATUS_NEEDS_CORRECTION,
        STATUS_APPROVED,
    }:
        from services.ebook_outline_fidelity import extract_manuscript_h2_titles

        return [
            _attach({"order": i, "title": t, "approved": False})
            for i, t in enumerate(extract_manuscript_h2_titles(md), 1)
        ]
    if stage_status(ws, "manuscript") in {
        STATUS_AWAITING,
        STATUS_NEEDS_CORRECTION,
        STATUS_APPROVED,
    }:
        return [
            _attach({"order": o.get("order"), "title": o.get("title"), "approved": False})
            for o in (data.get("outline") or [])
            if isinstance(o, dict)
        ]
    return []


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
        previous_outline = list(data.get("outline") or [])
        from services.ebook_manuscript_engine import remap_outline_purposes

        drafted = [
            {
                "order": int(c.get("n") or c.get("order") or i + 1),
                "title": str(c.get("title") or ""),
                "purpose": "\n".join(c.get("bullets") or []) if isinstance(c.get("bullets"), list) else str(c.get("purpose") or ""),
                "approved": True,
            }
            for i, c in enumerate(chapters)
            if isinstance(c, dict)
        ]
        data["outline"] = remap_outline_purposes(drafted, previous_outline=previous_outline)
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
            raise ValueError("Resolve structural/content findings before approving the manuscript.")
        if stage_status(ws, "manuscript") not in {STATUS_AWAITING, STATUS_APPROVED}:
            raise ValueError("Manuscript must be awaiting approval before it can be approved.")
        qa = list(ws.get("manuscript_qa") or [])
        structure = list(ws.get("manuscript_structure_findings") or [])
        if qa or structure:
            raise ValueError("Cannot approve manuscript while QA or outline-fidelity findings remain.")
        from services.ebook_outline_fidelity import validate_manuscript_outline_fidelity

        fidelity = validate_manuscript_outline_fidelity(
            approved_outline=authoritative_approved_outline(data),
            manuscript_md=md,
            current_outline_digest=outline_digest(data),
            token_outline_digest=outline_digest(data),
        )
        if not fidelity.get("ok"):
            ws["manuscript_structure_findings"] = list(fidelity.get("findings") or [])
            ws["manuscript_qa"] = list(fidelity.get("findings") or [])
            set_stage_status(
                ws,
                "manuscript",
                STATUS_NEEDS_CORRECTION,
                note="Approved-outline fidelity FAIL",
            )
            _recompute_next_action(ws)
            raise ValueError(
                "Manuscript fails approved-outline fidelity and cannot be approved."
            )
        from services.ebook_manuscript_engine import QUALITY_PASS, validate_manuscript_quality

        quality = validate_manuscript_quality(data, manuscript_md=md)
        if quality.status != QUALITY_PASS:
            ws["manuscript_quality"] = quality.as_dict()
            ws["manuscript_qa"] = quality.finding_messages
            set_stage_status(
                ws,
                "manuscript",
                STATUS_NEEDS_CORRECTION,
                note="Manuscript quality gate blocked approval",
            )
            _recompute_next_action(ws)
            raise ValueError(
                "Manuscript quality must be PASS before Approve Manuscript."
            )
        set_stage_status(ws, "manuscript", STATUS_APPROVED)
        _append_history(ws, "approve", stage="manuscript")

    elif stage == "visuals":
        if not is_approved(ws, "manuscript"):
            raise ValueError("Approve the manuscript before visuals.")
        from services.ebook_manuscript_engine import QUALITY_PASS, validate_manuscript_quality

        md = str(data.get("content") or data.get("ebook") or "")
        quality = validate_manuscript_quality(data, manuscript_md=md)
        if quality.status != QUALITY_PASS:
            raise ValueError("Only a manuscript-quality PASS may enter visuals or design.")
        from services.ebook_design_export import visual_manifest_from_manuscript

        manifest = visual_manifest_from_manuscript(md)
        data["ebook_visual_manifest"] = manifest
        data["ebook_visual_manifest_digest"] = manifest["digest"]
        set_stage_status(ws, "visuals", STATUS_APPROVED, note="Manuscript-derived visuals; no paid images")
        _append_history(ws, "approve", stage="visuals", paid_images=False)

    elif stage == "cover":
        if not is_approved(ws, "visuals"):
            raise ValueError("Approve visuals before the cover.")
        cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None
        if not cover:
            raise ValueError("Generate a local cover before approving.")
        from services.ebook_cover_local import generic_or_mismatched_cover_reason

        reason = generic_or_mismatched_cover_reason(
            cover,
            title=str(data.get("title") or ""),
            subtitle=str(data.get("subtitle") or ""),
            author=str(data.get("author_brand") or data.get("author") or ""),
            topic=str((data.get("fields") or {}).get("topic") or data.get("source") or data.get("title") or ""),
        )
        if reason:
            raise ValueError(f"Cover cannot be approved: {reason.replace('_', ' ')}.")
        set_stage_status(ws, "cover", STATUS_APPROVED)
        _append_history(ws, "approve", stage="cover")

    elif stage == "design":
        if not is_approved(ws, "cover"):
            raise ValueError("Approve the cover before design.")
        from services.ebook_manuscript_engine import QUALITY_PASS, validate_manuscript_quality
        from services.ebook_design_spec import design_is_stale

        md = str(data.get("content") or data.get("ebook") or "")
        quality = validate_manuscript_quality(data, manuscript_md=md)
        if quality.status != QUALITY_PASS:
            raise ValueError("Only a manuscript-quality PASS may enter design.")
        design = data.get("ebook_design") if isinstance(data.get("ebook_design"), dict) else None
        if not design:
            raise ValueError("Select a theme before approving design.")
        if design_is_stale(design, manuscript_digest=manuscript_digest(data)):
            raise ValueError("Design is stale. Select a theme again after the manuscript change.")
        set_stage_status(ws, "design", STATUS_APPROVED)
        _append_history(ws, "approve", stage="design", theme_id=design.get("theme_id"))

    elif stage == "preview":
        if not is_approved(ws, "design"):
            raise ValueError("Approve design before preview.")
        if not (data.get("ebook_preview_html") or data.get("preview_html")):
            raise ValueError("Build preview before approving.")
        set_stage_status(ws, "preview", STATUS_APPROVED)
        _append_history(ws, "approve", stage="preview")

    elif stage == "preflight":
        if not is_approved(ws, "preview"):
            raise ValueError("Approve preview before preflight.")
        pre = data.get("ebook_design_preflight") if isinstance(data.get("ebook_design_preflight"), dict) else {}
        if str(pre.get("status") or "").upper() != "PASS":
            raise ValueError("Preflight must PASS before it can be approved. The UI cannot invent PASS.")
        set_stage_status(ws, "preflight", STATUS_APPROVED)
        _append_history(ws, "approve", stage="preflight")

    elif stage == "export":
        raise ValueError("Export is a download of the approved artifact, not an approval stage.")

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
    previous_outline = list(data.get("outline") or [])
    from services.ebook_manuscript_engine import remap_outline_purposes

    drafted = [
        {
            "order": int(c.get("order") or c.get("n") or i + 1),
            "title": str(c.get("title") or ""),
            "purpose": str(c.get("purpose") or "\n".join(c.get("bullets") or [])),
            "approved": False,
        }
        for i, c in enumerate(chapters)
        if isinstance(c, dict)
    ]
    data["outline"] = remap_outline_purposes(drafted, previous_outline=previous_outline)
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
    action = normalize_paid_action(action)
    spec = PAID_ACTIONS.get(action)
    if not spec:
        known = ", ".join(sorted(PAID_ACTIONS))
        raise ValueError(f"Unknown paid action: {action}. Known actions: {known}")
    for req in spec["requires_approved"]:
        if not is_approved(ws, req):
            raise ValueError(f"Action '{action}' requires approved stage '{req}'.")
    if action == "generate_manuscript":
        assert_can_run_stage(ws, "manuscript")
        if stage_status(ws, "manuscript") == STATUS_NEEDS_CORRECTION and (
            data.get("content") or data.get("ebook")
        ):
            raise ValueError(
                "Manuscript needs correction. Use Request Correction (estimate + confirm) "
                "instead of regenerating a new book."
            )
        if stage_status(ws, "manuscript") == STATUS_AWAITING and (
            data.get("content") or data.get("ebook")
        ):
            raise ValueError(
                "Manuscript already generated and awaits approval. Approve or request correction first."
            )
    if action == "correct_manuscript":
        assert_can_run_stage(ws, "manuscript")
        if stage_status(ws, "manuscript") != STATUS_NEEDS_CORRECTION:
            raise ValueError("Correction is only available when manuscript status is Needs correction.")
        if not (data.get("content") or data.get("ebook")):
            raise ValueError("Correction requires the preserved manuscript draft.")
    ledger = ws.setdefault("paid_call_ledger", empty_ledger())
    estimate = round(float(spec["default_estimate_usd"]), 4)
    if action == "generate_manuscript":
        estimate = min(estimate, MANUSCRIPT_AUTH_MAX_USD)
    if action == "correct_manuscript":
        estimate = min(estimate, CORRECTION_AUTH_MAX_USD)
    remaining = round(float(ledger.get("remaining_usd") or 0), 4)
    cap = round(float(ledger.get("budget_cap_usd") or DEFAULT_BUDGET_CAP_USD), 4)
    spent = round(float(ledger.get("spent_usd") or 0), 4)
    if action == "correct_manuscript":
        # Correction estimates must fit remaining budget (never overshoot).
        estimate = min(estimate, remaining)
        if estimate <= 0:
            raise ValueError("No remaining budget for manuscript correction.")
    elif estimate > remaining + 1e-9:
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
    project_id = data.get("_project_id")
    from services.ebook_manuscript_engine import build_book_contract

    book_contract = build_book_contract(data)
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
        "project_id": int(project_id) if project_id is not None else None,
        "artifact_id": str(data.get("artifact_id") or data.get("package_id") or ""),
        "artifact_revision": int(data.get("artifact_revision") or 1),
        "outline_digest": outline_digest(data),
        "book_contract_digest": book_contract.digest(),
        "chapter_contract_digests": [c.digest() for c in book_contract.chapters],
        "manuscript_digest": manuscript_digest(data),
        "structural_findings_digest": structural_findings_digest(data),
        "used": False,
        "confirmation_required": True,
        "expires_note": "Confirmation required before any paid call. Opening this page does not spend.",
    }
    ledger["pending_estimate"] = pending
    _append_history(ws, "estimate", action=action, estimated_max_usd=estimate)
    data["ebook_workspace"] = ws
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
    generate_chapter_fn=None,
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
    from services.ebook_manuscript_engine import (
        QUALITY_FAIL,
        QUALITY_PASS,
        apply_quality_to_workspace,
        build_book_contract,
        run_chapter_pipeline,
        validate_manuscript_quality,
    )
    from services.ebook_outline_fidelity import (
        normalize_chapter_title,
        validate_manuscript_outline_fidelity,
    )

    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    ledger = ws.setdefault("paid_call_ledger", empty_ledger())
    idem_store = ledger.setdefault("idempotency_keys", {})
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValueError("Idempotency key is required.")
    if key in idem_store:
        prior = idem_store[key]
        return {
            "ok": True,
            "duplicate": True,
            "data": data,
            "result": prior.get("result") or {},
            "workspace_note": "Idempotent replay — no additional paid call.",
        }
    assert_can_run_stage(ws, "manuscript")
    if not (
        is_approved(ws, "research")
        and is_approved(ws, "title")
        and is_approved(ws, "outline")
    ):
        raise ValueError("Research, title, and outline must all be approved.")
    if stage_status(ws, "manuscript") == STATUS_NEEDS_CORRECTION and (
        data.get("content") or data.get("ebook")
    ):
        raise ValueError(
            "Manuscript already exists and needs correction — use correct_manuscript."
        )

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
    book_contract = build_book_contract(data)
    pending_book_digest = str(pending.get("book_contract_digest") or "")
    if pending_book_digest and pending_book_digest != book_contract.digest():
        raise ValueError("Book/chapter contract changed since the estimate — request a new cost estimate.")

    approved_outline = authoritative_approved_outline(data)
    if len(approved_outline) < 3:
        raise ValueError("Approved outline is missing — cannot generate manuscript.")

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

    if generate_chapter_fn is None and generate_fn is None:
        from services.ebook import generate_ebook as generate_fn

    research_notes = build_research_notes_for_manuscript(data)
    contract = build_manuscript_contract(data)
    prompt_titles = prompt_outline_titles_from_notes(research_notes)
    approved_titles = [c["title"] for c in approved_outline]
    if [normalize_chapter_title(t) for t in prompt_titles] != [
        normalize_chapter_title(t) for t in approved_titles
    ]:
        raise ValueError(
            "Generator prompt outline does not match the token-bound approved outline. "
            "Request a new cost estimate."
        )

    set_stage_status(ws, "manuscript", STATUS_IN_PROGRESS, note="Generating manuscript")
    source = str(data.get("title") or ws.get("topic") or "").strip()
    author = str(ws.get("author") or data.get("author_brand") or "").strip()

    provider_input = {
        "source": source,
        "author": author,
        "outline_digest": current_od,
        "approved_titles": approved_titles,
        "prompt_titles": prompt_titles,
        "chapter_count": len(approved_outline),
        "research_notes_prefix": research_notes[:2000],
        "book_contract_digest": book_contract.digest(),
        "chapter_titles": [c.title for c in book_contract.chapters],
    }

    if generate_chapter_fn is not None:
        pipeline = run_chapter_pipeline(
            book_contract,
            generate_chapter_fn=generate_chapter_fn,
        )
        manuscript_md = str(pipeline.get("manuscript_md") or "").strip()
        ws["accepted_chapters"] = [
            {"order": c.order, "title": c.title, "body": c.body}
            for c in pipeline.get("accepted_chapters") or []
        ]
        ws["chapter_pipeline"] = {
            "chapter_calls": pipeline.get("chapter_calls"),
            "failed_orders": pipeline.get("failed_orders"),
        }
    else:
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
    content_defects = find_customer_content_defects(cleaned)
    fidelity = validate_manuscript_outline_fidelity(
        approved_outline=approved_outline,
        manuscript_md=cleaned,
        prompt_outline_titles=prompt_titles,
        token_outline_digest=str(pending.get("outline_digest") or ""),
        current_outline_digest=current_od,
    )
    quality = validate_manuscript_quality(data, manuscript_md=cleaned, book_contract=book_contract)
    apply_quality_to_workspace(data, quality)
    structure_findings = list(fidelity.get("findings") or [])
    defects = list(structure_findings) + list(content_defects) + list(quality.finding_messages)
    chapters = manuscript_to_chapters(cleaned)

    # Record spend for the provider call that already ran. Structurally invalid
    # drafts are never accepted as Awaiting approval.
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
            "structure_ok": bool(fidelity.get("ok")),
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
    ws["manuscript_structure_findings"] = structure_findings
    ws["last_manuscript_generation"] = {
        "ts": _now(),
        "charge_usd": charge,
        "idempotency_key": key,
        "qa_defect_count": len(defects),
        "chapter_count": len(chapters),
        "outline_digest": current_od,
        "provider_input": provider_input,
        "provider_response_chapter_titles": list(fidelity.get("raw_h2_titles") or []),
        "structure_ok": bool(fidelity.get("ok")),
        "quality_status": quality.status,
        "confirmation_token": str(pending.get("confirmation_token") or ""),
    }
    quality_blocked = quality.status != QUALITY_PASS
    if content_defects or not fidelity.get("ok") or quality_blocked:
        data["release_status"] = "FAIL" if (not fidelity.get("ok") or quality.status == QUALITY_FAIL) else ""
        data["release_messages"] = list(defects)
        note = "Approved-outline fidelity FAIL — draft preserved"
        if not structure_findings:
            note = (
                "Manuscript quality FAIL — draft preserved"
                if quality.status == QUALITY_FAIL
                else "Manuscript quality needs correction"
            )
        set_stage_status(ws, "manuscript", STATUS_NEEDS_CORRECTION, note=note)
    else:
        data["release_status"] = ""
        data["release_messages"] = []
        set_stage_status(ws, "manuscript", STATUS_AWAITING, note="Awaiting human approval")

    for later in ("visuals", "cover", "design", "preview", "preflight", "export"):
        if stage_status(ws, later) != STATUS_NOT_STARTED:
            set_stage_status(ws, later, STATUS_NOT_STARTED)

    _recompute_next_action(ws)
    data = sync_document_from_workspace(data)
    doc = build_ebook_document_from_project(data=data)
    doc.manuscript_md = cleaned
    doc.chapters = chapters
    doc.title = str(data.get("title") or doc.title)
    doc.subtitle = str(data.get("subtitle") or doc.subtitle)
    doc.author = author
    if defects or not fidelity.get("ok"):
        doc.release_status = "FAIL"
        doc.release_messages = list(defects)
    data = attach_document_to_data(data, doc, sync_manuscript=True)
    data["ebook_workspace"] = ws

    result = {
        "ok": True,
        "duplicate": False,
        "manuscript_status": stage_status(ws, "manuscript"),
        "qa_findings": defects,
        "structure_findings": structure_findings,
        "structure_ok": bool(fidelity.get("ok")),
        "quality_status": quality.status,
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
        structure_ok=bool(fidelity.get("ok")),
    )
    return {"ok": True, "duplicate": False, "data": data, "result": result}


def execute_correct_manuscript(
    data: dict,
    *,
    confirmation_token: str,
    expected_artifact_id: str,
    expected_revision: int,
    outline_digest_expected: str,
    max_authorized_usd: float,
    idempotency_key: str,
    correct_fn=None,
    correct_chapter_fn=None,
) -> dict:
    """Correct an existing manuscript against the token-bound approved outline.

    Does not repeat research. Requires Needs correction + preserved draft.
    ``correct_fn`` is injectable for tests (zero paid calls). Accepted chapters
    are preserved; only failed chapters are replaced.
    """
    from services.ebook_document import (
        find_customer_content_defects,
        manuscript_to_chapters,
        strip_visual_instructions,
    )
    from services.ebook_manuscript_engine import (
        QUALITY_PASS,
        ParsedChapter,
        apply_quality_to_workspace,
        assemble_manuscript,
        build_book_contract,
        run_chapter_pipeline,
        split_front_chapters_back,
        validate_manuscript_quality,
    )
    from services.ebook_outline_fidelity import (
        normalize_chapter_title,
        validate_manuscript_outline_fidelity,
    )

    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    assert_can_run_stage(ws, "manuscript")
    if stage_status(ws, "manuscript") != STATUS_NEEDS_CORRECTION:
        raise ValueError("Correction requires manuscript status Needs correction.")
    existing = str(data.get("content") or data.get("ebook") or "").strip()
    if not existing:
        raise ValueError("Preserved manuscript draft is required for correction.")

    ledger = ws.setdefault("paid_call_ledger", empty_ledger())
    idem_store = ledger.setdefault("idempotency_keys", {})
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValueError("Idempotency key is required.")
    if key in idem_store:
        prior = idem_store[key]
        return {
            "ok": True,
            "duplicate": True,
            "data": data,
            "result": prior.get("result") or {},
            "workspace_note": "Idempotent replay — no additional paid call.",
        }

    pending = consume_confirmation(data, "correct_manuscript", confirmation_token)
    artifact_id = str(data.get("artifact_id") or data.get("package_id") or "")
    revision = int(data.get("artifact_revision") or 1)
    if str(expected_artifact_id or "") != artifact_id:
        raise ValueError("Stale artifact ID — reopen the project and try again.")
    if int(expected_revision) != revision:
        raise ValueError("Stale artifact revision — reopen the project and try again.")
    current_od = outline_digest(data)
    if str(outline_digest_expected or "") != current_od:
        raise ValueError("Outline changed since the estimate — request a new cost estimate.")
    if str(pending.get("outline_digest") or "") != current_od:
        raise ValueError("Confirmation token outline digest mismatch.")
    if str(pending.get("artifact_id") or "") != artifact_id:
        raise ValueError("Confirmation token was issued for a different artifact.")
    if int(pending.get("artifact_revision") or 0) != revision:
        raise ValueError("Confirmation token was issued for a different revision.")
    current_ms = manuscript_digest(data)
    if str(pending.get("manuscript_digest") or "") != current_ms:
        raise ValueError(
            "Preserved manuscript changed since the estimate — request a new correction estimate."
        )
    current_findings = structural_findings_digest(data)
    if str(pending.get("structural_findings_digest") or "") != current_findings:
        raise ValueError(
            "Structural findings changed since the estimate — request a new correction estimate."
        )
    token_project = pending.get("project_id")
    live_project = data.get("_project_id")
    if token_project is not None and live_project is not None:
        if int(token_project) != int(live_project):
            raise ValueError("Confirmation token was issued for a different project.")

    approved_outline = authoritative_approved_outline(data)
    book_contract = build_book_contract(data)
    pending_book_digest = str(pending.get("book_contract_digest") or "")
    if pending_book_digest and pending_book_digest != book_contract.digest():
        raise ValueError("Book/chapter contract changed since the estimate — request a new correction estimate.")
    auth_max = round(float(max_authorized_usd), 4)
    pending_max = round(float(pending.get("max_authorized_usd") or pending.get("estimated_max_usd") or 0), 4)
    if auth_max <= 0 or abs(auth_max - pending_max) > 1e-9:
        raise ValueError("Authorized charge does not match the pending correction estimate.")
    if auth_max > CORRECTION_AUTH_MAX_USD + 1e-9:
        raise ValueError(
            f"Correction authorization exceeds ${CORRECTION_AUTH_MAX_USD:.2f} maximum."
        )
    spent = round(float(ledger.get("spent_usd") or 0), 4)
    remaining = round(float(ledger.get("remaining_usd") or 0), 4)
    cap = round(float(ledger.get("budget_cap_usd") or DEFAULT_BUDGET_CAP_USD), 4)
    if auth_max > remaining + 1e-9 or spent + auth_max > cap + 1e-9:
        raise ValueError("Insufficient remaining budget for manuscript correction.")

    pending["used"] = True
    ledger["pending_estimate"] = pending
    ledger.setdefault("consumed_tokens", []).append(
        {
            "token": str(pending.get("confirmation_token")),
            "action": "correct_manuscript",
            "ts": _now(),
            "idempotency_key": key,
        }
    )

    research_notes = build_research_notes_for_manuscript(data)
    prompt_titles = prompt_outline_titles_from_notes(research_notes)
    approved_titles = [c["title"] for c in approved_outline]
    if [normalize_chapter_title(t) for t in prompt_titles] != [
        normalize_chapter_title(t) for t in approved_titles
    ]:
        raise ValueError(
            "Correction prompt outline does not match the token-bound approved outline."
        )

    if correct_fn is None and correct_chapter_fn is None:
        from services.ebook import correct_ebook_manuscript as correct_fn

    set_stage_status(ws, "manuscript", STATUS_IN_PROGRESS, note="Correcting manuscript")
    author = str(ws.get("author") or data.get("author_brand") or "").strip()
    prior_quality = validate_manuscript_quality(
        data, manuscript_md=existing, book_contract=book_contract
    )
    failed_orders = [
        int(r["order"])
        for r in prior_quality.chapter_results
        if r.get("status") != QUALITY_PASS
    ]
    if not prior_quality.outline_ok:
        failed_orders = [c.order for c in book_contract.chapters]
    _front, prior_chapters, prior_back = split_front_chapters_back(existing)
    accepted_keep = [
        ch for ch in prior_chapters if ch.order not in set(failed_orders)
    ]

    if correct_chapter_fn is not None:
        pipeline = run_chapter_pipeline(
            book_contract,
            generate_chapter_fn=correct_chapter_fn,
            accepted_chapters=accepted_keep,
            repair_orders=failed_orders,
            back_matter=prior_back,
        )
        manuscript_md = str(pipeline.get("manuscript_md") or "").strip()
        if prior_back and "**disclaimer**" not in manuscript_md.lower():
            manuscript_md = manuscript_md.rstrip() + "\n\n" + prior_back + "\n"
        ws["chapter_pipeline"] = {
            "chapter_calls": pipeline.get("chapter_calls"),
            "failed_orders": pipeline.get("failed_orders"),
            "preserved_orders": [c.order for c in accepted_keep],
        }
    else:
        raw = correct_fn(
            existing_manuscript=existing,
            approved_outline=approved_outline,
            author=author,
            research_notes=research_notes,
            title=str(data.get("title") or ""),
            subtitle=str(data.get("subtitle") or ""),
        )
        if not isinstance(raw, dict):
            raise ValueError("Correction generator returned an invalid payload.")
        manuscript_md = str(raw.get("ebook") or raw.get("content") or "").strip()
        # Preserve accepted chapters when the full-book corrector returns a new book.
        if accepted_keep and prior_quality.outline_ok:
            _nf, new_chs, new_back = split_front_chapters_back(manuscript_md)
            keep_by_order = {c.order: c for c in accepted_keep}
            merged: list[ParsedChapter] = []
            new_by_title = {normalize_chapter_title(c.title): c for c in new_chs}
            for contract in book_contract.chapters:
                if contract.order in keep_by_order:
                    merged.append(keep_by_order[contract.order])
                else:
                    nxt = new_by_title.get(normalize_chapter_title(contract.title))
                    if nxt is None:
                        nxt = ParsedChapter(order=contract.order, title=contract.title, body="")
                    nxt.order = contract.order
                    nxt.title = contract.title
                    merged.append(nxt)
            manuscript_md = assemble_manuscript(
                title=str(data.get("title") or book_contract.title),
                subtitle=str(data.get("subtitle") or book_contract.subtitle),
                author=author,
                chapters=merged,
                disclaimer="",
                sources="",
            )
            back = new_back or prior_back
            if back:
                manuscript_md = manuscript_md.rstrip() + "\n\n" + back + "\n"
    if not manuscript_md:
        raise ValueError("Correction generator returned empty content.")

    cleaned, _removed = strip_visual_instructions(manuscript_md)
    content_defects = find_customer_content_defects(cleaned)
    fidelity = validate_manuscript_outline_fidelity(
        approved_outline=approved_outline,
        manuscript_md=cleaned,
        prompt_outline_titles=prompt_titles,
        token_outline_digest=str(pending.get("outline_digest") or ""),
        current_outline_digest=current_od,
    )
    quality = validate_manuscript_quality(data, manuscript_md=cleaned, book_contract=book_contract)
    apply_quality_to_workspace(data, quality)
    structure_findings = list(fidelity.get("findings") or [])
    defects = list(structure_findings) + list(content_defects) + list(quality.finding_messages)
    chapters = manuscript_to_chapters(cleaned)

    charge = min(auth_max, remaining)
    ledger["spent_usd"] = round(spent + charge, 4)
    ledger["remaining_usd"] = round(cap - float(ledger["spent_usd"]), 4)
    ledger["paid_calls"] = int(ledger.get("paid_calls") or 0) + 1
    ledger.setdefault("calls", []).append(
        {
            "ts": _now(),
            "provider": "openai",
            "purpose": "correct_manuscript",
            "estimated_cost_usd": charge,
            "idempotency_key": key,
            "meta": {
                "outline_digest": current_od,
                "structure_ok": bool(fidelity.get("ok")),
            },
        }
    )
    ledger["pending_estimate"] = None

    # Preserve prior draft under history key; replace working manuscript with correction.
    ws["previous_manuscript_draft"] = existing
    data["content"] = cleaned
    data["ebook"] = cleaned
    ws["manuscript_qa"] = defects
    ws["manuscript_structure_findings"] = structure_findings
    ws["last_manuscript_correction"] = {
        "ts": _now(),
        "charge_usd": charge,
        "idempotency_key": key,
        "structure_ok": bool(fidelity.get("ok")),
        "outline_digest": current_od,
    }
    if defects or not fidelity.get("ok"):
        data["release_status"] = "FAIL"
        data["release_messages"] = list(defects)
        set_stage_status(
            ws,
            "manuscript",
            STATUS_NEEDS_CORRECTION,
            note="Correction still fails outline fidelity",
        )
    else:
        data["release_status"] = ""
        data["release_messages"] = []
        set_stage_status(ws, "manuscript", STATUS_AWAITING, note="Awaiting human approval")

    _recompute_next_action(ws)
    data = sync_document_from_workspace(data)
    doc = build_ebook_document_from_project(data=data)
    doc.manuscript_md = cleaned
    doc.chapters = chapters
    if defects or not fidelity.get("ok"):
        doc.release_status = "FAIL"
        doc.release_messages = list(defects)
    data = attach_document_to_data(data, doc, sync_manuscript=True)
    data["ebook_workspace"] = ws

    result = {
        "ok": True,
        "duplicate": False,
        "manuscript_status": stage_status(ws, "manuscript"),
        "qa_findings": defects,
        "structure_findings": structure_findings,
        "structure_ok": bool(fidelity.get("ok")),
        "charge_usd": charge,
        "spent_usd": ledger.get("spent_usd"),
        "remaining_usd": ledger.get("remaining_usd"),
        "chapter_count": len(chapters),
    }
    idem_store[key] = {"result": result, "ts": _now(), "charge_usd": charge}
    ledger["idempotency_keys"] = idem_store
    _append_history(
        ws,
        "correct_manuscript",
        charge_usd=charge,
        status=stage_status(ws, "manuscript"),
        structure_ok=bool(fidelity.get("ok")),
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

    # Force the user-approved revised 10-chapter titles AND catalog purposes.
    # Never copy a previous outline slot's purpose onto a new title.
    from services.ebook_manuscript_engine import event_photo_catalog_by_title
    from services.ebook_outline_fidelity import normalize_chapter_title as _norm_title

    catalog = event_photo_catalog_by_title()
    revised_o1_chapters = []
    for i, chapter_title in enumerate(REVISED_ACCEPTANCE_OUTLINE_TITLES):
        spec = catalog.get(_norm_title(chapter_title))
        purpose_bullets = [spec.purpose] if spec else [
            f"Cover the approved chapter purpose for: {chapter_title}",
        ]
        revised_o1_chapters.append(
            {
                "n": i + 1,
                "title": chapter_title,
                "bullets": purpose_bullets,
            }
        )
    o1 = dict(o1)
    o1["chapters"] = revised_o1_chapters
    o1["estimated_chapters"] = 10
    o1["name"] = "Journey outline (recommended) — revised 10-chapter approval"
    outline_options = []
    for opt in outlines.get("options") or []:
        if opt.get("id") == "O1":
            outline_options.append(o1)
        else:
            outline_options.append(opt)

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
    ws["outline_options"] = outline_options
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


def upsert_acceptance_project(database_module, *, preserve_live_manuscript: bool = True) -> dict:
    """Create or update the labeled DRAFT acceptance project in Saved Projects.

    ``preserve_live_manuscript`` keeps an existing paid manuscript/ledger when
    reseeding (production). Tests must pass False, which creates an isolated
    temporary project and never overwrites the live LIVE ACCEPTANCE row.
    """
    data = build_acceptance_project_data()

    if not preserve_live_manuscript:
        data["acceptance_marker"] = f"{ACCEPTANCE_MARKER}_TEST"
        data["ebook_workspace"]["marker"] = f"{ACCEPTANCE_MARKER}_TEST"
        return database_module.create_project(
            f"{ACCEPTANCE_PROJECT_NAME} [TEST]",
            "ebook",
            data,
            user_saved=False,
            system_test=True,
            temporary=True,
        )

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
        prev = dict(existing.get("data") or {})
        data["artifact_id"] = prev.get("artifact_id") or data.get("artifact_id")
        data["artifact_revision"] = prev.get("artifact_revision") or 1
        data["artifact_state"] = "DRAFT"

        prev_ws = get_workspace(prev) or {}
        prev_ledger = prev_ws.get("paid_call_ledger") if isinstance(prev_ws, dict) else None
        new_ws = data["ebook_workspace"]
        if isinstance(prev_ledger, dict):
            prev_spent = float(prev_ledger.get("spent_usd") or 0)
            seed_spent = float((new_ws.get("paid_call_ledger") or {}).get("spent_usd") or 0)
            if prev_spent > seed_spent + 1e-9:
                new_ws["paid_call_ledger"] = copy.deepcopy(prev_ledger)
            else:
                merged = dict(new_ws.get("paid_call_ledger") or {})
                for k in ("idempotency_keys", "consumed_tokens", "pending_estimate"):
                    if prev_ledger.get(k) and not merged.get(k):
                        merged[k] = copy.deepcopy(prev_ledger.get(k))
                prev_calls = list(prev_ledger.get("calls") or [])
                seed_calls = list(merged.get("calls") or [])
                extra = [
                    c
                    for c in prev_calls
                    if isinstance(c, dict)
                    and c.get("purpose") in {"generate_manuscript", "correct_manuscript"}
                ]
                if extra:
                    known = {
                        (c.get("ts"), c.get("purpose"), c.get("idempotency_key"))
                        for c in seed_calls
                        if isinstance(c, dict)
                    }
                    for c in extra:
                        key = (c.get("ts"), c.get("purpose"), c.get("idempotency_key"))
                        if key not in known:
                            seed_calls.append(c)
                    merged["calls"] = seed_calls
                new_ws["paid_call_ledger"] = merged

        has_ms = bool(
            prev.get("content")
            or prev.get("ebook")
            or (
                (prev.get("ebook_document") or {})
                if isinstance(prev.get("ebook_document"), dict)
                else {}
            ).get("manuscript_md")
        )
        if has_ms:
            data["content"] = prev.get("content") or prev.get("ebook") or ""
            data["ebook"] = prev.get("ebook") or prev.get("content") or ""
            if isinstance(prev.get("ebook_document"), dict):
                data["ebook_document"] = copy.deepcopy(prev.get("ebook_document"))
            for k in (
                "manuscript_qa",
                "manuscript_structure_findings",
                "last_manuscript_generation",
                "last_manuscript_correction",
                "previous_manuscript_draft",
            ):
                if prev_ws.get(k) is not None:
                    new_ws[k] = copy.deepcopy(prev_ws.get(k))
            prev_ms = (
                (prev_ws.get("rail") or {}).get("manuscript")
                if isinstance(prev_ws.get("rail"), dict)
                else None
            )
            if isinstance(prev_ms, dict) and prev_ms.get("status") not in {
                None,
                STATUS_NOT_STARTED,
            }:
                set_stage_status(
                    new_ws,
                    "manuscript",
                    str(prev_ms.get("status")),
                    note=str(prev_ms.get("note") or "Preserved manuscript draft"),
                )
            data["release_status"] = prev.get("release_status") or data.get("release_status") or ""
            data["release_messages"] = list(prev.get("release_messages") or [])
            _recompute_next_action(new_ws)

        data["ebook_workspace"] = new_ws

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
