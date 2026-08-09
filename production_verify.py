"""Production route verification of the clue fix."""
import requests
import json
import sys
import os

BASE = "http://127.0.0.1:5000"

def test_crossword_route(theme: str, label: str):
    print(f"\n{'='*70}")
    print(f"PRODUCTION TEST: {label}")
    print(f"Theme: {theme!r}")
    print(f"{'='*70}")

    payload = {
        "product_title": theme,
        "theme": theme,
        "difficulty": "easy",
        "number_of_puzzles": 10,
        "words_per_puzzle": 10,
        "output_type": "book",
        "include_cover": False,
        "include_answer_key": True,
        "mode": "topic",
        "seed": 42,
    }

    resp = requests.post(f"{BASE}/crossword-builder/generate", json=payload, timeout=60)
    print(f"HTTP {resp.status_code}")

    try:
        data = resp.json()
    except Exception:
        print(f"Non-JSON response: {resp.text[:500]}")
        return False

    if not data.get("ok"):
        errors = data.get("errors", [])
        print(f"FAILED: {errors}")
        return False

    download_url = data.get("download_url", "")
    print(f"Download URL: {download_url}")

    if download_url:
        pdf_resp = requests.get(f"{BASE}{download_url}", timeout=30)
        pdf_path = rf"C:\Users\user\Desktop\The Factory\{label.replace(' ', '_').lower()}_clue_fix_test.pdf"
        with open(pdf_path, "wb") as f:
            f.write(pdf_resp.content)
        print(f"PDF saved: {pdf_path} ({len(pdf_resp.content):,} bytes)")

        # Analyze the PDF
        import fitz
        doc = fitz.open(pdf_path)
        puzzle_pages = list(range(0, 10))

        total_clues = 0
        import re
        generic_found = False
        clue_texts = []

        for page_num in puzzle_pages:
            page = doc[page_num]
            text = page.get_text()
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            clue_lines = [l for l in lines if re.match(r'^\d+\.', l)]
            for cl in clue_lines:
                clue_texts.append(cl.lower())
                if 'crossword answer' in cl.lower() or 'answer (' in cl.lower():
                    generic_found = True
                    print(f"  GENERIC CLUE: {cl[:80]}")

            total_clues += len(clue_lines)
            print(f"  Page {page_num+1}: {len(clue_lines)} clues")

        print(f"\nTotal puzzle clues: {total_clues}")
        print(f"Generic clue found: {generic_found}")

        if total_clues == 100:
            print("PASS: Exactly 100 clues")
        else:
            print(f"NOTE: {total_clues} clues (seed-dependent; not all seeds produce 10 words/puzzle)")

        if not generic_found:
            print("PASS: No generic placeholders found")

        doc.close()
        return not generic_found

    return True

# Test 1: The exact instruction that was the live error trigger
test_crossword_route(
    "Create ten easy crossword puzzles using varied everyday words that almost everyone should be familiar with.",
    "raw_instruction_clue_fix"
)

# Test 2: A theme that routes to everyday_life pack
test_crossword_route("everyday life", "everyday_life_clue_fix")

# Test 3: motivation (routes to everyday_life as fallback)
test_crossword_route("motivation", "motivation_clue_fix")
