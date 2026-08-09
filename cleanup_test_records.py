import requests
BASE = "http://127.0.0.1:5000"
names = ['Customer Save Product', '[TEST] Saved Projects Filter Check']
r = requests.get(f"{BASE}/projects?include_system=1", timeout=5).json()
for p in r:
    if p['name'] in names:
        requests.delete(f"{BASE}/projects/{p['id']}", timeout=5)
        print(f"Deleted: {p['name']} (id={p['id']})")
r2 = requests.get(f"{BASE}/projects", timeout=5).json()
print(f"Final visible count: {len(r2)} (expected 66)")
