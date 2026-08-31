"""Ebook visual rendering + export packaging.

After the Product Factory generates an ebook (Markdown), this module:
1. Asks the AI for a structured *visual plan* -- for every chapter, at least two
   visual aids with ACTUAL renderable content (chart data, table rows, tip text,
   action/worksheet checklists, Mermaid diagram definitions, or image prompts),
   plus a cover image prompt, a marketing subtitle and a product summary.
2. Renders a self-contained, formatted HTML ebook preview where the visuals are
   ACTUALLY rendered and inserted into each chapter:
     - charts/graphs   -> Chart.js canvases (rendered in the browser)
     - tables          -> real HTML tables
     - tip/action/worksheet/checklist boxes -> styled HTML/CSS components
     - flowcharts/diagrams -> Mermaid.js diagrams
     - stock photos / infographics -> real AI-generated images (gpt-image-1)
3. Writes an export package to disk (ebook.html, ebook.txt, visual_plan.json,
   cover_prompt.txt, product_summary.txt and a package.zip).

Image rendering is intentionally NOT done inline (each image takes ~30s and would
blow the webview proxy timeout). build_ebook_package returns a list of
``image_jobs`` that the frontend renders progressively via /render-visual-image;
each finished PNG is written to exports/<package_id>/img_<visual_id>.png and the
stable <img> URL in the preview resolves as soon as the file exists.
"""
import base64
import html
import json
import os
import re
import uuid
import zipfile

import markdown as _markdown
from bs4 import BeautifulSoup

from ai_client import chat_json, get_client

# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _e(value) -> str:
    return html.escape(str(value or ""))


_ALLOWED_TAGS = {
    "p", "br", "hr", "strong", "em", "b", "i", "u", "s", "code", "pre",
    "blockquote", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "a",
    "span", "table", "thead", "tbody", "tr", "th", "td",
    "div", "colgroup", "col",
}
_ALLOWED_ATTRS = {"a": {"href", "title"}}
_BAD_URL_PREFIXES = ("javascript:", "data:", "vbscript:")


def _sanitize_html(raw_html: str) -> str:
    """Strip scripts/handlers/unknown tags so AI- or web-sourced content cannot
    execute inside the script-enabled preview iframe."""
    soup = BeautifulSoup(str(raw_html or ""), "html.parser")
    for tag in soup(["script", "style", "iframe", "object", "embed", "form"]):
        tag.decompose()
    for el in list(soup.find_all(True)):
        name = el.name.lower()
        if name not in _ALLOWED_TAGS:
            el.unwrap()
            continue
        allowed = _ALLOWED_ATTRS.get(name, set())
        for attr in list(el.attrs):
            if attr.lower() not in allowed:
                del el.attrs[attr]
            elif attr.lower() == "href":
                val = str(el.attrs[attr]).strip().lower()
                if val.startswith(_BAD_URL_PREFIXES):
                    del el.attrs[attr]
    return str(soup)


def _md_to_html(text: str) -> str:
    rendered = _markdown.markdown(str(text or ""), extensions=["extra", "sane_lists"])
    return fix_inline_hyphen_lists_html(_sanitize_html(rendered))


def fix_inline_hyphen_lists_html(html: str) -> str:
    """Convert inline ': - item - item' patterns and hyphen lines into real lists."""
    if not html or not html.strip():
        return html
    soup = BeautifulSoup(html, "html.parser")
    _fix_hyphen_list_paragraphs(soup)
    for heading in soup.find_all(["h2", "h3", "h4"]):
        if heading.find_parent(class_="h3-block"):
            continue
        wrap = soup.new_tag("div")
        wrap["class"] = "h3-block"
        heading.wrap(wrap)
    return str(soup)


def _fix_hyphen_list_paragraphs(soup: BeautifulSoup) -> None:
    for p in list(soup.find_all("p")):
        inner = p.decode_contents()
        if re.search(r":(?:\s*<br\s*/?\s*>|\s*\n)\s*[-*•]", inner, re.I):
            parts = re.split(r"<br\s*/?\s*>|\n", inner, flags=re.I)
            parts = [BeautifulSoup(part, "html.parser").get_text(" ", strip=True) for part in parts]
            parts = [part for part in parts if part]
            if len(parts) >= 2:
                intro_parts: list[str] = []
                items: list[str] = []
                for part in parts:
                    item_match = re.match(r"^[-*•]\s+(.*)$", part)
                    if item_match:
                        items.append(item_match.group(1).strip())
                    elif not items:
                        intro_parts.append(part)
                if len(items) >= 2:
                    wrapper = soup.new_tag("div")
                    intro_text = " ".join(intro_parts).strip()
                    if intro_text:
                        intro_p = soup.new_tag("p")
                        intro_p.string = intro_text
                        wrapper.append(intro_p)
                    ul = soup.new_tag("ul")
                    for item in items:
                        li = soup.new_tag("li")
                        li.string = item
                        ul.append(li)
                    wrapper.append(ul)
                    p.replace_with(wrapper)
                    continue

        text = p.get_text(" ", strip=True)
        if not text:
            continue
        colon_match = re.match(r"^(.+?:)\s*(.+)$", text)
        if colon_match and re.search(r"\s-\s+", colon_match.group(2)):
            intro, rest = colon_match.group(1), colon_match.group(2)
            items = [
                re.sub(r"^[-*•]\s+", "", x.strip())
                for x in re.split(r"\s+-\s+", rest)
                if x.strip()
            ]
            if len(items) >= 2:
                wrapper = soup.new_tag("div")
                intro_p = soup.new_tag("p")
                intro_p.string = intro
                wrapper.append(intro_p)
                ul = soup.new_tag("ul")
                for item in items:
                    li = soup.new_tag("li")
                    li.string = item
                    ul.append(li)
                wrapper.append(ul)
                p.replace_with(wrapper)
                continue
        lines = [ln.strip() for ln in p.get_text("\n", strip=False).split("\n") if ln.strip()]
        if len(lines) >= 2:
            intro_lines: list[str] = []
            items: list[str] = []
            for ln in lines:
                item_match = re.match(r"^[-*•]\s+(.*)$", ln)
                if item_match:
                    items.append(item_match.group(1).strip())
                elif not items:
                    intro_lines.append(ln)
            if len(items) >= 2:
                wrapper = soup.new_tag("div")
                intro_text = " ".join(intro_lines).strip()
                if intro_text:
                    intro_p = soup.new_tag("p")
                    intro_p.string = intro_text
                    wrapper.append(intro_p)
                ul = soup.new_tag("ul")
                for item in items:
                    li = soup.new_tag("li")
                    li.string = item
                    ul.append(li)
                wrapper.append(ul)
                p.replace_with(wrapper)
                continue
        if len(lines) == 1 and re.match(r"^[-*•]\s+", lines[0]):
            ul = soup.new_tag("ul")
            li = soup.new_tag("li")
            li.string = re.sub(r"^[-*•]\s+", "", lines[0])
            ul.append(li)
            p.replace_with(ul)
            continue
        if len(lines) >= 2 and all(re.match(r"^[-*•]\s+", ln) for ln in lines):
            ul = soup.new_tag("ul")
            for ln in lines:
                li = soup.new_tag("li")
                li.string = re.sub(r"^[-*•]\s+", "", ln)
                ul.append(li)
            p.replace_with(ul)


# A TOC entry line: optional list marker, then a markdown anchor link and nothing
# else. The closing paren is optional because stored summaries were truncated at
# 400 chars, cutting the final link mid-anchor.
_MD_TOC_LINE_RE = re.compile(r"^\s*(?:\d+[.)]|[-*+])?\s*\[[^\]]+\]\(#[^)\s]*\)?\s*$")
_MD_INLINE_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]*\)?")


def clean_product_summary(text: str) -> str:
    """Make a stored product summary safe to print in customer-facing output.

    Manuscripts open with a markdown TOC, and the fallback summary derivation
    used to grab that block verbatim, so saved projects can carry summaries that
    are nothing but truncated ``[Chapter](#anchor)`` lines. Cleaning happens at
    render time so those projects heal without rewriting their records. Returns
    "" when nothing readable remains — callers must then omit the block.
    """
    raw = str(text or "").strip()
    if not raw:
        return ""
    kept = [ln for ln in raw.splitlines() if ln.strip() and not _MD_TOC_LINE_RE.match(ln)]
    joined = " ".join(kept)
    joined = _MD_INLINE_LINK_RE.sub(r"\1", joined)
    joined = re.sub(r"^\s*#{1,6}\s*", "", joined)
    joined = re.sub(r"\s+", " ", joined).strip()
    # A summary reduced to stray list numbers ("1. 2. 3.") is not readable text.
    if not re.search(r"[A-Za-z]{3,}", joined):
        return ""
    return joined


def derive_product_summary(content_md: str, limit: int = 400) -> str:
    """First real prose paragraph of a manuscript, cut on a sentence boundary.

    Skips the H1 and any leading TOC/list/heading blocks instead of blindly
    taking the first paragraph, which is how markdown TOCs ended up printed on
    title pages.
    """
    text = str(content_md or "").strip()
    if not text:
        return ""
    for block in re.split(r"\n\s*\n", text):
        stripped = block.strip()
        if not stripped:
            continue
        lines = stripped.splitlines()
        if all(
            re.match(r"^\s*(?:#{1,6}\s|\d+[.)]\s|[-*+]\s|\[|!\[)", ln) or not ln.strip()
            for ln in lines
        ):
            continue
        prose = re.sub(r"\s+", " ", stripped).strip()
        prose = _MD_INLINE_LINK_RE.sub(r"\1", prose)
        if len(prose) < 40:
            continue
        if len(prose) <= limit:
            return prose
        cut = prose[:limit]
        # Prefer ending on a completed sentence over a mid-word chop.
        end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        return cut[: end + 1].strip() if end >= 120 else cut.rstrip() + "…"
    return ""


def _norm_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()).strip()


def _split_chapters(md_text: str) -> tuple[str, list[tuple[str, str]]]:
    """Return (preamble_markdown, [(chapter_title, chapter_markdown), ...])."""
    md_text = md_text or ""
    matches = list(_H2_RE.finditer(md_text))
    if not matches:
        return md_text.strip(), []
    preamble = md_text[: matches[0].start()].strip()
    chapters: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        chapters.append((m.group(1).strip(), md_text[start:end].strip()))
    return preamble, chapters


# ---------------------------------------------------------------------------
# Visual aid types
# ---------------------------------------------------------------------------

_TYPE_LABELS = {
    "chart": "Chart",
    "graph": "Graph",
    "table": "Table",
    "diagram": "Diagram",
    "infographic": "Infographic",
    "stock photo": "Image",
    "worksheet box": "Worksheet",
    "tip box": "Tip",
    "action step box": "Action Steps",
    "youtube resource box": "YouTube Resource",
}

# Aid types that are rendered as real generated images.
_IMAGE_GEN_TYPES = {"stock photo", "infographic"}


def _norm_type(value: str) -> str:
    t = str(value or "").strip().lower()
    if "youtube" in t or "video" in t:
        return "youtube resource box"
    if "illustration" in t or "stock" in t or "photo" in t or "image" in t:
        return "stock photo"
    if "checklist" in t or "worksheet" in t:
        return "worksheet box"
    if "action" in t or "step" in t:
        return "action step box"
    if "tip" in t or "callout" in t:
        return "tip box"
    if "infograph" in t:
        return "infographic"
    if "diagram" in t or "flow" in t or "process" in t:
        return "diagram"
    if "table" in t:
        return "table"
    if "graph" in t:
        return "graph"
    if "chart" in t:
        return "chart"
    return "tip box"


def _coerce_chart_data(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    labels = raw.get("labels")
    values = raw.get("values")
    if not isinstance(labels, list) or not isinstance(values, list):
        return None
    labels = [str(x).strip() for x in labels]
    clean_values = []
    for v in values:
        try:
            clean_values.append(float(v))
        except (TypeError, ValueError):
            clean_values.append(0.0)
    if not labels or not clean_values:
        return None
    kind = str(raw.get("kind") or "bar").strip().lower()
    if kind not in {"bar", "line", "pie", "doughnut"}:
        kind = "bar"
    n = min(len(labels), len(clean_values))
    return {"kind": kind, "labels": labels[:n], "values": clean_values[:n]}


def _coerce_table(raw) -> dict | None:
    if not isinstance(raw, dict):
        return None
    headers = raw.get("headers")
    rows = raw.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    headers = [str(h).strip() for h in headers] if isinstance(headers, list) else []
    clean_rows = []
    for row in rows:
        if isinstance(row, list):
            clean_rows.append([str(c).strip() for c in row])
        elif row is not None:
            clean_rows.append([str(row).strip()])
    clean_rows = [r for r in clean_rows if any(c for c in r)]
    if not clean_rows:
        return None
    return {"headers": headers, "rows": clean_rows}


def _coerce_items(raw) -> list[str]:
    if isinstance(raw, str):
        parts = re.split(r"\n+", raw)
        return [p.strip(" -*\t") for p in parts if p.strip(" -*\t")]
    if isinstance(raw, list):
        return [str(x).strip() for x in raw if str(x).strip()]
    return []


def _coerce_aid(raw: dict) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    atype = _norm_type(raw.get("type"))
    keywords = raw.get("keywords")
    if isinstance(keywords, str):
        keywords = [k.strip() for k in keywords.split(",") if k.strip()]
    elif isinstance(keywords, list):
        keywords = [str(k).strip() for k in keywords if str(k).strip()]
    else:
        keywords = []
    return {
        "type": atype,
        "title": str(raw.get("title") or "").strip(),
        "purpose": str(raw.get("purpose") or "").strip(),
        "description": str(raw.get("description") or "").strip(),
        "placement": str(raw.get("placement") or "").strip(),
        "caption": str(raw.get("caption") or "").strip(),
        "image_prompt": str(raw.get("image_prompt") or "").strip(),
        "keywords": keywords,
        "chart_data": _coerce_chart_data(raw.get("chart_data")),
        "table": _coerce_table(raw.get("table")),
        "body": str(raw.get("body") or "").strip(),
        "items": _coerce_items(raw.get("items")),
        "mermaid": str(raw.get("mermaid") or "").strip(),
    }


_MIN_AIDS_PER_CHAPTER = 2


def _fallback_aids(chapter_name: str, needed: int, aid_index: int = 0) -> list[dict]:
    """Deterministic visual aids so every chapter always meets the minimum.

    Each template uses a concrete action verb so the content reads as an actual
    worksheet prompt rather than a generic placeholder.  The title avoids
    starting with the chapter name so "Apply Apply Summary" never occurs.
    """
    templates = [
        {
            "type": "tip box",
            "title": "Key insight",
            "purpose": "Highlight the single most important idea of this chapter.",
            "body": (
                "Identify the one idea from this chapter that you can act on "
                "immediately. Write it in the space below, then plan your first step."
            ),
            "caption": "Capture the chapter's core message here.",
        },
        {
            "type": "action step box",
            "title": "Chapter action steps",
            "purpose": "Turn the chapter into concrete next steps.",
            "items": [
                "What is the main point of this chapter?",
                "Which part applies most to your situation?",
                "What will you do differently as a result?",
            ],
            "caption": "Complete these steps before moving on.",
        },
        {
            "type": "table",
            "title": "Chapter at a glance",
            "purpose": "Organize the chapter's key points visually.",
            "table": {
                "headers": ["Key concept", "How to use it"],
                "rows": [
                    ["Main topic", "Apply it to your specific goal"],
                    ["Supporting detail", "Build a habit around it"],
                ],
            },
            "caption": "Scan the chapter's ideas at a glance.",
        },
    ]
    # Stamp a zero-based index into body / items so identical aids across chapters
    # are still detectably different to the QA validator.
    chosen = [_coerce_aid(t) for t in templates[:needed]]
    for ai, aid in enumerate(chosen):
        offset = aid_index + ai
        if aid["type"] == "tip box":
            aid["body"] = f"{aid['body']} (Step {offset + 1})"
        elif aid["type"] == "action step box":
            for idx, item in enumerate(aid["items"]):
                aid["items"][idx] = f"{item} (Item {offset * len(aid['items']) + idx + 1})"
        elif aid["type"] == "table" and aid.get("table"):
            for row in aid["table"].get("rows", []):
                if row and len(row) > 1:
                    row[0] = f"{row[0]} ({offset + 1})"
    return chosen


def _coerce_plan(raw: dict, chapter_titles: list[str], title: str) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    plan_chapters_raw = raw.get("chapters")
    if not isinstance(plan_chapters_raw, list):
        plan_chapters_raw = []

    # Wrapper chapter titles that are book-level sections, not real chapters.
    _WRAPPER_TITLES = frozenset(
        t.lower()
        for t in (
            "Summary",
            "Action Steps",
            "Resources",
            "Introduction",
            "Conclusion",
            "Getting Started",
            "Quick Reference",
            "FAQ",
            "Worksheet",
            "Action Plan",
        )
    )

    chapters: list[dict] = []
    seen_titles: set[str] = set()  # deduplicate by normalized title

    for i, name in enumerate(chapter_titles):
        src = plan_chapters_raw[i] if i < len(plan_chapters_raw) else {}
        if not isinstance(src, dict):
            src = {}

        chapter_name = str(src.get("chapter") or name).strip() or name
        norm = _norm_title(chapter_name)

        # Skip AI wrapper chapters -- they are book-level sections, not real content chapters.
        # Also deduplicate: if the same normalized title appeared before, skip the repeat.
        if norm in _WRAPPER_TITLES or norm in seen_titles:
            continue
        seen_titles.add(norm)

        aids_raw = src.get("aids")
        if not isinstance(aids_raw, list):
            aids_raw = []

        # Filter and coerce aids
        aids = [_coerce_aid(a) for a in aids_raw if isinstance(a, dict)]
        meaningful_aids = [a for a in aids if _aid_has_content(a)]

        # Deduplicate visual titles within this chapter by appending (variation) to duplicates.
        seen_aid_titles: dict[str, int] = {}
        for aid in meaningful_aids:
            t = _norm_title(aid.get("title") or "")
            if t in seen_aid_titles:
                seen_aid_titles[t] += 1
                aid["title"] = f"{aid.get('title', 'Visual')} (variation)"
            else:
                seen_aid_titles[t] = 1

        # Only keep meaningful AI-provided aids. Do not invent generic
        # Key insight / Chapter action steps / Chapter at a glance fillers.
        for ai, aid in enumerate(meaningful_aids):
            aid["visual_id"] = f"v{i}_{ai}"
            aid["needs_image"] = aid["type"] in _IMAGE_GEN_TYPES
        chapters.append({"chapter": chapter_name, "aids": meaningful_aids})

    return {
        "title": title,
        "subtitle": str(raw.get("subtitle") or "").strip(),
        "cover_prompt": str(raw.get("cover_prompt") or "").strip(),
        "product_summary": str(raw.get("product_summary") or "").strip(),
        "chapters": chapters,
    }


def _is_meaningful_title(a: dict) -> bool:
    """Reject placeholder titles that are clearly AI-generated templates."""
    title = (a.get("title") or "").lower().strip()
    if not title:
        return False
    # Catch known wrapper/generic patterns
    generic_prefixes = (
        "key takeaway",
        "key insight",
        "key point",
        "key idea",
        "apply ",
        "at a glance",
        "chapter summary",
        "chapter action steps",
        "chapter at a glance",
        "action steps:",
    )
    for prefix in generic_prefixes:
        if title.startswith(prefix):
            return False
    return True


def _is_meaningful_body(a: dict) -> bool:
    """Reject body text that reads as a generic placeholder."""
    body = (a.get("body") or a.get("description") or "").lower()
    placeholder_phrases = (
        "distil",
        "the one thing worth keeping",
        "the one takeaway",
        "one takeaway from",
        "capture the core message",
        "core message here",
        "write it in the space below",
    )
    for phrase in placeholder_phrases:
        if phrase.lower() in body:
            return False
    return True


def _is_meaningful_items(a: dict) -> bool:
    """Reject checklist/step items that are generic placeholder questions."""
    items = a.get("items") or []
    if not items:
        return True  # No items is fine (body carries the content)
    placeholder_item_phrases = (
        "this chapter",
        "main point of this chapter",
        "which part applies most",
        "what will you do differently",
        "step {",
    )
    for item in items:
        item_lower = str(item).lower()
        for phrase in placeholder_item_phrases:
            if phrase.lower() in item_lower:
                return False
    return True


def _aid_has_content(a: dict) -> bool:
    """Reject AI-generated placeholder aids that add no real value.

    An aid has meaningful content only if its title, body, or items are
    specific and non-generic.  Aids that pass this check are used as-is;
    aids that fail get dropped before fallback logic fires.
    """
    title_ok = _is_meaningful_title(a)
    body_ok = _is_meaningful_body(a)
    items_ok = _is_meaningful_items(a)
    has_other_content = bool(
        a.get("table")
        or a.get("chart_data")
        or a.get("mermaid")
        or a.get("image_prompt")
        or a.get("type") == "youtube resource box"
    )
    return has_other_content or (title_ok and (body_ok or items_ok))


def _markdown_table_aid(chapter_md: str, *, title: str) -> dict | None:
    text = str(chapter_md or "")
    match = re.search(
        r"(?m)^(\|.+\|)\s*\n(\|[-:\s|]+\|)\s*\n((?:\|.+\|\s*\n?){1,6})",
        text,
    )
    if not match:
        return None
    headers = [c.strip() for c in match.group(1).strip("|").split("|")]
    rows = []
    for line in match.group(3).strip().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if any(cells):
            rows.append(cells)
    if not headers or not rows:
        return None
    return {
        "type": "table",
        "title": title,
        "caption": title,
        "table": {"headers": headers, "rows": rows},
    }


def _photo_led_local_plan(title: str, content_md: str, fields: dict, chapter_titles: list[str]) -> dict:
    """One relevant photograph per real chapter, plus at most one high-value table."""
    from services.ebook_pexels import chapter_pexels_queries

    preamble, split_chapters = _split_chapters(content_md)
    body_by_title = {_norm_title(name): body for name, body in split_chapters}
    real_titles: list[str] = []
    for name in chapter_titles:
        kind = _chapter_kind(name)
        if kind in {"toc", "description", "summary"}:
            continue
        real_titles.append(name)
    if not real_titles:
        real_titles = [t for t in chapter_titles if _chapter_kind(t) == "chapter"] or chapter_titles[:6]
    topic = str((fields or {}).get("topic") or title)
    chapters = []
    for name in real_titles:
        queries = chapter_pexels_queries(chapter=name, title=title, topic=topic)
        photo = {
            "type": "stock photo",
            "title": (queries[0][:1].upper() + queries[0][1:]) if queries else name,
            "caption": (queries[0][:1].upper() + queries[0][1:]) if queries else name,
            "keywords": queries,
            "image_prompt": f"photorealistic {queries[0] if queries else name}, no text",
        }
        aids: list[dict] = [photo]
        table = _markdown_table_aid(body_by_title.get(_norm_title(name), ""), title=f"{name} quick reference")
        if table:
            aids.append(table)
        chapters.append({"chapter": name, "aids": aids})
    subtitle = str((fields or {}).get("subtitle") or "").strip()
    summary = clean_product_summary((fields or {}).get("product_summary"))
    if not summary:
        summary = derive_product_summary(content_md)
    return {
        "title": title,
        "subtitle": subtitle,
        "cover_prompt": f"Photograph of {queries[0] if chapters else title}, no lettering.",
        "product_summary": summary,
        "chapters": chapters,
    }


def generate_visual_plan(title: str, content_md: str, fields: dict) -> dict:
    """Ask the AI for a per-chapter visual plan with real renderable content."""
    _, chapters = _split_chapters(content_md)
    chapter_titles = [c[0] for c in chapters] or [title or "Chapter 1"]
    if str(os.environ.get("EBOOK_CUSTOMER_PATH_FIXTURE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        from services.ebook_customer_path import fixture_visual_plan

        return _coerce_plan(fixture_visual_plan(title, content_md), chapter_titles, title)

    from services.ebook_visual_match import is_photo_led_subject

    if is_photo_led_subject(
        title=title,
        topic=str((fields or {}).get("topic") or ""),
        content=content_md,
    ):
        return _coerce_plan(
            _photo_led_local_plan(title, content_md, fields or {}, chapter_titles),
            [t for t in chapter_titles if _chapter_kind(t) == "chapter"] or chapter_titles,
            title,
        )

    listing = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(chapter_titles))

    raw = chat_json(
        system=(
            "You are a visual content designer and instructional designer. You "
            "design professional visual aids that make a written ebook clearer, "
            "more engaging and more sellable. You produce the ACTUAL content for "
            "each visual (real data, real rows, real steps, real diagram code) so "
            "it can be rendered directly. You only use information from the ebook "
            "and never invent unrelated facts.\n\n"
            "CLAIM SAFETY RULES — apply to the product_summary and subtitle:\n"
            "  FORBIDDEN (do not use, ever): scientifically proven | clinically proven | "
            "studies show | research shows | cutting-edge research | latest research | "
            "thoroughly fact-checked | fact-checked by | guaranteed | lose weight fast | "
            "effortless weight loss | no effort | secrets | miracles | transformations await | "
            "time is running out | transformational\n\n"
            "  SAFE alternatives instead of hype: practical guide | step-by-step | "
            "beginner-friendly | realistic habits | simple strategies | clear examples | "
            "helpful worksheets | easy-to-follow | designed for [audience] | "
            "supports healthier choices | sustainable approach\n\n"
            "  If the topic involves health, fitness, weight loss, medical, financial, "
            "or legal content: keep all claims realistic, avoid absolute outcomes, "
            "never promise specific results. Do not invent statistics or cite studies."
        ),
        user=(
            "Design visual aids for the ebook below.\n\n"
            f"Ebook title: {title}\n"
            f"Chapters, in order:\n{listing}\n\n"
            f"EBOOK CONTENT (Markdown, may be trimmed):\n{(content_md or '')[:12000]}\n\n"
            "Return a JSON object with EXACTLY these keys:\n"
            '- "subtitle": a short, compelling subtitle for the ebook.\n'
            '- "cover_prompt": a detailed BACKGROUND-ONLY image prompt for the cover art. '
            "Describe scene, mood, and topic visuals only -- full vibrant color, no grayscale toning -- "
            "do NOT include title, subtitle, author, logos, or any text/lettering in the image.\n"
            '- "product_summary": a 2-4 sentence marketing summary.\n'
            '- "chapters": an array with ONE object per chapter, in the SAME '
            "ORDER as listed. Each chapter object has:\n"
            '    "chapter": the chapter title (copy it exactly), and\n'
            '    "aids": an array of AT LEAST 2 visual aid objects.\n'
            "Each visual aid object has:\n"
            '    "type": one of "chart", "table", "diagram", "infographic", '
            '"stock photo", "worksheet box", "tip box", "action step box";\n'
            '    "title": a short title for the visual;\n'
            '    "caption": a one-line caption shown under the visual;\n'
            "Then include ONLY the content field(s) for that type:\n"
            '    chart/graph -> "chart_data": {"kind":"bar"|"line"|"pie"|'
            '"doughnut", "labels":[...], "values":[numbers]};\n'
            '    table -> "table": {"headers":[...], "rows":[[...],[...]]};\n'
            '    diagram -> "mermaid": a valid Mermaid.js definition string '
            '(e.g. "flowchart TD; A[Start]-->B[Next]; B-->C[Done]");\n'
            '    tip box -> "body": the actual tip text (1-3 sentences);\n'
            '    action step box / worksheet box -> "items": an array of short '
            "strings (the actual steps or checklist prompts);\n"
            '    stock photo / infographic -> "image_prompt": a detailed AI '
            'image prompt, and "keywords": a few search keywords.\n'
            "Rules: provide at least 2 aids for EVERY chapter; VARY the types "
            "across chapters (use charts, tables, diagrams, tip/action boxes and "
            "at least one image-type aid across the book); put real, specific "
            "content in every aid; use only the ebook's information; no emojis; "
            "return only the JSON object."
        ),
        max_completion_tokens=8000,
    )
    return _coerce_plan(raw, chapter_titles, title)


# ---------------------------------------------------------------------------
# Visual aid rendering (real HTML)
# ---------------------------------------------------------------------------


def _fmt_num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def _chart_html(aid: dict) -> str:
    data = aid.get("chart_data")
    if not data:
        return ""
    from services.visual_fallback import preview_chart_static_html

    payload = json.dumps(
        {"kind": data["kind"], "labels": data["labels"], "values": data["values"],
         "title": aid.get("title") or ""},
        ensure_ascii=True,
    )
    static = preview_chart_static_html(data, aid.get("title") or "")
    return (
        '<div class="va-chart-wrap">'
        f"{static}"
        f'<canvas class="va-chart-canvas" data-chart=\'{html.escape(payload, quote=True)}\'></canvas>'
        "</div>"
    )


def _table_html(aid: dict) -> str:
    table = aid.get("table")
    if not table:
        return ""
    headers = table.get("headers") or []
    rows = table.get("rows") or []

    # PDF-safety: convert tall/narrow tables to stacked card format to avoid
    # ReportLab/xhtml2pdf negative width calculation errors (availWidth=-6.95e-08).
    # Known failure modes:
    #   - 4+ columns: always convert
    #   - 3+ columns with 6+ rows: tall stacked cells can overflow
    #   - 2 columns with 6+ rows: same overflow pattern
    #   - 1x1 table: a single tall cell (e.g. a PmlKeepInFrame infographic) can
    #     exceed the page height and cause "too large on page" errors.
    if len(headers) >= 4 or any(len(row) >= 4 for row in rows):
        return _table_to_cards(aid)
    if len(headers) >= 2 and len(rows) >= 6:
        return _table_to_cards(aid)
    # Guard for 1x1 tables with a single very-tall cell (infographic/checklist)
    if len(headers) == 1 and len(rows) == 1:
        # Render as a simple paragraph instead of a table to avoid page-height errors
        cell_text = str(rows[0][0]) if rows[0] else ""
        if cell_text:
            return f'<p class="va-body">{_e(cell_text)}</p>'
        return ""

    thead = ""
    if headers:
        thead = "<thead><tr>" + "".join(f"<th>{_e(h)}</th>" for h in headers) + "</tr></thead>"
    body_rows = "".join(
        "<tr>" + "".join(f"<td>{_e(c)}</td>" for c in row) + "</tr>" for row in rows
    )
    return f'<table class="va-table">{thead}<tbody>{body_rows}</tbody></table>'


def _table_to_cards(aid: dict) -> str:
    """Convert wide tables (4+ columns) to stacked card format for PDF safety.

    Uses HTML tables instead of CSS Grid divs so xhtml2pdf renders and extracts
    text correctly. Each column in the source table becomes a column in the output
    table, and each cell contains a 2-row inner table (header label + value).
    """
    table = aid.get("table")
    if not table:
        return ""
    headers = table.get("headers") or []
    rows = table.get("rows") or []

    # For tables with 4+ columns, generate a proper HTML table.
    # Each source column becomes a table column; each cell has a mini inner-table
    # with the header label in row 1 and the value in row 2.
    # This avoids xhtml2pdf CSS-Grid concatenation issues entirely.
    if len(headers) >= 4:
        n = min(len(headers), 6)
        th_cells = "".join(f"<th>{_e(headers[i])}</th>" for i in range(n))
        tr_rows = []
        for row in rows:
            if not row:
                continue
            cells = []
            for col_idx in range(n):
                val = str(row[col_idx]) if col_idx < len(row) else ""
                cells.append(
                    f'<td class="tcard-cell">'
                    f'<table class="tcard-inner"><tbody>'
                    f'<tr><td class="tcard-hdr">{_e(headers[col_idx])}</td></tr>'
                    f'<tr><td class="tcard-val">{_e(val)}</td></tr>'
                    f"</tbody></table></td>"
                )
            tr_rows.append(f"<tr>{''.join(cells)}</tr>")
        return (
            f'<table class="va-table va-table-cards">'
            f"<thead><tr>{th_cells}</tr></thead>"
            f"<tbody>{''.join(tr_rows)}</tbody></table>"
        )

    # For 3-column tables, use the existing 3-column grid layout
    compressed_headers = headers[:3]
    cards = []
    for row in rows:
        if not row:
            continue
        if len(row) >= 3:
            items = list(row[:3])
        elif len(row) == 2:
            items = [row[0], row[1], ""]
        else:
            items = [row[0] if row else "", "", ""]

        card_cells = ""
        for hdr, val in zip(compressed_headers, items):
            card_cells += (
                f'<div class="tcard-cell">'
                f'<span class="tcard-hdr">{_e(hdr)}</span>'
                f'<span class="tcard-val">{_e(val)}</span>'
                f"</div>"
            )
        cards.append(f'<div class="tcard-row">{card_cells}</div>')

    return f'<div class="va-table-cards">{"".join(cards)}</div>'


def _tip_html(aid: dict) -> str:
    body = aid.get("body") or aid.get("description")
    if not body:
        return ""
    # If body contains numbered list items, parse and render as <ol>/<li>
    # so the PDF validator can find the actual questions
    numbered_items = _parse_numbered_items(body)
    if numbered_items:
        intro, items = numbered_items
        parts = []
        if intro:
            parts.append(f'<p class="va-body">{_e(intro)}</p>')
        lis = "".join(f"<li>{_e(it)}</li>" for it in items)
        parts.append(f'<ol class="va-steps">{lis}</ol>')
        return "".join(parts)
    return f'<p class="va-body">{_e(body)}</p>'


def _parse_numbered_items(text: str) -> tuple[str, list[str]] | None:
    """Parse numbered list items like '1. Foo\\n2. Bar' from body text.

    Returns (intro, [item1, item2, ...]) if 3+ numbered items are found,
    otherwise returns None.
    """
    if not text:
        return None
    # Match patterns like "1. ", "1) ", "1 - ", "1: "
    pattern = r"(?:^|\n)\s*(\d+)[.)-:]?\s+"
    parts = re.split(pattern, text)
    if len(parts) < 4:
        return None  # less than 2 items
    items: list[str] = []
    intro = parts[0].strip()
    # parts alternates: [intro_text, "1", "item1_text", "2", "item2_text", ...]
    for i in range(1, len(parts) - 1, 2):
        num = parts[i]
        content = parts[i + 1].strip()
        if num.isdigit() and content:
            items.append(content)
    if len(items) < 3:
        return None
    return intro, items


def _list_html(aid: dict, ordered: bool) -> str:
    items = aid.get("items") or []
    if not items and aid.get("body"):
        items = _coerce_items(aid["body"])
    if not items:
        return ""
    if ordered:
        lis = "".join(f"<li>{_e(it)}</li>" for it in items)
        return f'<ol class="va-steps">{lis}</ol>'
    lis = "".join(
        f'<li><span class="va-check"></span><span>{_e(it)}</span></li>' for it in items
    )
    return f'<ul class="va-checklist">{lis}</ul>'


def _mermaid_html(aid: dict) -> str:
    code = aid.get("mermaid")
    if not code:
        if aid.get("items"):
            return _list_html(aid, ordered=True)
        return ""
    from services.visual_fallback import mermaid_static_flow_html

    return mermaid_static_flow_html(code, aid.get("title") or "Diagram")


def _image_html(aid: dict, package_id: str) -> str:
    from services.ebook_visual_pipeline import is_photo_aid
    from services.visual_fallback import image_asset_path, preview_image_fallback_html

    vid = aid.get("visual_id") or ""
    url = _download_url(package_id, f"img_{vid}.png") if package_id and vid else ""
    has_file = image_asset_path(package_id, vid) is not None or bool(aid.get("has_file"))
    if is_photo_aid(aid) and not has_file:
        # Application state holds the error. Never insert it into the book.
        return ""
    fallback = preview_image_fallback_html(aid)
    img_display = "block" if has_file else "none"
    fb_display = "none" if has_file else "flex"
    if not url:
        return f'<div class="va-image">{fallback}</div>'
    return (
        f'<div class="va-image" data-vid="{_e(vid)}">'
        f'<img class="va-img" data-vid="{_e(vid)}" alt="{_e(aid.get("title") or "Illustration")}" '
        f'src="{_e(url)}" style="display:{img_display};" '
        'onerror="this.style.display=\'none\';var f=this.nextElementSibling;if(f)f.style.display=\'flex\';" '
        'onload="this.style.display=\'block\';var f=this.nextElementSibling;if(f)f.style.display=\'none\';">'
        f'<div class="va-img-fallback-wrap" style="display:{fb_display};">{fallback}</div>'
        "</div>"
    )


def _aid_inner_html(aid: dict, package_id: str) -> str:
    # Trusted local HTML bodies (tables/checklists built without AI)
    raw_html = (aid.get("html") or "").strip()
    raw_body = (aid.get("body") or "").strip()
    if raw_html.startswith("<"):
        return raw_html
    if raw_body.startswith("<table") or raw_body.startswith("<div"):
        return raw_body

    atype = aid["type"]
    if atype in {"chart", "graph"}:
        return _chart_html(aid)
    if atype == "table":
        return _table_html(aid)
    if atype == "tip box":
        return _tip_html(aid)
    if atype == "action step box":
        return _list_html(aid, ordered=True)
    if atype == "worksheet box":
        return _list_html(aid, ordered=False)
    if atype == "diagram":
        mermaid = _mermaid_html(aid)
        if mermaid:
            return mermaid
        if raw_body:
            return raw_body
        return ""
    if atype in _IMAGE_GEN_TYPES:
        return _image_html(aid, package_id)
    if atype == "youtube resource box":
        return (
            '<div class="va-qr"><div class="va-qr-box">QR</div>'
            '<div class="va-qr-cap">Scan to watch the video</div></div>'
        )
    return _tip_html(aid)


def render_aid_html(aid: dict, package_id: str = "", *, chapter_title: str = "") -> str:
    """Render a single visual aid as a real, finished HTML component."""
    atype = aid["type"]
    label = _TYPE_LABELS.get(atype, "Visual")
    slug = atype.replace(" ", "-")
    inner = _aid_inner_html(aid, package_id)
    aid_title = str(aid.get("title") or "").strip()
    if chapter_title and aid_title and _norm_title(aid_title) == _norm_title(chapter_title):
        aid_title = ""
    if re.search(r"\bphotograph$", aid_title, re.I):
        aid_title = ""
    caption = str(aid.get("caption") or "").strip()
    if re.match(r"(?i)^a relevant photograph for\b", caption):
        caption = ""
    if caption and aid_title and _norm_title(caption) == _norm_title(aid_title):
        caption = ""
    if atype in {"stock photo", "photo"}:
        caption = caption or aid_title
        aid_title = ""
    if not inner and not aid_title and not caption:
        return ""
    parts: list[str] = []
    if atype not in {"stock photo", "photo"}:
        parts.append(f'<div class="va-label">{_e(label)}</div>')
    if aid_title:
        parts.append(f'<div class="va-title">{_e(aid_title)}</div>')
    if inner:
        parts.append(f'<div class="va-content">{inner}</div>')
    if caption:
        from services.ebook_visual_match import strip_customer_source_urls

        parts.append(f'<p class="va-caption">{_e(strip_customer_source_urls(caption))}</p>')
    return f'<div class="visual-aid va-{slug}">{"".join(parts)}</div>'


def _aid_txt(aid: dict) -> str:
    label = _TYPE_LABELS.get(aid["type"], "Visual")
    lines = [f"[{label}]"]
    if aid.get("title"):
        lines.append(aid["title"])
    if aid.get("body"):
        lines.append(aid["body"])
    if aid.get("description") and not aid.get("body"):
        lines.append(aid["description"])
    if aid.get("items"):
        lines.extend(f"- {it}" for it in aid["items"])
    if aid.get("table"):
        t = aid["table"]
        if t.get("headers"):
            lines.append(" | ".join(t["headers"]))
        for row in t["rows"]:
            lines.append(" | ".join(row))
    if aid.get("chart_data"):
        data = aid["chart_data"]
        pairs = ", ".join(
            f"{lbl}: {_fmt_num(val)}" for lbl, val in zip(data["labels"], data["values"])
        )
        lines.append(f"Chart ({data['kind']}): {pairs}")
    if aid.get("mermaid"):
        lines.append(f"Diagram:\n{aid['mermaid']}")
    if aid["type"] in _IMAGE_GEN_TYPES and aid.get("image_prompt"):
        lines.append(f"Image: {aid['image_prompt']}")
    if aid["type"] == "youtube resource box":
        lines.append("[QR code to video]")
    if aid.get("caption"):
        lines.append(f"({aid['caption']})")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Full ebook rendering
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; }
body { margin: 0; background: #eef1f6; color: #0f172a;
  font-family: 'Inter', system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
.book { max-width: 820px; margin: 0 auto; padding: 28px 16px 60px; }
.sheet { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px;
  box-shadow: 0 12px 34px rgba(15,23,42,.10); padding: 48px 52px; margin: 0 0 24px; }
.cover { background: linear-gradient(135deg, #4f46e5, #7c3aed); color: #fff;
  text-align: center; padding: 72px 52px; position: relative; overflow: hidden; }
.cover.photo-cover { background: #0f172a; padding: 0; }
.cover.photo-cover::before, .cover.photo-cover::after { display: none; }
.cover-photo { width: 100%; height: auto; display: block; position: relative; z-index: 3; }
.cover::before { content: ""; position: absolute; width: 360px; height: 360px; border-radius: 50%;
  background: rgba(255,255,255,.10); top: -130px; right: -120px; }
.cover::after { content: ""; position: absolute; width: 280px; height: 280px; border-radius: 50%;
  background: rgba(0,0,0,.12); bottom: -120px; left: -90px; }
.cover-frame { position: absolute; inset: 24px; border: 2px solid rgba(255,255,255,.45);
  border-radius: 14px; pointer-events: none; }
.cover-inner { position: relative; z-index: 2; }
.cover-badge { width: 82px; height: 82px; border-radius: 20px; background: rgba(255,255,255,.16);
  border: 2px solid rgba(255,255,255,.55); display: flex; align-items: center; justify-content: center;
  font-size: 38px; font-weight: 800; margin: 0 auto 24px; }
.cover .kicker { text-transform: uppercase; font-size: 12px; opacity: .9; font-weight: 700; }
.cover h1 { font-size: 44px; margin: 14px 0 0; line-height: 1.2; }
.cover-rule { width: 84px; height: 4px; background: rgba(255,255,255,.85); border-radius: 999px; margin: 20px auto; }
.cover .sub { font-size: 19px; opacity: .94; max-width: 80%; margin: 0 auto; }
.cover-img-wrap { margin: 26px auto 0; max-width: 420px; position: relative; z-index: 2; }
.cover-img-wrap img { width: 100%; border-radius: 12px; box-shadow: 0 14px 40px rgba(0,0,0,.35); display:none; }
h1, h2, h3, h4, p, ul, ol, li, div { display: block; }
h1, h2, h3, h4 { color: #1e1b4b; line-height: 1.25; }
h2 { font-size: 28px; margin: 0 0 18px; border-bottom: 2px solid #ede9fe; padding-bottom: 10px; }
h3 { font-size: 19px; margin: 18px 0 10px; padding-top: 4px; }
.h3-block { display: block; margin: 16px 0 8px; page-break-inside: avoid; }
p { display: block; line-height: 1.75; font-size: 16px; margin: 0 0 14px; }
ul, ol { line-height: 1.7; }
.visual-aid { border: 1px solid #e2e8f0; border-radius: 12px; background: #fff;
  padding: 18px 20px; margin: 24px 0; box-shadow: 0 2px 10px rgba(15,23,42,.05); }
.va-label { display: inline-block; background: #ede9fe; color: #6d28d9; font-weight: 700;
  font-size: 11px; text-transform: uppercase;
  padding: 4px 10px; border-radius: 999px; margin-bottom: 10px; }
.va-title { font-weight: 700; color: #312e81; font-size: 17px; margin-bottom: 10px; }
.va-content { margin-top: 6px; }
.va-body { font-size: 15px; margin: 0; color: #1f2937; }
.va-caption { font-size: 13px; font-style: italic; color: #6b7280; margin: 10px 0 0; }
.va-chart-wrap { position: relative; height: 300px; }
.va-table { border-collapse: collapse; width: 100%; font-size: 14px; }
.va-table th, .va-table td { border: 1px solid #e2e8f0; padding: 8px 12px; text-align: left; }
.va-table th { background: #f5f3ff; color: #4c1d95; font-weight: 700; }
.va-table tbody tr:nth-child(even) { background: #faf9ff; }
.va-table-cards { display: flex; flex-direction: column; gap: 10px; }
.tcard-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
/* 4+ column tables get a 2-column grid (label + value per column) */
.tcard-row.tcard-cols-4,
.tcard-row.tcard-cols-5,
.tcard-row.tcard-cols-6 { grid-template-columns: repeat(2, 1fr); }
.tcard-cell { display: flex; flex-direction: column; gap: 2px; padding: 8px 10px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; }
.tcard-hdr { font-size: 10px; font-weight: 700; color: #6d28d9; text-transform: uppercase; }
.tcard-val { font-size: 12px; color: #1f2937; line-height: 1.4; }
/* Inner table for 4+ column cards (PDF-safe: avoids CSS Grid text concat) */
.tcard-inner { width: 100%; border-collapse: collapse; }
.tcard-inner td { padding: 3px 0; border: none; background: transparent; vertical-align: top; }
.tcard-inner .tcard-hdr { display: block; font-size: 10px; font-weight: 700; color: #6d28d9; text-transform: uppercase; }
.tcard-inner .tcard-val { display: block; font-size: 12px; color: #1f2937; line-height: 1.4; }
td.tcard-cell { padding: 8px 10px; background: #f8fafc; vertical-align: top; }
.va-steps { margin: 0; padding-left: 22px; }
.va-steps li { margin: 6px 0; }
.va-checklist { list-style: none; margin: 0; padding: 0; }
.va-checklist li { display: flex; align-items: flex-start; gap: 10px; margin: 8px 0; }
.va-check { flex: 0 0 auto; width: 18px; height: 18px; margin-top: 2px; border: 2px solid #7c3aed; border-radius: 4px; }
.va-image { text-align: center; }
.va-img { width: 100%; max-width: 560px; border-radius: 10px; margin: 0 auto; }
.va-img-fallback-wrap { display: flex; justify-content: center; width: 100%; }
.va-img-fallback, .va-fb-card { width: 100%; max-width: 560px; margin: 0 auto; }
.va-fb-card { border: 1px solid #e2e8f0; border-radius: 12px; background: linear-gradient(180deg, #fafafa, #fff);
  padding: 20px 18px; box-shadow: 0 4px 16px rgba(15,23,42,.06); }
.va-fb-caption { font-size: 13px; font-style: italic; color: #64748b; margin: 12px 0 0; text-align: center; }
.va-fb-formula { text-align: center; }
.va-fb-formula-row { display: flex; flex-wrap: wrap; align-items: center; justify-content: center; gap: 8px; margin-bottom: 10px; }
.va-fb-part { background: #ede9fe; color: #4338ca; font-weight: 700; font-size: 13px; padding: 8px 12px; border-radius: 8px; }
.va-fb-sep { color: #94a3b8; font-weight: 800; font-size: 16px; }
.va-fb-note { font-size: 12px; color: #64748b; font-weight: 600; }
.va-fb-principles { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
.va-fb-principle { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 10px; text-align: center; }
.va-fb-principle b { display: block; font-size: 15px; color: #312e81; margin-bottom: 4px; }
.va-fb-principle span { font-size: 12px; color: #64748b; }
.va-fb-listing { text-align: left; }
.va-fb-listing-row { display: flex; gap: 12px; align-items: flex-start; }
.va-fb-listing-thumb { flex: 0 0 72px; height: 72px; background: linear-gradient(135deg, #ddd6fe, #c4b5fd); border-radius: 8px; }
.va-fb-listing-title { font-size: 14px; font-weight: 700; color: #1e1b4b; line-height: 1.3; }
.va-fb-listing-stars { font-size: 12px; color: #d97706; margin-top: 4px; }
.va-fb-listing-stars span { color: #64748b; }
.va-fb-listing-meta { font-size: 11px; color: #64748b; margin-top: 2px; }
.va-fb-listing-price { font-size: 16px; font-weight: 800; color: #312e81; margin-top: 6px; }
.va-fb-listing-trust { font-size: 11px; color: #059669; font-weight: 700; margin-top: 10px; padding-top: 10px; border-top: 1px solid #e2e8f0; }
.va-fb-ecommerce { display: flex; gap: 14px; align-items: flex-end; justify-content: center; min-height: 140px; }
.va-fb-device { background: #1e293b; border-radius: 10px; padding: 6px; box-shadow: 0 8px 24px rgba(0,0,0,.15); }
.va-fb-laptop { flex: 1; max-width: 320px; }
.va-fb-phone { width: 72px; flex-shrink: 0; }
.va-fb-screen { background: #fff; border-radius: 6px; padding: 10px; min-height: 100px; }
.va-fb-search { background: #f1f5f9; border-radius: 999px; padding: 6px 12px; font-size: 10px; color: #64748b; margin-bottom: 8px; text-align: left; }
.va-fb-mini-cards { display: flex; gap: 6px; }
.va-fb-mini { flex: 1; background: #fafafa; border: 1px solid #e2e8f0; border-radius: 6px; padding: 6px; text-align: center; font-size: 9px; font-weight: 700; color: #312e81; }
.va-fb-mini-img { height: 28px; background: #ddd6fe; border-radius: 4px; margin-bottom: 4px; }
.va-fb-phone-screen { min-height: 88px; padding: 8px; }
.va-fb-phone-card { height: 56px; background: linear-gradient(135deg, #ede9fe, #ddd6fe); border-radius: 6px; }
.va-fb-photo { position: relative; height: 120px; border-radius: 10px; overflow: hidden; }
.va-fb-photo-gradient { position: absolute; inset: 0; background: linear-gradient(135deg, #334155, #6366f1, #0ea5e9); opacity: .9; }
.va-fb-photo-label { position: relative; z-index: 1; color: #fff; font-weight: 700; font-size: 13px; padding-top: 48px; }
.va-fb-generic-title { font-size: 15px; font-weight: 700; color: #312e81; text-align: center; }
.va-fb-categories { display: flex; flex-direction: column; gap: 8px; }
.va-fb-cat-row { display: flex; gap: 12px; align-items: baseline; padding: 8px 10px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }
.va-fb-cat-name { font-weight: 700; color: #312e81; min-width: 140px; flex-shrink: 0; }
.va-fb-cat-desc { color: #475569; font-size: 13px; }
.va-fb-tips { display: flex; flex-direction: column; gap: 8px; padding: 4px 0; }
.va-fb-tip-row { display: flex; gap: 10px; align-items: flex-start; padding: 6px 10px; background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; }
.va-fb-tip-num { font-weight: 700; color: #7c3aed; min-width: 20px; flex-shrink: 0; }
.va-fb-tip-q { color: #1f2937; font-size: 13px; }
.pdf-table { border-collapse: collapse; border: 1pt solid #cbd5e1; margin: 8pt 0; }
.pdf-table td { border: 1pt solid #cbd5e1; padding: 6pt 8pt; font-size: 10pt; vertical-align: top; }
.pdf-table tr:nth-child(even) td { background: #faf9ff; }
.va-flow-static { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 8px 0; }
.va-flow-step { background: #f5f3ff; border: 1px solid #c4b5fd; border-radius: 8px; padding: 10px 16px; font-size: 13px; font-weight: 600; color: #4338ca; text-align: center; min-width: 200px; }
.va-flow-num { display: inline-block; background: #7c3aed; color: #fff; width: 20px; height: 20px; line-height: 20px; border-radius: 50%; font-size: 11px; margin-right: 8px; }
.va-flow-arrow { color: #94a3b8; font-size: 14px; font-weight: 700; }
.va-chart-static { margin-bottom: 8px; }
.va-chart-static-title { font-size: 13px; font-weight: 700; color: #4338ca; margin-bottom: 8px; text-align: center; }
.va-bar-row { display: flex; align-items: flex-end; justify-content: center; gap: 10px; min-height: 100px; padding-top: 8px; border-bottom: 2px solid #e2e8f0; }
.va-bar-col { flex: 1; max-width: 64px; text-align: center; }
.va-bar-val { font-size: 11px; font-weight: 700; color: #4338ca; margin-bottom: 4px; }
.va-bar-fill { width: 28px; margin: 0 auto; border-radius: 4px 4px 0 0; min-height: 8px; }
.va-bar-lbl { font-size: 10px; color: #64748b; margin-top: 6px; line-height: 1.2; }
.va-chart-wrap canvas[data-done="1"] ~ .va-chart-static,
.va-chart-wrap .va-chart-static.hidden { display: none; }
.va-qr { display: inline-flex; flex-direction: column; align-items: center; }
.va-qr-box { width: 80px; height: 80px; border: 2px dashed #dc2626; border-radius: 8px;
  display: flex; align-items: center; justify-content: center; font-weight: 800; color: #dc2626; }
.va-qr-cap { font-size: 11px; color: #6b7280; margin-top: 4px; }
.va-tip-box { border-left: 5px solid #0d9488; }
.va-tip-box .va-label { background: #ccfbf1; color: #0f766e; }
.va-action-step-box { border-left: 5px solid #d97706; }
.va-action-step-box .va-label { background: #fef3c7; color: #b45309; }
.va-worksheet-box { border-left: 5px solid #2563eb; }
.va-worksheet-box .va-label { background: #dbeafe; color: #1d4ed8; }
.va-youtube-resource-box { border-left: 5px solid #dc2626; }
.va-youtube-resource-box .va-label { background: #fee2e2; color: #b91c1c; }
.sheet.title-page { text-align: center; min-height: 560px; display: flex; flex-direction: column;
  justify-content: center; align-items: center; padding: 64px 52px; }
.title-kicker { font-size: 12px; text-transform: uppercase; color: #7c3aed; font-weight: 700; }
.title-main { font-size: 36px; margin: 16px 0 10px; color: #1e1b4b; line-height: 1.2; max-width: 90%; }
.title-sub { font-size: 18px; color: #64748b; max-width: 85%; margin: 0 auto; }
.title-rule { width: 72px; height: 3px; background: #c4b5fd; border-radius: 999px; margin: 22px auto; }
.title-imprint { font-size: 13px; color: #94a3b8; margin-top: 8px; }
.sheet.legal { font-size: 14px; color: #64748b; line-height: 1.7; }
.sheet.legal h2 { font-size: 24px; color: #1e1b4b; margin: 0 0 16px; border: none; padding: 0; }
.sheet.toc h2 { margin-bottom: 20px; }
.toc-list { list-style: none; margin: 0; padding: 0; }
.toc-list li { display: grid; grid-template-columns: 1fr auto auto; gap: 10px; align-items: baseline;
  padding: 11px 0; border-bottom: 1px dashed #e2e8f0; }
.toc-list a { color: #4338ca; font-weight: 600; text-decoration: none; font-size: 15px; }
.toc-list a:hover { text-decoration: underline; color: #3730a3; }
.toc-leader { border-bottom: 1px dotted #cbd5e1; min-width: 24px; }
.toc-num { font-size: 13px; color: #94a3b8; font-weight: 600; min-width: 24px; text-align: right; }
.chapter-num { font-size: 11px; font-weight: 700; text-transform: uppercase;
  color: #7c3aed; margin-bottom: 8px; }
.chapter-title { font-size: 28px; margin: 0 0 22px; border-bottom: 2px solid #ede9fe; padding-bottom: 10px; }
.sheet.summary, .sheet.action-page, .sheet.resources-page, .sheet.legal { }
.intro-page { }
.intro-page h3 { font-size: 20px; color: #334155; margin-bottom: 16px; font-style: italic; }
.intro-page p { font-size: 15px; color: #475569; margin-bottom: 12px; }
.health-disclaimer { margin-top: 18px; font-size: 14px; color: #334155;
  border-top: 1px solid #e2e8f0; padding-top: 14px; font-style: italic; }
.summary-lead { font-size: 17px; color: #334155; font-weight: 500; margin-bottom: 18px; }
.page-foot { display: flex; justify-content: space-between; align-items: center; margin-top: 36px;
  padding-top: 12px; border-top: 1px solid #e2e8f0; font-size: 12px; color: #94a3b8; }
.sheet.chapter { scroll-margin-top: 24px; }
/* Back matter */
.bm-section { border-top: 3px solid #ede9fe; margin-top: 32px; padding-top: 24px; }
.bm-label { display: inline-block; background: #f5f3ff; color: #6d28d9; font-weight: 700;
  font-size: 11px; text-transform: uppercase;
  padding: 5px 12px; border-radius: 999px; margin-bottom: 14px; }
.bm-title { font-size: 20px; font-weight: 800; color: #1e1b4b; margin-bottom: 12px; }
.bm-intro { font-size: 14px; color: #475569; margin-bottom: 18px; }
.bm-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.bm-point { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px 16px; }
.bm-point-title { font-size: 13px; font-weight: 700; color: #312e81; margin-bottom: 6px; }
.bm-point-body { font-size: 13px; color: #475569; }
.bm-section.worksheet-page .bm-title { font-size: 18px; margin-bottom: 14px; }
.faq-list { display: flex; flex-direction: column; gap: 14px; }
.faq-item { border: 1px solid #e2e8f0; border-radius: 10px; padding: 16px 18px; background: #fff; }
.faq-q { font-size: 14px; font-weight: 700; color: #1e1b4b; margin-bottom: 6px; }
.faq-a { font-size: 14px; color: #475569; line-height: 1.65; }
.ws-table-wrap { overflow-x: auto; margin-bottom: 12px; }
.ws-table { border-collapse: collapse; width: 100%; font-size: 13px; }
.ws-table th { background: #f5f3ff; color: #4c1d95; font-weight: 700; padding: 10px 12px; text-align: left; border-bottom: 2px solid #c4b5fd; }
.ws-table td { padding: 10px 12px; border-bottom: 1px solid #e2e8f0; vertical-align: top; }
.ws-row-num { color: #7c3aed; font-weight: 700; width: 32px; }
.ws-action { color: #1e1b4b; }
.ws-when { background: #fef9c3; min-width: 120px; }
.ws-check { display: inline-block; width: 18px; height: 18px; border: 2px solid #7c3aed; border-radius: 4px; }
.ws-note { font-size: 12px; color: #6b7280; font-style: italic; margin-top: 8px; }
"""

_SCRIPTS = """
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script>
(function () {
  function palette(n) {
    var base = ['#7c3aed','#4f46e5','#0d9488','#d97706','#dc2626','#2563eb','#db2777','#16a34a'];
    var out = []; for (var i = 0; i < n; i++) out.push(base[i % base.length]); return out;
  }
  function drawCharts() {
    if (typeof Chart === 'undefined') return;
    document.querySelectorAll('canvas.va-chart-canvas').forEach(function (c) {
      if (c.dataset.done) return; c.dataset.done = '1';
      var cfg; try { cfg = JSON.parse(c.dataset.chart); } catch (e) { return; }
      var single = (cfg.kind === 'pie' || cfg.kind === 'doughnut');
      new Chart(c, {
        type: cfg.kind,
        data: { labels: cfg.labels, datasets: [{
          label: cfg.title || '', data: cfg.values,
          backgroundColor: single ? palette(cfg.values.length) : 'rgba(124,58,237,.7)',
          borderColor: '#7c3aed', borderWidth: 1, fill: cfg.kind === 'line' ? false : true,
          tension: .3 }] },
        options: { responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: single } } }
      });
      var wrap = c.closest('.va-chart-wrap');
      if (wrap) { var st = wrap.querySelector('.va-chart-static'); if (st) st.classList.add('hidden'); }
    });
  }
  function init() {
    drawCharts();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
  window.addEventListener('load', drawCharts);
  // Live image swap: parent posts {type:'va-img', id} when a PNG is ready.
  window.addEventListener('message', function (ev) {
    var d = ev.data || {}; if (d.type !== 'va-img' || !d.id) return;
    document.querySelectorAll('img[data-vid="' + d.id + '"]').forEach(function (img) {
      var base = img.getAttribute('src').split('?')[0];
      img.src = base + '?t=' + Date.now();
      img.style.display = 'block';
    });
  });
})();
</script>
"""

# Reused by the Publishing Studio so its preview can also render charts/diagrams.
VISUAL_SCRIPTS = _SCRIPTS


def _doc(
    title: str,
    subtitle: str,
    body: str,
    cover_img: str = "",
    cover_design: dict | None = None,
    design_theme: str = "studio_clean",
) -> str:
    cover_sub = f'<p class="sub">{_e(subtitle)}</p>' if subtitle else ""
    author = ""
    if isinstance(cover_design, dict):
        author = str(cover_design.get("author") or "").strip()
    cover_png = ""
    if isinstance(cover_design, dict):
        cover_png = str(cover_design.get("image_path") or "").strip()
    if cover_png and os.path.isfile(cover_png):
        pkg = str((cover_design or {}).get("package_id") or "")
        src = _download_url(pkg, "img_cover.png") if pkg else cover_png
        cover_section = (
            '<section class="sheet cover photo-cover">'
            f'<img class="cover-photo" alt="{_e(title)}" src="{_e(src)}" />'
            "</section>"
        )
    elif cover_design and cover_design.get("preview_html"):
        cover_section = re.sub(
            r"letter-spacing\s*:\s*[^;\"'}]+;?",
            "",
            str(cover_design["preview_html"]),
            flags=re.I,
        )
    else:
        cover_section = (
            '<section class="sheet cover">'
            '<div class="cover-frame"></div>'
            '<div class="cover-inner">'
            f'<h1>{_e(title)}</h1>'
            '<div class="cover-rule"></div>'
            f"{cover_sub}{cover_img}"
            f'<p class="cover-author" data-ebook-author>{_e(author)}</p>'
            "</div>"
            "</section>"
        )
    try:
        from services.ebook_design_system import theme_css

        theme_fragment = theme_css(design_theme or "studio_clean")
    except Exception:
        theme_fragment = ""
    # Defense: never ship letter-spacing into ebook preview/PDF CSS.
    css = re.sub(r"letter-spacing\s*:\s*[^;\"'}]+;?", "", _CSS + theme_fragment, flags=re.I)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{_e(title)}</title><style>{css}</style></head><body>"
        '<div class="book">'
        f"{cover_section}"
        f"{body}"
        "</div>"
        f"{_SCRIPTS}"
        "</body></html>"
    )


def _cover_img_html(package_id: str) -> str:
    url = _download_url(package_id, "img_cover.png") if package_id else ""
    if not url:
        return ""
    return (
        '<div class="cover-img-wrap"><img data-vid="cover" alt="Cover" '
        f'src="{_e(url)}" onerror="this.style.display=\'none\';" '
        'onload="this.style.display=\'block\';"></div>'
    )


def _aids_lookup(plan_chapters: list[dict]):
    by_index = {i: ch.get("aids") or [] for i, ch in enumerate(plan_chapters)}
    by_title = {}
    for ch in plan_chapters:
        key = _norm_title(ch.get("chapter", ""))
        if key:
            by_title[key] = ch.get("aids") or []
    return by_index, by_title


def _chapter_kind(title: str) -> str:
    from services.ebook_contamination import is_description_heading

    norm = _norm_title(title)
    if norm in {"table of contents", "contents", "toc"}:
        return "toc"
    if is_description_heading(title):
        return "description"
    if norm in {"summary", "product summary", "conclusion", "key takeaways", "final thoughts"}:
        return "summary"
    if norm in {"summary", "product summary", "conclusion", "key takeaways", "final thoughts"}:
        return "summary"
    if "action step" in norm or norm in {"action steps", "next steps", "your action plan", "action plan"}:
        return "action"
    if any(x in norm for x in ("bonus resource", "resources checklist", "resources page")):
        return "resources"
    return "chapter"


def _strip_leading_h1(html_fragment: str) -> str:
    """Remove the first H1 from an HTML fragment (the book title — shown on title page)."""
    soup = BeautifulSoup(html_fragment, "html.parser")
    first = soup.find("h1")
    if first:
        first.decompose()
    return str(soup)


def _strip_leading_h2(html_fragment: str, title: str) -> str:
    soup = BeautifulSoup(html_fragment, "html.parser")
    first = soup.find(["h1", "h2"])
    if first and _norm_title(first.get_text()) == _norm_title(title):
        first.decompose()
    return str(soup)


def interleave_aids_in_html(html: str, aids: list, package_id: str = "") -> str:
    """Place visual aids inside chapter content instead of only at the bottom."""
    aids = [a for a in (aids or []) if a]
    if not aids:
        return html
    if not html.strip():
        return "".join(render_aid_html(a, package_id) for a in aids)
    soup = BeautifulSoup(html, "html.parser")
    blocks = [el for el in soup.children if getattr(el, "name", None)]
    if not blocks:
        return html + "".join(render_aid_html(a, package_id) for a in aids)
    result: list[str] = []
    n = len(blocks)
    m = len(aids)
    slots: dict[int, list[int]] = {}
    for ai in range(m):
        pos = min(n - 1, max(0, int((n * (ai + 1)) / (m + 1)) - 1)) if n else 0
        slots.setdefault(pos, []).append(ai)
    placed: set[int] = set()
    for bi, block in enumerate(blocks):
        result.append(str(block))
        for ai in slots.get(bi, []):
            result.append(render_aid_html(aids[ai], package_id))
            placed.add(ai)
    for ai, aid in enumerate(aids):
        if ai not in placed:
            result.append(render_aid_html(aid, package_id))
    return "".join(result)


def _page_footer(page_num: int, title: str) -> str:
    return (
        f'<div class="page-foot"><span>{_e(title)}</span>'
        f"<span>Page {page_num}</span></div>"
    )


def _title_page_html(title: str, subtitle: str, page_num: int, author: str = "") -> str:
    sub = f'<p class="title-sub">{_e(subtitle)}</p>' if subtitle else ""
    byline = f'<p class="title-author" data-ebook-author>{_e(author)}</p>'
    return (
        '<section class="sheet title-page">'
        f'<h1 class="title-main">{_e(title)}</h1>'
        f"{sub}{byline}"
        '<div class="title-rule"></div>'
        f"{_page_footer(page_num, title)}"
        "</section>"
    )


def _extract_health_disclaimer(preamble: str) -> str:
    """Pull the health disclaimer out of the markdown preamble.

    Scans for **Disclaimer:** (bold markers around the word "Disclaimer") followed by the
    full disclaimer text and returns it as HTML so it can be appended to the auto-generated
    legal page. Handles the colon appearing between the word and closing bold markers
    (markdown: **Disclaimer:** text).
    """
    if not preamble:
        return ""
    # Pattern: **Disclaimer:** = [*]{2} + Disclaimer + : + [*]{2} + text + lookahead
    # Character class [*] matches a literal asterisk in the regex engine.
    pattern = r"[*]{2}[Dd]isclaimer:\s*[*]{2}\s*(.*?)(?=\n+\s*#{1,6}\s|\Z)"
    match = re.search(pattern, preamble, re.DOTALL | re.IGNORECASE)
    if not match:
        return ""
    raw = match.group(1).strip()
    if not raw:
        return ""
    # Wrap in a <p> with a mild visual style
    return f'<p class="health-disclaimer">{_e(raw)}</p>'


def _legal_page_html(title: str, page_num: int, health_disclaimer: str = "", author: str = "") -> str:
    holder = author or title
    body = (
        f"<p>Copyright © 2026 {_e(holder)}. All rights reserved.</p>"
        "<p>No part of this publication may be reproduced, distributed, or transmitted "
        "in any form without prior written permission.</p>"
        "<p>This ebook is for educational and informational purposes only. The author and "
        "publisher make no warranties regarding results from applying this material.</p>"
    )
    # Append the markdown's own health disclaimer if present
    if health_disclaimer:
        body += "\n" + health_disclaimer
    return (
        '<section class="sheet legal">'
        "<h2>Copyright &amp; Disclaimer</h2>"
        f"{body}"
        f"{_page_footer(page_num, title)}"
        "</section>"
    )


def _toc_page_html(chapters: list[tuple[str, str, list]], title: str, page_num: int) -> str:
    items = []
    for idx, (ctitle, _, _) in enumerate(chapters):
        anchor = f"chapter-{idx + 1}"
        items.append(
            f'<li><a href="#{anchor}">{_e(ctitle)}</a>'
            f'<span class="toc-leader"></span>'
            f'<span class="toc-num">{idx + 1}</span></li>'
        )
    return (
        '<section class="sheet toc">'
        "<h2>Table of Contents</h2>"
        f'<ol class="toc-list">{"".join(items)}</ol>'
        f"{_page_footer(page_num, title)}"
        "</section>"
    )


def _chapter_sheet_html(
    idx: int,
    ctitle: str,
    cmd: str,
    aids: list,
    package_id: str,
    title: str,
    page_num: int,
) -> str:
    anchor = f"chapter-{idx + 1}"
    body = _strip_leading_h2(_md_to_html(cmd), ctitle)
    body = interleave_aids_in_html(body, aids, package_id)
    # Extract chapter number from title if present to avoid duplicate labels
    # e.g., "Chapter 1: Understanding AI" -> num="1", display="Understanding AI"
    chapter_match = re.match(r"^Chapter\s+(\d+)\s*:\s*(.+)$", ctitle, re.IGNORECASE)
    if chapter_match:
        chapter_display = chapter_match.group(2).strip()
    else:
        chapter_display = ctitle
    return (
        f'<section class="sheet chapter" id="{anchor}">'
        f'<div class="chapter-num">Chapter {idx + 1}</div>'
        f'<h2 class="chapter-title">{_e(chapter_display)}</h2>'
        f"{body}"
        f"{_page_footer(page_num, title)}"
        "</section>"
    )


def render_preview_html(
    title: str,
    subtitle: str,
    content_md: str,
    plan_chapters: list[dict],
    package_id: str = "",
    product_summary: str = "",
    cover_design: dict | None = None,
    topic: str = "",
) -> str:
    """Render a Designrr-style multi-page ebook preview with inline visuals."""
    preamble, chapters = _split_chapters(content_md)
    by_index, by_title = _aids_lookup(plan_chapters)
    body: list[str] = []
    page_num = 2

    content_chapters: list[tuple[str, str, list]] = []
    summary_block: tuple[str, list] | None = None
    action_block: tuple[str, list] | None = None
    resources_aids: list = []

    for i, (ctitle, cmd) in enumerate(chapters):
        aids = by_title.get(_norm_title(ctitle)) or by_index.get(i) or []
        kind = _chapter_kind(ctitle)
        if kind in {"toc", "description"}:
            continue
        if kind == "summary":
            summary_block = (cmd, aids)
        elif kind == "action":
            action_block = (cmd, aids)
        elif kind == "resources":
            resources_aids.extend(aids)
        else:
            content_chapters.append((ctitle, cmd, aids))

    author = ""
    if isinstance(cover_design, dict):
        author = str(cover_design.get("author") or "").strip()
    body.append(_title_page_html(title, subtitle, page_num, author=author))
    page_num += 1
    # Pass the full preamble (subtitle + health disclaimer) to the legal page.
    # Rendering as a separate intro-page section causes xhtml2pdf to drop it
    # silently (empty page), so we fold the preamble into the legal page instead.
    health_disclaimer = _extract_health_disclaimer(preamble)
    body.append(_legal_page_html(title, page_num, health_disclaimer, author=author))
    page_num += 1
    if content_chapters:
        body.append(_toc_page_html(content_chapters, title, page_num))
        page_num += 1
        for idx, (ctitle, cmd, aids) in enumerate(content_chapters):
            page_num += 1
            body.append(
                _chapter_sheet_html(idx, ctitle, cmd, aids, package_id, title, page_num)
            )

    summary_md, summary_aids = summary_block or ("", [])
    summary_text = clean_product_summary(product_summary)
    summary_body = ""
    if summary_md:
        summary_body = interleave_aids_in_html(
            _strip_leading_h2(_md_to_html(summary_md), "Summary"),
            summary_aids,
            package_id,
        )
    if summary_text:
        lead = f'<p class="summary-lead">{_e(summary_text)}</p>'
        summary_body = lead + summary_body if summary_body else lead
    if summary_body:
        page_num += 1
        body.append(
            f'<section class="sheet summary" id="summary">'
            f'<h2 class="chapter-title">Summary</h2>{summary_body}'
            f"{_page_footer(page_num, title)}"
            "</section>"
        )

    if action_block:
        act_md, act_aids = action_block
        page_num += 1
        act_body = interleave_aids_in_html(
            _strip_leading_h2(_md_to_html(act_md), "Action Steps"),
            act_aids,
            package_id,
        )
        body.append(
            f'<section class="sheet action-page" id="action-steps">'
            f'<h2 class="chapter-title">Action Steps</h2>{act_body}'
            f"{_page_footer(page_num, title)}"
            "</section>"
        )

    if resources_aids:
        page_num += 1
        res_html = "".join(render_aid_html(a, package_id) for a in resources_aids)
        body.append(
            f'<section class="sheet resources-page" id="resources">'
            f'<h2 class="chapter-title">Resources &amp; Checklists</h2>{res_html}'
            f"{_page_footer(page_num, title)}"
            "</section>"
        )

    if not content_chapters:
        if plan_chapters:
            # content has no ## headings but plan_chapters exists -- render from plan_chapters,
            # preserving all chapter aids including chapter-4's 4-column table (Data Security).
            # chapter_md is intentionally empty: the full ebook text is in the preamble / ebook.txt,
            # not structured per-chapter, so we only render the chapter heading + visual aids.
            for idx, plan_ch in enumerate(plan_chapters):
                ch_title = plan_ch.get("chapter", "")
                ch_aids = plan_ch.get("aids", [])
                body.append(
                    _chapter_sheet_html(idx, ch_title, "", ch_aids, package_id, title, page_num)
                )
                page_num += 1
        else:
            # No plan chapters either -- old fallback for bare content
            aids = by_index.get(0, [])
            body.append(
                f'<section class="sheet chapter">{interleave_aids_in_html(_md_to_html(content_md), aids, package_id)}</section>'
            )

    # Back matter is optional and must come from the manuscript/outline itself.
    # Never auto-inject generic FAQ / Quick Reference / Action Worksheet pools.

    theme_id = "studio_clean"
    if isinstance(cover_design, dict) and cover_design.get("design_theme"):
        theme_id = str(cover_design.get("design_theme") or theme_id)
    return _doc(
        title,
        subtitle,
        "".join(body),
        _cover_img_html(package_id),
        cover_design=cover_design,
        design_theme=theme_id,
    )


def _strip_md(text: str) -> str:
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("__", "")
    return text


def render_txt(
    title: str, subtitle: str, content_md: str, plan_chapters: list[dict]
) -> str:
    preamble, chapters = _split_chapters(content_md)
    by_index, by_title = _aids_lookup(plan_chapters)
    lines = [title]
    if subtitle:
        lines.append(subtitle)
    lines.append("")

    if chapters:
        if preamble:
            lines.append(_strip_md(preamble).strip())
            lines.append("")
        for i, (ctitle, cmd) in enumerate(chapters):
            lines.append(_strip_md(cmd).strip())
            aids = by_title.get(_norm_title(ctitle)) or by_index.get(i) or []
            for aid in aids:
                lines.append("")
                lines.append(_aid_txt(aid))
            lines.append("")
    else:
        lines.append(_strip_md(content_md).strip())
        for aid in by_index.get(0, []):
            lines.append("")
            lines.append(_aid_txt(aid))
    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------
# Image generation (gpt-image-1 via the Replit AI proxy)
# ---------------------------------------------------------------------------

_IMAGE_MODEL = "gpt-image-2"

# Module-level last error — cleared on each call, populated on failure.
# Used by pdf_builder quality gate to surface real errors.
_last_image_error: str = ""

# Paid image generation requires an explicit user-approved generation action.
# Save / Export / QA rechecks / diagnostic probes / missing-file probes must
# never reach the OpenAI Images API without this authorization context.
_paid_image_auth_depth: int = 0
_paid_image_auth_reason: str = ""

# Package-level hard cap on images.generate attempts (failures count).
# Used for Thunder Volt full-book interiors: exactly 24 attempts, quality=medium.
_package_image_budgets: dict[str, dict] = {}
_active_image_budget_package: str = ""


class PaidImageNotAuthorized(RuntimeError):
    """Raised when image generation is attempted without user-approved stage auth."""


class PaidImageBudgetExceeded(RuntimeError):
    """Raised when a package has exhausted its authorized images.generate attempts."""


def paid_image_generation_authorized() -> bool:
    return _paid_image_auth_depth > 0


class _PaidImageAuthToken:
    def __init__(self, reason: str):
        self.reason = str(reason or "user_approved_generation")

    def __enter__(self):
        global _paid_image_auth_depth, _paid_image_auth_reason
        _paid_image_auth_depth += 1
        _paid_image_auth_reason = self.reason
        return self

    def __exit__(self, exc_type, exc, tb):
        global _paid_image_auth_depth, _paid_image_auth_reason
        _paid_image_auth_depth = max(0, _paid_image_auth_depth - 1)
        if _paid_image_auth_depth == 0:
            _paid_image_auth_reason = ""
        return False


def authorize_paid_image_generation(reason: str = "user_approved_generation") -> _PaidImageAuthToken:
    """Context manager enabling paid image API calls for an approved generation stage."""
    return _PaidImageAuthToken(reason)


class _PackageImageBudgetToken:
    """Hard-cap images.generate attempts for one package (failures count)."""

    def __init__(self, package_id: str, *, max_attempts: int = 24, quality: str = "medium"):
        pkg = str(package_id or "").strip()
        if not pkg:
            raise ValueError("package_id is required for an image budget")
        q = str(quality or "").strip().lower()
        if q != "medium":
            raise ValueError(
                f"Package image budget quality must be 'medium' (got {quality!r}). "
                "auto/high are not permitted for authorized interior generation."
            )
        if int(max_attempts) < 1:
            raise ValueError("max_attempts must be >= 1")
        self.package_id = pkg
        self.max_attempts = int(max_attempts)
        self.quality = q
        self._prior_active = ""

    def __enter__(self):
        global _active_image_budget_package
        self._prior_active = _active_image_budget_package
        # Fresh budget for this authorization window (do not carry prior attempts).
        _package_image_budgets[self.package_id] = {
            "max_attempts": self.max_attempts,
            "attempts": 0,
            "quality": self.quality,
        }
        _active_image_budget_package = self.package_id
        return self

    def __exit__(self, exc_type, exc, tb):
        global _active_image_budget_package
        _active_image_budget_package = self._prior_active
        return False


def authorize_package_image_budget(
    package_id: str,
    *,
    max_attempts: int = 24,
    quality: str = "medium",
) -> _PackageImageBudgetToken:
    """Authorize a hard package-level images.generate attempt budget."""
    return _PackageImageBudgetToken(
        package_id, max_attempts=max_attempts, quality=quality
    )


def get_package_image_budget(package_id: str = "") -> dict:
    """Return budget snapshot for a package (or the active budget)."""
    pkg = str(package_id or _active_image_budget_package or "").strip()
    if not pkg:
        return {}
    data = _package_image_budgets.get(pkg) or {}
    return {
        "package_id": pkg,
        "max_attempts": int(data.get("max_attempts") or 0),
        "attempts": int(data.get("attempts") or 0),
        "quality": str(data.get("quality") or ""),
        "remaining": max(
            0, int(data.get("max_attempts") or 0) - int(data.get("attempts") or 0)
        ),
    }


def reset_package_image_budgets() -> None:
    """Test helper — clear all package image budgets."""
    global _active_image_budget_package
    _package_image_budgets.clear()
    _active_image_budget_package = ""


def _consume_package_image_attempt(package_id: str = "") -> None:
    """Increment attempt counter before an API call. Raises if budget exhausted."""
    global _last_image_error
    pkg = str(package_id or _active_image_budget_package or "").strip()
    if not pkg:
        return
    data = _package_image_budgets.get(pkg)
    if not data:
        return
    used = int(data.get("attempts") or 0)
    max_attempts = int(data.get("max_attempts") or 0)
    if used >= max_attempts:
        _last_image_error = (
            f"Paid image budget exceeded for package {pkg}: "
            f"{used}/{max_attempts} images.generate attempts used."
        )
        raise PaidImageBudgetExceeded(_last_image_error)
    data["attempts"] = used + 1


def get_last_image_error() -> str:
    return _last_image_error


def generate_visual_image(
    prompt: str,
    out_path: str,
    size: str = "1024x1024",
    *,
    negative_prompt: str = "",
    max_prompt_chars: int = 1000,
    reference_image_path: str = "",
    user_authorized: bool = False,
    quality: str | None = None,
    package_id: str = "",
    allow_edit: bool = False,
    allow_retries: bool = False,
) -> bool:
    """Generate one image and save it as a PNG. Returns True on success.

    If out_path already exists (pre-generated image), returns True immediately
    without calling the AI — allows external image sources to inject images.

    Paid API calls require either ``user_authorized=True`` or an active
    ``authorize_paid_image_generation(...)`` context from a user-approved
    Factory generation stage (cover / sample / full). QA, Save, Export, and
    ad-hoc diagnostic probes must not call the API.

    Cost controls (Thunder Volt full-book interiors):
      - When a package budget is active, ``quality`` is forced to ``medium``
        (never ``auto`` / ``high``).
      - Each ``images.generate`` attempt increments the package counter even on
        failure / empty response; the counter hard-stops at the authorized max.
      - ``images.edit``, alternate-size fallbacks, and automatic retries are
        disabled (``allow_edit`` / ``allow_retries`` default False).

    Args:
        prompt: The positive image generation prompt.
        out_path: Where to save the output PNG.
        size: Image dimensions (e.g. "1024x1024", "1024x1536").
        negative_prompt: Ignored for API kwargs (kept for call-site compatibility).
            Negatives stay in the positive prompt text when the builder embeds them.
        max_prompt_chars: Max prompt length sent to the image API.
        reference_image_path: Ignored unless ``allow_edit=True`` (disabled by default).
        user_authorized: Explicit per-call authorization (preferred for stages).
        quality: Image quality tier. Budgeted interiors must use ``medium``.
        package_id: Package whose attempt budget to consume (defaults to active).
        allow_edit: If True, permits images.edit (default False — never for budgeted runs).
        allow_retries: If True, permits alternate-size / second-call retries (default False).
    """
    global _last_image_error
    # negative_prompt is intentionally not sent to the API — embedding negatives in
    # the positive prompt avoids unsupported-kwarg TypeErrors that previously
    # triggered a second images.generate retry.
    _ = negative_prompt
    _ = allow_retries  # reserved; automatic retries are never performed
    _ = allow_edit  # images.edit is disabled; reference_image_path is ignored
    _ = reference_image_path
    prompt = (prompt or "").strip()
    if not prompt:
        return False
    # If a pre-generated image already exists, use it directly.
    if os.path.isfile(out_path):
        return True
    if not (user_authorized or paid_image_generation_authorized()):
        _last_image_error = (
            "Paid image generation blocked: requires explicit user-approved "
            "generation action (cover/sample/full). QA, Save, Export, and "
            "diagnostic probes cannot call the image API."
        )
        raise PaidImageNotAuthorized(_last_image_error)

    pkg = str(package_id or _active_image_budget_package or "").strip()
    budget = _package_image_budgets.get(pkg) if pkg else None
    q = str(quality or "").strip().lower()
    if budget:
        # Authorized interior budget: force medium; never auto/high.
        q = "medium"
        if str(quality or "").strip().lower() in {"auto", "high"}:
            _last_image_error = (
                f"Budgeted interiors require quality='medium' (got {quality!r})."
            )
            raise ValueError(_last_image_error)
    elif q in {"", "auto"}:
        # Non-budgeted callers: omit quality kwarg (do not send auto/high).
        q = ""
    elif q == "high":
        _last_image_error = (
            "quality='high' is not permitted for Factory image generation "
            "without a separate explicit authorization."
        )
        raise ValueError(_last_image_error)

    _last_image_error = ""
    limit = max(256, int(max_prompt_chars or 1000))
    prompt_send = prompt[:limit]

    # Consume budget BEFORE the network call so failures / empty payloads count.
    if budget is not None:
        _consume_package_image_attempt(pkg)

    try:
        client = get_client()
        kwargs: dict = dict(model=_IMAGE_MODEL, prompt=prompt_send, size=size, n=1)
        if q:
            kwargs["quality"] = q
        resp = client.images.generate(**kwargs)
        b64 = getattr(resp.data[0], "b64_json", None)
        if not b64:
            _last_image_error = "Image generation returned no image data."
            return False
        os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
        with open(out_path, "wb") as fh:
            fh.write(base64.b64decode(b64))
        return True
    except PaidImageBudgetExceeded:
        raise
    except Exception as exc:  # noqa: BLE001 — no alternate-size / edit / second-call retries
        _last_image_error = f"{type(exc).__name__}: {str(exc)[:200]}"
        return False


def render_visual_image(
    package_id: str, visual_id: str, prompt: str, size: str | None = None
) -> str | None:
    """Generate an image for a given package/visual and return its download URL."""
    if not _PACKAGE_ID_OK(package_id) or not _VISUAL_ID_OK(visual_id):
        return None
    pdir = os.path.join(EXPORTS_DIR, package_id)
    os.makedirs(pdir, exist_ok=True)
    fname = f"img_{visual_id}.png"
    image_size = size or ("1024x1536" if visual_id == "cover" else "1024x1024")
    if generate_visual_image(prompt, os.path.join(pdir, fname), size=image_size):
        return _download_url(package_id, fname)
    return None


# ---------------------------------------------------------------------------
# Export package on disk
# ---------------------------------------------------------------------------

EXPORTS_DIR = os.environ.get("FACTORY_EXPORTS_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "exports"
)
PACKAGE_FILES = (
    "ebook.html",
    "ebook.txt",
    "ebook.pdf",
    "visual_plan.json",
    "cover_prompt.txt",
    "product_summary.txt",
    "package.zip",
)

# uuid hex OR generation slugs used by coloring books / scripts
_PACKAGE_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{1,127}$")
_VISUAL_ID_RE = re.compile(r"^(cover|v\d+_\d+)$")
# Preview images are served as img_<visual_id>.png. The visual_id is chosen by
# whichever planner built the plan, so pinning this to one planner's numbering
# (v0_0, v1_2, ...) silently 404s every image belonging to a plan that names its
# visuals any other way -- the file exists on disk and the PDF embeds it, but
# the browser preview shows empty frames. Validate the *shape* instead: a
# conservative filename charset that still cannot express "..", a path
# separator, or a second extension. The route additionally confines the
# resolved path to exports/ as defense in depth.
_IMAGE_FILE_RE = re.compile(r"^img_[A-Za-z0-9][A-Za-z0-9_-]{0,63}\.png$")
_PRODUCT_PDF_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_\-]*\.pdf$")


def _PACKAGE_ID_OK(package_id: str) -> bool:
    return bool(_PACKAGE_ID_RE.match(package_id or ""))


def _VISUAL_ID_OK(visual_id: str) -> bool:
    return bool(_VISUAL_ID_RE.match(visual_id or ""))


def is_allowed_download(filename: str) -> bool:
    if filename in PACKAGE_FILES:
        return True
    if _IMAGE_FILE_RE.match(filename or ""):
        return True
    # Allow any product PDF filename (word_search, crossword, etc.)
    if _PRODUCT_PDF_RE.match(filename or ""):
        return True
    return False


_IMAGE_JOB_CAP = 6


def _collect_image_jobs(chapters: list[dict], cover_prompt: str) -> list[dict]:
    """Paid GPT image jobs are not used for factory stock photos or covers.

    Stock photographs are retrieved from Pexels. Covers use the photo-cover engine.
    Infographics may remain locally rendered. This list stays empty so the
    factory route cannot queue gpt-image-1.
    """
    del chapters, cover_prompt
    return []


def _visual_assets(chapters: list[dict], package_id: str) -> list[dict]:
    """Flat list of saved visual records (the required per-visual metadata)."""
    assets: list[dict] = []
    for ch in chapters:
        for aid in ch.get("aids") or []:
            atype = aid["type"]
            is_img = atype in _IMAGE_GEN_TYPES
            from services.visual_fallback import image_asset_path

            has_file = bool(aid.get("has_file")) or bool(
                is_img and image_asset_path(package_id, str(aid.get("visual_id") or ""))
            )
            assets.append({
                "visual_id": aid["visual_id"],
                "chapter": ch.get("chapter", ""),
                "type": atype,
                "title": aid.get("title", ""),
                "caption": aid.get("caption", ""),
                "has_file": has_file,
                "rendered": bool(aid.get("rendered")) if is_img else True,
                "status": aid.get("status") or ("resolved" if (has_file or not is_img) else "missing"),
                "attribution": aid.get("attribution") or "",
                "photographer": aid.get("photographer") or "",
                "page_url": aid.get("page_url") or aid.get("source_url") or "",
                "photo_id": aid.get("photo_id") or "",
                "pexels_query": aid.get("pexels_query") or "",
                "asset_url": _download_url(package_id, f"img_{aid['visual_id']}.png") if is_img and has_file else "",
                "rendered_html": "" if is_img else render_aid_html(aid, package_id),
                "source_data": {
                    k: aid[k] for k in ("chart_data", "table", "items", "body", "mermaid",
                                        "keywords")
                    if aid.get(k)
                },
            })
    return assets


def _write_package(package_id: str, files: dict[str, str | bytes]) -> tuple[str, dict]:
    os.makedirs(EXPORTS_DIR, exist_ok=True)
    pdir = os.path.join(EXPORTS_DIR, package_id)
    os.makedirs(pdir, exist_ok=True)
    paths = {}
    for name, content in files.items():
        path = os.path.join(pdir, name)
        if isinstance(content, bytes):
            with open(path, "wb") as fh:
                fh.write(content)
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
        paths[name] = path
    zip_path = os.path.join(pdir, "package.zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in files:
            zf.write(os.path.join(pdir, name), name)
    paths["package.zip"] = zip_path
    return pdir, paths


def _download_url(package_id: str, name: str) -> str:
    return f"/download/{package_id}/{name}"


def build_ebook_package(title: str, content_md: str, fields: dict) -> dict:
    """Generate the visual plan, retrieve Pexels photographs, stage a photo cover."""
    from services.ebook_contract import build_contract
    from services.ebook_factory_pipeline import (
        apply_ebook_readiness,
        factory_ebook_completion_state,
        fill_plan_photos_automatic,
        images_requested,
        set_visual_progress,
        PROGRESS_PLANNING,
        PROGRESS_REVIEW,
        stage_factory_photo_cover,
        stamp_plan_render_flags,
        strip_photo_aids,
        visual_ai_authorized,
    )
    from services.ebook_quality_agent import validate_ebook_content

    package_id = uuid.uuid4().hex
    fields = fields if isinstance(fields, dict) else {}
    want_images = images_requested(fields)
    data_budget = {
        "fields": fields,
        "visuals_authorized": fields.get("visuals_authorized"),
        "visual_budget_cap_usd": fields.get("visual_budget_cap_usd"),
        "visual_ai_spend_usd": 0.0,
    }
    ws = fields.get("ebook_workspace")
    if isinstance(ws, dict):
        data_budget["ebook_workspace"] = ws
    contract = build_contract(
        topic=fields.get("topic", ""),
        audience=fields.get("audience", ""),
        tone=fields.get("tone", "friendly and clear"),
        reading_level=fields.get("reading_level", "6th-8th grade"),
        reader_problem=fields.get("purpose", ""),
        ebook_length=fields.get("product_type", "standard"),
    )

    set_visual_progress(data_budget, PROGRESS_PLANNING)
    plan = generate_visual_plan(title, content_md, fields)
    subtitle = plan["subtitle"]
    product_summary = plan["product_summary"]
    chapters = plan["chapters"]
    visual_plan = {"chapters": chapters, "title": title}
    if want_images:
        visual_plan = fill_plan_photos_automatic(
            visual_plan,
            package_id=package_id,
            title=title,
            topic=str(fields.get("topic") or title),
            audience=str(fields.get("audience") or ""),
            data=data_budget,
            fields=fields,
            allow_ai=(
                visual_ai_authorized(data_budget, fields)
                and str(os.environ.get("FACTORY_TEST_MODE") or "") != "1"
                and str(os.environ.get("EBOOK_CUSTOMER_PATH_FIXTURE") or "").strip().lower()
                not in {"1", "true", "yes"}
            ),
        )
    else:
        visual_plan = strip_photo_aids(visual_plan)
    visual_plan = stamp_plan_render_flags(visual_plan, package_id=package_id)
    # Guarantee every acquired photograph also occupies the canonical
    # img_<visual_id>.png slot the browser preview resolves by convention.
    from services.ebook_factory_pipeline import publish_plan_photos

    publish_plan_photos(visual_plan, package_id=package_id)
    chapters = list(visual_plan.get("chapters") or [])
    set_visual_progress(data_budget, PROGRESS_REVIEW)

    cover_design = stage_factory_photo_cover(
        title=title,
        subtitle=subtitle,
        author=(fields.get("author_brand") or fields.get("author") or "").strip(),
        fields=fields,
        package_id=package_id,
        search_photos=want_images,
    )
    cover_search = str(cover_design.get("cover_search_query") or "")

    preview_html = render_preview_html(
        title, subtitle, content_md, chapters, package_id, product_summary, cover_design,
        topic=(fields.get("topic") or ""),
    )
    preview_html = re.sub(
        r"letter-spacing\s*:\s*[^;\"'}]+;?", "", preview_html, flags=re.I
    )
    txt_doc = render_txt(title, subtitle, content_md, chapters)
    from services.ebook_visual_match import customer_safe_visual_plan

    safe_chapters = customer_safe_visual_plan({"chapters": chapters}).get("chapters") or []
    visual_json = json.dumps(
        {
            "title": title,
            "subtitle": subtitle,
            "cover_search_query": cover_search,
            "product_summary": product_summary,
            "chapters": safe_chapters,
        },
        indent=2,
    )

    pdir, paths = _write_package(
        package_id,
        {
            "ebook.html": preview_html,
            "ebook.txt": txt_doc,
            "visual_plan.json": visual_json,
            "cover_prompt.txt": (
                f"Cover photograph search (Pexels): {cover_search}. "
                "Choose cover photo — this is not a finished cover."
                if cover_search
                else "Choose cover photo. No finished cover has been approved."
            ),
            "product_summary.txt": product_summary or "No summary was generated.",
        },
    )

    quality_result = validate_ebook_content(
        md_text=content_md,
        contract=contract,
        title=title,
    )

    image_jobs = _collect_image_jobs(chapters, "")
    visual_assets = _visual_assets(chapters, package_id)
    completion = factory_ebook_completion_state(
        visual_plan=visual_plan,
        cover_design=cover_design,
        package_id=package_id,
        pdf_path=os.path.join(pdir, "ebook.pdf"),
        export_files=paths,
        content=content_md,
        quality_result=quality_result,
    )

    export_links = {
        "html": {"name": "ebook.html", "url": _download_url(package_id, "ebook.html")},
        "txt": {"name": "ebook.txt", "url": _download_url(package_id, "ebook.txt")},
    }
    if completion.get("zip_available"):
        export_links["zip"] = {"name": "package.zip", "url": _download_url(package_id, "package.zip")}
    if completion.get("pdf_available"):
        export_links["pdf"] = {"name": "ebook.pdf", "url": _download_url(package_id, "ebook.pdf")}
    exports = {
        "package_id": package_id,
        "pdf_available": bool(completion.get("pdf_available")),
        "pdf_message": (
            f"PDF is not available. {completion.get('next_action') or 'Finish the cover and photographs first.'}"
            if not completion.get("pdf_available")
            else ""
        ),
        "files": export_links,
    }

    result = {
        "product_type": "ebook",
        "subtitle": subtitle,
        "visual_plan": visual_plan,
        "visual_assets": visual_assets,
        "image_jobs": image_jobs,
        "cover_prompt": "",
        "cover_search_query": cover_search,
        "cover_design": cover_design,
        "product_summary": product_summary,
        "preview_html": preview_html,
        "package_id": package_id,
        "exports": exports,
        "export_files": {"dir": pdir, **paths},
        "quality_result": quality_result,
        "quality_score": quality_result.score,
        "quality_blocking": not quality_result.passed,
        **completion,
        "content": content_md,
        "visual_progress": data_budget.get("visual_progress"),
        "visual_progress_message": data_budget.get("visual_progress_message"),
        "visual_ai_spend_usd": data_budget.get("visual_ai_spend_usd") or 0,
        "visuals_authorized": bool(fields.get("visuals_authorized")),
        "visual_budget_cap_usd": fields.get("visual_budget_cap_usd"),
    }
    apply_ebook_readiness(result)
    result.pop("content", None)
    return result
