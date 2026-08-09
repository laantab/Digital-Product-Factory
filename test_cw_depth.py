import sys, traceback, threading
sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')
import os
os.environ['FLASK_APP'] = 'app.py'

# Patch RecursionError to get a full traceback
_orig_recursion_error = None

import builtins
_orig_excepthook = None

def test_with_deep_trace():
    import traceback as tb_module
    
    from services.crossword import word_entries, builder, engine, clues
    from services.factory import topic_intelligence
    import random
    
    # Test 1: suggest words for "golf"
    print("=== Test 1: suggest_crossword_words_from_topic('golf') ===")
    try:
        words, warnings, errors = word_entries.suggest_crossword_words_from_topic("golf", max_words=20)
        print(f"Words: {words[:10]}")
        print(f"Warnings: {warnings[:2]}")
    except RecursionError:
        print("RECURSION in suggest_crossword_words_from_topic!")
        traceback.print_exc()
        return
    
    # Test 2: build_local_clue (called for each word)
    print("\n=== Test 2: build_local_clue for GOLF ===")
    try:
        for word in ["GOLF", "TEE", "PAR", "BIRDIE", "DRIVER"]:
            clue = topic_intelligence.build_local_clue(word, topic="golf")
            print(f"  {word} -> {clue}")
    except RecursionError:
        print("RECURSION in build_local_clue!")
        traceback.print_exc()
        return
    
    # Test 3: generate_clues_for_words
    print("\n=== Test 3: generate_clues_for_words ===")
    try:
        test_words = ["GOLF", "TEE", "PAR", "BIRDIE", "DRIVER"]
        clues_map = clues.generate_clues_for_words(test_words, theme="golf")
        print(f"Generated {len(clues_map)} clues")
    except RecursionError:
        print("RECURSION in generate_clues_for_words!")
        traceback.print_exc()
        return
    
    # Test 4: build_crossword_grid with 1 tiny word
    print("\n=== Test 4: build_crossword_grid with 1 word ===")
    try:
        result = engine.build_crossword_grid(["GOLF"], {}, grid_size=15, seed=42)
        print(f"Placed: {result.placed_words}, Rejected: {result.rejected_words}")
        print(f"Errors: {result.errors}")
    except RecursionError:
        print("RECURSION in build_crossword_grid!")
        traceback.print_exc()
        return
    
    # Test 5: build_crossword_from_custom_list with 1 word
    print("\n=== Test 5: build_crossword_from_custom_list with 1 word ===")
    try:
        result = builder.build_crossword_from_custom_list(
            "GOLF", 
            puzzle_title="Golf", 
            theme="golf", 
            difficulty="Easy",
            grid_size=15,
            seed=42
        )
        print(f"Placed: {result.placed_words}")
        print(f"Errors: {result.errors}")
    except RecursionError:
        print("RECURSION in build_crossword_from_custom_list!")
        traceback.print_exc()
        return
    
    print("\n=== ALL TESTS PASSED - no recursion found ===")
    print("Recursion error might be in a different code path (Flask-specific, AI call, etc.)")

test_with_deep_trace()
