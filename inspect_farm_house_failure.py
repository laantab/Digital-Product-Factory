"""
Compare the two 13-page Farm House exports to understand what changed.
"""
import os, sys, fitz, json, sqlite3

sys.path.insert(0, os.path.dirname(__file__))

# Old export: ID 69, pkg_id = 88a1c5efad29414cb9f10804b5919661
old_pdf = "exports/88a1c5efad29414cb9f10804b5919661/the_farm_house.pdf"
# New export: ID 70, pkg_id = 770f5c272c2c4f5c85c68a5e3904a639
new_pdf = "exports/770f5c272c2c4f5c85c68a5e3904a639/the_farm_house.pdf"

print("OLD (ID 69, 2026-07-11 20:47) - 13 pages with cover:")
doc_old = fitz.open(old_pdf)
print(f"  Pages: {doc_old.page_count}")
for i, p in enumerate(doc_old):
    t = p.get_text().strip()
    imgs = p.get_images(full=True)
    print(f"  Page {i+1}: chars={len(t)}, imgs={len(imgs)}, text={repr(t[:60])}")

print()
print("NEW (ID 70, 2026-07-12 08:29) - 13 pages:")
doc_new = fitz.open(new_pdf)
print(f"  Pages: {doc_new.page_count}")
for i, p in enumerate(doc_new):
    t = p.get_text().strip()
    imgs = p.get_images(full=True)
    print(f"  Page {i+1}: chars={len(t)}, imgs={len(imgs)}, text={repr(t[:60])}")

print()
print("ANALYSIS:")
print("  Both are 13 pages.")
print("  OLD: page 1 is image+no text (cover), pages 2-13 are coloring pages with text")
print("  NEW: page 1 is image+no text, pages 2-13 are coloring pages with text")
print("  Both have 1 image per page.")
print("  NEW was generated AFTER the first fix attempt (which only fixed basic_test logic).")
print("  NEW was likely generated through the UI without the Single Sheet enforcement.")

# Check what the NEW generation (pkg f1346f5d) looks like
print()
print("NEWEST CORRECT GENERATION (pkg f1346f5d, 2026-07-12 08:55):")
newest = "exports/f1346f5d57fb45dbacce34bf570852db/farm_house.pdf"
doc_n = fitz.open(newest)
print(f"  Pages: {doc_n.page_count}")
for i, p in enumerate(doc_n):
    t = p.get_text().strip()
    imgs = p.get_images(full=True)
    print(f"  Page {i+1}: chars={len(t)}, imgs={len(imgs)}, text={repr(t[:60])}")

# Check the PDF bytes size comparison
print()
print("PDF SIZE COMPARISON:")
for label, path in [("OLD 13-page", old_pdf), ("NEW 13-page", new_pdf), ("NEWEST 1-page", newest)]:
    sz = os.path.getsize(path)
    print(f"  {label}: {sz:,} bytes")
