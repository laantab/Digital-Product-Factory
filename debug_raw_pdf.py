"""Check raw PDF content - write to file"""
import sys, base64, json, urllib.request, re, os
sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')

body = {
    'product_type': 'crossword',
    'fields': {
        'book_title': 'Fruit World',
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
    pdf = base64.b64decode(resp['pdf_bytes'])

output = []
output.append(f"PDF size: {len(pdf)} bytes")
output.append(f"Starts with %PDF: {pdf.startswith(b'%PDF')}")

# Search for text in raw bytes (use ascii-only search)
raw_bytes = pdf
for term in [b'Fruit', b'WORLD', b'Puzzle', b'ANSWER', b'Apple', b'Banana', b'Cherry']:
    pos = raw_bytes.find(term)
    if pos >= 0:
        snippet = raw_bytes[pos-5:pos+len(term)+20]
        output.append(f"  Found {term}: at {pos}: {snippet}")
    else:
        output.append(f"  '{term.decode()}': NOT FOUND")

# Check streams
streams = [(m.start(), m.end()) for m in re.finditer(b'stream\r?\n', pdf)]
output.append(f"\nStreams: {len(streams)}")
for i, (start, end) in enumerate(streams[:5]):
    # find endstream
    end_pos = pdf.find(b'endstream', start)
    raw_stream = pdf[end:end_pos]
    output.append(f"  Stream {i}: {len(raw_stream)} bytes raw")
    try:
        dec = raw_stream.decode('zlib')
        output.append(f"    Decompressed ({len(dec)} chars): {dec[:300]}")
    except Exception as e:
        output.append(f"    Decompress failed: {e}")
        output.append(f"    Raw: {repr(raw_stream[:100])}")

output.append(f"\nQA answer_key_included: {resp.get('qa_report', {}).get('answer_key_included')}")
output.append(f"QA answer_key_requested: {resp.get('qa_report', {}).get('answer_key_requested')}")
output.append(f"layout_info: {resp.get('layout_info')}")
output.append(f"puzzle_count: {resp.get('puzzle_count')}")
output.append(f"custom_words: {resp.get('custom_words', '')[:50]}")

# Save to file
report_path = os.path.join(os.path.dirname(__file__), 'pdf_debug_report.txt')
with open(report_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))
print(f"Written to {report_path}")
print('\n'.join(output))
