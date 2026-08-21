import json
from pathlib import Path

idx = json.loads(Path("_visual_swap_4249_candidates/index.json").read_text(encoding="utf-8"))
for label in ("ch7", "ch9"):
    print("=" * 80, label)
    for row in idx["results"][label]:
        url = row.get("page_url") or ""
        slug = url.rstrip("/").split("/")[-1]
        print(f"{row['photo_id']:10} {row['width']:5}x{row['height']:<5} {row['photographer'][:28]:28} {slug}")
