"""Coloring Book PDF builder — orchestrates AI prompt generation + ReportLab PDF rendering."""
from __future__ import annotations

import base64
import os
import uuid
from dataclasses import dataclass, field

from services.coloring_book.builder import (
    ColoringBookResult,
    build_coloring_book,
    validate_theme_adherence,
    _generate_cover_image,
)
from services.coloring_book.prompt_engine import derive_cover_copy
from services.coloring_book.renderer import (
    ColoringBookLayoutInfo,
    build_coloring_book_pdf_bytes,
    save_coloring_book_pdf,
    draw_coloring_book_cover,
)
from services.ebook_package import get_last_image_error

EXPORTS_DIR = os.environ.get(
    "FLASK_EXPORTS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "exports"),
)


def _slugify(value: str) -> str:
    import re

    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "coloring_book").strip())
    return cleaned.strip("_").lower() or "coloring_book"


@dataclass
class ColoringBookPdfRequest:
    product_title: str = ""
    subtitle: str = ""
    theme: str = ""
    topic: str = ""  # Overall book topic (e.g. "Dinosaur Adventures")
    setting: str = ""  # The world/environment (e.g. "Enchanted jungle")
    main_character: str = ""  # Recurring character name
    page_count: int = 12
    age_group: str = ""
    art_style: str = ""
    include_captions: bool = False
    output_type: str = "book"
    include_cover: bool = True
    cover_design: dict | None = None
    package_id: str = ""
    seed: int | None = None
    # Quality mode: "ai_image_coloring_page" (AI images required) or "basic_test" (local fallback OK)
    quality_mode: str = "ai_image_coloring_page"
    # Creation modes
    creation_mode: str = "theme"  # "market_research" | "scratch" | "theme"
    # Benchmark data (market research mode)
    benchmark_niche: str = ""
    benchmark_audience: str = ""
    benchmark_reason: str = ""
    # Staged approval workflow
    generation_stage: str = "full"  # cover_preview | sample_interior | full
    character_approved: bool = False
    sample_approved: bool = False
    reference_image_path: str = ""
    force_image_regen: bool = False


@dataclass
class ColoringBookPdfResult:
    pdf_bytes: bytes = b""
    pages: list = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    filename: str = "coloring_book.pdf"
    render_engine: str = "coloring_book_direct"
    layout_info: dict = field(default_factory=dict)
    cover_image_path: str = ""
    cover_design: dict | None = None
    cover_prompt: str = ""
    qa_result: dict | None = None  # ColoringBookQualityResult.as_dict()
    generation_stage: str = "full"
    character_bible: dict | None = None
    sample_prompt: str = ""
    consistency_notes: list = field(default_factory=list)


def build_coloring_book_pdf(request: ColoringBookPdfRequest) -> ColoringBookPdfResult:
    """
    Generate coloring book PDF:
    1. Build page prompts via AI (builder.py)
    2. Render pages to PDF (renderer.py)
    3. Optionally merge cover image as first page
    """
    pkg = request.package_id or uuid.uuid4().hex
    slug = _slugify(request.product_title)
    filename = f"{slug}.pdf"
    output_dir = os.path.join(EXPORTS_DIR, pkg)

    stage = str(request.generation_stage or "full").strip().lower()
    if stage not in {"cover_preview", "sample_interior", "full"}:
        stage = "full"

    # Step 1: Generate page prompts (and attempt image generation based on quality_mode)
    book = build_coloring_book(
        theme=request.theme,
        topic=request.topic,
        setting=request.setting,
        main_character=request.main_character,
        page_count=request.page_count,
        age_group=request.age_group,
        art_style=request.art_style,
        product_title=request.product_title,
        subtitle=request.subtitle,
        include_captions=request.include_captions,
        package_id=pkg,
        seed=request.seed,
        quality_mode=request.quality_mode,
        creation_mode=request.creation_mode,
        benchmark_niche=request.benchmark_niche,
        benchmark_audience=request.benchmark_audience,
        benchmark_reason=request.benchmark_reason,
        generation_stage=stage,
        character_approved=bool(request.character_approved),
        sample_approved=bool(request.sample_approved),
        reference_image_path=request.reference_image_path or "",
        force_image_regen=bool(request.force_image_regen),
    )

    if book.errors:
        return ColoringBookPdfResult(
            errors=book.errors,
            warnings=list(book.warnings or []),
            pages=[p.as_dict() for p in book.pages],
            cover_prompt=book.cover_prompt or "",
            generation_stage=stage,
            character_bible=book.character_bible,
            sample_prompt=(book.pages[0].line_art_prompt if book.pages else ""),
            consistency_notes=list(book.consistency_notes or []),
        )

    # ── Theme Adherence Validation ─────────────────────────────────────────────
    # Ensure generated pages actually incorporate the user's full theme.
    # If required theme keywords are missing from most pages, surface a warning
    # so the QA agent can flag it downstream.
    theme_adherence_ok, missing_keywords = validate_theme_adherence(
        theme=request.theme,
        pages=[p.as_dict() for p in book.pages],
        cover_prompt=book.cover_prompt or "",
    )
    theme_warnings = []
    if not theme_adherence_ok:
        missing_display = ", ".join(repr(k) for k in missing_keywords[:5])
        warning = (
            f"Theme adherence warning: the following theme details may be missing "
            f"from the generated plan: {missing_display}. "
            f"The plan should reflect every key element from the user's theme."
        )
        theme_warnings.append(warning)
        book.warnings = list(book.warnings) + theme_warnings

    # AI Image Coloring Page quality gate: AI images MUST be generated for full books.
    # Preview stages intentionally omit most interiors until the user approves.
    if request.quality_mode == "ai_image_coloring_page" and stage == "full":
        pages_without_images = [
            p.page_number for p in book.pages if not p.image_path or not os.path.isfile(p.image_path)
        ]
        if pages_without_images:
            real_error = get_last_image_error()
            if real_error:
                ai_error = (
                    "AI Image Coloring Page is configured but image generation failed: "
                    f"{real_error}"
                )
            else:
                ai_error = (
                    "AI Image Coloring Page requires an image-generation key. "
                    "Add the following to your .env file:\n\n"
                    "AI_INTEGRATIONS_OPENAI_API_KEY=your_api_key_here\n"
                    "AI_INTEGRATIONS_OPENAI_BASE_URL=https://api.openai.com/v1\n\n"
                    "Then restart the app. "
                    "Or switch to Basic Test Fallback for a non-sellable test page."
                )
            return ColoringBookPdfResult(
                errors=[ai_error],
                warnings=book.warnings,
                generation_stage=stage,
                character_bible=book.character_bible,
            )
    elif request.quality_mode == "ai_image_coloring_page" and stage == "sample_interior":
        sample = next((p for p in book.pages if p.page_number == 1), None)
        if not sample or not sample.image_path or not os.path.isfile(sample.image_path):
            real_error = get_last_image_error()
            return ColoringBookPdfResult(
                errors=[
                    f"Sample interior image generation failed: {real_error}"
                    if real_error
                    else "Sample interior image was not generated."
                ],
                warnings=book.warnings,
                generation_stage=stage,
                character_bible=book.character_bible,
                cover_prompt=book.cover_prompt or "",
                sample_prompt=(sample.line_art_prompt if sample else ""),
            )

    # Extract QA result (already run inside build_coloring_book)
    qa_result = book.quality_result
    qa_passed = qa_result is None or qa_result.get("all_passed", False) if qa_result else True

    # A full product that fails QA must never become a downloadable artifact.
    # Preview stages may still render so the user can inspect and revise them.
    warnings = list(book.warnings or [])
    if qa_result and qa_result.get("blocked_export"):
        failed = qa_result.get("total_failed", 0)
        failed_pages = [
            f"P{p['page_number']} ({p.get('topic', '')})"
            for p in qa_result.get("pages", [])
            if not p.get("quality_pass")
        ]
        qa_message = (
            f"QA blocked: {failed} page(s) with quality issues — {', '.join(failed_pages[:3])}"
            + (" ..." if len(failed_pages) > 3 else "")
        )
        if stage == "full":
            return ColoringBookPdfResult(
                pdf_bytes=b"",
                pages=[p.as_dict() for p in book.pages],
                warnings=warnings,
                errors=[qa_message],
                filename=filename,
                qa_result=qa_result,
                generation_stage=stage,
                character_bible=book.character_bible,
                cover_prompt=book.cover_prompt or "",
                consistency_notes=list(book.consistency_notes or []),
            )
        warnings.append(qa_message)

    # Step 2: Cover design — title/subtitle via layout; artwork separate
    cover_copy = derive_cover_copy(
        request.theme,
        product_title=request.product_title or book.product_title,
        subtitle=request.subtitle or book.subtitle,
    )
    cover_design = dict(request.cover_design or {}) if request.cover_design else {}
    cover_img = ""
    if request.include_cover and request.output_type != "single_page":
        os.makedirs(output_dir, exist_ok=True)
        cover_candidate = os.path.join(output_dir, "cover.png")
        img_cover_path = os.path.join(output_dir, "img_cover.png")

        force_cover = bool(request.force_image_regen and stage == "cover_preview")
        if (
            not force_cover
            and cover_design.get("local_image_path")
            and os.path.isfile(str(cover_design.get("local_image_path")))
        ):
            cover_img = str(cover_design.get("local_image_path"))
        elif not force_cover and os.path.isfile(img_cover_path):
            cover_img = img_cover_path
        elif not force_cover and os.path.isfile(cover_candidate):
            cover_img = cover_candidate
        elif request.quality_mode == "ai_image_coloring_page" and book.cover_prompt:
            # Paid image path — cover preview / AI mode only (never on Save/Export alone)
            if stage in {"cover_preview", "sample_interior", "full"}:
                if _generate_cover_image(
                    book.cover_prompt,
                    img_cover_path,
                    force=force_cover,
                ):
                    cover_img = img_cover_path
                    try:
                        import shutil
                        shutil.copyfile(img_cover_path, cover_candidate)
                    except Exception:  # noqa: BLE001
                        pass

        if not cover_img:
            local_cover = draw_coloring_book_cover(
                product_title=cover_copy.title,
                subtitle=cover_copy.subtitle,
                theme=request.theme,
                age_group=request.age_group,
                art_style=request.art_style,
                package_id=pkg,
                badge=cover_copy.badge,
                cover_design=cover_design or None,
            )
            if local_cover and os.path.isfile(local_cover):
                cover_img = local_cover

        cover_design.update(
            {
                "title": cover_copy.title,
                "subtitle": cover_copy.subtitle,
                "badge": cover_copy.badge,
                "overlay_style": cover_copy.overlay_style or "retail_jumbo_banner",
                "author": "",  # coloring covers: no author name overlay
                "package_id": pkg,
                "product_type": "coloring_book",
                "image_prompt": book.cover_prompt,
                "cover_prompt": book.cover_prompt,
                "local_image_path": cover_img,
                "text_overlay": True,
                "text_y": 78,
                "text_position": {"x": 50.0, "y": 12.0, "align": "left"},
                "use_ai_image": bool(cover_img and os.path.isfile(cover_img)),
                "layout": "full_bleed_retail_jumbo",
            }
        )

    _single_sheet_flag = (request.output_type == "single_page")
    print(f"[pdf_builder] output_type={request.output_type!r} -> single_sheet={_single_sheet_flag}")
    # Preview stages: cover-only or cover+sample page PDF for approval UI
    pages_for_pdf = book.pages
    if stage == "cover_preview":
        pages_for_pdf = []
    elif stage == "sample_interior":
        pages_for_pdf = [p for p in book.pages if p.page_number == 1]

    from types import SimpleNamespace

    book_for_pdf = SimpleNamespace(
        product_title=book.product_title,
        subtitle=book.subtitle,
        pages=pages_for_pdf,
        cover_prompt=book.cover_prompt,
    )

    from services.coloring_book.prompt_engine import pdf_metadata_for_theme

    meta = pdf_metadata_for_theme(request.theme, product_title=request.product_title or book.product_title)

    pdf_bytes, layout = build_coloring_book_pdf_bytes(
        book_for_pdf,
        include_answer_key=False,
        cover_image_path=cover_img,
        single_sheet=_single_sheet_flag,
        cover_design=cover_design if cover_design else None,
        pdf_metadata=meta,
    )

    if not pdf_bytes:
        return ColoringBookPdfResult(
            errors=["Failed to render coloring book PDF."],
            qa_result=qa_result,
        )

    # Step 3: Save to disk
    try:
        save_coloring_book_pdf(book, output_dir, filename)
    except Exception:  # noqa: BLE001
        pass  # non-fatal; bytes are already returned

    layout_dict = {
        "render_engine": layout.render_engine,
        "page_count": layout.page_count,
        "image_pages": layout.image_pages,
        "text_pages": layout.text_pages,
        "cover_page_count": layout.cover_page_count,
    }

    if layout.image_pages == 0:
        if request.quality_mode == "ai_image_coloring_page":
            real_error = get_last_image_error()
            if real_error:
                warnings.append(
                    f"Image generation failed: {real_error}"
                )
            else:
                warnings.append(
                    "No images were generated. AI Image Coloring Page requires an image-generation key."
                )
        # In basic_test mode, local fallback is expected — no need to warn again

    return ColoringBookPdfResult(
        pdf_bytes=pdf_bytes,
        pages=[p.as_dict() for p in book.pages],
        warnings=warnings,
        errors=list(book.errors or []),
        filename=filename,
        render_engine=layout.render_engine,
        layout_info=layout_dict,
        cover_image_path=cover_img,
        cover_design=cover_design if cover_design else None,
        cover_prompt=book.cover_prompt or "",
        qa_result=qa_result,
        generation_stage=stage,
        character_bible=book.character_bible,
        sample_prompt=(book.pages[0].line_art_prompt if book.pages else ""),
        consistency_notes=list(book.consistency_notes or []),
    )
