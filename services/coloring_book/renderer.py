"""PDF renderer for Coloring Book — embeds line-art images as printable pages."""
from __future__ import annotations

import io
import math
import os
import random
from dataclasses import dataclass

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from services.coloring_book.builder import ColoringBookResult, ColoringPageResult

_MARGIN_IN = 0.4  # ~0.35–0.5" safe margins on US Letter
_CAPTION_PT = 10.0
_TOPIC_PT = 12.0
# Fill the available coloring box (contain/fit — no stretch, no forced downscale)
_IMAGE_SCALE = 1.0
# Target coloring area ≈ 7.5" × 10" on US Letter (≥80% of page)
_COLORING_TARGET_W_IN = 7.5
_COLORING_TARGET_H_IN = 10.0


@dataclass
class ColoringBookLayoutInfo:
    render_engine: str = "coloring_book_direct"
    page_count: int = 0
    image_pages: int = 0
    text_pages: int = 0
    cover_page_count: int = 0


def _paint_white_page(pdf: canvas.Canvas) -> None:
    page_w, page_h = letter
    pdf.setFillColor(colors.white)
    pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)


def _draw_centered_text(
    pdf: canvas.Canvas,
    x_center: float,
    y_baseline: float,
    text: str,
    *,
    font_name: str = "Helvetica",
    font_size: float = 10,
) -> None:
    pdf.setFillColor(colors.black)
    pdf.setFont(font_name, font_size)
    pdf.drawCentredString(x_center, y_baseline, text)


def _fit_image_to_box(
    img_path: str, *, box_w: float, box_h: float
) -> tuple[float, float, float, float]:
    """Return (draw_x, draw_y, draw_w, draw_h) to fit image within box, centered."""
    try:
        with PILImage.open(img_path) as img:
            iw, ih = img.size
    except Exception:  # noqa: BLE001
        return 0, 0, box_w, box_h
    scale = min(box_w / iw, box_h / ih) * _IMAGE_SCALE
    draw_w = iw * scale
    draw_h = ih * scale
    draw_x = (box_w - draw_w) / 2.0
    draw_y = (box_h - draw_h) / 2.0
    return draw_x, draw_y, draw_w, draw_h


# ---------------------------------------------------------------------------
# Local procedural line-art renderer — no AI required
# ---------------------------------------------------------------------------

def _draw_line_art(
    pdf: canvas.Canvas,
    topic: str,
    line_art_prompt: str,
    box_x: float,
    box_y: float,
    box_w: float,
    box_h: float,
    age_group: str = "",
    art_style: str = "",
) -> None:
    """
    Draw a themed line-art illustration using ReportLab primitives.
    Falls back gracefully if the theme is not recognized.
    """
    topic_lower = topic.lower()
    prompt_lower = line_art_prompt.lower()
    combined = f"{topic_lower} {prompt_lower}"
    theme = f"{topic} {line_art_prompt}"

    is_kids = any(w in age_group.lower() for w in ["kids", "children", "6-8", "8-10", "all ages"])
    is_adult = "adult" in age_group.lower()
    is_cartoon = any(w in art_style.lower() for w in ["cartoon", "cute", "bold"])
    is_realistic = any(w in art_style.lower() for w in ["realistic", "detailed adult"])

    # Line weight
    if is_adult or is_realistic:
        lw = 0.8
        detail = "detailed"
    elif is_kids:
        lw = 1.4
        detail = "simple"
    else:
        lw = 1.0
        detail = "medium"

    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(lw)
    pdf.setFillColor(colors.white)

    cx = box_x + box_w / 2
    cy = box_y + box_h / 2

    # ── Superhero / action theme ──────────────────────────────────────────
    if any(kw in combined for kw in [
        "volt", "hero", "power", "captain", "warrior", "guardian",
        "lightning", "thunder", "storm", "strike", "force", "superhero",
        "energy shield", "lightning bolt", "villain", "flying", "skyline",
    ]):
        _draw_superhero(pdf, cx, cy, box_w, box_h, topic, lw, detail, is_cartoon)

    # ── Dragon / fantasy creature ───────────────────────────────────────
    elif any(kw in combined for kw in ["dragon", "unicorn", "wizard", "fairy", "castle", "knight", "mermaid", "enchanted"]):
        _draw_fantasy(pdf, cx, cy, box_w, box_h, topic, lw, detail)

    # ── Nature / animals ────────────────────────────────────────────────
    elif any(kw in combined for kw in [
        "lion", "tiger", "bear", "wolf", "fox", "deer", "rabbit",
        "bird", "owl", "fish", "dolphin", "sea turtle", "animal",
        "wildlife", "nature", "forest", "jungle", "ocean", "desert",
        "flower", "tree", "garden", "butterfly", "botanical",
    ]):
        _draw_animal(pdf, cx, cy, box_w, box_h, topic, lw, detail, is_realistic)

    # ── Vehicle / transport ─────────────────────────────────────────────
    elif any(kw in combined for kw in ["car", "truck", "plane", "boat", "motorcycle", "vehicle", "train", "race", "rocket"]):
        _draw_vehicle(pdf, cx, cy, box_w, box_h, topic, lw, detail)

    # ── Mandala / geometric / adult pattern ─────────────────────────────
    elif any(kw in combined for kw in [
        "mandala", "pattern", "geometric", "intricate", "celtic",
        "decorative", "abstract", "floral element", "architectural",
        "complex", "detailed", "adult",
    ]):
        _draw_mandala(pdf, cx, cy, min(box_w, box_h) * 0.85, lw)

    # ── Generic fallback ─────────────────────────────────────────────────
    else:
        _draw_generic_scene(pdf, box_x, box_y, box_w, box_h, topic, lw, detail, is_cartoon)


def _draw_superhero(
    pdf: canvas.Canvas, cx: float, cy: float,
    bw: float, bh: float, topic: str,
    lw: float, detail: str, is_cartoon: bool,
) -> None:
    """Draw a superhero/action themed illustration."""
    scale = min(bw, bh) * 0.42

    # Body (dynamic pose)
    pdf.setLineWidth(lw)
    # Torso
    pdf.setStrokeColor(colors.black)
    pdf.setFillColor(colors.white)
    # Draw heroic figure silhouette
    head_r = scale * 0.13
    head_cx, head_cy = cx, cy + scale * 0.35
    # Head circle
    pdf.circle(head_cx, head_cy, head_r, stroke=1, fill=0)
    # Eyes
    pdf.setLineWidth(lw * 0.6)
    pdf.line(head_cx - head_r * 0.35, head_cy + head_r * 0.05,
             head_cx - head_r * 0.1, head_cy + head_r * 0.05)
    pdf.line(head_cx + head_r * 0.1, head_cy + head_r * 0.05,
             head_cx + head_r * 0.35, head_cy + head_r * 0.05)
    # Smile
    pdf.arc(head_cx - head_r * 0.3, head_cy - head_r * 0.25,
            head_cx + head_r * 0.3, head_cy + head_r * 0.1, 20, 160)
    pdf.setLineWidth(lw)
    # Neck
    pdf.line(head_cx, head_cy - head_r, head_cx, head_cy - head_r * 1.2)
    # Torso
    pdf.line(head_cx, head_cy - head_r * 1.2, head_cx, cy - scale * 0.25)
    # Arms in power pose
    pdf.line(head_cx, cy - scale * 0.1, cx - scale * 0.45, cy + scale * 0.3)
    pdf.line(head_cx, cy - scale * 0.1, cx + scale * 0.4, cy + scale * 0.15)
    # Legs
    pdf.line(head_cx, cy - scale * 0.25, cx - scale * 0.2, cy - scale * 0.6)
    pdf.line(head_cx, cy - scale * 0.25, cx + scale * 0.25, cy - scale * 0.6)
    # Emblem on chest
    pdf.setLineWidth(lw * 0.8)
    pdf.setStrokeColor(colors.black)
    pdf.circle(cx, cy + scale * 0.05, head_r * 0.55, stroke=1, fill=0)
    # Lightning bolt emblem
    bolt_cx = cx
    bolt_cy = cy + scale * 0.05
    bolt_h = head_r * 0.5
    bolt_w = bolt_h * 0.4
    pdf.setLineWidth(lw * 0.9)
    pdf.setFillColor(colors.HexColor("#F3F4F6"))
    pts = [
        (bolt_cx + bolt_w * 0.5, bolt_cy + bolt_h * 0.5),
        (bolt_cx - bolt_w * 0.5, bolt_cy + bolt_h * 0.1),
        (bolt_cx, bolt_cy + bolt_h * 0.1),
        (bolt_cx - bolt_w * 0.5, bolt_cy - bolt_h * 0.5),
        (bolt_cx + bolt_w * 0.5, bolt_cy - bolt_h * 0.1),
        (bolt_cx, bolt_cy - bolt_h * 0.1),
    ]
    _polygon(pdf, pts, stroke=1, fill=0)
    # Lightning sparks
    pdf.setLineWidth(lw * 0.6)
    for angle_deg, length in [(30, scale * 0.15), (150, scale * 0.15), (270, scale * 0.15),
                               (60, scale * 0.1), (120, scale * 0.1)]:
        angle = math.radians(angle_deg)
        ex = bolt_cx + math.cos(angle) * length
        ey = bolt_cy + math.sin(angle) * length
        pdf.line(bolt_cx, bolt_cy, ex, ey)
    # City skyline in background
    if detail != "simple":
        pdf.setLineWidth(lw * 0.5)
        buildings = [
            (cx - scale * 0.85, cy - scale * 0.7, scale * 0.12, scale * 0.35),
            (cx - scale * 0.68, cy - scale * 0.7, scale * 0.1, scale * 0.25),
            (cx - scale * 0.52, cy - scale * 0.7, scale * 0.15, scale * 0.5),
            (cx + scale * 0.52, cy - scale * 0.7, scale * 0.1, scale * 0.2),
            (cx + scale * 0.68, cy - scale * 0.7, scale * 0.14, scale * 0.4),
            (cx + scale * 0.88, cy - scale * 0.7, scale * 0.12, scale * 0.3),
        ]
        for bx, by, bw_, bh_ in buildings:
            pdf.rect(bx, by, bw_, bh_, stroke=1, fill=0)
            # Windows
            wx = bx + bw_ * 0.2
            while wx < bx + bw_ * 0.85:
                wy = by + bh_ * 0.15
                while wy < by + bh_ * 0.85:
                    pdf.rect(wx, wy, bw_ * 0.2, bh_ * 0.1, stroke=1, fill=0)
                    wy += bh_ * 0.2
                wx += bw_ * 0.3


def _draw_fantasy(
    pdf: canvas.Canvas, cx: float, cy: float,
    bw: float, bh: float, topic: str, lw: float, detail: str,
) -> None:
    """Draw a fantasy-themed illustration (dragon, castle, fairy, etc.)."""
    scale = min(bw, bh) * 0.4
    topic_l = topic.lower()

    if "dragon" in topic_l:
        # Dragon body
        pdf.setLineWidth(lw)
        # Body curve
        pdf.ellipse(cx - scale * 0.35, cy - scale * 0.15, cx + scale * 0.35, cy + scale * 0.25, stroke=1, fill=0)
        # Neck
        pdf.line(cx + scale * 0.1, cy + scale * 0.2, cx + scale * 0.15, cy + scale * 0.45)
        # Head
        pdf.ellipse(cx, cy + scale * 0.35, cx + scale * 0.3, cy + scale * 0.55, stroke=1, fill=0)
        # Eye
        pdf.circle(cx + scale * 0.2, cy + scale * 0.48, scale * 0.04, stroke=1, fill=0)
        # Wings
        pdf.setLineWidth(lw * 0.7)
        wing_pts = [
            (cx - scale * 0.1, cy + scale * 0.1),
            (cx - scale * 0.6, cy + scale * 0.45),
            (cx - scale * 0.5, cy + scale * 0.1),
            (cx - scale * 0.7, cy - scale * 0.1),
            (cx - scale * 0.35, cy + scale * 0.05),
        ]
        _polygon(pdf, wing_pts, stroke=1, fill=0)
        wing_pts2 = [
            (cx + scale * 0.1, cy + scale * 0.1),
            (cx + scale * 0.6, cy + scale * 0.45),
            (cx + scale * 0.5, cy + scale * 0.1),
            (cx + scale * 0.7, cy - scale * 0.1),
            (cx + scale * 0.35, cy + scale * 0.05),
        ]
        _polygon(pdf, wing_pts2, stroke=1, fill=0)
        pdf.setLineWidth(lw)
        # Tail
        pdf.curve(cx - scale * 0.35, cy, cx - scale * 0.7, cy - scale * 0.3,
                  cx - scale * 0.9, cy + scale * 0.1, cx - scale * 0.85, cy + scale * 0.35)
        # Legs
        pdf.line(cx - scale * 0.15, cy - scale * 0.15, cx - scale * 0.2, cy - scale * 0.5)
        pdf.line(cx + scale * 0.15, cy - scale * 0.15, cx + scale * 0.2, cy - scale * 0.5)
    elif "castle" in topic_l or "knight" in topic_l:
        # Castle
        main_w = scale * 0.5
        main_h = scale * 0.4
        bx = cx - main_w / 2
        by = cy - scale * 0.3
        pdf.rect(bx, by, main_w, main_h, stroke=1, fill=0)
        # Battlements
        for i in range(5):
            bw_ = main_w / 7
            bx_ = bx + bw_ + i * bw_ * 1.4
            pdf.rect(bx_, by + main_h, bw_ * 0.8, bw_ * 0.6, stroke=1, fill=0)
        # Gate
        pdf.setFillColor(colors.white)
        gate_w = main_w * 0.25
        gate_h = main_h * 0.4
        pdf.arc(cx - gate_w / 2, by, cx + gate_w / 2, by + gate_h * 2, stroke=1, fill=0)
        # Towers
        for tx in [bx - scale * 0.1, bx + main_w - scale * 0.1]:
            pdf.rect(tx, by, scale * 0.2, main_h * 1.3, stroke=1, fill=0)
            pdf.line(tx, by + main_h * 1.3, tx + scale * 0.1, by + main_h * 1.5 + scale * 0.1)
            pdf.line(tx + scale * 0.1, by + main_h * 1.3, tx + scale * 0.2, by + main_h * 1.3 + scale * 0.1)
        # Flag
        if detail != "simple":
            pdf.setLineWidth(lw * 0.6)
            pdf.line(cx, by + main_h * 1.5, cx, by + main_h * 1.5 + scale * 0.2)
            flag_pts = [(cx, by + main_h * 1.5 + scale * 0.2),
                        (cx + scale * 0.15, by + main_h * 1.5 + scale * 0.12),
                        (cx, by + main_h * 1.5 + scale * 0.04)]
            _polygon(pdf, flag_pts, stroke=1, fill=0)
    else:
        # Generic fantasy: tree + moon
        pdf.setLineWidth(lw)
        # Trunk
        pdf.line(cx, cy - scale * 0.5, cx, cy + scale * 0.05)
        # Canopy
        pdf.circle(cx, cy + scale * 0.25, scale * 0.28, stroke=1, fill=0)
        pdf.circle(cx - scale * 0.18, cy + scale * 0.15, scale * 0.18, stroke=1, fill=0)
        pdf.circle(cx + scale * 0.18, cy + scale * 0.15, scale * 0.18, stroke=1, fill=0)
        # Moon
        if detail != "simple":
            pdf.setLineWidth(lw * 0.7)
            pdf.circle(cx + scale * 0.55, cy + scale * 0.5, scale * 0.12, stroke=1, fill=0)
            pdf.setLineWidth(lw)


def _draw_animal(
    pdf: canvas.Canvas, cx: float, cy: float,
    bw: float, bh: float, topic: str, lw: float,
    detail: str, is_realistic: bool,
) -> None:
    """Draw an animal/nature themed illustration."""
    scale = min(bw, bh) * 0.4
    topic_l = topic.lower()

    # Base: ground line
    pdf.setLineWidth(lw)
    ground_y = cy - scale * 0.45
    pdf.line(cx - scale * 0.7, ground_y, cx + scale * 0.7, ground_y)

    if any(a in topic_l for a in ["lion", "tiger", "cat"]):
        # Cat face
        pdf.setFillColor(colors.white)
        pdf.circle(cx, cy + scale * 0.05, scale * 0.22, stroke=1, fill=0)
        # Ears
        for side in [-1, 1]:
            ear_pts = [
                (cx + side * scale * 0.12, cy + scale * 0.25),
                (cx + side * scale * 0.05, cy + scale * 0.35),
                (cx + side * scale * 0.22, cy + scale * 0.3),
            ]
            _polygon(pdf, ear_pts, stroke=1, fill=0)
        # Eyes
        pdf.setLineWidth(lw * 0.7)
        for side in [-1, 1]:
            pdf.circle(cx + side * scale * 0.09, cy + scale * 0.1, scale * 0.04, stroke=1, fill=0)
        pdf.setLineWidth(lw)
        # Nose
        pdf.circle(cx, cy - scale * 0.02, scale * 0.03, stroke=1, fill=0)
        # Mouth
        pdf.line(cx, cy - scale * 0.02, cx - scale * 0.05, cy - scale * 0.07)
        pdf.line(cx, cy - scale * 0.02, cx + scale * 0.05, cy - scale * 0.07)
        # Whiskers
        if detail != "simple":
            pdf.setLineWidth(lw * 0.5)
            for side in [-1, 1]:
                pdf.line(cx + side * scale * 0.05, cy, cx + side * scale * 0.25, cy - scale * 0.02)
                pdf.line(cx + side * scale * 0.05, cy + scale * 0.02, cx + side * scale * 0.25, cy + scale * 0.04)
            pdf.setLineWidth(lw)
    elif any(a in topic_l for a in ["bird", "owl", "eagle", "hawk"]):
        # Bird body
        pdf.ellipse(cx - scale * 0.2, cy - scale * 0.08, cx + scale * 0.2, cy + scale * 0.15, stroke=1, fill=0)
        # Head
        pdf.circle(cx, cy + scale * 0.2, scale * 0.13, stroke=1, fill=0)
        # Eye
        pdf.setLineWidth(lw * 0.6)
        pdf.circle(cx + scale * 0.05, cy + scale * 0.23, scale * 0.035, stroke=1, fill=0)
        pdf.setLineWidth(lw)
        # Beak
        pdf.line(cx + scale * 0.12, cy + scale * 0.2, cx + scale * 0.25, cy + scale * 0.18)
        pdf.line(cx + scale * 0.12, cy + scale * 0.2, cx + scale * 0.25, cy + scale * 0.23)
        # Wing
        pdf.ellipse(cx - scale * 0.15, cy - scale * 0.02, cx + scale * 0.15, cy + scale * 0.12, stroke=1, fill=0)
        # Branch
        if detail != "simple":
            pdf.setLineWidth(lw * 0.8)
            pdf.line(cx - scale * 0.5, cy - scale * 0.1, cx + scale * 0.5, cy - scale * 0.05)
            pdf.setLineWidth(lw)
    elif any(a in topic_l for a in ["fish", "dolphin", "shark", "whale", "sea turtle", "octopus"]):
        # Fish
        pdf.ellipse(cx - scale * 0.25, cy - scale * 0.1, cx + scale * 0.25, cy + scale * 0.1, stroke=1, fill=0)
        # Tail
        tail_pts = [
            (cx - scale * 0.25, cy),
            (cx - scale * 0.5, cy - scale * 0.18),
            (cx - scale * 0.5, cy + scale * 0.18),
        ]
        _polygon(pdf, tail_pts, stroke=1, fill=0)
        # Eye
        pdf.setLineWidth(lw * 0.6)
        pdf.circle(cx + scale * 0.15, cy + scale * 0.02, scale * 0.035, stroke=1, fill=0)
        pdf.setLineWidth(lw)
        # Fins
        pdf.line(cx, cy + scale * 0.1, cx - scale * 0.05, cy + scale * 0.28)
        pdf.line(cx + scale * 0.05, cy + scale * 0.1, cx + scale * 0.1, cy + scale * 0.25)
        # Bubbles
        if detail != "simple":
            for i in range(3):
                by_ = cy + scale * 0.3 + i * scale * 0.12
                pdf.circle(cx + scale * 0.3 + i * scale * 0.05, by_, scale * 0.03, stroke=1, fill=0)
    elif any(a in topic_l for a in ["flower", "garden", "butterfly", "botanical", "floral"]):
        # Flower
        center_x, center_y = cx, cy + scale * 0.05
        petal_count = 6 if detail == "simple" else 8
        petal_r = scale * 0.18
        for i in range(petal_count):
            angle = 2 * math.pi * i / petal_count
            px = center_x + math.cos(angle) * petal_r
            py = center_y + math.sin(angle) * petal_r
            pdf.circle(px, py, petal_r * 0.7, stroke=1, fill=0)
        # Center
        pdf.circle(center_x, center_y, petal_r * 0.4, stroke=1, fill=0)
        if detail != "simple":
            pdf.circle(center_x, center_y, petal_r * 0.2, stroke=1, fill=0)
        # Stem
        pdf.setLineWidth(lw * 0.8)
        pdf.line(center_x, center_y - petal_r, center_x, ground_y)
        # Leaves
        leaf_pts = [
            (center_x, center_y - petal_r * 0.5),
            (center_x + scale * 0.2, center_y - petal_r * 0.3),
            (center_x, center_y - petal_r * 0.7),
        ]
        _polygon(pdf, leaf_pts, stroke=1, fill=0)
        # Second leaf
        leaf_pts2 = [
            (center_x, center_y - petal_r * 0.3),
            (center_x - scale * 0.18, center_y - petal_r * 0.1),
            (center_x, center_y - petal_r * 0.5),
        ]
        _polygon(pdf, leaf_pts2, stroke=1, fill=0)
        pdf.setLineWidth(lw)
    else:
        # Generic animal: bear silhouette
        pdf.circle(cx, cy + scale * 0.15, scale * 0.22, stroke=1, fill=0)  # head
        pdf.ellipse(cx - scale * 0.2, cy - scale * 0.15, cx + scale * 0.2, cy + scale * 0.2, stroke=1, fill=0)  # body
        # Ears
        for side in [-1, 1]:
            pdf.circle(cx + side * scale * 0.2, cy + scale * 0.32, scale * 0.08, stroke=1, fill=0)
        # Eyes
        pdf.setLineWidth(lw * 0.6)
        pdf.circle(cx - scale * 0.08, cy + scale * 0.2, scale * 0.03, stroke=1, fill=0)
        pdf.circle(cx + scale * 0.08, cy + scale * 0.2, scale * 0.03, stroke=1, fill=0)
        # Nose
        pdf.circle(cx, cy + scale * 0.1, scale * 0.04, stroke=1, fill=0)
        pdf.setLineWidth(lw)


def _draw_vehicle(
    pdf: canvas.Canvas, cx: float, cy: float,
    bw: float, bh: float, topic: str, lw: float, detail: str,
) -> None:
    """Draw a vehicle themed illustration."""
    scale = min(bw, bh) * 0.35
    topic_l = topic.lower()

    if any(v in topic_l for v in ["car", "race", "vehicle"]):
        # Car body
        pdf.setLineWidth(lw)
        pdf.rect(cx - scale * 0.6, cy - scale * 0.1, scale * 1.2, scale * 0.3, stroke=1, fill=0)
        # Cabin
        cabin_pts = [
            (cx - scale * 0.3, cy + scale * 0.1),
            (cx - scale * 0.2, cy + scale * 0.3),
            (cx + scale * 0.25, cy + scale * 0.3),
            (cx + scale * 0.4, cy + scale * 0.1),
        ]
        _polygon(pdf, cabin_pts, stroke=1, fill=0)
        # Windows
        if detail != "simple":
            pdf.setLineWidth(lw * 0.6)
            pdf.rect(cx - scale * 0.15, cy + scale * 0.13, scale * 0.35, scale * 0.13, stroke=1, fill=0)
            pdf.setLineWidth(lw)
        # Wheels
        for wx in [cx - scale * 0.35, cx + scale * 0.35]:
            pdf.circle(wx, cy - scale * 0.1, scale * 0.12, stroke=1, fill=0)
            pdf.circle(wx, cy - scale * 0.1, scale * 0.06, stroke=1, fill=0)
        # Headlights
        pdf.setLineWidth(lw * 0.6)
        pdf.circle(cx + scale * 0.55, cy + scale * 0.05, scale * 0.04, stroke=1, fill=0)
        pdf.setLineWidth(lw)
    elif "plane" in topic_l or "airplane" in topic_l or "rocket" in topic_l:
        # Fuselage
        pdf.setLineWidth(lw)
        pdf.ellipse(cx - scale * 0.6, cy - scale * 0.08, cx + scale * 0.6, cy + scale * 0.08, stroke=1, fill=0)
        # Wings
        wing_pts = [
            (cx - scale * 0.1, cy),
            (cx - scale * 0.05, cy - scale * 0.35),
            (cx + scale * 0.1, cy - scale * 0.35),
            (cx + scale * 0.05, cy),
        ]
        _polygon(pdf, wing_pts, stroke=1, fill=0)
        wing_pts2 = [
            (cx - scale * 0.1, cy),
            (cx - scale * 0.05, cy + scale * 0.35),
            (cx + scale * 0.1, cy + scale * 0.35),
            (cx + scale * 0.05, cy),
        ]
        _polygon(pdf, wing_pts2, stroke=1, fill=0)
        # Tail
        pdf.line(cx + scale * 0.5, cy, cx + scale * 0.6, cy + scale * 0.2)
        pdf.line(cx + scale * 0.55, cy + scale * 0.2, cx + scale * 0.7, cy + scale * 0.1)
        # Cockpit
        pdf.circle(cx - scale * 0.4, cy, scale * 0.08, stroke=1, fill=0)
    else:
        # Generic boat
        pdf.setLineWidth(lw)
        pdf.ellipse(cx - scale * 0.4, cy - scale * 0.1, cx + scale * 0.4, cy + scale * 0.08, stroke=1, fill=0)
        # Sail
        pdf.line(cx, cy + scale * 0.05, cx, cy + scale * 0.4)
        sail_pts = [(cx, cy + scale * 0.4), (cx + scale * 0.3, cy + scale * 0.05), (cx, cy + scale * 0.05)]
        _polygon(pdf, sail_pts, stroke=1, fill=0)
        # Waves
        if detail != "simple":
            pdf.setLineWidth(lw * 0.6)
            for i in range(3):
                wx = cx - scale * 0.5 + i * scale * 0.5
                pdf.arc(wx, cy - scale * 0.3, wx + scale * 0.3, cy - scale * 0.1, stroke=1, fill=0)
            pdf.setLineWidth(lw)


def _draw_mandala(
    pdf: canvas.Canvas, cx: float, cy: float, size: float, lw: float
) -> None:
    """Draw a mandala/geometric pattern."""
    r = size / 2
    rings = 5
    for ring in range(1, rings + 1):
        ring_r = r * ring / rings
        if ring % 2 == 0:
            # Circle ring
            pdf.circle(cx, cy, ring_r, stroke=1, fill=0)
        else:
            # Petal ring
            petals = ring * 4
            for i in range(petals):
                angle = 2 * math.pi * i / petals
                nx = math.cos(angle) * ring_r
                ny = math.sin(angle) * ring_r
                pdf.circle(cx + nx, cy + ny, ring_r * 0.35 / rings, stroke=1, fill=0)
    # Center
    pdf.circle(cx, cy, r * 0.12, stroke=1, fill=0)
    # Radial lines
    pdf.setLineWidth(lw * 0.4)
    for i in range(16):
        angle = 2 * math.pi * i / 16
        pdf.line(cx, cy, cx + math.cos(angle) * r, cy + math.sin(angle) * r)
    pdf.setLineWidth(lw)


def _draw_generic_scene(
    pdf: canvas.Canvas, bx: float, by: float, bw: float, bh: float,
    topic: str, lw: float, detail: str, is_cartoon: bool,
) -> None:
    """Draw a generic themed illustration from the topic."""
    scale = min(bw, bh) * 0.4
    cx = bx + bw / 2
    cy = by + bh / 2
    pdf.setLineWidth(lw)

    # Draw a simple tree and sun
    # Ground
    ground_y = cy - scale * 0.4
    pdf.line(bx + bw * 0.1, ground_y, bx + bw * 0.9, ground_y)
    # Sun
    if is_cartoon:
        pdf.circle(bx + bw * 0.85, by + bh * 0.8, scale * 0.12, stroke=1, fill=0)
        # Sun rays
        pdf.setLineWidth(lw * 0.5)
        for i in range(8):
            angle = 2 * math.pi * i / 8
            pdf.line(
                bx + bw * 0.85 + math.cos(angle) * scale * 0.14,
                by + bh * 0.8 + math.sin(angle) * scale * 0.14,
                bx + bw * 0.85 + math.cos(angle) * scale * 0.22,
                by + bh * 0.8 + math.sin(angle) * scale * 0.22,
            )
        pdf.setLineWidth(lw)
    # Tree
    pdf.line(cx, ground_y, cx, cy - scale * 0.1)
    pdf.circle(cx, cy + scale * 0.2, scale * 0.22, stroke=1, fill=0)
    pdf.circle(cx - scale * 0.15, cy + scale * 0.12, scale * 0.15, stroke=1, fill=0)
    pdf.circle(cx + scale * 0.15, cy + scale * 0.12, scale * 0.15, stroke=1, fill=0)
    # Topic label
    pdf.setFont("Helvetica-Oblique", max(7, scale * 0.07))
    pdf.setFillColor(colors.black)
    pdf.drawCentredString(cx, by + bh * 0.1, topic[:60])


def _polygon(
    pdf: canvas.Canvas, points: list[tuple[float, float]],
    stroke: int = 1, fill: int = 0
) -> None:
    """Draw a closed polygon from a list of (x, y) points."""
    if not points:
        return
    path = pdf.beginPath()
    path.moveTo(points[0][0], points[0][1])
    for pt in points[1:]:
        path.lineTo(pt[0], pt[1])
    path.close()
    pdf.drawPath(path, stroke=stroke, fill=fill)


def _coloring_image_box(page_w: float, page_h: float, *, footer_h: float = 18.0) -> tuple[float, float, float, float]:
    """Return (x, y, w, h) for a ~7.5×10" coloring area centered on US Letter."""
    target_w = min(_COLORING_TARGET_W_IN * 72.0, page_w - 2 * (0.35 * 72.0))
    target_h = min(_COLORING_TARGET_H_IN * 72.0, page_h - 2 * (0.35 * 72.0) - footer_h)
    x = (page_w - target_w) / 2.0
    # Leave a thin footer strip for the page number
    y = ((page_h - footer_h) - target_h) / 2.0 + footer_h * 0.35
    return x, y, target_w, target_h


def _draw_coloring_page(
    pdf: canvas.Canvas,
    page: ColoringPageResult,
    *,
    product_title: str,
    page_index: int,
    total_pages: int,
    single_sheet: bool = False,
) -> None:
    """Draw one coloring book page.

    Interiors: full-page coloring area (~7.5×10"), no product title / topic /
    long prompt headers. Small page-number footer only (book mode).
    single_sheet=True: no footer either (clean printable sheet).
    """
    page_w, page_h = letter
    margin = _MARGIN_IN * 72.0
    _paint_white_page(pdf)

    has_image = page.image_path and os.path.isfile(page.image_path)
    footer_h = 0.0 if single_sheet else 16.0
    box_x, box_y, img_w, img_h = _coloring_image_box(page_w, page_h, footer_h=footer_h)

    if has_image:
        off_x, off_y, dw, dh = _fit_image_to_box(
            page.image_path, box_w=img_w, box_h=img_h
        )
        try:
            pdf.drawImage(
                page.image_path,
                box_x + off_x,
                box_y + off_y,
                width=dw,
                height=dh,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:  # noqa: BLE001
            has_image = False

    if not has_image:
        try:
            _draw_line_art(
                pdf,
                topic=page.topic,
                line_art_prompt=page.line_art_prompt,
                box_x=box_x,
                box_y=box_y,
                box_w=img_w,
                box_h=img_h,
                age_group="",
                art_style="",
            )
        except Exception:  # noqa: BLE001
            pdf.setStrokeColor(colors.HexColor("#D1D5DB"))
            pdf.setLineWidth(0.5)
            pdf.setFillColor(colors.HexColor("#F9FAFB"))
            pdf.rect(box_x, box_y, img_w, img_h, fill=1, stroke=1)
            pdf.setFillColor(colors.black)
            pdf.setFont("Helvetica-Oblique", 9)
            pdf.drawCentredString(page_w / 2.0, page_h / 2.0, "[Basic Test Fallback]")

    # Captions only when explicitly requested — never dump the full prompt
    if page.caption and len(str(page.caption)) <= 120:
        _draw_centered_text(
            pdf, page_w / 2.0, margin * 0.55,
            str(page.caption)[:100],
            font_name="Helvetica-Oblique",
            font_size=8,
        )

    # Book mode: small page number footer only (no title / topic / prompt header)
    if not single_sheet:
        _draw_centered_text(
            pdf,
            page_w / 2.0,
            0.28 * 72.0,
            str(page_index + 1),
            font_name="Helvetica",
            font_size=9,
        )


def _draw_comic_title(
    pdf: canvas.Canvas,
    text: str,
    *,
    x: float,
    y: float,
    font_size: float,
    fill_hex: str = "#F6E05E",
    outline_hex: str = "#C53030",
    centered: bool = False,
) -> None:
    """Yellow fill + red outline/shadow comic title (layout text, not AI)."""
    text = str(text or "")
    if not text:
        return
    pdf.setFont("Helvetica-Bold", font_size)
    width = pdf.stringWidth(text, "Helvetica-Bold", font_size)
    draw_x = x - (width / 2.0 if centered else 0.0)
    # Soft red drop shadow / outline via offsets
    pdf.setFillColor(colors.HexColor(outline_hex))
    for dx, dy in (
        (-2.2, -2.0),
        (2.2, -2.0),
        (-2.2, 1.4),
        (2.2, 1.4),
        (0.0, -2.4),
        (0.0, 1.8),
        (-2.4, 0.0),
        (2.4, 0.0),
    ):
        pdf.drawString(draw_x + dx, y + dy, text)
    pdf.setFillColor(colors.HexColor(fill_hex))
    pdf.drawString(draw_x, y, text)


def _draw_cover_text_overlay(
    pdf: canvas.Canvas,
    *,
    title: str,
    subtitle: str = "",
    badge: str = "",
    page_w: float,
    page_h: float,
) -> None:
    """Retail jumbo-book title banner — layout text only, never AI-painted."""
    title = str(title or "THUNDER VOLT").strip().upper()[:48]
    subtitle = str(subtitle or "").strip()[:60]
    badge = str(badge or "Jumbo Coloring & Activity Book").strip()[:48]

    # Top navy banner with diagonal/jagged bottom edge (Bendon-style packaging)
    left_bottom = page_h - 118
    right_bottom = page_h - 148
    banner = pdf.beginPath()
    banner.moveTo(0, page_h)
    banner.lineTo(page_w, page_h)
    banner.lineTo(page_w, right_bottom)
    banner.lineTo(page_w * 0.62, left_bottom - 10)
    banner.lineTo(page_w * 0.48, left_bottom + 14)
    banner.lineTo(page_w * 0.34, left_bottom - 6)
    banner.lineTo(0, left_bottom)
    banner.close()
    pdf.setFillColor(colors.HexColor("#0A2342"))
    pdf.drawPath(banner, fill=1, stroke=0)
    # Thin cyan accent under the jagged edge
    pdf.setStrokeColor(colors.HexColor("#38B2AC"))
    pdf.setLineWidth(2.2)
    edge = pdf.beginPath()
    edge.moveTo(0, left_bottom)
    edge.lineTo(page_w * 0.34, left_bottom - 6)
    edge.lineTo(page_w * 0.48, left_bottom + 14)
    edge.lineTo(page_w * 0.62, left_bottom - 10)
    edge.lineTo(page_w, right_bottom)
    pdf.drawPath(edge, fill=0, stroke=1)

    # Title on the left of the banner
    title_size = 34
    max_title_w = page_w * 0.55
    pdf.setFont("Helvetica-Bold", title_size)
    while title_size > 18 and pdf.stringWidth(title, "Helvetica-Bold", title_size) > max_title_w:
        title_size -= 1
        pdf.setFont("Helvetica-Bold", title_size)
    _draw_comic_title(
        pdf,
        title,
        x=28,
        y=page_h - 72,
        font_size=title_size,
    )
    if subtitle:
        pdf.setFillColor(colors.HexColor("#E2E8F0"))
        pdf.setFont("Helvetica", 11)
        pdf.drawString(30, page_h - 92, subtitle)

    # Product line stacked on the right (JUMBO / COLORING & ACTIVITY BOOK)
    badge_u = badge.upper()
    show_jumbo = "JUMBO" in badge_u
    if "ACTIVITY" in badge_u:
        line1, line2 = "COLORING &", "ACTIVITY BOOK"
    elif "COLORING" in badge_u:
        line1, line2 = "COLORING", "BOOK"
    else:
        words = [w for w in badge_u.replace("JUMBO", "").split() if w]
        if len(words) >= 2:
            line1, line2 = words[0], " ".join(words[1:])
        else:
            line1, line2 = (words[0] if words else "COLORING BOOK"), ""

    right_x = page_w - 28
    if show_jumbo:
        pdf.setFont("Helvetica-Bold", 22)
        jumbo_w = pdf.stringWidth("JUMBO", "Helvetica-Bold", 22)
        _draw_comic_title(
            pdf,
            "JUMBO",
            x=right_x - jumbo_w,
            y=page_h - 58,
            font_size=22,
            fill_hex="#F6E05E",
            outline_hex="#C53030",
        )
        y1, y2 = page_h - 74, page_h - 86
    else:
        y1, y2 = page_h - 64, page_h - 78
    pdf.setFillColor(colors.HexColor("#FC8181"))
    pdf.setFont("Helvetica-Bold", 9)
    pdf.drawRightString(right_x, y1, line1)
    if line2:
        pdf.drawRightString(right_x, y2, line2)

    # Bottom-right retail callout tab
    tab = pdf.beginPath()
    tab.moveTo(page_w - 168, 0)
    tab.lineTo(page_w, 0)
    tab.lineTo(page_w, 54)
    tab.lineTo(page_w - 132, 54)
    tab.close()
    pdf.setFillColor(colors.HexColor("#1A365D"))
    pdf.drawPath(tab, fill=1, stroke=0)
    pdf.setFillColor(colors.HexColor("#F6E05E"))
    pdf.setFont("Helvetica-Bold", 8)
    pdf.drawRightString(page_w - 14, 30, "COLORING PAGES")
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica", 7)
    pdf.drawRightString(page_w - 14, 16, "Print & Share")


def draw_cover_page_on_canvas(
    pdf: canvas.Canvas,
    *,
    cover_image_path: str = "",
    title: str = "",
    subtitle: str = "",
    badge: str = "Jumbo Coloring & Activity Book",
    cover_design: dict | None = None,
) -> None:
    """Full-bleed cover + retail title banner overlay (US Letter)."""
    page_w, page_h = letter
    design = cover_design if isinstance(cover_design, dict) else {}
    title = str(design.get("title") or title or "THUNDER VOLT")
    subtitle = str(design.get("subtitle") or subtitle or "")
    badge = str(design.get("badge") or badge or "")
    img = cover_image_path or str(design.get("local_image_path") or "")

    painted = False
    if img and os.path.isfile(img):
        try:
            # Full-bleed cover — scale to cover page, centered (may crop edges, not text)
            with PILImage.open(img) as im:
                iw, ih = im.size
            scale = max(page_w / max(iw, 1), page_h / max(ih, 1))
            dw, dh = iw * scale, ih * scale
            x = (page_w - dw) / 2.0
            y = (page_h - dh) / 2.0
            pdf.drawImage(img, x, y, width=dw, height=dh, preserveAspectRatio=True, mask="auto")
            painted = True
        except Exception:  # noqa: BLE001
            painted = False

    if not painted:
        # Cinematic local fallback (color band + skyline suggestion) — not a tiny lightning icon
        _paint_white_page(pdf)
        pdf.setFillColor(colors.HexColor("#0B1B33"))
        pdf.rect(0, 0, page_w, page_h, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor("#1E3A5F"))
        pdf.rect(0, page_h * 0.35, page_w, page_h * 0.65, fill=1, stroke=0)
        # Simple skyline silhouettes
        pdf.setFillColor(colors.HexColor("#0A1628"))
        buildings = [
            (40, page_h * 0.35, 50, 160), (100, page_h * 0.35, 40, 220),
            (160, page_h * 0.35, 70, 180), (250, page_h * 0.35, 45, 260),
            (320, page_h * 0.35, 55, 150), (400, page_h * 0.35, 60, 210),
            (480, page_h * 0.35, 40, 170), (540, page_h * 0.35, 50, 240),
        ]
        for bx, by, bw, bh in buildings:
            pdf.rect(bx, by, bw, bh, fill=1, stroke=0)
        # Hero circle accent (large — not a tiny bolt as whole design)
        pdf.setStrokeColor(colors.HexColor("#F6C945"))
        pdf.setLineWidth(3)
        pdf.circle(page_w / 2.0, page_h * 0.62, 90, stroke=1, fill=0)
        pdf.setFillColor(colors.HexColor("#F6C945"))
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawCentredString(page_w / 2.0, page_h * 0.60, "HERO")

    if design.get("text_overlay", True) is not False:
        _draw_cover_text_overlay(
            pdf,
            title=title,
            subtitle=subtitle,
            badge=badge,
            page_w=page_w,
            page_h=page_h,
        )


def build_coloring_book_pdf_bytes(
    result: ColoringBookResult,
    *,
    include_answer_key: bool = False,
    cover_image_path: str = "",
    single_sheet: bool = False,
    cover_design: dict | None = None,
    pdf_metadata: dict | None = None,
) -> tuple[bytes, ColoringBookLayoutInfo]:
    """Render a coloring book PDF from ColoringBookResult.

    single_sheet=True renders each page as a clean printable coloring sheet
    (no headers, no labels, image fills the page). Use for Single Sheet output.
    """
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    layout = ColoringBookLayoutInfo()
    page_w, page_h = letter

    meta = dict(pdf_metadata or {})
    if not meta:
        from services.coloring_book.prompt_engine import pdf_metadata_for_theme

        meta = pdf_metadata_for_theme(
            "",
            product_title=getattr(result, "product_title", "") or "",
        )
    try:
        pdf.setTitle(str(meta.get("title") or "Coloring Book"))
        pdf.setAuthor(str(meta.get("author") or "Digital Product Factory"))
        pdf.setSubject(str(meta.get("subject") or ""))
        pdf.setKeywords(str(meta.get("keywords") or "coloring book"))
        pdf.setCreator("Digital Product Factory")
    except Exception:  # noqa: BLE001
        pass

    include_cover = bool(cover_image_path or cover_design) and not single_sheet
    if include_cover:
        draw_cover_page_on_canvas(
            pdf,
            cover_image_path=cover_image_path,
            title=result.product_title,
            subtitle=result.subtitle,
            badge="Jumbo Coloring & Activity Book",
            cover_design=cover_design,
        )
        layout.cover_page_count = 1
        pdf.showPage()

    pages = list(getattr(result, "pages", None) or [])
    for idx, page in enumerate(pages):
        _draw_coloring_page(
            pdf,
            page,
            product_title=result.product_title,
            page_index=idx,
            total_pages=len(pages),
            single_sheet=single_sheet,
        )
        layout.page_count += 1
        img = getattr(page, "image_path", "") or (page.get("image_path") if isinstance(page, dict) else "")
        if img and os.path.isfile(img):
            layout.image_pages += 1
        else:
            layout.text_pages += 1
        pdf.showPage()

    # Cover-only preview still needs at least the cover page written.
    if include_cover and not pages:
        pass
    elif not include_cover and not pages:
        # Avoid empty PDF; draw a blank placeholder page
        _paint_white_page(pdf)
        pdf.showPage()
        layout.page_count = 1

    pdf.save()
    layout.page_count = layout.cover_page_count + layout.page_count
    return buffer.getvalue(), layout


def draw_coloring_book_cover(
    product_title: str,
    subtitle: str = "",
    theme: str = "",
    age_group: str = "",
    art_style: str = "",
    package_id: str = "",
    badge: str = "Jumbo Coloring & Activity Book",
    cover_design: dict | None = None,
) -> str:
    """
    Draw a local cinematic cover page and return the image path (or empty string).
    Saves the cover as a PNG to EXPORTS_DIR/pkg/cover.png and img_cover.png.
    Title/subtitle are applied via layout code (not AI text).
    """
    from reportlab.pdfgen import canvas as pdfgen_canvas

    from services.coloring_book.prompt_engine import derive_cover_copy

    copy = derive_cover_copy(theme or product_title, product_title=product_title, subtitle=subtitle)
    title = copy.title
    sub = copy.subtitle or subtitle
    badge_text = badge or copy.badge

    buf = io.BytesIO()
    cover_pdf = pdfgen_canvas.Canvas(buf, pagesize=letter)
    draw_cover_page_on_canvas(
        cover_pdf,
        title=title,
        subtitle=sub,
        badge=badge_text,
        cover_design=cover_design,
    )
    cover_pdf.save()

    buf.seek(0)
    try:
        import fitz

        doc = fitz.open(stream=buf.getvalue(), filetype="pdf")
        if len(doc) > 0:
            page = doc[0]
            mat = fitz.Matrix(2.0, 2.0)
            pix = page.get_pixmap(matrix=mat)
            png_bytes = pix.tobytes("png")
            doc.close()

            EXPORTS_DIR = os.environ.get(
                "FLASK_EXPORTS_DIR",
                os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "exports"),
            )
            pkg_dir = package_id or "coloring_book"
            out_dir = os.path.join(EXPORTS_DIR, pkg_dir)
            os.makedirs(out_dir, exist_ok=True)
            out_path = os.path.join(out_dir, "cover.png")
            with open(out_path, "wb") as fh:
                fh.write(png_bytes)
            # Shared cover editor expects img_cover.png
            img_cover = os.path.join(out_dir, "img_cover.png")
            with open(img_cover, "wb") as fh:
                fh.write(png_bytes)
            return out_path
        doc.close()
    except Exception:  # noqa: BLE001
        pass
    return ""


def save_coloring_book_pdf(
    result: ColoringBookResult,
    output_dir: str,
    filename: str = "coloring_book.pdf",
) -> tuple[bytes, ColoringBookLayoutInfo]:
    pdf_bytes, layout = build_coloring_book_pdf_bytes(result)
    path = os.path.join(output_dir, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(pdf_bytes)
    return pdf_bytes, layout
