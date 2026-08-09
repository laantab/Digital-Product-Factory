"""Test the product pipeline path: Topic mode should not be blocked by old saved words."""
import requests
import json

BASE = "http://127.0.0.1:5000"

# Test /generate-product with Topic mode and 3 old stored_words
# This simulates: user saved a project with 3 custom words, then switched to Topic mode
payload = {
    "product_type": "crossword",
    "fields": {
        "title": "Garden Vegetables",
        "theme": "Garden Vegetables",
        "subtitle": "Garden Vegetables",
        "creation_mode": "Topic (AI generates words)",
        "puzzles": "5",
        "output_type": "book",
        "difficulty": "easy",
        "words_per_puzzle": "10",
    },
    # Simulate: this saved project had only 3 old custom words
    "custom_words": "APPLE\nBANANA\nCHERRY",
}

resp = requests.post(f"{BASE}/generate-product", json=payload, timeout=60)
print(f"HTTP {resp.status_code}")
data = resp.json()
print(f"ok={data.get('ok')}")

if data.get("ok"):
    print(f"puzzle_count={data.get('puzzle_count')}")
    print(f"warnings={data.get('warnings', [])[:2]}")
    # Download the PDF
    filename = data.get("filename", "")
    if filename:
        dl_resp = requests.get(f"{BASE}/download/{filename}", timeout=30)
        print(f"PDF size: {len(dl_resp.content):,} bytes")
    print("PASS: Topic mode generated successfully despite old 3 stored_words")
else:
    errors = data.get("errors", [])
    print(f"errors={errors}")
    if any("at least 4 words" in str(e) for e in errors):
        print("FAIL: Still blocked by old stored_words!")
    else:
        print("FAIL: Different error")
