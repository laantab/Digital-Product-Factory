"""Deep-dive puzzle 6 of Just for Fun fixture, plus instruction-text check."""
import fitz
import re

FACTORY_PDF = r'C:\Users\user\Desktop\The Factory\just_for_fun_fixture.pdf'
BUILDER_PDF = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\crossword_builder\raw_instruction_fixture.pdf'

INSTRUCTION = "Create ten easy crossword puzzles using varied everyday words that almost everyone should be familiar with."

def show_page_text(path, page_num, label):
    doc = fitz.open(path)
    page = doc[page_num]
    text = page.get_text()
    print(f"\n{'='*70}")
    print(f"PAGE {page_num+1} — {label}")
    print(f"{'='*70}")
    print(text)
    return text

def check_instruction_in_clues(path, label):
    doc = fitz.open(path)
    instruction_words = set(INSTRUCTION.lower().split())

    print(f"\n{'='*70}")
    print(f"INSTRUCTION TEXT CHECK: {label}")
    print(f"{'='*70}")

    # Check puzzle pages (1-10)
    all_clues = []
    for page_num in range(10):
        page = doc[page_num]
        text = page.get_text()
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        clue_lines = [l for l in lines if re.match(r'^\d+\.', l)]
        for cl in clue_lines:
            # Extract the clue text (after "N. ")
            m = re.match(r'^\d+\.\s+(.+)', cl)
            if m:
                all_clues.append(m.group(1).lower())

    print(f"Total clues checked: {len(all_clues)}")

    # Check for any instruction words appearing as whole tokens in clues
    instruction_tokens = set(INSTRUCTION.lower().replace('.', '').split())
    # Remove common words that might appear naturally
    stopwords = {'a', 'an', 'the', 'to', 'be', 'is', 'are', 'that', 'with', 'from', 'or', 'and', 'of', 'in', 'for', 'on', 'as', 'it', 'at', 'by', 'i', 'you', 'should', 'can', 'all'}
    meaningful_tokens = instruction_tokens - stopwords

    print(f"Instruction tokens to check: {sorted(meaningful_tokens)}")

    # Check each clue for instruction text
    suspicious = []
    for clue in all_clues:
        # Check for multi-word instruction phrases
        for phrase in ['almost everyone', 'almost everyone should', 'crossword puzzles', 'easy crossword',
                       'varied everyday words', 'familiar with', 'ten easy', 'crossword puzzles using']:
            if phrase.lower() in clue:
                suspicious.append((clue, f"phrase: '{phrase}'"))

    if suspicious:
        print(f"\nSUSPICIOUS MATCHES:")
        for clue, reason in suspicious:
            print(f"  '{clue}' — {reason}")
    else:
        print("  No instruction text found in any clue. PASS.")

    return all_clues

# 1. Page 6 of Just for Fun — show raw text
t6 = show_page_text(FACTORY_PDF, 5, "Just for Fun — Puzzle 6 (page 6)")

# 2. Check instruction text in both fixtures
check_instruction_in_clues(FACTORY_PDF, "Just for Fun (seed=42)")
check_instruction_in_clues(BUILDER_PDF, "Raw Instruction (seed=99)")
