import requests

# Quick logic-only test for Digital Book
resp = requests.post(
    "http://127.0.0.1:5000/generate-product",
    json={
        "product_type": "coloring_book",
        "fields": {
            "coloring_title": "Ocean Adventures",
            "theme": "Ocean Adventures",
            "output_format": "Digital Book",
            "pages": "5",
            "quality_mode": "basic_test",
            "age_group": "12-adult",
            "art_style": "Cartoon comic-book",
            "include_captions": "No",
            "page_size": "US Letter"
        }
    },
    timeout=60
)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    layout = data.get("layout_info", {})
    print(f"layout: {layout}")
    print(f"errors: {data.get('errors', [])}")
else:
    print(f"Error: {resp.text[:300]}")
