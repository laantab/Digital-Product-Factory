"""Check if 'crossword' appears in clue text vs headers/footers."""
import fitz
import re

# Raw instruction fixture
doc = fitz.open(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\crossword_builder\raw_instruction_fixture.pdf')

print("Checking 'crossword' in raw_instruction_fixture.pdf (seed=99)")
print("="*60)

# Separate clue text from non-clue text
clue_text_only = ""
header_footer_text = ""

for page_num in range(10):
    page = doc[page_num]
    text = page.get_text()
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    for line in lines:
        if re.match(r'^\d+\.\s+', line):
            clue_text_only += line + "\n"
        else:
            header_footer_text += line + "\n"

# Count occurrences
import re as re2
pattern = re2.compile(r'\bcrossword\b', re2.IGNORECASE)
clue_matches = pattern.findall(clue_text_only)
hf_matches = pattern.findall(header_footer_text)

print(f"'crossword' in CLUE text:     {len(clue_matches)} occurrences")
print(f"'crossword' in HEADER/FOOTER: {len(hf_matches)} occurrences")

if clue_matches:
    print(f"\nClues containing 'crossword':")
    for line in clue_text_only.split('\n'):
        if re2.search(r'\bcrossword\b', line, re2.IGNORECASE):
            print(f"  {line[:100]}")

print("\n" + "="*60)
print("Checking 'crossword' in just_for_fun_fixture.pdf (seed=42)")
print("="*60)

doc2 = fitz.open(r'C:\Users\user\Desktop\The Factory\just_for_fun_fixture.pdf')

clue_text_only2 = ""
header_footer_text2 = ""
for page_num in range(10):
    page = doc2[page_num]
    text = page.get_text()
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines:
        if re.match(r'^\d+\.\s+', line):
            clue_text_only2 += line + "\n"
        else:
            header_footer_text2 += line + "\n"

clue_matches2 = pattern.findall(clue_text_only2)
hf_matches2 = pattern.findall(header_footer_text2)
print(f"'crossword' in CLUE text:     {len(clue_matches2)} occurrences")
print(f"'crossword' in HEADER/FOOTER: {len(hf_matches2)} occurrences")

if clue_matches2:
    print(f"\nClues containing 'crossword':")
    for line in clue_text_only2.split('\n'):
        if re2.search(r'\bcrossword\b', line, re2.IGNORECASE):
            print(f"  {line[:100]}")
