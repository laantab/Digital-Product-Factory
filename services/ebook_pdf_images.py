"""PDF-only image helpers: compress, crop white frames, near-dup skip, full-bleed cover.

Never mutates source files on disk. Zero paid/external calls.
"""
from __future__ import annotations

import base64
import hashlib
import io
import os
from typing import Iterable

from PIL import Image

LETTER_PT = (612.0, 792.0)
MAX_INTERIOR_PX = 1100
INTERIOR_JPEG_QUALITY = 78
COVER_JPEG_QUALITY = 86


def _open_rgb(path: str) -> Image.Image:
    im = Image.open(path)
    if im.mode in {"RGBA", "LA", "P"}:
        bg = Image.new("RGB", im.size, (255, 255, 255))
        converted = im.convert("RGBA")
        bg.paste(converted, mask=converted.split()[-1] if converted.mode == "RGBA" else None)
        return bg
    return im.convert("RGB")


def crop_white_border(im: Image.Image, *, thresh: int = 248, min_crop: int = 2) -> Image.Image:
    """Trim a uniform near-white frame without changing the photograph itself."""
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()

    def white_row(y: int) -> bool:
        step = max(1, w // 80)
        return all(px[x, y][0] >= thresh and px[x, y][1] >= thresh and px[x, y][2] >= thresh for x in range(0, w, step))

    def white_col(x: int) -> bool:
        step = max(1, h // 80)
        return all(px[x, y][0] >= thresh and px[x, y][1] >= thresh and px[x, y][2] >= thresh for y in range(0, h, step))

    top = 0
    while top < h // 4 and white_row(top):
        top += 1
    bottom = h - 1
    while bottom > (h * 3) // 4 and white_row(bottom):
        bottom -= 1
    left = 0
    while left < w // 4 and white_col(left):
        left += 1
    right = w - 1
    while right > (w * 3) // 4 and white_col(right):
        right -= 1
    if top < min_crop and (h - 1 - bottom) < min_crop and left < min_crop and (w - 1 - right) < min_crop:
        return rgb
    box = (left, top, right + 1, bottom + 1)
    if box[2] - box[0] < w * 0.7 or box[3] - box[1] < h * 0.7:
        return rgb
    return rgb.crop(box)


def average_hash(im: Image.Image, size: int = 8) -> int:
    g = im.convert("L").resize((size, size), Image.Resampling.BILINEAR)
    pixels = list(g.getdata())
    avg = sum(pixels) / max(len(pixels), 1)
    bits = 0
    for i, value in enumerate(pixels):
        if value >= avg:
            bits |= 1 << i
    return bits


def hamming_distance(a: int, b: int) -> int:
    return (int(a) ^ int(b)).bit_count()


def is_near_duplicate(phash: int, seen: Iterable[int], *, max_distance: int = 14) -> bool:
    return any(hamming_distance(phash, prev) <= max_distance for prev in seen)


def jpeg_bytes(im: Image.Image, *, quality: int, max_px: int | None = None) -> bytes:
    rgb = im.convert("RGB")
    if max_px:
        w, h = rgb.size
        longest = max(w, h)
        if longest > max_px:
            scale = max_px / float(longest)
            rgb = rgb.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    rgb.save(buf, format="JPEG", quality=quality, optimize=True, progressive=True)
    return buf.getvalue()


def jpeg_data_uri_from_path(
    path: str,
    *,
    quality: int = INTERIOR_JPEG_QUALITY,
    max_px: int = MAX_INTERIOR_PX,
) -> tuple[str, int, str]:
    """Return (data_uri, average_hash, sha256) for PDF embedding. Source file unchanged."""
    im = _open_rgb(path)
    phash = average_hash(im)
    data = jpeg_bytes(im, quality=quality, max_px=max_px)
    digest = hashlib.sha256(data).hexdigest()
    uri = "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")
    return uri, phash, digest


def full_bleed_cover_pdf_bytes(path: str) -> bytes:
    """Letter-size PDF page with the photograph filling the trim. No white frame."""
    import fitz

    im = crop_white_border(_open_rgb(path))
    page_w, page_h = LETTER_PT
    page_aspect = page_w / page_h
    w, h = im.size
    img_aspect = w / max(h, 1)
    if img_aspect > page_aspect:
        new_w = int(h * page_aspect)
        left = max(0, (w - new_w) // 2)
        im = im.crop((left, 0, left + new_w, h))
    elif img_aspect < page_aspect:
        new_h = int(w / page_aspect)
        top = max(0, (h - new_h) // 2)
        im = im.crop((0, top, w, top + new_h))
    jpeg = jpeg_bytes(im, quality=COVER_JPEG_QUALITY, max_px=2200)
    doc = fitz.open()
    page = doc.new_page(width=page_w, height=page_h)
    page.insert_image(page.rect, stream=jpeg, keep_proportion=False)
    out = doc.tobytes()
    doc.close()
    return out


def _stamp_fontname(page, fontfile: str | None) -> str:
    """Register the embedded body TTF on this page; fall back to Helvetica only if missing."""
    if not fontfile or not os.path.isfile(fontfile):
        return "helv"
    try:
        page.insert_font(fontname="EbookSans", fontfile=fontfile)
        return "EbookSans"
    except Exception:
        return "helv"


def stamp_running_matter(
    pdf_bytes: bytes,
    *,
    title: str,
    author: str = "",
) -> bytes:
    """Add running header + page numbers to interior pages. Cover (page 1) is skipped."""
    import fitz

    if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
        return pdf_bytes
    try:
        from services.ebook_fonts import ebook_stamp_fontfile

        fontfile = ebook_stamp_fontfile()
    except Exception:
        fontfile = None
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    header = (title or "").strip()
    if len(header) > 68:
        header = header[:65].rstrip() + "…"
    author_bit = (author or "").strip()
    try:
        for i, page in enumerate(doc):
            if i == 0:
                continue
            fontname = _stamp_fontname(page, fontfile)
            rect = page.rect
            header_rect = fitz.Rect(54, 28, rect.width - 54, 46)
            page.insert_textbox(
                header_rect,
                header,
                fontsize=8,
                fontname=fontname,
                color=(0.38, 0.42, 0.48),
                align=0,
            )
            if author_bit:
                page.insert_textbox(
                    header_rect,
                    author_bit[:40],
                    fontsize=8,
                    fontname=fontname,
                    color=(0.38, 0.42, 0.48),
                    align=2,
                )
            page.draw_line(
                fitz.Point(54, 48),
                fitz.Point(rect.width - 54, 48),
                color=(0.86, 0.89, 0.91),
                width=0.4,
            )
            footer_rect = fitz.Rect(54, rect.height - 48, rect.width - 54, rect.height - 28)
            page.insert_textbox(
                footer_rect,
                str(i + 1),
                fontsize=9,
                fontname=fontname,
                color=(0.38, 0.42, 0.48),
                align=1,
            )
        return doc.tobytes()
    except Exception:
        return pdf_bytes
    finally:
        doc.close()
