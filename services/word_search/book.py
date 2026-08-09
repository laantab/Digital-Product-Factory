"""Build multi-puzzle word search books from engine inputs."""
from __future__ import annotations

import math

from .builder import PuzzleResult, _assemble_result
from .engine import build_grid, normalize_difficulty, normalize_grid_size
from .word_lists import WordEntry, parse_custom_word_list, suggest_words_from_topic, supplement_entries_to_count, word_list_fetch_target


def _split_entries(
    entries: list[WordEntry],
    puzzle_count: int,
    *,
    words_per_puzzle: int | None = None,
) -> list[list[WordEntry]]:
    count = max(1, int(puzzle_count))
    if not entries:
        return [[] for _ in range(count)]

    per_puzzle = int(words_per_puzzle or 0)
    if per_puzzle > 0:
        chunk_size = per_puzzle
    else:
        chunk_size = max(1, math.ceil(len(entries) / count))

    chunks: list[list[WordEntry]] = []
    for index in range(0, len(entries), chunk_size):
        chunks.append(entries[index : index + chunk_size])
    while len(chunks) < count:
        chunks.append([])
    return chunks[:count]


def _collect_entries_from_custom(raw: str, *, grid_size: int) -> tuple[list[WordEntry], list[str], list[str], list[str]]:
    parsed = parse_custom_word_list(raw, grid_size=grid_size)
    return parsed.entries, parsed.warnings, parsed.errors, parsed.rejected


def _collect_entries_from_topic(
    topic: str,
    audience: str,
    *,
    grid_size: int,
    max_words: int,
) -> tuple[list[WordEntry], list[str], list[str], str]:
    suggested, warnings, errors, matched_pack_id = suggest_words_from_topic(topic, audience, max_words=max_words)
    if errors:
        return [], warnings, errors, ""
    lines = "\n".join(suggested)
    parsed = parse_custom_word_list(lines, grid_size=grid_size)
    return parsed.entries, warnings + parsed.warnings, parsed.errors + parsed.errors, matched_pack_id


def build_word_search_puzzles(
    *,
    mode: str,
    product_title: str,
    custom_words: str = "",
    topic: str = "",
    audience: str = "",
    theme: str = "",
    difficulty: str = "medium",
    grid_size: int | str = 15,
    number_of_puzzles: int = 1,
    words_per_puzzle: int | None = None,
    output_type: str = "book",
    seed: int | None = None,
) -> tuple[list[PuzzleResult], list[str], list[str]]:
    """
    Build one or more puzzles for worksheet/book output.

    mode: ``topic`` or ``custom_word_list``
    output_type: ``single_worksheet`` (1 puzzle) or ``book`` (N puzzles)
    """
    size = normalize_grid_size(grid_size)
    diff = normalize_difficulty(difficulty)
    warnings: list[str] = []
    errors: list[str] = []

    puzzle_count = 1 if output_type in {"single_worksheet", "single_page"} else max(1, int(number_of_puzzles or 1))
    mode_key = str(mode or "").strip().lower()
    title_base = str(product_title or "Word Search").strip() or "Word Search"
    theme_label = str(theme or topic or "").strip()

    if mode_key in {"custom", "custom_word_list", "custom_list"}:
        entries, parse_warnings, parse_errors, _rejected = _collect_entries_from_custom(custom_words, grid_size=size)
        warnings.extend(parse_warnings)
        errors.extend(parse_errors)
        book_mode = "custom_list"
    elif mode_key == "topic":
        per_puzzle = int(words_per_puzzle or 10)
        required_words = puzzle_count * per_puzzle
        max_words = word_list_fetch_target(max(12, required_words))
        entries, topic_warnings, topic_errors, matched_pack_id = _collect_entries_from_topic(
            topic or theme_label,
            audience,
            grid_size=size,
            max_words=max_words,
        )
        warnings.extend(topic_warnings)
        errors.extend(topic_errors)
        book_mode = "topic"
    else:
        errors.append('Mode must be "topic" or "custom_word_list".')
        return [], warnings, errors

    if errors:
        return [], warnings, errors
    if not entries:
        errors.append("No usable words available to build puzzles.")
        return [], warnings, errors

    per_puzzle = int(words_per_puzzle or 0) if output_type == "book" else 0
    if output_type == "book" and per_puzzle > 0:
        required_words = puzzle_count * per_puzzle
        if len(entries) < required_words:
            deficit = required_words - len(entries)
            allow_top_up = book_mode == "topic" or deficit <= max(
                15, int(required_words * 0.15)
            )
            if allow_top_up:
                entries, topup_warnings = supplement_entries_to_count(
                    entries,
                    required_words,
                    grid_size=size,
                    topic=theme_label,
                    matched_pack_id=matched_pack_id,
                )
                warnings.extend(topup_warnings)
        if len(entries) < required_words:
            # If no pack was matched and we still can't fill, return clear error
            if not matched_pack_id:
                errors.append(
                    f'Not enough topic-specific words found for "{theme_label}". '
                    f"Please add more custom words or choose a broader topic."
                )
            else:
                errors.append(
                    f"Need at least {required_words} words for {puzzle_count} worksheets "
                    f"with {per_puzzle} words each; only {len(entries)} available."
                )
            return [], warnings, errors
        entries = entries[:required_words]

    chunks = _split_entries(
        entries,
        1 if output_type in {"single_worksheet", "single_page"} else puzzle_count,
        words_per_puzzle=per_puzzle if output_type == "book" else None,
    )
    chunks = [chunk for chunk in chunks if chunk]
    if not chunks:
        errors.append("No puzzle groups could be created from the word list.")
        return [], warnings, errors

    puzzles: list[PuzzleResult] = []
    for index, chunk in enumerate(chunks, start=1):
        puzzle_seed = None if seed is None else int(seed) + index
        build = build_grid(chunk, grid_size=size, difficulty=diff, seed=puzzle_seed)
        if puzzle_count == 1 and output_type in {"single_worksheet", "single_page"}:
            puzzle_title = title_base
        else:
            puzzle_title = f"{title_base} — Puzzle {index}"

        result = _assemble_result(
            mode=book_mode,
            puzzle_title=puzzle_title,
            difficulty=diff,
            grid_size=size,
            entries=[entry for entry in chunk if entry.display not in build.rejected_words],
            build=build,
            extra_warnings=[w for w in warnings if "Used local vocabulary pack" in w],
            extra_errors=[],
            topic=topic or theme_label or None,
            audience=audience or None,
        )
        if result.errors:
            errors.extend(result.errors)
        warnings.extend(result.warnings)
        if result.placed_words:
            puzzles.append(result)

    if not puzzles:
        errors.append("No puzzles could be generated.")
    return puzzles, warnings, errors
