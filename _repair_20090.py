"""Repair project 20090 in place. Live Pexels only. No manuscript regeneration."""
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
from services.ebook_customer_path import complete_factory_ebook  # noqa: E402
from services.ebook_factory_pipeline import remaining_visual_budget_usd  # noqa: E402
from services.ebook_pexels import pexels_configured  # noqa: E402

PROTECTED = 4249
TARGET = 20090


def _cover_sha(pid: int) -> str:
    row = database.get_project(pid) or {}
    cover = (row.get("data") or {}).get("cover_design") or {}
    return str(((cover.get("source") or {}).get("sha256")) or "")


def main() -> int:
    if not pexels_configured():
        print("BLOCKER: Pexels is not configured in this process")
        return 2
    before_4249 = _cover_sha(PROTECTED)
    proj = database.get_project(TARGET)
    if not proj:
        print("BLOCKER: project 20090 missing")
        return 2
    data = dict(proj.get("data") or {})
    fields = dict(data.get("fields") or {})
    title = str(data.get("title") or fields.get("ebook_title") or proj.get("name") or "")
    content = str(data.get("content") or data.get("ebook") or "")
    fields.setdefault("include_images", "Yes")
    fields.setdefault("visuals_authorized", data.get("visuals_authorized") or "true")
    fields.setdefault("visual_budget_cap_usd", data.get("visual_budget_cap_usd") or "0.48")
    fields.setdefault("author_brand", data.get("author") or data.get("author_brand") or "Lonnie Brown")
    fields.setdefault("subtitle", data.get("subtitle") or "")
    prior_spend = float(data.get("visual_ai_spend_usd") or 0)
    prior_remaining = remaining_visual_budget_usd(data, fields)
    print("start repair", TARGET, "chars", len(content), "remaining", prior_remaining, "spend", prior_spend)
    result = complete_factory_ebook(title, content, fields)
    result["_project_id"] = TARGET
    result["fields"] = fields
    result["visuals_authorized"] = fields.get("visuals_authorized")
    result["visual_budget_cap_usd"] = fields.get("visual_budget_cap_usd")
    result["hidden_from_customer"] = False
    result["internal_record"] = False
    result["temporary"] = False
    result["user_confirmed_save"] = bool(data.get("user_confirmed_save"))
    # Preserve ledger/spend; never raise the cap.
    if result.get("visual_ai_spend_usd") is None:
        result["visual_ai_spend_usd"] = prior_spend
    cover = result.get("cover_design") if isinstance(result.get("cover_design"), dict) else {}
    plan = result.get("visual_plan") if isinstance(result.get("visual_plan"), dict) else {}
    photos = []
    for ch in plan.get("chapters") or []:
        for aid in ch.get("aids") or []:
            kind = str(aid.get("type") or "").lower()
            if "photo" in kind:
                photos.append(
                    {
                        "chapter": ch.get("chapter"),
                        "title": aid.get("title"),
                        "query": aid.get("pexels_query"),
                        "source": aid.get("source"),
                        "photo_id": aid.get("photo_id"),
                        "status": aid.get("status"),
                        "has_file": bool(aid.get("has_file")),
                        "path": aid.get("factory_asset_path") or aid.get("asset_path"),
                    }
                )
    summary = {
        "ebook_ready": result.get("ebook_ready"),
        "pdf_available": result.get("pdf_available"),
        "zip_available": result.get("zip_available"),
        "next_action": result.get("next_action"),
        "cover_layout": cover.get("selected_layout"),
        "cover_query": result.get("cover_search_query") or cover.get("cover_search_query") or cover.get("pexels_query"),
        "cover_photo_id": ((cover.get("source") or {}).get("pexels") or {}).get("photo_id")
        or (cover.get("pexels") or {}).get("photo_id")
        or ((cover.get("source") or {}).get("photo_id")),
        "cover_path": cover.get("image_path"),
        "package_id": result.get("package_id"),
        "pdf_path": result.get("pdf_path") or result.get("_pdf_path"),
        "contamination": result.get("contamination"),
        "visual_ai_spend_usd": result.get("visual_ai_spend_usd"),
        "remaining_budget": remaining_visual_budget_usd(result, fields),
        "photo_count": len(photos),
        "photos": photos,
        "chapter_titles": [ch.get("chapter") for ch in (plan.get("chapters") or [])],
        "cover_error": result.get("cover_error"),
        "customer_error": result.get("customer_error"),
        "4249_before": before_4249,
        "4249_after": _cover_sha(PROTECTED),
    }
    (ROOT / "_repair_20090_summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    saved = database.update_project(
        TARGET,
        title,
        result,
        user_saved=bool(proj.get("user_saved")),
        user_confirmed_save=bool(data.get("user_confirmed_save")),
    )
    print("updated", saved.get("id") if saved else None)
    print("ready", result.get("ebook_ready"), "pdf", result.get("pdf_available"), "photos", len(photos))
    print("next", result.get("next_action"), "cover", bool(cover.get("selected_layout")))
    print("4249 unchanged", before_4249 == _cover_sha(PROTECTED))
    return 0 if result.get("ebook_ready") else 1


if __name__ == "__main__":
    raise SystemExit(main())
