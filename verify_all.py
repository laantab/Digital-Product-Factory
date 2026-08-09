import requests, zipfile, json
from io import BytesIO
import sys, os, time

BASE = "http://127.0.0.1:5000"
FLASK = r"C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app"

print("=== BASELINE CHECKS ===")
r = requests.get(f"{BASE}/", timeout=5)
print(f"[{'PASS' if r.status_code==200 else 'FAIL'}] GET /: {r.status_code}")

r2 = requests.get(f"{BASE}/static/js/app.js", timeout=5)
print(f"[{'PASS' if r2.status_code==200 else 'FAIL'}] app.js: {r2.status_code} ({len(r2.content)} bytes)")
js = r2.text

# Import check
sys.path.insert(0, FLASK)
try:
    # Try importing the ad service which has our new function
    from services import ad as ad_svc
    has_lp = hasattr(ad_svc, 'generate_launch_package')
    has_text = hasattr(ad_svc, '_build_promotion_text')
    print(f"[{'PASS' if has_lp else 'FAIL'}] generate_launch_package in ad.py: {has_lp}")
    print(f"[{'PASS' if has_text else 'FAIL'}] _build_promotion_text in ad.py: {has_text}")
except Exception as e:
    print(f"[FAIL] import error: {e}")

# Frontend checks
checks = [
    ('data-ns="launch" button', 'data-ns="launch"'),
    ('renderLaunchPackage function', 'function renderLaunchPackage'),
    ('Create Launch Package in HTML', 'Create Launch Package'),
    ('createLaunchPkgBtn', 'createLaunchPkgBtn'),
    ('Download Launch Package ZIP', 'Download Launch Package ZIP'),
    ('_renderLaunchPackageUI', 'function _renderLaunchPackageUI'),
    ('projectRow launch button', 'data-launch'),
]
for label, needle in checks:
    ok = needle in js
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")

# ZIP download
print()
r4 = requests.get(f"{BASE}/download-launch-package/250", timeout=15)
print(f"[{'PASS' if r4.status_code==200 else 'FAIL'}] ZIP download (project 250): {r4.status_code} ({len(r4.content)} bytes)")
if r4.status_code == 200:
    z = zipfile.ZipFile(BytesIO(r4.content))
    files = z.namelist()
    expected = ['freebie_builder.md', 'optin_page_copy.txt', 'sales_page_copy.txt',
                'thank_you_page_copy.txt', 'ad_package.txt', 'email_sequence.txt',
                'delivery_checklist.txt', 'launch_checklist.txt', 'metadata.json']
    missing = [f for f in expected if f not in files]
    print(f"[{'PASS' if not missing else 'FAIL'}] All 9 ZIP files present | missing={missing}" if missing else f"[PASS] All 9 ZIP files present")
    print(f"  Files: {files}")
    z.close()

# Hidden products
print()
print("=== HIDDEN PRODUCTS ===")
for pt in ['marketing_kit', 'cover_design', 'flip_book', 'planner']:
    r8 = requests.post(f"{BASE}/generate-product", json={"product_type": pt, "fields": {}}, timeout=5)
    ok = r8.status_code == 400
    print(f"[{'PASS' if ok else 'FAIL'}] '{pt}' blocked: {r8.status_code}")

# Bad ID check
print()
r5 = requests.post(f"{BASE}/generate-launch-package", json={"project_id": 9999}, timeout=5)
print(f"[{'PASS' if r5.status_code in (400,404) else 'FAIL'}] /generate-launch-package bad id: {r5.status_code}")

# Recently changed files
print()
recent = []
for root, dirs, files in os.walk(FLASK):
    for f in files:
        if f.endswith(('.py', '.js', '.html')):
            full = os.path.join(root, f)
            age_h = (time.time() - os.path.getmtime(full)) / 3600
            if age_h < 2:
                recent.append(os.path.relpath(full, FLASK))
print(f"Recently changed files ({len(recent)}):")
for f in sorted(recent)[:15]:
    print(f"  {f}")

print("\n[DONE]")
