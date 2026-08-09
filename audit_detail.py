import sqlite3, json

DB = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\projects.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Focus on ebook projects and related orphans
targets = [2, 3, 28, 60, 61, 62]

print('=== DETAILED EBOOK PROJECT DATA ===')
for tid in targets:
    r = conn.execute('SELECT id, type, name, created_at, updated_at, data FROM projects WHERE id = ?', (tid,)).fetchone()
    if not r:
        print(f'ID={tid}: NOT FOUND')
        continue
    d = json.loads(r['data'])
    print(f'--- ID={r["id"]} ---')
    print(f'  name: {r["name"]!r}')
    print(f'  type: {r["type"]!r}')
    print(f'  product_type: {d.get("product_type")!r}')
    print(f'  created: {r["created_at"]}')
    print(f'  updated: {r["updated_at"]}')
    print(f'  export_dir: {d.get("export_dir")!r}')
    print(f'  preview_html type: {type(d.get("preview_html")).__name__}')
    if isinstance(d.get('preview_html'), dict):
        ph = d['preview_html']
        print(f'  preview_html title: {ph.get("title")!r}')
        print(f'  preview_html keys: {list(ph.keys())}')
    elif d.get('preview_html'):
        print(f'  preview_html (str): {str(d["preview_html"])[:100]!r}')
    cover = d.get('cover', {})
    if isinstance(cover, dict):
        print(f'  cover keys: {list(cover.keys())}')
    print(f'  sections_count: {len(d.get("sections", []))}')
    print(f'  layout_data keys: {list(d.get("layout_data", {}).keys())}')
    print(f'  data keys: {list(d.keys())}')
    print()

# Check for Marketing Funnel in DB
print('=== SEARCHING FOR MARKETING FUNNEL ===')
for r in conn.execute('SELECT id, type, name, created_at, updated_at FROM projects').fetchall():
    if 'marketing' in r['name'].lower() or 'funnel' in r['name'].lower():
        print(f'  FOUND: ID={r["id"]} name={r["name"]!r}')

# Search data for Marketing Funnel
for r in conn.execute('SELECT id, name, data FROM projects').fetchall():
    d = json.loads(r['data'])
    ph = d.get('preview_html', {})
    if isinstance(ph, dict):
        t = ph.get('title', '')
        if 'marketing' in t.lower() or 'funnel' in t.lower():
            print(f'  FOUND in preview_html title: ID={r["id"]} preview.title={t!r}')
    # Check sections
    sections = d.get('sections', [])
    if sections:
        first = sections[0] if isinstance(sections[0], str) else (sections[0].get('title', '') if isinstance(sections[0], dict) else '')
        if 'marketing' in str(first).lower() or 'funnel' in str(first).lower():
            print(f'  FOUND in sections[0]: ID={r["id"]} section[0]={first!r}')

conn.close()
