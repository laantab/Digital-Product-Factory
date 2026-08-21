"""Editor-in-Chief — independent release gate for every Factory product.

The production agent builds a candidate; this module reviews the *finished
artifact* and returns a verdict the production agent cannot overrule. It is
deliberately generic: no product type, project id, topic, filename, or asset
hash appears in any rule below.

Design stance
-------------
Two kinds of check live here and they are never blended:

  * OBJECTIVE  -- decidable from the artifact itself (a digest matches or it
    does not; a page is blank or it is not; an image is 900px or it is not).
    These produce PASS/FAIL directly.

  * JUDGMENT   -- requires reading meaning or subject-matter expertise (is
    this photograph actually the movement the text describes? is this claim
    true?). Code cannot settle these. Rather than guess, the reviewer raises
    a REVIEW_REQUIRED finding, which blocks PASS and names what a human must
    confirm. Silently treating an unverifiable thing as verified is the one
    failure mode this module exists to prevent.

A serious defect is never averaged away. Category scores are advisory; the
blocker list is authoritative.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

VERDICT_PASS = "EDITOR-IN-CHIEF PASS"
VERDICT_CORRECTION = "EDITOR-IN-CHIEF — CORRECTION REQUIRED"
VERDICT_BLOCKED = "EDITOR-IN-CHIEF — BLOCKED"

SEV_CRITICAL = "critical"
SEV_MAJOR = "major"
SEV_MINOR = "minor"

KIND_OBJECTIVE = "objective"
KIND_JUDGMENT = "judgment"

# Categories scored 1-10. PASS requires every applicable category >= 8,
# overall >= 9, and package_integrity == 10.
CATEGORIES = (
    "originality", "relevance", "accuracy", "consistency", "editorial_quality",
    "visual_quality", "instructional_value", "image_resolution", "cover_quality",
    "interior_design", "accessibility", "package_integrity", "customer_value",
)
MIN_CATEGORY = 8
MIN_OVERALL = 9
PACKAGE_INTEGRITY_REQUIRED = 10

# Subjects where a wrong instructional visual can hurt somebody. A visual in
# one of these domains is never auto-approved on metadata alone.
SAFETY_SENSITIVE_TERMS = (
    "exercise", "workout", "fitness", "strength", "training", "stretch",
    "yoga", "pilates", "rehab", "physical therapy", "posture", "lifting",
    "medical", "health", "medication", "dosage", "nutrition", "diet",
    "food safety", "cooking", "knife", "machinery", "power tool", "saw",
    "drill", "electrical", "wiring", "ladder", "chemical", "welding",
    "firearm", "climbing", "swimming", "childcare", "infant", "toddler",
    "finance", "investment", "tax", "legal",
)

PLACEHOLDER_PATTERNS = (
    r"\blorem ipsum\b", r"\bTODO\b", r"\bTBD\b", r"\bFIXME\b",
    r"\bplaceholder\b", r"\bcoming soon\b", r"\[insert[^\]]*\]",
    r"\bXXX+\b", r"\bYOUR (?:NAME|TITLE|BRAND) HERE\b",
)
# Text that reveals the generator rather than serving the reader.
PROMPT_LEAK_PATTERNS = (
    r"\bas an ai\b", r"\bas a language model\b", r"\bi cannot\b.{0,40}\bas an ai\b",
    r"\byou are a helpful\b", r"\bsystem prompt\b", r"\bwrite a chapter about\b",
    r"\bhere is the (?:chapter|section|article) you requested\b",
    r"\bcertainly!\s+here\b", r"\bi hope this helps\b",
)

_MIN_BODY_PT = 9.0
_MIN_CAPTION_PT = 8.0
_PRINT_DPI_TARGET = 300
_PRINT_DPI_REVIEW = 200
_PRINT_DPI_BLOCK = 150


@dataclass
class Finding:
    code: str
    category: str
    severity: str
    kind: str
    summary: str
    detail: str = ""
    location: str = ""
    asset: str = ""

    def blocks(self) -> bool:
        """Critical always blocks. A judgment finding blocks PASS even at
        major severity: an unverified safety-sensitive visual is exactly the
        thing that must not slip through on someone's optimism."""
        return self.severity == SEV_CRITICAL or (
            self.kind == KIND_JUDGMENT and self.severity in (SEV_CRITICAL, SEV_MAJOR)
        )


@dataclass
class ReviewReport:
    verdict: str = VERDICT_CORRECTION
    findings: list[Finding] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)
    overall: float = 0.0
    checks_run: list[str] = field(default_factory=list)
    checks_skipped: dict[str, str] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    external_plagiarism_checked: bool = False

    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.blocks()]

    def by_severity(self, sev: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == sev]

    def customer_message(self) -> str:
        if self.verdict == VERDICT_PASS:
            return "Quality review passed — ready for your review."
        if self.verdict == VERDICT_BLOCKED:
            return "We found production issues and are correcting them before your review."
        return "We found production issues and are correcting them before your review."

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["blocker_count"] = len(self.blockers())
        d["customer_message"] = self.customer_message()
        return d


def _sha(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return ""


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def is_safety_sensitive(*texts: str) -> bool:
    blob = _norm(" ".join(str(t or "") for t in texts))
    return any(term in blob for term in SAFETY_SENSITIVE_TERMS)


# ---------------------------------------------------------------------------
# 1. Originality — internal only. External search is never assumed.
# ---------------------------------------------------------------------------
def check_self_duplication(manuscript: str, *, min_words: int = 12) -> list[Finding]:
    """Repeated paragraphs and repeated chapter openers/closers inside one book."""
    out: list[Finding] = []
    paras = [p.strip() for p in re.split(r"\n\s*\n", str(manuscript or "")) if p.strip()]
    seen: dict[str, int] = {}
    for p in paras:
        body = _norm(re.sub(r"[#*_`>-]", " ", p))
        if len(body.split()) < min_words:
            continue
        seen[body] = seen.get(body, 0) + 1
    for body, n in seen.items():
        if n > 1:
            out.append(Finding(
                code="ORIG_DUP_PARAGRAPH", category="originality",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary=f"A paragraph appears {n} times in the manuscript.",
                detail=body[:180],
            ))
    return out


def check_cross_project_duplication(
    manuscript: str, other_manuscripts: dict[Any, str], *, min_words: int = 25
) -> list[Finding]:
    """Long passages shared with another product in the library."""
    out: list[Finding] = []
    mine = {
        _norm(p): p for p in re.split(r"\n\s*\n", str(manuscript or ""))
        if len(_norm(p).split()) >= min_words
    }
    if not mine:
        return out
    for pid, other in (other_manuscripts or {}).items():
        theirs = {
            _norm(p) for p in re.split(r"\n\s*\n", str(other or ""))
            if len(_norm(p).split()) >= min_words
        }
        shared = set(mine) & theirs
        for body in list(shared)[:5]:
            out.append(Finding(
                code="ORIG_CROSS_PROJECT", category="originality",
                severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                summary=f"A substantial passage is identical to project {pid}.",
                detail=body[:180], location=f"project {pid}",
            ))
    return out


def check_placeholder_and_leak(manuscript: str) -> list[Finding]:
    out: list[Finding] = []
    text = str(manuscript or "")
    for pat in PLACEHOLDER_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            out.append(Finding(
                code="EDIT_PLACEHOLDER", category="editorial_quality",
                severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                summary="Placeholder text reached the customer-facing manuscript.",
                detail=text[max(0, m.start() - 60):m.end() + 60].strip(),
            ))
    for pat in PROMPT_LEAK_PATTERNS:
        m = re.search(pat, text, re.I)
        if m:
            out.append(Finding(
                code="EDIT_PROMPT_LEAK", category="editorial_quality",
                severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                summary="Generator/prompt language leaked into the manuscript.",
                detail=text[max(0, m.start() - 60):m.end() + 60].strip(),
            ))
    return out


# ---------------------------------------------------------------------------
# 2. Relevance
# ---------------------------------------------------------------------------
_STOP = frozenset("""a an the and or but of for to in on at by with from as is are was were be been
this that these those your you it its how what why when where which who will can may
into over under more most other some such only own same than too very just about""".split())


def _content_tokens(text: str, limit: int = 400) -> set[str]:
    toks = [w for w in re.findall(r"[a-z]{4,}", _norm(text)) if w not in _STOP]
    return set(toks[:limit])


def check_relevance(title: str, chapters: list[tuple[str, str]], *, floor: float = 0.34) -> list[Finding]:
    """Each chapter should speak the product's vocabulary.

    Measured as the share of the *title's* distinctive words that appear in
    the chapter -- not as a ratio over the chapter body. A ratio over the body
    punishes long chapters purely for being long, which produces a false
    alarm on every substantial book; the question that actually matters is
    whether the subject shows up at all.

    Deliberately forgiving: this is meant to catch a chapter belonging to a
    different product, not stylistic variety.
    """
    out: list[Finding] = []
    title_toks = _content_tokens(title)
    for ctitle, body in chapters or []:
        body_toks = _content_tokens(body, limit=4000)
        if not body_toks:
            out.append(Finding(
                code="REL_EMPTY_CHAPTER", category="relevance",
                severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                summary="Chapter has no readable body text.", location=ctitle,
            ))
            continue
        if not title_toks:
            continue
        # A chapter earns relevance either by echoing the product vocabulary
        # or by echoing its own heading -- both mean it is on subject.
        title_hit = len(title_toks & body_toks) / max(len(title_toks), 1)
        head_toks = _content_tokens(ctitle)
        head_hit = (len(head_toks & body_toks) / max(len(head_toks), 1)) if head_toks else 0.0
        if max(title_hit, head_hit) < floor:
            out.append(Finding(
                code="REL_OFF_TOPIC", category="relevance",
                severity=SEV_MAJOR, kind=KIND_JUDGMENT,
                summary="Chapter shares little vocabulary with the product; confirm it belongs.",
                detail=f"title match {title_hit:.2f}, heading match {head_hit:.2f}, floor {floor}",
                location=ctitle,
            ))
    return out


# ---------------------------------------------------------------------------
# 3. Consistency
# ---------------------------------------------------------------------------
def check_identity_consistency(
    *, title: str, author: str, pdf_title: str, pdf_author: str,
    cover_title: str = "", toc_titles: list[str] | None = None,
    chapter_titles: list[str] | None = None,
) -> list[Finding]:
    out: list[Finding] = []
    if title and pdf_title and _norm(title) != _norm(pdf_title):
        out.append(Finding(
            code="META_TITLE_MISMATCH", category="consistency",
            severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
            summary="PDF title metadata does not match the product title.",
            detail=f"product={title!r} pdf={pdf_title!r}",
        ))
    if author and not _norm(pdf_author):
        out.append(Finding(
            code="META_AUTHOR_MISSING", category="package_integrity",
            severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
            summary="PDF author metadata is empty.",
            detail=f"expected {author!r}",
        ))
    elif author and pdf_author and _norm(author) != _norm(pdf_author):
        out.append(Finding(
            code="META_AUTHOR_MISMATCH", category="consistency",
            severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
            summary="PDF author metadata does not match the product author.",
            detail=f"product={author!r} pdf={pdf_author!r}",
        ))
    if toc_titles and chapter_titles:
        if [_norm(t) for t in toc_titles] != [_norm(t) for t in chapter_titles]:
            out.append(Finding(
                code="CONS_TOC_MISMATCH", category="consistency",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary="Table of contents does not match the chapters present.",
            ))
    return out


# ---------------------------------------------------------------------------
# 4. Images: existence, integrity, resolution at placement
# ---------------------------------------------------------------------------
def inspect_image_file(path: str) -> dict[str, Any]:
    """Objective facts about one image. Never an opinion about its subject."""
    info: dict[str, Any] = {"path": path, "exists": False, "opens": False,
                            "width": 0, "height": 0, "bytes": 0, "mode": "",
                            "format": "", "flat": False}
    if not path or not os.path.isfile(path):
        return info
    info["exists"] = True
    info["bytes"] = os.path.getsize(path)
    try:
        from PIL import Image

        with Image.open(path) as im:
            im.load()
            info["opens"] = True
            info["width"], info["height"] = im.size
            info["mode"] = im.mode
            info["format"] = im.format or ""
            g = im.convert("L").resize((64, 64))
            hist = g.histogram()
            total = float(sum(hist)) or 1.0
            mean = sum(i * c for i, c in enumerate(hist)) / total
            var = (sum(((i - mean) ** 2) * c for i, c in enumerate(hist)) / total) ** 0.5
            info["variance"] = round(var, 2)
            # A near-uniform field is a placeholder/blank, not a photograph.
            info["flat"] = var < 8.0
    except Exception as exc:  # noqa: BLE001
        info["error"] = str(exc)[:160]
    return info


def effective_dpi(pixels: int, inches: float) -> int:
    if not inches or inches <= 0:
        return 0
    return int(round(pixels / float(inches)))


def check_image_resolution(
    assets: list[dict[str, Any]], *, print_product: bool = True
) -> list[Finding]:
    """Judge resolution at the size the image is actually placed, not raw pixels."""
    out: list[Finding] = []
    for a in assets or []:
        name = a.get("name") or os.path.basename(a.get("path") or "")
        px = int(a.get("width") or 0)
        inches = float(a.get("placed_inches") or 0)
        if not px or not inches:
            continue
        dpi = effective_dpi(px, inches)
        a["effective_dpi"] = dpi
        if not print_product:
            continue
        if dpi < _PRINT_DPI_BLOCK:
            out.append(Finding(
                code="IMG_DPI_BLOCK", category="image_resolution",
                severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                summary=f"Image is {dpi} DPI at its placed size; below {_PRINT_DPI_BLOCK} blocks print-ready status.",
                asset=name, location=a.get("location", ""),
            ))
        elif dpi < _PRINT_DPI_REVIEW:
            out.append(Finding(
                code="IMG_DPI_REVIEW", category="image_resolution",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary=f"Image is {dpi} DPI at its placed size; below {_PRINT_DPI_REVIEW} needs review before print.",
                asset=name, location=a.get("location", ""),
            ))
        elif dpi < _PRINT_DPI_TARGET:
            out.append(Finding(
                code="IMG_DPI_SUBTARGET", category="image_resolution",
                severity=SEV_MINOR, kind=KIND_OBJECTIVE,
                summary=f"Image is {dpi} DPI at its placed size; {_PRINT_DPI_TARGET} is the print target.",
                asset=name, location=a.get("location", ""),
            ))
    return out


def check_assets_present(assets: list[dict[str, Any]]) -> list[Finding]:
    out: list[Finding] = []
    seen_digests: dict[str, str] = {}
    for a in assets or []:
        name = a.get("name") or os.path.basename(a.get("path") or "")
        info = a.get("_info") or inspect_image_file(a.get("path") or "")
        a["_info"] = info
        if not info["exists"]:
            out.append(Finding(
                code="IMG_MISSING", category="visual_quality",
                severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                summary="A visual the product claims is missing from disk.",
                asset=name, location=a.get("location", "")))
            continue
        if not info["opens"]:
            out.append(Finding(
                code="IMG_UNREADABLE", category="visual_quality",
                severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                summary="Image file exists but cannot be opened.",
                asset=name, location=a.get("location", "")))
            continue
        if info.get("flat"):
            out.append(Finding(
                code="IMG_PLACEHOLDER", category="visual_quality",
                severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                summary="Image is a near-uniform field — a placeholder, not a photograph.",
                asset=name, location=a.get("location", "")))
        digest = a.get("sha256") or _sha(a.get("path") or "")
        if digest:
            if digest in seen_digests and seen_digests[digest] != name:
                out.append(Finding(
                    code="IMG_DUPLICATE", category="visual_quality",
                    severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                    summary="The same image is reused for two different visuals.",
                    asset=name, detail=f"identical to {seen_digests[digest]}"))
            seen_digests.setdefault(digest, name)
    return out


def check_visual_subject_verification(assets: list[dict[str, Any]], *, subject_text: str) -> list[Finding]:
    """Safety-sensitive visuals cannot be signed off by code.

    Whether a photograph depicts the movement/technique the text teaches is a
    subject-matter judgment. Metadata proximity is not evidence. This raises a
    REVIEW_REQUIRED finding for each such visual that no human has confirmed.
    """
    out: list[Finding] = []
    if not is_safety_sensitive(subject_text):
        return out
    for a in assets or []:
        if a.get("kind") not in ("photo", "illustration"):
            continue
        if a.get("subject_verified_by_human") is True:
            continue
        name = a.get("name") or os.path.basename(a.get("path") or "")
        out.append(Finding(
            code="VIS_SUBJECT_UNVERIFIED", category="accuracy",
            severity=SEV_MAJOR, kind=KIND_JUDGMENT,
            summary="Safety-sensitive visual has not been confirmed to depict the technique described.",
            detail=("Automated review cannot verify that this image shows the stated action. "
                    "A person with subject-matter knowledge must confirm or reject it."),
            asset=name, location=a.get("location", "")))
    return out


# ---------------------------------------------------------------------------
# 5. Rendered pages
# ---------------------------------------------------------------------------
def analyse_rendered_pages(page_images: list[str]) -> dict[str, Any]:
    """Ink coverage per rendered page. Objective; no opinion about design."""
    stats: list[dict[str, Any]] = []
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return {"available": False, "pages": []}
    for i, p in enumerate(page_images or [], start=1):
        if not os.path.isfile(p):
            continue
        try:
            with Image.open(p) as im:
                rgb = im.convert("RGB").resize((100, 130))
                px = list(rgb.getdata())
        except Exception:  # noqa: BLE001
            continue
        n = len(px) or 1
        ink = sum(1 for r, g, b in px if (r + g + b) / 3 < 245)
        mid = sum(1 for r, g, b in px if 40 < (r + g + b) / 3 < 220)
        stats.append({"page": i, "ink_pct": round(100.0 * ink / n, 2),
                      "midtone_pct": round(100.0 * mid / n, 2),
                      "has_imagery": (100.0 * mid / n) > 18})
    return {"available": True, "pages": stats}


def check_page_quality(page_stats: list[dict[str, Any]], *, blank_ink_pct: float = 1.0,
                       sparse_ink_pct: float = 6.0) -> list[Finding]:
    out: list[Finding] = []
    for s in page_stats or []:
        if s["ink_pct"] < blank_ink_pct:
            out.append(Finding(
                code="PAGE_BLANK", category="interior_design",
                severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                summary="Rendered page is effectively blank.",
                location=f"page {s['page']}", detail=f"ink {s['ink_pct']}%"))
        elif s["ink_pct"] < sparse_ink_pct and not s["has_imagery"]:
            out.append(Finding(
                code="PAGE_SPARSE", category="interior_design",
                severity=SEV_MINOR, kind=KIND_OBJECTIVE,
                summary="Rendered page is mostly empty.",
                location=f"page {s['page']}", detail=f"ink {s['ink_pct']}%"))
    return out


def check_cover_page(cover_page_image: str, *, max_border_pct: float = 2.0) -> list[Finding]:
    """Objective cover-composition checks on the rendered first page.

    Catches the unintended white frame that appears when cover artwork is
    laid out as an ordinary in-flow image instead of bleeding to the trim
    edge. A cover that does not reach the page edge reads as a mistake at
    any size, and it is measurable, so it belongs with the objective rules
    rather than being left to eyeballing.
    """
    out: list[Finding] = []
    if not cover_page_image or not os.path.isfile(cover_page_image):
        return out
    try:
        from PIL import Image

        with Image.open(cover_page_image) as im:
            rgb = im.convert("RGB")
            w, h = rgb.size
            px = rgb.load()
    except Exception:  # noqa: BLE001
        return out

    def _blank_row(y: int) -> bool:
        step = max(1, w // 120)
        return all(sum(px[x, y]) / 3 > 246 for x in range(0, w, step))

    def _blank_col(x: int) -> bool:
        step = max(1, h // 120)
        return all(sum(px[x, y]) / 3 > 246 for y in range(0, h, step))

    top = next((y for y in range(h) if not _blank_row(y)), h)
    bottom = next((h - 1 - y for y in range(h) if not _blank_row(h - 1 - y)), 0)
    left = next((x for x in range(w) if not _blank_col(x)), w)
    right = next((w - 1 - x for x in range(w) if not _blank_col(w - 1 - x)), 0)

    margins = {
        "top": 100.0 * top / h, "bottom": 100.0 * (h - 1 - bottom) / h,
        "left": 100.0 * left / w, "right": 100.0 * (w - 1 - right) / w,
    }
    framed = [k for k, v in margins.items() if v > max_border_pct]
    if len(framed) >= 3:
        out.append(Finding(
            code="COVER_UNINTENDED_BORDER", category="cover_quality",
            severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
            summary="Cover artwork does not reach the page edge; it sits inside a white frame.",
            detail=", ".join(f"{k} {margins[k]:.1f}%" for k in sorted(framed)),
            location="page 1",
        ))
    return out


def check_page_count(declared: int, rendered: int, pdf_reported: int) -> list[Finding]:
    out: list[Finding] = []
    vals = {"declared": declared, "rendered": rendered, "pdf": pdf_reported}
    present = {k: v for k, v in vals.items() if v}
    if len(set(present.values())) > 1:
        out.append(Finding(
            code="META_PAGECOUNT_MISMATCH", category="package_integrity",
            severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
            summary="Reported page count disagrees with the rendered PDF.",
            detail=json.dumps(present)))
    return out


# ---------------------------------------------------------------------------
# 6. Typography / accessibility
# ---------------------------------------------------------------------------
def check_typography(css_or_html: str) -> list[Finding]:
    out: list[Finding] = []
    text = str(css_or_html or "")
    sizes = [float(x) for x in re.findall(r"font-size\s*:\s*([\d.]+)pt", text)]
    for s in sorted(set(sizes)):
        if s < _MIN_CAPTION_PT:
            out.append(Finding(
                code="A11Y_TEXT_TOO_SMALL", category="accessibility",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary=f"Type set at {s}pt is below the {_MIN_CAPTION_PT}pt readable floor.",
            ))
    # Character-level letter-spacing is the classic broken-heading artifact.
    for m in re.finditer(r"letter-spacing\s*:\s*([\d.]+)(px|pt|em)", text, re.I):
        val, unit = float(m.group(1)), m.group(2).lower()
        too_wide = (unit == "em" and val > 0.35) or (unit in ("px", "pt") and val > 4)
        if too_wide:
            out.append(Finding(
                code="TYPO_LETTERSPACING", category="interior_design",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary=f"Letter-spacing of {val}{unit} will visibly break word shapes.",
            ))
    return out


def check_customer_facing_leaks(*documents: str) -> list[Finding]:
    """No localhost, file://, or absolute local paths in anything a customer opens."""
    out: list[Finding] = []
    pats = [(r"localhost(?::\d+)?", "localhost URL"), (r"file://", "file:// URL"),
            (r"[A-Za-z]:\\\\Users\\\\", "absolute Windows path"),
            (r"/(?:home|Users)/[A-Za-z0-9._-]+/", "absolute local path")]
    for doc in documents:
        for pat, label in pats:
            if re.search(pat, str(doc or ""), re.I):
                out.append(Finding(
                    code="PKG_LOCAL_LEAK", category="package_integrity",
                    severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                    summary=f"A {label} appears in a customer-facing file.",
                ))
                break
    return out


# ---------------------------------------------------------------------------
# 7. Charts and tables
# ---------------------------------------------------------------------------
def check_chart_and_table_data(aids: list[dict[str, Any]]) -> list[Finding]:
    out: list[Finding] = []
    for aid in aids or []:
        kind = str(aid.get("type") or "").lower()
        title = str(aid.get("title") or aid.get("visual_id") or "visual")
        if kind in ("chart", "graph", "data_chart"):
            data = aid.get("chart_data") or {}
            labels = data.get("labels") or []
            values = data.get("values") or []
            if not labels or not values:
                out.append(Finding(
                    code="CHART_NO_DATA", category="accuracy", severity=SEV_CRITICAL,
                    kind=KIND_OBJECTIVE, summary="Chart has no data behind it.", asset=title))
            elif len(labels) != len(values):
                out.append(Finding(
                    code="CHART_SHAPE", category="accuracy", severity=SEV_CRITICAL,
                    kind=KIND_OBJECTIVE,
                    summary="Chart label and value counts disagree.", asset=title))
            elif not aid.get("data_source"):
                out.append(Finding(
                    code="CHART_NO_SOURCE", category="accuracy", severity=SEV_MAJOR,
                    kind=KIND_JUDGMENT,
                    summary="Numeric chart has no recorded data source; confirm the figures are real.",
                    asset=title))
        elif kind in ("table", "comparison_table", "comparison"):
            table = aid.get("table") or {}
            headers = table.get("headers") or []
            rows = table.get("rows") or []
            if table and (not headers or not rows):
                out.append(Finding(
                    code="TABLE_EMPTY", category="visual_quality", severity=SEV_MAJOR,
                    kind=KIND_OBJECTIVE, summary="Table has no headers or no rows.", asset=title))
            for r in rows:
                cells = [str(c).strip() for c in (r or [])]
                if cells and all(c in ("", "—", "-", "n/a", "N/A") for c in cells[1:]):
                    out.append(Finding(
                        code="TABLE_EMPTY_ROW", category="visual_quality", severity=SEV_MAJOR,
                        kind=KIND_OBJECTIVE,
                        summary="Table row is entirely empty or em-dashes.", asset=title,
                        detail=" | ".join(cells)[:120]))
                    break
    return out


# ---------------------------------------------------------------------------
# 8. Package integrity
# ---------------------------------------------------------------------------
def check_package_identity(
    *, registered_pdf: str, served_pdf_sha: str = "", zip_path: str = "",
    pdf_name_in_zip: str = "ebook.pdf", rollback_pdf: str = "",
    rollback_expected_sha: str = "",
) -> list[Finding]:
    out: list[Finding] = []
    reg_sha = _sha(registered_pdf)
    if not reg_sha:
        out.append(Finding(
            code="PKG_PDF_MISSING", category="package_integrity", severity=SEV_CRITICAL,
            kind=KIND_OBJECTIVE, summary="Registered PDF is missing or unreadable."))
        return out
    if served_pdf_sha and served_pdf_sha != reg_sha:
        out.append(Finding(
            code="PKG_SERVED_MISMATCH", category="package_integrity", severity=SEV_CRITICAL,
            kind=KIND_OBJECTIVE,
            summary="The PDF served to the customer differs from the registered PDF."))
    if zip_path:
        if not os.path.isfile(zip_path):
            out.append(Finding(
                code="PKG_ZIP_MISSING", category="package_integrity", severity=SEV_CRITICAL,
                kind=KIND_OBJECTIVE, summary="ZIP package is missing."))
        else:
            try:
                with zipfile.ZipFile(zip_path) as z:
                    if pdf_name_in_zip not in z.namelist():
                        out.append(Finding(
                            code="PKG_ZIP_NO_PDF", category="package_integrity",
                            severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                            summary="ZIP does not contain the product PDF."))
                    elif hashlib.sha256(z.read(pdf_name_in_zip)).hexdigest() != reg_sha:
                        out.append(Finding(
                            code="PKG_ZIP_PDF_MISMATCH", category="package_integrity",
                            severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                            summary="PDF inside the ZIP differs from the registered PDF."))
            except zipfile.BadZipFile:
                out.append(Finding(
                    code="PKG_ZIP_CORRUPT", category="package_integrity", severity=SEV_CRITICAL,
                    kind=KIND_OBJECTIVE, summary="ZIP package is corrupt."))
    if rollback_expected_sha:
        if _sha(rollback_pdf) != rollback_expected_sha:
            out.append(Finding(
                code="PKG_ROLLBACK_LOST", category="package_integrity", severity=SEV_CRITICAL,
                kind=KIND_OBJECTIVE,
                summary="The previous package is no longer intact for rollback."))
    return out


# ---------------------------------------------------------------------------
# Scoring and verdict
# ---------------------------------------------------------------------------
_SEV_PENALTY = {SEV_CRITICAL: 10, SEV_MAJOR: 3, SEV_MINOR: 1}


def score_categories(findings: list[Finding], applicable: list[str] | None = None) -> dict[str, int]:
    cats = list(applicable or CATEGORIES)
    scores = {c: 10 for c in cats}
    for f in findings:
        if f.category not in scores:
            continue
        scores[f.category] = max(1, scores[f.category] - _SEV_PENALTY.get(f.severity, 1))
    return scores


def decide_verdict(findings: list[Finding], scores: dict[str, int]) -> tuple[str, float]:
    overall = round(sum(scores.values()) / max(len(scores), 1), 2) if scores else 0.0
    blockers = [f for f in findings if f.blocks()]
    judgment_blockers = [f for f in blockers if f.kind == KIND_JUDGMENT]
    critical = [f for f in blockers if f.severity == SEV_CRITICAL]

    if judgment_blockers and not critical:
        # Nothing objectively broken, but something material cannot be
        # verified without a human. That is BLOCKED, never PASS.
        return VERDICT_BLOCKED, overall
    if critical:
        return VERDICT_CORRECTION, overall
    if any(v < MIN_CATEGORY for v in scores.values()):
        return VERDICT_CORRECTION, overall
    if scores.get("package_integrity", 0) < PACKAGE_INTEGRITY_REQUIRED:
        return VERDICT_CORRECTION, overall
    if overall < MIN_OVERALL:
        return VERDICT_CORRECTION, overall
    return VERDICT_PASS, overall


# ---------------------------------------------------------------------------
# Independence guard
# ---------------------------------------------------------------------------
class SelfApprovalError(PermissionError):
    """Raised when a production component tries to sign off its own output."""


def assert_independent_review(*, produced_by: str, reviewed_by: str) -> None:
    """The agent that built the candidate may not be the agent that clears it."""
    if not reviewed_by or not produced_by:
        raise SelfApprovalError("Both producer and reviewer identities are required.")
    if _norm(produced_by) == _norm(reviewed_by):
        raise SelfApprovalError(
            f"{produced_by!r} cannot approve its own output; an independent "
            "Editor-in-Chief review is required."
        )


def customer_ready(report: ReviewReport | None) -> bool:
    """The single question the rest of the Factory should ask."""
    return bool(report) and report.verdict == VERDICT_PASS


# ---------------------------------------------------------------------------
# Correction loop
# ---------------------------------------------------------------------------
MAX_CORRECTION_ROUNDS = 2


@dataclass
class CorrectionSession:
    rounds_used: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    def may_correct(self) -> bool:
        return self.rounds_used < MAX_CORRECTION_ROUNDS

    def record(self, report: ReviewReport) -> None:
        self.rounds_used += 1
        self.history.append({
            "round": self.rounds_used, "verdict": report.verdict,
            "blockers": len(report.blockers()), "overall": report.overall,
        })

    def exhausted_message(self) -> str:
        return (
            f"Two correction rounds were used and defects remain. Stopping honestly "
            f"rather than continuing: {self.rounds_used}/{MAX_CORRECTION_ROUNDS} rounds."
        )


def defect_list(report: ReviewReport) -> list[dict[str, Any]]:
    """Numbered, classified, assignable defect list for the production agent."""
    order = {SEV_CRITICAL: 0, SEV_MAJOR: 1, SEV_MINOR: 2}
    ranked = sorted(report.findings, key=lambda f: (order.get(f.severity, 3), f.category))
    return [{
        "n": i, "code": f.code, "severity": f.severity, "kind": f.kind,
        "category": f.category, "summary": f.summary, "detail": f.detail,
        "location": f.location, "asset": f.asset,
        "owner": _OWNER.get(f.category, "production"),
        "blocks_release": f.blocks(),
    } for i, f in enumerate(ranked, start=1)]


_OWNER = {
    "originality": "manuscript", "relevance": "manuscript", "accuracy": "manuscript",
    "consistency": "manuscript", "editorial_quality": "manuscript",
    "visual_quality": "visual_production", "instructional_value": "visual_production",
    "image_resolution": "visual_production", "cover_quality": "cover_production",
    "interior_design": "layout", "accessibility": "layout",
    "package_integrity": "packaging", "customer_value": "editorial_direction",
}
