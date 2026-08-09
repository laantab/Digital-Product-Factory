"""Orchestration for Create From Topic and Use My Own Word List modes."""
from __future__ import annotations

from dataclasses import dataclass, field

from .engine import GridBuildResult, build_grid, normalize_difficulty, normalize_grid_size
from .word_lists import WordEntry, parse_custom_word_list, suggest_words_from_topic


@dataclass
class PuzzleResult:
    puzzle_title: str
    word_bank: list[str]
    grid: list[list[str]]
    answer_key: list[dict]
    difficulty: str
    grid_size: int
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    mode: str = ""
    topic: str | None = None
    audience: str | None = None
    placed_words: list[str] = field(default_factory=list)
    rejected_words: list[str] = field(default_factory=list)
    validated_answer_key: list[dict] = field(default_factory=list)
    solution_table: object | None = None

    def as_dict(self) -> dict:
        return {
            "puzzle_title": self.puzzle_title,
            "word_bank": self.word_bank,
            "grid": self.grid,
            "answer_key": self.answer_key,
            "difficulty": self.difficulty,
            "grid_size": self.grid_size,
            "warnings": self.warnings,
            "errors": self.errors,
            "mode": self.mode,
            "topic": self.topic,
            "audience": self.audience,
            "placed_words": self.placed_words,
            "rejected_words": self.rejected_words,
            "validated_answer_key": self.validated_answer_key,
            "solution_table": (
                self.solution_table.as_dict()
                if self.solution_table is not None and hasattr(self.solution_table, "as_dict")
                else {}
            ),
        }


def _entries_from_display_words(words: list[str], *, grid_size: int) -> tuple[list[WordEntry], list[str], list[str]]:
    lines = "\n".join(words)
    parsed = parse_custom_word_list(lines, grid_size=grid_size)
    return parsed.entries, parsed.warnings, parsed.errors


def _assemble_result(
    *,
    mode: str,
    puzzle_title: str,
    difficulty: str,
    grid_size: int,
    entries: list[WordEntry],
    build: GridBuildResult,
    extra_warnings: list[str],
    extra_errors: list[str],
    topic: str | None = None,
    audience: str | None = None,
) -> PuzzleResult:
    word_bank = [entry.display for entry in entries if entry.display in build.placed_words]
    if not word_bank:
        word_bank = list(build.placed_words)

    warnings = list(extra_warnings) + list(build.warnings)
    errors = list(extra_errors) + list(build.errors)

    return PuzzleResult(
        puzzle_title=puzzle_title,
        word_bank=sorted(word_bank, key=str.lower),
        grid=build.grid,
        answer_key=[item.as_dict() for item in build.placements],
        difficulty=normalize_difficulty(difficulty),
        grid_size=grid_size,
        warnings=warnings,
        errors=errors,
        mode=mode,
        topic=topic,
        audience=audience,
        placed_words=list(build.placed_words),
        rejected_words=list(build.rejected_words),
    )


def build_puzzle_from_custom_list(
    raw_word_list: str,
    *,
    puzzle_title: str = "Word Search",
    difficulty: str = "medium",
    grid_size: int | str = 15,
    seed: int | None = None,
) -> PuzzleResult:
    """Use My Own Word List mode."""
    size = normalize_grid_size(grid_size)
    parsed = parse_custom_word_list(raw_word_list, grid_size=size)

    if parsed.errors:
        return PuzzleResult(
            puzzle_title=puzzle_title,
            word_bank=[],
            grid=[],
            answer_key=[],
            difficulty=normalize_difficulty(difficulty),
            grid_size=size,
            warnings=parsed.warnings,
            errors=parsed.errors,
            mode="custom_list",
            rejected_words=list(parsed.rejected),
        )

    build = build_grid(parsed.entries, grid_size=size, difficulty=difficulty, seed=seed)
    return _assemble_result(
        mode="custom_list",
        puzzle_title=puzzle_title,
        difficulty=difficulty,
        grid_size=size,
        entries=[entry for entry in parsed.entries if entry.display not in build.rejected_words],
        build=build,
        extra_warnings=parsed.warnings,
        extra_errors=[],
    )


def build_puzzle_from_topic(
    topic: str,
    audience: str = "",
    *,
    puzzle_title: str = "",
    difficulty: str = "medium",
    grid_size: int | str = 15,
    max_words: int = 12,
    seed: int | None = None,
) -> PuzzleResult:
    """Create From Topic mode — local vocabulary only."""
    size = normalize_grid_size(grid_size)
    title = str(puzzle_title or topic or "Word Search").strip() or "Word Search"

    suggested, topic_warnings, topic_errors, matched_pack_id = suggest_words_from_topic(
        topic,
        audience,
        max_words=max_words,
    )

    if topic_errors:
        return PuzzleResult(
            puzzle_title=title,
            word_bank=[],
            grid=[],
            answer_key=[],
            difficulty=normalize_difficulty(difficulty),
            grid_size=size,
            warnings=topic_warnings,
            errors=topic_errors,
            mode="topic",
            topic=topic,
            audience=audience or None,
        )

    entries, parse_warnings, parse_errors = _entries_from_display_words(suggested, grid_size=size)
    all_warnings = topic_warnings + parse_warnings

    if parse_errors or not entries:
        return PuzzleResult(
            puzzle_title=title,
            word_bank=[],
            grid=[],
            answer_key=[],
            difficulty=normalize_difficulty(difficulty),
            grid_size=size,
            warnings=all_warnings,
            errors=parse_errors or ["No usable words available for this topic."],
            mode="topic",
            topic=topic,
            audience=audience or None,
        )

    build = build_grid(entries, grid_size=size, difficulty=difficulty, seed=seed)
    return _assemble_result(
        mode="topic",
        puzzle_title=title,
        difficulty=difficulty,
        grid_size=size,
        entries=entries,
        build=build,
        extra_warnings=all_warnings,
        extra_errors=[],
        topic=topic,
        audience=audience or None,
    )
