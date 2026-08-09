import sqlite3, json, uuid as uuid_module, os

DB = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\projects.db'

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Add product_uuid column if it doesn't exist
cols = [r[1] for r in conn.execute('PRAGMA table_info(projects)').fetchall()]
print(f'Existing columns: {cols}')

if 'product_uuid' not in cols:
    conn.execute('ALTER TABLE projects ADD COLUMN product_uuid TEXT')
    conn.commit()
    print('Added product_uuid column')
else:
    print('product_uuid column already exists')

# Populate product_uuid for all existing projects that don't have one
for r in conn.execute('SELECT id, data FROM projects').fetchall():
    d = json.loads(r['data'])
    puuid = d.get('product_uuid', '')
    if not puuid:
        puuid = uuid_module.uuid4().hex
        d['product_uuid'] = puuid
        conn.execute(
            'UPDATE projects SET data = ? WHERE id = ?',
            (json.dumps(d), r['id'])
        )
    else:
        print(f'  ID={r["id"]}: already has product_uuid={puuid}')

conn.commit()

# Verify no duplicate product_uuids
uuids = [r[0] for r in conn.execute('SELECT product_uuid FROM projects WHERE product_uuid IS NOT NULL').fetchall()]
duplicates = len(uuids) - len(set(uuids))
print(f'Total projects: {len(uuids)} | Unique UUIDs: {len(set(uuids))} | Duplicates: {duplicates}')

# Verify product_uuid is now in all ebook records
for tid, label in [(3, 'Fast Cash Now'), (28, 'Test/Etsy'), (60, 'Taming Your Pup #1'), (61, 'Taming Your Pup #2'), (62, 'AI Model')]:
    r = conn.execute('SELECT id, data FROM projects WHERE id = ?', (tid,)).fetchone()
    if r:
        d = json.loads(r['data'])
        puuid = d.get('product_uuid', '')
        print(f'  {label} (ID={tid}): product_uuid={puuid}')

conn.close()
print()
print('Database protection applied.')
