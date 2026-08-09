import requests, pypdf, io

BASE = "http://127.0.0.1:5000"

# Step 1: Generate
r = requests.post(f"{BASE}/generate-product", json={
    "product_type": "word_search",
    "fields": {
        "title": "Animals in America",
        "theme": "American Animals",
        "audience": "Kids",
        "puzzle_count": "1",
        "words_per_puzzle": "10",
        "include_answer_key": "Yes",
        "include_cover": "No",
        "output_format": "single_page",
    }
})
gen = r.json()
pdf_b64 = gen.get("pdf_bytes", "")
filename = gen.get("filename", "no-filename")
print(f"Generation: filename={filename}, pdf_bytes_len={len(pdf_b64)}")

# Step 2: Save
body_data = {k: v for k, v in gen.items() if not k.startswith("_")}
saved = requests.post(f"{BASE}/projects", json={
    "name": gen.get("title"),
    "type": "product",
    "data": body_data
}).json()
pid = saved["id"]
print(f"Saved: project_id={pid}")

# Step 3: Export
exp = requests.post(f"{BASE}/export-product", json={"project_id": pid}).json()
files = exp["exports"]["files"]
pdf_file = files["pdf"]
print(f"Export: pdf name={pdf_file['name']!r}, url={pdf_file['url']}")

# Step 4: Download and check
dl = requests.get(BASE + pdf_file["url"])
cd = dl.headers.get("Content-Disposition", "N/A")
print(f"Download: status={dl.status_code}, Content-Disposition={cd[:80]}")
reader = pypdf.PdfReader(io.BytesIO(dl.content))
print(f"Pages: {len(reader.pages)}")
for i, p in enumerate(reader.pages):
    t = p.extract_text()
    print(f"  Page {i+1}: {t[:80]!r}")
