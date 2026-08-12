"""Contract-driven Ebook manuscript engine.

Deterministic. No network. Used to build book/chapter contracts, generate
chapters independently (with injected providers), and gate Approve Manuscript
on a hard quality result: PASS, NEEDS_CORRECTION, or FAIL.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from services.ebook_contract import (
    FOREVER_FORBIDDEN_MARKETING,
    GENERIC_FILLER_PHRASES,
    PLACEHOLDER_PHRASES,
    UNSUPPORTED_CLAIM_PHRASES,
)
from services.ebook_outline_fidelity import (
    PROHIBITED_BACK_MATTER_TITLES,
    extract_manuscript_h2_titles,
    normalize_chapter_title,
    validate_manuscript_outline_fidelity,
)

QUALITY_PASS = "PASS"
QUALITY_NEEDS_CORRECTION = "NEEDS_CORRECTION"
QUALITY_FAIL = "FAIL"

_H2_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")
_WORD_RE = re.compile(r"\b\w+\b")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}")
_MONEY_RE = re.compile(r"\$\s*\d")
_HEDGE_RE = re.compile(
    r"\b(may vary|it depends|in some cases|generally speaking|it is important to|"
    r"keep in mind|as a rule of thumb|there is no one.size|"
    r"should be verified|treat them as items to verify)\b",
    re.I,
)
_UNSUPPORTED_NUMERIC_RE = re.compile(
    r"\b(studies show|research proves|guaranteed (?:income|earnings|results)|"
    r"average photographer (?:makes|earns)|you will (?:make|earn) \$)\b",
    re.I,
)

FROZEN_2472_SHA256 = "f0b3c8c4b8e0c24df29fe0c695a0a84d26e2f1bb00182bc1e210968e67611560"
FROZEN_2472_SPENT_USD = 3.178
FROZEN_2472_REMAINING_USD = 0.322


def _sha(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def word_count(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


@dataclass
class ChapterContract:
    order: int
    title: str
    purpose: str
    reader_questions: list[str] = field(default_factory=list)
    required_facts: list[str] = field(default_factory=list)
    required_citations: list[str] = field(default_factory=list)
    required_examples: list[str] = field(default_factory=list)
    required_table: str = ""
    required_workflow: str = ""
    required_checklist: str = ""
    min_useful_words: int = 600
    prohibited_repetition: list[str] = field(default_factory=list)
    prohibited_claims: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)

    def digest(self) -> str:
        return _sha(asdict(self))


@dataclass
class BookContract:
    title: str
    subtitle: str
    author: str
    audience: str
    primary_outcome: str
    approved_outline: list[dict[str, Any]]
    research_brief: str
    citations: list[str]
    editorial_rules: list[str]
    target_word_min: int = 12000
    target_word_max: int = 16000
    required_tables: list[str] = field(default_factory=list)
    required_comparisons: list[str] = field(default_factory=list)
    required_examples: list[str] = field(default_factory=list)
    required_workflows: list[str] = field(default_factory=list)
    required_checklists: list[str] = field(default_factory=list)
    prohibited_filler: list[str] = field(default_factory=list)
    prohibited_unsupported_claims: list[str] = field(default_factory=list)
    front_matter: list[str] = field(default_factory=list)
    back_matter: list[str] = field(default_factory=list)
    chapters: list[ChapterContract] = field(default_factory=list)
    outline_digest: str = ""
    catalog_id: str = ""

    def digest(self) -> str:
        payload = asdict(self)
        payload["chapters"] = [c.digest() if isinstance(c, ChapterContract) else c for c in self.chapters]
        return _sha(payload)


@dataclass
class ChapterFinding:
    order: int
    title: str
    code: str
    message: str
    severity: str  # FAIL | NEEDS_CORRECTION

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class QualityResult:
    status: str
    findings: list[ChapterFinding] = field(default_factory=list)
    book_findings: list[str] = field(default_factory=list)
    chapter_results: list[dict[str, Any]] = field(default_factory=list)
    word_count: int = 0
    outline_ok: bool = False
    quality_ok: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "findings": [f.as_dict() for f in self.findings],
            "book_findings": list(self.book_findings),
            "chapter_results": list(self.chapter_results),
            "word_count": self.word_count,
            "outline_ok": self.outline_ok,
            "quality_ok": self.quality_ok,
        }

    @property
    def finding_messages(self) -> list[str]:
        msgs = list(self.book_findings)
        for f in self.findings:
            msgs.append(f"Ch{f.order} {f.code}: {f.message}")
        return msgs


@dataclass
class ParsedChapter:
    order: int
    title: str
    body: str
    tables: list[str] = field(default_factory=list)
    checklists: list[str] = field(default_factory=list)
    workflows: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)
    citations: list[str] = field(default_factory=list)
    accepted: bool = False


# ---------------------------------------------------------------------------
# Event-photography acceptance catalog (project #2472 outline)
# ---------------------------------------------------------------------------

def _ch(
    order: int,
    title: str,
    purpose: str,
    *,
    questions: list[str],
    facts: list[str],
    citations: list[str] | None = None,
    examples: list[str] | None = None,
    table: str = "",
    workflow: str = "",
    checklist: str = "",
    min_words: int = 350,
    extra_criteria: list[str] | None = None,
) -> ChapterContract:
    criteria = [
        f"Use the exact approved title: {title}",
        "Answer the chapter's reader questions with practical steps",
        "Do not repeat another chapter's core deliverable as filler",
        "Do not invent Lonnie Brown stories, earnings, or quotations",
    ]
    if table:
        criteria.append(f"Include a markdown table covering: {table}")
    if workflow:
        criteria.append(f"Include a numbered workflow for: {workflow}")
    if checklist:
        criteria.append(f"Include a usable checklist for: {checklist}")
    if extra_criteria:
        criteria.extend(extra_criteria)
    return ChapterContract(
        order=order,
        title=title,
        purpose=purpose,
        reader_questions=questions,
        required_facts=facts,
        required_citations=list(citations or []),
        required_examples=list(examples or []),
        required_table=table,
        required_workflow=workflow,
        required_checklist=checklist,
        min_useful_words=min_words,
        prohibited_repetition=[
            "on-site prints also add operational complexity",
            "the practical business lesson is simple",
        ],
        prohibited_claims=[
            "guaranteed earnings",
            "invented production specifications for keepsakes",
        ],
        acceptance_criteria=criteria,
    )


EVENT_PHOTO_CHAPTER_SPECS: list[ChapterContract] = [
    _ch(
        1,
        "What This Business Actually Looks Like",
        "Event photography niches: weddings, parties, schools, churches, reunions, "
        "community events. How on-site prints change the offer and guest experience. "
        "Outcomes for this guide; what will and will not be claimed.",
        questions=[
            "What event types does this business actually serve?",
            "How do on-site prints change the offer?",
            "What will this guide claim and refuse to claim?",
        ],
        facts=["weddings", "parties", "schools", "churches", "reunions", "community"],
        examples=["event-type comparison"],
        table="event-niche-comparison",
        extra_criteria=["State that earnings and booking volume are not guaranteed"],
    ),
    _ch(
        2,
        "Startup Reality Check: Budget, Legal Basics, and Insurance",
        "Lean vs event-focused startup ranges from research (as planning ranges, not "
        "guarantees). Business registration and insurance as operating requirements. "
        "Portfolio, website, and bookkeeping as launch essentials.",
        questions=[
            "What is a lean vs event-focused startup budget range?",
            "Which insurance and COI items matter for venues?",
            "What legal and bookkeeping basics are required before event one?",
        ],
        facts=["$2,000", "$5,000", "$10,000", "$25,000", "insurance", "registration"],
        citations=["startcosts.com", "photographylaunchpad.com"],
        table="startup-budget-and-insurance",
        checklist="insurance-and-coi",
        extra_criteria=["Label startup ranges as planning ranges, not guarantees"],
    ),
    _ch(
        3,
        "Core Camera Kit, Printing Equipment, and Backup Gear",
        "Bodies, lenses, flash/lighting, computer, editing software. Backup body, "
        "batteries, and memory cards as operational priorities. Used gear and rentals "
        "as cost-control options. Printing equipment as a distinct station, compared "
        "at a kit level and detailed in the dye-sub chapter.",
        questions=[
            "What belongs in a starter vs event camera kit?",
            "What backup gear is non-negotiable?",
            "How should printing equipment be planned without duplicating Chapter 8?",
        ],
        facts=["24-70", "70-200", "backup", "batteries", "memory cards", "printer"],
        examples=["used vs rent vs buy"],
        table="starter-vs-event-kit",
        checklist="event-backup-kit",
    ),
    _ch(
        4,
        "Finding Clients and Turning Inquiries into Signed Bookings",
        "Where beginners actually find event clients. Lead questions, expectations, "
        "contracts, deposits, and timelines. Turning an inquiry into a signed booking "
        "without inventing case studies.",
        questions=[
            "Where do first event clients come from?",
            "What happens between inquiry and signed contract?",
            "When should a deposit and contract go out?",
        ],
        facts=["inquiry", "contract", "deposit", "follow-up"],
        examples=["inquiry-to-booking scenario"],
        workflow="inquiry-to-signed-booking",
        extra_criteria=["Do not substitute package templates for a client-finding workflow"],
    ),
    _ch(
        5,
        "Packages and Pricing Scenarios That Protect Your Margin",
        "Define hours, deliverables, planning meetings, and turnaround. Event-type "
        "package templates as planning examples. Cover shooting, planning, editing, "
        "travel, taxes, gear recovery, and profit with clearly labeled hypothetical "
        "dollar scenarios. Published averages are signals, not a local price list.",
        questions=[
            "What belongs in a package clients can understand?",
            "How do I build price from a cost stack with dollars?",
            "Why are published averages not my price list?",
        ],
        facts=["$50", "$150", "$500", "$1,500", "$100", "$250", "hypothetical"],
        examples=["hypothetical dollar-margin scenario"],
        table="package-and-margin",
        extra_criteria=["Every pricing table must be labeled hypothetical / planning-scenario"],
    ),
    _ch(
        6,
        "Planning the Event: Contracts, Timelines, Space, Power, and Staffing",
        "Pre-event shot lists and venue constraints. Event planning timeline. Space, "
        "power, cable-safety, and staffing. Setting print expectations before event day.",
        questions=[
            "What timeline should exist before arrival?",
            "How do I plan space, power, and cable safety?",
            "How should staffing roles be assigned?",
        ],
        facts=["timeline", "power", "space", "staffing", "cable"],
        table="event-planning-timeline",
        checklist="space-power-cable-staffing",
        workflow="pre-event-planning",
    ),
    _ch(
        7,
        "Event-Day Operations: From Photograph to Guest Delivery",
        "Before / during / after workflow. Coverage roles: wide, medium, telephoto; "
        "flash discipline; file hygiene. Staffing, timing, guest flow, run-of-show, "
        "and file-backup procedure.",
        questions=[
            "What is the timed run-of-show?",
            "How are files backed up during and after the event?",
            "How do photography and print-station roles stay out of each other's way?",
        ],
        facts=["before", "during", "after", "backup", "wide", "telephoto"],
        workflow="event-day-run-of-show",
        checklist="file-backup-procedure",
    ),
    _ch(
        8,
        "Dye-Sublimation Printing: Setup, Queue, Ordering, Payment, and Pickup",
        "Why dye-sub is used for fast take-home photo prints. Source-supported overview "
        "of DS-RX1HS, DS620A, and QW410 (sizes, speeds, media capacities where documented). "
        "Hot Folder Print, multi-printer distribution, status monitoring. Equipment and "
        "media prices vary; verify with current suppliers. Hypothetical media-planning "
        "and margin scenarios only.",
        questions=[
            "How do DS-RX1HS, DS620A, and QW410 compare on documented specs?",
            "What is the live print workflow from setup through pickup?",
            "How should media and margin be planned without quoting live market prices?",
        ],
        facts=["DS-RX1HS", "DS620A", "QW410", "Hot Folder", "4x6", "4×6"],
        citations=["dnpphoto.com"],
        examples=["hypothetical media-planning scenario"],
        table="dye-sub-printer-comparison",
        workflow="setup-queue-order-pay-pickup",
        extra_criteria=[
            "State source-supported printer specs; do not omit them as unverifiable",
            "State that equipment and media prices vary and must be verified with current suppliers",
        ],
    ),
    _ch(
        9,
        "Keepsakes Beyond Photo Prints: Separate Equipment and Workflow",
        "Photo prints vs mugs, buttons, shirts, plates, and similar items. Separate "
        "equipment, materials, production time, staffing, and safety planning required. "
        "Not verified by the printer-manufacturer sources used for dye-sub photo printers; "
        "no invented production specs.",
        questions=[
            "When should I refuse or delay keepsakes?",
            "What extra staffing and safety planning do keepsakes require?",
            "Why are keepsakes not the same as dye-sub photo prints?",
        ],
        facts=["mugs", "buttons", "shirts", "plates", "separate equipment", "safety"],
        checklist="keepsake-go-no-go-staffing-safety",
        extra_criteria=["Do not invent mug/shirt/plate production specifications"],
    ),
    _ch(
        10,
        "Common Mistakes and Your 30-Day First Paid Event Plan",
        "Underpricing, no backup gear, vague packages, weak print planning. "
        "First-paid-event checklist spanning kit, insurance, packages, booking, and "
        "print readiness. How to refine after event one without inventing case studies.",
        questions=[
            "What mistakes sink event one?",
            "What is a 30-day plan to the first paid event?",
            "How do I refine after event one without fake case studies?",
        ],
        facts=["underpricing", "backup", "30-day", "checklist"],
        checklist="first-paid-event-30-day",
        extra_criteria=["Include a day-banded 30-day plan, not only a recap of earlier chapters"],
    ),
]


def event_photo_catalog_by_title() -> dict[str, ChapterContract]:
    return {normalize_chapter_title(c.title): c for c in EVENT_PHOTO_CHAPTER_SPECS}


def event_photo_book_requirements() -> dict[str, list[str]]:
    return {
        "tables": [
            "event-niche-comparison",
            "startup-budget-and-insurance",
            "starter-vs-event-kit",
            "package-and-margin",
            "event-planning-timeline",
            "dye-sub-printer-comparison",
        ],
        "comparisons": ["starter vs event kit", "DS-RX1HS vs DS620A vs QW410"],
        "workflows": [
            "inquiry-to-signed-booking",
            "setup-queue-order-pay-pickup",
            "event-day-run-of-show",
        ],
        "checklists": [
            "insurance-and-coi",
            "space-power-cable-staffing",
            "file-backup-procedure",
            "keepsake-go-no-go-staffing-safety",
            "first-paid-event-30-day",
        ],
    }


def uses_event_photo_catalog(titles: list[str]) -> bool:
    catalog = event_photo_catalog_by_title()
    hits = sum(1 for t in titles if normalize_chapter_title(t) in catalog)
    return hits >= 8


def remap_outline_purposes(
    new_chapters: list[dict[str, Any]],
    *,
    previous_outline: list[dict[str, Any]] | None = None,
    catalog: dict[str, ChapterContract] | None = None,
) -> list[dict[str, Any]]:
    """Keep purpose only when the title still matches. Never keep a prior slot's purpose."""
    catalog = catalog or event_photo_catalog_by_title()
    prev_by_title: dict[str, str] = {}
    for item in previous_outline or []:
        if not isinstance(item, dict):
            continue
        prev_by_title[normalize_chapter_title(item.get("title"))] = str(item.get("purpose") or "")
    out: list[dict[str, Any]] = []
    for i, raw in enumerate(new_chapters or []):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()
        norm = normalize_chapter_title(title)
        purpose = str(raw.get("purpose") or "").strip()
        if isinstance(raw.get("bullets"), list) and not purpose:
            purpose = "\n".join(str(b) for b in raw["bullets"] if b).strip()
        prev_at_index = None
        if previous_outline and i < len(previous_outline) and isinstance(previous_outline[i], dict):
            prev_at_index = previous_outline[i]
        if prev_at_index and normalize_chapter_title(prev_at_index.get("title")) != norm:
            old_purpose = str(prev_at_index.get("purpose") or "").strip()
            if purpose and purpose == old_purpose:
                purpose = ""
        if not purpose and norm in prev_by_title:
            purpose = prev_by_title[norm]
        spec = catalog.get(norm)
        if spec and (not purpose or purpose.startswith("Cover the approved chapter purpose")):
            purpose = spec.purpose
        elif spec and prev_at_index and normalize_chapter_title(prev_at_index.get("title")) != norm:
            purpose = spec.purpose
        out.append(
            {
                "order": int(raw.get("order") or raw.get("n") or i + 1),
                "title": title,
                "purpose": purpose,
                "approved": bool(raw.get("approved", True)),
            }
        )
    return out


def _research_citations(data: dict) -> list[str]:
    ws = data.get("ebook_workspace") or {}
    payload = ws.get("research_payload") or {}
    urls = [str(u) for u in (payload.get("source_urls") or []) if u]
    printing = payload.get("printing_research") or {}
    for fact in printing.get("manufacturer_facts") or []:
        if isinstance(fact, dict) and fact.get("source_url"):
            urls.append(str(fact["source_url"]))
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _research_brief_text(data: dict) -> str:
    ws = data.get("ebook_workspace") or {}
    payload = ws.get("research_payload") or {}
    parts = [str(payload.get("summary") or "").strip()]
    findings = payload.get("key_findings") or []
    if findings:
        parts.append("Key findings: " + "; ".join(str(f) for f in findings[:16]))
    return "\n".join(p for p in parts if p)


def _outline_digest_from_data(data: dict | None) -> str:
    outline = (data or {}).get("outline") or []
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


def build_book_contract(data: dict | None) -> BookContract:
    """Authoritative book + chapter contracts from project data."""
    from services.ebook_outline_fidelity import approved_outline_chapters

    data = data or {}
    ws = data.get("ebook_workspace") or {}
    stored = approved_outline_chapters(data)
    remapped = remap_outline_purposes(stored, previous_outline=None)
    titles = [c["title"] for c in remapped]
    catalog = event_photo_catalog_by_title()
    use_catalog = uses_event_photo_catalog(titles)
    chapters: list[ChapterContract] = []
    for item in remapped:
        spec = catalog.get(normalize_chapter_title(item["title"])) if use_catalog else None
        if spec:
            chapters.append(
                ChapterContract(
                    order=int(item["order"]),
                    title=item["title"],
                    purpose=spec.purpose,
                    reader_questions=list(spec.reader_questions),
                    required_facts=list(spec.required_facts),
                    required_citations=list(spec.required_citations),
                    required_examples=list(spec.required_examples),
                    required_table=spec.required_table,
                    required_workflow=spec.required_workflow,
                    required_checklist=spec.required_checklist,
                    min_useful_words=spec.min_useful_words,
                    prohibited_repetition=list(spec.prohibited_repetition),
                    prohibited_claims=list(spec.prohibited_claims),
                    acceptance_criteria=list(spec.acceptance_criteria),
                )
            )
        else:
            purpose = str(item.get("purpose") or "")
            need_table = any(k in purpose.lower() for k in ("table", "compar", "pric", "budget"))
            need_check = any(k in purpose.lower() for k in ("checklist", "check list"))
            need_flow = any(k in purpose.lower() for k in ("workflow", "booking", "procedure"))
            chapters.append(
                ChapterContract(
                    order=int(item["order"]),
                    title=item["title"],
                    purpose=purpose,
                    reader_questions=[f"What practical steps belong in {item['title']}?"],
                    required_facts=[],
                    required_examples=["concrete example or scenario"],
                    required_table="chapter-comparison" if need_table else "",
                    required_workflow="chapter-workflow" if need_flow else "",
                    required_checklist="chapter-checklist" if need_check else "",
                    min_useful_words=500,
                    acceptance_criteria=["Cover the approved purpose with usable steps"],
                )
            )
    req = event_photo_book_requirements() if use_catalog else {
        "tables": [], "comparisons": [], "workflows": [], "checklists": [],
    }
    citations = _research_citations(data)
    return BookContract(
        title=str(data.get("title") or ws.get("topic") or ""),
        subtitle=str(data.get("subtitle") or ""),
        author=str(ws.get("author") or data.get("author_brand") or ""),
        audience=str(ws.get("audience") or data.get("audience") or ""),
        primary_outcome=str(ws.get("outcome") or data.get("reader_promise") or ""),
        approved_outline=remapped,
        research_brief=_research_brief_text(data),
        citations=citations,
        editorial_rules=list(ws.get("editorial_rules_locked") or []),
        target_word_min=12000 if use_catalog else 4000,
        target_word_max=16000 if use_catalog else 12000,
        required_tables=list(req["tables"]),
        required_comparisons=list(req["comparisons"]),
        required_examples=["hypothetical dollar-margin scenario"] if use_catalog else [],
        required_workflows=list(req["workflows"]),
        required_checklists=list(req["checklists"]),
        prohibited_filler=sorted(GENERIC_FILLER_PHRASES),
        prohibited_unsupported_claims=sorted(UNSUPPORTED_CLAIM_PHRASES),
        front_matter=["title", "subtitle", "author"],
        back_matter=["disclaimer", "sources"],
        chapters=chapters,
        outline_digest=_outline_digest_from_data(data),
        catalog_id="event_photo_v1" if use_catalog else "generic",
    )


def book_contract_digest(contract: BookContract) -> str:
    return contract.digest()


def chapter_contract_prompt(book: BookContract, chapter: ChapterContract) -> str:
    lines = [
        f"BOOK TITLE: {book.title}",
        f"SUBTITLE: {book.subtitle}",
        f"AUTHOR (do not invent biography or quotes): {book.author}",
        f"AUDIENCE: {book.audience}",
        f"OUTCOME: {book.primary_outcome}",
        f"WRITE ONLY CHAPTER {chapter.order}: {chapter.title}",
        "Use that exact string as the ## heading. Do not write other chapters.",
        f"PURPOSE:\n{chapter.purpose}",
        "READER QUESTIONS TO ANSWER:",
    ]
    for q in chapter.reader_questions:
        lines.append(f"- {q}")
    if chapter.required_facts:
        lines.append("REQUIRED FACTS TO USE (do not invent extras):")
        for f in chapter.required_facts:
            lines.append(f"- {f}")
    if chapter.required_citations:
        lines.append("ATTRIBUTE THESE SOURCES WHERE USED:")
        for c in chapter.required_citations:
            lines.append(f"- {c}")
    if chapter.required_table:
        lines.append(f"REQUIRED MARKDOWN TABLE: {chapter.required_table}")
    if chapter.required_workflow:
        lines.append(f"REQUIRED NUMBERED WORKFLOW: {chapter.required_workflow}")
    if chapter.required_checklist:
        lines.append(f"REQUIRED CHECKLIST: {chapter.required_checklist}")
    if chapter.required_examples:
        lines.append("REQUIRED EXAMPLES (label hypothetical/planning scenarios clearly):")
        for e in chapter.required_examples:
            lines.append(f"- {e}")
    lines.append(f"MINIMUM USEFUL DEPTH: {chapter.min_useful_words} words of specific, usable content.")
    lines.append("Do not pad with repeated hedges. Do not add Conclusion/Disclaimer/Sources as H2.")
    if book.editorial_rules:
        lines.append("LOCKED EDITORIAL RULES:")
        for r in book.editorial_rules:
            lines.append(f"- {r}")
    if book.research_brief:
        lines.append("RESEARCH BRIEF (paraphrase; do not copy):\n" + book.research_brief[:6000])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def extract_markdown_tables(text: str) -> list[str]:
    tables: list[str] = []
    lines = (text or "").splitlines()
    i = 0
    while i < len(lines):
        if "|" in lines[i] and i + 1 < len(lines) and _TABLE_SEP_RE.search(lines[i + 1].replace(" ", "")):
            block = [lines[i], lines[i + 1]]
            i += 2
            while i < len(lines) and "|" in lines[i]:
                block.append(lines[i])
                i += 1
            tables.append("\n".join(block))
            continue
        i += 1
    return tables


def extract_list_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in (text or "").splitlines():
        if re.match(r"^\s*(?:[-*]|\d+\.)\s+\S", line):
            current.append(line.strip())
        else:
            if len(current) >= 3:
                blocks.append("\n".join(current))
            current = []
    if len(current) >= 3:
        blocks.append("\n".join(current))
    return blocks


def split_front_chapters_back(md_text: str) -> tuple[str, list[ParsedChapter], str]:
    text = md_text or ""
    matches = list(_H2_RE.finditer(text))
    if not matches:
        return text.strip(), [], ""
    front = text[: matches[0].start()].strip()
    chapters: list[ParsedChapter] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        title = m.group(1).strip()
        lists = extract_list_blocks(body)
        numbered = [b for b in lists if re.search(r"^\s*\d+\.", b, re.M)]
        bullets = [b for b in lists if not re.search(r"^\s*\d+\.", b, re.M)]
        examples = []
        for label in ("hypothetical", "example scenario", "planning scenario", "sample", "example"):
            if re.search(label, body, re.I):
                examples.append(label)
        citations = re.findall(r"https?://[^\s)]+", body)
        citations += re.findall(r"(?i)(?:source|according to)[:\s]+([A-Za-z0-9 ./-]{3,80})", body)
        chapters.append(
            ParsedChapter(
                order=i + 1,
                title=title,
                body=body,
                tables=extract_markdown_tables(body),
                checklists=bullets,
                workflows=numbered,
                examples=examples,
                citations=citations,
            )
        )
    back = ""
    if chapters:
        last = chapters[-1]
        parts = re.split(r"\n(?=\*\*(?:Disclaimer|Sources|References)\*\*)", last.body, maxsplit=1)
        if len(parts) == 2:
            last.body = parts[0].strip()
            back = parts[1].strip()
            last.tables = extract_markdown_tables(last.body)
            lists = extract_list_blocks(last.body)
            last.checklists = [b for b in lists if not re.search(r"^\s*\d+\.", b, re.M)]
            last.workflows = [b for b in lists if re.search(r"^\s*\d+\.", b, re.M)]
    return front, chapters, back


def assemble_manuscript(
    *,
    title: str,
    subtitle: str,
    author: str,
    chapters: list[ParsedChapter],
    disclaimer: str = "",
    sources: str = "",
) -> str:
    parts = [f"# {title}".strip()]
    if author:
        parts.append(f"*{author}*")
    if subtitle:
        parts.append(f"*{subtitle}*")
    for ch in chapters:
        parts.append(f"## {ch.title}\n\n{ch.body.strip()}")
    if disclaimer:
        label = disclaimer if disclaimer.lstrip().startswith("**") else f"**Disclaimer** {disclaimer}"
        parts.append(label.strip())
    if sources:
        label = sources if sources.lstrip().startswith("**") else f"**Sources** {sources}"
        parts.append(label.strip())
    return "\n\n".join(parts).strip() + "\n"


def parse_chapter_response(raw: Any, expected: ChapterContract) -> ParsedChapter:
    if isinstance(raw, dict):
        text = str(raw.get("ebook") or raw.get("content") or raw.get("chapter") or "")
    else:
        text = str(raw or "")
    _front, chapters, _back = split_front_chapters_back(text)
    if not chapters:
        body = re.sub(r"^#\s+.*\n", "", text).strip()
        return ParsedChapter(order=expected.order, title=expected.title, body=body)
    # Prefer the chapter whose title matches; else the first H2 body.
    for ch in chapters:
        if normalize_chapter_title(ch.title) == normalize_chapter_title(expected.title):
            ch.order = expected.order
            ch.title = expected.title
            return ch
    ch = chapters[0]
    ch.order = expected.order
    ch.title = expected.title
    return ch


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def _fact_present(fact: str, body: str) -> bool:
    needle = fact.lower().replace("×", "x")
    hay = body.lower().replace("×", "x")
    if needle in hay or needle.replace(" ", "") in hay.replace(" ", ""):
        return True
    if needle.endswith("es") and needle[:-2] in hay:
        return True
    if needle.endswith("s") and needle[:-1] in hay:
        return True
    if not needle.endswith("s") and (needle + "s") in hay:
        return True
    return False


def _negated_claim(body: str, phrase: str) -> bool:
    low = (body or "").lower()
    idx = 0
    saw = False
    while True:
        idx = low.find(phrase, idx)
        if idx < 0:
            return saw
        start = max(low.rfind(".", 0, idx), low.rfind("\n", 0, idx), 0)
        end = low.find(".", idx)
        if end < 0:
            end = len(low)
        sentence = low[start:end]
        if any(
            n in sentence
            for n in ("not ", "never ", "do not", "don't", "will not", "cannot", "no ", "without ")
        ):
            saw = True
            idx += len(phrase)
            continue
        return False


def _has_table_for(spec: str, tables: list[str], body: str) -> bool:
    blob = "\n".join(tables).lower() + "\n" + (body or "").lower()
    if not tables:
        return False
    tokens = {
        "event-niche-comparison": ["wedding", "school", "reunion"],
        "startup-budget-and-insurance": ["insurance", "$"],
        "starter-vs-event-kit": ["starter", "event"],
        "package-and-margin": ["$", "hour"],
        "event-planning-timeline": ["timeline"] ,
        "dye-sub-printer-comparison": ["ds-rx1hs", "ds620a", "qw410"],
        "chapter-comparison": ["|"],
    }.get(spec, [spec.replace("-", " ")[:12]])
    return all(t.lower() in blob for t in tokens)


def _has_workflow(spec: str, workflows: list[str], body: str) -> bool:
    blob = "\n".join(workflows).lower() + "\n" + (body or "").lower()
    if not workflows and not re.search(r"(?m)^\s*1\.\s+\S", body or ""):
        return False
    tokens = {
        "inquiry-to-signed-booking": ["inquiry", "contract"],
        "setup-queue-order-pay-pickup": ["queue", "pickup"],
        "event-day-run-of-show": ["before", "during"],
        "pre-event-planning": ["timeline"],
        "chapter-workflow": [],
    }.get(spec, [])
    return all(t in blob for t in tokens)


def _has_checklist(spec: str, checklists: list[str], body: str) -> bool:
    blob = "\n".join(checklists).lower() + "\n" + (body or "").lower()
    items = len(re.findall(r"(?m)^\s*(?:[-*]|\d+\.)\s+\S", body or ""))
    if items < 4:
        return False
    tokens = {
        "insurance-and-coi": ["insurance"],
        "space-power-cable-staffing": ["power", "cable"],
        "file-backup-procedure": ["backup"],
        "keepsake-go-no-go-staffing-safety": ["safety"],
        "first-paid-event-30-day": ["30"],
        "event-backup-kit": ["batter"],
        "chapter-checklist": [],
    }.get(spec, [])
    return all(t in blob for t in tokens)


def _excessive_hedging(body: str) -> bool:
    words = max(word_count(body), 1)
    hedges = len(_HEDGE_RE.findall(body or ""))
    sentences = max(len(re.findall(r"[.!?]", body or "")), 1)
    if words < 900 and hedges >= 5:
        return True
    return hedges >= 4 and (hedges / sentences) > 0.2


def _padding_without_substance(body: str, contract: ChapterContract, parsed: ParsedChapter) -> bool:
    words = word_count(body)
    if words < 1500:
        return False
    missing = False
    if contract.required_table and not parsed.tables:
        missing = True
    if contract.required_workflow and not parsed.workflows:
        missing = True
    if contract.required_checklist and not parsed.checklists:
        missing = True
    unique_ratio = len(set(_WORD_RE.findall(body.lower()))) / max(words, 1)
    return missing or unique_ratio < 0.18


def validate_chapter(
    parsed: ParsedChapter,
    contract: ChapterContract,
    *,
    book: BookContract | None = None,
) -> list[ChapterFinding]:
    findings: list[ChapterFinding] = []
    body = parsed.body or ""
    title = contract.title

    def add(code: str, message: str, severity: str = QUALITY_NEEDS_CORRECTION) -> None:
        findings.append(ChapterFinding(contract.order, title, code, message, severity))

    if normalize_chapter_title(parsed.title) != normalize_chapter_title(contract.title):
        add("CHAPTER_TITLE_MISMATCH", f"expected {contract.title!r} got {parsed.title!r}", QUALITY_FAIL)
    wc = word_count(body)
    if wc < contract.min_useful_words:
        add(
            "THIN_CHAPTER",
            f"{wc} useful words; minimum {contract.min_useful_words} with required deliverables",
        )
    purpose_tokens = [t for t in re.findall(r"[A-Za-z]{5,}", contract.purpose.lower()) if t not in {
        "about", "their", "there", "which", "where", "these", "those", "should", "would",
    }]
    hits = sum(1 for t in purpose_tokens[:12] if t in body.lower())
    if purpose_tokens and hits < max(2, min(4, len(purpose_tokens) // 4)):
        add("PURPOSE_MISALIGN", "Chapter body does not cover the approved purpose for this title")
    for fact in contract.required_facts:
        if not _fact_present(fact, body):
            add("MISSING_REQUIRED_FACT", f"Missing required fact or term: {fact}")
    for cite in contract.required_citations:
        blob = body.lower() + " " + " ".join(parsed.citations).lower()
        if cite.lower() not in blob:
            add("MISSING_CITATION", f"Missing required citation/attribution: {cite}")
    if contract.required_table and not _has_table_for(contract.required_table, parsed.tables, body):
        add("MISSING_REQUIRED_TABLE", f"Missing required table: {contract.required_table}")
    if contract.required_workflow and not _has_workflow(contract.required_workflow, parsed.workflows, body):
        add("MISSING_REQUIRED_WORKFLOW", f"Missing required workflow: {contract.required_workflow}")
    if contract.required_checklist and not _has_checklist(contract.required_checklist, parsed.checklists, body):
        add("MISSING_REQUIRED_CHECKLIST", f"Missing required checklist: {contract.required_checklist}")
    if contract.required_examples:
        blob = body.lower()
        if not parsed.examples and "hypothetical" not in blob and "example" not in blob:
            add("MISSING_REQUIRED_EXAMPLE", f"Missing required example: {contract.required_examples[0]}")
    if contract.required_table == "package-and-margin" and not _MONEY_RE.search(body):
        add("MISSING_DOLLAR_SCENARIO", "Pricing chapter has no labeled dollar amounts")
    low = body.lower()
    for phrase in GENERIC_FILLER_PHRASES:
        if phrase in low:
            add("GENERIC_FILLER", f"Generic filler phrase: {phrase}")
    for phrase in PLACEHOLDER_PHRASES:
        if phrase in low:
            add("PLACEHOLDER", f"Placeholder/production instruction: {phrase}", QUALITY_FAIL)
    for phrase in FOREVER_FORBIDDEN_MARKETING:
        if phrase in low and not _negated_claim(body, phrase):
            if phrase in {"secret"}:
                continue
            add("UNSUPPORTED_CLAIM", f"Forbidden marketing/unsupported claim: {phrase}")
    for match in _UNSUPPORTED_NUMERIC_RE.finditer(body):
        if not _negated_claim(body, match.group(0).lower()):
            add("UNSUPPORTED_CLAIM", "Unsupported numerical or outcome claim")
            break
    if _excessive_hedging(body):
        add("EXCESSIVE_HEDGING", "Chapter hedges instead of delivering the required specifics")
    if _padding_without_substance(body, contract, parsed):
        add("PADDING_WITHOUT_SUBSTANCE", "Word count without required tables/workflows/checklists")
    if book and book.author:
        # Invented first-person memoir using the listed author.
        if re.search(rf"\bI\b.{{0,40}}\b{re.escape(book.author.split()[0])}\b", body):
            add("UNSUPPORTED_CLAIM", "Possible invented personal story attributed to the listed author")
    return findings


def _repeated_material(chapters: list[ParsedChapter]) -> list[ChapterFinding]:
    findings: list[ChapterFinding] = []
    paras: dict[str, list[int]] = {}
    for ch in chapters:
        for para in re.split(r"\n\s*\n", ch.body or ""):
            key = re.sub(r"\s+", " ", para.strip().lower())
            if len(key) < 80:
                continue
            paras.setdefault(key, []).append(ch.order)
    for key, orders in paras.items():
        uniq = sorted(set(orders))
        if len(orders) >= 2 and len(uniq) >= 2:
            findings.append(
                ChapterFinding(
                    uniq[-1],
                    "",
                    "REPEATED_MATERIAL",
                    f"Substantially repeated paragraph across chapters {uniq}: {key[:80]}",
                    QUALITY_NEEDS_CORRECTION,
                )
            )
    return findings


def validate_manuscript_quality(
    data: dict | None = None,
    *,
    manuscript_md: str | None = None,
    book_contract: BookContract | None = None,
) -> QualityResult:
    """Server-authoritative quality gate. Word count alone can never PASS."""
    data = data or {}
    md = manuscript_md if manuscript_md is not None else str(data.get("content") or data.get("ebook") or "")
    book = book_contract or build_book_contract(data)
    fidelity = validate_manuscript_outline_fidelity(
        approved_outline=[{"order": c.order, "title": c.title, "purpose": c.purpose} for c in book.chapters],
        manuscript_md=md,
        current_outline_digest=book.outline_digest,
        token_outline_digest=book.outline_digest,
    )
    front, chapters, back = split_front_chapters_back(md)
    result = QualityResult(
        status=QUALITY_PASS,
        word_count=word_count(md),
        outline_ok=bool(fidelity.get("ok")),
    )
    structural_fail = False
    if not fidelity.get("ok"):
        structural_fail = True
        for msg in fidelity.get("findings") or []:
            code = "STRUCTURAL"
            sev = QUALITY_FAIL
            if "PROHIBITED_NUMBERED_BACK_MATTER" in str(msg) or "CHAPTER_COUNT" in str(msg) or "CHAPTER_TITLE" in str(msg) or "EXTRA_CHAPTER" in str(msg):
                sev = QUALITY_FAIL
            result.book_findings.append(str(msg))
            result.findings.append(ChapterFinding(0, "", code, str(msg), sev))

    generated = extract_manuscript_h2_titles(md)
    for title in generated:
        if normalize_chapter_title(title) in PROHIBITED_BACK_MATTER_TITLES:
            structural_fail = True
            result.findings.append(
                ChapterFinding(
                    0,
                    title,
                    "PROHIBITED_NUMBERED_BACK_MATTER",
                    f"{title} appeared as a numbered H2 chapter",
                    QUALITY_FAIL,
                )
            )

    # Align parsed chapters to contracts by order when titles match.
    by_title = {normalize_chapter_title(c.title): c for c in chapters}
    chapter_findings: list[ChapterFinding] = []
    for contract in book.chapters:
        parsed = by_title.get(normalize_chapter_title(contract.title))
        if parsed is None:
            chapter_findings.append(
                ChapterFinding(
                    contract.order,
                    contract.title,
                    "MISSING_CORE_CHAPTER",
                    "Approved chapter is missing from the manuscript",
                    QUALITY_FAIL,
                )
            )
            structural_fail = True
            result.chapter_results.append(
                {"order": contract.order, "title": contract.title, "status": QUALITY_FAIL, "words": 0}
            )
            continue
        parsed.order = contract.order
        cf = validate_chapter(parsed, contract, book=book)
        chapter_findings.extend(cf)
        ch_status = QUALITY_PASS
        if any(f.severity == QUALITY_FAIL for f in cf):
            ch_status = QUALITY_FAIL
        elif cf:
            ch_status = QUALITY_NEEDS_CORRECTION
        result.chapter_results.append(
            {
                "order": contract.order,
                "title": contract.title,
                "status": ch_status,
                "words": word_count(parsed.body),
                "findings": [f.as_dict() for f in cf],
                "tables": len(parsed.tables),
                "checklists": len(parsed.checklists),
                "workflows": len(parsed.workflows),
            }
        )

    chapter_findings.extend(_repeated_material(chapters))
    result.findings.extend(chapter_findings)

    back_l = (back or "").lower()
    if "disclaimer" not in back_l and "**disclaimer**" not in (md or "").lower():
        result.findings.append(
            ChapterFinding(0, "", "MISSING_DISCLAIMER", "Disclaimer must appear as unnumbered back matter", QUALITY_NEEDS_CORRECTION)
        )
    if "source" not in back_l and "**sources**" not in (md or "").lower():
        result.findings.append(
            ChapterFinding(0, "", "MISSING_SOURCES", "Sources must appear as unnumbered back matter", QUALITY_NEEDS_CORRECTION)
        )
    elif book.citations and back:
        missing_src = [c for c in book.citations[:6] if c.lower() not in (back + md).lower()]
        # Require at least one research URL in sources for catalog books.
        if book.catalog_id == "event_photo_v1" and missing_src and not re.search(r"https?://", back):
            result.findings.append(
                ChapterFinding(
                    0,
                    "",
                    "WEAK_SOURCES",
                    "Sources back matter does not list attributed research URLs",
                    QUALITY_NEEDS_CORRECTION,
                )
            )

    # Topic drift: body mentions none of the title tokens across most chapters.
    if book.catalog_id == "event_photo_v1":
        joined = (md or "").lower()
        if "dye" not in joined and "event photograph" not in joined:
            result.book_findings.append("TOPIC_DRIFT: manuscript does not stay on event photography / on-site printing")
            result.findings.append(
                ChapterFinding(0, "", "TOPIC_DRIFT", "Manuscript drifts off the approved topic", QUALITY_FAIL)
            )
            structural_fail = True

    # Word count is never sufficient for PASS.
    if result.word_count >= book.target_word_min and not any(
        f.code in {"MISSING_REQUIRED_TABLE", "MISSING_REQUIRED_WORKFLOW", "MISSING_REQUIRED_CHECKLIST", "THIN_CHAPTER"}
        for f in result.findings
    ):
        pass  # depth already enforced per chapter

    fail = structural_fail or any(f.severity == QUALITY_FAIL for f in result.findings)
    repair = any(f.severity == QUALITY_NEEDS_CORRECTION for f in result.findings)
    if fail:
        result.status = QUALITY_FAIL
    elif repair:
        result.status = QUALITY_NEEDS_CORRECTION
    else:
        # Guard: empty or tiny books cannot pass even if somehow finding-free.
        if result.word_count < 2500 or not book.chapters:
            result.status = QUALITY_NEEDS_CORRECTION
            result.findings.append(
                ChapterFinding(0, "", "THIN_MANUSCRIPT", "Manuscript is too thin to be professionally useful", QUALITY_NEEDS_CORRECTION)
            )
        else:
            result.status = QUALITY_PASS
    result.quality_ok = result.status == QUALITY_PASS
    return result


# ---------------------------------------------------------------------------
# Chapter pipeline (providers injected; default path makes no network calls)
# ---------------------------------------------------------------------------

def run_chapter_pipeline(
    book: BookContract,
    *,
    generate_chapter_fn: Callable[..., Any] | None = None,
    generate_fn: Callable[..., Any] | None = None,
    accepted_chapters: list[ParsedChapter] | None = None,
    repair_orders: list[int] | None = None,
    generate_fn_kwargs: dict[str, Any] | None = None,
    back_matter: str = "",
) -> dict[str, Any]:
    """Generate or repair chapters independently. Never silently rewrite accepted chapters."""
    accepted = {c.order: c for c in (accepted_chapters or [])}
    repair = set(repair_orders or [])
    produced: list[ParsedChapter] = []
    chapter_calls = 0

    if generate_chapter_fn is not None:
        for contract in book.chapters:
            if contract.order in accepted and (not repair or contract.order not in repair):
                kept = accepted[contract.order]
                kept.accepted = True
                produced.append(kept)
                continue
            raw = generate_chapter_fn(book, contract)
            chapter_calls += 1
            parsed = parse_chapter_response(raw, contract)
            parsed.order = contract.order
            parsed.title = contract.title
            produced.append(parsed)
    else:
        if generate_fn is None:
            raise ValueError("generate_chapter_fn or generate_fn is required")
        raw = generate_fn(**(generate_fn_kwargs or {}))
        chapter_calls = 1
        text = raw.get("ebook") if isinstance(raw, dict) else str(raw or "")
        if isinstance(raw, dict):
            text = str(raw.get("ebook") or raw.get("content") or "")
        _front, split_chs, _back = split_front_chapters_back(text)
        by_title = {normalize_chapter_title(c.title): c for c in split_chs}
        for contract in book.chapters:
            if contract.order in accepted and (not repair or contract.order not in repair):
                kept = accepted[contract.order]
                kept.accepted = True
                produced.append(kept)
                continue
            parsed = by_title.get(normalize_chapter_title(contract.title))
            if parsed is None:
                parsed = ParsedChapter(order=contract.order, title=contract.title, body="")
            parsed.order = contract.order
            parsed.title = contract.title
            produced.append(parsed)
        # If generate_fn returned a full book, capture back matter from it.
        full_md = text
    assembled = assemble_manuscript(
        title=book.title,
        subtitle=book.subtitle,
        author=book.author,
        chapters=produced,
        disclaimer="",
        sources="",
    )
    # Preserve unnumbered back matter from a one-shot payload or caller.
    if generate_chapter_fn is None and generate_fn is not None:
        orig = text if "text" in locals() else assembled
        _f2, _c2, back = split_front_chapters_back(orig)
        if back:
            assembled = assembled.rstrip() + "\n\n" + back.strip() + "\n"
    elif back_matter:
        assembled = assembled.rstrip() + "\n\n" + back_matter.strip() + "\n"

    quality = validate_manuscript_quality(manuscript_md=assembled, book_contract=book)
    accepted_out: list[ParsedChapter] = []
    failed_orders: list[int] = []
    ch_status = {r["order"]: r["status"] for r in quality.chapter_results}
    for ch in produced:
        if ch_status.get(ch.order) == QUALITY_PASS:
            ch.accepted = True
            accepted_out.append(ch)
        else:
            failed_orders.append(ch.order)
    return {
        "manuscript_md": assembled,
        "chapters": produced,
        "accepted_chapters": accepted_out,
        "failed_orders": failed_orders,
        "quality": quality,
        "chapter_calls": chapter_calls,
    }


def apply_quality_to_workspace(data: dict, quality: QualityResult) -> dict:
    """Persist quality findings. Does not mutate status by itself."""
    ws = data.setdefault("ebook_workspace", {})
    ws["manuscript_quality"] = quality.as_dict()
    ws["manuscript_quality_status"] = quality.status
    messages = quality.finding_messages
    # Keep outline-fidelity codes in structure_findings; quality in manuscript_qa.
    structure = [f.message for f in quality.findings if f.severity == QUALITY_FAIL and f.code in {
        "STRUCTURAL",
        "PROHIBITED_NUMBERED_BACK_MATTER",
        "MISSING_CORE_CHAPTER",
        "CHAPTER_TITLE_MISMATCH",
        "TOPIC_DRIFT",
        "PLACEHOLDER",
    } or str(f.code).startswith("CHAPTER_")]
    # Also copy fidelity book_findings that look structural.
    structure_msgs = [
        m for m in quality.book_findings
        if any(k in m for k in ("CHAPTER_", "PROHIBITED_", "OUTLINE_", "EXTRA_CHAPTER", "MISSING_CORE"))
    ]
    ws["manuscript_structure_findings"] = structure_msgs or [
        f.message for f in quality.findings if f.severity == QUALITY_FAIL
    ]
    ws["manuscript_qa"] = messages
    return data
