"""Local margin fix for P21 cleaned → final candidate. Zero paid calls."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from services.coloring_book.line_art_layout import (
    fit_artwork_to_safe_margins,
    measure_line_art_layout,
)
from services.coloring_book.prompt_engine import (
    BANK_RESCUE_SCENES,
    build_character_bible,
    build_interior_page_prompt,
)
from services.coloring_book.quality_agent import (
    _check_prompt_quality,
    _encode_image_jpeg,
    _run_deterministic_image_checks,
    validate_coloring_book_page,
)

THEME = (
    "Thunder Volt is a Black superhero. "
    "He is stopping two adult men from robbing a bank and getting away in New York City."
)
PKG = Path("exports/a092b8e351174900a9082fbb46350364")
SRC_ORIG = PKG / "coloring_p21.png"
SRC_CLEAN = PKG / "coloring_p21_cleaned.png"
ORIG_BACKUP = PKG / "originals" / "coloring_p21_original.png"
FINAL = PKG / "coloring_p21_final_candidate.png"
TRIO = PKG / "coloring_p21_original_cleaned_final.png"


def side_by_side_trio(paths: list[Path], labels: list[str], out: Path, target_h: int = 720) -> None:
    imgs = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        ratio = target_h / im.size[1]
        imgs.append(
            im.resize((max(1, int(im.size[0] * ratio)), target_h), Image.Resampling.LANCZOS)
        )
    pad, label_h = 14, 40
    sheet_w = sum(i.size[0] for i in imgs) + pad * (len(imgs) + 1)
    sheet_h = target_h + label_h + pad * 2
    sheet = Image.new("RGB", (sheet_w, sheet_h), (236, 236, 236))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    x = pad
    for lab, im in zip(labels, imgs):
        draw.text((x, 8), lab, fill=(20, 20, 20), font=font)
        sheet.paste(im, (x, label_h + pad))
        x += im.size[0] + pad
    sheet.save(out, format="PNG")


def main() -> int:
    assert SRC_ORIG.is_file() and SRC_CLEAN.is_file()
    ORIG_BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if not ORIG_BACKUP.is_file():
        shutil.copy2(SRC_ORIG, ORIG_BACKUP)

    before = measure_line_art_layout(str(SRC_CLEAN))
    metrics = fit_artwork_to_safe_margins(
        str(SRC_CLEAN),
        str(FINAL),
        canvas_size=(1024, 1536),
        min_margin_px=30,
        max_coverage=0.90,
        target_coverage=0.89,
    )
    after = measure_line_art_layout(str(FINAL))

    bible = build_character_bible(THEME)
    scenes = list(BANK_RESCUE_SCENES)
    scene = next(s for s in scenes if "returns the money" in s.get("topic", "").lower())
    page_number = next(i for i, s in enumerate(scenes, 1) if s["id"] == scene["id"])
    prompt = build_interior_page_prompt(
        bible=bible, scene=scene, page_number=page_number, total_pages=25
    )

    b64 = _encode_image_jpeg(str(FINAL))
    det = _run_deterministic_image_checks(b64) if b64 else ["encode failed"]
    prompt_issues = _check_prompt_quality(scene["topic"], prompt)
    page_result = validate_coloring_book_page(
        page_number=page_number,
        topic=scene["topic"],
        line_art_prompt=prompt,
        image_path=str(FINAL),
        main_character="Thunder Volt",
        setting="New York City",
        topic_field=THEME,
    )

    edge_ok = after["edge_contact"]["sides_pressed"] == 0
    mid_ok = after["midtone_pct"] < 12.0
    quality_pass = (
        bool(page_result.quality_pass)
        and edge_ok
        and mid_ok
        and len(det) == 0
        and len(prompt_issues) == 0
    )

    side_by_side_trio(
        [SRC_ORIG, SRC_CLEAN, FINAL],
        [
            "ORIGINAL coloring_p21.png",
            "CLEANED coloring_p21_cleaned.png",
            "FINAL CANDIDATE coloring_p21_final_candidate.png",
        ],
        TRIO,
    )

    report = {
        "source_cleaned": str(SRC_CLEAN),
        "final_candidate": str(FINAL),
        "preserved": {
            "coloring_p21.png": SRC_ORIG.is_file(),
            "coloring_p21_cleaned.png": SRC_CLEAN.is_file(),
            "original_backup": str(ORIG_BACKUP),
        },
        "before_clean_source": {
            "midtone_pct": before["midtone_pct"],
            "edge_contact": before["edge_contact"],
            "edge_margins_px": before["edge_margins_px"],
        },
        "fit_metrics": metrics,
        "after": after,
        "scene": {
            "id": scene["id"],
            "topic": scene["topic"],
            "page_number": page_number,
        },
        "prompt_len": len(prompt),
        "deterministic_issues": det,
        "prompt_issues": prompt_issues,
        "page_qa": {
            "quality_pass": page_result.quality_pass,
            "issues": page_result.issues,
            "ai_vision_notes": page_result.ai_vision_notes,
        },
        "gates": {
            "edge_contact_cleared": edge_ok,
            "midtone_under_12": mid_ok,
            "no_deterministic_issues": len(det) == 0,
            "prompt_ok": len(prompt_issues) == 0,
        },
        "quality_pass": quality_pass,
        "side_by_side_trio": str(TRIO),
        "paid_calls": 0,
        "promoted": False,
        "pdf_built": False,
    }
    (PKG / "coloring_p21_final_candidate_qa.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if quality_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
