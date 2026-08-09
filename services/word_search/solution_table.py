"""Source-of-truth solution table for Word Search answer-key ovals — no API calls."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .direct_pdf_renderer import GridLayout

_OVAL_GRID_ESCALATION = (17, 19, 21, 23)


def oval_retry_grid_sizes(selected_grid: int) -> list[int]:
    """Grid sizes to try when answer ovals cannot fit on the selected size."""
    selected = int(selected_grid)
    sizes: list[int] = [selected]
    for size in _OVAL_GRID_ESCALATION:
        if size not in sizes:
            sizes.append(size)
    return sizes

_OVAL_END_PAD_RATIO = 0.85
_OVAL_SIDE_PAD_RATIO = 0.45
_ELLIPSE_SLACK = 0.015
_OVAL_COLLISION_GAP_PT = 2.5
_STROKE_TOLERANCE_PT = 1.5


def _normalize_word(value: str) -> str:
    return "".join(str(value or "").split()).upper()


def _parse_cells(raw: object) -> list[tuple[int, int]]:
    cells: list[tuple[int, int]] = []
    if not isinstance(raw, list):
        return cells
    for cell in raw:
        if isinstance(cell, (list, tuple)) and len(cell) == 2:
            cells.append((int(cell[0]), int(cell[1])))
    return cells


def _direction_from_cells(cells: list[tuple[int, int]]) -> str:
    if len(cells) < 2:
        return "horizontal"
    r0, c0 = cells[0]
    r1, c1 = cells[-1]
    if r0 == r1:
        return "horizontal"
    if c0 == c1:
        return "vertical"
    return "diagonal"


def _letter_centers(entry: WordSolutionEntry, grid: GridLayout) -> tuple[tuple[float, float], tuple[float, float]]:
    start = grid.letter_center(entry.cells[0][0], entry.cells[0][1])
    end = grid.letter_center(entry.cells[-1][0], entry.cells[-1][1])
    return start, end


def _to_ellipse_local(px: float, py: float, entry: WordSolutionEntry) -> tuple[float, float]:
    rad = math.radians(entry.rotation_degrees)
    cos_r, sin_r = math.cos(rad), math.sin(rad)
    dx = px - entry.center_x
    dy = py - entry.center_y
    lx = dx * cos_r + dy * sin_r
    ly = -dx * sin_r + dy * cos_r
    return lx, ly


def _point_in_rotated_ellipse(
    px: float,
    py: float,
    entry: WordSolutionEntry,
    *,
    scale: float = 1.0,
    slack: float = _ELLIPSE_SLACK,
) -> bool:
    half_w = (entry.oval_width / 2.0) * scale
    half_h = (entry.oval_height / 2.0) * scale
    if half_w <= 0 or half_h <= 0:
        return False
    lx, ly = _to_ellipse_local(px, py, entry)
    limit = 1.0 + slack
    return (lx / half_w) ** 2 + (ly / half_h) ** 2 <= limit * limit


def _ellipse_boundary_points(entry: WordSolutionEntry, samples: int = 40) -> list[tuple[float, float]]:
    half_w = entry.oval_width / 2.0
    half_h = entry.oval_height / 2.0
    rad = math.radians(entry.rotation_degrees)
    cos_r, sin_r = math.cos(rad), math.sin(rad)
    points: list[tuple[float, float]] = []
    for index in range(samples):
        theta = 2.0 * math.pi * index / samples
        lx = half_w * math.cos(theta)
        ly = half_h * math.sin(theta)
        x = entry.center_x + lx * cos_r - ly * sin_r
        y = entry.center_y + lx * sin_r + ly * cos_r
        points.append((x, y))
    return points


def _path_spells_word(entry: WordSolutionEntry, grid_letters: list[list[str]]) -> bool:
    letters: list[str] = []
    for row, col in entry.cells:
        if not (0 <= row < len(grid_letters) and 0 <= col < len(grid_letters[row])):
            return False
        letters.append(grid_letters[row][col])
    return "".join(letters).upper() == entry.word_normalized


def _all_answer_cells(table: SolutionTable) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for entry in table.entries:
        cells.update(entry.cells)
    return cells


def _ellipses_overlap(left: WordSolutionEntry, right: WordSolutionEntry, *, gap: float) -> bool:
    expanded_right = WordSolutionEntry(
        word_display=right.word_display,
        word_normalized=right.word_normalized,
        cells=list(right.cells),
        start_row=right.start_row,
        start_col=right.start_col,
        end_row=right.end_row,
        end_col=right.end_col,
        direction=right.direction,
        min_row=right.min_row,
        max_row=right.max_row,
        min_col=right.min_col,
        max_col=right.max_col,
        center_x=right.center_x,
        center_y=right.center_y,
        oval_width=right.oval_width + gap,
        oval_height=right.oval_height + gap,
        rotation_degrees=right.rotation_degrees,
    )
    expanded_left = WordSolutionEntry(
        word_display=left.word_display,
        word_normalized=left.word_normalized,
        cells=list(left.cells),
        start_row=left.start_row,
        start_col=left.start_col,
        end_row=left.end_row,
        end_col=left.end_col,
        direction=left.direction,
        min_row=left.min_row,
        max_row=left.max_row,
        min_col=left.min_col,
        max_col=left.max_col,
        center_x=left.center_x,
        center_y=left.center_y,
        oval_width=left.oval_width + gap,
        oval_height=left.oval_height + gap,
        rotation_degrees=left.rotation_degrees,
    )
    for x, y in _ellipse_boundary_points(left):
        if _point_in_rotated_ellipse(x, y, expanded_right, slack=0.0):
            return True
    for x, y in _ellipse_boundary_points(right):
        if _point_in_rotated_ellipse(x, y, expanded_left, slack=0.0):
            return True
    if _point_in_rotated_ellipse(left.center_x, left.center_y, expanded_right, slack=0.0):
        return True
    if _point_in_rotated_ellipse(right.center_x, right.center_y, expanded_left, slack=0.0):
        return True
    return False


@dataclass
class WordSolutionEntry:
    word_display: str
    word_normalized: str
    cells: list[tuple[int, int]]
    start_row: int
    start_col: int
    end_row: int
    end_col: int
    direction: str
    min_row: int
    max_row: int
    min_col: int
    max_col: int
    first_center_x: float = 0.0
    first_center_y: float = 0.0
    last_center_x: float = 0.0
    last_center_y: float = 0.0
    word_angle: float = 0.0
    word_length_in_cells: int = 0
    required_oval_width: float = 0.0
    required_oval_height: float = 0.0
    center_x: float = 0.0
    center_y: float = 0.0
    oval_width: float = 0.0
    oval_height: float = 0.0
    rotation_degrees: float = 0.0
    safe_padding: float = 0.0
    side_padding: float = 0.0

    def as_dict(self) -> dict:
        return {
            "word": self.word_display,
            "word_display": self.word_display,
            "word_normalized": self.word_normalized,
            "cells": [[row, col] for row, col in self.cells],
            "start_row": self.start_row,
            "start_col": self.start_col,
            "end_row": self.end_row,
            "end_col": self.end_col,
            "direction": self.direction,
            "first_letter_center": [self.first_center_x, self.first_center_y],
            "last_letter_center": [self.last_center_x, self.last_center_y],
            "first_center_x": self.first_center_x,
            "first_center_y": self.first_center_y,
            "last_center_x": self.last_center_x,
            "last_center_y": self.last_center_y,
            "oval_center": [self.center_x, self.center_y],
            "oval_center_x": self.center_x,
            "oval_center_y": self.center_y,
            "oval_width": self.oval_width,
            "oval_height": self.oval_height,
            "oval_rotation": self.rotation_degrees,
            "padding_used": {
                "end_pt": self.safe_padding,
                "side_pt": self.side_padding,
                "end_ratio": _OVAL_END_PAD_RATIO,
                "side_ratio": _OVAL_SIDE_PAD_RATIO,
            },
            "min_row": self.min_row,
            "max_row": self.max_row,
            "min_col": self.min_col,
            "max_col": self.max_col,
            "word_angle": self.word_angle,
            "word_length_in_cells": self.word_length_in_cells,
            "required_oval_width": self.required_oval_width,
            "required_oval_height": self.required_oval_height,
            "safe_padding": self.safe_padding,
            "side_padding": self.side_padding,
        }


@dataclass
class SolutionTable:
    entries: list[WordSolutionEntry] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {"entries": [entry.as_dict() for entry in self.entries]}


def entry_from_validated_path(path: dict) -> WordSolutionEntry | None:
    cells = _parse_cells(path.get("cells"))
    if not cells:
        return None
    word_display = str(path.get("word") or "")
    rows = [row for row, _col in cells]
    cols = [col for _row, col in cells]
    return WordSolutionEntry(
        word_display=word_display,
        word_normalized=str(path.get("grid_word") or _normalize_word(word_display)),
        cells=cells,
        start_row=int(path.get("start_row", cells[0][0])),
        start_col=int(path.get("start_col", cells[0][1])),
        end_row=int(path.get("end_row", cells[-1][0])),
        end_col=int(path.get("end_col", cells[-1][1])),
        direction=_direction_from_cells(cells),
        min_row=min(rows),
        max_row=max(rows),
        min_col=min(cols),
        max_col=max(cols),
        word_length_in_cells=len(cells),
    )


def build_solution_table(validated_paths: list[dict]) -> tuple[SolutionTable, list[str]]:
    """Build the solution-tracking table once from validated solver output."""
    table = SolutionTable()
    errors: list[str] = []
    for path in validated_paths:
        entry = entry_from_validated_path(path)
        if entry is None:
            word = path.get("word", "?")
            errors.append(f'Solution table row for "{word}" has no valid cells.')
            continue
        table.entries.append(entry)
    if not errors and len(table.entries) != len(validated_paths):
        errors.append("Solution table entry count does not match validated path count.")
    return table, errors


def compute_oval_geometry(entry: WordSolutionEntry, grid: GridLayout) -> str | None:
    """Compute one oval from validated path letter centers. Called before render, never during draw."""
    if not entry.cells:
        return f'Oval cannot be computed for "{entry.word_display}": no cells.'

    start, end = _letter_centers(entry, grid)
    cell_size = grid.cell_size
    end_pad = cell_size * _OVAL_END_PAD_RATIO
    side_pad = cell_size * _OVAL_SIDE_PAD_RATIO
    span = math.hypot(end[0] - start[0], end[1] - start[1])

    entry.first_center_x = start[0]
    entry.first_center_y = start[1]
    entry.last_center_x = end[0]
    entry.last_center_y = end[1]
    entry.word_length_in_cells = len(entry.cells)
    entry.safe_padding = end_pad
    entry.side_padding = side_pad
    entry.word_angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    entry.center_x = (start[0] + end[0]) / 2.0
    entry.center_y = (start[1] + end[1]) / 2.0
    entry.rotation_degrees = entry.word_angle

    # Use the same perpendicular extent for all words regardless of direction.
    # The rotation handles the angle, so the oval width stays consistent.
    perpendicular_span = cell_size + 2.0 * side_pad

    path_major = span + 2.0 * end_pad
    path_minor = perpendicular_span + 2.0 * side_pad

    entry.required_oval_width = max(path_major, cell_size + 2.0 * end_pad)
    entry.required_oval_height = path_minor
    entry.oval_width = entry.required_oval_width
    entry.oval_height = entry.required_oval_height

    if entry.oval_width <= cell_size * 0.5:
        return f'Oval for "{entry.word_display}" is too short.'
    if entry.oval_height <= cell_size * 0.35:
        return f'Oval for "{entry.word_display}" is collapsed.'
    if not math.isfinite(entry.center_x) or not math.isfinite(entry.center_y):
        return f'Oval center is invalid for "{entry.word_display}".'

    for x, y in _ellipse_boundary_points(entry):
        if (
            x < grid.box_x - _STROKE_TOLERANCE_PT
            or x > grid.box_x + grid.box_w + _STROKE_TOLERANCE_PT
            or y < grid.box_y - _STROKE_TOLERANCE_PT
            or y > grid.box_y + grid.box_h + _STROKE_TOLERANCE_PT
        ):
            return f'Answer oval for "{entry.word_display}" extends outside the puzzle border.'
    return None


def validate_oval_coverage(
    entry: WordSolutionEntry,
    grid: GridLayout,
    grid_letters: list[list[str]],
) -> list[str]:
    """Verify one answer oval surrounds its word — blocking correctness checks only."""
    errors: list[str] = []
    word = entry.word_display
    if not entry.cells:
        errors.append(f'Answer oval for "{word}" is missing a validated path.')
        return errors

    if not _path_spells_word(entry, grid_letters):
        errors.append(f'Answer path for "{word}" does not spell the word correctly.')

    if entry.oval_width <= 0 or entry.oval_height <= 0:
        errors.append(f'Answer oval for "{word}" is missing or collapsed.')
        return errors

    start, end = _letter_centers(entry, grid)

    if entry.oval_width + 0.01 < entry.required_oval_width:
        errors.append(f'Answer oval for "{word}" is too short to cover the full word length.')

    for label, px, py in (
        ("first letter", start[0], start[1]),
        ("last letter", end[0], end[1]),
    ):
        if not _point_in_rotated_ellipse(px, py, entry):
            errors.append(f'Answer oval for "{word}" does not cover the {label}.')

    for row, col in entry.cells:
        cx, cy = grid.letter_center(row, col)
        if not _point_in_rotated_ellipse(cx, cy, entry):
            errors.append(f'Answer oval for "{word}" leaves out a letter in the path.')
            break

    for x, y in _ellipse_boundary_points(entry):
        if (
            x < grid.box_x - _STROKE_TOLERANCE_PT
            or x > grid.box_x + grid.box_w + _STROKE_TOLERANCE_PT
            or y < grid.box_y - _STROKE_TOLERANCE_PT
            or y > grid.box_y + grid.box_h + _STROKE_TOLERANCE_PT
        ):
            errors.append(f'Answer oval for "{word}" extends outside the puzzle border.')
            break

    return errors


def collect_oval_proximity_warnings(
    entry: WordSolutionEntry,
    table: SolutionTable,
    grid: GridLayout,
) -> list[str]:
    """Non-blocking notes when ovals pass near other answer words or overlap slightly."""
    warnings: list[str] = []
    word = entry.word_display
    own_cells = set(entry.cells)

    for other in table.entries:
        if other is entry:
            continue
        if _ellipses_overlap(entry, other, gap=_OVAL_COLLISION_GAP_PT):
            warnings.append(
                f'Answer oval for "{word}" passes near the answer oval for "{other.word_display}".'
            )
        for row, col in other.cells:
            if (row, col) in own_cells:
                continue
            cx, cy = grid.letter_center(row, col)
            if _point_in_rotated_ellipse(cx, cy, entry, slack=0.0):
                warnings.append(
                    f'Answer oval for "{word}" passes near letters from "{other.word_display}".'
                )
                break

    return warnings


def validate_oval_collisions(
    entry: WordSolutionEntry,
    table: SolutionTable,
    grid: GridLayout,
) -> list[str]:
    """Deprecated blocking alias — proximity is warning-only; returns no errors."""
    return []


def validate_oval_coverage_for_table(
    table: SolutionTable,
    grid: GridLayout,
    grid_letters: list[list[str]],
) -> list[str]:
    """Validate every answer oval covers its word — blocking errors only."""
    errors: list[str] = []
    for entry in table.entries:
        errors.extend(validate_oval_coverage(entry, grid, grid_letters))
    return errors


def collect_oval_proximity_warnings_for_table(
    table: SolutionTable,
    grid: GridLayout,
) -> list[str]:
    """Collect non-blocking proximity warnings for all answer ovals."""
    warnings: list[str] = []
    for entry in table.entries:
        warnings.extend(collect_oval_proximity_warnings(entry, table, grid))
    return warnings


def prepare_answer_key_geometry(
    table: SolutionTable,
    grid: GridLayout,
    grid_letters: list[list[str]],
) -> tuple[list[str], list[str]]:
    """Compute oval geometry once before QA/export. Renderer must not call this."""
    errors: list[str] = []
    for entry in table.entries:
        error = compute_oval_geometry(entry, grid)
        if error:
            errors.append(error)
    if errors:
        return errors, []
    coverage_errors = validate_oval_coverage_for_table(table, grid, grid_letters)
    if coverage_errors:
        return coverage_errors, []
    return [], collect_oval_proximity_warnings_for_table(table, grid)


def require_renderer_geometry(
    table: SolutionTable | None,
    *,
    word_count: int,
) -> list[str]:
    """Locked renderer gate: ovals must already be computed; draw must not recompute."""
    return validate_solution_table_for_render(
        table,
        word_count=word_count,
        require_geometry=True,
    )


def finalize_solution_ovals(
    table: SolutionTable,
    grid: GridLayout,
    grid_letters: list[list[str]],
) -> list[str]:
    """Fill oval geometry and return blocking validation errors only."""
    blocking, _warnings = prepare_answer_key_geometry(table, grid, grid_letters)
    return blocking


def finalize_solution_ovals_with_warnings(
    table: SolutionTable,
    grid: GridLayout,
    grid_letters: list[list[str]],
) -> tuple[list[str], list[str]]:
    """Return blocking oval errors and non-blocking proximity warnings."""
    return prepare_answer_key_geometry(table, grid, grid_letters)


def validate_solution_table_for_render(
    table: SolutionTable | None,
    *,
    word_count: int,
    require_geometry: bool = False,
) -> list[str]:
    """Validate table before answer-key export."""
    errors: list[str] = []
    if table is None or not table.entries:
        errors.append("Solution table is missing.")
        return errors
    if len(table.entries) != word_count:
        errors.append(
            f"Solution table has {len(table.entries)} entries but {word_count} words were solved."
        )
    for entry in table.entries:
        if not entry.cells:
            errors.append(f'Solution table row for "{entry.word_display}" has no cells.')
        elif require_geometry and (entry.oval_width <= 0 or entry.oval_height <= 0):
            errors.append(f'Oval geometry was not computed for "{entry.word_display}".')
    return errors


def errors_are_oval_layout_failures(errors: list[str]) -> bool:
    """Deprecated: grid-size retry is disabled; kept for compatibility."""
    return False
