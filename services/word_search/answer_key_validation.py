"""Validate Word Search answer paths before PDF export using the deterministic solver."""
from __future__ import annotations

from .answer_key_solver import (
    AnswerKeyValidationResult,
    solve_puzzle_answer_key,
)
from .builder import PuzzleResult


def validate_puzzle_answer_key(puzzle: PuzzleResult) -> AnswerKeyValidationResult:
    """Validate official placement paths before PDF export."""
    return solve_puzzle_answer_key(puzzle)
