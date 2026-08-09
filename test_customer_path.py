"""Full customer-path regression test for Crossword Generator V1.
Tests Generate -> Save -> Export through the actual running Flask app.
No OpenAI, no Tavily.

Uses pypdf for reliable text extraction from ReportLab PDFs.
"""
import base64
import hashlib
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile

BASE = "http://localhost:5000"
TIMEOUT = 120

def api(path, method="GET", body=None):
    url = BASE + path
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            ct = resp.headers.get("Content-Type", "")
            if "application/json" in ct:
                return json.loads(resp.read()), resp.status, resp
            return resp.read(), resp.status, resp
    except urllib.error.HTTPError as e:
        try:
            text = e.read().decode()
            try:
                return json.loads(text), e.code, e
            except Exception:
                return {"raw": text[:500], "error": e.reason}, e.code, e
        except Exception:
            return {"error": e.reason}, e.code, e
    except Exception as e:
        return {"error": str(e)}, -1, None

def passfail(label, ok, detail=""):
    icon = "PASS" if ok else "FAIL"
    print(f"  [{icon}] {label}")
    if detail:
        print(f"       {detail}")
    return ok

def pdf_page_count(pdf_bytes):
    text = pdf_bytes.decode("latin-1", errors="replace")
    return text.count("/Type /Page") - 2  # subtract catalog/page parent objects

def pdf_text_extract(pdf_bytes):
    """Extract text from PDF using pypdf (handles ReportLab ASCII85+Flate encoding)."""
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
        return pages
    except ImportError:
        # Fallback: search raw bytes for ASCII text
        import re
        strings = re.findall(b"[A-Za-z ]{4,}", pdf_bytes)
        return [" ".join(s.decode("ascii", errors="ignore") for s in strings)]
    except Exception as e:
        return [f"[extraction error: {e}]"]

def main():
    print("=" * 60)
    print("CROSSWORD CUSTOMER-PATH REGRESSION TEST")
    print("=" * 60)
    all_ok = True

    # ── Step 0: Form fields ──────────────────────────────────────────────────
    print("\n-- Step 0: Form fields in PRODUCT_TYPES crossword --")
    app_js_path = os.path.join(os.path.dirname(__file__), "static", "js", "app.js")
    with open(app_js_path, encoding="utf-8") as f:
        js = f.read()

    # Find PRODUCT_TYPES array and then the crossword entry
    pt_start = js.find("PRODUCT_TYPES")
    cw_start = js.find('id: "crossword"', pt_start)
    cw_end = js.find("\n  {", cw_start + 20)  # end of crossword object
    cw_section = js[cw_start:cw_end]

    # Fields block
    fields_start = cw_section.find("fields: [")
    fields_end = cw_section.find("  ],", fields_start)
    fields_block = cw_section[fields_start:fields_end + 5]

    # Check patterns (JS uses: name: "field_name", no quotes around property name)
    field_checks = {
        "creation_mode field present": 'name: "creation_mode"' in fields_block,
        "custom_words field present": 'name: "custom_words"' in fields_block,
        "include_answer_key field present": 'name: "include_answer_key"' in fields_block,
        "include_answer_key default=Yes": (
            'name: "include_answer_key"' in fields_block
            and 'default: "Yes"' in fields_block[fields_block.find('name: "include_answer_key"'):fields_block.find('name: "include_answer_key"')+300]
        ),
        "Word source select (creation_mode label)": 'label: "Word source"' in fields_block,
        "Custom words textarea label": 'label: "Custom words' in fields_block,
    }
    for label, ok in field_checks.items():
        if not passfail(label, ok):
            all_ok = False

    # ── Step 1: Generate crossword with custom words ──────────────────────────
    print("\n-- Step 1: Generate crossword with custom fruit word list --")

    custom_words = (
        "APPLE\nBANANA\nCHERRY\nGRAPE\nMANGO\n"
        "PEACH\nLEMON\nMELON\nPEAR\nPLUM"
    )

    body = {
        "product_type": "crossword",
        "fields": {
            "book_title": "Fruit World Crossword",
            "theme": "fruit",
            "creation_mode": "Custom word list",
            "custom_words": custom_words,
            "output_format": "Single Worksheet",
            "include_answer_key": "Yes",
            "include_cover": "No",
            "puzzles": "1",
            "words_per_puzzle": "10",
            "difficulty": "Easy",
        }
    }
    gen_resp, status, _ = api("/generate-product", method="POST", body=body)
    if not passfail("Generate returns 200", status == 200, f"Got {status}"):
        all_ok = False
        print("  Cannot continue — generation failed")
        sys.exit(1)

    if not passfail("pdf_bytes returned", bool(gen_resp.get("pdf_bytes")), "No pdf_bytes"):
        all_ok = False
        sys.exit(1)

    pdf_bytes = base64.b64decode(gen_resp["pdf_bytes"])
    if not passfail("Valid PDF (starts %PDF)", pdf_bytes.startswith(b"%PDF"), "Not a PDF"):
        all_ok = False
        all_ok = False

    pages = pdf_page_count(pdf_bytes)
    if not passfail(f"PDF has 2 pages (puzzle + AK) ({pages} found)", pages >= 2, f"{pages} pages"):
        all_ok = False

    # Extract text using pypdf
    text_pages = pdf_text_extract(pdf_bytes)
    all_text = "\n".join(text_pages)
    print(f"       Extracted {sum(len(t) for t in text_pages)} chars from {len(text_pages)} pages")

    # Check custom words in extracted text
    # The words appear as grid fills in the AK page AND as clues on both pages
    topic_clues = {
        "GRAPE": "bunches on vines" in all_text,       # GRAPE clue
        "BANANA": "curved fruit" in all_text,          # BANANA clue
        "CHERRY": "pit inside" in all_text,            # CHERRY clue
        "LEMON": "citrus" in all_text,                  # LEMON clue
    }
    clue_ok = True
    for word, clue_ok_flag in topic_clues.items():
        if not passfail(f"Topic-specific clue for {word}", clue_ok_flag, all_text[:200]):
            all_ok = False

    # Check no placeholder clues
    placeholders = ["themed answer", "placeholder", "sample clue", "example clue"]
    for ph in placeholders:
        if ph.lower() in all_text.lower():
            if not passfail(f"No placeholder '{ph}'", False, "Found in PDF!"):
                all_ok = False

    # Check answer key
    # Page 2 should have "Answer Key" and filled grid letters
    has_answer_key_page = len(text_pages) >= 2 and any(
        "answer key" in text_pages[i].lower()
        for i in range(1, len(text_pages))
    )
    if not passfail("Answer key page present (page 2)", has_answer_key_page,
                   [f"Page {i+1}: {t[:80]}" for i, t in enumerate(text_pages)]):
        all_ok = False

    # Check QA report
    qa = gen_resp.get("qa_report", {})
    if not passfail("QA passed", qa.get("passed"), str(qa)):
        all_ok = False
    if not passfail("Answer key flag set in QA", qa.get("answer_key_included"), str(qa)):
        all_ok = False

    # ── Step 2: Save project ─────────────────────────────────────────────────
    print("\n-- Step 2: Save project --")

    save_data = {
        "name": "Fruit World Crossword - Customer Test",
        "type": "product",
        "data": {
            "product_type": "crossword",
            "title": "Fruit World Crossword",
            "pdf_bytes": gen_resp.get("pdf_bytes", ""),
            "package_id": gen_resp.get("package_id", ""),
            "filename": gen_resp.get("filename", "fruit_world.pdf"),
            "custom_words": custom_words,
            "fields": body["fields"],
        }
    }
    save_resp, status, _ = api("/projects", method="POST", body=save_data)
    if not passfail("Save project returns 201", status == 201, f"Got {status}"):
        all_ok = False
    else:
        saved_id = save_resp.get("id")
        if not passfail("Saved project has ID", bool(saved_id), f"ID={saved_id}"):
            all_ok = False

    # ── Step 3: Export ───────────────────────────────────────────────────────
    print("\n-- Step 3: Export project --")

    export_resp, status, _ = api("/export-product", method="POST", body={"id": saved_id})
    if not passfail("Export returns 200", status == 200, f"Got {status}"):
        all_ok = False

    # The export response format: check what keys it has
    export_keys = list(export_resp.keys()) if isinstance(export_resp, dict) else []
    print(f"       Export keys: {export_keys}")

    # Try /download endpoint if export has a package_id
    package_id = export_resp.get("package_id") or ""
    pdf_downloaded = False
    zip_downloaded = False
    exported_pdf_bytes = b""
    zip_bytes = b""

    if package_id:
        # Try to find the PDF and ZIP in the exports directory
        exports_dir = os.path.join(os.path.dirname(__file__), "exports", "products", package_id)
        if os.path.exists(exports_dir):
            files = os.listdir(exports_dir)
            print(f"       Export files: {files}")
            for f in files:
                if f.endswith(".pdf"):
                    with open(os.path.join(exports_dir, f), "rb") as pf:
                        exported_pdf_bytes = pf.read()
                        pdf_downloaded = True
                if f.endswith(".zip"):
                    with open(os.path.join(exports_dir, f), "rb") as zf:
                        zip_bytes = zf.read()
                        zip_downloaded = True

    # Also try direct download URLs if available
    if not pdf_downloaded:
        # Try the /download/products/<id>/file.pdf pattern
        dl_url = f"/download/products/{saved_id}/file.pdf"
        try:
            req = urllib.request.Request(BASE + dl_url, headers={"Accept": "application/pdf"})
            with urllib.request.urlopen(req, timeout=30) as r:
                exported_pdf_bytes = r.read()
                pdf_downloaded = True
        except Exception:
            pass

    if not zip_downloaded:
        dl_url = f"/download/products/{saved_id}/package.zip"
        try:
            req = urllib.request.Request(BASE + dl_url, headers={"Accept": "application/zip"})
            with urllib.request.urlopen(req, timeout=30) as r:
                zip_bytes = r.read()
                zip_downloaded = True
        except Exception:
            pass

    if not passfail("PDF downloaded (direct)", pdf_downloaded,
                   f"{len(exported_pdf_bytes)} bytes" if exported_pdf_bytes else "not found"):
        all_ok = False

    if not passfail("ZIP downloaded (direct)", zip_downloaded,
                   f"{len(zip_bytes)} bytes" if zip_bytes else "not found"):
        all_ok = False

    # ── Step 4: PDF comparison ─────────────────────────────────────────────
    print("\n-- Step 4: Compare direct PDF with downloaded PDF --")

    if exported_pdf_bytes:
        same_md5 = hashlib.md5(exported_pdf_bytes).hexdigest() == hashlib.md5(pdf_bytes).hexdigest()
        if not passfail("Downloaded PDF matches generated PDF (byte-identical)", same_md5,
                       f"Gen: {hashlib.md5(pdf_bytes).hexdigest()[:8]}, Download: {hashlib.md5(exported_pdf_bytes).hexdigest()[:8]}"):
            all_ok = False

    # ── Step 5: ZIP inspection ───────────────────────────────────────────────
    print("\n-- Step 5: Inspect ZIP contents --")

    forbidden = ["ebook.pdf", "ebook.html", "ebook.txt", "FALLBACK"]
    if zip_bytes:
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                names = zf.namelist()
                if not passfail("ZIP has files", len(names) > 0, f"Files: {names}"):
                    all_ok = False
                ebook_files = [n for n in names if "ebook" in n.lower()]
                if not passfail("No ebook fallback files", not ebook_files, f"Found: {ebook_files}"):
                    all_ok = False
                pdf_in_zip = [n for n in names if n.endswith(".pdf")]
                if not passfail(f"ZIP contains PDF ({len(pdf_in_zip)})", bool(pdf_in_zip), str(pdf_in_zip)):
                    all_ok = False
                if pdf_in_zip:
                    zip_pdf = zf.read(pdf_in_zip[0])
                    same_as_direct = hashlib.md5(zip_pdf).hexdigest() == hashlib.md5(pdf_bytes).hexdigest()
                    if not passfail("ZIP PDF matches generated PDF", same_as_direct,
                                   f"ZIP MD5: {hashlib.md5(zip_pdf).hexdigest()[:8]}"):
                        all_ok = False
        except zipfile.BadZipFile:
            passfail("ZIP is valid", False, "Bad ZIP file")
            all_ok = False
    else:
        passfail("ZIP contents checked", False, "ZIP not downloaded")

    # ── Step 6: Answer key in downloads ───────────────────────────────────
    print("\n-- Step 6: Answer key in downloaded files --")

    for label, pdf_data in [("Generated PDF", pdf_bytes), ("Downloaded PDF", exported_pdf_bytes), ("ZIP PDF", None)]:
        if label == "ZIP PDF" and zip_bytes:
            try:
                with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                    pdf_names = [n for n in zf.namelist() if n.endswith(".pdf")]
                    if pdf_names:
                        pdf_data = zf.read(pdf_names[0])
                        label = f"ZIP {pdf_names[0]}"
            except Exception:
                pdf_data = None

        if pdf_data:
            tp = pdf_text_extract(pdf_data)
            has_ak = any("answer key" in p.lower() for p in tp)
            if not passfail(f"Answer key in {label}", has_ak,
                           [f"Page {i+1}: {p[:80]}" for i, p in enumerate(tp)]):
                all_ok = False

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("CUSTOMER-PATH SUMMARY")
    print("=" * 60)
    print(f"  Paid API calls: 0 (custom words, no AI)")
    print()
    if all_ok:
        print("  ALL CHECKS PASSED")
    else:
        print("  SOME CHECKS FAILED")
    sys.exit(0 if all_ok else 1)

if __name__ == "__main__":
    main()
