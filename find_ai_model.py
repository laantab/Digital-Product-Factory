import sqlite3, json, os

DB_PATH = os.path.join(os.path.dirname(__file__), "projects.db")
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.execute("SELECT id, name, type, created_at, updated_at FROM projects ORDER BY updated_at DESC")
for row in cursor.fetchall():
    print(row["id"], row["type"], row["name"], row["updated_at"])
conn.close()
