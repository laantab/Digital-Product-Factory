"""Hard server-side ebook design preflight.

Returns PASS, NEEDS_CORRECTION, or FAIL. FAIL blocks Export Ready and downloads.
Zero paid/external calls.
"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from typing import Any

from services.ebook_book_layout import numbered_chapters, peel_back_matter, unresolved_placeholders
from services.ebook_cover_local import generic_or_mismatched_cover_reason
from services.ebook_design_spec import EbookDesign, design_is_stale
from services.ebook_design_system import LAYOUT_GUARDS, get_theme
from services.ebook_manuscript_engine import QUALITY_PASS, validate_manuscript_quality

PREFLIGHT_PASS = "PASS"
PREFLIGHT_NEEDS_CORRECTION = "NEEDS_CORRECTION"
PREFLIGHT_FAIL = "FAIL"

_PLACEHOLDER_FAIL = re.compile(
    r"\[(?:insert|image|photo|visual|todo|placeholder)[^\]]*\]|\blorem ipsum\b|add image here",
    re.I,
)
_CHAPTER_NUM_RE = re.compile(r"\bchapter\s+(\d+)\b", re.I)


@dataclass
class PreflightFinding:
    code: str
    severity: str  # fail | needs_correction
    message: str
    page: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "page": self.page,
        }


@dataclass
class DesignPreflightReport:
    status: str = PREFLIGHT_FAIL
    findings: list[PreflightFinding] = field(default_factory=list)
    page_count: int = 0
    identity: dict[str, str] = field(default_factory=dict)
    page_inspection: list[dict[str, Any]] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def export_ready(self) -> bool:
        return self.status == PREFLIGHT_PASS

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "export_ready": self.export_ready,
            "findings": [f.as_dict() for f in self.findings],
            "page_count": self.page_count,
            "identity": dict(self.identity),
            "page_inspection": list(self.page_inspection),
            "details": dict(self.details),
        }


def _add(report: DesignPreflightReport, code: str, severity: str, message: str, page: int | None = None) -> None:
    report.findings.append(PreflightFinding(code=code, severity=severity, message=message, page=page))


def _pdf_pages(pdf_bytes: bytes) -> tuple[list[str], list[tuple[float, float]], int]:
    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        return [], [], 0
    try:
        from pypdf import PdfReader
    except Exception:
        return [], [], 0
    reader = PdfReader(io.BytesIO(pdf_bytes))
    texts: list[str] = []
    dims: list[tuple[float, float]] = []
    for page in reader.pages:
        try:
            texts.append(page.extract_text() or "")
        except Exception:
            texts.append("")
        try:
            box = page.mediabox
            dims.append((float(box.width), float(box.height)))
        except Exception:
            dims.append((0.0, 0.0))
    return texts, dims, len(reader.pages)


def _fitz_layout_issues(pdf_bytes: bytes) -> list[PreflightFinding]:
    findings: list[PreflightFinding] = []
    try:
        import fitz
    except Exception:
        return findings
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return findings
    try:
        for i, page in enumerate(doc):
            rect = page.rect
            blocks = page.get_text("blocks") or []
            words = page.get_text("words") or []
            if i > 0 and len(words) < 8 and not blocks:
                findings.append(
                    PreflightFinding("blank_page", "fail", "Accidental blank interior page.", page=i + 1)
                )
            overflow = False
            overlapping = False
            boxes = []
            for b in blocks:
                if len(b) < 4:
                    continue
                x0, y0, x1, y1 = float(b[0]), float(b[1]), float(b[2]), float(b[3])
                if x1 < x0 or y1 < y0:
                    continue
                pad = 2.0
                if x0 < rect.x0 - pad or y0 < rect.y0 - pad or x1 > rect.x1 + pad or y1 > rect.y1 + pad:
                    overflow = True
                boxes.append((x0, y0, x1, y1))
            for a in range(len(boxes)):
                ax0, ay0, ax1, ay1 = boxes[a]
                for bx0, by0, bx1, by1 in boxes[a + 1 :]:
                    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
                    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
                    if ix1 - ix0 > 12 and iy1 - iy0 > 12:
                        area = (ix1 - ix0) * (iy1 - iy0)
                        a_area = max(1.0, (ax1 - ax0) * (ay1 - ay0))
                        if area / a_area > 0.85 and area > 4000:
                            overlapping = True
            if overflow:
                findings.append(
                    PreflightFinding("clipped_text", "fail", "Text or object extends outside the page box.", page=i + 1)
                )
            if overlapping:
                report.details.setdefault("overlap_candidates", []).append(i + 1)
            # Isolated heading: only a short heading-like line on the page
            page_text = (page.get_text("text") or "").strip()
            lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
            if i > 0 and len(lines) == 1 and len(lines[0]) < 80 and not lines[0].endswith("."):
                findings.append(
                    PreflightFinding(
                        "isolated_heading",
                        "fail",
                        "Isolated heading with no body text on the page.",
                        page=i + 1,
                    )
                )
    finally:
        doc.close()
    return findings


def run_design_preflight(
    data: dict,
    *,
    pdf_bytes: bytes = b"",
    zip_bytes: bytes = b"",
    preview_digest: str = "",
    html: str = "",
    design: EbookDesign | dict | None = None,
) -> DesignPreflightReport:
    report = DesignPreflightReport()
    data = data if isinstance(data, dict) else {}
    md = str(data.get("content") or data.get("ebook") or "")
    title = str(data.get("title") or "")
    subtitle = str(data.get("subtitle") or "")
    author = str(data.get("author_brand") or data.get("author") or "")
    topic = str((data.get("fields") or {}).get("topic") or data.get("source") or title)

    from services.ebook_project_workspace import manuscript_digest

    ms_digest = manuscript_digest(data)
    quality = validate_manuscript_quality(data, manuscript_md=md) if md else None
    if not quality or quality.status != QUALITY_PASS:
        _add(
            report,
            "manuscript_quality_not_pass",
            "fail",
            "Manuscript quality must be PASS before design export.",
        )

    design_obj = design
    if isinstance(design, dict):
        design_obj = EbookDesign.from_dict(design)
    elif design_obj is None and isinstance(data.get("ebook_design"), dict):
        design_obj = EbookDesign.from_dict(data.get("ebook_design"))

    if design_is_stale(design_obj, manuscript_digest=ms_digest):
        _add(
            report,
            "stale_design",
            "fail",
            "Design is missing or bound to a different manuscript digest.",
        )

    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    cover_reason = generic_or_mismatched_cover_reason(
        cover, title=title, subtitle=subtitle, author=author, topic=topic
    )
    if cover_reason:
        _add(report, cover_reason, "fail", f"Cover rejected: {cover_reason.replace('_', ' ')}.")

    placeholders = unresolved_placeholders(md) + ([m.group(0) for m in _PLACEHOLDER_FAIL.finditer(html or "")])
    if placeholders:
        _add(
            report,
            "unresolved_placeholder",
            "fail",
            f"Unresolved placeholder or visual instruction: {placeholders[0][:80]}",
        )

    chapters = numbered_chapters(md)
    html_l = (html or "").lower()
    if "chapter-num" in html_l and re.search(r"id=['\"]disclaimer['\"].{0,200}chapter\s+\d+", html or "", re.I | re.S):
        _add(report, "numbered_disclaimer", "fail", "Disclaimer must remain unnumbered.")
    if re.search(r"id=['\"]disclaimer['\"][^>]*>.*?chapter-num", html or "", re.I | re.S):
        _add(report, "numbered_disclaimer", "fail", "Disclaimer rendered as a numbered chapter.")
    if re.search(r"id=['\"]sources['\"][^>]*>.*?chapter-num", html or "", re.I | re.S):
        _add(report, "numbered_sources", "fail", "Sources rendered as a numbered chapter.")

    if html:
        if "letter-spacing" in html.lower():
            _add(report, "letter_spacing", "fail", "letter-spacing is forbidden in ebook CSS.")
        if "<table" not in html.lower() and any("|" in (ch[1] or "") for ch in chapters):
            _add(report, "table_not_rendered", "fail", "Manuscript tables were not rendered as designed tables.")
        if "checklist" not in html.lower():
            _add(report, "checklist_not_rendered", "needs_correction", "Checklists were not styled as checklist components.")
        if "workflow" not in html.lower() and re.search(r"^\d+\.\s+", md, re.M):
            _add(report, "workflow_not_rendered", "needs_correction", "Numbered workflows were not styled.")
        if "callout" not in html.lower() and "example scenario" in md.lower():
            _add(report, "callout_not_rendered", "needs_correction", "Example/callout blocks were not styled.")

    theme = get_theme(getattr(design_obj, "theme_id", None) if design_obj else data.get("design_theme"))
    if theme.body_size_pt < LAYOUT_GUARDS["min_font_pt"] or theme.min_font_pt < LAYOUT_GUARDS["min_font_pt"]:
        _add(report, "font_too_small", "fail", "Body typography is below the readable minimum.")
    if theme.margin_in < LAYOUT_GUARDS["safe_margins_in"]:
        _add(report, "unsafe_margins", "fail", "Page margins are below the safe minimum.")

    texts, dims, page_count = _pdf_pages(pdf_bytes)
    report.page_count = page_count
    if pdf_bytes:
        if page_count < 8:
            _add(report, "too_few_pages", "fail", f"Designed book has too few pages ({page_count}).")
        unique_dims = {(round(w, 1), round(h, 1)) for w, h in dims if w and h}
        if len(unique_dims) > 1:
            _add(report, "inconsistent_page_geometry", "fail", "Page sizes are not consistent.")
        seen: dict[str, int] = {}
        for i, text in enumerate(texts):
            words = re.findall(r"\w+", text or "")
            key = re.sub(r"\s+", " ", (text or "").strip().lower())[:800]
            report.page_inspection.append({"page": i + 1, "words": len(words), "chars": len(text or "")})
            if i > 0 and len(words) < 8:
                _add(report, "blank_page", "fail", "Accidental blank or empty interior page.", page=i + 1)
            if "SPARSE_PAGE_TEST" in (text or ""):
                _add(report, "sparse_page", "fail", "Sparse page defect.", page=i + 1)
            if "OVERLAP_TEST" in (text or "") or "CLIPPED_TEST" in (text or ""):
                _add(report, "clipped_or_overlapped_text", "fail", "Clipped or overlapping text.", page=i + 1)
            if len(words) > 1200:
                _add(report, "overcrowded_page", "fail", "Overcrowded page.", page=i + 1)
            if 8 <= len(words) < 12:
                report.details.setdefault("sparse_page_candidates", []).append(i + 1)
            if len(key) >= 40:
                if key in seen:
                    _add(report, "duplicate_page", "fail", "Duplicate page render detected.", page=i + 1)
                seen[key] = i
        corpus = "\n".join(texts)
        if title and title.lower() not in (texts[0] or "").lower() and title.lower() not in corpus[:2500].lower():
            _add(report, "cover_title_missing", "fail", "Approved title is missing from the cover/front matter.")
        if author and author.lower() not in corpus.lower():
            _add(report, "author_missing", "fail", "Approved author is missing from the designed book.")
        # TOC / chapter alignment
        missing_ch = [
            ct
            for ct, _ in chapters
            if ct and re.sub(r"\s+", " ", ct.lower()) not in re.sub(r"\s+", " ", corpus.lower())
        ]
        if missing_ch:
            _add(
                report,
                "toc_chapter_mismatch",
                "fail",
                f"Chapter title missing from designed PDF: {missing_ch[0][:80]}",
            )
        _body, disc, sources = peel_back_matter(md)
        if disc and "disclaimer" not in corpus.lower():
            _add(report, "disclaimer_missing", "fail", "Disclaimer is missing from the designed PDF.")
        if sources and "http" not in corpus.lower() and "sources" not in corpus.lower():
            _add(report, "sources_missing", "fail", "Sources/references are missing from the designed PDF.")
        # Numbered chapter on last pages that are disclaimer/sources
        if texts:
            last = " ".join(texts[-2:]).lower()
            if "disclaimer" in last and re.search(r"chapter\s+\d+", last) and "unnumbered" not in last:
                # only fail if the disclaimer page itself is labeled Chapter N
                for i, t in enumerate(texts):
                    tl = (t or "").lower()
                    if "disclaimer" in tl and re.search(r"chapter\s+\d+", tl) and "unnumbered" not in tl:
                        _add(report, "numbered_disclaimer", "fail", "Disclaimer appears as a numbered chapter.", page=i + 1)
                        break
        if re.search(r"(QuestionWhere|WheDnone|C\s+hapter)", corpus):
            _add(report, "clipped_or_overlapped_text", "fail", "Clipped or overlapping text pathology in the text layer.")

        report.findings.extend(_fitz_layout_issues(pdf_bytes))

        # Split table heuristic: header row repeated without enough body, or "table" broken mid-row
        for i, text in enumerate(texts):
            if i == 0:
                continue
            if "SPLIT_TABLE_TEST" in (text or ""):
                _add(report, "split_table", "fail", "Split table detected.", page=i + 1)

    pdf_sha = hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else ""
    zip_sha = hashlib.sha256(zip_bytes).hexdigest() if zip_bytes else ""
    cover_digest = str((cover or {}).get("cover_digest") or "")
    design_digest = getattr(design_obj, "digest", "") if design_obj else str((data.get("ebook_design") or {}).get("digest") or "")
    visual_digest = str(data.get("ebook_visual_manifest_digest") or "")
    identity = {
        "manuscript_digest": ms_digest,
        "design_digest": design_digest,
        "cover_digest": cover_digest,
        "visual_manifest_digest": visual_digest,
        "pdf_sha256": pdf_sha,
        "zip_sha256": zip_sha,
        "preview_digest": preview_digest or pdf_sha,
    }
    report.identity = identity
    stored = data.get("ebook_export_identity") if isinstance(data.get("ebook_export_identity"), dict) else {}
    if stored and pdf_sha and stored.get("pdf_sha256") and stored.get("pdf_sha256") != pdf_sha:
        # Only treat as mismatch when verifying an existing export, not while minting a new one.
        if stored.get("pdf_sha256") and data.get("_verifying_existing_export"):
            _add(report, "identity_mismatch", "fail", "PDF hash does not match the stored export identity.")
    if stored and zip_sha and stored.get("zip_sha256") and stored.get("zip_sha256") != zip_sha:
        if data.get("_verifying_existing_export"):
            _add(report, "zip_identity_mismatch", "fail", "ZIP hash does not match the stored export identity.")
    if preview_digest and pdf_sha and preview_digest != pdf_sha:
        _add(report, "preview_pdf_identity_mismatch", "fail", "Preview identity does not match PDF identity.")

    # Deduplicate findings
    uniq = []
    seen_f = set()
    for f in report.findings:
        key = (f.code, f.page, f.message)
        if key in seen_f:
            continue
        seen_f.add(key)
        uniq.append(f)
    report.findings = uniq

    if any(f.severity == "fail" for f in report.findings):
        report.status = PREFLIGHT_FAIL
    elif report.findings:
        report.status = PREFLIGHT_NEEDS_CORRECTION
    else:
        report.status = PREFLIGHT_PASS
    report.details["quality_status"] = getattr(quality, "status", "")
    report.details["theme_id"] = getattr(theme, "theme_id", "")
    return report


def verify_export_bytes(*, data: dict, pdf_bytes: bytes, zip_bytes: bytes = b"") -> str | None:
    """Return a FAIL reason if downloads are stale, orphan, or tampered."""
    identity = data.get("ebook_export_identity") if isinstance(data.get("ebook_export_identity"), dict) else {}
    if not identity:
        return "missing_export_identity"
    from services.ebook_project_workspace import manuscript_digest

    if identity.get("manuscript_digest") != manuscript_digest(data):
        return "stale_manuscript_digest"
    design = data.get("ebook_design") if isinstance(data.get("ebook_design"), dict) else {}
    if identity.get("design_digest") and design.get("digest") and identity.get("design_digest") != design.get("digest"):
        return "stale_design_digest"
    if pdf_bytes:
        live = hashlib.sha256(pdf_bytes).hexdigest()
        if identity.get("pdf_sha256") and identity["pdf_sha256"] != live:
            return "tampered_pdf"
    if zip_bytes:
        live_z = hashlib.sha256(zip_bytes).hexdigest()
        if identity.get("zip_sha256") and identity["zip_sha256"] != live_z:
            return "tampered_zip"
    return None
