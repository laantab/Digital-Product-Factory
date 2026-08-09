import sqlite3, json, os

DB = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\projects.db'
EXPORT_BASE = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\exports'

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

rows = conn.execute('SELECT id, type, name, created_at, updated_at, data FROM projects ORDER BY id').fetchall()
print(f'Total projects in DB: {len(rows)}')
print()

# Build map: export_folder -> ebook.txt content
export_content_map = {}
if os.path.isdir(EXPORT_BASE):
    for folder in os.listdir(EXPORT_BASE):
        fp = os.path.join(EXPORT_BASE, folder)
        if os.path.isdir(fp):
            et = os.path.join(fp, 'ebook.txt')
            if os.path.exists(et):
                with open(et, 'r', encoding='utf-8', errors='replace') as f:
                    export_content_map[folder] = f.read().strip()

print('=== FULL PROJECT AUDIT ===')
print()

for r in rows:
    d = json.loads(r['data'])
    pt = d.get('product_type', 'N/A')
    title = r['name']
    slug = d.get('slug', '')
    preview_html = d.get('preview_html')
    preview_title = preview_html.get('title', '') if isinstance(preview_html, dict) else ''
    export_dir = d.get('export_dir') or d.get('exports', {}).get('folder', '') or ''
    cover_asset = ''
    cover_data = d.get('cover', {})
    if isinstance(cover_data, dict):
        cover_asset = cover_data.get('asset', '') or cover_data.get('image', '') or cover_data.get('background', '')
    elif isinstance(cover_data, str):
        cover_asset = cover_data

    # Flags
    flags = []
    if title != preview_title and preview_title:
        flags.append('TITLE_MISMATCH')
    if pt == 'ebook' and export_dir and export_dir in export_content_map:
        content = export_content_map[export_dir]
        if content and content != title:
            flags.append(f'EXPORT_CONTENT_MISMATCH: "{content}"')

    # Check orphan exports (no matching project)
    print(f'ID={r["id"]:3d} | type={pt:15s} | name={str(title)[:50]:50s} | slug={str(slug)[:30]:30s}')
    print(f'  created={r["created_at"]} | updated={r["updated_at"]}')
    print(f'  export_dir={export_dir!r} | cover_asset={cover_asset!r}')
    if preview_title:
        print(f'  preview_title={preview_title!r}')
    if flags:
        print(f'  FLAGS: {flags}')
    else:
        print(f'  FLAGS: OK')

    # Content checks for ebooks
    if pt == 'ebook':
        sections = d.get('sections', [])
        layout_data = d.get('layout_data', {})
        print(f'  sections_count={len(sections)} | layout_keys={list(layout_data.keys())[:5]}')
        # Check first section title
        if sections:
            first = sections[0] if isinstance(sections[0], str) else (sections[0].get('title', '') if isinstance(sections[0], dict) else '')
            if first:
                print(f'  first_section={first!r}')

    # Check export folder content
    if export_dir and export_dir in export_content_map:
        print(f'  export_ebook.txt="{export_content_map[export_dir]}"')
    elif export_dir:
        print(f'  export_ebook.txt: NOT FOUND (folder={export_dir!r})')

    print()

conn.close()

print()
print('=== ORPHAN EXPORT FOLDERS (no matching project) ===')
# Find export folders not referenced by any project
all_export_dirs = set(export_content_map.keys())
referenced_dirs = set()
conn2 = sqlite3.connect(DB)
conn2.row_factory = sqlite3.Row
for r2 in conn2.execute('SELECT data FROM projects').fetchall():
    d2 = json.loads(r2['data'])
    ed = d2.get('export_dir') or d2.get('exports', {}).get('folder', '') or ''
    if ed:
        referenced_dirs.add(ed)
conn2.close()

orphan = all_export_dirs - referenced_dirs
if orphan:
    for folder in sorted(orphan):
        content = export_content_map[folder]
        print(f'  ORPHAN folder={folder!r} ebook.txt="{content}"')
        # List files in orphan folder
        fp = os.path.join(EXPORT_BASE, folder)
        for f in os.listdir(fp):
            sz = os.path.getsize(os.path.join(fp, f))
            print(f'    {f}: {sz:,} bytes')
else:
    print('  None found')
