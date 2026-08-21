"""Local full-page ebook covers (ReportLab) — no image API calls.

Title/subtitle are drawn by the renderer. Theme art is vector illustration
matched to topic keywords (parenting / screen habits, etc.).
"""
from __future__ import annotations

import hashlib
import io
import os
import re
from typing import Any

from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as rl_canvas

from services.ebook_fonts import ensure_ebook_fonts


EVENT_PHOTO_KEYS = (
    "photo",
    "photography",
    "event",
    "dye-sub",
    "dye sub",
    "booking",
    "on-site print",
    "onsite print",
    "printer",
    "ds-rx1",
    "ds620",
)


def _theme_key(title: str, subtitle: str = "", topic: str = "", audience: str = "") -> str:
    blob = " ".join([title or "", subtitle or "", topic or "", audience or ""]).lower()
    if any(k in blob for k in EVENT_PHOTO_KEYS):
        return "event_photography"
    if any(k in blob for k in ("screen", "digital media", "tablet", "parent", "toddler", "preschool", "child")):
        return "parenting_screens"
    if any(k in blob for k in ("money", "budget", "finance", "invest")):
        return "finance"
    return "general"


def proposed_cover_prompt(
    *,
    title: str,
    subtitle: str = "",
    audience: str = "",
    topic: str = "",
) -> str:
    """Human-readable AI cover prompt for optional paid generation (approval only)."""
    theme = _theme_key(title, subtitle, topic, audience)
    if theme == "event_photography":
        return (
            f'Professional portrait ebook cover for "{title}". '
            f"Subtitle: {subtitle or 'A practical event photography guide'}. "
            f"Audience: {audience or 'new event photographers'}. "
            f"Topic: {topic or title}. "
            "Stylized event-photography story, not a business-report template: a recognizable "
            "three-quarter camera body and lens in the lower left, visually leading along a warm "
            "amber/cobalt light path toward two overlapping white-bordered take-home photographs "
            "on the right. Inside the prints: celebration lights and a decorated venue, no faces "
            "and no text in the photograph. Optional compact dye-sub printer with a print on the "
            "output tray. Visual movement from capture to print to guest delivery. Dark navy-to-"
            "charcoal field-guide background. Leave clear space for title/subtitle overlays. "
            "No brand logos, no copyrighted camera designs, no clip-art."
        )
    return (
        f'Professional portrait ebook cover for "{title}". '
        f"Subtitle: {subtitle or 'Practical guide'}. "
        f"Audience: {audience or 'general readers'}. "
        f"Topic: {topic or title}. "
        "Topic-specific photography matching this title, audience, and subject. "
        "Leave clear space for title/subtitle overlays. No text in the image. "
        "Do not use artwork or wording from any other book topic."
    )


def generate_local_cover_pdf_bytes(
    title: str,
    subtitle: str = "",
    *,
    author: str = "Digital Product Factory",
    topic: str = "",
    audience: str = "",
) -> bytes:
    """Full-bleed 8.5×11 cover with theme art + readable title hierarchy."""
    regular, bold, italic, _bi = ensure_ebook_fonts()
    buf = io.BytesIO()
    W, H = letter
    c = rl_canvas.Canvas(buf, pagesize=letter)
    c.setTitle(title or "Ebook")
    c.setAuthor(author or "Digital Product Factory")

    theme = _theme_key(title, subtitle, topic, audience)
    qa_marker = "Practical Family Guide"
    title_size = 26
    title_wrap = 28
    if theme == "event_photography":
        _draw_event_photography_bg(c, W, H)
        _reset_opaque(c)
        accent = (0.93, 0.64, 0.18)
        title_color = (1.0, 1.0, 1.0)
        sub_color = (0.93, 0.90, 0.82)
        qa_marker = "Event Photography Field Guide"
        title_size = 30
        title_wrap = 24
    elif theme == "parenting_screens":
        _draw_parenting_screens_bg(c, W, H)
        accent = (0.95, 0.78, 0.28)  # gold
        title_color = (0.06, 0.18, 0.28)
        sub_color = (0.18, 0.32, 0.38)
    else:
        _draw_general_bg(c, W, H)
        accent = (0.15, 0.55, 0.62)
        title_color = (0.08, 0.12, 0.22)
        sub_color = (0.25, 0.32, 0.40)

    # Safe content band
    margin = 48
    c.setFillColorRGB(*accent)
    c.rect(margin, H - 88, 84, 7, fill=1, stroke=0)

    c.setFillColorRGB(*title_color)
    c.setFont(bold, title_size)
    y = H - 138
    for line in _wrap_text(title or "Untitled", title_wrap):
        c.drawString(margin, y, line)
        y -= title_size + 6

    if subtitle:
        y -= 8
        c.setFillColorRGB(*sub_color)
        c.setFont(regular, 12)
        for line in _wrap_text(subtitle, 62):
            c.drawString(margin, y, line)
            y -= 16

    if audience:
        y -= 10
        c.setFont(italic, 10)
        c.setFillColorRGB(*(sub_color if theme == "event_photography" else (0.25, 0.35, 0.40)))
        for line in _wrap_text(f"For {audience}", 58):
            c.drawString(margin, y, line)
            y -= 14

    author_fill = (0.98, 0.96, 0.92) if theme == "event_photography" else (0.25, 0.35, 0.40)
    c.setFillColorRGB(*author_fill)
    c.setFont(bold if theme == "event_photography" else regular, 14 if theme == "event_photography" else 10)
    c.drawString(margin, 46, author or "Digital Product Factory")
    # QA marker — proves a ReportLab theme cover (not HTML purple shell)
    c.setFont(regular, 8)
    c.drawString(margin, 28, qa_marker)
    c.showPage()
    c.save()
    return buf.getvalue()


def _reset_opaque(c) -> None:
    """Alpha colors leave an ExtGState; clear it so later fills stay solid."""
    if hasattr(c, "setFillAlpha"):
        c.setFillAlpha(1.0)
    if hasattr(c, "setStrokeAlpha"):
        c.setStrokeAlpha(1.0)


def _ellipse(c, cx: float, cy: float, rx: float, ry: float, fill: int = 1, stroke: int = 0) -> None:
    c.saveState()
    c.translate(cx, cy)
    c.scale(max(rx, 0.01), max(ry, 0.01))
    c.circle(0, 0, 1, fill=fill, stroke=stroke)
    c.restoreState()


def _draw_event_photography_bg(c, W: float, H: float) -> None:
    """Navy-to-charcoal field guide: camera → light path → white-bordered event prints."""
    steps = 28
    for i in range(steps):
        t = i / max(steps - 1, 1)
        c.setFillColorRGB(0.045 + 0.05 * t, 0.07 + 0.03 * t, 0.14 - 0.03 * t)
        y = H * (1 - (i + 1) / steps)
        c.rect(0, y, W, H / steps + 1.5, fill=1, stroke=0)
    c.saveState()
    c.setFillColor(Color(0.18, 0.38, 0.72, alpha=0.16))
    _ellipse(c, W * 0.76, H * 0.34, 130, 88)
    c.setFillColor(Color(0.93, 0.64, 0.18, alpha=0.10))
    _ellipse(c, W * 0.36, H * 0.20, 100, 56)
    c.restoreState()
    _reset_opaque(c)
    # Ground plane so the kit reads as objects on a station, not floating geometry
    c.setFillColorRGB(0.08, 0.09, 0.12)
    floor = c.beginPath()
    floor.moveTo(18, 42)
    floor.lineTo(W - 28, 58)
    floor.lineTo(W - 12, 78)
    floor.lineTo(8, 70)
    floor.close()
    c.drawPath(floor, fill=1, stroke=0)

    _draw_capture_print_beam(c, W, H)
    _draw_compact_printer(c, 268, 70)
    _draw_event_camera(c, 28, 78)
    _draw_event_print(c, W * 0.54, H * 0.158, 210, 148, tilt=7, scene="venue")
    _draw_event_print(c, W * 0.655, H * 0.275, 188, 136, tilt=-6, scene="celebration")
    _draw_delivery_chevrons(c, W, H)
    _reset_opaque(c)


def _draw_capture_print_beam(c, W: float, H: float) -> None:
    """Warm amber/cobalt path from the lens toward the prints."""
    c.saveState()
    path = c.beginPath()
    path.moveTo(268, 148)
    path.curveTo(340, 168, 400, 230, 448, 292)
    path.lineTo(468, 268)
    path.curveTo(410, 210, 348, 150, 276, 128)
    path.close()
    c.setFillColor(Color(0.93, 0.64, 0.18, alpha=0.42))
    c.drawPath(path, fill=1, stroke=0)
    inner = c.beginPath()
    inner.moveTo(274, 144)
    inner.curveTo(346, 164, 406, 224, 452, 280)
    inner.lineTo(460, 272)
    inner.curveTo(408, 218, 350, 156, 278, 134)
    inner.close()
    c.setFillColor(Color(0.35, 0.55, 0.88, alpha=0.28))
    c.drawPath(inner, fill=1, stroke=0)
    c.restoreState()
    _reset_opaque(c)
    core = c.beginPath()
    core.moveTo(278, 142)
    core.curveTo(348, 162, 408, 220, 450, 274)
    core.lineTo(456, 266)
    core.curveTo(412, 214, 352, 156, 282, 136)
    core.close()
    c.setFillColorRGB(0.93, 0.64, 0.18)
    c.drawPath(core, fill=1, stroke=0)


def _draw_delivery_chevrons(c, W: float, H: float) -> None:
    c.setFillColorRGB(0.93, 0.64, 0.18)
    for x, y in ((292, 154), (342, 186), (392, 226)):
        p = c.beginPath()
        p.moveTo(x, y)
        p.lineTo(x + 14, y + 8)
        p.lineTo(x, y + 16)
        p.lineTo(x + 5, y + 8)
        p.close()
        c.drawPath(p, fill=1, stroke=0)


def _draw_event_print(c, x: float, y: float, w: float, h: float, *, tilt: float, scene: str) -> None:
    """Physical take-home 4×6 with a thick white border. No text inside the image."""
    c.saveState()
    c.translate(x + w / 2, y + h / 2)
    c.rotate(tilt)
    bottom_mat = 22
    inset_x, inset_top = 12, 12
    c.setFillColorRGB(0.05, 0.04, 0.04)
    c.roundRect(-w / 2 + 6, -h / 2 - 7, w, h, 3, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.roundRect(-w / 2, -h / 2, w, h, 3, fill=1, stroke=0)
    c.setStrokeColorRGB(0.92, 0.92, 0.93)
    c.setLineWidth(1.2)
    c.roundRect(-w / 2, -h / 2, w, h, 3, fill=0, stroke=1)
    ix = -w / 2 + inset_x
    iy = -h / 2 + bottom_mat
    iw = w - 2 * inset_x
    ih = h - inset_top - bottom_mat
    c.saveState()
    clip = c.beginPath()
    clip.rect(ix, iy, iw, ih)
    c.clipPath(clip, stroke=0)
    if scene == "venue":
        c.setFillColorRGB(0.10, 0.12, 0.20)
        c.rect(ix, iy, iw, ih, fill=1, stroke=0)
        c.setFillColorRGB(0.16, 0.14, 0.22)
        c.rect(ix, iy + ih * 0.38, iw, ih * 0.62, fill=1, stroke=0)
        c.setFillColorRGB(0.38, 0.26, 0.14)
        c.rect(ix, iy, iw, ih * 0.38, fill=1, stroke=0)
        c.setFillColorRGB(0.12, 0.10, 0.16)
        c.roundRect(ix + 10, iy + ih * 0.42, 36, ih * 0.50, 4, fill=1, stroke=0)
        c.roundRect(ix + iw / 2 - 18, iy + ih * 0.46, 36, ih * 0.46, 4, fill=1, stroke=0)
        c.roundRect(ix + iw - 46, iy + ih * 0.42, 36, ih * 0.50, 4, fill=1, stroke=0)
        c.setFillColorRGB(0.93, 0.64, 0.18)
        _ellipse(c, ix + iw * 0.5, iy + ih * 0.22, 28, 8)
        c.setFillColorRGB(0.98, 0.82, 0.42)
        _ellipse(c, ix + iw * 0.5, iy + ih * 0.88, 16, 5)
        c.setFillColorRGB(0.98, 0.76, 0.36)
        for n in range(7):
            c.circle(ix + 14 + n * (iw - 28) / 6, iy + ih * 0.74, 3.2, fill=1, stroke=0)
        c.setFillColorRGB(0.04, 0.04, 0.06)
        for sx, sw, sh in ((ix + 10, 20, 26), (ix + 34, 22, 32), (ix + 60, 18, 24), (ix + 84, 21, 28)):
            if sx + sw < ix + iw - 8:
                c.roundRect(sx, iy + 4, sw, sh, 6, fill=1, stroke=0)
    else:
        c.setFillColorRGB(0.08, 0.10, 0.22)
        c.rect(ix, iy, iw, ih, fill=1, stroke=0)
        c.setFillColorRGB(0.18, 0.28, 0.62)
        _ellipse(c, ix + iw * 0.46, iy + ih * 0.62, 30, 16)
        c.setStrokeColorRGB(0.72, 0.58, 0.92)
        c.setLineWidth(2.2)
        arch = c.beginPath()
        arch.moveTo(ix + 16, iy + ih * 0.42)
        arch.curveTo(ix + iw * 0.35, iy + ih * 0.92, ix + iw * 0.65, iy + ih * 0.92, ix + iw - 16, iy + ih * 0.42)
        c.drawPath(arch, fill=0, stroke=1)
        lights = (
            (ix + 18, iy + ih * 0.70, 5),
            (ix + 42, iy + ih * 0.82, 7),
            (ix + 68, iy + ih * 0.68, 4.5),
            (ix + 92, iy + ih * 0.78, 6),
            (ix + iw * 0.58, iy + ih * 0.52, 9),
            (ix + iw * 0.76, iy + ih * 0.64, 4),
        )
        for lx, ly, r in lights:
            c.setFillColorRGB(0.98, 0.78, 0.38)
            c.circle(lx, ly, r, fill=1, stroke=0)
        c.setFillColorRGB(0.04, 0.04, 0.06)
        c.roundRect(ix + 10, iy + 4, 24, 34, 8, fill=1, stroke=0)
        c.roundRect(ix + 38, iy + 4, 22, 38, 8, fill=1, stroke=0)
        c.roundRect(ix + 64, iy + 4, 24, 30, 8, fill=1, stroke=0)
    c.restoreState()
    c.restoreState()


def _draw_compact_printer(c, x: float, y: float) -> None:
    """Generic compact dye-sub motif with a print on the output tray. No brand marks."""
    c.setFillColorRGB(0.05, 0.05, 0.06)
    c.roundRect(x + 6, y + 8, 108, 18, 3, fill=1, stroke=0)
    c.setFillColorRGB(0.22, 0.23, 0.27)
    c.roundRect(x, y + 24, 118, 48, 6, fill=1, stroke=0)
    c.setFillColorRGB(0.32, 0.33, 0.38)
    c.roundRect(x + 8, y + 52, 102, 16, 3, fill=1, stroke=0)
    c.setFillColorRGB(0.10, 0.11, 0.14)
    c.rect(x + 18, y + 46, 82, 6, fill=1, stroke=0)
    c.setFillColorRGB(0.93, 0.64, 0.18)
    c.circle(x + 22, y + 62, 3.4, fill=1, stroke=0)
    c.setFillColorRGB(0.18, 0.19, 0.22)
    c.roundRect(x + 14, y, 78, 28, 3, fill=1, stroke=0)
    c.saveState()
    c.translate(x + 28, y + 10)
    c.rotate(8)
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, 52, 38, fill=1, stroke=0)
    c.setFillColorRGB(0.12, 0.16, 0.28)
    c.rect(5, 10, 42, 24, fill=1, stroke=0)
    c.setFillColorRGB(0.95, 0.74, 0.34)
    c.circle(26, 22, 3.6, fill=1, stroke=0)
    c.restoreState()


def _draw_event_camera(c, x: float, y: float) -> None:
    """Recognizable three-quarter camera: grip, body, pentaprism, cylindrical lens, glass."""
    c.saveState()
    c.translate(x, y)
    c.scale(1.18, 1.18)
    c.saveState()
    c.setFillColor(Color(0, 0, 0, alpha=0.32))
    _ellipse(c, 118, 16, 96, 14)
    c.restoreState()
    _reset_opaque(c)
    # Rear / grip plane
    c.setFillColorRGB(0.18, 0.19, 0.22)
    grip = c.beginPath()
    grip.moveTo(6, 16)
    grip.lineTo(38, 12)
    grip.lineTo(44, 92)
    grip.lineTo(4, 98)
    grip.close()
    c.drawPath(grip, fill=1, stroke=0)
    c.setFillColorRGB(0.28, 0.29, 0.32)
    c.roundRect(10, 30, 16, 52, 4, fill=1, stroke=0)
    # Body side plane
    c.setFillColorRGB(0.34, 0.35, 0.40)
    side = c.beginPath()
    side.moveTo(38, 12)
    side.lineTo(128, 22)
    side.lineTo(132, 84)
    side.lineTo(44, 92)
    side.close()
    c.drawPath(side, fill=1, stroke=0)
    # Body front plane
    c.setFillColorRGB(0.50, 0.51, 0.56)
    front = c.beginPath()
    front.moveTo(128, 22)
    front.lineTo(176, 32)
    front.lineTo(178, 80)
    front.lineTo(132, 84)
    front.close()
    c.drawPath(front, fill=1, stroke=0)
    c.setStrokeColorRGB(0.82, 0.83, 0.88)
    c.setLineWidth(1.6)
    c.line(128, 24, 174, 34)
    # Top plate + pentaprism + hot shoe
    c.setFillColorRGB(0.42, 0.43, 0.48)
    top = c.beginPath()
    top.moveTo(44, 90)
    top.lineTo(132, 82)
    top.lineTo(140, 106)
    top.lineTo(52, 112)
    top.close()
    c.drawPath(top, fill=1, stroke=0)
    c.setFillColorRGB(0.30, 0.31, 0.36)
    prism = c.beginPath()
    prism.moveTo(74, 106)
    prism.lineTo(122, 100)
    prism.lineTo(114, 128)
    prism.lineTo(82, 132)
    prism.close()
    c.drawPath(prism, fill=1, stroke=0)
    c.setFillColorRGB(0.08, 0.08, 0.10)
    c.roundRect(90, 128, 18, 7, 1, fill=1, stroke=0)
    c.setFillColorRGB(0.22, 0.23, 0.26)
    c.circle(124, 108, 9, fill=1, stroke=0)
    c.setFillColorRGB(0.40, 0.41, 0.45)
    c.circle(124, 108, 5, fill=1, stroke=0)
    c.setFillColorRGB(0.93, 0.64, 0.18)
    c.circle(146, 106, 6, fill=1, stroke=0)
    # Cylindrical lens barrel aimed at the prints (not rings floating without a body)
    c.setFillColorRGB(0.16, 0.17, 0.20)
    c.roundRect(168, 36, 86, 48, 12, fill=1, stroke=0)
    c.setStrokeColorRGB(0.30, 0.31, 0.35)
    c.setLineWidth(2.0)
    for gx in (186, 202, 218):
        c.line(gx, 40, gx, 80)
    c.setFillColorRGB(0.12, 0.13, 0.16)
    _ellipse(c, 254, 60, 22, 26)
    c.setStrokeColorRGB(0.55, 0.56, 0.60)
    c.setLineWidth(2.2)
    c.saveState()
    c.translate(254, 60)
    c.scale(22, 26)
    c.circle(0, 0, 1, fill=0, stroke=1)
    c.restoreState()
    c.setFillColorRGB(0.12, 0.24, 0.42)
    _ellipse(c, 254, 60, 15, 18)
    c.setFillColorRGB(0.04, 0.07, 0.12)
    _ellipse(c, 254, 60, 8, 10)
    c.setFillColorRGB(0.86, 0.90, 0.96)
    _ellipse(c, 248, 66, 3.2, 4.0)
    c.setStrokeColorRGB(0.10, 0.10, 0.12)
    c.setLineWidth(1.4)
    c.line(38, 14, 44, 90)
    c.restoreState()


def _draw_parenting_screens_bg(c, W: float, H: float) -> None:
    # Warm teal/blue wash
    c.setFillColorRGB(0.90, 0.95, 0.96)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColorRGB(0.18, 0.52, 0.58)
    c.rect(0, 0, W, H * 0.38, fill=1, stroke=0)
    c.setFillColorRGB(0.14, 0.42, 0.48)
    c.rect(0, 0, W, H * 0.22, fill=1, stroke=0)

    # Soft gold arc
    c.setStrokeColorRGB(0.95, 0.78, 0.28)
    c.setLineWidth(3)
    c.circle(W * 0.78, H * 0.22, 90, fill=0, stroke=1)

    # Simple parent + child silhouettes (abstract, friendly)
    c.setFillColorRGB(0.98, 0.96, 0.92)
    # Parent torso
    c.circle(W * 0.28, H * 0.20, 22, fill=1, stroke=0)
    c.roundRect(W * 0.22, H * 0.08, 48, 70, 12, fill=1, stroke=0)
    # Child
    c.circle(W * 0.42, H * 0.16, 16, fill=1, stroke=0)
    c.roundRect(W * 0.38, H * 0.07, 32, 48, 10, fill=1, stroke=0)
    # Tablet resting nearby
    c.setFillColorRGB(0.12, 0.18, 0.24)
    c.roundRect(W * 0.55, H * 0.10, 70, 48, 6, fill=1, stroke=0)
    c.setFillColorRGB(0.55, 0.78, 0.82)
    c.roundRect(W * 0.57, H * 0.13, 54, 34, 3, fill=1, stroke=0)


def _draw_general_bg(c, W: float, H: float) -> None:
    c.setFillColorRGB(0.94, 0.96, 0.98)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColorRGB(0.12, 0.28, 0.42)
    c.rect(0, 0, W, H * 0.30, fill=1, stroke=0)
    c.setFillColorRGB(0.15, 0.55, 0.62)
    c.rect(0, H * 0.30, W, 8, fill=1, stroke=0)


def _wrap_text(text: str, max_chars: int) -> list[str]:
    words = re.findall(r"\S+", text or "")
    lines: list[str] = []
    cur: list[str] = []
    for w in words:
        trial = (" ".join(cur + [w])).strip()
        if cur and len(trial) > max_chars:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return lines or [""]


def cover_design_from_local(
    *,
    title: str,
    subtitle: str,
    author: str,
    package_id: str,
    topic: str = "",
    audience: str = "",
    fields: dict | None = None,
) -> dict[str, Any]:
    """Minimal cover_design dict compatible with cover_agent consumers."""
    from services.ebook_package import EXPORTS_DIR

    pdf_bytes = generate_local_cover_pdf_bytes(
        title,
        subtitle,
        author=author,
        topic=topic,
        audience=audience,
    )
    pkg_dir = os.path.join(EXPORTS_DIR, package_id)
    os.makedirs(pkg_dir, exist_ok=True)
    cover_pdf_path = os.path.join(pkg_dir, "cover_local.pdf")
    with open(cover_pdf_path, "wb") as fh:
        fh.write(pdf_bytes)

    # Rasterize page 1 for preview/img_cover.png when possible (no paid API)
    cover_png = os.path.join(pkg_dir, "img_cover.png")
    try:
        import fitz

        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        pix = doc[0].get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
        pix.save(cover_png)
        doc.close()
    except Exception:
        cover_png = ""

    prompt = proposed_cover_prompt(
        title=title, subtitle=subtitle, audience=audience, topic=topic or title
    )
    return {
        "title": title,
        "subtitle": subtitle,
        "author": author,
        "package_id": package_id,
        "product_type": "ebook",
        "theme": _theme_key(title, subtitle, topic, audience),
        "cover_prompt": prompt,
        "image_path": cover_png,
        "local_cover_pdf": cover_pdf_path,
        "preview_html": "",
        "fields": fields or {},
        "local_generated": True,
        "paid_api_required": False,
        "cover_digest": hashlib.sha256(pdf_bytes).hexdigest(),
        "qa_marker": (
            "Event Photography Field Guide"
            if _theme_key(title, subtitle, topic, audience) == "event_photography"
            else "Practical Family Guide"
            if _theme_key(title, subtitle, topic, audience) == "parenting_screens"
            else str(title or "Ebook")[:48]
        ),
    }


GENERIC_COVER_MARKERS = (
    "Practical Family Guide",
    "AI Model Selection Guide",
    "#1 bestseller",
    "as seen on",
    "new york times",
    "guaranteed income",
)
INVENTED_CLAIM_RE = re.compile(
    r"\b(#1\s+bestseller|as seen on|new york times|guaranteed (?:income|results)|award[- ]winning)\b",
    re.I,
)


def cover_bytes_digest(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes or b"").hexdigest()


def generic_or_mismatched_cover_reason(
    cover: dict | None,
    *,
    title: str,
    subtitle: str = "",
    author: str = "",
    topic: str = "",
) -> str | None:
    """Return a FAIL reason if the cover is missing, generic, or mismatched."""
    if not isinstance(cover, dict) or not cover:
        return "missing_cover"
    cover_title = str(cover.get("title") or "").strip()
    cover_author = str(cover.get("author") or "").strip()
    if cover_title and title and cover_title.strip() != str(title).strip():
        return "cover_title_mismatch"
    if cover_author and author and cover_author.strip() != str(author).strip():
        return "cover_author_mismatch"
    if cover.get("workflow") == "photo_backed":
        source = cover.get("source") if isinstance(cover.get("source"), dict) else None
        if not source or not str(source.get("sha256") or "").strip():
            return "missing_cover_photograph"
        return None
    prompt = " ".join(
        [
            str(cover.get("image_prompt") or ""),
            str(cover.get("cover_prompt") or ""),
        ]
    )
    has_file = bool(
        (cover.get("image_path") and os.path.isfile(str(cover.get("image_path"))))
        or (cover.get("local_cover_pdf") and os.path.isfile(str(cover.get("local_cover_pdf"))))
    )
    if prompt.strip() and not has_file and cover.get("use_ai_image"):
        return "prompt_only_cover"
    expected_theme = _theme_key(title, subtitle, topic, "")
    actual_theme = str(cover.get("theme") or "")
    if expected_theme == "event_photography" and actual_theme in {"parenting_screens", "general", ""}:
        return "generic_or_mismatched_cover"
    blob = " ".join(
        [
            str(cover.get("qa_marker") or ""),
            str(cover.get("cover_prompt") or ""),
            str(cover.get("subtitle") or ""),
        ]
    )
    if expected_theme == "event_photography" and "Practical Family Guide" in blob:
        return "generic_or_mismatched_cover"
    if INVENTED_CLAIM_RE.search(blob):
        return "invented_cover_claim"
    if actual_theme == "parenting_screens" and expected_theme == "event_photography":
        return "generic_or_mismatched_cover"
    own = f"{title} {subtitle} {topic}".lower()
    combined = f"{prompt} {blob}".lower()
    if "black history" not in own and "black history" in combined:
        return "cross_topic_prompt_contamination"
    return None
