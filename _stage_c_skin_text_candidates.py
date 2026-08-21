"""Local open-skin + no-text cleanup for all 25 Thunder Volt interiors.

Zero paid calls. Writes candidates only — does not promote / Save / PDF / ZIP / commit.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from services.coloring_book.line_art_cleanup import (
    cleanup_thunder_volt_interior,
    count_robber_mask_candidates,
    detect_prohibited_text_marks,
    measure_open_skin_score,
)
from services.coloring_book.line_art_layout import (
    measure_line_art_layout,
    prepare_print_interior_300dpi,
)
from services.coloring_book.prompt_engine import BANK_RESCUE_SCENES
from services.coloring_book.quality_agent import (
    _encode_image_jpeg,
    _run_deterministic_image_checks,
)

PKG = Path("exports/a092b8e351174900a9082fbb46350364")
CAND = PKG / "candidates_open_skin_notext"
PRESERVE = PKG / "preserved_before_skin_text_pass"


def source_for_page(n: int) -> Path:
    """Prefer prior accepted/final assets without destroying them."""
    if n == 21:
        for p in (
            PKG / "coloring_p21_final_candidate.png",
            PKG / "coloring_p21_accepted.png",
            PKG / "accepted_interiors" / "coloring_p21.png",
            PKG / "coloring_p21.png",
        ):
            if p.is_file():
                return p
    # Use API/source originals (not already upscaled print) when present
    src = PKG / f"coloring_p{n:02d}.png"
    if src.is_file():
        return src
    acc = PKG / "accepted_interiors" / f"coloring_p{n:02d}.png"
    return acc


def contact_sheet(paths: list[tuple[int, Path, str, bool]], out: Path, title: str) -> None:
    cols = 5
    thumb_w, thumb_h = 220, 330
    pad, label_h, title_h = 12, 46, 40
    rows = (len(paths) + cols - 1) // cols
    sw = cols * thumb_w + (cols + 1) * pad
    sh = title_h + rows * (thumb_h + label_h) + (rows + 1) * pad
    canvas = Image.new("RGB", (sw, sh), (240, 240, 240))
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 13)
        title_font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
        title_font = font
    draw.text((pad, 8), title, fill=(20, 20, 20), font=title_font)
    for idx, (n, path, topic, ok) in enumerate(paths):
        r, c = divmod(idx, cols)
        x = pad + c * (thumb_w + pad)
        y = title_h + pad + r * (thumb_h + label_h + pad)
        im = Image.open(path).convert("RGB")
        im.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        cell = Image.new("RGB", (thumb_w, thumb_h), (255, 255, 255))
        cell.paste(im, ((thumb_w - im.size[0]) // 2, (thumb_h - im.size[1]) // 2))
        canvas.paste(cell, (x, y))
        border = (20, 140, 60) if ok else (190, 40, 40)
        draw.rectangle([x - 2, y - 2, x + thumb_w + 1, y + thumb_h + 1], outline=border, width=3)
        status = "PASS" if ok else "FAIL"
        draw.text((x, y + thumb_h + 3), f"P{n:02d} {status}", fill=(20, 20, 20), font=font)
        draw.text((x, y + thumb_h + 20), (topic or "")[:28], fill=(50, 50, 50), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out, format="PNG")


def main() -> int:
    CAND.mkdir(parents=True, exist_ok=True)
    PRESERVE.mkdir(parents=True, exist_ok=True)
    scenes = list(BANK_RESCUE_SCENES)
    rows = []
    sheet_items = []

    for n, scene in enumerate(scenes, start=1):
        src = source_for_page(n)
        assert src.is_file(), src
        # Preserve source snapshot once
        snap = PRESERVE / f"coloring_p{n:02d}_pre_skin_text.png"
        if not snap.is_file():
            shutil.copy2(src, snap)

        raw = Image.open(src).convert("RGB")
        cleaned, creport = cleanup_thunder_volt_interior(raw, page_number=n)

        cand_src = CAND / f"coloring_p{n:02d}_candidate_src.png"
        cleaned.save(cand_src, format="PNG")

        # Always finish as 2250×3000 @ 300 DPI
        print_path = CAND / f"coloring_p{n:02d}_candidate_2250x3000.png"
        original_path = CAND / f"coloring_p{n:02d}_candidate_src_preserved.png"
        metrics = prepare_print_interior_300dpi(
            str(cand_src), str(print_path), original_path=str(original_path)
        )

        det = _run_deterministic_image_checks(_encode_image_jpeg(str(print_path)) or "")
        text_issues = detect_prohibited_text_marks(Image.open(print_path))
        skin = measure_open_skin_score(Image.open(print_path))
        layout = measure_line_art_layout(str(print_path))
        masks = count_robber_mask_candidates(Image.open(print_path))
        expects_robbers = bool(scene.get("includes_robbers"))
        robber_note = None
        if expects_robbers and masks < 2:
            robber_note = (
                f"Scene expects robbers but mask-like blobs counted={masks} "
                "(soft review — not always equal to robber heads)."
            )
        elif not expects_robbers:
            robber_note = "Scene plan allows omitting robbers."

        blocking = list(det) + list(text_issues)
        if not skin.get("open_skin_ok"):
            blocking.append(
                f"Open-skin gate failed (face_midtone_pct={skin.get('face_midtone_pct')})."
            )
        if layout["edge_contact"]["sides_pressed"] > 0:
            blocking.append("Edge contact remains after print prep.")
        if layout["midtone_pct"] >= 12.0:
            blocking.append(f"Midtone {layout['midtone_pct']}% >= 12%.")

        qa_pass = len(blocking) == 0
        row = {
            "page_number": n,
            "topic": scene.get("topic"),
            "source": str(src),
            "candidate_src": str(cand_src),
            "candidate_print": str(print_path),
            "cleanup": creport.as_dict(),
            "layout": {
                "width": layout["width"],
                "height": layout["height"],
                "edge_margins_px": layout["edge_margins_px"],
                "bbox_coverage": layout["bbox_coverage"],
                "white_pct": layout["white_pct"],
                "black_ink_pct": layout["black_ink_pct"],
                "midtone_pct": layout["midtone_pct"],
                "dpi": metrics.get("dpi"),
            },
            "open_skin": skin,
            "text_issues": text_issues,
            "deterministic_issues": det,
            "expects_robbers": expects_robbers,
            "robber_mask_candidates": masks,
            "robber_note": robber_note,
            "qa_pass": qa_pass,
            "blocking_issues": blocking,
        }
        rows.append(row)
        sheet_items.append((n, print_path, scene.get("topic", ""), qa_pass))
        print(
            f"P{n:02d} skin={creport.skin_fill_removed} "
            f"text={creport.text_symbols_removed} "
            f"pass={qa_pass} mid={layout['midtone_pct']}"
        )

    contact_all = PKG / "candidates_contact_sheet_all_25.png"
    contact_a = PKG / "candidates_contact_sheet_pages_01_15.png"
    contact_b = PKG / "candidates_contact_sheet_pages_16_25.png"
    contact_sheet(sheet_items, contact_all, "Thunder Volt candidates — open skin / no text (all 25)")
    contact_sheet(sheet_items[:15], contact_a, "Thunder Volt candidates (pages 01-15)")
    contact_sheet(sheet_items[15:], contact_b, "Thunder Volt candidates (pages 16-25)")

    skin_pages = [r["page_number"] for r in rows if r["cleanup"]["skin_fill_removed"]]
    text_pages = [r["page_number"] for r in rows if r["cleanup"]["text_symbols_removed"]]
    failed = [r for r in rows if not r["qa_pass"]]

    report = {
        "package_id": PKG.name,
        "paid_calls": 0,
        "promoted": False,
        "book_locked": False,
        "rule": (
            "Thunder Volt face/neck/arms/hands/visible skin = unfilled white coloring regions; "
            "identity via structure/hair/beard/costume/bible; no gray/solid skin fill; "
            "no dollar signs/letters/numbers in interior art."
        ),
        "candidates_dir": str(CAND),
        "preserved_dir": str(PRESERVE),
        "pages_skin_fill_removed": skin_pages,
        "pages_text_symbols_removed": text_pages,
        "qa_passed": sum(1 for r in rows if r["qa_pass"]),
        "qa_failed": len(failed),
        "failed_pages": [
            {"page_number": r["page_number"], "issues": r["blocking_issues"]} for r in failed
        ],
        "contact_sheets": [str(contact_all), str(contact_a), str(contact_b)],
        "pages": rows,
        "stopped_before": [
            "promotion",
            "save",
            "final_pdf",
            "zip",
            "book_lock",
            "git_commit",
        ],
    }
    out = PKG / "candidates_open_skin_notext_report.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("REPORT", out)
    print("SKIN_PAGES", skin_pages)
    print("TEXT_PAGES", text_pages)
    print("QA", report["qa_passed"], "/", len(rows), "failed", report["failed_pages"])
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
