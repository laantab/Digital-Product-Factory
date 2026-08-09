"""Crossword grid generation — separate from Word Search engine."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from services.crossword.clues import simple_clue


@dataclass
class CrosswordClueEntry:
    number: int
    direction: str
    answer: str
    clue: str
    row: int
    col: int

    def as_dict(self) -> dict:
        return {
            "number": self.number,
            "direction": self.direction,
            "answer": self.answer,
            "clue": self.clue,
            "row": self.row,
            "col": self.col,
        }


@dataclass
class CrosswordBuildResult:
    grid: list[list[str | None]]
    clues: list[CrosswordClueEntry]
    placed_words: list[str]
    rejected_words: list[str]
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def normalize_grid_size(value: int | str, *, default: int = 15) -> int:
    try:
        size = int(value)
    except (TypeError, ValueError):
        size = default
    return max(11, min(size, 21))


def _blank_grid(size: int) -> list[list[str | None]]:
    return [[None for _ in range(size)] for _ in range(size)]


def _can_place(grid: list[list[str | None]], word: str, row: int, col: int, dr: int, dc: int) -> bool:
    size = len(grid)
    before_r, before_c = row - dr, col - dc
    if 0 <= before_r < size and 0 <= before_c < size and grid[before_r][before_c] is not None:
        return False
    after_r, after_c = row + dr * len(word), col + dc * len(word)
    if 0 <= after_r < size and 0 <= after_c < size and grid[after_r][after_c] is not None:
        return False

    for i, letter in enumerate(word):
        r, c = row + dr * i, col + dc * i
        if not (0 <= r < size and 0 <= c < size):
            return False
        cell = grid[r][c]
        if cell is not None and cell != letter:
            return False
        if cell is None:
            if dr == 0:
                if (r > 0 and grid[r - 1][c] is not None) or (r + 1 < size and grid[r + 1][c] is not None):
                    if i == 0 or i == len(word) - 1:
                        pass
                    else:
                        return False
            else:
                if (c > 0 and grid[r][c - 1] is not None) or (c + 1 < size and grid[r][c + 1] is not None):
                    if i == 0 or i == len(word) - 1:
                        pass
                    else:
                        return False
    return True


def _place_word(grid: list[list[str | None]], word: str, row: int, col: int, dr: int, dc: int) -> None:
    for i, letter in enumerate(word):
        grid[row + dr * i][col + dc * i] = letter


def _assign_numbers(clues: list[CrosswordClueEntry]) -> None:
    positions: dict[tuple[int, int], int] = {}
    next_num = 1
    for entry in sorted(clues, key=lambda c: (c.row, c.col, c.direction)):
        key = (entry.row, entry.col)
        if key not in positions:
            positions[key] = next_num
            next_num += 1
        entry.number = positions[key]


def _build_crossword_single_attempt(
    unique: list[str],
    clues_map: dict[str, str],
    size: int,
    rng: random.Random,
) -> CrosswordBuildResult:
    """Single-attempt grid building (no recursive retry). Used by build_crossword_grid."""
    grid = _blank_grid(size)
    clue_entries: list[CrosswordClueEntry] = []
    placed: list[str] = []
    rejected: list[str] = []
    order = list(unique)
    rng.shuffle(order)

    first = order[0]
    start_row = size // 2
    start_col = max(0, (size - len(first)) // 2)
    _place_word(grid, first, start_row, start_col, 0, 1)
    clue_entries.append(
        CrosswordClueEntry(
            number=1,
            direction="across",
            answer=first,
            clue=clues_map.get(first) or simple_clue(first, theme=""),
            row=start_row,
            col=start_col,
        )
    )
    placed.append(first)

    for word in order[1:]:
        placed_ok = False
        candidates: list[tuple[int, int, str, int, int]] = []
        for existing in clue_entries:
            for idx, letter in enumerate(existing.answer):
                for pos in range(len(word)):
                    if word[pos] != letter:
                        continue
                    if existing.direction == "across":
                        row = existing.row - pos
                        col = existing.col + idx
                        direction = "down"
                        dr, dc = 1, 0
                    else:
                        row = existing.row + idx
                        col = existing.col - pos
                        direction = "across"
                        dr, dc = 0, 1
                    candidates.append((row, col, direction, dr, dc))

        rng.shuffle(candidates)
        for row, col, direction, dr, dc in candidates:
            if _can_place(grid, word, row, col, dr, dc):
                _place_word(grid, word, row, col, dr, dc)
                clue_entries.append(
                    CrosswordClueEntry(
                        number=0,
                        direction=direction,
                        answer=word,
                        clue=clues_map.get(word) or simple_clue(word, theme=""),
                        row=row,
                        col=col,
                    )
                )
                placed.append(word)
                placed_ok = True
                break
        if not placed_ok:
            rejected.append(word)

    _assign_numbers(clue_entries)
    return CrosswordBuildResult(
        grid=grid,
        clues=clue_entries,
        placed_words=placed,
        rejected_words=rejected,
        warnings=[],
    )


def build_crossword_grid(
    words: list[str],
    clues_map: dict[str, str],
    *,
    grid_size: int | str = 15,
    seed: int | None = None,
) -> CrosswordBuildResult:
    """Place words into a crossword grid with across/down clues."""
    size = normalize_grid_size(grid_size)
    rng = random.Random(seed)
    unique: list[str] = []
    seen: set[str] = set()
    for raw in words:
        word = str(raw or "").strip().upper().replace(" ", "")
        if not word or not word.isalpha() or word in seen:
            continue
        if len(word) > size:
            continue
        seen.add(word)
        unique.append(word)

    unique.sort(key=len, reverse=True)
    if not unique:
        return CrosswordBuildResult(
            grid=_blank_grid(size),
            clues=[],
            placed_words=[],
            rejected_words=list(words),
            errors=["No valid crossword words to place."],
        )

    best: CrosswordBuildResult | None = None
    attempts = min(48, max(12, len(unique) * 4))

    for _ in range(attempts):
        grid = _blank_grid(size)
        clue_entries: list[CrosswordClueEntry] = []
        placed: list[str] = []
        rejected: list[str] = []
        order = list(unique)
        rng.shuffle(order)

        first = order[0]
        start_row = size // 2
        start_col = max(0, (size - len(first)) // 2)
        _place_word(grid, first, start_row, start_col, 0, 1)
        clue_entries.append(
            CrosswordClueEntry(
                number=1,
                direction="across",
                answer=first,
                clue=clues_map.get(first) or simple_clue(first, theme=""),
                row=start_row,
                col=start_col,
            )
        )
        placed.append(first)

        for word in order[1:]:
            placed_ok = False
            candidates: list[tuple[int, int, str, int, int]] = []
            for existing in clue_entries:
                for idx, letter in enumerate(existing.answer):
                    for pos in range(len(word)):
                        if word[pos] != letter:
                            continue
                        if existing.direction == "across":
                            row = existing.row - pos
                            col = existing.col + idx
                            direction = "down"
                            dr, dc = 1, 0
                        else:
                            row = existing.row + idx
                            col = existing.col - pos
                            direction = "across"
                            dr, dc = 0, 1
                        candidates.append((row, col, direction, dr, dc))

            rng.shuffle(candidates)
            for row, col, direction, dr, dc in candidates:
                if _can_place(grid, word, row, col, dr, dc):
                    _place_word(grid, word, row, col, dr, dc)
                    clue_entries.append(
                        CrosswordClueEntry(
                            number=0,
                            direction=direction,
                            answer=word,
                            clue=clues_map.get(word) or simple_clue(word, theme=""),
                            row=row,
                            col=col,
                        )
                    )
                    placed.append(word)
                    placed_ok = True
                    break
            if not placed_ok:
                rejected.append(word)

        _assign_numbers(clue_entries)
        result = CrosswordBuildResult(
            grid=grid,
            clues=clue_entries,
            placed_words=placed,
            rejected_words=rejected,
            warnings=[],
        )
        if best is None or len(placed) > len(best.placed_words):
            best = result
        if len(placed) == len(unique):
            break

    assert best is not None

    # If fewer than 4 words placed, try larger grid sizes iteratively (not recursively)
    # to avoid hitting Python's recursion limit when many attempts all fail.
    if len(best.placed_words) < 4:
        for larger_size in [min(size + 4, 21), min(size + 8, 21)]:
            larger = _build_crossword_single_attempt(unique, clues_map, larger_size, rng)
            if len(larger.placed_words) >= 4:
                best = larger
                break
            if len(larger.placed_words) > len(best.placed_words):
                best = larger

    if len(best.placed_words) < max(3, min(5, len(unique))):
        best.errors.append(
            f"Could only place {len(best.placed_words)} of {len(unique)} words. Try fewer or shorter answers."
        )
    if best.rejected_words:
        best.warnings.append(
            f"Could not place {len(best.rejected_words)} word(s): {', '.join(best.rejected_words[:6])}."
        )
    return best
