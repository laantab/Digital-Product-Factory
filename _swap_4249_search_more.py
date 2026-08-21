"""Second-pass free Pexels search. Does not write project data."""
from __future__ import annotations

import json
from pathlib import Path

import database
from services.ebook_pexels import _http_get, search_pexels

DEST = Path("_visual_swap_4249_candidates")
DEST.mkdir(exist_ok=True)
INDEX = DEST / "index_pass2.json"

QUERIES_7 = [
    "canon selphy printer",
    "selphy photo printer",
    "instax printer",
    "smartphone photo printer",
    "hp sprocket printer",
    "dye sublimation printer",
    "event photo booth printer",
    "photo booth wedding print",
    "4x6 photo print printer",
    "printing photographs event",
    "portable photo printer printing",
    "photo coming out of printer",
    "compact photo printer tray",
    "wedding photo print station",
]
QUERIES_9 = [
    "custom mug photo print",
    "sublimation mug photo",
    "personalized mug couple photo",
    "wedding photo mug",
    "mug with face photo",
    "printed cup photograph",
    "photo gift mug",
    "family portrait mug",
    "picture printed on coffee mug",
    "custom printed photo cup",
    "personalized ceramic mug photograph",
    "couple photo on mug",
]


def main() -> None:
    before = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("BEFORE", before.get("paid_calls"), before.get("spent_usd"))
    seen: set[str] = set()
    for p in DEST.glob("ch7_*.jpg"):
        seen.add(p.stem.split("_", 1)[1])
    for p in DEST.glob("ch9_*.jpg"):
        seen.add(p.stem.split("_", 1)[1])
    results: dict[str, list] = {"ch7": [], "ch9": []}
    http = {"search": 0, "preview": 0}

    def collect(label: str, queries: list[str]) -> None:
        for q in queries:
            for page in (1, 2):
                payload = search_pexels(q, page=page, per_page=15, orientation="landscape")
                http["search"] += 1
                photos = payload.get("photos") or []
                print(f"Q[{label} p{page}] {q!r} -> {len(photos)}")
                if not photos:
                    break
                for ph in photos:
                    pid = str(ph.get("photo_id"))
                    if pid in seen:
                        continue
                    seen.add(pid)
                    row = {
                        "chapter": label,
                        "query": q,
                        "page": page,
                        "photo_id": pid,
                        "photographer": ph.get("photographer"),
                        "page_url": ph.get("page_url"),
                        "preview_url": ph.get("preview_url"),
                        "original_url": ph.get("original_url"),
                        "width": ph.get("width"),
                        "height": ph.get("height"),
                        "attribution": ph.get("attribution"),
                    }
                    results[label].append(row)
                    try:
                        preview = _http_get(ph["preview_url"], {}, binary=True)
                        http["preview"] += 1
                        (DEST / f"{label}_{pid}.jpg").write_bytes(preview)
                        row["preview_bytes"] = len(preview)
                    except Exception as exc:  # noqa: BLE001
                        row["preview_error"] = str(exc)

    collect("ch7", QUERIES_7)
    collect("ch9", QUERIES_9)
    INDEX.write_text(json.dumps({"http": http, "results": results}, indent=2), encoding="utf-8")
    after = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("AFTER", after.get("paid_calls"), after.get("spent_usd"))
    print("HTTP", http, "new ch7", len(results["ch7"]), "new ch9", len(results["ch9"]))
    for label in ("ch7", "ch9"):
        print("====", label)
        for row in results[label]:
            slug = (row.get("page_url") or "").rstrip("/").split("/")[-1]
            print(row["photo_id"], slug)


if __name__ == "__main__":
    main()
