import sqlite3, hashlib, subprocess

db = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\projects.db'
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM projects WHERE user_saved=1 AND system_test=0 AND temporary=0')
real = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM projects WHERE user_saved=0 OR system_test=1 OR temporary=1')
hidden = cur.fetchone()[0]
print('Real products:', real)
print('Hidden test/debug:', hidden)
cur.execute("SELECT id, name FROM projects WHERE user_saved=1 AND system_test=0 AND temporary=0 ORDER BY updated_at DESC LIMIT 3")
for r in cur.fetchall():
    print('  Recent:', r[1][:50])
conn.close()

appjs = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\static\js\app.js'
h = hashlib.md5(open(appjs,'rb').read()).hexdigest()
print('app.js md5:', h)

r = subprocess.run(['node','--check', appjs], capture_output=True, text=True)
print('Syntax check:', 'PASS' if r.returncode == 0 else 'FAIL: ' + r.stderr[:200])

# Check key elements exist in index.html
index = open(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\templates\index.html', encoding='utf-8').read()
checks = [
    ('Upgrade Plan button', 'Upgrade Plan'),
    ('Plan badge', 'Plan: Starter'),
    ('Quick Actions section', 'Create New Product'),
    ('Product Type Shortcuts', 'Popular Product Types'),
    ('Ebook shortcut', 'data-ft=ebook'),
    ('Subscription section', 'data-view="subscription"'),
    ('Free plan card', 'Starter'),
    ('Sidebar section groups', 'Create & Build'),
    ('Ad Scripts renamed', 'Promotion Packages'),
]
for label, term in checks:
    found = term in index
    print(f'  {label}: {"FOUND" if found else "MISSING"}')
