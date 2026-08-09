import requests, time

BASE = "http://127.0.0.1:5000"

# Get project 250 (Flexible Focus Weekly Kit)
r = requests.get(f"{BASE}/projects/250", timeout=5)
p = r.json()
print(f"Product: {p.get('name')}")
print(f"Has data: {bool(p.get('data'))}")
data = p.get("data") or {}
print(f"Title: {data.get('title', 'N/A')}")
print(f"Audience: {data.get('audience', 'N/A')[:60]}")
print(f"Problem: {data.get('problem', 'N/A')[:60]}")

# Generate launch package
print("\nGenerating launch package (this takes ~60s)...")
t0 = time.time()
r2 = requests.post(
    f"{BASE}/generate-launch-package",
    json={"project_id": 250, "promotion_goal": "sell_paid_product"},
    timeout=180,
)
t1 = time.time()
print(f"Status: {r2.status_code} ({t1-t0:.1f}s)")

if r2.status_code == 200:
    result = r2.json()
    pkg = result.get("package", result)
    fb = pkg.get("freebie", {})
    op = pkg.get("optin_page", {})
    sp = pkg.get("sales_page", {})
    tw = pkg.get("thank_you_tripwire", {})
    es = pkg.get("email_sequence", {})
    ad = pkg.get("ad_package", {})

    print("\n=== SECTION 1: Freebie Builder ===")
    print(f"  Name: {fb.get('freebie_name', 'MISSING')}")
    print(f"  Format: {fb.get('freebie_format', 'MISSING')}")
    print(f"  Opt-in headline: {fb.get('freebie_optin_headline', 'MISSING')[:80]}")

    print("\n=== SECTION 2: Opt-in Page ===")
    print(f"  Headline: {op.get('headline', 'MISSING')[:80]}")
    print(f"  CTA: {op.get('signup_cta', 'MISSING')}")

    print("\n=== SECTION 3: Sales Page ===")
    print(f"  Headline: {sp.get('headline', 'MISSING')[:80]}")
    print(f"  Price: {sp.get('price_display', 'MISSING')}")
    print(f"  CTA: {sp.get('cta_button', 'MISSING')}")

    print("\n=== SECTION 4: Thank-You / Tripwire ===")
    print(f"  Tripwire headline: {tw.get('tripwire_headline', 'MISSING')[:80]}")
    print(f"  Tripwire CTA: {tw.get('tripwire_cta', 'MISSING')}")

    print("\n=== SECTION 5: Ad Package ===")
    print(f"  Has short_video_scripts: {len(ad.get('short_video_scripts', []))} scripts")
    print(f"  Has pinterest_pins: {len(ad.get('pinterest_pins', []))} pins")
    print(f"  Has facebook_posts: {len(ad.get('facebook_posts', []))} posts")
    print(f"  Has seven_day_plan: {bool(ad.get('seven_day_plan'))}")

    print("\n=== SECTION 6: Email Sequence ===")
    emails = es.get("emails", [])
    print(f"  Email count: {len(emails)}")
    for i, em in enumerate(emails):
        print(f"  [{i+1}] {em.get('subject', 'MISSING')[:60]}")

    print("\n=== SECTION 7: Delivery Checklist ===")
    dc = pkg.get("delivery_checklist", "")
    print(f"  Length: {len(dc)} chars")
    print(f"  Has 'PDF': {'PDF' in dc}")

    print("\n=== SECTION 8: Launch Checklist ===")
    lc = pkg.get("launch_checklist", "")
    print(f"  Length: {len(lc)} chars")
    print(f"  Has 'Week Before': {'Week Before' in lc}")

    print("\n[PASS] All 8 sections present")

    # Test download endpoint
    print("\nTesting ZIP download...")
    r3 = requests.get(f"{BASE}/download-launch-package/250", timeout=10)
    print(f"  ZIP status: {r3.status_code}")
    print(f"  Content-Type: {r3.headers.get('Content-Type', '')}")
    print(f"  Content-Length: {len(r3.content)} bytes")
    if r3.status_code == 200 and "zip" in r3.headers.get("Content-Type", ""):
        print("[PASS] ZIP download works")
    else:
        print(f"[FAIL] ZIP download: {r3.text[:100]}")

else:
    print(f"FAIL: {r2.status_code} | {r2.text[:300]}")
