import json, urllib.request, base64, re, zlib

content = open(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\static\js\app.js', encoding='utf-8').read()

# Find PRODUCT_TYPES crossword section
pt_start = content.find('PRODUCT_TYPES')
pt_cw = content.find('id: "crossword"', pt_start)
section_end = content.find('\n  {', pt_cw + 20)
section = content[pt_cw:section_end]
fields_start = section.find('fields: [')
fields_end = section.find('  },', fields_start)
fields_block = section[fields_start:fields_end + 5]

# Check the actual patterns used in the JS
checks = {
    'creation_mode field': 'name: "creation_mode"' in fields_block,
    'custom_words field': 'name: "custom_words"' in fields_block,
    'include_answer_key field': 'name: "include_answer_key"' in fields_block,
    'default Yes on AK': fields_block.find('include_answer_key"') >= 0 and 
                          'default: "Yes"' in fields_block[fields_block.find('include_answer_key"'):fields_block.find('include_answer_key"')+200],
}
print("=== FORM FIELD CHECKS (corrected patterns) ===")
for label, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'} {label}")

# Now check the actual crossword PDF
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
    pdf = base64.b64decode(resp['pdf_bytes'])
    text = pdf.decode('latin-1', errors='replace')
    
    print("\n=== PDF CONTENT ANALYSIS ===")
    print(f"PDF size: {len(pdf)} bytes")
    print(f"Pages: {text.count('/Type /Page')}")
    
    # Decompress any FlateDecode streams to find text
    # Look for stream objects
    stream_pattern = re.compile(b'stream\r?\n(.*?)\r?\nendstream', re.DOTALL)
    decoded_texts = []
    for match in stream_pattern.finditer(pdf):
        stream_data = match.group(1)
        try:
            decompressed = zlib.decompress(stream_data)
            decoded_texts.append(decompressed.decode('latin-1', errors='replace'))
        except Exception:
            pass
    
    all_text = ' '.join(decoded_texts)
    
    # Search for the fruit words
    print("\n=== WORD SEARCH IN PDF STREAMS ===")
    for word in ['APPLE', 'BANANA', 'CHERRY', 'GRAPE', 'MANGO', 'PEACH', 'LEMON', 'MELON']:
        found = word in all_text.upper() or word in text
        print(f"  {word}: {'FOUND' if found else 'NOT FOUND'}")
    
    # Look for answer key indicators
    print("\n=== ANSWER KEY CHECK ===")
    ak_indicators = ['ANSWER KEY', 'ANSWER', 'SOLUTION', 'Fill In', 'KEY', 'ACROSS', 'DOWN']
    for indicator in ak_indicators:
        found_text = indicator in all_text.upper()
        found_raw = indicator in text
        print(f"  '{indicator}': text={found_text}, raw={found_raw}")
    
    # Show first decoded stream (usually page 1 content)
    if decoded_texts:
        first_stream = decoded_texts[0][:2000]
        print(f"\n=== FIRST STREAM CONTENT (first 500 chars) ===")
        print(first_stream[:500])
    
    print(f"\n=== QA REPORT ===")
    print(f"passed: {resp.get('qa_report', {}).get('passed')}")
    print(f"answer_key_included: {resp.get('qa_report', {}).get('answer_key_included')}")
    print(f"answer_key_requested: {resp.get('qa_report', {}).get('answer_key_requested')}")
    print(f"errors: {resp.get('qa_report', {}).get('errors')}")
    print(f"warnings: {resp.get('qa_report', {}).get('warnings')}")
    
    # Also check the crossword meta
    print(f"\n=== CROSSWORD META ===")
    print(f"crossword_meta: {resp.get('crossword_meta')}")
    
    # Check how many puzzles were generated
    print(f"\npuzzle_count: {resp.get('puzzle_count')}")
    print(f"custom_words in response: {repr(resp.get('custom_words', '')[:60])}")
