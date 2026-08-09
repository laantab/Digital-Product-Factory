"""Full coloring book PDF generation test."""
from dotenv import load_dotenv
load_dotenv()

import os, base64, uuid

# Generate the full coloring book PDF
from services.product import _generate_coloring_book_pdf

fields = {
    "coloring_title": "Thunder Volt Man",
    "theme": "Thunder Volt Man superhero with lightning powers protecting a city power station",
    "output_format": "Single Sheet",
    "quality_mode": "AI Image Coloring Page",
    "age_group": "12-adult",
    "pages": "1",
    "art_style": "Cartoon comic-book",
    "include_captions": "No",
    "page_size": "US Letter"
}

print("Generating coloring book PDF...")
result = _generate_coloring_book_pdf(fields)

print(f"Errors: {result.get('errors', [])}")
print(f"Warnings: {result.get('warnings', [])}")
print(f"Filename: {result.get('filename', 'N/A')}")
print(f"Package ID: {result.get('package_id', 'N/A')}")
print(f"Is PDF: {result.get('is_pdf', False)}")
print(f"Layout info: {result.get('layout_info', {})}")

pkg_id = result.get("package_id", "")
if pkg_id:
    export_dir = f"exports/{pkg_id}"
    print(f"\nExport directory: {export_dir}")
    if os.path.isdir(export_dir):
        files = os.listdir(export_dir)
        print(f"Files in export dir ({len(files)}):")
        for f in files:
            fpath = os.path.join(export_dir, f)
            size = os.path.getsize(fpath)
            print(f"  {f}: {size:,} bytes")
    else:
        print(f"Export dir does not exist: {export_dir}")

# Check image files
coloring_png = f"exports/coloring_book/coloring_p01.png"
if os.path.isfile(coloring_png):
    print(f"\nImage found: {coloring_png}")
    print(f"Image size: {os.path.getsize(coloring_png):,} bytes")

pdf_bytes = result.get("pdf_bytes", "")
if pdf_bytes:
    print(f"\nPDF in response: YES ({len(pdf_bytes):,} chars base64)")
else:
    print("\nPDF in response: NO")
