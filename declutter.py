import sqlite3
import re

conn = sqlite3.connect(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\projects.db')
conn.row_factory = sqlite3.Row

# ── Patterns ──────────────────────────────────────────────────────────────────
# Matches test/debug/QA/validation/system patterns in project names.
# Extended beyond the backend regex to catch everything listed in the request.
TEST_NAME_PATTERNS = re.compile(
    r"(?i)"
    r"\b("
    r"test|workflow\.?test|pipeline\.?test|validation|regression|smoke|"
    r"qa\.?test|debug|unit\.?test|integration\.?test|bench"
    r"|download\.?proof|next\.?steps|nest\.?steps|math\.?final|handoff"
    r"|verification\.?test|\[test\]|test/|test-"
    r")\b",
    re.VERBOSE,
)

# Real user products that contain "Test" as a legitimate product name variant
# (e.g. "Fit After 50 QA Test" — user may have downloaded this as a real product)
# These get NEEDS_USER_DECISION instead of auto-flagging.
REAL_PRODUCT_LIKE = re.compile(
    r"(?i)^(fit\.?after\.?50|reclaim\.?the\.?night|taming\.?your\.?pup|"
    r"bold\.?kawaii|farm\.?animals|easy\.?budget|budget\.?meal|"
    r"flexible\.?focus|no\.?screen|remote\.?job|etsy\.?digital|"
    r"local\.?service\.?social|ai\.?at\.?work|4.?week)"
)

def is_clutter(name: str) -> bool:
    return bool(TEST_NAME_PATTERNS.search(name))

# ── Scan visible records ──────────────────────────────────────────────────────
visible = conn.execute(
    "SELECT id, name, type, user_saved, system_test, temporary "
    "FROM projects WHERE user_saved=1 AND system_test=0 AND temporary=0 "
    "ORDER BY id"
).fetchall()

clutter = []
real_products = []
needs_decision = []

for r in visible:
    name = r['name']
    if is_clutter(name):
        # Check if this looks like a real product with "test" in the version/name
        if REAL_PRODUCT_LIKE.search(name):
            needs_decision.append(dict(r))
        else:
            clutter.append(dict(r))
    else:
        real_products.append(dict(r))

print(f"=== SCAN RESULTS ===")
print(f"Total visible records: {len(visible)}")
print(f"  Real products (no test patterns): {len(real_products)}")
print(f"  Auto-flaggable clutter: {len(clutter)}")
print(f"  Needs user decision: {len(needs_decision)}")

print(f"\n=== AUTO-FLAGGABLE CLUTTER ({len(clutter)}) ===")
for r in clutter:
    print(f"  [{r['id']}] '{r['name']}' ({r['type']})")

print(f"\n=== NEEDS USER DECISION ({len(needs_decision)}) ===")
for r in needs_decision:
    print(f"  [{r['id']}] '{r['name']}' ({r['type']})")

print(f"\n=== REAL PRODUCTS ({len(real_products)}) ===")
for r in real_products:
    print(f"  [{r['id']}] '{r['name']}' ({r['type']})")

# ── Apply cleanup ──────────────────────────────────────────────────────────────
print(f"\n=== APPLYING CLEANUP ===")
conn2 = sqlite3.connect(r'C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\projects.db')
count = 0
for r in clutter:
    cur = conn2.execute(
        "UPDATE projects SET system_test=1, temporary=1, user_saved=0 WHERE id=?",
        (r['id'],)
    )
    if cur.rowcount:
        count += 1
        print(f"  Flagged: [{r['id']}] '{r['name']}'")
conn2.commit()

# Verify new counts
after_visible = conn.execute(
    "SELECT COUNT(*) FROM projects WHERE user_saved=1 AND system_test=0 AND temporary=0"
).fetchone()[0]
after_hidden = conn.execute(
    "SELECT COUNT(*) FROM projects WHERE NOT (user_saved=1 AND system_test=0 AND temporary=0)"
).fetchone()[0]
print(f"\nAfter cleanup:")
print(f"  Visible (user_saved=1,sys=0,temp=0): {after_visible}")
print(f"  Hidden: {after_hidden}")
print(f"  Records updated: {count}")

conn.close()
conn2.close()
