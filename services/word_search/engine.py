"""Deterministic word search grid generation and placement."""
from __future__ import annotations

import random
import string
from dataclasses import dataclass, field
from typing import Iterable

from .word_lists import WordEntry

Direction = tuple[int, int]

DIRECTIONS: dict[str, Direction] = {
    "E": (0, 1),
    "S": (1, 0),
    "SE": (1, 1),
    "NE": (-1, 1),
    "W": (0, -1),
    "N": (-1, 0),
    "SW": (1, -1),
    "NW": (-1, -1),
}


@dataclass
class AnswerPlacement:
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
class GridBuildResult:
    grid: list[list[str]]
    placements: list[AnswerPlacement]
    placed_words: list[str]
    rejected_words: list[str]
    warnings: list[str]
    errors: list[str]


def normalize_difficulty(value: str) -> str:
    lowered = str(value or "medium").strip().lower()
    if lowered in {"easy", "medium", "hard"}:
        return lowered
    return "medium"


def normalize_grid_size(value: int | str) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = 15
    return max(8, min(size, 25))


def allowed_directions(difficulty: str) -> list[tuple[str, Direction]]:
    diff = normalize_difficulty(difficulty)
    if diff == "easy":
        keys = ("E", "S")
    elif diff == "medium":
        keys = ("E", "S", "SE", "NE")
    else:
        keys = tuple(DIRECTIONS.keys())
    return [(name, DIRECTIONS[name]) for name in keys]


def _in_bounds(size: int, row: int, col: int) -> bool:
    return 0 <= row < size and 0 <= col < size


def _cells_for_word(row: int, col: int, dr: int, dc: int, length: int) -> list[tuple[int, int]]:
    return [(row + dr * i, col + dc * i) for i in range(length)]


def _can_place(grid: list[list[str]], cells: Iterable[tuple[int, int]], word: str) -> bool:
    for (row, col), letter in zip(cells, word):
        current = grid[row][col]
        if current != " " and current != letter:
            return False
    return True


def _place_word(grid: list[list[str]], cells: Iterable[tuple[int, int]], word: str) -> None:
    for (row, col), letter in zip(cells, word):
        grid[row][col] = letter


def _fill_empty_cells(grid: list[list[str]], rng: random.Random) -> None:
    for row_idx, row in enumerate(grid):
        for col_idx, letter in enumerate(row):
            if letter == " ":
                row[col_idx] = rng.choice(string.ascii_uppercase)


def _try_reduce_short_word_duplicates(
    grid: list[list[str]],
    placements: list[AnswerPlacement],
    *,
    grid_size: int,
    difficulty: str,
    rng: random.Random,
) -> list[str]:
    """Best-effort filler tweak so short placed words do not gain accidental duplicates."""
    from .answer_key_solver import find_word_paths_in_grid

    warnings: list[str] = []
    for placement in placements:
        if len(placement.grid_word) > 4:
            continue

        official_cells = {(row, col) for row, col in placement.cells}
        matches = find_word_paths_in_grid(
            grid,
            grid_size=grid_size,
            display_word=placement.word,
            difficulty=difficulty,
        )
        if len(matches) <= 1:
            continue

        for match in matches:
            match_cells = {(row, col) for row, col in match.cells}
            if match_cells == official_cells:
                continue

            fixed = False
            for row, col in match.cells:
                if (row, col) in official_cells:
                    continue
                original = grid[row][col]
                candidates = list(string.ascii_uppercase)
                rng.shuffle(candidates)
                for replacement in candidates:
                    if replacement == original:
                        continue
                    grid[row][col] = replacement
                    remaining = find_word_paths_in_grid(
                        grid,
                        grid_size=grid_size,
                        display_word=placement.word,
                        difficulty=difficulty,
                    )
                    if len(remaining) <= 1:
                        fixed = True
                        break
                    grid[row][col] = original
                if fixed:
                    break
            if not fixed:
                warnings.append(
                    f'Could not remove every accidental duplicate for short word "{placement.word}".'
                )
            break

    return warnings


def build_grid(
    entries: list[WordEntry],
    *,
    grid_size: int,
    difficulty: str,
    seed: int | None = None,
) -> GridBuildResult:
    """Place words on a grid using backtracking; longest words first."""
    size = normalize_grid_size(grid_size)
    rng = random.Random(seed)
    grid: list[list[str]] = [[" " for _ in range(size)] for _ in range(size)]

    warnings: list[str] = []
    errors: list[str] = []
    placements: list[AnswerPlacement] = []
    placed_words: list[str] = []
    rejected_words: list[str] = []

    ordered = sorted(entries, key=lambda item: len(item.grid), reverse=True)
    dirs = allowed_directions(difficulty)

    for entry in ordered:
        word = entry.grid
        placed = False
        attempts: list[tuple[int, int, str, Direction]] = []
        for name, (dr, dc) in dirs:
            for row in range(size):
                for col in range(size):
                    end_row = row + dr * (len(word) - 1)
                    end_col = col + dc * (len(word) - 1)
                    if not _in_bounds(size, end_row, end_col):
                        continue
                    cells = _cells_for_word(row, col, dr, dc, len(word))
                    if _can_place(grid, cells, word):
                        attempts.append((row, col, name, (dr, dc)))

        rng.shuffle(attempts)
        for row, col, direction_name, (dr, dc) in attempts:
            cells = _cells_for_word(row, col, dr, dc, len(word))
            if _can_place(grid, cells, word):
                _place_word(grid, cells, word)
                end_row = row + dr * (len(word) - 1)
                end_col = col + dc * (len(word) - 1)
                placements.append(
                    AnswerPlacement(
                        word=entry.display,
                        grid_word=word,
                        direction=direction_name,
                        start_row=row,
                        start_col=col,
                        end_row=end_row,
                        end_col=end_col,
                        cells=[[r, c] for r, c in cells],
                    )
                )
                placed_words.append(entry.display)
                placed = True
                break

        if not placed:
            rejected_words.append(entry.display)
            warnings.append(f'Could not place "{entry.display}" on the grid. Try a larger grid or fewer words.')

    if not placed_words:
        errors.append("No words could be placed on the grid.")

    _fill_empty_cells(grid, rng)
    duplicate_warnings = _try_reduce_short_word_duplicates(
        grid,
        placements,
        grid_size=size,
        difficulty=normalize_difficulty(difficulty),
        rng=rng,
    )
    warnings.extend(duplicate_warnings)

    return GridBuildResult(
        grid=grid,
        placements=placements,
        placed_words=placed_words,
        rejected_words=rejected_words,
        warnings=warnings,
        errors=errors,
    )
