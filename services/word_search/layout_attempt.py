"""Complete Word Search layout attempts — build fully before QA decides export."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .answer_key_validation import validate_puzzle_answer_key
from .book import build_word_search_puzzles
from .builder import PuzzleResult
from .direct_pdf_renderer import (
    DirectPdfLayoutInfo,
    compute_single_worksheet_layout,
    layout_info_to_dict,
)
from .qa_agent import WordSearchQAResult, run_layout_attempt_qa
from .solution_table import (
    SolutionTable,
    build_solution_table,
)


@dataclass
class LayoutAttempt:
    attempt_number: int
    grid_size: int
    grid: list[list[str]] = field(default_factory=list)
    word_list: list[str] = field(default_factory=list)
    solution_paths: list[dict] = field(default_factory=list)
    oval_table: SolutionTable | None = None
    puzzle_page_layout: dict = field(default_factory=dict)
    answer_key_layout: dict = field(default_factory=dict)
    qa_result: WordSearchQAResult | None = None
    passed: bool = False
    puzzle: PuzzleResult | None = None
    layout_info: DirectPdfLayoutInfo | None = None
    build_errors: list[str] = field(default_factory=list)
    oval_errors: list[str] = field(default_factory=list)
    oval_warnings: list[str] = field(default_factory=list)
    generation_errors: list[str] = field(default_factory=list)
    pdf_bytes: bytes = b""


def _prepare_solution_data(puzzle: PuzzleResult) -> list[str]:
    """Validate paths and build the solution table. Returns errors or empty list."""
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


def build_complete_layout_attempt(
    *,
    attempt_number: int,
    grid_size: int,
    seed: int,
    mode: str,
    request,
) -> LayoutAttempt:
    """Build one full layout attempt before any export decision."""
    attempt = LayoutAttempt(attempt_number=attempt_number, grid_size=grid_size)
    output_type = "single_worksheet"

    puzzles, warnings, errors = build_word_search_puzzles(
        mode=mode,
        product_title=request.product_title,
        custom_words=request.custom_words,
        topic=request.theme,
        audience=request.audience,
        theme=request.theme,
        difficulty=request.difficulty,
        grid_size=grid_size,
        number_of_puzzles=1,
        output_type=output_type,
        seed=seed,
    )
    attempt.generation_errors = list(errors)
    if warnings:
        attempt.build_errors.extend(warnings)

    if errors or not puzzles:
        attempt.build_errors.extend(errors or ["No puzzle generated."])
        attempt.qa_result = WordSearchQAResult(
            passed=False,
            errors=list(attempt.build_errors),
            blocked_export=True,
        )
        attempt.passed = False
        return attempt

    puzzle = copy.deepcopy(puzzles[0])
    attempt.puzzle = puzzle
    attempt.grid = [list(row) for row in puzzle.grid]
    attempt.word_list = list(puzzle.word_bank)

    prep_errors = _prepare_solution_data(puzzle)
    if prep_errors:
        attempt.build_errors.extend(prep_errors)
        attempt.solution_paths = list(puzzle.validated_answer_key)
        attempt.oval_table = puzzle.solution_table
        attempt.qa_result = WordSearchQAResult(
            passed=False,
            errors=list(prep_errors),
            blocked_export=True,
        )
        attempt.passed = False
        return attempt

    attempt.solution_paths = list(puzzle.validated_answer_key)
    attempt.oval_table = puzzle.solution_table

    include_answer_key = bool(request.include_answer_key)
    layout, oval_errors, oval_warnings = compute_single_worksheet_layout(
        puzzle,
        subtitle=request.subtitle,
        include_answer_key=include_answer_key,
    )
    attempt.layout_info = layout
    attempt.oval_errors = list(oval_errors)
    attempt.oval_warnings = list(oval_warnings)

    layout_dict = layout_info_to_dict(layout)
    attempt.puzzle_page_layout = {
        key: layout_dict[key]
        for key in (
            "page_count",
            "outer_box_count",
            "word_list_columns",
            "cell_size_pt",
            "grid_size",
            "puzzle_page_mark_count",
            "grid_centered",
            "puzzle_fits_one_page",
            "word_list_draw_count",
        )
        if key in layout_dict
    }
    attempt.answer_key_layout = {
        key: layout_dict[key]
        for key in (
            "answer_fill_count",
            "answer_outline_count",
            "answer_oval_count",
            "answer_line_mark_count",
            "answer_cell_box_segment_count",
            "answer_key_validated",
            "answer_box_top_y",
            "answer_ovals_validated",
        )
        if key in layout_dict
    }

    if oval_errors:
        attempt.build_errors.extend(oval_errors)

    attempt.qa_result = run_layout_attempt_qa(
        puzzle=puzzle,
        layout_info=layout_dict,
        solution_paths=attempt.solution_paths,
        oval_table=attempt.oval_table,
        oval_errors=attempt.oval_errors,
        oval_warnings=attempt.oval_warnings,
        include_answer_key=include_answer_key,
    )
    attempt.passed = attempt.qa_result.passed
    return attempt


def _failure_record(attempt: LayoutAttempt) -> dict:
    errors = list(attempt.build_errors)
    if attempt.qa_result and attempt.qa_result.errors:
        for item in attempt.qa_result.errors:
            if item not in errors:
                errors.append(item)
    return {
        "attempt_number": attempt.attempt_number,
        "grid_size": attempt.grid_size,
        "errors": errors,
    }


def _aggregate_qa_report(
    *,
    attempts: list[LayoutAttempt],
    original_grid_size: int,
    success: LayoutAttempt | None,
) -> WordSearchQAResult:
    attempted_grid_sizes = [item.grid_size for item in attempts]
    failure_reasons = [
        _failure_record(item)
        for item in attempts
        if not item.passed
    ]

    if success is not None and success.qa_result is not None:
        qa = copy.deepcopy(success.qa_result)
        qa.original_grid_size = original_grid_size
        qa.attempted_grid_sizes = attempted_grid_sizes
        qa.total_attempts = len(attempts)
        qa.final_grid_size_used = success.grid_size
        qa.regeneration_attempts = max(0, success.attempt_number - 1)
        qa.failure_reasons = failure_reasons
        qa.warnings.extend(success.oval_warnings)
        qa.oval_qa_passed = True
        qa.blocked_export = False
        qa.passed = True
        return qa

    last_errors = (
        attempts[-1].qa_result.errors
        if attempts and attempts[-1].qa_result and attempts[-1].qa_result.errors
        else attempts[-1].build_errors
        if attempts and attempts[-1].build_errors
        else ["Answer key validation failed."]
    )

    return WordSearchQAResult(
        passed=False,
        errors=list(last_errors),
        blocked_export=True,
        original_grid_size=original_grid_size,
        attempted_grid_sizes=attempted_grid_sizes,
        total_attempts=len(attempts),
        final_grid_size_used=attempts[-1].grid_size if attempts else original_grid_size,
        regeneration_attempts=max(0, len(attempts) - 1),
        failure_reasons=failure_reasons,
        oval_qa_passed=False,
    )


def build_worksheet_layout_attempts(
    request,
) -> tuple[list[LayoutAttempt], list[str], LayoutAttempt | None, WordSearchQAResult]:
    """Build one complete layout attempt at the requested grid size."""
    mode = str(request.mode or "topic").strip().lower()
    if mode in {"custom", "custom_list"}:
        mode = "custom_word_list"

    original_grid_size = int(request.grid_size)
    base_seed = 0 if request.seed is None else int(request.seed)
    all_warnings: list[str] = []

    attempt = build_complete_layout_attempt(
        attempt_number=1,
        grid_size=original_grid_size,
        seed=base_seed,
        mode=mode,
        request=request,
    )
    attempts = [attempt]

    if attempt.passed:
        return attempts, all_warnings, attempt, _aggregate_qa_report(
            attempts=attempts,
            original_grid_size=original_grid_size,
            success=attempt,
        )

    return (
        attempts,
        all_warnings,
        None,
        _aggregate_qa_report(
            attempts=attempts,
            original_grid_size=original_grid_size,
            success=None,
        ),
    )
