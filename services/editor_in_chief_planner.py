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
    zip_path: str = "",
) -> dict[str, Any]:
    """Read the finished artifact. Nothing here trusts the builder's claims
    except the page plan itself, which is what the artifact is measured
    against."""
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
        page_texts = [p.get_text() for p in doc]
        doc.close()
    except Exception:  # noqa: BLE001
        pass
    candidate["page_texts"] = page_texts
    candidate["pdf_pages"] = pdf_pages
    candidate["pdf_meta"] = meta
    candidate["full_text"] = "\n".join(page_texts)
    return candidate


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

    # -- rendered pages ----------------------------------------------------
    page_stats: list[dict[str, Any]] = []
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
    else:
        rep.checks_skipped["rendered_page_analysis"] = "no rendered page images supplied"

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
        "planner covers are typographic by design; no photographic asset exists "
        "to verify"
    )
    rep.checks_skipped["image_resolution"] = "planner contains no raster images"
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
    })
    return rep
