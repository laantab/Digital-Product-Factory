"""Local summary of project 20090. Writes JSON; avoids printing secrets."""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
import database  # noqa: E402

out: dict = {"db_path": database.DB_PATH, "db_exists": Path(database.DB_PATH).exists()}

con = sqlite3.connect(database.DB_PATH)
con.row_factory = sqlite3.Row
out["recent_ids"] = [r[0] for r in con.execute("SELECT id FROM projects ORDER BY id DESC LIMIT 40")]
out["title_matches"] = [
    {"id": r["id"], "name": r["name"], "type": r["type"]}
    for r in con.execute(
        "SELECT id, name, type FROM projects WHERE name LIKE '%Container%' OR name LIKE '%Gardening%'"
    )
]
row = con.execute("SELECT id, name, type FROM projects WHERE id=20090").fetchone()
out["row_20090"] = dict(row) if row else None

proj = database.get_project(20090)
if not proj:
    out["project_20090"] = None
else:
    data = proj.get("data") or {}
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {}
    chapters = plan.get("chapters") if isinstance(plan.get("chapters"), list) else []
    aid_types: list[str] = []
    photo_count = 0
    box_count = 0
    missing = []
    for ch in chapters:
        for aid in (ch.get("aids") or []):
            at = str(aid.get("type") or "")
            aid_types.append(at)
            low = at.lower()
            if "photo" in low or "image" in low or "stock" in low:
                photo_count += 1
                path = aid.get("local_path") or aid.get("image_path") or aid.get("path") or ""
                if not path or (path and not Path(str(path)).is_file() and "data:" not in str(path)):
                    missing.append({"chapter": ch.get("chapter"), "title": aid.get("title"), "path": path, "status": aid.get("status")})
            else:
                box_count += 1
    src = cover.get("source") if isinstance(cover.get("source"), dict) else {}
    out["project_20090"] = {
        "id": proj.get("id"),
        "name": proj.get("name"),
        "type": proj.get("type"),
        "data_keys": sorted(data.keys()) if isinstance(data, dict) else [],
        "title": data.get("title") or fields.get("ebook_title"),
        "subtitle": data.get("subtitle") or fields.get("subtitle"),
        "author": data.get("author") or data.get("author_brand") or fields.get("author_brand"),
        "package_id": data.get("package_id"),
        "status": data.get("status"),
        "ebook_ready": data.get("ebook_ready"),
        "export_ready": data.get("export_ready"),
        "pdf_available": data.get("pdf_available"),
        "pdf_path": data.get("pdf_path") or data.get("_pdf_path"),
        "cover_selected_layout": cover.get("selected_layout"),
        "cover_image_path": cover.get("image_path"),
        "cover_source_type": src.get("source_type") or src.get("type"),
        "cover_has_source": bool(src),
        "cover_pexels_query": cover.get("pexels_query") or src.get("query") or data.get("pexels_query"),
        "visual_budget_cap_usd": fields.get("visual_budget_cap_usd") or data.get("visual_budget_cap_usd"),
        "visual_spend_usd": fields.get("visual_spend_usd") or data.get("visual_spend_usd"),
        "ai_visual_authorized": fields.get("ai_visual_authorized") or data.get("ai_visual_authorized"),
        "chapter_count": len(chapters),
        "aid_types": aid_types,
        "photo_count": photo_count,
        "non_photo_count": box_count,
        "missing_photos": missing,
        "exports": data.get("exports") if isinstance(data.get("exports"), dict) else {},
        "cover_error": data.get("cover_error"),
        "customer_error": data.get("customer_error"),
        "next_action": data.get("next_action"),
        "save_disabled_reason": data.get("save_disabled_reason"),
        "fields_topic": fields.get("topic"),
        "fields_keys": sorted(fields.keys()),
    }
    # write a compact visual plan summary
    plan_sum = []
    for ch in chapters:
        plan_sum.append({
            "chapter": ch.get("chapter"),
            "aids": [
                {
                    "type": a.get("type"),
                    "title": a.get("title"),
                    "keywords": a.get("keywords") or a.get("pexels_query"),
                    "status": a.get("status"),
                    "has_path": bool(a.get("local_path") or a.get("image_path") or a.get("path")),
                }
                for a in (ch.get("aids") or [])
            ],
        })
    out["visual_plan_summary"] = plan_sum

# protected identity checks (hashes written to file only)
protected = {}
for pid in (4249, 14626, 17365):
    p = database.get_project(pid)
    if not p:
        protected[str(pid)] = {"exists": False}
        continue
    d = p.get("data") or {}
    cover = d.get("cover_design") if isinstance(d.get("cover_design"), dict) else {}
    src = cover.get("source") if isinstance(cover.get("source"), dict) else {}
    rec = {
        "exists": True,
        "name": p.get("name"),
        "type": p.get("type"),
        "cover_sha_field": src.get("sha256"),
        "paths": {},
        "file_hashes": {},
    }
    for key in ("cover_path", "pdf_path", "manuscript_path", "accepted_pdf_path", "image_path"):
        val = d.get(key) or cover.get(key)
        if val:
            rec["paths"][key] = str(val)
            pth = Path(str(val))
            if pth.is_file():
                rec["file_hashes"][key] = hashlib.sha256(pth.read_bytes()).hexdigest()
    # manuscript blob hash if present
    ms = d.get("content") or d.get("ebook") or d.get("manuscript")
    if isinstance(ms, str) and ms:
        rec["manuscript_sha"] = hashlib.sha256(ms.encode("utf-8")).hexdigest()
    protected[str(pid)] = rec
out["protected"] = protected

# process cwd via open files is skipped
# env presence
out["env"] = {
    "PEXELS_SET": bool(os.environ.get("PEXELS_API_KEY")),
    "FACTORY_TEST_MODE": os.environ.get("FACTORY_TEST_MODE"),
    "dotenv_exists": (ROOT / ".env").exists(),
}

# also list exports dirs related to 20090
exports = ROOT / "exports"
out["export_dirs_sample"] = []
if exports.exists():
    names = sorted(os.listdir(exports), reverse=True)[:40]
    out["export_dirs_sample"] = names

(ROOT / "_diag_20090_summary.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print("wrote _diag_20090_summary.json")
print("20090 exists", bool(proj))
print("recent_ids_count", len(out["recent_ids"]))
print("title_matches", len(out["title_matches"]))
