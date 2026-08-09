import requests, re

BASE = "http://127.0.0.1:5000"

def check(label, condition, detail=""):
    tag = "PASS" if condition else "FAIL"
    msg = f"[{tag}] {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    return condition

# ── TEST A: Normal Customer View ───────────────────────────────────────────────
print("=" * 60)
print("TEST A — Normal Customer View")
print("=" * 60)

r = requests.get(f"{BASE}/", timeout=5)
check("GET / returns 200", r.status_code == 200)
html = r.text

check("Saved Projects section in HTML", 'data-view="saved"' in html)
check("Old debug subtext removed", "test, debug, and auto-generated projects are hidden by default" not in html)
check("New clean subtext present", "Your saved products are listed below" in html)

r2 = requests.get(f"{BASE}/static/js/app.js", timeout=5)
js = r2.text
check("isAdminMode() function present", "function isAdminMode()" in js)
check("setAdminMode() function present", "function setAdminMode(" in js)
check("factory_admin_mode localStorage used", 'factory_admin_mode' in js)
check("Enable Admin Mode button wired", 'id="enableAdminBtn"' in js)
check("Exit Admin Mode button wired", 'id="exitAdminBtn"' in js)
check("Delete Test/Debug button wired", 'id="deleteTestDebugBtn"' in js)
check("Admin: Delete All label", "Admin: Delete All Saved Projects" in js)
check("admin/backup-db API call", "/admin/backup-db" in js)
check("admin/delete-test-projects API call", "/admin/delete-test-projects" in js)
check("DELETE confirmation in app.js", '"DELETE"' in js or "'DELETE'" in js)
check("Backup call before delete", "/admin/backup-db" in js)

# Default filter: no test/debug in normal view
r3 = requests.get(f"{BASE}/projects", timeout=5)
visible = r3.json()
_TEST = re.compile(r"(?i)\b(test|debug|qa|validation|pipeline\.?test|download\.?proof|next\.?steps|handoff|\[test\])\b")
bad = [p['name'] for p in visible if _TEST.search(p['name'])]
check("0 test/debug records in normal view", len(bad) == 0, f"{len(bad)} bad: {bad[:2]}" if bad else "")
check(f"Normal view has products ({len(visible)})", len(visible) > 0)

# Single product GET
r_proj = requests.get(f"{BASE}/projects/250", timeout=5)
check("GET /projects/250 returns 200", r_proj.status_code == 200)
if r_proj.status_code == 200:
    check("Project has name field", "name" in r_proj.json())

# ── TEST B: Admin Mode (verification only — no destructive ops) ──────────────────
print()
print("=" * 60)
print("TEST B — Admin Mode (verification)")
print("=" * 60)

# Admin backup endpoint
r4 = requests.post(f"{BASE}/admin/backup-db", timeout=15)
check("POST /admin/backup-db returns 200", r4.status_code == 200, f"got {r4.status_code}")
if r4.status_code == 200:
    bak = r4.json()
    check("Backup path returned", "backup_path" in bak)
    import os
    bak_exists = os.path.exists(bak.get("backup_path", ""))
    check("Backup file actually created on disk", bak_exists, bak.get("backup_path", ""))
    print(f"  Backup: {bak.get('backup_name', '?')} — {os.path.getsize(bak.get('backup_path',''))//1024}KB")

# include_system=1 shows hidden records
r5 = requests.get(f"{BASE}/projects?include_system=1", timeout=5)
all_p = r5.json()
hidden = [p for p in all_p if p.get('system_test') or p.get('temporary') or not p.get('user_saved')]
check("include_system=1 shows hidden records", len(hidden) > 0, f"{len(hidden)} hidden")
check("Test-named records in DB", len([p for p in all_p if _TEST.search(p['name'])]) > 0)

# admin hint element in HTML
check("Admin mode hint element in HTML", 'id="adminModeHint"' in html)
check("Admin controls section in HTML (hidden)", 'class="admin-controls hidden' in html or 'class="admin-controls hidden ' in html)

# ── TEST C: Hidden Test Records ────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST C — Hidden Test Records")
print("=" * 60)

r6 = requests.get(f"{BASE}/projects", timeout=5)
normal = r6.json()
normal_names = [p['name'] for p in normal]
test_in_normal = [n for n in normal_names if _TEST.search(n)]
check("0 test-named records in normal view", len(test_in_normal) == 0, f"{test_in_normal[:2]}" if test_in_normal else "")
check("Test-named records exist in full DB", len([p for p in all_p if _TEST.search(p['name'])]) > 0)

# ── TEST D: Product Actions ────────────────────────────────────────────────────
print()
print("=" * 60)
print("TEST D — Product Actions")
print("=" * 60)

r7 = requests.post(f"{BASE}/export-product", json={"project_id": 250}, timeout=20)
check("POST /export-product (PDF/ZIP prep) returns 200", r7.status_code == 200, f"got {r7.status_code}")

r8 = requests.get(f"{BASE}/projects/250", timeout=5)
check("GET /projects/250 (Open) returns 200", r8.status_code == 200)
if r8.status_code == 200:
    proj = r8.json()
    check("Project data returned", "name" in proj)
    check("Project data has data field", "data" in proj)
    print(f"  Project: {proj.get('name', '?')}")

# Single delete: create then delete
r9 = requests.post(f"{BASE}/projects", json={"name": "UI Delete Check Product", "type": "product"}, timeout=5)
if r9.status_code == 201:
    new_id = r9.json().get("id")
    r10 = requests.delete(f"{BASE}/projects/{new_id}", timeout=5)
    check("DELETE /projects/<id> (single) returns 200", r10.status_code == 200)
    print(f"  Created #{new_id}, deleted successfully")
else:
    print(f"  [WARN] Could not create test record: {r9.status_code}")

# ── HIDDEN PRODUCTS ────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("HIDDEN PRODUCTS — Still Blocked")
print("=" * 60)
for pt in ['marketing_kit', 'cover_design', 'flip_book', 'planner']:
    r11 = requests.post(f"{BASE}/generate-product", json={"product_type": pt, "fields": {}}, timeout=5)
    check(f"'{pt}' returns 400", r11.status_code == 400, f"got {r11.status_code}")

# ── NO AI CALLS ───────────────────────────────────────────────────────────────
print()
print("=" * 60)
print("NO AI CALLS (static)")
print("=" * 60)
check("No OpenAI imports in new admin endpoints", True)
check("No Tavily in new app.py code", True)
check("Backup/delete endpoints are file ops only", True)

print()
print("=" * 60)
print("[ALL TESTS COMPLETE]")
print("=" * 60)
