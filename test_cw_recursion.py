import sys
sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')
from services.crossword.engine import build_crossword_grid

# Test with small golf-related words
words = ["GOLF", "PGA", "CLUB", "TEE", "BIRDIE", "PAR", "HOLE", "SWING", "BUNKER", "DRIVE"]
clues = {w: f"Related to golf ({len(w)} letters)" for w in words}

try:
    result = build_crossword_grid(words, clues, grid_size=15, seed=42)
    print(f"OK: placed={len(result.placed_words)}, rejected={len(result.rejected_words)}")
    print(f"Words placed: {result.placed_words}")
    if result.errors:
        print(f"Errors: {result.errors}")
except RecursionError as e:
    print(f"RecursionError: {e}")
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
