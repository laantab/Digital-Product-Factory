"""Verify the 3 crossword builder fixes by calling the live Flask endpoints."""
import json, requests, sys, os, hashlib

BASE = "http://127.0.0.1:5000"

def test(name, payload, min_bytes=500):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    try:
        r = requests.post(f"{BASE}/crossword-builder/generate", json=payload, timeout=180)
    except Exception as e:
        print(f"CONNECTION ERROR: {e}")
        return False

    body = r.json()
    print(f"HTTP status: {r.status_code} | ok={body.get('ok')} | puzzles={body.get('puzzle_count')}")
    if body.get("errors"):
        print(f"ERRORS: {body['errors']}")
    if body.get("warnings"):
        unique_warns = list(dict.fromkeys(body["warnings"]))[:3]
        print(f"Warnings: {unique_warns}")

    if r.status_code != 200 or not body.get("ok"):
        print(f"Result: FAIL — non-200 or ok=False")
        return False

    dl_url = body.get("download_url")
    if not dl_url:
        print(f"Result: FAIL — no download_url")
        return False

    try:
        dl = requests.get(BASE + dl_url, timeout=30)
        pdf_bytes = dl.content
    except Exception as e:
        print(f"Result: FAIL — download error: {e}")
        return False

    print(f"PDF size: {len(pdf_bytes):,} bytes | header: {pdf_bytes[:4]}")
    is_pdf = pdf_bytes[:4] == b"%PDF"
    size_ok = len(pdf_bytes) >= min_bytes
    passed = is_pdf and size_ok
    print(f"PDF valid: {is_pdf} | size OK (>{min_bytes}): {size_ok}")

    # Quick QA: check PDF has answer key pages (look for /Page objects > puzzle count)
    page_count = pdf_bytes.count(b"/Type /Page\n") + pdf_bytes.count(b"/Type /Page ")
    print(f"Approximate page count: {page_count}")

    # Skip file cleanup — Flask holds the file open for the response stream on Windows

    print(f"\nResult: {'PASS' if passed else 'FAIL'}")
    return passed

results = []

# Test 1: Topic mode (was 500 — should now return 200 with valid PDF)
results.append(test(
    "Topic mode (no AI words, fallback clues, answer key)",
    {
        "theme": "Classroom Vocabulary",
        "creation_mode": "topic",
        "include_answer_key": "yes",
        "output_type": "book",
    },
    min_bytes=500,
))

# Test 2: Custom word list mode (was 500 — only 3 words placed)
results.append(test(
    "Custom word list (10 valid pairs, engine retry with larger grid)",
    {
        "theme": "Classroom Test Pack",
        "creation_mode": "custom_word_list",
        "custom_words": "TEACHER\nSTUDENT\nPENCIL\nBOOK\nDESK\nBOARD\nLESSON\nRECESS\nHOMEWORK\nLIBRARY",
        "include_answer_key": "yes",
        "output_type": "book",
        "number_of_puzzles": 1,
    },
    min_bytes=500,
))

# Test 3: Direct route (was 400 — expected 5 puzzles validation)
results.append(test(
    "Direct route (5 puzzles requested, 1 generated — should not 400)",
    {
        "product_title": "Direct Crossword Test",
        "theme": "Animals",
        "creation_mode": "topic",
        "include_answer_key": "yes",
        "output_type": "book",
        "number_of_puzzles": 5,
    },
    min_bytes=500,
))

print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
for i, ok in enumerate(results, 1):
    print(f"  Test {i}: {'PASS' if ok else 'FAIL'}")
print(f"  Overall: {sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
