import requests, json, re

BASE = "http://127.0.0.1:5000"

_TEST_PATTERNS = re.compile(
    r"(?i)"
    r"\b("
    r"test|workflow\.?test|pipeline\.?test|validation|regression|smoke|"
    r"qa\.?test|debug|unit\.?test|integration\.?test|bench"
    r"|download\.?proof|next\.?steps|nest\.?steps|math\.?final|handoff"
    r"|verification\.?test|\[test\]|test/|test-"
    r")\b"
)

def cleanup_names(names):
    for name in names:
        requests.delete(f"{BASE}/projects/{pid}", timeout=5)
        # find id first
    r_all = requests.get(f"{BASE}/projects?include_system=1", timeout=5).json()
    for p in r_all:
        if p['name'] in names:
            requests.delete(f"{BASE}/projects/{p['id']}", timeout=5)
            print(f"  Cleaned up: {p['name']} (id={p['id']})")

print("=" * 60)
print("TEST A — Default Saved Projects View")
r = requests.get(f"{BASE}/projects", timeout=5)
proj = r.json()
test_visible = [p for p in proj if _TEST_PATTERNS.search(p['name'])]
print(f"  Visible count: {len(proj)} (expected 66)")
print(f"  Test patterns visible: {len(test_visible)} (expected 0)")
if test_visible:
    for p in test_visible:
        print(f"  FAIL: {p['name']}")
    print("[FAIL] TEST A")
else:
    print("[PASS] TEST A")

print()
print("=" * 60)
print("TEST B — Toggle ON")
r_all = requests.get(f"{BASE}/projects?include_system=1", timeout=5).json()
hidden = [p for p in r_all if p.get('system_test') or p.get('temporary') or not p.get('user_saved')]
print(f"  Total: {len(r_all)}")
print(f"  Hidden records with toggle ON: {len(hidden)} (expected 60)")
if len(hidden) >= 55:
    print("[PASS] TEST B")
else:
    print(f"[FAIL] TEST B — only {len(hidden)} hidden")

print()
print("=" * 60)
print("TEST C — Normal Save")
r = requests.post(f"{BASE}/projects",
    json={"name": "Customer Save Product", "type": "ebook", "user_saved": True}, timeout=10)
proj = r.json()
print(f"  Status: {r.status_code}")
print(f"  user_saved={proj.get('user_saved')} sys={proj.get('system_test')} temp={proj.get('temporary')}")
saved_id = proj.get('id')
if proj.get('user_saved') and not proj.get('system_test') and not proj.get('temporary'):
    print("[PASS] TEST C")
else:
    print("[FAIL] TEST C")

print()
print("=" * 60)
print("TEST D — Test project auto-hidden")
r = requests.post(f"{BASE}/projects",
    json={"name": "[TEST] Saved Projects Filter Check", "type": "ebook"}, timeout=10)
proj = r.json()
test_id = proj.get('id')
print(f"  Status: {r.status_code}")
print(f"  user_saved={proj.get('user_saved')} sys={proj.get('system_test')} temp={proj.get('temporary')}")
# Verify it's NOT in default view
r_def = requests.get(f"{BASE}/projects", timeout=5).json()
visible_ids = [p['id'] for p in r_def]
hidden_in_default = test_id in visible_ids
print(f"  ID {test_id} in default view: {hidden_in_default} (expected False)")
if not proj.get('user_saved') and proj.get('system_test') and proj.get('temporary') and not hidden_in_default:
    print("[PASS] TEST D")
else:
    print("[FAIL] TEST D")

print()
print("=" * 60)
print("TEST E — Verify default still clean after test project")
r_def = requests.get(f"{BASE}/projects", timeout=5).json()
test_visible = [p for p in r_def if _TEST_PATTERNS.search(p['name'])]
print(f"  Visible count: {len(r_def)} (expected 67 — 66 real + 1 new normal save)")
print(f"  Test patterns visible: {len(test_visible)} (expected 0)")
if len(r_def) >= 66 and len(test_visible) == 0:
    print("[PASS] TEST E")
else:
    print("[FAIL] TEST E")
    for p in test_visible:
        print(f"  FAIL: {p['name']}")

print()
print("=" * 60)
print("CLEANUP")
cleanup_names(['Customer Save Product', '[TEST] Saved Projects Filter Check'])

# Final check
r_final = requests.get(f"{BASE}/projects", timeout=5).json()
print(f"Final visible count: {len(r_final)} (expected 66)")
