"""Replace ONLY visuals 7 and 9 on Factory project 4249. No preview rebuild."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import database
from services.ebook_pexels import download_pexels_original, fetch_pexels_photo
from services.ebook_visual_pipeline import (
    manifest_from_plan,
    store_interior_photo,
    write_visual_contact_sheet,
)

PROJECT_ID = 4249
PKG = "ebook-ws-0f45e1eab3a0"
SNAP = Path("_visual_swap_4249_snapshot/keepers.json")
KEEP = {1, 2, 3, 4, 5, 6, 8, 10}

CH7 = {
    "photo_id": "7014397",
    "title": "Compact event photo printer with prints in the tray",
    "caption": (
        "A compact photo printer with bordered photographs emerging from the tray "
        "— the capture-to-print-to-guest-delivery station this chapter describes."
    ),
}
CH9 = {
    "photo_id": "3493047",
    "title": "Ceramic mug with a photograph applied",
    "caption": (
        "A ceramic mug with a photographic wrap visibly applied "
        "— a keepsake that needs separate equipment and workflow from dye-sub prints."
    ),
}


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    row = database.get_project(PROJECT_ID)
    data = row["data"]
    ledger = (data.get("ebook_workspace") or {}).get("paid_call_ledger") or {}
    print("BEFORE_LEDGER", ledger.get("paid_calls"), ledger.get("spent_usd"), ledger.get("remaining_usd"))
    preview_html = data.get("ebook_preview_html")
    preview_sha = hashlib.sha256(str(preview_html or "").encode("utf-8")).hexdigest()
    cover_sha = ((data.get("cover_design") or {}).get("source") or {}).get("sha256")
    cover_digest = data.get("ebook_cover_digest")
    ms = data.get("content") or data.get("ebook")
    ms_sha = hashlib.sha256(str(ms or "").encode("utf-8")).hexdigest()

    keepers = json.loads(SNAP.read_text(encoding="utf-8"))
    before_keep = {}
    for k in keepers:
        p = Path(k["src"])
        raw = p.read_bytes()
        assert hashlib.sha256(raw).hexdigest() == k["sha"], f"keeper drifted before write: {k['vid']}"
        assert len(raw) == k["bytes"]
        before_keep[k["vid"]] = (k["sha"], k["bytes"], raw)

    http = {"fetch": 0, "download": 0}
    replacements = {"7": CH7, "9": CH9}
    photos = {}
    for key, spec in replacements.items():
        photo = fetch_pexels_photo(spec["photo_id"])
        http["fetch"] += 1
        original = download_pexels_original(photo)
        http["download"] += 1
        photos[key] = (photo, original)
        print("FETCHED", key, spec["photo_id"], photo.get("photographer"), photo.get("width"), "x", photo.get("height"), len(original))

    plan = data["visual_plan"]
    for ch in plan.get("chapters") or []:
        for aid in ch.get("aids") or []:
            idx = str(aid.get("chapter_index"))
            if idx not in replacements:
                continue
            spec = replacements[idx]
            photo, original = photos[idx]
            updated = store_interior_photo(aid, original, package_id=PKG)
            updated["source"] = "pexels"
            updated["photo_id"] = str(photo.get("photo_id"))
            updated["photographer"] = photo.get("photographer") or ""
            updated["attribution"] = photo.get("attribution") or f"Photo by {photo.get('photographer')} on Pexels"
            updated["page_url"] = photo.get("page_url") or ""
            updated["source_url"] = photo.get("page_url") or ""
            updated["title"] = spec["title"]
            updated["caption"] = spec["caption"]
            updated["chapter"] = aid.get("chapter")
            updated["chapter_index"] = aid.get("chapter_index")
            updated["placement"] = aid.get("placement") or "after_opening"
            updated["required"] = True
            updated["status"] = "resolved"
            aid.clear()
            aid.update(updated)
            print(
                "STORED",
                idx,
                aid["visual_id"],
                aid["width"],
                "x",
                aid["height"],
                aid["sha256"],
                Path(aid["asset_path"]).stat().st_size,
            )

    manifest = manifest_from_plan(plan)
    contact = write_visual_contact_sheet(plan, package_id=PKG)
    data["visual_plan"] = plan
    data["ebook_visual_manifest"] = manifest
    data["ebook_visual_manifest_digest"] = manifest["digest"]
    data["ebook_visual_contact_sheet"] = contact
    # Freeze identities that must not change.
    data["ebook_preview_html"] = preview_html
    database.update_project(PROJECT_ID, None, data)

    stored = database.get_project(PROJECT_ID)["data"]
    ledger2 = (stored.get("ebook_workspace") or {}).get("paid_call_ledger") or {}
    print("AFTER_LEDGER", ledger2.get("paid_calls"), ledger2.get("spent_usd"), ledger2.get("remaining_usd"))
    print("HTTP", http)
    print("CONTACT", contact)
    print("MANIFEST", stored.get("ebook_visual_manifest_digest"))

    print("--- KEEPER VERIFY ---")
    ok = True
    for ch in stored["visual_plan"]["chapters"]:
        for aid in ch.get("aids") or []:
            idx = int(aid.get("chapter_index") or 0)
            vid = aid.get("visual_id")
            path = Path(aid["asset_path"])
            raw = path.read_bytes()
            disk = hashlib.sha256(raw).hexdigest()
            if idx in KEEP:
                exp_sha, exp_len, exp_raw = before_keep[vid]
                match = raw == exp_raw and disk == exp_sha and len(raw) == exp_len
                print(f"KEEP {idx} {vid} {disk} bytes={len(raw)} match={match}")
                if not match:
                    ok = False
            else:
                print(f"NEW  {idx} {vid} {disk} {aid['width']}x{aid['height']} {aid.get('photographer')} {aid.get('page_url')}")
            if disk != aid.get("sha256"):
                print("SHA_MISMATCH", vid)
                ok = False

    html2 = stored.get("ebook_preview_html")
    print("PREVIEW_HTML_UNCHANGED", hashlib.sha256(str(html2 or "").encode("utf-8")).hexdigest() == preview_sha)
    print("COVER_SHA_UNCHANGED", ((stored.get("cover_design") or {}).get("source") or {}).get("sha256") == cover_sha)
    print("COVER_DIGEST_UNCHANGED", stored.get("ebook_cover_digest") == cover_digest)
    print("MS_UNCHANGED", hashlib.sha256(str(stored.get("content") or stored.get("ebook") or "").encode("utf-8")).hexdigest() == ms_sha)
    rail = (stored.get("ebook_workspace") or {}).get("rail") or {}
    print("RAIL visuals", (rail.get("visuals") or {}).get("status"), "preview", (rail.get("preview") or {}).get("status"), "export", (rail.get("export") or {}).get("status"))
    print("OK" if ok else "KEEPER_FAIL")


if __name__ == "__main__":
    main()
