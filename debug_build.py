"""Debug: trace crossword puzzle building to see where words go"""
import sys
sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')

from services.crossword.book import build_crossword_puzzles
from services.crossword.word_entries import parse_crossword_word_list
from services.crossword.engine import build_crossword_grid
from services.crossword.clues import generate_clues_for_words

custom_words_raw = "APPLE\nBANANA\nCHERRY\nGRAPE\nMANGO\nPEACH\nLEMON\nMELON\nPEAR\nPLUM"

print("=== STEP 1: Parse custom word list ===")
parsed = parse_crossword_word_list(custom_words_raw, max_word_len=15)
print(f"Entries: {[e.answer for e in parsed.entries]}")
print(f"Errors: {parsed.errors}")
print(f"Warnings: {parsed.warnings}")
print(f"Rejected: {parsed.rejected}")

answers = [e.answer for e in parsed.entries]
print(f"\n=== STEP 2: Generate clues ===")
clues = generate_clues_for_words(answers, theme="fruit")
print(f"Clues generated: {len(clues)}")
for k, v in list(clues.items())[:5]:
    print(f"  {k}: {v}")

print(f"\n=== STEP 3: Build crossword grid ===")
result = build_crossword_grid(answers, clues, grid_size=15)
print(f"Placed words: {result.placed_words}")
print(f"Rejected words: {result.rejected_words}")
print(f"Errors: {result.errors}")
print(f"Grid size: {len(result.grid)}x{len(result.grid[0])}")
print(f"Grid non-None cells: {sum(1 for row in result.grid for c in row if c)}")
print(f"Clue entries: {len(result.clues)}")
for clue in result.clues[:3]:
    print(f"  {clue.number}. {clue.direction} {clue.answer}: {clue.clue}")

print(f"\n=== STEP 4: Build full puzzles ===")
puzzles, warnings, errors = build_crossword_puzzles(
    mode="custom_word_list",
    product_title="Fruit World",
    custom_words=custom_words_raw,
    theme="fruit",
    difficulty="easy",
    grid_size=15,
    number_of_puzzles=1,
    words_per_puzzle=10,
    output_type="single_worksheet",
)
print(f"Puzzles: {len(puzzles)}")
print(f"Warnings: {warnings}")
print(f"Errors: {errors}")
if puzzles:
    p = puzzles[0]
    print(f"Puzzle placed words: {p.placed_words}")
    print(f"Puzzle rejected words: {p.rejected_words}")
    print(f"Puzzle clues: {len(p.clues)}")
    print(f"Puzzle grid sample (first 5 rows):")
    for row in p.grid[:5]:
        print(f"  {[c if c else '.' for c in row[:10]]}")
