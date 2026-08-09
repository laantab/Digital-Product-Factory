"""Analyze both crossword fixture PDFs in detail."""
import fitz
import sys

FACTORY_PDF = r'C:\Users\user\Desktop\The Factory\just_for_fun_fixture.pdf'
BUILDER_PDF = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\crossword_builder\raw_instruction_fixture.pdf'

def extract_puzzle_data(doc):
    """Extract puzzle number, grid size, filled cells, and clues from a crossword PDF."""
    puzzles = []
    i = 0
    while i < doc.page_count:
        page = doc[i]
        text = page.get_text()
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # Look for puzzle marker
        puzzle_start = None
        for li, line in enumerate(lines):
            if line.startswith('PUZZLE') or line.startswith('Puzzle'):
                puzzle_start = li
                break

        if puzzle_start is not None:
            puzzle_lines = lines[puzzle_start:]
            puzzle_text = '\n'.join(puzzle_lines)
            puzzles.append({
                'page': i + 1,
                'lines': puzzle_lines,
                'full_text': puzzle_text
            })
        i += 1
    return puzzles

def analyze_pdf(path, label):
    print(f"\n{'='*60}")
    print(f"ANALYZING: {label}")
    print(f"Path: {path}")
    print(f"{'='*60}")
    doc = fitz.open(path)
    print(f"Total pages: {doc.page_count}")
    print(f"File size: {doc.stream_length if hasattr(doc, 'stream_length') else 'N/A'} bytes")

    puzzles = extract_puzzle_data(doc)
    print(f"\nPuzzles found: {len(puzzles)}")

    total_clues = 0
    for p in puzzles:
        print(f"\n--- Page {p['page']} ---")
        # Count clues (lines that start with a number followed by dot or dash)
        clue_lines = [l for l in p['lines'] if len(l) > 3 and l[0].isdigit() and (l[1] == '.' or l[1] == '-')]
        print(f"  Clue count: {len(clue_lines)}")
        total_clues += len(clue_lines)

        # Print first few clues
        if clue_lines:
            print(f"  First 5 clues:")
            for c in clue_lines[:5]:
                print(f"    {c[:80]}")
            if len(clue_lines) > 5:
                print(f"  Last 3 clues:")
                for c in clue_lines[-3:]:
                    print(f"    {c[:80]}")

    print(f"\n>>> TOTAL CLUES: {total_clues}")
    return total_clues

# Analyze both
t1 = analyze_pdf(FACTORY_PDF, "JUST FOR FUN FIXTURE (seed=42)")
t2 = analyze_pdf(BUILDER_PDF, "RAW INSTRUCTION FIXTURE (seed=99)")

print(f"\n{'='*60}")
print(f"SUMMARY:")
print(f"  Just for Fun:  {t1} clues")
print(f"  Raw Instruction: {t2} clues")
print(f"{'='*60}")
