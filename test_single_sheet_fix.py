"""
Phase 4: Single Sheet structural tests (basic_test mode).
"""
import os, sys, fitz, base64, zipfile

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv()

from services.factory.puzzle_plan import parse_puzzle_output_plan, normalize_coloring_page_count

TEST_OUT = "exports/single_sheet_tests"
os.makedirs(TEST_OUT, exist_ok=True)

PASS = "PASS"
FAIL = "FAIL"

results = {}

# ── Test 1: Logic-level check ────────────────────────────────────────────────
print("TEST 1: Single Sheet, captions=No — logic-level check")
fields1 = {
    "coloring_title": "Farm House",
    "theme": "Farm House",
    "output_format": "Single Sheet",
    "pages": "1",
    "quality_mode": "basic_test",
    "art_style": "realistic",
    "age_group": "12-adult",
    "include_captions": "No",
    "page_size": "US Letter",
    "product_type": "coloring_book",
}

plan1 = parse_puzzle_output_plan(fields1, product_type="coloring_book")
ot1 = plan1.get("output_type", "book")
rc1 = int(fields1.get("pages", "1") or "1")
pages1, _ = normalize_coloring_page_count(ot1, rc1)

# Apply the enforcement
if ot1 == "single_page":
    pages1 = 1
    plan1 = dict(plan1, include_cover=False)

ic1 = plan1.get("include_cover", plan1.get("is_book", True))
print(f"  output_type: {ot1!r}")
print(f"  pages (enforced): {pages1}")
print(f"  include_cover (enforced): {ic1}")
print(f"  Expected: output_type='single_page', pages=1, include_cover=False")

t1 = (ot1 == "single_page" and pages1 == 1 and ic1 == False)
print(f"  RESULT: {PASS if t1 else FAIL}")
results["Test 1"] = t1


# ── Test 2: captions=Yes logic ────────────────────────────────────────────────
print()
print("TEST 2: Single Sheet, captions=Yes — logic-level check")
fields2 = {
    "coloring_title": "Country Barn",
    "theme": "Country Barn",
    "output_format": "Single Sheet",
    "pages": "1",
    "quality_mode": "basic_test",
    "art_style": "Cartoon comic-book",
    "age_group": "12-adult",
    "include_captions": "Yes",
    "page_size": "US Letter",
    "product_type": "coloring_book",
}

plan2 = parse_puzzle_output_plan(fields2, product_type="coloring_book")
ot2 = plan2.get("output_type", "book")
rc2 = int(fields2.get("pages", "1") or "1")
pages2, _ = normalize_coloring_page_count(ot2, rc2)

if ot2 == "single_page":
    pages2 = 1
    plan2 = dict(plan2, include_cover=False)

ic2 = plan2.get("include_cover", plan2.get("is_book", True))
print(f"  output_type: {ot2!r}")
print(f"  pages (enforced): {pages2}")
print(f"  include_cover (enforced): {ic2}")
print(f"  Expected: output_type='single_page', pages=1, include_cover=False")

t2 = (ot2 == "single_page" and pages2 == 1 and ic2 == False)
print(f"  RESULT: {PASS if t2 else FAIL}")
results["Test 2"] = t2


# ── Test 3: Digital Book preserved ──────────────────────────────────────────
print()
print("TEST 3: Digital Book — logic preserved")
fields3 = {
    "coloring_title": "Ocean Adventures",
    "theme": "Ocean Adventures",
    "output_format": "Digital Book",
    "pages": "5",
    "quality_mode": "basic_test",
    "art_style": "Cartoon comic-book",
    "age_group": "12-adult",
    "include_captions": "No",
    "page_size": "US Letter",
    "product_type": "coloring_book",
}

plan3 = parse_puzzle_output_plan(fields3, product_type="coloring_book")
ot3 = plan3.get("output_type", "book")
rc3 = int(fields3.get("pages", "1") or "1")
pages3, _ = normalize_coloring_page_count(ot3, rc3)

if ot3 == "single_page":
    pages3 = 1
    plan3 = dict(plan3, include_cover=False)

ic3 = plan3.get("include_cover", plan3.get("is_book", True))
print(f"  output_type: {ot3!r}")
print(f"  pages: {pages3}")
print(f"  include_cover: {ic3}")
print(f"  Expected: output_type='book', pages=5, include_cover=True")

t3 = (ot3 == "book" and pages3 >= 5 and ic3 == True)
print(f"  RESULT: {PASS if t3 else FAIL}")
results["Test 3"] = t3


# ── Test 4: Full integration with basic_test PDF (AI skipped) ─────────────────
print()
print("TEST 4: Full PDF generation (basic_test mode, no AI)")
print("  Running full _coloring_book_pdf_payload (basic_test)...")
print("  [this calls AI for prompts only; image generation skipped in basic_test]")

from services.product import _coloring_book_pdf_payload

try:
    result4 = _coloring_book_pdf_payload(fields1)
    pdf_bytes4 = base64.b64decode(result4["pdf_bytes"])
    pdf_path4 = os.path.join(TEST_OUT, "farm_house_basic_test.pdf")
    with open(pdf_path4, "wb") as f:
        f.write(pdf_bytes4)

    doc4 = fitz.open(stream=pdf_bytes4, filetype="pdf")
    pages4 = []
    for i, page in enumerate(doc4):
        text = page.get_text().strip()
        imgs = page.get_images(full=True)
        pages4.append({
            "num": i + 1,
            "text_chars": len(text),
            "text_preview": text[:80] if text else "(no text)",
            "image_count": len(imgs),
        })

    layout4 = result4.get("layout_info", {})
    print(f"  Page count: {doc4.page_count}")
    print(f"  Cover pages: {layout4.get('cover_page_count', 0)}")
    for p in pages4:
        print(f"    Page {p['num']}: chars={p['text_chars']}, imgs={p['image_count']}, text={repr(p['text_preview'])}")

    t4 = (
        doc4.page_count == 1
        and layout4.get("cover_page_count", 99) == 0
        and all(p["text_chars"] == 0 for p in pages4)
    )
    print(f"  RESULT: {PASS if t4 else FAIL}")
    results["Test 4"] = t4
    print(f"  PDF saved: {pdf_path4}")
except Exception as e:
    print(f"  EXCEPTION: {e}")
    results["Test 4"] = False


# ── Test 5: ZIP export ───────────────────────────────────────────────────────
print()
print("TEST 5: ZIP export contains correct PDF")
try:
    project_dict = {
        "data": {
            "product_type": "coloring_book",
            "is_pdf": True,
            "pdf_bytes": base64.b64encode(pdf_bytes4).decode("utf-8"),
            "filename": result4.get("filename", "farm_house_basic_test.pdf"),
            "title": "Farm House",
        },
        "name": "Farm House Single Sheet",
        "type": "product",
    }
    from services.packaging import build_product_export
    z_result = build_product_export(project_dict)
    z_pkg_id = z_result.get("package_id", "")
    z_path = f"exports/{z_pkg_id}/package.zip"
    pdf_name = result4.get("filename", "farm_house_basic_test.pdf")

    if os.path.exists(z_path):
        with zipfile.ZipFile(z_path, "r") as zf:
            names = zf.namelist()
            has_pdf = pdf_name in names
            matches = False
            if has_pdf:
                matches = zf.read(pdf_name) == pdf_bytes4
        print(f"  ZIP path: {z_path}")
        print(f"  ZIP files: {names}")
        print(f"  Has PDF: {has_pdf}")
        print(f"  PDF matches: {matches}")
        t5 = has_pdf and matches
    else:
        print(f"  ZIP not found: {z_path}")
        t5 = False
    print(f"  RESULT: {PASS if t5 else FAIL}")
    results["Test 5"] = t5
except Exception as e:
    print(f"  EXCEPTION: {e}")
    results["Test 5"] = False


# ── Summary ─────────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("FINAL RESULTS")
print("=" * 60)
all_pass = all(results.values())
for name, result in results.items():
    print(f"  {name}: {PASS if result else FAIL}")
print()
print(f"ALL TESTS: {PASS if all_pass else FAIL}")
