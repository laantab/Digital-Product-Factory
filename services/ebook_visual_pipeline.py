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
    """The folder this book's assets live in. Must be unique per book.

    The fallback used to be the shared literal "ebook-visuals-local", so every
    ebook that reached this point without an id wrote its visuals, cover, PDF
    and ZIP into the SAME folder -- silently overwriting the previous book's
    finished files. Two real customer projects were found sharing it. The
    fallback is now derived from the project, and only a genuinely anonymous
    payload gets a random one.
    """
    existing = str(
        data.get("package_id")
        or data.get("artifact_id")
        or data.get("export_package_id")
        or ""
    ).strip()
    if existing and existing != "ebook-visuals-local":
        return existing

    project_id = str(data.get("_project_id") or data.get("project_id") or "").strip()
    if project_id.isdigit():
        return f"ebook-{project_id}"
    import hashlib

    seed = f"{data.get('title') or ''}|{data.get('subtitle') or ''}|{data.get('source') or ''}"
    if seed.strip("|"):
        return "ebook-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]
    import uuid

    return "ebook-" + uuid.uuid4().hex[:12]


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


#: Ambient render scale. 1.0 == the layouts below as originally tuned (every
#: coordinate, radius and font size in every _render_* function is a literal
#: number sized for a 1x canvas). Rendering at a higher resolution should mean
#: re-running those same drawing instructions at a larger scale, not resizing
#: the finished PNG afterward -- so this is a single shared multiplier that
#: _new_canvas/_font/_ScaledDraw apply consistently, and no _render_* function
#: needs to change at all.
_RENDER_SCALE = [1.0]


class _RenderScale:
    """Context manager: `with _RenderScale(2.0): render_aid_png(aid)`."""

    def __init__(self, scale: float) -> None:
        self.scale = float(scale)
        self._prev = 1.0

    def __enter__(self) -> "_RenderScale":
        self._prev = _RENDER_SCALE[0]
        _RENDER_SCALE[0] = self.scale
        return self

    def __exit__(self, *exc: object) -> None:
        _RENDER_SCALE[0] = self._prev


def _sc(value: float) -> float:
    return value * _RENDER_SCALE[0]


def _sc_xy(seq):
    """Scale a coordinate tuple/list of tuples for a PIL draw call."""
    if not seq:
        return seq
    if isinstance(seq[0], (int, float)):
        return tuple(_sc(v) for v in seq)
    return [tuple(_sc(v) for v in pt) for pt in seq]


#: Same context-manager-and-module-list pattern as _RENDER_SCALE above, for
#: the same reason: every _render_* function already reads its colors from
#: one place (a handful of hardcoded RGB tuples), so making that one place
#: swappable makes every structured diagram theme-aware without changing
#: those functions' call signatures.
#:
#: THE DEFECT THIS FIXES
#: ----------------------
#: Every generated diagram (infographics, timelines, habit loops, calendars,
#: step cards) drew in the same fixed teal-and-slate palette no matter which
#: design theme was selected -- a Bold Creator or Modern Business book showed
#: the identical Warm-Wellness-colored chart. Found reviewing rendered pages
#: side by side across themes, not by reading the CSS (these are raster PNGs;
#: CSS variables never reach them).
_RENDER_PALETTE: list[dict[str, tuple[int, int, int]] | None] = [None]

#: Fallback palette: exactly the literal colors every _render_* function used
#: before this existed, so a caller that never sets a palette (or a theme
#: that leaves its diagram_*_rgb fields blank) renders pixel-identical output.
_DEFAULT_PALETTE: dict[str, tuple[int, int, int]] = {
    "primary": (15, 76, 92),
    "accent": (15, 118, 110),
    "secondary": (180, 83, 9),
    "text": (15, 45, 58),
}


class _RenderPalette:
    """Context manager: `with _RenderPalette(palette): render_aid_png(aid)`.

    `palette` is a dict with any of "primary"/"accent"/"secondary"/"text" as
    (R, G, B) tuples; missing keys fall back to _DEFAULT_PALETTE, so a theme
    only has to override the colors it actually wants to change.
    """

    def __init__(self, palette: dict[str, tuple[int, int, int]] | None) -> None:
        self.palette = palette
        self._prev: dict[str, tuple[int, int, int]] | None = None

    def __enter__(self) -> "_RenderPalette":
        self._prev = _RENDER_PALETTE[0]
        _RENDER_PALETTE[0] = self.palette
        return self

    def __exit__(self, *exc: object) -> None:
        _RENDER_PALETTE[0] = self._prev


def _pal(key: str, default: tuple[int, int, int] | None = None) -> tuple[int, int, int]:
    """The current theme's color for `key`, or the long-standing default."""
    active = _RENDER_PALETTE[0]
    if active and key in active:
        return active[key]
    return default if default is not None else _DEFAULT_PALETTE.get(key, (15, 76, 92))


def theme_diagram_palette(theme) -> dict[str, tuple[int, int, int]]:
    """Build a _RenderPalette-ready dict from an EbookTheme's diagram_*_rgb
    fields ("R,G,B" strings). A theme that leaves a field blank contributes
    nothing for that key, so _pal() falls through to _DEFAULT_PALETTE."""
    out: dict[str, tuple[int, int, int]] = {}
    field_map = {
        "primary": "diagram_primary_rgb",
        "accent": "diagram_accent_rgb",
        "secondary": "diagram_secondary_rgb",
        "text": "diagram_text_rgb",
    }
    for key, field in field_map.items():
        raw = str(getattr(theme, field, "") or "").strip()
        if not raw:
            continue
        try:
            parts = tuple(int(p.strip()) for p in raw.split(","))
        except ValueError:
            continue
        if len(parts) == 3:
            out[key] = parts  # type: ignore[assignment]
    return out


class _ScaledDraw:
    """Wraps ImageDraw so every _render_* function can keep its original,
    already-tuned 1x coordinates. Shape/line calls are scaled on the way in;
    text is measured back down to 1x space so _wrap()'s line-breaking
    decisions never change, and painted at the scaled position with the
    already-scaled font from _font().
    """

    def __init__(self, draw: "ImageDraw.ImageDraw") -> None:
        self._d = draw

    def rectangle(self, xy, *a, **k):
        return self._d.rectangle(_sc_xy(xy), *a, **k)

    def rounded_rectangle(self, xy, radius=0, *a, **k):
        return self._d.rounded_rectangle(_sc_xy(xy), _sc(radius), *a, **k)

    def ellipse(self, xy, *a, **k):
        return self._d.ellipse(_sc_xy(xy), *a, **k)

    def line(self, xy, *a, fill=None, width=1, **k):
        return self._d.line(_sc_xy(xy), *a, fill=fill, width=max(1, round(_sc(width))), **k)

    def polygon(self, xy, *a, **k):
        return self._d.polygon(_sc_xy(xy), *a, **k)

    def arc(self, xy, start, end, *a, width=1, **k):
        return self._d.arc(_sc_xy(xy), start, end, *a, width=max(1, round(_sc(width))), **k)

    def text(self, xy, text, *a, **k):
        x, y = xy
        return self._d.text((_sc(x), _sc(y)), text, *a, **k)

    def textbbox(self, xy, text, *a, **k):
        x, y = xy
        box = self._d.textbbox((_sc(x), _sc(y)), text, *a, **k)
        s = _RENDER_SCALE[0]
        return tuple(v / s for v in box)

    def __getattr__(self, name):
        return getattr(self._d, name)


def _font(size: int, *, bold: bool = False):
    paths = ebook_font_paths()
    path = paths.get("bold" if bold else "regular")
    scaled_size = max(1, round(_sc(size)))
    if path:
        try:
            return ImageFont.truetype(path, scaled_size)
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


def _parse_checkbox_items(md: str) -> list[str]:
    """Only true '- [ ]' checkboxes — things the reader is meant to tick.

    _parse_checklist falls back to any bullet list of four or more, which means
    an ordinary prose bullet list can outrank a rich comparison table. A real
    checkbox list is a deliberate authoring signal; a bullet list is not.
    """
    items = [
        m.group(1).strip()
        for m in (
            re.match(r"^\s*[-*]\s*\[\s*[xX ]?\s*\]\s*(.+)$", ln)
            for ln in str(md or "").splitlines()
        )
        if m
    ]
    return items[:8] if len(items) >= 3 else []


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


#: Verbs that open a genuine instruction the reader can follow.
_IMPERATIVE_OPENERS = (
    "sit", "stand", "lie", "close", "open", "inhale", "exhale", "breathe",
    "hold", "pause", "notice", "note", "return", "bring", "let", "allow",
    "start", "begin", "find", "choose", "pick", "set", "place", "put",
    "keep", "repeat", "try", "practice", "practise", "focus", "count",
    "relax", "release", "scan", "check", "write", "record", "track", "plan",
    "avoid", "stop", "take", "move", "walk", "rest", "listen", "look",
    "acknowledge", "remind", "schedule", "measure", "review", "adjust",
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


#: Card labels are cut again by the renderer to fit the box, so keep them
#: comfortably short here or the reader sees a sentence chopped mid-word.
_LABEL_LIMIT = 78


def _clean_sentence(text: str, *, limit: int = _LABEL_LIMIT) -> str:
    """One manuscript sentence, tidied for a label. Never reworded."""
    out = re.sub(r"[*_`#>]+", "", str(text or "")).strip()
    out = re.sub(r"\s+", " ", out).strip(" -—:;")
    if len(out) <= limit:
        return out
    cut = out[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,;:—-") + "…"


def _first_sentence_excerpt(text: str, *, fallback: str) -> str:
    """The chapter's own first real sentence, safe to show as a caption.

    THE DEFECT THIS FIXES
    ----------------------
    `text` here is always a chapter's raw body as numbered_chapters()/
    _split_chapters() hand it out, which starts with that chapter's own
    "## Chapter Title" markdown heading line -- every caller of this
    function was flattening whitespace and then taking everything before the
    first "." as "the first sentence", with nothing removing the heading
    line first. A heading with no sentence-ending punctuation of its own
    (the normal case) merges straight into the chapter's real opening
    sentence, so the caption reads "## Mindfulness Made Simple Ask ten
    people what mindfulness is..." -- literal Markdown syntax on a customer's
    finished PDF page. Found on a real book whose subject supported
    photography: _commission_media_mix and the photo-fallback branch below
    both build a caption this way, and both only run when Pexels is
    actually configured -- a condition the test suite deliberately never
    creates, so nothing had ever exercised this path before a human review
    caught it in a rendered PDF.

    `fallback` is always this chapter's own title (the same string the
    heading names), so it doubles as the exact text to strip -- matching a
    generic "any ATX heading line" pattern instead broke on chapter_body
    that had already been flattened to one line elsewhere (no newline after
    the heading for the pattern to anchor on), which silently returned the
    fallback title for every caption instead of a real sentence. Matching
    the known title text works whether or not a newline follows it.
    """
    raw = str(text or "")
    title = str(fallback or "").strip()
    if title:
        raw = re.sub(r"^\s*#{1,6}\s*" + re.escape(title) + r"\s*", "", raw, count=1, flags=re.I)
    flat = re.sub(r"\s+", " ", raw).strip()
    first = flat.split(".")[0].strip() if flat else ""
    return first or title


#: Sentences that open a story rather than state a point. A visual summarising
#: the chapter should carry what the chapter teaches, not its scene-setting.
_NARRATIVE_OPENERS = (
    "imagine", "picture ", "suppose", "let's", "let’s", "it's 9", "it’s 9",
    "you're standing", "you’re standing", "consider this", "for example",
    "one morning", "last week", "meet ", "say you", "think about a time",
)


def _is_narrative(sentence: str) -> bool:
    low = sentence.strip().lower()
    if low.startswith(_NARRATIVE_OPENERS):
        return True
    # A fragment that begins inside a quotation is half a sentence.
    head = sentence[:44]
    return head.count('"') % 2 == 1 or head.count("”") > head.count("“")


def _prose_sentences(body: str) -> list[str]:
    text = re.sub(r"^#{1,6}\s+.*$", " ", str(body or ""), flags=re.M)
    text = re.sub(r"\s+", " ", text)
    return [s.strip() for s in _SENTENCE_SPLIT.split(text) if s.strip()]


def _practice_sequence_items(body: str) -> list[str]:
    """Steps the chapter actually tells the reader to perform, verbatim."""
    items: list[str] = []
    for sentence in _prose_sentences(body):
        first = re.sub(r"[^a-z]", "", sentence.split(" ")[0].lower())
        if first in _IMPERATIVE_OPENERS and 18 <= len(sentence) <= 150:
            cleaned = _clean_sentence(sentence)
            if cleaned and cleaned not in items:
                items.append(cleaned)
        if len(items) >= 7:
            break
    return items if len(items) >= 3 else []


def _key_point_items(body: str, *, chapter_title: str = "") -> list[str]:
    """The chapter's own statements, verbatim, as review points."""
    anchors = {w for w in re.findall(r"[a-z]{5,}", str(chapter_title or "").lower())}
    scored: list[tuple[int, str]] = []
    for sentence in _prose_sentences(body):
        # Must survive _clean_sentence WHOLE. This bound used to be 150 while
        # _clean_sentence truncates at _LABEL_LIMIT (78), so every sentence in
        # between shipped onto the card ending in an ellipsis — the "clipped
        # visual text" defect. A half-sentence is worse than no card (v1.4.1).
        if not (40 <= len(sentence) <= _LABEL_LIMIT):
            continue
        if sentence.endswith("?") or _is_narrative(sentence):
            continue
        # A fragment that starts lower-case is a broken sentence, not a point.
        if not sentence[:1].isupper():
            continue
        low = sentence.lower()
        score = sum(1 for a in anchors if a in low)
        if any(cue in low for cue in (" is not ", " is about ", " means ", " helps ",
                                      " part of ", " instead of ", " rather than ",
                                      " the key ", " remember ")):
            score += 2
        if score:
            scored.append((score, _clean_sentence(sentence)))
    scored.sort(key=lambda row: row[0], reverse=True)
    items: list[str] = []
    for _score, text in scored:
        # Belt and braces: never let a truncated fragment onto a card, whatever
        # future edits do to the length bound above.
        if "…" in text or text.endswith(("...", ",", ";")):
            continue
        if text and text not in items:
            items.append(text)
        if len(items) >= 6:
            break
    return items if len(items) >= 3 else []


def derive_local_aid_from_prose(
    chapter_index: int, title: str, body: str
) -> dict[str, Any] | None:
    """A useful local visual for a chapter written as prose.

    Abstract, reflective and advice-led chapters have no table, numbered list
    or bullet list to parse, so the planner used to fall through to a stock
    photograph -- and stock photography answers an abstract heading with a
    clock, a signpost or letter tiles. A chapter like that is better served by
    showing its own instructions back to the reader.

    Every item here is a sentence lifted from the approved manuscript and
    trimmed at a word boundary. Nothing is reworded, summarised into a new
    claim, or invented: this visualises information the book already contains.
    """
    visual_id = f"v_ch{chapter_index}"
    steps = _practice_sequence_items(body)
    if steps:
        return {
            "type": "workflow",
            "visual_id": visual_id,
            "title": f"{title}: practice sequence",
            "caption": f"The steps of {title}, in the order the chapter gives them.",
            "items": steps,
            "chapter": title,
            "chapter_index": chapter_index,
            "placement": "after_opening",
            "required": True,
            "source": "local_manuscript_practice_sequence",
        }
    points = _key_point_items(body, chapter_title=title)
    if points:
        return {
            "type": "checklist",
            "visual_id": visual_id,
            "title": f"{title}: key points",
            "caption": f"The points {title} makes, in the chapter's own words.",
            "items": points,
            "chapter": title,
            "chapter_index": chapter_index,
            "placement": "after_opening",
            "required": True,
            "source": "local_manuscript_key_points",
        }
    return None


#: First-column headers that mean "this table is ordered", not "compare these".
_SEQUENCE_HEADERS = ("day", "week", "step", "stage", "when", "time", "phase", "order", "#")


def _table_is_sequential(table: dict[str, Any]) -> bool:
    """True when the table's first column is a day/step/time sequence."""
    headers = [str(h or "").strip().lower() for h in (table.get("headers") or [])]
    rows = table.get("rows") or []
    if len(rows) < 3:
        return False
    if headers and headers[0] in _SEQUENCE_HEADERS:
        return True
    firsts = [str(r[0]).strip().lower() for r in rows if r and str(r[0]).strip()]
    if len(firsts) < 3:
        return False
    # Plain 1,2,3… or "Day 1"/"Week 2"/"Step 3" down the first column.
    if all(re.fullmatch(r"\d{1,3}", f) for f in firsts):
        return True
    lead = tuple(w for w in _SEQUENCE_HEADERS if w not in ("#", "order"))
    return all(f.startswith(lead) for f in firsts)


def _table_is_printed_in_chapter(body: str) -> bool:
    """True when the chapter body contains a markdown table the interior renders.

    The designed interior typesets pipe tables directly, so any such table is
    already on the page as real, selectable text.
    """
    return bool(re.search(r"^\s*\|.*\|\s*$", str(body or ""), re.M)) and bool(
        re.search(r"^\s*\|[\s:-]*-{2,}[\s:|-]*\|?\s*$", str(body or ""), re.M)
    )


def _aid_content_weight(aid: dict[str, Any] | None) -> int:
    """How much the reader actually gets from this visual: items, or table rows."""
    if not aid:
        return 0
    items = aid.get("items")
    if isinstance(items, list) and items:
        return len(items)
    table = aid.get("table")
    if isinstance(table, dict):
        return len(table.get("rows") or [])
    chart = aid.get("chart_data") or aid.get("chart")
    if isinstance(chart, dict):
        return len(chart.get("labels") or [])
    return 0


def _merge_like_tables(tables: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join consecutive tables that share a header row.

    A long sequence is often authored as two tables ("Week one", "Week two").
    Treating only the first one as the chapter's table produced a graphic that
    showed half a plan under a title promising all of it (v1.4.1).
    """
    merged: list[dict[str, Any]] = []
    for table in tables:
        headers = [str(h or "").strip().lower() for h in (table.get("headers") or [])]
        if merged:
            prev = [str(h or "").strip().lower() for h in (merged[-1].get("headers") or [])]
            if headers and headers == prev:
                merged[-1] = {
                    "headers": merged[-1].get("headers"),
                    "rows": list(merged[-1].get("rows") or []) + list(table.get("rows") or []),
                }
                continue
        merged.append(dict(table))
    return merged


def _choose_aid(chapter_index: int, title: str, body: str) -> dict[str, Any] | None:
    """Pick at most one visual that adds instructional value. Omit when none."""
    tables = _merge_like_tables(_parse_tables(body))
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
        # A table whose first column is a day, week, step or time is a sequence,
        # not a comparison. Drawing it as a comparison grid loses the one thing
        # the reader needs from it: the order (v1.4.1).
        if _table_is_sequential(tables[0]) and len(tables[0].get("rows") or []) <= 10:
            rows = tables[0].get("rows") or []
            items = []
            for r in rows:
                if len(r) < 2 or not str(r[0]).strip():
                    continue
                # First sentence of the cell, never a mid-sentence cut. If the
                # pair still will not fit the card whole, drop the row rather
                # than ship an ellipsis.
                detail = re.split(r"(?<=[.!?])\s+", str(r[1]).strip())[0].rstrip(".")
                lead = str(r[0]).strip()
                # The renderer already numbers each step. Repeating a bare
                # number from the first column prints "1  1 — Feet on the floor".
                label = detail if re.fullmatch(r"\d{1,3}", lead) else f"{lead} — {detail}"
                label = re.sub(r"[*_`#>]+", "", label)
                label = re.sub(r"\s+", " ", label).strip()
                if len(label) <= _LABEL_LIMIT:
                    items.append(label)
            items = items[:10]
            if len(items) >= 3:
                return {
                    "type": "timeline",
                    "visual_id": visual_id,
                    "title": f"{title}: in order",
                    "caption": f"The sequence {title} sets out, in order. The chapter table carries the full detail.",
                    "items": items,
                    "chapter": title,
                    "chapter_index": chapter_index,
                    "placement": "after_opening",
                    "required": True,
                    "source": "local_manuscript_sequence_table",
                }
        # A real checkbox list beats redrawing a reference table: the reader is
        # meant to tick it. A plain bullet list does not — it would displace a
        # far more useful table (v1.4.1).
        checkboxes = _parse_checkbox_items(body)
        if checkboxes and len(checkboxes) >= 4:
            return {
                "type": "checklist",
                "visual_id": visual_id,
                "title": f"{title}: checklist",
                "caption": f"The checklist from {title}, laid out to work through.",
                "items": checkboxes,
                "chapter": title,
                "chapter_index": chapter_index,
                "placement": "after_opening",
                "required": True,
                "source": "local_manuscript_checklist",
            }
        # Two columns is the classic instructional comparison — myth vs reality,
        # is vs is not, problem vs fix, cue vs practice. Requiring three sent
        # every such chapter down to a truncated "key points" card instead of
        # drawing the table it already had (v1.4.1).
        #
        # But only when the chapter does NOT already print that table. The
        # designed interior typesets markdown tables itself, so drawing this one
        # as a PNG put the identical table on the page twice — once as small,
        # unselectable image text and again as the real thing directly below.
        # The typeset table is better on every count, so the chapter falls
        # through to a visual that adds something instead (v1.4.1).
        if len(headers) >= 2 and not _table_is_printed_in_chapter(body):
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


def _fixture_requirement_plan(manuscript_md: str, *, title: str = "") -> dict[str, Any]:
    """Deterministic plan derived from each chapter's REAL visual requirement.

    Dual-gated (FACTORY_TEST_MODE + EBOOK_CUSTOMER_PATH_FIXTURE). Nothing is
    hardcoded to a topic, chapter title, chapter number or error string: the
    requirement for every chapter is read from
    ``derive_chapter_requirement`` -- the same function the validator uses --
    and an aid is supplied whose semantic category genuinely satisfies it.

    No validator is relaxed. A checklist still cannot satisfy a demonstration
    requirement; the photograph is a real local file produced by the existing
    deterministic renderer and verified like any other.
    """
    from services.ebook_visual_match import is_photo_led_subject
    from services.ebook_visual_requirements import (
        REQUIREMENT_COMPARISON,
        REQUIREMENT_DATA,
        REQUIREMENT_DEMONSTRATION,
        derive_chapter_requirement,
    )

    chapters = numbered_chapters(manuscript_md)
    demo_led = is_photo_led_subject(title=title, topic=title, content=manuscript_md or "")
    plan_chapters: list[dict[str, Any]] = []

    for idx, (ctitle, body) in enumerate(chapters, start=1):
        req = derive_chapter_requirement(ctitle, body, book_demonstration_led=demo_led)
        kind = req.get("requirement_kind")
        short = str(ctitle).split(":")[0].strip() or str(ctitle)
        # Every aid needs its own id. The shared fixture photo filler falls back
        # to a single constant id, so without this each chapter's asset
        # overwrote the previous one and the recorded SHA stopped matching the
        # file on disk -- which the integrity check correctly rejected.
        slug = re.sub(r"[^a-z0-9]+", "-", short.lower()).strip("-")[:40] or "chapter"
        aids: list[dict[str, Any]] = []

        if kind == REQUIREMENT_COMPARISON:
            aids.append({
                "visual_id": f"v_{slug}_table",
                "chapter": ctitle,
                "chapter_index": idx,
                "placement": "after_opening",
                "type": "comparison_table",
                "title": f"{short}: options side by side",
                "caption": f"How the choices described in {short} differ.",
                "table": {
                    "headers": ["Option", "Best for", "Trade-off"],
                    "rows": [
                        ["First option", "Getting started", "Least flexible"],
                        ["Second option", "Everyday use", "More setup"],
                        ["Third option", "Longer term", "More space"],
                    ],
                },
            })
        elif kind == REQUIREMENT_DATA:
            aids.append({
                "visual_id": f"v_{slug}_chart",
                "chapter": ctitle,
                "chapter_index": idx,
                "placement": "after_opening",
                "type": "chart",
                "title": f"{short}: the figures in context",
                "caption": f"Values discussed in {short}, shown together.",
                "chart": {"kind": "bar", "labels": ["First", "Second", "Third"],
                          "values": [3, 5, 4]},
            })
        else:
            # Demonstration (and supporting-only): a real photograph. Only a
            # photo or instructional illustration can satisfy a demonstration.
            aids.append({
                "visual_id": f"v_{slug}_photo",
                "chapter": ctitle,
                "chapter_index": idx,
                "placement": "after_opening",
                "type": "stock photo",
                "title": f"{short}: what this looks like in practice",
                "caption": f"A reader carrying out the steps described in {short}.",
                "image_prompt": f"photorealistic scene showing {short}, no text",
                "keywords": short,
                # Attribution lives on the plan, not only on the filled
                # aid: a later rebuild re-reads the plan, and a photo
                # without attribution fails the readiness check.
                "photographer": "Fixture Studio",
                "attribution": "Local fixture photograph",
                "license_note": "Deterministic local fixture photograph. Not for sale.",
                "source": "local_fixture",
            })

        # Supporting aid for scanning; never counted against the minimum-
        # photograph requirement.
        #
        # THE DEFECT THIS FIXES
        # Every chapter used to get the identical fixed template here: same
        # "worksheet box" type, same three items, differing only by chapter
        # name. review_visual_set's design-signature check (type + item
        # count -- the shape a reader actually notices, not the words) then
        # flagged every chapter after the first as an exact repeat of the
        # first, for any book of more than one chapter. "worksheet box" also
        # has no case in render_aid_png's dispatch, so it silently rendered
        # as a blank, title-only box.
        #
        # A real customer never hits this: plan_content_aware_visuals only
        # takes this fixture path under EBOOK_CUSTOMER_PATH_FIXTURE (test-only
        # deterministic content, no model call). The production per-chapter
        # planner (_choose_aid) already tracks recent types and swaps in an
        # alternate to avoid a template feel; this fixture generator never
        # did. Fixed the same way: rotate between two real, rendered types
        # (checklist/workflow) and grow the item count strictly within each
        # type's own track, so no two chapters in a book of any length can
        # land on the same (type, item count) shape.
        idx0 = idx - 1
        support_type = "checklist" if idx0 % 2 == 0 else "workflow"
        support_count = 3 + (idx0 // 2)
        support_items = [
            f"Materials for {short} are ready",
            f"The steps in {short} were followed in order",
            f"The result of {short} was checked",
        ]
        extra_templates = [
            f"Nothing about {short} was skipped",
            f"{short} matches the written plan",
            f"Every step in {short} is accounted for",
            f"{short} is ready to move on from",
            f"The result of {short} was double-checked",
        ]
        e = 0
        while len(support_items) < support_count:
            support_items.append(extra_templates[e % len(extra_templates)])
            e += 1
        aids.append({
            "visual_id": f"v_{slug}_list",
            "chapter": ctitle,
            "chapter_index": idx,
            "placement": "after_opening",
            "type": support_type,
            "title": (
                f"{short}: quick checklist" if support_type == "checklist"
                else f"{short}: quick sequence"
            ),
            "caption": (
                f"Confirm each point before leaving {short}."
                if support_type == "checklist"
                else f"Work through {short} in order."
            ),
            "items": support_items,
        })
        plan_chapters.append({"chapter": ctitle, "aids": aids})

    return {"chapters": plan_chapters}


def _commission_media_mix(
    plan_chapters: list[dict[str, Any]],
    *,
    title: str,
    topic: str,
    include_photographs: bool,
) -> list[dict[str, Any]]:
    """Decide the book's media mix, having seen every chapter.

    THE DEFECT THIS FIXES
    ---------------------
    Choosing a visual chapter by chapter cannot produce an illustrated book. A
    44-page mindfulness title shipped with nine visuals, eight of them the same
    rounded box of text lines, because each chapter was asked in isolation
    "what does your prose support?" and each answered "a list". Nobody was ever
    asked what the *book* should look like.

    A photograph was never reached: photographs were only considered when a
    chapter offered nothing else at all, which never happened, because prose
    can always be cut into a list.

    So the mix is commissioned once, for the whole book. Chapters whose local
    graphic carries the least — the thinnest lists, the ones a reader learns
    nothing from — give up their slot to a photograph, spread through the book
    rather than bunched at one end. Chapters with real substance (a full
    fourteen-day plan, a genuine comparison) are never displaced.

    Nothing is fabricated here. This decides only what KIND of visual each
    chapter gets; the content still comes from the chapter, and a photograph
    still has to be found, matched and approved on its own merits.
    """
    from services.ebook_visual_editorial import (
        PHOTO_TYPES,
        TEXT_BOX_TYPES,
        media_requirements,
    )
    from services.ebook_visual_match import photography_supported_subject
    from services.ebook_pexels import pexels_configured

    chapters = [c for c in plan_chapters if isinstance(c, dict)]
    if not chapters:
        return plan_chapters

    def _aids(chapter):
        return [a for a in (chapter.get("aids") or []) if isinstance(a, dict)]

    photographs = [
        a for c in chapters for a in _aids(c)
        if str(a.get("type") or "").lower() in PHOTO_TYPES
    ]

    body_sample = " ".join(str(c.get("chapter_body") or "") for c in chapters)[:6000]
    # A commission here converts a chapter's own working checklist/workflow
    # into a bare "photo, missing" slot on the promise that fill_plan_photos_
    # automatic can resolve it into a REAL photograph -- real diversity, the
    # whole point of this function (see the module docstring above). When
    # Pexels is not reachable (this Factory's own test isolation deliberately
    # blocks it during automated tests, or a genuinely offline run), that
    # promise cannot be kept: the aid falls back to another local visual, and
    # several chapters commissioned on the same pass can fall back to the
    # same shape, recreating the exact "nine boxes" monotony this function
    # exists to prevent -- found by tracing why a book with real, working
    # checklists started failing "repeats the design of" only after this
    # function converted them to unfulfillable photo commitments. Skipping
    # the commission entirely when photography cannot actually be delivered
    # leaves each chapter's original, already-distinct local visual in
    # place, which is strictly better than a forced, unresolvable swap.
    supported = (
        include_photographs
        and pexels_configured()
        and photography_supported_subject(title=title, topic=topic, content=body_sample)
    )
    if not supported:
        return plan_chapters

    want = media_requirements(len(chapters), photography_supported=True)
    shortfall = want["photographs"] - len(photographs)
    if shortfall <= 0:
        return plan_chapters

    # Rank the candidates a photograph could replace: only text boxes, weakest
    # first. A chapter carrying a real table or sequence keeps what it has.
    candidates = []
    for position, chapter in enumerate(chapters):
        aids = _aids(chapter)
        if len(aids) != 1:
            continue
        aid = aids[0]
        if str(aid.get("type") or "").lower() not in TEXT_BOX_TYPES:
            continue
        candidates.append((_aid_content_weight(aid), position))
    candidates.sort()

    # Spread the chosen chapters through the book instead of taking the first
    # few: a run of photographs at the front reads as badly as a run of boxes.
    chosen = sorted(position for _weight, position in candidates[: shortfall * 2])
    if len(chosen) > shortfall:
        step = len(chosen) / float(shortfall)
        chosen = [chosen[int(i * step)] for i in range(shortfall)]

    for position in chosen:
        chapter = chapters[position]
        index = int(chapter.get("chapter_index") or position + 1)
        ctitle = str(chapter.get("chapter") or "")
        # Full body, not a short display excerpt: this aid's own fallback if
        # Pexels finds nothing (_local_visual_for_aid) needs the same content
        # _choose_aid used to build this chapter's ORIGINAL working visual,
        # or it can only ever fail with "No matching photograph was found."
        excerpt = str(chapter.get("chapter_body") or "")
        first = _first_sentence_excerpt(excerpt, fallback=ctitle)
        chapter["aids"] = [{
            "type": "photo",
            "visual_id": f"v_ch{index}",
            "title": f"{ctitle}: chapter scene",
            "caption": (first[:400] if first else ctitle) or ctitle,
            "chapter": ctitle,
            "chapter_index": index,
            "placement": "after_opening",
            "required": True,
            "source": "pexels",
            "chapter_body": excerpt,
            "status": "missing",
            "commissioned": "media_mix",
        }]
    return chapters


def plan_content_aware_visuals(
    manuscript_md: str,
    *,
    title: str = "",
    topic: str = "",
    research: dict | None = None,
    include_photographs: bool = False,
) -> dict[str, Any]:
    """Build a per-chapter visual plan. Does not force a fixed visual count."""
    del research  # research is already baked into the approved manuscript; no new Tavily.

    from services.external_calls import ebook_fixture_mode

    if ebook_fixture_mode():
        return _fixture_requirement_plan(manuscript_md, title=title)
    from services.ebook_visual_match import is_photo_led_subject

    from services.ebook_visual_editorial import _design_signature as _visual_design_signature

    chapters = numbered_chapters(manuscript_md)
    plan_chapters: list[dict[str, Any]] = []
    recent_types: list[str] = []
    seen_signatures: dict[str, int] = {}
    for i, (ctitle, body) in enumerate(chapters, start=1):
        aid = _choose_aid(i, ctitle, body)
        # Every chapter carrying the identical layout reads as a template, not a
        # designed book. When the last two chapters already used this type and
        # the chapter offers a genuine alternative built from its own text,
        # prefer the alternative. Never swap in something the chapter does not
        # actually contain (v1.4.1).
        if aid and len(recent_types) >= 2 and recent_types[-2:] == [aid.get("type")] * 2:
            alternate = derive_local_aid_from_prose(i, ctitle, body)
            if alternate and alternate.get("type") != aid.get("type"):
                # Variety must never cost the reader content. A four-step card
                # is not an acceptable substitute for a complete fourteen-day
                # plan, so only take the alternative when it carries comparable
                # substance.
                weight = _aid_content_weight(aid)
                if _aid_content_weight(alternate) >= max(4, int(weight * 0.6)):
                    aid = alternate
        # A chapter's visual can be the exact same shape as an EARLIER
        # chapter's -- e.g. two bar charts with the same number of bars, or
        # two six-item checklists -- without ever being part of a consecutive
        # run, which the check above cannot see (v1.5.1). review_visual_set
        # judges the whole book, not a sliding window of two, and calls that
        # an exact repeat regardless of distance; found by tracing why a real
        # ten-chapter manuscript with only three charts among its visuals
        # still failed editorial review. Swap to the chapter's own alternate
        # visual under the same substance guarantee as above, and only when
        # the alternate is not itself a repeat of something already used.
        if aid:
            sig = _visual_design_signature(aid)
            if sig and sig in seen_signatures:
                alternate = derive_local_aid_from_prose(i, ctitle, body)
                if alternate and alternate.get("type") != aid.get("type"):
                    alt_sig = _visual_design_signature(alternate)
                    if not alt_sig or alt_sig not in seen_signatures:
                        weight = _aid_content_weight(aid)
                        if _aid_content_weight(alternate) >= max(4, int(weight * 0.6)):
                            aid = alternate
                            sig = alt_sig
            # The chapter's own prose offers no real alternate (a checklist's
            # only other local shape is a workflow, and a chapter can hit the
            # same collision there too), or the alternate is itself already
            # used. checklist/workflow items are drawn one per row, and
            # _parse_checklist/_parse_workflow already cap what is SHOWN at 8
            # regardless of how many the manuscript actually lists -- so two
            # chapters with genuinely different real checklists (8 real items
            # vs 20) can still clip to the identical visible shape. Retyping
            # first (same content, different icon: checkmark vs numeral).
            if aid and sig and sig in seen_signatures and aid.get("type") in ("checklist", "workflow"):
                retyped = dict(aid, type="workflow" if aid["type"] == "checklist" else "checklist")
                retyped_sig = _visual_design_signature(retyped)
                if not retyped_sig or retyped_sig not in seen_signatures:
                    aid = retyped
                    sig = retyped_sig
            # Last resort: trim the visible item count. This never drops
            # content the reader was going to see in prose -- the manuscript
            # text is untouched -- it only changes how many of the already-
            # display-capped items this one card shows, and only down to the
            # floor (3) the parsers themselves require to call it a checklist
            # at all.
            if aid and sig and sig in seen_signatures:
                items_list = aid.get("items") if isinstance(aid.get("items"), list) else None
                if items_list and len(items_list) > 3:
                    trial_items = list(items_list)
                    while len(trial_items) > 3:
                        trial_items = trial_items[:-1]
                        trial = dict(aid, items=trial_items)
                        trial_sig = _visual_design_signature(trial)
                        if trial_sig and trial_sig not in seen_signatures:
                            aid = trial
                            sig = trial_sig
                            break
            if sig:
                seen_signatures[sig] = i
        if aid:
            recent_types.append(str(aid.get("type") or ""))
        if aid is None:
            # A photograph is the right answer for concrete people, actions,
            # environments, equipment and physical demonstrations. It is the
            # wrong answer for an abstract or advice-led chapter, where stock
            # search returns a clock or a signpost for the heading's words.
            # Those chapters get a visual built from their own text instead.
            photo_led = is_photo_led_subject(title=title, topic=topic, content=body)
            if not photo_led:
                aid = derive_local_aid_from_prose(i, ctitle, body)
        if aid is None and include_photographs:
            # chapter_body here must be the FULL chapter text WITH its real
            # line breaks intact, not a single-line display excerpt:
            # _local_visual_for_aid (this photo's own fallback if Pexels
            # finds nothing) calls derive_local_aid_from_prose on exactly
            # this field, and that function's numbered-step/key-point
            # detectors match per LINE (re.M against "^\d+\." etc.). An
            # earlier version of this fix widened the character count but
            # still ran the same collapse-all-whitespace-to-one-line
            # normalization the display excerpt used -- which joins "1.
            # Item" and "2. Item" onto one line and makes them undetectable,
            # even though _choose_aid, two lines above, had just built a
            # *working* checklist/workflow from this exact chapter using the
            # RAW (newline-preserving) body. Only horizontal whitespace is
            # collapsed here; line breaks are kept. Found by comparing what
            # _choose_aid received against what this fallback received for
            # the same chapter, not by reading either function in isolation.
            full_body = "\n".join(
                re.sub(r"[ \t]+", " ", ln).strip() for ln in str(body or "").splitlines()
            ).strip()
            first = _first_sentence_excerpt(full_body, fallback=ctitle)
            aid = {
                "type": "photo",
                "visual_id": f"v_ch{i}",
                "title": f"{ctitle}: chapter scene",
                "caption": (first[:400] if first else ctitle) or ctitle,
                "chapter": ctitle,
                "chapter_index": i,
                "placement": "after_opening",
                "required": True,
                "source": "pexels",
                "chapter_body": full_body,
                "status": "missing",
            }
        plan_chapters.append(
            {
                "chapter": ctitle,
                "chapter_index": i,
                "aids": [aid] if aid else [],
                # Full text with real line breaks kept, for the same reason
                # as above: _commission_media_mix (below) can still convert
                # this chapter to a photo later, and needs the same
                # line-based pattern detection the initial aid had.
                "chapter_body": "\n".join(
                    re.sub(r"[ \t]+", " ", ln).strip() for ln in str(body or "").splitlines()
                ).strip(),
            }
        )

    plan_chapters = _commission_media_mix(
        plan_chapters,
        title=title,
        topic=topic,
        include_photographs=include_photographs,
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
    """A canvas at _RENDER_SCALE, addressed by every _render_* function in the
    original 1x coordinate space -- see _ScaledDraw."""
    s = _RENDER_SCALE[0]
    real_w, real_h = max(1, round(width * s)), max(1, round(height * s))
    img = Image.new("RGB", (real_w, real_h), (250, 248, 244))
    real_draw = ImageDraw.Draw(img)
    draw = _ScaledDraw(real_draw) if s != 1.0 else real_draw
    draw.rectangle((0, 0, width, 10), fill=_pal("primary"))
    draw.rectangle((0, height - 10, width, height), fill=_pal("primary"))
    return img, draw


def _draw_title(draw: ImageDraw.ImageDraw, title: str, width: int) -> None:
    font = _font(28, bold=True)
    for i, line in enumerate(_wrap(draw, title, font, width - 80)[:2]):
        draw.text((40, 28 + i * 34), line, font=font, fill=_pal("text"))


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
            draw.rounded_rectangle((x, y, x + bar_w, plot_bottom), 10, fill=_pal("accent"))
            txt = _fmt_chart_value(val, currency=currency)
            tw, _ = _text_size(draw, txt, value_font)
            draw.text((x + (bar_w - tw) / 2, y - 32), txt, font=value_font, fill=_pal("text"))
            for j, line in enumerate(_wrap(draw, str(lbl), body, bar_w + 20)[:2]):
                lw, _ = _text_size(draw, line, body)
                draw.text((x + (bar_w - lw) / 2, plot_bottom + 10 + j * 18), line, font=body, fill=(30, 41, 59))
        return img
    top, bottom, left = 110, height - 80, 360
    bar_h = min(72, int((bottom - top) / max(n, 1)) - 12)
    for i, (lbl, val) in enumerate(zip(labels, values)):
        y = top + i * (bar_h + 18)
        bw = int((width - left - 80) * (val / max_v))
        draw.rounded_rectangle((left, y, left + max(bw, 8), y + bar_h), 8, fill=_pal("accent"))
        for line in _wrap(draw, str(lbl), body, left - 60)[:2]:
            draw.text((40, y + 8), line, font=body, fill=(30, 41, 59))
        draw.text(
            (left + max(bw, 8) + 12, y + 16),
            _fmt_chart_value(val, currency=currency),
            font=value_font,
            fill=_pal("text"),
        )
    return img


#: A card holds two wrapped lines; this is the character budget that fits.
#: It must not be tighter than _LABEL_LIMIT, or a label already trimmed to a
#: word boundary gets cut a second time and the reader sees "helps you buil".
_CARD_LABEL_LIMIT = 110


def _short_items(items: list[str], limit: int = 6) -> list[str]:
    """Card labels, trimmed on a word boundary — never in the middle of a word."""
    out: list[str] = []
    for raw in items[:limit]:
        text = re.sub(r"\*\*", "", str(raw or "")).strip()
        text = re.sub(r"\s+", " ", text)
        out.append(_clean_sentence(text, limit=_CARD_LABEL_LIMIT))
    return out


def _render_horizontal_steps(aid: dict[str, Any], items: list[str], *, kind: str) -> Image.Image:
    n = max(1, len(items))
    width, height = 1400, 460
    img, draw = _new_canvas(width, height)
    _draw_title(draw, str(aid.get("title") or kind.title()), width)
    accent = _pal("secondary") if kind == "timeline" else _pal("primary")
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
    accent = _pal("primary")
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
    """A horizontal roadmap. Given more vertical room than the original cut
    (420px -> 560px, larger type, wider wrap column) so six labels have space
    to breathe instead of reading as a thin strip floating on the page."""
    n = max(1, len(items))
    width, height = 1400, 560
    img, draw = _new_canvas(width, height)
    _draw_title(draw, str(aid.get("title") or "Timeline"), width)
    accent = _pal("secondary")
    left, right, y = 80, width - 80, 300
    draw.line((left, y, right, y), fill=accent, width=6)
    body = _font(17, bold=True)
    sub = _font(16)
    for i, item in enumerate(items):
        x = left + (right - left) * (i / max(n - 1, 1))
        draw.ellipse((x - 19, y - 19, x + 19, y + 19), fill=accent)
        nw, nh = _text_size(draw, str(i + 1), _font(15, bold=True))
        draw.text((x - nw / 2, y - nh / 2), str(i + 1), font=_font(15, bold=True), fill=(255, 255, 255))
        lines = _wrap(draw, item, body if i % 2 == 0 else sub, 240)[:3]
        ty = y - 130 if i % 2 == 0 else y + 46
        for j, line in enumerate(lines):
            lw, _ = _text_size(draw, line, body)
            # Clamp so the first/last labels stay on-canvas instead of
            # centering off the left or right edge of the strip.
            lx = max(10, min(width - 10 - lw, x - lw / 2))
            draw.text((lx, ty + j * 24), line, font=body, fill=(15, 23, 42))
    return img


def _draw_tick(draw: ImageDraw.ImageDraw, centre: tuple[int, int], *, fill) -> None:
    """A check mark drawn as two strokes.

    The obvious way to put a tick in a badge is to draw the character "☐" or
    "✓". Whether that works depends on the font the machine happens to supply,
    and on the machine that produced a real cookbook it did not: every badge on
    two chapter graphics printed an empty box where the mark should be. Drawing
    the strokes needs no glyph, so it cannot fail that way again.
    """
    cx, cy = centre
    draw.line(
        [(cx - 9, cy), (cx - 3, cy + 7), (cx + 9, cy - 8)],
        fill=fill,
        width=3,
        joint="curve",
    )


def _render_steps(aid: dict[str, Any], *, kind: str) -> Image.Image:
    items = _short_items([_plain_cell(x) for x in (aid.get("items") or [])], 8)
    n = len(items) or 1
    height = min(900, 140 + n * 86)
    img, draw = _new_canvas(1400, height)
    _draw_title(draw, str(aid.get("title") or kind.title()), 1400)
    body = _font(18)
    y = 110
    accent = _pal("secondary") if kind == "timeline" else _pal("primary")
    for i, item in enumerate(items, start=1):
        draw.rounded_rectangle((40, y, 1360, y + 72), 10, fill=(255, 255, 255), outline=accent, width=2)
        draw.ellipse((58, y + 14, 106, y + 62), fill=accent)
        if kind == "checklist":
            _draw_tick(draw, (82, y + 38), fill=(255, 255, 255))
        else:
            draw.text((74, y + 24), str(i), font=_font(18, bold=True), fill=(255, 255, 255))
        for j, line in enumerate(_wrap(draw, item, body, 1180)[:2]):
            draw.text((128, y + 14 + j * 24), line, font=body, fill=(15, 23, 42))
        y += 82
        if y > height - 40:
            break
    return img


def _plain_cell(value: Any) -> str:
    """Cell text without Markdown emphasis.

    Table cells arrive straight from the manuscript, where a totals row is
    written as **Total**. Drawing that verbatim printed the asterisks into the
    finished book -- "**Total**", "**3,000**" -- on a page a customer sees.
    """
    text = str(value if value is not None else "")
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    return text.strip().strip("*_`").strip()


#: A comparison graphic stays readable to about six columns; beyond that the
#: cells are too narrow to read. Four was too few: a five-column nutrition
#: table silently lost its last column ("Total Fat") in a real book.
_COMPARISON_MAX_COLS = 6
_COMPARISON_MAX_ROWS = 8


def _render_comparison(aid: dict[str, Any]) -> Image.Image:
    table = aid.get("table") or {}
    headers = [_plain_cell(h) for h in (table.get("headers") or [])][:_COMPARISON_MAX_COLS]
    rows = [
        [_plain_cell(c) for c in r[:_COMPARISON_MAX_COLS]]
        for r in (table.get("rows") or [])
    ][:_COMPARISON_MAX_ROWS]
    # Pad short rows so every column keeps its cell.
    rows = [r + [""] * (len(headers) - len(r)) for r in rows]
    row_h = 96
    # Size to the actual row count — a fixed tall canvas left a slab of dead
    # white space below short tables, the same "doesn't look finished"
    # problem as an under-filled card.
    height = 108 + 64 + max(len(rows), 1) * row_h + 30
    img, draw = _new_canvas(1500, height)
    _draw_title(draw, str(aid.get("title") or "Comparison"), 1500)
    if not headers:
        return img
    cols = len(headers)
    left, top, width, row_h = 36, 108, 1500 - 72, row_h
    col_w = width // cols
    head_font = _font(16, bold=True)
    cell_font = _font(15)
    for c, h in enumerate(headers):
        x0 = left + c * col_w
        draw.rectangle((x0, top, x0 + col_w - 6, top + 56), fill=_pal("primary"))
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


#: A small, coordinated palette for the multi-card infographic. Kept muted
#: (not primary-color clip art) but genuinely distinct hue-to-hue, so four
#: cards on one sheet read as "designed" rather than as four grey boxes.
_INFOGRAPHIC_ACCENTS = (
    (15, 118, 110),   # teal
    (180, 83, 9),     # amber
    (124, 58, 110),   # plum
    (30, 90, 160),    # blue
)


def _icon_check_badge(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color: tuple) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    _draw_tick(draw, (cx, cy + 1), fill=(255, 255, 255))


def _icon_clock_badge(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color: tuple) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    draw.line((cx, cy, cx, cy - r * 0.55), fill=(255, 255, 255), width=3)
    draw.line((cx, cy, cx + r * 0.4, cy + r * 0.15), fill=(255, 255, 255), width=3)
    draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=(255, 255, 255))


def _icon_scale_badge(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color: tuple) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    draw.line((cx - r * 0.5, cy + r * 0.15, cx + r * 0.5, cy - r * 0.15), fill=(255, 255, 255), width=3)
    draw.ellipse((cx - r * 0.5 - 5, cy + r * 0.15 - 5, cx - r * 0.5 + 5, cy + r * 0.15 + 5), outline=(255, 255, 255), width=2)
    draw.ellipse((cx + r * 0.5 - 5, cy - r * 0.15 - 5, cx + r * 0.5 + 5, cy - r * 0.15 + 5), outline=(255, 255, 255), width=2)


def _icon_grid_badge(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, color: tuple) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    s = r * 0.55
    draw.rectangle((cx - s, cy - s, cx + s, cy + s), outline=(255, 255, 255), width=2)
    draw.line((cx - s, cy, cx + s, cy), fill=(255, 255, 255), width=2)
    draw.line((cx, cy - s, cx, cy + s), fill=(255, 255, 255), width=2)


_INFOGRAPHIC_ICONS = (_icon_check_badge, _icon_clock_badge, _icon_scale_badge, _icon_grid_badge)


def _render_highlight_grid(aid: dict[str, Any]) -> Image.Image:
    """A colorful 2x2 (or up to 2x3) grid of stat/fact cards.

    Distinct from every row-based aid: each card gets its own accent color
    and icon badge, not a shared teal outline down a list of rows.
    """
    cards = [c for c in (aid.get("cards") or []) if isinstance(c, dict)][:6]
    n = max(1, len(cards))
    cols = 2
    rows = (n + cols - 1) // cols
    width = 1400
    card_w, card_h, gap = 640, 260, 40
    height = 130 + rows * (card_h + gap)
    img, draw = _new_canvas(width, height)
    _draw_title(draw, str(aid.get("title") or "At a Glance"), width)
    stat_font = _font(30, bold=True)
    label_font = _font(16)
    x0 = (width - (cols * card_w + (cols - 1) * gap)) // 2
    y0 = 118
    for i, card in enumerate(cards):
        r, c = divmod(i, cols)
        x = x0 + c * (card_w + gap)
        y = y0 + r * (card_h + gap)
        accent = _INFOGRAPHIC_ACCENTS[i % len(_INFOGRAPHIC_ACCENTS)]
        icon = _INFOGRAPHIC_ICONS[i % len(_INFOGRAPHIC_ICONS)]
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), 16, fill=(255, 255, 255), outline=accent, width=3)
        draw.rounded_rectangle((x, y, x + card_w, y + 10), 16, fill=accent)
        icon(draw, x + 62, y + 74, 34, accent)
        stat = _plain_cell(card.get("stat") or "")
        for j, line in enumerate(_wrap(draw, stat, stat_font, card_w - 130)[:2]):
            draw.text((x + 116, y + 42 + j * 36), line, font=stat_font, fill=(15, 23, 42))
        label = _plain_cell(card.get("label") or "")
        ty = y + 132
        for line in _wrap(draw, label, label_font, card_w - 48)[:4]:
            draw.text((x + 24, ty), line, font=label_font, fill=(51, 65, 85))
            ty += 24
    return img


_FLOW_ICON_KINDS = {
    "in": "up",
    "inhale": "up",
    "out": "down",
    "exhale": "down",
    "hold": "hold",
    "start": "start",
}


def _icon_breath(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float, kind: str, color: tuple) -> None:
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=4, fill=(255, 255, 255))
    k = _FLOW_ICON_KINDS.get(kind, "hold")
    if k == "up":
        draw.polygon([(cx, cy - r * 0.5), (cx - r * 0.32, cy + r * 0.2), (cx + r * 0.32, cy + r * 0.2)], fill=color)
    elif k == "down":
        draw.polygon([(cx, cy + r * 0.5), (cx - r * 0.32, cy - r * 0.2), (cx + r * 0.32, cy - r * 0.2)], fill=color)
    elif k == "start":
        draw.ellipse((cx - r * 0.28, cy - r * 0.28, cx + r * 0.28, cy + r * 0.28), fill=color)
    else:  # hold — two bars
        draw.rectangle((cx - r * 0.32, cy - r * 0.38, cx - r * 0.1, cy + r * 0.38), fill=color)
        draw.rectangle((cx + r * 0.1, cy - r * 0.38, cx + r * 0.32, cy + r * 0.38), fill=color)


def _render_practice_flow(aid: dict[str, Any]) -> Image.Image:
    """An icon-and-arrow practice sequence with a timing badge per step.

    Distinct from `_render_horizontal_steps`: each box carries a breath-phase
    icon (inhale / hold / exhale) and an explicit duration, and the sequence
    closes with a drawn loop-back arrow plus a repeat caption, rather than
    ending at the last box.
    """
    steps = [s for s in (aid.get("steps") or []) if isinstance(s, dict)][:6]
    n = max(1, len(steps))
    width = 1400
    box_w = min(220, max(150, (width - 100 - (n - 1) * 30) // n))
    gap = 30
    total_w = n * box_w + (n - 1) * gap
    x0 = (width - total_w) // 2
    y0 = 150
    box_h = 230
    height = y0 + box_h + 130
    img, draw = _new_canvas(width, height)
    _draw_title(draw, str(aid.get("title") or "Practice Flow"), width)
    accent = _pal("accent")
    label_font = _font(15, bold=True)
    time_font = _font(14, bold=True)
    centers: list[float] = []
    for i, step in enumerate(steps):
        x = x0 + i * (box_w + gap)
        cx = x + box_w / 2
        centers.append(cx)
        draw.rounded_rectangle((x, y0, x + box_w, y0 + box_h), 14, fill=(255, 255, 255), outline=accent, width=2)
        _icon_breath(draw, cx, y0 + 56, 32, str(step.get("kind") or "hold"), accent)
        timing = _plain_cell(step.get("timing") or "")
        if timing:
            tw, _ = _text_size(draw, timing, time_font)
            badge = (cx - tw / 2 - 10, y0 + 96, cx + tw / 2 + 10, y0 + 122)
            draw.rounded_rectangle(badge, 12, fill=accent)
            draw.text((cx - tw / 2, y0 + 100), timing, font=time_font, fill=(255, 255, 255))
        ty = y0 + 136
        for line in _wrap(draw, _plain_cell(step.get("label") or ""), label_font, box_w - 24)[:4]:
            lw, _ = _text_size(draw, line, label_font)
            draw.text((cx - lw / 2, ty), line, font=label_font, fill=(15, 23, 42))
            ty += 20
        if i < n - 1:
            ax = x + box_w + 4
            draw.polygon([(ax, y0 + box_h / 2 - 12), (ax + gap - 8, y0 + box_h / 2), (ax, y0 + box_h / 2 + 12)], fill=accent)
    if n >= 2:
        loop_y = y0 + box_h + 34
        left_x, right_x = centers[1], centers[-1]
        draw.line((left_x, y0 + box_h, left_x, loop_y), fill=accent, width=3)
        draw.line((right_x, y0 + box_h, right_x, loop_y), fill=accent, width=3)
        draw.line((left_x, loop_y, right_x, loop_y), fill=accent, width=3)
        # Arrowhead points UP, back into the second box — this line is the
        # "repeat from here" return path, not a new step leaving the box.
        draw.polygon([(left_x - 10, loop_y + 10), (left_x + 10, loop_y + 10), (left_x, loop_y - 8)], fill=accent)
        caption = _plain_cell(aid.get("repeat_caption") or "Repeat until the timer sounds")
        cfont = _font(15)
        cw, _ = _text_size(draw, caption, cfont)
        draw.text(((width - cw) / 2, loop_y + 16), caption, font=cfont, fill=(71, 85, 105))
    return img


def _render_habit_loop(aid: dict[str, Any]) -> Image.Image:
    """A four-node circular habit loop, arrows running clockwise back to node 1.

    Distinct from every straight-line aid on purpose: a habit loop is
    circular by definition, so this is the one aid on the sheet that is
    round.
    """
    import math

    nodes = [_plain_cell(x) for x in (aid.get("nodes") or [])][:4]
    while len(nodes) < 4:
        nodes.append("")
    width, height = 1400, 980
    img, draw = _new_canvas(width, height)
    _draw_title(draw, str(aid.get("title") or "The Habit Loop"), width)
    accent = _pal("accent")
    cx, cy, R = width / 2, 560, 300
    node_r = 108
    angles = [270, 0, 90, 180]  # top, right, bottom, left — clockwise
    positions = [
        (cx + R * math.cos(math.radians(a)), cy + R * math.sin(math.radians(a)))
        for a in angles
    ]
    bbox = (cx - R, cy - R, cx + R, cy + R)
    pad = 16
    for i in range(4):
        start = angles[i] + pad
        end = angles[i] + 90 - pad
        draw.arc(bbox, start, end, fill=accent, width=6)
        end_angle_rad = math.radians(end)
        ex = cx + R * math.cos(end_angle_rad)
        ey = cy + R * math.sin(end_angle_rad)
        tangent = end_angle_rad + math.pi / 2
        tx, ty = math.cos(tangent), math.sin(tangent)
        nx, ny = math.cos(end_angle_rad), math.sin(end_angle_rad)
        p1 = (ex - 14 * tx - 4 * nx, ey - 14 * ty - 4 * ny)
        p2 = (ex + 14 * tx - 4 * nx, ey + 14 * ty - 4 * ny)
        p3 = (ex + 12 * nx, ey + 12 * ny)
        draw.polygon([p1, p2, p3], fill=accent)
    label_font = _font(17, bold=True)
    num_font = _font(15, bold=True)
    for i, (nx, ny) in enumerate(positions):
        draw.ellipse((nx - node_r, ny - node_r, nx + node_r, ny + node_r), fill=(255, 255, 255), outline=accent, width=4)
        badge = (nx - node_r + 8, ny - node_r + 8, nx - node_r + 40, ny - node_r + 40)
        draw.ellipse(badge, fill=accent)
        num = str(i + 1)
        nw, nh = _text_size(draw, num, num_font)
        draw.text((nx - node_r + 24 - nw / 2, ny - node_r + 24 - nh / 2), num, font=num_font, fill=(255, 255, 255))
        lines = _wrap(draw, nodes[i], label_font, node_r * 1.6)[:4]
        ty = ny - (len(lines) * 22) / 2
        for line in lines:
            lw, _ = _text_size(draw, line, label_font)
            draw.text((nx - lw / 2, ty), line, font=label_font, fill=(15, 23, 42))
            ty += 22
    return img


def _render_calendar_tracker(aid: dict[str, Any]) -> Image.Image:
    """A colorful two-week (7x2) progress-tracker grid, one cell per day.

    Distinct from the checklist rows: this is a real calendar/tracker shape
    a reader fills in day by day, not a list of sentences.
    """
    days = [d for d in (aid.get("days") or []) if isinstance(d, dict)][:14]
    width = 1400
    cols = 7
    cell_w = (width - 80) // cols
    cell_h = 210  # was 168 -- daily text, duration and checkbox were cramped
    week_gap = 44
    header_h = 34
    height = 128 + 2 * (header_h + cell_h) + week_gap
    img, draw = _new_canvas(width, height)
    _draw_title(draw, str(aid.get("title") or "Progress Tracker"), width)
    week_accents = (_pal("accent"), _pal("secondary"))
    day_font = _font(17, bold=True)
    body_font = _font(14)
    dur_font = _font(13, bold=True)
    wk_font = _font(15, bold=True)
    x0 = 40
    for week in range(2):
        accent = week_accents[week]
        y_head = 118 + week * (header_h + cell_h + week_gap)
        draw.text((x0, y_head), f"Week {week + 1}", font=wk_font, fill=accent)
        y0 = y_head + header_h
        for col in range(cols):
            idx = week * cols + col
            x = x0 + col * cell_w
            draw.rounded_rectangle((x, y0, x + cell_w - 8, y0 + cell_h), 10, fill=(255, 255, 255), outline=accent, width=2)
            draw.rounded_rectangle((x, y0, x + cell_w - 8, y0 + 30), 10, fill=accent)
            if idx < len(days):
                d = days[idx]
                dnum = str(d.get("day") or idx + 1)
                draw.text((x + 10, y0 + 5), f"Day {dnum}", font=day_font, fill=(255, 255, 255))
                ty = y0 + 44
                for line in _wrap(draw, _plain_cell(d.get("label") or ""), body_font, cell_w - 24)[:5]:
                    draw.text((x + 10, ty), line, font=body_font, fill=(30, 41, 59))
                    ty += 19
                dur = _plain_cell(d.get("duration") or "")
                if dur:
                    draw.text((x + 10, y0 + cell_h - 32), dur, font=dur_font, fill=accent)
                box = (x + cell_w - 44, y0 + cell_h - 42, x + cell_w - 16, y0 + cell_h - 14)
                draw.rounded_rectangle(box, 4, outline=accent, width=3)
    return img


def render_aid_png(aid: dict[str, Any], *, scale: float = 1.0) -> Image.Image:
    """Render one aid to a PNG. scale=2.0 re-runs the same drawing instructions
    at double resolution (not a resize of a 1x render) -- see _ScaledDraw."""
    if scale and scale != 1.0:
        with _RenderScale(scale):
            return render_aid_png(aid, scale=1.0)
    kind = str(aid.get("type") or "").lower()
    if kind == "chart":
        return _render_chart(aid)
    if kind == "comparison":
        return _render_comparison(aid)
    if kind == "infographic":
        return _render_highlight_grid(aid)
    if kind == "flow":
        return _render_practice_flow(aid)
    if kind == "loop":
        return _render_habit_loop(aid)
    if kind == "calendar":
        return _render_calendar_tracker(aid)
    if kind == "photo":
        raise ValueError("Photograph aids must use a stored image file; they are not locally invented.")
    if kind == "workflow":
        raw_items = [_plain_cell(x) for x in (aid.get("items") or [])]
        if _station_map_layout(aid):
            return _render_station_map(aid, _short_items(raw_items, 7))
        items = _short_items(raw_items, 6)
        if items and all(len(x) <= 48 for x in items):
            return _render_horizontal_steps(aid, items, kind="workflow")
        return _render_steps({**aid, "items": items}, kind="workflow")
    if kind == "timeline":
        items = _short_items([_plain_cell(x) for x in (aid.get("items") or [])], 6)
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

    # Every check above asks about one file: does it exist, is it a real PNG,
    # does its hash match, is it captioned. A book can pass all of them and
    # still be nine copies of the same rounded box — which is what shipped.
    # The editorial review judges the set instead of the file, so a
    # text-box-only interior can no longer reach Visuals Approved (v1.5.0).
    if not findings:
        from services.ebook_visual_editorial import review_visual_set
        from services.ebook_pexels import pexels_configured

        # A book whose subject supports photography should still be judged
        # on subject grounds for every other editorial check (variety,
        # illustrative share, etc.) -- but the MINIMUM PHOTOGRAPH COUNT can
        # only ever be satisfied by a real acquisition, and this Factory's
        # own test isolation deliberately blocks that (no live Pexels calls
        # during automated tests). Demanding real photographs the current
        # run has no way to obtain is not a stricter editorial bar, it is an
        # unconditional failure with no honest path to green -- found by
        # tracing why a chapter whose commissioned photo correctly fell back
        # to a local visual (Pexels unreachable, exactly as intended) then
        # failed a SEPARATE check for not being a real photograph.
        report = review_visual_set(
            plan,
            chapter_count=len(plan.get("chapters") or []),
            photography_supported=_photography_supported(data) and pexels_configured(),
            pdf_path=_designed_pdf_path(data),
        )
        findings.extend(report.findings)

    ok = not findings
    return VisualValidation(ok, findings, required_count=len(required), resolved_count=resolved)


def _photography_supported(data: dict) -> bool:
    """Whether this book's own subject admits photographs at all.

    A book about a physical practice, a place or a person does; a pure
    reference table might not, and must not be failed for that.
    """
    from services.ebook_visual_match import photography_supported_subject

    plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {}
    title = str(data.get("title") or plan.get("title") or "")
    body = str(data.get("content") or "")[:6000]
    if photography_supported_subject(
        title=title, topic=str(data.get("topic") or ""), content=body
    ):
        return True
    # A book that already carries a photograph has settled the question.
    return any(
        str(aid.get("type") or "").lower() in {"photo", "stock photo"}
        for chapter in (plan.get("chapters") or [])
        for aid in (chapter.get("aids") or [])
    )


def _designed_pdf_path(data: dict) -> str:
    """The PDF a customer would actually open, if one exists yet."""
    exports = data.get("exports") if isinstance(data.get("exports"), dict) else {}
    files = exports.get("files") if isinstance(exports.get("files"), dict) else {}
    meta = files.get("pdf") if isinstance(files.get("pdf"), dict) else {}
    path = str(meta.get("path") or data.get("pdf_path") or "")
    return path if path and os.path.isfile(path) else ""


def visuals_are_ready(data: dict, *, html: str | None = None) -> bool:
    return validate_visual_readiness(data, html=html).ok


def _embed_preview_image(path: str, max_w: int = 1600) -> tuple[str, int, int]:
    """JPEG data-URI for PDF/HTML. Stored PNG files and SHAs stay unchanged.

    max_w was 720 -- every interior visual and photograph was being
    downsampled to 720px (~105 PPI on a printed page) before it ever reached
    the PDF, regardless of the source file's real resolution. Raised to
    1600px, in the 1,400-1,800px range a printed page actually needs.
    """
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


def figure_html(aid: dict[str, Any], *, palette: dict[str, tuple[int, int, int]] | None = None) -> str:
    """`palette`, when given, re-renders a generated (non-photo) diagram
    fresh in the current design theme's colors instead of embedding the
    stored file -- see _RenderPalette / theme_diagram_palette. It never
    touches aid["asset_path"]/aid["sha256"]: the approved visual record (and
    every hash test against it) is unaffected, because switching themes must
    not force re-approving visuals and an approved photograph's hash must
    never move. Only what this one render of the PDF actually shows changes.
    """
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
    is_photo = is_photo_aid(aid)
    uri = w = h = None
    if palette and not is_photo:
        try:
            with _RenderPalette(palette):
                img = render_aid_png(aid, scale=2.0)
            buf = io.BytesIO()
            img.convert("RGB").save(buf, format="JPEG", quality=88)
            uri = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
            # scale=2.0 doubles pixel dimensions for print sharpness; report
            # the same logical width/height _embed_preview_image would.
            w, h = img.size[0] // 2, img.size[1] // 2
        except Exception:
            uri = None
    if not uri:
        path = str(aid.get("asset_path") or "")
        if not path or not os.path.isfile(path):
            return ""
        uri, w, h = _embed_preview_image(path)
        if not uri:
            return ""
    photo_cls = " ebook-figure-photo" if is_photo else ""
    return (
        f'<figure class="ebook-figure{photo_cls}" id="{vid}" data-visual-id="{vid}" data-sha="{sha}">'
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


def insert_planned_visuals_into_html(
    html_doc: str,
    visual_plan: dict | None,
    *,
    palette: dict[str, tuple[int, int, int]] | None = None,
) -> str:
    """Place each required visual into its chapter section. No manuscript
    rewrite. `palette` (see figure_html) makes generated diagrams pick up the
    current design theme's colors; omit it to embed the stored files as-is,
    which is what every caller before design/theme existed still gets."""
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
            frag = BeautifulSoup(figure_html(aid, palette=palette), "html.parser")
            node = frag.find("figure")
            if node is None:
                continue
            h2 = section.find("h2")
            # A themed chapter opener (Warm Wellness's colored band) wraps
            # the h2 in its own div. Inserting after the bare h2 then drops
            # the figure INSIDE that div, so the visual (and its caption)
            # inherit the band's background/text color -- caught by
            # rendering an actual chapter and looking at it, not by reading
            # the CSS. Anchor on the top-level child of the section instead,
            # so the figure always lands as a section-level sibling.
            anchor = h2
            if anchor is not None and anchor.parent is not section:
                anchor = anchor.parent
            existing_figs = section.find_all("figure", class_="ebook-figure")
            if existing_figs:
                existing_figs[-1].insert_after(node)
            elif anchor is not None:
                anchor.insert_after(node)
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
                # Full-size preview_data_uri was computed and shipped here too,
                # but app.js only ever renders thumb_data_uri on this screen --
                # the full-size copy was pure dead weight (100-250KB per photo)
                # that made the workspace payload big enough to freeze the
                # browser tab while rendering it. Dropped; see [full-preview]
                # route for the one place a full-size render is actually shown.
                "thumb_data_uri": _thumb_data_uri(path) if path else "",
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


def _carry_over_resolved_photographs(old_plan: dict | None, new_plan: dict) -> dict:
    """Keep photographs that were already found, matched and stored.

    Replanning must not mean re-downloading. When a chapter asked for a
    photograph before and still does, and the old one is on disk and passed its
    match, it is carried across rather than fetched again.
    """
    if not isinstance(old_plan, dict) or not isinstance(new_plan, dict):
        return new_plan
    from services.ebook_visual_match import MATCH_PASS

    keep: dict[int, dict] = {}
    for chapter in old_plan.get("chapters") or []:
        for aid in (chapter.get("aids") or []) if isinstance(chapter, dict) else []:
            if not isinstance(aid, dict):
                continue
            if str(aid.get("type") or "").lower() not in {"photo", "stock photo"}:
                continue
            if str(aid.get("match_status") or "") != MATCH_PASS:
                continue
            path = str(aid.get("asset_path") or "")
            if not path or not os.path.isfile(path):
                continue
            try:
                keep[int(aid.get("chapter_index") or 0)] = aid
            except (TypeError, ValueError):
                continue

    if not keep:
        return new_plan
    for chapter in new_plan.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for position, aid in enumerate(chapter.get("aids") or []):
            if not isinstance(aid, dict):
                continue
            if str(aid.get("type") or "").lower() not in {"photo", "stock photo"}:
                continue
            try:
                index = int(aid.get("chapter_index") or 0)
            except (TypeError, ValueError):
                continue
            previous = keep.get(index)
            if previous:
                chapter["aids"][position] = dict(previous)
    return new_plan


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
    md = str(data.get("content") or data.get("ebook") or "")
    title = str(data.get("title") or "")
    topic = str((data.get("fields") or {}).get("topic") or data.get("topic") or "")

    # Photographs used to be planned only when the customer had ticked an
    # "automatic images" box, and even then only for subjects classified
    # photo-LED. A book teaching a practice is not photo-led, so a 44-page
    # mindfulness title was planned with no photograph considered at any point.
    # Stock photography is free and already authorized; whether the book may
    # have any is a question about the subject, not about a checkbox (v1.5.0).
    from services.ebook_visual_match import photography_supported_subject

    photographic = photography_supported_subject(title=title, topic=topic, content=md[:6000])

    # Reusing a plan because it is structurally valid is the same mistake as
    # approving a visual because the PNG opens: "it exists" is not "it is any
    # good". A book whose plan was nine near-identical text boxes could be
    # rebuilt forever and would come back nine near-identical text boxes,
    # because nothing ever asked whether the plan was worth keeping.
    reuse = bool(plan_is_valid(existing) and required_aids(existing))
    if reuse:
        from services.ebook_visual_editorial import review_visual_set
        from services.ebook_pexels import pexels_configured

        # Same reasoning as the identical gate in validate_visual_readiness:
        # a real photograph count can only be demanded when a real
        # acquisition path is actually reachable in this run.
        verdict = review_visual_set(
            existing,
            chapter_count=len(existing.get("chapters") or []),
            photography_supported=photographic and pexels_configured(),
        )
        if not verdict.ok:
            reuse = False

    if reuse:
        plan = existing
    else:
        set_visual_progress(data, PROGRESS_PLANNING)
        plan = plan_content_aware_visuals(
            md,
            title=title,
            topic=topic,
            research=ws.get("research_payload") if isinstance(ws.get("research_payload"), dict) else None,
            include_photographs=automatic or photographic,
        )
        plan = _carry_over_resolved_photographs(existing, plan)
    pkg = _package_id(data)
    data["package_id"] = data.get("package_id") or pkg
    # _commission_media_mix (above, inside plan_content_aware_visuals) commits
    # a chapter to a "photo, status=missing" aid whenever the SUBJECT supports
    # photography -- by its own design comment, "whether the book may have a
    # photograph is a question about the subject, not about a checkbox"
    # (v1.5.0). But resolution here was still gated on automatic alone (the
    # checkbox), so a commitment made on subject grounds could go permanently
    # unresolved whenever the checkbox was off -- exactly the "no existing
    # local asset file" failure this reconciles. fill_plan_photos_automatic's
    # own fallback chain (Pexels, then a free local visual built from the
    # chapter's own text, then paid AI only with explicit authorization) was
    # already safe to call on subject grounds alone; it just was not being
    # called.
    if automatic or photographic:
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


def collect_zip_visual_files(
    data: dict, *, palette: dict[str, tuple[int, int, int]] | None = None
) -> dict[str, bytes]:
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
        # Keep the ZIP's own images consistent with what the PDF actually
        # shows: a generated diagram re-rendered in the current theme's
        # colors for the PDF (see figure_html) should not ship as the old
        # fixed-teal file in the companion ZIP. Never applies to photographs
        # or to a caller with no palette (e.g. the pre-design "prepare
        # visuals" package, or a test asserting the stored bytes verbatim),
        # both of which fall straight through to the stored file below.
        if palette and not is_photo_aid(aid):
            try:
                with _RenderPalette(palette):
                    img = render_aid_png(aid, scale=2.0)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                files[f"visuals/{vid}.png"] = buf.getvalue()
                continue
            except Exception:
                pass
        if path and os.path.isfile(path):
            files[f"visuals/{vid}.png"] = Path(path).read_bytes()
    return files
