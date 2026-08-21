"""Third-pass Pexels search: mug press / photo-on-mug and compact printers."""
from __future__ import annotations

import json
from pathlib import Path

import database
from services.ebook_pexels import _http_get, search_pexels

DEST = Path("_visual_swap_4249_candidates")
QUERIES = {
    "ch7": [
        "mug press printing",
        "heat press mug photo",
        "compact dye sub photo printer",
        "small photo printer 4x6",
        "event table photo printer",
    ],
    "ch9": [
        "mug press",
        "heat press mug",
        "sublimation printing mug",
        "custom mug printing",
        "photo on cup",
        "ceramic mug portrait",
        "printed photo cup",
        "picture mug gift",
        "family photo ceramic",
        "personalized photo cup",
    ],
}


def main() -> None:
    before = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("BEFORE", before.get("paid_calls"), before.get("spent_usd"))
    seen = {p.stem.split("_", 1)[1] for p in DEST.glob("ch*_*.jpg")}
    results: dict[str, list] = {"ch7": [], "ch9": []}
    http = {"search": 0, "preview": 0}
    for label, queries in QUERIES.items():
        for q in queries:
            for ori in ("landscape", "square"):
                payload = search_pexels(q, page=1, per_page=15, orientation=ori)
                http["search"] += 1
                photos = payload.get("photos") or []
                print(f"Q[{label} {ori}] {q!r} -> {len(photos)}")
                for ph in photos:
                    pid = str(ph.get("photo_id"))
                    if pid in seen:
                        continue
                    seen.add(pid)
                    row = {
                        "chapter": label,
                        "query": q,
                        "orientation": ori,
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
                    except Exception as exc:  # noqa: BLE001
                        row["preview_error"] = str(exc)
    (DEST / "index_pass3.json").write_text(
        json.dumps({"http": http, "results": results}, indent=2), encoding="utf-8"
    )
    after = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("AFTER", after.get("paid_calls"), after.get("spent_usd"))
    print("HTTP", http, "new", {k: len(v) for k, v in results.items()})
    for label, rows in results.items():
        print("====", label)
        for row in rows:
            slug = (row.get("page_url") or "").rstrip("/").split("/")[-1]
            print(row["photo_id"], row["width"], "x", row["height"], slug)


if __name__ == "__main__":
    main()
