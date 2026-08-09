import sqlite3, json, requests

BASE = "http://127.0.0.1:5000"
conn = sqlite3.connect('C:/Users/user/Documents/Product-Pipeline/Product-Pipeline/flask_app/projects.db')
conn.row_factory = sqlite3.Row

# Check for crossword projects
rows = conn.execute("""
    SELECT id, name, data
    FROM projects
    WHERE type = 'product'
    ORDER BY updated_at DESC
""").fetchall()

crossword_projects = []
for r in rows:
    d = json.loads(r['data'])
    if d.get('product_type') == 'crossword':
        crossword_projects.append({
            'id': r['id'],
            'name': r['name'],
            'has_pdf_bytes': bool(d.get('pdf_bytes')),
            'has_fields': bool(d.get('fields')),
        })

print(f"Crossword projects found: {len(crossword_projects)}")
for p in crossword_projects:
    print(f"  ID={p['id']} name={p['name']!r} pdf_bytes={p['has_pdf_bytes']} fields={p['has_fields']}")

# Test crossword export
for p in crossword_projects[:3]:
    try:
        r = requests.post(f"{BASE}/export-product", json={"project_id": p['id']})
        exp = r.json()
        if r.status_code != 200:
            print(f"  ID={p['id']}: ERROR {r.status_code} - {exp}")
        else:
            files = exp.get('exports', {}).get('files', {})
            pdf = files.get('pdf')
            print(f"  ID={p['id']}: pdf={bool(pdf)} → {pdf}")
    except Exception as e:
        print(f"  ID={p['id']}: Exception: {e}")

conn.close()
