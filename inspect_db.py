import sqlite3
import json
import re

conn = sqlite3.connect(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\projects.db')
conn.row_factory = sqlite3.Row
cur = conn.execute("PRAGMA table_info(projects)")
cols = [r['name'] for r in cur.fetchall()]
print("Columns:", cols)

rows = conn.execute('SELECT id, name, type, user_saved, system_test, temporary FROM projects ORDER BY updated_at DESC').fetchall()
total = len(rows)
print(f'\nTotal records: {total}')

# Flag distribution
flags = {}
for r in rows:
    k = f"user_saved={r['user_saved']} system_test={r['system_test']} temporary={r['temporary']}"
    flags[k] = flags.get(k, 0) + 1
print('\nFlag distribution:')
for k, v in sorted(flags.items()):
    print(f'  {k}: {v}')

# How many would be hidden by current WHERE clause?
hidden = conn.execute(
    'SELECT COUNT(*) FROM projects WHERE user_saved=1 AND system_test=0 AND temporary=0'
).fetchone()[0]
print(f'\nRecords visible with current WHERE (user_saved=1 AND system_test=0 AND temporary=0): {hidden}')

# Names of records that are visible but contain test/debug patterns
_TEST_PATTERNS = re.compile(
    r"(?i)\b(test|workflow\.test|pipeline\.test|validation|regression|smoke|"
    r"qa\.test|debug|unit\.test|integration\.test|bench|"
    r"download\.proof|next\.steps|nest\.steps|"
    r"math\.final|handoff|handoff)\b"
)

visible_but_test = []
all_visible = conn.execute(
    'SELECT id, name, type, user_saved, system_test, temporary FROM projects WHERE user_saved=1 AND system_test=0 AND temporary=0'
).fetchall()
for r in all_visible:
    if _TEST_PATTERNS.search(r['name']):
        visible_but_test.append(r)

print(f'\nVisible records that match test/debug patterns: {len(visible_but_test)}')
for r in visible_but_test:
    print(f"  [{r['id']}] '{r['name']}' (type={r['type']})")

# Also show what's currently hidden but might be real products
all_test_hidden = conn.execute(
    'SELECT id, name, type, user_saved, system_test, temporary FROM projects WHERE NOT (user_saved=1 AND system_test=0 AND temporary=0) ORDER BY updated_at DESC LIMIT 20'
).fetchall()
print(f'\nRecently updated hidden records (sample): {len(all_test_hidden)}')
for r in all_test_hidden[:10]:
    print(f"  [{r['id']}] user_saved={r['user_saved']} sys={r['system_test']} temp={r['temporary']} | '{r['name']}'")

conn.close()
