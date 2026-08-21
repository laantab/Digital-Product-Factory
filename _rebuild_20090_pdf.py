"""Rebuild 20090 preview/PDF from stored photos after layout caption fixes."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ.pop("FACTORY_TEST_MODE", None)
from dotenv import load_dotenv

load_dotenv(ROOT / ".env")
import database  # noqa: E402
from services.ebook_customer_path import _write_sellable_pdf  # noqa: E402
from services.ebook_factory_pipeline import apply_ebook_readiness  # noqa: E402
from services.ebook_package import render_preview_html  # noqa: E402

TARGET = 20090
CAPTIONS = {
    "Getting Started With Container Gardening": "Sowing a seed in a small starter pot",
    "Choosing the Right Containers and Soil": "Pots filled with fresh potting mix",
    "Picking Vegetables and Herbs That Grow Well in Pots": "Vegetable seedlings ready for containers",
    "Water, Sun, and Daily Care": "Watering garden plants on a sunny day",
    "Handling Pests and Plant Problems": "Aphids clustered on plant stems",
    "Harvesting, Replanting, and Keeping Your Garden Going": "Repotting plants with soil and tools",
}


def main() -> int:
    proj = database.get_project(TARGET)
    data = dict(proj.get("data") or {})
    plan = dict(data.get("visual_plan") or {})
    for ch in plan.get("chapters") or []:
        name = str(ch.get("chapter") or "")
        for aid in ch.get("aids") or []:
            if "photo" in str(aid.get("type") or "").lower():
                cap = CAPTIONS.get(name)
                if cap:
                    aid["title"] = cap
                    aid["caption"] = cap
    data["visual_plan"] = plan
    title = str(data.get("title") or "")
    data["preview_html"] = render_preview_html(
        title,
        str(data.get("subtitle") or ""),
        str(data.get("content") or ""),
        list(plan.get("chapters") or []),
        str(data.get("package_id") or ""),
        str(data.get("product_summary") or ""),
        data.get("cover_design"),
        topic=str((data.get("fields") or {}).get("topic") or ""),
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
    print("ready", data.get("ebook_ready"), "pdf", data.get("pdf_path"))
    return 0 if data.get("ebook_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
