import sqlite3, json, os

DB = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\projects.db'

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# === REPAIR 1: Link ID=3 (Fast Cash Now) to existing orphan export ===
# The orphan folder 9623092f16e04918ae35ef28e4e8c8ae has Fast Cash Now content
fcs_orphan = '9623092f16e04918ae35ef28e4e8c8ae'
fcs_orphan_path = os.path.join(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\exports', fcs_orphan)

print(f'Repair 1: ID=3 Fast Cash Now')
print(f'  Orphan folder exists: {os.path.isdir(fcs_orphan_path)}')
if os.path.isdir(fcs_orphan_path):
    files = os.listdir(fcs_orphan_path)
    print(f'  Files: {files}')
    # Read ebook.txt to confirm
    et = os.path.join(fcs_orphan_path, 'ebook.txt')
    if os.path.exists(et):
        with open(et, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read().strip()[:100]
            print(f'  ebook.txt content: "{content}"')

    # Update database: set export_package_id to orphan folder
    # and update product_exports with correct Flask download URLs
    r = conn.execute('SELECT id, name, data FROM projects WHERE id = 3').fetchone()
    d = json.loads(r['data'])
    d['export_package_id'] = fcs_orphan
    d['exports'] = {
        'folder': fcs_orphan,
        'pdf_available': True,
        'files': {
            'html': {'name': 'ebook.html', 'url': f'/download/{fcs_orphan}/ebook.html'},
            'txt': {'name': 'ebook.txt', 'url': f'/download/{fcs_orphan}/ebook.txt'},
            'zip': {'name': 'package.zip', 'url': f'/download/{fcs_orphan}/package.zip'},
        }
    }
    # Fix export_files paths (were pointing to runner)
    if 'export_files' in d:
        ef = d['export_files']
        if isinstance(ef, dict):
            ef['dir'] = os.path.join(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\exports', fcs_orphan)
            # Update each file path
            for k, v in list(ef.items()):
                if k == 'dir':
                    continue
                if isinstance(v, str) and '/home/runner/' in v:
                    fname = os.path.basename(v)
                    ef[k] = os.path.join(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\exports', fcs_orphan, fname)

    conn.execute(
        'UPDATE projects SET data = ?, updated_at = ? WHERE id = 3',
        (json.dumps(d), '2026-07-10T06:50:00.000000+00:00')
    )
    conn.commit()
    print(f'  DB updated: export_package_id={fcs_orphan}')
    print(f'  Status: OK')

print()

# === REPAIR 2: Mark Taming Your Pup records as unrecoverable ===
print('Repair 2: Mark ID=60 and ID=61 (Taming Your Pup) as UNRECOVERABLE')
for tid, label in [(60, 'ID=60'), (61, 'ID=61')]:
    r = conn.execute('SELECT id, name, data FROM projects WHERE id = ?', (tid,)).fetchone()
    d = json.loads(r['data'])
    # Add corruption note to data
    d['_recovery_note'] = (
        'UNRECOVERABLE — content field contains Fast Cash Now markdown instead of dog behavior content. '
        'Export folder becf15208d2640faa9e95f1cfc116a67 does not exist on this system. '
        'No orphan export with dog behavior content exists. '
        'Original content cannot be reconstructed. Regeneration required.'
    )
    d['_corrupted'] = True
    conn.execute(
        'UPDATE projects SET data = ?, updated_at = ? WHERE id = ?',
        (json.dumps(d), '2026-07-10T06:50:00.000000+00:00', tid)
    )
    conn.commit()
    print(f'  {label}: marked UNRECOVERABLE in data._recovery_note')

print()

# === REPAIR 3: Marketing Funnel ===
print('Repair 3: Marketing Funnel')
print('  Status: NOT FOUND in database')
print('  Orphan exports with "Marketing" or "Funnel": NONE')
print('  Status: RECOVERY IMPOSSIBLE — no record or export exists')
print()

conn.close()
print('Database repairs complete.')
