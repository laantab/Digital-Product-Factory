"""Authoritative structured ebook document model.

Research, outline, manuscript, preview, editor, Save, PDF, and ZIP must all
read/write this same document. Customer content and visual-production
instructions are stored separately — visual suggestions never enter the
manuscript string used for export.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Leak / placeholder patterns that must never reach customer content
# ---------------------------------------------------------------------------

VISUAL_INSTRUCTION_PATTERNS = [
    re.compile(r"visual\s+plan\s+for\s+this\s+chapter", re.I),
    re.compile(r"chart\s+suggestion", re.I),
    re.compile(r"diagram\s+suggestion", re.I),
    re.compile(r"photo\s+placement", re.I),
    re.compile(r"insert\s+(an?\s+)?image", re.I),
    re.compile(r"\[(?:chart|diagram|photo|image|infographic|table)\s*(?:suggestion)?\]", re.I),
    re.compile(r"suggested\s+visual", re.I),
    re.compile(r"image\s+prompt\s*:", re.I),
]

CUSTOMER_BLOCK_PATTERNS = [
    re.compile(r"sub-goal\s*#?\s*\d+", re.I),
    re.compile(r"what\s+this\s+book\s+helps\s+you\s+do", re.I),
    re.compile(r"lorem\s+ipsum", re.I),
    re.compile(r"TODO:?\s", re.I),
    re.compile(r"\[placeholder[^\]]*\]", re.I),
    re.compile(r"as an AI language model", re.I),
    re.compile(r"I (?:will|would) (?:now )?(?:write|generate) (?:the|this) (?:chapter|book)", re.I),
]

WORKFLOW_STAGES = (
    "research",
    "review_research",
    "save_research",
    "use_research",
    "title_options",
    "approve_title",
    "outline",
    "approve_outline",
    "manuscript",
    "content_qa",
    "edit_chapters",
    "assign_visuals",
    "approve_cover",
    "apply_theme",
    "preview",
    "preflight",
    "save_approved",
    "download",
)


@dataclass
class ContentBlock:
    block_id: str
    kind: str  # paragraph | heading | list | callout | example | exercise | table | quote
    text: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class VisualSlot:
    """Visual instruction — never printed as customer prose."""
    slot_id: str
    kind: str  # chart | diagram | table | image | omitted
    brief: str = ""
    caption: str = ""
    chapter_id: str = ""
    status: str = "planned"  # planned | resolved | omitted
    asset_path: str = ""
    rendered_html: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChapterDoc:
    chapter_id: str
    order: int
    title: str
    purpose: str = ""
    blocks: list[ContentBlock] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    exercises: list[str] = field(default_factory=list)
    visual_slot_ids: list[str] = field(default_factory=list)
    approved: bool = False


@dataclass
class OutlineItem:
    order: int
    title: str
    purpose: str = ""
    approved: bool = False


@dataclass
class ResearchBrief:
    topic: str = ""
    audience: str = ""
    reader_promise: str = ""
    notes: str = ""
    sources: list[dict[str, str]] = field(default_factory=list)
    approved: bool = False


@dataclass
class EbookIdentity:
    artifact_id: str = ""
    project_id: Optional[int] = None
    revision: int = 1
    content_digest: str = ""
    asset_manifest_digest: str = ""
    design_theme_version: str = "studio-v1"
    cover_reference: str = ""
    preview_digest: str = ""
    export_digest: str = ""


@dataclass
class EbookDocument:
    """Single authoritative structured ebook document."""

    identity: EbookIdentity = field(default_factory=EbookIdentity)
    title: str = ""
    subtitle: str = ""
    author: str = ""
    audience: str = ""
    reader_promise: str = ""
    tone: str = "friendly and clear"
    reading_level: str = "6th-8th grade"
    research: ResearchBrief = field(default_factory=ResearchBrief)
    outline: list[OutlineItem] = field(default_factory=list)
    chapters: list[ChapterDoc] = field(default_factory=list)
    visuals: list[VisualSlot] = field(default_factory=list)
    front_matter: dict[str, str] = field(default_factory=dict)
    back_matter: dict[str, Any] = field(default_factory=dict)
    cover: dict[str, Any] = field(default_factory=dict)
    design_theme: str = "studio_clean"
    workflow_stage: str = "manuscript"
    approval_state: str = "draft"  # draft | in_review | approved | blocked
    release_status: str = ""  # PASS | WARNING | FAIL
    release_messages: list[str] = field(default_factory=list)
    # Customer-facing manuscript (sanitized). Visual instructions live only in visuals[].
    manuscript_md: str = ""

    # ------------------------------------------------------------------
    # Digests / identity
    # ------------------------------------------------------------------
    def recompute_digests(self) -> None:
        payload = {
            "title": self.title,
            "subtitle": self.subtitle,
            "author": self.author,
            "audience": self.audience,
            "reader_promise": self.reader_promise,
            "chapters": [
                {
                    "order": c.order,
                    "title": c.title,
                    "purpose": c.purpose,
                    "blocks": [asdict(b) for b in c.blocks],
                    "exercises": c.exercises,
                }
                for c in sorted(self.chapters, key=lambda x: x.order)
            ],
            "manuscript_md": self.manuscript_md,
        }
        self.identity.content_digest = _sha(payload)
        assets = [
            {
                "slot_id": v.slot_id,
                "kind": v.kind,
                "status": v.status,
                "asset_path": v.asset_path,
                "caption": v.caption,
            }
            for v in self.visuals
        ]
        self.identity.asset_manifest_digest = _sha(assets)
        self.identity.cover_reference = (
            self.cover.get("local_cover_pdf")
            or self.cover.get("image_path")
            or self.cover.get("cover_id")
            or ""
        )
        self.identity.design_theme_version = self.design_theme or "studio-v1"

    def identity_match(self, other: "EbookDocument") -> bool:
        self.recompute_digests()
        other.recompute_digests()
        a, b = self.identity, other.identity
        return (
            a.content_digest == b.content_digest
            and a.asset_manifest_digest == b.asset_manifest_digest
            and a.cover_reference == b.cover_reference
            and a.design_theme_version == b.design_theme_version
            and [c.chapter_id for c in sorted(self.chapters, key=lambda x: x.order)]
            == [c.chapter_id for c in sorted(other.chapters, key=lambda x: x.order)]
            and [v.slot_id for v in self.visuals] == [v.slot_id for v in other.visuals]
        )

    def to_dict(self) -> dict[str, Any]:
        self.recompute_digests()
        return {
            "identity": asdict(self.identity),
            "title": self.title,
            "subtitle": self.subtitle,
            "author": self.author,
            "audience": self.audience,
            "reader_promise": self.reader_promise,
            "tone": self.tone,
            "reading_level": self.reading_level,
            "research": asdict(self.research),
            "outline": [asdict(o) for o in self.outline],
            "chapters": [asdict(c) for c in self.chapters],
            "visuals": [asdict(v) for v in self.visuals],
            "front_matter": dict(self.front_matter),
            "back_matter": dict(self.back_matter),
            "cover": dict(self.cover),
            "design_theme": self.design_theme,
            "workflow_stage": self.workflow_stage,
            "approval_state": self.approval_state,
            "release_status": self.release_status,
            "release_messages": list(self.release_messages),
            "manuscript_md": self.manuscript_md,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any] | None) -> "EbookDocument":
        d = d or {}
        ident = d.get("identity") or {}
        base_ident = EbookIdentity()
        doc = cls(
            identity=EbookIdentity(
                artifact_id=str(ident.get("artifact_id", base_ident.artifact_id) or ""),
                project_id=ident.get("project_id", base_ident.project_id),
                revision=int(ident.get("revision") or 1),
                content_digest=str(ident.get("content_digest") or ""),
                asset_manifest_digest=str(ident.get("asset_manifest_digest") or ""),
                design_theme_version=str(ident.get("design_theme_version") or "studio-v1"),
                cover_reference=str(ident.get("cover_reference") or ""),
                preview_digest=str(ident.get("preview_digest") or ""),
                export_digest=str(ident.get("export_digest") or ""),
            ),
            title=str(d.get("title") or ""),
            subtitle=str(d.get("subtitle") or ""),
            author=str(d.get("author") or ""),
            audience=str(d.get("audience") or ""),
            reader_promise=str(d.get("reader_promise") or ""),
            tone=str(d.get("tone") or "friendly and clear"),
            reading_level=str(d.get("reading_level") or "6th-8th grade"),
            design_theme=str(d.get("design_theme") or "studio_clean"),
            workflow_stage=str(d.get("workflow_stage") or "manuscript"),
            approval_state=str(d.get("approval_state") or "draft"),
            release_status=str(d.get("release_status") or ""),
            release_messages=list(d.get("release_messages") or []),
            manuscript_md=str(d.get("manuscript_md") or ""),
            front_matter=dict(d.get("front_matter") or {}),
            back_matter=dict(d.get("back_matter") or {}),
            cover=dict(d.get("cover") or {}),
        )
        research = d.get("research") or {}
        doc.research = ResearchBrief(
            topic=str(research.get("topic") or ""),
            audience=str(research.get("audience") or ""),
            reader_promise=str(research.get("reader_promise") or ""),
            notes=str(research.get("notes") or ""),
            sources=list(research.get("sources") or []),
            approved=bool(research.get("approved")),
        )
        for o in d.get("outline") or []:
            if not isinstance(o, dict):
                continue
            doc.outline.append(
                OutlineItem(
                    order=int(o.get("order") or 0),
                    title=str(o.get("title") or ""),
                    purpose=str(o.get("purpose") or ""),
                    approved=bool(o.get("approved")),
                )
            )
        for i, c in enumerate(d.get("chapters") or []):
            if not isinstance(c, dict):
                continue
            blocks: list[ContentBlock] = []
            for b in c.get("blocks") or []:
                if not isinstance(b, dict):
                    continue
                blocks.append(
                    ContentBlock(
                        block_id=str(b.get("block_id") or ""),
                        kind=str(b.get("kind") or "paragraph"),
                        text=str(b.get("text") or ""),
                        meta=dict(b.get("meta") or {}),
                    )
                )
            doc.chapters.append(
                ChapterDoc(
                    chapter_id=str(c.get("chapter_id") or f"ch_{i+1}"),
                    order=int(c.get("order") or i + 1),
                    title=str(c.get("title") or ""),
                    purpose=str(c.get("purpose") or ""),
                    blocks=blocks,
                    examples=list(c.get("examples") or []),
                    exercises=list(c.get("exercises") or []),
                    visual_slot_ids=list(c.get("visual_slot_ids") or []),
                    approved=bool(c.get("approved")),
                )
            )
        for v in d.get("visuals") or []:
            if not isinstance(v, dict):
                continue
            doc.visuals.append(
                VisualSlot(
                    slot_id=str(v.get("slot_id") or ""),
                    kind=str(v.get("kind") or "omitted"),
                    brief=str(v.get("brief") or ""),
                    caption=str(v.get("caption") or ""),
                    chapter_id=str(v.get("chapter_id") or ""),
                    status=str(v.get("status") or "planned"),
                    asset_path=str(v.get("asset_path") or ""),
                    rendered_html=str(v.get("rendered_html") or ""),
                    data=dict(v.get("data") or {}),
                )
            )
        return doc


# ---------------------------------------------------------------------------
# Sanitization + builders
# ---------------------------------------------------------------------------

_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_H3_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)


def strip_visual_instructions(md_text: str) -> tuple[str, list[str]]:
    """Remove visual-production instructions from customer manuscript.

    Returns (cleaned_md, removed_snippets).
    """
    if not md_text:
        return "", []
    removed: list[str] = []
    lines = md_text.splitlines()
    out: list[str] = []
    skip_block = False
    for line in lines:
        lower = line.lower().strip()
        if any(p.search(line) for p in VISUAL_INSTRUCTION_PATTERNS):
            removed.append(line.strip()[:160])
            # Drop following bullet block that elaborates the suggestion
            if lower.startswith("#") or lower.startswith("visual plan"):
                skip_block = True
            continue
        if skip_block:
            if not line.strip() or line.lstrip().startswith(("#", "##")):
                skip_block = False
                if line.strip() and not any(p.search(line) for p in VISUAL_INSTRUCTION_PATTERNS):
                    out.append(line)
            else:
                removed.append(line.strip()[:160])
            continue
        out.append(line)
    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"
    return cleaned, removed


def find_customer_content_defects(md_text: str) -> list[str]:
    """Return defect codes for leaked / placeholder / generic content."""
    defects: list[str] = []
    text = md_text or ""
    for p in VISUAL_INSTRUCTION_PATTERNS:
        if p.search(text):
            defects.append(f"leaked_visual_instruction:{p.pattern}")
    for p in CUSTOMER_BLOCK_PATTERNS:
        if p.search(text):
            defects.append(f"blocked_customer_phrase:{p.pattern}")
    # Duplicate headings — fail on known bad labels (any repeat) or 3+ repeats
    _BAD_DUP_HEADINGS = {
        "what this book helps you do",
        "chapter takeaway",
        "key takeaway",
        "apply what you learned",
        "common mistakes",
        "a step-by-step method",
    }
    headings = [m.group(1).strip().lower() for m in _H2_RE.finditer(text)]
    headings += [m.group(1).strip().lower() for m in _H3_RE.finditer(text)]
    seen: dict[str, int] = {}
    for h in headings:
        seen[h] = seen.get(h, 0) + 1
    for h, n in seen.items():
        if not h:
            continue
        if h in _BAD_DUP_HEADINGS and n > 1:
            defects.append(f"duplicate_heading:{h}")
        elif n >= 4:
            # 4+ identical headings usually means mechanical scaffolding
            defects.append(f"duplicate_heading:{h}")
    # Duplicate paragraphs (near-exact, >= 100 chars, 3+ copies = scaffolding)
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) >= 100]
    pcounts: dict[str, int] = {}
    for p in paras:
        key = re.sub(r"\s+", " ", p.lower())
        pcounts[key] = pcounts.get(key, 0) + 1
    for p, n in pcounts.items():
        if n >= 3:
            defects.append(f"duplicate_paragraph:{p[:60]}")
    # Checklist duplicates — 3+ identical items (Average Joe pattern)
    items = re.findall(r"^\s*[-*]\s+(.+)$", text, re.M)
    icounts: dict[str, int] = {}
    for it in items:
        key = it.strip().lower()
        icounts[key] = icounts.get(key, 0) + 1
    for it, n in icounts.items():
        if n >= 3 and len(it) > 12:
            defects.append(f"duplicate_checklist:{it[:60]}")
    return defects


def manuscript_to_chapters(md_text: str) -> list[ChapterDoc]:
    matches = list(_H2_RE.finditer(md_text or ""))
    chapters: list[ChapterDoc] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        body = (md_text[start:end] or "").strip()
        title = m.group(1).strip()
        blocks: list[ContentBlock] = []
        for j, para in enumerate(re.split(r"\n\s*\n", body)):
            para = para.strip()
            if not para:
                continue
            kind = "paragraph"
            if para.startswith("### "):
                kind = "heading"
            elif re.match(r"^\s*[-*]\s+", para) or re.match(r"^\s*\d+\.\s+", para):
                kind = "list"
            elif para.lower().startswith("|") and "|" in para[1:]:
                kind = "table"
            blocks.append(ContentBlock(block_id=f"b{i+1}_{j+1}", kind=kind, text=para))
        purpose = ""
        if blocks:
            purpose = blocks[0].text[:180]
        chapters.append(
            ChapterDoc(
                chapter_id=f"ch_{i+1}",
                order=i + 1,
                title=title,
                purpose=purpose,
                blocks=blocks,
            )
        )
    return chapters


def visual_plan_to_slots(visual_plan: dict | None, chapters: list[ChapterDoc]) -> list[VisualSlot]:
    slots: list[VisualSlot] = []
    if not isinstance(visual_plan, dict):
        return slots
    by_title = {c.title.strip().lower(): c for c in chapters}
    for ci, ch in enumerate(visual_plan.get("chapters") or []):
        if not isinstance(ch, dict):
            continue
        ctitle = str(ch.get("chapter") or "").strip()
        chapter = by_title.get(ctitle.lower())
        chapter_id = chapter.chapter_id if chapter else f"ch_{ci+1}"
        for ai, aid in enumerate(ch.get("aids") or []):
            if not isinstance(aid, dict):
                continue
            kind = str(aid.get("type") or "diagram").lower()
            slot_id = str(aid.get("visual_id") or f"v_{ci+1}_{ai+1}")
            status = "resolved"
            asset = str(aid.get("image_path") or aid.get("asset_path") or "")
            rendered = str(aid.get("rendered_html") or aid.get("body") or aid.get("html") or "")
            if kind in {"image", "photo"} and not asset:
                status = "planned"
            if kind in {"chart", "table", "diagram", "tip"} and rendered:
                status = "resolved"
            if aid.get("omitted"):
                status = "omitted"
            slots.append(
                VisualSlot(
                    slot_id=slot_id,
                    kind=kind,
                    brief=str(aid.get("title") or aid.get("prompt") or ""),
                    caption=str(aid.get("caption") or ""),
                    chapter_id=chapter_id,
                    status=status,
                    asset_path=asset,
                    rendered_html=rendered,
                    data={
                        k: aid[k]
                        for k in ("chart_data", "table", "rows", "columns")
                        if k in aid
                    },
                )
            )
            if chapter and slot_id not in chapter.visual_slot_ids:
                chapter.visual_slot_ids.append(slot_id)
    return slots


def build_ebook_document_from_project(project: dict | None = None, data: dict | None = None) -> EbookDocument:
    """Build/refresh authoritative document from project data blob."""
    project = project or {}
    data = dict(data or project.get("data") or {})
    if isinstance(data.get("ebook_document"), dict) and data["ebook_document"].get("manuscript_md"):
        doc = EbookDocument.from_dict(data["ebook_document"])
    else:
        doc = EbookDocument()

    title = (
        data.get("title")
        or project.get("name")
        or doc.title
        or "Untitled Ebook"
    ).strip()
    manuscript = (
        data.get("content")
        or data.get("ebook")
        or doc.manuscript_md
        or ""
    )
    cleaned, _removed = strip_visual_instructions(manuscript)
    fields = dict(data.get("fields") or {})

    doc.title = title
    doc.subtitle = str(data.get("subtitle") or fields.get("subtitle") or doc.subtitle or "")
    doc.author = str(
        data.get("author_brand")
        or fields.get("author_brand")
        or fields.get("author")
        or doc.author
        or ""
    )
    doc.audience = str(fields.get("audience") or data.get("audience") or doc.audience or "")
    doc.reader_promise = str(
        fields.get("product_promise")
        or fields.get("main_transformation")
        or data.get("reader_promise")
        or doc.reader_promise
        or ""
    )
    doc.tone = str(fields.get("tone") or doc.tone)
    doc.reading_level = str(fields.get("reading_level") or doc.reading_level)
    doc.manuscript_md = cleaned
    doc.chapters = manuscript_to_chapters(cleaned)
    doc.outline = [
        OutlineItem(order=c.order, title=c.title, purpose=c.purpose, approved=True)
        for c in doc.chapters
    ]
    doc.visuals = visual_plan_to_slots(
        data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None,
        doc.chapters,
    )
    if isinstance(data.get("cover_design"), dict):
        doc.cover = dict(data["cover_design"])
    doc.research = ResearchBrief(
        topic=str(fields.get("topic") or data.get("source") or title),
        audience=doc.audience,
        reader_promise=doc.reader_promise,
        notes=str(data.get("research_notes") or fields.get("research_notes") or ""),
        sources=_sources_from_data(data),
        approved=bool(data.get("research_approved") or data.get("research_notes")),
    )
    if project.get("id") is not None:
        doc.identity.project_id = int(project["id"])
    doc.identity.artifact_id = str(
        data.get("package_id")
        or data.get("export_package_id")
        or doc.identity.artifact_id
        or ""
    )
    doc.identity.revision = int(data.get("revision") or doc.identity.revision or 1)
    doc.design_theme = str(data.get("design_theme") or doc.design_theme or "studio_clean")
    doc.recompute_digests()
    return doc


def attach_document_to_data(
    data: dict,
    doc: EbookDocument,
    *,
    sync_manuscript: bool = True,
) -> dict:
    """Persist ebook document metadata alongside Stabilized artifact fields.

    Does **not** overwrite Stabilized ``content_digest`` / ``asset_manifest_digest`` /
    ``artifact_revision``. Ebook-specific digests are stored under ebook_* keys
    and feed release/preview checks without replacing the artifact-identity system.
    """
    data = dict(data or {})
    doc.recompute_digests()
    data["ebook_document"] = doc.to_dict()
    if sync_manuscript:
        data["content"] = doc.manuscript_md
        data["ebook"] = doc.manuscript_md
    if doc.title:
        data["title"] = doc.title
    if doc.subtitle:
        data["subtitle"] = doc.subtitle
    if doc.author:
        data["author_brand"] = doc.author
    data["design_theme"] = doc.design_theme
    data["release_status"] = doc.release_status
    data["release_messages"] = list(doc.release_messages)
    data["ebook_workflow_stage"] = doc.workflow_stage
    data["ebook_manuscript_digest"] = doc.identity.content_digest
    data["ebook_asset_manifest_digest"] = doc.identity.asset_manifest_digest
    data["ebook_cover_reference"] = doc.identity.cover_reference
    # Visual plan rebuilt from slots (customer-safe) — only when syncing manuscript
    # path (DRAFT mutation). Packaging must pass sync_manuscript=False.
    if sync_manuscript:
        chapters_plan: list[dict] = []
        by_ch: dict[str, list[VisualSlot]] = {}
        for v in doc.visuals:
            by_ch.setdefault(v.chapter_id, []).append(v)
        for c in sorted(doc.chapters, key=lambda x: x.order):
            aids = []
            for v in by_ch.get(c.chapter_id, []):
                if v.status == "omitted":
                    continue
                aid = {
                    "type": v.kind,
                    "title": v.brief,
                    "caption": v.caption,
                    "visual_id": v.slot_id,
                    "rendered_html": v.rendered_html,
                    "asset_path": v.asset_path,
                }
                aid.update(v.data)
                aids.append(aid)
            chapters_plan.append({"chapter": c.title, "aids": aids})
        if chapters_plan:
            data["visual_plan"] = {"chapters": chapters_plan}
        if doc.cover:
            data["cover_design"] = dict(doc.cover)
    return data


def _sources_from_data(data: dict) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    brief = data.get("research_brief")
    if isinstance(brief, dict):
        for s in brief.get("sources") or []:
            if isinstance(s, dict):
                out.append({"title": str(s.get("title") or ""), "url": str(s.get("url") or "")})
            elif isinstance(s, str):
                out.append({"title": s, "url": ""})
    notes = str(data.get("research_notes") or "")
    for m in re.finditer(r"https?://\S+", notes):
        out.append({"title": m.group(0), "url": m.group(0)})
    return out


def _sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
