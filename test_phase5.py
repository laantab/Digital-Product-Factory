"""Phase 5: All 6 required tests for Word Search and Crossword."""
import sys, os, time, json, requests

sys.path.insert(0, r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app')
BASE = 'http://127.0.0.1:5000'
EXPORT_BASE = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\exports'
os.makedirs(EXPORT_BASE, exist_ok=True)

RESULTS = []


def make_request(url, payload, timeout=300):
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        return r.status_code, r.json()
    except Exception as e:
        return 0, {"error": str(e)}


def check_topic_words(word_bank, forbidden, required_prefix=None):
    """Check if word bank contains forbidden words or required prefixes."""
    issues = []
    for w in word_bank:
        wl = w.lower()
        for bad in forbidden:
            if bad.lower() in wl:
                issues.append(f"FORBIDDEN:{w}")
    if required_prefix:
        has_computer = any(required_prefix.lower() in w.lower() for w in word_bank)
        if not has_computer and issues:
            pass  # Pack-matched words are fine even without explicit token
    return issues


# ── WORD SEARCH TEST 1: Custom List ──────────────────────────────────────────
print("\n=== WS TEST 1: Custom Word List ===")
payload1 = {
    "product_title": "Computer Parts Custom",
    "creation_mode": "custom_word_list",
    "custom_words": "keyboard\nmonitor\nmouse\nprinter\nspeaker\ncamera\nrouter\nscreen\nmemory\nstorage",
    "include_answer_key": "yes",
    "output_type": "book",
    "number_of_puzzles": 1,
}
code1, body1 = make_request(f'{BASE}/word-search-builder/generate', payload1)
print(f"HTTP {code1} | ok={body1.get('ok')} | errors={body1.get('errors', [])[:2]}")
print(f"WARNINGS: {body1.get('warnings', [])[:2]}")
ws1_pass = code1 == 200 and body1.get('ok') == True
word_bank1 = []
if ws1_pass:
    word_bank1 = body1.get('word_bank', [])
    print(f"Words used: {word_bank1}")
    # Should use only the 10 custom words (some may be rejected if too long for grid)
    # Check no forbidden words
    forbidden_ws1 = ['apple', 'banana', 'cherry', 'dragon', 'forest', 'harbor', 'island', 'energy', 'river']
    bad_ws1 = [w for w in word_bank1 if any(f in w.lower() for f in forbidden_ws1)]
    if bad_ws1:
        print(f"FAIL: Found forbidden words: {bad_ws1}")
        ws1_pass = False
    else:
        print(f"PASS: No forbidden words found")
print(f"WS1 Result: {'PASS' if ws1_pass else 'FAIL'}")
RESULTS.append(('WS1 Custom List', ws1_pass))


# ── WORD SEARCH TEST 2: Topic Mode "computer parts" ───────────────────────────
print("\n=== WS TEST 2: Topic 'computer parts' ===")
payload2 = {
    "product_title": "Computer Parts Topic",
    "theme": "computer parts",
    "creation_mode": "topic",
    "include_answer_key": "yes",
    "output_type": "book",
    "number_of_puzzles": 1,
    "words_per_puzzle": 10,
}
code2, body2 = make_request(f'{BASE}/word-search-builder/generate', payload2)
print(f"HTTP {code2} | ok={body2.get('ok')} | errors={body2.get('errors', [])[:3]}")
print(f"WARNINGS: {body2.get('warnings', [])[:2]}")
ws2_pass = code2 == 200 and body2.get('ok') == True
word_bank2 = []
if ws2_pass:
    word_bank2 = body2.get('word_bank', [])
    print(f"Words: {word_bank2}")
    forbidden_ws2 = ['apple', 'banana', 'cherry', 'dragon', 'forest', 'harbor', 'island', 'jungle', 'energy', 'river', 'ocean', 'mountain', 'snow', 'reindeer', 'ornament']
    bad_ws2 = [w for w in word_bank2 if any(f in w.lower() for f in forbidden_ws2)]
    if bad_ws2:
        print(f"FAIL: Found forbidden words: {bad_ws2}")
        ws2_pass = False
    else:
        print(f"PASS: No forbidden/animal/nature words found")
    qa2 = body2.get('qa_report', {})
    if qa2.get('errors'):
        print(f"FAIL: QA errors: {qa2['errors']}")
        ws2_pass = False
else:
    # Check if the error is the correct "not enough topic words" error
    errs2 = body2.get('errors', [])
    if any('not enough' in e.lower() or 'topic-specific' in e.lower() for e in errs2):
        print(f"EXPECTED FAIL (topic not supported): {errs2}")
        ws2_pass = False  # This is actually the correct behavior for an unknown topic
    else:
        print(f"UNEXPECTED FAIL: {errs2}")
print(f"WS2 Result: {'PASS' if ws2_pass else 'FAIL'}")
RESULTS.append(('WS2 Topic: computer parts', ws2_pass))


# ── WORD SEARCH TEST 3: Topic/Subtopic "school" / "classroom supplies" ──────────
print("\n=== WS TEST 3: Topic 'school', Subtopic 'classroom supplies' ===")
payload3 = {
    "product_title": "Classroom Supplies",
    "theme": "school",
    "sub_topic": "classroom supplies",
    "creation_mode": "topic",
    "include_answer_key": "yes",
    "output_type": "book",
    "number_of_puzzles": 1,
    "words_per_puzzle": 10,
}
code3, body3 = make_request(f'{BASE}/word-search-builder/generate', payload3)
print(f"HTTP {code3} | ok={body3.get('ok')} | errors={body3.get('errors', [])[:3]}")
print(f"WARNINGS: {body3.get('warnings', [])[:2]}")
ws3_pass = code3 == 200 and body3.get('ok') == True
word_bank3 = []
if ws3_pass:
    word_bank3 = body3.get('word_bank', [])
    print(f"Words: {word_bank3}")
    forbidden_ws3 = ['apple', 'banana', 'cherry', 'harbor', 'jungle', 'energy', 'river']
    bad_ws3 = [w for w in word_bank3 if any(f in w.lower() for f in forbidden_ws3)]
    if bad_ws3:
        print(f"FAIL: Found forbidden words: {bad_ws3}")
        ws3_pass = False
    else:
        print(f"PASS: No forbidden words found")
    qa3 = body3.get('qa_report', {})
    if qa3.get('errors'):
        print(f"FAIL: QA errors: {qa3['errors']}")
        ws3_pass = False
else:
    errs3 = body3.get('errors', [])
    print(f"Error: {errs3}")
print(f"WS3 Result: {'PASS' if ws3_pass else 'FAIL'}")
RESULTS.append(('WS3 Topic: school/classroom supplies', ws3_pass))


# ── CROSSWORD TEST 1: Custom Clue/Answer List ───────────────────────────────────
print("\n=== CW TEST 1: Custom Clue/Answer List ===")
# Check the crossword route
payload_cw1 = {
    "product_title": "Computer Parts Crossword",
    "creation_mode": "custom_word_list",
    "custom_words": "keyboard\nmonitor\nmouse\nprinter\nspeaker\ncamera\nrouter\nscreen\nmemory\nstorage",
    "include_answer_key": "yes",
    "output_type": "book",
    "number_of_puzzles": 1,
    "words_per_puzzle": 10,
}
# First check the crossword route
cw_routes = ['/crossword-builder/generate', '/crossword/generate']
cw1_ok = False
cw1_body = None
cw1_code = 0
for route in cw_routes:
    try:
        r = requests.post(f'{BASE}{route}', json=payload_cw1, timeout=120)
        if r.status_code not in [404, 405]:
            cw1_code = r.status_code
            cw1_body = r.json()
            cw1_ok = cw1_code == 200 and cw1_body.get('ok') == True
            print(f"Route {route}: HTTP {cw1_code} | ok={cw1_ok}")
            break
    except Exception as e:
        print(f"Route {route}: error {e}")
if cw1_ok:
    print(f"Clues: {[(c['answer'], c['clue'][:40]) for c in cw1_body.get('clues', [])[:5]]}")
    print(f"Placed words: {cw1_body.get('placed_words', [])[:5]}")
    print(f"Errors: {cw1_body.get('errors', [])[:2]}")
    qa_cw1 = cw1_body.get('qa_report', {})
    if qa_cw1.get('errors'):
        print(f"QA errors: {qa_cw1['errors']}")
        cw1_ok = False
    else:
        print(f"PASS: QA passed")
elif cw1_body:
    print(f"Errors: {cw1_body.get('errors', [])[:3]}")
print(f"CW1 Result: {'PASS' if cw1_ok else 'FAIL'}")
RESULTS.append(('CW1 Custom Clue/Answer List', cw1_ok))


# ── CROSSWORD TEST 2: Topic Mode "computer parts" ─────────────────────────────
print("\n=== CW TEST 2: Topic 'computer parts' ===")
payload_cw2 = {
    "product_title": "Computer Parts Crossword",
    "theme": "computer parts",
    "creation_mode": "topic",
    "include_answer_key": "yes",
    "output_type": "book",
    "number_of_puzzles": 1,
    "words_per_puzzle": 10,
}
cw2_ok = False
cw2_body = None
cw2_code = 0
for route in cw_routes:
    try:
        r = requests.post(f'{BASE}{route}', json=payload_cw2, timeout=120)
        if r.status_code not in [404, 405]:
            cw2_code = r.status_code
            cw2_body = r.json()
            cw2_ok = cw2_code == 200 and cw2_body.get('ok') == True
            print(f"Route {route}: HTTP {cw2_code} | ok={cw2_ok}")
            break
    except Exception as e:
        print(f"Route {route}: error {e}")
if cw2_ok:
    clues2 = cw2_body.get('clues', [])
    print(f"Clues: {[(c['answer'], c['clue'][:50]) for c in clues2[:5]]}")
    forbidden_cw2 = ['apple', 'banana', 'cherry', 'forest', 'harbor', 'jungle', 'energy', 'river', 'ocean']
    bad_cw2 = [c for c in clues2 if any(f in c['answer'].lower() for f in forbidden_cw2)]
    if bad_cw2:
        print(f"FAIL: Found forbidden answers: {[(c['answer'], c['clue'][:30]) for c in bad_cw2]}")
        cw2_ok = False
    else:
        print(f"PASS: No forbidden/nature/animal answers found")
    qa_cw2 = cw2_body.get('qa_report', {})
    if qa_cw2.get('errors'):
        print(f"QA errors: {qa_cw2['errors']}")
        cw2_ok = False
elif cw2_body:
    errs_cw2 = cw2_body.get('errors', [])
    print(f"Errors: {errs_cw2[:3]}")
    if any('not enough' in e.lower() or 'topic-specific' in e.lower() for e in errs_cw2):
        print(f"EXPECTED FAIL (no pack for 'computer parts')")
        cw2_ok = False  # Expected if no pack
print(f"CW2 Result: {'PASS' if cw2_ok else 'FAIL'}")
RESULTS.append(('CW2 Topic: computer parts', cw2_ok))


# ── CROSSWORD TEST 3: Hard Unknown Topic ─────────────────────────────────────
print("\n=== CW TEST 3: Unknown narrow topic ===")
payload_cw3 = {
    "product_title": "Quantum Algorithms",
    "theme": "quantum superposition algorithms",
    "creation_mode": "topic",
    "include_answer_key": "yes",
    "output_type": "book",
    "number_of_puzzles": 1,
    "words_per_puzzle": 10,
}
cw3_ok = False
cw3_body = None
cw3_code = 0
for route in cw_routes:
    try:
        r = requests.post(f'{BASE}{route}', json=payload_cw3, timeout=120)
        if r.status_code not in [404, 405]:
            cw3_code = r.status_code
            cw3_body = r.json()
            cw3_ok = cw3_code == 200 and cw3_body.get('ok') == True
            break
    except Exception as e:
        print(f"Route {route}: error {e}")
if cw3_code == 400 or cw3_code == 200:
    errs_cw3 = (cw3_body or {}).get('errors', [])
    # Should show a clear error about no topic match
    has_clear_error = any(
        'not enough' in e.lower() or 'custom' in e.lower() or 'broader' in e.lower()
        for e in errs_cw3
    )
    # Or if it succeeded, check it's not using generic unrelated words
    if cw3_ok:
        clues3 = cw3_body.get('clues', [])
        bad3 = [c for c in clues3 if c['answer'].lower() in {'apple','banana','cherry','forest','harbor','island','jungle'}]
        if bad3:
            print(f"FAIL: Used unrelated words for unknown topic: {bad3}")
            cw3_ok = False
        else:
            print(f"PASS: No unrelated filler words")
    elif has_clear_error:
        print(f"PASS: Clear error shown for unknown topic: {errs_cw3[:2]}")
        cw3_ok = True
    else:
        print(f"FAIL: No clear error for unknown topic. Errors: {errs_cw3[:2]}")
else:
    print(f"Unexpected status: {cw3_code}")
print(f"CW3 Result: {'PASS' if cw3_ok else 'FAIL'}")
RESULTS.append(('CW3 Unknown topic handling', cw3_ok))


# ── SUMMARY ────────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
for name, ok in RESULTS:
    print(f"  {'PASS' if ok else 'FAIL'}: {name}")
passed = sum(1 for _, ok in RESULTS if ok)
print(f"\n  {passed}/{len(RESULTS)} tests passed")
sys.exit(0 if passed == len(RESULTS) else 1)
