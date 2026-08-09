import sys, traceback, json
sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')
import os
os.environ['FLASK_APP'] = 'app.py'

# Monkey-patch to catch RecursionError with full trace
_orig_build_grid = None

try:
    # Test the build_crossword_grid function directly with a word list that could cause deep recursion
    from services.crossword.engine import build_crossword_grid, _build_crossword_single_attempt, _blank_grid
    import random
    
    # Simulate what happens with many tiny words (golf-related)
    # Try with 20 tiny golf words
    words = ["GOLF", "TEE", "PAR", "PUTT", "CLUB", "IRON", "WOOD", "BALL", "BIRD", "EAGLE",
             "HOLE", "FLAG", "CUP", "BAG", "MITT", "GRIP", "SHAFT", "HEAD", "SOLE", "FACE"]
    
    rng = random.Random(42)
    # Test _build_crossword_single_attempt
    result = _build_crossword_single_attempt(words, {}, 15, rng)
    print(f"Single attempt: placed={len(result.placed_words)}, rejected={len(result.rejected_words)}")
    
    # Test build_crossword_grid (with the iterative fix)
    result2 = build_crossword_grid(words, {}, grid_size=11, seed=42)
    print(f"Grid build (size=11): placed={len(result2.placed_words)}")
    
    result3 = build_crossword_grid(words, {}, grid_size=9, seed=42)
    print(f"Grid build (size=9): placed={len(result3.placed_words)}")
    
    print("\nEngine test PASSED - no recursion error")
    
except RecursionError as e:
    print("RECURSION ERROR:")
    traceback.print_exc()
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    traceback.print_exc()
