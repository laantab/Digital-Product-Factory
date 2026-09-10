"""Cover-art engine for the planner renderer.

Produces the full-bleed background artwork for a planner cover as a PIL image,
in one of four styles:

  * ``full_photo``      -- the hero image fills the cover; a soft scrim sits
                           behind the title so type stays legible.
  * ``photo_panel``     -- hero image on the upper part of the cover, a solid
                           colour panel below carrying the title block.
  * ``soft_overlay``    -- hero image washed with the theme colour, vignetted,
                           with a fine inset frame.
  * ``minimal_texture`` -- no photo: paper texture, gentle light, thin frame.

The hero image comes from the **cover image slot**: any local photograph
(``cover_image_path``), typically sourced through the Factory's Pexels
workflow. When no image is supplied, a procedural hero is painted from the
theme's recipe so the cover never depends on an outside service and never
ships as a flat block of colour.

Typography is not painted here. The renderer sets the title, subtitle and
caption as vector text on top of this artwork, so the type is embedded in the
PDF (export-safe, sharp at any size, and readable by the Editor-in-Chief).
``text_on_dark`` tells the renderer which ink to use, measured from the pixels
the title will actually sit on rather than assumed from the theme.

Live Pexels sourcing is an explicit, opt-in path (``source_pexels_cover``)
that respects ``FACTORY_TEST_MODE`` and the owner's paid-call rule; the
default build makes no network call at all.
"""
from __future__ import annotations

import io
import math
import os
import random
from dataclasses import dataclass, field
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from services.planner.themes import COVER_STYLES, PlannerTheme, hex_to_rgb255

DEFAULT_DPI = 200
MIN_COVER_DPI = 150


@dataclass
class CoverArt:
    image: Image.Image
    style: str
    source: str                 # "procedural" | "file" | "pexels"
    text_on_dark: bool
    dpi: int
    panel_top_frac: float = 0.0  # photo_panel: where the text panel begins (0..1 from top)
    notes: list[str] = field(default_factory=list)
    attribution: dict[str, Any] = field(default_factory=dict)

    def to_jpeg_bytes(self, quality: int = 88) -> bytes:
        buf = io.BytesIO()
        self.image.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue()


# --------------------------------------------------------------------------- #
# Small raster helpers (pure PIL, no numpy)
# --------------------------------------------------------------------------- #
def _lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _mix(c: tuple[int, int, int], target: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return _lerp(c, target, amount)


def _vertical_gradient(size: tuple[int, int], top: tuple[int, int, int],
                       bottom: tuple[int, int, int]) -> Image.Image:
    w, h = size
    mask = Image.linear_gradient("L").rotate(180).resize((w, h))
    return Image.composite(Image.new("RGB", size, bottom), Image.new("RGB", size, top), mask)


def _diagonal_gradient(size: tuple[int, int], a: tuple[int, int, int],
                       b: tuple[int, int, int], angle: float = 35.0) -> Image.Image:
    w, h = size
    big = int(math.hypot(w, h)) + 4
    mask = Image.linear_gradient("L").resize((big, big)).rotate(angle, expand=False)
    mask = mask.crop(((big - w) // 2, (big - h) // 2, (big - w) // 2 + w, (big - h) // 2 + h))
    return Image.composite(Image.new("RGB", size, a), Image.new("RGB", size, b), mask)


def _radial_glow(img: Image.Image, center: tuple[float, float], radius: float,
                 color: tuple[int, int, int], strength: float) -> Image.Image:
    """Blend `color` into `img` with a soft radial falloff around `center`."""
    w, h = img.size
    r = max(8, int(radius))
    glow = Image.radial_gradient("L").resize((2 * r, 2 * r))
    glow = ImageOps.invert(glow)
    glow = glow.point(lambda v: int(v * strength))
    mask = Image.new("L", (w, h), 0)
    mask.paste(glow, (int(center[0] - r), int(center[1] - r)))
    return Image.composite(Image.new("RGB", (w, h), color), img, mask)


def _vignette(img: Image.Image, strength: float = 0.35,
              color: tuple[int, int, int] = (0, 0, 0)) -> Image.Image:
    w, h = img.size
    mask = Image.radial_gradient("L").resize((int(w * 1.55), int(h * 1.55)))
    mask = mask.crop(((mask.width - w) // 2, (mask.height - h) // 2,
                      (mask.width - w) // 2 + w, (mask.height - h) // 2 + h))
    mask = mask.point(lambda v: int(max(0, v - 90) * strength * 1.5))
    return Image.composite(Image.new("RGB", (w, h), color), img, mask)


def _grain(img: Image.Image, amount: float = 6.0, seed: int = 7) -> Image.Image:
    """Fine paper / linen grain. Keeps the cover from reading as a flat fill."""
    w, h = img.size
    noise = Image.effect_noise((w, h), max(1.0, amount)).convert("L")
    noise = noise.point(lambda v: 128 + (v - 128) // 3)
    grain = Image.merge("RGB", (noise, noise, noise))
    # img + (grain - 128): adds +/- a few levels of texture, never a tone shift.
    return ImageChops.add(img, grain, scale=1.0, offset=-128)


def _linen(img: Image.Image, seed: int = 7, alpha: int = 10) -> Image.Image:
    """Horizontal and vertical thread texture, very light."""
    w, h = img.size
    rng = random.Random(seed)
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    for y in range(0, h, 3):
        d.line([(0, y), (w, y)], fill=rng.randint(0, alpha))
    for x in range(0, w, 3):
        d.line([(x, 0), (x, h)], fill=rng.randint(0, alpha))
    lighter = ImageChops.add(img, Image.merge("RGB", (layer, layer, layer)))
    return Image.blend(img, lighter, 0.6)


def _rays(img: Image.Image, origin: tuple[float, float], color: tuple[int, int, int],
          count: int = 9, strength: float = 0.16, seed: int = 3) -> Image.Image:
    """Soft light rays fanning from `origin`."""
    w, h = img.size
    rng = random.Random(seed)
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    reach = math.hypot(w, h) * 1.2
    base = math.atan2(h - origin[1], (w / 2) - origin[0])
    for i in range(count):
        a = base + (i - count / 2) * 0.16 + rng.uniform(-0.03, 0.03)
        spread = rng.uniform(0.018, 0.05)
        p1 = (origin[0] + math.cos(a - spread) * reach, origin[1] + math.sin(a - spread) * reach)
        p2 = (origin[0] + math.cos(a + spread) * reach, origin[1] + math.sin(a + spread) * reach)
        d.polygon([origin, p1, p2], fill=rng.randint(40, 110))
    layer = layer.filter(ImageFilter.GaussianBlur(radius=max(6, w // 40)))
    layer = layer.point(lambda v: int(v * strength * 2.2))
    return Image.composite(Image.new("RGB", (w, h), color), img, layer)


def _bokeh(img: Image.Image, color: tuple[int, int, int], count: int = 14,
           seed: int = 5, strength: float = 0.5) -> Image.Image:
    w, h = img.size
    rng = random.Random(seed)
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    for _ in range(count):
        r = rng.randint(int(w * 0.02), int(w * 0.09))
        x, y = rng.randint(0, w), rng.randint(0, int(h * 0.75))
        d.ellipse([x - r, y - r, x + r, y + r], fill=rng.randint(30, 90))
    layer = layer.filter(ImageFilter.GaussianBlur(radius=max(4, w // 90)))
    layer = layer.point(lambda v: int(v * strength * 1.6))
    return Image.composite(Image.new("RGB", (w, h), color), img, layer)


def _paint_sprig(d: ImageDraw.ImageDraw, x: float, y: float, length: float,
                 angle: float, color: tuple[int, int, int], scale: float,
                 leaves: int = 7, rng: random.Random | None = None) -> None:
    rng = rng or random.Random(1)
    a = math.radians(angle)
    ex, ey = x + math.cos(a) * length, y + math.sin(a) * length
    cx, cy = x + math.cos(a + 0.4) * length * 0.55, y + math.sin(a + 0.4) * length * 0.55
    pts = []
    for i in range(41):
        t = i / 40
        px = (1 - t) ** 2 * x + 2 * (1 - t) * t * cx + t ** 2 * ex
        py = (1 - t) ** 2 * y + 2 * (1 - t) * t * cy + t ** 2 * ey
        pts.append((px, py))
    d.line(pts, fill=color, width=max(2, int(3 * scale)))
    for i in range(leaves):
        t = (i + 1) / (leaves + 1)
        px, py = pts[int(t * 40)]
        side = 1 if i % 2 == 0 else -1
        ll = (34 + 18 * (1 - t)) * scale * rng.uniform(0.85, 1.1)
        la = a + side * math.radians(58)
        tipx, tipy = px + math.cos(la) * ll, py + math.sin(la) * ll
        nx, ny = -math.sin(la) * ll * 0.34, math.cos(la) * ll * 0.34
        mx, my = px + math.cos(la) * ll * 0.5, py + math.sin(la) * ll * 0.5
        poly = [(px, py), (mx + nx, my + ny), (tipx, tipy), (mx - nx * 0.2, my - ny * 0.2)]
        d.polygon(poly, fill=color)


def _botanicals(img: Image.Image, color: tuple[int, int, int], seed: int = 11,
                alpha: float = 0.55, scale: float = 1.0, hero_bottom: float = 1.0) -> Image.Image:
    """Sprigs in two corners of the hero region, blurred slightly so they sit
    behind the type. `hero_bottom` is where the photo region ends (0..1)."""
    w, h = img.size
    rng = random.Random(seed)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    col = (*color, int(255 * alpha))
    s = (w / 1700.0) * scale * 1.35
    hb = max(0.35, min(1.0, hero_bottom))
    # Lower-left cluster, growing up into the hero region.
    for k in range(4):
        _paint_sprig(d, w * (0.0 + k * 0.02), h * (hb - 0.02 + k * 0.015), w * (0.30 + k * 0.05),
                     -58 + k * 12, col, s, leaves=8, rng=rng)
    # Top-right cluster, hanging down.
    for k in range(4):
        _paint_sprig(d, w * (1.0 - k * 0.02), h * (0.03 + k * 0.02), w * (0.28 + k * 0.05),
                     128 - k * 12, col, s, leaves=8, rng=rng)
    layer = layer.filter(ImageFilter.GaussianBlur(radius=1.2 * s))
    base = img.convert("RGBA")
    return Image.alpha_composite(base, layer).convert("RGB")


def _clamp_edges(img: Image.Image, max_avg: int = 238) -> Image.Image:
    """Cover artwork must reach the trim edge as *ink*. Very light art would
    read as a white border to the Editor-in-Chief's cover check, so the whole
    image is darkened just enough that its lightest areas stay under the
    threshold the reviewer uses."""
    w, h = img.size
    small = img.resize((60, 80))
    px = list(small.getdata())
    lightest = max((r + g + b) / 3 for r, g, b in px) if px else 0
    if lightest <= max_avg:
        return img
    factor = max_avg / lightest
    return ImageEnhance.Brightness(img).enhance(factor)


# --------------------------------------------------------------------------- #
# Procedural hero recipes -- one per theme
# --------------------------------------------------------------------------- #
def _hero_claret_glow(size, T: PlannerTheme, seed: int, hero_bottom: float = 1.0) -> Image.Image:
    w, h = size
    bg = hex_to_rgb255(T.cover_bg)
    top = _mix(bg, (0, 0, 0), 0.18)
    bottom = _mix(bg, (255, 190, 140), 0.16)
    img = _vertical_gradient(size, top, bottom)
    img = _radial_glow(img, (w * 0.5, h * 0.34), w * 0.78, _mix(bg, (255, 215, 160), 0.48), 0.85)
    img = _rays(img, (w * 0.5, -h * 0.12), _mix(bg, (255, 232, 195), 0.55), count=13,
                strength=0.22, seed=seed)
    img = _bokeh(img, _mix(bg, (255, 225, 180), 0.5), count=10, seed=seed, strength=0.35)
    img = _linen(img, seed=seed, alpha=9)
    return _vignette(img, 0.34, _mix(bg, (0, 0, 0), 0.55))


def _hero_taupe_paper(size, T: PlannerTheme, seed: int, hero_bottom: float = 1.0) -> Image.Image:
    w, h = size
    bg = hex_to_rgb255(T.cover_bg)
    img = _diagonal_gradient(size, _mix(bg, (255, 255, 255), 0.35), _mix(bg, (0, 0, 0), 0.06), 28)
    img = _radial_glow(img, (w * 0.28, h * 0.22), w * 0.8, (255, 255, 255), 0.35)
    img = _grain(img, amount=7.0, seed=seed)
    return _vignette(img, 0.12, _mix(bg, (0, 0, 0), 0.25))


def _hero_blush_botanical(size, T: PlannerTheme, seed: int, hero_bottom: float = 1.0) -> Image.Image:
    w, h = size
    bg = hex_to_rgb255(T.cover_bg)
    img = _vertical_gradient(size, _mix(bg, (255, 255, 255), 0.35), _mix(bg, (200, 150, 165), 0.18))
    img = _radial_glow(img, (w * 0.5, h * 0.45), w * 0.7, (255, 250, 248), 0.45)
    img = _botanicals(img, hex_to_rgb255(T.cover_accent), seed=seed, alpha=0.7, scale=1.2,
                      hero_bottom=hero_bottom)
    img = _grain(img, amount=4.0, seed=seed)
    return _vignette(img, 0.10, _mix(bg, (120, 70, 90), 0.5))


def _hero_walnut_grain(size, T: PlannerTheme, seed: int, hero_bottom: float = 1.0) -> Image.Image:
    w, h = size
    bg = hex_to_rgb255(T.cover_bg)
    img = _vertical_gradient(size, _mix(bg, (0, 0, 0), 0.22), _mix(bg, (170, 115, 70), 0.22))
    # Soft horizontal grain: wide, faint, heavily blurred bands.
    rng = random.Random(seed)
    layer = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(layer)
    y = 0
    while y < h:
        band = rng.randint(10, 40)
        d.rectangle([0, y, w, y + band], fill=rng.randint(0, 12))
        y += band + rng.randint(6, 22)
    layer = layer.filter(ImageFilter.GaussianBlur(max(6, w // 160)))
    img = ImageChops.add(img, Image.merge("RGB", (layer, layer, layer)))
    img = _radial_glow(img, (w * 0.5, h * 0.30), w * 0.7, _mix(bg, (255, 200, 140), 0.45), 0.55)
    img = _rays(img, (w * 0.5, -h * 0.1), _mix(bg, (255, 215, 160), 0.5), count=9,
                strength=0.14, seed=seed)
    img = _radial_glow(img, (w * 0.5, h * 0.78), w * 0.7, hex_to_rgb255(T.cover_accent), 0.20)
    img = _linen(img, seed=seed, alpha=7)
    return _vignette(img, 0.40, (10, 6, 4))


def _hero_sunrise_sky(size, T: PlannerTheme, seed: int, hero_bottom: float = 1.0) -> Image.Image:
    w, h = size
    bg = hex_to_rgb255(T.cover_bg)
    img = _vertical_gradient(size, _mix(bg, (70, 140, 200), 0.35), _mix(bg, (255, 250, 235), 0.55))
    img = _radial_glow(img, (w * 0.78, h * 0.18), w * 0.55, (255, 244, 205), 0.75)
    img = _rays(img, (w * 0.78, h * 0.18), (255, 248, 220), count=13, strength=0.16, seed=seed)
    img = _bokeh(img, (255, 255, 255), count=16, seed=seed, strength=0.35)
    img = _grain(img, amount=3.0, seed=seed)
    return img


def _hero_teal_ledger(size, T: PlannerTheme, seed: int, hero_bottom: float = 1.0) -> Image.Image:
    w, h = size
    bg = hex_to_rgb255(T.cover_bg)
    img = _diagonal_gradient(size, _mix(bg, (0, 0, 0), 0.3), _mix(bg, (120, 200, 190), 0.16), 30)
    img = _radial_glow(img, (w * 0.5, h * 0.4), w * 0.6, _mix(bg, (180, 230, 220), 0.3), 0.4)
    img = _linen(img, seed=seed, alpha=8)
    return _vignette(img, 0.35, _mix(bg, (0, 0, 0), 0.5))


_RECIPES = {
    "claret_glow": _hero_claret_glow,
    "taupe_paper": _hero_taupe_paper,
    "blush_botanical": _hero_blush_botanical,
    "walnut_grain": _hero_walnut_grain,
    "sunrise_sky": _hero_sunrise_sky,
    "teal_ledger": _hero_teal_ledger,
}


def procedural_hero(T: PlannerTheme, size: tuple[int, int], *, seed: int = 7,
                    hero_bottom: float = 1.0) -> Image.Image:
    recipe = _RECIPES.get(T.cover_art) or _hero_claret_glow
    return recipe(size, T, seed, hero_bottom)


# --------------------------------------------------------------------------- #
# Image slot
# --------------------------------------------------------------------------- #
def load_slot_image(path: str, size: tuple[int, int]) -> tuple[Image.Image | None, str]:
    """Open a supplied photograph and fit it to the cover. Returns (image, note)."""
    if not path:
        return None, ""
    if not os.path.isfile(path):
        return None, f"Cover image not found: {os.path.basename(path)}; painted a themed cover instead."
    try:
        with Image.open(path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            if im.width < 600 or im.height < 600:
                return None, ("Cover image is too small to print well "
                              f"({im.width}x{im.height}); painted a themed cover instead.")
            fitted = ImageOps.fit(im, size, method=Image.LANCZOS, centering=(0.5, 0.42))
            return fitted, ""
    except Exception as exc:  # noqa: BLE001
        return None, f"Cover image could not be read ({type(exc).__name__}); painted a themed cover instead."


def _region_is_dark(img: Image.Image, box: tuple[float, float, float, float]) -> bool:
    w, h = img.size
    region = img.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
    region = region.resize((24, 24))
    px = list(region.convert("L").getdata())
    return (sum(px) / max(len(px), 1)) < 135


def _scrim(img: Image.Image, box: tuple[float, float, float, float],
           color: tuple[int, int, int], strength: float) -> Image.Image:
    """Soft rectangular wash with feathered edges, for type legibility."""
    w, h = img.size
    x0, y0, x1, y1 = int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rectangle([x0, y0, x1, y1], fill=int(255 * strength))
    mask = mask.filter(ImageFilter.GaussianBlur(radius=max(10, w // 22)))
    return Image.composite(Image.new("RGB", (w, h), color), img, mask)


# --------------------------------------------------------------------------- #
# Composition
# --------------------------------------------------------------------------- #
def build_cover_art(T: PlannerTheme, page_size_pt: tuple[float, float], *,
                    style: str = "", image_path: str = "", dpi: int = DEFAULT_DPI,
                    seed: int = 7) -> CoverArt:
    style = style if style in COVER_STYLES else T.cover_style_default
    w = max(600, int(round(page_size_pt[0] / 72.0 * dpi)))
    h = max(800, int(round(page_size_pt[1] / 72.0 * dpi)))
    size = (w, h)
    notes: list[str] = []

    hero, note = load_slot_image(image_path, size)
    source = "file" if hero is not None else "procedural"
    if note:
        notes.append(note)
    if hero is None:
        hero = procedural_hero(T, size, seed=seed, hero_bottom=0.56 if style == "photo_panel" else 1.0)
    else:
        hero = ImageEnhance.Color(hero).enhance(0.92)

    bg = hex_to_rgb255(T.cover_bg)
    panel_top = 0.0

    if style == "full_photo":
        img = hero
        title_box = (0.08, 0.16, 0.92, 0.58)
        dark_title_area = _region_is_dark(img, title_box)
        scrim_color = (18, 14, 12) if (dark_title_area or T.cover_is_dark) else (255, 252, 248)
        img = _scrim(img, title_box, scrim_color, 0.42)
        img = _vignette(img, 0.22, (0, 0, 0) if scrim_color[0] < 128 else (255, 255, 255))
        text_on_dark = scrim_color[0] < 128
    elif style == "photo_panel":
        panel_top = 0.56
        img = hero.copy()
        panel = Image.new("RGB", (w, int(h * (1 - panel_top)) + 2), bg)
        img.paste(panel, (0, int(h * panel_top)))
        # A soft feathered edge where the photo meets the panel.
        seam = Image.new("L", (w, h), 0)
        ImageDraw.Draw(seam).rectangle([0, int(h * panel_top) - 26, w, int(h * panel_top)], fill=140)
        seam = seam.filter(ImageFilter.GaussianBlur(radius=14))
        img = Image.composite(Image.new("RGB", (w, h), bg), img, seam)
        img = _grain(img, amount=3.0, seed=seed)
        text_on_dark = T.cover_is_dark
    elif style == "soft_overlay":
        wash = Image.new("RGB", size, bg)
        img = Image.blend(hero, wash, 0.62)
        img = _vignette(img, 0.30, _mix(bg, (0, 0, 0), 0.6) if T.cover_is_dark else _mix(bg, (0, 0, 0), 0.25))
        img = _grain(img, amount=4.0, seed=seed)
        text_on_dark = T.cover_is_dark
    else:  # minimal_texture
        paper = _mix(bg, (255, 255, 255), 0.10)
        img = _diagonal_gradient(size, _mix(paper, (255, 255, 255), 0.3), _mix(paper, (0, 0, 0), 0.06), 30)
        img = _radial_glow(img, (w * 0.3, h * 0.25), w * 0.9, (255, 255, 255), 0.32)
        img = _grain(img, amount=6.0, seed=seed)
        img = _linen(img, seed=seed, alpha=8)
        if T.cover_art == "blush_botanical":
            img = _botanicals(img, hex_to_rgb255(T.cover_accent), seed=seed, alpha=0.35, scale=0.9)
        text_on_dark = T.cover_is_dark

    img = _clamp_edges(img.convert("RGB"))
    return CoverArt(image=img, style=style, source=source, text_on_dark=text_on_dark,
                    dpi=dpi, panel_top_frac=panel_top, notes=notes)


def cover_art_effective_dpi(art: CoverArt, page_size_pt: tuple[float, float]) -> float:
    return art.image.width / (page_size_pt[0] / 72.0)


# --------------------------------------------------------------------------- #
# Optional: source a hero photograph through the Pexels workflow
# --------------------------------------------------------------------------- #
def source_pexels_cover(T: PlannerTheme, dest_dir: str, *, query: str = "",
                        orientation: str = "portrait") -> dict[str, Any]:
    """Fetch one faith-appropriate hero photo into `dest_dir` and return
    ``{"path": ..., "photo": {...}, "query": ...}``.

    This is the only network path in the planner engine. It is never called by
    a default build; a caller opts in by setting ``cover_image_source="pexels"``
    on the request. It fails closed under ``FACTORY_TEST_MODE`` and when no
    Pexels key is installed, raising rather than silently shipping a blank
    slot, so the caller can fall back to the procedural hero and say so.
    """
    from services.ebook_pexels import (
        PexelsError,
        download_pexels_original,
        pexels_configured,
        search_pexels,
    )
    from services.external_calls import assert_external_call_allowed

    assert_external_call_allowed("pexels")
    if not pexels_configured():
        raise PexelsError("Pexels is not configured; install a key to source cover photos.")
    queries = [q for q in ([query] if query else []) + list(T.pexels_queries) if q]
    last_error: Exception | None = None
    for q in queries:
        try:
            found = search_pexels(q, per_page=6, orientation=orientation)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
        photos = list(found.get("photos") or [])
        if not photos:
            continue
        photo = photos[0]
        payload = download_pexels_original(photo)
        os.makedirs(dest_dir, exist_ok=True)
        path = os.path.join(dest_dir, f"cover_hero_{T.key}.jpg")
        with open(path, "wb") as fh:
            fh.write(payload)
        return {"path": path, "photo": photo, "query": q}
    if last_error:
        raise last_error
    raise PexelsError("No Pexels photograph matched the theme's cover queries.")
