"""Connected ebook approval workflow (BookyAI-style stages).

Stages are persisted on EbookDocument.workflow_stage. Moving backward never
wipes completed artifacts unless the user explicitly regenerates that stage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.ebook_document import WORKFLOW_STAGES, EbookDocument, attach_document_to_data


STAGE_LABELS = {
    "research": "Research",
    "review_research": "Review Research",
    "save_research": "Save Research",
    "use_research": "Use This Research",
    "title_options": "Generate Title Options",
    "approve_title": "Approve Title/Subtitle",
    "outline": "Generate Outline",
    "approve_outline": "Approve Outline",
    "manuscript": "Generate Manuscript",
    "content_qa": "Content-Quality Validation",
    "edit_chapters": "Edit/Revise Chapters",
    "assign_visuals": "Create or Assign Visuals",
    "approve_cover": "Select/Approve Cover",
    "apply_theme": "Apply Design Theme",
    "preview": "Preview Complete Ebook",
    "preflight": "Final Preflight",
    "save_approved": "Save Approved Artifact",
    "download": "Download PDF and ZIP",
}


@dataclass
class WorkflowSnapshot:
    stage: str
    can_go_back: bool
    can_advance: bool
    preserved_keys: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "label": STAGE_LABELS.get(self.stage, self.stage),
            "can_go_back": self.can_go_back,
            "can_advance": self.can_advance,
            "preserved_keys": list(self.preserved_keys),
            "messages": list(self.messages),
        }


PRESERVE_ON_BACK = (
    "research",
    "outline",
    "chapters",
    "manuscript_md",
    "visuals",
    "cover",
    "design_theme",
    "title",
    "subtitle",
    "author",
    "audience",
    "reader_promise",
)


def stage_index(stage: str) -> int:
    try:
        return WORKFLOW_STAGES.index(stage)
    except ValueError:
        return WORKFLOW_STAGES.index("manuscript")


def set_workflow_stage(doc: EbookDocument, stage: str) -> EbookDocument:
    if stage not in WORKFLOW_STAGES:
        raise ValueError(f"Unknown ebook workflow stage: {stage}")
    doc.workflow_stage = stage
    return doc


def go_back(doc: EbookDocument, to_stage: str) -> WorkflowSnapshot:
    """Move to an earlier stage without wiping completed work."""
    if to_stage not in WORKFLOW_STAGES:
        raise ValueError(f"Unknown ebook workflow stage: {to_stage}")
    if stage_index(to_stage) > stage_index(doc.workflow_stage):
        raise ValueError("go_back cannot move forward; use advance_workflow")
    doc.workflow_stage = to_stage
    # Explicitly do NOT clear manuscript/visuals/cover/research
    return WorkflowSnapshot(
        stage=to_stage,
        can_go_back=stage_index(to_stage) > 0,
        can_advance=True,
        preserved_keys=list(PRESERVE_ON_BACK),
        messages=["Moved back without discarding completed work."],
    )


def advance_workflow(doc: EbookDocument, *, require_gate: bool = True) -> WorkflowSnapshot:
    """Advance one stage if gates allow."""
    idx = stage_index(doc.workflow_stage)
    msgs: list[str] = []
    if require_gate:
        gate = _gate_for_stage(doc, doc.workflow_stage)
        if not gate[0]:
            return WorkflowSnapshot(
                stage=doc.workflow_stage,
                can_go_back=idx > 0,
                can_advance=False,
                messages=[gate[1]],
            )
    if idx >= len(WORKFLOW_STAGES) - 1:
        return WorkflowSnapshot(
            stage=doc.workflow_stage,
            can_go_back=True,
            can_advance=False,
            messages=["Already at final download stage."],
        )
    doc.workflow_stage = WORKFLOW_STAGES[idx + 1]
    msgs.append(f"Advanced to {STAGE_LABELS.get(doc.workflow_stage)}.")
    return WorkflowSnapshot(
        stage=doc.workflow_stage,
        can_go_back=True,
        can_advance=True,
        preserved_keys=list(PRESERVE_ON_BACK),
        messages=msgs,
    )


def _gate_for_stage(doc: EbookDocument, stage: str) -> tuple[bool, str]:
    if stage == "approve_title" and not (doc.title and doc.subtitle):
        return False, "Approve a title and subtitle before continuing."
    if stage == "approve_outline" and len(doc.outline) < 3:
        return False, "Approve an outline with at least 3 chapters."
    if stage == "content_qa" and doc.release_status == "FAIL":
        return False, "Content QA failed — revise before continuing."
    if stage == "approve_cover" and not doc.cover:
        return False, "Select or approve a cover before continuing."
    if stage == "preflight" and doc.release_status == "FAIL":
        return False, "Preflight FAIL — export blocked."
    if stage in {"save_approved", "download"} and doc.release_status != "PASS":
        return False, "Release status must be PASS before save/download."
    return True, "ok"


def sync_workflow_into_project(project: dict, doc: EbookDocument) -> dict:
    project = dict(project or {})
    data = attach_document_to_data(dict(project.get("data") or {}), doc)
    data["ebook_workflow_stage"] = doc.workflow_stage
    project["data"] = data
    return project


def assert_no_silent_substitution(
    before: EbookDocument,
    after: EbookDocument,
    *,
    allowed_changes: set[str] | None = None,
) -> list[str]:
    """Detect silent topic/audience/outline/cover/manuscript swaps."""
    allowed = allowed_changes or set()
    errors: list[str] = []
    checks = [
        ("topic", before.research.topic, after.research.topic),
        ("audience", before.audience, after.audience),
        ("title", before.title, after.title),
        ("manuscript_digest", before.identity.content_digest, after.identity.content_digest),
        ("cover_reference", before.identity.cover_reference, after.identity.cover_reference),
    ]
    before.recompute_digests()
    after.recompute_digests()
    checks = [
        ("topic", before.research.topic, after.research.topic),
        ("audience", before.audience, after.audience),
        ("title", before.title, after.title),
        ("manuscript_digest", before.identity.content_digest, after.identity.content_digest),
        ("cover_reference", before.identity.cover_reference, after.identity.cover_reference),
    ]
    for name, a, b in checks:
        if name in allowed:
            continue
        if (a or "") != (b or "") and a:
            errors.append(f"Silent substitution of {name}: {a!r} → {b!r}")
    return errors
