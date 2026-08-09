"""Decode ASCII85-encoded PDF streams"""
import sys, base64, json, urllib.request, re, zlib, os
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

# Find all ASCII85Decode streams
import struct

output = []
output.append(f"PDF size: {len(pdf)} bytes")

# Decode ASCII85 manually (simple implementation)
def decode_ascii85(data):
    """Decode ASCII85 encoded data."""
    # Remove whitespace
    data = b''.join(data.split())
    # Remove end marker ~>
    if data.endswith(b'~>'):
        data = data[:-2]
    # Decode
    result = []
    i = 0
    while i < len(data):
        if data[i:i+1] == b'z':
            result.extend([0, 0, 0, 0])
            i += 1
        else:
            chunk = data[i:i+5]
            if len(chunk) < 5:
                # Pad with 'u' (0x75) for incomplete final block
                chunk = chunk + b'u' * (5 - len(chunk))
            val = 0
            for c in chunk:
                val = val * 85 + (c - 33)
            # Extract 4 bytes
            b4 = [(val >> 24) & 0xFF, (val >> 16) & 0xFF, (val >> 8) & 0xFF, val & 0xFF]
            # Remove padding bytes if original chunk was short
            if len(data) - i < 5:
                padding = 5 - len(chunk)
                b4 = b4[:4 - (5 - (len(data) - i))]
            result.extend(b4)
            i += 5
    return bytes(result[:len(result) - (len(result) % 4)] if len(result) % 4 != 0 else len(result))

# Find ASCII85 encoded streams
pattern = re.compile(b'stream\r?\n(.*?)\r?\nendstream', re.DOTALL)
output.append("=== DECODING ASCII85 STREAMS ===")
for i, match in enumerate(pattern.finditer(pdf)):
    raw = match.group(1).strip()
    output.append(f"\nStream {i}: {len(raw)} bytes raw")
    try:
        decoded = decode_ascii85(raw)
        # Now decompress if needed
        try:
            decompressed = zlib.decompress(decoded)
            text = decompressed.decode('latin-1', errors='replace')
            output.append(f"  Decompressed: {len(decompressed)} bytes")
            # Search for key terms
            for term in ['Fruit', 'World', 'Answer', 'Apple', 'Banana', 'Cherry', 'across', 'down']:
                if term.lower() in text.lower():
                    idx = text.lower().find(term.lower())
                    output.append(f"  FOUND '{term}': {repr(text[idx:idx+60])}")
            # Show first 300 chars
            output.append(f"  First 300 chars:\n    {repr(text[:300])}")
        except Exception as e:
            # Maybe it's not compressed after ASCII85
            text = decoded.decode('latin-1', errors='replace')
            output.append(f"  Raw decoded: {len(decoded)} bytes")
            output.append(f"  First 300 chars:\n    {repr(text[:300])}")
    except Exception as e:
        output.append(f"  ASCII85 decode failed: {e}")

output.append("\n=== SEARCHING ENTIRE PDF FOR KEY TERMS ===")
for term in [b'Fruit', b'WORLD', b'Puzzle', b'ANSWER', b'Apple', b'Banana', b'Cherry',
             b'Fruit World', b'Answer Key', b'Clue', b'ACROSS', b'DOWN', b'Puzzle 1']:
    if term in pdf:
        pos = pdf.find(term)
        output.append(f"  FOUND {term}: at {pos}: {repr(pdf[pos-5:pos+len(term)+30])}")

output.append("\n=== QA REPORT ===")
qa = resp.get('qa_report', {})
output.append(f"passed: {qa.get('passed')}")
output.append(f"answer_key_included: {qa.get('answer_key_included')}")
output.append(f"answer_key_requested: {qa.get('answer_key_requested')}")
output.append(f"errors: {qa.get('errors')}")
output.append(f"warnings: {qa.get('warnings')}")
output.append(f"fixes_applied: {qa.get('fixes_applied')}")

report_path = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\pdf_debug_report.txt'
with open(report_path, 'w', encoding='utf-8') as f:
    f.write('\n'.join(output))
print(f"Written: {report_path}")
