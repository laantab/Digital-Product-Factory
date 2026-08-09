"""Deterministic Word Search product QA and export gate — read-only inspector, no AI/API calls."""
from __future__ import annotations

from dataclasses import dataclass, field

from .answer_key_solver import solve_puzzle_answer_key
from .builder import PuzzleResult
from .solution_table import (
    SolutionTable,
    validate_solution_table_for_render,
    validate_oval_coverage_for_table,
)
from .direct_pdf_renderer import calculate_grid_layout
from .engine import DIRECTIONS


@dataclass
class WordSearchQAResult:
    passed: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)
    blocked_export: bool = True
    original_grid_size: int | None = None
    final_grid_size_used: int | None = None
    regeneration_attempts: int = 0
    attempted_grid_sizes: list[int] = field(default_factory=list)
    total_attempts: int = 0
    failure_reasons: list[dict] = field(default_factory=list)
    oval_qa_passed: bool = False

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "fixes_applied": self.fixes_applied,
            "blocked_export": self.blocked_export,
            "original_grid_size": self.original_grid_size,
            "final_grid_size_used": self.final_grid_size_used,
            "regeneration_attempts": self.regeneration_attempts,
            "attempted_grid_sizes": self.attempted_grid_sizes,
            "total_attempts": self.total_attempts,
            "failure_reasons": self.failure_reasons,
            "oval_qa_passed": self.oval_qa_passed,
        }


def _paths_match(left: dict, right: dict) -> bool:
    left_cells = left.get("cells_in_order") or left.get("cells")
    right_cells = right.get("cells_in_order") or right.get("cells")
    return left_cells == right_cells and left.get("direction") == right.get("direction")


# Generic/fallback/unrelated words that should NEVER appear for a non-matching topic.
# Now sourced from topic_intelligence for consistency across all puzzle engines.
# This set is intentionally broad — any puzzle using these words for an
# unrelated topic has failed Level 1+2 and must be blocked.
from services.factory.topic_intelligence import (
    GENERIC_FALLBACK_WORDS as _TI_GENERIC_WORDS,
    has_real_topic_content,
    is_placeholder_phrase,
)

_GENERIC_FALLBACK_WORDS: set[str] = _TI_GENERIC_WORDS


def _is_related_to_topic(word_lower: str, topic_lower: str) -> bool:
    """Return True if word has at least one character overlap with topic tokens."""
    topic_tokens = set(topic_lower.replace("-", " ").split())
    word_tokens = set(word_lower.replace("-", " ").split())
    # Direct token overlap
    if topic_tokens & word_tokens:
        return True
    # Character overlap — at least 4 shared characters
    topic_chars = set(topic_lower.replace(" ", ""))
    word_chars = set(word_lower.replace(" ", ""))
    if len(topic_chars & word_chars) >= 4:
        return True
    return False


def _check_topic_relevance(puzzle: PuzzleResult, result: WordSearchQAResult) -> None:
    """Block export if word list contains generic fallback words for a topic-based puzzle.

    Topic pack matches are verified upstream by the semantic relevance check in
    suggest_words_from_topic, so when a pack was matched we trust those words
    regardless of character overlap with the topic name.

    Level 3 blocking: when no pack matched AND word quality is insufficient,
    block and request custom input from the user.
    """
    if not puzzle.topic or puzzle.mode != "topic":
        return  # Custom word lists are always accepted as-is

    topic_lower = puzzle.topic.lower().strip()
    if not topic_lower:
        return

    # Check warnings for "Used local vocabulary pack" to know a real pack was matched.
    # If a pack matched, we trust the words — the pack-matching logic already verified
    # semantic relevance via keywords + semantic overlap.
    pack_used = any("Used local vocabulary pack" in w for w in puzzle.warnings)

    generic_words: list[str] = []
    for word in puzzle.word_bank:
        word_lower = word.lower().strip()
        if not word_lower:
            continue
        if word_lower in _GENERIC_FALLBACK_WORDS:
            generic_words.append(word)

    if generic_words:
        result.errors.append(
            f"Word list contains generic fallback words {generic_words!r} "
            f"that are unrelated to topic \"{puzzle.topic}\". "
            "This indicates no matching vocabulary pack was found for this topic. "
            "Please enter a custom word list or choose a broader topic."
        )

    # Level 3 blocking: no pack matched + insufficient quality = ask for input
    if not pack_used:
        if generic_words or not has_real_topic_content(puzzle.word_bank, puzzle.topic):
            topic_clean = str(puzzle.topic or "").strip()
            result.errors.append(
                f"I need a little more information to build a quality word search for \"{topic_clean}\". "
                f"No matching vocabulary pack found for this topic and the word list is not "
                f"topic-specific enough. "
                f"Please enter 10–20 specific words or terms related to this topic."
            )


def _check_word_accuracy(puzzle: PuzzleResult, result: WordSearchQAResult) -> None:
    validation = solve_puzzle_answer_key(puzzle)
    if not validation.ok:
        result.errors.extend(validation.errors)
        return

    result.warnings.extend(validation.warnings)

    if len(validation.validated_paths) != len(puzzle.word_bank):
        result.errors.append("Not every word in the word list was validated against its official path.")

    official_by_word = {
        str(path.get("word") or "").lower(): path for path in puzzle.answer_key
    }
    for path in validation.validated_paths:
        word = str(path.get("word") or "").lower()
        expected = official_by_word.get(word)
        if expected is None:
            result.errors.append(f'Validated path for "{path.get("word")}" has no official placement.')
            continue
        if not _paths_match(path, expected):
            result.errors.append(
                f'Validated path for "{path.get("word")}" does not match the official placement.'
            )
            continue
        dr, dc = DIRECTIONS[path["direction"]]
        letters = []
        for row, col in path.get("cells_in_order") or path.get("cells") or []:
            if not (0 <= row < puzzle.grid_size and 0 <= col < puzzle.grid_size):
                result.errors.append(f'Path for "{path.get("word")}" goes outside the grid.')
                break
            letters.append(puzzle.grid[row][col])
        else:
            expected_word = "".join(path["word"].split()).upper()
            if "".join(letters).upper() != expected_word:
                result.errors.append(
                    f'Path letters do not spell "{path.get("word")}" correctly.'
                )

    if puzzle.validated_answer_key:
        if len(puzzle.validated_answer_key) != len(validation.validated_paths):
            result.errors.append("Validated answer paths do not match official placement count.")
        validated_by_word = {item["word"].lower(): item for item in validation.validated_paths}
        for path in puzzle.validated_answer_key:
            word = str(path.get("word") or "").lower()
            expected = validated_by_word.get(word)
            if expected is None:
                result.errors.append(f'Fake or unvalidated answer path for "{path.get("word")}".')
                continue
            if not _paths_match(path, expected):
                result.errors.append(
                    f'Answer path for "{path.get("word")}" does not match the official placement.'
                )


def _check_answer_key_accuracy(
    puzzle: PuzzleResult,
    layout_info: dict,
    *,
    include_answer_key: bool,
    result: WordSearchQAResult,
) -> None:
    if include_answer_key and not puzzle.validated_answer_key:
        result.errors.append("Answer key requested but no validated solution paths are available.")
        return

    if include_answer_key:
        table_errors = validate_solution_table_for_render(
            puzzle.solution_table,
            word_count=len(puzzle.word_bank),
        )
        result.errors.extend(table_errors)

    if layout_info.get("puzzle_page_mark_count", 0) != 0:
        result.errors.append("Puzzle page contains answer marks.")

    if layout_info.get("answer_cell_box_segment_count", 0) != 0:
        result.errors.append("Answer key uses individual letter boxes instead of ovals.")

    if layout_info.get("answer_fill_count", 0) != 0:
        result.errors.append("Answer key uses shaded cell fills.")

    if layout_info.get("answer_line_mark_count", 0) != 0:
        result.errors.append("Answer key uses line-segment marks instead of ovals.")

    if include_answer_key:
        expected_marks = len(puzzle.validated_answer_key)
        if layout_info.get("answer_key_validated") is not True:
            result.errors.append("Answer ovals were not drawn from the solution table.")
        oval_count = layout_info.get("answer_oval_count", layout_info.get("answer_smooth_mark_count", 0))
        if oval_count != expected_marks:
            result.errors.append(
                "Answer key page is missing ovals for one or more validated words."
            )
        if layout_info.get("answer_outline_count", 0) != expected_marks:
            result.errors.append("Answer oval count does not match validated word count.")
        if layout_info.get("answer_ovals_validated") is not True:
            result.errors.append("Answer ovals were not validated before export.")
        cell_size = float(layout_info.get("cell_size_pt") or 0)
        box_top_y = float(layout_info.get("answer_box_top_y") or 0)
        if (
            layout_info.get("answer_ovals_validated") is True
            and cell_size > 0
            and box_top_y > 0
            and puzzle.solution_table
            and puzzle.solution_table.entries
        ):
            from reportlab.lib.pagesizes import letter

            page_w, _page_h = letter
            grid = calculate_grid_layout(
                page_w=page_w,
                box_top_y=box_top_y,
                grid_size=puzzle.grid_size,
                cell_size=cell_size,
            )
            result.errors.extend(
                validate_oval_coverage_for_table(
                    puzzle.solution_table,
                    grid,
                    puzzle.grid,
                )
            )
    elif layout_info.get("answer_oval_count", layout_info.get("answer_smooth_mark_count", 0)) != 0:
        result.errors.append("Answer ovals were drawn but answer key was not requested.")


def _check_layout_quality(
    puzzle: PuzzleResult,
    layout_info: dict,
    *,
    include_answer_key: bool,
    pdf_bytes: bytes,
    result: WordSearchQAResult,
    require_pdf: bool = True,
) -> None:
    if not layout_info:
        result.errors.append("Layout information is missing.")
        return

    if require_pdf and (not pdf_bytes or not pdf_bytes.startswith(b"%PDF")):
        result.errors.append("PDF output is missing or invalid.")

    expected_pages = 2 if include_answer_key else 1
    if layout_info.get("page_count") != expected_pages:
        result.errors.append(
            f"Expected {expected_pages} page(s) but layout reports {layout_info.get('page_count')}."
        )

    if include_answer_key and layout_info.get("page_count") != 2:
        result.errors.append("Answer key must start on page 2.")

    if not include_answer_key and layout_info.get("page_count") != 1:
        result.errors.append("Puzzle worksheet must fit on a single page.")

    if layout_info.get("puzzle_fits_one_page") is False:
        result.errors.append("Puzzle content does not fit properly on page 1.")

    if layout_info.get("grid_centered") is False:
        result.errors.append("Puzzle grid is not centered on the page.")

    if layout_info.get("cell_border_count", 0) != 0:
        result.errors.append("Puzzle uses individual letter boxes in the grid.")

    outer_boxes = layout_info.get("outer_box_count", 0)
    if outer_boxes < expected_pages:
        result.errors.append("Outer puzzle border is incomplete.")

    if layout_info.get("word_list_columns") != 3:
        result.errors.append("Word list is not separated into readable columns.")

    drawn = layout_info.get("word_list_draw_count")
    if drawn is not None and drawn != len(puzzle.word_bank):
        result.errors.append("Word list entries are missing or concatenated on the page.")

    for word in puzzle.word_bank:
        cleaned = word.strip()
        if not cleaned:
            result.errors.append("Word list contains an empty entry.")
        if len(cleaned.replace(" ", "")) >= 18 and " " not in cleaned:
            result.errors.append(
                f'Word list entry "{word}" looks concatenated; words must be listed separately.'
            )


def _check_words_per_worksheet(
    puzzle: PuzzleResult,
    *,
    expected_words: int | None,
    puzzle_index: int,
    puzzle_count: int,
    result: WordSearchQAResult,
) -> None:
    """Product quality check: each worksheet should contain the requested word count."""
    if not expected_words or expected_words <= 0:
        return

    actual = len(puzzle.word_bank)
    if actual >= expected_words:
        return

    label = puzzle.puzzle_title or f"Puzzle {puzzle_index}"
    if puzzle_count == 1:
        result.errors.append(
            f'Worksheet "{label}" has {actual} word(s) but {expected_words} were requested.'
        )
        return

    is_last = puzzle_index == puzzle_count
    if is_last and actual > 0:
        result.warnings.append(
            f'Worksheet {puzzle_index} ("{label}") has {actual} word(s); '
            f"expected {expected_words} (short word list for the final worksheet)."
        )
        return

    result.errors.append(
        f'Worksheet {puzzle_index} ("{label}") has {actual} word(s) but '
        f"{expected_words} were requested."
    )


def _check_puzzle_count(
    *,
    puzzles: list[PuzzleResult],
    expected_puzzle_count: int,
    result: WordSearchQAResult,
) -> None:
    """Product quality check: book should contain the requested number of worksheets."""
    expected = max(1, int(expected_puzzle_count or 1))
    actual = len(puzzles)
    if actual != expected:
        result.errors.append(
            f"Expected {expected} worksheet(s) but generated {actual}."
        )


def run_book_product_quality_qa(
    *,
    puzzles: list[PuzzleResult],
    expected_puzzle_count: int,
    words_per_puzzle: int | None,
    include_answer_key: bool = True,
    pdf_bytes: bytes = b"",
) -> WordSearchQAResult:
    """Validate an entire word search book before export."""
    result = WordSearchQAResult()
    _check_puzzle_count(
        puzzles=puzzles,
        expected_puzzle_count=expected_puzzle_count,
        result=result,
    )

    per_puzzle = int(words_per_puzzle or 0) or None
    puzzle_count = max(1, int(expected_puzzle_count or len(puzzles) or 1))
    for index, puzzle in enumerate(puzzles, start=1):
        if puzzle.errors:
            result.errors.extend(puzzle.errors)
        _check_words_per_worksheet(
            puzzle,
            expected_words=per_puzzle,
            puzzle_index=index,
            puzzle_count=puzzle_count,
            result=result,
        )
        _check_topic_relevance(puzzle, result)
        _check_word_accuracy(puzzle, result)

    if pdf_bytes and not pdf_bytes.startswith(b"%PDF"):
        result.errors.append("PDF output is missing or invalid.")

    result.passed = not result.errors
    result.blocked_export = not result.passed
    return result


def run_word_search_qa(
    *,
    puzzle: PuzzleResult,
    layout_info: dict | None = None,
    include_answer_key: bool = True,
    pdf_bytes: bytes = b"",
    words_per_puzzle: int | None = None,
) -> WordSearchQAResult:
    """Inspect a generated word search and decide whether export is allowed.

    Read-only inspector: never modifies the puzzle, paths, layout, renderer output,
    or solution-table geometry. Does not redraw ovals or regenerate puzzles.
    """
    result = WordSearchQAResult()

    if puzzle.errors:
        result.errors.extend(puzzle.errors)

    _check_words_per_worksheet(
        puzzle,
        expected_words=words_per_puzzle,
        puzzle_index=1,
        puzzle_count=1,
        result=result,
    )
    _check_topic_relevance(puzzle, result)
    _check_word_accuracy(puzzle, result)

    if layout_info is not None:
        _check_answer_key_accuracy(puzzle, layout_info, include_answer_key=include_answer_key, result=result)
        _check_layout_quality(
            puzzle,
            layout_info,
            include_answer_key=include_answer_key,
            pdf_bytes=pdf_bytes,
            result=result,
        )
    elif pdf_bytes and not pdf_bytes.startswith(b"%PDF"):
        result.errors.append("PDF output is missing or invalid.")

    result.passed = not result.errors
    result.blocked_export = not result.passed
    return result


def run_layout_attempt_qa(
    *,
    puzzle: PuzzleResult,
    layout_info: dict,
    solution_paths: list[dict],
    oval_table: SolutionTable | None,
    oval_errors: list[str],
    oval_warnings: list[str] | None = None,
    include_answer_key: bool = True,
) -> WordSearchQAResult:
    """Run QA against one complete layout attempt without requiring PDF bytes."""
    result = WordSearchQAResult()
    proximity_warnings = list(oval_warnings or [])

    if puzzle.errors:
        result.errors.extend(puzzle.errors)

    if include_answer_key and not solution_paths:
        result.errors.append("Answer key requested but no validated solution paths are available.")
    if include_answer_key and oval_table is None:
        result.errors.append("Answer key requested but oval table was not built.")

    _check_topic_relevance(puzzle, result)
    _check_word_accuracy(puzzle, result)

    if layout_info and layout_info.get("puzzle_fits_one_page") is False:
        result.errors.append("Puzzle content does not fit properly on page 1.")
    if layout_info and layout_info.get("grid_centered") is False:
        result.errors.append("Puzzle grid is not centered on the page.")

    if oval_errors:
        result.errors.extend(oval_errors)
    else:
        if layout_info:
            _check_answer_key_accuracy(
                puzzle,
                layout_info,
                include_answer_key=include_answer_key,
                result=result,
            )
            _check_layout_quality(
                puzzle,
                layout_info,
                include_answer_key=include_answer_key,
                pdf_bytes=b"",
                result=result,
                require_pdf=False,
            )

    result.warnings.extend(proximity_warnings)
    result.passed = not result.errors
    result.blocked_export = not result.passed
    result.oval_qa_passed = result.passed and include_answer_key and not oval_errors
    return result
