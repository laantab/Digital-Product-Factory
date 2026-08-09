import sys
sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')

import traceback
import sys

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
except RecursionError:
    traceback.print_exc()
    print("RECURSION ERROR")
except Exception as e:
    traceback.print_exc()
    print(f"ERROR: {type(e).__name__}: {e}")
