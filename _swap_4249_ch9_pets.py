"""Last Ch9 search: pet/travel photo mugs. Also fetch a few IDs."""
from __future__ import annotations

from pathlib import Path

import database
from services.ebook_pexels import _http_get, fetch_pexels_photo, search_pexels

DEST = Path("_visual_swap_4249_candidates")
QUERIES = [
    "dog photo mug",
    "cat photograph ceramic mug",
    "pet photo printed mug",
    "travel photo mug",
    "black and white photo mug",
    "wrap around photo mug",
    "dye sublimation mug photo",
]


def save_preview(pid: str, url: str) -> None:
    path = DEST / f"ch9_{pid}.jpg"
    if path.exists():
        return
    raw = _http_get(url, {}, binary=True)
    path.write_bytes(raw)


def main() -> None:
    before = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("BEFORE", before.get("paid_calls"), before.get("spent_usd"))
    seen = {p.stem.split("_", 1)[-1] for p in DEST.glob("ch9_*.jpg")}
    http = 0
    for q in QUERIES:
        payload = search_pexels(q, page=1, per_page=15, orientation="landscape")
        http += 1
        photos = payload.get("photos") or []
        print(f"Q {q!r} -> {len(photos)}")
        for ph in photos:
            pid = str(ph.get("photo_id"))
            slug = (ph.get("page_url") or "").rstrip("/").split("/")[-1]
            print(" ", pid, ph.get("width"), "x", ph.get("height"), slug)
            if pid in seen:
                continue
            seen.add(pid)
            try:
                save_preview(pid, ph["preview_url"])
            except Exception as exc:  # noqa: BLE001
                print("  ERR", pid, exc)
    for pid in ("767107", "11075707", "9546953", "1382905", "3493047"):
        try:
            ph = fetch_pexels_photo(pid)
            http += 1
            print("ID", pid, ph.get("width"), "x", ph.get("height"), ph.get("page_url"))
            save_preview(pid, ph["preview_url"])
        except Exception as exc:  # noqa: BLE001
            print("IDERR", pid, exc)
    after = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("AFTER", after.get("paid_calls"), after.get("spent_usd"), "searches+", http)


if __name__ == "__main__":
    main()
