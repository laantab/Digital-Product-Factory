"""Promote accepted P21 + full 25-page deterministic QA + contact sheets.

Zero paid calls. No PDF/ZIP/Save/Git commit.
"""
from __future__ import annotations

import hashlib
import json
import shutil
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
ACCEPTED = PKG / "accepted_interiors"
MANIFEST = PKG / "package_acceptance_manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def promote_p21() -> dict:
    final = PKG / "coloring_p21_final_candidate.png"
    assert final.is_file(), "missing final candidate"
    ACCEPTED.mkdir(parents=True, exist_ok=True)

    # Preserve intermediates / originals (never overwrite).
    preserved = {
        "coloring_p21.png": (PKG / "coloring_p21.png").is_file(),
        "coloring_p21_cleaned.png": (PKG / "coloring_p21_cleaned.png").is_file(),
        "coloring_p21_final_candidate.png": final.is_file(),
        "originals/coloring_p21_original.png": (
            PKG / "originals" / "coloring_p21_original.png"
        ).is_file(),
    }

    # Backup prior print asset if present, then refresh print from accepted candidate
    # without touching coloring_p21.png source/originals.
    print_path = PKG / "coloring_p21_print_300dpi.png"
    if print_path.is_file():
        bak = PKG / "originals" / "coloring_p21_print_300dpi_pre_accept.png"
        bak.parent.mkdir(parents=True, exist_ok=True)
        if not bak.is_file():
            shutil.copy2(print_path, bak)

    accepted_p21 = ACCEPTED / "coloring_p21.png"
    shutil.copy2(final, accepted_p21)

    # Also write package-root accepted alias used by later book assembly.
    root_accepted = PKG / "coloring_p21_accepted.png"
    shutil.copy2(final, root_accepted)

    # Rebuild 300-DPI print from accepted candidate (local only).
    from services.coloring_book.line_art_layout import prepare_print_interior_300dpi

    prepare_print_interior_300dpi(
        str(accepted_p21),
        str(print_path),
        original_path=str(PKG / "originals" / "coloring_p21_accepted_source.png"),
    )

    m = measure_line_art_layout(str(accepted_p21))
    return {
        "page_number": 21,
        "accepted_path": str(accepted_p21),
        "root_alias": str(root_accepted),
        "print_300dpi": str(print_path),
        "sha256": sha256_file(accepted_p21),
        "qa_measurements": m,
        "preserved": preserved,
        "promoted_from": str(final),
        "regenerated": False,
        "paid_calls": 0,
    }


def gather_accepted_paths() -> list[tuple[int, Path, str]]:
    """Return (page_no, path, topic) for all 25 accepted interiors."""
    scenes = list(BANK_RESCUE_SCENES)
    out: list[tuple[int, Path, str]] = []
    for i, scene in enumerate(scenes, start=1):
        if i == 21:
            path = ACCEPTED / "coloring_p21.png"
            source = "accepted_final_candidate"
        else:
            print_p = PKG / f"coloring_p{i:02d}_print_300dpi.png"
            src_p = PKG / f"coloring_p{i:02d}.png"
            if print_p.is_file():
                # Mirror non-P21 accepted copies for a stable accepted set.
                dest = ACCEPTED / f"coloring_p{i:02d}.png"
                if not dest.is_file() or dest.stat().st_mtime < print_p.stat().st_mtime:
                    shutil.copy2(print_p, dest)
                path = dest
                source = "print_300dpi"
            else:
                dest = ACCEPTED / f"coloring_p{i:02d}.png"
                shutil.copy2(src_p, dest)
                path = dest
                source = "source"
        out.append((i, path, scene.get("topic", f"Page {i}")))
        # stash source tag on path via sidecar later
        (ACCEPTED / f"coloring_p{i:02d}.source.txt").write_text(source, encoding="utf-8")
    return out


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
    # Scene-content heuristics from canonical beats
    scene = BANK_RESCUE_SCENES[page_no - 1]
    t = (topic or "").lower()
    if scene.get("includes_robbers") and "robber" not in t and "getaway" not in t and "surrender" not in t and "police" not in t and "money" not in t and "alarm" not in t and "leaves the bank" not in t and "race" not in t:
        # topic may still be valid; only soft-flag non-obvious pages
        pass
    # Soft flags for human review (cannot prove costume/anatomy without vision)
    flags.append("visual_review: character costume / anatomy / composition uniqueness")
    return flags


def build_contact_sheets(pages: list[tuple[int, Path, str]], qa_rows: list[dict]) -> list[str]:
    """Create readable numbered contact sheets (two sheets: 1-15 and 16-25)."""
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
            f"Thunder Volt — accepted interiors ({name}) — visual approval",
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
            # status border
            status = "PASS" if row["qa_pass"] else "FAIL"
            border = (20, 140, 60) if row["qa_pass"] else (190, 40, 40)
            canvas.paste(cell, (x, y))
            draw.rectangle([x - 2, y - 2, x + thumb_w + 1, y + thumb_h + 1], outline=border, width=3)
            topic = (row["topic"] or "")[:26]
            flags = row.get("review_flags") or []
            hard = [f for f in flags if not str(f).startswith("visual_review")]
            note = "OK" if not hard else "REVIEW"
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
    # Full 5x5 overview
    sheet(list(range(1, 26)), "all_25", cols=5)
    return outs


def main() -> int:
    p21 = promote_p21()
    pages = gather_accepted_paths()
    bible = build_character_bible(THEME)
    scenes = list(BANK_RESCUE_SCENES)

    qa_rows: list[dict] = []
    for page_no, path, topic in pages:
        scene = scenes[page_no - 1]
        prompt = build_interior_page_prompt(
            bible=bible, scene=scene, page_number=page_no, total_pages=25
        )
        metrics = measure_line_art_layout(str(path))
        b64 = _encode_image_jpeg(str(path))
        det = _run_deterministic_image_checks(b64) if b64 else ["encode failed"]
        prompt_issues = _check_prompt_quality(topic, prompt)
        # Blocking = deterministic structural issues only (vision unavailable is not blocking)
        blocking = list(det) + list(prompt_issues)
        qa_pass = len(blocking) == 0
        flags = flag_review_issues(page_no, topic, metrics, blocking)
        source_tag = (ACCEPTED / f"coloring_p{page_no:02d}.source.txt").read_text(
            encoding="utf-8"
        ).strip()
        qa_rows.append(
            {
                "page_number": page_no,
                "topic": topic,
                "filename": path.name,
                "relative_path": str(path.relative_to(PKG)).replace("\\", "/"),
                "source_tag": source_tag,
                "sha256": sha256_file(path),
                "dimensions": {"width": metrics["width"], "height": metrics["height"]},
                "edge_margins_px": metrics["edge_margins_px"],
                "ink_bbox_coverage": metrics["bbox_coverage"],
                "white_pct": metrics["white_pct"],
                "black_ink_pct": metrics["black_ink_pct"],
                "midtone_pct": metrics["midtone_pct"],
                "edge_contact": metrics["edge_contact"],
                "deterministic_issues": det,
                "prompt_issues": prompt_issues,
                "prompt_len": len(prompt),
                "qa_pass": qa_pass,
                "review_flags": flags,
            }
        )

    contact_sheets = build_contact_sheets(pages, qa_rows)
    failed = [r for r in qa_rows if not r["qa_pass"]]
    review_hard = []
    for r in qa_rows:
        hard = [f for f in r["review_flags"] if not str(f).startswith("visual_review")]
        if hard:
            review_hard.append({"page_number": r["page_number"], "topic": r["topic"], "flags": hard})

    # Soft visual-review notes for composition/robbers from scene metadata
    soft_visual = []
    for r in qa_rows:
        scene = scenes[r["page_number"] - 1]
        soft_visual.append(
            {
                "page_number": r["page_number"],
                "topic": r["topic"],
                "expected_robbers": bool(scene.get("includes_robbers")),
                "expected_police": bool(scene.get("includes_police")),
                "note": (
                    "Manual visual review required for character drift, anatomy, "
                    "costume consistency, repeated poses, unrelated content, and robber presence."
                ),
            }
        )

    manifest = {
        "package_id": PKG.name,
        "theme": THEME,
        "paid_calls": 0,
        "p21_promotion": p21,
        "accepted_interiors_dir": str(ACCEPTED),
        "pages": qa_rows,
        "summary": {
            "total_pages": len(qa_rows),
            "qa_passed": sum(1 for r in qa_rows if r["qa_pass"]),
            "qa_failed": len(failed),
            "failed_pages": [
                {"page_number": r["page_number"], "topic": r["topic"], "issues": r["deterministic_issues"]}
                for r in failed
            ],
            "hard_review_flags": review_hard,
        },
        "contact_sheets": contact_sheets,
        "soft_visual_review": soft_visual,
        "stopped_before": ["save", "final_pdf", "zip", "git_commit", "final_book_lock"],
        "book_locked": False,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    # Human-readable table
    print("P21_SHA256", p21["sha256"])
    print("CONTACT_SHEETS")
    for c in contact_sheets:
        print(" ", c)
    print("QA_SUMMARY", manifest["summary"]["qa_passed"], "/", manifest["summary"]["total_pages"])
    print("FAILED", manifest["summary"]["failed_pages"])
    print("HARD_FLAGS", json.dumps(review_hard, indent=2))
    print("--- PAGE REPORT ---")
    for r in qa_rows:
        em = r["edge_margins_px"]
        print(
            f"P{r['page_number']:02d} {r['filename']} "
            f"{r['dimensions']['width']}x{r['dimensions']['height']} "
            f"margins L{em['left']}/T{em['top']}/R{em['right']}/B{em['bottom']} "
            f"bbox={r['ink_bbox_coverage']:.4f} "
            f"W={r['white_pct']:.2f} K={r['black_ink_pct']:.2f} M={r['midtone_pct']:.2f} "
            f"{'PASS' if r['qa_pass'] else 'FAIL'}"
        )
    print("MANIFEST", MANIFEST)
    print("PROMOTED", False)  # book not locked
    print("P21_ACCEPTED_ASSET", True)
    return 0 if not failed else 1


if __name__ == "__main__":
    # fix typo open mode
    raise SystemExit(main())
