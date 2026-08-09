"""Debug: trace PDF rendering"""
import sys
sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')

from services.crossword.book import build_crossword_puzzles
from services.crossword.direct_pdf_renderer import build_single_crossword_pdf_bytes
from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf

puzzles, warnings, errors = build_crossword_puzzles(
    mode="custom_word_list",
    product_title="Fruit World",
    custom_words="APPLE\nBANANA\nCHERRY\nGRAPE\nMANGO\nPEACH\nLEMON\nMELON\nPEAR\nPLUM",
    theme="fruit",
    difficulty="easy",
    grid_size=15,
    number_of_puzzles=1,
    words_per_puzzle=10,
    output_type="single_worksheet",
)
print(f"Puzzles: {len(puzzles)}")
puzzle = puzzles[0]
print(f"Clues: {len(puzzle.clues)}")
print(f"Placed: {puzzle.placed_words}")

print("\n=== RENDER WITH include_answer_key=True ===")
pdf_bytes, layout = build_single_crossword_pdf_bytes(
    puzzle,
    product_title="Fruit World",
    include_answer_key=True,
)
print(f"PDF size: {len(pdf_bytes)} bytes")
print(f"PDF starts with %PDF: {pdf_bytes.startswith(b'%PDF')}")
print(f"Layout: {layout}")

print("\n=== RENDER WITH include_answer_key=False ===")
pdf_bytes2, layout2 = build_single_crossword_pdf_bytes(
    puzzle,
    product_title="Fruit World",
    include_answer_key=False,
)
print(f"PDF size (no AK): {len(pdf_bytes2)} bytes")
print(f"Layout (no AK): {layout2}")

print(f"\n=== FULL PDF BUILDER ===")
req = CrosswordPdfRequest(
    product_title="Fruit World",
    theme="fruit",
    mode="custom_word_list",
    custom_words="APPLE\nBANANA\nCHERRY\nGRAPE\nMANGO\nPEACH\nLEMON\nMELON\nPEAR\nPLUM",
    output_type="single_worksheet",
    include_answer_key=True,
    grid_size=15,
    number_of_puzzles=1,
    words_per_puzzle=10,
    difficulty="easy",
    include_cover=False,
)
result = build_crossword_pdf(req)
print(f"Result errors: {result.errors}")
print(f"Result warnings: {result.warnings}")
print(f"PDF size: {len(result.pdf_bytes)}")
print(f"Layout info: {result.layout_info}")
print(f"QA report: {result.qa_report.as_dict() if result.qa_report else None}")
