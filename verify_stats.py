import urllib.request, json

# Check app.js stats rendering is correct
appjs_path = r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\static\js\app.js'
with open(appjs_path, encoding='utf-8') as f:
    js = f.read()

stats_labels = [
    'Saved Products',
    'Promotion Packages',
    'Launch Packages',
    'Promotion Packages',
]
for label in stats_labels:
    found = label in js
    print(f'Stats label "{label}" in app.js: {"FOUND" if found else "MISSING"}')

# Check the sidebar NAV has section headers
nav_sections = ['Create & Build', 'Publish & Sell', 'Account']
for section in nav_sections:
    found = section in js
    print(f'Sidebar section "{section}" in app.js: {"FOUND" if found else "MISSING"}')

# Check subscription nav item
found = 'subscription' in js
print(f'Subscription in NAV: {"FOUND" if found else "MISSING"}')

# Check factory type buttons have data-ft
found = 'btn.dataset.ft = t.id' in js
print(f'data-ft attribute on factory types: {"FOUND" if found else "MISSING"}')

# Verify launch package count fix
found = '_launch_package' in js and 'counts.launch++' in js
print(f'Launch Packages stat (fixed): {"FOUND" if found else "MISSING"}')
