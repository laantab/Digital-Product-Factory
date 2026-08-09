import sqlite3
conn = sqlite3.connect(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\projects.db')
cur = conn.cursor()
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print("Tables:", tables)
if 'products' in tables:
    cur.execute("SELECT COUNT(*) FROM products WHERE hidden=0 AND system_test=0 AND temporary=0")
    print("Visible products:", cur.fetchone()[0])
    cur.execute("SELECT name FROM products WHERE hidden=0 AND system_test=0 AND temporary=0 ORDER BY created_at DESC LIMIT 5")
    print("Recent:", [r[0] for r in cur.fetchall()])
elif 'project' in tables:
    cur.execute("SELECT COUNT(*) FROM project WHERE hidden=0 AND system_test=0 AND temporary=0")
    print("Visible projects:", cur.fetchone()[0])
    cur.execute("SELECT name FROM project WHERE hidden=0 AND system_test=0 AND temporary=0 ORDER BY created_at DESC LIMIT 5")
    print("Recent:", [r[0] for r in cur.fetchall()])
conn.close()
