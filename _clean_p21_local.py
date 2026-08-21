"""Local gray cleanup for coloring_p21 — zero paid API calls."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from services.coloring_book.line_art_layout import measure_line_art_layout
from services.coloring_book.quality_agent import (
    _encode_image_jpeg,
    _run_deterministic_image_checks,
)

PKG = Path("exports/a092b8e351174900a9082fbb46350364")
SRC = PKG / "coloring_p21.png"
CLEAN = PKG / "coloring_p21_cleaned.png"
SIDE = PKG / "coloring_p21_original_vs_cleaned.png"
ORIG_BACKUP = PKG / "originals" / "coloring_p21_original.png"


def clean_line_art(im: Image.Image) -> Image.Image:
    """Reduce gray/midtone fills; keep black outlines and white open regions.

    Does not crop, resize, or change canvas margins. Only lifts light gray haze
    / soft fills to pure white and snaps near-black ink to pure black — mid-tone
    anti-alias on faces and hands is left intact for smooth outlines.
    """
    rgb = im.convert("RGB")
    w, h = rgb.size
    src = rgb.load()
    out = Image.new("RGB", (w, h), (255, 255, 255))
    dst = out.load()
    for y in range(h):
        for x in range(w):
            r, g, b = src[x, y]
            L = (r + g + b) / 3.0
            if L >= 200:
                dst[x, y] = (255, 255, 255)
            elif L <= 40:
                dst[x, y] = (0, 0, 0)
            elif L >= 185:
                # Remaining soft fill / light AA haze → open white
                dst[x, y] = (255, 255, 255)
            else:
                # Preserve stroke AA and facial detail midtones as-is
                dst[x, y] = (r, g, b)
    return out


def side_by_side(a_path: Path, b_path: Path, out_path: Path) -> None:
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    # Match heights; keep aspect
    target_h = 900
    def scale(im):
        ratio = target_h / im.size[1]
        return im.resize((max(1, int(im.size[0] * ratio)), target_h), Image.Resampling.LANCZOS)

    a_s, b_s = scale(a), scale(b)
    pad = 16
    label_h = 36
    sheet = Image.new(
        "RGB",
        (a_s.size[0] + b_s.size[0] + pad * 3, target_h + label_h + pad * 2),
        (235, 235, 235),
    )
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
    draw.text((pad, 8), "ORIGINAL coloring_p21.png", fill=(20, 20, 20), font=font)
    draw.text(
        (pad * 2 + a_s.size[0], 8),
        "CLEANED coloring_p21_cleaned.png (local, 0 paid)",
        fill=(20, 20, 20),
        font=font,
    )
    sheet.paste(a_s, (pad, label_h + pad))
    sheet.paste(b_s, (pad * 2 + a_s.size[0], label_h + pad))
    sheet.save(out_path, format="PNG")


def main() -> int:
    if not SRC.is_file():
        print("missing", SRC)
        return 2
    ORIG_BACKUP.parent.mkdir(parents=True, exist_ok=True)
    if not ORIG_BACKUP.is_file():
        shutil.copy2(SRC, ORIG_BACKUP)
    # Never overwrite the original slot.
    before = measure_line_art_layout(str(SRC))
    cleaned = clean_line_art(Image.open(SRC))
    assert cleaned.size == Image.open(SRC).size
    cleaned.save(CLEAN, format="PNG")
    after = measure_line_art_layout(str(CLEAN))
    b64 = _encode_image_jpeg(str(CLEAN))
    issues = _run_deterministic_image_checks(b64) if b64 else ["encode failed"]
    side_by_side(SRC, CLEAN, SIDE)
    report = {
        "source": str(SRC),
        "original_preserved": str(ORIG_BACKUP),
        "cleaned": str(CLEAN),
        "side_by_side": str(SIDE),
        "before": {
            "white_pct": before["white_pct"],
            "black_ink_pct": before["black_ink_pct"],
            "midtone_pct": before["midtone_pct"],
            "edge_margins_px": before["edge_margins_px"],
            "width": before["width"],
            "height": before["height"],
        },
        "after": {
            "white_pct": after["white_pct"],
            "black_ink_pct": after["black_ink_pct"],
            "midtone_pct": after["midtone_pct"],
            "edge_margins_px": after["edge_margins_px"],
            "width": after["width"],
            "height": after["height"],
        },
        "deterministic_issues": issues,
        "quality_pass": len(issues) == 0 and after["midtone_pct"] < 12.0,
        "paid_calls": 0,
    }
    (PKG / "coloring_p21_clean_qa.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["quality_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
