"""Photo-backed Ebook covers: Pexels stock or user upload, three type variants, QA.

Zero paid calls. Tests mock Pexels; live HTTP is blocked in FACTORY_TEST_MODE.
Does not rewrite manuscript or ledgers.
Renders the selected photograph full-bleed (EXIF-correct, crop-to-fill).
Typography varies; the photograph is not decorated, framed, or distorted.
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import logging
import os
import re
import shutil
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from services.ebook_fonts import ebook_font_paths
from services.ebook_package import EXPORTS_DIR

LAYOUT_IDS = ("full_bleed_editorial", "split_studio", "printed_moment")
LAYOUT_LABELS = {
    "full_bleed_editorial": "Full Bleed · Top Type",
    "split_studio": "Full Bleed · Center Type",
    "printed_moment": "Full Bleed · Lower Type",
}
LAYOUT_TYPE = {
    "full_bleed_editorial": {"align": "left", "anchor": "top"},
    "split_studio": {"align": "center", "anchor": "center"},
    "printed_moment": {"align": "left", "anchor": "bottom"},
}
MIN_SHORT_SIDE = 800
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
COVER_W, COVER_H = 1275, 1650
THUMB_W = 240
MIN_TITLE_PT = 28
MIN_SUBTITLE_PT = 12
MIN_AUTHOR_PT = 13
# Universal typography — preferred editor sizes are starting points only.
# Wrap more lines to keep subtitle readable; shrink title slightly if needed;
# FAIL rather than emit tiny unclipped text.
TITLE_PX_SCALE = 2.0
SUBTITLE_PX_SCALE = 3.4
AUTHOR_PX_SCALE = 2.05
SERIES_PX_SCALE = 1.85
MIN_TITLE_RENDER_PX = 48
MAX_TITLE_RENDER_PX = 88
MIN_SUBTITLE_RENDER_PX = 44
MAX_SUBTITLE_RENDER_PX = 56
MIN_AUTHOR_RENDER_PX = 28
MAX_AUTHOR_RENDER_PX = 42
MIN_SERIES_RENDER_PX = 22
MAX_SERIES_RENDER_PX = 36
TITLE_LINE_GAP = 12
SUBTITLE_LINE_GAP = 16
SERIES_LINE_GAP = 8
BLOCK_GAP = 32
AUTHOR_GAP = 24
SAFE_MARGIN_X_FRAC = 0.07
SAFE_MARGIN_Y_FRAC = 0.05
MAX_TITLE_LINES = 4
MAX_SUBTITLE_LINES = 6
MAX_SERIES_LINES = 2
MAX_AUTHOR_LINES = 2
SUBJECT_PAD_PX = 20
MIN_SIDE_COLUMN_FRAC = 0.22
THUMB_SCALE = THUMB_W / float(COVER_W)
# Absolute thumbnail floors (px on the 240-wide raster), not a restatement of full-size mins.
MIN_TITLE_THUMB_PX = 9.0
MIN_SUBTITLE_THUMB_PX = 8.0
MIN_AUTHOR_THUMB_PX = 5.2
AI_COVER_ESTIMATE_USD = 0.04
FINDING_MESSAGES = {
    "missing_identity_text": "Title and author are required and cannot be invented.",
    "word_too_wide": "A word is too long to wrap inside the print-safe margins.",
    "text_does_not_fit": "This layout cannot fit the approved text at readable sizes.",
    "text_clipped": "Cover text would be clipped at the edge of the cover.",
    "text_overlap": "Cover text blocks overlap.",
    "outside_safe_margin": "Cover text sits outside the print-safe margins.",
    "identity_text_rewritten": "Cover text does not match the approved wording.",
    "unapproved_label": "Cover contains an unapproved marketing label.",
    "cover_size_mismatch": "Cover is not the required portrait size.",
    "blank_white_area": "Cover still contains a blank white area.",
    "not_full_bleed": "Photograph must fill the portrait cover edge to edge.",
    "title_unreadable_at_thumbnail": "Title is not readable at thumbnail size.",
    "weak_contrast": "Cover text does not have enough contrast against the photograph.",
    "title_too_small": "Title is below the minimum readable size.",
    "author_too_small": "Author is below the minimum readable size.",
    "subtitle_unreadable": "Subtitle is below the minimum readable size.",
    "subtitle_unreadable_at_thumbnail": "Subtitle is not readable at thumbnail size.",
    "author_unreadable_at_thumbnail": "Author is not readable at thumbnail size.",
    "subject_overlap": "Cover text overlaps the photograph's subject.",
    "text_crowded": "Cover text is crowded against the edge of the cover.",
    "insufficient_block_spacing": "Title and subtitle do not have enough breathing room.",
    "insufficient_line_spacing": "Cover text lines are too tightly spaced.",
}
NO_SAFE_COVER_MESSAGE = (
    "This photo does not leave enough room for readable cover text. Please choose another photo."
)
GUIDED_STEP_CHOOSE_PHOTO = "choose_photo"
GUIDED_STEP_CHOOSE_COVER = "choose_cover"
GUIDED_STEP_REVIEW = "review"
GUIDED_STEP_CHOOSE_ANOTHER = "choose_another_photo"
GUIDED_STEP_APPROVED = "approved"
GUIDED_STEPS = (
    GUIDED_STEP_CHOOSE_PHOTO,
    GUIDED_STEP_CHOOSE_COVER,
    GUIDED_STEP_REVIEW,
    GUIDED_STEP_CHOOSE_ANOTHER,
    GUIDED_STEP_APPROVED,
)
GUIDED_STEP_LABELS = {
    GUIDED_STEP_CHOOSE_PHOTO: "Step 1 of 3 — Choose a photo",
    GUIDED_STEP_CHOOSE_COVER: "Step 2 of 3 — Choose a cover",
    GUIDED_STEP_REVIEW: "Step 3 of 3 — Review and approve",
    GUIDED_STEP_CHOOSE_ANOTHER: "Choose another photo",
    GUIDED_STEP_APPROVED: "Cover approved",
}
GUIDED_STEP_NUMBERS = {
    GUIDED_STEP_CHOOSE_PHOTO: 1,
    GUIDED_STEP_CHOOSE_ANOTHER: 1,
    GUIDED_STEP_CHOOSE_COVER: 2,
    GUIDED_STEP_REVIEW: 3,
    GUIDED_STEP_APPROVED: "approved",
}
USER_STATUS = {
    GUIDED_STEP_CHOOSE_PHOTO: "Choose a photo to start your cover.",
    GUIDED_STEP_CHOOSE_COVER: "Choose the cover you like.",
    GUIDED_STEP_REVIEW: "Review this cover. Approval adds this exact cover to the finished PDF.",
    GUIDED_STEP_CHOOSE_ANOTHER: NO_SAFE_COVER_MESSAGE,
    GUIDED_STEP_APPROVED: "This cover is approved. Continue with the next production action.",
}
INCOMPLETE_SELECTION_RECOVERY = "Choose a cover from the options already saved."
MISSING_STEP_RECOVERY = (
    "This cover step could not be shown. Choose another photo, or pick a cover "
    "from the options already saved."
)
RECOVERY_VERSION = 2
MAX_RECOVERY_ATTEMPTS = 12
FORBIDDEN_LABELS = (
    "Event Photography Field Guide",
    "Practical Family Guide",
    "#1 bestseller",
    "as seen on",
    "new york times",
    "guaranteed income",
    "award-winning",
)
_HEX = re.compile(r"^#?[0-9a-fA-F]{6}$")
log = logging.getLogger(__name__)


class PhotoCoverError(ValueError):
    """User-facing cover workflow error."""


def _pkg_dir(data: dict) -> str:
    pkg = str(data.get("package_id") or data.get("artifact_id") or "").strip()
    if not pkg:
        raise PhotoCoverError("Cover image storage requires a package id.")
    path = os.path.join(EXPORTS_DIR, pkg, "cover_photo")
    os.makedirs(path, exist_ok=True)
    return path


def _approved_identity(data: dict) -> dict[str, str]:
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    series = (
        str(data.get("series") or "").strip()
        or str(data.get("series_name") or "").strip()
        or str(data.get("series_title") or "").strip()
        or str(fields.get("series") or "").strip()
    )
    return {
        "title": str(data.get("title") or "").strip(),
        "subtitle": str(data.get("subtitle") or "").strip(),
        "author": str(data.get("author_brand") or data.get("author") or "").strip(),
        "series": series,
    }


def default_editor() -> dict[str, Any]:
    return {
        "zoom": 1.0,
        "focal_x": 0.52,
        "focal_y": 0.42,
        "overlay_strength": 0.58,
        "title_size": 40,
        "subtitle_size": 14,
        "author_size": 16,
        "title_y": 0.07,
        "subtitle_y": 0.26,
        "author_y": 0.915,
        "accent": "#d4a017",
    }


def licensed_catalog() -> list[dict[str, str]]:
    manifest_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "cover_assets",
        "licensed",
        "manifest.json",
    )
    with open(manifest_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return list(raw.get("assets") or [])


def _licensed_asset(asset_id: str) -> dict[str, str]:
    for row in licensed_catalog():
        if str(row.get("id") or "") == str(asset_id):
            return dict(row)
    raise PhotoCoverError("Licensed image not found.")


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    paths = ebook_font_paths()
    path = paths["bold" if bold else "regular"]
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _hex_rgb(value: str) -> tuple[int, int, int]:
    raw = str(value or "#d4a017").strip()
    if not _HEX.match(raw):
        raw = "#d4a017"
    if not raw.startswith("#"):
        raw = "#" + raw
    return int(raw[1:3], 16), int(raw[3:5], 16), int(raw[5:7], 16)


def _clamp_editor(editor: dict | None) -> dict[str, Any]:
    base = default_editor()
    src = dict(editor or {})
    base["zoom"] = min(2.4, max(1.0, float(src.get("zoom") or 1.0)))
    base["focal_x"] = min(0.92, max(0.08, float(src.get("focal_x") or 0.52)))
    base["focal_y"] = min(0.92, max(0.08, float(src.get("focal_y") or 0.42)))
    base["overlay_strength"] = min(0.85, max(0.25, float(src.get("overlay_strength") or 0.58)))
    base["title_size"] = int(min(56, max(MIN_TITLE_PT, float(src.get("title_size") or 40))))
    base["subtitle_size"] = int(min(20, max(MIN_SUBTITLE_PT, float(src.get("subtitle_size") or 14))))
    base["author_size"] = int(min(24, max(MIN_AUTHOR_PT, float(src.get("author_size") or 16))))
    base["title_y"] = min(0.22, max(0.04, float(src.get("title_y") or 0.07)))
    base["subtitle_y"] = min(0.42, max(0.16, float(src.get("subtitle_y") or 0.26)))
    base["author_y"] = min(0.96, max(0.82, float(src.get("author_y") or 0.915)))
    accent = str(src.get("accent") or base["accent"])
    base["accent"] = accent if _HEX.match(accent) else "#d4a017"
    return base


def build_licensed_event_photo(*, width: int = 1800, height: int = 2700) -> Image.Image:
    """Original local licensed event photograph (not a book-cover template)."""
    img = Image.new("RGB", (width, height), (12, 18, 32))
    draw = ImageDraw.Draw(img)
    for y in range(0, height, 6):
        t = y / max(height - 1, 1)
        draw.rectangle(
            (0, y, width, y + 6),
            fill=(int(10 + 28 * t), int(14 + 18 * t), int(28 + 10 * (1 - t))),
        )
    for i in range(18):
        cx = int(width * (0.22 + 0.03 * (i % 5)))
        cy = int(height * 0.78)
        rad = 220 - i * 8
        draw.ellipse(
            (cx - rad, cy - int(rad * 0.35), cx + rad + 420, cy + int(rad * 0.45)),
            fill=(int(70 + i), int(42 + i * 0.6), int(18 + i * 0.3)),
        )
    for x0 in (120, width // 2 - 140, width - 420):
        draw.rounded_rectangle((x0, int(height * 0.18), x0 + 220, int(height * 0.62)), 18, fill=(22, 28, 48))
        draw.rectangle((x0 + 24, int(height * 0.22), x0 + 196, int(height * 0.58)), fill=(38, 48, 78))
    for n in range(42):
        lx = 80 + (n * 41) % (width - 160)
        ly = int(height * (0.16 + 0.012 * (n % 11)))
        rr = 7 + (n % 5) * 3
        draw.ellipse((lx - rr, ly - rr, lx + rr, ly + rr), fill=(252, 210, 96))
        draw.ellipse((lx - rr // 2, ly - rr // 2, lx + rr // 2, ly + rr // 2), fill=(255, 236, 170))
    for n in range(28):
        lx = 140 + (n * 53) % (width - 200)
        ly = int(height * (0.48 + 0.01 * (n % 7)))
        rr = 10 + (n % 4) * 4
        draw.ellipse((lx - rr, ly - rr, lx + rr, ly + rr), fill=(252, 196, 80))
    for sx, sw, sh in ((90, 70, 160), (180, 78, 190), (280, 64, 150), (370, 80, 180), (480, 68, 155)):
        draw.rounded_rectangle((sx, height - sh - 80, sx + sw, height - 70), 22, fill=(8, 8, 12))
    return ImageEnhance.Contrast(img).enhance(1.08)


def ensure_licensed_image(asset_id: str) -> str:
    row = _licensed_asset(asset_id)
    dest_dir = os.path.join(EXPORTS_DIR, "_licensed_cover_assets")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, str(row["filename"]))
    if not os.path.isfile(dest):
        build_licensed_event_photo().save(dest, "PNG")
    return dest


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _sha_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def cover_input_digest(*, source_sha: str, ident: dict[str, str], editor: dict | None) -> str:
    """Stable render-input identity. Cache keys and preview URLs must include this."""
    payload = {
        "source_sha256": str(source_sha or "").strip().lower(),
        "title": str(ident.get("title") or ""),
        "subtitle": str(ident.get("subtitle") or ""),
        "author": str(ident.get("author") or ""),
        "series": str(ident.get("series") or ""),
        "editor": _clamp_editor(editor),
        "layouts": list(LAYOUT_IDS),
        "recovery": RECOVERY_VERSION,
    }
    return _sha_bytes(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def _to_oriented_rgb(img: Image.Image) -> Image.Image:
    """Apply EXIF orientation, then convert to RGB. Never stretches."""
    oriented = ImageOps.exif_transpose(img)
    if oriented is None:
        oriented = img
    if oriented.mode == "RGB":
        return oriented
    return oriented.convert("RGB")


def _open_rgb(path: str) -> Image.Image:
    img = Image.open(path)
    img.load()
    return _to_oriented_rgb(img)


def _open_rgb_bytes(image_bytes: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(image_bytes))
    img.load()
    return _to_oriented_rgb(img)


def _blank_strip(im: Image.Image, box: tuple[int, int, int, int], *, threshold: int = 242, frac: float = 0.992) -> bool:
    band = im.crop(box).convert("RGB")
    data = band.tobytes()
    n = len(data) // 3
    if n <= 0:
        return True
    blank = 0
    for i in range(0, len(data), 3):
        if data[i] >= threshold and data[i + 1] >= threshold and data[i + 2] >= threshold:
            blank += 1
    return (blank / n) >= frac


def _trim_blank_padding(im: Image.Image) -> Image.Image:
    """Remove letterbox/pillarbox white padding. Does not pad, frame, or stretch."""
    w, h = im.size
    if w < 8 or h < 8:
        return im
    scale = 4 if min(w, h) >= 400 else 1
    small = im.resize((max(1, w // scale), max(1, h // scale)), Image.Resampling.BOX)
    sw, sh = small.size

    def blank_row(y: int) -> bool:
        return _blank_strip(small, (0, y, sw, y + 1))

    def blank_col(x: int) -> bool:
        return _blank_strip(small, (x, 0, x + 1, sh))

    top = 0
    while top < sh - 2 and blank_row(top):
        top += 1
    bot = sh
    while bot > top + 2 and blank_row(bot - 1):
        bot -= 1
    left = 0
    while left < sw - 2 and blank_col(left):
        left += 1
    right = sw
    while right > left + 2 and blank_col(right - 1):
        right -= 1
    if top == 0 and left == 0 and bot == sh and right == sw:
        return im
    return im.crop((left * scale, top * scale, min(w, right * scale), min(h, bot * scale)))


def _prepare_photo(im: Image.Image) -> Image.Image:
    rgb = im if im.mode == "RGB" else im.convert("RGB")
    return _trim_blank_padding(rgb)


def _cover_crop(im: Image.Image, editor: dict) -> Image.Image:
    """Aspect-preserving crop-to-fill. Focal point pans the window; never pads or distorts."""
    z = max(1.0, float(editor["zoom"]))
    fx, fy = float(editor["focal_x"]), float(editor["focal_y"])
    dst_aspect = COVER_W / float(COVER_H)
    src_w, src_h = float(im.width), float(im.height)
    if (src_w / max(src_h, 1.0)) > dst_aspect:
        crop_h = src_h / z
        crop_w = crop_h * dst_aspect
    else:
        crop_w = src_w / z
        crop_h = crop_w / dst_aspect
    if crop_w > src_w:
        crop_w = src_w
        crop_h = crop_w / dst_aspect
    if crop_h > src_h:
        crop_h = src_h
        crop_w = crop_h * dst_aspect
    left = fx * src_w - crop_w / 2.0
    top = fy * src_h - crop_h / 2.0
    left = max(0.0, min(src_w - crop_w, left))
    top = max(0.0, min(src_h - crop_h, top))
    i_left = int(round(left))
    i_top = int(round(top))
    i_w = max(1, int(round(crop_w)))
    i_h = max(1, int(round(crop_h)))
    if i_left + i_w > im.width:
        i_left = max(0, im.width - i_w)
    if i_top + i_h > im.height:
        i_top = max(0, im.height - i_h)
    i_w = min(i_w, im.width - i_left)
    i_h = min(i_h, im.height - i_top)
    actual_aspect = i_w / max(i_h, 1)
    if actual_aspect > dst_aspect:
        new_w = max(1, int(round(i_h * dst_aspect)))
        i_left += max(0, (i_w - new_w) // 2)
        i_w = new_w
    elif actual_aspect < dst_aspect:
        new_h = max(1, int(round(i_w / dst_aspect)))
        i_top += max(0, (i_h - new_h) // 2)
        i_h = new_h
    cropped = im.crop((i_left, i_top, i_left + i_w, i_top + i_h))
    return cropped.resize((COVER_W, COVER_H), Image.Resampling.LANCZOS)


def _text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text or "", font=font)
    return max(0, bbox[2] - bbox[0])


def _text_height(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text or "Ag", font=font)
    return max(1, bbox[3] - bbox[1])


def _join_wrapped(lines: list[str]) -> str:
    tokens: list[str] = []
    for line in lines:
        tokens.extend(re.findall(r"\S+", line or ""))
    out = ""
    for token in tokens:
        if not out:
            out = token
        elif out.endswith("-"):
            out += token
        else:
            out += " " + token
    return out


def _glue_tokens(parts: list[str]) -> str:
    out = ""
    for token in parts:
        if not out:
            out = token
        elif out.endswith("-"):
            out += token
        else:
            out += " " + token
    return out


def _wrap_tokens(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str] | None:
    """Split on spaces and existing hyphens. Never splits letters."""
    raw = re.findall(r"\S+", text or "")
    if not raw:
        return []
    words: list[str] = []
    for token in raw:
        if _text_width(draw, token, font) <= max_w:
            words.append(token)
            continue
        if "-" not in token:
            return None
        chunk = ""
        for part in token.split("-"):
            piece = part if not chunk else f"{chunk}-{part}"
            if chunk and _text_width(draw, piece, font) > max_w:
                words.append(chunk + "-")
                chunk = part
            else:
                chunk = piece
        if chunk:
            words.append(chunk)
        if words and _text_width(draw, words[-1], font) > max_w:
            return None
    return words


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str] | None:
    """Word-wrap only. Breaks at spaces or existing hyphens. Never splits letters."""
    words = _wrap_tokens(draw, text, font, max_w)
    if words is None:
        return None
    if not words:
        return [""]
    lines: list[str] = []
    cur: list[str] = []
    for word in words:
        if _text_width(draw, word, font) > max_w:
            return None
        trial = _glue_tokens(cur + [word])
        if cur and _text_width(draw, trial, font) > max_w:
            lines.append(_glue_tokens(cur))
            cur = [word]
        else:
            cur.append(word)
    if cur:
        lines.append(_glue_tokens(cur))
    return lines or [""]


def _wrap_flowing(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    *,
    start_y: int,
    line_gap: int,
    full_w: int,
    side_w: int,
    ceiling_y: int,
    max_lines: int,
) -> list[str] | None:
    """Full width above the subject; continue in the side column beside the face."""
    probe_w = min(full_w, side_w) if side_w else full_w
    words = _wrap_tokens(draw, text, font, probe_w)
    if words is None:
        return None
    if not words:
        return [""]
    lines: list[str] = []
    cur: list[str] = []
    cy = int(start_y)
    lh = max(_text_height(draw, word, font) for word in words) if words else _text_height(draw, "Ag", font)

    def width_for(y: int) -> int:
        return full_w if (y + lh) <= ceiling_y else side_w

    for word in words:
        max_w = width_for(cy)
        if _text_width(draw, word, font) > max_w:
            if cur:
                lines.append(_glue_tokens(cur))
                if len(lines) >= max_lines:
                    return None
                cy += lh + line_gap
                cur = []
                max_w = width_for(cy)
            if _text_width(draw, word, font) > max_w:
                return None
        trial = _glue_tokens(cur + [word])
        if cur and _text_width(draw, trial, font) > max_w:
            lines.append(_glue_tokens(cur))
            if len(lines) >= max_lines:
                return None
            cy += lh + line_gap
            cur = [word]
            max_w = width_for(cy)
            if _text_width(draw, word, font) > max_w:
                return None
        else:
            cur.append(word)
    if cur:
        if len(lines) >= max_lines:
            return None
        lines.append(_glue_tokens(cur))
    if len(lines) > max_lines:
        return None
    return lines or [""]


def _wrap_balanced(
    draw: ImageDraw.ImageDraw,
    text: str,
    font,
    max_w: int,
    *,
    max_lines: int,
    target_lines: int | None = None,
) -> list[str] | None:
    """Wrap to additional balanced lines instead of shrinking into a single strip."""
    words = re.findall(r"\S+", text or "")
    greedy = _wrap(draw, text, font, max_w)
    if greedy is None:
        return None
    if len(words) <= 1:
        return greedy
    if target_lines is None:
        target_lines = min(max_lines, max(len(greedy), (len(words) + 3) // 4))
    target_lines = max(len(greedy), min(int(target_lines), max_lines))
    if target_lines <= len(greedy) or len(greedy) >= max_lines:
        return greedy
    min_col = max(_text_width(draw, word, font) for word in words)
    lo, hi = min_col, max_w
    best = greedy
    while lo <= hi:
        mid = (lo + hi) // 2
        trial = _wrap(draw, text, font, mid)
        if trial is None or len(trial) > max_lines:
            lo = mid + 1
            continue
        if len(trial) < target_lines:
            hi = mid - 1
            continue
        best = trial
        lo = mid + 1
    return best


def _block_size(draw: ImageDraw.ImageDraw, lines: list[str], font, gap: int) -> tuple[int, int]:
    width = 0
    height = 0
    for i, line in enumerate(lines):
        width = max(width, _text_width(draw, line, font))
        height += _text_height(draw, line, font) + (gap if i < len(lines) - 1 else 0)
    return width, height


def _fit_role(
    draw: ImageDraw.ImageDraw,
    text: str,
    *,
    bold: bool,
    start_px: int,
    min_px: int,
    max_px: int,
    max_lines: int,
    max_w: int,
    line_gap: int,
    prefer_wrap: bool = False,
) -> dict[str, Any] | None:
    if not str(text or "").strip():
        return {"lines": [], "font": None, "size": 0, "width": 0, "height": 0, "gap": line_gap}
    size = min(max_px, max(min_px, int(start_px)))
    last_word_fail = False
    while size >= min_px:
        font = _font(size, bold=bold)
        if prefer_wrap:
            lines = _wrap_balanced(draw, text, font, max_w, max_lines=max_lines)
        else:
            lines = _wrap(draw, text, font, max_w)
        if lines is None:
            last_word_fail = True
            size -= 2
            continue
        last_word_fail = False
        if len(lines) > max_lines:
            size -= 2
            continue
        width, height = _block_size(draw, lines, font, line_gap)
        return {
            "lines": lines,
            "font": font,
            "size": size,
            "width": width,
            "height": height,
            "gap": line_gap,
        }
    return {"error": "word_too_wide" if last_word_fail else "text_does_not_fit"}


def detect_subject_region(img: Image.Image, editor: dict | None = None) -> dict[str, Any] | None:
    """Compact face / primary focal-object box. Not the full body.

    Uses sharp (high local-variance) pixels so blurred background bokeh is ignored.
    Text may sit on uncluttered clothing or background if it stays readable.
    Never uses project-specific coordinates.
    """
    w, h = img.size
    if w < 32 or h < 32:
        return None
    grid_w, grid_h = 48, 64
    small = img.resize((grid_w, grid_h), Image.Resampling.BOX).convert("RGB")
    pix = small.load()
    luma = [[_luma(*pix[x, y][:3]) for x in range(grid_w)] for y in range(grid_h)]
    var = [[0.0] * grid_w for _ in range(grid_h)]
    for y in range(1, grid_h - 1):
        for x in range(1, grid_w - 1):
            cells = [luma[y + dy][x + dx] for dy in (-1, 0, 1) for dx in (-1, 0, 1)]
            mean = sum(cells) / 9.0
            var[y][x] = sum((v - mean) ** 2 for v in cells) / 9.0
    values = [var[y][x] for y in range(grid_h) for x in range(grid_w)]
    values.sort()
    med = values[len(values) // 2]
    thr = med * 2.6 + 22
    fx = float((editor or {}).get("focal_x") or 0.52)
    fy = float((editor or {}).get("focal_y") or 0.42)
    cx = min(grid_w - 1, max(0, int(round(fx * (grid_w - 1)))))
    cy = min(grid_h - 1, max(0, int(round(fy * (grid_h - 1)))))

    def is_skin(r: int, g: int, b: int) -> bool:
        if r < 90 or g < 35 or b < 15:
            return False
        if not (r > g and (r - g) >= 12 and (r - g) >= (g - b) - 8):
            return False
        yv = 0.299 * r + 0.587 * g + 0.114 * b
        cb = 128 - 0.168736 * r - 0.331264 * g + 0.5 * b
        cr = 128 + 0.5 * r - 0.418688 * g - 0.081312 * b
        return 55 <= yv <= 230 and 77 <= cb <= 127 and 133 <= cr <= 173

    peak = None
    peak_score = -1.0
    sharp: list[tuple[int, int]] = []
    for y in range(grid_h):
        for x in range(grid_w):
            if var[y][x] < thr:
                continue
            dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
            score = float(var[y][x]) / (1.0 + dist * 0.35)
            sharp.append((x, y))
            if score > peak_score:
                peak_score = score
                peak = (x, y)
    if peak is None or len(sharp) < 6:
        return None
    px, py = peak
    cluster_r = 9
    cluster = [
        (x, y) for x, y in sharp if ((x - px) ** 2 + (y - py) ** 2) ** 0.5 <= cluster_r
    ]
    if len(cluster) < 6:
        cluster = list(sharp)
    gw = max(c[0] for c in cluster) - min(c[0] for c in cluster) + 1
    gh = max(c[1] for c in cluster) - min(c[1] for c in cluster) + 1
    fill = len(cluster) / float(max(gw * gh, 1))
    if fill < 0.18:
        return None
    if gw > grid_w * 0.72 and gh < grid_h * 0.28:
        return None
    skin_cells = []
    dark_cells = []
    bright_n = 0
    for x, y in cluster:
        r, g, b = pix[x, y]
        lu = _luma(r, g, b)
        if lu > 180:
            bright_n += 1
        if is_skin(r, g, b):
            skin_cells.append((x, y))
        if lu < 92:
            dark_cells.append((x, y))
    if bright_n / float(max(len(cluster), 1)) > 0.22:
        return None
    if len(skin_cells) < 6 and len(dark_cells) < 10:
        return None
    face_cells = skin_cells if len(skin_cells) >= 6 else cluster

    def _bbox(cells: list[tuple[int, int]], *, grow: int = 8) -> tuple[int, int, int, int]:
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        x0 = max(0, int(min(xs) * w / grid_w) - grow)
        y0 = max(0, int(min(ys) * h / grid_h) - grow)
        x1 = min(w, int((max(xs) + 1) * w / grid_w) + grow)
        y1 = min(h, int((max(ys) + 1) * h / grid_h) + grow)
        return x0, y0, x1, y1

    def _clamp_box(box: tuple[int, int, int, int], max_w_frac: float, max_h_frac: float) -> tuple[int, int, int, int]:
        x0, y0, x1, y1 = box
        bw, bh = x1 - x0, y1 - y0
        max_w = int(w * max_w_frac)
        max_h = int(h * max_h_frac)
        if bw > max_w:
            mid = (x0 + x1) // 2
            x0 = max(0, mid - max_w // 2)
            x1 = min(w, x0 + max_w)
        if bh > max_h:
            mid = (y0 + y1) // 2
            y0 = max(0, mid - max_h // 2)
            y1 = min(h, y0 + max_h)
        return x0, y0, x1, y1

    face_box = _clamp_box(_bbox(face_cells, grow=10), 0.42, 0.38)
    focal_box = _clamp_box(_bbox(cluster, grow=12), 0.50, 0.48)
    bw = (focal_box[2] - focal_box[0]) / float(w)
    bh = (focal_box[3] - focal_box[1]) / float(h)
    if bw < 0.06 or bh < 0.06:
        return None
    return {"box": focal_box, "face_box": face_box, "focal_box": focal_box}


def _norm_ws(text: str) -> str:
    return " ".join(re.findall(r"\S+", text or ""))


def _boxes_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int], pad: int = 4) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 + pad <= bx0 or bx1 + pad <= ax0 or ay1 + pad <= by0 or by1 + pad <= ay0)


def _protected_boxes(subject: dict[str, Any] | None) -> list[tuple[int, int, int, int]]:
    """Face and compact focal object only — not the full body."""
    if not subject:
        return []
    boxes: list[tuple[int, int, int, int]] = []
    for key in ("face_box", "focal_box"):
        box = subject.get(key)
        if box and len(box) == 4:
            boxes.append(tuple(int(v) for v in box))
    if not boxes and subject.get("box"):
        boxes.append(tuple(int(v) for v in subject["box"]))
    # De-dupe identical boxes.
    uniq: list[tuple[int, int, int, int]] = []
    for box in boxes:
        if box not in uniq:
            uniq.append(box)
    return uniq


def _block_hit_boxes(block: dict[str, Any]) -> list[tuple[int, int, int, int]]:
    boxes = block.get("line_boxes") or []
    if boxes:
        return [tuple(b) for b in boxes]
    box = block.get("box")
    return [tuple(box)] if box else []


def _region_luma(img: Image.Image, box: tuple[int, int, int, int]) -> float:
    x0, y0, x1, y1 = box
    x0 = max(0, min(img.width - 1, x0))
    y0 = max(0, min(img.height - 1, y0))
    x1 = max(x0 + 1, min(img.width, x1))
    y1 = max(y0 + 1, min(img.height, y1))
    sample = img.crop((x0, y0, x1, y1)).resize((24, 24), Image.Resampling.BOX)
    pix = sample.load()
    total = 0.0
    n = 24 * 24
    for y in range(24):
        for x in range(24):
            r, g, b = pix[x, y][:3]
            total += _luma(r, g, b)
    return total / max(n, 1)


def _contrast_fills(img: Image.Image, box: tuple[int, int, int, int]) -> dict[str, tuple[int, int, int]]:
    lu = _region_luma(img, box)
    if lu >= 150:
        return {
            "title": (18, 16, 14),
            "subtitle": (36, 32, 28),
            "series": (42, 38, 34),
            "author": (22, 20, 18),
            "shadow": (255, 255, 255),
        }
    return {
        "title": (255, 255, 255),
        "subtitle": (236, 230, 214),
        "series": (228, 220, 200),
        "author": (252, 248, 240),
        "shadow": (8, 10, 16),
    }


def _draw_text_block(draw, lines, font, x, y, fill, *, shadow=True, shadow_fill=(8, 10, 16), line_gap=8, align="left", box_x=0, box_w=0) -> int:
    cy = y
    for line in lines:
        lw = _text_width(draw, line, font)
        lh = _text_height(draw, line, font)
        if align == "center" and box_w:
            lx = box_x + max(0, (box_w - lw) // 2)
        else:
            lx = x
        if shadow:
            draw.text((lx + 2, cy + 2), line, font=font, fill=shadow_fill)
        draw.text((lx, cy), line, font=font, fill=fill)
        cy += lh + line_gap
    return cy


def _edge_scrim(img: Image.Image, strength: float, *, side: str, height_frac: float) -> None:
    h = max(1, int(img.height * height_frac))
    a_max = int(190 * strength)
    grad = Image.new("L", (1, h))
    for y in range(h):
        t = y / max(h - 1, 1)
        alpha = int(a_max * (1 - t)) if side == "top" else int(a_max * t)
        grad.putpixel((0, y), alpha)
    alpha_img = grad.resize((img.width, h), Image.Resampling.BILINEAR)
    band = Image.new("RGBA", (img.width, h), (8, 12, 22, 0))
    band.putalpha(alpha_img)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay.paste(band, (0, 0 if side == "top" else img.height - h))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))


def _readability_overlay(
    img: Image.Image,
    strength: float,
    *,
    layout_id: str = "",
    text_bottom_frac: float | None = None,
) -> None:
    """Subtle adaptive veil + edge scrim. Never a panel, frame, or decoration."""
    mean = _region_luma(img, (0, 0, img.width, img.height))
    adj = float(strength)
    if mean > 165:
        adj = min(0.85, adj + 0.10)
    elif mean < 55:
        adj = max(0.25, adj - 0.08)
    veil_a = int(34 * adj)
    if veil_a > 0:
        veil = Image.new("RGBA", img.size, (8, 12, 22, veil_a))
        img.paste(Image.alpha_composite(img.convert("RGBA"), veil).convert("RGB"))
    spec = LAYOUT_TYPE.get(layout_id) or LAYOUT_TYPE["full_bleed_editorial"]
    anchor = spec["anchor"]
    if anchor == "top":
        top_frac = 0.42
        if text_bottom_frac is not None:
            top_frac = min(0.58, max(0.42, float(text_bottom_frac) + 0.08))
        _edge_scrim(img, adj, side="top", height_frac=top_frac)
        _edge_scrim(img, adj * 0.72, side="bottom", height_frac=0.24)
    elif anchor == "center":
        _edge_scrim(img, adj * 0.70, side="top", height_frac=0.26)
        _edge_scrim(img, adj * 0.78, side="bottom", height_frac=0.28)
    else:
        _edge_scrim(img, adj * 0.55, side="top", height_frac=0.18)
        _edge_scrim(img, adj, side="bottom", height_frac=0.44)


def _preferred_px(editor: dict) -> dict[str, int]:
    return {
        "title": int(float(editor.get("title_size") or 40) * TITLE_PX_SCALE),
        "subtitle": int(float(editor.get("subtitle_size") or 14) * SUBTITLE_PX_SCALE),
        "author": int(float(editor.get("author_size") or 16) * AUTHOR_PX_SCALE),
        "series": int(float(editor.get("author_size") or 16) * SERIES_PX_SCALE),
    }


def plan_typography(
    ident: dict[str, str],
    editor: dict,
    layout_id: str,
    img: Image.Image | None = None,
    subject: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Measure and fit approved text. Never rewrites, abbreviates, or invents copy.

    Typography priority: wrap more subtitle lines at a readable size; shrink the
    title slightly if needed; FAIL rather than emit tiny unclipped subtitle.
    """
    title = str(ident.get("title") or "").strip()
    subtitle = str(ident.get("subtitle") or "").strip()
    author = str(ident.get("author") or "").strip()
    series = str(ident.get("series") or "").strip()
    if not title or not author:
        return {"pass": False, "findings": ["missing_identity_text"], "blocks": []}
    spec = LAYOUT_TYPE.get(layout_id) or LAYOUT_TYPE["full_bleed_editorial"]
    align = spec["align"]
    anchor = spec["anchor"]
    margin_x = int(COVER_W * SAFE_MARGIN_X_FRAC)
    margin_y = int(COVER_H * SAFE_MARGIN_Y_FRAC)
    full_w = COVER_W - (2 * margin_x)
    probe = Image.new("RGB", (COVER_W, COVER_H), (20, 20, 24))
    draw = ImageDraw.Draw(probe)
    pref = _preferred_px(editor)
    if subject is None and img is not None:
        subject = detect_subject_region(img, editor)

    columns: list[tuple[int, int]] = [(margin_x, full_w)]
    flow_side: tuple[int, int, int] | None = None
    prot_boxes = _protected_boxes(subject)
    if subject and prot_boxes:
        face = subject.get("face_box") or subject.get("focal_box") or subject.get("box")
        fx0, fy0, fx1, _fy1 = face
        pad = SUBJECT_PAD_PX
        left_w = int(fx0) - pad - margin_x
        right_x = int(fx1) + pad
        right_w = COVER_W - margin_x - right_x
        min_side = int(COVER_W * MIN_SIDE_COLUMN_FRAC)
        if left_w >= min_side or right_w >= min_side:
            if left_w >= right_w:
                flow_side = (margin_x, int(left_w), int(fy0) - pad)
            else:
                flow_side = (int(right_x), int(right_w), int(fy0) - pad)
        focal = subject.get("focal_box") or face
        px0, _py0, px1, _py1 = focal
        left_col_w = int(px0) - pad - margin_x
        right_col_x = int(px1) + pad
        right_col_w = COVER_W - margin_x - right_col_x
        if left_col_w >= min_side:
            columns.append((margin_x, int(left_col_w)))
        if right_col_w >= min_side:
            columns.append((int(right_col_x), int(right_col_w)))

    def plan_column(col_x: int, col_w: int) -> dict[str, Any]:
        findings: list[str] = []

        def fit(text, *, bold, start, min_px, max_px, max_lines, gap, prefer_wrap=False, max_w=None):
            return _fit_role(
                draw,
                text,
                bold=bold,
                start_px=start,
                min_px=min_px,
                max_px=max_px,
                max_lines=max_lines,
                max_w=col_w if max_w is None else int(max_w),
                line_gap=gap,
                prefer_wrap=prefer_wrap,
            )

        title_x, title_w = col_x, col_w
        use_flow = bool(flow_side) and anchor == "top" and col_w >= full_w
        if use_flow:
            title_x, title_w = margin_x, full_w

        roles = [
            ("title", title, True, pref["title"], MIN_TITLE_RENDER_PX, MAX_TITLE_RENDER_PX, MAX_TITLE_LINES, TITLE_LINE_GAP, False),
            ("subtitle", subtitle, False, pref["subtitle"], MIN_SUBTITLE_RENDER_PX, MAX_SUBTITLE_RENDER_PX, MAX_SUBTITLE_LINES, SUBTITLE_LINE_GAP, True),
            ("series", series, False, pref["series"], MIN_SERIES_RENDER_PX, MAX_SERIES_RENDER_PX, MAX_SERIES_LINES, SERIES_LINE_GAP, False),
            ("author", author, True, pref["author"], MIN_AUTHOR_RENDER_PX, MAX_AUTHOR_RENDER_PX, MAX_AUTHOR_LINES, 6, False),
        ]
        fitted: dict[str, dict[str, Any]] = {}
        for role, text, bold, start, min_px, max_px, max_lines, gap, prefer_wrap in roles:
            if not text:
                fitted[role] = {"lines": [], "font": None, "size": 0, "width": 0, "height": 0, "gap": gap}
                continue
            row = fit(
                text,
                bold=bold,
                start=start,
                min_px=min_px,
                max_px=max_px,
                max_lines=max_lines,
                gap=gap,
                prefer_wrap=prefer_wrap,
                max_w=title_w if role == "title" else col_w,
            )
            if not row or row.get("error"):
                findings.append(str((row or {}).get("error") or "text_does_not_fit"))
                return {"pass": False, "findings": findings, "blocks": []}
            if _norm_ws(_join_wrapped(row["lines"])) != _norm_ws(text):
                return {"pass": False, "findings": ["identity_text_rewritten"], "blocks": []}
            fitted[role] = row

        if use_flow and subtitle:
            side_x, side_w, ceiling_y = flow_side
            sub_size = min(MAX_SUBTITLE_RENDER_PX, max(MIN_SUBTITLE_RENDER_PX, pref["subtitle"]))
            sub_lh = _text_height(draw, "Ag", _font(sub_size, bold=False))
            room = 2 * sub_lh + SUBTITLE_LINE_GAP
            target_title_h = max(0, ceiling_y - margin_y - BLOCK_GAP - room)
            tsize = int(fitted["title"]["size"])
            while int(fitted["title"]["height"]) > target_title_h and tsize > MIN_TITLE_RENDER_PX:
                tsize -= 2
                row = fit(
                    title,
                    bold=True,
                    start=tsize,
                    min_px=MIN_TITLE_RENDER_PX,
                    max_px=tsize,
                    max_lines=MAX_TITLE_LINES,
                    gap=TITLE_LINE_GAP,
                    max_w=title_w,
                )
                if not row or row.get("error"):
                    break
                fitted["title"] = row
            start_y = margin_y + int(fitted["title"]["height"]) + BLOCK_GAP
            flowed = None
            size = sub_size
            while size >= MIN_SUBTITLE_RENDER_PX:
                font = _font(size, bold=False)
                lines = _wrap_flowing(
                    draw,
                    subtitle,
                    font,
                    start_y=start_y,
                    line_gap=SUBTITLE_LINE_GAP,
                    full_w=full_w,
                    side_w=side_w,
                    ceiling_y=ceiling_y,
                    max_lines=MAX_SUBTITLE_LINES,
                )
                if lines is None or _norm_ws(_join_wrapped(lines)) != _norm_ws(subtitle):
                    size -= 2
                    continue
                width, height = _block_size(draw, lines, font, SUBTITLE_LINE_GAP)
                flowed = {
                    "lines": lines,
                    "font": font,
                    "size": size,
                    "width": width,
                    "height": height,
                    "gap": SUBTITLE_LINE_GAP,
                    "flow_x": side_x,
                    "flow_ceiling": ceiling_y,
                }
                break
            if not flowed:
                return {"pass": False, "findings": ["subtitle_unreadable"], "blocks": []}
            fitted["subtitle"] = flowed

        # Shrink title first if the stack cannot fit. Never shrink subtitle below min.
        shrink_order = ["title", "series", "author"]

        def stack_height(include_author: bool) -> int:
            parts = ["title", "subtitle", "series"] + (["author"] if include_author else [])
            live = [fitted[r]["height"] for r in parts if fitted[r]["height"]]
            if not live:
                return 0
            return int(sum(live) + BLOCK_GAP * (len(live) - 1))

        include_author_in_stack = anchor == "bottom"
        available = COVER_H - (2 * margin_y)
        if not include_author_in_stack:
            available = COVER_H - (2 * margin_y) - fitted["author"]["height"] - AUTHOR_GAP

        def shrink_to_fit() -> bool:
            for role in shrink_order:
                if include_author_in_stack is False and role == "author":
                    continue
                text = {"title": title, "subtitle": subtitle, "series": series, "author": author}[role]
                if not text:
                    continue
                spec_row = next(r for r in roles if r[0] == role)
                _role, _text, bold, start, min_px, max_px, max_lines, gap, prefer_wrap = spec_row
                size = int(fitted[role]["size"])
                while stack_height(include_author_in_stack) > available and size > min_px:
                    size -= 2
                    row = fit(
                        text,
                        bold=bold,
                        start=size,
                        min_px=min_px,
                        max_px=size,
                        max_lines=max_lines,
                        gap=gap,
                        prefer_wrap=prefer_wrap,
                        max_w=title_w if role == "title" else col_w,
                    )
                    if not row or row.get("error"):
                        break
                    fitted[role] = row
                if stack_height(include_author_in_stack) <= available:
                    return True
            return stack_height(include_author_in_stack) <= available

        if stack_height(include_author_in_stack) > available and not shrink_to_fit():
            return {"pass": False, "findings": ["text_does_not_fit"], "blocks": []}

        body_h = stack_height(False)
        author_h = fitted["author"]["height"]
        if include_author_in_stack:
            total_h = stack_height(True)
            y0 = COVER_H - margin_y - total_h
            y0 = max(margin_y, y0)
        elif anchor == "top":
            y0 = margin_y
        else:
            y0 = int((COVER_H - author_h - AUTHOR_GAP - body_h) / 2)
            y0 = max(margin_y, min(y0, COVER_H - margin_y - author_h - AUTHOR_GAP - body_h))

        fills = _contrast_fills(
            img or probe,
            (col_x, y0, col_x + col_w, min(COVER_H - margin_y, y0 + body_h + author_h + AUTHOR_GAP)),
        )
        blocks: list[dict[str, Any]] = []
        cy = y0

        def _append_block(role: str, row: dict[str, Any], bx: int, by: int, fill) -> int:
            font = row["font"]
            lines = list(row["lines"] or [])
            gap = int(row.get("gap") or 0)
            line_boxes: list[tuple[int, int, int, int]] = []
            ly = by
            ceiling = int(row["flow_ceiling"]) if role == "subtitle" and row.get("flow_ceiling") is not None else COVER_H
            side_x = int(row.get("flow_x") or bx)
            for i, line in enumerate(lines):
                lw = _text_width(draw, line, font) if font else 0
                lh = _text_height(draw, line, font) if font else 0
                lx = side_x if (role == "subtitle" and row.get("flow_ceiling") is not None and (ly + lh) > ceiling) else bx
                line_boxes.append((lx, ly, lx + lw, ly + lh))
                ly += lh + (gap if i < len(lines) - 1 else 0)
            if line_boxes:
                union = (
                    min(b[0] for b in line_boxes),
                    min(b[1] for b in line_boxes),
                    max(b[2] for b in line_boxes),
                    max(b[3] for b in line_boxes),
                )
            else:
                union = (bx, by, bx + int(row["width"]), by + int(row["height"]))
            blocks.append(
                {
                    "role": role,
                    "lines": lines,
                    "font": font,
                    "size": row["size"],
                    "x": union[0],
                    "y": union[1],
                    "w": union[2] - union[0],
                    "h": union[3] - union[1],
                    "gap": gap,
                    "box": union,
                    "line_boxes": line_boxes,
                    "fill": fill,
                }
            )
            return union[3]

        for role in ("title", "subtitle", "series"):
            row = fitted[role]
            if not row["height"]:
                continue
            bx = title_x if role == "title" else (int(row["flow_x"]) if row.get("flow_x") is not None else col_x)
            if role == "subtitle" and row.get("flow_ceiling") is not None:
                bx = margin_x
            bottom = _append_block(role, row, bx, cy, fills[role])
            cy = bottom + BLOCK_GAP
        author_x = margin_x if anchor == "top" else col_x
        if include_author_in_stack:
            auth_y = cy
            author_x = col_x
        else:
            auth_y = COVER_H - margin_y - author_h
            auth_y = min(auth_y, COVER_H - margin_y - author_h)
            auth_y = max(auth_y, cy + AUTHOR_GAP)
        row = fitted["author"]
        _append_block("author", row, author_x, auth_y, fills["author"])

        by_role = {b["role"]: b for b in blocks}
        if "title" in by_role and "subtitle" in by_role:
            gap = by_role["subtitle"]["y"] - (by_role["title"]["y"] + by_role["title"]["h"])
            if gap < BLOCK_GAP - 2:
                findings.append("insufficient_block_spacing")
        for block in blocks:
            if block["role"] in {"title", "subtitle", "series"} and len(block["lines"]) > 1:
                if int(block.get("gap") or 0) < (SUBTITLE_LINE_GAP if block["role"] == "subtitle" else TITLE_LINE_GAP) - 2:
                    findings.append("insufficient_line_spacing")
            for x0, y0b, x1, y1b in _block_hit_boxes(block):
                if x0 < margin_x - 1 or y0b < margin_y - 1 or x1 > COVER_W - margin_x + 1 or y1b > COVER_H - margin_y + 1:
                    findings.append("outside_safe_margin")
                if x0 < 0 or y0b < 0 or x1 > COVER_W or y1b > COVER_H:
                    findings.append("text_clipped")
        if anchor == "bottom":
            lowest = max(b["box"][3] for b in blocks)
            if lowest > COVER_H - margin_y + 1:
                findings.append("text_clipped")
        for i, a in enumerate(blocks):
            for b in blocks[i + 1 :]:
                if any(
                    _boxes_overlap(ha, hb)
                    for ha in _block_hit_boxes(a)
                    for hb in _block_hit_boxes(b)
                ):
                    findings.append("text_overlap")
        if fitted["title"]["size"] < MIN_TITLE_RENDER_PX:
            findings.append("title_too_small")
        if fitted["author"]["size"] < MIN_AUTHOR_RENDER_PX:
            findings.append("author_too_small")
        if subtitle and fitted["subtitle"]["size"] < MIN_SUBTITLE_RENDER_PX:
            findings.append("subtitle_unreadable")
        if subject:
            protected = _protected_boxes(subject)
            for block in blocks:
                if block["role"] == "author" and anchor != "bottom":
                    continue
                if any(
                    _boxes_overlap(hit, prot, pad=8)
                    for hit in _block_hit_boxes(block)
                    for prot in protected
                ):
                    findings.append("subject_overlap")
                    break
        findings = list(dict.fromkeys(findings))
        return {
            "pass": not findings,
            "findings": findings,
            "blocks": blocks,
            "align": align,
            "margin_x": col_x,
            "max_w": col_w,
            "fills": fills,
            "sizes": {role: fitted[role]["size"] for role in fitted},
            "subject": bool(subject),
        }

    best_fail: dict[str, Any] | None = None
    for col_x, col_w in columns:
        result = plan_column(col_x, col_w)
        if result.get("pass"):
            return result
        if best_fail is None or (
            "subject_overlap" in (best_fail.get("findings") or [])
            and "subject_overlap" not in (result.get("findings") or [])
        ):
            best_fail = result
    return best_fail or {"pass": False, "findings": ["text_does_not_fit"], "blocks": []}


def _paint_plan(img: Image.Image, plan: dict[str, Any]) -> None:
    if not plan.get("pass"):
        return
    draw = ImageDraw.Draw(img)
    align = plan.get("align") or "left"
    box_x = int(plan.get("margin_x") or 0)
    box_w = int(plan.get("max_w") or 0)
    shadow_fill = (plan.get("fills") or {}).get("shadow") or (8, 10, 16)
    for block in plan.get("blocks") or []:
        line_boxes = block.get("line_boxes") or []
        if line_boxes and block.get("font") is not None:
            for line, box in zip(block.get("lines") or [], line_boxes):
                lx, ly = int(box[0]), int(box[1])
                if align == "center" and box_w:
                    lw = _text_width(draw, line, block["font"])
                    lx = box_x + max(0, (box_w - lw) // 2)
                if shadow_fill:
                    draw.text((lx + 2, ly + 2), line, font=block["font"], fill=shadow_fill)
                draw.text((lx, ly), line, font=block["font"], fill=block["fill"])
            continue
        _draw_text_block(
            draw,
            block["lines"],
            block["font"],
            block["x"],
            block["y"],
            block["fill"],
            shadow=True,
            shadow_fill=shadow_fill,
            line_gap=int(block.get("gap") or 8),
            align=align,
            box_x=box_x,
            box_w=box_w,
        )


def render_layout_with_qa(
    photo: Image.Image, layout_id: str, ident: dict[str, str], editor: dict
) -> tuple[Image.Image, dict[str, Any]]:
    cropped = _cover_crop(_prepare_photo(photo), editor)
    subject = detect_subject_region(cropped, editor)
    plan = plan_typography(ident, editor, layout_id, cropped, subject=subject)
    img = cropped
    text_bottom = 0.0
    if plan.get("blocks"):
        body = [b for b in plan["blocks"] if b.get("role") != "author"]
        if body:
            text_bottom = max(b["y"] + b["h"] for b in body) / float(COVER_H)
    _readability_overlay(
        img,
        float(editor["overlay_strength"]),
        layout_id=layout_id,
        text_bottom_frac=text_bottom or None,
    )
    plan = plan_typography(ident, editor, layout_id, img, subject=subject)
    if plan.get("pass"):
        _paint_plan(img, plan)
    qa = inspect_variant(img, layout_id, ident, plan=plan, subject=subject)
    return img, qa


def render_layout(photo: Image.Image, layout_id: str, ident: dict[str, str], editor: dict) -> Image.Image:
    img, _qa = render_layout_with_qa(photo, layout_id, ident, editor)
    return img


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _pdf_from_png(png: bytes, *, title: str, author: str, subtitle: str = "", series: str = "") -> bytes:
    buf = io.BytesIO()
    W, H = letter
    c = rl_canvas.Canvas(buf, pagesize=letter)
    c.setTitle(title)
    c.setAuthor(author)
    c.setSubject(subtitle)
    c.drawImage(ImageReader(io.BytesIO(png)), 0, 0, width=W, height=H, preserveAspectRatio=False, mask="auto")
    # Invisible text layer so identity can be verified without OCR.
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Times-Roman", 8)
    c._code.append("3 Tr")
    c.drawString(36, 60, title or "")
    c.drawString(36, 48, subtitle or "")
    c.drawString(36, 36, series or "")
    c.drawString(36, 24, author or "")
    c._code.append("0 Tr")
    c.showPage()
    c.save()
    return buf.getvalue()


def _thumb(img: Image.Image) -> Image.Image:
    h = int(THUMB_W * COVER_H / COVER_W)
    return img.resize((THUMB_W, h), Image.Resampling.LANCZOS)


def _luma(r: int, g: int, b: int) -> float:
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def inspect_variant(
    img: Image.Image,
    layout_id: str,
    ident: dict[str, str],
    plan: dict[str, Any] | None = None,
    subject: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Raster typography QA. Fitting without clipping is not a pass."""
    findings: list[str] = []
    if plan:
        findings.extend(list(plan.get("findings") or []))
    blob = f"{ident.get('title') or ''}\n{ident.get('subtitle') or ''}\n{ident.get('author') or ''}\n{ident.get('series') or ''}"
    for label in FORBIDDEN_LABELS:
        if label.lower() in blob.lower():
            findings.append("unapproved_label")
    if not str(ident.get("title") or "").strip() or not str(ident.get("author") or "").strip():
        findings.append("missing_identity_text")
    if img.size != (COVER_W, COVER_H):
        findings.append("cover_size_mismatch")
    sizes = dict((plan or {}).get("sizes") or {})
    if plan:
        for block in plan.get("blocks") or []:
            sizes[str(block.get("role") or "")] = int(block.get("size") or sizes.get(block.get("role") or "") or 0)
        title_px = int(sizes.get("title") or 0)
        sub_px = int(sizes.get("subtitle") or 0)
        auth_px = int(sizes.get("author") or 0)
        if title_px and title_px < MIN_TITLE_RENDER_PX:
            findings.append("title_too_small")
        if str(ident.get("subtitle") or "").strip() and sub_px < MIN_SUBTITLE_RENDER_PX:
            findings.append("subtitle_unreadable")
        if auth_px and auth_px < MIN_AUTHOR_RENDER_PX:
            findings.append("author_too_small")
        probe = ImageDraw.Draw(img)
        for block in plan.get("blocks") or []:
            role = str(block.get("role") or "")
            size = int(block.get("size") or 0)
            if not size or not block.get("lines"):
                continue
            font = _font(size, bold=role in {"title", "author"})
            for line in block.get("lines") or []:
                measured = _text_height(probe, line, font)
                if measured < size * 0.55:
                    findings.append("title_too_small" if role == "title" else "subtitle_unreadable" if role == "subtitle" else "author_too_small")
                    break
        if title_px and (title_px * THUMB_SCALE) < MIN_TITLE_THUMB_PX - 0.05:
            findings.append("title_unreadable_at_thumbnail")
        if str(ident.get("subtitle") or "").strip() and sub_px and (sub_px * THUMB_SCALE) < MIN_SUBTITLE_THUMB_PX - 0.05:
            findings.append("subtitle_unreadable_at_thumbnail")
        if auth_px and (auth_px * THUMB_SCALE) < MIN_AUTHOR_THUMB_PX - 0.05:
            findings.append("author_unreadable_at_thumbnail")
        by_role = {b.get("role"): b for b in (plan.get("blocks") or [])}
        if "title" in by_role and "subtitle" in by_role:
            gap = by_role["subtitle"]["y"] - (by_role["title"]["y"] + by_role["title"]["h"])
            if gap < BLOCK_GAP - 2:
                findings.append("insufficient_block_spacing")
        if subject:
            protected = _protected_boxes(subject)
            spec = LAYOUT_TYPE.get(layout_id) or LAYOUT_TYPE["full_bleed_editorial"]
            for block in plan.get("blocks") or []:
                if block.get("role") == "author" and spec["anchor"] != "bottom":
                    continue
                if any(
                    _boxes_overlap(hit, prot, pad=8)
                    for hit in _block_hit_boxes(block)
                    for prot in protected
                ):
                    findings.append("subject_overlap")
                    break
    findings = list(dict.fromkeys(findings))
    if plan is not None and (not plan.get("pass") or findings):
        return {
            "findings": findings,
            "pass": False,
            "messages": [FINDING_MESSAGES.get(code, code) for code in findings],
            "thumbnail": {"width": 0, "height": 0, "bright_top": 0, "white": 0, "edge_white": 0},
            "plan_sizes": sizes,
        }
    thumb = _thumb(img)
    tw, th = thumb.size
    small = img.resize((318, 412), Image.Resampling.LANCZOS)
    sw, sh = small.size
    pix = small.load()
    white = 0
    edge_white = 0
    edge_n = 0
    bright_title = 0
    dark_near_title = 0
    bands = {
        "full_bleed_editorial": (0.04, 0.32),
        "split_studio": (0.28, 0.64),
        "printed_moment": (0.48, 0.96),
    }
    y0f, y1f = bands.get(layout_id, (0.04, 0.32))
    y0, y1 = int(sh * y0f), int(sh * y1f)
    title_block = None
    if plan:
        title_block = next((b for b in (plan.get("blocks") or []) if b.get("role") == "title"), None)
    if title_block:
        y0 = max(0, int(sh * (title_block["y"] / COVER_H)) - 2)
        y1 = min(sh, int(sh * ((title_block["y"] + title_block["h"]) / COVER_H)) + 4)
    margin = max(2, int(min(sw, sh) * 0.03))
    total = sw * sh
    for y in range(sh):
        for x in range(sw):
            r, g, b = pix[x, y]
            lu = _luma(r, g, b)
            is_white = r > 242 and g > 242 and b > 238
            if is_white:
                white += 1
            on_edge = x < margin or y < margin or x >= sw - margin or y >= sh - margin
            if on_edge:
                edge_n += 1
                if is_white:
                    edge_white += 1
            if y0 <= y < y1:
                if lu > 190:
                    bright_title += 1
                if lu < 90:
                    dark_near_title += 1
    if total and (white / total) > 0.06:
        findings.append("blank_white_area")
    if edge_n and (edge_white / edge_n) > 0.22:
        findings.append("not_full_bleed")
    for cx, cy in ((1, 1), (sw - 2, 1), (1, sh - 2), (sw - 2, sh - 2)):
        r, g, b = pix[cx, cy]
        if r > 242 and g > 242 and b > 238:
            findings.append("blank_white_area")
            break
    title_fill = None
    if plan:
        for block in plan.get("blocks") or []:
            if block.get("role") == "title":
                title_fill = block.get("fill")
                break
    dark_title = bool(title_fill) and _luma(*(title_fill[:3])) < 80
    if dark_title:
        if dark_near_title < 16:
            findings.append("title_unreadable_at_thumbnail")
        if bright_title < 12:
            findings.append("weak_contrast")
    else:
        if bright_title < 16:
            findings.append("title_unreadable_at_thumbnail")
        if dark_near_title < 18:
            findings.append("weak_contrast")
    findings = list(dict.fromkeys(findings))
    return {
        "findings": findings,
        "pass": not findings,
        "messages": [FINDING_MESSAGES.get(code, code) for code in findings],
        "thumbnail": {"width": tw, "height": th, "bright_top": bright_title, "white": white, "edge_white": edge_white},
        "plan_sizes": sizes,
    }


def verify_source(source: dict | None, *, project_id: int | None, data: dict) -> dict[str, Any]:
    if not isinstance(source, dict) or not source:
        raise PhotoCoverError("No cover photograph is registered.")
    path = str(source.get("path") or "")
    pkg = str(data.get("package_id") or data.get("artifact_id") or "")
    if not path or not os.path.isfile(path):
        raise PhotoCoverError("Cover photograph is missing.")
    try:
        real = os.path.realpath(path)
        root = os.path.realpath(os.path.join(EXPORTS_DIR, pkg))
        if os.path.commonpath([real, root]) != root:
            raise PhotoCoverError("Cover photograph is outside this project.")
    except (OSError, ValueError) as exc:
        raise PhotoCoverError("Cover photograph path is invalid.") from exc
    owned = source.get("project_id")
    if project_id is not None and owned not in (None, project_id) and int(owned) != int(project_id):
        raise PhotoCoverError("Cover photograph belongs to another project.")
    digest = _sha_file(path)
    # source["sha256"] is the customer-facing cover identity digest (what
    # every UI/API surface and export bundle report as "the cover"). It is
    # normally also the real on-disk file's own hash. source["local_asset_sha256"],
    # when present, names the exact on-disk file this verification step
    # should re-hash and match against instead — for the one real, narrow
    # case where a project's identity digest and its currently-registered
    # local file digest are legitimately expected to differ (e.g. a
    # reviewable local test fixture standing in for an asset whose identity
    # digest cannot be reproduced locally). Absent, behavior is byte-for-byte
    # identical to before: re-hash the file and compare to source["sha256"].
    expected_digest = str(source.get("local_asset_sha256") or source.get("sha256") or "")
    if digest != expected_digest:
        raise PhotoCoverError("Cover photograph is stale or has been replaced.")
    img = _open_rgb(path)
    w, h = img.size
    if min(w, h) < MIN_SHORT_SIDE:
        raise PhotoCoverError("Cover photograph is below the 800px minimum.")
    if str(source.get("source_type") or "") not in {"upload", "pexels", "local_licensed", "ai_generated"}:
        raise PhotoCoverError("Unidentified cover image source.")
    if not str(source.get("license_note") or "").strip():
        raise PhotoCoverError("Cover photograph is missing a license/source note.")
    if str(source.get("source_type") or "") == "ai_generated":
        # An AI-generated cover's provenance record is its generation
        # prompt, not a photographer credit -- require it so every
        # AI-generated asset carries an auditable record of what was asked
        # for, same spirit as the Pexels photo_id/photographer check below.
        if not str(source.get("prompt") or "").strip():
            raise PhotoCoverError("AI-generated cover record is missing its prompt record.")
    basename = os.path.basename(path).lower()
    if "thumb" in basename and "source" not in basename:
        raise PhotoCoverError("Refusing to use a thumbnail as the cover source.")
    if str(source.get("source_type") or "") == "pexels":
        rec = source.get("pexels") if isinstance(source.get("pexels"), dict) else {}
        if not rec.get("photo_id") or not rec.get("photographer"):
            raise PhotoCoverError("Pexels cover record is incomplete.")
        if rec.get("sha256") and str(rec.get("sha256")) != digest:
            raise PhotoCoverError("Pexels cover record does not match the stored image.")
        rec_pid = rec.get("project_id")
        if project_id is not None and rec_pid not in (None, project_id) and int(rec_pid) != int(project_id):
            raise PhotoCoverError("Pexels cover record belongs to another project.")
        art = str(data.get("artifact_id") or data.get("package_id") or "")
        if rec.get("artifact_id") and art and str(rec.get("artifact_id")) != art:
            raise PhotoCoverError("Pexels cover record does not match this artifact.")
    return {"image": img, "digest": digest, "width": w, "height": h}


def _sniff_image(image_bytes: bytes) -> str:
    if not image_bytes:
        raise PhotoCoverError("Cover photograph is empty.")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise PhotoCoverError("Photograph is too large. Use a JPG or PNG under 12 MB.")
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_bytes[:2] == b"\xff\xd8":
        return "image/jpeg"
    raise PhotoCoverError("Unsupported or corrupted image. Upload a JPG or PNG.")


def _store_source_bytes(
    data: dict,
    image_bytes: bytes,
    *,
    source_type: str,
    filename: str,
    license_note: str,
    project_id: int | None,
) -> dict[str, Any]:
    mime = _sniff_image(image_bytes)
    name = os.path.basename(str(filename or "").strip())
    if not re.search(r"\.(png|jpe?g)$", name, re.I):
        raise PhotoCoverError("Unsupported or corrupted image. Upload a JPG or PNG.")
    ext_png = bool(re.search(r"\.png$", name, re.I))
    if mime == "image/png" and not ext_png:
        raise PhotoCoverError("Unsupported or corrupted image. Upload a JPG or PNG.")
    if mime == "image/jpeg" and ext_png:
        raise PhotoCoverError("Unsupported or corrupted image. Upload a JPG or PNG.")
    try:
        img = _open_rgb_bytes(image_bytes)
    except Exception as exc:  # noqa: BLE001
        raise PhotoCoverError("Unsupported or corrupted image. Upload a JPG or PNG.") from exc
    if min(img.size) < MIN_SHORT_SIDE:
        raise PhotoCoverError("Cover photograph is below the 800px minimum.")
    note = str(license_note or "").strip()
    if not note:
        raise PhotoCoverError("Provide a license or source note for this photograph.")
    digest = _sha_bytes(image_bytes)
    ext = ".png" if mime == "image/png" else ".jpg"
    dest_dir = os.path.join(_pkg_dir(data), "sources")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, digest + ext)
    if not os.path.isfile(dest):
        tmp = dest + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(image_bytes)
        os.replace(tmp, dest)
    stored = _sha_file(dest)
    if stored != digest:
        raise PhotoCoverError("Cover photograph did not persist with a matching SHA-256.")
    return {
        "source_type": source_type,
        "filename": name,
        "license_note": note,
        "sha256": digest,
        "width": img.size[0],
        "height": img.size[1],
        "orientation": "portrait" if img.size[1] >= img.size[0] else "landscape",
        "mime": mime,
        "project_id": project_id,
        "path": dest,
        "package_id": str(data.get("package_id") or data.get("artifact_id") or ""),
        "artifact_id": str(data.get("artifact_id") or data.get("package_id") or ""),
        "artifact_revision": int(data.get("artifact_revision") or 1),
    }


def _failed_variant(layout_id: str, qa: dict[str, Any]) -> dict[str, Any]:
    return {
        "layout_id": layout_id,
        "label": LAYOUT_LABELS[layout_id],
        "png_path": "",
        "pdf_path": "",
        "thumb_path": "",
        "digest": "",
        "png_digest": "",
        "quality": qa,
    }


def _write_variant_files(
    data: dict,
    layout_id: str,
    img: Image.Image,
    ident: dict[str, str],
    qa: dict[str, Any] | None = None,
    *,
    cache_key: str,
) -> dict[str, Any]:
    key = str(cache_key or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", key):
        raise PhotoCoverError("Cover render cache key is missing the source photograph digest.")
    folder = os.path.join(_pkg_dir(data), "variants", key, layout_id)
    os.makedirs(folder, exist_ok=True)
    png = _png_bytes(img)
    pdf = _pdf_from_png(
        png,
        title=ident["title"],
        author=ident["author"],
        subtitle=ident.get("subtitle") or "",
        series=ident.get("series") or "",
    )
    png_path = os.path.join(folder, "cover.png")
    pdf_path = os.path.join(folder, "cover.pdf")
    thumb_path = os.path.join(folder, "thumb.png")
    with open(png_path, "wb") as fh:
        fh.write(png)
    stored = Image.open(png_path)
    stored.load()
    stored = stored.convert("RGB")
    thumb = _png_bytes(_thumb(stored))
    with open(pdf_path, "wb") as fh:
        fh.write(pdf)
    with open(thumb_path, "wb") as fh:
        fh.write(thumb)
    if qa is None:
        qa = inspect_variant(img, layout_id, ident)
    return {
        "layout_id": layout_id,
        "label": LAYOUT_LABELS[layout_id],
        "png_path": png_path,
        "pdf_path": pdf_path,
        "thumb_path": thumb_path,
        "digest": hashlib.sha256(pdf).hexdigest(),
        "png_digest": hashlib.sha256(png).hexdigest(),
        "cache_key": key,
        "quality": qa,
    }


def _invalidate_stale_variant_caches(data: dict, *, keep: str) -> None:
    """Remove only stale cover variants/thumbnails for this draft. Keep the active cache."""
    folder = os.path.join(_pkg_dir(data), "variants")
    if not os.path.isdir(folder):
        return
    keep_key = str(keep or "").strip().lower()
    for name in os.listdir(folder):
        path = os.path.join(folder, name)
        if not os.path.isdir(path):
            continue
        if keep_key and name.lower() == keep_key:
            continue
        shutil.rmtree(path, ignore_errors=True)


def _recovery_editors(base: dict, layout_id: str) -> list[dict]:
    """Deterministic safe crop / overlay combinations. Users never set these sliders."""
    used = _clamp_editor(base)
    spec = LAYOUT_TYPE.get(layout_id) or LAYOUT_TYPE["full_bleed_editorial"]
    anchor = spec["anchor"]
    candidates: list[dict[str, Any]] = []

    def add(**over: Any) -> None:
        candidates.append(_clamp_editor({**used, **over}))

    if anchor == "top":
        focals = ((0.38, 0.58), (0.32, 0.66), (0.62, 0.58), (0.50, 0.70), (0.42, 0.50))
    elif anchor == "center":
        focals = ((0.32, 0.42), (0.68, 0.42), (0.32, 0.52), (0.68, 0.52), (0.50, 0.48))
    else:
        focals = ((0.38, 0.32), (0.32, 0.38), (0.62, 0.32), (0.50, 0.36), (0.42, 0.42))
    overlays = (0.40, 0.50, 0.62)
    for fx, fy in focals:
        for ov in overlays:
            add(focal_x=fx, focal_y=fy, overlay_strength=ov, zoom=1.0)
    add(zoom=1.0, focal_x=0.50, focal_y=0.48, overlay_strength=0.40)
    add(zoom=1.12, focal_x=used["focal_x"], focal_y=used["focal_y"], overlay_strength=0.46)
    seen: set[tuple] = set()
    out: list[dict[str, Any]] = []
    base_key = tuple(sorted((k, used[k]) for k in used))
    for cand in candidates:
        key = tuple(sorted((k, cand[k]) for k in cand))
        if key in seen or key == base_key:
            continue
        seen.add(key)
        out.append(cand)
        if len(out) >= MAX_RECOVERY_ATTEMPTS:
            break
    return out


def render_layout_with_recovery(
    photo: Image.Image, layout_id: str, ident: dict[str, str], editor: dict
) -> tuple[Image.Image, dict[str, Any], dict[str, Any], bool]:
    """Try the requested editor, then additional safe local combinations."""
    used = _clamp_editor(editor)
    img, qa = render_layout_with_qa(photo, layout_id, ident, used)
    if qa.get("pass"):
        return img, qa, used, False
    log.info("photo-cover layout %s initial findings=%s", layout_id, qa.get("findings"))
    best = (img, qa, used)
    for cand in _recovery_editors(used, layout_id):
        img2, qa2 = render_layout_with_qa(photo, layout_id, ident, cand)
        if qa2.get("pass"):
            log.info("photo-cover layout %s recovered", layout_id)
            return img2, qa2, cand, True
        if len(qa2.get("findings") or []) < len(best[1].get("findings") or []):
            best = (img2, qa2, cand)
    log.info("photo-cover layout %s exhausted findings=%s", layout_id, best[1].get("findings"))
    return best[0], best[1], best[2], False


def _activate_source(data: dict, source: dict, *, project_id: int | None) -> dict:
    """Swap in a new immutable source. Restore the previous cover if render fails."""
    previous = (
        copy.deepcopy(data["cover_design"])
        if isinstance(data.get("cover_design"), dict)
        else None
    )
    data["cover_design"] = {
        "source": source,
        "editor": default_editor(),
        "workflow": "photo_backed",
    }
    try:
        return render_photo_variants(data, project_id=project_id)
    except Exception:
        if previous is not None:
            data["cover_design"] = previous
        else:
            data["cover_design"] = None
        raise


def render_photo_variants(data: dict, *, project_id: int | None = None) -> dict:
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    incoming = copy.deepcopy(cover) if cover else {}
    source = cover.get("source") if isinstance(cover.get("source"), dict) else None
    verified = verify_source(source, project_id=project_id, data=data)
    ident = _approved_identity(data)
    editor = _clamp_editor(cover.get("editor"))
    source_sha = str(source.get("sha256") or verified["digest"])
    input_digest = cover_input_digest(source_sha=source_sha, ident=ident, editor=editor)
    cache_key = input_digest
    dest_root = os.path.join(_pkg_dir(data), "variants", cache_key)
    try:
        variants = {}
        prepared = _prepare_photo(verified["image"])
        for layout_id in LAYOUT_IDS:
            rendered, qa, used_editor, recovered = render_layout_with_recovery(
                prepared, layout_id, ident, editor
            )
            if qa.get("pass"):
                row = _write_variant_files(
                    data, layout_id, rendered, ident, qa, cache_key=cache_key
                )
                row["source_sha256"] = source_sha
                row["recovered"] = recovered
                row["recovered_editor"] = used_editor
                variants[layout_id] = row
            else:
                failed = _failed_variant(layout_id, qa)
                failed["recovered"] = False
                variants[layout_id] = failed
        _invalidate_stale_variant_caches(data, keep=cache_key)
    except Exception:
        previous_key = str(incoming.get("cover_input_digest") or incoming.get("cache_key") or "")
        if os.path.isdir(dest_root) and previous_key != cache_key:
            shutil.rmtree(dest_root, ignore_errors=True)
        if incoming:
            data["cover_design"] = incoming
        raise
    photo = {
        "title": ident["title"],
        "subtitle": ident["subtitle"],
        "author": ident["author"],
        "series": ident.get("series") or "",
        "package_id": str(data.get("package_id") or data.get("artifact_id") or ""),
        "product_type": str(data.get("type") or data.get("product_type") or "ebook"),
        "theme": str(cover.get("theme") or data.get("theme") or ""),
        "workflow": "photo_backed",
        "photo_backed": True,
        "image_digest": source_sha,
        "cover_input_digest": input_digest,
        "cache_key": cache_key,
        "local_generated": True,
        "paid_api_required": False,
        "source": source,
        "editor": editor,
        "variants": variants,
        "selected_layout": None,
        "cover_digest": "",
        "image_path": "",
        "local_cover_pdf": "",
        "qa_marker": "",
        "ai_cover": {
            "enabled": False,
            "configured": False,
            "label": "Optional paid feature — not configured",
        },
        "fields": dict(data.get("fields") or {}),
    }
    data["cover_design"] = photo
    data["ebook_cover_digest"] = ""
    data["export_ready"] = False
    data["release_status"] = ""
    return data


def attach_upload(
    data: dict,
    image_bytes: bytes,
    *,
    filename: str,
    license_note: str,
    project_id: int | None,
    owned: bool = False,
) -> dict:
    if not owned:
        raise PhotoCoverError("Confirm that you own this image or have permission to use it commercially.")
    note = str(license_note or "").strip() or (
        "User-uploaded photograph. Ownership/permission attested by the user. "
        "This Factory does not certify model releases, trademark clearance, or Amazon approval."
    )
    source = _store_source_bytes(
        data,
        image_bytes,
        source_type="upload",
        filename=filename,
        license_note=note,
        project_id=project_id,
    )
    source["ownership_attested"] = True
    return _activate_source(data, source, project_id=project_id)


def attach_pexels(data: dict, photo_id: str, *, project_id: int | None) -> dict:
    from services.ebook_pexels import (
        cache_record,
        download_pexels_original,
        fetch_pexels_photo,
    )

    pid = str(photo_id or "").strip()
    ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
    cache = ws.get("pexels_cache") if isinstance(ws.get("pexels_cache"), dict) else {}
    photo = None
    for row in list(cache.get("photos") or []):
        if isinstance(row, dict) and str(row.get("photo_id") or "") == pid:
            photo = dict(row)
            break
    if photo is None or not str(photo.get("original_url") or "").strip():
        photo = fetch_pexels_photo(pid)
    raw = download_pexels_original(photo)
    source = _store_source_bytes(
        data,
        raw,
        source_type="pexels",
        filename=f"pexels-{photo['photo_id']}.jpg",
        license_note=str(photo.get("license_note") or ""),
        project_id=project_id,
    )
    source["pexels"] = cache_record(
        photo,
        project_id=project_id,
        artifact_id=str(data.get("artifact_id") or data.get("package_id") or ""),
        revision=int(data.get("artifact_revision") or 1),
    )
    source["pexels"]["sha256"] = source["sha256"]
    return _activate_source(data, source, project_id=project_id)


def attach_licensed(data: dict, asset_id: str, *, project_id: int | None) -> dict:
    row = _licensed_asset(asset_id)
    path = ensure_licensed_image(asset_id)
    with open(path, "rb") as fh:
        raw = fh.read()
    source = _store_source_bytes(
        data,
        raw,
        source_type="local_licensed",
        filename=str(row["filename"]),
        license_note=str(row["license_note"]),
        project_id=project_id,
    )
    source["licensed_asset_id"] = asset_id
    return _activate_source(data, source, project_id=project_id)


def apply_editor(data: dict, editor: dict, *, project_id: int | None = None) -> dict:
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    if cover.get("workflow") != "photo_backed":
        raise PhotoCoverError("Register a photograph before editing the cover.")
    previous = copy.deepcopy(cover)
    cover["editor"] = _clamp_editor({**(cover.get("editor") or {}), **dict(editor or {})})
    cover["selected_layout"] = None
    data["cover_design"] = cover
    try:
        return render_photo_variants(data, project_id=project_id)
    except Exception:
        data["cover_design"] = previous
        raise


def select_layout(data: dict, layout_id: str, *, project_id: int | None = None) -> dict:
    layout_id = str(layout_id or "").strip()
    if layout_id not in LAYOUT_IDS:
        raise PhotoCoverError("Choose one of the three full-bleed typography variants.")
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    if cover.get("workflow") != "photo_backed":
        raise PhotoCoverError("Register a photograph before selecting a layout.")
    verify_source(cover.get("source"), project_id=project_id, data=data)
    variants = cover.get("variants") if isinstance(cover.get("variants"), dict) else {}
    chosen = variants.get(layout_id)
    if not isinstance(chosen, dict):
        raise PhotoCoverError("Render the three cover variants before selecting one.")
    qa = chosen.get("quality") or {}
    if not qa.get("pass"):
        raise PhotoCoverError("That cover is not available. Please choose another.")
    if not chosen.get("png_path") or not os.path.isfile(str(chosen.get("png_path"))):
        raise PhotoCoverError("That cover is not available. Please choose another.")
    passing = [
        lid
        for lid in LAYOUT_IDS
        if ((variants.get(lid) or {}).get("quality") or {}).get("pass")
        and os.path.isfile(str((variants.get(lid) or {}).get("png_path") or ""))
    ]
    if not passing:
        raise PhotoCoverError(NO_SAFE_COVER_MESSAGE)
    cover["selected_layout"] = layout_id
    cover["cover_digest"] = str(chosen.get("digest") or "")
    cover["image_path"] = str(chosen.get("png_path") or "")
    cover["local_cover_pdf"] = str(chosen.get("pdf_path") or "")
    cover["qa_marker"] = ""
    data["cover_design"] = cover
    data["ebook_cover_digest"] = cover["cover_digest"]
    return data


def clear_layout_selection(data: dict) -> dict:
    """Return to cover choices without deleting the photograph or variants."""
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    if cover.get("workflow") != "photo_backed":
        raise PhotoCoverError("Register a photograph before choosing a cover.")
    cover["selected_layout"] = None
    cover["cover_digest"] = ""
    cover["image_path"] = ""
    cover["local_cover_pdf"] = ""
    data["cover_design"] = cover
    data["ebook_cover_digest"] = ""
    return data


def assert_photo_cover_approvable(data: dict, *, project_id: int | None = None) -> None:
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None
    if not isinstance(cover, dict) or cover.get("workflow") != "photo_backed":
        raise PhotoCoverError("Approve is blocked until a verified photograph is used.")
    if not cover.get("selected_layout"):
        raise PhotoCoverError("Select a cover before approving.")
    verify_source(cover.get("source"), project_id=project_id, data=data)
    ident = _approved_identity(data)
    if (cover.get("title"), cover.get("subtitle"), cover.get("author")) != (
        ident["title"],
        ident["subtitle"],
        ident["author"],
    ):
        raise PhotoCoverError("Cover text does not match the approved title, subtitle, and author.")
    if str(cover.get("series") or "") != str(ident.get("series") or ""):
        raise PhotoCoverError("Cover text does not match the approved series text.")
    variants = cover.get("variants") if isinstance(cover.get("variants"), dict) else {}
    passing = [
        lid
        for lid in LAYOUT_IDS
        if ((variants.get(lid) or {}).get("quality") or {}).get("pass")
        and os.path.isfile(str((variants.get(lid) or {}).get("png_path") or ""))
    ]
    if not passing:
        raise PhotoCoverError(NO_SAFE_COVER_MESSAGE)
    chosen = variants.get(str(cover.get("selected_layout")))
    if not chosen or str(chosen.get("digest") or "") != str(cover.get("cover_digest") or ""):
        raise PhotoCoverError("Cover digest does not match the selected variant.")
    if not (chosen.get("quality") or {}).get("pass"):
        raise PhotoCoverError("The selected cover failed quality checks.")
    pdf_path = str(chosen.get("pdf_path") or "")
    if pdf_path and os.path.isfile(pdf_path):
        try:
            import fitz

            text = fitz.open(pdf_path)[0].get_text()
        except Exception:
            text = ""
        for label in FORBIDDEN_LABELS:
            if label.lower() in text.lower():
                raise PhotoCoverError("Cover contains an unapproved label.")
        if ident["title"] and ident["title"] not in text.replace("\n", " "):
            # wrapped titles may split; require all words
            for word in ident["title"].split():
                if word and word not in text:
                    raise PhotoCoverError("Cover title identity failed.")


def photo_cover_preflight_failures(data: dict, *, project_id: int | None = None) -> list[tuple[str, str]]:
    """Hard cover FAIL list. Never claims Amazon, copyright, model-release, or legal approval."""
    failures: list[tuple[str, str]] = []
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None
    if not isinstance(cover, dict) or not cover:
        return [("missing_cover_photograph", "No cover photograph is registered.")]
    if cover.get("workflow") != "photo_backed":
        failures.append(("vector_cover_rejected", "Vector-only covers cannot pass cover preflight."))
        return failures
    source = cover.get("source") if isinstance(cover.get("source"), dict) else None
    try:
        verify_source(source, project_id=project_id, data=data)
    except PhotoCoverError as exc:
        msg = str(exc)
        code = "stale_cover_photograph"
        if "missing" in msg.lower() and "license" not in msg.lower():
            code = "missing_cover_photograph_file"
        elif "another project" in msg.lower():
            code = "cross_project_cover_photograph"
        elif "thumbnail" in msg.lower():
            code = "thumbnail_used_as_cover_source"
        elif "800" in msg:
            code = "low_resolution_cover_photograph"
        elif "license" in msg.lower() or "ownership" in msg.lower():
            code = "missing_cover_license"
        elif "incomplete" in msg.lower() or "does not match" in msg.lower():
            code = "mismatched_cover_record"
        failures.append((code, msg))
        return failures
    variants = cover.get("variants") if isinstance(cover.get("variants"), dict) else {}
    for layout_id in LAYOUT_IDS:
        qa = (variants.get(layout_id) or {}).get("quality") or {}
        findings = list(qa.get("findings") or [])
        if "blank_white_area" in findings:
            failures.append(("blank_white_area", "Cover still contains a blank white area."))
            break
    for layout_id in LAYOUT_IDS:
        qa = (variants.get(layout_id) or {}).get("quality") or {}
        findings = list(qa.get("findings") or [])
        if "not_full_bleed" in findings:
            failures.append(("cover_not_full_bleed", "Photograph must fill the portrait cover edge to edge."))
            break
    selected = str(cover.get("selected_layout") or "")
    if not selected:
        failures.append(("cover_layout_not_selected", "Select one cover layout before preflight can pass."))
    try:
        if selected:
            assert_photo_cover_approvable(data, project_id=project_id)
    except PhotoCoverError as exc:
        msg = str(exc)
        code = "cover_not_approvable"
        if "digest" in msg.lower():
            code = "cover_digest_mismatch"
        elif "label" in msg.lower():
            code = "unapproved_cover_label"
        elif "title" in msg.lower() or "identity" in msg.lower() or "readable" in msg.lower():
            code = "unreadable_cover_text"
        failures.append((code, msg))
    blob = " ".join(
        [
            str(cover.get("title") or ""),
            str(cover.get("subtitle") or ""),
            str(cover.get("author") or ""),
            str(cover.get("qa_marker") or ""),
        ]
    )
    for label in FORBIDDEN_LABELS:
        if label.lower() in blob.lower():
            failures.append(("unapproved_cover_label", f"Unapproved cover label: {label}."))
            break
    legal = blob.lower()
    if any(tok in legal for tok in ("amazon approved", "model release on file", "copyright cleared")):
        failures.append(("invented_legal_claim", "Cover must not claim Amazon, copyright, or model-release approval."))
    return failures


def resolve_cover_guided_step(
    *,
    has_valid_photo: bool,
    passing_count: int,
    selected_layout: str = "",
    selected_is_passing: bool = False,
    cover_approved: bool = False,
) -> str:
    """Authoritative cover UI step from persisted facts. Never invents a selection.

    Step 1 — no valid active photograph.
    Step 2 — photograph exists but no passing cover has been selected.
    Step 3 — a passing cover has been selected and is waiting for review/approval.
    Approved — show the approved cover and next production action.
    choose_another_photo — photograph exists but no passing variant; nearest safe recovery.
    """
    selected = str(selected_layout or "").strip()
    passing = int(passing_count or 0)
    if cover_approved and selected and selected_is_passing:
        return GUIDED_STEP_APPROVED
    if not has_valid_photo:
        return GUIDED_STEP_CHOOSE_PHOTO
    if passing <= 0:
        return GUIDED_STEP_CHOOSE_ANOTHER
    if not selected or not selected_is_passing:
        return GUIDED_STEP_CHOOSE_COVER
    return GUIDED_STEP_REVIEW


def cover_guided_recovery_action(
    step: str,
    *,
    selected_layout: str = "",
    selected_is_passing: bool = False,
) -> str:
    """Plain-language recovery when persisted cover state is incomplete."""
    selected = str(selected_layout or "").strip()
    if step == GUIDED_STEP_CHOOSE_COVER and selected and not selected_is_passing:
        return INCOMPLETE_SELECTION_RECOVERY
    if step == GUIDED_STEP_CHOOSE_ANOTHER:
        return NO_SAFE_COVER_MESSAGE
    if step not in GUIDED_STEPS:
        return MISSING_STEP_RECOVERY
    return USER_STATUS.get(step) or USER_STATUS[GUIDED_STEP_CHOOSE_PHOTO]


def photo_cover_public_fields(data: dict, *, project_id: int | None) -> dict[str, Any]:
    from services.ebook_pexels import pexels_public_status

    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    photo = cover.get("workflow") == "photo_backed"
    variants = []
    failed_variants = []
    raw = cover.get("variants") if isinstance(cover.get("variants"), dict) else {}
    digest = str(cover.get("cover_digest") or "")
    sha = str((cover.get("source") or {}).get("sha256") or cover.get("image_digest") or "").strip()
    input_digest = str(cover.get("cover_input_digest") or cover.get("cache_key") or "").strip()
    for layout_id in LAYOUT_IDS:
        row = raw.get(layout_id) or {}
        qa = row.get("quality") or {}
        vd = str(row.get("digest") or "")
        passed = bool(qa.get("pass")) and bool(vd)
        findings = list(qa.get("findings") or [])
        messages = list(qa.get("messages") or [FINDING_MESSAGES.get(code, code) for code in findings])
        cache_bust = ""
        if project_id and passed and vd:
            cache_bust = f"&src={sha}" if sha else ""
            if input_digest:
                cache_bust += f"&v={input_digest}"
        item = {
            "layout_id": layout_id,
            "label": LAYOUT_LABELS[layout_id],
            "digest": vd,
            "cache_key": str(row.get("cache_key") or input_digest or ""),
            "source_sha256": str(row.get("source_sha256") or sha or ""),
            "quality_pass": passed,
            "findings": findings,
            "messages": messages,
            "full_url": (
                f"/ebook-workspace/{int(project_id)}/cover-variant?layout={layout_id}&size=full&digest={vd}{cache_bust}"
                if project_id and passed and vd
                else ""
            ),
            "thumb_url": (
                f"/ebook-workspace/{int(project_id)}/cover-variant?layout={layout_id}&size=thumb&digest={vd}{cache_bust}"
                if project_id and passed and vd
                else ""
            ),
        }
        variants.append(item)
        if raw.get(layout_id) and not passed:
            failed_variants.append(item)
    selected = str(cover.get("selected_layout") or "")
    approvable = False
    try:
        if photo and selected:
            assert_photo_cover_approvable(data, project_id=project_id)
            approvable = True
    except PhotoCoverError:
        approvable = False
    pexels_public = pexels_public_status()
    from services.ebook_pexels import public_photos

    ws = data.get("ebook_workspace") if isinstance(data.get("ebook_workspace"), dict) else {}
    cache = ws.get("pexels_cache") if isinstance(ws.get("pexels_cache"), dict) else {}
    src = cover.get("source") if isinstance(cover.get("source"), dict) else {}
    pexels_rec = src.get("pexels") if isinstance(src.get("pexels"), dict) else {}
    sha = str(src.get("sha256") or "").strip()
    local_source_url = (
        f"/ebook-workspace/{int(project_id)}/cover-photo?digest={sha}"
        + (f"&v={input_digest}" if input_digest else "")
        if photo and project_id and sha
        else ""
    )
    source_public = None
    if photo:
        source_public = {
            "source_type": src.get("source_type") or "",
            "filename": src.get("filename") or "",
            "license_note": src.get("license_note") or "",
            "sha256": sha,
            "width": src.get("width"),
            "height": src.get("height"),
            "orientation": src.get("orientation") or "",
            "photographer": pexels_rec.get("photographer") or "",
            "attribution": pexels_rec.get("attribution") or "",
            "page_url": pexels_rec.get("page_url") or "",
            "photo_id": pexels_rec.get("photo_id") or "",
            "preview_url": local_source_url,
        }
    selected_pexels_id = (
        str(pexels_rec.get("photo_id") or "")
        if photo and str(src.get("source_type") or "") == "pexels"
        else ""
    )
    pexels_photos = public_photos(cache.get("photos"))
    for row in pexels_photos:
        if local_source_url and selected_pexels_id and str(row.get("photo_id") or "") == selected_pexels_id:
            row["preview_url"] = local_source_url
            row["selected"] = True
        else:
            row["selected"] = False
    pexels_public = {
        **pexels_public,
        "query": cache.get("query") or "",
        "page": cache.get("page") or 1,
        "photos": pexels_photos,
        "next_page": cache.get("next_page"),
    }
    passing_count = sum(1 for row in variants if row.get("quality_pass"))
    has_source = bool(photo and sha)
    selected_row = next((row for row in variants if row.get("layout_id") == selected), None)
    if selected_row and selected_row.get("quality_pass"):
        if project_id:
            selected_is_passing = bool(selected_row.get("full_url") and selected_row.get("thumb_url"))
        else:
            selected_is_passing = True
    else:
        selected_is_passing = False
    rail_cover = (ws.get("rail") or {}).get("cover") if isinstance(ws.get("rail"), dict) else {}
    cover_approved = str((rail_cover or {}).get("status") or "") == "approved"
    workflow_step = resolve_cover_guided_step(
        has_valid_photo=has_source,
        passing_count=passing_count,
        selected_layout=selected,
        selected_is_passing=selected_is_passing,
        cover_approved=cover_approved,
    )
    developer_details = {
        "image_digest": str(cover.get("image_digest") or src.get("sha256") or ""),
        "cover_input_digest": input_digest,
        "failed_findings": [
            {
                "layout_id": row.get("layout_id"),
                "findings": row.get("findings") or [],
                "messages": row.get("messages") or [],
            }
            for row in failed_variants
        ],
    }
    return {
        "workflow": "photo_backed" if photo else str(cover.get("workflow") or ""),
        "photo_backed": photo,
        "source": source_public,
        "editor": cover.get("editor") if photo else default_editor(),
        "variants": variants,
        "failed_variants": failed_variants,
        "passing_count": passing_count,
        "selected_layout": selected,
        "image_digest": str(cover.get("image_digest") or src.get("sha256") or ""),
        "cover_input_digest": input_digest,
        "ai_cover": cover.get("ai_cover")
        or {
            "enabled": False,
            "configured": False,
            "label": "Optional paid feature — not configured",
        },
        "pexels": pexels_public,
        "approvable": approvable and workflow_step == GUIDED_STEP_REVIEW,
        "cover_approved": cover_approved and workflow_step == GUIDED_STEP_APPROVED,
        "workflow_step": workflow_step,
        "guided_step": GUIDED_STEP_NUMBERS.get(workflow_step, 1),
        "guided_step_label": GUIDED_STEP_LABELS.get(workflow_step) or GUIDED_STEP_LABELS[GUIDED_STEP_CHOOSE_PHOTO],
        "user_status": cover_guided_recovery_action(
            workflow_step,
            selected_layout=selected,
            selected_is_passing=selected_is_passing,
        ),
        "recovery_action": cover_guided_recovery_action(
            workflow_step,
            selected_layout=selected,
            selected_is_passing=selected_is_passing,
        ),
        "no_safe_cover": workflow_step == GUIDED_STEP_CHOOSE_ANOTHER,
        "choose_another_photo_message": NO_SAFE_COVER_MESSAGE if workflow_step == GUIDED_STEP_CHOOSE_ANOTHER else "",
        "developer_details": developer_details,
        "preview_url": (
            f"/ebook-workspace/{int(project_id)}/cover-preview?digest={digest}"
            if project_id and digest
            else ""
        ),
        "vector_rejected": bool(cover) and not photo,
        "legal_disclaimer": (
            "This Factory does not certify Amazon approval, copyright clearance, "
            "model releases, or other legal rights."
        ),
    }


def verified_variant_asset(
    data: dict,
    *,
    project_id: int | None,
    layout: str,
    digest: str,
    size: str,
    source_sha: str = "",
) -> dict[str, Any]:
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    if cover.get("workflow") != "photo_backed":
        raise PhotoCoverError("Cover variant is unavailable.")
    verified = verify_source(cover.get("source"), project_id=project_id, data=data)
    requested_src = str(source_sha or "").strip().lower()
    if requested_src and requested_src != str(verified["digest"] or "").lower():
        raise PhotoCoverError("Cover variant digest does not match.")
    row = ((cover.get("variants") or {}).get(layout) or {})
    if str(row.get("digest") or "").lower() != str(digest or "").strip().lower():
        raise PhotoCoverError("Cover variant digest does not match.")
    row_src = str(row.get("source_sha256") or "").strip().lower()
    if row_src and row_src != str(verified["digest"] or "").lower():
        raise PhotoCoverError("Cover variant digest does not match.")
    path = str(row.get("thumb_path") if size == "thumb" else row.get("png_path") or "")
    if not path or not os.path.isfile(path):
        raise PhotoCoverError("Cover variant file is missing.")
    with open(path, "rb") as fh:
        body = fh.read()
    return {"bytes": body, "mimetype": "image/png", "digest": row["digest"]}


def verified_source_photo_asset(
    data: dict, *, project_id: int | None, digest: str
) -> dict[str, Any]:
    """Return the registered cover photograph bytes. Never generates or downloads."""
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    if cover.get("workflow") != "photo_backed":
        raise PhotoCoverError("Cover photograph is unavailable.")
    source = cover.get("source") if isinstance(cover.get("source"), dict) else {}
    requested = str(digest or "").strip().lower()
    stored = str(source.get("sha256") or "").strip().lower()
    if not requested or requested != stored:
        raise PhotoCoverError("Cover photograph digest does not match.")
    verify_source(source, project_id=project_id, data=data)
    path = str(source.get("path") or "")
    if not path or not os.path.isfile(path):
        raise PhotoCoverError("Cover photograph is missing.")
    with open(path, "rb") as fh:
        body = fh.read()
    mime = _sniff_image(body)
    return {"bytes": body, "mimetype": mime, "digest": stored}
