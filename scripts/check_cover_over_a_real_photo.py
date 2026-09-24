"""Build the three cover layouts over a REAL photograph and save the pictures.

The Editor-in-Chief approved the v1.9.0 interior but would not sign off the
cover over a photograph, because the only build available was over a generated
placeholder. A flat fixture cannot show type-over-image legibility, whether the
type collides with the subject, or whether the scrim behind the subtitle is
enough. Those three things need one real photograph.

Pexels is unreachable from the build environment, so this runs on the machine
that can reach it. It is FREE: Pexels costs nothing and the paid-call ledger is
never touched. Nothing is saved to any project and no existing file is changed.

    python scripts/check_cover_over_a_real_photo.py
    python scripts/check_cover_over_a_real_photo.py --query "container garden balcony"
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TITLE = "Container Gardening - A Beginner's Guide"
SUBTITLE = "Grow food in small spaces, on a balcony, a step or a windowsill"
AUTHOR = "Lonnie Brown"


def out_dir() -> Path:
    for candidate in (Path.home() / "OneDrive" / "Desktop", Path.home() / "Desktop"):
        if candidate.is_dir():
            target = candidate / "Cover check over a real photo"
            target.mkdir(exist_ok=True)
            return target
    target = ROOT / "exports" / "_cover_check"
    target.mkdir(parents=True, exist_ok=True)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", default="container garden vegetables balcony")
    args = parser.parse_args()

    from services.ebook_pexels import (
        fetch_pexels_photo,
        pexels_public_status,
        search_pexels,
    )
    from services.ebook_photo_cover import LAYOUT_IDS, attach_pexels

    status = pexels_public_status()
    if not status.get("configured"):
        print("PEXELS_API_KEY is not set on this machine, so no photograph can be fetched.")
        print("Set it in .env (the value is in the Render dashboard) and run this again.")
        return 2

    print(f"Searching Pexels for: {args.query}")
    found = search_pexels(args.query, per_page=6, orientation="portrait")
    photos = found.get("photos") or []
    if not photos:
        print("Pexels returned no photographs for that search. Try another --query.")
        return 3
    first = photos[0]
    # search_pexels returns NORMALISED rows, whose id key is "photo_id".
    # Reading "id" here silently gave "" and the fetch refused it.
    photo_id = str(first.get("photo_id") or first.get("id") or "")
    if not photo_id.isdigit():
        print("Pexels returned a photograph without a usable id.")
        return 3
    photo = fetch_pexels_photo(photo_id)
    print(f"Photograph {photo_id} by {photo.get('photographer')}")

    data = {"title": TITLE, "subtitle": SUBTITLE, "author": AUTHOR,
            "package_id": f"cover_check_{photo_id}"}
    # Go through the same entry point the customer path uses. The earlier
    # hand-rolled copy of it stored no source["pexels"] record, and
    # verify_source rightly refused the result.
    data = attach_pexels(data, photo_id, project_id=None)

    target = out_dir()
    cover = data["cover_design"]
    report = [
        "COVER CHECK OVER A REAL PHOTOGRAPH",
        "",
        f"Photograph : Pexels {photo_id} by {photo.get('photographer')}",
        f"Title      : {TITLE}",
        f"Subtitle   : {SUBTITLE}",
        "",
        "Three things to look at on each picture:",
        "  1. Can you read every line of type over the photograph?",
        "  2. Does any line sit on top of the subject's face or the main object?",
        "  3. Is the panel behind the subtitle dark enough for the subtitle to read?",
        "",
    ]
    from PIL import Image

    for layout in LAYOUT_IDS:
        variant = (cover.get("variants") or {}).get(layout) or {}
        quality = variant.get("quality") or {}
        png = variant.get("png_path")
        line = f"{layout:24} quality {'PASS' if quality.get('pass') else 'FAIL'}"
        if png and Path(png).is_file():
            full = target / f"{layout}.png"
            full.write_bytes(Path(png).read_bytes())
            with Image.open(full) as im:
                im.convert("RGB").resize((im.width // 8, im.height // 8)).save(
                    target / f"{layout}_thumbnail.png"
                )
            line += f"  ->  {full.name} and {layout}_thumbnail.png"
        else:
            line += "  ->  no picture was produced"
        if quality.get("findings"):
            line += f"\n{'':26}findings: {quality['findings']}"
        print(line)
        report.append(line)

    report += ["", "Nothing was saved to any project. No paid call was made.",
               "Send these pictures to Claude for the Editor-in-Chief to inspect."]
    (target / "READ ME FIRST.txt").write_text("\n".join(report), encoding="utf-8")
    print(f"\nPictures and a note are in: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
