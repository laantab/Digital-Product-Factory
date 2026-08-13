"""Photo-backed Ebook covers: Pexels stock or user upload, three layouts, QA.

Zero paid calls. Tests mock Pexels; live HTTP is blocked in FACTORY_TEST_MODE.
Does not rewrite manuscript or ledgers.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

from services.ebook_fonts import ebook_font_paths
from services.ebook_package import EXPORTS_DIR

LAYOUT_IDS = ("full_bleed_editorial", "split_studio", "printed_moment")
LAYOUT_LABELS = {
    "full_bleed_editorial": "Full-Bleed Editorial",
    "split_studio": "Split-Studio",
    "printed_moment": "Printed-Moment",
}
MIN_SHORT_SIDE = 800
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
COVER_W, COVER_H = 1275, 1650
THUMB_W = 160
MIN_TITLE_PT = 28
MIN_SUBTITLE_PT = 12
MIN_AUTHOR_PT = 13
AI_COVER_ESTIMATE_USD = 0.04
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
    return {
        "title": str(data.get("title") or "").strip(),
        "subtitle": str(data.get("subtitle") or "").strip(),
        "author": str(data.get("author_brand") or data.get("author") or "").strip(),
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


def _sha_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()


def _open_rgb(path: str) -> Image.Image:
    img = Image.open(path)
    img.load()
    return img.convert("RGB")


def _cover_crop(im: Image.Image, editor: dict) -> Image.Image:
    z = float(editor["zoom"])
    fx, fy = float(editor["focal_x"]), float(editor["focal_y"])
    src_aspect = im.width / max(im.height, 1)
    dst_aspect = COVER_W / COVER_H
    if src_aspect > dst_aspect:
        crop_h = im.height / z
        crop_w = crop_h * dst_aspect
    else:
        crop_w = im.width / z
        crop_h = crop_w / dst_aspect
    crop_w = min(crop_w, float(im.width))
    crop_h = min(crop_h, float(im.height))
    left = max(0.0, min(im.width - crop_w, fx * im.width - crop_w / 2))
    top = max(0.0, min(im.height - crop_h, fy * im.height - crop_h / 2))
    cropped = im.crop((int(left), int(top), int(left + crop_w), int(top + crop_h)))
    return cropped.resize((COVER_W, COVER_H), Image.Resampling.LANCZOS)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words = re.findall(r"\S+", text or "")
    lines: list[str] = []
    cur: list[str] = []
    for word in words:
        trial = " ".join(cur + [word])
        bbox = draw.textbbox((0, 0), trial, font=font)
        if cur and (bbox[2] - bbox[0]) > max_w:
            lines.append(" ".join(cur))
            cur = [word]
        else:
            cur.append(word)
    if cur:
        lines.append(" ".join(cur))
    return lines or [""]


def _draw_text_block(draw, lines, font, x, y, fill, *, shadow=True, line_gap=8) -> int:
    cy = y
    for line in lines:
        if shadow:
            draw.text((x + 2, cy + 2), line, font=font, fill=(8, 10, 16))
        draw.text((x, cy), line, font=font, fill=fill)
        bbox = draw.textbbox((0, 0), line, font=font)
        cy += (bbox[3] - bbox[1]) + line_gap
    return cy


def _top_scrim(img: Image.Image, strength: float, height_frac: float = 0.46) -> None:
    h = max(1, int(img.height * height_frac))
    a_max = int(230 * strength)
    grad = Image.new("L", (1, h))
    for y in range(h):
        grad.putpixel((0, y), int(a_max * (1 - y / max(h - 1, 1))))
    alpha = grad.resize((img.width, h), Image.Resampling.BILINEAR)
    band = Image.new("RGBA", (img.width, h), (8, 12, 22, 0))
    band.putalpha(alpha)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay.paste(band, (0, 0))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))


def _draw_camera(draw: ImageDraw.ImageDraw, origin: tuple[int, int], scale: float = 1.0) -> None:
    """Recognizable body + grip + lens + controls. Not rings-only."""
    x, y = origin
    s = scale

    def p(pts):
        return [(int(x + a * s), int(y + b * s)) for a, b in pts]

    def oval(x0, y0, x1, y1, fill):
        if x1 < x0:
            x0, x1 = x1, x0
        if y1 < y0:
            y0, y1 = y1, y0
        if (x1 - x0) < 2 or (y1 - y0) < 2:
            return
        draw.ellipse((x0, y0, x1, y1), fill=fill)

    draw.polygon(p([(8, 78), (70, 70), (78, 210), (4, 222)]), fill=(28, 30, 34))  # grip
    draw.rounded_rectangle((int(x + 14 * s), int(y + 96 * s), int(x + 36 * s), int(y + 196 * s)), int(6 * s), fill=(48, 50, 54))
    draw.polygon(p([(70, 70), (210, 86), (216, 196), (78, 210)]), fill=(62, 64, 70))  # body
    draw.polygon(p([(210, 86), (286, 102), (290, 186), (216, 196)]), fill=(92, 94, 102))  # front
    draw.polygon(p([(78, 64), (216, 80), (228, 118), (88, 128)]), fill=(78, 80, 86))  # top
    draw.polygon(p([(118, 48), (196, 56), (188, 8), (128, 2)]), fill=(44, 46, 52))  # prism
    draw.rectangle((int(x + 146 * s), int(y + 0 * s), int(x + 176 * s), int(y + 12 * s)), fill=(16, 16, 18))
    oval(int(x + 198 * s), int(y + 52 * s), int(x + 222 * s), int(y + 76 * s), (36, 38, 42))  # dial
    oval(int(x + 204 * s), int(y + 58 * s), int(x + 216 * s), int(y + 70 * s), (120, 122, 128))
    accent = (212, 160, 23)
    oval(int(x + 232 * s), int(y + 54 * s), int(x + 252 * s), int(y + 74 * s), accent)  # shutter
    # Lens barrel + glass
    draw.rounded_rectangle((int(x + 270 * s), int(y + 108 * s), int(x + 430 * s), int(y + 188 * s)), int(22 * s), fill=(22, 24, 28))
    for gx in (300, 332, 364):
        draw.line((int(x + gx * s), int(y + 114 * s), int(x + gx * s), int(y + 182 * s)), fill=(70, 72, 78), width=max(2, int(3 * s)))
    lx0, ly0 = int(x + 412 * s), int(y + 112 * s)
    lx1, ly1 = int(x + 468 * s), int(y + 186 * s)
    oval(lx0, ly0, lx1, ly1, (18, 20, 24))
    pad = max(2, int(min(lx1 - lx0, ly1 - ly0) * 0.16))
    oval(lx0 + pad, ly0 + pad, lx1 - pad, ly1 - pad, (28, 58, 102))
    pad2 = max(pad + 2, int(min(lx1 - lx0, ly1 - ly0) * 0.28))
    oval(lx0 + pad2, ly0 + pad2, lx1 - pad2, ly1 - pad2, (8, 12, 20))
    oval(lx0 + pad, ly0 + max(2, pad // 2), lx0 + pad + max(6, int(10 * s)), ly0 + pad + max(6, int(10 * s)), (220, 230, 240))


def _paste_print(base: Image.Image, photo: Image.Image, box: tuple[int, int, int, int], *, tilt: float) -> None:
    x, y, w, h = box
    card = Image.new("RGBA", (w, h), (255, 255, 255, 255))
    inset_x, inset_top, inset_bot = 16, 16, 28
    inner = photo.resize((w - 2 * inset_x, h - inset_top - inset_bot), Image.Resampling.LANCZOS)
    card.paste(inner.convert("RGBA"), (inset_x, inset_top))
    if abs(tilt) > 0.1:
        card = card.rotate(tilt, resample=Image.Resampling.BICUBIC, expand=True)
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    layer.paste(card, (x, y), card)
    base.paste(Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB"))


def _identity_text(img: Image.Image, ident: dict[str, str], editor: dict, *, max_w: int, x: int) -> None:
    draw = ImageDraw.Draw(img)
    title_font = _font(int(editor["title_size"] * 2.0), bold=True)
    sub_font = _font(int(editor["subtitle_size"] * 2.0), bold=False)
    auth_font = _font(int(editor["author_size"] * 2.0), bold=True)
    title_lines = _wrap(draw, ident["title"], title_font, max_w)
    sub_lines = _wrap(draw, ident["subtitle"], sub_font, max_w)
    ty = int(COVER_H * float(editor["title_y"]))
    _draw_text_block(draw, title_lines, title_font, x, ty, (255, 255, 255), line_gap=10)
    sy = int(COVER_H * float(editor["subtitle_y"]))
    _draw_text_block(draw, sub_lines, sub_font, x, sy, (236, 230, 214), line_gap=8)
    ay = int(COVER_H * float(editor["author_y"]))
    _draw_text_block(draw, [ident["author"]], auth_font, x, ay, (252, 248, 240), line_gap=6)


def render_layout(photo: Image.Image, layout_id: str, ident: dict[str, str], editor: dict) -> Image.Image:
    cropped = _cover_crop(photo, editor)
    strength = float(editor["overlay_strength"])
    accent = _hex_rgb(str(editor["accent"]))
    if layout_id == "full_bleed_editorial":
        img = cropped.copy()
        _top_scrim(img, strength, 0.50)
        bar = ImageDraw.Draw(img)
        bar.rectangle((64, 48, 220, 62), fill=accent)
        _identity_text(img, ident, editor, max_w=COVER_W - 140, x=64)
        return img
    if layout_id == "split_studio":
        img = Image.new("RGB", (COVER_W, COVER_H), (10, 16, 28))
        split = int(COVER_W * 0.52)
        left = cropped.resize((split, COVER_H), Image.Resampling.LANCZOS)
        img.paste(left, (0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle((split, 0, COVER_W, COVER_H), fill=(12, 18, 32))
        draw.rectangle((split, 0, split + 10, COVER_H), fill=accent)
        panel_w = COVER_W - split - 88
        _identity_text(img, ident, {**editor, "title_y": 0.12, "subtitle_y": 0.38, "author_y": 0.86}, max_w=panel_w, x=split + 44)
        # Subtle capture-to-print cue on the photo side
        _draw_camera(draw, (36, COVER_H - 430), scale=0.72)
        return img
    # printed_moment
    img = cropped.filter(ImageFilter.GaussianBlur(10))
    img = ImageEnhance.Brightness(img).enhance(0.62)
    _top_scrim(img, max(0.45, strength), 0.42)
    draw = ImageDraw.Draw(img)
    draw.rectangle((64, 48, 220, 62), fill=accent)
    _draw_camera(draw, (48, COVER_H - 520), scale=1.05)
    sharp = cropped
    _paste_print(img, sharp.crop((int(COVER_W * 0.18), int(COVER_H * 0.22), int(COVER_W * 0.78), int(COVER_H * 0.62))), (690, 620, 430, 310), tilt=7)
    _paste_print(img, sharp.crop((int(COVER_W * 0.28), int(COVER_H * 0.12), int(COVER_W * 0.88), int(COVER_H * 0.52))), (780, 430, 390, 280), tilt=-6)
    _identity_text(img, ident, editor, max_w=COVER_W - 140, x=64)
    return img


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _pdf_from_png(png: bytes, *, title: str, author: str, subtitle: str = "") -> bytes:
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
    c.drawString(36, 48, title or "")
    c.drawString(36, 36, subtitle or "")
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


def inspect_variant(img: Image.Image, layout_id: str, ident: dict[str, str]) -> dict[str, Any]:
    findings: list[str] = []
    blob = f"{ident['title']}\n{ident['subtitle']}\n{ident['author']}"
    for label in FORBIDDEN_LABELS:
        if label.lower() in blob.lower():
            findings.append("unapproved_label")
    if not ident["title"] or not ident["subtitle"] or not ident["author"]:
        findings.append("missing_identity_text")
    thumb = _thumb(img)
    tw, th = thumb.size
    samples = thumb.tobytes()
    n = 3
    white = amber = gray = bright_top = dark_top = 0
    white_right = color_right = 0
    for i in range(0, len(samples) - 2, n):
        r, g, b = samples[i], samples[i + 1], samples[i + 2]
        px = (i // n) % tw
        py = (i // n) // tw
        if r > 220 and g > 220 and b > 210:
            white += 1
            if px > tw * 0.52:
                white_right += 1
        if py < th * 0.28:
            if _luma(r, g, b) > 200:
                bright_top += 1
            if _luma(r, g, b) < 80:
                dark_top += 1
        if 35 < r < 160 and abs(r - g) < 28 and abs(g - b) < 32 and b <= r + 20:
            gray += 1
        if r > 150 and 70 < g < 220 and b < 140 and r > b + 30:
            amber += 1
        if px > tw * 0.55 and _luma(r, g, b) > 40 and not (r > 220 and g > 220):
            color_right += 1
    if bright_top < 18:
        findings.append("title_unreadable_at_thumbnail")
    if dark_top < 30:
        findings.append("weak_contrast")
    if layout_id == "printed_moment":
        if gray < 40:
            findings.append("camera_not_recognizable")
        if white_right < 80:
            findings.append("print_border_missing")
        if color_right < 40:
            findings.append("empty_photo_rectangles")
        if amber < 8:
            findings.append("event_lighting_missing")
    # Full-size subtitle/author occupancy
    full = img.resize((318, 412), Image.Resampling.LANCZOS)
    # Safe margins: avoid drawing into the outer 3%
    edge = full.crop((0, 0, full.width, 8)).tobytes()
    if all(edge[i] > 250 for i in range(0, len(edge), 3)):
        findings.append("clipped_or_empty_edge")
    return {
        "findings": findings,
        "pass": not findings,
        "thumbnail": {"width": tw, "height": th, "bright_top": bright_top, "gray": gray, "white_right": white_right},
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
    if digest != str(source.get("sha256") or ""):
        raise PhotoCoverError("Cover photograph is stale or has been replaced.")
    img = _open_rgb(path)
    w, h = img.size
    if min(w, h) < MIN_SHORT_SIDE:
        raise PhotoCoverError("Cover photograph is below the 800px minimum.")
    if str(source.get("source_type") or "") not in {"upload", "pexels", "local_licensed"}:
        raise PhotoCoverError("Unidentified cover image source.")
    if not str(source.get("license_note") or "").strip():
        raise PhotoCoverError("Cover photograph is missing a license/source note.")
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
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
        img = img.convert("RGB")
    except Exception as exc:  # noqa: BLE001
        raise PhotoCoverError("Unsupported or corrupted image. Upload a JPG or PNG.") from exc
    if min(img.size) < MIN_SHORT_SIDE:
        raise PhotoCoverError("Cover photograph is below the 800px minimum.")
    note = str(license_note or "").strip()
    if not note:
        raise PhotoCoverError("Provide a license or source note for this photograph.")
    name = os.path.basename(str(filename or "cover-source.png"))
    if not re.search(r"\.(png|jpe?g)$", name, re.I):
        name += ".png" if mime == "image/png" else ".jpg"
    dest_dir = _pkg_dir(data)
    dest = os.path.join(dest_dir, "source.png")
    img.save(dest, "PNG")
    digest = _sha_file(dest)
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


def _write_variant_files(data: dict, layout_id: str, img: Image.Image, ident: dict[str, str]) -> dict[str, Any]:
    folder = os.path.join(_pkg_dir(data), "variants", layout_id)
    os.makedirs(folder, exist_ok=True)
    png = _png_bytes(img)
    pdf = _pdf_from_png(png, title=ident["title"], author=ident["author"], subtitle=ident["subtitle"])
    thumb = _png_bytes(_thumb(img))
    png_path = os.path.join(folder, "cover.png")
    pdf_path = os.path.join(folder, "cover.pdf")
    thumb_path = os.path.join(folder, "thumb.png")
    with open(png_path, "wb") as fh:
        fh.write(png)
    with open(pdf_path, "wb") as fh:
        fh.write(pdf)
    with open(thumb_path, "wb") as fh:
        fh.write(thumb)
    qa = inspect_variant(img, layout_id, ident)
    return {
        "layout_id": layout_id,
        "label": LAYOUT_LABELS[layout_id],
        "png_path": png_path,
        "pdf_path": pdf_path,
        "thumb_path": thumb_path,
        "digest": hashlib.sha256(pdf).hexdigest(),
        "quality": qa,
    }


def render_photo_variants(data: dict, *, project_id: int | None = None) -> dict:
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    source = cover.get("source") if isinstance(cover.get("source"), dict) else None
    verified = verify_source(source, project_id=project_id, data=data)
    ident = _approved_identity(data)
    editor = _clamp_editor(cover.get("editor"))
    variants = {}
    for layout_id in LAYOUT_IDS:
        rendered = render_layout(verified["image"], layout_id, ident, editor)
        variants[layout_id] = _write_variant_files(data, layout_id, rendered, ident)
    photo = {
        "title": ident["title"],
        "subtitle": ident["subtitle"],
        "author": ident["author"],
        "package_id": str(data.get("package_id") or data.get("artifact_id") or ""),
        "product_type": "ebook",
        "theme": "event_photography",
        "workflow": "photo_backed",
        "photo_backed": True,
        "image_digest": str(source.get("sha256") or verified["digest"]),
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
    data["cover_design"] = {"source": source, "editor": default_editor(), "workflow": "photo_backed"}
    return render_photo_variants(data, project_id=project_id)


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
    data["cover_design"] = {"source": source, "editor": default_editor(), "workflow": "photo_backed"}
    return render_photo_variants(data, project_id=project_id)


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
    data["cover_design"] = {"source": source, "editor": default_editor(), "workflow": "photo_backed"}
    return render_photo_variants(data, project_id=project_id)


def apply_editor(data: dict, editor: dict, *, project_id: int | None = None) -> dict:
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    if cover.get("workflow") != "photo_backed":
        raise PhotoCoverError("Register a photograph before editing the cover.")
    cover["editor"] = _clamp_editor({**(cover.get("editor") or {}), **dict(editor or {})})
    cover["selected_layout"] = None
    data["cover_design"] = cover
    return render_photo_variants(data, project_id=project_id)


def select_layout(data: dict, layout_id: str, *, project_id: int | None = None) -> dict:
    layout_id = str(layout_id or "").strip()
    if layout_id not in LAYOUT_IDS:
        raise PhotoCoverError("Choose Full-Bleed Editorial, Split-Studio, or Printed-Moment.")
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    if cover.get("workflow") != "photo_backed":
        raise PhotoCoverError("Register a photograph before selecting a layout.")
    verify_source(cover.get("source"), project_id=project_id, data=data)
    variants = cover.get("variants") if isinstance(cover.get("variants"), dict) else {}
    chosen = variants.get(layout_id)
    if not isinstance(chosen, dict):
        raise PhotoCoverError("Render the three cover variants before selecting one.")
    story = variants.get("printed_moment") or {}
    story_qa = (story.get("quality") or {})
    if not story_qa.get("pass"):
        raise PhotoCoverError(
            "Printed-Moment must show camera → captured event image → physical print at thumbnail size."
        )
    qa = chosen.get("quality") or {}
    if not qa.get("pass"):
        raise PhotoCoverError("That layout failed readability or identity checks.")
    cover["selected_layout"] = layout_id
    cover["cover_digest"] = str(chosen.get("digest") or "")
    cover["image_path"] = str(chosen.get("png_path") or "")
    cover["local_cover_pdf"] = str(chosen.get("pdf_path") or "")
    cover["qa_marker"] = ""
    data["cover_design"] = cover
    data["ebook_cover_digest"] = cover["cover_digest"]
    return data


def assert_photo_cover_approvable(data: dict, *, project_id: int | None = None) -> None:
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None
    if not isinstance(cover, dict) or cover.get("workflow") != "photo_backed":
        raise PhotoCoverError("Approve is blocked until a verified photograph is used.")
    if not cover.get("selected_layout"):
        raise PhotoCoverError("Select one of the three cover variants before approving.")
    verify_source(cover.get("source"), project_id=project_id, data=data)
    ident = _approved_identity(data)
    if (cover.get("title"), cover.get("subtitle"), cover.get("author")) != (
        ident["title"],
        ident["subtitle"],
        ident["author"],
    ):
        raise PhotoCoverError("Cover text does not match the approved title, subtitle, and author.")
    variants = cover.get("variants") if isinstance(cover.get("variants"), dict) else {}
    for layout_id in LAYOUT_IDS:
        row = variants.get(layout_id) or {}
        if not row.get("png_path") or not os.path.isfile(str(row.get("png_path"))):
            raise PhotoCoverError("All three cover variants must be available.")
        if layout_id == "printed_moment" and not (row.get("quality") or {}).get("pass"):
            raise PhotoCoverError("Printed-Moment thumbnail story failed.")
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
    story = (variants.get("printed_moment") or {}).get("quality") or {}
    if story.get("findings") and "empty_photo_rectangles" in story["findings"]:
        failures.append(("abstract_cover_boxes", "Printed-Moment still contains empty or abstract photo boxes."))
    if not story.get("pass"):
        failures.append(
            (
                "printed_moment_story_failed",
                "Printed-Moment must show camera → captured event image → physical print.",
            )
        )
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


def photo_cover_public_fields(data: dict, *, project_id: int | None) -> dict[str, Any]:
    from services.ebook_pexels import pexels_public_status

    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    photo = cover.get("workflow") == "photo_backed"
    variants = []
    raw = cover.get("variants") if isinstance(cover.get("variants"), dict) else {}
    digest = str(cover.get("cover_digest") or "")
    for layout_id in LAYOUT_IDS:
        row = raw.get(layout_id) or {}
        vd = str(row.get("digest") or "")
        variants.append(
            {
                "layout_id": layout_id,
                "label": LAYOUT_LABELS[layout_id],
                "digest": vd,
                "quality_pass": bool((row.get("quality") or {}).get("pass")),
                "findings": list((row.get("quality") or {}).get("findings") or []),
                "full_url": (
                    f"/ebook-workspace/{int(project_id)}/cover-variant?layout={layout_id}&size=full&digest={vd}"
                    if project_id and vd
                    else ""
                ),
                "thumb_url": (
                    f"/ebook-workspace/{int(project_id)}/cover-variant?layout={layout_id}&size=thumb&digest={vd}"
                    if project_id and vd
                    else ""
                ),
            }
        )
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
    pexels_public = {
        **pexels_public,
        "query": cache.get("query") or "",
        "page": cache.get("page") or 1,
        "photos": public_photos(cache.get("photos")),
        "next_page": cache.get("next_page"),
    }
    src = cover.get("source") if isinstance(cover.get("source"), dict) else {}
    pexels_rec = src.get("pexels") if isinstance(src.get("pexels"), dict) else {}
    source_public = None
    if photo:
        source_public = {
            "source_type": src.get("source_type") or "",
            "filename": src.get("filename") or "",
            "license_note": src.get("license_note") or "",
            "sha256": src.get("sha256") or "",
            "width": src.get("width"),
            "height": src.get("height"),
            "orientation": src.get("orientation") or "",
            "photographer": pexels_rec.get("photographer") or "",
            "attribution": pexels_rec.get("attribution") or "",
            "page_url": pexels_rec.get("page_url") or "",
            "photo_id": pexels_rec.get("photo_id") or "",
        }
    return {
        "workflow": "photo_backed" if photo else str(cover.get("workflow") or ""),
        "photo_backed": photo,
        "source": source_public,
        "editor": cover.get("editor") if photo else default_editor(),
        "variants": variants,
        "selected_layout": selected,
        "image_digest": str(cover.get("image_digest") or src.get("sha256") or ""),
        "ai_cover": cover.get("ai_cover")
        or {
            "enabled": False,
            "configured": False,
            "label": "Optional paid feature — not configured",
        },
        "pexels": pexels_public,
        "approvable": approvable,
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


def verified_variant_asset(data: dict, *, project_id: int | None, layout: str, digest: str, size: str) -> dict[str, Any]:
    cover = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else {}
    if cover.get("workflow") != "photo_backed":
        raise PhotoCoverError("Cover variant is unavailable.")
    verify_source(cover.get("source"), project_id=project_id, data=data)
    row = ((cover.get("variants") or {}).get(layout) or {})
    if str(row.get("digest") or "").lower() != str(digest or "").strip().lower():
        raise PhotoCoverError("Cover variant digest does not match.")
    path = str(row.get("thumb_path") if size == "thumb" else row.get("png_path") or "")
    if not path or not os.path.isfile(path):
        raise PhotoCoverError("Cover variant file is missing.")
    with open(path, "rb") as fh:
        body = fh.read()
    return {"bytes": body, "mimetype": "image/png", "digest": row["digest"]}
