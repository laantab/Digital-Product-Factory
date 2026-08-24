"""Ebook adapter for the Editor-in-Chief gate.

Collects the evidence an ebook candidate can supply -- rendered pages, the
real image files at their real placement sizes, PDF metadata, package digests
-- and runs the generic checks in services.editor_in_chief against it.

Nothing here is specific to a topic or project. Another product type gets its
own adapter; the rules themselves stay shared.
"""
from __future__ import annotations

import os
import re
from typing import Any

from services.editor_in_chief import (
    CorrectionSession, Finding, ReviewReport,
    KIND_JUDGMENT, KIND_OBJECTIVE, SEV_CRITICAL, SEV_MAJOR, SEV_MINOR,
    analyse_rendered_pages, check_assets_present, check_chart_and_table_data,
    check_cross_project_duplication, check_customer_facing_leaks,
    check_identity_consistency, check_image_resolution, check_package_identity,
    check_page_count, check_page_quality, check_placeholder_and_leak,
    check_cover_page, check_cover_is_photo_backed, check_relevance,
    check_self_duplication, check_typography,
    check_visual_subject_verification, decide_verdict, inspect_image_file,
    is_safety_sensitive, score_categories,
)


def read_pdf_metadata(pdf_path: str) -> dict[str, str]:
    """Title/Author/Subject as actually written into the PDF."""
    out = {"Title": "", "Author": "", "Subject": "", "Creator": "", "Producer": ""}
    try:
        raw = open(pdf_path, "rb").read()
    except OSError:
        return out
    for key in out:
        m = re.search(rb"/" + key.encode() + rb"\s*\(((?:[^()\\]|\\.)*)\)", raw)
        if m:
            try:
                decoded = m.group(1).decode("latin-1")
                # PDF literal strings escape non-ASCII bytes as \NNN octal
                # (e.g. an apostrophe as \047). Leaving them unexpanded made a
                # correct title read as "Beginner\047s Guide..." and raised a
                # false META_TITLE_MISMATCH against its own product title.
                decoded = re.sub(
                    r"\\([0-7]{1,3})", lambda g: chr(int(g.group(1), 8)), decoded
                )
                out[key] = decoded.replace("\\(", "(").replace("\\)", ")")
            except Exception:  # noqa: BLE001
                out[key] = ""
    return out


def pdf_page_count(pdf_path: str) -> int:
    try:
        raw = open(pdf_path, "rb").read()
    except OSError:
        return 0
    counts = [int(m) for m in re.findall(rb"/Count\s+(\d+)", raw)]
    pages = len(re.findall(rb"/Type\s*/Page[^s]", raw))
    return max(counts) if counts else pages


def css_placement_inches(html: str) -> dict[str, float]:
    """Placement sizes the stylesheet actually imposes, used for DPI maths."""
    out = {"figure_max_in": 0.0, "cover_max_in": 0.0}
    m = re.search(r"\.ebook-figure img\s*\{[^}]*max-height\s*:\s*([\d.]+)in", html, re.I)
    if m:
        out["figure_max_in"] = float(m.group(1))
    m = re.search(r"max-width\s*:\s*([\d.]+)in", html, re.I)
    if m:
        out["cover_max_in"] = float(m.group(1))
    return out


def collect_ebook_candidate(
    data: dict[str, Any], *, package_dir: str, page_images: list[str] | None = None,
) -> dict[str, Any]:
    """Gather the artifact-level evidence for one ebook candidate."""
    html_path = os.path.join(package_dir, "ebook.html")
    pdf_path = os.path.join(package_dir, "ebook.pdf")
    zip_path = os.path.join(package_dir, "package.zip")
    html = ""
    if os.path.isfile(html_path):
        html = open(html_path, encoding="utf-8", errors="replace").read()
    placement = css_placement_inches(html)

    assets: list[dict[str, Any]] = []
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    cover_path = str(cover.get("image_path") or os.path.join(package_dir, "img_cover.png"))
    if os.path.isfile(cover_path):
        info = inspect_image_file(cover_path)
        assets.append({
            "name": os.path.basename(cover_path), "path": cover_path, "kind": "cover",
            "location": "cover (page 1)", "width": info["width"], "height": info["height"],
            "placed_inches": placement["cover_max_in"], "_info": info,
            "source_type": (cover.get("source") or {}).get("source_type", ""),
            "subject_verified_by_human": bool(cover.get("subject_verified_by_human")),
        })

    plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {}
    aids: list[dict[str, Any]] = []
    for ch in plan.get("chapters") or []:
        for aid in ch.get("aids") or []:
            if not isinstance(aid, dict):
                continue
            aids.append(aid)
            kind = str(aid.get("type") or "").lower()
            if kind not in ("stock photo", "photo", "illustration", "infographic"):
                continue
            p = str(aid.get("factory_asset_path") or aid.get("asset_path") or "")
            info = inspect_image_file(p)
            assets.append({
                "name": os.path.basename(p) or str(aid.get("visual_id") or ""),
                "path": p, "kind": "photo",
                "location": f"{ch.get('chapter', '')} (ch {aid.get('chapter_index', '?')})",
                "width": info["width"], "height": info["height"],
                "placed_inches": placement["figure_max_in"], "_info": info,
                "sha256": aid.get("sha256") or "",
                "source_type": aid.get("source_type") or aid.get("source") or "",
                "subject_verified_by_human": bool(aid.get("subject_verified_by_human")),
                "caption": aid.get("caption") or "",
            })

    return {
        "title": str(data.get("title") or ""),
        "author": str(data.get("author_brand") or data.get("author") or ""),
        "manuscript": str(data.get("content") or data.get("ebook") or ""),
        "html": html, "html_path": html_path, "pdf_path": pdf_path, "zip_path": zip_path,
        "package_dir": package_dir, "assets": assets, "aids": aids,
        "page_images": list(page_images or []),
        "pdf_meta": read_pdf_metadata(pdf_path),
        "pdf_pages": pdf_page_count(pdf_path),
        "declared_pages": int(data.get("page_count") or 0),
        "placement": placement,
        # Real per-chapter grouping for the visual-sufficiency check. Aid dicts
        # carry no "chapter" field of their own, so without this the fallback
        # reconstruction in _plan_from_candidate() grouped every aid from every
        # chapter under one bucket keyed by "" (aid.get("chapter") always
        # missing) -- the visual_sufficiency check has never been able to tell
        # which chapter's requirement a photo actually satisfied.
        "_plan_chapters": list(plan.get("chapters") or []),
    }


def review_ebook(
    candidate: dict[str, Any], *,
    other_manuscripts: dict[Any, str] | None = None,
    served_pdf_sha: str = "", rollback_pdf: str = "", rollback_expected_sha: str = "",
    external_plagiarism_available: bool = False,
    print_product: bool = True,
) -> ReviewReport:
    """Independent review of a finished ebook candidate."""
    rep = ReviewReport()
    f: list[Finding] = []
    manuscript = candidate.get("manuscript") or ""
    html = candidate.get("html") or ""
    title = candidate.get("title") or ""
    author = candidate.get("author") or ""
    assets = candidate.get("assets") or []

    from services.ebook_book_layout import numbered_chapters
    chapters = numbered_chapters(manuscript)

    # -- originality -------------------------------------------------------
    rep.checks_run.append("self_duplication")
    f += check_self_duplication(manuscript)
    rep.checks_run.append("placeholder_and_prompt_leak")
    f += check_placeholder_and_leak(manuscript)
    if other_manuscripts:
        rep.checks_run.append("cross_project_duplication")
        f += check_cross_project_duplication(manuscript, other_manuscripts)
    else:
        rep.checks_skipped["cross_project_duplication"] = "no comparison corpus supplied"
    if external_plagiarism_available:
        rep.external_plagiarism_checked = True
        rep.checks_run.append("external_plagiarism")
    else:
        rep.external_plagiarism_checked = False
        rep.checks_skipped["external_plagiarism"] = "EXTERNAL PLAGIARISM CHECK NOT RUN"

    # -- relevance / consistency ------------------------------------------
    rep.checks_run.append("relevance")
    f += check_relevance(title, chapters)
    rep.checks_run.append("identity_consistency")
    meta = candidate.get("pdf_meta") or {}
    f += check_identity_consistency(
        title=title, author=author,
        pdf_title=meta.get("Title", ""), pdf_author=meta.get("Author", ""))

    # -- visuals -----------------------------------------------------------
    rep.checks_run.append("asset_integrity")
    f += check_assets_present(assets)
    rep.checks_run.append("cover_photo_backed")
    f += check_cover_is_photo_backed(assets)
    rep.checks_run.append("image_resolution")
    f += check_image_resolution(assets, print_product=print_product)
    rep.checks_run.append("chart_and_table_data")
    f += check_chart_and_table_data(candidate.get("aids") or [])
    rep.checks_run.append("safety_sensitive_visual_verification")
    f += check_visual_subject_verification(
        assets, subject_text=f"{title} {manuscript[:4000]}")

    # -- rendered pages ----------------------------------------------------
    page_stats: list[dict[str, Any]] = []
    if candidate.get("page_images"):
        rep.checks_run.append("rendered_page_analysis")
        res = analyse_rendered_pages(candidate["page_images"])
        page_stats = res.get("pages") or []
        page_texts: list[str] | None = None
        try:
            import fitz

            doc = fitz.open(candidate.get("pdf_path") or "")
            page_texts = [p.get_text() for p in doc]
        except Exception:
            page_texts = None
        f += check_page_quality(page_stats, page_texts=page_texts)
        rep.checks_run.append("cover_page_composition")
        f += check_cover_page(candidate["page_images"][0])
    else:
        rep.checks_skipped["rendered_page_analysis"] = "no rendered page images supplied"
    rep.checks_run.append("page_count_reconciliation")
    f += check_page_count(candidate.get("declared_pages") or 0,
                          len(page_stats), candidate.get("pdf_pages") or 0)

    # -- typography / leaks ------------------------------------------------
    rep.checks_run.append("typography")
    f += check_typography(html)
    rep.checks_run.append("customer_facing_leaks")
    f += check_customer_facing_leaks(html, manuscript)

    # -- packaging ---------------------------------------------------------
    rep.checks_run.append("package_identity")
    f += check_package_identity(
        registered_pdf=candidate.get("pdf_path", ""), served_pdf_sha=served_pdf_sha,
        zip_path=candidate.get("zip_path", ""), rollback_pdf=rollback_pdf,
        rollback_expected_sha=rollback_expected_sha)

    # -- visual sufficiency (reuses the typed requirement model) -----------
    try:
        from services.ebook_visual_requirements import validate_visual_plan_typed

        rep.checks_run.append("visual_sufficiency")
        typed = validate_visual_plan_typed(
            {"chapters": (candidate.get("_plan_chapters") or [])} if candidate.get("_plan_chapters")
            else _plan_from_candidate(candidate),
            content_md=manuscript, title=title, topic=title)
        for u in typed.get("unresolved_visual_requirements") or []:
            f.append(Finding(
                code="VIS_REQUIREMENT_UNMET", category="instructional_value",
                severity=SEV_MAJOR, kind=KIND_OBJECTIVE,
                summary="A chapter's visual requirement is not satisfied by a real visual.",
                location=str(u.get("chapter") or "")))
        rep.evidence["typed_visuals"] = {
            k: typed.get(k) for k in
            ("required_instructional_count", "verified_instructional_count",
             "supporting_component_count", "visual_requirements_met")
        }
    except Exception as exc:  # noqa: BLE001
        rep.checks_skipped["visual_sufficiency"] = f"unavailable: {exc}"[:120]

    # -- verdict -----------------------------------------------------------
    rep.findings = f
    rep.scores = score_categories(f)
    rep.verdict, rep.overall = decide_verdict(f, rep.scores)
    rep.evidence.update({
        "pdf_pages": candidate.get("pdf_pages"),
        "rendered_pages": len(page_stats),
        "pdf_meta": meta,
        "asset_count": len(assets),
        "safety_sensitive": is_safety_sensitive(title, manuscript[:4000]),
        "placement_inches": candidate.get("placement"),
        "asset_dpi": {a.get("name"): a.get("effective_dpi") for a in assets
                      if a.get("effective_dpi")},
    })
    return rep


def _plan_from_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    """Rebuild a minimal plan shape for the typed visual validator."""
    by_chapter: dict[str, list[dict[str, Any]]] = {}
    for aid in candidate.get("aids") or []:
        by_chapter.setdefault(str(aid.get("chapter") or ""), []).append(aid)
    return {"chapters": [{"chapter": k, "aids": v} for k, v in by_chapter.items()]}
