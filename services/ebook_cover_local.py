"""Local full-page ebook covers (ReportLab) — no image API calls.

Title/subtitle are drawn by the renderer. Theme art is vector illustration
matched to topic keywords (parenting / screen habits, etc.).
"""
from __future__ import annotations

import io
import os
import re
from typing import Any

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas as rl_canvas

from services.ebook_fonts import ensure_ebook_fonts


def _theme_key(title: str, subtitle: str = "", topic: str = "", audience: str = "") -> str:
    blob = " ".join([title or "", subtitle or "", topic or "", audience or ""]).lower()
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
    return (
        f'Professional portrait ebook cover for "{title}". '
        f"Subtitle: {subtitle or 'Practical guide'}. "
        f"Audience: {audience or 'general readers'}. "
        f"Topic: {topic or title}. "
        "Warm parenting scene: diverse parent and young child interacting together "
        "while a tablet rests nearby, communicating balance, connection, learning, "
        "and healthy screen habits. Inviting blue, teal, gold, and warm neutrals. "
        "Trustworthy, modern, practical, supportive — not clinical or judgmental. "
        "Leave clear space for title/subtitle overlays. No text in the image."
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
    if theme == "parenting_screens":
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
    c.rect(margin, H - 96, 72, 6, fill=1, stroke=0)

    c.setFillColorRGB(*title_color)
    c.setFont(bold, 26)
    y = H - 150
    for line in _wrap_text(title or "Untitled", 28):
        c.drawString(margin, y, line)
        y -= 32

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
        c.setFillColorRGB(0.25, 0.35, 0.40)
        c.drawString(margin, y, f"For {audience}")

    c.setFillColorRGB(0.25, 0.35, 0.40)
    c.setFont(regular, 10)
    c.drawString(margin, 42, author or "Digital Product Factory")
    # QA marker — proves a ReportLab theme cover (not HTML purple shell)
    c.setFont(regular, 8)
    c.drawString(margin, 28, "Practical Family Guide")
    c.showPage()
    c.save()
    return buf.getvalue()


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
    }
