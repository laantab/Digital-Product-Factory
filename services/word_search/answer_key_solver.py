"""Deterministic Word Search answer validation — official placements are the source of truth."""
from __future__ import annotations

from dataclasses import dataclass, field

from .builder import PuzzleResult
from .engine import DIRECTIONS, allowed_directions


def _normalize_word(value: str) -> str:
    return "".join(str(value or "").split()).upper()


@dataclass
class SolvedPath:
    word: str
    grid_word: str
    direction: str
    start_row: int
    start_col: int
    end_row: int
    end_col: int
    cells: list[list[int]] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "word": self.word,
            "grid_word": self.grid_word,
            "normalized_word": self.grid_word,
            "direction": self.direction,
            "start_row": self.start_row,
            "start_col": self.start_col,
            "end_row": self.end_row,
            "end_col": self.end_col,
            "cells": self.cells,
            "cells_in_order": self.cells,
        }


@dataclass
class AnswerKeyValidationResult:
    validated_paths: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _letters_at_path(
    grid: list[list[str]],
    *,
    start_row: int,
    start_col: int,
    dr: int,
    dc: int,
    length: int,
    grid_size: int,
) -> str | None:
    letters: list[str] = []
    for index in range(length):
        row = start_row + dr * index
        col = start_col + dc * index
        if not (0 <= row < grid_size and 0 <= col < grid_size):
            return None
        letters.append(grid[row][col])
    return "".join(letters).upper()


def _path_cells(
    *,
    start_row: int,
    start_col: int,
    dr: int,
    dc: int,
    length: int,
) -> list[list[int]]:
    return [
        [start_row + dr * index, start_col + dc * index]
        for index in range(length)
    ]


def _cell_set(path: dict) -> set[tuple[int, int]]:
    cells = path.get("cells_in_order") or path.get("cells") or []
    return {(int(row), int(col)) for row, col in cells}


def _official_paths_by_word(puzzle: PuzzleResult) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    for path in puzzle.answer_key:
        word = str(path.get("word") or "").strip()
        if word:
            mapping[word.lower()] = path
    return mapping


def _validate_official_path_spells_word(
    grid: list[list[str]],
    *,
    grid_size: int,
    path: dict,
    display_word: str,
) -> str | None:
    cells = path.get("cells_in_order") or path.get("cells") or []
    if not cells:
        return f'Official path for "{display_word}" is missing cell coordinates.'

    letters: list[str] = []
    for row, col in cells:
        row_i = int(row)
        col_i = int(col)
        if not (0 <= row_i < grid_size and 0 <= col_i < grid_size):
            return f'Official path for "{display_word}" goes outside the grid.'
        letters.append(grid[row_i][col_i])

    expected = _normalize_word(display_word)
    actual = "".join(letters).upper()
    if actual != expected:
        return f'Official path letters "{actual}" do not spell "{display_word}".'

    direction = str(path.get("direction") or "")
    if direction in DIRECTIONS:
        dr, dc = DIRECTIONS[direction]
        start_row = int(path.get("start_row", cells[0][0]))
        start_col = int(path.get("start_col", cells[0][1]))
        via_direction = _letters_at_path(
            grid,
            start_row=start_row,
            start_col=start_col,
            dr=dr,
            dc=dc,
            length=len(expected),
            grid_size=grid_size,
        )
        if via_direction != expected:
            return f'Official path for "{display_word}" does not match its declared direction.'

    return None


def find_word_paths_in_grid(
    grid: list[list[str]],
    *,
    grid_size: int,
    display_word: str,
    difficulty: str,
) -> list[SolvedPath]:
    """Search the grid for every exact location of display_word."""
    grid_word = _normalize_word(display_word)
    if not grid_word:
        return []

    matches: list[SolvedPath] = []
    for direction_name, (dr, dc) in allowed_directions(difficulty):
        length = len(grid_word)
        for row in range(grid_size):
            for col in range(grid_size):
                end_row = row + dr * (length - 1)
                end_col = col + dc * (length - 1)
                if not (0 <= end_row < grid_size and 0 <= end_col < grid_size):
                    continue
                found = _letters_at_path(
                    grid,
                    start_row=row,
                    start_col=col,
                    dr=dr,
                    dc=dc,
                    length=length,
                    grid_size=grid_size,
                )
                if found != grid_word:
                    continue
                matches.append(
                    SolvedPath(
                        word=display_word,
                        grid_word=grid_word,
                        direction=direction_name,
                        start_row=row,
                        start_col=col,
                        end_row=end_row,
                        end_col=end_col,
                        cells=_path_cells(
                            start_row=row,
                            start_col=col,
                            dr=dr,
                            dc=dc,
                            length=length,
                        ),
                    )
                )
    return matches


def _count_extra_matches(
    grid: list[list[str]],
    *,
    grid_size: int,
    display_word: str,
    difficulty: str,
    official_path: dict,
) -> int:
    official_cells = _cell_set(official_path)
    matches = find_word_paths_in_grid(
        grid,
        grid_size=grid_size,
        display_word=display_word,
        difficulty=difficulty,
    )
    extra = 0
    for match in matches:
        if {(row, col) for row, col in match.cells} != official_cells:
            extra += 1
    return extra


def _normalize_validated_path(path: dict) -> dict:
    normalized = dict(path)
    grid_word = _normalize_word(str(path.get("grid_word") or path.get("normalized_word") or path.get("word") or ""))
    cells = list(path.get("cells_in_order") or path.get("cells") or [])
    normalized["grid_word"] = grid_word
    normalized["normalized_word"] = grid_word
    normalized["cells"] = cells
    normalized["cells_in_order"] = cells
    return normalized


def solve_puzzle_answer_key(puzzle: PuzzleResult) -> AnswerKeyValidationResult:
    """Validate official placement paths and confirm they spell each word in the grid."""
    result = AnswerKeyValidationResult()
    grid = puzzle.grid
    grid_size = puzzle.grid_size

    if not grid or grid_size <= 0:
        result.errors.append("Puzzle grid is missing.")
        return result

    if not puzzle.word_bank:
        result.errors.append("Word list is empty.")
        return result

    if not puzzle.answer_key:
        result.errors.append("Official placement paths are missing.")
        return result

    official_by_word = _official_paths_by_word(puzzle)
    validated: list[dict] = []

    for word in puzzle.word_bank:
        official = official_by_word.get(word.lower())
        if official is None:
            result.errors.append(f'Word "{word}" was never placed on the grid.')
            continue

        path_error = _validate_official_path_spells_word(
            grid,
            grid_size=grid_size,
            path=official,
            display_word=word,
        )
        if path_error:
            result.errors.append(path_error)
            continue

        extra_matches = _count_extra_matches(
            grid,
            grid_size=grid_size,
            display_word=word,
            difficulty=puzzle.difficulty,
            official_path=official,
        )
        if extra_matches > 0:
            result.warnings.append(
                f'Word "{word}" has extra accidental matches in the filler grid.'
            )

        validated.append(_normalize_validated_path(official))

    if result.errors:
        result.validated_paths = []
        return result

    if len(validated) != len(puzzle.word_bank):
        result.errors.append("Not every word in the word list has an official placement path.")
        result.validated_paths = []
        return result

    result.validated_paths = validated
    return result
