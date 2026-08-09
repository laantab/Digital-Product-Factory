import requests, json, re

BASE = "http://127.0.0.1:5000"

def test(name, expected_status, check_fn=None):
    try:
        r = requests.request(method="POST", url=f"{BASE}/projects",
                             json={"name": name, "type": "ebook", "user_saved": True}, timeout=10)
        result = {"status": r.status_code, "body": r.json()}
    except Exception as e:
        result = {"error": str(e)}
    status_ok = result.get("status") == expected_status
    fn_ok = check_fn(result) if check_fn else True
    tag = "PASS" if (status_ok and fn_ok) else "FAIL"
    print(f"[{tag}] {name}")
    if not status_ok:
        print(f"  Expected status {expected_status}, got {result.get('status')} | {result}")
    elif not fn_ok:
        print(f"  Check failed: {result}")
    else:
        print(f"  {result.get('status')} OK")
    return tag == "PASS"


# ── Test D: New Test Project ──────────────────────────────────────────────────
print("\n=== TEST D: New Test Project ===")
_TEST_PATTERNS = re.compile(
    r"(?i)"
    r"\b("
    r"test|workflow\.?test|pipeline\.?test|validation|regression|smoke|"
    r"qa\.?test|debug|unit\.?test|integration\.?test|bench"
    r"|download\.?proof|next\.?test|math\.?final|handoff"
    r"|verification\.?test|\[test\]|test/|test-"
    r")\b"
)

r = requests.post(f"{BASE}/projects",
                  json={"name": "[TEST] Saved Projects Filter Check", "type": "ebook"},
                  timeout=10)
proj = r.json()
print(f"  Status={r.status_code}")
print(f"  name='{proj.get('name')}'")
print(f"  user_saved={proj.get('user_saved')} system_test={proj.get('system_test')} temporary={proj.get('temporary')}")

if r.status_code == 200 and not proj.get('user_saved') and proj.get('system_test') and proj.get('temporary'):
    print("[PASS] Test project auto-hidden")
else:
    print("[FAIL] Flags not correct")

# ── Test E: Verify visible still correct ────────────────────────────────────
print("\n=== VERIFY: Default visible still 66 ===")
r = requests.get(f"{BASE}/projects", timeout=5)
proj_list = r.json()
visible = [p for p in proj_list if not (
    p.get('system_test') or p.get('temporary') or not p.get('user_saved')
)]
test_visible = [p for p in visible if _TEST_PATTERNS.search(p['name'])]
print(f"  Visible count: {len(visible)} (expected 66)")
print(f"  Test patterns in visible: {len(test_visible)} (expected 0)")
if len(visible) == 66 and len(test_visible) == 0:
    print("[PASS] Default view clean")
else:
    print("[FAIL] View not clean")
    for p in test_visible:
        print(f"  STILL VISIBLE: {p['name']}")

# Clean up test records
print("\n=== Cleanup test records ===")
ids_to_delete = []
r_all = requests.get(f"{BASE}/projects?include_system=1", timeout=5).json()
for p in r_all:
    if p['name'] in ('Customer Save Product', '[TEST] Saved Projects Filter Check', 'Customer Save Test Product'):
        ids_to_delete.append(p['id'])
for pid in ids_to_delete:
    requests.delete(f"{BASE}/projects/{pid}", timeout=5)
print(f"  Deleted: {ids_to_delete}")
