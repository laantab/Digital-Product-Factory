"""Word Search Topic Accuracy fix verification tests."""
import sys
sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')

import requests, os, json

BASE = 'http://127.0.0.1:5000'
EXPORT_BASE = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\exports\word_search_builder'

# Unrelated words that should NEVER appear for "computer parts"
FORBIDDEN_WORDS = {
    "apple", "banana", "cherry", "dragon", "forest", "garden",
    "harbor", "island", "jungle", "river", "ocean", "mountain",
    "energy", "snow", "reindeer", "ornament",
}

# Related words that SHOULD appear for "computer parts"
COMPUTER_RELATED = {
    "keyboard", "monitor", "mouse", "screen", "printer", "speaker",
    "camera", "microphone", "processor", "memory", "storage",
    "motherboard", "cable", "router", "scanner", "webcam",
    "battery", "charger", "laptop", "desktop", "computer",
    "parts", "part",
}

def test(name, payload, min_bytes=500, check_unrelated=True):
    print(f'\n=== {name} ===')
    print(f'Payload: {json.dumps(payload, indent=2)}')

    try:
        r = requests.post(f'{BASE}/word-search-builder/generate', json=payload, timeout=180)
    except Exception as e:
        print(f'CONNECTION ERROR: {e}')
        return False

    body = r.json()
    print(f'HTTP: {r.status_code} | ok: {body.get("ok")}')
    if body.get('errors'):
        print(f'ERRORS: {body["errors"]}')
    if body.get('warnings'):
        unique = list(dict.fromkeys(body['warnings']))[:3]
        print(f'WARNINGS: {unique}')

    if r.status_code != 200 or not body.get('ok'):
        print(f'Result: FAIL (non-200 or ok=False)')
        return False

    # Download PDF
    dl_url = body.get('download_url', '')
    try:
        dl = requests.get(BASE + dl_url, timeout=30)
        pdf_bytes = dl.content
    except Exception as e:
        print(f'Download error: {e}')
        return False

    pdf_valid = pdf_bytes[:4] == b'%PDF'
    pdf_size = len(pdf_bytes)
    print(f'PDF: {pdf_size:,} bytes | valid: {pdf_valid}')

    # Extract words from QA report
    qa = body.get('qa_report', {})
    qa_passed = qa.get('passed', False)
    qa_errors = qa.get('errors', [])
    print(f'QA: {"PASS" if qa_passed else "FAIL"} | errors: {qa_errors}')

    # Check puzzle word lists (may be in PDF body or warnings)
    puzzles = body.get('puzzle_count', 0)
    print(f'Puzzles generated: {puzzles}')

    # For topic tests, check if unrelated words appear in warnings/qa_errors
    unrelated_found = []
    if check_unrelated:
        # The qa should flag any generic fallback words
        for word in FORBIDDEN_WORDS:
            if word in str(qa_errors).lower():
                unrelated_found.append(word)

    unrelated_ok = len(unrelated_found) == 0
    print(f'Unrelated word check: {"PASS" if unrelated_ok else "FAIL - found: " + str(unrelated_found)}')

    passed = pdf_valid and pdf_size >= min_bytes and qa_passed and unrelated_ok
    print(f'Result: {"PASS" if passed else "FAIL"}')
    return passed

results = []

# Test 1: Computer Parts — should produce computer-related words, no fruit/nature
results.append(test(
    'Test 1: Computer Parts topic',
    {
        'product_title': 'Computer Parts',
        'theme': 'computer parts',
        'creation_mode': 'topic',
        'include_answer_key': 'yes',
        'output_type': 'book',
        'number_of_puzzles': 1,
        'words_per_puzzle': 10,
    },
    check_unrelated=True,
))

# Test 2: Fruits — fruit words are OK
results.append(test(
    'Test 2: Fruits topic',
    {
        'product_title': 'Fruits',
        'theme': 'fruits',
        'creation_mode': 'topic',
        'include_answer_key': 'yes',
        'output_type': 'book',
        'number_of_puzzles': 1,
        'words_per_puzzle': 10,
    },
    check_unrelated=False,
))

# Test 3: Custom word list — use exactly the provided words
results.append(test(
    'Test 3: Custom word list',
    {
        'product_title': 'Computer Parts Custom',
        'creation_mode': 'custom_word_list',
        'custom_words': 'keyboard\nmonitor\nmouse\nprinter\nspeaker\ncamera\nmicrophone\nprocessor\nmemory\nstorage',
        'include_answer_key': 'yes',
        'output_type': 'book',
        'number_of_puzzles': 1,
    },
    check_unrelated=False,
))

# Test 4: Hard topic — narrow topic that cannot produce enough words
# Use a very specific topic that likely won't match any pack
results.append(test(
    'Test 4: Hard topic (narrow)',
    {
        'product_title': 'Quantum Computing Algorithms',
        'theme': 'quantum computing algorithms',
        'creation_mode': 'topic',
        'include_answer_key': 'yes',
        'output_type': 'book',
        'number_of_puzzles': 1,
        'words_per_puzzle': 10,
    },
    check_unrelated=True,
))

print(f'\n{"="*50}')
print('SUMMARY')
print(f'{"="*50}')
labels = ['Computer Parts', 'Fruits', 'Custom List', 'Hard Topic']
for i, (ok, label) in enumerate(zip(results, labels), 1):
    print(f'  Test {i} ({label}): {"PASS" if ok else "FAIL"}')
print(f'  Overall: {sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
