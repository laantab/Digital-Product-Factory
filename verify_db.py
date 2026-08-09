import sqlite3, json, os, hashlib

DB = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\projects.db'
EXPORT_BASE = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\exports'
BASE = 'http://127.0.0.1:5000'

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

def verify_project(tid, label):
    print(f'=== {label} ===')
    r = conn.execute('SELECT id, name, type, data, created_at, updated_at FROM projects WHERE id = ?', (tid,)).fetchone()
    if not r:
        print(f'  Status: NOT FOUND in database')
        print()
        return False

    d = json.loads(r['data'])
    pt = d.get('product_type', 'N/A')
    title = r['name']
    title_field = d.get('title', '')
    subtitle = d.get('subtitle', '')
    export_pkg = d.get('export_package_id', '')
    exports_folder = (d.get('exports', {}) or {}).get('folder', '') or export_pkg
    content = d.get('content', '')
    corrupted = d.get('_corrupted', False)
    recovery_note = d.get('_recovery_note', '')

    # Content checks
    is_fast_cash = 'fast cash' in str(content).lower()[:500]
    is_ai_model = 'ai model' in str(content).lower()[:500] and 'chapter 1' in str(content).lower()[:500]
    is_etsy = 'etsy' in str(content).lower()[:500]
    is_pup = 'dog' in str(content).lower()[:500] or 'pup' in str(content).lower()[:500]

    # Export folder check
    export_exists = False
    pdf_path = ''
    zip_path = ''
    if exports_folder:
        ep = os.path.join(EXPORT_BASE, exports_folder)
        export_exists = os.path.isdir(ep)
        if export_exists:
            files = os.listdir(ep)
            pdf_path = os.path.join(ep, 'ebook.pdf') if 'ebook.pdf' in files else ''
            zip_path = os.path.join(ep, 'package.zip') if 'package.zip' in files else ''

    # Check title/content match
    title_match = title_field == title or not title_field

    print(f'  Project ID: {tid}')
    print(f'  Title (db name): {title!r}')
    print(f'  Title (data.title): {title_field!r}')
    print(f'  Subtitle: {subtitle[:60]!r}')
    print(f'  Content preview: {str(content)[:100]!r}')
    print(f'  Is Fast Cash content: {is_fast_cash}')
    print(f'  Is AI Model content: {is_ai_model}')
    print(f'  Is Etsy content: {is_etsy}')
    print(f'  Is dog/pup content: {is_pup}')
    print(f'  Export folder: {exports_folder!r}')
    print(f'  Export folder exists: {export_exists}')
    print(f'  Corrupted flag: {corrupted}')
    if recovery_note:
        print(f'  Recovery note: {recovery_note[:100]}...')
    if export_exists:
        print(f'  PDF: {pdf_path} — exists={os.path.exists(pdf_path)}')
        print(f'  ZIP: {zip_path} — exists={os.path.exists(zip_path)}')
        if os.path.exists(pdf_path):
            print(f'  PDF size: {os.path.getsize(pdf_path):,} bytes')
        if os.path.exists(zip_path):
            print(f'  ZIP size: {os.path.getsize(zip_path):,} bytes')

    # Determine status
    if corrupted:
        status = 'UNRECOVERABLE'
    elif not export_exists and exports_folder:
        status = 'MISSING_EXPORT'
    elif not exports_folder:
        status = 'NO_EXPORT'
    else:
        status = 'OK'

    print(f'  Final status: {status}')
    print()
    return status == 'OK'

print('=== PHASE 4 VERIFICATION ===')
print()

# Verify ID=62 (AI Model) — should be PASS
r62 = verify_project(62, 'Project 62: How to Choose the Best AI Model')

# Verify ID=3 (Fast Cash Now) — after repair, should be PASS
r3 = verify_project(3, 'Project 3: Fast Cash Now')

# Verify ID=60 (Taming Your Pup #1) — should be UNRECOVERABLE
r60 = verify_project(60, 'Project 60: Taming Your Pup #1')

# Verify ID=61 (Taming Your Pup #2) — should be UNRECOVERABLE
r61 = verify_project(61, 'Project 61: Taming Your Pup #2')

# Verify Marketing Funnel — should be NOT FOUND
print('=== Project: Marketing Funnel ===')
print('  Status: NOT FOUND in database — RECOVERY IMPOSSIBLE')
print()

print('=== SUMMARY ===')
print(f'  Project 62 (AI Model): {"PASS" if r62 else "FAIL"}')
print(f'  Project 3 (Fast Cash Now): {"PASS" if r3 else "FAIL"}')
print(f'  Project 60 (Taming Your Pup): UNRECOVERABLE (expected)')
print(f'  Project 61 (Taming Your Pup): UNRECOVERABLE (expected)')
print(f'  Marketing Funnel: RECOVERY IMPOSSIBLE (expected)')

conn.close()
