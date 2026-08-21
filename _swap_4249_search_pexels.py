"""Free Pexels search for #4249 visual replacements. Does not write project data."""
from __future__ import annotations

import json
from pathlib import Path

import database
from services.ebook_pexels import _http_get, search_pexels

DEST = Path("_visual_swap_4249_candidates")
DEST.mkdir(exist_ok=True)

QUERIES_7 = [
    "portable photo printer event",
    "dye sublimation compact printer photo coming out",
    "instant photo printer wedding",
    "dye-sub printer 4x6 print tray",
    "compact photo printer",
    "event photo printing station",
    "portable dye sublimation printer",
    "photo printer printing photograph",
    "instant print photo booth wedding",
    "dye sub printer event",
    "polaroid printer wedding",
    "mini photo printer",
    "photo booth instant print",
]
QUERIES_9 = [
    "photo printed on mug",
    "personalized photo mug family",
    "ceramic mug with photograph",
    "custom photo mug",
    "family photo on coffee mug",
    "printed photograph ceramic mug",
    "personalized picture mug",
    "custom printed coffee mug photo",
    "photo collage mug",
    "picture on ceramic cup",
]


def main() -> None:
    before = (database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {})
    print(
        "BEFORE paid_calls",
        before.get("paid_calls"),
        "spent",
        before.get("spent_usd"),
        "remaining",
        before.get("remaining_usd"),
    )

    results: dict[str, list] = {"ch7": [], "ch9": []}
    seen: set[str] = set()
    http_count = {"search": 0, "preview": 0}

    def collect(label: str, queries: list[str]) -> None:
        for q in queries:
            payload = search_pexels(q, page=1, per_page=12, orientation="landscape")
            http_count["search"] += 1
            photos = payload.get("photos") or []
            print(f"Q[{label}] {q!r} -> {len(photos)}")
            for ph in photos:
                pid = str(ph.get("photo_id"))
                if pid in seen:
                    continue
                seen.add(pid)
                row = {
                    "chapter": label,
                    "query": q,
                    "photo_id": pid,
                    "photographer": ph.get("photographer"),
                    "page_url": ph.get("page_url"),
                    "preview_url": ph.get("preview_url"),
                    "original_url": ph.get("original_url"),
                    "width": ph.get("width"),
                    "height": ph.get("height"),
                    "orientation": ph.get("orientation"),
                    "attribution": ph.get("attribution"),
                }
                results[label].append(row)
                try:
                    preview = _http_get(ph["preview_url"], {}, binary=True)
                    http_count["preview"] += 1
                    (DEST / f"{label}_{pid}.jpg").write_bytes(preview)
                    row["preview_bytes"] = len(preview)
                except Exception as exc:  # noqa: BLE001
                    row["preview_error"] = str(exc)

    collect("ch7", QUERIES_7)
    collect("ch9", QUERIES_9)

    (DEST / "index.json").write_text(
        json.dumps({"http_count": http_count, "results": results}, indent=2),
        encoding="utf-8",
    )
    after = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print(
        "AFTER paid_calls",
        after.get("paid_calls"),
        "spent",
        after.get("spent_usd"),
        "remaining",
        after.get("remaining_usd"),
    )
    print("HTTP", http_count)
    print("UNIQUE ch7", len(results["ch7"]), "ch9", len(results["ch9"]))
    for label in ("ch7", "ch9"):
        print("---", label, "---")
        for row in results[label]:
            print(
                row["photo_id"],
                row["width"],
                "x",
                row["height"],
                row["photographer"],
                row["query"][:40],
                row["page_url"],
            )


if __name__ == "__main__":
    main()
