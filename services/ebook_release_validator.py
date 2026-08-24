"""Ebook-specific release validator.

Final status:
  PASS    — Ready for customer review
  WARNING — Human review required
  FAIL    — Save/export blocked (no Export Ready, no customer downloads)

Operates on the authoritative EbookDocument (+ optional PDF text / visual QA).
No paid API calls.

PASS/WARNING/FAIL may only be issued by the server via issue_release_certificate.
Client-invented status is rejected as stale/forged.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from services.ebook_document import (
    EbookDocument,
    find_customer_content_defects,
    strip_visual_instructions,
)

# Generic injected back-matter phrases (FAQ pools / Key Practice / Takeaway / Apply).
_GENERIC_BACK_MATTER_PATTERNS = [
    re.compile(r"how do i stay motivated over time\??", re.I),
    re.compile(r"is this approach right for me\??", re.I),
    re.compile(r"will these principles work for me\??", re.I),
    re.compile(r"what if my situation is unique\??", re.I),
    re.compile(r"do i need special tools or software\??", re.I),
    re.compile(r"key practice\s*[—\-:]", re.I),
    re.compile(r"apply one idea from this chapter today", re.I),
    re.compile(r"chapter action steps", re.I),
    re.compile(r"chapter at a glance", re.I),
    re.compile(r"\bkey insight\b", re.I),
    re.compile(r"chapter takeaway", re.I),
    re.compile(r"generic takeaway", re.I),
]


@dataclass
class ReleaseIssue:
    code: str
    severity: str  # fail | warning
    message: str


@dataclass
class EbookReleaseReport:
    status: str  # PASS | WARNING | FAIL
    issues: list[ReleaseIssue] = field(default_factory=list)
    export_ready: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.status == "PASS"

    @property
    def blocking(self) -> list[str]:
        return [i.message for i in self.issues if i.severity == "fail"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "export_ready": self.export_ready,
            "issues": [
                {"code": i.code, "severity": i.severity, "message": i.message}
                for i in self.issues
            ],
            "blocking": self.blocking,
            "details": dict(self.details),
        }


def release_identity_from_doc(
    doc: EbookDocument,
    *,
    project_id: Any = None,
    artifact_id: str = "",
    revision: Any = None,
) -> dict[str, Any]:
    """Identity fields that a PASS certificate must bind to."""
    doc.recompute_digests()
    return {
        "project_id": project_id if project_id is not None else doc.identity.project_id,
        "artifact_id": str(
            artifact_id
            or doc.identity.artifact_id
            or ""
        ),
        "revision": int(revision if revision is not None else doc.identity.revision or 1),
        "ebook_manuscript_digest": doc.identity.content_digest,
        "ebook_asset_manifest_digest": doc.identity.asset_manifest_digest,
        "cover_reference": str(doc.identity.cover_reference or ""),
        "design_theme_version": str(doc.identity.design_theme_version or doc.design_theme or ""),
    }


def issue_release_certificate(
    report: EbookReleaseReport,
    identity: dict[str, Any],
) -> dict[str, Any]:
    """Server-only release certificate. UI must display this verbatim."""
    payload = {
        "status": report.status,
        "export_ready": bool(report.export_ready and report.status == "PASS"),
        "issued_by": "server",
        "identity": dict(identity),
        "blocking": list(report.blocking),
        "issues": [
            {"code": i.code, "severity": i.severity, "message": i.message}
            for i in report.issues
        ],
    }
    digest_src = json.dumps(
        {
            "status": payload["status"],
            "identity": payload["identity"],
            "export_ready": payload["export_ready"],
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    payload["certificate_digest"] = hashlib.sha256(digest_src.encode("utf-8")).hexdigest()
    return payload


def verify_release_certificate(
    certificate: dict[str, Any] | None,
    current_identity: dict[str, Any],
    *,
    require_pass: bool = False,
) -> tuple[bool, str]:
    """Reject missing, client-forged, or stale certificates."""
    if not isinstance(certificate, dict) or not certificate:
        return False, "Missing server release certificate."
    if str(certificate.get("issued_by") or "") != "server":
        return False, "Release certificate was not issued by the server."
    status = str(certificate.get("status") or "").upper()
    if status not in {"PASS", "WARNING", "FAIL"}:
        return False, "Release certificate has an invalid status."
    if require_pass and status != "PASS":
        return False, f"Release certificate status is {status}, not PASS."
    bound = certificate.get("identity")
    if not isinstance(bound, dict):
        return False, "Release certificate missing identity binding."
    for key in (
        "ebook_manuscript_digest",
        "ebook_asset_manifest_digest",
        "cover_reference",
        "design_theme_version",
        "revision",
    ):
        if str(bound.get(key) or "") != str(current_identity.get(key) or ""):
            return False, f"Stale release certificate — '{key}' no longer matches."
    # project_id / artifact_id when present on both sides
    for key in ("project_id", "artifact_id"):
        cur = current_identity.get(key)
        old = bound.get(key)
        if cur not in (None, "") and old not in (None, "") and str(cur) != str(old):
            return False, f"Stale release certificate — '{key}' no longer matches."
    expected = issue_release_certificate(
        EbookReleaseReport(
            status=status,
            export_ready=bool(certificate.get("export_ready")),
            issues=[
                ReleaseIssue(
                    str(i.get("code") or "issue"),
                    str(i.get("severity") or "fail"),
                    str(i.get("message") or ""),
                )
                for i in (certificate.get("issues") or [])
                if isinstance(i, dict)
            ],
        ),
        bound,
    )["certificate_digest"]
    # Soft check: if digest present and mismatches, reject as forged/tampered.
    got = str(certificate.get("certificate_digest") or "")
    if got and got != expected:
        # Recompute with stored export_ready/status only — identity already matched.
        digest_src = json.dumps(
            {
                "status": status,
                "identity": bound,
                "export_ready": bool(certificate.get("export_ready")),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        if got != hashlib.sha256(digest_src.encode("utf-8")).hexdigest():
            return False, "Release certificate digest mismatch (forged or corrupted)."
    return True, ""


def invalidate_release_on_data(data: dict[str, Any]) -> dict[str, Any]:
    """Clear server PASS after content/theme/cover edits."""
    data = data if isinstance(data, dict) else {}
    data["release_status"] = ""
    data["export_ready"] = False
    data["release_certificate"] = None
    data["release_report"] = None
    return data


def validate_ebook_release(
    doc: EbookDocument,
    *,
    pdf_text: str = "",
    pdf_page_count: int = 0,
    visual_qa: dict | None = None,
    preview_identity: dict | None = None,
    export_identity: dict | None = None,
    require_research_forward: bool = False,
    pdf_qa_passed: Optional[bool] = None,
    originality_passed: Optional[bool] = None,
    has_pdf: bool = False,
    has_zip: bool = False,
    stale_export: bool = False,
) -> EbookReleaseReport:
    """Run all release gates. FAIL blocks export_ready."""
    issues: list[ReleaseIssue] = []
    details: dict[str, Any] = {}
    doc.recompute_digests()

    md = doc.manuscript_md or ""
    cleaned, removed = strip_visual_instructions(md)
    if removed:
        issues.append(
            ReleaseIssue(
                "placeholder_or_prompt_text",
                "fail",
                f"Visual/prompt instructions leaked into manuscript ({len(removed)} lines).",
            )
        )
    defects = find_customer_content_defects(md)
    details["content_defects"] = defects
    for d in defects:
        if d.startswith("leaked_visual_instruction"):
            issues.append(ReleaseIssue("leaked_visual_instruction", "fail", d))
        elif d.startswith("blocked_customer_phrase"):
            issues.append(ReleaseIssue("placeholder_or_prompt_text", "fail", d))
        elif d.startswith("duplicate_heading"):
            issues.append(ReleaseIssue("duplicated_heading", "fail", d))
        elif d.startswith("duplicate_paragraph"):
            issues.append(ReleaseIssue("duplicated_paragraph", "fail", d))
        elif d.startswith("duplicate_checklist"):
            issues.append(ReleaseIssue("duplicated_checklist", "fail", d))

    if re.search(r"sub-goal\s*#?\s*\d+", md, re.I):
        issues.append(
            ReleaseIssue(
                "generic_action_steps",
                "fail",
                "Generic action-step placeholders (sub-goal #N) present.",
            )
        )

    # Generic injected FAQ / Key Practice / Takeaway / Apply (not outline-backed).
    outline_titles = " ".join((o.title or "").lower() for o in (doc.outline or []))
    corpus_for_generic = md
    # Also inspect back_matter blob if present on the document.
    bm = doc.back_matter if isinstance(doc.back_matter, dict) else {}
    if bm:
        corpus_for_generic += "\n" + json.dumps(bm)
    for pat in _GENERIC_BACK_MATTER_PATTERNS:
        if not pat.search(corpus_for_generic):
            continue
        # Allow only when a matching outline section explicitly requested it.
        needle = pat.pattern.split(r"\s")[0].replace(r"\b", "").replace("?", "")
        outline_ok = False
        if "faq" in pat.pattern.lower() or "motivated" in pat.pattern.lower() or "approach right" in pat.pattern.lower():
            outline_ok = "faq" in outline_titles or "frequently asked" in outline_titles
        elif "key practice" in pat.pattern.lower() or "apply one idea" in pat.pattern.lower():
            outline_ok = "key practice" in outline_titles
        elif "action steps" in pat.pattern.lower() or "at a glance" in pat.pattern.lower():
            outline_ok = "action" in outline_titles
        elif "takeaway" in pat.pattern.lower() or "key insight" in pat.pattern.lower():
            outline_ok = "takeaway" in outline_titles or "insight" in outline_titles
        if not outline_ok:
            issues.append(
                ReleaseIssue(
                    "generic_injected_back_matter",
                    "fail",
                    f"Generic injected back matter detected ({pat.pattern[:48]}).",
                )
            )
            break
    if re.search(r"(?i)what\s+this\s+book\s+helps\s+you\s+do", md):
        # Allow once; fail on duplicate (find_customer_content_defects catches dup headings)
        count = len(re.findall(r"(?i)what\s+this\s+book\s+helps\s+you\s+do", md))
        if count > 1:
            issues.append(
                ReleaseIssue(
                    "duplicated_section_label",
                    "fail",
                    "Duplicate 'What This Book Helps You Do' section labels.",
                )
            )

    # Chapters (body chapters — skip known front/back-matter headings)
    _SKIP_SHORT = re.compile(
        r"^(introduction|summary|conclusion|resources|sources|references|"
        r"about the author|disclaimer|copyright|table of contents|toc)\b",
        re.I,
    )
    # Everything before the Table of Contents is front matter. Manuscripts that
    # write the subtitle as an H2 under the H1 ("## A practical guide for...")
    # otherwise register it as a body chapter and fail as "too short (N words)",
    # blocking release on a book whose real chapters are all fine.
    _toc_order = next(
        (
            c.order
            for c in doc.chapters
            if re.match(r"^(table of contents|toc)\b", (c.title or "").strip(), re.I)
        ),
        None,
    )
    body_chapters = [
        c
        for c in doc.chapters
        if not _SKIP_SHORT.match((c.title or "").strip())
        and (_toc_order is None or c.order > _toc_order)
    ]
    if len(body_chapters) < 3:
        issues.append(
            ReleaseIssue(
                "missing_chapter",
                "fail",
                f"Only {len(body_chapters)} body chapters — need at least 3.",
            )
        )
    for c in body_chapters:
        words = sum(len(re.findall(r"\w+", b.text)) for b in c.blocks)
        if words < 60:
            issues.append(
                ReleaseIssue(
                    "empty_or_short_chapter",
                    "fail",
                    f"Chapter '{c.title}' is too short ({words} words).",
                )
            )
        if not c.title.strip():
            issues.append(ReleaseIssue("missing_chapter", "fail", "A chapter is missing its title."))

    # Topic / audience / research drift
    topic = (doc.research.topic or doc.title or "").lower()
    if topic and doc.audience and doc.manuscript_md:
        topic_tokens = [t for t in re.findall(r"[a-z0-9]{4,}", topic) if t not in {"with", "that", "this", "from", "your"}]
        hits = sum(1 for t in topic_tokens[:8] if t in md.lower())
        if topic_tokens and hits == 0:
            issues.append(
                ReleaseIssue(
                    "topic_audience_drift",
                    "fail",
                    "Manuscript does not carry the approved topic forward.",
                )
            )
    if require_research_forward or doc.research.approved or doc.research.notes:
        if not doc.research.notes and not doc.research.sources:
            issues.append(
                ReleaseIssue(
                    "research_not_carried_forward",
                    "fail",
                    "Research was expected but brief/sources are missing.",
                )
            )

    # Visuals: planned must resolve or omit
    missing_visuals = [
        v for v in doc.visuals
        if v.status == "planned" or (v.kind in {"image", "photo"} and not v.asset_path and v.status != "omitted")
    ]
    for v in missing_visuals:
        issues.append(
            ReleaseIssue(
                "missing_planned_visual",
                "fail",
                f"Visual slot '{v.slot_id}' is not resolved to an asset/chart/table/diagram/omission.",
            )
        )
    broken = [v for v in doc.visuals if v.asset_path and v.status == "resolved" and v.asset_path.startswith("http://broken")]
    for v in broken:
        issues.append(ReleaseIssue("broken_asset", "fail", f"Broken asset path for '{v.slot_id}'."))

    # Cover
    if not doc.cover or not (
        doc.cover.get("title") or doc.title
    ):
        issues.append(ReleaseIssue("cover_mismatch", "fail", "Cover missing required identity fields."))
    else:
        cover_title = str(doc.cover.get("title") or "").strip()
        if cover_title and doc.title and cover_title.lower() != doc.title.lower():
            # warning unless completely unrelated
            if not any(tok in cover_title.lower() for tok in doc.title.lower().split()[:3] if len(tok) > 3):
                issues.append(
                    ReleaseIssue(
                        "cover_mismatch",
                        "fail",
                        "Cover title does not match approved ebook title.",
                    )
                )
        if doc.cover.get("generic_template") is True or doc.cover.get("plain_fallback") is True:
            issues.append(
                ReleaseIssue(
                    "cover_too_generic",
                    "fail",
                    "Cover is marked as a plain/generic template.",
                )
            )
        if not (
            doc.cover.get("local_cover_pdf")
            or doc.cover.get("image_path")
            or doc.cover.get("local_generated")
            or doc.cover.get("fixture")
        ):
            issues.append(
                ReleaseIssue(
                    "cover_mismatch",
                    "fail",
                    "Cover artwork reference missing (local fixture or asset required).",
                )
            )

    # Identity preview vs export
    if preview_identity and export_identity:
        for key in (
            "artifact_id",
            "revision",
            "content_digest",
            "asset_manifest_digest",
            "cover_reference",
            "design_theme_version",
        ):
            if preview_identity.get(key) != export_identity.get(key):
                issues.append(
                    ReleaseIssue(
                        "preview_export_mismatch",
                        "fail",
                        f"Preview/export identity mismatch on '{key}'.",
                    )
                )

    # PDF text-layer regression patterns
    corpus = (pdf_text or "") + "\n" + md
    _check_pdf_regression_patterns(corpus, issues)

    if pdf_qa_passed is False:
        issues.append(
            ReleaseIssue("unreadable_typography", "fail", "PDF QA validator reported FAIL.")
        )
    if originality_passed is False:
        issues.append(
            ReleaseIssue(
                "failed_plagiarism_originality",
                "fail",
                "Originality / plagiarism requirement failed.",
            )
        )
    if stale_export:
        issues.append(ReleaseIssue("stale_export", "fail", "Export package is stale vs current revision."))
    # When validating a finished package, missing PDF/ZIP is FAIL
    if has_pdf is False and export_identity is not None:
        issues.append(ReleaseIssue("missing_pdf", "fail", "PDF missing from export package."))
    if has_zip is False and export_identity is not None:
        issues.append(ReleaseIssue("missing_zip", "fail", "ZIP missing from export package."))

    # Visual QA signals
    vqa = visual_qa or {}
    for code in vqa.get("fail_codes") or []:
        issues.append(ReleaseIssue(str(code), "fail", f"Visual QA failed: {code}"))
    for code in vqa.get("warning_codes") or []:
        issues.append(ReleaseIssue(str(code), "warning", f"Visual QA warning: {code}"))

    if pdf_page_count and pdf_page_count < 4:
        issues.append(
            ReleaseIssue("incorrect_page_numbering", "warning", f"Very short PDF ({pdf_page_count} pages).")
        )

    # Author required
    if not (doc.author or "").strip():
        issues.append(ReleaseIssue("missing_author", "fail", "Author name is required."))

    fails = [i for i in issues if i.severity == "fail"]
    warns = [i for i in issues if i.severity == "warning"]
    if fails:
        status = "FAIL"
        export_ready = False
    elif warns:
        status = "WARNING"
        export_ready = False  # human review required — not Export Ready
    else:
        status = "PASS"
        export_ready = True

    doc.release_status = status
    doc.release_messages = [i.message for i in issues]
    doc.approval_state = "approved" if status == "PASS" else ("blocked" if status == "FAIL" else "in_review")

    return EbookReleaseReport(
        status=status,
        issues=issues,
        export_ready=export_ready,
        details=details,
    )


def classify_failed_pdf_text(text: str, *, title: str = "") -> EbookReleaseReport:
    """Classify a raw PDF/text extract (e.g. Average Joe fixture) as release status."""
    from services.ebook_document import EbookDocument, manuscript_to_chapters

    doc = EbookDocument(
        title=title or "Failed ebook fixture",
        author="",  # missing author → fail
        manuscript_md=text,
        chapters=manuscript_to_chapters(text),
        cover={"generic_template": True, "title": title or "Untitled"},
    )
    # Treat every planned visual as missing for fixture classification when suggestions present
    if re.search(r"chart\s+suggestion|diagram\s+suggestion|photo\s+placement|visual\s+plan", text, re.I):
        from services.ebook_document import VisualSlot

        doc.visuals.append(
            VisualSlot(slot_id="v_leaked", kind="image", brief="leaked", status="planned")
        )
    return validate_ebook_release(doc, pdf_text=text)


def _check_pdf_regression_patterns(corpus: str, issues: list[ReleaseIssue]) -> None:
    """Hard FAIL patterns from the Average Joe / Designrr failure class."""
    checks = [
        (
            r"visual\s+plan\s+for\s+this\s+chapter",
            "leaked_visual_plan",
            "Leaked 'Visual plan for this chapter' in finished book.",
        ),
        (
            r"chart\s+suggestion",
            "leaked_chart_suggestion",
            "Leaked chart suggestion in customer content.",
        ),
        (
            r"diagram\s+suggestion",
            "leaked_diagram_suggestion",
            "Leaked diagram suggestion in customer content.",
        ),
        (
            r"photo\s+placement",
            "leaked_photo_placement",
            "Leaked photo placement instruction in customer content.",
        ),
        (
            r"sub-goal\s*#?\s*[123]",
            "generic_subgoal",
            "Generic sub-goal #N action steps present.",
        ),
        (
            r"(?:C\s+hapter|S\s+creens|M\s+oney)\b",
            "abnormal_character_spacing",
            "Abnormal character spacing / run-apart glyphs detected.",
        ),
        (
            r"letter-spacing\s*:",
            "letter_spacing_css",
            "Customer-facing ebook content still contains letter-spacing CSS.",
        ),
        (
            r"Chapter\s+\d+\s*Chapter\s+\d+",
            "chapter_heading_collision",
            "Chapter labels appear to collide or duplicate without separation.",
        ),
    ]
    for pat, code, msg in checks:
        if re.search(pat, corpus, re.I):
            issues.append(ReleaseIssue(code, "fail", msg))

    # Duplicate table header rows (same header line repeated many times)
    header_lines = re.findall(r"^(?:\|\s*[\w ]+\s*\|.*)$", corpus, re.M)
    from collections import Counter

    for h, n in Counter(header_lines).items():
        if n >= 3 and len(h) > 8:
            issues.append(
                ReleaseIssue(
                    "duplicate_table_headers",
                    "fail",
                    f"Table header repeated {n} times: {h[:60]}",
                )
            )
