"""Ebook Project workspace: stage rail, approvals, invalidation, cost ledger.

Server-authoritative. UI may display state but cannot invent approvals or PASS.
Paid actions require a prior estimate + explicit confirmation token.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
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
ACCEPTANCE_EXPORT_DIR = (
    Path(os.environ.get("FACTORY_EXPORTS_DIR") or (ROOT / "exports"))
    / "ebook_live_acceptance_lonnie_event_photo"
)
ACCEPTANCE_PROJECT_NAME = "LIVE ACCEPTANCE — EVENT PHOTOGRAPHY EBOOK"
ACCEPTANCE_MARKER = "live_acceptance_event_photography_ebook_v1"
# Frozen live manuscript project — never a seed target.
FROZEN_LIVE_EBOOK_PROJECT_ID = 2472

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


def current_preview_digest(data: dict | None) -> str:
    ident = (data or {}).get("ebook_export_identity")
    if not isinstance(ident, dict):
        ident = {}
    return str(ident.get("preview_digest") or ident.get("pdf_sha256") or "").strip()


def preview_opened_matches_current(data: dict | None) -> bool:
    """True only when the stored opened record matches the current preview digest."""
    data = data or {}
    ws = get_workspace(data) or {}
    rec = ws.get("preview_opened") if isinstance(ws.get("preview_opened"), dict) else {}
    current = current_preview_digest(data)
    return bool(current) and str(rec.get("digest") or "").strip() == current


def record_preview_opened(data: dict) -> dict:
    """Record that the current stored preview was actually opened."""
    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    html = str(data.get("ebook_preview_html") or data.get("preview_html") or "")
    digest = current_preview_digest(data)
    if not html.strip():
        raise ValueError("Build preview before opening it.")
    if not digest:
        raise ValueError("Preview identity is missing. Rebuild preview before opening it.")
    ws["preview_opened"] = {"digest": digest, "opened_at": _now()}
    _append_history(ws, "preview_opened", digest=digest)
    _recompute_next_action(ws)
    return sync_document_from_workspace(data)


def revoke_unviewed_preview_approval(data: dict) -> dict:
    """If preview is approved without a matching opened record, return it to review."""
    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    if not is_approved(ws, "preview"):
        return data
    if preview_opened_matches_current(data):
        return data
    set_stage_status(
        ws,
        "preview",
        STATUS_AWAITING,
        note="Preview approval revoked: full preview was not opened",
    )
    cleared = invalidate_after(
        ws, "preview", reason="Preview approval revoked: no matching opened record"
    )
    if "preflight" in cleared or "export" in cleared:
        data["export_ready"] = False
        data["release_status"] = ""
    _append_history(ws, "revoke_preview_approval", reason="no_preview_opened")
    _recompute_next_action(ws)
    return sync_document_from_workspace(data)


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
CHAPTER_UNIT_USD = 0.15
RESEARCH_AUTH_MAX_USD = 0.50


def correction_auth_max_usd(ledger: dict | None) -> float:
    """Per-confirmation correction ceiling.

    Default remains $0.75. After an explicit user budget-cap authorization,
    remaining authorized work may use the project's remaining budget.
    """
    ledger = ledger or {}
    remaining = round(float(ledger.get("remaining_usd") or 0), 4)
    if ledger.get("budget_authorizations"):
        return remaining
    return round(float(CORRECTION_AUTH_MAX_USD), 4)


ONESHOT_WORKSPACE_BLOCKED = (
    "One-shot workspace generation is blocked. "
    "Workspace ebooks must use the chapter pipeline "
    "(exactly one approved chapter per provider request)."
)


def chapter_acceptance_digest(order: int, title: str, body: str) -> str:
    """Stable digest of one preserved chapter (order + title + body)."""
    return _sha(
        {
            "order": int(order or 0),
            "title": str(title or ""),
            "body": str(body or ""),
        }
    )


def accepted_chapter_digests(data: dict) -> list[str]:
    """Stable digests of preserved accepted chapters (resume/idempotency binding)."""
    ws = get_workspace(data) or {}
    out: list[str] = []
    for item in ws.get("accepted_chapters") or []:
        if not isinstance(item, dict):
            continue
        out.append(
            chapter_acceptance_digest(
                int(item.get("order") or 0),
                str(item.get("title") or ""),
                str(item.get("body") or ""),
            )
        )
    return out


def chapter_pipeline_stats(data: dict) -> dict[str, Any]:
    """Accepted vs pending chapter counts for estimates and the confirmation UI."""
    from services.ebook_manuscript_engine import build_book_contract

    book = build_book_contract(data)
    ws = get_workspace(data) or {}
    accepted = [
        c
        for c in (ws.get("accepted_chapters") or [])
        if isinstance(c, dict) and str(c.get("body") or "").strip()
    ]
    accepted_orders = {int(c.get("order") or 0) for c in accepted}
    n_total = len(book.chapters)
    n_accepted = len(accepted_orders)
    n_pending = max(0, n_total - n_accepted)
    return {
        "accepted_chapter_count": n_accepted,
        "pending_chapter_count": n_pending,
        "total_chapter_count": n_total,
        "per_chapter_max_usd": CHAPTER_UNIT_USD,
        "accepted_chapter_digests": accepted_chapter_digests(data),
        "resume_from_order": min(
            (c.order for c in book.chapters if c.order not in accepted_orders),
            default=None,
        ),
    }


def reconcile_validated_preserved_chapters(data: dict) -> dict:
    """Accept preserved manuscript chapters that now PASS, without a provider call.

    Used when a validator repair makes already-written chapter bytes PASS.
    Copies bodies byte-for-byte from the current manuscript. Does not generate,
    rewrite, charge, or mutate frozen project #2472. Already-accepted chapters
    are kept unchanged.
    """
    from services.ebook_manuscript_engine import (
        build_book_contract,
        split_front_chapters_back,
        validate_chapter,
    )
    from services.ebook_outline_fidelity import normalize_chapter_title

    data = ensure_workspace(data)
    project_id = data.get("_project_id")
    if project_id is not None and int(project_id) == FROZEN_LIVE_EBOOK_PROJECT_ID:
        return data
    md = str(data.get("content") or data.get("ebook") or "")
    if not md.strip():
        return data
    book = build_book_contract(data)
    _front, parsed_chapters, _back = split_front_chapters_back(md)
    by_order = {int(ch.order): ch for ch in parsed_chapters}
    ws = data["ebook_workspace"]
    existing_by_order: dict[int, dict] = {}
    for item in ws.get("accepted_chapters") or []:
        if not isinstance(item, dict):
            continue
        if not str(item.get("body") or "").strip():
            continue
        existing_by_order[int(item.get("order") or 0)] = {
            "order": int(item.get("order") or 0),
            "title": str(item.get("title") or ""),
            "body": str(item.get("body") or ""),
        }
    accepted_out: list[dict] = []
    promoted: list[dict] = []
    for contract in book.chapters:
        prev = existing_by_order.get(int(contract.order))
        if prev:
            accepted_out.append(prev)
            continue
        parsed = by_order.get(int(contract.order))
        if parsed is None:
            continue
        if int(parsed.order) != int(contract.order):
            continue
        if normalize_chapter_title(parsed.title) != normalize_chapter_title(contract.title):
            continue
        if str(parsed.title).strip() != str(contract.title).strip():
            continue
        body = str(parsed.body or "")
        content_digest = chapter_acceptance_digest(parsed.order, parsed.title, body)
        contract_aligned_digest = chapter_acceptance_digest(contract.order, contract.title, body)
        if content_digest != contract_aligned_digest:
            continue
        findings = validate_chapter(parsed, contract, book=book)
        if findings:
            continue
        accepted_out.append(
            {
                "order": int(contract.order),
                "title": str(contract.title),
                "body": body,
            }
        )
        promoted.append(
            {
                "order": int(contract.order),
                "title": str(contract.title),
                "digest": content_digest,
                "contract_digest": contract.digest(),
            }
        )
    accepted_out.sort(key=lambda row: int(row["order"]))
    if promoted:
        ws["accepted_chapters"] = accepted_out
        record = {
            "paid_call": False,
            "provider_called": False,
            "promoted_orders": [row["order"] for row in promoted],
            "promoted": promoted,
            "accepted_orders": [row["order"] for row in accepted_out],
        }
        ws["validated_chapter_reconciliation"] = record
        _append_history(ws, "reconcile_validated_chapters", **record)
    data["ebook_workspace"] = ws
    return data


def reconcile_validated_preserved_chapters_into_project(database_module, project_id: int) -> dict:
    """Persist local PASS reconciliation. Never mutates project #2472 or spend."""
    pid = int(project_id)
    if pid == FROZEN_LIVE_EBOOK_PROJECT_ID:
        raise ValueError(
            f"Refusing to modify frozen live project #{FROZEN_LIVE_EBOOK_PROJECT_ID}."
        )
    project = database_module.get_project(pid)
    if not project:
        raise ValueError(f"Project #{pid} was not found.")
    data = dict(project.get("data") or {})
    data["_project_id"] = pid
    ws = get_workspace(data) or {}
    ledger = ws.get("paid_call_ledger") or {}
    spent_before = round(float(ledger.get("spent_usd") or 0), 4)
    remaining_before = round(float(ledger.get("remaining_usd") or 0), 4)
    paid_before = int(ledger.get("paid_calls") or 0)
    calls_before = list(ledger.get("calls") or [])
    content_before = str(data.get("content") or "")
    ebook_before = str(data.get("ebook") or "")
    data = reconcile_validated_preserved_chapters(data)
    ledger_after = (data.get("ebook_workspace") or {}).get("paid_call_ledger") or {}
    if str(data.get("content") or "") != content_before or str(data.get("ebook") or "") != ebook_before:
        raise ValueError("Reconciliation must not rewrite manuscript text.")
    if (
        round(float(ledger_after.get("spent_usd") or 0), 4) != spent_before
        or round(float(ledger_after.get("remaining_usd") or 0), 4) != remaining_before
        or int(ledger_after.get("paid_calls") or 0) != paid_before
        or list(ledger_after.get("calls") or []) != calls_before
    ):
        raise ValueError("Reconciliation must not charge or alter the paid-call ledger.")
    updated = database_module.update_project(pid, None, data)
    if not updated:
        raise ValueError(f"Failed to update project #{pid}.")
    return updated


def sanitize_preserved_chapter_content(data: dict, order: int) -> dict:
    """Deterministic $0 cleanup of leaked production labels in one preserved chapter."""
    from services.ebook_document import sanitize_leaked_production_labels
    from services.ebook_manuscript_engine import split_front_chapters_back

    data = ensure_workspace(data)
    project_id = data.get("_project_id")
    if project_id is not None and int(project_id) == FROZEN_LIVE_EBOOK_PROJECT_ID:
        return data
    md = str(data.get("content") or data.get("ebook") or "")
    if not md.strip():
        return data
    _front, chapters, _back = split_front_chapters_back(md)
    target = next((ch for ch in chapters if int(ch.order) == int(order)), None)
    if target is None:
        return data
    cleaned, removed = sanitize_leaked_production_labels(target.body)
    if cleaned == target.body or not removed:
        return data
    if md.count(target.body) != 1:
        raise ValueError(
            f"Refusing to sanitize Chapter {order}: manuscript body is not uniquely located."
        )
    new_md = md.replace(target.body, cleaned, 1)
    ebook = str(data.get("ebook") or "")
    data["content"] = new_md
    if ebook == md or not ebook.strip():
        data["ebook"] = new_md
    elif ebook.count(target.body) == 1:
        data["ebook"] = ebook.replace(target.body, cleaned, 1)
    ws = data["ebook_workspace"]
    record = {
        "paid_call": False,
        "provider_called": False,
        "order": int(order),
        "removed": removed,
    }
    ws["production_label_sanitization"] = record
    _append_history(ws, "sanitize_leaked_production_labels", **record)
    data["ebook_workspace"] = ws
    return data


def sanitize_and_reconcile_preserved_chapter_into_project(
    database_module,
    project_id: int,
    order: int,
) -> dict:
    """Apply local leaked-label cleanup and promote the chapter only if it PASSes."""
    from services.ebook_manuscript_engine import (
        build_book_contract,
        split_front_chapters_back,
        validate_chapter,
    )

    pid = int(project_id)
    if pid == FROZEN_LIVE_EBOOK_PROJECT_ID:
        raise ValueError(
            f"Refusing to modify frozen live project #{FROZEN_LIVE_EBOOK_PROJECT_ID}."
        )
    project = database_module.get_project(pid)
    if not project:
        raise ValueError(f"Project #{pid} was not found.")
    data = dict(project.get("data") or {})
    data["_project_id"] = pid
    ws = get_workspace(data) or {}
    ledger = ws.get("paid_call_ledger") or {}
    spent_before = round(float(ledger.get("spent_usd") or 0), 4)
    remaining_before = round(float(ledger.get("remaining_usd") or 0), 4)
    paid_before = int(ledger.get("paid_calls") or 0)
    calls_before = list(ledger.get("calls") or [])
    accepted_before = [
        {
            "order": int(item.get("order") or 0),
            "title": str(item.get("title") or ""),
            "body": str(item.get("body") or ""),
        }
        for item in (ws.get("accepted_chapters") or [])
        if isinstance(item, dict) and int(item.get("order") or 0) != int(order)
    ]
    data = sanitize_preserved_chapter_content(data, order)
    book = build_book_contract(data)
    md = str(data.get("content") or "")
    _front, chapters, _back = split_front_chapters_back(md)
    parsed = next((ch for ch in chapters if int(ch.order) == int(order)), None)
    contract = next((c for c in book.chapters if int(c.order) == int(order)), None)
    findings = []
    if parsed is not None and contract is not None:
        findings = validate_chapter(parsed, contract, book=book)
    if not findings:
        data = reconcile_validated_preserved_chapters(data)
    ledger_after = (data.get("ebook_workspace") or {}).get("paid_call_ledger") or {}
    if (
        round(float(ledger_after.get("spent_usd") or 0), 4) != spent_before
        or round(float(ledger_after.get("remaining_usd") or 0), 4) != remaining_before
        or int(ledger_after.get("paid_calls") or 0) != paid_before
        or list(ledger_after.get("calls") or []) != calls_before
    ):
        raise ValueError("Local sanitization must not charge or alter the paid-call ledger.")
    accepted_after = {
        int(item.get("order") or 0): str(item.get("body") or "")
        for item in ((data.get("ebook_workspace") or {}).get("accepted_chapters") or [])
        if isinstance(item, dict)
    }
    for prev in accepted_before:
        if accepted_after.get(prev["order"]) != prev["body"]:
            raise ValueError(
                f"Local sanitization must not alter accepted Chapter {prev['order']}."
            )
    data["ebook_workspace"]["local_chapter_sanitization_result"] = {
        "order": int(order),
        "passed": not findings,
        "finding_codes": [getattr(f, "code", "") for f in findings],
        "paid_call": False,
    }
    updated = database_module.update_project(pid, None, data)
    if not updated:
        raise ValueError(f"Failed to update project #{pid}.")
    return updated


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
    if project.get("id") is not None:
        data["_project_id"] = project.get("id")
    data = reconcile_validated_preserved_chapters(data)
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
    design_view = _design_view(data)
    if not isinstance(design_view, dict):
        design_view = {}
    cover_obj = design_view.get("cover")
    if not isinstance(cover_obj, dict):
        cover_obj = {}
        design_view["cover"] = cover_obj
    photo = cover_obj.get("photo") if isinstance(cover_obj.get("photo"), dict) else {}
    from services.ebook_photo_cover import (
        GUIDED_STEP_CHOOSE_PHOTO,
        GUIDED_STEP_LABELS,
        resolve_cover_guided_step,
    )

    cover_guided_step = str(photo.get("workflow_step") or "") or resolve_cover_guided_step(
        has_valid_photo=False,
        passing_count=0,
    )
    cover_obj["guided_step"] = photo.get("guided_step") if photo.get("guided_step") is not None else 1
    cover_obj["guided_step_id"] = cover_guided_step
    cover_obj["guided_step_label"] = (
        photo.get("guided_step_label")
        or GUIDED_STEP_LABELS.get(cover_guided_step)
        or GUIDED_STEP_LABELS[GUIDED_STEP_CHOOSE_PHOTO]
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
            "cover_enabled": is_approved(ws, "visuals") and _visuals_ready(data),
            "design_enabled": is_approved(ws, "cover") and quality_status == QUALITY_PASS,
            "preview_enabled": is_approved(ws, "design")
            and is_approved(ws, "visuals")
            and _visuals_ready(data),
            "approve_preview_enabled": is_approved(ws, "design")
            and is_approved(ws, "visuals")
            and _visuals_ready(data)
            and not is_approved(ws, "preview")
            and bool(data.get("ebook_preview_html") or data.get("preview_html"))
            and preview_opened_matches_current(data),
            "preflight_enabled": is_approved(ws, "preview") and _visuals_ready(data),
            "export_enabled": str(data.get("release_status") or "").upper() == "PASS"
            and data.get("export_ready") is True
            and str((data.get("ebook_design_preflight") or {}).get("status") or "").upper() == "PASS"
            and is_approved(ws, "preflight")
            and _visuals_ready(data),
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
            "correction_estimate_usd": min(
                round(max(int(chapter_pipeline_stats(data).get("pending_chapter_count") or 1), 1) * CHAPTER_UNIT_USD, 4),
                correction_auth_max_usd(ledger),
                round(float(ledger.get("remaining_usd") or 0), 4),
            ),
            "remaining_usd": ledger.get("remaining_usd"),
        },
        "outline_digest": outline_digest(data),
        "design": design_view,
        "cover_guided_step": cover_guided_step,
        "cover_guided_step_label": cover_obj.get("guided_step_label") or "",
    }


def _visuals_ready(data: dict) -> bool:
    try:
        from services.ebook_visual_pipeline import visuals_are_ready

        return visuals_are_ready(data)
    except Exception:
        return False


def _design_view(data: dict) -> dict:
    from services.ebook_design_workspace import design_public_view

    try:
        return design_public_view(data, project_id=data.get("_project_id"))
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


def approve_stage(
    data: dict,
    stage: str,
    *,
    choice_id: str | None = None,
    preview_digest: str | None = None,
) -> dict:
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
        from services.ebook_visual_pipeline import approve_visual_plan

        md = str(data.get("content") or data.get("ebook") or "")
        quality = validate_manuscript_quality(data, manuscript_md=md)
        if quality.status != QUALITY_PASS:
            raise ValueError("Only a manuscript-quality PASS may enter visuals or design.")
        return approve_visual_plan(data)

    elif stage == "cover":
        if not is_approved(ws, "visuals"):
            raise ValueError("Approve visuals before the cover.")
        from services.ebook_visual_pipeline import visuals_are_ready

        if not visuals_are_ready(data):
            raise ValueError("Visuals must have valid local assets before the cover.")
        cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None
        if not cover:
            raise ValueError("Upload or select a cover photograph before approving.")
        from services.ebook_photo_cover import PhotoCoverError, assert_photo_cover_approvable

        try:
            assert_photo_cover_approvable(data, project_id=data.get("_project_id"))
        except PhotoCoverError as exc:
            raise ValueError(str(exc)) from exc
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
        from services.ebook_preview_review import STALE_PREVIEW_MESSAGE
        from services.quality.artifact_state import ArtifactState, ArtifactStateError, resolve_artifact_state

        state = resolve_artifact_state(data)
        if state is ArtifactState.LOCKED:
            raise ArtifactStateError(
                "LOCKED artifact cannot approve preview. Locked products cannot be changed."
            )
        if is_approved(ws, "preview"):
            raise ValueError("Preview is already approved.")
        if not is_approved(ws, "design"):
            raise ValueError("Approve design before preview.")
        from services.ebook_visual_pipeline import validate_visual_readiness, visuals_are_ready

        if not is_approved(ws, "visuals") or not visuals_are_ready(data):
            raise ValueError("Approve visuals with valid local assets before preview approval.")
        html = str(data.get("ebook_preview_html") or data.get("preview_html") or "")
        if not html:
            raise ValueError("Build preview before approving.")
        html_report = validate_visual_readiness(data, html=html)
        if not html_report.ok:
            raise ValueError(
                "Preview HTML does not contain the approved visual assets. Rebuild preview after visuals."
            )
        supplied = str(preview_digest or "").strip()
        current = current_preview_digest(data)
        if supplied and current and supplied != current:
            raise ValueError(STALE_PREVIEW_MESSAGE)
        if not preview_opened_matches_current(data):
            raise ValueError("Open the full preview before approving.")
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


def authorize_workspace_budget_cap(
    data: dict,
    new_cap_usd: float,
    *,
    reason: str = "",
    authorized_by: str = "user",
) -> dict:
    """Raise the hard project cap without spending or changing manuscript state.

    Records user authorization metadata on the ledger. Does not create a paid
    call, change spend, artifact identity, accepted chapters, or findings.
    """
    data = ensure_workspace(dict(data or {}))
    project_id = data.get("_project_id")
    if project_id is not None and int(project_id) == FROZEN_LIVE_EBOOK_PROJECT_ID:
        raise ValueError(
            f"Refusing to modify frozen live project #{FROZEN_LIVE_EBOOK_PROJECT_ID}."
        )
    ws = data["ebook_workspace"]
    ledger = ws.setdefault("paid_call_ledger", empty_ledger())
    old_cap = round(float(ledger.get("budget_cap_usd") or DEFAULT_BUDGET_CAP_USD), 4)
    spent = round(float(ledger.get("spent_usd") or 0), 4)
    new_cap = round(float(new_cap_usd), 4)
    if new_cap + 1e-9 < spent:
        raise ValueError(
            f"New cap ${new_cap:.2f} is below already-spent ${spent:.2f}."
        )
    if new_cap + 1e-9 < old_cap:
        raise ValueError(
            f"Budget authorization can only raise the cap (old ${old_cap:.2f})."
        )
    remaining = round(new_cap - spent, 4)
    ledger["budget_cap_usd"] = new_cap
    ledger["spent_usd"] = spent
    ledger["remaining_usd"] = remaining
    record = {
        "ts": _now(),
        "event": "authorize_budget_cap",
        "old_cap_usd": old_cap,
        "new_cap_usd": new_cap,
        "spent_usd": spent,
        "remaining_usd": remaining,
        "paid_call": False,
        "reason": str(reason or "User authorized additional remaining chapter work"),
        "authorized_by": str(authorized_by or "user"),
    }
    auths = list(ledger.get("budget_authorizations") or [])
    auths.append(record)
    ledger["budget_authorizations"] = auths
    _append_history(
        ws,
        "authorize_budget_cap",
        old_cap_usd=old_cap,
        new_cap_usd=new_cap,
        spent_usd=spent,
        remaining_usd=remaining,
        paid_call=False,
        reason=record["reason"],
    )
    data["ebook_workspace"] = ws
    return data


def authorize_workspace_budget_into_project(
    database_module,
    project_id: int,
    new_cap_usd: float,
    *,
    reason: str = "",
) -> dict:
    """Persist a user budget-cap authorization. Never mutates project #2472."""
    pid = int(project_id)
    if pid == FROZEN_LIVE_EBOOK_PROJECT_ID:
        raise ValueError(
            f"Refusing to modify frozen live project #{FROZEN_LIVE_EBOOK_PROJECT_ID}."
        )
    project = database_module.get_project(pid)
    if not project:
        raise ValueError(f"Project #{pid} was not found.")
    data = dict(project.get("data") or {})
    data["_project_id"] = pid
    data = authorize_workspace_budget_cap(
        data,
        new_cap_usd,
        reason=reason,
        authorized_by="user",
    )
    updated = database_module.update_project(pid, None, data)
    if not updated:
        raise ValueError(f"Failed to update project #{pid}.")
    return updated


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
    if action == "run_research":
        if is_approved(ws, "research"):
            raise ValueError(
                "Research is already approved. Edit the research to revise it instead."
            )
        if stage_status(ws, "research") == STATUS_AWAITING and (
            (ws.get("research_payload") or {}).get("summary")
        ):
            raise ValueError(
                "Research already ran and awaits your approval. Approve it or edit it first."
            )
    if action == "correct_manuscript":
        assert_can_run_stage(ws, "manuscript")
        if stage_status(ws, "manuscript") != STATUS_NEEDS_CORRECTION:
            raise ValueError("Correction is only available when manuscript status is Needs correction.")
        if not (data.get("content") or data.get("ebook")):
            raise ValueError("Correction requires the preserved manuscript draft.")
        data = reconcile_validated_preserved_chapters(data)
        ws = data["ebook_workspace"]
    ledger = ws.setdefault("paid_call_ledger", empty_ledger())
    spent_before = round(float(ledger.get("spent_usd") or 0), 4)
    remaining_before = round(float(ledger.get("remaining_usd") or 0), 4)
    paid_calls_before = int(ledger.get("paid_calls") or 0)
    calls_before = list(ledger.get("calls") or [])
    stats = chapter_pipeline_stats(data)
    n_pending = int(stats["pending_chapter_count"] or 0)
    if action in {"generate_manuscript", "correct_manuscript"}:
        estimate = round(max(n_pending, 1) * CHAPTER_UNIT_USD, 4)
        if action == "generate_manuscript":
            estimate = min(estimate, MANUSCRIPT_AUTH_MAX_USD)
        else:
            estimate = min(estimate, correction_auth_max_usd(ledger))
    else:
        estimate = round(float(spec["default_estimate_usd"]), 4)
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
        "accepted_chapter_digests": list(stats.get("accepted_chapter_digests") or []),
        "per_chapter_max_usd": CHAPTER_UNIT_USD,
        "accepted_chapter_count": int(stats.get("accepted_chapter_count") or 0),
        "pending_chapter_count": (
            n_pending if action in {"generate_manuscript", "correct_manuscript"} else None
        ),
        "max_total_usd": estimate,
        "resume_from_order": stats.get("resume_from_order"),
        "failed_chapter_order": stats.get("resume_from_order"),
        "used": False,
        "confirmation_required": True,
        "estimate_cost_usd": 0.0,
        "estimate_is_free": True,
        "expires_note": (
            "This estimate costs $0. No provider is called. "
            "Confirmation required before any paid call. Opening this page does not spend."
        ),
    }
    ledger["pending_estimate"] = pending
    if (
        round(float(ledger.get("spent_usd") or 0), 4) != spent_before
        or round(float(ledger.get("remaining_usd") or 0), 4) != remaining_before
        or int(ledger.get("paid_calls") or 0) != paid_calls_before
        or list(ledger.get("calls") or []) != calls_before
        or pending.get("used") is True
    ):
        raise ValueError("Estimate issuance must not charge, call a provider, or mark a token used.")
    _append_history(ws, "estimate", action=action, estimated_max_usd=estimate, estimate_cost_usd=0.0)
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
    data = ensure_workspace(data)
    ledger = data["ebook_workspace"].setdefault("paid_call_ledger", empty_ledger())
    spent_before = round(float(ledger.get("spent_usd") or 0), 4)
    remaining_before = round(float(ledger.get("remaining_usd") or 0), 4)
    paid_calls_before = int(ledger.get("paid_calls") or 0)
    calls_before = list(ledger.get("calls") or [])
    data = clear_pending_estimate(data)
    ledger = data["ebook_workspace"].setdefault("paid_call_ledger", empty_ledger())
    if (
        round(float(ledger.get("spent_usd") or 0), 4) != spent_before
        or round(float(ledger.get("remaining_usd") or 0), 4) != remaining_before
        or int(ledger.get("paid_calls") or 0) != paid_calls_before
        or list(ledger.get("calls") or []) != calls_before
    ):
        raise ValueError("Cancel estimate must not charge.")
    _append_history(data["ebook_workspace"], "cancel_estimate")
    return data


def execute_run_research(
    data: dict,
    *,
    confirmation_token: str,
    expected_artifact_id: str,
    expected_revision: int,
    max_authorized_usd: float,
    idempotency_key: str,
    research_fn=None,
) -> dict:
    """Server-authoritative topic research after explicit cost confirmation.

    Mirrors the manuscript flow: estimate (free) -> confirm -> execute.
    ``research_fn`` is injectable for tests (zero paid calls). The default
    engine performs one web search plus one synthesis call and reports how
    many provider requests actually ran; only those are charged.
    """
    from services.ebook_research_engine import (
        RESEARCH_FAILED_MESSAGE,
        RESEARCH_UNIT_USD,
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
    if is_approved(ws, "research"):
        raise ValueError("Research is already approved. Edit the research to revise it instead.")
    if stage_status(ws, "research") == STATUS_AWAITING and (
        (ws.get("research_payload") or {}).get("summary")
    ):
        raise ValueError("Research already ran and awaits your approval. Approve it or edit it first.")

    pending = consume_confirmation(data, "run_research", confirmation_token)

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

    auth_max = round(float(max_authorized_usd), 4)
    pending_max = round(
        float(pending.get("max_authorized_usd") or pending.get("estimated_max_usd") or 0), 4
    )
    if auth_max <= 0:
        raise ValueError("Maximum authorized charge must be positive.")
    if abs(auth_max - pending_max) > 1e-9:
        raise ValueError("Authorized charge does not match the pending estimate.")
    if auth_max > RESEARCH_AUTH_MAX_USD + 1e-9:
        raise ValueError(
            f"Research authorization exceeds ${RESEARCH_AUTH_MAX_USD:.2f} maximum."
        )

    spent = round(float(ledger.get("spent_usd") or 0), 4)
    remaining = round(float(ledger.get("remaining_usd") or 0), 4)
    cap = round(float(ledger.get("budget_cap_usd") or DEFAULT_BUDGET_CAP_USD), 4)
    if auth_max > remaining + 1e-9 or spent + auth_max > cap + 1e-9:
        raise ValueError("Insufficient remaining budget for research.")

    pending["used"] = True
    ledger["pending_estimate"] = pending
    ledger.setdefault("consumed_tokens", []).append(
        {
            "token": str(pending.get("confirmation_token")),
            "action": "run_research",
            "ts": _now(),
            "idempotency_key": key,
        }
    )

    if research_fn is None:
        from services.ebook_research_engine import run_topic_research as research_fn

    set_stage_status(ws, "research", STATUS_IN_PROGRESS, note="Running research")
    topic = str(ws.get("topic") or data.get("title") or "").strip()
    payload = research_fn(
        topic=topic,
        audience=str(ws.get("audience") or ""),
        outcome=str(ws.get("outcome") or ""),
    ) or {}

    summary = str(payload.get("summary") or "").strip()
    findings = [str(x).strip() for x in list(payload.get("key_findings") or []) if str(x).strip()]
    if not summary or len(findings) < 3:
        raise ValueError(RESEARCH_FAILED_MESSAGE)

    paid_calls = max(0, int(payload.get("paid_calls") or 0))
    charge = round(min(float(RESEARCH_UNIT_USD), auth_max, remaining), 4) if paid_calls else 0.0
    ledger["spent_usd"] = round(spent + charge, 4)
    ledger["remaining_usd"] = round(cap - float(ledger["spent_usd"]), 4)
    ledger["paid_calls"] = int(ledger.get("paid_calls") or 0) + paid_calls
    ledger.setdefault("calls", []).append(
        {
            "ts": _now(),
            "provider": "tavily+openai",
            "purpose": "run_research",
            "estimated_cost_usd": charge,
            "idempotency_key": key,
            "meta": {
                "topic": topic,
                "live_search": bool(payload.get("live_search")),
                "provider_requests": paid_calls,
                "artifact_id": artifact_id,
                "artifact_revision": revision,
            },
        }
    )
    ledger["pending_estimate"] = None

    data = save_research(
        data,
        {
            "summary": summary,
            "key_findings": findings,
            "notes_sections": dict(payload.get("notes_sections") or {}),
            "source_urls": list(payload.get("source_urls") or []),
            "topic": topic,
        },
        mark_awaiting=True,
    )
    ws = data["ebook_workspace"]
    result = {
        "research_status": "awaiting_approval",
        "live_search": bool(payload.get("live_search")),
        "provider_requests": paid_calls,
        "charged_usd": charge,
        "key_findings_count": len(findings),
    }
    idem_store[key] = {"result": result, "ts": _now()}
    _append_history(ws, "run_research", charged_usd=charge, provider_requests=paid_calls)
    return {"ok": True, "duplicate": False, "data": data, "result": result}


def _consume_confirmed_simple_action(
    data: dict,
    *,
    action: str,
    auth_cap_usd: float,
    confirmation_token: str,
    expected_artifact_id: str,
    expected_revision: int,
    max_authorized_usd: float,
    idempotency_key: str,
) -> dict:
    """Shared confirm/validate/mark-used step for simple paid stage actions.

    Returns a context dict, or {"duplicate": True, "result": ...} for an
    idempotent replay. Raises ValueError on any mismatch. Never charges.
    """
    ws = data["ebook_workspace"]
    ledger = ws.setdefault("paid_call_ledger", empty_ledger())
    idem_store = ledger.setdefault("idempotency_keys", {})
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValueError("Idempotency key is required.")
    if key in idem_store:
        return {"duplicate": True, "result": (idem_store[key] or {}).get("result") or {}}

    pending = consume_confirmation(data, action, confirmation_token)

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

    auth_max = round(float(max_authorized_usd), 4)
    pending_max = round(
        float(pending.get("max_authorized_usd") or pending.get("estimated_max_usd") or 0), 4
    )
    if auth_max <= 0:
        raise ValueError("Maximum authorized charge must be positive.")
    if abs(auth_max - pending_max) > 1e-9:
        raise ValueError("Authorized charge does not match the pending estimate.")
    if auth_max > float(auth_cap_usd) + 1e-9:
        raise ValueError(f"Authorization exceeds ${float(auth_cap_usd):.2f} maximum for this action.")

    spent = round(float(ledger.get("spent_usd") or 0), 4)
    remaining = round(float(ledger.get("remaining_usd") or 0), 4)
    cap = round(float(ledger.get("budget_cap_usd") or DEFAULT_BUDGET_CAP_USD), 4)
    if auth_max > remaining + 1e-9 or spent + auth_max > cap + 1e-9:
        raise ValueError("Insufficient remaining budget for this action.")

    pending["used"] = True
    ledger["pending_estimate"] = pending
    ledger.setdefault("consumed_tokens", []).append(
        {
            "token": str(pending.get("confirmation_token")),
            "action": action,
            "ts": _now(),
            "idempotency_key": key,
        }
    )
    return {
        "ledger": ledger,
        "idem_store": idem_store,
        "key": key,
        "auth_max": auth_max,
        "spent": spent,
        "remaining": remaining,
        "cap": cap,
        "artifact_id": artifact_id,
        "revision": revision,
    }


def _charge_simple_action(
    ctx: dict,
    *,
    purpose: str,
    unit_usd: float,
    paid_calls: int,
    meta: dict,
) -> float:
    """Record the charge for provider calls that actually ran. Returns charge."""
    ledger = ctx["ledger"]
    charge = (
        round(min(float(unit_usd), float(ctx["auth_max"]), float(ctx["remaining"])), 4)
        if paid_calls
        else 0.0
    )
    ledger["spent_usd"] = round(float(ctx["spent"]) + charge, 4)
    ledger["remaining_usd"] = round(float(ctx["cap"]) - float(ledger["spent_usd"]), 4)
    ledger["paid_calls"] = int(ledger.get("paid_calls") or 0) + int(paid_calls)
    ledger.setdefault("calls", []).append(
        {
            "ts": _now(),
            "provider": "openai" if purpose != "run_research" else "tavily+openai",
            "purpose": purpose,
            "estimated_cost_usd": charge,
            "idempotency_key": ctx["key"],
            "meta": dict(meta or {}),
        }
    )
    ledger["pending_estimate"] = None
    return charge


def execute_generate_title_options(
    data: dict,
    *,
    confirmation_token: str,
    expected_artifact_id: str,
    expected_revision: int,
    max_authorized_usd: float,
    idempotency_key: str,
    titles_fn=None,
) -> dict:
    """Server-authoritative title-option generation after cost confirmation."""
    from services.ebook_research_engine import (
        TITLE_FAILED_MESSAGE,
        TITLE_UNIT_USD,
    )

    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    if not is_approved(ws, "research"):
        raise ValueError("Approve research before generating title options.")
    if is_approved(ws, "title"):
        raise ValueError("Title is already approved.")
    ctx = _consume_confirmed_simple_action(
        data,
        action="generate_title_options",
        auth_cap_usd=TITLE_UNIT_USD,
        confirmation_token=confirmation_token,
        expected_artifact_id=expected_artifact_id,
        expected_revision=expected_revision,
        max_authorized_usd=max_authorized_usd,
        idempotency_key=idempotency_key,
    )
    if ctx.get("duplicate"):
        return {"ok": True, "duplicate": True, "data": data, "result": ctx.get("result") or {}}

    if titles_fn is None:
        from services.ebook_research_engine import generate_title_options as titles_fn

    out = titles_fn(
        topic=str(ws.get("topic") or data.get("title") or ""),
        audience=str(ws.get("audience") or ""),
        outcome=str(ws.get("outcome") or ""),
        research=dict(ws.get("research_payload") or {}),
    ) or {}
    options = [
        o
        for o in list(out.get("options") or [])
        if isinstance(o, dict) and str(o.get("title") or "").strip()
    ]
    if len(options) < 2:
        raise ValueError(TITLE_FAILED_MESSAGE)

    paid_calls = max(0, int(out.get("paid_calls") or 0))
    charge = _charge_simple_action(
        ctx,
        purpose="generate_title_options",
        unit_usd=TITLE_UNIT_USD,
        paid_calls=paid_calls,
        meta={"option_count": len(options), "artifact_id": ctx["artifact_id"]},
    )
    ws["title_options"] = options
    set_stage_status(ws, "title", STATUS_AWAITING, note="Choose a title")
    _append_history(ws, "generate_title_options", charged_usd=charge, option_count=len(options))
    _recompute_next_action(ws)
    data = sync_document_from_workspace(data)
    result = {
        "title_status": "awaiting_approval",
        "option_count": len(options),
        "provider_requests": paid_calls,
        "charged_usd": charge,
    }
    ctx["idem_store"][ctx["key"]] = {"result": result, "ts": _now()}
    return {"ok": True, "duplicate": False, "data": data, "result": result}


def execute_generate_outline_options(
    data: dict,
    *,
    confirmation_token: str,
    expected_artifact_id: str,
    expected_revision: int,
    max_authorized_usd: float,
    idempotency_key: str,
    outlines_fn=None,
) -> dict:
    """Server-authoritative outline-option generation after cost confirmation."""
    from services.ebook_research_engine import (
        OUTLINE_FAILED_MESSAGE,
        OUTLINE_UNIT_USD,
    )

    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    if not is_approved(ws, "title"):
        raise ValueError("Approve the title before generating an outline.")
    if is_approved(ws, "outline"):
        raise ValueError("Outline is already approved.")
    ctx = _consume_confirmed_simple_action(
        data,
        action="generate_outline_options",
        auth_cap_usd=OUTLINE_UNIT_USD,
        confirmation_token=confirmation_token,
        expected_artifact_id=expected_artifact_id,
        expected_revision=expected_revision,
        max_authorized_usd=max_authorized_usd,
        idempotency_key=idempotency_key,
    )
    if ctx.get("duplicate"):
        return {"ok": True, "duplicate": True, "data": data, "result": ctx.get("result") or {}}

    if outlines_fn is None:
        from services.ebook_research_engine import generate_outline_options as outlines_fn

    out = outlines_fn(
        topic=str(ws.get("topic") or data.get("title") or ""),
        audience=str(ws.get("audience") or ""),
        outcome=str(ws.get("outcome") or ""),
        title=str(data.get("title") or ""),
        subtitle=str(data.get("subtitle") or ""),
        research=dict(ws.get("research_payload") or {}),
    ) or {}
    options = []
    for opt in list(out.get("options") or []):
        if not isinstance(opt, dict):
            continue
        chapters = [c for c in list(opt.get("chapters") or []) if isinstance(c, dict) and str(c.get("title") or "").strip()]
        if len(chapters) >= 3:
            options.append(opt)
    if not options:
        raise ValueError(OUTLINE_FAILED_MESSAGE)

    paid_calls = max(0, int(out.get("paid_calls") or 0))
    charge = _charge_simple_action(
        ctx,
        purpose="generate_outline_options",
        unit_usd=OUTLINE_UNIT_USD,
        paid_calls=paid_calls,
        meta={"option_count": len(options), "artifact_id": ctx["artifact_id"]},
    )
    ws["outline_options"] = options
    set_stage_status(ws, "outline", STATUS_AWAITING, note="Choose an outline")
    _append_history(ws, "generate_outline_options", charged_usd=charge, option_count=len(options))
    _recompute_next_action(ws)
    data = sync_document_from_workspace(data)
    result = {
        "outline_status": "awaiting_approval",
        "option_count": len(options),
        "provider_requests": paid_calls,
        "charged_usd": charge,
    }
    ctx["idem_store"][ctx["key"]] = {"result": result, "ts": _now()}
    return {"ok": True, "duplicate": False, "data": data, "result": result}


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

    Production uses the chapter pipeline (one approved chapter per provider
    request). ``generate_chapter_fn`` is injectable for tests (zero paid calls).
    One-shot ``generate_fn`` is blocked and cannot create Export Ready workspace ebooks.
    """
    if generate_fn is not None and generate_chapter_fn is None:
        raise ValueError(ONESHOT_WORKSPACE_BLOCKED)

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
    token_accepted = list(pending.get("accepted_chapter_digests") or [])
    if token_accepted != accepted_chapter_digests(data):
        raise ValueError(
            "Accepted chapters changed since the estimate — request a new cost estimate."
        )

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

    if generate_fn is not None and generate_chapter_fn is None:
        raise ValueError(ONESHOT_WORKSPACE_BLOCKED)
    if generate_chapter_fn is None:
        from services.ebook import generate_one_chapter as generate_chapter_fn

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
        "chapter_contract_digests": [c.digest() for c in book_contract.chapters],
        "pipeline": "one_chapter_per_request",
    }

    from services.ebook_manuscript_engine import ParsedChapter

    stored_accepted = []
    for item in ws.get("accepted_chapters") or []:
        if not isinstance(item, dict):
            continue
        stored_accepted.append(
            ParsedChapter(
                order=int(item.get("order") or 0),
                title=str(item.get("title") or ""),
                body=str(item.get("body") or ""),
                accepted=True,
            )
        )
    max_calls = max(1, int(auth_max / CHAPTER_UNIT_USD + 1e-9))
    pipeline = run_chapter_pipeline(
        book_contract,
        generate_chapter_fn=generate_chapter_fn,
        accepted_chapters=stored_accepted,
        stop_on_failure=True,
        max_chapter_calls=max_calls,
    )
    manuscript_md = str(pipeline.get("manuscript_md") or "").strip()
    ws["accepted_chapters"] = [
        {"order": c.order, "title": c.title, "body": c.body}
        for c in pipeline.get("accepted_chapters") or []
    ]
    ws["chapter_pipeline"] = {
        "chapter_calls": pipeline.get("chapter_calls"),
        "failed_orders": pipeline.get("failed_orders"),
        "skipped_ungenerated": pipeline.get("skipped_ungenerated"),
        "assembled_complete": pipeline.get("assembled_complete"),
        "provider_payloads": pipeline.get("provider_payloads"),
    }
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

    # Charge only the chapter provider requests that ran. Later chapters after
    # a failure are not generated and not charged.
    chapter_calls = int(pipeline.get("chapter_calls") or 0)
    charge = round(min(chapter_calls * CHAPTER_UNIT_USD, auth_max, remaining), 4)
    ledger["spent_usd"] = round(spent + charge, 4)
    ledger["remaining_usd"] = round(cap - float(ledger["spent_usd"]), 4)
    ledger["paid_calls"] = int(ledger.get("paid_calls") or 0) + chapter_calls
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
            "chapter_calls": chapter_calls,
            "failed_orders": pipeline.get("failed_orders"),
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
        "chapter_calls": chapter_calls,
        "failed_orders": list(pipeline.get("failed_orders") or []),
        "assembled_complete": bool(pipeline.get("assembled_complete")),
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
        "chapter_calls": chapter_calls,
        "failed_orders": list(pipeline.get("failed_orders") or []),
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
        findings_by_order_from_quality,
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

    data = reconcile_validated_preserved_chapters(data)
    ws = data["ebook_workspace"]
    ledger = ws.setdefault("paid_call_ledger", empty_ledger())

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
    if "accepted_chapter_digests" in pending:
        if list(pending.get("accepted_chapter_digests") or []) != accepted_chapter_digests(data):
            raise ValueError(
                "Accepted chapters changed since the estimate — request a new correction estimate."
            )
    auth_max = round(float(max_authorized_usd), 4)
    pending_max = round(float(pending.get("max_authorized_usd") or pending.get("estimated_max_usd") or 0), 4)
    if auth_max <= 0 or abs(auth_max - pending_max) > 1e-9:
        raise ValueError("Authorized charge does not match the pending correction estimate.")
    corr_max = correction_auth_max_usd(ledger)
    if auth_max > corr_max + 1e-9:
        raise ValueError(
            f"Correction authorization exceeds ${corr_max:.2f} maximum."
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

    if correct_fn is not None and correct_chapter_fn is None:
        raise ValueError(ONESHOT_WORKSPACE_BLOCKED)
    if correct_chapter_fn is None:
        from services.ebook import generate_one_chapter as correct_chapter_fn

    set_stage_status(ws, "manuscript", STATUS_IN_PROGRESS, note="Correcting manuscript")
    author = str(ws.get("author") or data.get("author_brand") or "").strip()
    stored_accepted: list = []
    for item in ws.get("accepted_chapters") or []:
        if not isinstance(item, dict):
            continue
        body = str(item.get("body") or "").strip()
        if not body:
            continue
        stored_accepted.append(
            ParsedChapter(
                order=int(item.get("order") or 0),
                title=str(item.get("title") or ""),
                body=body,
                accepted=True,
            )
        )
    accepted_orders = {c.order for c in stored_accepted}
    prior_quality = validate_manuscript_quality(
        data, manuscript_md=existing, book_contract=book_contract
    )
    findings_map = findings_by_order_from_quality(prior_quality)
    if stored_accepted:
        accepted_keep = stored_accepted
        failed_orders = [c.order for c in book_contract.chapters if c.order not in accepted_orders]
    else:
        failed_orders = [
            int(r["order"])
            for r in prior_quality.chapter_results
            if r.get("status") != QUALITY_PASS
        ]
        if not prior_quality.outline_ok:
            failed_orders = [c.order for c in book_contract.chapters]
        _front, prior_chapters, _prior_back = split_front_chapters_back(existing)
        accepted_keep = [ch for ch in prior_chapters if ch.order not in set(failed_orders)]
        for ch in accepted_keep:
            ch.accepted = True

    max_calls = max(1, int(auth_max / CHAPTER_UNIT_USD + 1e-9))
    pipeline = run_chapter_pipeline(
        book_contract,
        generate_chapter_fn=correct_chapter_fn,
        accepted_chapters=accepted_keep,
        repair_orders=failed_orders,
        stop_on_failure=True,
        max_chapter_calls=max_calls,
        prior_manuscript_md=existing,
        findings_by_order=findings_map,
    )
    manuscript_md = str(pipeline.get("manuscript_md") or "").strip()
    ws["accepted_chapters"] = [
        {"order": c.order, "title": c.title, "body": c.body}
        for c in pipeline.get("accepted_chapters") or []
    ]
    ws["chapter_pipeline"] = {
        "chapter_calls": pipeline.get("chapter_calls"),
        "failed_orders": pipeline.get("failed_orders"),
        "skipped_ungenerated": pipeline.get("skipped_ungenerated"),
        "preserved_orders": [c.order for c in accepted_keep],
        "assembled_complete": pipeline.get("assembled_complete"),
        "provider_payloads": pipeline.get("provider_payloads"),
    }
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

    chapter_calls = int((ws.get("chapter_pipeline") or {}).get("chapter_calls") or 0)
    charge = round(min(chapter_calls * CHAPTER_UNIT_USD, auth_max, remaining), 4)
    ledger["spent_usd"] = round(spent + charge, 4)
    ledger["remaining_usd"] = round(cap - float(ledger["spent_usd"]), 4)
    ledger["paid_calls"] = int(ledger.get("paid_calls") or 0) + chapter_calls
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
                "chapter_calls": chapter_calls,
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
        "chapter_calls": chapter_calls,
        "failed_orders": list((ws.get("chapter_pipeline") or {}).get("failed_orders") or []),
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


def apply_pre_manuscript_acceptance_seed(
    target_data: dict,
    source_data: dict,
    *,
    budget_cap_usd: float = MANUSCRIPT_AUTH_MAX_USD,
) -> dict[str, Any]:
    """Copy approved pre-manuscript inputs only into a separate DRAFT workspace.

    Never copies manuscript, quality results, design, exports, ledger, spend,
    tokens, provider responses, or correction history. Always assigns a new
    artifact identity and a fresh $0 / cap ledger.
    """
    source = dict(source_data or {})
    src_ws = get_workspace(source)
    if not src_ws:
        raise ValueError("Source project is not an Ebook workspace.")
    for stage in ("research", "title", "outline"):
        if not is_approved(src_ws, stage):
            raise ValueError(
                f"Source must have approved {stage} before pre-manuscript seed."
            )

    src_content = str(source.get("content") or source.get("ebook") or "")
    src_doc = source.get("ebook_document") if isinstance(source.get("ebook_document"), dict) else {}
    src_doc_md = str(src_doc.get("manuscript_md") or "")

    target = ensure_workspace(dict(target_data or {}))
    _clear_manuscript_fields(target)
    ws = target["ebook_workspace"]
    created_at = ws.get("created_at") or _now()

    author = "Lonnie Brown"
    title = str(source.get("title") or "").strip()
    subtitle = str(source.get("subtitle") or "").strip()
    if not title:
        raise ValueError("Source is missing an approved title.")
    outline = copy.deepcopy(source.get("outline") or [])
    if len(outline) != 10:
        raise ValueError("Source approved outline must contain exactly 10 chapters.")

    ws["topic"] = str(src_ws.get("topic") or source.get("source") or title)
    ws["audience"] = str(src_ws.get("audience") or source.get("audience") or "")
    ws["outcome"] = str(src_ws.get("outcome") or source.get("reader_promise") or "")
    ws["author"] = author
    ws["editorial_rules_locked"] = copy.deepcopy(list(src_ws.get("editorial_rules_locked") or []))
    ws["research_payload"] = copy.deepcopy(src_ws.get("research_payload") or {})
    ws["title_options"] = copy.deepcopy(list(src_ws.get("title_options") or []))
    ws["approved_title_id"] = src_ws.get("approved_title_id")
    ws["outline_options"] = copy.deepcopy(list(src_ws.get("outline_options") or []))
    ws["approved_outline_id"] = src_ws.get("approved_outline_id")
    ws["marker"] = None
    ws["paid_call_ledger"] = empty_ledger(spent_usd=0.0, paid_calls=0, cap_usd=budget_cap_usd)
    ws["approval_history"] = []
    ws["accepted_chapters"] = []
    ws["manuscript_qa"] = []
    ws["manuscript_structure_findings"] = []
    ws["last_manuscript_generation"] = None
    ws["last_manuscript_correction"] = None
    ws["previous_manuscript_draft"] = None
    ws.pop("consumed_tokens", None)
    ws["created_at"] = created_at
    ws["updated_at"] = _now()

    set_stage_status(ws, "research", STATUS_APPROVED, note="Seeded approved research (pre-manuscript only)")
    set_stage_status(ws, "title", STATUS_APPROVED, note="Seeded approved title (pre-manuscript only)")
    set_stage_status(ws, "outline", STATUS_APPROVED, note="Seeded approved outline (pre-manuscript only)")
    for stage in ("manuscript", "visuals", "cover", "design", "preview", "preflight", "export"):
        set_stage_status(ws, stage, STATUS_NOT_STARTED)
    _append_history(
        ws,
        "seed_pre_manuscript",
        title=title,
        subtitle=subtitle,
        outline_id=ws.get("approved_outline_id"),
        spent_usd=0.0,
        budget_cap_usd=float(budget_cap_usd),
    )
    _recompute_next_action(ws)

    target["title"] = title
    target["subtitle"] = subtitle
    target["author"] = author
    target["author_brand"] = author
    target["audience"] = ws["audience"]
    target["reader_promise"] = ws["outcome"]
    target["source"] = title
    target["outline"] = outline
    target["artifact_state"] = "DRAFT"
    target["artifact_revision"] = 1
    target["artifact_id"] = f"ebook-ws-{uuid.uuid4().hex[:12]}"
    target["product_type"] = "ebook"
    target["ebook_project_workspace"] = True
    target["export_ready"] = False
    target["release_status"] = ""
    target["release_messages"] = []
    target["content"] = ""
    target["ebook"] = ""
    target.pop("package_id", None)
    target.pop("acceptance_marker", None)
    target.pop("acceptance_export_dir", None)
    for drop in (
        "visual_plan",
        "ebook_cover_reference",
        "cover_design",
        "ebook_design",
        "ebook_design_digest",
        "ebook_preview_html",
        "ebook_export_identity",
        "ebook_design_preflight",
        "ebook_visual_manifest",
        "release_certificate",
    ):
        target.pop(drop, None)

    target["ebook_workspace"] = ws
    target = sync_document_from_workspace(target)
    _clear_manuscript_fields(target)
    # sync_document_from_workspace may restore empty-doc manuscript fields; keep bytes empty.
    target["content"] = ""
    target["ebook"] = ""
    if src_content and src_content[:80] and src_content[:80] in str(target.get("content") or ""):
        raise ValueError("Refusing seed: source manuscript leaked into target.")
    if src_doc_md and src_doc_md[:80] and src_doc_md[:80] in str(
        ((target.get("ebook_document") or {}) if isinstance(target.get("ebook_document"), dict) else {}).get(
            "manuscript_md"
        )
        or ""
    ):
        raise ValueError("Refusing seed: source manuscript document leaked into target.")
    ed = target.get("ebook_document")
    if isinstance(ed, dict):
        ed["manuscript_md"] = ""
        ed["chapters"] = []
        ed["release_status"] = ""
    target["artifact_state"] = "DRAFT"
    return target


def seed_pre_manuscript_into_project(
    database_module,
    target_project_id: int,
    *,
    source_project_id: int,
    budget_cap_usd: float = MANUSCRIPT_AUTH_MAX_USD,
) -> dict:
    """Apply pre-manuscript seed to an existing empty workspace. Never mutates the source."""
    target_id = int(target_project_id)
    source_id = int(source_project_id)
    if target_id == FROZEN_LIVE_EBOOK_PROJECT_ID:
        raise ValueError(f"Refusing to modify frozen live project #{FROZEN_LIVE_EBOOK_PROJECT_ID}.")
    if target_id == source_id:
        raise ValueError("Refusing to seed a project into itself.")
    target = database_module.get_project(target_id)
    source = database_module.get_project(source_id)
    if not target:
        raise ValueError(f"Target project #{target_id} was not found.")
    if not source:
        raise ValueError(f"Source project #{source_id} was not found.")
    tdata = dict(target.get("data") or {})
    tws = get_workspace(tdata) or {}
    if (
        tdata.get("content")
        or tdata.get("ebook")
        or (
            isinstance(tdata.get("ebook_document"), dict)
            and str((tdata.get("ebook_document") or {}).get("manuscript_md") or "").strip()
        )
        or tws.get("last_manuscript_generation")
        or tws.get("accepted_chapters")
    ):
        raise ValueError("Target already has manuscript or generation history; refuse to overwrite.")
    if stage_status(tws, "manuscript") not in {STATUS_NOT_STARTED, ""}:
        raise ValueError("Target manuscript stage is not Not started; refuse to overwrite.")

    seeded = apply_pre_manuscript_acceptance_seed(
        tdata,
        dict(source.get("data") or {}),
        budget_cap_usd=budget_cap_usd,
    )
    updated = database_module.update_project(
        target_id,
        target.get("name"),
        seeded,
        type_=target.get("type") or "ebook",
    )
    if not updated:
        raise ValueError(f"Failed to update target project #{target_id}.")
    return updated


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
