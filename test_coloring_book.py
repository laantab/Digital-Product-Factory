"""
Coloring Book Generator — Phase 3 Test Script
Tests the local fallback generator WITHOUT AI configured.
"""
import sys, os, base64, io, zipfile, time
sys.path.insert(0, os.path.dirname(__file__))

FLASK_APP = r"C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app"
OUTPUT_DIR = r"C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\exports\cb_tests"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ─── Utility functions ───────────────────────────────────────────────────────
def _count_pdf_pages(pdf_bytes: bytes) -> int:
    """Count pages in PDF by counting /Type /Page entries."""
    return pdf_bytes.count(b"/Type /Page")


def _write_zip(output_dir: str, name: str, pdf_path: str):
    zip_path = os.path.join(output_dir, f"{name}.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(pdf_path, os.path.basename(pdf_path))
    print(f"  ZIP written: {zip_path} ({os.path.getsize(zip_path):,} bytes)")


# ─── Test 1: Single Sheet ───────────────────────────────────────────────────
print("=" * 60)
print("TEST 1: Single Sheet — Thunder Volt Man")
print("=" * 60)
try:
    from services.coloring_book.pdf_builder import (
        ColoringBookPdfRequest, build_coloring_book_pdf,
    )
    req = ColoringBookPdfRequest(
        product_title="Thunder Volt Man",
        theme="Thunder Volt Man",
        topic="Thunder Volt Man",
        page_count=1,
        age_group="12-adult",
        art_style="Cartoon",
        include_captions=False,
        include_cover=False,
        output_type="single",
        package_id="test1_singlesheet",
    )
    result = build_coloring_book_pdf(req)
    if result.errors:
        print("FAIL — errors:", result.errors)
    else:
        pdf_bytes = result.pdf_bytes
        if not pdf_bytes:
            print("FAIL — no PDF bytes returned")
        elif not pdf_bytes.startswith(b"%PDF"):
            print("FAIL — not a valid PDF")
        else:
            path = os.path.join(OUTPUT_DIR, "test1_singlesheet.pdf")
            with open(path, "wb") as f:
                f.write(pdf_bytes)
            page_count = _count_pdf_pages(pdf_bytes)
            warnings = result.warnings or []
            print(f"PASS — PDF: {path}")
            print(f"  PDF size: {len(pdf_bytes):,} bytes")
            print(f"  Page count: {page_count}")
            print(f"  Warnings: {warnings}")
            if any("AI not available" in str(w) or "not configured" in str(w).lower() or "local" in str(w).lower() for w in warnings):
                print(f"  Local fallback used: YES")
except Exception as e:
    print(f"FAIL — exception: {e}")
    import traceback; traceback.print_exc()

# ─── Test 2: Digital Book ────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 2: Digital Book — Thunder Volt Man (12 pages + cover)")
print("=" * 60)
try:
    req2 = ColoringBookPdfRequest(
        product_title="Thunder Volt Man",
        theme="Thunder Volt Man",
        topic="Thunder Volt Man",
        page_count=12,
        age_group="12-adult",
        art_style="Cartoon",
        include_captions=False,
        include_cover=True,
        output_type="book",
        package_id="test2_digitalbook",
    )
    result2 = build_coloring_book_pdf(req2)
    if result2.errors:
        print("FAIL — errors:", result2.errors)
    else:
        pdf_bytes2 = result2.pdf_bytes
        if not pdf_bytes2:
            print("FAIL — no PDF bytes returned")
        elif not pdf_bytes2.startswith(b"%PDF"):
            print("FAIL — not a valid PDF")
        else:
            path2 = os.path.join(OUTPUT_DIR, "test2_digitalbook_thunder_volt_man.pdf")
            with open(path2, "wb") as f:
                f.write(pdf_bytes2)
            page_count2 = _count_pdf_pages(pdf_bytes2)
            layout = result2.layout_info or {}
            cover_img = result2.cover_image_path
            warnings2 = result2.warnings or []
            print(f"PASS — PDF: {path2}")
            print(f"  PDF size: {len(pdf_bytes2):,} bytes")
            print(f"  Page count: {page_count2}")
            print(f"  Layout: {layout}")
            print(f"  Cover image: {cover_img}")
            print(f"  Warnings: {warnings2}")
            if cover_img and os.path.isfile(cover_img):
                print(f"  Cover present: YES ({cover_img})")
            else:
                print(f"  Cover present: NO")
            _write_zip(OUTPUT_DIR, "test2_digitalbook", path2)
except Exception as e:
    print(f"FAIL — exception: {e}")
    import traceback; traceback.print_exc()

# ─── Test 3: Adult Realistic ─────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 3: Adult Realistic — Desert Wildlife (6 pages + cover)")
print("=" * 60)
try:
    req3 = ColoringBookPdfRequest(
        product_title="Desert Wildlife Coloring Book",
        theme="desert animals and landscapes",
        topic="Desert Wildlife",
        page_count=6,
        age_group="Adults",
        art_style="Realistic",
        include_captions=True,
        include_cover=True,
        output_type="book",
        package_id="test3_adult_realistic",
    )
    result3 = build_coloring_book_pdf(req3)
    if result3.errors:
        print("FAIL — errors:", result3.errors)
    else:
        pdf_bytes3 = result3.pdf_bytes
        if not pdf_bytes3:
            print("FAIL — no PDF bytes")
        else:
            path3 = os.path.join(OUTPUT_DIR, "test3_desert_wildlife_coloring_book.pdf")
            with open(path3, "wb") as f:
                f.write(pdf_bytes3)
            page_count3 = _count_pdf_pages(pdf_bytes3)
            layout3 = result3.layout_info or {}
            cover_img3 = result3.cover_image_path
            warnings3 = result3.warnings or []
            print(f"PASS — PDF: {path3}")
            print(f"  PDF size: {len(pdf_bytes3):,} bytes")
            print(f"  Page count: {page_count3}")
            print(f"  Layout: {layout3}")
            print(f"  Cover image: {cover_img3}")
            print(f"  Warnings: {warnings3}")
            if cover_img3 and os.path.isfile(cover_img3):
                print(f"  Cover present: YES")
            else:
                print(f"  Cover present: NO")
            _write_zip(OUTPUT_DIR, "test3_adult_realistic", path3)
except Exception as e:
    print(f"FAIL — exception: {e}")
    import traceback; traceback.print_exc()

# ─── Test 4: AI Not Configured ──────────────────────────────────────────────
print()
print("=" * 60)
print("TEST 4: AI Not Configured — confirm no hard crash")
print("=" * 60)
try:
    ai_key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
    print(f"  AI env var: {'SET' if ai_key else 'NOT SET'}")
    req4 = ColoringBookPdfRequest(
        product_title="Dinosaur Adventures",
        theme="Dinosaur Adventures",
        topic="Dinosaur Adventures",
        page_count=3,
        age_group="Kids",
        art_style="Cartoon",
        include_captions=False,
        include_cover=True,
        output_type="book",
        package_id="test4_no_ai",
    )
    result4 = build_coloring_book_pdf(req4)
    if result4.errors:
        err_str = str(result4.errors)
        if "AI is not configured" in err_str:
            print(f"FAIL — AI error still crashes: {result4.errors}")
        else:
            print(f"FAIL — other errors: {result4.errors}")
    elif not result4.pdf_bytes:
        print("FAIL — no PDF returned")
    else:
        pdf_bytes4 = result4.pdf_bytes
        path4 = os.path.join(OUTPUT_DIR, "test4_no_ai_dinosaur_adventures.pdf")
        with open(path4, "wb") as f:
            f.write(pdf_bytes4)
        page_count4 = _count_pdf_pages(pdf_bytes4)
        warnings4 = result4.warnings or []
        print(f"PASS — No hard crash with AI unconfigured")
        print(f"  PDF size: {len(pdf_bytes4):,} bytes")
        print(f"  Page count: {page_count4}")
        print(f"  Warnings: {warnings4}")
        if any("AI not available" in str(w) or "local" in str(w).lower() for w in warnings4):
            print(f"  Local fallback used: YES")
except Exception as e:
    print(f"FAIL — exception: {e}")
    import traceback; traceback.print_exc()

print()
print("=" * 60)
print("ALL TESTS COMPLETE")
print("=" * 60)
print(f"Output dir: {OUTPUT_DIR}")
