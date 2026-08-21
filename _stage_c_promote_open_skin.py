"""Promote approved open-skin/no-text candidates into accepted interiors.

Zero paid calls. No image generation. No Save / PDF / ZIP / book-lock / Git commit.
Preserves prior accepted + print_300dpi slots before overwrite.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from services.coloring_book.line_art_layout import measure_line_art_layout
from services.coloring_book.prompt_engine import (
    BANK_RESCUE_SCENES,
    build_character_bible,
    build_interior_page_prompt,
)
from services.coloring_book.quality_agent import (
    _check_prompt_quality,
    _encode_image_jpeg,
    _run_deterministic_image_checks,
)

THEME = (
    "Thunder Volt is a Black superhero. "
    "He is stopping two adult men from robbing a bank and getting away in New York City."
)
PKG = Path("exports/a092b8e351174900a9082fbb46350364")
CAND = PKG / "candidates_open_skin_notext"
ACCEPTED = PKG / "accepted_interiors"
MANIFEST = PKG / "package_acceptance_manifest.json"
PRESERVE_PREV = PKG / "preserved_before_open_skin_promote"
CAND_REPORT = PKG / "candidates_open_skin_notext_report.json"
SOURCE_TAG = "open_skin_notext_candidate_2250x3000"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _preserve_once(src: Path, dest: Path) -> bool:
    """Copy src→dest only if dest does not already exist. Never overwrite preserve."""
    if not src.is_file():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        return False
    shutil.copy2(src, dest)
    return True


def promote_all() -> list[dict]:
    ACCEPTED.mkdir(parents=True, exist_ok=True)
    PRESERVE_PREV.mkdir(parents=True, exist_ok=True)
    promotions: list[dict] = []

    for n in range(1, 26):
        cand = CAND / f"coloring_p{n:02d}_candidate_2250x3000.png"
        assert cand.is_file(), f"missing candidate {cand}"

        accepted_path = ACCEPTED / f"coloring_p{n:02d}.png"
        print_path = PKG / f"coloring_p{n:02d}_print_300dpi.png"

        preserved = {
            "accepted_interiors_prev": _preserve_once(
                accepted_path,
                PRESERVE_PREV / f"accepted_interiors_coloring_p{n:02d}.png",
            ),
            "print_300dpi_prev": _preserve_once(
                print_path,
                PRESERVE_PREV / f"coloring_p{n:02d}_print_300dpi.png",
            ),
            # Root coloring_pNN.png and originals/ are never overwritten.
            "root_source_untouched": (PKG / f"coloring_p{n:02d}.png").is_file(),
            "originals_untouched": (
                PKG / "originals" / f"coloring_p{n:02d}_original.png"
            ).is_file(),
        }

        # Promote candidate bytes into accepted + print slots (already 2250×3000 @ 300 DPI).
        shutil.copy2(cand, accepted_path)
        shutil.copy2(cand, print_path)

        aliases: dict[str, str] = {}
        if n == 21:
            root_accepted = PKG / "coloring_p21_accepted.png"
            _preserve_once(
                root_accepted,
                PRESERVE_PREV / "coloring_p21_accepted.png",
            )
            shutil.copy2(cand, root_accepted)
            aliases["coloring_p21_accepted.png"] = str(root_accepted)

        (ACCEPTED / f"coloring_p{n:02d}.source.txt").write_text(
            SOURCE_TAG, encoding="utf-8"
        )

        promotions.append(
            {
                "page_number": n,
                "candidate": str(cand),
                "accepted_path": str(accepted_path),
                "print_300dpi": str(print_path),
                "aliases": aliases,
                "sha256": sha256_file(accepted_path),
                "preserved_actions": preserved,
                "regenerated": False,
                "paid_calls": 0,
            }
        )
    return promotions


def flag_review_issues(page_no: int, topic: str, metrics: dict, det_issues: list[str]) -> list[str]:
    flags: list[str] = []
    flags.extend(det_issues)
    if metrics["edge_contact"]["sides_pressed"] > 0:
        flags.append("edge_contact / possible cropping")
    if metrics["bbox_coverage"] > 0.92:
        flags.append("very high bbox coverage — check cropping/margins")
    if metrics["bbox_coverage"] < 0.40:
        flags.append("tiny coloring area / subject too small")
    if metrics["midtone_pct"] >= 12.0:
        flags.append("gray/shading midtone >= 12%")
    if metrics["white_pct"] < 35.0:
        flags.append("insufficient open coloring space")
    if metrics["black_ink_pct"] > 55.0:
        flags.append("excessive ink density")
    flags.append("visual_review: character costume / anatomy / composition uniqueness")
    return flags


def build_contact_sheets(qa_rows: list[dict]) -> list[str]:
    by_no = {r["page_number"]: r for r in qa_rows}
    outs: list[str] = []

    def sheet(page_nos: list[int], name: str, cols: int = 5) -> Path:
        thumbs = []
        for n in page_nos:
            path = ACCEPTED / f"coloring_p{n:02d}.png"
            im = Image.open(path).convert("RGB")
            im.thumbnail((240, 360), Image.Resampling.LANCZOS)
            thumbs.append((n, im, by_no[n]))
        rows = (len(thumbs) + cols - 1) // cols
        thumb_w, thumb_h = 240, 360
        pad, label_h, title_h = 14, 48, 44
        sw = cols * thumb_w + (cols + 1) * pad
        sh = title_h + rows * (thumb_h + label_h) + (rows + 1) * pad
        canvas = Image.new("RGB", (sw, sh), (242, 242, 242))
        draw = ImageDraw.Draw(canvas)
        try:
            font = ImageFont.truetype("arial.ttf", 14)
            title_font = ImageFont.truetype("arial.ttf", 20)
        except OSError:
            font = ImageFont.load_default()
            title_font = font
        draw.text(
            (pad, 10),
            f"Thunder Volt — accepted open-skin/no-text ({name})",
            fill=(15, 15, 15),
            font=title_font,
        )
        for idx, (n, im, row) in enumerate(thumbs):
            r, c = divmod(idx, cols)
            x = pad + c * (thumb_w + pad)
            y = title_h + pad + r * (thumb_h + label_h + pad)
            cell = Image.new("RGB", (thumb_w, thumb_h), (255, 255, 255))
            ox = (thumb_w - im.size[0]) // 2
            oy = (thumb_h - im.size[1]) // 2
            cell.paste(im, (ox, oy))
            border = (20, 140, 60) if row["qa_pass"] else (190, 40, 40)
            canvas.paste(cell, (x, y))
            draw.rectangle(
                [x - 2, y - 2, x + thumb_w + 1, y + thumb_h + 1],
                outline=border,
                width=3,
            )
            topic = (row["topic"] or "")[:26]
            hard = [
                f
                for f in (row.get("review_flags") or [])
                if not str(f).startswith("visual_review")
            ]
            note = "OK" if not hard else "REVIEW"
            status = "PASS" if row["qa_pass"] else "FAIL"
            draw.text(
                (x, y + thumb_h + 4),
                f"P{n:02d} {status}/{note}",
                fill=(20, 20, 20),
                font=font,
            )
            draw.text((x, y + thumb_h + 22), topic, fill=(50, 50, 50), font=font)
        out = PKG / f"accepted_contact_sheet_{name.replace(' ', '_').replace('-', '_')}.png"
        canvas.save(out, format="PNG")
        outs.append(str(out))
        return out

    sheet(list(range(1, 16)), "pages_01-15")
    sheet(list(range(16, 26)), "pages_16-25")
    sheet(list(range(1, 26)), "all_25", cols=5)
    return outs


def main() -> int:
    promotions = promote_all()
    bible = build_character_bible(THEME)
    scenes = list(BANK_RESCUE_SCENES)

    # Load candidate report open-skin / text notes when available.
    cand_by_page: dict[int, dict] = {}
    if CAND_REPORT.is_file():
        crep = json.loads(CAND_REPORT.read_text(encoding="utf-8"))
        for row in crep.get("pages") or []:
            cand_by_page[int(row["page_number"])] = row

    qa_rows: list[dict] = []
    for promo in promotions:
        page_no = promo["page_number"]
        path = Path(promo["accepted_path"])
        scene = scenes[page_no - 1]
        topic = scene.get("topic", f"Page {page_no}")
        prompt = build_interior_page_prompt(
            bible=bible, scene=scene, page_number=page_no, total_pages=25
        )
        metrics = measure_line_art_layout(str(path))
        b64 = _encode_image_jpeg(str(path))
        det = _run_deterministic_image_checks(b64) if b64 else ["encode failed"]
        prompt_issues = _check_prompt_quality(topic, prompt)
        blocking = list(det) + list(prompt_issues)
        qa_pass = len(blocking) == 0
        flags = flag_review_issues(page_no, topic, metrics, blocking)
        crow = cand_by_page.get(page_no, {})
        qa_rows.append(
            {
                "page_number": page_no,
                "topic": topic,
                "filename": path.name,
                "relative_path": str(path.relative_to(PKG)).replace("\\", "/"),
                "source_tag": SOURCE_TAG,
                "promoted_from": promo["candidate"],
                "promotion_note": (
                    "Promoted from approved open-skin/no-text candidate "
                    "(candidate_2250x3000); zero paid calls; no regeneration."
                ),
                "sha256": promo["sha256"],
                "dimensions": {
                    "width": metrics["width"],
                    "height": metrics["height"],
                },
                "edge_margins_px": metrics["edge_margins_px"],
                "ink_bbox_coverage": metrics["bbox_coverage"],
                "white_pct": metrics["white_pct"],
                "black_ink_pct": metrics["black_ink_pct"],
                "midtone_pct": metrics["midtone_pct"],
                "edge_contact": metrics["edge_contact"],
                "dpi": metrics.get("dpi")
                or {"x": 300, "y": 300},
                "open_skin": crow.get("open_skin"),
                "text_issues": crow.get("text_issues") or [],
                "cleanup": crow.get("cleanup"),
                "deterministic_issues": det,
                "prompt_issues": prompt_issues,
                "prompt_len": len(prompt),
                "qa_pass": qa_pass,
                "review_flags": flags,
                "print_300dpi": promo["print_300dpi"],
                "aliases": promo["aliases"],
                "preserved_actions": promo["preserved_actions"],
            }
        )

    contact_sheets = build_contact_sheets(qa_rows)
    failed = [r for r in qa_rows if not r["qa_pass"]]
    review_hard = []
    for r in qa_rows:
        hard = [f for f in r["review_flags"] if not str(f).startswith("visual_review")]
        if hard:
            review_hard.append(
                {
                    "page_number": r["page_number"],
                    "topic": r["topic"],
                    "flags": hard,
                }
            )

    soft_visual = []
    for r in qa_rows:
        scene = scenes[r["page_number"] - 1]
        soft = [
            f
            for f in r["review_flags"]
            if str(f).startswith("visual_review")
            or "midtone" in str(f).lower()
            or "bbox" in str(f).lower()
        ]
        # Include non-blocking hard-ish soft flags too
        soft_extra = [
            f
            for f in r["review_flags"]
            if not str(f).startswith("visual_review")
            and f not in (r.get("deterministic_issues") or [])
            and f not in (r.get("prompt_issues") or [])
        ]
        soft_visual.append(
            {
                "page_number": r["page_number"],
                "topic": r["topic"],
                "expected_robbers": bool(scene.get("includes_robbers")),
                "expected_police": bool(scene.get("includes_police")),
                "soft_flags": soft + soft_extra,
                "note": (
                    "Manual visual review required for character drift, anatomy, "
                    "costume consistency, repeated poses, unrelated content, and robber presence."
                ),
            }
        )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest = {
        "package_id": PKG.name,
        "theme": THEME,
        "paid_calls": 0,
        "promoted_at": now,
        "promotion": {
            "kind": "open_skin_notext_candidates",
            "candidates_dir": str(CAND),
            "candidate_report": str(CAND_REPORT),
            "preserved_previous_accepted_dir": str(PRESERVE_PREV),
            "pages_promoted": 25,
            "regenerated": False,
            "paid_calls": 0,
            "rule": (
                "Thunder Volt face/neck/arms/hands/visible skin = unfilled white "
                "coloring regions; identity via structure/hair/beard/costume/bible; "
                "no gray/solid skin fill; no dollar signs/letters/numbers in interior art."
            ),
        },
        "accepted_interiors_dir": str(ACCEPTED),
        "pages": qa_rows,
        "summary": {
            "total_pages": len(qa_rows),
            "qa_passed": sum(1 for r in qa_rows if r["qa_pass"]),
            "qa_failed": len(failed),
            "failed_pages": [
                {
                    "page_number": r["page_number"],
                    "topic": r["topic"],
                    "issues": r["deterministic_issues"] + r["prompt_issues"],
                }
                for r in failed
            ],
            "hard_review_flags": review_hard,
        },
        "contact_sheets": contact_sheets,
        "soft_visual_review": soft_visual,
        "stopped_before": [
            "save",
            "final_pdf",
            "zip",
            "git_commit",
            "final_book_lock",
        ],
        "book_locked": False,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Mark candidate report as promoted (local book assets only; not book-locked).
    if CAND_REPORT.is_file():
        crep = json.loads(CAND_REPORT.read_text(encoding="utf-8"))
        crep["promoted"] = True
        crep["promoted_at"] = now
        crep["promoted_into"] = str(ACCEPTED)
        crep["book_locked"] = False
        crep["paid_calls"] = 0
        CAND_REPORT.write_text(json.dumps(crep, indent=2), encoding="utf-8")

    print("PROMOTED_PAGES", len(promotions))
    print("PRESERVE_DIR", PRESERVE_PREV)
    print("CONTACT_SHEETS")
    for c in contact_sheets:
        print(" ", c)
    print(
        "QA_SUMMARY",
        manifest["summary"]["qa_passed"],
        "/",
        manifest["summary"]["total_pages"],
    )
    print("FAILED", manifest["summary"]["failed_pages"])
    print("HARD_FLAGS", json.dumps(review_hard, indent=2))
    soft_nonzero = [s for s in soft_visual if s.get("soft_flags")]
    print("SOFT_VISUAL_FLAG_PAGES", len(soft_nonzero))
    for s in soft_nonzero:
        non_generic = [
            f
            for f in s["soft_flags"]
            if f != "visual_review: character costume / anatomy / composition uniqueness"
        ]
        if non_generic:
            print(f"  P{s['page_number']:02d}", non_generic)
    print("--- PAGE REPORT ---")
    for r in qa_rows:
        em = r["edge_margins_px"]
        print(
            f"P{r['page_number']:02d} {r['filename']} "
            f"{r['dimensions']['width']}x{r['dimensions']['height']} "
            f"sha={r['sha256'][:12]} "
            f"margins L{em['left']}/T{em['top']}/R{em['right']}/B{em['bottom']} "
            f"bbox={r['ink_bbox_coverage']:.4f} "
            f"W={r['white_pct']:.2f} K={r['black_ink_pct']:.2f} M={r['midtone_pct']:.2f} "
            f"{'PASS' if r['qa_pass'] else 'FAIL'}"
        )
    print("MANIFEST", MANIFEST)
    print("BOOK_LOCKED", False)
    print("STOPPED_BEFORE", manifest["stopped_before"])
    print("PAID_CALLS", 0)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
