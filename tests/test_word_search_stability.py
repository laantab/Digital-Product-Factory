from services.word_search.book import build_word_search_puzzles
from services.word_search.answer_key_solver import solve_puzzle_answer_key


def test_custom_word_search_book_is_deterministic_and_solvable():
    words = "\n".join(
        [
            "apple", "banana", "cherry", "grape", "lemon",
            "mango", "orange", "papaya", "peach", "pear",
            "plum", "berry", "melon", "kiwi", "lime",
            "apricot", "fig", "guava", "coconut", "date",
        ]
    )
    kwargs = dict(
        mode="custom_word_list",
        product_title="Fruit Search",
        custom_words=words,
        difficulty="easy",
        grid_size=15,
        number_of_puzzles=2,
        words_per_puzzle=10,
        output_type="book",
        seed=417,
    )
    first, warnings, errors = build_word_search_puzzles(**kwargs)
    second, _, second_errors = build_word_search_puzzles(**kwargs)

    assert not errors
    assert not second_errors
    assert len(first) == 2
    assert [p.grid for p in first] == [p.grid for p in second]
    assert len({w.lower() for p in first for w in p.word_bank}) == 20
    for puzzle in first:
        solved = solve_puzzle_answer_key(puzzle)
        assert solved.ok, solved.errors
        assert len(solved.validated_paths) == len(puzzle.word_bank)
