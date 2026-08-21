"""Authorized Stage C — 24 medium gpt-image-2 interiors for Thunder Volt.

Does NOT Save, build final PDF/ZIP, or commit. Stops after QA + contact sheet.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

PKG = "a092b8e351174900a9082fbb46350364"
THEME = (
    "Thunder Volt is a Black superhero. "
    "He is stopping two adult men from robbing a bank and getting away in New York City."
)
EXPORT = ROOT / "exports" / PKG


def sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def build_contact_sheet(paths: list[tuple[int, str, Path]], out_path: Path) -> Path:
    """5×5 grid of thumbnails for visual approval."""
    cols, rows = 5, 5
    thumb_w, thumb_h = 220, 330
    pad = 12
    label_h = 28
    sheet_w = cols * thumb_w + (cols + 1) * pad
    sheet_h = rows * (thumb_h + label_h) + (rows + 1) * pad + 36
    sheet = Image.new("RGB", (sheet_w, sheet_h), (245, 245, 245))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 14)
        title_font = ImageFont.truetype("arial.ttf", 18)
    except OSError:
        font = ImageFont.load_default()
        title_font = font
    draw.text((pad, 8), "Thunder Volt — Stage C contact sheet (visual approval)", fill=(20, 20, 20), font=title_font)

    by_num = {n: (topic, p) for n, topic, p in paths}
    for idx in range(25):
        page_no = idx + 1
        r, c = divmod(idx, cols)
        x = pad + c * (thumb_w + pad)
        y = 36 + pad + r * (thumb_h + label_h + pad)
        topic, path = by_num.get(page_no, ("", None))
        cell = Image.new("RGB", (thumb_w, thumb_h), (255, 255, 255))
        status = "MISSING"
        if path and path.is_file():
            im = Image.open(path).convert("RGB")
            im.thumbnail((thumb_w, thumb_h), Image.Resampling.LANCZOS)
            ox = (thumb_w - im.size[0]) // 2
            oy = (thumb_h - im.size[1]) // 2
            cell.paste(im, (ox, oy))
            status = "OK"
            im.close()
        sheet.paste(cell, (x, y))
        label = f"P{page_no:02d} {status} {(topic or '')[:28]}"
        draw.text((x, y + thumb_h + 4), label, fill=(30, 30, 30), font=font)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, format="PNG")
    return out_path


def main() -> int:
    t0 = time.time()
    EXPORT.mkdir(parents=True, exist_ok=True)

    cover = EXPORT / "img_cover.png"
    sample_corrected = EXPORT / "sample_interior_margin_corrected.png"
    sample_slot = EXPORT / "coloring_p10.png"
    if not cover.is_file():
        print("FATAL: approved cover missing — abort (no cover regen).")
        return 2
    cover_sha = sha16(cover)
    print("cover_sha", cover_sha)

    # Promote approved Stage B sample into page-10 slot (0 paid).
    if sample_corrected.is_file():
        original = EXPORT / "coloring_p10_original_fullres.png"
        if sample_slot.is_file() and not original.is_file():
            shutil.copy2(sample_slot, original)
        # Keep Stage-B API original if already present; slot becomes approved corrected.
        shutil.copy2(sample_corrected, sample_slot)
        print("promoted_sample", sample_slot, "bytes", sample_slot.stat().st_size)
    elif not sample_slot.is_file():
        print("FATAL: page-10 sample missing — abort (no sample regen).")
        return 2
    sample_sha = sha16(sample_slot)
    print("sample_sha", sample_sha)

    from services.coloring_book.builder import build_coloring_book
    from services.ebook_package import get_package_image_budget, reset_package_image_budgets

    reset_package_image_budgets()
    print("=== Stage C generation start (max 24 medium attempts) ===")
    book = build_coloring_book(
        theme=THEME,
        topic=THEME,
        setting="New York City",
        main_character="Thunder Volt",
        page_count=25,
        age_group="Ages 8-12",
        art_style="comic",
        package_id=PKG,
        quality_mode="ai_image_coloring_page",
        generation_stage="full",
        character_approved=True,
        sample_approved=True,
        force_image_regen=False,
        reference_image_path=str(cover),
    )

    budget = get_package_image_budget(PKG)
    print("budget", json.dumps(budget))
    print("image_failures", book.image_failures)
    print("warnings:")
    for w in book.warnings or []:
        print(" -", w)

    # Cover must be unchanged.
    if sha16(cover) != cover_sha:
        print("FATAL: cover SHA changed — unexpected regeneration")
        return 3
    print("cover_unchanged OK")

    # Inventory + contact sheet from API/source slots (not final export).
    page_paths: list[tuple[int, str, Path]] = []
    missing: list[int] = []
    for page in book.pages:
        src = EXPORT / f"coloring_p{page.page_number:02d}.png"
        print_path = EXPORT / f"coloring_p{page.page_number:02d}_print_300dpi.png"
        use = src if src.is_file() else print_path
        if not use.is_file():
            missing.append(page.page_number)
        page_paths.append((page.page_number, page.topic, use))

    contact = EXPORT / "stage_c_contact_sheet.png"
    build_contact_sheet(page_paths, contact)
    print("contact_sheet", contact, "bytes", contact.stat().st_size)

    qa = book.quality_result or {}
    failed = [
        p for p in qa.get("pages", []) if not p.get("quality_pass")
    ]
    questionable = []
    for p in qa.get("pages", []):
        notes = str(p.get("ai_vision_notes") or "")
        if p.get("quality_pass") and (
            "Limited QA" in notes or "review" in notes.lower() or p.get("issues")
        ):
            questionable.append(p)

    report = {
        "package_id": PKG,
        "elapsed_sec": round(time.time() - t0, 1),
        "budget": budget,
        "image_failures": list(book.image_failures or []),
        "missing_source_pages": missing,
        "cover_sha": cover_sha,
        "sample_sha": sample_sha,
        "qa_all_passed": qa.get("all_passed"),
        "qa_blocked_export": qa.get("blocked_export"),
        "failed_pages": failed,
        "questionable_pages": [
            {
                "page_number": p.get("page_number"),
                "topic": p.get("topic"),
                "issues": p.get("issues"),
                "ai_vision_notes": p.get("ai_vision_notes"),
            }
            for p in questionable
        ],
        "warnings": list(book.warnings or []),
        "contact_sheet": str(contact),
        "export_blocked": bool(
            missing
            or book.image_failures
            or qa.get("blocked_export")
            or not qa.get("all_passed", False)
        ),
        "stopped_before": ["save", "final_pdf", "zip", "git_commit"],
    }
    report_path = EXPORT / "stage_c_qa_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("report", report_path)
    print("export_blocked", report["export_blocked"])
    print("FAILED_PAGES", len(failed))
    for p in failed:
        print(
            f"  FAIL P{p.get('page_number')}: {p.get('topic')} | {p.get('issues')}"
        )
    print("QUESTIONABLE_PAGES", len(questionable))
    for p in questionable:
        print(
            f"  REVIEW P{p.get('page_number')}: {p.get('topic')} | {p.get('ai_vision_notes')}"
        )
    print("MISSING", missing)
    print("=== Stage C complete — awaiting visual approval ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
