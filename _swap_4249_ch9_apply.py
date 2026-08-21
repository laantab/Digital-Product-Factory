"""Replace ONLY Visual chapter 9 on Factory project 4249. No preview rebuild."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from PIL import Image

import database
from services.ebook_pexels import download_pexels_original, fetch_pexels_photo
from services.ebook_project_workspace import manuscript_digest
from services.ebook_visual_pipeline import (
    manifest_from_plan,
    visuals_dir,
    write_visual_contact_sheet,
)

PROJECT_ID = 4249
PKG = "ebook-ws-0f45e1eab3a0"
SNAP = Path("_visual_swap_4249_snapshot/keepers_ch9swap.json")
KEEP = {1, 2, 3, 4, 5, 6, 7, 8, 10}
PHOTO_ID = "5656143"
TITLE = "Ceramic mug with a photograph applied"
CAPTION = (
    "A ceramic mug with a photographic image visibly printed on the surface "
    "— a keepsake that needs separate equipment and workflow from dye-sub prints."
)


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    row = database.get_project(PROJECT_ID)
    data = row["data"]
    ws = data.get("ebook_workspace") or {}
    ledger = ws.get("paid_call_ledger") or {}
    print("BEFORE_LEDGER", ledger.get("paid_calls"), ledger.get("spent_usd"), ledger.get("remaining_usd"))
    preview_html = data.get("ebook_preview_html")
    preview_sha = sha_bytes(str(preview_html or "").encode("utf-8"))
    cover_digest = data.get("ebook_cover_digest")
    cover_sha = ((data.get("cover_design") or {}).get("source") or {}).get("sha256")
    ms_digest = manuscript_digest(data)
    ident = data.get("ebook_export_identity") if isinstance(data.get("ebook_export_identity"), dict) else {}
    preview_digest = ident.get("preview_digest")
    print("COVER_DIGEST", cover_digest)
    print("MS_DIGEST", ms_digest)
    print("PREVIEW_DIGEST", preview_digest)
    print("PREVIEW_HTML_SHA", preview_sha)

    keepers = json.loads(SNAP.read_text(encoding="utf-8"))
    before_keep = {}
    for k in keepers:
        p = Path(k["src"])
        raw = p.read_bytes()
        assert sha_bytes(raw) == k["sha"], f"keeper drifted before write: {k['vid']}"
        assert len(raw) == k["bytes"]
        before_keep[k["vid"]] = (k["sha"], k["bytes"], raw)
        print("SNAP", k["vid"], k["sha"][:16], k["bytes"])

    photo = fetch_pexels_photo(PHOTO_ID)
    original = download_pexels_original(photo)
    orig_img = Image.open(io.BytesIO(original))
    orig_w, orig_h = orig_img.size
    print(
        "FETCHED",
        PHOTO_ID,
        photo.get("photographer"),
        photo.get("width"),
        "x",
        photo.get("height"),
        "download_pixels",
        orig_w,
        "x",
        orig_h,
        "bytes",
        len(original),
        photo.get("original_url"),
        photo.get("page_url"),
    )
    assert "original" in str(photo.get("original_url") or "") or not (
        "h=650" in str(photo.get("original_url") or "") or "w=940" in str(photo.get("original_url") or "")
    )
    if orig_img.mode not in {"RGB", "L"}:
        orig_img = orig_img.convert("RGB")
    elif orig_img.mode == "L":
        orig_img = orig_img.convert("RGB")
    dest = visuals_dir(PKG)
    dest.mkdir(parents=True, exist_ok=True)
    out_path = dest / "v_ch9.png"
    buf = io.BytesIO()
    orig_img.save(buf, format="PNG", optimize=True)
    png = buf.getvalue()
    out_path.write_bytes(png)
    stored_w, stored_h = orig_img.size
    stored_sha = sha_bytes(png)
    print("STORED", out_path, stored_w, "x", stored_h, stored_sha, len(png))

    plan = data["visual_plan"]
    for ch in plan.get("chapters") or []:
        for aid in ch.get("aids") or []:
            if int(aid.get("chapter_index") or 0) != 9:
                continue
            aid["type"] = "photo"
            aid["asset_path"] = str(out_path)
            aid["sha256"] = stored_sha
            aid["width"] = int(stored_w)
            aid["height"] = int(stored_h)
            aid["source"] = "pexels"
            aid["photo_id"] = str(photo.get("photo_id"))
            aid["photographer"] = photo.get("photographer") or ""
            aid["attribution"] = photo.get("attribution") or f"Photo by {photo.get('photographer')} on Pexels"
            aid["page_url"] = photo.get("page_url") or ""
            aid["source_url"] = photo.get("page_url") or ""
            aid["original_url"] = photo.get("original_url") or ""
            aid["original_width"] = int(orig_w)
            aid["original_height"] = int(orig_h)
            aid["title"] = TITLE
            aid["caption"] = CAPTION
            aid["placement"] = aid.get("placement") or "after_opening"
            aid["required"] = True
            aid["status"] = "resolved"
            print("AID", aid["visual_id"], aid["width"], "x", aid["height"], aid["photographer"])

    manifest = manifest_from_plan(plan)
    contact = write_visual_contact_sheet(plan, package_id=PKG)
    data["visual_plan"] = plan
    data["ebook_visual_manifest"] = manifest
    data["ebook_visual_manifest_digest"] = manifest["digest"]
    data["ebook_visual_contact_sheet"] = contact
    data["ebook_preview_html"] = preview_html
    database.update_project(PROJECT_ID, None, data)

    stored = database.get_project(PROJECT_ID)["data"]
    ledger2 = (stored.get("ebook_workspace") or {}).get("paid_call_ledger") or {}
    print("AFTER_LEDGER", ledger2.get("paid_calls"), ledger2.get("spent_usd"), ledger2.get("remaining_usd"))
    print("CONTACT", contact)
    print("MANIFEST", stored.get("ebook_visual_manifest_digest"))
    print("HTTP fetch=1 download=1")

    ok = True
    print("--- KEEPER VERIFY ---")
    for ch in stored["visual_plan"]["chapters"]:
        for aid in ch.get("aids") or []:
            idx = int(aid.get("chapter_index") or 0)
            vid = aid.get("visual_id")
            path = Path(aid["asset_path"])
            raw = path.read_bytes()
            disk = sha_bytes(raw)
            if idx in KEEP:
                exp_sha, exp_len, exp_raw = before_keep[vid]
                match = raw == exp_raw and disk == exp_sha and len(raw) == exp_len
                print(f"KEEP {idx} {vid} {disk} bytes={len(raw)} match={match}")
                if not match:
                    ok = False
            else:
                print(
                    f"NEW  {idx} {vid} {disk} {aid['width']}x{aid['height']} "
                    f"{aid.get('photographer')} {aid.get('page_url')}"
                )
            if disk != aid.get("sha256"):
                print("SHA_MISMATCH", vid)
                ok = False

    html2 = stored.get("ebook_preview_html")
    ident2 = stored.get("ebook_export_identity") if isinstance(stored.get("ebook_export_identity"), dict) else {}
    print("PREVIEW_HTML_UNCHANGED", sha_bytes(str(html2 or "").encode("utf-8")) == preview_sha)
    print("COVER_SHA_UNCHANGED", ((stored.get("cover_design") or {}).get("source") or {}).get("sha256") == cover_sha)
    print("COVER_DIGEST_UNCHANGED", stored.get("ebook_cover_digest") == cover_digest)
    print("MS_DIGEST_UNCHANGED", manuscript_digest(stored) == ms_digest)
    print("PREVIEW_DIGEST_UNCHANGED", ident2.get("preview_digest") == preview_digest)
    rail = (stored.get("ebook_workspace") or {}).get("rail") or {}
    print(
        "RAIL visuals",
        (rail.get("visuals") or {}).get("status"),
        "preview",
        (rail.get("preview") or {}).get("status"),
        "export",
        (rail.get("export") or {}).get("status"),
    )
    print("OK" if ok else "KEEPER_FAIL")


if __name__ == "__main__":
    main()
