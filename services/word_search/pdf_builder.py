"""Word Search PDF builder — routes all exports through the MiniMax-style direct renderer."""
from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field

from .book import build_word_search_puzzles
from .builder import PuzzleResult
from .answer_key_validation import validate_puzzle_answer_key
from .direct_pdf_renderer import (
    DirectPdfLayoutInfo,
    build_book_pdf_bytes,
    build_single_worksheet_pdf_bytes,
    generate_verified_pdf,
    layout_info_to_dict,
)
from .layout_attempt import build_worksheet_layout_attempts
from .qa_agent import (
    WordSearchQAResult,
    run_book_product_quality_qa,
    run_word_search_qa,
)
from .solution_table import build_solution_table

# ACTIVE WORD SEARCH RENDERER: MiniMax-style renderer (direct_pdf_renderer.py)
# Legacy HTML/yellow-highlight renderer: renderer.py — not used for builder exports.


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "word_search").strip())
    return cleaned.strip("_").lower() or "word_search"


def html_to_pdf_bytes(html_doc: str) -> bytes:
    """LEGACY: convert old HTML workbook output to PDF — not used for builder exports."""
    from xhtml2pdf import pisa

    buffer = io.BytesIO()
    result = pisa.CreatePDF(html_doc, dest=buffer, encoding="utf-8")
    if result.err:
        raise RuntimeError("Word search PDF conversion failed.")
    data = buffer.getvalue()
    if not data:
        raise RuntimeError("Word search PDF conversion produced empty output.")
    return data


@dataclass
class WordSearchPdfRequest:
    product_title: str
    subtitle: str = ""
    audience: str = ""
    theme: str = ""
    difficulty: str = "medium"
    grid_size: int | str = 15
    number_of_puzzles: int = 5
    mode: str = "topic"
    custom_words: str = ""
    include_answer_key: bool = True
    output_type: str = "book"
    words_per_puzzle: int = 0
    include_cover: bool = True
    cover_design: dict | None = None
    package_id: str = ""
    seed: int | None = None


@dataclass
class WordSearchPdfResult:
    html: str = ""
    pdf_bytes: bytes = b""
    puzzles: list[PuzzleResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    filename: str = "word_search.pdf"
    render_engine: str = ""
    layout_info: dict = field(default_factory=dict)
    qa_report: WordSearchQAResult | None = None

    def as_dict(self) -> dict:
        return {
            "html": self.html,
            "puzzle_count": len(self.puzzles),
            "warnings": self.warnings,
            "errors": self.errors,
            "filename": self.filename,
            "pdf_size": len(self.pdf_bytes),
            "render_engine": self.render_engine,
            "layout_info": self.layout_info,
            "qa_report": self.qa_report.as_dict() if self.qa_report else {},
        }


def _layout_info_dict(layout: DirectPdfLayoutInfo) -> dict:
    return layout_info_to_dict(layout)


def _prepare_puzzle_for_export(puzzle: PuzzleResult) -> list[str]:
    """Validate paths and build the solution table for one puzzle."""
    validation = validate_puzzle_answer_key(puzzle)
    if not validation.ok:
        return list(validation.errors)
    puzzle.warnings.extend(validation.warnings)
    puzzle.validated_answer_key = list(validation.validated_paths)
    table, table_errors = build_solution_table(validation.validated_paths)
    if table_errors:
        return list(table_errors)
    puzzle.solution_table = table
    return []


def _build_book_with_minimax_renderer(
    request: WordSearchPdfRequest,
    puzzles: list[PuzzleResult],
) -> tuple[bytes, DirectPdfLayoutInfo, WordSearchQAResult]:
    """ACTIVE WORD SEARCH RENDERER: MiniMax-style renderer for multi-puzzle books."""
    for puzzle in puzzles:
        prep_errors = _prepare_puzzle_for_export(puzzle)
        if prep_errors:
            qa = WordSearchQAResult(
                passed=False,
                errors=list(prep_errors),
                blocked_export=True,
            )
            return b"", DirectPdfLayoutInfo(), qa

    pdf_bytes, layout = build_book_pdf_bytes(
        puzzles=puzzles,
        product_title=request.product_title,
        subtitle=request.subtitle,
        difficulty=request.difficulty,
        include_answer_key=bool(request.include_answer_key),
        cover_design=request.cover_design if request.include_cover else None,
    )
    qa = run_book_product_quality_qa(
        puzzles=puzzles,
        expected_puzzle_count=int(request.number_of_puzzles or len(puzzles)),
        words_per_puzzle=int(request.words_per_puzzle or 0) or None,
        include_answer_key=bool(request.include_answer_key),
        pdf_bytes=pdf_bytes,
    )
    if not pdf_bytes.startswith(b"%PDF"):
        qa.errors.append("PDF output is missing or invalid.")
        qa.passed = False
        qa.blocked_export = True
    return pdf_bytes, layout, qa


def _export_passing_layout_attempt(
    *,
    request: WordSearchPdfRequest,
    attempt,
) -> tuple[bytes, DirectPdfLayoutInfo, WordSearchQAResult]:
    """Render PDF only after a complete layout attempt has passed QA.

    ACTIVE WORD SEARCH RENDERER: MiniMax-style renderer via generate_verified_pdf.
    """
    puzzle = attempt.puzzle
    if puzzle is None:
        raise RuntimeError("Passing layout attempt is missing puzzle data.")

    # Use verified PDF generation with auto-fix for capsule issues
    pdf_bytes, layout, verification_errors = generate_verified_pdf(
        puzzle=puzzle,
        product_title=request.product_title,
        subtitle=request.subtitle,
        difficulty=request.difficulty,
        include_answer_key=bool(request.include_answer_key),
        cover_design=request.cover_design if request.include_cover else None,
    )
    
    qa = run_word_search_qa(
        puzzle=puzzle,
        layout_info=_layout_info_dict(layout),
        include_answer_key=bool(request.include_answer_key),
        pdf_bytes=pdf_bytes,
        words_per_puzzle=int(request.words_per_puzzle or 0) or None,
    )
    
    # If verification found issues, add warnings to QA result
    if verification_errors:
        qa.failure_reasons.extend(verification_errors)
    
    return pdf_bytes, layout, qa


def _build_single_worksheet_with_regen(
    request: WordSearchPdfRequest,
) -> tuple[list[PuzzleResult], list[str], bytes, DirectPdfLayoutInfo, WordSearchQAResult]:
    """Build worksheet PDF using complete layout attempts before export."""
    attempts, all_warnings, passing_attempt, qa_report = build_worksheet_layout_attempts(request)
    last_layout = DirectPdfLayoutInfo()

    if passing_attempt is not None and passing_attempt.puzzle is not None:
        pdf_bytes, layout, export_qa = _export_passing_layout_attempt(
            request=request,
            attempt=passing_attempt,
        )
        export_qa.original_grid_size = qa_report.original_grid_size
        export_qa.attempted_grid_sizes = list(qa_report.attempted_grid_sizes)
        export_qa.total_attempts = qa_report.total_attempts
        export_qa.final_grid_size_used = qa_report.final_grid_size_used
        export_qa.regeneration_attempts = qa_report.regeneration_attempts
        export_qa.failure_reasons = list(qa_report.failure_reasons)
        export_qa.oval_qa_passed = qa_report.oval_qa_passed
        if export_qa.passed:
            return [passing_attempt.puzzle], all_warnings, pdf_bytes, layout, export_qa
        qa_report = export_qa
        last_layout = layout

    puzzles = [item.puzzle for item in attempts if item.puzzle is not None]
    return puzzles[:1] if puzzles else [], all_warnings, b"", last_layout, qa_report


def build_word_search_pdf(request: WordSearchPdfRequest) -> WordSearchPdfResult:
    """Build worksheet or book PDF from topic/custom-list modes."""
    output_type = str(request.output_type or "book").strip().lower()

    result = WordSearchPdfResult(
        filename=f"{_slugify(request.product_title)}.pdf",
    )

    if output_type in {"single_worksheet", "single_page"}:
        from dataclasses import replace

        # HARD GUARD: single worksheet/page must NEVER have a cover.
        # Strip cover at the builder level as the final enforcement.
        if request.include_cover or request.cover_design:
            request = replace(request, include_cover=False, cover_design=None)

        puzzles, regen_warnings, pdf_bytes, layout, qa = _build_single_worksheet_with_regen(request)
        result.puzzles = puzzles
        result.warnings.extend(regen_warnings)
        result.qa_report = qa
        result.layout_info = _layout_info_dict(layout)
        if not qa.passed or not pdf_bytes:
            result.errors.extend(qa.errors)
            result.warnings.extend(qa.warnings)
            return result

        result.pdf_bytes = pdf_bytes
        result.render_engine = layout.render_engine
        result.warnings.extend(qa.warnings)
        result.html = ""
        return result

    mode = str(request.mode or "topic").strip().lower()
    if mode in {"custom", "custom_list"}:
        mode = "custom_word_list"

    puzzles, warnings, errors = build_word_search_puzzles(
        mode=mode,
        product_title=request.product_title,
        custom_words=request.custom_words,
        topic=request.theme,
        audience=request.audience,
        theme=request.theme,
        difficulty=request.difficulty,
        grid_size=request.grid_size,
        number_of_puzzles=request.number_of_puzzles,
        words_per_puzzle=request.words_per_puzzle,
        output_type=output_type,
        seed=request.seed,
    )

    result.puzzles = puzzles
    result.warnings = warnings
    result.errors = errors

    if errors or not puzzles:
        return result

    for puzzle in puzzles:
        prep_errors = _prepare_puzzle_for_export(puzzle)
        if prep_errors:
            result.errors.extend(prep_errors)
            result.qa_report = WordSearchQAResult(
                passed=False,
                errors=list(prep_errors),
                blocked_export=True,
            )
            return result

    pdf_bytes, layout, book_qa = _build_book_with_minimax_renderer(request, puzzles)
    result.qa_report = book_qa
    if not book_qa.passed or not pdf_bytes:
        result.errors.extend(book_qa.errors)
        result.warnings.extend(book_qa.warnings)
        return result

    result.pdf_bytes = pdf_bytes
    result.render_engine = layout.render_engine
    result.layout_info = _layout_info_dict(layout)
    result.warnings.extend(book_qa.warnings)
    result.html = ""
    return result


def save_word_search_pdf(
    request: WordSearchPdfRequest,
    output_dir: str,
) -> WordSearchPdfResult:
    """Build PDF and write to output_dir (for tests and local samples)."""
    result = build_word_search_pdf(request)
    if result.errors or not result.pdf_bytes:
        return result
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, result.filename)
    with open(path, "wb") as handle:
        handle.write(result.pdf_bytes)
    result.warnings.append(f"Saved PDF to {path}")
    return result
