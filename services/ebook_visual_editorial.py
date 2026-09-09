"""Editor-in-Chief checks for a book's interior visuals.

WHY THIS EXISTS
---------------
A finished 44-page book passed every visual gate the Factory had and was still
not sellable. Nine PNG files existed, one per chapter, each valid, correctly
sized, correctly hashed, correctly captioned — and eight of them were the same
rounded-box list with different words in it. No photographs. No explanatory
diagram. No chart. No infographic. The asset checks all passed because they
only ever asked questions about one file at a time:

    does it exist, is it a real PNG, does its hash match, is it captioned

Not one of them asked the question a reader asks: *is this book illustrated?*

So these checks judge the set, not the file. They are deterministic — no model
is consulted, nothing here is a matter of taste — and they are written against
properties any illustrated non-fiction book has, not against one book.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
No check invents a standard the manuscript cannot meet. A book whose subject
genuinely admits no photography is not failed for having none; the requirement
is applied to books whose own subject supports it. Variety is required, but
only among visuals the chapters actually support — the fix for a monotonous
book is a better plan, never a fabricated chart.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

#: Visual types that are, structurally, a box of text lines. They are useful,
#: and a book may contain several — but a book made only of these is a
#: worksheet, not an illustrated book.
TEXT_BOX_TYPES = frozenset({"checklist", "workflow", "worksheet box", "key points"})

#: Types that carry information a paragraph cannot: a real photograph, a drawn
#: relationship, a quantity, a sequence over time, a side-by-side.
ILLUSTRATIVE_TYPES = frozenset(
    {"photo", "stock photo", "chart", "comparison", "comparison_table", "timeline", "diagram"}
)

PHOTO_TYPES = frozenset({"photo", "stock photo"})

#: A photograph below this is a thumbnail; it prints soft at page width.
MIN_PHOTO_PIXELS = (1000, 700)
#: A drawn graphic is rendered by us, so the bar is only "not a thumbnail".
MIN_GRAPHIC_PIXELS = (600, 300)

#: Editorial standard for an illustrated interior. Scaled to book length in
#: media_requirements(); these are the floors.
MIN_DISTINCT_TYPES = 3
MIN_ILLUSTRATIVE_SHARE = 0.34
MAX_SINGLE_TYPE_SHARE = 0.55


@dataclass
class EditorialReport:
    ok: bool
    findings: list[str] = field(default_factory=list)
    type_counts: dict[str, int] = field(default_factory=dict)
    photograph_count: int = 0
    illustrative_count: int = 0
    total: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": list(self.findings),
            "type_counts": dict(self.type_counts),
            "photograph_count": self.photograph_count,
            "illustrative_count": self.illustrative_count,
            "total": self.total,
        }


# --------------------------------------------------------------- helpers ---


def aid_type(aid: dict) -> str:
    return str((aid or {}).get("type") or "").strip().lower()


def plan_aids(plan: dict | None) -> list[dict]:
    out: list[dict] = []
    if not isinstance(plan, dict):
        return out
    for chapter in plan.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for aid in chapter.get("aids") or []:
            if isinstance(aid, dict):
                out.append(aid)
    return out


def media_requirements(chapter_count: int, *, photography_supported: bool) -> dict[str, int]:
    """The editorial floor for a book of this length.

    Deliberately modest. The point is to make a monotonous set impossible, not
    to dictate a house style.
    """
    n = max(int(chapter_count or 0), 1)
    photographs = min(4, max(3, round(n * 0.3))) if photography_supported else 0
    return {
        "photographs": int(photographs),
        "distinct_types": MIN_DISTINCT_TYPES if n >= 4 else 2,
        "illustrative": max(2, int(round(n * MIN_ILLUSTRATIVE_SHARE))),
    }


def _looks_like_a_photograph(aid: dict) -> tuple[bool, str]:
    """A photograph is a photograph, not a graphic we drew and labelled one."""
    source = str(aid.get("source") or "").strip().lower()
    if source in {"local", "generated", "rendered", "content_aware_local"}:
        return False, "its source says the Factory drew it"
    if not str(aid.get("attribution") or "").strip():
        return False, "it has no attribution"
    detail = aid.get("detail_spread")
    if detail is not None:
        try:
            # Flat drawn graphics sit far below a photograph's tonal spread.
            if float(detail) < 0.45:
                return False, "its tonal range is that of a flat graphic"
        except (TypeError, ValueError):
            pass
    return True, ""


def _pixels(aid: dict) -> tuple[int, int]:
    try:
        return int(aid.get("width") or 0), int(aid.get("height") or 0)
    except (TypeError, ValueError):
        return 0, 0


def _design_signature(aid: dict) -> str:
    """What this visual looks like, independent of its words.

    Two checklists of six items are the same design. Comparing rendered bytes
    would miss that, because the words differ; comparing the type and shape
    catches exactly the repetition a reader notices.

    A chart's content lives in chart_data (or, from the fixture planner,
    chart) rather than items/table -- omitting it here meant EVERY chart in a
    book compared equal regardless of how many bars it drew or what they
    showed, so a two-bar chart and a five-bar chart with unrelated figures
    were flagged as "repeats the design" of one another. That is not the
    repetition a reader notices; it is two different charts. Counting the
    chart's own data points keeps the comparison honest the same way
    items/rows already do for the other types.
    """
    kind = aid_type(aid)
    if kind in PHOTO_TYPES:
        return ""  # photographs are compared by identity elsewhere
    items = aid.get("items") if isinstance(aid.get("items"), list) else []
    table = aid.get("table") if isinstance(aid.get("table"), dict) else {}
    rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    cols = table.get("headers") if isinstance(table.get("headers"), list) else []
    chart = aid.get("chart_data") if isinstance(aid.get("chart_data"), dict) else aid.get("chart")
    chart = chart if isinstance(chart, dict) else {}
    chart_points = len(chart.get("values") or chart.get("labels") or [])
    w, h = _pixels(aid)
    return (
        f"{kind}|items={len(items)}|rows={len(rows)}|cols={len(cols)}|"
        f"chart={chart_points}|{w}x{h}"
    )


_STAT_RE = re.compile(
    r"\b\d{1,3}(?:\.\d+)?\s?%|\b(?:study|studies|research|researchers|trial|"
    r"clinical|scientists?|survey of)\b",
    re.I,
)


# ----------------------------------------------------------- the checks ---


def review_visual_set(
    plan: dict | None,
    *,
    chapter_count: int = 0,
    photography_supported: bool = True,
    pdf_path: str = "",
) -> EditorialReport:
    """Judge the whole interior visual set. Deterministic; no model is called."""
    aids = [a for a in plan_aids(plan) if a.get("required") is not False]
    findings: list[str] = []

    counts: dict[str, int] = {}
    for aid in aids:
        kind = aid_type(aid) or "unknown"
        counts[kind] = counts.get(kind, 0) + 1

    total = len(aids)
    photographs = [a for a in aids if aid_type(a) in PHOTO_TYPES]
    illustrative = [a for a in aids if aid_type(a) in ILLUSTRATIVE_TYPES]

    if total == 0:
        return EditorialReport(False, ["The book has no interior visuals."], counts, 0, 0, 0)

    want = media_requirements(chapter_count or total, photography_supported=photography_supported)

    # 1. A book of text boxes is not an illustrated book.
    text_boxes = [a for a in aids if aid_type(a) in TEXT_BOX_TYPES]
    if len(text_boxes) == total:
        findings.append(
            "Every interior visual is a box of text lines. A reader cannot tell "
            "one chapter's illustration from another's, and the book reads as a "
            "worksheet. It needs photographs, diagrams or charts."
        )

    # 2. Variety of kind.
    distinct = len({aid_type(a) for a in aids})
    if distinct < want["distinct_types"]:
        findings.append(
            f"Only {distinct} kind(s) of visual across {total}: "
            f"{', '.join(sorted(counts))}. A designed interior needs at least "
            f"{want['distinct_types']}."
        )
    for kind, count in counts.items():
        if total >= 4 and count / total > MAX_SINGLE_TYPE_SHARE:
            findings.append(
                f"{count} of {total} visuals are the same kind ({kind}). "
                "That repetition reads as a template."
            )

    # 3. Photographs, when the subject supports them.
    if photography_supported and len(photographs) < want["photographs"]:
        findings.append(
            f"{len(photographs)} photograph(s) for a subject that supports them; "
            f"at least {want['photographs']} are needed."
        )

    # 4. Enough visuals that carry more than a paragraph would.
    if len(illustrative) < want["illustrative"]:
        findings.append(
            f"Only {len(illustrative)} of {total} visuals show something prose "
            f"cannot; at least {want['illustrative']} are needed."
        )

    # 5. A photograph must actually be a photograph.
    for aid in photographs:
        real, why = _looks_like_a_photograph(aid)
        if not real:
            findings.append(
                f"Visual {aid.get('visual_id')} is planned as a photograph but "
                f"{why}."
            )

    # 6. Resolution, judged by what the visual is.
    for aid in aids:
        w, h = _pixels(aid)
        floor = MIN_PHOTO_PIXELS if aid_type(aid) in PHOTO_TYPES else MIN_GRAPHIC_PIXELS
        if w < floor[0] or h < floor[1]:
            findings.append(
                f"Visual {aid.get('visual_id')} is {w}x{h}; it prints soft at "
                f"page width (needs at least {floor[0]}x{floor[1]})."
            )

    # 7. No two visuals may be the same design.
    seen: dict[str, str] = {}
    for aid in aids:
        signature = _design_signature(aid)
        if not signature:
            continue
        first = seen.get(signature)
        if first:
            findings.append(
                f"Visual {aid.get('visual_id')} repeats the design of "
                f"{first} exactly ({aid_type(aid)})."
            )
        else:
            seen[signature] = str(aid.get("visual_id") or "")

    # 8. A chart must carry real, supported numbers; a diagram must teach.
    for aid in aids:
        kind = aid_type(aid)
        if kind == "chart":
            values = ((aid.get("chart_data") or {}).get("values")) or []
            if len(values) < 2:
                findings.append(
                    f"Chart {aid.get('visual_id')} has fewer than two data "
                    "points; there is nothing to compare."
                )
            blob = f"{aid.get('title') or ''} {aid.get('caption') or ''}"
            if _STAT_RE.search(blob) and not str(aid.get("data_source") or "").strip():
                findings.append(
                    f"Chart {aid.get('visual_id')} presents research-sounding "
                    "figures with no source. Statistics must come from the "
                    "manuscript's own cited material."
                )
        if kind in {"timeline", "workflow", "diagram"}:
            items = aid.get("items") if isinstance(aid.get("items"), list) else []
            if len(items) < 3:
                findings.append(
                    f"Diagram {aid.get('visual_id')} has {len(items)} step(s); "
                    "it does not explain a sequence."
                )

    # 9. Captions and attribution.
    for aid in aids:
        if not str(aid.get("caption") or "").strip():
            findings.append(f"Visual {aid.get('visual_id')} has no caption.")
        if aid_type(aid) in PHOTO_TYPES and not str(aid.get("attribution") or "").strip():
            findings.append(f"Photograph {aid.get('visual_id')} has no attribution.")

    # 10. The visuals must be in the book, not merely beside it.
    if pdf_path:
        embedded = verify_embedded_in_pdf(plan, pdf_path)
        findings.extend(embedded.findings)

    return EditorialReport(
        ok=not findings,
        findings=findings,
        type_counts=counts,
        photograph_count=len(photographs),
        illustrative_count=len(illustrative),
        total=total,
    )


def verify_embedded_in_pdf(plan: dict | None, pdf_path: str) -> EditorialReport:
    """Open the PDF and count real embedded images.

    Every other check in the Factory reasons about files in the exports folder
    or entries in the ZIP. A file can be all of those things and still not
    appear on a page — which is exactly what a customer opens.
    """
    aids = [a for a in plan_aids(plan) if a.get("required") is not False]
    findings: list[str] = []
    if not pdf_path or not os.path.isfile(pdf_path):
        return EditorialReport(False, [f"No PDF to inspect at {pdf_path!r}."], total=len(aids))
    try:
        import fitz
    except ImportError:
        return EditorialReport(True, [], total=len(aids))

    pages: dict[int, int] = {}
    embedded = 0
    try:
        doc = fitz.open(pdf_path)
        try:
            for number, page in enumerate(doc, start=1):
                images = page.get_images(full=True)
                if images:
                    pages[number] = len(images)
                    embedded += len(images)
        finally:
            doc.close()
    except Exception as exc:  # noqa: BLE001
        return EditorialReport(False, [f"The PDF could not be read: {exc}"], total=len(aids))

    # One of the embedded images is the cover, which is not an interior visual.
    interior = max(0, embedded - (1 if 1 in pages else 0))
    if interior < len(aids):
        findings.append(
            f"The PDF carries {interior} interior image(s) for {len(aids)} "
            "planned visual(s). A visual that is not on a page is not in the book."
        )
    report = EditorialReport(not findings, findings, total=len(aids))
    report.type_counts = {f"page_{n}": c for n, c in sorted(pages.items())}
    return report
