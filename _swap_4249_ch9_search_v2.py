"""Continue Ch9 Pexels search. ASCII-safe. No project writes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import database
from services.ebook_pexels import _http_get, fetch_pexels_photo, search_pexels

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEST = Path("_visual_swap_4249_candidates")
DEST.mkdir(exist_ok=True)

QUERIES = [
    "photo printed mug",
    "personalized photo mug",
    "family photo ceramic mug",
    "sublimation mug photograph",
    "custom photo mug",
    "mug with photograph of people",
    "picture printed on mug",
    "photo wrap ceramic mug",
    "personalized picture mug",
    "family portrait coffee mug",
    "heat press mug photo",
    "mug press photograph",
    "custom printed photo cup",
    "ceramic mug family picture",
    "photo gift mug",
    "sublimation photo mug",
    "printed photograph mug product",
    "couple photo mug",
    "baby photo mug",
    "wedding photo mug",
    "picture on coffee mug",
    "photo collage mug",
    "full wrap photo mug",
    "dye sublimation mug photo",
]

# Known IDs from prior passes plus any extra we want metadata for.
EXTRA_IDS = [
    "20633747",
    "14522881",
    "2480399",
    "1724181",
    "6312157",
    "9806720",
    "34534478",
    "30198273",
    "3890592",
    "1382907",
]


def slug(url: str) -> str:
    return (url or "").rstrip("/").split("/")[-1]


def main() -> None:
    before = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("BEFORE", before.get("paid_calls"), before.get("spent_usd"), before.get("remaining_usd"))
    seen = {p.stem.split("_", 1)[-1] for p in DEST.glob("ch9_*.jpg")}
    rows = []
    http = {"search": 0, "preview": 0, "fetch": 0}
    for q in QUERIES:
        for ori in ("landscape",):
            for page in (1, 2):
                payload = search_pexels(q, page=page, per_page=15, orientation=ori)
                http["search"] += 1
                photos = payload.get("photos") or []
                print(f"Q[{ori} p{page}] {q!r} -> {len(photos)}")
                for ph in photos:
                    pid = str(ph.get("photo_id"))
                    w, h = ph.get("width"), ph.get("height")
                    print(f"  {pid} {w}x{h} {slug(ph.get('page_url') or '')}")
                    row = {
                        "photo_id": pid,
                        "query": q,
                        "orientation": ori,
                        "page": page,
                        "photographer": ph.get("photographer"),
                        "page_url": ph.get("page_url"),
                        "preview_url": ph.get("preview_url"),
                        "original_url": ph.get("original_url"),
                        "width": w,
                        "height": h,
                        "already": pid in seen,
                    }
                    rows.append(row)
                    if pid in seen:
                        continue
                    seen.add(pid)
                    try:
                        preview_bytes = _http_get(ph["preview_url"], {}, binary=True)
                        http["preview"] += 1
                        (DEST / f"ch9_{pid}.jpg").write_bytes(preview_bytes)
                    except Exception as exc:  # noqa: BLE001
                        row["preview_error"] = str(exc)

    for pid in EXTRA_IDS:
        try:
            ph = fetch_pexels_photo(pid)
            http["fetch"] += 1
            print(f"ID {pid} {ph.get('width')}x{ph.get('height')} {slug(ph.get('page_url') or '')}")
            if pid not in seen:
                preview_bytes = _http_get(ph["preview_url"], {}, binary=True)
                http["preview"] += 1
                (DEST / f"ch9_{pid}.jpg").write_bytes(preview_bytes)
                seen.add(pid)
        except Exception as exc:  # noqa: BLE001
            print("IDERR", pid, exc)

    (DEST / "index_ch9_v2.json").write_text(
        json.dumps({"http": http, "rows": rows}, indent=2), encoding="utf-8"
    )
    after = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("AFTER", after.get("paid_calls"), after.get("spent_usd"), after.get("remaining_usd"))
    print("HTTP", http, "rows", len(rows), "unique_files", len(list(DEST.glob('ch9_*.jpg'))))


if __name__ == "__main__":
    main()
