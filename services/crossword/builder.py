"""Crossword puzzle assembly — separate from Word Search builder."""
from __future__ import annotations

from dataclasses import dataclass, field

from services.crossword.clues import generate_clues_for_words  # generate_clues_from_ai removed: crossword is fully local
from services.crossword.engine import CrosswordBuildResult, CrosswordClueEntry, build_crossword_grid, normalize_grid_size
from services.crossword.word_entries import CrosswordEntry, parse_crossword_word_list, suggest_crossword_words_from_topic


@dataclass
class CrosswordPuzzleResult:
    puzzle_title: str
    grid: list[list[str | None]]
    clues: list[CrosswordClueEntry]
    placed_words: list[str]
    rejected_words: list[str]
    difficulty: str
    grid_size: int
    theme: str = ""
    mode: str = ""  # "topic" or "custom_list"
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    no_pack_matched: bool = False  # True when no local vocabulary pack matched the topic

    def as_dict(self) -> dict:
        return {
            "puzzle_title": self.puzzle_title,
            "grid": self.grid,
            "clues": [c.as_dict() for c in self.clues],
            "placed_words": self.placed_words,
            "rejected_words": self.rejected_words,
            "difficulty": self.difficulty,
            "grid_size": self.grid_size,
            "theme": self.theme,
            "mode": self.mode,
            "warnings": self.warnings,
            "errors": self.errors,
            "no_pack_matched": self.no_pack_matched,
        }


def _normalize_difficulty(value: str) -> str:
    lowered = str(value or "medium").strip().lower()
    return lowered if lowered in {"easy", "medium", "hard"} else "medium"


def build_crossword_from_entries(
    entries: list[CrosswordEntry],
    *,
    puzzle_title: str,
    theme: str,
    difficulty: str,
    grid_size: int | str,
    clues_map: dict[str, str] | None = None,
    seed: int | None = None,
) -> CrosswordPuzzleResult:
    answers = [entry.answer for entry in entries]
    clues = clues_map or generate_clues_for_words(answers, theme=theme)
    build: CrosswordBuildResult = build_crossword_grid(
        answers,
        clues,
        grid_size=grid_size,
        seed=seed,
    )
    return CrosswordPuzzleResult(
        puzzle_title=puzzle_title,
        grid=build.grid,
        clues=build.clues,
        placed_words=build.placed_words,
        rejected_words=build.rejected_words,
        difficulty=_normalize_difficulty(difficulty),
        grid_size=normalize_grid_size(grid_size),
        theme=theme,
        mode="custom_list",
        warnings=list(build.warnings),
        errors=list(build.errors),
    )


def build_crossword_from_custom_list(
    raw_words: str,
    *,
    puzzle_title: str,
    theme: str,
    difficulty: str,
    grid_size: int | str,
    clues_map: dict[str, str] | None = None,
    seed: int | None = None,
) -> CrosswordPuzzleResult:
    size = normalize_grid_size(grid_size)
    parsed = parse_crossword_word_list(raw_words, max_word_len=size)
    if parsed.errors:
        return CrosswordPuzzleResult(
            puzzle_title=puzzle_title,
            grid=[[None] * size for _ in range(size)],
            clues=[],
            placed_words=[],
            rejected_words=parsed.rejected,
            difficulty=_normalize_difficulty(difficulty),
            grid_size=size,
            theme=theme,
            mode="custom_list",
            warnings=parsed.warnings,
            errors=parsed.errors,
        )
    if not clues_map:
        clues_map = generate_clues_for_words([e.answer for e in parsed.entries], theme=theme)
    result = build_crossword_from_entries(
        parsed.entries,
        puzzle_title=puzzle_title,
        theme=theme,
        difficulty=difficulty,
        grid_size=size,
        clues_map=clues_map,
        seed=seed,
    )
    result.warnings = parsed.warnings + result.warnings
    return result


def build_crossword_from_topic(
    *,
    puzzle_title: str,
    theme: str,
    sub_topic: str = "",
    difficulty: str,
    grid_size: int | str,
    words_per_puzzle: int,
    use_ai_words: bool = False,
    seed: int | None = None,
) -> CrosswordPuzzleResult:
    size = normalize_grid_size(grid_size)
    count = max(6, int(words_per_puzzle or 10))
    warnings: list[str] = []
    errors: list[str] = []

    # Word selection: sub_topic is primary, theme is fallback
    # Try sub_topic first (most specific), then theme, then combined
    primary_topic = sub_topic.strip() if sub_topic else ""
    fallback_topic = theme.strip() if theme else ""
    combined_topic = f"{fallback_topic} {primary_topic}".strip()
    suggested: list[str] = []

    if use_ai_words:
        # Try sub_topic first, then theme, then combined
        if primary_topic:
            suggested, w, e = suggest_crossword_words_from_topic(primary_topic, max_words=count)
            warnings.extend(w)
            errors.extend(e)
        if not primary_topic or not suggested:
            search_term = fallback_topic if (not primary_topic and suggested) else (
                combined_topic if not suggested else ""
            )
            if search_term:
                s2, w2, e2 = suggest_crossword_words_from_topic(search_term, max_words=count)
                suggested = s2
                warnings.extend(w2)
                errors.extend(e2)
        if suggested:
            entries = [CrosswordEntry(display=a, answer=a) for a in suggested]
        else:
            try:
                from services.crossword.word_entries import fetch_crossword_words_from_ai
                raw = fetch_crossword_words_from_ai(primary_topic or fallback_topic, count)
                parsed = parse_crossword_word_list(raw, max_word_len=size)
                entries = parsed.entries
                warnings.extend(parsed.warnings)
                errors.extend(parsed.errors)
                if entries:
                    warnings.append(f"Used AI-generated vocabulary for \"{primary_topic or fallback_topic}\".")
            except Exception:
                pass
    else:
        # Try sub_topic first (most specific)
        if primary_topic:
            suggested, w, e = suggest_crossword_words_from_topic(primary_topic, max_words=count)
            warnings.extend(w)
            errors.extend(e)
        # If sub_topic found nothing, try theme
        if not suggested:
            suggested, w, e = suggest_crossword_words_from_topic(fallback_topic, max_words=count)
            warnings.extend(w)
            errors.extend(e)
        # If still nothing, try combined
        if not suggested:
            suggested, w, e = suggest_crossword_words_from_topic(combined_topic, max_words=count)
            warnings.extend(w)
            errors.extend(e)
        parsed = parse_crossword_word_list("\n".join(suggested), max_word_len=size)
        entries = parsed.entries
        warnings.extend(parsed.warnings)
        errors.extend(parsed.errors)

    if errors or not entries:
        return CrosswordPuzzleResult(
            puzzle_title=puzzle_title,
            grid=[[None] * size for _ in range(size)],
            clues=[],
            placed_words=[],
            rejected_words=[],
            difficulty=_normalize_difficulty(difficulty),
            grid_size=size,
            theme=theme,
            mode="topic",
            warnings=warnings,
            errors=errors or [f"Could not build crossword vocabulary for \"{combined_topic}\"."],
            no_pack_matched=True,
        )

    # Detect whether a real vocabulary pack was matched
    pack_matched = any("Used local vocabulary pack" in w for w in warnings)
    no_pack_matched = not pack_matched

    answers = [entry.answer for entry in entries[:count]]
    # Clues: use local rule-based clue builder — no placeholder phrases, no OpenAI.
    clue_topic = primary_topic or fallback_topic or combined_topic
    clues_map = generate_clues_for_words(answers, theme=clue_topic)

    result = build_crossword_from_entries(
        [CrosswordEntry(display=a, answer=a) for a in answers],
        puzzle_title=puzzle_title,
        theme=theme,
        difficulty=difficulty,
        grid_size=size,
        clues_map=clues_map,
        seed=seed,
    )
    result.warnings = warnings + result.warnings
    result.mode = "topic"
    result.no_pack_matched = no_pack_matched
    return result
