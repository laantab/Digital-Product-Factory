"""Local Coloring Book line-art cleanup — zero paid API / vision calls."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# Global Thunder Volt interior rule (also mirrored in prompt_engine).
THUNDER_VOLT_OPEN_SKIN_RULE = (
    "Thunder Volt’s face, neck, arms, hands, and all visible skin must remain "
    "unfilled white coloring regions. Preserve his Black identity through "
    "consistent facial structure, hairstyle, beard outline, costume, and "
    "character bible—not gray shading or solid skin-tone fill."
)


@dataclass
class CleanupReport:
    page_number: int
    skin_fill_removed: bool = False
    skin_pixels_cleared: int = 0
    text_symbols_removed: bool = False
    text_regions_cleared: int = 0
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "skin_fill_removed": self.skin_fill_removed,
            "skin_pixels_cleared": self.skin_pixels_cleared,
            "text_symbols_removed": self.text_symbols_removed,
            "text_regions_cleared": self.text_regions_cleared,
            "notes": list(self.notes),
        }


def _to_gray_u8(im: Image.Image) -> np.ndarray:
    return np.array(im.convert("L"), dtype=np.uint8)


def clear_soft_gray_and_skin_stipple(gray: np.ndarray) -> tuple[np.ndarray, int]:
    """Lift soft gray / stipple fills to white; keep core black outlines.

    Does not aggressively destroy near-black stroke cores (hairline, features,
    costume outlines, masks). Targets midtone skin stipple and haze.
    """
    g = gray.copy()
    # Soft gray / stipple band → pure white (open coloring regions).
    soft = (g >= 145) & (g <= 250)
    cleared = int(soft.sum())
    g[soft] = 255
    # Near-white cleanup
    g[g >= 248] = 255
    # Snap core ink for stable outlines (eyes/nose/mouth strokes stay).
    g[g <= 55] = 0
    return g, cleared


def open_large_facial_black_fills(gray: np.ndarray) -> tuple[np.ndarray, int]:
    """Whiten bulky black fill interiors in the upper figure (face/neck zone).

    Preserves thin strokes (eyes, nose, mouth, beard outline, hairline) by only
    clearing distance-transform interiors thicker than a stroke. Restricted to
    the upper portion of the largest ink component so boots/emblems/bags are
    less likely to be hit.
    """
    g = gray.copy()
    ink = (g < 90).astype(np.uint8) * 255
    if ink.sum() < 500:
        return g, 0
    # Largest external blob ≈ main cluster / hero group
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    if n <= 1:
        return g, 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    main = 1 + int(np.argmax(areas))
    x, y, w, h, _a = stats[main]
    # Face/neck band: top ~38% of main component
    face = np.zeros_like(ink)
    y1 = y
    y2 = y + max(8, int(h * 0.38))
    x1 = x
    x2 = x + w
    face[y1:y2, x1:x2] = ink[y1:y2, x1:x2]

    dist = cv2.distanceTransform(face, cv2.DIST_L2, 5)
    # Interior of thick fills (not thin outline strokes)
    fill_interior = (dist >= 3.2) & (face > 0)
    cleared = int(fill_interior.sum())
    if cleared:
        g[fill_interior] = 255
    return g, cleared


def _dollar_templates() -> list[np.ndarray]:
    templates: list[np.ndarray] = []
    fonts = [
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\comic.ttf",
        r"C:\Windows\Fonts\courbd.ttf",
        r"C:\Windows\Fonts\impact.ttf",
        r"C:\Windows\Fonts\consolab.ttf",
    ]
    for size in range(36, 140, 8):
        for fp in fonts:
            try:
                font = ImageFont.truetype(fp, size)
            except OSError:
                continue
            canvas = Image.new("L", (size * 3, size * 3), 255)
            draw = ImageDraw.Draw(canvas)
            draw.text((size // 3, size // 6), "$", font=font, fill=0)
            # Also draw a thicker stroke variant
            arr = np.array(canvas)
            ys, xs = np.where(arr < 200)
            if len(xs) < 20:
                continue
            t = arr[ys.min() : ys.max() + 1, xs.min() : xs.max() + 1]
            t = (t < 200).astype(np.uint8) * 255
            # thicken
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            t2 = cv2.dilate(t, k, iterations=1)
            templates.append(t)
            templates.append(t2)
    return templates


_TEMPLATES: list[np.ndarray] | None = None


def _get_templates() -> list[np.ndarray]:
    global _TEMPLATES
    if _TEMPLATES is None:
        _TEMPLATES = _dollar_templates()
    return _TEMPLATES


def remove_dollar_and_text_marks(gray: np.ndarray) -> tuple[np.ndarray, int]:
    """Remove dollar signs / bag lettering via high-confidence template matches only.

    MSER-based wiping is intentionally disabled — it erased legitimate line art.
    Only clears `$` (and near-duplicate currency-mark templates) at score >= 0.78
    on mostly-white bag/open regions. Costume emblems/masks are left alone.
    """
    g = gray.copy()
    inv = 255 - g
    cleared_regions = 0
    h, w = g.shape
    mask = np.zeros_like(g, dtype=np.uint8)

    for templ in _get_templates()[::2]:
        th, tw = templ.shape[:2]
        if th >= h or tw >= w or th < 28 or tw < 14:
            continue
        # Templates store ink as 255 on black=0 background — match against inv
        # where ink is also bright.
        res = cv2.matchTemplate(inv, templ, cv2.TM_CCOEFF_NORMED)
        locs = np.where(res >= 0.78)
        for y, x in zip(locs[0].tolist(), locs[1].tolist()):
            if mask[y : y + th, x : x + tw].mean() > 30:
                continue
            pad = 8
            y0, y1 = max(0, y - pad), min(h, y + th + pad)
            x0, x1 = max(0, x - pad), min(w, x + tw + pad)
            surround = g[y0:y1, x0:x1]
            # Must sit on open/white area (money bag / open region)
            if surround.size == 0 or (surround > 230).mean() < 0.55:
                continue
            cv2.rectangle(mask, (x, y), (x + tw, y + th), 255, -1)
            cleared_regions += 1

    if cleared_regions:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.dilate(mask, k, iterations=1)
        g[mask > 0] = 255
    return g, cleared_regions


def cleanup_thunder_volt_interior(
    im: Image.Image, *, page_number: int = 0
) -> tuple[Image.Image, CleanupReport]:
    """Apply open-skin + no-text local cleanup. Returns RGB image + report."""
    report = CleanupReport(page_number=page_number)
    gray = _to_gray_u8(im)
    g1, soft_cleared = clear_soft_gray_and_skin_stipple(gray)
    g2, face_cleared = open_large_facial_black_fills(g1)
    g3, text_cleared = remove_dollar_and_text_marks(g2)

    skin_cleared = soft_cleared + face_cleared
    report.skin_pixels_cleared = int(skin_cleared)
    report.skin_fill_removed = skin_cleared > 200
    report.text_regions_cleared = int(text_cleared)
    report.text_symbols_removed = text_cleared > 0
    if report.skin_fill_removed:
        report.notes.append(f"cleared_skin_related_pixels={skin_cleared}")
    if report.text_symbols_removed:
        report.notes.append(f"cleared_text_regions={text_cleared}")

    # Pure RGB line art
    rgb = np.stack([g3, g3, g3], axis=-1)
    return Image.fromarray(rgb, mode="RGB"), report


# ----- Deterministic QA helpers (no paid vision) -----

_TEXTISH_RE = re.compile(r"[A-Za-z0-9$€£¥#@&%]")


def detect_prohibited_text_marks(im: Image.Image) -> list[str]:
    """Deterministic check for leftover `$` / text-like marks."""
    issues: list[str] = []
    gray = _to_gray_u8(im)
    inv = 255 - gray
    h, w = gray.shape
    for templ in _get_templates()[::4]:
        th, tw = templ.shape[:2]
        if th >= h or tw >= w:
            continue
        res = cv2.matchTemplate(inv, templ, cv2.TM_CCOEFF_NORMED)
        _minv, maxv, _minl, maxl = cv2.minMaxLoc(res)
        if maxv >= 0.78:
            x, y = maxl
            pad = 4
            roi = gray[max(0, y - pad) : y + th + pad, max(0, x - pad) : x + tw + pad]
            if roi.size and (roi > 230).mean() >= 0.4:
                issues.append(
                    f"Prohibited text/symbol likely present near ({x},{y}) "
                    f"(dollar-template score={maxv:.2f})."
                )
                break
    return issues


def measure_open_skin_score(im: Image.Image) -> dict[str, Any]:
    """Estimate whether hero upper-body skin band is open (unfilled) for coloring."""
    gray = _to_gray_u8(im)
    ink = (gray < 90).astype(np.uint8) * 255
    h, w = gray.shape
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    if n <= 1:
        return {"open_skin_ok": False, "reason": "no_ink", "face_midtone_pct": 100.0}
    main = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    x, y, bw, bh, _a = stats[main]
    y1, y2 = y, y + max(8, int(bh * 0.38))
    x1, x2 = x, x + bw
    face = gray[y1:y2, x1:x2]
    if face.size == 0:
        return {"open_skin_ok": False, "reason": "empty_face_band", "face_midtone_pct": 100.0}
    mid = float(((face > 55) & (face < 245)).mean() * 100.0)
    # Soft gray in face band should be low after cleanup
    open_ok = mid <= 14.0
    return {
        "open_skin_ok": open_ok,
        "face_midtone_pct": round(mid, 4),
        "face_bbox": {"x": int(x1), "y": int(y1), "w": int(x2 - x1), "h": int(y2 - y1)},
    }


def count_robber_mask_candidates(im: Image.Image) -> int:
    """Weak deterministic count of dark eye-mask-like blobs (review aid)."""
    gray = _to_gray_u8(im)
    dark = (gray < 40).astype(np.uint8) * 255
    n, labels, stats, _ = cv2.connectedComponentsWithStats(dark, 8)
    count = 0
    for i in range(1, n):
        x, y, w, h, a = stats[i]
        if a < 80 or a > 6000:
            continue
        aspect = w / float(h + 1e-6)
        if 1.2 <= aspect <= 4.5 and 10 <= h <= 80 and 20 <= w <= 160:
            count += 1
    return count
