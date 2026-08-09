"""Direct test of Coloring Book AI generation bypassing Flask."""
from dotenv import load_dotenv
load_dotenv()

import os, sys, base64

# Verify env
key = os.environ.get("AI_INTEGRATIONS_OPENAI_API_KEY", "")
print(f"Key loaded: {'YES' if key else 'NO'}")
print(f"Key starts with: {key[:10] if key else 'N/A'}...")
print(f"Base URL: {os.environ.get('AI_INTEGRATIONS_OPENAI_BASE_URL', 'NOT SET')}")

# Test AI client
from ai_client import get_client
try:
    client = get_client()
    print("AI client created: YES")
    print(f"Base URL: {client.base_url}")
except Exception as e:
    print(f"AI client error: {type(e).__name__}: {str(e)[:200]}")
    sys.exit(1)

# Test image generation
from services.ebook_package import generate_visual_image
out_path = "exports/direct_test_coloring.png"
os.makedirs("exports", exist_ok=True)
ok = generate_visual_image(
    "Thunder Volt Man superhero with lightning powers, black and white line art",
    out_path
)
print(f"\nImage generation result: {'SUCCESS' if ok else 'FAILED'}")
print(f"Image saved: {'YES' if os.path.isfile(out_path) else 'NO'}")
if os.path.isfile(out_path):
    size = os.path.getsize(out_path)
    print(f"Image size: {size} bytes")

# Now generate the full coloring book
if ok:
    from services.coloring_book.builder import build_coloring_book
    print("\nGenerating coloring book...")
    result = build_coloring_book(
        theme="Thunder Volt Man",
        topic="Thunder Volt Man superhero with lightning powers",
        page_count=1,
        quality_mode="ai_image_coloring_page",
        art_style="Cartoon comic-book",
        age_group="12-adult",
    )
    print(f"Pages: {len(result.pages)}")
    print(f"Errors: {result.errors}")
    print(f"Warnings: {result.warnings}")
    print(f"Image failures: {result.image_failures}")
    for p in result.pages:
        print(f"  Page {p.page_number}: topic={p.topic}, image_path={p.image_path}, exists={os.path.isfile(p.image_path) if p.image_path else False}")
