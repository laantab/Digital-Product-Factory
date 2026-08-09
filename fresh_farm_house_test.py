import requests, json, base64, fitz, os, zipfile

url = "http://127.0.0.1:5000/generate-product"
payload = {
    "product_type": "coloring_book",
    "fields": {
        "coloring_title": "Farm House",
        "theme": "Farm House",
        "output_format": "Single Sheet",
        "pages": "1",
        "quality_mode": "AI Image Coloring Page",
        "age_group": "12-adult",
        "art_style": "realistic",
        "include_captions": "No",
        "page_size": "US Letter"
    }
}

print("FRESH USER-PATH TEST: Farm House Single Sheet")
print("=" * 60)
resp = requests.post(url, json=payload, timeout=300)
print(f"HTTP Status: {resp.status_code}")

if resp.status_code != 200:
    print(f"Error: {resp.text[:500]}")
    exit(1)

data = resp.json()
pkg_id = data.get("package_id", "")
filename = data.get("filename", "")
layout = data.get("layout_info", {})
errors = data.get("errors", [])

print(f"package_id: {pkg_id}")
print(f"filename: {filename}")
print(f"layout: {layout}")
print(f"errors: {errors}")

# Decode PDF
pdf_b64 = data.get("pdf_bytes", "")
pdf_bytes = base64.b64decode(pdf_b64)
print(f"\nPDF size: {len(pdf_bytes):,} bytes")

doc = fitz.open(stream=pdf_bytes, filetype="pdf")
print(f"Page count: {doc.page_count}")

for i, p in enumerate(doc):
    t = p.get_text().strip()
    imgs = p.get_images(full=True)
    print(f"  Page {i+1}: text_chars={len(t)}, imgs={len(imgs)}, text={repr(t[:80])}")

# Render page to PNG
out_dir = "exports/fresh_farm_house_test"
os.makedirs(out_dir, exist_ok=True)
out_path = os.path.join(out_dir, filename)
with open(out_path, "wb") as f:
    f.write(pdf_bytes)

mat = fitz.Matrix(2, 2)
pix = doc[0].get_pixmap(matrix=mat)
png_path = os.path.join(out_dir, filename.replace(".pdf", "_preview.png"))
pix.save(png_path)
print(f"\nPDF saved: {out_path}")
print(f"PNG preview: {png_path}")

# ZIP export test: save project first, then export
print("\n--- ZIP Export Test ---")

# 1. Create project
proj_resp = requests.post(
    "http://127.0.0.1:5000/projects",
    json={"name": "Farm House Single Sheet Test", "type": "product", "data": {}},
    timeout=10
)
print(f"Create project: {proj_resp.status_code}")
proj_id = proj_resp.json().get("id") if proj_resp.status_code == 201 else None

if proj_id:
    # 2. Update project with generation data
    project_data = {
        "name": "Farm House Single Sheet Test",
        "type": "product",
        "data": {
            "product_type": "coloring_book",
            "is_pdf": True,
            "pdf_bytes": pdf_b64,
            "filename": filename,
            "title": "Farm House",
            "fields": payload["fields"],
            "package_id": pkg_id,
            "layout_info": layout,
        }
    }
    upd = requests.put(
        f"http://127.0.0.1:5000/projects/{proj_id}",
        json=project_data,
        timeout=10
    )
    print(f"Update project: {upd.status_code}")

    # 3. Export
    exp_resp = requests.post(
        "http://127.0.0.1:5000/export-product",
        json={"project_id": proj_id},
        timeout=30
    )
    print(f"Export: {exp_resp.status_code}")
    if exp_resp.status_code == 200:
        exp = exp_resp.json()
        exp_pkg = exp.get("export_package_id", "")
        print(f"Export package_id: {exp_pkg}")
        zipped = f"exports/{exp_pkg}/package.zip"
        if os.path.exists(zipped):
            with zipfile.ZipFile(zipped, "r") as zf:
                names = zf.namelist()
                print(f"ZIP files: {names}")
            with zipfile.ZipFile(zipped, "r") as zf:
                zipped_pdf = zf.read(filename)
                matches = zipped_pdf == pdf_bytes
                print(f"ZIP PDF matches generated PDF: {matches}")
                print(f"ZIP path: {zipped}")
        else:
            print(f"ZIP not found: {zipped}")
    else:
        print(f"Export error: {exp_resp.text[:300]}")
else:
    print("Could not create project for ZIP test")

print()
print("=" * 60)
print("VERIFICATION SUMMARY")
print("=" * 60)
all_ok = (
    resp.status_code == 200
    and len(errors) == 0
    and doc.page_count == 1
    and layout.get("cover_page_count", 99) == 0
    and all(len(p.get_text().strip()) == 0 for p in doc)
)
for i, p in enumerate(doc):
    t = p.get_text().strip()
    print(f"Page {i+1}: {len(t)} text chars, {len(p.get_images())} images")

print()
print(f"Page count = 1: {doc.page_count == 1}")
print(f"Cover count = 0: {layout.get('cover_page_count', 99) == 0}")
print(f"Errors = 0: {len(errors) == 0}")
print(f"Zero text on all pages: {all(len(p.get_text().strip()) == 0 for p in doc)}")
print(f"Image on page: {len(doc[0].get_images()) > 0}")
print()
print(f"FINAL RESULT: {'PASS' if all_ok else 'FAIL'}")
