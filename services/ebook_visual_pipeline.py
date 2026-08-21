"""Content-aware ebook visual pipeline: plan, local assets, review, approval gates.

No paid APIs. No AI image generation. Charts/timelines/workflows/checklists are
rendered locally from approved manuscript data. Interior photographs may use
free Pexels stock with attribution; that path must never increment paid_calls
or spend_usd. Visuals cannot be approved unless every required asset exists on
disk with SHA, dimensions, source, caption, and chapter placement.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from services.ebook_book_layout import numbered_chapters
from services.ebook_fonts import ebook_font_paths
from services.ebook_visual_match import (
    MATCH_PASS,
    apply_match_report,
    customer_safe_visual_plan,
    customer_source_label,
    customer_visual_description,
    evaluate_photo_aid,
    photo_blocks_approval,
    stamp_plan_photo_matches,
    strip_customer_source_urls,
)

EXPORTS_DIR = os.environ.get("FACTORY_EXPORTS_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "exports"
)
_AID_META_KEYS = (
    "sha256",
    "width",
    "height",
    "source",
    "chapter",
    "chapter_index",
    "placement",
    "required",
    "chart_data",
    "table",
    "items",
    "rows",
    "columns",
    "attribution",
    "photographer",
    "page_url",
    "source_url",
    "photo_id",
)


@dataclass
class VisualValidation:
    ok: bool
    findings: list[str] = field(default_factory=list)
    required_count: int = 0
    resolved_count: int = 0

    @property
    def summary(self) -> str:
        if self.ok:
            return f"{self.resolved_count} visual asset(s) ready."
        return self.findings[0] if self.findings else "Visual plan is not approvable."


def _sha_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload or b"").hexdigest()


def _package_id(data: dict) -> str:
    return str(
        data.get("package_id")
        or data.get("artifact_id")
        or data.get("export_package_id")
        or "ebook-visuals-local"
    )


def visuals_dir(package_id: str) -> Path:
    return Path(EXPORTS_DIR) / str(package_id or "ebook-visuals-local") / "visuals"


PHOTO_AID_TYPES = {"photo", "stock photo"}


def is_photo_aid(aid: dict | None) -> bool:
    if not isinstance(aid, dict):
        return False
    kind = str(aid.get("type") or "").strip().lower()
    return kind in PHOTO_AID_TYPES


def photo_file_is_valid(path: str) -> bool:
    if not path or not os.path.isfile(path):
        return False
    try:
        if os.path.getsize(path) < 64:
            return False
        ok, w, h = _png_ok(path)
        return bool(ok and w >= 64 and h >= 64)
    except OSError:
        return False


def stamp_photo_aid_metadata(
    aid: dict[str, Any],
    *,
    status: str = "missing",
    error: str = "",
) -> dict[str, Any]:
    out = dict(aid or {})
    out["status"] = status
    out["retryable"] = status != "resolved"
    out["error"] = str(error or "")
    out["has_file"] = False
    out["rendered"] = False
    if status != "resolved":
        out["sha256"] = ""
    return out


def _font(size: int, *, bold: bool = False):
    paths = ebook_font_paths()
    path = paths.get("bold" if bold else "regular")
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _parse_tables(md: str) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    lines = str(md or "").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("|") and i + 1 < len(lines) and re.search(r"\|\s*-{3,}", lines[i + 1]):
            headers = [c.strip() for c in line.strip().strip("|").split("|")]
            i += 2
            rows: list[list[str]] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            if headers and rows:
                tables.append({"headers": headers, "rows": rows})
            continue
        i += 1
    return tables


def _parse_checklist(md: str) -> list[str]:
    items: list[str] = []
    in_list = False
    for line in str(md or "").splitlines():
        if re.match(r"(?i)^\*\*.*checklist.*\*\*", line) or re.match(r"(?i)^#{2,4}\s*.*checklist", line):
            in_list = True
            continue
        m = re.match(r"^\s*[-*]\s+(.+)$", line)
        if m and (in_list or "checklist" in str(md or "").lower()):
            items.append(m.group(1).strip())
            in_list = True
            continue
        if in_list and line.strip() and not line.strip().startswith(("-", "*")):
            if items and len(items) >= 3:
                break
            in_list = False
    if len(items) >= 3:
        return items[:8]
    bullets = [re.sub(r"^\s*[-*]\s+", "", ln).strip() for ln in str(md or "").splitlines() if re.match(r"^\s*[-*]\s+\S", ln)]
    return bullets[:8] if len(bullets) >= 4 else []


def _parse_workflow(md: str) -> list[str]:
    steps: list[str] = []
    for line in str(md or "").splitlines():
        m = re.match(r"^\s*(\d+)\.\s+(.+)$", line)
        if m:
            steps.append(m.group(2).strip())
    return steps[:8] if len(steps) >= 3 else []


def _numeric_series(table: dict[str, Any]) -> dict[str, Any] | None:
    headers = list(table.get("headers") or [])
    rows = list(table.get("rows") or [])
    if not headers or not rows:
        return None
    best = None
    for col in range(1, len(headers)):
        labels: list[str] = []
        values: list[float] = []
        for row in rows:
            if col >= len(row) or not row:
                continue
            raw = str(row[col])
            nums = [float(x.replace(",", "")) for x in re.findall(r"[0-9]+(?:\.[0-9]+)?", raw.replace(",", ""))]
            if not nums:
                continue
            labels.append(str(row[0])[:42])
            values.append(sum(nums) / len(nums))
        if len(values) >= 3:
            best = {"labels": labels, "values": values, "title": headers[col]}
            break
    return best


def _choose_aid(chapter_index: int, title: str, body: str) -> dict[str, Any] | None:
    """Pick at most one visual that adds instructional value. Omit when none."""
    tables = _parse_tables(body)
    workflow = _parse_workflow(body)
    checklist = _parse_checklist(body)
    blob = f"{title}\n{body}".lower()
    visual_id = f"v_ch{chapter_index}"

    if tables:
        series = _numeric_series(tables[0])
        if series and ("price" in blob or "budget" in blob or "$" in body or "range" in blob):
            return {
                "type": "chart",
                "visual_id": visual_id,
                "title": f"{title}: planning numbers",
                "caption": f"Planning figures drawn from the {title} table. Verify current supplier quotes before you buy.",
                "chart_data": {"kind": "bar", "labels": series["labels"], "values": series["values"]},
                "chapter": title,
                "chapter_index": chapter_index,
                "placement": "after_opening",
                "required": True,
                "source": "local_manuscript_chart",
            }
        headers = tables[0].get("headers") or []
        if len(headers) >= 3:
            return {
                "type": "comparison",
                "visual_id": visual_id,
                "title": f"{title}: side-by-side",
                "caption": f"Comparison graphic for {title}. Use it with the chapter table, not instead of it.",
                "table": tables[0],
                "chapter": title,
                "chapter_index": chapter_index,
                "placement": "after_opening",
                "required": True,
                "source": "local_manuscript_comparison",
            }

    if any(k in blob for k in ("30-day", "timeline", "days out", "week of")) and (workflow or tables):
        items = workflow or [f"{r[0]} — {r[1]}" for r in (tables[0].get("rows") or []) if len(r) >= 2][:7]
        if len(items) >= 3:
            return {
                "type": "timeline",
                "visual_id": visual_id,
                "title": f"{title}: sequence",
                "caption": f"Timeline for {title}. Keep dates and owners on the written plan.",
                "items": items,
                "chapter": title,
                "chapter_index": chapter_index,
                "placement": "after_opening",
                "required": True,
                "source": "local_manuscript_timeline",
            }

    if workflow:
        return {
            "type": "workflow",
            "visual_id": visual_id,
            "title": f"{title}: working sequence",
            "caption": f"Workflow graphic for {title}. Follow the chapter steps in order.",
            "items": workflow,
            "chapter": title,
            "chapter_index": chapter_index,
            "placement": "after_opening",
            "required": True,
            "source": "local_manuscript_workflow",
        }

    if checklist:
        return {
            "type": "checklist",
            "visual_id": visual_id,
            "title": f"{title}: field checklist",
            "caption": f"Printable checklist distilled from {title}.",
            "items": checklist,
            "chapter": title,
            "chapter_index": chapter_index,
            "placement": "after_opening",
            "required": True,
            "source": "local_manuscript_checklist",
        }
    return None


def plan_content_aware_visuals(
    manuscript_md: str,
    *,
    title: str = "",
    research: dict | None = None,
    include_photographs: bool = False,
) -> dict[str, Any]:
    """Build a per-chapter visual plan. Does not force a fixed visual count."""
    del research  # research is already baked into the approved manuscript; no new Tavily.
    chapters = numbered_chapters(manuscript_md)
    plan_chapters: list[dict[str, Any]] = []
    for i, (ctitle, body) in enumerate(chapters, start=1):
        aid = _choose_aid(i, ctitle, body)
        if aid is None and include_photographs:
            excerpt = re.sub(r"\s+", " ", str(body or "")).strip()[:400]
            first = excerpt.split(".")[0].strip() if excerpt else ctitle
            aid = {
                "type": "photo",
                "visual_id": f"v_ch{i}",
                "title": f"{ctitle}: chapter scene",
                "caption": first or ctitle,
                "chapter": ctitle,
                "chapter_index": i,
                "placement": "after_opening",
                "required": True,
                "source": "pexels",
                "chapter_body": excerpt,
                "status": "missing",
            }
        plan_chapters.append(
            {
                "chapter": ctitle,
                "chapter_index": i,
                "aids": [aid] if aid else [],
            }
        )
    return {
        "title": title,
        "source": "content_aware_local",
        "paid_images": False,
        "chapters": plan_chapters,
    }


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0], box[3] - box[1]


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> list[str]:
    words = str(text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = words[0]
    for w in words[1:]:
        trial = f"{cur} {w}"
        tw, _ = _text_size(draw, trial, font)
        if tw <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines[:8]


def _new_canvas(width: int = 1400, height: int = 900) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (width, height), (250, 248, 244))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width, 10), fill=(15, 76, 92))
    draw.rectangle((0, height - 10, width, height), fill=(15, 76, 92))
    return img, draw


def _draw_title(draw: ImageDraw.ImageDraw, title: str, width: int) -> None:
    font = _font(28, bold=True)
    for i, line in enumerate(_wrap(draw, title, font, width - 80)[:2]):
        draw.text((40, 28 + i * 34), line, font=font, fill=(15, 45, 58))


def _looks_currency(aid: dict[str, Any], values: list[float]) -> bool:
    data = aid.get("chart_data") or {}
    if data.get("currency"):
        return True
    blob = f"{aid.get('title') or ''} {aid.get('caption') or ''}".lower()
    if any(k in blob for k in ("$", "price", "cost", "budget", "package", "usd")):
        return True
    return bool(values) and all(v >= 50 for v in values)


def _fmt_chart_value(val: float, *, currency: bool) -> str:
    if currency:
        if abs(val - round(val)) < 0.05:
            return f"${val:,.0f}"
        return f"${val:,.2f}"
    if abs(val - round(val)) < 0.05:
        return f"{val:,.0f}"
    return f"{val:g}"


def _render_chart(aid: dict[str, Any]) -> Image.Image:
    data = aid.get("chart_data") or {}
    labels = list(data.get("labels") or [])
    values = [float(v) for v in (data.get("values") or [])]
    n = min(len(labels), len(values), 8)
    labels, values = labels[:n], values[:n]
    width, height = 1400, 720 if n <= 6 else 900
    img, draw = _new_canvas(width, height)
    _draw_title(draw, str(aid.get("title") or "Chart"), width)
    if not values:
        return img
    currency = _looks_currency(aid, values)
    max_v = max(values) or 1.0
    body = _font(16)
    value_font = _font(18, bold=True)
    if n <= 6:
        plot_top, plot_bottom = 130, height - 88
        gap = 36
        bar_w = min(170, max(72, (width - 160) // max(n, 1) - gap))
        total_w = n * bar_w + (n - 1) * gap
        x0 = (width - total_w) // 2
        for i, (lbl, val) in enumerate(zip(labels, values)):
            x = x0 + i * (bar_w + gap)
            bh = int((plot_bottom - plot_top) * (val / max_v))
            y = plot_bottom - max(bh, 8)
            draw.rounded_rectangle((x, y, x + bar_w, plot_bottom), 10, fill=(15, 118, 110))
            txt = _fmt_chart_value(val, currency=currency)
            tw, _ = _text_size(draw, txt, value_font)
            draw.text((x + (bar_w - tw) / 2, y - 32), txt, font=value_font, fill=(15, 45, 58))
            for j, line in enumerate(_wrap(draw, str(lbl), body, bar_w + 20)[:2]):
                lw, _ = _text_size(draw, line, body)
                draw.text((x + (bar_w - lw) / 2, plot_bottom + 10 + j * 18), line, font=body, fill=(30, 41, 59))
        return img
    top, bottom, left = 110, height - 80, 360
    bar_h = min(72, int((bottom - top) / max(n, 1)) - 12)
    for i, (lbl, val) in enumerate(zip(labels, values)):
        y = top + i * (bar_h + 18)
        bw = int((width - left - 80) * (val / max_v))
        draw.rounded_rectangle((left, y, left + max(bw, 8), y + bar_h), 8, fill=(15, 118, 110))
        for line in _wrap(draw, str(lbl), body, left - 60)[:2]:
            draw.text((40, y + 8), line, font=body, fill=(30, 41, 59))
        draw.text(
            (left + max(bw, 8) + 12, y + 16),
            _fmt_chart_value(val, currency=currency),
            font=value_font,
            fill=(15, 45, 58),
        )
    return img


def _short_items(items: list[str], limit: int = 6) -> list[str]:
    out: list[str] = []
    for raw in items[:limit]:
        text = re.sub(r"\*\*", "", str(raw or "")).strip()
        text = re.sub(r"\s+", " ", text)
        out.append(text[:72])
    return out


def _render_horizontal_steps(aid: dict[str, Any], items: list[str], *, kind: str) -> Image.Image:
    n = max(1, len(items))
    width, height = 1400, 460
    img, draw = _new_canvas(width, height)
    _draw_title(draw, str(aid.get("title") or kind.title()), width)
    accent = (180, 83, 9) if kind == "timeline" else (15, 76, 92)
    gap = 22
    box_w = min(210, max(120, (width - 80 - (n - 1) * gap) // n))
    total_w = n * box_w + (n - 1) * gap
    x0 = (width - total_w) // 2
    y0 = 150
    body = _font(16, bold=True)
    sub = _font(15)
    for i, item in enumerate(items):
        x = x0 + i * (box_w + gap)
        draw.rounded_rectangle((x, y0, x + box_w, y0 + 210), 12, fill=(255, 255, 255), outline=accent, width=2)
        draw.ellipse((x + box_w / 2 - 22, y0 + 18, x + box_w / 2 + 22, y0 + 62), fill=accent)
        num = str(i + 1)
        nw, _ = _text_size(draw, num, body)
        draw.text((x + (box_w - nw) / 2, y0 + 28), num, font=body, fill=(255, 255, 255))
        for j, line in enumerate(_wrap(draw, item, sub, box_w - 20)[:4]):
            lw, _ = _text_size(draw, line, sub)
            draw.text((x + (box_w - lw) / 2, y0 + 80 + j * 22), line, font=sub, fill=(15, 23, 42))
        if i < n - 1:
            ax = x + box_w + 4
            draw.polygon(
                [(ax, y0 + 100), (ax + gap - 8, y0 + 112), (ax, y0 + 124)],
                fill=accent,
            )
    return img


def _station_map_layout(aid: dict[str, Any]) -> bool:
    layout = str(aid.get("layout") or aid.get("composition") or "").lower()
    layout = layout.replace("-", "_").replace(" ", "_")
    return layout in {"station_map", "production_station", "workstation", "production_line"}


def _icon_prepare(draw: ImageDraw.ImageDraw, cx: float, cy: float, color: tuple[int, int, int]) -> None:
    draw.rounded_rectangle((cx - 22, cy - 6, cx + 22, cy + 20), 4, fill=color)
    draw.arc((cx - 10, cy - 20, cx + 10, cy + 2), 200, 340, fill=color, width=3)
    draw.line((cx, cy - 4, cx, cy + 18), fill=(15, 76, 92), width=3)


def _icon_camera(draw: ImageDraw.ImageDraw, cx: float, cy: float, color: tuple[int, int, int]) -> None:
    draw.rounded_rectangle((cx - 24, cy - 12, cx + 24, cy + 18), 6, fill=color)
    draw.rectangle((cx - 8, cy - 20, cx + 6, cy - 12), fill=color)
    draw.ellipse((cx - 10, cy - 8, cx + 12, cy + 14), fill=(15, 76, 92), outline=color, width=3)
    draw.ellipse((cx - 4, cy - 2, cx + 6, cy + 8), fill=color)
    draw.rectangle((cx + 14, cy - 8, cx + 20, cy - 2), fill=(15, 76, 92))


def _icon_payment(draw: ImageDraw.ImageDraw, cx: float, cy: float, color: tuple[int, int, int]) -> None:
    draw.rounded_rectangle((cx - 24, cy - 16, cx + 16, cy + 12), 4, fill=color)
    draw.rectangle((cx - 24, cy - 6, cx + 16, cy), fill=(15, 76, 92))
    draw.rectangle((cx - 18, cy + 2, cx - 8, cy + 8), fill=(15, 76, 92))
    draw.rounded_rectangle((cx - 4, cy - 4, cx + 24, cy + 22), 3, outline=color, width=3)
    draw.line((cx + 2, cy + 6, cx + 18, cy + 6), fill=color, width=2)
    draw.line((cx + 2, cy + 12, cx + 14, cy + 12), fill=color, width=2)


def _icon_queue(draw: ImageDraw.ImageDraw, cx: float, cy: float, color: tuple[int, int, int]) -> None:
    for dx, dy in ((-8, -10), (-2, -4), (6, 2)):
        draw.rounded_rectangle((cx - 16 + dx, cy - 14 + dy, cx + 14 + dx, cy + 16 + dy), 3, outline=color, width=3)
    draw.line((cx - 4, cy - 4, cx + 12, cy - 4), fill=color, width=2)
    draw.line((cx - 4, cy + 4, cx + 10, cy + 4), fill=color, width=2)
    draw.line((cx - 4, cy + 12, cx + 8, cy + 12), fill=color, width=2)


def _icon_printer(draw: ImageDraw.ImageDraw, cx: float, cy: float, color: tuple[int, int, int]) -> None:
    draw.rounded_rectangle((cx - 24, cy - 6, cx + 24, cy + 16), 4, fill=color)
    draw.rectangle((cx - 16, cy - 22, cx + 16, cy - 4), outline=color, width=3)
    draw.rectangle((cx - 10, cy - 16, cx + 10, cy - 8), fill=color)
    draw.rectangle((cx - 14, cy + 8, cx + 14, cy + 22), outline=color, width=3)
    draw.rectangle((cx - 8, cy + 12, cx + 8, cy + 18), fill=color)


def _icon_inspect(draw: ImageDraw.ImageDraw, cx: float, cy: float, color: tuple[int, int, int]) -> None:
    draw.ellipse((cx - 18, cy - 20, cx + 10, cy + 8), outline=color, width=4)
    draw.line((cx + 6, cy + 4, cx + 20, cy + 20), fill=color, width=4)
    draw.line((cx - 8, cy - 2, cx - 2, cy + 4), fill=color, width=3)
    draw.line((cx - 2, cy + 4, cx + 8, cy - 8), fill=color, width=3)


def _icon_pickup(draw: ImageDraw.ImageDraw, cx: float, cy: float, color: tuple[int, int, int]) -> None:
    draw.polygon(
        [(cx - 18, cy - 4), (cx - 22, cy + 20), (cx + 22, cy + 20), (cx + 18, cy - 4)],
        outline=color,
        width=3,
    )
    draw.arc((cx - 12, cy - 22, cx + 12, cy + 2), 200, 340, fill=color, width=3)
    draw.line((cx, cy - 4, cx, cy + 20), fill=color, width=3)
    draw.rectangle((cx + 10, cy - 16, cx + 26, cy + 8), outline=color, width=3)
    draw.line((cx + 10, cy - 6, cx + 26, cy - 6), fill=color, width=2)


_STATION_ICONS = (
    _icon_prepare,
    _icon_camera,
    _icon_payment,
    _icon_queue,
    _icon_printer,
    _icon_inspect,
    _icon_pickup,
)


def _draw_belt_arrow(draw: ImageDraw.ImageDraw, x0: float, y: float, x1: float, fill: tuple[int, int, int]) -> None:
    if x1 - x0 < 20:
        return
    draw.rectangle((x0, y - 5, x1 - 14, y + 5), fill=fill)
    draw.polygon([(x1 - 16, y - 12), (x1, y), (x1 - 16, y + 12)], fill=fill)


def _render_station_map(aid: dict[str, Any], items: list[str]) -> Image.Image:
    """Production-line / workstation map. Distinct from the horizontal booking workflow."""
    items = [str(x).strip() for x in items[:7] if str(x).strip()] or ["Station"]
    n = len(items)
    width, height = 1400, 900
    img, draw = _new_canvas(width, height)
    _draw_title(draw, str(aid.get("title") or "Production station"), width)
    accent = (15, 76, 92)
    ink = (15, 23, 42)
    floor = (236, 242, 239)
    white = (255, 255, 255)
    banner = _font(18, bold=True)
    label_font = _font(16, bold=True)
    num_font = _font(16, bold=True)
    direction_parts = ["Capture", "order", "print", "quality check", "pickup"]
    gap_w = 28
    part_sizes = [_text_size(draw, part, banner) for part in direction_parts]
    banner_w = sum(w for w, _ in part_sizes) + gap_w * (len(direction_parts) - 1) + 36
    bx0 = (width - banner_w) / 2
    draw.rounded_rectangle((bx0, 88, bx0 + banner_w, 128), 16, fill=accent)
    cursor = bx0 + 18
    for i, part in enumerate(direction_parts):
        pw, _ph = part_sizes[i]
        draw.text((cursor, 96), part, font=banner, fill=white)
        cursor += pw
        if i < len(direction_parts) - 1:
            ax = cursor + 8
            draw.polygon([(ax, 100), (ax + 12, 108), (ax, 116)], fill=white)
            cursor += gap_w

    draw.rounded_rectangle((36, 150, width - 36, height - 28), 18, fill=floor, outline=(203, 213, 225), width=2)
    draw.text((56, 164), "Production floor  ·  guest path follows the numbered stations", font=_font(14), fill=(71, 85, 105))

    top_count = min(4, n)
    bottom_items = items[top_count:]
    card_w, card_h = 286, 248
    gap = 36
    top_span = top_count * card_w + max(top_count - 1, 0) * gap
    top_x0 = (width - top_span) / 2
    top_y = 204
    bottom_y = 568
    aisle_y = (top_y + 176 + bottom_y) / 2
    boxes: list[tuple[float, float]] = []

    def _station(i: int, item: str, x: float, y: float) -> None:
        draw.rounded_rectangle((x, y + 168, x + card_w, y + card_h), 8, fill=(214, 219, 214))
        draw.rounded_rectangle((x, y, x + card_w, y + 176), 14, fill=white, outline=accent, width=3)
        draw.rectangle((x, y, x + 10, y + 176), fill=accent)
        pad = (x + card_w / 2 - 36, y + 36, x + card_w / 2 + 36, y + 108)
        draw.rounded_rectangle(pad, 16, fill=(232, 244, 242), outline=accent, width=2)
        icon = _STATION_ICONS[i] if i < len(_STATION_ICONS) else _icon_queue
        icon(draw, x + card_w / 2, y + 72, accent)
        badge = (x + 18, y + 12, x + 52, y + 46)
        draw.rounded_rectangle(badge, 6, fill=accent)
        num = str(i + 1)
        nw, nh = _text_size(draw, num, num_font)
        draw.text((x + 18 + (34 - nw) / 2, y + 12 + (34 - nh) / 2 - 1), num, font=num_font, fill=white)
        text_top = y + 118
        for j, line in enumerate(_wrap(draw, item, label_font, card_w - 28)[:3]):
            lw, _ = _text_size(draw, line, label_font)
            draw.text((x + (card_w - lw) / 2, text_top + j * 18), line, font=label_font, fill=ink)
        boxes.append((x, y))

    for i, item in enumerate(items[:top_count]):
        _station(i, item, top_x0 + i * (card_w + gap), top_y)
    bot_x0 = top_x0
    for j, item in enumerate(bottom_items):
        _station(top_count + j, item, bot_x0 + j * (card_w + gap), bottom_y)

    def _row_arrows(start: int, count: int, y: float) -> None:
        for i in range(start, start + count - 1):
            if i + 1 >= len(boxes):
                return
            x_a, _ = boxes[i]
            x_b, _ = boxes[i + 1]
            _draw_belt_arrow(draw, x_a + card_w + 4, y, x_b - 4, accent)

    _row_arrows(0, top_count, top_y + 88)
    if bottom_items:
        _row_arrows(top_count, len(bottom_items), bottom_y + 88)
        x_from = boxes[top_count - 1][0] + card_w / 2
        x_to = boxes[top_count][0] + card_w / 2
        draw.rectangle((x_from - 5, top_y + 176, x_from + 5, aisle_y + 5), fill=accent)
        left, right = min(x_from, x_to), max(x_from, x_to)
        draw.rectangle((left, aisle_y - 5, right, aisle_y + 5), fill=accent)
        draw.rectangle((x_to - 5, aisle_y - 5, x_to + 5, bottom_y - 8), fill=accent)
        draw.polygon(
            [(x_to - 12, bottom_y - 18), (x_to + 12, bottom_y - 18), (x_to, bottom_y + 2)],
            fill=accent,
        )
    return img


def _render_timeline_roadmap(aid: dict[str, Any], items: list[str]) -> Image.Image:
    n = max(1, len(items))
    width, height = 1400, 420
    img, draw = _new_canvas(width, height)
    _draw_title(draw, str(aid.get("title") or "Timeline"), width)
    accent = (180, 83, 9)
    left, right, y = 70, width - 70, 200
    draw.line((left, y, right, y), fill=accent, width=6)
    body = _font(15, bold=True)
    sub = _font(14)
    for i, item in enumerate(items):
        x = left + (right - left) * (i / max(n - 1, 1))
        draw.ellipse((x - 16, y - 16, x + 16, y + 16), fill=accent)
        draw.text((x - 5, y - 10), str(i + 1), font=_font(14, bold=True), fill=(255, 255, 255))
        lines = _wrap(draw, item, body if i % 2 == 0 else sub, 200)[:3]
        ty = y - 88 if i % 2 == 0 else y + 28
        for j, line in enumerate(lines):
            lw, _ = _text_size(draw, line, body)
            draw.text((x - lw / 2, ty + j * 20), line, font=body, fill=(15, 23, 42))
    return img


def _render_steps(aid: dict[str, Any], *, kind: str) -> Image.Image:
    items = _short_items([str(x) for x in (aid.get("items") or [])], 8)
    n = len(items) or 1
    height = min(900, 140 + n * 86)
    img, draw = _new_canvas(1400, height)
    _draw_title(draw, str(aid.get("title") or kind.title()), 1400)
    body = _font(18)
    y = 110
    accent = (180, 83, 9) if kind == "timeline" else (15, 76, 92)
    for i, item in enumerate(items, start=1):
        draw.rounded_rectangle((40, y, 1360, y + 72), 10, fill=(255, 255, 255), outline=accent, width=2)
        draw.ellipse((58, y + 14, 106, y + 62), fill=accent)
        if kind == "checklist":
            draw.text((70, y + 22), "☐", font=_font(22, bold=True), fill=(255, 255, 255))
        else:
            draw.text((74, y + 24), str(i), font=_font(18, bold=True), fill=(255, 255, 255))
        for j, line in enumerate(_wrap(draw, item, body, 1180)[:2]):
            draw.text((128, y + 14 + j * 24), line, font=body, fill=(15, 23, 42))
        y += 82
        if y > height - 40:
            break
    return img


def _render_comparison(aid: dict[str, Any]) -> Image.Image:
    table = aid.get("table") or {}
    headers = [str(h) for h in (table.get("headers") or [])][:4]
    rows = [[str(c) for c in r[:4]] for r in (table.get("rows") or [])][:6]
    img, draw = _new_canvas(1500, 980)
    _draw_title(draw, str(aid.get("title") or "Comparison"), 1500)
    if not headers:
        return img
    cols = len(headers)
    left, top, width, row_h = 36, 108, 1500 - 72, 96
    col_w = width // cols
    head_font = _font(16, bold=True)
    cell_font = _font(15)
    for c, h in enumerate(headers):
        x0 = left + c * col_w
        draw.rectangle((x0, top, x0 + col_w - 6, top + 56), fill=(15, 76, 92))
        for j, line in enumerate(_wrap(draw, h, head_font, col_w - 20)[:2]):
            draw.text((x0 + 10, top + 8 + j * 18), line, font=head_font, fill=(255, 255, 255))
    y = top + 64
    for r, row in enumerate(rows):
        bg = (255, 255, 255) if r % 2 == 0 else (236, 242, 239)
        for c in range(cols):
            x0 = left + c * col_w
            draw.rectangle((x0, y, x0 + col_w - 6, y + row_h - 8), fill=bg, outline=(203, 213, 225))
            text = row[c] if c < len(row) else ""
            for j, line in enumerate(_wrap(draw, text, cell_font, col_w - 20)[:3]):
                draw.text((x0 + 10, y + 10 + j * 20), line, font=cell_font, fill=(15, 23, 42))
        y += row_h
    return img


def render_aid_png(aid: dict[str, Any]) -> Image.Image:
    kind = str(aid.get("type") or "").lower()
    if kind == "chart":
        return _render_chart(aid)
    if kind == "comparison":
        return _render_comparison(aid)
    if kind == "photo":
        raise ValueError("Photograph aids must use a stored image file; they are not locally invented.")
    if kind == "workflow":
        raw_items = [str(x) for x in (aid.get("items") or [])]
        if _station_map_layout(aid):
            return _render_station_map(aid, _short_items(raw_items, 7))
        items = _short_items(raw_items, 6)
        if items and all(len(x) <= 48 for x in items):
            return _render_horizontal_steps(aid, items, kind="workflow")
        return _render_steps({**aid, "items": items}, kind="workflow")
    if kind == "timeline":
        items = _short_items([str(x) for x in (aid.get("items") or [])], 6)
        if items and all(len(x) <= 48 for x in items):
            return _render_timeline_roadmap(aid, items)
        return _render_steps({**aid, "items": items}, kind="timeline")
    if kind == "checklist":
        return _render_steps(aid, kind=kind)
    img, draw = _new_canvas()
    _draw_title(draw, str(aid.get("title") or "Visual"), 1400)
    return img


def required_aids(visual_plan: dict | None) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not isinstance(visual_plan, dict):
        return out
    for ch in visual_plan.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        for aid in ch.get("aids") or []:
            if isinstance(aid, dict) and not aid.get("omitted") and aid.get("required", True):
                out.append(aid)
    return out


def plan_is_valid(visual_plan: Any) -> bool:
    if not isinstance(visual_plan, dict):
        return False
    chapters = visual_plan.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        return False
    return all(isinstance(ch, dict) and str(ch.get("chapter") or "").strip() for ch in chapters)


def _aid_file(package_id: str, visual_id: str) -> Path:
    return visuals_dir(package_id) / f"{visual_id}.png"


def _stamp_aid_from_file(aid: dict[str, Any], path: Path, *, ctitle: str, cidx: int) -> None:
    payload = path.read_bytes()
    with Image.open(path) as img:
        w, h = img.size
    aid["asset_path"] = str(path)
    aid["sha256"] = _sha_bytes(payload)
    aid["width"] = int(w)
    aid["height"] = int(h)
    aid["source"] = str(aid.get("source") or "local_render")
    aid["chapter"] = aid.get("chapter") or ctitle
    aid["chapter_index"] = aid.get("chapter_index") or cidx
    aid["placement"] = aid.get("placement") or "after_opening"
    aid["caption"] = str(aid.get("caption") or aid.get("title") or "")
    aid["required"] = True
    aid["status"] = "resolved"


def prepare_interior_photo(image_bytes: bytes) -> Image.Image:
    """Resize a licensed photograph for interior use. No letterbox padding."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode not in {"RGB", "L"}:
        img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")
    img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
    if min(img.size) < 64:
        raise ValueError("Photograph is too small for an interior visual.")
    return img


def store_interior_photo(
    aid: dict[str, Any],
    image_bytes: bytes,
    *,
    package_id: str,
) -> dict[str, Any]:
    """Write a photograph PNG and stamp SHA/dimensions. Does not call Pexels."""
    vid = str(aid.get("visual_id") or "").strip()
    if not vid:
        raise ValueError("Photograph aid is missing visual_id.")
    dest = visuals_dir(package_id)
    dest.mkdir(parents=True, exist_ok=True)
    path = _aid_file(package_id, vid)
    img = prepare_interior_photo(image_bytes)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    path.write_bytes(buf.getvalue())
    out = json.loads(json.dumps(aid))
    out["type"] = "photo"
    _stamp_aid_from_file(
        out,
        path,
        ctitle=str(out.get("chapter") or ""),
        cidx=int(out.get("chapter_index") or 0),
    )
    out["source"] = str(out.get("source") or "pexels")
    return out


def materialize_visual_plan(visual_plan: dict, *, package_id: str) -> dict[str, Any]:
    """Render missing local PNG assets and stamp SHA/dimensions/source/path.

    Photograph aids are never invented: an existing file is stamped in place.
    """
    plan = json.loads(json.dumps(visual_plan))
    dest = visuals_dir(package_id)
    dest.mkdir(parents=True, exist_ok=True)
    for ch in plan.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        ctitle = str(ch.get("chapter") or "")
        cidx = int(ch.get("chapter_index") or 0)
        for aid in ch.get("aids") or []:
            if not isinstance(aid, dict) or aid.get("omitted"):
                continue
            vid = str(aid.get("visual_id") or "")
            if not vid:
                continue
            path = _aid_file(package_id, vid)
            kind = str(aid.get("type") or "").lower()
            if kind == "photo":
                existing = Path(str(aid.get("asset_path") or path))
                if existing.is_file() and existing != path:
                    path.write_bytes(existing.read_bytes())
                if not path.is_file():
                    aid["status"] = "missing"
                    continue
                _stamp_aid_from_file(aid, path, ctitle=ctitle, cidx=cidx)
                aid["source"] = str(aid.get("source") or "pexels")
                continue
            img = render_aid_png(aid)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            payload = buf.getvalue()
            path.write_bytes(payload)
            aid["asset_path"] = str(path)
            aid["sha256"] = _sha_bytes(payload)
            aid["width"] = int(img.size[0])
            aid["height"] = int(img.size[1])
            aid["source"] = str(aid.get("source") or "local_render")
            aid["chapter"] = aid.get("chapter") or ctitle
            aid["chapter_index"] = aid.get("chapter_index") or cidx
            aid["placement"] = aid.get("placement") or "after_opening"
            aid["caption"] = str(aid.get("caption") or aid.get("title") or "")
            aid["required"] = True
            aid["status"] = "resolved"
    plan["paid_images"] = False
    plan["source"] = plan.get("source") or "content_aware_local"
    return plan


def manifest_from_plan(visual_plan: dict | None) -> dict[str, Any]:
    assets: list[dict[str, Any]] = []
    for aid in required_aids(visual_plan):
        assets.append(
            {
                "visual_id": aid.get("visual_id"),
                "chapter": aid.get("chapter"),
                "chapter_index": aid.get("chapter_index"),
                "type": aid.get("type"),
                "title": aid.get("title"),
                "caption": aid.get("caption"),
                "sha256": aid.get("sha256"),
                "width": aid.get("width"),
                "height": aid.get("height"),
                "source": aid.get("source"),
                "asset_path": aid.get("asset_path"),
                "placement": aid.get("placement"),
                "attribution": aid.get("attribution") or "",
                "photographer": aid.get("photographer") or "",
                "page_url": aid.get("page_url") or aid.get("source_url") or "",
                "photo_id": aid.get("photo_id") or "",
            }
        )
    payload = {
        "slots": assets,
        "assets": assets,
        "paid_images": False,
        "source": "content_aware_local",
        "required_count": len(assets),
    }
    raw = json.dumps(
        {k: payload[k] for k in ("source", "paid_images", "required_count", "assets")},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    payload["digest"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return payload


def _file_sha(path: str) -> str:
    try:
        with open(path, "rb") as fh:
            return _sha_bytes(fh.read())
    except OSError:
        return ""


def _png_ok(path: str) -> tuple[bool, int, int]:
    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            w, h = img.size
        return w >= 64 and h >= 64, w, h
    except Exception:
        return False, 0, 0


def validate_visual_readiness(data: dict, *, html: str | None = None) -> VisualValidation:
    plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None
    findings: list[str] = []
    if not plan_is_valid(plan):
        return VisualValidation(False, ["Visuals cannot be approved without a valid visual plan."])
    required = required_aids(plan)
    resolved = 0
    for aid in required:
        vid = str(aid.get("visual_id") or "")
        path = str(aid.get("asset_path") or "")
        caption = str(aid.get("caption") or "").strip()
        source = str(aid.get("source") or "").strip()
        chapter = str(aid.get("chapter") or "").strip()
        sha = str(aid.get("sha256") or "").strip()
        if not vid:
            findings.append("A planned visual is missing a visual_id.")
            continue
        if not path or not os.path.isfile(path):
            findings.append(f"Visual {vid} has no existing local asset file.")
            continue
        try:
            size = os.path.getsize(path)
        except OSError:
            size = 0
        if size < 32:
            findings.append(f"Visual {vid} file is empty or corrupt.")
            continue
        ok, w, h = _png_ok(path)
        if not ok:
            findings.append(f"Visual {vid} file is corrupt or too small.")
            continue
        disk_sha = _file_sha(path)
        if not sha or sha != disk_sha:
            findings.append(f"Visual {vid} SHA does not match the local file.")
            continue
        if int(aid.get("width") or 0) != w or int(aid.get("height") or 0) != h:
            findings.append(f"Visual {vid} stored dimensions do not match the file.")
            continue
        if not source:
            findings.append(f"Visual {vid} is missing a source.")
            continue
        if not caption:
            findings.append(f"Visual {vid} is missing a caption.")
            continue
        if is_photo_aid(aid):
            attribution = str(aid.get("attribution") or "").strip()
            page_url = str(aid.get("page_url") or aid.get("source_url") or "").strip()
            source_l = source.lower()
            if not attribution:
                findings.append(f"Visual {vid} photograph is missing photographer attribution.")
                continue
            if "pexels" in source_l and not page_url:
                findings.append(f"Visual {vid} photograph is missing a Pexels source URL.")
                continue
            report = evaluate_photo_aid(aid)
            aid.update(apply_match_report(aid, report))
            block = photo_blocks_approval(aid)
            if block:
                idx = aid.get("chapter_index") or ""
                ctitle = str(aid.get("chapter") or "this chapter")
                findings.append(
                    f"We could not finish a visual for Chapter {idx}: {ctitle}."
                    if idx
                    else f"We could not finish a visual for {ctitle}."
                )
                continue
            if str(aid.get("match_status") or "") != MATCH_PASS:
                idx = aid.get("chapter_index") or ""
                ctitle = str(aid.get("chapter") or "this chapter")
                findings.append(
                    f"Chapter {idx}: {ctitle} still needs a visual review."
                    if idx
                    else f"{ctitle} still needs a visual review."
                )
                continue
            # Asset hash proves the file is present, not that the scene matches.
        if not chapter or not aid.get("placement") or not aid.get("chapter_index"):
            findings.append(f"Visual {vid} is missing chapter placement.")
            continue
        if html is not None:
            if f'data-visual-id="{vid}"' not in html and f"data-visual-id='{vid}'" not in html:
                findings.append(f"Visual {vid} is not rendered in preview HTML.")
                continue
            if sha not in html:
                findings.append(f"Visual {vid} SHA is missing from preview HTML.")
                continue
        resolved += 1
    ok = not findings
    return VisualValidation(ok, findings, required_count=len(required), resolved_count=resolved)


def visuals_are_ready(data: dict, *, html: str | None = None) -> bool:
    return validate_visual_readiness(data, html=html).ok


def _embed_preview_image(path: str, max_w: int = 720) -> tuple[str, int, int]:
    """JPEG data-URI for PDF/HTML. Stored PNG files and SHAs stay unchanged."""
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            w, h = img.size
            if w > max_w > 0:
                h = max(1, int(round(h * (max_w / float(w)))))
                w = max_w
                resample = getattr(Image, "Resampling", Image).LANCZOS
                img = img.resize((w, h), resample)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=82, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii"), w, h
    except Exception:
        return "", 0, 0


def figure_html(aid: dict[str, Any]) -> str:
    vid = _e(str(aid.get("visual_id") or ""))
    sha = _e(str(aid.get("sha256") or ""))
    cap = _e(strip_customer_source_urls(str(aid.get("caption") or aid.get("title") or "")))
    html_body = str(aid.get("html") or "").strip()
    if not html_body:
        raw_body = str(aid.get("body") or "").strip()
        if raw_body.startswith("<"):
            html_body = raw_body
    if html_body.startswith("<"):
        title = _e(strip_customer_source_urls(str(aid.get("title") or "")))
        heading = f'<div class="va-title">{title}</div>' if title else ""
        return (
            f'<figure class="ebook-figure ebook-figure-table" id="{vid}" '
            f'data-visual-id="{vid}" data-sha="{sha}">'
            f"{heading}{html_body}"
            f"<figcaption>{cap}</figcaption></figure>"
        )
    path = str(aid.get("asset_path") or "")
    if not path or not os.path.isfile(path):
        return ""
    uri, w, h = _embed_preview_image(path)
    if not uri:
        return ""
    return (
        f'<figure class="ebook-figure" id="{vid}" data-visual-id="{vid}" data-sha="{sha}">'
        f'<img src="{uri}" alt="{cap}" width="{w}" height="{h}"/>'
        f"<figcaption>{cap}</figcaption></figure>"
    )


def _e(value: str) -> str:
    import html as _html

    return _html.escape(str(value or ""))


def _table_aid(visual_id: str, title: str, caption: str, headers: list[str], rows: list[list[str]], chapter: str, chapter_index: int) -> dict[str, Any]:
    th = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(c)}</td>" for c in row) + "</tr>" for row in rows
    )
    html = f'<table class="va-table"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'
    return {
        "type": "table",
        "visual_id": visual_id,
        "title": title,
        "caption": caption,
        "html": html,
        "chapter": chapter,
        "chapter_index": chapter_index,
        "placement": "after_opening",
        "required": False,
        "source": "manuscript_table",
        "sha256": "",
        "omitted": False,
    }


def event_photo_teaching_tables() -> dict[int, list[dict[str, Any]]]:
    """Chapter-specific comparison/workflow tables derived from the stored manuscript."""
    return {
        1: [
            _table_aid(
                "v_ch1_niches",
                "How event niches actually differ",
                "From Chapter 1: the same camera can cover these jobs, but they do not behave the same way.",
                ["Niche", "What usually differs"],
                [
                    ["Weddings", "Higher expectations, more planning, family dynamics, backup gear, and insurance"],
                    ["Parties", "Energy and guest interaction more than formal coverage"],
                    ["Schools", "Volume, repeatable setups, permission rules, and organization"],
                    ["Churches", "Recurring gatherings and trust-based access"],
                    ["Reunions", "Multi-generation groups and name/relationship pressure"],
                    ["Community", "Public timeline, crowd flow, and variable lighting"],
                ],
                "What This Business Actually Looks Like",
                1,
            )
        ],
        3: [
            _table_aid(
                "v_ch3_kits",
                "Starter kit versus event-ready kit",
                "From Chapter 3: build a kit that keeps you shooting when lighting changes and gear fails.",
                ["Decision", "Starter path", "Event-ready path"],
                [
                    ["Bodies", "One capable camera body", "Primary and backup bodies"],
                    ["Lenses", "One or two versatile lenses", "Multiple lenses covering wide-to-medium roles"],
                    ["Power and cards", "Spare batteries and cards", "Redundant power, cards, and chargers"],
                    ["Printing", "Optional later", "Treated as its own station with supplies packed"],
                    ["Backup", "File plan before you leave", "Duplicate storage confirmed before the event"],
                ],
                "Core Camera Kit, Printing Equipment, and Backup Gear",
                3,
            )
        ],
        7: [
            _table_aid(
                "v_ch7_run",
                "Event-day run of show",
                "From Chapter 7: a profitable event day is usually won before the first guest arrives.",
                ["Phase", "What this phase protects"],
                [
                    ["Before", "One-page event map: contacts, times, load-in, power, shot priorities, roles"],
                    ["During", "Coverage keeps moving while print-station work stays assigned"],
                    ["After", "Print-delivery folders stay separate from archives; every file exists in more than one place"],
                ],
                "Event-Day Operations: From Photograph to Guest Delivery",
                7,
            )
        ],
        9: [
            _table_aid(
                "v_ch9_split",
                "Photo prints versus keepsakes",
                "From Chapter 9: mugs, buttons, shirts, and plates are not another version of a 4x6 print.",
                ["Question", "Fast dye-sub photo prints", "Keepsakes (mugs, buttons, shirts, plates)"],
                [
                    ["Equipment", "Event photo printer named in this guide", "Separate production tools"],
                    ["Time on site", "Minutes from image to dry print", "More handling steps and wait time"],
                    ["Staffing", "Can sit beside coverage if assigned", "Needs its own person and guest control"],
                    ["Safety", "Standard print-station setup", "Heat, cords, isolation, and inspection"],
                    ["When to add", "After capture-to-print is reliable", "One product line at a time, not on event one"],
                ],
                "Keepsakes Beyond Photo Prints: Separate Equipment and Workflow",
                9,
            )
        ],
    }


def merge_teaching_tables_into_plan(visual_plan: dict | None) -> dict:
    """Append manuscript-derived tables without dropping stored PNG aids."""
    plan = json.loads(json.dumps(visual_plan if isinstance(visual_plan, dict) else {"chapters": []}))
    extras = event_photo_teaching_tables()
    chapters = plan.get("chapters") or []
    for i, ch in enumerate(chapters, start=1):
        if not isinstance(ch, dict):
            continue
        idx = int(ch.get("chapter_index") or i)
        added = extras.get(idx) or extras.get(i) or []
        aids = list(ch.get("aids") or [])
        have = {str(a.get("visual_id") or "") for a in aids if isinstance(a, dict)}
        for extra in added:
            if extra["visual_id"] not in have:
                extra = dict(extra)
                extra["chapter"] = extra.get("chapter") or ch.get("chapter")
                extra["chapter_index"] = idx
                aids.append(extra)
        ch["aids"] = aids
        ch["chapter_index"] = idx
    plan["chapters"] = chapters
    return plan


def insert_planned_visuals_into_html(html_doc: str, visual_plan: dict | None) -> str:
    """Place each required visual into its chapter section. No manuscript rewrite."""
    if not html_doc or not isinstance(visual_plan, dict):
        return html_doc
    from bs4 import BeautifulSoup

    marker = "<!--FACTORY_PDF_NEXTPAGE-->"
    protected = re.sub(r"<pdf:nextpage\s*/>", marker, html_doc, flags=re.I)
    soup = BeautifulSoup(protected, "html.parser")
    sections = soup.select("section.chapter-page")
    by_index: dict[int, list[dict[str, Any]]] = {}
    by_title: dict[str, list[dict[str, Any]]] = {}
    for ch in visual_plan.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        aids = [a for a in (ch.get("aids") or []) if isinstance(a, dict) and not a.get("omitted")]
        idx = int(ch.get("chapter_index") or 0)
        title = str(ch.get("chapter") or "").strip().lower()
        if idx:
            by_index[idx] = aids
        if title:
            by_title[title] = aids
    for i, section in enumerate(sections, start=1):
        h2 = section.find("h2")
        title = (h2.get_text(" ", strip=True) if h2 else "").strip().lower()
        aids = by_title.get(title) or by_index.get(i) or []
        for aid in aids:
            existing = section.find(attrs={"data-visual-id": str(aid.get("visual_id") or "")})
            if existing:
                continue
            frag = BeautifulSoup(figure_html(aid), "html.parser")
            node = frag.find("figure")
            if node is None:
                continue
            h2 = section.find("h2")
            existing_figs = section.find_all("figure", class_="ebook-figure")
            if existing_figs:
                existing_figs[-1].insert_after(node)
            elif h2 is not None:
                h2.insert_after(node)
            else:
                section.append(node)
    restored = str(soup).replace(marker, "<pdf:nextpage />")
    restored = re.sub(r"<pdf:nextpage></pdf:nextpage>", "<pdf:nextpage />", restored, flags=re.I)
    return restored


def _thumb_data_uri(path: str) -> str:
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            img.thumbnail((360, 240))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=78)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


def write_visual_contact_sheet(visual_plan: dict, *, package_id: str) -> str:
    aids = required_aids(visual_plan)
    dest = visuals_dir(package_id)
    dest.mkdir(parents=True, exist_ok=True)
    cols = min(3, max(1, len(aids) or 1))
    rows = max(1, (len(aids) + cols - 1) // cols)
    cell_w, cell_h = 420, 300
    sheet = Image.new("RGB", (cols * cell_w + 40, rows * cell_h + 80), (248, 250, 252))
    draw = ImageDraw.Draw(sheet)
    draw.text((20, 16), "Visual Review contact sheet", font=_font(22, bold=True), fill=(15, 23, 42))
    for i, aid in enumerate(aids):
        r, c = divmod(i, cols)
        x, y = 20 + c * cell_w, 56 + r * cell_h
        path = str(aid.get("asset_path") or "")
        if path and os.path.isfile(path):
            with Image.open(path) as im:
                im = im.convert("RGB")
                im.thumbnail((cell_w - 24, cell_h - 70))
                sheet.paste(im, (x + 8, y + 8))
        cap = f"Ch {aid.get('chapter_index')}: {aid.get('type')}"
        draw.text((x + 8, y + cell_h - 48), cap[:48], font=_font(14, bold=True), fill=(15, 23, 42))
    out = dest / "contact_sheet.png"
    sheet.save(out, format="PNG")
    return str(out)


def _preview_data_uri(path: str, max_w: int = 1200) -> str:
    try:
        with Image.open(path) as img:
            img = img.convert("RGB")
            w, h = img.size
            if w > max_w > 0:
                h = max(1, int(round(h * (max_w / float(w)))))
                w = max_w
                img = img.resize((w, h), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=86)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        return ""


def visual_review_payload(data: dict) -> dict[str, Any]:
    plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {}
    if isinstance(plan, dict):
        stamp_plan_photo_matches(plan)
        data["visual_plan"] = plan
    report = validate_visual_readiness(data)
    assets = []
    technical_assets = []
    photo_blockers = 0
    unresolved_chapter = ""
    for aid in required_aids(plan):
        path = str(aid.get("asset_path") or "")
        is_photo = is_photo_aid(aid)
        match_status = str(aid.get("match_status") or "")
        if is_photo and match_status != MATCH_PASS:
            photo_blockers += 1
            if not unresolved_chapter:
                idx = aid.get("chapter_index") or ""
                unresolved_chapter = (
                    f"Chapter {idx}: {aid.get('chapter') or 'this chapter'}"
                    if idx
                    else str(aid.get("chapter") or "this chapter")
                )
        page_url = str(aid.get("page_url") or aid.get("source_url") or "") if is_photo else ""
        source_label = customer_source_label(aid)
        description = customer_visual_description(aid)
        assets.append(
            {
                "visual_id": aid.get("visual_id"),
                "chapter": aid.get("chapter"),
                "chapter_index": aid.get("chapter_index"),
                "type": aid.get("type"),
                "title": aid.get("title"),
                "caption": strip_customer_source_urls(str(aid.get("caption") or "")),
                "description": description,
                "source_label": source_label,
                "thumb_data_uri": _thumb_data_uri(path) if path else "",
                "preview_data_uri": _preview_data_uri(path) if path and is_photo else "",
                "has_file": bool(path and os.path.isfile(path)),
                "match_status": match_status,
                "internally_ready": bool(aid.get("internally_ready") or match_status == MATCH_PASS),
                "user_accepted": bool(aid.get("user_accepted")),
                "replace_enabled": is_photo,
            }
        )
        technical_assets.append(
            {
                "visual_id": aid.get("visual_id"),
                "sha256": aid.get("sha256"),
                "width": aid.get("width"),
                "height": aid.get("height"),
                "source": aid.get("source"),
                "placement": aid.get("placement"),
                "attribution": aid.get("attribution") or "",
                "photographer": aid.get("photographer") or "",
                "page_url": page_url,
                "photo_id": aid.get("photo_id") or "",
                "required_scene": aid.get("required_scene") or "",
                "appears_to_show": aid.get("appears_to_show") or "",
                "match_score": aid.get("match_score"),
                "match_status": match_status,
                "review_status": aid.get("review_status") or "",
                "passed_requirements": list(aid.get("passed_requirements") or []),
                "missing_requirements": list(aid.get("missing_requirements") or []),
                "rejection_reason": aid.get("rejection_reason") or "",
                "replacement_queries": list(aid.get("replacement_queries") or []),
                "recommended_replacement": aid.get("recommended_replacement") if isinstance(aid.get("recommended_replacement"), dict) else None,
                "user_accepted": bool(aid.get("user_accepted")),
                "seen_full_size": bool(aid.get("seen_full_size") or aid.get("full_size_viewed")),
            }
        )
    contact = str(data.get("ebook_visual_contact_sheet") or "")
    contact_uri = _preview_data_uri(contact, max_w=1400) if contact and os.path.isfile(contact) else ""
    approvable = bool(report.ok and assets and photo_blockers == 0)
    customer_findings = []
    if unresolved_chapter and not approvable:
        customer_findings.append(
            f"We could not finish a visual for {unresolved_chapter}. "
            "Your other visuals were kept. You can retry automatically or edit this visual."
        )
        if plan.get("customer_budget_message"):
            customer_findings.append(str(plan.get("customer_budget_message")))
    elif report.findings and not approvable:
        customer_findings = list(report.findings)[:3]
    from services.ebook_factory_pipeline import remaining_visual_budget_usd, visual_ai_authorized

    ai_edit_enabled = visual_ai_authorized(data) and remaining_visual_budget_usd(data) > 0
    heading = "Visuals Ready for Review"
    intro = (
        "Your chapter visuals have been selected and prepared. "
        "Review them below, then approve them to build your ebook preview."
    )
    return {
        "assets": assets,
        "technical_assets": technical_assets,
        "findings": customer_findings,
        "technical_findings": list(report.findings),
        "approvable": approvable,
        "required_count": report.required_count,
        "resolved_count": report.resolved_count,
        "plan_source": plan.get("source") if isinstance(plan, dict) else "",
        "paid_images": bool(data.get("visual_ai_spend_usd")),
        "contact_sheet": contact,
        "contact_sheet_data_uri": contact_uri,
        "private_review": True,
        "simplified_review": True,
        "heading": heading,
        "intro": intro,
        "progress": str(data.get("visual_progress_message") or data.get("visual_progress") or ""),
        "customer_message": str(plan.get("customer_visual_message") or (customer_findings[0] if customer_findings else "")),
        "budget_message": str(plan.get("customer_budget_message") or ""),
        "ai_edit_enabled": bool(ai_edit_enabled),
    }


def _assert_mutable(data: dict, action: str) -> None:
    from services.quality.artifact_state import assert_content_mutation_allowed

    assert_content_mutation_allowed(data, action=action)


def prepare_visuals_for_review(data: dict, *, preserve_downstream: bool = False) -> dict:
    """Create/reuse local visual assets and leave Visuals awaiting approval."""
    from services.ebook_project_workspace import (
        STATUS_AWAITING,
        STATUS_NEEDS_CORRECTION,
        _append_history,
        _recompute_next_action,
        ensure_workspace,
        is_approved,
        set_stage_status,
    )

    data = ensure_workspace(data)
    _assert_mutable(data, "prepare visuals")
    ws = data["ebook_workspace"]
    if not is_approved(ws, "manuscript"):
        raise ValueError("Approve the manuscript before visuals.")

    frozen = {
        "content": data.get("content"),
        "ebook": data.get("ebook"),
        "cover_design": data.get("cover_design"),
        "ebook_design": data.get("ebook_design"),
        "ebook_design_digest": data.get("ebook_design_digest"),
        "ebook_preview_html": data.get("ebook_preview_html"),
        "preview_html": data.get("preview_html"),
        "ebook_export_identity": data.get("ebook_export_identity"),
        "ebook_design_preflight": data.get("ebook_design_preflight"),
    }

    existing = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    from services.ebook_factory_pipeline import (
        PROGRESS_LOCAL,
        PROGRESS_PLANNING,
        PROGRESS_REVIEW,
        automatic_visuals_requested,
        fill_plan_photos_automatic,
        set_visual_progress,
        visual_ai_authorized,
    )

    automatic = automatic_visuals_requested(fields) or automatic_visuals_requested(data)
    if plan_is_valid(existing) and required_aids(existing):
        plan = existing
    else:
        set_visual_progress(data, PROGRESS_PLANNING)
        md = str(data.get("content") or data.get("ebook") or "")
        plan = plan_content_aware_visuals(
            md,
            title=str(data.get("title") or ""),
            research=ws.get("research_payload") if isinstance(ws.get("research_payload"), dict) else None,
            include_photographs=automatic,
        )
    pkg = _package_id(data)
    data["package_id"] = data.get("package_id") or pkg
    if automatic:
        plan = fill_plan_photos_automatic(
            plan,
            package_id=pkg,
            title=str(data.get("title") or ""),
            topic=str(data.get("topic") or data.get("title") or ""),
            audience=str(data.get("audience") or ""),
            data=data,
            fields=fields,
            allow_ai=visual_ai_authorized(data, fields),
        )
    set_visual_progress(data, PROGRESS_LOCAL)
    plan = materialize_visual_plan(plan, package_id=pkg)
    plan = stamp_plan_photo_matches(plan)
    set_visual_progress(data, PROGRESS_REVIEW)
    manifest = manifest_from_plan(plan)
    contact = write_visual_contact_sheet(plan, package_id=pkg)
    data["visual_plan"] = plan
    data["ebook_visual_manifest"] = manifest
    data["ebook_visual_manifest_digest"] = manifest["digest"]
    data["ebook_visual_contact_sheet"] = contact

    report = validate_visual_readiness(data)
    if report.ok and report.required_count:
        set_stage_status(ws, "visuals", STATUS_AWAITING, note="Visual plan ready for review")
    else:
        set_stage_status(
            ws,
            "visuals",
            STATUS_NEEDS_CORRECTION,
            note=report.summary,
        )
    _append_history(ws, "prepare_visuals", findings=report.findings[:8], required=report.required_count)
    if not preserve_downstream:
        _recompute_next_action(ws)
    else:
        ws["current_stage"] = "visuals"
        ws["next_action"] = "resolve_visuals"
        data["content"] = frozen["content"]
        data["ebook"] = frozen["ebook"]
        data["cover_design"] = frozen["cover_design"]
        data["ebook_design"] = frozen["ebook_design"]
        data["ebook_design_digest"] = frozen["ebook_design_digest"]
        data["ebook_preview_html"] = frozen["ebook_preview_html"]
        data["preview_html"] = frozen["preview_html"]
        data["ebook_export_identity"] = frozen["ebook_export_identity"]
        data["ebook_design_preflight"] = frozen["ebook_design_preflight"]
        data["visual_plan"] = plan
        data["ebook_visual_manifest"] = manifest
        data["ebook_visual_manifest_digest"] = manifest["digest"]
    return data


def approve_visual_plan(data: dict) -> dict:
    """Approve only when the visual plan and local assets are valid."""
    from services.ebook_project_workspace import (
        STATUS_APPROVED,
        STATUS_NEEDS_CORRECTION,
        _append_history,
        _recompute_next_action,
        assert_can_run_stage,
        ensure_workspace,
        is_approved,
        set_stage_status,
        sync_document_from_workspace,
    )

    data = ensure_workspace(data)
    _assert_mutable(data, "approve visuals")
    ws = data["ebook_workspace"]
    assert_can_run_stage(ws, "visuals")
    if not is_approved(ws, "manuscript"):
        raise ValueError("Approve the manuscript before visuals.")
    if not plan_is_valid(data.get("visual_plan")) or not required_aids(data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None):
        data = prepare_visuals_for_review(data)
    html = str(data.get("ebook_preview_html") or data.get("preview_html") or "") or None
    # Preview HTML is optional at visuals approval; require assets/files now.
    report = validate_visual_readiness(data, html=None)
    if not report.ok or not report.required_count:
        set_stage_status(ws, "visuals", STATUS_NEEDS_CORRECTION, note=report.summary)
        _recompute_next_action(ws)
        raise ValueError("Visuals cannot be approved: " + report.summary)
    if html:
        rendered = insert_planned_visuals_into_html(html, data.get("visual_plan"))
        html_report = validate_visual_readiness({**data, "visual_plan": data.get("visual_plan")}, html=rendered)
        if not html_report.ok and any("not rendered" in f or "SHA is missing" in f for f in html_report.findings):
            set_stage_status(ws, "visuals", STATUS_NEEDS_CORRECTION, note="Approved visuals must render in preview HTML.")
            _recompute_next_action(ws)
            raise ValueError("Visuals cannot be approved: preview HTML is missing rendered figures.")
    set_stage_status(ws, "visuals", STATUS_APPROVED, note="Visual plan and local assets validated")
    _append_history(ws, "approve", stage="visuals", paid_images=False, required=report.required_count)
    _recompute_next_action(ws)
    plan = data.get("visual_plan")
    manifest = data.get("ebook_visual_manifest")
    data = sync_document_from_workspace(data)
    if isinstance(plan, dict):
        data["visual_plan"] = plan
    if isinstance(manifest, dict):
        data["ebook_visual_manifest"] = manifest
        data["ebook_visual_manifest_digest"] = manifest.get("digest") or data.get("ebook_visual_manifest_digest")
    return data


def _find_aid(data: dict, visual_id: str) -> dict | None:
    vid = str(visual_id or "").strip()
    plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {}
    for ch in plan.get("chapters") or []:
        if not isinstance(ch, dict):
            continue
        for aid in ch.get("aids") or []:
            if isinstance(aid, dict) and str(aid.get("visual_id") or "") == vid:
                return aid
    return None


def mark_photo_full_size_viewed(data: dict, visual_id: str) -> dict:
    aid = _find_aid(data, visual_id)
    if aid is None:
        raise ValueError("Photograph not found.")
    aid["seen_full_size"] = True
    aid["full_size_viewed"] = True
    stamp_plan_photo_matches(data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {})
    return data


def accept_photo_aid(data: dict, visual_id: str) -> dict:
    """User explicitly accepts the current photograph after seeing it. Does not approve Visuals."""
    _assert_mutable(data, "accept photograph")
    aid = _find_aid(data, visual_id)
    if aid is None or not is_photo_aid(aid):
        raise ValueError("Photograph not found.")
    path = str(aid.get("asset_path") or "")
    if not path or not os.path.isfile(path):
        raise ValueError("Photograph file is missing.")
    aid["seen_full_size"] = True
    aid["full_size_viewed"] = True
    aid["user_accepted"] = True
    stamp_plan_photo_matches(data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {})
    return data


def replace_photo_aid(
    data: dict,
    visual_id: str,
    *,
    local_path: str = "",
    mode: str = "",
) -> dict:
    """Replace one photograph. Does not approve Visuals or rebuild the customer PDF."""
    from services.ebook_factory_pipeline import fill_photo_aid_automatic, fill_photo_aid_from_pexels

    _assert_mutable(data, "replace photograph")
    aid = _find_aid(data, visual_id)
    if aid is None or not is_photo_aid(aid):
        raise ValueError("Photograph not found.")
    pkg = _package_id(data)
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    mode_l = str(mode or "").strip().lower()
    rec = aid.get("recommended_replacement") if isinstance(aid.get("recommended_replacement"), dict) else {}
    source_path = str(local_path or rec.get("path") or "").strip()
    if source_path and os.path.isfile(source_path) and mode_l in {"", "upload", "local", "keep"}:
        payload = Path(source_path).read_bytes()
        rejected = list(aid.get("rejected_photo_ids") or [])
        old_id = str(aid.get("photo_id") or "")
        if old_id and old_id not in rejected:
            rejected.append(old_id)
        filled = store_interior_photo(aid, payload, package_id=pkg)
        filled["source"] = str(rec.get("source") or aid.get("source") or "pexels")
        filled["attribution"] = str(rec.get("attribution") or aid.get("attribution") or "")
        filled["photographer"] = str(rec.get("photographer") or aid.get("photographer") or "")
        filled["page_url"] = str(rec.get("page_url") or "")
        filled["source_url"] = filled["page_url"]
        filled["photo_id"] = str(rec.get("photo_id") or "")
        filled["alt"] = str(rec.get("appears_to_show") or rec.get("alt") or "")
        filled["rejected_photo_ids"] = rejected
        filled["user_accepted"] = False
        filled["seen_full_size"] = False
        filled["approved"] = False
        filled.pop("content_labels", None)
        filled.pop("inspected_labels", None)
        aid.clear()
        aid.update(filled)
    elif mode_l in {"keep", "keep-current"}:
        return data
    else:
        old_id = str(aid.get("photo_id") or "")
        rejected = list(aid.get("rejected_photo_ids") or [])
        if old_id and old_id not in rejected:
            rejected.append(old_id)
        aid["rejected_photo_ids"] = rejected
        aid["user_accepted"] = False
        aid["seen_full_size"] = False
        aid.pop("content_labels", None)
        aid.pop("inspected_labels", None)
        allow_ai = mode_l in {"ai", "generate-ai", "ai-alternative"}
        if allow_ai:
            filled = fill_photo_aid_automatic(
                aid,
                package_id=pkg,
                title=str(data.get("title") or ""),
                topic=str(data.get("topic") or data.get("title") or ""),
                audience=str(data.get("audience") or ""),
                chapter=str(aid.get("chapter") or ""),
                data=data,
                fields=fields,
                allow_ai=True,
            )
        else:
            filled = fill_photo_aid_from_pexels(
                aid,
                package_id=pkg,
                title=str(data.get("title") or ""),
                topic=str(data.get("topic") or data.get("title") or ""),
                audience=str(data.get("audience") or ""),
                chapter=str(aid.get("chapter") or ""),
            )
        filled["approved"] = False
        filled["user_accepted"] = False
        filled.pop("content_labels", None)
        filled.pop("inspected_labels", None)
        aid.clear()
        aid.update(filled)
    stamp_plan_photo_matches(data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {})
    data["ebook_visual_manifest"] = manifest_from_plan(data.get("visual_plan"))
    data["ebook_visual_manifest_digest"] = data["ebook_visual_manifest"].get("digest")
    try:
        data["ebook_visual_contact_sheet"] = write_visual_contact_sheet(
            data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {},
            package_id=pkg,
        )
    except Exception:
        pass
    return data


def reconcile_visuals_gate(data: dict, *, html: str | None = None) -> dict:
    """If Visuals is approved without valid assets, return it to Needs Correction."""
    from services.ebook_project_workspace import (
        STATUS_APPROVED,
        STATUS_NEEDS_CORRECTION,
        _append_history,
        _recompute_next_action,
        ensure_workspace,
        set_stage_status,
        stage_status,
    )

    data = ensure_workspace(data)
    ws = data["ebook_workspace"]
    if stage_status(ws, "visuals") != STATUS_APPROVED:
        return data
    report = validate_visual_readiness(data, html=html)
    if report.ok and report.required_count:
        return data
    try:
        _assert_mutable(data, "reconcile visuals")
    except Exception:
        return data
    set_stage_status(ws, "visuals", STATUS_NEEDS_CORRECTION, note=report.summary)
    _append_history(ws, "visuals_invalidated", findings=report.findings[:8])
    _recompute_next_action(ws)
    return data


def collect_zip_visual_files(data: dict) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None
    if plan:
        files["visual_plan.json"] = json.dumps(
            customer_safe_visual_plan(plan), indent=2, ensure_ascii=False
        ).encode("utf-8")
    manifest = data.get("ebook_visual_manifest") if isinstance(data.get("ebook_visual_manifest"), dict) else None
    if manifest:
        safe_manifest = json.loads(json.dumps(manifest))
        for row in list(safe_manifest.get("assets") or []) + list(safe_manifest.get("slots") or []):
            if isinstance(row, dict):
                row.pop("page_url", None)
                row.pop("source_url", None)
                row.pop("photographer_url", None)
                if row.get("caption"):
                    row["caption"] = strip_customer_source_urls(str(row.get("caption") or ""))
        files["visual_manifest.json"] = json.dumps(safe_manifest, indent=2, ensure_ascii=False).encode("utf-8")
    for aid in required_aids(plan):
        path = str(aid.get("asset_path") or "")
        vid = str(aid.get("visual_id") or "visual")
        if path and os.path.isfile(path):
            files[f"visuals/{vid}.png"] = Path(path).read_bytes()
    return files
