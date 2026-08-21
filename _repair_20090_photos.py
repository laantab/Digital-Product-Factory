"""Replace irrelevant interior photos on project 20090. Keep cover and manuscript."""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ.pop("FACTORY_TEST_MODE", None)
os.environ.pop("EBOOK_CUSTOMER_PATH_FIXTURE", None)
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

import database  # noqa: E402
from services.ebook_customer_path import _write_sellable_pdf  # noqa: E402
from services.ebook_factory_pipeline import apply_ebook_readiness, fill_photo_aid_from_pexels  # noqa: E402
from services.ebook_package import render_preview_html  # noqa: E402
from services.ebook_visual_pipeline import is_photo_aid  # noqa: E402

TARGET = 20090
BAD_IDS = {"2720445", "10574048"}  # kitchen food prep; skincare after-sun


def main() -> int:
    proj = database.get_project(TARGET)
    data = dict(proj.get("data") or {})
    fields = dict(data.get("fields") or {})
    plan = dict(data.get("visual_plan") or {})
    package_id = str(data.get("package_id") or "")
    title = str(data.get("title") or "")
    topic = str(fields.get("topic") or title)
    replaced = []
    for ch in plan.get("chapters") or []:
        aids = list(ch.get("aids") or [])
        chapter = str(ch.get("chapter") or "")
        for i, aid in enumerate(aids):
            if not is_photo_aid(aid):
                continue
            pid = str(aid.get("photo_id") or "")
            if pid not in BAD_IDS:
                continue
            fresh = {
                "type": "stock photo",
                "visual_id": aid.get("visual_id"),
                "title": aid.get("title") or f"{chapter} photograph",
                "caption": chapter,
                "chapter": chapter,
                "keywords": [],
                "rejected_photo_ids": sorted(BAD_IDS | {pid}),
            }
            filled = fill_photo_aid_from_pexels(
                fresh,
                package_id=package_id,
                title=title,
                topic=topic,
                audience=str(fields.get("audience") or ""),
                chapter=chapter,
            )
            aids[i] = filled
            replaced.append(
                {
                    "chapter": chapter,
                    "old": pid,
                    "new": filled.get("photo_id"),
                    "query": filled.get("pexels_query"),
                    "status": filled.get("status"),
                    "has_file": filled.get("has_file"),
                    "alt": filled.get("alt"),
                }
            )
        ch["aids"] = aids
    data["visual_plan"] = plan
    data["preview_html"] = render_preview_html(
        title,
        str(data.get("subtitle") or ""),
        str(data.get("content") or ""),
        list(plan.get("chapters") or []),
        package_id,
        str(data.get("product_summary") or ""),
        data.get("cover_design"),
        topic=topic,
    )
    data = _write_sellable_pdf(
        data,
        title=title,
        subtitle=str(data.get("subtitle") or ""),
        author=str(data.get("author") or data.get("author_brand") or ""),
        content=str(data.get("content") or ""),
    )
    apply_ebook_readiness(data)
    database.update_project(TARGET, title, data, user_saved=bool(proj.get("user_saved")))
    (ROOT / "_repair_20090_photo_swap.json").write_text(json.dumps(replaced, indent=2, default=str), encoding="utf-8")
    print("replaced", len(replaced), "ready", data.get("ebook_ready"), "pdf", data.get("pdf_available"))
    for row in replaced:
        print(row)
    return 0 if data.get("ebook_ready") and len(replaced) == len(BAD_IDS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
