import sys, traceback, json
sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')
import os
os.environ['FLASK_APP'] = 'app.py'

try:
    # Test the full crossword generation with proper word list
    from services.crossword.word_entries import suggest_crossword_words_from_topic, parse_crossword_word_list
    from services.crossword.engine import build_crossword_grid, _build_crossword_single_attempt
    import random
    
    topic = "golf"
    words, warnings, errors = suggest_crossword_words_from_topic(topic, max_words=20)
    print(f"Words from topic '{topic}': {len(words)}")
    print(f"Words: {words}")
    print(f"Warnings: {warnings}")
    print(f"Errors: {errors}")
    
    if words:
        # Test grid building with these words
        rng = random.Random(42)
        result = build_crossword_grid(words, {}, grid_size=15, seed=42)
        print(f"\nGrid build: placed={len(result.placed_words)}, rejected={len(result.rejected_words)}")
        if result.errors:
            print(f"Errors: {result.errors}")
        if result.warnings:
            print(f"Warnings: {result.warnings}")
    
    print("\nTest PASSED")
    
except RecursionError as e:
    print("RECURSION ERROR:")
    traceback.print_exc()
    frames = []
    seen = set()
    for frame in traceback.extract_tb(e.__traceback__):
        key = f"{frame.filename}:{frame.lineno}"
        if key not in seen:
            seen.add(key)
            frames.append(f"  {frame.filename.split('\\')[-1]}:{frame.lineno} in {frame.name}: {frame.line}")
    print("\nRecursion stack:")
    for f in frames[-10:]:
        print(f)
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    traceback.print_exc()
