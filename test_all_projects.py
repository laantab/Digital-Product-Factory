import sqlite3, json, requests

BASE = "http://127.0.0.1:5000"
conn = sqlite3.connect('C:/Users/user/Documents/Product-Pipeline/Product-Pipeline/flask_app/projects.db')
conn.row_factory = sqlite3.Row

rows = conn.execute("""
    SELECT id, name, data
    FROM projects
    WHERE type = 'product'
    ORDER BY updated_at DESC
    LIMIT 20
""").fetchall()

print("All recent products and their export status:")
for r in rows:
    d = json.loads(r['data'])
    pt = d.get('product_type', 'N/A')
    has_pdf = bool(d.get('pdf_bytes'))
    has_ex = bool(d.get('exports', {}).get('files')) or bool(d.get('product_exports', {}).get('files'))
    pe = d.get('product_exports')
    print(f"  ID={r['id']:3d} type={pt:20s} pdf_bytes={has_pdf} exports={has_ex} pe_type={type(pe).__name__}")

# Test export on all word_search projects
ws_ids = [r['id'] for r in rows if json.loads(r['data']).get('product_type') == 'word_search']
print(f"\nExport test for {len(ws_ids)} word search projects:")
for pid in ws_ids[:5]:
    r = requests.post(f"{BASE}/export-product", json={"project_id": pid})
    exp = r.json()
    files = exp.get('exports', {}).get('files', {})
    pdf = files.get('pdf')
    print(f"  ID={pid}: pdf={bool(pdf)} → {pdf}")

conn.close()
