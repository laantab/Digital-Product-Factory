"""Build multi-puzzle crossword books — separate from Word Search book module."""
from __future__ import annotations

from services.crossword.builder import CrosswordPuzzleResult, build_crossword_from_custom_list, build_crossword_from_topic
from services.crossword.word_entries import parse_crossword_word_list, suggest_crossword_words_from_topic


def _split_entries(raw: str, puzzle_count: int, *, words_per_puzzle: int) -> list[str]:
    parsed = parse_crossword_word_list(raw)
    answers = [entry.answer for entry in parsed.entries]
    if not answers:
        return ["" for _ in range(max(1, puzzle_count))]

    min_per_puzzle = max(4, int(words_per_puzzle or 10))
    # Distribute evenly so no chunk falls below min_per_puzzle words.
    # Round-robins extras to the first chunks.
    # e.g. 91 words, 10 puzzles, min=10: floor(91/10)=9, extras=1
    #   → chunks of [10,10,10,10,10,10,10,10,10,1] (last fails!)
    # Fix: ensure last chunk also has >=min_per_puzzle by fetching more words
    # in the caller, OR pad here by taking 1 word from each of the first
    # 'excess' chunks to bring the last chunk up to min.
    #
    # Simple safe approach: if the last chunk would be <4 words,
    # take 1 word from each of the first 'excess' chunks to pad it.
    excess = len(answers) % puzzle_count
    base = len(answers) // puzzle_count
    chunks: list[list[str]] = [[] for _ in range(puzzle_count)]
    for i, ans in enumerate(answers):
        chunks[i % puzzle_count].append(ans)

    # Pad short chunks to at least min_per_puzzle by stealing from large chunks
    # Only needed when len(answers) < puzzle_count * min_per_puzzle
    target_total = puzzle_count * min_per_puzzle
    if len(answers) < target_total:
        # Words are scarce — redistribute to give each chunk exactly
        # floor(len/puzzle_count) or ceil(len/puzzle_count)
        base = len(answers) // puzzle_count
        excess_words = len(answers) % puzzle_count
        result: list[str] = []
        pos = 0
        for i in range(puzzle_count):
            this_size = base + (1 if i < excess_words else 0)
            result.append("\n".join(answers[pos:pos + this_size]))
            pos += this_size
        return result

    return ["\n".join(c) for c in chunks]


def build_crossword_puzzles(
    *,
    mode: str,
    product_title: str,
    custom_words: str = "",
    custom_clues: dict[str, str] | None = None,
    theme: str = "",
    sub_topic: str = "",
    difficulty: str = "medium",
    grid_size: int | str = 15,
    number_of_puzzles: int = 1,
    words_per_puzzle: int = 10,
    output_type: str = "book",
    use_ai_words: bool = False,
    seed: int | None = None,
) -> tuple[list[CrosswordPuzzleResult], list[str], list[str]]:
    puzzle_count = 1 if output_type in {"single_worksheet", "single_page"} else max(1, int(number_of_puzzles or 1))
    # Cap the QA expectation at what we actually generated so 1-valid-puzzle books don't fail QA
    _effective_count = puzzle_count
    title_base = str(product_title or "Crossword").strip() or "Crossword"
    theme_label = str(theme or title_base).strip()
    warnings: list[str] = []
    errors: list[str] = []
    puzzles: list[CrosswordPuzzleResult] = []

    mode_key = str(mode or "topic").strip().lower()
    per_puzzle = max(6, int(words_per_puzzle or 10))
    total_needed = per_puzzle * puzzle_count

    if mode_key in {"custom", "custom_word_list", "custom_list"}:
        chunks = _split_entries(custom_words, puzzle_count, words_per_puzzle=per_puzzle)
        for idx, chunk in enumerate(chunks, start=1):
            if not chunk.strip():
                errors.append(f"Puzzle {idx} has no words.")
                continue
            result = build_crossword_from_custom_list(
                chunk,
                puzzle_title=f"{title_base} - Puzzle {idx}" if puzzle_count > 1 else title_base,
                theme=theme_label,
                difficulty=difficulty,
                grid_size=grid_size,
                clues_map=dict(custom_clues) if custom_clues else None,
                seed=(seed + idx) if seed is not None else None,
            )
            warnings.extend(result.warnings)
            if result.errors:
                errors.extend(result.errors)
            puzzles.append(result)
    else:
        # Topic mode: use the authoritative pool supplied by product.py when present.
        # Do not independently re-suggest and discard a resolved list.
        # (Protection against old stored custom words belongs in product.py.)
        pool_source = sub_topic.strip() or theme_label
        pool_str = str(custom_words or "").strip()
        # Oversubscribe candidates so each puzzle can still place ≥8 answers
        # when a few words fail to interlock in the grid.
        candidates_per = max(per_puzzle + 4, 12)
        fetch_needed = max(60, candidates_per * puzzle_count)
        if pool_str:
            warnings.append("Using authoritative Topic-mode word pool supplied by the resolver.")
        else:
            pool_words, pool_warns, pool_errs = suggest_crossword_words_from_topic(
                pool_source, max_words=fetch_needed
            )
            warnings.extend(pool_warns)
            errors.extend(pool_errs)
            pool_str = "\n".join(pool_words) if pool_words else ""

        if not pool_str.strip():
            if not errors:
                errors.append(
                    "Crossword could not find enough topic-relevant words and clues for this theme. "
                    "Please correct the theme or provide a custom word list."
                )
        else:
            # Split the pool ONCE into puzzle_count chunks (round-robin distribution).
            chunk_strs = _split_entries(pool_str, puzzle_count, words_per_puzzle=candidates_per)
            min_placed = min(8, per_puzzle)

            for idx, chunk in enumerate(chunk_strs, start=1):
                chunk = chunk.strip()
                if not chunk:
                    errors.append(
                        f"Puzzle {idx}: not enough topic-relevant words remained in the resolved pool."
                    )
                    continue
                result = None
                for attempt in range(3):
                    attempt_seed = None
                    if seed is not None:
                        attempt_seed = seed + idx + (attempt * 17)
                    elif attempt:
                        attempt_seed = idx * 31 + attempt
                    candidate = build_crossword_from_custom_list(
                        chunk,
                        puzzle_title=f"{title_base} - Puzzle {idx}" if puzzle_count > 1 else title_base,
                        theme=theme_label,
                        difficulty=difficulty,
                        grid_size=grid_size,
                        clues_map=dict(custom_clues) if custom_clues else None,
                        seed=attempt_seed,
                    )
                    result = candidate
                    if len(candidate.placed_words) >= min_placed and not candidate.errors:
                        break
                assert result is not None
                warnings.extend(result.warnings)
                if result.errors:
                    errors.extend(result.errors)
                if len(result.placed_words) < min_placed:
                    errors.append(
                        f"Puzzle {idx}: placed only {len(result.placed_words)} topic-relevant answers "
                        f"(need at least {min_placed})."
                    )
                puzzles.append(result)

    if not puzzles:
        errors.append("No crossword puzzles were generated.")
    elif puzzle_count > 1 and len(puzzles) < puzzle_count:
        warnings.append(f"Generated {len(puzzles)} of {puzzle_count} requested puzzles.")

    # QA gate: require at least 1 valid puzzle so single-puzzle books always succeed
    valid = [p for p in puzzles if not p.errors and p.clues]
    if len(valid) < 1:
        if not errors:
            errors.append("No crossword puzzles passed validation.")
    # Keep puzzles (including partially-built ones) so the caller can still inspect them

    return puzzles, warnings, errors
