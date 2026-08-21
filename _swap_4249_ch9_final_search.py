"""Focused Ch9 search + fetch Ch7 original. No project writes."""
from __future__ import annotations

import json
from pathlib import Path

import database
from services.ebook_pexels import _http_get, download_pexels_original, fetch_pexels_photo, search_pexels

DEST = Path("_visual_swap_4249_candidates")
DEST.mkdir(exist_ok=True)
QUERIES = [
    "white mug printed portrait photo",
    "coffee mug with photo of people",
    "mug with baby photograph",
    "personalized mug couple photograph",
    "photo collage printed on mug",
    "ceramic mug family picture print",
    "picture of child on coffee mug",
    "wedding photo printed mug",
    "face photo ceramic mug",
    "custom photo mug product",
]


def main() -> None:
    before = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("BEFORE", before.get("paid_calls"), before.get("spent_usd"))
    seen = {p.stem.split("_", 1)[-1] for p in DEST.glob("ch9_*.jpg")}
    rows = []
    http = {"search": 0, "preview": 0}
    for q in QUERIES:
        for ori in ("landscape", "square"):
            payload = search_pexels(q, page=1, per_page=12, orientation=ori)
            http["search"] += 1
            photos = payload.get("photos") or []
            print(f"Q[{ori}] {q!r} -> {len(photos)}")
            for ph in photos:
                pid = str(ph.get("photo_id"))
                if pid in seen:
                    continue
                seen.add(pid)
                row = {
                    "photo_id": pid,
                    "query": q,
                    "photographer": ph.get("photographer"),
                    "page_url": ph.get("page_url"),
                    "preview_url": ph.get("preview_url"),
                    "original_url": ph.get("original_url"),
                    "width": ph.get("width"),
                    "height": ph.get("height"),
                    "attribution": ph.get("attribution"),
                }
                rows.append(row)
                try:
                    preview = _http_get(ph["preview_url"], {}, binary=True)
                    http["preview"] += 1
                    (DEST / f"ch9_{pid}.jpg").write_bytes(preview)
                except Exception as exc:  # noqa: BLE001
                    row["preview_error"] = str(exc)
    (DEST / "index_ch9_final.json").write_text(json.dumps({"http": http, "rows": rows}, indent=2), encoding="utf-8")
    after = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("AFTER", after.get("paid_calls"), after.get("spent_usd"))
    print("HTTP", http, "new", len(rows))
    for row in rows:
        slug = (row.get("page_url") or "").rstrip("/").split("/")[-1]
        print(row["photo_id"], row["width"], "x", row["height"], slug)

    # Prefetch Ch7 original (already inspected).
    photo7 = fetch_pexels_photo("7014397")
    raw7 = download_pexels_original(photo7)
    (DEST / "orig_7014397.jpg").write_bytes(raw7)
    print("CH7_ORIG", photo7.get("photographer"), photo7.get("width"), photo7.get("height"), len(raw7), photo7.get("page_url"))
    after2 = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("AFTER2", after2.get("paid_calls"), after2.get("spent_usd"))


if __name__ == "__main__":
    main()
