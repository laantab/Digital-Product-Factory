"""Extract text from PDF using pypdf"""
import sys, base64, json, urllib.request, os
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
    pdf_bytes = base64.b64decode(resp['pdf_bytes'])

# Save PDF to disk for inspection
pdf_path = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\test_crossword_output.pdf'
with open(pdf_path, 'wb') as f:
    f.write(pdf_bytes)
print(f"PDF saved: {pdf_path}")

# Try to extract text using pypdf
try:
    import pypdf
    reader = pypdf.PdfReader(pdf_path)
    print(f"Pages: {len(reader.pages)}")
    for i, page in enumerate(reader.pages):
        text = page.extract_text()
        print(f"\n--- Page {i+1} ({len(text)} chars) ---")
        print(text[:1000])
except ImportError:
    print("pypdf not available")
    # Try pdfplumber
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            print(f"Pages: {len(pdf.pages)}")
            for i, page in enumerate(pdf.pages):
                text = page.extract_text()
                print(f"\n--- Page {i+1} ({len(text) if text else 0} chars) ---")
                if text:
                    print(text[:1000])
                else:
                    print("No text extracted (may be images/vectors)")
    except ImportError:
        print("Neither pypdf nor pdfplumber available")
        # Use command-line tool
        import subprocess
        result = subprocess.run(['python', '-m', 'pdfminer.high_level', pdf_path], capture_output=True, text=True)
        print("pdfminer output:", result.stdout[:500] if result.stdout else "no output", result.stderr[:200] if result.stderr else "")

# Also try pdftotext if available
try:
    import subprocess
    result = subprocess.run(['pdftotext', '-layout', pdf_path, '-'], capture_output=True)
    if result.returncode == 0:
        print("\n=== pdftotext output ===")
        print(result.stdout[:2000])
    else:
        print(f"pdftotext failed: {result.returncode}")
except Exception as e:
    print(f"pdftotext not available: {e}")

print(f"\nQA result: {resp.get('qa_report', {})}")
print(f"custom_words in response: {resp.get('custom_words', '')[:50]}")
print(f"puzzle_count: {resp.get('puzzle_count')}")
