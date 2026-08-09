"""Targeted crossword repair — replaces failed words and clues without full regeneration.

The repair pipeline:
  1. Analyze QA errors to find failed words and clues per puzzle.
  2. For each failed puzzle, get replacement words (local pack or fallback).
  3. Rebuild the grid with replacements (or the full puzzle if grid is broken).
  4. Re-validate. Stop if the puzzle passes.
  5. Report which words were replaced for transparency.

Guarded against:
  - Infinite loops: max 3 repair attempts per puzzle
  - API calls: only uses local fallback library
  - Collateral damage: only replaces words that failed, keeps valid words
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from services.crossword.builder import (
    CrosswordPuzzleResult,
    build_crossword_from_entries,
    build_crossword_from_topic,
    build_crossword_from_custom_list,
)
from services.crossword.clues import generate_clues_for_words
from services.crossword.engine import normalize_grid_size
from services.crossword.word_entries import (
    CrosswordEntry,
    suggest_crossword_words_from_topic,
    parse_crossword_word_list,
)
from services.crossword.qa_agent import CrosswordQAResult, run_crossword_qa, run_crossword_book_qa
from services.crossword.crossword_fallback import (
    get_fallback_words_and_clues,
    get_fallback_book_vocabulary,
    select_fallback_pack,
)


# ---------------------------------------------------------------------------
# Error analysis
# ---------------------------------------------------------------------------

@dataclass
class PuzzleRepairPlan:
    """Describes what needs to be repaired in one puzzle."""
    puzzle_index: int  # 0-based
    failed_words: list[str]  # answers that failed validation
    failed_reasons: dict[str, str]  # {word: short_reason}
    use_fallback: bool = False  # True when no local pack matches


@dataclass
class RepairReport:
    """Outcome of a single repair attempt."""
    repaired_puzzles: list[CrosswordPuzzleResult]  # new puzzle objects
    replaced_words: dict[int, list[str]]  # puzzle_index → [old_word → new_word]
    all_passed: bool
    final_qa: CrosswordQAResult
    used_fallback: bool
    attempt: int


# ---------------------------------------------------------------------------
# Error → repair plan
# ---------------------------------------------------------------------------

def _extract_failed_words_from_errors(errors: list[str], placed_words: list[str]) -> list[str]:
    """Parse QA errors to find specific words that failed."""
    failed: set[str] = set()
    placed_upper = {w.upper() for w in placed_words if w}

    for err in errors:
        err_lower = err.lower()
        # Patterns that carry the word name
        for word in placed_upper:
            if word.lower() in err_lower:
                failed.add(word)

    return list(failed)


def _is_grid_failure_only(errors: list[str]) -> bool:
    """Return True if all errors are about grid quality, not word/clue content."""
    grid_keywords = {"grid", "empty", "isolated", "density", "placed"}
    clue_keywords = {"clue", "placeholder", "generic", "unrelated", "duplicate"}
    for err in errors:
        err_lower = err.lower()
        has_grid = any(k in err_lower for k in grid_keywords)
        has_clue = any(k in err_lower for k in clue_keywords)
        if has_clue or not has_grid:
            return False
    return True


def analyze_book_qa_for_repair(
    puzzles: list[CrosswordPuzzleResult],
    qa: CrosswordQAResult,
) -> list[PuzzleRepairPlan]:
    """Determine which puzzles need repair and why."""
    plans: list[PuzzleRepairPlan] = []

    # Parse book-level errors
    book_errors = list(qa.errors)

    # Per-puzzle errors from book QA are prefixed with "Puzzle N:"
    puzzle_errors: dict[int, list[str]] = {}
    for err in book_errors:
        for i in range(1, 20):
            prefix = f"Puzzle {i}: "
            if err.startswith(prefix):
                idx = i - 1  # 0-based
                msg = err[len(prefix):]
                puzzle_errors.setdefault(idx, []).append(msg)
                break

    for idx, puzzle in enumerate(puzzles):
        errors = puzzle_errors.get(idx, [])
        placed = list(puzzle.placed_words)
        failed_words = _extract_failed_words_from_errors(errors, placed)

        # Check if fallback is needed: "no pack matched" + generic content
        use_fallback = (
            puzzle.no_pack_matched
            or any("no matching vocabulary pack" in e.lower() for e in errors)
            or any("generic fallback" in e.lower() for e in errors)
        )

        reasons: dict[str, str] = {}
        for err in errors:
            for fw in failed_words:
                if fw.lower() in err.lower():
                    reasons[fw] = err[:80]

        if failed_words or errors:
            plans.append(PuzzleRepairPlan(
                puzzle_index=idx,
                failed_words=failed_words,
                failed_reasons=reasons,
                use_fallback=use_fallback,
            ))

    return plans


# ---------------------------------------------------------------------------
# Word replacement
# ---------------------------------------------------------------------------

def _get_replacement_words(
    theme: str,
    count: int,
    exclude: set[str],
    use_fallback: bool,
    seed: int | None = None,
) -> tuple[list[str], dict[str, str], bool]:
    """Get replacement words and their clues.

    Returns (words, clues_map, used_fallback).
    Never silently substitutes the EVERYDAY_LIFE pack for an unmatched topic.
    """
    pack_key = select_fallback_pack(theme)
    if not pack_key:
        return [], {}, False

    if use_fallback:
        words, clues = get_fallback_words_and_clues(
            theme,
            count=count + len(exclude) + 5,
            exclude_words=exclude,
            random_seed=seed,
        )
        return words[:count], clues, True

    # Try local pack first
    topic = theme or ""
    suggested, warnings, errors = suggest_crossword_words_from_topic(topic, max_words=count + len(exclude) + 5)
    clean = [w.upper() for w in suggested if w.upper() not in exclude]
    if len(clean) >= count:
        clues = generate_clues_for_words(clean[:count], theme=topic)
        return clean[:count], clues, False

    # Topic-matched fallback library only (empty when unmatched).
    words, clues = get_fallback_words_and_clues(
        theme,
        count=count + len(exclude) + 5,
        exclude_words=exclude,
        random_seed=seed,
    )
    return words[:count], clues, bool(words)


def _rebuild_puzzle_with_replacements(
    puzzle: CrosswordPuzzleResult,
    replacement_words: list[str],
    replacement_clues: dict[str, str],
    failed_words: list[str],
    seed: int | None,
) -> CrosswordPuzzleResult:
    """Rebuild a puzzle using replacement words, preserving valid existing words.

    Key distinction:
      - Words that passed QA are always kept (preserves user's custom word list).
      - Only words that explicitly failed validation are replaced.
      - Replacement clues are used for new words; existing clues are kept unless
        the word itself is being replaced.
    """
    failed_set = {w.upper() for w in failed_words if w}
    # Keep all words that did NOT fail QA — preserves user's custom word list
    kept = [w for w in puzzle.placed_words if w and w.upper() not in failed_set]
    combined = kept + replacement_words
    unique = []
    seen = set()
    for w in combined:
        u = w.upper()
        if u not in seen and u not in {"", "NONE"}:
            seen.add(u)
            unique.append(u)

    # Build clues map: merge existing clues + replacement clues
    existing_clues: dict[str, str] = {}
    for clue_obj in puzzle.clues:
        if clue_obj.answer and clue_obj.clue:
            existing_clues[clue_obj.answer.upper()] = clue_obj.clue

    all_clues: dict[str, str] = {}
    for word in unique:
        # If this word failed and has a replacement clue, use the replacement
        if word in replacement_clues:
            all_clues[word] = replacement_clues[word]
        # If the word is kept and has an existing clue, keep it
        elif word in existing_clues:
            all_clues[word] = existing_clues[word]
        # Otherwise generate a clue
        else:
            generated = generate_clues_for_words([word], theme=puzzle.theme)
            clue_text = (generated.get(word) or "").strip()
            if not clue_text:
                continue
            all_clues[word] = clue_text

    entries = [CrosswordEntry(display=w, answer=w) for w in unique]
    return build_crossword_from_entries(
        entries,
        puzzle_title=puzzle.puzzle_title or "Crossword Puzzle",
        theme=puzzle.theme or "General",
        difficulty=puzzle.difficulty or "medium",
        grid_size=puzzle.grid_size,
        clues_map=all_clues,
        seed=seed,
    )


# ---------------------------------------------------------------------------
# Main repair loop
# ---------------------------------------------------------------------------

# AI-call budget: 1 initial generation + 1 targeted repair = 2 total generation cycles.
# After that, only the local verified fallback library is used (no AI calls).
MAX_REPAIR_ATTEMPTS = 1


def repair_crossword_book(
    puzzles: list[CrosswordPuzzleResult],
    original_theme: str,
    difficulty: str = "medium",
    grid_size: int = 15,
    seed: int | None = None,
) -> RepairReport:
    """Attempt to repair a failed crossword book through targeted replacement.

    Returns a RepairReport with the result of the repair attempt.
    """
    # Run initial QA to know which puzzles failed
    initial_qa = run_crossword_book_qa(
        puzzles,
        expected_puzzle_count=len(puzzles),
        include_answer_key=True,
    )

    if initial_qa.passed:
        return RepairReport(
            repaired_puzzles=list(puzzles),
            replaced_words={},
            all_passed=True,
            final_qa=initial_qa,
            used_fallback=False,
            attempt=0,
        )

    plans = analyze_book_qa_for_repair(puzzles, initial_qa)
    if not plans:
        return RepairReport(
            repaired_puzzles=list(puzzles),
            replaced_words={},
            all_passed=False,
            final_qa=initial_qa,
            used_fallback=False,
            attempt=0,
        )

    replaced_words: dict[int, list[str]] = {}
    current_puzzles = list(puzzles)

    for attempt in range(1, MAX_REPAIR_ATTEMPTS + 1):
        new_puzzles: list[CrosswordPuzzleResult] = []
        used_fallback_any = False
        attempt_replaced: dict[int, list[str]] = {}

        for plan in plans:
            idx = plan.puzzle_index
            puzzle = current_puzzles[idx]

            # Collect words already used in OTHER puzzles (to avoid repetition)
            other_words: set[str] = set()
            for j, p in enumerate(current_puzzles):
                if j != idx:
                    for w in p.placed_words:
                        other_words.add(w.upper())

            # Add failed words to exclusion
            exclude = other_words | {w.upper() for w in puzzle.placed_words if w}
            count_needed = max(6, len(puzzle.placed_words))
            new_words, new_clues, used_fb = _get_replacement_words(
                theme=original_theme,
                count=count_needed,
                exclude=exclude,
                use_fallback=plan.use_fallback,
                seed=None if seed is None else seed + attempt * 100 + idx,
            )
            used_fallback_any = used_fallback_any or used_fb

            # Record what was replaced
            old_words = [w.upper() for w in puzzle.placed_words if w]
            attempt_replaced[idx] = old_words

            # Rebuild the puzzle — pass failed_words so only the broken ones are replaced
            rebuilt = _rebuild_puzzle_with_replacements(
                puzzle=puzzle,
                replacement_words=new_words,
                replacement_clues=new_clues,
                failed_words=plan.failed_words,
                seed=None if seed is None else seed + attempt,
            )
            rebuilt.mode = puzzle.mode
            rebuilt.warnings = puzzle.warnings + [
                f"Repair attempt {attempt}: replaced {len(old_words)} words with {len(new_words)} replacements."
            ]
            new_puzzles.append(rebuilt)

        # Validate rebuilt puzzles
        new_qa = run_crossword_book_qa(
            new_puzzles,
            expected_puzzle_count=len(puzzles),
            include_answer_key=True,
        )

        if new_qa.passed:
            return RepairReport(
                repaired_puzzles=new_puzzles,
                replaced_words={k: attempt_replaced.get(k, []) for k in range(len(new_puzzles))},
                all_passed=True,
                final_qa=new_qa,
                used_fallback=used_fallback_any,
                attempt=attempt,
            )

        # Update for next attempt — keep only puzzles that still fail
        remaining_plans: list[PuzzleRepairPlan] = []
        for plan in plans:
            idx = plan.puzzle_index
            rebuilt_qa = run_crossword_qa(new_puzzles[idx])
            if not rebuilt_qa.passed:
                remaining_plans.append(plan)
        plans = remaining_plans
        current_puzzles = new_puzzles

        if not plans:
            break

    # All repair attempts exhausted
    final_qa = run_crossword_book_qa(
        current_puzzles,
        expected_puzzle_count=len(puzzles),
        include_answer_key=True,
    )
    return RepairReport(
        repaired_puzzles=current_puzzles,
        replaced_words=attempt_replaced,
        all_passed=False,
        final_qa=final_qa,
        used_fallback=used_fallback_any,
        attempt=MAX_REPAIR_ATTEMPTS,
    )


def build_crossword_book_with_recovery(
    *,
    theme: str,
    difficulty: str = "medium",
    grid_size: int | str = 15,
    number_of_puzzles: int = 10,
    words_per_puzzle: int = 10,
    output_type: str = "book",
    seed: int | None = None,
    include_answer_key: bool = True,
    mode: str = "topic",
    custom_words: str = "",
) -> tuple[list[CrosswordPuzzleResult], list[str], list[str], CrosswordQAResult, bool]:
    """Build a crossword book with automatic repair and fallback recovery.

    Returns (puzzles, warnings, errors, qa, used_fallback)
    """
    from services.crossword.book import build_crossword_puzzles

    # Stage 1: initial generation
    puzzles, warnings, errors = build_crossword_puzzles(
        mode=mode,
        product_title=theme,
        custom_words=custom_words,
        theme=theme,
        difficulty=difficulty,
        grid_size=grid_size,
        number_of_puzzles=number_of_puzzles,
        words_per_puzzle=words_per_puzzle,
        output_type=output_type,
        use_ai_words=False,
        seed=seed,
    )

    initial_qa = run_crossword_book_qa(
        puzzles,
        expected_puzzle_count=number_of_puzzles,
        include_answer_key=include_answer_key,
        words_per_puzzle=words_per_puzzle,
    )

    if initial_qa.passed:
        return puzzles, warnings, errors, initial_qa, False

    # Stage 2: targeted repair (up to 3 attempts)
    repair_report = repair_crossword_book(
        puzzles=puzzles,
        original_theme=theme,
        difficulty=difficulty,
        grid_size=normalize_grid_size(grid_size),
        seed=seed,
    )

    if repair_report.all_passed:
        warnings.extend([
            f"Crossword repaired on attempt {repair_report.attempt}."
        ])
        return (
            repair_report.repaired_puzzles,
            warnings,
            [],
            repair_report.final_qa,
            repair_report.used_fallback,
        )

    # Stage 3: fallback book vocabulary (last resort before error).
    # Only for a matched pack — never silent EVERYDAY_LIFE substitution.
    pack_key = select_fallback_pack(theme)
    if not pack_key:
        fail_msg = (
            "Crossword could not find enough topic-relevant words and clues for this theme. "
            "Please correct the theme or provide a custom word list."
        )
        failed_qa = CrosswordQAResult(
            passed=False,
            blocked_export=True,
            errors=list(repair_report.final_qa.errors) + [fail_msg],
            warnings=list(warnings),
        )
        return [], warnings, [fail_msg], failed_qa, False

    fallback_plans = get_fallback_book_vocabulary(
        theme=theme,
        puzzle_count=number_of_puzzles,
        words_per_puzzle=words_per_puzzle,
        random_seed=seed,
    )
    if not fallback_plans:
        fail_msg = (
            "Crossword could not find enough topic-relevant words and clues for this theme. "
            "Please correct the theme or provide a custom word list."
        )
        failed_qa = CrosswordQAResult(
            passed=False,
            blocked_export=True,
            errors=list(repair_report.final_qa.errors) + [fail_msg],
            warnings=list(warnings),
        )
        return [], warnings, [fail_msg], failed_qa, False

    fallback_puzzles: list[CrosswordPuzzleResult] = []
    for idx, (words, clues_map) in enumerate(fallback_plans):
        size = normalize_grid_size(grid_size)
        entries = [CrosswordEntry(display=w, answer=w) for w in words]
        puzzle = build_crossword_from_entries(
            entries,
            puzzle_title=f"Puzzle {idx + 1}",
            theme=theme,
            difficulty=difficulty,
            grid_size=size,
            clues_map=clues_map,
            seed=None if seed is None else seed + idx,
        )
        puzzle.mode = "fallback"
        fallback_puzzles.append(puzzle)

    # Ensure we have the right count
    while len(fallback_puzzles) < number_of_puzzles:
        extra_words, extra_clues = get_fallback_words_and_clues(
            theme,
            count=words_per_puzzle,
            exclude_words={w for p in fallback_puzzles for w in p.placed_words},
            random_seed=None if seed is None else seed + 1000 + len(fallback_puzzles),
        )
        if not extra_words:
            break
        size = normalize_grid_size(grid_size)
        entries = [CrosswordEntry(display=w, answer=w) for w in extra_words]
        puzzle = build_crossword_from_entries(
            entries,
            puzzle_title=f"Puzzle {len(fallback_puzzles) + 1}",
            theme=theme,
            difficulty=difficulty,
            grid_size=size,
            clues_map=extra_clues,
            seed=seed,
        )
        puzzle.mode = "fallback"
        fallback_puzzles.append(puzzle)

    fallback_qa = run_crossword_book_qa(
        fallback_puzzles,
        expected_puzzle_count=len(fallback_puzzles),
        include_answer_key=include_answer_key,
        words_per_puzzle=words_per_puzzle,
    )

    if fallback_qa.passed:
        return (
            fallback_puzzles,
            warnings + ["Used verified fallback vocabulary (no matching pack found)."],
            [],
            fallback_qa,
            True,
        )

    # Stage 4: even the fallback failed final QA.
    # NEVER return defective puzzles — return empty puzzles so the downstream
    # builder's error guard fires and produces a clear user-facing error.
    # final_qa must be fallback_qa (the last QA run), not repair_report.final_qa.
    return (
        [],
        warnings + [
            "Crossword repair and verified fallback both failed final QA. "
            "No PDF or ZIP will be produced. "
            "Please try a different topic or provide a custom word list."
        ],
        repair_report.final_qa.errors + fallback_qa.errors,
        fallback_qa,  # last QA run = fallback_qa
        True,
    )
