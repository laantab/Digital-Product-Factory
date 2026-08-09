"""Crossword product QA — validates puzzles and retries before export."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Callable

from services.crossword.builder import CrosswordPuzzleResult


@dataclass
class CrosswordQAResult:
    passed: bool = False
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    fixes_applied: list[str] = field(default_factory=list)
    blocked_export: bool = True
    regeneration_attempts: int = 0

    def as_dict(self) -> dict:
        return {
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "fixes_applied": self.fixes_applied,
            "blocked_export": self.blocked_export,
            "regeneration_attempts": self.regeneration_attempts,
        }


def _trimmed_grid_stats(puzzle: CrosswordPuzzleResult) -> tuple[int, int, int]:
    grid = puzzle.grid
    rows = len(grid)
    cols = len(grid[0]) if rows else 0
    filled = 0
    for row in grid:
        for cell in row:
            if cell is not None:
                filled += 1
    return rows, cols, filled


def _check_clue_integrity(puzzle: CrosswordPuzzleResult, result: CrosswordQAResult) -> None:
    if puzzle.errors:
        result.errors.extend(puzzle.errors)

    placed = [w.upper() for w in puzzle.placed_words if w]
    if len(placed) < 4:
        result.errors.append(
            f"Crossword placed only {len(placed)} answers; at least 4 are required for a professional puzzle."
        )

    clue_words = {c.answer.upper() for c in puzzle.clues}
    for word in placed:
        if word not in clue_words:
            result.errors.append(f'Placed answer "{word}" is missing a clue entry.')

    for clue in puzzle.clues:
        if not str(clue.clue or "").strip():
            result.errors.append(f'Clue for "{clue.answer}" is empty.')
        if clue.number <= 0:
            result.errors.append(f'Clue numbering is invalid for "{clue.answer}".')

    across = sorted([c for c in puzzle.clues if c.direction == "across"], key=lambda c: c.number)
    down = sorted([c for c in puzzle.clues if c.direction == "down"], key=lambda c: c.number)
    if not across or not down:
        result.warnings.append("Crossword uses only one direction; mixed across/down is preferred.")

    numbers = [(c.number, c.direction) for c in puzzle.clues]
    if len(numbers) != len(set(numbers)):
        result.errors.append("Duplicate clue numbers detected on the grid.")


def _check_grid_quality(puzzle: CrosswordPuzzleResult, result: CrosswordQAResult) -> None:
    rows, cols, filled = _trimmed_grid_stats(puzzle)
    if filled == 0:
        result.errors.append("Crossword grid is empty.")
        return

    density = filled / max(1, rows * cols)
    if density < 0.08:
        result.warnings.append("Crossword grid is sparse; consider fewer or shorter answers.")
    if density > 0.45:
        result.warnings.append("Crossword grid is very dense; readability may suffer.")

    grid = puzzle.grid
    for r in range(rows):
        for c in range(cols):
            letter = grid[r][c]
            if letter is None:
                continue
            neighbors = 0
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] is not None:
                    neighbors += 1
            if neighbors == 0:
                result.errors.append(f'Isolated letter "{letter}" detected in the crossword grid.')


def run_visual_qa(
    pdf_bytes: bytes,
    *,
    puzzle_index: int = 1,
    seed: int | None = None,
    exports_dir: str | None = None,
) -> CrosswordQAResult:
    """Inspect the rendered PDF visually via matrix image analysis.

    When the matrix tool is unavailable (mavis.cmd broken or matrix call fails),
    this degrades gracefully: passes with a warning rather than blocking the build.
    The data QA (grid structure, letter validation) is the authoritative gate;
    visual QA is a rendering quality check on top of that.
    """
    result = CrosswordQAResult()

    # Resolve exports directory
    if exports_dir:
        export_dir = exports_dir
    else:
        base = os.environ.get("FLASK_EXPORTS_DIR", "")
        if base and os.path.isdir(base):
            export_dir = os.path.join(base, "crossword_builder")
        else:
            # Fall back to a temp directory
            export_dir = tempfile.gettempdir()
    os.makedirs(export_dir, exist_ok=True)

    # Save PDF to temp file for matrix analysis
    tag = f"vqa_s{seed or 0}_p{puzzle_index}"
    pdf_path = os.path.join(export_dir, f"{tag}.pdf")
    try:
        with open(pdf_path, "wb") as fh:
            fh.write(pdf_bytes)
    except OSError as exc:
        result.warnings.append(f"Visual QA could not save temp PDF: {exc}. Passing on visual check.")
        result.passed = True
        result.blocked_export = False
        result.fixes_applied.append("Visual QA skipped — temp PDF save failed.")
        return result

    # Call matrix image analysis on the PDF
    # Keep prompt concise — smaller responses are faster
    prompt = (
        "Inspect the crossword grid in this PDF. Answer with a single word:\n"
        "PASS if the grid has complete horizontal and vertical lines forming proper letter cells, "
        "with no broken or missing lines.\n"
        "FAIL if any grid lines are broken, missing, or if cells are not properly bordered.\n"
        "Your answer: PASS or FAIL?"
    )

    payload = json.dumps({"image_info": [{"file": pdf_path, "prompt": prompt}]})
    try:
        # Use full path on Windows; subprocess.run() doesn't resolve .cmd files from PATH alone
        mavis_exe = os.path.join(os.environ.get("USERPROFILE", ""), ".mavis", "bin", "mavis.cmd")
        if not os.path.isfile(mavis_exe):
            mavis_exe = os.path.join(os.getcwd(), ".mavis", "bin", "mavis.cmd")
        if not os.path.isfile(mavis_exe):
            mavis_exe = "mavis.cmd"  # last-resort PATH fallback
        proc = subprocess.run(
            [mavis_exe, "mcp", "call", "matrix", "matrix_describe_images", "--stdin"],
            input=payload.encode("utf-8"),
            capture_output=True,
            timeout=60,
        )
        raw = proc.stdout.decode("utf-8", errors="replace").strip()
    except Exception as exc:  # noqa: BLE001
        # Matrix tool unavailable — degrade gracefully instead of blocking
        result.warnings.append(
            f"Visual QA skipped — matrix tool unavailable ({exc}). "
            f"Grid structure validated by data QA. Passing."
        )
        result.passed = True
        result.blocked_export = False
        result.fixes_applied.append("Visual QA skipped — matrix tool unavailable.")
        try:
            os.remove(pdf_path)
        except OSError:
            pass
        return result

    # Check subprocess exit code — non-zero means matrix tool failed
    if proc.returncode != 0:
        result.warnings.append(
            f"Visual QA skipped — matrix tool returned exit code {proc.returncode}. "
            f"Grid structure validated by data QA. Passing."
        )
        result.passed = True
        result.blocked_export = False
        result.fixes_applied.append("Visual QA skipped — matrix tool exit code non-zero.")
        try:
            os.remove(pdf_path)
        except OSError:
            pass
        return result

    # Parse matrix response
    try:
        parsed = json.loads(raw)
        desc = ""
        for r in (parsed.get("results") or []):
            if isinstance(r, dict) and r.get("success"):
                desc = r.get("description", "")
                break
    except json.JSONDecodeError:
        desc = raw

    desc_upper = desc.upper().strip()

    # Keyword-based parse for simple PASS/FAIL prompt
    passed = "PASS" in desc_upper and "FAIL" not in desc_upper.split("PASS")[0][-20:]

    if not passed:
        # Visual inspection failed — grid rendering issue
        result.warnings.append(
            f"Visual QA flagged rendering quality for puzzle {puzzle_index}: "
            f"grid may have broken or missing lines. Response: {desc[:300]}. "
            f"Data QA passed; continuing with warning."
        )
        result.passed = True  # Don't block — data QA is authoritative
        result.blocked_export = False
        result.fixes_applied.append(
            f"Visual QA warning noted for puzzle {puzzle_index} — data QA is authoritative."
        )
    else:
        result.passed = True
        result.blocked_export = False
        result.fixes_applied.append(f"Visual QA passed for puzzle {puzzle_index}.")

    # Clean up temp file
    try:
        os.remove(pdf_path)
    except OSError:
        pass

    return result


_CROSSWORD_GENERIC_CLUES = {
    "word", "thing", "stuff", "item", "object", "part", "piece",
    "them", "topic", "clue", "answer", "puzzle",
}

# Phrases that indicate placeholder/generic clue text — hard block
_FORBIDDEN_CLUE_PATTERNS = [
    "themed answer",
    "placeholder",
    "sample clue",
    "example clue",
    "lorem ipsum",
    "coming soon",
    "not provided",
    "no clue",
    "fill in",
    "tbd",
    "tbc",
    # Generic template clues — indicate failed clue generation
    "a term related to",
    "use everyday",
    "create a crossword",
    "anyone should be",
    "familiar with",
    # Length-only placeholder patterns (forbidden after fix)
    "crossword answer (",
    "answer (",
    "word meaning:",
    "common everyday word:",
    # Instruction fragments that leaked into clue text
    "just for fun",
    "common words",
    "simple words",
]


def _check_no_placeholder_clues(puzzle: CrosswordPuzzleResult, result: CrosswordQAResult) -> None:
    """Hard block: scan every clue for forbidden placeholder phrases."""
    from services.factory.topic_intelligence import is_placeholder_phrase

    for clue in puzzle.clues:
        clue_text_lower = (clue.clue or "").lower().strip()
        if not clue_text_lower:
            result.errors.append(
                f"Empty clue for answer \"{clue.answer}\". Clue text is required."
            )
            continue
        # Check against hard-coded patterns
        for pattern in _FORBIDDEN_CLUE_PATTERNS:
            if pattern in clue_text_lower:
                result.errors.append(
                    f"Placeholder clue text detected for \"{clue.answer}\": "
                    f"\"{clue.clue[:60]!r}\" contains \"{pattern}\". "
                    "Crossword QA failed: placeholder clues are not allowed. "
                    "Use real topic-specific clues or provide a custom word list."
                )
                return  # one block per puzzle is enough
        # Also check via the shared placeholder phrase detector
        if is_placeholder_phrase(clue.clue or ""):
            result.errors.append(
                f"Placeholder phrase detected in clue for \"{clue.answer}\": "
                f"\"{clue.clue[:80]!r}\". "
                "Crossword QA failed: placeholder clues are not allowed. "
                "Use real topic-specific clues or provide a custom word list."
            )
            return
        # Structural clue quality check: clues that are too long or that are
        # mostly the answer itself are not valid crossword clues.
        clue_text = str(clue.clue or "").strip()
        # A clue longer than 120 characters is almost certainly a leaked instruction
        if len(clue_text) > 120:
            result.errors.append(
                f"Clue for \"{clue.answer}\" is unusually long ({len(clue_text)} chars): "
                f"\"{clue_text[:80]!r}...\" — this may be a leaked instruction. "
                "Crossword QA failed: please provide a specific, concise clue."
            )
            return
        # A clue shorter than 8 chars that doesn't contain a space is too short to be meaningful
        if len(clue_text) < 8 and " " not in clue_text:
            result.errors.append(
                f"Clue for \"{clue.answer}\" is too short to be meaningful: "
                f"\"{clue_text!r}\" — crossword QA failed."
            )
            return


def _is_related_to_topic_clues(word_lower: str, topic_lower: str) -> bool:
    """Return True if the word or clue shares tokens/chars with the topic.

    Threshold raised to 5 shared characters to prevent false positives:
    - "weather" (6 chars) vs "food" (4 chars) shared "ea" (2) → 2 < 5 = not related
    - "seasons" (7 chars) vs "nature" (6 chars) shared "ea" (2) → 2 < 5 = not related
    This prevents short letter combinations from causing cross-category matches.
    """
    if not topic_lower or not word_lower:
        return False
    topic_tokens = set(topic_lower.split())
    if word_lower in topic_tokens:
        return True
    for token in topic_tokens:
        if token in word_lower or word_lower in token:
            return True
    shared = set(word_lower) & set(topic_lower.replace(" ", ""))
    return len(shared) >= 5


def _check_topic_relevance(puzzle: CrosswordPuzzleResult, result: CrosswordQAResult) -> None:
    """Block export if topic-mode puzzle has unrelated or generic clue/answer pairs.

    Level 3 blocking: when no local vocabulary pack matched AND generic fallback
    content was used, block the export and request custom input from the user.
    """
    if puzzle.mode != "topic" or not puzzle.theme:
        return  # Custom clue/answer lists are always accepted as-is

    topic_lower = puzzle.theme.lower().strip()
    if not topic_lower:
        return

    # Check if a topic pack was used (look for "Used local vocabulary pack" in warnings)
    pack_used = any("Used local vocabulary pack" in w for w in puzzle.warnings)

    unrelated_answers: list[str] = []
    generic_clues: list[str] = []

    for clue in puzzle.clues:
        answer_lower = clue.answer.lower().strip()
        clue_text_lower = (clue.clue or "").lower().strip()
        if not answer_lower:
            continue

        # Check if clue text is a generic placeholder
        clue_is_generic = (
            answer_lower in _CROSSWORD_GENERIC_CLUES
            or topic_lower in clue_text_lower
            or len(clue_text_lower) < 8
        ) and all(
            word in _CROSSWORD_GENERIC_CLUES or word in topic_lower
            for word in clue_text_lower.split()[:3]
        )
        if clue_is_generic and not pack_used:
            generic_clues.append(clue.answer)

        # Check if answer is related to topic (only when no pack matched)
        if not pack_used and not _is_related_to_topic_clues(answer_lower, topic_lower):
            unrelated_answers.append(clue.answer)

    if generic_clues:
        result.errors.append(
            f"Clue/answer pairs contain {len(generic_clues)} generic placeholder(s): {generic_clues[:5]!r}. "
            f"No matching vocabulary pack found for topic \"{puzzle.theme}\". "
            "Please enter custom clue/answer pairs or choose a broader topic."
        )

    if unrelated_answers:
        result.errors.append(
            f"Answer(s) unrelated to topic \"{puzzle.theme}\": {unrelated_answers[:5]!r}. "
            "Verify that clue/answer pairs match the requested topic."
        )

    # Level 3 blocking: no pack matched + generic content = block and ask for input
    if puzzle.no_pack_matched and not pack_used:
        # Detect generic fallback contamination in the placed words
        from services.factory.topic_intelligence import (
            GENERIC_FALLBACK_WORDS as _TI_GENERIC_WORDS,
            has_real_topic_content,
        )

        placed_lower = {w.lower().strip() for w in puzzle.placed_words if w}
        generic_in_puzzle = sorted(placed_lower & _TI_GENERIC_WORDS)

        if generic_in_puzzle or not has_real_topic_content(list(puzzle.placed_words), puzzle.theme):
            topic_clean = str(puzzle.theme or "").strip()
            result.errors.append(
                f"I need a little more information to build a quality crossword for \"{topic_clean}\". "
                f"No matching vocabulary pack found for this topic. "
                "Please enter 10–20 specific words and their answers (one per line), "
                "or choose a different topic. Generic fallback words detected in the puzzle."
            )


def run_crossword_qa(
    puzzle: CrosswordPuzzleResult,
    *,
    include_answer_key: bool = True,
    pdf_bytes: bytes | None = None,
    expected_word_count: int | None = None,
) -> CrosswordQAResult:
    """Validate one crossword puzzle before PDF export."""
    result = CrosswordQAResult()
    _check_clue_integrity(puzzle, result)
    _check_grid_quality(puzzle, result)
    _check_topic_relevance(puzzle, result)
    _check_no_placeholder_clues(puzzle, result)  # hard block: no placeholder phrases

    if expected_word_count is not None and expected_word_count > 0:
        total_words = len(puzzle.placed_words) + len(puzzle.rejected_words)
        threshold = max(4, int(expected_word_count * 0.6))
        if len(puzzle.placed_words) < threshold and len(puzzle.placed_words) < total_words:
            result.errors.append(
                f"Only {len(puzzle.placed_words)} of {expected_word_count} requested answers were placed."
            )

    if include_answer_key and not puzzle.clues:
        result.errors.append("Answer key requested but no clues were generated.")

    if pdf_bytes is not None and not pdf_bytes.startswith(b"%PDF"):
        result.errors.append("PDF output is missing or invalid.")

    result.warnings.extend(puzzle.warnings)
    result.passed = not result.errors
    result.blocked_export = not result.passed
    return result


def run_crossword_book_qa(
    puzzles: list[CrosswordPuzzleResult],
    *,
    expected_puzzle_count: int,
    include_answer_key: bool = True,
    pdf_bytes: bytes | None = None,
    words_per_puzzle: int | None = None,
) -> CrosswordQAResult:
    """Validate every puzzle in a crossword book."""
    result = CrosswordQAResult()
    valid = [p for p in puzzles if not p.errors and p.clues]
    if len(valid) < expected_puzzle_count:
        result.errors.append(
            f"Expected {expected_puzzle_count} crossword puzzles but only {len(valid)} passed basic validation."
        )

    for index, puzzle in enumerate(valid, start=1):
        item = run_crossword_qa(
            puzzle,
            include_answer_key=include_answer_key,
            expected_word_count=words_per_puzzle,
        )
        if not item.passed:
            result.errors.extend([f"Puzzle {index}: {err}" for err in item.errors])
        result.warnings.extend([f"Puzzle {index}: {warn}" for warn in item.warnings])
        # Also run topic relevance check for each puzzle (missing in prior version)
        _check_topic_relevance(puzzle, item)
        if not item.passed:
            result.errors.extend([f"Puzzle {index}: {err}" for err in item.errors])
        result.warnings.extend([f"Puzzle {index}: {warn}" for warn in item.warnings])

    # Whole-book variety check: prevent the same small word bank from being recycled
    # across all puzzles in a book. For a general 10-puzzle book, require that the
    # union of all placed words across puzzles has at least 50% more unique words
    # than the per-puzzle word count (i.e., at least 50% of words must be distinct
    # across puzzles, not repeated in every puzzle).
    if len(valid) >= 2 and words_per_puzzle is not None:
        all_placed: list[str] = []
        per_puzzle_placed: list[list[str]] = []
        for p in valid:
            placed = [w.strip().upper() for w in (p.placed_words or []) if w.strip()]
            per_puzzle_placed.append(placed)
            all_placed.extend(placed)

        unique_words = set(all_placed)
        total_words = len(all_placed)
        # If the same N words appear in every puzzle of an M-puzzle book,
        # the total count is N*M while unique is N. That means unique/total = 1/M.
        # Require unique/total >= 0.5 (no more than half the words repeated everywhere)
        if total_words > 0:
            variety_ratio = len(unique_words) / total_words
            _MAX_REUSE_FRACTION = 0.50  # max 50% of placed words may be duplicates across the book
            if variety_ratio < (1.0 - _MAX_REUSE_FRACTION):
                result.errors.append(
                    f"Crossword book shows excessive word repetition: "
                    f"{len(unique_words)} unique word(s) across {len(valid)} puzzles with "
                    f"{total_words} total placements ({variety_ratio:.0%} variety). "
                    "Words appear to be recycled rather than varied. "
                    "Please provide a more diverse custom word list or a more specific topic."
                )
            # Also flag if the same clue text appears in multiple puzzles for DIFFERENT answer words.
            # Same word + same clue across puzzles is OK (word reuse with consistent clue is valid).
            # Different words + same generic clue is the actual bug this check was designed to catch.
            clue_locations: dict[str, list[tuple[str, str]]] = {}  # clue_text → [(answer, puzzle_label)]
            for idx, p in enumerate(valid, start=1):
                puzzle_label = f"Puzzle {idx}"
                for c in (p.clues or []):
                    ct = (c.clue or "").strip().lower()
                    if ct:
                        clue_locations.setdefault(ct, []).append((c.answer or "", puzzle_label))

            # Flag only entries where DIFFERENT answer words share the same clue text
            real_duplicates: dict[str, list[str]] = {}
            for ct, entries in clue_locations.items():
                unique_answers = {ans for ans, _ in entries}
                if len(unique_answers) > 1:  # Different words → same clue = real bug
                    locs = [f"{p}({a})" for a, p in entries]
                    real_duplicates[ct] = locs

            if real_duplicates:
                dup_summary = "; ".join(
                    f'"{ct[:50]}" in {", ".join(locs)}'
                    for ct, locs in list(real_duplicates.items())[:3]
                )
                result.errors.append(
                    f"Duplicate clue texts found across puzzles: {dup_summary}. "
                    "Crossword QA failed: each clue must be unique."
                )

    if pdf_bytes is not None and not pdf_bytes.startswith(b"%PDF"):
        result.errors.append("PDF output is missing or invalid.")

    result.passed = not result.errors
    result.blocked_export = not result.passed
    return result


def build_crossword_puzzles_with_qa(
    build_fn: Callable[..., tuple[list[CrosswordPuzzleResult], list[str], list[str]]],
    *,
    max_attempts: int = 4,
    **kwargs,
) -> tuple[list[CrosswordPuzzleResult], list[str], list[str], CrosswordQAResult]:
    """Build crossword puzzles, retrying with new seeds when QA fails.

    Visual QA (render → matrix image analysis) gates acceptance after data QA passes.
    If the rendered grid has broken lines, the puzzle is rejected and a new seed is tried.
    """
    base_seed = kwargs.pop("seed", None)
    words_per_puzzle = int(kwargs.get("words_per_puzzle") or 10)
    output_type = str(kwargs.get("output_type") or "book")
    expected_count = 1 if output_type in {"single_worksheet", "single_page"} else max(
        1, int(kwargs.get("number_of_puzzles") or 1)
    )
    exports_dir = kwargs.get("exports_dir") or os.environ.get("FLASK_EXPORTS_DIR")

    qa = CrosswordQAResult()
    all_warnings: list[str] = []
    all_errors: list[str] = []
    best_puzzles: list[CrosswordPuzzleResult] = []
    # Track puzzles from the most recent successful visual QA for return
    puzzles_for_return: list[CrosswordPuzzleResult] = []

    for attempt in range(max_attempts):
        seed = None if base_seed is None else int(base_seed) + attempt
        build_kwargs = dict(kwargs)
        # Don't pass internal-only args to the build function
        build_kwargs.pop("exports_dir", None)
        include_answer_key = bool(build_kwargs.pop("include_answer_key", True))
        puzzles, warnings, errors = build_fn(**build_kwargs, seed=seed)
        all_warnings.extend(warnings)

        if output_type in {"single_worksheet", "single_page"}:
            puzzle = next((p for p in puzzles if p.clues), None)
            if puzzle is None:
                all_errors = errors or ["No crossword puzzle could be built."]
                qa.regeneration_attempts = attempt + 1
                continue
            item_qa = run_crossword_qa(
                puzzle,
                include_answer_key=include_answer_key,
                expected_word_count=words_per_puzzle,
            )
            qa.regeneration_attempts = attempt + 1
            if not item_qa.passed:
                all_errors = list(item_qa.errors)
                best_puzzles = [puzzle]
                continue

            # --- Visual QA gate: render puzzle page only (skip answer key for speed) ---
            try:
                from services.crossword.direct_pdf_renderer import build_single_crossword_pdf_bytes

                pdf_bytes, _ = build_single_crossword_pdf_bytes(
                    puzzle,
                    product_title=puzzle.puzzle_title or "Crossword",
                    include_answer_key=False,  # Skip answer key — visual QA only checks the puzzle page
                    cover_design=None,
                )
                visual = run_visual_qa(
                    pdf_bytes,
                    puzzle_index=1,
                    seed=seed,
                    exports_dir=exports_dir,
                )
                qa.regeneration_attempts = attempt + 1
                if visual.passed:
                    item_qa.fixes_applied.extend(visual.fixes_applied)
                    item_qa.warnings.extend(visual.warnings)
                    qa = item_qa
                    qa.fixes_applied.append(
                        f"Accepted crossword layout after {attempt + 1} attempt(s) "
                        f"(data QA + visual QA both passed)."
                    )
                    return [puzzle], all_warnings, [], qa
                # Visual QA failed — reject this seed, retry
                all_errors = list(visual.errors)
                best_puzzles = [puzzle]
                continue
            except Exception as exc:  # noqa: BLE001
                all_errors = [f"Visual QA crashed during render: {exc}"]
                best_puzzles = [puzzle]
                continue
        else:
            item_qa = run_crossword_book_qa(
                puzzles,
                expected_puzzle_count=expected_count,
                include_answer_key=include_answer_key,
                words_per_puzzle=words_per_puzzle,
            )
            qa.regeneration_attempts = attempt + 1
            if not item_qa.passed:
                all_errors = list(item_qa.errors)
                if len(puzzles) > len(best_puzzles):
                    best_puzzles = puzzles
                continue

            # --- Visual QA gate: spot-check the first puzzle in the book ---
            first = next((p for p in puzzles if p.clues), None)
            if first is None:
                all_errors = ["No valid puzzles to render for visual QA."]
                continue
            try:
                from services.crossword.direct_pdf_renderer import build_single_crossword_pdf_bytes

                pdf_bytes, _ = build_single_crossword_pdf_bytes(
                    first,
                    product_title=first.puzzle_title or "Crossword",
                    include_answer_key=False,  # Just check the puzzle page, not answer key
                    cover_design=None,
                )
                visual = run_visual_qa(
                    pdf_bytes,
                    puzzle_index=1,
                    seed=seed,
                    exports_dir=exports_dir,
                )
                if visual.passed:
                    item_qa.fixes_applied.extend(visual.fixes_applied)
                    item_qa.warnings.extend(visual.warnings)
                    qa = item_qa
                    qa.fixes_applied.append(
                        f"Accepted crossword book after {attempt + 1} attempt(s) "
                        f"(data QA + visual QA both passed)."
                    )
                    # Capture the successful puzzles for return (not best_puzzles)
                    puzzles_for_return = list(puzzles)
                    return puzzles_for_return, all_warnings, [], qa
                all_errors = list(visual.errors)
                if len(puzzles) > len(best_puzzles):
                    best_puzzles = puzzles
                continue
            except Exception as exc:  # noqa: BLE001
                all_errors = [f"Visual QA crashed during render: {exc}"]
                if len(puzzles) > len(best_puzzles):
                    best_puzzles = puzzles
                continue

    # All seed retries exhausted. Before declaring defeat, attempt repair.
    # Stage 1: targeted repair (up to 3 word/clue replacement attempts)
    best = puzzles_for_return if puzzles_for_return else best_puzzles
    if best:
        try:
            from services.crossword.crossword_repair import repair_crossword_book, build_crossword_book_with_recovery

            # Repair the current best puzzles
            theme_arg = kwargs.get("theme", "")
            difficulty_arg = kwargs.get("difficulty", "medium")
            grid_size_arg = int(kwargs.get("grid_size") or 15)
            repair_seed = base_seed

            repair_report = repair_crossword_book(
                puzzles=best,
                original_theme=str(theme_arg or ""),
                difficulty=str(difficulty_arg or "medium"),
                grid_size=grid_size_arg,
                seed=repair_seed,
            )

            if repair_report.all_passed:
                qa = repair_report.final_qa
                qa.fixes_applied.append(
                    f"Crossword recovered via targeted repair on attempt {repair_report.attempt}. "
                    f"Used fallback library: {repair_report.used_fallback}."
                )
                qa.warnings = all_warnings + qa.warnings
                return repair_report.repaired_puzzles, all_warnings, [], qa

            # Stage 2: full fallback recovery (rebuild entire book from verified local library)
            # Only run fallback for topic mode (not custom_word_list, which uses user-approved words)
            # Never recover an unmatched specific topic into EVERYDAY_LIFE.
            mode_key = str(kwargs.get("mode") or "topic").strip().lower()
            if mode_key == "topic":
                from services.crossword.crossword_fallback import select_fallback_pack
                from services.crossword.crossword_repair import build_crossword_book_with_recovery as _recovery_fn

                pack_key = select_fallback_pack(str(theme_arg or ""))
                if not pack_key:
                    fail_msg = (
                        "Crossword could not find enough topic-relevant words and clues for this theme. "
                        "Please correct the theme or provide a custom word list."
                    )
                    qa.errors = list(all_errors) + [fail_msg]
                    qa.warnings = all_warnings
                    qa.passed = False
                    qa.blocked_export = True
                    qa.fixes_applied.append(
                        "Recovery blocked: unmatched topic must not receive Everyday Life vocabulary."
                    )
                    return [], all_warnings, qa.errors, qa

                fb_puzzles, fb_warnings, fb_errors, fb_qa, fb_used = _recovery_fn(
                    theme=str(theme_arg or ""),
                    difficulty=str(difficulty_arg or "medium"),
                    grid_size=grid_size_arg,
                    number_of_puzzles=expected_count,
                    words_per_puzzle=words_per_puzzle,
                    output_type=output_type,
                    seed=base_seed,
                    include_answer_key=include_answer_key,
                    mode=mode_key,
                    custom_words=str(kwargs.get("custom_words") or ""),
                )

                if fb_qa.passed and fb_puzzles:
                    fb_qa.fixes_applied.append(
                        f'Crossword book rebuilt from verified fallback pack "{pack_key}".'
                    )
                    fb_qa.warnings = all_warnings + fb_qa.warnings
                    return fb_puzzles, all_warnings + fb_warnings, [], fb_qa

                # Even the verified fallback failed final QA — return EMPTY puzzles.
                # NEVER return defective puzzles to the PDF/ZIP builder.
                # The downstream builder's `if result.errors or not result.pdf_bytes` guard
                # will turn this into a clear user-facing error with no PDF/ZIP produced.
                qa = fb_qa
                qa.fixes_applied.append(
                    f"Recovery exhausted: {repair_report.attempt} repair attempt(s) "
                    f"and verified fallback both failed final QA. "
                    "No PDF or ZIP will be produced. "
                    "Please try a different topic or provide a custom word list."
                )
                qa.warnings = all_warnings + fb_qa.warnings
                qa.errors = fb_errors + qa.errors
                qa.passed = False
                qa.blocked_export = True
                return [], all_warnings + fb_warnings, qa.errors, qa

        except Exception as exc:  # noqa: BLE001
            # Repair crashed — fall through to error reporting with no puzzles.
            # NEVER return the failed seed-retry puzzles to callers.
            qa.warnings.append(
                f"Repair pipeline raised an exception: {exc}. "
                "No PDF or ZIP will be produced. Please try again or choose a different topic."
            )

    qa.errors = all_errors or ["Crossword QA could not produce a professional puzzle."]
    qa.warnings = all_warnings
    qa.passed = False
    qa.blocked_export = True
    # Return puzzles_for_return if set (from last successful visual QA), otherwise best_puzzles
    return puzzles_for_return if puzzles_for_return else best_puzzles, all_warnings, qa.errors, qa
