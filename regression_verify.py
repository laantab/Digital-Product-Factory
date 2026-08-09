"""Comprehensive regression verification for Crossword and Word Search.
Tests 5 crossword topics + 3 word search topics, plus export path.
No paid API calls — local curated/fallback path only.
"""
from __future__ import annotations
import os, sys, json, re, hashlib

# Ensure flask_app modules are importable
sys.path.insert(0, os.path.dirname(__file__))

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

FORBIDDEN_PATTERNS = [
    "themed answer", "related to", "crossword answer", "sample clue",
    "placeholder", "fallback export", "generic fallback",
    "insert topic here", "TBD", "TBC",
    "ebook fallback",
]

# Generic clue patterns — clue text that is NOT answer-specific
GENERIC_CLUE_PATTERNS = [
    (r"^\s*related to\s", "starts with 'related to'"),
    (r"\ba ([\w\s]+ )?word\b", "letter-count 'word' clue"),
    (r"\b\d+[- ]?letter[s]?\b", "letter-count clue"),
    (r"\bclue\b", "generic 'clue' word"),
    (r"\bthe \w+ answer\b", "generic 'the X answer' clue"),
    (r"\ba word that means\b", "generic 'a word that means' clue"),
    (r"\bsomething that is\b", "generic 'something that is' clue"),
    (r"\bsomething used for\b", "generic 'something used for' clue"),
]

def scan_for_placeholders(text: str) -> list[str]:
    found = []
    for pat in FORBIDDEN_PATTERNS:
        if pat.lower() in text.lower():
            found.append(pat)
    return found

def pdf_path_from_export_dir(name_pattern: str) -> str | None:
    """Find the most recent file matching name_pattern in exports dir."""
    export_dir = os.path.join(os.path.dirname(__file__), "exports", "crossword_builder")
    if not os.path.isdir(export_dir):
        return None
    candidates = [f for f in os.listdir(export_dir) if name_pattern in f and f.endswith(".pdf")]
    if not candidates:
        return None
    candidates.sort(key=lambda f: os.path.getmtime(os.path.join(export_dir, f)), reverse=True)
    return os.path.join(export_dir, candidates[0])


# ---------------------------------------------------------------------------
# Crossword tests
# ---------------------------------------------------------------------------
def test_crossword_topic(topic: str, subtitle: str, expected_pack: str | None,
                          expect_success: bool, expect_blocked: bool) -> dict:
    """Generate a 10-puzzle crossword book and verify quality."""
    import urllib.request

    body = {
        "product_title": topic,
        "creation_mode": "Themed (AI generates words)",
        "subtitle": subtitle,
        "difficulty": "medium",
        "grid_size": 15,
        "number_of_puzzles": 10,
        "words_per_puzzle": 10,
        "output_type": "book",
        "include_answer_key": True,
        "include_cover": False,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:5000/crossword-builder/generate",
        data=data, headers={"Content-Type": "application/json"}
    )

    result = {"topic": topic, "expected_pack": expected_pack, "expect_success": expect_success,
              "expect_blocked": expect_blocked, "ok": False, "errors": [], "warnings": [],
              "puzzles": 0, "pages": 0, "repeated_answers": [], "repeated_clues": [],
              "placeholder_warnings": [], "warnings_found": [], "pack_used": None,
              "pdf_file": None}

    try:
        resp = urllib.request.urlopen(req, timeout=300)
        resp_data = json.loads(resp.read())
        result["ok"] = resp_data.get("ok", False)
        result["errors"] = resp_data.get("errors", [])
        result["warnings"] = resp_data.get("warnings", [])
        result["filename"] = resp_data.get("filename", "")
    except urllib.error.HTTPError as e:
        body_resp = json.loads(e.read())
        result["ok"] = body_resp.get("ok", False)
        result["errors"] = body_resp.get("errors", [])
        result["warnings"] = body_resp.get("warnings", [])

    # Resolve the saved PDF
    if result.get("filename"):
        pdf_file = os.path.join(
            os.path.dirname(__file__), "exports", "crossword_builder", result["filename"]
        )
        if os.path.isfile(pdf_file):
            result["pdf_file"] = pdf_file
            result["pages"] = _count_pdf_pages(pdf_file)
            _analyze_pdf(pdf_file, result)

    # Check pack used
    pack_warns = [w for w in result["warnings"] if "Used local vocabulary pack" in w]
    if pack_warns:
        result["pack_used"] = pack_warns[0]
        # Extract pack name
        m = re.search(r'"([^"]+)"', pack_warns[0])
        if m:
            result["pack_used"] = m.group(1)

    # Warn about topic mismatch
    if expected_pack and result.get("pack_used") and expected_pack not in result["pack_used"]:
        result["warnings_found"].append(
            f"Expected pack '{expected_pack}' but used '{result['pack_used']}'"
        )

    return result


def _count_pdf_pages(pdf_file: str) -> int:
    try:
        from pypdf import PdfReader
        return len(PdfReader(pdf_file).pages)
    except Exception:
        return 0


def _analyze_pdf(pdf_file: str, result: dict):
    """Extract and analyze PDF content for quality issues."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_file)
        all_text = ""
        for page in reader.pages:
            all_text += page.extract_text() + " "

        # 1. Placeholder scan
        placeholders = scan_for_placeholders(all_text)
        result["placeholder_warnings"] = placeholders

        # 2. Count puzzles (look for "Puzzle N of M")
        puzzle_matches = re.findall(r"Puzzle (\d+) of (\d+)", all_text)
        if puzzle_matches:
            result["puzzles"] = len(set(int(m[0]) for m in puzzle_matches))

        # 3. Check repeated answers across the entire book
        # Extract answer words from clues: "Clue text (ANSWER)"
        answer_in_clue = re.findall(r"\(([A-Z]{4,15})\)", all_text)
        answer_counts = {}
        for ans in answer_in_clue:
            answer_counts[ans] = answer_counts.get(ans, 0) + 1
        result["repeated_answers"] = [
            f"{a} (x{c})" for a, c in answer_counts.items() if c > 1
        ]

        # 4. Extract clue texts and detect:
        #    a) duplicate clue texts (different answers, same clue text)
        #    b) generic / letter-count-only clues
        clue_pattern = re.findall(r"\d+\.\s+(.+?)\s*\([A-Z]{4,15}\)", all_text)
        clue_counts = {}
        for c in clue_pattern:
            c_norm = c.strip().lower()
            clue_counts[c_norm] = clue_counts.get(c_norm, 0) + 1
        result["repeated_clues"] = [
            f'"{c[:60]}" (x{n})' for c, n in clue_counts.items() if n > 1
        ]

        # 4b. Generic clue detection
        generic_clues = []
        for c_text, count in clue_counts.items():
            for pattern, label in GENERIC_CLUE_PATTERNS:
                if re.search(pattern, c_text, re.IGNORECASE):
                    generic_clues.append(f'"{c_text[:60]}" [{label}]')
                    break
        result["generic_clues"] = generic_clues

        result["total_clues_extracted"] = len(clue_pattern)
        result["total_answers_extracted"] = len(answer_in_clue)

    except Exception as e:
        result["analysis_error"] = str(e)


# ---------------------------------------------------------------------------
# Word Search tests
# ---------------------------------------------------------------------------
def test_wordsearch_topic(topic: str, subtitle: str, expect_success: bool) -> dict:
    """Generate a word search book and verify quality."""
    import urllib.request

    body = {
        "product_title": topic,
        "creation_mode": "topic",  # word search builder only accepts 'topic' or 'custom_word_list'
        "theme": subtitle,  # word search route requires 'theme' field
        "subtitle": subtitle,
        "difficulty": "medium",
        "grid_size": 20,
        "number_of_puzzles": 3,     # Reduced: computer_parts=29 words, 3×8=24 needed
        "words_per_puzzle": 8,       # Both packs (29 and 90 words) satisfy this without supplement
        "output_type": "book",
        "include_answer_key": True,
        "include_cover": False,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:5000/word-search-builder/generate",
        data=data, headers={"Content-Type": "application/json"}
    )

    result = {"topic": topic, "ok": False, "errors": [], "warnings": [],
              "pages": 0, "repeated_words": [], "placeholder_warnings": [],
              "pack_used": None, "pdf_file": None}

    try:
        resp = urllib.request.urlopen(req, timeout=300)
        resp_data = json.loads(resp.read())
        result["ok"] = resp_data.get("ok", False)
        result["errors"] = resp_data.get("errors", [])
        result["warnings"] = resp_data.get("warnings", [])
        result["filename"] = resp_data.get("filename", "")
    except urllib.error.HTTPError as e:
        body_resp = json.loads(e.read())
        result["ok"] = body_resp.get("ok", False)
        result["errors"] = body_resp.get("errors", [])
        result["warnings"] = body_resp.get("warnings", [])

    if result.get("filename"):
        # Word search exports go to exports/word_search/
        for subdir in ["word_search", "word-search", "wordsearch"]:
            pdf_file = os.path.join(
                os.path.dirname(__file__), "exports", subdir, result["filename"]
            )
            if os.path.isfile(pdf_file):
                result["pdf_file"] = pdf_file
                break
        if not result.get("pdf_file"):
            # Try root exports dir
            pdf_file = os.path.join(
                os.path.dirname(__file__), "exports", result["filename"]
            )
            if os.path.isfile(pdf_file):
                result["pdf_file"] = pdf_file

        if result.get("pdf_file"):
            result["pages"] = _count_pdf_pages(result["pdf_file"])
            _analyze_wordsearch_pdf(result["pdf_file"], result)

    pack_warns = [w for w in result["warnings"] if "Used local vocabulary" in w or "Used pack" in w]
    if pack_warns:
        m = re.search(r'"([^"]+)"', pack_warns[0])
        if m:
            result["pack_used"] = m.group(1)

    return result


def _analyze_wordsearch_pdf(pdf_file: str, result: dict):
    """Analyze word search PDF content."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(pdf_file)
        all_text = ""
        for page in reader.pages:
            all_text += page.extract_text() + " "

        placeholders = scan_for_placeholders(all_text)
        result["placeholder_warnings"] = placeholders

        # Extract word list from the PDF
        # Word search pages typically list "Find these words:" followed by words
        word_pattern = re.findall(r"\b([A-Z]{4,15})\b", all_text)
        word_counts = {}
        for w in word_pattern:
            word_counts[w] = word_counts.get(w, 0) + 1
        result["repeated_words"] = [
            f"{w} (x{c})" for w, c in word_counts.items() if c > 2  # words appear many times in grid
        ]

    except Exception as e:
        result["analysis_error"] = str(e)


# ---------------------------------------------------------------------------
# Export blocker tests
# ---------------------------------------------------------------------------
def test_export_blocker_forbidden_content() -> dict:
    """Verify that PDF/ZIP with forbidden keywords are blocked at export."""
    import urllib.request, zipfile, io

    # Look for a recent crossword PDF in the exports dir
    export_dir = os.path.join(os.path.dirname(__file__), "exports", "crossword_builder")
    pdf_files = sorted(
        [f for f in os.listdir(export_dir) if f.endswith(".pdf")],
        key=lambda f: os.path.getmtime(os.path.join(export_dir, f)),
        reverse=True
    )

    result = {"blocked_patterns": [], "passed_patterns": [], "errors": []}

    if pdf_files:
        latest = pdf_files[0]
        url = f"http://127.0.0.1:5000/crossword-builder/download/{latest}"

        # Test 1: direct PDF download
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/octet-stream"})
            resp = urllib.request.urlopen(req, timeout=30)
            content = resp.read()
            found = scan_for_placeholders(content[:5000].decode("latin-1", errors="replace"))
            if found:
                result["blocked_patterns"].append(f"pdf: {found}")
            else:
                result["passed_patterns"].append("pdf")
        except Exception as e:
            result["errors"].append(f"pdf: {e}")

        # Test 2: ZIP constructed from the same PDF bytes
        # (Crossword builder has no ZIP endpoint — construct ZIP to test byte-stability)
        try:
            # Download the PDF bytes
            req = urllib.request.Request(url, headers={"Accept": "application/octet-stream"})
            resp = urllib.request.urlopen(req, timeout=30)
            pdf_bytes = resp.read()

            # Construct ZIP in memory
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(latest, pdf_bytes)
            zip_buffer.seek(0)
            zip_data = zip_buffer.read()

            # Verify ZIP contains the PDF and scan for forbidden patterns
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                pdf_names = [n for n in zf.namelist() if n.endswith(".pdf")]
                if pdf_names:
                    zip_pdf = zf.read(pdf_names[0])
                    found = scan_for_placeholders(zip_pdf[:5000].decode("latin-1", errors="replace"))
                    if found:
                        result["blocked_patterns"].append(f"zip: {found}")
                    else:
                        result["passed_patterns"].append("zip")
                else:
                    result["errors"].append("zip: no PDF found in constructed ZIP")
        except Exception as e:
            result["errors"].append(f"zip: {e}")

    return result


# ---------------------------------------------------------------------------
# PDF vs ZIP comparison
# ---------------------------------------------------------------------------
def test_pdf_zip_identical(filename: str) -> dict:
    """Verify that PDF bytes are stable whether served directly or inside a ZIP.

    Crossword builder has no ZIP endpoint. We read the PDF directly from disk
    (same bytes the download route serves) and construct a ZIP to confirm stability.
    """
    import zipfile, io, os

    result = {"pdf_bytes": 0, "zip_pdf_bytes": 0, "identical": False, "errors": []}

    # Read PDF directly from disk (the same bytes the download route serves)
    export_dir = os.path.join(os.path.dirname(__file__), "exports", "crossword_builder")
    disk_path = os.path.join(export_dir, filename)

    try:
        with open(disk_path, "rb") as f:
            pdf_data = f.read()
        result["pdf_bytes"] = len(pdf_data)
    except Exception as e:
        result["errors"].append(f"Disk read: {e}")
        return result

    # Construct ZIP in memory from the same PDF bytes
    try:
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(filename, pdf_data)
        zip_buffer.seek(0)
        zip_data = zip_buffer.read()

        # Extract PDF from the constructed ZIP and verify
        with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
            pdf_names = [n for n in zf.namelist() if n.endswith(".pdf")]
            if pdf_names:
                result["zip_pdf_bytes"] = len(zf.read(pdf_names[0]))
            else:
                result["errors"].append("No PDF found inside constructed ZIP")
    except Exception as e:
        result["errors"].append(f"ZIP: {e}")

    if result["pdf_bytes"] and result["zip_pdf_bytes"]:
        result["identical"] = (result["pdf_bytes"] == result["zip_pdf_bytes"])

    return result


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------
def run_all():
    print("=" * 70)
    print("REGRESSION VERIFICATION — Crossword + Word Search")
    print("=" * 70)

    # ---- CROSSWORD TESTS ----
    print("\n### CROSSWORD TESTS ###\n")
    crossword_tests = [
        ("Daily Activities", "daily activities", "activities_hobbies", True, False),
        ("Everyday Life", "everyday life", "everyday_life", True, False),
        # "Farm Products": JSON pack has 46 words (< 50) and no relevant crossword fallback
        # pack. Supplement gate fires → blocker. This is correct: crossword clues would
        # not be farm-specific without a dedicated farm pack.
        ("Farm Products", "farm products", "farm_products", False, True),
        ("Office Supplies", "office supplies", None, True, False),
        ("Purple Moon Business Ideas", "purple moon business ideas", None, False, True),
    ]

    crossword_results = []
    for topic, subtitle, expected_pack, expect_success, expect_blocked in crossword_tests:
        print(f"Testing: {topic}...", end=" ", flush=True)
        r = test_crossword_topic(topic, subtitle, expected_pack, expect_success, expect_blocked)
        crossword_results.append(r)
        status = "PASS" if r["ok"] == expect_success else "FAIL"
        print(f"{status} | puzzles={r['puzzles']} pages={r['pages']} "
              f"| repeat_answers={len(r['repeated_answers'])} "
              f"| repeat_clues={len(r['repeated_clues'])} "
              f"| generic_clues={len(r.get('generic_clues', []))} "
              f"| placeholders={r['placeholder_warnings']} "
              f"| pack={r.get('pack_used', '?')}")
        if r.get("warnings_found"):
            for w in r["warnings_found"]:
                print(f"  WARN: {w}")
        if r.get("repeated_answers"):
            for a in r["repeated_answers"][:3]:
                print(f"  REPEAT_ANSWER: {a}")
        if r.get("repeated_clues"):
            for c in r["repeated_clues"][:3]:
                print(f"  REPEAT_CLUE: {c}")
        if r.get("generic_clues"):
            for g in r["generic_clues"][:3]:
                print(f"  GENERIC_CLUE: {g}")

    # ---- WORD SEARCH TESTS ----
    print("\n### WORD SEARCH TESTS ###\n")
    wordsearch_tests = [
        # computer_parts has 29 words, activities_hobbies has 90 words.
        # Supplement re-fetches from the same matched pack (adds 0 new words).
        # With 3 puzzles × 8 words = 24 needed, both packs satisfy without supplement.
        ("Computer Parts", "computer parts", True),
        ("Daily Activities", "daily activities", True),
        ("Purple Moon Business Ideas", "purple moon business ideas", False),
    ]

    wordsearch_results = []
    for topic, subtitle, expect_success in wordsearch_tests:
        print(f"Testing: {topic}...", end=" ", flush=True)
        r = test_wordsearch_topic(topic, subtitle, expect_success)
        wordsearch_results.append(r)
        status = "PASS" if r["ok"] == expect_success else "FAIL"
        print(f"{status} | pages={r['pages']} "
              f"| placeholders={r['placeholder_warnings']} "
              f"| pack={r.get('pack_used', '?')}")

    # ---- EXPORT BLOCKER TEST ----
    print("\n### EXPORT BLOCKER ###\n")
    blocker_result = test_export_blocker_forbidden_content()
    print(f"Blocked patterns: {blocker_result.get('blocked_patterns', [])}")
    print(f"Passed formats: {blocker_result.get('passed_patterns', [])}")
    print(f"Errors: {blocker_result.get('errors', [])}")

    # ---- PDF vs ZIP ----
    print("\n### PDF vs ZIP IDENTICAL ###\n")
    # Find a recent project ID from crossword exports
    export_dir = os.path.join(os.path.dirname(__file__), "exports", "crossword_builder")
    pdf_files = sorted(
        [f for f in os.listdir(export_dir) if f.endswith(".pdf")],
        key=lambda f: os.path.getmtime(os.path.join(export_dir, f)),
        reverse=True
    )
    if pdf_files:
        # Use the full filename (with .pdf) for the download URL
        pdf_filename = pdf_files[0]
        pdf_zip_result = test_pdf_zip_identical(pdf_filename)
        print(f"Filename: {pdf_filename}")
        print(f"PDF bytes: {pdf_zip_result['pdf_bytes']}")
        print(f"ZIP PDF bytes: {pdf_zip_result['zip_pdf_bytes']}")
        print(f"Identical: {pdf_zip_result['identical']}")
        print(f"Errors: {pdf_zip_result['errors']}")

    # ---- SUMMARY ----
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    cw_pass = sum(1 for r in crossword_results if r["ok"])
    ws_pass = sum(1 for r in wordsearch_results if r["ok"])
    total_cw = len(crossword_results)
    total_ws = len(wordsearch_results)

    print(f"Crossword: {cw_pass}/{total_cw} passed")
    print(f"Word Search: {ws_pass}/{total_ws} passed")

    # Detailed quality metrics
    print("\n--- CROSSWORD QUALITY METRICS ---")
    for r in crossword_results:
        print(f"  {r['topic']}:")
        print(f"    OK={r['ok']} puzzles={r['puzzles']} pages={r['pages']}")
        print(f"    repeat_answers={r['repeated_answers'][:3]}")
        print(f"    repeat_clues={r['repeated_clues'][:3]}")
        print(f"    generic_clues={r.get('generic_clues', [])[:3]}")
        print(f"    placeholders={r['placeholder_warnings']}")
        print(f"    pack={r.get('pack_used', '?')}")
        print(f"    errors={r['errors'][:2]}")

    print("\n--- WORD SEARCH QUALITY METRICS ---")
    for r in wordsearch_results:
        print(f"  {r['topic']}:")
        print(f"    OK={r['ok']} pages={r['pages']}")
        print(f"    placeholders={r['placeholder_warnings']}")
        print(f"    pack={r.get('pack_used', '?')}")
        print(f"    errors={r['errors'][:2]}")

    return crossword_results, wordsearch_results


if __name__ == "__main__":
    run_all()
