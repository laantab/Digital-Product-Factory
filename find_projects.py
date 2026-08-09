import sqlite3, json

conn = sqlite3.connect('instance/products.db')
cur = conn.execute(
    "SELECT id, name, type, data FROM projects WHERE type='product' ORDER BY id DESC LIMIT 30"
)
rows = cur.fetchall()
print(f"{'ID':<6} {'title':<40} {'product_type':<20} {'output_format':<20} {'pages':<8} {'has_pdf'}")
print("-" * 110)
for r in rows:
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
    print(f"{pid:<6} {str(title)[:38]:<40} {str(pt)[:18]:<20} {str(fmt)[:18]:<20} {str(num_pages):<8} {str(has_pdf):<8} pdf_len={pdf_len}")
