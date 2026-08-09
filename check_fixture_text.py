import sys, os
FLASK_DIR = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app'
sys.path.insert(0, FLASK_DIR)
import fitz

pdf_path = r'C:\Users\user\Desktop\The Factory\fixture_garden_vegetables_crossword.pdf'
doc = fitz.open(pdf_path)
full_text = ''
for i in range(doc.page_count):
    full_text += doc[i].get_text()
doc.close()

text_lower = full_text.lower()

forbidden = [
    'create a crossword', 'a term related to', 'use everyday', 'just for fun',
    'anyone should be', 'common words', 'simple words', 'placeholder',
    'everday',
]
print('FORBIDDEN PATTERN SCAN:')
for pat in forbidden:
    found = pat.lower() in text_lower
    status = 'FOUND!' if found else 'OK'
    print(f'  {pat!r}: {status}')

print()
print('SAMPLE TEXT (first 3000 chars):')
print(full_text[:3000])
