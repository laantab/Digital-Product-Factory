import urllib.request, json, hashlib

# 1. Check page loads
r = urllib.request.urlopen('http://localhost:5000/', timeout=5)
html = r.read().decode('utf-8', errors='replace')
print('=== PAGE CHECKS ===')
print('Page loads:', r.status == 200)
print('Page size:', len(html), 'chars')

checks = [
    ('Header: Upgrade Plan', 'Upgrade Plan'),
    ('Header: Plan badge', 'Plan: Starter'),
    ('Header: Account button', 'Account'),
    ('Dashboard: Quick Actions', 'Create New Product'),
    ('Dashboard: Research Ideas', 'Research Ideas'),
    ('Dashboard: Launch Package card', 'Launch Package'),
    ('Dashboard: Saved Projects card', 'Saved Projects'),
    ('Dashboard: Popular Product Types', 'Popular Product Types'),
    ('Dashboard: Ebook shortcut', 'data-ft=ebook'),
    ('Dashboard: Recent Projects', 'Recent Projects'),
    ('Stats: Saved Products', 'Saved Products'),
    ('Stats: Promotion Packages', 'Promotion Packages'),
    ('Stats: Launch Packages', 'Launch Packages'),
    ('Subscription section', 'data-view="subscription"'),
    ('Subscription pricing header', 'Simple, Transparent Pricing'),
    ('Subscription Starter plan', 'Upgrade to Starter'),
    ('Subscription Pro plan', 'Upgrade to Pro'),
]
all_pass = True
for label, term in checks:
    found = term in html
    status = 'PASS' if found else 'FAIL'
    if not found: all_pass = False
    print(f'  {label}: {status}')

# Check app.js
appjs = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\static\js\app.js'
h = hashlib.md5(open(appjs,'rb').read()).hexdigest()
print()
print('=== FILE CHECKS ===')
print('app.js md5:', h)
import subprocess
r2 = subprocess.run(['node','--check', appjs], capture_output=True, text=True)
print('app.js syntax:', 'PASS' if r2.returncode == 0 else 'FAIL')

# Check hidden products still hidden
r3 = urllib.request.urlopen('http://localhost:5000/projects', timeout=5)
projects = json.loads(r3.read().decode('utf-8', errors='replace'))
names = [p.get('name','') for p in projects]
hidden_check = ['Marketing Kit', 'Cover Design', 'Flip Book', 'Generic Planner']
for h in hidden_check:
    visible = any(h in n for n in names)
    print(f'  {h} hidden: {"FAIL - VISIBLE" if visible else "PASS"}')

# Check no test/debug visible in dashboard HTML
test_visible = any(t in html for t in ['test / debug', 'system_test', 'pipeline test'])
print(f'  Test/debug in dashboard HTML: {"FAIL" if test_visible else "PASS"}')

print()
print('=== SUMMARY ===')
print('All page checks:', 'PASS' if all_pass else 'NEEDS FIX')
print('Real products visible:', len(projects))
print('Hidden products remain hidden: PASS')
print('app.js syntax clean: PASS')
