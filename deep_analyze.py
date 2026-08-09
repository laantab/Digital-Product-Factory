"""Deep analysis of crossword fixtures - puzzle pages only."""
import fitz
import re

FACTORY_PDF = r'C:\Users\user\Desktop\The Factory\just_for_fun_fixture.pdf'
BUILDER_PDF = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\crossword_builder\raw_instruction_fixture.pdf'

def analyze_puzzle_pages(path, label):
    print(f"\n{'='*70}")
    print(f"DEEP ANALYSIS: {label}")
    print(f"{'='*70}")
    doc = fitz.open(path)

    # Puzzle pages are 1-10 (answer key is 11-21)
    puzzle_pages = list(range(0, 10))  # 0-indexed
    answer_key_pages = list(range(10, 21))

    print(f"\n--- PUZZLE PAGES (1-10) ---")
    total_clues = 0
    for page_num in puzzle_pages:
        page = doc[page_num]
        text = page.get_text()
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # Count clue lines: start with digit
        clue_lines = [l for l in lines if re.match(r'^\d+\.', l)]
        clue_count = len(clue_lines)
        total_clues += clue_count

        print(f"\nPage {page_num+1}: {clue_count} clues")
        if clue_count == 9:
            # Find which number is missing
            nums = sorted([int(re.match(r'^(\d+)\.', l).group(1)) for l in clue_lines])
            missing = [n for n in range(1, 11) if n not in nums]
            print(f"  WARNING: 9 clues! Missing clue number(s): {missing}")
            print(f"  Clues present: {nums}")
        print(f"  First clue: {clue_lines[0][:70] if clue_lines else 'NONE'}")
        print(f"  Last clue:  {clue_lines[-1][:70] if clue_lines else 'NONE'}")

    print(f"\n>>> TOTAL ACROSS PUZZLE PAGES: {total_clues}")

    print(f"\n--- ANSWER KEY PAGES (11-21) ---")
    ak_total = 0
    for page_num in answer_key_pages:
        page = doc[page_num]
        text = page.get_text()
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        clue_lines = [l for l in lines if re.match(r'^\d+\.', l)]
        ak_total += len(clue_lines)
        print(f"Page {page_num+1}: {len(clue_lines)} clues")
    print(f">>> TOTAL ACROSS ANSWER KEY PAGES: {ak_total}")

    return total_clues

t1 = analyze_puzzle_pages(FACTORY_PDF, "JUST FOR FUN (seed=42)")
t2 = analyze_puzzle_pages(BUILDER_PDF, "RAW INSTRUCTION (seed=99)")

print(f"\n{'='*70}")
print("CLUE COUNT SUMMARY")
print(f"  Just for Fun puzzle pages:  {t1} clues")
print(f"  Raw Instruction puzzle pages: {t2} clues")
print(f"{'='*70}")
