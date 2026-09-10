"""Editor-in-Chief review for planner products (Faith Planner, Budget Planner).

The ebook reviewer cannot be reused unchanged, and pretending otherwise would
produce a verdict that means nothing. Two differences drive this module:

  * **Repetition is the product.** A planner is fifty near-identical worksheet
    pages on purpose. Running `check_self_duplication` over the extracted PDF
    text would report a hundred duplicate paragraphs and block every planner
    forever. Duplication is therefore checked over the *prose* only -- the
    instructional sections, where a repeat really is a defect -- and the
    worksheet furniture is checked a different way, by ink and by structure.

  * **There are no photographs.** Photo-backed cover, image resolution, and
    safety-sensitive visual verification have no subject to run against. They
    are recorded in `checks_skipped` with the reason rather than being quietly
    dropped, and their categories are excluded from scoring instead of being
    scored 10 for free.

Three checks exist only here, because they guard failures only a planner has:
a contents page that points at the wrong page, a cover that advertises a page
count the book does not have, and a "planner" that is blank grids with no
instruction in it at all.
"""
from __future__ import annotations

import os
import re
from typing import Any

from services.editor_in_chief import (
    KIND_OBJECTIVE,
    SEV_CRITICAL,
    SEV_MAJOR,
    SEV_MINOR,
    Finding,
    ReviewReport,
    analyse_rendered_pages,
    assert_independent_review,
    check_cover_page,
    check_customer_facing_leaks,
    check_identity_consistency,
    check_package_identity,
    check_page_count,
    check_page_quality,
    check_placeholder_and_leak,
    check_relevance,
    check_self_duplication,
    decide_verdict,
    score_categories,
)

REVIEWER_ID = "editor_in_chief_planner"
PRODUCER_ID = "planner_pdf_builder"

# Photographs, charts, and rendered artwork are absent by design, so the
# categories that score them are not applicable rather than free marks.
PLANNER_CATEGORIES = [
    "originality", "relevance", "accuracy", "consistency", "editorial_quality",
    "instructional_value", "interior_design", "cover_quality",
    "package_integrity", "customer_value",
]

# The instructional prose a planner must actually contain to be a book rather
# than a pad of forms. Tuned against the shipped page plans, which carry well
# over a thousand words; the floor is what a *thin* planner may not go below.
MIN_PROSE_WORDS = 450
MIN_PROSE_SECTIONS = 4

# Money planners must say, in the customer's copy, that they are not advice.
_ADVICE_ANCHORS = (
    "does not provide personalised financial",
    "does not provide personalized financial",
    "not financial advice",
    "does not provide financial",
)
_PROFESSIONAL_ANCHORS = ("qualified professional", "financial adviser", "financial advisor")

_PROSE_KINDS = ("prose", "ownership")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _words(text: str) -> int:
    return len(re.findall(r"[A-Za-z']+", str(text or "")))


# --------------------------------------------------------------------------- #
# Candidate collection
# --------------------------------------------------------------------------- #
def collect_planner_candidate(
    plan: Any, *, pdf_path: str, package_dir: str = "",
    page_images: list[str] | None = None, author: str = "",
    zip_path: str = "", layout_info: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Read the finished artifact. Nothing here trusts the builder's claims
    except the page plan itself, which is what the artifact is measured
    against. `layout_info` is the renderer's own report (theme key, cover
    source, what did not fit); it is read for the design checks but every
    claim in it is verified against the PDF."""
    layout_info = dict(layout_info or {})
    candidate: dict[str, Any] = {
        "planner_type": getattr(plan, "planner_type", ""),
        "title": getattr(plan, "title", ""),
        "subtitle": getattr(plan, "subtitle", ""),
        "author": author,
        "pdf_path": pdf_path,
        "package_dir": package_dir,
        "zip_path": zip_path,
        "page_images": list(page_images or []),
        "declared_pages": len(getattr(plan, "pages", []) or []),
        "design_theme": str(getattr(plan, "design_theme", "") or layout_info.get("design_theme") or ""),
        "cover_style": str(getattr(plan, "cover_style", "") or layout_info.get("cover_style") or ""),
        "render_notes": list(layout_info.get("render_notes") or []),
    }

    pages = list(getattr(plan, "pages", []) or [])
    candidate["page_kinds"] = [p.kind for p in pages]
    candidate["page_titles"] = [p.title for p in pages]
    candidate["toc"] = [
        (p.toc_entry, i + 1) for i, p in enumerate(pages) if p.toc_entry
    ]

    # Prose is pulled from the plan rather than from PDF text extraction: the
    # section boundaries are known there, and a wrapped PDF line break must not
    # decide whether two paragraphs count as identical.
    #
    # Reflection prompts printed above ruled lines are deliberately excluded.
    # They are worksheet furniture -- the same five questions are meant to
    # reappear every month -- so counting them as prose would both inflate the
    # instructional word count and report the repetition as plagiarism.
    prose: list[tuple[str, str]] = []
    prose_pages: list[tuple[str, str]] = []
    prompts: list[str] = []
    for p in pages:
        if p.kind in _PROSE_KINDS:
            sections = list(p.spec.get("sections") or [])
            for heading, body in sections:
                prose.append((heading, body))
            if sections:
                # Bodies only. Folding the headings into the text being
                # measured would guarantee a heading match on every page and
                # leave the relevance check unable to fail.
                prose_pages.append(
                    (p.title, " ".join(b for _h, b in sections)))
        if p.kind == "prompt_page":
            prompts.extend(p.spec.get("prompts") or [])
    candidate["prose_sections"] = prose
    # Relevance is judged per *page*, not per bullet: a four-word method
    # heading with a two-sentence body is not a chapter, and scoring it as one
    # produces a wall of false "off topic" findings on a well-made planner.
    candidate["prose_pages"] = prose_pages
    candidate["worksheet_prompts"] = prompts

    page_texts: list[str] = []
    header_texts: list[str] = []
    footer_texts: list[str] = []
    text_boxes: list[list[tuple[float, float, float, float]]] = []
    page_rects: list[tuple[float, float]] = []
    cover_images: list[dict[str, float]] = []
    pdf_pages = 0
    meta: dict[str, str] = {}
    try:
        import fitz

        doc = fitz.open(pdf_path)
        pdf_pages = doc.page_count
        raw_meta = doc.metadata or {}
        meta = {
            "Title": raw_meta.get("title") or "",
            "Author": raw_meta.get("author") or "",
            "Subject": raw_meta.get("subject") or "",
        }
        for pi, p in enumerate(doc):
            page_texts.append(p.get_text())
            w, h = float(p.rect.width), float(p.rect.height)
            page_rects.append((w, h))
            blocks = [b for b in p.get_text("blocks") if len(b) > 4 and str(b[4]).strip()]
            header_texts.append(" ".join(str(b[4]) for b in blocks if b[3] <= HEADER_ZONE_PT))
            footer_texts.append(" ".join(str(b[4]) for b in blocks if b[1] >= h - FOOTER_ZONE_PT))
            text_boxes.append([(float(b[0]), float(b[1]), float(b[2]), float(b[3])) for b in blocks])
            if pi == 0:
                for img in p.get_images(full=True):
                    try:
                        rects = p.get_image_rects(img[0])
                    except Exception:  # noqa: BLE001
                        rects = []
                    placed = rects[0] if rects else p.rect
                    cover_images.append({
                        "px_w": float(img[2]), "px_h": float(img[3]),
                        "pt_w": float(placed.width), "pt_h": float(placed.height),
                    })
        doc.close()
    except Exception:  # noqa: BLE001
        pass
    candidate["page_texts"] = page_texts
    candidate["header_texts"] = header_texts
    candidate["footer_texts"] = footer_texts
    candidate["text_boxes"] = text_boxes
    candidate["page_rects"] = page_rects
    candidate["cover_images"] = cover_images
    candidate["pdf_pages"] = pdf_pages
    candidate["pdf_meta"] = meta
    candidate["full_text"] = "\n".join(page_texts)
    return candidate


# --------------------------------------------------------------------------- #
# Design-system checks
#
# The planner engine is a themed design system (services/planner/themes.py).
# These checks verify, on the rendered artifact, that the design promises were
# kept: the same chrome on every page, page numbers that count, text inside
# the printable area, nothing silently truncated, cover artwork that will
# print sharp, colours that stay on the theme's palette, and pages that look
# like a product rather than a form. A technically valid but visually plain
# planner is reported as needing improvement instead of passing quietly.
# --------------------------------------------------------------------------- #
HEADER_ZONE_PT = 1.05 * 72.0
FOOTER_ZONE_PT = 0.62 * 72.0
SAFE_MARGIN_PT = 0.25 * 72.0
MIN_COVER_IMAGE_DPI = 150.0
# A working page with less tint and colour than this reads as a bare form.
PLAIN_TINT_PCT = 2.0
PLAIN_COLOR_PCT = 0.25
PLAIN_PAGE_SHARE = 0.25

_CHROME_EXEMPT_KINDS = ("cover",)
_TITLE_PAGE_KINDS = ("ownership",)
_WORKING_KINDS = (
    "open_table", "labeled_table", "faith_daily", "faith_weekly", "habit_tracker",
    "calendar_month", "prompt_page", "snapshot", "lined_notes", "reading_plan",
)


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def check_planner_page_furniture(
    page_kinds: list[str], page_titles: list[str], page_texts: list[str],
    header_texts: list[str], footer_texts: list[str], running_title: str,
) -> list[Finding]:
    """Header carries the page title, footer carries the running title and the
    right page number, on every interior page."""
    out: list[Finding] = []
    run = _squash(running_title)
    for i, kind in enumerate(page_kinds or [], start=1):
        if kind in _CHROME_EXEMPT_KINDS or i > len(page_texts):
            continue
        title = page_titles[i - 1] if i - 1 < len(page_titles) else ""
        head = header_texts[i - 1] if i - 1 < len(header_texts) else ""
        foot = footer_texts[i - 1] if i - 1 < len(footer_texts) else ""
        where = page_texts[i - 1] if kind in _TITLE_PAGE_KINDS else head
        if title and _squash(title) not in _squash(where):
            out.append(Finding(
                code="PLAN_HEADER_MISSING", category="consistency",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary="Page heading is missing from the page's header zone.",
                location=f"page {i}", detail=f"expected {title!r}"))
        tokens = str(foot or "").split()
        if not tokens or tokens[-1] != str(i):
            out.append(Finding(
                code="PLAN_PAGE_NUMBER_WRONG", category="consistency",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary="Footer page number is missing or does not match the page.",
                location=f"page {i}", detail=f"footer reads {foot.strip()!r}"))
        if run and run not in _squash(foot):
            out.append(Finding(
                code="PLAN_FOOTER_TITLE_MISSING", category="consistency",
                severity=SEV_MINOR, kind=KIND_OBJECTIVE,
                summary="Running title is missing from the footer.",
                location=f"page {i}"))
    return out


def check_planner_print_safety(
    page_kinds: list[str], text_boxes: list[list[tuple[float, float, float, float]]],
    page_rects: list[tuple[float, float]], *, safe_margin: float = SAFE_MARGIN_PT,
) -> list[Finding]:
    """No text may sit inside the trim-safe margin or run off the page. The
    cover is full-bleed art and is exempt; its type is placed inside a frame."""
    out: list[Finding] = []
    for i, kind in enumerate(page_kinds or [], start=1):
        if kind in _CHROME_EXEMPT_KINDS or i > len(text_boxes) or i > len(page_rects):
            continue
        w, h = page_rects[i - 1]
        clipped = [b for b in text_boxes[i - 1] if b[0] < -0.5 or b[1] < -0.5 or b[2] > w + 0.5 or b[3] > h + 0.5]
        near = [b for b in text_boxes[i - 1]
                if b not in clipped and (b[0] < safe_margin or b[1] < safe_margin
                                          or b[2] > w - safe_margin or b[3] > h - safe_margin)]
        if clipped:
            out.append(Finding(
                code="PLAN_TEXT_CLIPPED", category="interior_design",
                severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                summary="Text runs off the page edge.",
                location=f"page {i}", detail=f"{len(clipped)} text block(s)"))
        elif near:
            out.append(Finding(
                code="PLAN_TEXT_NEAR_TRIM", category="interior_design",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary="Text sits inside the print-safe margin and may be cut off by a home printer.",
                location=f"page {i}", detail=f"{len(near)} text block(s) within {safe_margin / 72:.2f} in of the edge"))
    return out


def check_planner_render_notes(render_notes: list[str]) -> list[Finding]:
    """The renderer reports what it could not fit. That is a defect the
    customer would see as a missing paragraph or a short table, so it blocks
    rather than being left in a log nobody reads."""
    out: list[Finding] = []
    for note in render_notes or []:
        low = str(note).lower()
        if "did not fit" in low or "no drawer" in low:
            out.append(Finding(
                code="PLAN_CONTENT_TRUNCATED", category="interior_design",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary="Planned content was dropped because it did not fit the page.",
                detail=str(note)))
        elif "trimmed" in low or "instead" in low:
            out.append(Finding(
                code="PLAN_RENDER_FALLBACK", category="interior_design",
                severity=SEV_MINOR, kind=KIND_OBJECTIVE,
                summary="The renderer fell back from what was requested.",
                detail=str(note)))
    return out


def check_planner_cover_artwork(
    page_kinds: list[str], cover_images: list[dict[str, float]], *,
    min_dpi: float = MIN_COVER_IMAGE_DPI,
) -> list[Finding]:
    """The cover must carry an artwork layer that prints sharp."""
    out: list[Finding] = []
    if not page_kinds or page_kinds[0] != "cover":
        return out
    if not cover_images:
        out.append(Finding(
            code="PLAN_COVER_FLAT", category="cover_quality",
            severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
            summary="Cover has no artwork layer; it is a flat fill with type on it.",
            location="page 1"))
        return out
    for img in cover_images:
        pt_w = float(img.get("pt_w") or 0.0)
        px_w = float(img.get("px_w") or 0.0)
        if pt_w <= 0 or px_w <= 0:
            continue
        dpi = px_w / (pt_w / 72.0)
        if dpi < min_dpi:
            out.append(Finding(
                code="PLAN_COVER_IMAGE_LOW_RES", category="cover_quality",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary="Cover artwork is too low-resolution to print cleanly.",
                location="page 1", detail=f"{dpi:.0f} dpi at placed size, floor {min_dpi:.0f}"))
    return out


def analyse_planner_design(page_images: list[str]) -> list[dict[str, Any]]:
    """Per-page colour facts for the design checks: how much of the page is a
    light tint (panels, zebra rows), how much carries real colour, and the
    hue those coloured pixels lean to. Objective measurements only."""
    stats: list[dict[str, Any]] = []
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return stats
    for i, path in enumerate(page_images or [], start=1):
        if not os.path.isfile(path):
            continue
        try:
            with Image.open(path) as im:
                small = im.convert("RGB").resize((120, 156))
                rgb = list(small.getdata())
                hsv = list(small.convert("HSV").getdata())
        except Exception:  # noqa: BLE001
            continue
        n = max(len(rgb), 1)
        # A tint is a *coloured* light pixel (panels, zebra rows). Greys that
        # anti-aliasing makes out of black rules on white are not tint.
        tint = sum(1 for r, g, b in rgb
                   if 196 <= (r + g + b) / 3 <= 250 and (max(r, g, b) - min(r, g, b)) >= 5)
        colored = [(h, s, v) for (h, s, v) in hsv if s >= 56 and v >= 40]
        hist: dict[int, int] = {}
        for h, _s, _v in colored:
            bucket = int(h * 360 / 256) // 10 * 10
            hist[bucket] = hist.get(bucket, 0) + 1
        hues = sorted(hist.items(), key=lambda kv: -kv[1])
        stats.append({
            "page": i,
            "tint_pct": round(100.0 * tint / n, 2),
            "color_pct": round(100.0 * len(colored) / n, 2),
            "hue_hist": hist,
            "dominant_hue": hues[0][0] if hues else None,
        })
    return stats


def _hue_of_hex(value: str) -> tuple[float, float]:
    """(hue degrees, saturation 0..1) of a hex colour."""
    v = str(value or "").lstrip("#")
    if len(v) != 6:
        return 0.0, 0.0
    r, g, b = (int(v[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    s = 0.0 if mx == 0 else d / mx
    if d == 0:
        return 0.0, s
    if mx == r:
        h = (60 * ((g - b) / d) + 360) % 360
    elif mx == g:
        h = 60 * ((b - r) / d) + 120
    else:
        h = 60 * ((r - g) / d) + 240
    return h, s


def _hue_distance(a: float, b: float) -> float:
    d = abs(a - b) % 360
    return min(d, 360 - d)


def check_planner_theme_consistency(
    design_stats: list[dict[str, Any]], page_kinds: list[str], theme_key: str, *,
    tolerance_deg: float = 28.0, max_off_share: float = 0.25,
) -> list[Finding]:
    """Every interior page's colour must come from the theme's palette. A
    page whose colour leans to a hue the theme does not own is design drift."""
    out: list[Finding] = []
    if not theme_key or not design_stats:
        return out
    try:
        from services.planner.themes import THEMES
    except Exception:  # noqa: BLE001
        return out
    theme = THEMES.get(theme_key)
    if theme is None:
        out.append(Finding(
            code="PLAN_THEME_UNKNOWN", category="consistency",
            severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
            summary="Planner declares a design theme the engine does not define.",
            detail=repr(theme_key)))
        return out
    palette = [_hue_of_hex(c) for c in theme.palette_hex()]
    palette_hues = [h for h, s in palette if s >= 0.18]
    for s in design_stats:
        i = int(s["page"])
        if i - 1 < len(page_kinds) and page_kinds[i - 1] in _CHROME_EXEMPT_KINDS:
            continue
        hist: dict[int, int] = s.get("hue_hist") or {}
        total = sum(hist.values())
        if total < 6:  # fewer than ~0.03% coloured pixels: a neutral page
            continue
        if not palette_hues:
            # A neutral theme must stay neutral: colour on the page is drift.
            if s["color_pct"] > 1.0:
                out.append(Finding(
                    code="PLAN_THEME_DRIFT", category="consistency",
                    severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                    summary="Page carries colour that the neutral theme does not use.",
                    location=f"page {i}", detail=f"{s['color_pct']}% coloured pixels"))
            continue
        off = sum(cnt for hue, cnt in hist.items()
                  if all(_hue_distance(hue + 5, ph) > tolerance_deg for ph in palette_hues))
        if off / total > max_off_share:
            out.append(Finding(
                code="PLAN_THEME_DRIFT", category="consistency",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary="Page colour leans to a hue outside the design theme's palette.",
                location=f"page {i}",
                detail=f"{100 * off / total:.0f}% of coloured pixels off-palette for {theme.label}"))
    return out


def check_planner_design_richness(
    page_stats: list[dict[str, Any]], design_stats: list[dict[str, Any]],
    page_kinds: list[str],
) -> list[Finding]:
    """Sellable-quality gate. A working page with no tinted structure and no
    colour is a bare form; when a quarter or more of the working pages look
    like that, the planner is technically valid but visually weak, and it is
    reported as needing improvement instead of passing."""
    out: list[Finding] = []
    by_page = {int(s["page"]): s for s in design_stats or []}
    plain: list[int] = []
    working = 0
    for s in page_stats or []:
        i = int(s["page"])
        kind = page_kinds[i - 1] if i - 1 < len(page_kinds) else ""
        if kind not in _WORKING_KINDS:
            continue
        working += 1
        d = by_page.get(i)
        if d is None:
            continue
        if d["tint_pct"] < PLAIN_TINT_PCT and d["color_pct"] < PLAIN_COLOR_PCT:
            plain.append(i)
    if working and len(plain) / working >= PLAIN_PAGE_SHARE:
        out.append(Finding(
            code="PLAN_DESIGN_PLAIN", category="interior_design",
            severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
            summary="Interior pages read as bare forms: no tinted panels, no theme colour. "
                    "Needs improvement before it is sold as a premium planner.",
            detail=f"{len(plain)} of {working} working pages are plain: "
                   + ", ".join(str(p) for p in plain[:12])))
    return out


# --------------------------------------------------------------------------- #
# Planner-specific checks
# --------------------------------------------------------------------------- #
def check_planner_instruction_substance(
    prose_sections: list[tuple[str, str]], *,
    min_words: int = MIN_PROSE_WORDS, min_sections: int = MIN_PROSE_SECTIONS,
) -> list[Finding]:
    """A planner sold as a book has to teach something.

    Blank grids with a cover on them is the defining way this product type
    fails a customer, and it is measurable, so it is an objective check rather
    than a matter of taste.
    """
    out: list[Finding] = []
    total = sum(_words(body) for _h, body in prose_sections or [])
    count = len(prose_sections or [])
    if total < min_words:
        out.append(Finding(
            code="PLAN_NO_INSTRUCTION", category="instructional_value",
            severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
            summary="Planner carries almost no instructional text; it is a pad of "
                    "blank forms rather than a book.",
            detail=f"{total} words of prose, floor {min_words}"))
    elif count < min_sections:
        out.append(Finding(
            code="PLAN_THIN_INSTRUCTION", category="instructional_value",
            severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
            summary="Planner has very few instructional sections.",
            detail=f"{count} sections, floor {min_sections}"))
    return out


def check_planner_toc_accuracy(
    toc: list[tuple[str, int]], page_texts: list[str], page_titles: list[str],
) -> list[Finding]:
    """Every contents entry must point at the page it claims.

    A contents page is a promise about navigation. It is cheap to get wrong
    when the page plan and the renderer drift apart, and a reader finds it
    immediately.
    """
    out: list[Finding] = []
    total = len(page_texts)
    if not toc or not total:
        return out
    for label, number in toc:
        if number < 1 or number > total:
            out.append(Finding(
                code="PLAN_TOC_OUT_OF_RANGE", category="consistency",
                severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
                summary="Contents entry points to a page that does not exist.",
                location=f"'{label}' -> page {number}"))
            continue

        target = _norm(page_texts[number - 1])

        # 1. The entry must describe the page it points at. Comparing the
        #    *label* against the target page is the check that matters; an
        #    earlier version compared the target page against its own planned
        #    title, which is true by construction and caught nothing.
        #    Entries may carry a qualifier after a colon ("Week 1: Genesis
        #    1-3"), so the leading phrase is what must appear on the page.
        head = _norm(str(label).split(":")[0])
        if head and head not in target:
            out.append(Finding(
                code="PLAN_TOC_MISMATCH", category="consistency",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary="Contents entry does not match the page it points to.",
                location=f"'{label}' -> page {number}",
                detail=f"page {number} does not carry the heading {head!r}"))
            continue

        # 2. The renderer must also have drawn the page the planner planned,
        #    which catches drift between the page plan and the PDF.
        expected = page_titles[number - 1] if number - 1 < len(page_titles) else ""
        if expected and _norm(expected) not in target:
            out.append(Finding(
                code="PLAN_PAGE_TITLE_MISSING", category="consistency",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary="Planned page heading was not rendered on its page.",
                location=f"page {number}",
                detail=f"expected heading {expected!r}"))
    return out


def check_planner_cover_claim(
    cover_text: str, actual_pages: int,
) -> list[Finding]:
    """The cover advertises a page count. It has to be the real one."""
    out: list[Finding] = []
    m = re.search(r"(\d{1,4})\s*PAGES", str(cover_text or ""), re.I)
    if not m:
        return out
    claimed = int(m.group(1))
    if claimed != actual_pages:
        out.append(Finding(
            code="PLAN_COVER_PAGE_CLAIM", category="accuracy",
            severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
            summary="The cover advertises a page count the book does not have.",
            location="page 1",
            detail=f"cover claims {claimed} pages, PDF has {actual_pages}"))
    return out


def check_money_advice_disclaimer(
    planner_type: str, front_text: str,
) -> list[Finding]:
    """A budgeting product must tell the reader it is not personalised advice.

    Kept objective -- the presence of the statement is decidable -- but its
    absence is critical, because the failure mode is a reader treating a
    worksheet as guidance about their own money.
    """
    out: list[Finding] = []
    if planner_type != "budget_planner":
        return out
    blob = _norm(front_text)
    if not any(a in blob for a in _ADVICE_ANCHORS):
        out.append(Finding(
            code="PLAN_NO_ADVICE_DISCLAIMER", category="accuracy",
            severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
            summary="Money planner does not state that it is not personalised "
                    "financial advice.",
            location="front matter"))
    elif not any(a in blob for a in _PROFESSIONAL_ANCHORS):
        out.append(Finding(
            code="PLAN_NO_PROFESSIONAL_REFERRAL", category="accuracy",
            severity=SEV_MINOR, kind=KIND_OBJECTIVE,
            summary="Disclaimer does not point the reader to a qualified "
                    "professional for consequential decisions.",
            location="front matter"))
    return out


def check_planner_structure(page_kinds: list[str]) -> list[Finding]:
    """The page plan must contain the parts that make it a usable planner."""
    out: list[Finding] = []
    kinds = set(page_kinds or [])
    if "cover" not in kinds:
        out.append(Finding(
            code="PLAN_NO_COVER", category="cover_quality",
            severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
            summary="Planner has no cover page."))
    if "toc" not in kinds:
        out.append(Finding(
            code="PLAN_NO_CONTENTS", category="customer_value",
            severity=SEV_MINOR, kind=KIND_OBJECTIVE,
            summary="Planner has no contents page."))
    working = kinds & {
        "open_table", "labeled_table", "faith_daily", "faith_weekly",
        "habit_tracker", "calendar_month", "prompt_page", "snapshot",
        "lined_notes", "reading_plan",
    }
    if not working:
        out.append(Finding(
            code="PLAN_NO_WORKING_PAGES", category="customer_value",
            severity=SEV_CRITICAL, kind=KIND_OBJECTIVE,
            summary="Planner contains no worksheet pages to write on."))
    return out


# --------------------------------------------------------------------------- #
# Review
# --------------------------------------------------------------------------- #
def review_planner(
    candidate: dict[str, Any], *,
    served_pdf_sha: str = "",
    other_prose: dict[Any, str] | None = None,
    produced_by: str = PRODUCER_ID,
) -> ReviewReport:
    """Independent review of a finished planner. Never called by the builder
    that made the candidate -- `assert_independent_review` enforces it."""
    assert_independent_review(produced_by=produced_by, reviewed_by=REVIEWER_ID)

    rep = ReviewReport()
    f: list[Finding] = []

    planner_type = candidate.get("planner_type") or ""
    title = candidate.get("title") or ""
    page_texts: list[str] = candidate.get("page_texts") or []
    page_kinds: list[str] = candidate.get("page_kinds") or []
    page_titles: list[str] = candidate.get("page_titles") or []
    prose_sections: list[tuple[str, str]] = candidate.get("prose_sections") or []
    prose_pages: list[tuple[str, str]] = candidate.get("prose_pages") or []
    prose_blob = "\n\n".join(body for _h, body in prose_sections)
    full_text = candidate.get("full_text") or ""

    # -- originality / editorial ------------------------------------------
    # Duplication over prose only: repeated worksheet furniture is the design.
    rep.checks_run.append("prose_self_duplication")
    f += check_self_duplication(prose_blob)
    rep.checks_skipped["worksheet_self_duplication"] = (
        "repeated worksheet pages are intentional in a planner; duplication is "
        "checked over instructional prose instead"
    )
    rep.checks_run.append("placeholder_and_prompt_leak")
    f += check_placeholder_and_leak(full_text)
    rep.checks_run.append("customer_facing_leaks")
    f += check_customer_facing_leaks(full_text)

    # -- relevance ---------------------------------------------------------
    rep.checks_run.append("relevance")
    f += check_relevance(title, prose_pages)
    rep.checks_skipped["prompt_relevance"] = (
        "reflection prompts are recurring worksheet furniture, not chapters; "
        "relevance is judged over the instructional pages"
    )

    # -- consistency -------------------------------------------------------
    rep.checks_run.append("identity_consistency")
    meta = candidate.get("pdf_meta") or {}
    f += check_identity_consistency(
        title=title, author=candidate.get("author") or "",
        pdf_title=meta.get("Title", ""), pdf_author=meta.get("Author", ""))
    rep.checks_run.append("contents_accuracy")
    f += check_planner_toc_accuracy(
        candidate.get("toc") or [], page_texts, page_titles)

    # -- planner substance -------------------------------------------------
    rep.checks_run.append("instruction_substance")
    f += check_planner_instruction_substance(prose_sections)
    rep.checks_run.append("planner_structure")
    f += check_planner_structure(page_kinds)
    rep.checks_run.append("money_advice_disclaimer")
    f += check_money_advice_disclaimer(
        planner_type, "\n".join(page_texts[:4]))

    # -- design system -----------------------------------------------------
    rep.checks_run.append("page_furniture")
    f += check_planner_page_furniture(
        page_kinds, page_titles, page_texts,
        candidate.get("header_texts") or [], candidate.get("footer_texts") or [], title)
    rep.checks_run.append("print_safety")
    f += check_planner_print_safety(
        page_kinds, candidate.get("text_boxes") or [], candidate.get("page_rects") or [])
    rep.checks_run.append("render_notes")
    f += check_planner_render_notes(candidate.get("render_notes") or [])
    rep.checks_run.append("image_resolution")
    f += check_planner_cover_artwork(page_kinds, candidate.get("cover_images") or [])

    # -- rendered pages ----------------------------------------------------
    page_stats: list[dict[str, Any]] = []
    design_stats: list[dict[str, Any]] = []
    images = candidate.get("page_images") or []
    if images:
        rep.checks_run.append("rendered_page_analysis")
        page_stats = analyse_rendered_pages(images).get("pages") or []
        f += check_page_quality(page_stats, page_texts=page_texts or None)
        if "cover" in page_kinds[:1]:
            rep.checks_run.append("cover_page_composition")
            f += check_cover_page(images[0])
            rep.checks_run.append("cover_page_claim")
            f += check_planner_cover_claim(
                page_texts[0] if page_texts else "", len(page_texts) or len(images))
        rep.checks_run.append("theme_consistency")
        design_stats = analyse_planner_design(images)
        f += check_planner_theme_consistency(
            design_stats, page_kinds, candidate.get("design_theme") or "")
        rep.checks_run.append("design_richness")
        f += check_planner_design_richness(page_stats, design_stats, page_kinds)
    else:
        rep.checks_skipped["rendered_page_analysis"] = "no rendered page images supplied"
        rep.checks_skipped["theme_consistency"] = "no rendered page images supplied"
        rep.checks_skipped["design_richness"] = "no rendered page images supplied"

    rep.checks_run.append("page_count_reconciliation")
    f += check_page_count(
        int(candidate.get("declared_pages") or 0),
        len(page_stats) or len(page_texts),
        int(candidate.get("pdf_pages") or 0))

    # -- packaging ---------------------------------------------------------
    rep.checks_run.append("package_identity")
    f += check_package_identity(
        registered_pdf=candidate.get("pdf_path", ""),
        served_pdf_sha=served_pdf_sha,
        zip_path=candidate.get("zip_path", "") or "",
        pdf_name_in_zip=os.path.basename(candidate.get("pdf_path", "") or ""))

    # -- honestly recorded non-checks --------------------------------------
    rep.checks_skipped["photo_cover_verification"] = (
        "cover artwork is painted by the planner's own cover engine unless a "
        "photograph is dropped into the cover image slot; a supplied photograph "
        "is not verified for subject or licence here"
    )
    rep.checks_skipped["safety_sensitive_visual_verification"] = (
        "no instructional visuals in this product type"
    )
    rep.checks_skipped["external_plagiarism"] = "EXTERNAL PLAGIARISM CHECK NOT RUN"
    rep.checks_skipped["accessibility"] = (
        "print product; screen-reader and contrast review not automated here"
    )
    # Every finding this module can raise is objective. That is a real
    # limitation, not a clean bill of health: whether the budgeting guidance is
    # sound, or the reading plan well chosen, is a judgment no code makes. It
    # is defensible only because planner prose is fixed, human-authored content
    # reviewed once when written rather than generated per build. If planner
    # copy ever becomes model-generated, a judgment check belongs here and a
    # PASS without one would be misleading.
    rep.checks_skipped["editorial_judgment"] = (
        "planner prose is fixed human-authored copy, reviewed when written; "
        "no per-build judgment of its substance is performed"
    )
    if other_prose:
        from services.editor_in_chief import check_cross_project_duplication

        rep.checks_run.append("cross_project_duplication")
        f += check_cross_project_duplication(prose_blob, other_prose)
    else:
        rep.checks_skipped["cross_project_duplication"] = "no comparison corpus supplied"

    # -- verdict -----------------------------------------------------------
    rep.findings = f
    rep.scores = score_categories(f, PLANNER_CATEGORIES)
    rep.verdict, rep.overall = decide_verdict(f, rep.scores)
    rep.external_plagiarism_checked = False
    rep.evidence.update({
        "planner_type": planner_type,
        "declared_pages": candidate.get("declared_pages"),
        "pdf_pages": candidate.get("pdf_pages"),
        "rendered_pages": len(page_stats),
        "prose_words": _words(prose_blob),
        "prose_sections": len(prose_sections),
        "page_kinds": sorted(set(page_kinds)),
        "min_ink_pct": min((s["ink_pct"] for s in page_stats), default=None),
        "pdf_meta": meta,
        "design_theme": candidate.get("design_theme") or "",
        "cover_style": candidate.get("cover_style") or "",
        "cover_images": candidate.get("cover_images") or [],
        "render_notes": candidate.get("render_notes") or [],
        "design_quality": (
            "premium" if not any(fi.code in ("PLAN_DESIGN_PLAIN", "PLAN_THEME_DRIFT",
                                             "PLAN_COVER_FLAT", "PLAN_COVER_IMAGE_LOW_RES")
                                 for fi in f)
            else "needs improvement"),
    })
    return rep
