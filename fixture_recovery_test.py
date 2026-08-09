"""Verify the recovery pipeline end-to-end — no AI calls, fixture data only."""
import sys, os
FLASK_DIR = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app'
sys.path.insert(0, FLASK_DIR)

from services.crossword.crossword_repair import build_crossword_book_with_recovery
from services.crossword.pdf_builder import build_crossword_book_pdf_bytes
from services.crossword.qa_agent import run_crossword_book_qa
import fitz

OUTPUT_DIR = r'C:\Users\user\Desktop\The Factory'

def test_food_crossword():
    print("=== Test: Food-themed crossword with recovery ===")
    puzzles, warnings, errors, qa, used_fallback = build_crossword_book_with_recovery(
        theme="Food",
        difficulty="easy",
        grid_size=15,
        number_of_puzzles=3,
        words_per_puzzle=6,
        output_type="book",
        seed=99,
        include_answer_key=True,
        mode="topic",
    )
    print(f"  Puzzles: {len(puzzles)}")
    print(f"  QA passed: {qa.passed}")
    print(f"  Used fallback: {used_fallback}")
    print(f"  Errors: {errors}")
    print(f"  Warnings: {warnings}")
    if qa.errors:
        print(f"  QA errors: {qa.errors}")

    if not puzzles:
        print("  ERROR: No puzzles generated!")
        return False

    for i, p in enumerate(puzzles):
        print(f"  Puzzle {i+1}: {len(p.placed_words)} words, {len(p.clues)} clues, mode={p.mode}")
        if p.clues:
            print(f"    Sample clue: {p.clues[0].answer} = {p.clues[0].clue[:60]!r}")

    # Render PDF
    pdf_bytes, layout = build_crossword_book_pdf_bytes(
        puzzles,
        product_title="Test Food Puzzles",
        subtitle="Recovery Test",
        include_answer_key=True,
    )
    print(f"  PDF bytes: {len(pdf_bytes):,}")
    if not pdf_bytes.startswith(b'%PDF'):
        print("  ERROR: Not a valid PDF!")
        return False

    # Save
    pdf_path = os.path.join(OUTPUT_DIR, "fixture_recovery_test.pdf")
    with open(pdf_path, "wb") as f:
        f.write(pdf_bytes)
    print(f"  Saved: {pdf_path}")

    # Render pages
    doc = fitz.open(pdf_path)
    ws_dir = r'C:\Users\user\.mavis\agents\mavis\workspace'
    page_count = doc.page_count
    for i in range(min(6, page_count)):
        page = doc[i]
        mat = fitz.Matrix(1.5, 1.5)
        pix = page.get_pixmap(matrix=mat)
        img_path = os.path.join(ws_dir, f"recovery_p{i+1:02d}.png")
        pix.save(img_path)
    doc.close()
    print(f"  Rendered {min(6, page_count)} pages to workspace")
    return True

def test_everyday_crossword():
    print("\n=== Test: Everyday general crossword ===")
    puzzles, warnings, errors, qa, used_fallback = build_crossword_book_with_recovery(
        theme="Everyday Life",
        difficulty="easy",
        grid_size=15,
        number_of_puzzles=3,
        words_per_puzzle=6,
        output_type="book",
        seed=77,
        include_answer_key=True,
        mode="topic",
    )
    print(f"  Puzzles: {len(puzzles)}")
    print(f"  QA passed: {qa.passed}")
    print(f"  Used fallback: {used_fallback}")
    if qa.errors:
        print(f"  QA errors: {qa.errors}")

    for i, p in enumerate(puzzles):
        print(f"  Puzzle {i+1}: {len(p.placed_words)} words, clues sample: {[c.answer for c in p.clues[:2]]}")

    # Check no computer words in everyday
    all_words = [w for p in puzzles for w in p.placed_words]
    computer = {"keyboard", "monitor", "mouse", "software", "hardware", "processor", "ethernet", "bluetooth"}
    found = {w.lower() for w in all_words} & computer
    if found:
        print(f"  ERROR: Computer words in everyday puzzle: {found}")
        return False
    print(f"  No computer words in everyday puzzle — OK")
    return True

if __name__ == "__main__":
    r1 = test_food_crossword()
    r2 = test_everyday_crossword()
    if r1 and r2:
        print("\nAll recovery fixture tests passed!")
    else:
        print("\nSome recovery tests failed.")
