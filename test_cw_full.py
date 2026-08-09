import sys, traceback
sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')
import os
os.environ['FLASK_APP'] = 'app.py'

# Set up Flask's app context manually
from flask import Flask
app = Flask(__name__)

with app.app_context():
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
        print("Starting crossword generation...")
        result = _generate_crossword_pdf(fields)
        print(f"OK: title={result.get('title')}")
    except RecursionError as e:
        print("RECURSION ERROR:")
        tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
        # Print unique frames
        seen = set()
        for line in tb_lines:
            print(line.strip())
            # Extract frame info
            import re
            matches = re.findall(r'File "([^"]+)", line (\d+)', line)
            for fn, ln in matches:
                key = f"{fn}:{ln}"
                if key not in seen:
                    seen.add(key)
        print(f"\nRecursion depth at error: {e}")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")
        traceback.print_exc()
