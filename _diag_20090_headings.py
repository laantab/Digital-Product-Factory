"""Extract 20090 headings and runtime facts. No secrets printed."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
import database  # noqa: E402
from services.ebook_contamination import is_description_heading, sanitize_manuscript  # noqa: E402
from services.ebook_package import _split_chapters  # noqa: E402
from services.ebook_pexels import pexels_configured, pexels_status_label  # noqa: E402
from services.ebook_factory_pipeline import remaining_visual_budget_usd  # noqa: E402

proj = database.get_project(20090)
data = proj["data"] if proj else {}
content = str(data.get("content") or data.get("ebook") or "")
fields = data.get("fields") or {}
headings = re.findall(r"(?m)^#{1,3}\s+(.+)$", content)
preamble, chapters = _split_chapters(content)
out = {
    "heading_count": len(headings),
    "headings": headings[:20],
    "split_chapter_titles": [t for t, _ in chapters],
    "preamble_len": len(preamble),
    "content_len": len(content),
    "has_localhost": "127.0.0.1" in content or "localhost" in content,
    "preview_has_localhost": "127.0.0.1" in str(data.get("preview_html") or ""),
    "visuals_authorized": fields.get("visuals_authorized"),
    "include_images": fields.get("include_images"),
    "visual_budget_cap_usd": fields.get("visual_budget_cap_usd"),
    "visual_ai_spend_usd": data.get("visual_ai_spend_usd"),
    "remaining_budget": remaining_visual_budget_usd(data, fields),
    "package_id": data.get("package_id"),
    "cover_search_query": data.get("cover_search_query"),
    "pexels_status_field": data.get("pexels_status"),
    "missing_photo_count": data.get("missing_photo_count"),
    "required_visual_count": data.get("required_visual_count"),
    "rendered_visual_count": data.get("rendered_visual_count"),
    "user_saved": data.get("user_saved"),
    "pexels_configured_after_dotenv": pexels_configured(),
    "pexels_status_label": pexels_status_label(),
    "desc_flags": [
        {"title": t, "is_desc": is_description_heading(t, book_title=data.get("title") or "", subtitle=data.get("subtitle") or "")}
        for t in [x for x, _ in chapters]
    ],
}
(ROOT / "_diag_20090_headings.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print("wrote headings json", len(headings), "chapters", len(chapters), "pexels", pexels_configured())
