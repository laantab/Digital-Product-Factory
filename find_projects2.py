import sqlite3, json, os, sys

# Try different DB paths
for db_path in ['products.db', 'data/products.db', 'projects.db']:
    if not os.path.exists(db_path):
        continue
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.execute(
            "SELECT id, name, type, data FROM projects WHERE type='product' ORDER BY id DESC LIMIT 30"
        )
        rows = cur.fetchall()
        print(f"=== {db_path} ({len(rows)} rows) ===")
        print(f"{'ID':<6} {'title':<35} {'product_type':<20} {'output_format':<20} {'num_pages':<8} {'has_pdf'}")
        print("-" * 105)
        for r in rows[:20]:
            pid, name, ptype, blob = r
            try:
                d = json.loads(blob)
                pt = d.get('product_type', '')
                fields = d.get('fields') or {}
                fmt = fields.get('output_format', '')
                num_pages = fields.get('num_pages', '')
                title = d.get('title', '')
                has_pdf = bool(d.get('pdf_bytes'))
                pdf_len = len(d.get('pdf_bytes', '')) if has_pdf else 0
            except Exception as e:
                pt = f'ERR:{e}'
                fmt = '?'
                num_pages = '?'
                title = '?'
                has_pdf = False
                pdf_len = 0
            print(f"{pid:<6} {str(title)[:33]:<35} {str(pt)[:18]:<20} {str(fmt)[:18]:<20} {str(num_pages):<8} {str(has_pdf):<8} pdf_len={pdf_len}")
        conn.close()
        print()
    except Exception as e:
        print(f"{db_path}: {e}\n")
