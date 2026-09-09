"""Build multi-puzzle word search books from engine inputs."""
from __future__ import annotations

import math

from .answer_key_validation import validate_puzzle_answer_key
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


def _drop_substring_collisions(entries: list[WordEntry]) -> list[WordEntry]:
    """Drop any word that is a literal substring of another word in the pool.

    UNIVERSAL TOPIC PUZZLE ENGINE — grid-aware filtering (2026-09-08): a
    pair like "BASE" / "BASEBALLCAP" is legal by every relevance/length
    check, but placing both in the same grid lets the engine's overlap
    logic treat BASE's path as fully contained in BASEBALLCAP's -- the
    two placements alias the same cells, and the shared cells later get
    attributed to only one word, corrupting the other's official answer-
    key path (caught downstream as "Official path letters ... do not
    spell ...", with no way to recover it by retrying since the collision
    is deterministic, not seed-dependent). Removing the shorter word up
    front avoids ever constructing an unsafe grid -- this is a real
    placement-safety filter, not topic curation, so it runs for every
    word list (topic-resolved or customer-submitted) rather than only the
    new curated packs. Keeps the longer/more specific word; on an exact
    length tie, keeps the one seen first.
    """
    grids = [(entry, entry.grid.upper()) for entry in entries]
    keep: list[WordEntry] = []
    for entry, grid in grids:
        is_shorter_substring_of_another = any(
            grid != other_grid and grid in other_grid and len(grid) < len(other_grid)
            for other, other_grid in grids
            if other is not entry
        )
        if not is_shorter_substring_of_another:
            keep.append(entry)
    return keep


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

    # WORD SEARCH SHORT-TOPIC CRASH REPAIR: matched_pack_id used to be
    # assigned only inside the "topic" branch below, yet the shared top-up
    # block further down (used by BOTH branches whenever a book's word
    # requirement comes up short) unconditionally reads it -- raising
    # UnboundLocalError for custom_word_list mode whenever the customer's
    # list needed topping up. "" here matches exactly what
    # _collect_entries_from_topic itself returns when no specific pack
    # matched a topic, and is the value
    # services.word_search.word_lists.supplement_entries_to_count already
    # documents as its safe path: "Only use generic_fallback -- NEVER pull
    # from unrelated topic packs." No behavior invented -- this restores
    # the exact fallback the function was already built to take.
    matched_pack_id = ""

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

    entries = _drop_substring_collisions(entries)
    if not entries:
        errors.append("No usable words available to build puzzles.")
        return [], warnings, errors

    # A book puzzle needs at least this many words to be a real puzzle --
    # matches services.product._crossword_pdf_payload's own "at least 4
    # words" floor for the same reason (below it, build_grid has too
    # little to place and QA-empty puzzles get silently dropped anyway --
    # see "if result.placed_words" below).
    MIN_WORDS_PER_PUZZLE = 4

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
            # WORD SEARCH ADAPTIVE SIZING (2026-09-08): the customer's
            # requested book (puzzle_count x words_per_puzzle) may exceed
            # what a topic or short custom list can supply even after
            # generic-fallback top-up. Rather than blocking the whole
            # order, shrink the book to what the available words can
            # actually build -- never fabricate or duplicate words to hit
            # the original count.
            #
            # Shrink words-per-puzzle first (keeps the puzzle *count* the
            # customer asked for, and therefore the page count they were
            # quoted); only reduce puzzle_count when even the floor
            # words-per-puzzle can't be met for every requested puzzle.
            available = len(entries)
            if available < MIN_WORDS_PER_PUZZLE:
                if not matched_pack_id:
                    errors.append(
                        f'Not enough usable words were found for "{theme_label}" to build even '
                        f"one puzzle (need at least {MIN_WORDS_PER_PUZZLE}, found {available}). "
                        f"Please add more custom words or choose a broader topic."
                    )
                else:
                    errors.append(
                        f"Only {available} usable words were available; at least "
                        f"{MIN_WORDS_PER_PUZZLE} are needed to build even one puzzle."
                    )
                return [], warnings, errors

            shrunk_per_puzzle = available // puzzle_count
            if shrunk_per_puzzle >= MIN_WORDS_PER_PUZZLE:
                per_puzzle = shrunk_per_puzzle
                warnings.append(
                    f'Only {available} usable words were available for "{theme_label}" -- '
                    f"reduced to {per_puzzle} words per puzzle (requested {words_per_puzzle}) "
                    f"instead of leaving the book incomplete."
                )
            else:
                shrunk_puzzle_count = max(1, available // MIN_WORDS_PER_PUZZLE)
                per_puzzle = MIN_WORDS_PER_PUZZLE
                warnings.append(
                    f'Only {available} usable words were available for "{theme_label}" -- '
                    f"built {shrunk_puzzle_count} of the requested {puzzle_count} puzzles "
                    f"({per_puzzle} words each) instead of leaving the book incomplete."
                )
                puzzle_count = shrunk_puzzle_count
            required_words = puzzle_count * per_puzzle
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
        if puzzle_count == 1 and output_type in {"single_worksheet", "single_page"}:
            puzzle_title = title_base
        else:
            puzzle_title = f"{title_base} — Puzzle {index}"

        # UNIVERSAL TOPIC PUZZLE ENGINE — auto-recovery (2026-09-08): two
        # placed words can occasionally overlap in a way that corrupts one
        # another's solution path (e.g. "BASE" placed across "BASEBALLCAP"
        # at a shared prefix) -- the grid still renders, but the answer key
        # no longer spells the word. This was previously undetected until
        # final PDF-level QA rejected the whole puzzle with no retry.
        # Mirrors Crossword's existing bounded-retry recovery (see
        # services.crossword.book.build_crossword_puzzles): try a few
        # different seeds and keep the first attempt whose paths verify;
        # fall back to the last attempt (unchanged failure surfacing) if
        # none do.
        build = None
        result = None
        for attempt in range(3):
            attempt_seed = None if seed is None else int(seed) + index + (attempt * 97)
            candidate_build = build_grid(chunk, grid_size=size, difficulty=diff, seed=attempt_seed)
            candidate_result = _assemble_result(
                mode=book_mode,
                puzzle_title=puzzle_title,
                difficulty=diff,
                grid_size=size,
                entries=[entry for entry in chunk if entry.display not in candidate_build.rejected_words],
                build=candidate_build,
                extra_warnings=[w for w in warnings if "Used local vocabulary pack" in w],
                extra_errors=[],
                topic=topic or theme_label or None,
                audience=audience or None,
            )
            build, result = candidate_build, candidate_result
            if candidate_result.errors:
                continue
            validation = validate_puzzle_answer_key(candidate_result)
            if validation.ok:
                break

        assert result is not None
        if result.errors:
            errors.extend(result.errors)
        warnings.extend(result.warnings)
        if result.placed_words:
            puzzles.append(result)

    if not puzzles:
        errors.append("No puzzles could be generated.")
    return puzzles, warnings, errors
