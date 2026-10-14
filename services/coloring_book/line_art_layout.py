"""Local line-art layout helpers — no paid image calls."""
from __future__ import annotations

import os
import shutil
from typing import Any

from PIL import Image, ImageChops

# US Letter coloring area ≈ 7.5" × 10" at 300 DPI
PRINT_INTERIOR_SIZE = (2250, 3000)
PRINT_DPI = (300, 300)


def ink_bounding_box(im: Image.Image, *, white_threshold: int = 240) -> tuple[int, int, int, int]:
    """Return inclusive ink bbox (min_x, min_y, max_x, max_y) for non-white pixels."""
    with im.convert("RGB") as rgb:
        channels = rgb.split()
        try:
            with ImageChops.darker(channels[0], channels[1]) as rg:
                with ImageChops.darker(rg, channels[2]) as minimum:
                    with minimum.point([255 if i <= white_threshold else 0 for i in range(256)]) as mask:
                        box = mask.getbbox()
            if box is None:
                return 0, 0, rgb.width - 1, rgb.height - 1
            return box[0], box[1], box[2] - 1, box[3] - 1
        finally:
            for channel in channels:
                channel.close()


def measure_line_art_layout(path: str, *, white_threshold: int = 240) -> dict[str, Any]:
    """Exact edge-contact / bbox / white / black / midtone measurements."""
    with Image.open(path) as source, source.convert("RGB") as im:
        w, h = im.size
        min_x, min_y, max_x, max_y = ink_bounding_box(im, white_threshold=white_threshold)
        total = w * h
        channels = im.split()
        try:
            with ImageChops.darker(channels[0], channels[1]) as rg, ImageChops.darker(rg, channels[2]) as minimum:
                white = sum(minimum.histogram()[241:])
            with ImageChops.lighter(channels[0], channels[1]) as rg, ImageChops.lighter(rg, channels[2]) as maximum:
                black = sum(maximum.histogram()[:40])
        finally:
            for channel in channels:
                channel.close()
        mid = total - white - black
    bw = max(0, max_x - min_x + 1)
    bh = max(0, max_y - min_y + 1)
    margin = max(int(min(w, h) * 0.03), 8)
    return {
        "width": w,
        "height": h,
        "ink_bbox": {"min_x": min_x, "min_y": min_y, "max_x": max_x, "max_y": max_y},
        "bbox_width": bw,
        "bbox_height": bh,
        "bbox_coverage": round((bw * bh) / float(total), 6),
        "edge_margins_px": {
            "left": min_x,
            "top": min_y,
            "right": w - 1 - max_x,
            "bottom": h - 1 - max_y,
        },
        "edge_contact": {
            "left": min_x < margin,
            "top": min_y < margin,
            "right": max_x > w - margin,
            "bottom": max_y > h - margin,
            "sides_pressed": sum(
                [
                    min_x < margin,
                    min_y < margin,
                    max_x > w - margin,
                    max_y > h - margin,
                ]
            ),
            "margin_threshold_px": margin,
        },
        "white_pct": round(100.0 * white / total, 4),
        "black_ink_pct": round(100.0 * black / total, 4),
        "midtone_pct": round(100.0 * mid / total, 4),
        "bytes": os.path.getsize(path) if os.path.isfile(path) else 0,
    }


def fit_artwork_to_safe_margins(
    src_path: str,
    dst_path: str,
    *,
    canvas_size: tuple[int, int] = (1024, 1536),
    min_margin_px: int | None = None,
    max_coverage: float = 0.90,
    target_coverage: float = 0.89,
) -> dict[str, Any]:
    """Proportionally shrink artwork onto a pure-white canvas with safe margins.

    Does not stretch, flip, redraw, or alter character artwork — only scales and
    centers the existing pixels. Trims only surrounding empty white before scale.

    Targets ~88–90% bbox coverage when the art aspect ratio allows it while
    keeping every edge at/above the QA safe-margin threshold (~3%).
    """
    W, H = canvas_size
    src = Image.open(src_path).convert("RGB")
    min_x, min_y, max_x, max_y = ink_bounding_box(src)
    # Keep a tiny pad of source white around ink so outlines are not clipped.
    pad = 2
    x0 = max(0, min_x - pad)
    y0 = max(0, min_y - pad)
    x1 = min(src.size[0], max_x + pad + 1)
    y1 = min(src.size[1], max_y + pad + 1)
    art = src.crop((x0, y0, x1, y1))
    aw, ah = art.size

    # Match quality_agent safe-margin floor (3% of min side, min 8px) + 2px cushion.
    qa_margin = max(int(min(W, H) * 0.03), 8)
    margin = int(min_margin_px) if min_margin_px is not None else qa_margin + 2
    max_w = max(1, W - 2 * margin)
    max_h = max(1, H - 2 * margin)

    # Largest fit inside the margin box.
    scale = min(max_w / float(aw), max_h / float(ah))
    # If that overshoots max coverage, shrink toward target band.
    coverage = (aw * scale) * (ah * scale) / float(W * H)
    if coverage > max_coverage:
        scale *= (target_coverage / coverage) ** 0.5

    nw = max(1, int(round(aw * scale)))
    nh = max(1, int(round(ah * scale)))
    if nw > max_w or nh > max_h:
        s2 = min(max_w / float(nw), max_h / float(nh))
        nw = max(1, int(nw * s2))
        nh = max(1, int(nh * s2))

    resized = art.resize((nw, nh), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (W, H), (255, 255, 255))
    x = (W - nw) // 2
    y = (H - nh) // 2
    canvas.paste(resized, (x, y))
    os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)
    canvas.save(dst_path, format="PNG")
    src.close()
    art.close()
    resized.close()
    canvas.close()
    metrics = measure_line_art_layout(dst_path)
    metrics["scale"] = round(nw / float(aw), 6)
    metrics["source"] = src_path
    metrics["dest"] = dst_path
    metrics["target_coverage"] = target_coverage
    metrics["max_coverage"] = max_coverage
    metrics["min_margin_px_applied"] = margin
    return metrics


def preserve_original_png(src_path: str, original_path: str) -> str:
    """Copy source PNG to a separate original path if not already preserved."""
    if not os.path.isfile(src_path):
        raise FileNotFoundError(src_path)
    os.makedirs(os.path.dirname(original_path) or ".", exist_ok=True)
    if os.path.abspath(src_path) != os.path.abspath(original_path):
        if not os.path.isfile(original_path):
            shutil.copy2(src_path, original_path)
    return original_path


def prepare_print_interior_300dpi(
    src_path: str,
    dst_path: str,
    *,
    original_path: str = "",
    canvas_size: tuple[int, int] = PRINT_INTERIOR_SIZE,
    dpi: tuple[int, int] = PRINT_DPI,
) -> dict[str, Any]:
    """Local print prep: safe-margin fit → 2250×3000 PNG with 300-DPI metadata.

    No stretching, cropping of subject ink (only empty white trim), redrawing,
    or paid API calls. Original API/sample bytes are preserved separately when
    ``original_path`` is provided.
    """
    if original_path:
        preserve_original_png(src_path, original_path)
        fit_src = original_path if os.path.isfile(original_path) else src_path
    else:
        fit_src = src_path

    with Image.open(fit_src) as source:
        src_w = source.width
    # Match QA 3% safe-margin floor on the print canvas (+2px cushion).
    qa_margin = max(int(min(canvas_size) * 0.03), 8)
    margin = qa_margin + 2

    metrics = fit_artwork_to_safe_margins(
        fit_src,
        dst_path,
        canvas_size=canvas_size,
        min_margin_px=margin,
        max_coverage=0.90,
        target_coverage=0.89,
    )
    # Re-save with embedded DPI metadata (Pillow).
    with Image.open(dst_path) as im:
        im.save(dst_path, format="PNG", dpi=dpi)
    metrics["dpi"] = {"x": dpi[0], "y": dpi[1]}
    metrics["print_canvas"] = {"width": canvas_size[0], "height": canvas_size[1]}
    metrics["original_path"] = original_path or ""
    metrics["source_width"] = src_w
    return metrics
