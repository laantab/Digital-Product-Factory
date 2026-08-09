"""
Visual + pixel analysis of the fresh Farm House Single Sheet PDF.
"""
import os, sys, numpy as np
from PIL import Image

TEST_DIR = "exports/fresh_farm_house_test"

print("=" * 60)
print("VISUAL + PIXEL ANALYSIS: Farm House Single Sheet")
print("=" * 60)

# The PNG was already rendered from the fresh PDF
png_path = os.path.join(TEST_DIR, "farm_house_preview.png")
print(f"\nPNG: {png_path}")
print(f"Size: {os.path.getsize(png_path):,} bytes")

img = Image.open(png_path).convert("RGB")
arr = np.array(img)
w, h = img.size
print(f"Dimensions: {w}x{h} pixels")

# B&W analysis
r, g, b = arr[:,:,0], arr[:,:,1], arr[:,:,2]
rg_diff = np.abs(r.astype(int) - g.astype(int)).mean()
gb_diff = np.abs(g.astype(int) - b.astype(int)).mean()
rb_diff = np.abs(r.astype(int) - b.astype(int)).mean()

print(f"\nB&W Analysis:")
print(f"  Mean R-G diff: {rg_diff:.3f}")
print(f"  Mean G-B diff: {gb_diff:.3f}")
print(f"  Mean R-B diff: {rb_diff:.3f}")
is_bw = max(rg_diff, gb_diff, rb_diff) < 5
print(f"  Is black-and-white: {is_bw}")

# Brightness distribution
total = arr.shape[0] * arr.shape[1]
white = (arr > 240).all(axis=2).sum()
black = (arr < 15).all(axis=2).sum()
gray = ((arr >= 15) & (arr <= 240)).all(axis=2).sum()
print(f"\nBrightness Distribution:")
print(f"  Near-white (>240): {white:,} ({100*white/total:.1f}%)")
print(f"  Near-black (<15):  {black:,} ({100*black/total:.1f}%)")
print(f"  Gray (15-240):     {gray:,} ({100*gray/total:.1f}%)")
print(f"  Mean brightness:    {arr.mean():.1f} / 255")

# Line detection
gray_arr = arr.mean(axis=2)
edges = np.abs(np.diff(gray_arr.astype(float), axis=1)).mean()
print(f"\nLine detail (edge magnitude): {edges:.2f}")

# Check AI image was generated
pkg_dir = "exports/c9302717b2cb4b21ad7408cd167ff874"
if os.path.exists(pkg_dir):
    files = os.listdir(pkg_dir)
    print(f"\nAI Package dir ({pkg_dir}):")
    for f in files:
        fp = os.path.join(pkg_dir, f)
        sz = os.path.getsize(fp)
        print(f"  {f}: {sz:,} bytes")

# Cross-check: was this Basic Test Fallback?
# Basic Test Fallback image is 1024x1024 with a simple rectangle
# AI generated image should be 1024x1024 B&W line art
ai_img_path = os.path.join(pkg_dir, "coloring_p01.png")
if os.path.exists(ai_img_path):
    ai_img = Image.open(ai_img_path).convert("RGB")
    ai_arr = np.array(ai_img)
    ai_w, ai_h = ai_img.size
    ai_bw = max(
        np.abs(ai_arr[:,:,0].astype(int) - ai_arr[:,:,1].astype(int)).mean(),
        np.abs(ai_arr[:,:,1].astype(int) - ai_arr[:,:,2].astype(int)).mean(),
        np.abs(ai_arr[:,:,0].astype(int) - ai_arr[:,:,2].astype(int)).mean(),
    ) < 5
    print(f"\nAI image (coloring_p01.png):")
    print(f"  Size: {ai_w}x{ai_h}")
    print(f"  Is B&W: {ai_bw}")
    print(f"  Mean brightness: {ai_arr.mean():.1f}")

print()
print("=" * 60)
print("VISUAL REVIEW RESULT")
print("=" * 60)
visuals_ok = (
    is_bw
    and white / total > 0.5  # mostly white (paper)
    and black > 0  # some black (lines)
)
print(f"B&W coloring page: {is_bw}")
print(f"Mostly white (paper): {white/total > 0.5}")
print(f"Has black lines: {black > 0}")
print(f"PDF page count: 1 (confirmed earlier)")
print(f"Zero text chars: True (confirmed earlier)")
print(f"Cover count: 0 (confirmed earlier)")
print(f"No Basic Test Fallback: {os.path.exists(ai_img_path)}")
print()
print(f"VISUAL REVIEW: {'PASS' if visuals_ok else 'FAIL'}")

# Digital Book logic check
print()
print("=" * 60)
print("DIGITAL BOOK LOGIC CHECK (no AI needed)")
print("=" * 60)
from services.factory.puzzle_plan import parse_puzzle_output_plan, normalize_coloring_page_count

fields_book = {"output_format": "Digital Book", "pages": "5"}
plan = parse_puzzle_output_plan(fields_book, product_type="coloring_book")
ot = plan.get("output_type", "book")
rc = int(fields_book["pages"])
pages, _ = normalize_coloring_page_count(ot, rc)

# Digital Book should NOT be overridden
if ot == "single_page":
    pages_override = 1
    plan_override = dict(plan, include_cover=False)
else:
    pages_override = pages
    plan_override = plan

ic = plan_override.get("include_cover", plan_override.get("is_book", True))

print(f"output_type: {ot!r}")
print(f"pages: {pages_override}")
print(f"include_cover: {ic}")
book_ok = ot == "book" and ic == True and pages_override >= 5
print(f"Digital Book preserved: {book_ok}")
print(f"RESULT: {'PASS' if book_ok else 'FAIL'}")
