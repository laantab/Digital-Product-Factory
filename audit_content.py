import sqlite3, json

DB = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\projects.db'
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Check content of each ebook record
for tid, label in [(3, 'ID=3 Fast Cash Now'), (28, 'ID=28 Test'), (60, 'ID=60 Taming Your Pup #1'), (61, 'ID=61 Taming Your Pup #2'), (62, 'ID=62 AI Model')]:
    r = conn.execute('SELECT id, name, created_at, updated_at, data FROM projects WHERE id = ?', (tid,)).fetchone()
    d = json.loads(r['data'])
    content = d.get('content', '')
    title_field = d.get('title', '')
    subtitle = d.get('subtitle', '')
    preview_html = d.get('preview_html', '')
    if isinstance(preview_html, str):
        # Extract title from HTML
        import re
        m = re.search(r'<title[^>]*>([^<]+)</title>', preview_html, re.IGNORECASE)
        html_title = m.group(1) if m else ''
        # Check for Fast Cash content
        is_fast_cash = 'fast cash' in preview_html.lower() or 'fast cash' in str(content).lower()
        is_ai_model = 'ai model' in preview_html.lower() or 'ai model' in str(content).lower()
        is_etsy = 'etsy' in preview_html.lower() or 'etsy' in str(content).lower()
        is_pup = 'pup' in preview_html.lower() or 'pup' in str(content).lower()
        is_marketing = 'marketing' in preview_html.lower() or 'marketing' in str(content).lower()
        # Get first 200 chars of content
        content_preview = str(content)[:300] if content else '(empty)'
        exports = d.get('exports', {})
        export_files = d.get('export_files', [])
        pexp = d.get('product_exports', {})
        print(f'=== {label} ===')
        print(f'  db_name={r["name"]!r}')
        print(f'  title field={title_field!r}')
        print(f'  subtitle={subtitle!r}')
        print(f'  html_title={html_title!r}')
        print(f'  content_preview={content_preview!r}')
        print(f'  Fast Cash: {is_fast_cash}')
        print(f'  AI Model: {is_ai_model}')
        print(f'  Etsy: {is_etsy}')
        print(f'  Pup: {is_pup}')
        print(f'  Marketing: {is_marketing}')
        print(f'  exports={exports}')
        print(f'  export_files={export_files}')
        print(f'  product_exports keys={list(pexp.keys()) if pexp else "empty"}')
        print()

# Search ALL records for Marketing Funnel by title/content
print('=== FULL DATABASE SEARCH FOR MARKETING FUNNEL ===')
found = False
for r in conn.execute('SELECT id, type, name, created_at, updated_at, data FROM projects').fetchall():
    d = json.loads(r['data'])
    name = r['name']
    title_field = str(d.get('title', '')).lower()
    content = str(d.get('content', '')).lower()
    preview = str(d.get('preview_html', '')).lower()
    if 'marketing' in name.lower() or 'funnel' in name.lower() or 'marketing' in title_field or 'funnel' in title_field or 'marketing funnel' in content or 'marketing funnel' in preview:
        print(f'  FOUND: ID={r["id"]} name={name!r} type={r["type"]}')
        print(f'    title={d.get("title")!r}')
        found = True
if not found:
    print('  NOT FOUND anywhere in database')

conn.close()
