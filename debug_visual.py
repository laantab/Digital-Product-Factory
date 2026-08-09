"""Debug: inspect the ebook HTML to understand the Data Security visual structure."""
import os, sys, json, re

flask_dir = r"C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app"
sys.path.insert(0, flask_dir)
os.chdir(flask_dir)

import sqlite3
from bs4 import BeautifulSoup
from services.ebook_package import render_preview_html

DB_PATH = os.path.join(flask_dir, "projects.db")
PROJECT_ID = 62

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.execute(
    "SELECT id, name, type, data FROM projects WHERE id = ?", (PROJECT_ID,)
)
row = cursor.fetchone()
conn.close()

project = {
    "id": row["id"],
    "name": row["name"],
    "type": row["type"],
    "data": json.loads(row["data"] or "{}"),
}

data = project["data"]
title = data.get("title") or project["name"]
subtitle = data.get("subtitle", "")
content_md = data.get("content") or data.get("ebook") or ""
visual_plan = data.get("visual_plan")
plan_chapters = (visual_plan or {}).get("chapters", []) if isinstance(visual_plan, dict) else []
pkg_id = data.get("package_id") or ""
summary = data.get("product_summary") or ""
cover_design = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None
topic = (data.get("fields") or {}).get("topic", "")

print(f"Title: {title}")
print(f"Plan chapters: {len(plan_chapters)}")
print(f"Topic: {topic}")

# Find the Data Security chapter
for i, ch in enumerate(plan_chapters):
    title_ch = ch.get("chapter", "")
    if "data security" in title_ch.lower():
        print(f"\n=== Data Security chapter (index {i}) ===")
        aids = ch.get("aids", [])
        print(f"Aids count: {len(aids)}")
        for j, aid in enumerate(aids):
            print(f"\nAid {j}:")
            print(f"  Type: {aid.get('type')}")
            print(f"  Title: {aid.get('title')}")
            table = aid.get("table")
            if table:
                print(f"  Table headers: {table.get('headers')}")
                print(f"  Table rows: {table.get('rows')}")

# Render preview HTML and find the Data Security section
preview_html = render_preview_html(
    title, subtitle, content_md, plan_chapters, pkg_id, summary, cover_design, topic=topic
)

soup = BeautifulSoup(preview_html, "html.parser")

# Find the Data Security visual
for va in soup.find_all(class_="visual-aid"):
    va_title_el = va.find(class_="va-title")
    va_title = va_title_el.get_text(strip=True) if va_title_el else ""
    if "data security" in va_title.lower():
        print(f"\n=== Data Security visual in HTML ===")
        print(f"Visual title: {va_title}")
        content = va.find(class_="va-content")
        if content:
            inner = content.decode_contents()
            print(f"Content HTML: {inner[:500]}")
            # Check for cards
            cards = content.find(class_="va-table-cards")
            if cards:
                print("HAS va-table-cards class!")
                rows = cards.find_all(class_="tcard-row")
                print(f"Card rows: {len(rows)}")
                for k, row_el in enumerate(rows):
                    cells = row_el.find_all(class_="tcard-cell")
                    print(f"  Row {k}: {[c.get_text(' ', strip=True)[:60] for c in cells]}")
