import requests, json

BASE = "http://127.0.0.1:5000"

# Step 1: Generate a word search via Product Factory
fields = {
    "title": "Animals",
    "theme": "Safari Animals",
    "audience": "Kids ages 6-9",
    "puzzle_count": "1",
    "words_per_puzzle": "10",
    "include_answer_key": "Yes",
    "include_cover": "No",
    "output_format": "single_page",
}

print("=== Step 1: Generate ===")
r = requests.post(f"{BASE}/generate-product", json={"product_type": "word_search", "fields": fields})
print(f"Status: {r.status_code}")
gen = r.json()
print(f"product_type: {gen.get('product_type')}")
print(f"has pdf_bytes: {bool(gen.get('pdf_bytes'))}")
print(f"pdf_bytes len: {len(gen.get('pdf_bytes', ''))}")
print(f"has fields: {bool(gen.get('fields'))}")
print(f"fields keys: {list(gen.get('fields', {}).keys())}")

# Step 2: Save to DB (simulate what runProduct does)
name = gen.get("title") or "Untitled Product"
body_data = {k: v for k, v in gen.items() if not k.startswith("_")}
r2 = requests.post(f"{BASE}/projects", json={
    "name": name,
    "type": "product",
    "data": body_data
})
print(f"\n=== Step 2: Save ===")
print(f"Status: {r2.status_code}")
saved = r2.json()
project_id = saved.get("id")
print(f"project_id: {project_id}")
saved_data = saved.get("data", {})
print(f"saved has pdf_bytes: {bool(saved_data.get('pdf_bytes'))}")
print(f"saved pdf_bytes len: {len(saved_data.get('pdf_bytes', ''))}")
print(f"saved has fields: {bool(saved_data.get('fields'))}")
print(f"saved has product_type: {bool(saved_data.get('product_type'))}")

# Step 3: Export (simulate what nsExport does)
print(f"\n=== Step 3: Export ===")
r3 = requests.post(f"{BASE}/export-product", json={"project_id": project_id})
print(f"Status: {r3.status_code}")
exp = r3.json()
exports = exp.get("exports", {})
files = exports.get("files", {})
pdf = files.get("pdf")
print(f"pdf_available: {exports.get('pdf_available')}")
print(f"pdf file: {pdf}")
print(f"Full exports keys: {list(exports.keys())}")

# Step 4: Simulate nsExport reuse check
print(f"\n=== Step 4: nsExport reuse logic ===")
has_existing = bool(saved_data.get("exports", {}).get("files")) or bool(saved_data.get("product_exports"))
print(f"Would reuse existing exports: {has_existing}")
print(f"d.exports: {saved_data.get('exports')}")
print(f"d.product_exports: {saved_data.get('product_exports')}")
