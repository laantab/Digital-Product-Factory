"""Spelling Worksheet PDF builder — orchestrates AI word generation + PDF rendering."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field

from services.spelling_worksheet.builder import SpellingWorksheetResult, build_spelling_worksheet
from services.spelling_worksheet.renderer import (
    SpellingWorksheetLayoutInfo,
    build_spelling_worksheet_pdf_bytes,
)

EXPORTS_DIR = os.environ.get(
    "FLASK_EXPORTS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "exports"),
)


def _slugify(value: str) -> str:
    import re
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "spelling_worksheet").strip())
    return cleaned.strip("_").lower() or "spelling_worksheet"


@dataclass
class SpellingWorksheetPdfRequest:
    theme: str = ""
    grade: str = "3"
    word_count: int = 10
    custom_words: str = ""
    include_answer_key: bool = True
    output_type: str = "book"
    include_cover: bool = True
    cover_design: dict | None = None
    package_id: str = ""
    seed: int | None = None
    activity_type: str = "word list"


@dataclass
class SpellingWorksheetPdfResult:
    pdf_bytes: bytes = b""
    words: list = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    filename: str = "spelling_worksheet.pdf"
    render_engine: str = "spelling_worksheet_direct"
    layout_info: dict = field(default_factory=dict)


def build_spelling_worksheet_pdf(request: SpellingWorksheetPdfRequest) -> SpellingWorksheetPdfResult:
    """Generate spelling worksheet PDF: AI words + PDF rendering."""
    pkg = request.package_id or uuid.uuid4().hex
    slug = _slugify(request.theme or "spelling_worksheet")
    filename = f"{slug}.pdf"
    output_dir = os.path.join(EXPORTS_DIR, pkg)

    # Generate words via AI or use custom list
    worksheet = build_spelling_worksheet(
        theme=request.theme,
        grade=request.grade,
        word_count=request.word_count,
        custom_words=request.custom_words,
        include_answer_key=request.include_answer_key,
        activity_type=request.activity_type,
    )

    if worksheet.errors:
        return SpellingWorksheetPdfResult(errors=worksheet.errors)

    if not worksheet.all_words:
        return SpellingWorksheetPdfResult(errors=["No spelling words were generated."])

    # Render to PDF
    cover_img = ""
    if request.cover_design:
        cover_img = request.cover_design.get("local_image_path", "")

    pdf_bytes, layout = build_spelling_worksheet_pdf_bytes(
        worksheet,
        include_answer_key=request.include_answer_key,
        cover_image_path=cover_img,
    )

    if not pdf_bytes:
        return SpellingWorksheetPdfResult(errors=["Failed to render spelling worksheet PDF."])

    # Save to disk
    try:
        from services.spelling_worksheet.renderer import save_spelling_worksheet_pdf
        save_spelling_worksheet_pdf(worksheet, output_dir, filename)
    except Exception:  # noqa: BLE001
        pass

    layout_dict = {
        "render_engine": layout.render_engine,
        "practice_pages": layout.practice_pages,
        "dictation_pages": layout.dictation_pages,
        "answer_key_pages": layout.answer_key_pages,
        "cover_page_count": layout.cover_page_count,
        "word_count": len(worksheet.all_words),
    }

    return SpellingWorksheetPdfResult(
        pdf_bytes=pdf_bytes,
        words=worksheet.all_words,
        warnings=list(worksheet.warnings or []),
        errors=list(worksheet.errors or []),
        filename=filename,
        render_engine=layout.render_engine,
        layout_info=layout_dict,
    )
