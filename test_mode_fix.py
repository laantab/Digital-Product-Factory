"""Smoke test: Topic mode should not be blocked by old saved words."""
import requests

# Test via the crossword-builder API route
resp = requests.post("http://127.0.0.1:5000/crossword-builder/generate", json={
    "product_title": "Garden Vegetables",
    "theme": "Garden Vegetables",
    "difficulty": "easy",
    "number_of_puzzles": 5,
    "words_per_puzzle": 10,
    "output_type": "book",
    "include_cover": False,
    "include_answer_key": True,
    "mode": "topic",
    "seed": 99,
}, timeout=60)

print(f"HTTP {resp.status_code}")
data = resp.json()
print(f"ok={data.get('ok')}")
if data.get("ok"):
    print(f"puzzle_count={data.get('puzzle_count')}")
    print(f"warnings={data.get('warnings', [])[:2]}")
    print("PASS: Topic mode generated successfully")
else:
    print(f"errors={data.get('errors', [])}")
    print(f"warnings={data.get('warnings', [])}")
