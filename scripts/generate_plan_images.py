"""Generate one product image per billing plan, for manual upload to Lemon
Squeezy's Media section (their API has no image-upload endpoint, so this
cannot be automated end to end — see docs/BILLING_SETUP.md).

    .venv/Scripts/python.exe scripts/generate_plan_images.py

Writes 1600x1200 (4:3) PNGs to exports/plan_images/ — Lemon Squeezy's own
recommended size for a product's Media images, which is a landscape ratio, not
square. An earlier version of this script produced 1000x1000 squares before
that field had been found in the product editor; if any of those got uploaded,
replace them with this run's output.

Colors match the rest of the app (templates/index.html's tailwind `brand`
scale). Price, tagline, and seat count come from services/billing/plans.py, so
a price change stays in sync automatically on the next run.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageFont

from services.billing import plans as P

# Lemon Squeezy's stated recommendation for product Media images.
WIDTH, HEIGHT = 1600, 1200
OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "exports", "plan_images")

# templates/index.html brand scale.
BRAND_600 = (79, 70, 229)
BRAND_700 = (67, 56, 202)
BRAND_900 = (49, 46, 129)
WHITE = (255, 255, 255)
GOLD = (245, 197, 66)   # founder-plan accent, distinct from the indigo ladder


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    windir = os.environ.get("WINDIR", r"C:\Windows")
    candidates = [
        os.path.join(windir, "Fonts", "segoeuib.ttf" if bold else "segoeui.ttf"),
        os.path.join(windir, "Fonts", "arialbd.ttf" if bold else "arial.ttf"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _text(draw: ImageDraw.ImageDraw, xy, text: str, font, fill, anchor="mm"):
    draw.text(xy, text, font=font, fill=fill, anchor=anchor)


def _gradient(w: int, h: int, top, bottom) -> Image.Image:
    """Left-to-right gradient — a landscape canvas reads better with the
    gradient running along its long axis than a top-to-bottom one does."""
    img = Image.new("RGB", (w, h), top)
    px = img.load()
    for x in range(w):
        t = x / max(w - 1, 1)
        r = round(top[0] + (bottom[0] - top[0]) * t)
        g = round(top[1] + (bottom[1] - top[1]) * t)
        b = round(top[2] + (bottom[2] - top[2]) * t)
        for y in range(h):
            px[x, y] = (r, g, b)
    return img


def _wordmark(draw: ImageDraw.ImageDraw, cx: float, y: int):
    font = _font(30, bold=True)
    _text(draw, (cx, y), "DIGITAL PRODUCT FACTORY", font, (255, 255, 255, 210))


def render_plan(plan: P.Plan) -> Image.Image:
    """Landscape layout: badge/wordmark across the top, price block centred
    in the remaining space, capacity pill anchored to the bottom. Built for
    1600x1200 -- a straight square-to-landscape stretch of the earlier layout
    left huge gaps in the extra width, so the vertical rhythm here is
    re-tuned for this canvas rather than scaled from it."""
    accent = GOLD if plan.id == "founder" else WHITE
    img = _gradient(WIDTH, HEIGHT, BRAND_600, BRAND_900)
    draw = ImageDraw.Draw(img)
    cx = WIDTH / 2

    inset = 34
    draw.rectangle([inset, inset, WIDTH - inset, HEIGHT - inset],
                  outline=accent, width=4)

    _wordmark(draw, cx, 96)

    if plan.highlight:
        badge_font = _font(28, bold=True)
        text = "MOST POPULAR"
        bbox = draw.textbbox((0, 0), text, font=badge_font)
        w = bbox[2] - bbox[0]
        pad = 24
        bx0, by0 = cx - w / 2 - pad, 156
        bx1, by1 = cx + w / 2 + pad, 156 + 58
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=29, fill=WHITE)
        _text(draw, ((bx0 + bx1) / 2, (by0 + by1) / 2), text, badge_font, BRAND_700)
    elif plan.limited_seats:
        badge_font = _font(26, bold=True)
        text = f"LIMITED - FIRST {plan.limited_seats} MEMBERS"
        bbox = draw.textbbox((0, 0), text, font=badge_font)
        w = bbox[2] - bbox[0]
        pad = 22
        bx0, by0 = cx - w / 2 - pad, 156
        bx1, by1 = cx + w / 2 + pad, 156 + 54
        draw.rounded_rectangle([bx0, by0, bx1, by1], radius=27, outline=GOLD, width=3)
        _text(draw, ((bx0 + bx1) / 2, (by0 + by1) / 2), text, badge_font, GOLD)

    name_font = _font(84, bold=True)
    _text(draw, (cx, 400), plan.name.upper(), name_font, WHITE)

    price_font = _font(180, bold=True)
    price = P.format_price(plan.monthly_cents or plan.annual_cents)
    _text(draw, (cx, 600), price, price_font, accent)

    period_font = _font(36)
    period = "per month" if plan.monthly_cents else "per year, locked for life"
    _text(draw, (cx, 720), period, period_font, (226, 226, 250))

    tagline_font = _font(32)
    tagline = plan.tagline
    max_w = WIDTH - 460  # wide margins so a landscape canvas doesn't run edge-to-edge
    words = tagline.split()
    lines, cur = [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        bbox = draw.textbbox((0, 0), trial, font=tagline_font)
        if bbox[2] - bbox[0] <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    ty = 810
    for line in lines[:2]:
        _text(draw, (cx, ty), line, tagline_font, (226, 226, 250))
        ty += 44

    cap_font = _font(30, bold=True)
    cap_text = (
        f"{plan.products_per_month} products / month"
        if plan.products_per_month >= 0 else "Unlimited products"
    )
    cy0 = HEIGHT - 150
    bbox = draw.textbbox((0, 0), cap_text, font=cap_font)
    w = bbox[2] - bbox[0]
    pad = 26
    bx0 = cx - w / 2 - pad
    bx1 = cx + w / 2 + pad
    draw.rounded_rectangle([bx0, cy0, bx1, cy0 + 58], radius=29,
                           outline=(255, 255, 255), width=2)
    _text(draw, ((bx0 + bx1) / 2, cy0 + 29), cap_text, cap_font, WHITE)

    return img


def main() -> int:
    os.makedirs(OUT_DIR, exist_ok=True)
    written = []
    for plan in sorted(P.ALL_PLANS, key=lambda p: p.order):
        if plan.id == "free":
            continue  # Free has no Lemon Squeezy product to attach an image to.
        img = render_plan(plan)
        path = os.path.join(OUT_DIR, f"{plan.id}.png")
        img.save(path, "PNG")
        written.append((plan.name, path))

    print(f"\nWrote {len(written)} images to {OUT_DIR}\n")
    for name, path in written:
        print(f"  {name:<16} {path}")
    print("\nUpload each one in Lemon Squeezy: open the product -> Media -> "
          "drag the matching file in. The API has no way to do this step "
          "for you.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
