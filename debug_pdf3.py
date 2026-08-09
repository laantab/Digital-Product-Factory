"""Deep PDF content analysis"""
import sys, zlib, re, base64, json, urllib.request
sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')

from services.crossword.book import build_crossword_puzzles
from services.crossword.direct_pdf_renderer import build_single_crossword_pdf_bytes

puzzles, _, _ = build_crossword_puzzles(
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
puzzle = puzzles[0]
pdf_bytes, layout = build_single_crossword_pdf_bytes(puzzle, product_title="Fruit World", include_answer_key=True)

print(f"Direct render PDF size: {len(pdf_bytes)} bytes")
print(f"Layout: {layout}")
print(f"Page count: {layout.page_count}")
print(f"Answer key pages: {layout.answer_key_page_count}")

# Extract all text from all streams
text_parts = []
stream_pattern = re.compile(b'stream\r?\n(.*?)\r?\nendstream', re.DOTALL)
for match in stream_pattern.finditer(pdf_bytes):
    data = match.group(1)
    try:
        dec = zlib.decompress(data).decode('latin-1', errors='replace')
        text_parts.append(dec)
    except Exception:
        try:
            text_parts.append(data.decode('latin-1', errors='replace'))
        except Exception:
            pass

full_text = '\n'.join(text_parts)
print(f"\n=== TEXT IN PDF STREAMS ({len(full_text)} chars) ===")
print(full_text[:3000])

print(f"\n=== SEARCH FOR KEY TERMS ===")
search_terms = ['ANSWER', 'Solution', 'APPLE', 'BANANA', 'CHERRY', 'PEACH', 'LEMON', 'GRAPE',
                'ACROSS', 'DOWN', 'Fill', 'Clue', 'Fruit', 'Puzzle']
for term in search_terms:
    found = term.upper() in full_text.upper()
    print(f"  '{term}': {'FOUND' if found else 'not found'}")

# Now check via /generate-product (the actual API path)
print(f"\n=== CHECKING ACTUAL API RESPONSE ===")
body = {
    'product_type': 'crossword',
    'fields': {
        'book_title': 'Fruit Test',
        'theme': 'fruit',
        'creation_mode': 'Custom word list',
        'custom_words': 'APPLE\nBANANA\nCHERRY\nGRAPE\nMANGO\nPEACH\nLEMON\nMELON\nPEAR\nPLUM',
        'output_format': 'Single Worksheet',
        'include_answer_key': 'Yes',
        'include_cover': 'No',
        'puzzles': '1',
        'words_per_puzzle': '10',
        'difficulty': 'Easy',
    }
}
data = json.dumps(body).encode()
req = urllib.request.Request('http://localhost:5000/generate-product', data=data, headers={'Content-Type': 'application/json'}, method='POST')
with urllib.request.urlopen(req, timeout=90) as r:
    resp = json.loads(r.read())
    pdf_api = base64.b64decode(resp['pdf_bytes'])
    print(f"API PDF size: {len(pdf_api)} bytes")
    print(f"layout_info: {resp.get('layout_info')}")
    api_text = pdf_api.decode('latin-1', errors='replace')
    
    print(f"\n=== API PDF TEXT SEARCH ===")
    for term in search_terms:
        found = term.upper() in api_text.upper()
        print(f"  '{term}': {'FOUND' if found else 'not found'}")
    
    print(f"\n=== RESPONSE CHECKS ===")
    print(f"custom_words returned: {repr(resp.get('custom_words', '')[:50])}")
    print(f"pdf_bytes length: {len(resp.get('pdf_bytes', ''))}")
    print(f"qa passed: {resp.get('qa_report', {}).get('passed')}")
    print(f"answer_key_included: {resp.get('qa_report', {}).get('answer_key_included')}")
    print(f"puzzle_count: {resp.get('puzzle_count')}")
    print(f"puzzles in response: {resp.get('puzzles')}")  # might not be in the response
