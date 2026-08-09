"""Crossword Generator V1 regression test — run after any change to:
  - flask_app/static/js/app.js (form fields)
  - flask_app/services/product.py (crossword dispatch)
  - flask_app/services/packaging.py (export path)
  - flask_app/services/crossword/ (engine, builder, pdf_builder, qa_agent, book)

  This test verifies the fixes from 2026-08-04:
  1. Crossword factory form has creation_mode + custom_words fields
  2. include_answer_key defaults to Yes
  3. Custom word list mode works end-to-end with answer key
  4. word_placement field is in the generate response
  5. Export pipeline: saved crossword exports crossword PDF (not ebook fallback)
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error

BASE = "http://localhost:5000"
TIMEOUT = 120  # seconds

def md5_of_file(path):
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()

def api(path, method="GET", body=None):
    url = BASE + path
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read()), resp.status
    except urllib.error.HTTPError as e:
        try:
            body_text = e.read().decode()
            return json.loads(body_text), e.code
        except Exception:
            return {"error": e.reason}, e.code
    except Exception as e:
        return {"error": str(e)}, -1

def passfail(label, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    icon = "[PASS]" if ok else "[FAIL]"
    print(f"  {icon} {label}")
    if detail:
        print(f"       {detail}")
    return ok

# ── Check 1: app.js crossword form fields ──────────────────────────────────
def check_form_fields():
    print("\n-- Check 1: Crossword factory form fields in app.js --")
    app_js = os.path.join(os.path.dirname(__file__), "static", "js", "app.js")
    with open(app_js, encoding="utf-8") as f:
        content = f.read()

    # Find the crossword section
    m = re.search(r'id:\s*"crossword".*?fields:\s*\[(.*?)\n\s*\]', content, re.DOTALL)
    if not m:
        return passfail("Crossword form found in app.js", False, "Pattern not found")

    fields_block = m.group(1)
    checks = {
        "creation_mode field": 'name: "creation_mode"' in fields_block,
        "custom_words field": 'name: "custom_words"' in fields_block,
        "include_answer_key field": 'name: "include_answer_key"' in fields_block,
        "include_answer_key has default:Yes": 'default: "Yes"' in fields_block and 'include_answer_key' in fields_block,
    }
    all_ok = True
    for label, ok in checks.items():
        if not passfail(label, ok):
            all_ok = False
    return all_ok

# ── Check 2: product.py uses creation_mode not use_custom_words ─────────────
def check_backend_fix():
    print("\n-- Check 2: Backend uses creation_mode for custom word detection --")
    product_py = os.path.join(os.path.dirname(__file__), "services", "product.py")
    with open(product_py, encoding="utf-8") as f:
        content = f.read()

    # Find the _crossword_plan function
    m = re.search(r'"use_custom":\s*str\(_f\(fields,\s*"creation_mode"', content)
    ok = bool(m)
    passfail("Backend checks creation_mode for custom word detection", ok,
             "Found creation_mode check" if ok else "Still checking use_custom_words!")
    return ok

# ── Check 3: Custom word list + answer key end-to-end ──────────────────────
def check_custom_words_with_answer_key():
    print("\n-- Check 3: Custom word list + answer key end-to-end --")
    custom_words_str = "APPLE\nBANANA\nCHERRY\nGRAPE\nMANGO\nPEACH\nLEMON\nMELON"
    body = {
        "product_type": "crossword",
        "fields": {
            "book_title": "Fruit Crossword Test",
            "theme": "fruit",
            "creation_mode": "Custom word list",
            "custom_words": custom_words_str,
            "output_format": "Single Worksheet",
            "include_answer_key": "Yes",
            "include_cover": "No",
            "puzzles": "1",
            "words_per_puzzle": "8",
            "difficulty": "Easy",
        }
    }
    result, status = api("/generate-product", method="POST", body=body)
    if not passfail("HTTP 200", status == 200, f"Got {status}: {result.get('error', '')[:80]}"):
        return False

    if not passfail("PDF returned", result.get("pdf_bytes"), "No pdf_bytes"):
        return False

    if not passfail("Answer key included", result.get("qa_report", {}).get("answer_key_included"), str(result.get("qa_report", {}))[:80]):
        return False

    if not passfail("Custom words used", "APPLE" in result.get("custom_words", "").upper() or "BANANA" in result.get("custom_words", "").upper(), f"custom_words={result.get('custom_words', '')[:60]}"):
        return False

    if not passfail("No errors in qa_report", not result.get("qa_report", {}).get("errors"), str(result.get("qa_report", {}).get("errors", [])[:3])):
        return False

    print(f"       PDF size: {len(result.get('pdf_bytes', ''))} bytes")
    return True

# ── Check 4: Answer key default (no explicit include_answer_key) ─────────────
def check_answer_key_default():
    print("\n-- Check 4: Answer key defaults to Yes (no explicit flag) --")
    # Use "animals" topic which has a local pack
    body = {
        "product_type": "crossword",
        "fields": {
            "book_title": "Animal World",
            "theme": "animals",
            "output_format": "Single Worksheet",
            # NOTE: include_answer_key NOT passed — form should default to "Yes"
            "include_cover": "No",
            "puzzles": "1",
            "words_per_puzzle": "10",
            "difficulty": "Easy",
        }
    }
    result, status = api("/generate-product", method="POST", body=body)
    if not passfail("HTTP 200", status == 200, f"Got {status}"):
        return False

    qa = result.get("qa_report", {})
    if not passfail("Answer key included (default)", qa.get("answer_key_included"), f"qa_report={qa}"):
        return False

    return True

# ── Check 5: word_placement field in generate response ─────────────────────────
def check_word_placement():
    print("\n-- Check 5: word_placement field in generate response --")
    body = {
        "product_type": "crossword",
        "fields": {
            "book_title": "Fruit Crossword Placement Test",
            "theme": "fruits",
            "creation_mode": "Custom word list",
            "custom_words": "APPLE\nBANANA\nGRAPE\nORANGE",
            "output_format": "Single Worksheet",
            "include_answer_key": "Yes",
            "include_cover": "No",
            "puzzles": "1",
            "difficulty": "Easy",
        }
    }
    result, status = api("/generate-product", method="POST", body=body)
    if not passfail("HTTP 200", status == 200, f"Got {status}"):
        return False

    wp = result.get("word_placement", {})
    if not passfail("word_placement field present", bool(wp), f"word_placement={wp}"):
        return False

    if not passfail("placed_words reported", len(wp.get("placed_words", [])) > 0,
                    f"placed_words={wp.get('placed_words', [])}"):
        return False

    if not passfail("note field present", bool(wp.get("note")), f"note={wp.get('note', 'MISSING')}"):
        return False

    return True

# ── Check 6: Export pipeline — saved crossword exports crossword PDF ─────────────
def check_export_path():
    print("\n-- Check 6: Export pipeline (save -> export -> crossword PDF) --")
    # Generate
    body = {
        "product_type": "crossword",
        "fields": {
            "book_title": "Fruit Crossword Export Test",
            "theme": "fruits",
            "creation_mode": "Custom word list",
            "custom_words": "APPLE\nBANANA\nGRAPE\nMANGO",
            "output_format": "Single Worksheet",
            "include_answer_key": "Yes",
            "include_cover": "No",
            "puzzles": "1",
            "difficulty": "Easy",
        }
    }
    gen, status = api("/generate-product", method="POST", body=body)
    if not passfail("Generate HTTP 200", status == 200, f"Got {status}"):
        return False
    if not passfail("PDF returned from generate", bool(gen.get("pdf_bytes")), ""):
        return False

    # Save (with is_pdf and pdf_bytes)
    save_body = {
        "name": "Fruit Crossword Export Test",
        "type": "product",
        "data": {
            "product_type": "crossword",
            "title": "Fruit Crossword Export Test",
            "fields": gen.get("fields", {}),
            "pdf_bytes": gen["pdf_bytes"],
            "filename": gen.get("filename", "fruit_crossword_export_test.pdf"),
            "is_pdf": True,
            "is_book": False,
            "package_id": gen.get("package_id", ""),
        }
    }
    saved, status = api("/projects", method="POST", body=save_body)
    if not passfail("Save HTTP 200/201", status in (200, 201), f"Got {status}"):
        return False
    project_id = saved.get("id")
    if not passfail("Project ID returned", bool(project_id), f"id={project_id}"):
        return False

    # Export
    export, status = api("/export-product", method="POST", body={"project_id": project_id})
    if not passfail("Export HTTP 200", status == 200,
                    f"Got {status}: {export.get('error', '')[:80]}"):
        return False

    files = export.get("exports", {}).get("files", {})
    if not passfail("PDF file in export", bool(files.get("pdf")), f"files={list(files.keys())}"):
        return False
    if not passfail("ZIP file in export", bool(files.get("zip")), ""):
        return False

    # Download PDF and verify it's the crossword (not ebook fallback)
    pdf_url = BASE + files["pdf"]["url"]
    try:
        with urllib.request.urlopen(pdf_url, timeout=30) as resp:
            pdf_bytes = resp.read()
    except Exception as e:
        passfail("PDF download", False, f"Error: {e}")
        return False

    if not passfail("PDF starts with %PDF", pdf_bytes.startswith(b"%PDF"), ""):
        return False
    if not passfail("No FALLBACK EXPORT text", b"FALLBACK" not in pdf_bytes and b"fallback" not in pdf_bytes.lower(),
                    "PDF contains FALLBACK text — ebook fallback was served!"):
        return False

    # Compare: direct PDF and exported PDF must be byte-identical
    import base64
    gen_pdf = base64.b64decode(gen["pdf_bytes"])
    if not passfail("Direct PDF == Exported PDF", gen_pdf == pdf_bytes,
                    f"Direct {len(gen_pdf)} bytes vs Exported {len(pdf_bytes)} bytes"):
        return False

    return True

# ── Check 7: Minimum word count guard ───────────────────────────────────────────
def check_min_word_count():
    print("\n-- Check 7: Minimum word count guard (3 words -> clear error) --")
    body = {
        "product_type": "crossword",
        "fields": {
            "book_title": "Too Few Words Test",
            "theme": "Test",
            "creation_mode": "Custom word list",
            "custom_words": "APPLE\nBANANA\nCHERRY",
            "output_format": "Single Worksheet",
            "include_answer_key": "Yes",
            "include_cover": "No",
            "puzzles": "1",
            "difficulty": "Easy",
        }
    }
    result, status = api("/generate-product", method="POST", body=body)
    if not passfail("HTTP 400 for <4 words", status == 400, f"Got {status}"):
        return False
    err = result.get("error", "")
    if not passfail("Clear error message about minimum word count",
                    "at least 4 words" in err,
                    f"Error: {err[:120]}"):
        return False
    return True

# ── Run ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("Crossword Generator V1 Regression Test")
    print("=" * 60)

    results = []
    results.append(("Form fields", check_form_fields()))
    results.append(("Backend fix", check_backend_fix()))
    results.append(("Custom words + AK", check_custom_words_with_answer_key()))
    results.append(("AK default", check_answer_key_default()))
    results.append(("word_placement field", check_word_placement()))
    results.append(("Export pipeline", check_export_path()))
    results.append(("Min word count guard", check_min_word_count()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    all_pass = True
    for name, ok in results:
        icon = "PASS" if ok else "FAIL"
        print(f"  [{icon}] {name}")
        if not ok:
            all_pass = False

    print()
    if all_pass:
        print("ALL CHECKS PASSED")
        sys.exit(0)
    else:
        print("SOME CHECKS FAILED — review output above")
        sys.exit(1)
