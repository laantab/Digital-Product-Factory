"""Multilingual + square Pexels search for photo-on-mug. No project writes."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import database
from services.ebook_pexels import _http_get, search_pexels

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = Path("_visual_swap_4249_candidates")

QUERIES = [
    "fototasse",
    "taza con foto",
    "caneca com foto",
    "tasse photo personnalisee",
    "tasse mit foto",
    "photo cup gift",
    "polaroid mug",
    "heart photo mug",
    "souvenir photo mug",
    "printed family portrait mug",
    "mug with printed faces",
    "ceramic cup with photograph",
    "customized picture cup",
    "photo transfer mug",
    "full color photo mug",
]


def slug(url: str) -> str:
    return (url or "").rstrip("/").split("/")[-1]


def main() -> None:
    before = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("BEFORE", before.get("paid_calls"), before.get("spent_usd"))
    seen = {p.stem.split("_", 1)[-1] for p in DEST.glob("ch9_*.jpg")}
    http = {"search": 0, "preview": 0}
    rows = []
    for q in QUERIES:
        for ori in ("landscape", "square"):
            payload = search_pexels(q, page=1, per_page=15, orientation=ori)
            http["search"] += 1
            photos = payload.get("photos") or []
            print(f"Q[{ori}] {q!r} -> {len(photos)}")
            for ph in photos:
                pid = str(ph.get("photo_id"))
                print(f"  {pid} {ph.get('width')}x{ph.get('height')} {slug(ph.get('page_url') or '')}")
                row = {
                    "photo_id": pid,
                    "query": q,
                    "orientation": ori,
                    "photographer": ph.get("photographer"),
                    "page_url": ph.get("page_url"),
                    "preview_url": ph.get("preview_url"),
                    "original_url": ph.get("original_url"),
                    "width": ph.get("width"),
                    "height": ph.get("height"),
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
    (DEST / "index_ch9_v3.json").write_text(json.dumps({"http": http, "rows": rows}, indent=2), encoding="utf-8")
    after = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("AFTER", after.get("paid_calls"), after.get("spent_usd"))
    print("HTTP", http)


if __name__ == "__main__":
    main()
