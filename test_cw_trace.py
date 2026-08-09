import sys, traceback, json
sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')

# Set up so Flask imports work
import os
os.environ['FLASK_APP'] = 'app.py'

try:
    from services.product import _generate_crossword_pdf
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
    print(f"OK: title={result.get('title')}")
    print(f"PDF bytes: {len(result.get('pdf_bytes', ''))} chars base64")
except RecursionError as e:
    tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
    # Find the recursion depth
    for line in tb_lines:
        print(line)
    # Get the last 5 unique stack frames
    print("\n=== UNIQUE FRAMES ===")
    seen = set()
    for line in reversed(tb_lines):
        for part in line.split('\n'):
            if 'File "' in part and 'line ' in part:
                key = part.split('File "')[1].split('"')[0] + ':' + part.split('line ')[1].split(',')[0]
                if key not in seen:
                    seen.add(key)
                    print(part.strip())
    print(f"\nRecursion depth at error: {e}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    traceback.print_exc()
