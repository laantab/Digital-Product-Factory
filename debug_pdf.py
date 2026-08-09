import json, urllib.request, base64, re

body = {
    'product_type': 'crossword',
    'fields': {
        'book_title': 'Fruit Test Debug',
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
    
    pages = text.split('/Type /Page')
    print(f'Total page sections: {len(pages)-1}')
    
    keywords = ['ANSWER', 'SOLUTION', 'Key', 'KEY', 'Fill', 'Clue', 'CLUE', 'Solution']
    for kw in keywords:
        print(f'Found "{kw}": {"YES" if kw in text else "no"}')
    
    clue_pattern = re.compile(r'\(([A-Z]{4,10})\)')
    clues = clue_pattern.findall(text)
    print(f'Clues found: {clues[:20]}')
    
    print(f'QA passed: {resp.get("qa_report", {}).get("passed")}')
    print(f'AK included: {resp.get("qa_report", {}).get("answer_key_included")}')
    print(f'AK requested: {resp.get("qa_report", {}).get("answer_key_requested")}')
    print(f'QA errors: {resp.get("qa_report", {}).get("errors")}')
    print(f'QA warnings: {resp.get("qa_report", {}).get("warnings")}')
    print(f'Layout info: {resp.get("layout_info", {})}')
    print(f'Crossword meta: {resp.get("crossword_meta")}')
    print(f'Render engine: {resp.get("render_engine", "not returned")}')
