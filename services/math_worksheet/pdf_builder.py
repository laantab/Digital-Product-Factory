"""Math Worksheet PDF builder — orchestrates local procedural problem generation + PDF rendering."""
from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field

from services.math_worksheet.builder import MathWorksheetResult, build_math_worksheet
from services.math_worksheet.renderer import (
    MathWorksheetLayoutInfo,
    build_math_worksheet_pdf_bytes,
)

EXPORTS_DIR = os.environ.get(
    "FLASK_EXPORTS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "exports"),
)


def _slugify(value: str) -> str:
    import re
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "math_worksheet").strip())
    return cleaned.strip("_").lower() or "math_worksheet"


@dataclass
class MathWorksheetPdfRequest:
    worksheet_title: str = ""
    grade: str = "3"
    math_topic: str = ""
    difficulty: str = "Medium"
    problem_count: int = 20
    include_answer_key: bool = True
    include_challenge: bool = False
    output_type: str = "book"
    include_cover: bool = True
    cover_design: dict | None = None
    package_id: str = ""
    seed: int | None = None


@dataclass
class MathWorksheetPdfResult:
    pdf_bytes: bytes = b""
    problems: list = field(default_factory=list)
    challenge_problems: list = field(default_factory=list)
    include_challenge: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    filename: str = "math_worksheet.pdf"
    render_engine: str = "math_worksheet_direct"
    layout_info: dict = field(default_factory=dict)


def build_math_worksheet_pdf(request: MathWorksheetPdfRequest) -> MathWorksheetPdfResult:
    """Generate math worksheet PDF using the local procedural generator (no AI)."""
    pkg = request.package_id or uuid.uuid4().hex
    slug = _slugify(request.worksheet_title or "math_worksheet")
    filename = f"{slug}.pdf"
    output_dir = os.path.join(EXPORTS_DIR, pkg)

    # Local procedural generation — no AI dependency.
    worksheet = build_math_worksheet(
        worksheet_title=request.worksheet_title,
        grade=request.grade,
        math_topic=request.math_topic,
        difficulty=request.difficulty,
        problem_count=request.problem_count,
        include_answer_key=request.include_answer_key,
        include_challenge=request.include_challenge,
    )

    if worksheet.errors:
        return MathWorksheetPdfResult(errors=worksheet.errors)

    if not worksheet.problems:
        return MathWorksheetPdfResult(errors=["No math problems were generated."])

    # Render to PDF
    cover_img = ""
    if request.cover_design:
        cover_img = request.cover_design.get("local_image_path", "")

    pdf_bytes, layout = build_math_worksheet_pdf_bytes(
        worksheet,
        include_answer_key=request.include_answer_key,
        cover_image_path=cover_img,
    )

    if not pdf_bytes:
        return MathWorksheetPdfResult(errors=["Failed to render math worksheet PDF."])

    # Save to disk
    try:
        from services.math_worksheet.renderer import save_math_worksheet_pdf
        save_math_worksheet_pdf(worksheet, output_dir, filename)
    except Exception:  # noqa: BLE001
        pass

    layout_dict = {
        "render_engine": layout.render_engine,
        "worksheet_pages": layout.worksheet_pages,
        "answer_key_pages": layout.answer_key_pages,
        "cover_page_count": layout.cover_page_count,
        "problem_count": len(worksheet.problems),
        "challenge_count": len(worksheet.challenge_problems),
        "include_challenge": bool(request.include_challenge),
    }

    return MathWorksheetPdfResult(
        pdf_bytes=pdf_bytes,
        problems=[p.as_dict() for p in worksheet.problems],
        challenge_problems=[p.as_dict() for p in worksheet.challenge_problems],
        include_challenge=bool(request.include_challenge),
        warnings=list(worksheet.warnings or []),
        errors=list(worksheet.errors or []),
        filename=filename,
        render_engine=layout.render_engine,
        layout_info=layout_dict,
    )
