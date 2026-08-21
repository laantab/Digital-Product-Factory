"""Fetch nearby Brett Sayles mug IDs and extra targeted queries. No project writes."""
from __future__ import annotations

import sys
from pathlib import Path

import database
from services.ebook_pexels import _http_get, fetch_pexels_photo, search_pexels

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
DEST = Path("_visual_swap_4249_candidates")


def slug(url: str) -> str:
    return (url or "").rstrip("/").split("/")[-1]


def save(pid: str, url: str) -> None:
    path = DEST / f"ch9_{pid}.jpg"
    if path.exists():
        return
    path.write_bytes(_http_get(url, {}, binary=True))


def main() -> None:
    before = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("BEFORE", before.get("paid_calls"), before.get("spent_usd"))
    http = 0
    for pid in range(3493035, 3493065):
        try:
            ph = fetch_pexels_photo(str(pid))
            http += 1
            print("ID", pid, ph.get("width"), "x", ph.get("height"), ph.get("photographer"), slug(ph.get("page_url") or ""))
            save(str(pid), ph["preview_url"])
        except Exception as exc:  # noqa: BLE001
            print("MISS", pid, type(exc).__name__)
    queries = [
        "commemorative photo mug",
        "souvenir photograph mug",
        "black and white portrait mug",
        "mug with printed photograph of couple",
        "keepsake photo mug",
        "picture of family on coffee mug",
        "ceramic mug photo wrap people",
        "printed faces coffee mug",
    ]
    seen = {p.stem.split("_", 1)[-1] for p in DEST.glob("ch9_*.jpg")}
    for q in queries:
        payload = search_pexels(q, page=1, per_page=15, orientation="landscape")
        http += 1
        photos = payload.get("photos") or []
        print(f"Q {q!r} -> {len(photos)}")
        for ph in photos:
            pid = str(ph.get("photo_id"))
            print(" ", pid, ph.get("width"), "x", ph.get("height"), slug(ph.get("page_url") or ""))
            if pid not in seen:
                try:
                    save(pid, ph["preview_url"])
                    seen.add(pid)
                except Exception as exc:  # noqa: BLE001
                    print("  ERR", pid, exc)
    after = database.get_project(4249)["data"]["ebook_workspace"]["paid_call_ledger"] or {}
    print("AFTER", after.get("paid_calls"), after.get("spent_usd"), "http", http)


if __name__ == "__main__":
    main()
