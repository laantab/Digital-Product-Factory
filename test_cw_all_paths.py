import sys, traceback
sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')
import os
os.environ['FLASK_APP'] = 'app.py'

# Manually import everything and run the full generation
import threading, traceback as tb_module

# Override RecursionError to capture full stack
original_recursion_error = None

errors_captured = []

def trace_recursion_test():
    import sys
    
    old_excepthook = sys.excepthook
    def my_hook(type, value, tb):
        if type == RecursionError:
            errors_captured.append({
                'type': 'RecursionError',
                'message': str(value),
                'traceback': tb_module.format_exception(type, value, tb)
            })
        old_excepthook(type, value, tb)
    sys.excepthook = my_hook

    try:
        from services.product import _generate_crossword_pdf
        from services.crossword.word_entries import suggest_crossword_words_from_topic
        from services.crossword.engine import build_crossword_grid
        import random
        
        print("Testing suggest_crossword_words_from_topic...")
        words, warnings, errors = suggest_crossword_words_from_topic("golf", max_words=20)
        print(f"Got {len(words)} words: {words[:5]}")
        
        print("\nTesting build_crossword_grid with 1 word...")
        result = build_crossword_grid(words, {}, grid_size=15, seed=42)
        print(f"Grid: placed={len(result.placed_words)}, rejected={len(result.rejected_words)}")
        
        print("\nTesting full _generate_crossword_pdf...")
        fields = {
            "title": "Golf",
            "theme": "golf",
            "age_group": "12 to adults",
            "output_format": "Single page",
            "pages": "5",
            "num_puzzles": "5",
            "difficulty": "Easy",
            "clue_style": "Easy",
            "include_answer_key": True,
            "include_cover": False,
            "quality_mode": "standard",
        }
        result = _generate_crossword_pdf(fields)
        print(f"Result: title={result.get('title')}, pdf_bytes={len(result.get('pdf_bytes', ''))}")
        print("\nFULL GENERATION PASSED")
        
    except RecursionError as e:
        print("RECURSION ERROR!")
        for line in tb_module.format_exception(type(e), e, e.__traceback__):
            print(line.strip())
    except Exception as e:
        print(f"OTHER ERROR: {type(e).__name__}: {e}")
        tb_module.print_exc()

    if errors_captured:
        print("\n=== CAPTURED RECURSION ERRORS ===")
        for err in errors_captured:
            print(f"Type: {err['type']}")
            print(f"Message: {err['message']}")
            print("Traceback:")
            for line in err['traceback']:
                print(line.rstrip())

trace_recursion_test()
