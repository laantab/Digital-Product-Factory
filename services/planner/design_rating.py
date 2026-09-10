"""Design rating for planner PDFs: the difference between 7, 8, 9 and 10.

The objective checks in `editor_in_chief_planner` catch defects. This module
answers a different question the Factory owner asked: *how good does it look*,
on a scale the marketplace understands --

    7  functional   -- it works, it prints, it is a form
    8  professional -- consistent chrome, real typography, clean tables
    9  premium      -- themed, guided, generous, nothing awkward
    10 exceptional  -- a photographic cover with excellent contrast, every
                       page composed, ready to compete with leading listings

Every criterion is measured on the rendered artifact (fonts and colours from
the PDF's own text spans, line pitch from its vector drawings, whitespace and
contrast from the page images). Nothing is taken from the builder's claims. A
10 requires positive evidence on every criterion; each shortfall costs a point
in the relevant category, so a good planner is not failed unnecessarily but
the top mark is reserved.
"""
from __future__ import annotations

import math
import os
import statistics
from typing import Any

TIERS = {10: "exceptional", 9: "premium", 8: "professional", 7: "functional"}

_STRUCTURAL_KINDS = ("cover", "ownership", "toc")
_WORKING_KINDS = (
    "open_table", "labeled_table", "faith_daily", "faith_weekly", "habit_tracker",
    "calendar_month", "prompt_page", "snapshot", "lined_notes", "reading_plan",
)


def tier_label(score: int) -> str:
    return TIERS.get(int(score), "functional" if score < 7 else "exceptional")


# --------------------------------------------------------------------------- #
# Collection: typography, drawings and cover geometry from the PDF itself
# --------------------------------------------------------------------------- #
def collect_design_facts(pdf_path: str) -> dict[str, Any]:
    """Per-page typography, vector-drawing and cover facts read with PyMuPDF."""
    facts: dict[str, Any] = {"pages": [], "cover": {}}
    if not pdf_path or not os.path.isfile(pdf_path):
        return facts
    try:
        import fitz
    except Exception:  # noqa: BLE001
        return facts
    doc = fitz.open(pdf_path)
    for pi, page in enumerate(doc):
        w, h = float(page.rect.width), float(page.rect.height)
        spans: list[dict[str, Any]] = []
        try:
            for block in page.get_text("dict").get("blocks", []):
                for line in block.get("lines", []):
                    for sp in line.get("spans", []):
                        txt = str(sp.get("text") or "").strip()
                        if not txt:
                            continue
                        spans.append({
                            "size": round(float(sp.get("size") or 0.0), 1),
                            "font": str(sp.get("font") or ""),
                            "color": int(sp.get("color") or 0),
                            "bbox": tuple(float(v) for v in sp.get("bbox") or (0, 0, 0, 0)),
                            "chars": len(txt),
                        })
        except Exception:  # noqa: BLE001
            pass
        draw_count = 0
        curves = 0
        h_lines: list[float] = []
        try:
            for item in page.get_drawings():
                draw_count += 1
                for seg in item.get("items", []):
                    kind = seg[0]
                    if kind == "c":
                        curves += 1
                    elif kind == "l":
                        p1, p2 = seg[1], seg[2]
                        if abs(p1.y - p2.y) < 0.3 and abs(p1.x - p2.x) > w * 0.3:
                            h_lines.append(round(float(p1.y), 1))
        except Exception:  # noqa: BLE001
            pass
        pitch = None
        ys = sorted(set(h_lines))
        gaps = [b - a for a, b in zip(ys, ys[1:]) if 8.0 <= (b - a) <= 40.0]
        if len(gaps) >= 3:
            pitch = statistics.median(gaps)
        facts["pages"].append({
            "page": pi + 1, "width": w, "height": h, "spans": spans,
            "draw_count": draw_count, "curves": curves, "rule_pitch": pitch,
        })
        if pi == 0:
            big = sorted(spans, key=lambda s: -s["size"])
            facts["cover"] = {
                "spans": spans,
                "title_bbox": big[0]["bbox"] if big else None,
                "title_size": big[0]["size"] if big else 0.0,
                "sizes": sorted({s["size"] for s in spans}, reverse=True),
                "fonts": sorted({s["font"] for s in spans}),
            }
    doc.close()
    return facts


# --------------------------------------------------------------------------- #
# Measurement helpers
# --------------------------------------------------------------------------- #
def _lum(rgb: tuple[int, int, int]) -> float:
    def ch(c: float) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _int_rgb(value: int) -> tuple[int, int, int]:
    return ((value >> 16) & 255, (value >> 8) & 255, value & 255)


def _hue_sat(value: str) -> tuple[float, float]:
    r, g, b = (c / 255.0 for c in _hex_rgb(value))
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    s = 0.0 if mx == 0 else d / mx
    if d == 0:
        return 0.0, s
    if mx == r:
        h = (60 * ((g - b) / d) + 360) % 360
    elif mx == g:
        h = 60 * ((b - r) / d) + 120
    else:
        h = 60 * ((r - g) / d) + 240
    return h, s


def _hex_rgb(value: str) -> tuple[int, int, int]:
    v = str(value or "").lstrip("#")
    if len(v) != 6:
        return (255, 255, 255)
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _image_region_stats(image_path: str, page_w: float, page_h: float,
                        bbox: tuple[float, float, float, float] | None) -> dict[str, float]:
    """Luminance percentiles inside a page-space bbox of a rendered page."""
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return {}
    if not bbox or not os.path.isfile(image_path):
        return {}
    with Image.open(image_path) as im:
        rgb = im.convert("RGB")
        iw, ih = rgb.size
        sx, sy = iw / page_w, ih / page_h
        x0, y0, x1, y1 = bbox
        pad = 6
        box = (max(0, int(x0 * sx) - pad), max(0, int(y0 * sy) - pad),
               min(iw, int(x1 * sx) + pad), min(ih, int(y1 * sy) + pad))
        if box[2] - box[0] < 4 or box[3] - box[1] < 4:
            return {}
        region = rgb.crop(box).convert("L")
        px = sorted(region.getdata())
    n = len(px)
    if not n:
        return {}
    p = lambda q: px[min(n - 1, int(q * n))]  # noqa: E731
    return {"p05": p(0.05), "p50": p(0.50), "p95": p(0.95), "n": n}


def _dark_ink_pct(image_path: str) -> float:
    """Share of the page that is dark ink (text, rules, fills), in percent."""
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return 0.0
    if not os.path.isfile(image_path):
        return 0.0
    with Image.open(image_path) as im:
        px = list(im.convert("L").resize((100, 130)).getdata())
    return 100.0 * sum(1 for v in px if v < 150) / max(len(px), 1)


def _body_band_ink(image_path: str, page_h: float, *, top_frac: float = 0.12,
                   bottom_frac: float = 0.09, bands: int = 6) -> list[float]:
    """Ink fraction per horizontal band of the body area (header/footer excluded)."""
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001
        return []
    if not os.path.isfile(image_path):
        return []
    with Image.open(image_path) as im:
        g = im.convert("L").resize((80, 104))
        px = list(g.getdata())
    w, h = 80, 104
    top = int(h * top_frac)
    bottom = h - int(h * bottom_frac)
    span = max(1, bottom - top)
    out: list[float] = []
    for b in range(bands):
        y0 = top + span * b // bands
        y1 = top + span * (b + 1) // bands
        rows = px[y0 * w:y1 * w]
        if not rows:
            out.append(0.0)
            continue
        out.append(sum(1 for v in rows if v < 245) / len(rows))
    return out


# --------------------------------------------------------------------------- #
# Rating
# --------------------------------------------------------------------------- #
def rate_planner_design(
    facts: dict[str, Any], *, page_kinds: list[str], page_images: list[str],
    page_stats: list[dict[str, Any]], design_stats: list[dict[str, Any]],
    theme: Any | None, cover_source: str, cover_dpi: float,
) -> dict[str, Any]:
    """Return {"cover": int, "interior": int, "rating": int, "tier": str,
    "deductions": [(category, code, reason)], "evidence": {...}}."""
    deductions: list[tuple[str, str, str]] = []
    evidence: dict[str, Any] = {}
    pages = facts.get("pages") or []
    cover = facts.get("cover") or {}
    paper = _hex_rgb(getattr(theme, "paper", "#FFFFFF")) if theme is not None else (255, 255, 255)

    # ---------------- cover ----------------
    if page_kinds and page_kinds[0] == "cover" and pages:
        pw, ph = pages[0]["width"], pages[0]["height"]
        # Artwork: a photograph is what leading listings carry.
        if cover_source not in ("file", "pexels"):
            deductions.append(("cover_quality", "DESIGN_COVER_NO_PHOTOGRAPH",
                               "cover artwork is painted, not photographic"))
        if 0 < cover_dpi < 200:
            deductions.append(("cover_quality", "DESIGN_COVER_SOFT_ARTWORK",
                               f"cover artwork at {cover_dpi:.0f} dpi; 200+ prints crisper"))
        # Hierarchy: the title must lead, with a supporting size below it.
        sizes = cover.get("sizes") or []
        title_size = float(cover.get("title_size") or 0.0)
        min_title = 0.045 * pw  # ~27.5 pt on Letter
        if title_size < min_title:
            deductions.append(("cover_quality", "DESIGN_COVER_TITLE_SMALL",
                               f"title {title_size:.0f} pt; expected at least {min_title:.0f} pt at this size"))
        if len(sizes) >= 2 and sizes[1] > 0 and title_size / sizes[1] < 1.8:
            deductions.append(("cover_quality", "DESIGN_COVER_FLAT_HIERARCHY",
                               "title is not clearly larger than the next line"))
        if len(set(cover.get("fonts") or [])) < 2:
            deductions.append(("cover_quality", "DESIGN_COVER_ONE_FACE",
                               "cover uses a single type face; premium covers pair two"))
        # Legibility: contrast of the title against what sits behind it.
        stats = _image_region_stats(page_images[0] if page_images else "", pw, ph, cover.get("title_bbox"))
        if stats:
            ink, bg = (stats["p05"], stats["p95"]) if stats["p50"] > 127 else (stats["p95"], stats["p05"])
            ratio = contrast_ratio((ink, ink, ink), (bg, bg, bg))
            evidence["cover_title_contrast"] = round(ratio, 2)
            if ratio < 3.0:
                deductions.append(("cover_quality", "DESIGN_COVER_WEAK_CONTRAST",
                                   f"title contrast {ratio:.1f}:1 against its background; 4.5:1 expected"))
            elif ratio < 4.5:
                deductions.append(("cover_quality", "DESIGN_COVER_SOFT_CONTRAST",
                                   f"title contrast {ratio:.1f}:1; 4.5:1 expected"))
        # Every label on the cover must read, not only the title: the
        # ownership line and the caption sit where a photograph is busiest.
        lost = 0
        for s in cover.get("spans") or []:
            if s["chars"] < 3 or s["bbox"] == cover.get("title_bbox"):
                continue
            st = _image_region_stats(page_images[0] if page_images else "", pw, ph, s["bbox"])
            if not st:
                continue
            bg = (int(st["p50"]),) * 3
            if contrast_ratio(_int_rgb(s["color"]), bg) < (4.5 if s["size"] < 8.0 else 3.0):
                lost += 1
        evidence["cover_labels_low_contrast"] = lost
        if lost:
            deductions.append(("cover_quality", "DESIGN_COVER_LABEL_LOST",
                               f"{lost} cover label(s) sit on a background they cannot be read against"))
        # Whitespace: type should occupy a modest share of the cover.
        spans = cover.get("spans") or []
        area = sum(max(0.0, s["bbox"][2] - s["bbox"][0]) * max(0.0, s["bbox"][3] - s["bbox"][1]) for s in spans)
        share = area / max(pw * ph, 1.0)
        evidence["cover_text_share"] = round(share, 4)
        if share > 0.22:
            deductions.append(("cover_quality", "DESIGN_COVER_CROWDED",
                               f"type covers {share:.0%} of the cover"))
        elif share < 0.012:
            deductions.append(("cover_quality", "DESIGN_COVER_LOST_TYPE",
                               f"type covers only {share:.1%} of the cover"))
        # Cover / interior compatibility: the interior primary should share the
        # cover's family of colour.
        if theme is not None and design_stats and not getattr(theme, "is_neutral", False):
            cov = next((s for s in design_stats if s["page"] == 1), None)
            if cov and cov.get("dominant_hue") is not None and (cov.get("color_pct") or 0) > 1.0:
                ch = float(cov["dominant_hue"]) + 5.0
                palette = []
                for token in ("primary", "accent", "cover_bg", "cover_accent"):
                    hh, ss = _hue_sat(getattr(theme, token, "#000000"))
                    if ss >= 0.18:
                        palette.append(hh)
                if palette and all(min(abs(ch - ph), 360 - abs(ch - ph)) > 45 for ph in palette):
                    deductions.append(("cover_quality", "DESIGN_COVER_INTERIOR_MISMATCH",
                                       "cover colour family is outside the theme's palette"))

    # ---------------- interior ----------------
    interior_pages = [(i, k) for i, k in enumerate(page_kinds, start=1) if k != "cover" and i - 1 < len(pages)]
    working = [(i, k) for i, k in interior_pages if k in _WORKING_KINDS]
    n_int = max(len(interior_pages), 1)
    n_work = max(len(working), 1)

    # Typography: at least two faces and a real size ladder on every page.
    weak_type = 0
    for i, _k in interior_pages:
        sp = pages[i - 1]["spans"]
        faces = {s["font"] for s in sp}
        sizes = {s["size"] for s in sp}
        if len(faces) < 2 or not (3 <= len(sizes) <= 8):
            weak_type += 1
    evidence["pages_with_weak_typography"] = weak_type
    if weak_type / n_int > 0.2:
        deductions.append(("interior_design", "DESIGN_TYPOGRAPHY_FLAT",
                           f"{weak_type} of {n_int} pages lack a type pairing or a size ladder"))

    # Contrast: body text must read; small labels need more. The background
    # is measured behind each span on the rendered page (a band, a panel or
    # the paper), so gold on a dark band is judged against the band.
    weak_contrast = 0
    for i, _k in interior_pages:
        img = page_images[i - 1] if i - 1 < len(page_images) else ""
        pw, ph = pages[i - 1]["width"], pages[i - 1]["height"]
        for s in pages[i - 1]["spans"]:
            if s["chars"] < 3:
                continue
            bg = paper
            st = _image_region_stats(img, pw, ph, s["bbox"]) if img else {}
            if st:
                # Glyphs cover a minority of a padded text box, so the median
                # luminance of the box is the surface the text sits on.
                bg = (int(st["p50"]),) * 3
            ratio = contrast_ratio(_int_rgb(s["color"]), bg)
            need = 4.5 if s["size"] < 8.0 else 3.0
            if ratio < need:
                weak_contrast += 1
                break
    evidence["pages_with_weak_contrast"] = weak_contrast
    if weak_contrast:
        deductions.append(("interior_design", "DESIGN_WEAK_CONTRAST",
                           f"{weak_contrast} page(s) carry text below the contrast floor"))

    # Whitespace balance on working pages: not empty, not crowded. Crowding
    # is measured on dark ink (text and rules); light tints are breathing room.
    ink_by_page = {int(s["page"]): float(s["ink_pct"]) for s in page_stats or []}
    empties = [i for i, _k in working if ink_by_page.get(i, 0.0) < 9.0]
    crowded = []
    for i, _k in working:
        dark = _dark_ink_pct(page_images[i - 1]) if i - 1 < len(page_images) else 0.0
        if dark > 28.0:
            crowded.append(i)
    evidence["working_pages_thin"] = len(empties)
    evidence["working_pages_crowded"] = len(crowded)
    if len(empties) / n_work > 0.12:
        deductions.append(("interior_design", "DESIGN_PAGES_THIN",
                           f"{len(empties)} working pages are mostly empty"))
    if len(crowded) / n_work > 0.12:
        deductions.append(("interior_design", "DESIGN_PAGES_CROWDED",
                           f"{len(crowded)} working pages are overcrowded"))

    # Awkward empty areas: content that stops well above the footer.
    tails = 0
    for i, k in interior_pages:
        if k in _STRUCTURAL_KINDS or i - 1 >= len(page_images):
            continue
        bands = _body_band_ink(page_images[i - 1], pages[i - 1]["height"])
        if len(bands) >= 6 and sum(bands[:3]) / 3 > 0.06 and max(bands[-2:]) < 0.012:
            tails += 1
    evidence["pages_with_empty_tail"] = tails
    if tails / n_int > 0.12:
        deductions.append(("interior_design", "DESIGN_AWKWARD_EMPTY_AREA",
                           f"{tails} pages leave the lower part of the page bare"))

    # Writing usability: ruled lines must leave room for a pen.
    pitches = [pages[i - 1]["rule_pitch"] for i, _k in working if pages[i - 1]["rule_pitch"]]
    if pitches:
        evidence["median_rule_pitch_pt"] = round(statistics.median(pitches), 1)
        if statistics.median(pitches) < 16.0:
            deductions.append(("interior_design", "DESIGN_WRITING_LINES_TIGHT",
                               f"writing lines {statistics.median(pitches):.0f} pt apart; 16 pt or more expected"))

    # Decorative treatment: present but restrained, and not a bare form.
    plain = 0
    heavy = 0
    for i, _k in working:
        pg = pages[i - 1]
        if pg["curves"] == 0:
            plain += 1
        if pg["draw_count"] > 900:
            heavy += 1
    evidence["working_pages_without_ornament"] = plain
    if plain / n_work > 0.12:
        deductions.append(("interior_design", "DESIGN_GENERIC_WORKSHEET",
                           f"{plain} working pages have no rounded or drawn element; they read as forms"))
    if heavy / n_work > 0.12:
        deductions.append(("interior_design", "DESIGN_OVER_DECORATED",
                           f"{heavy} working pages carry heavy decoration"))

    # Consistency: the same type ladder page to page (the footer size, the
    # heading size) -- measured as the spread of the dominant heading size.
    heads = []
    for i, k in interior_pages:
        if k in _STRUCTURAL_KINDS:
            continue
        sp = pages[i - 1]["spans"]
        if sp:
            heads.append(max(s["size"] for s in sp))
    if len(heads) >= 3 and (max(heads) - min(heads)) > 6.0:
        deductions.append(("interior_design", "DESIGN_INCONSISTENT_HEADINGS",
                           f"heading sizes range {min(heads):.0f}-{max(heads):.0f} pt across pages"))

    cover_score = 10 - sum(1 for c, _code, _r in deductions if c == "cover_quality")
    interior_score = 10 - sum(1 for c, _code, _r in deductions if c == "interior_design")
    cover_score = max(6, cover_score)
    interior_score = max(6, interior_score)
    rating = min(cover_score, interior_score)
    return {
        "cover": cover_score, "interior": interior_score, "rating": rating,
        "tier": tier_label(rating), "deductions": deductions, "evidence": evidence,
    }
