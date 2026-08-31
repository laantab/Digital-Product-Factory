"""Render an approved manuscript into designed book HTML without rewriting text.

Structured markdown (tables, lists, callouts) is wrapped as design components.
Disclaimer and Sources are unnumbered back matter, never chapters.
"""
from __future__ import annotations

import html
import re
from typing import Any

import markdown as _markdown
from bs4 import BeautifulSoup

from services.ebook_design_spec import EbookDesign, is_unnumbered_back_matter_title
from services.ebook_design_system import LAYOUT_GUARDS, theme_css
from services.ebook_package import _split_chapters, _sanitize_html, fix_inline_hyphen_lists_html, _MD_TOC_LINE_RE

# Visual/todo tokens: [photo], [photo: cat], [insert image] — not [photographylaunchpad.com].
_PLACEHOLDER_RE = re.compile(
    r"\[(?:insert|image|photo|visual|todo|placeholder)(?![a-z0-9])[^\]]*\]|\bTODO\b|\blorem ipsum\b",
    re.I,
)
# Bracketed website/domain tokens treated as unresolved URL placeholders.
_URL_PLACEHOLDER_RE = re.compile(
    r"\[(?:https?://)?(?:www\.)?[a-z0-9][a-z0-9.-]*\.[a-z]{2,}(?:/[^\]]*)?\]",
    re.I,
)
_CONSECUTIVE_NEXTPAGE_RE = re.compile(r"(?:<pdf:nextpage\s*/>\s*){2,}", re.I)
_LAST_BLOCK_TAGS = ("p", "ul", "ol", "table", "div", "blockquote")
_BRACKETED_WEBSITE_SENTENCE_REWRITES = (
    (
        re.compile(
            r"Research summarized by sources such as \[startcosts\.com\]\([^)]*\) and "
            r"\[photographylaunchpad\.com\]\([^)]*\) points to two common starting lanes:",
            re.I,
        ),
        "Research summarized by independent photography-startup cost guides such as startcosts.com and photographylaunchpad.com points to two common starting lanes:",
        "Research summarized by sources such as [startcosts.com](https://startcosts.com) and [photographylaunchpad.com](https://photographylaunchpad.com) points to two common starting lanes:",
    ),
    (
        re.compile(
            r"Research cited by \[photographylaunchpad\.com\]\([^)]*\) and \[startcosts\.com\]\([^)]*\) "
            r"shows wide pricing variation, which is exactly why guesswork is risky\.",
            re.I,
        ),
        "Independent photography-startup cost research from startcosts.com and photographylaunchpad.com shows wide pricing variation, which is exactly why guesswork is risky.",
        "Research cited by [photographylaunchpad.com](https://photographylaunchpad.com) and [startcosts.com](https://startcosts.com) shows wide pricing variation, which is exactly why guesswork is risky.",
    ),
)
_DISCLAIMER_SPLIT = re.compile(
    r"(?:^|\n)(?:##\s+)?\*{0,2}Disclaimer\b\*{0,2}\s*",
    re.I,
)
_SOURCES_SPLIT = re.compile(
    r"(?:^|\n)(?:##\s+)?\*{0,2}Sources\b\*{0,2}\s*",
    re.I,
)


def _e(value: Any) -> str:
    return html.escape(str(value or ""))


def peel_back_matter(manuscript_md: str) -> tuple[str, str, str]:
    """Return (body_md, disclaimer_md, sources_md) without inventing copy."""
    text = str(manuscript_md or "")
    disclaimer = ""
    sources = ""
    src_match = _SOURCES_SPLIT.search(text)
    if src_match:
        sources = text[src_match.end() :].strip()
        text = text[: src_match.start()].rstrip()
    disc_match = _DISCLAIMER_SPLIT.search(text)
    if disc_match:
        disclaimer = text[disc_match.end() :].strip()
        text = text[: disc_match.start()].rstrip()
    return text, disclaimer, sources


def numbered_chapters(manuscript_md: str) -> list[tuple[str, str]]:
    body, _disc, _src = peel_back_matter(manuscript_md)
    _preamble, chapters = _split_chapters(body)
    out: list[tuple[str, str]] = []
    for title, md in chapters:
        if is_unnumbered_back_matter_title(title):
            continue
        out.append((title, md))
    return out


def _md_fragment(text: str) -> str:
    rendered = _markdown.markdown(str(text or ""), extensions=["extra", "sane_lists", "tables"])
    return fix_inline_hyphen_lists_html(_sanitize_html(rendered))


def _strip_leading_heading(fragment: str, title: str) -> str:
    soup = BeautifulSoup(fragment, "html.parser")
    first = soup.find(["h1", "h2", "h3"])
    if first and first.get_text(" ", strip=True).lower() == (title or "").strip().lower():
        first.decompose()
    return str(soup)


def _promote_numbered_paragraphs(soup: BeautifulSoup) -> None:
    for p in list(soup.find_all("p")):
        text = p.get_text("\n", strip=False)
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        numbered = [ln for ln in lines if re.match(r"^\d+\.\s+", ln)]
        if len(numbered) < 3:
            continue
        intro = [ln for ln in lines if not re.match(r"^\d+\.\s+", ln)]
        wrapper = soup.new_tag("div")
        if intro:
            lead = soup.new_tag("p")
            lead.string = " ".join(intro)
            wrapper.append(lead)
        ol = soup.new_tag("ol")
        ol["class"] = ["workflow"]
        for ln in numbered:
            li = soup.new_tag("li")
            li.string = re.sub(r"^\d+\.\s+", "", ln)
            ol.append(li)
        wrapper.append(ol)
        p.replace_with(wrapper)


_CHECKBOX_PREFIX_RE = re.compile(r"^\s*\[\s*[xX ]?\s*\]\s*")
_CHECKBOX_SPLIT_RE = re.compile(r"(?=\[\s*[xX ]?\s*\])")
_EMBEDDED_HEADING_RE = re.compile(
    r"^((?:Checklist:\s+)?[A-Z][^.!?\n]{8,80}?[a-z])([A-Z].+)$"
)
_HEADING_LINE_RE = re.compile(
    r"^(?:checklist\s*:|how |what |legal |a practical |from inquiry ).{8,80}$",
    re.I,
)
_LAYOUT_TABLE_CLASSES = {
    "toc-list",
    "toc-table",
    "chapter-opener",
    "checklist",
    "ebook-list",
    "heading-keep",
}


def _strip_checkbox_prefix_node(li) -> None:
    for node in li.find_all(string=True):
        text = str(node)
        cleaned = _CHECKBOX_PREFIX_RE.sub("", text, count=1)
        if cleaned != text:
            node.replace_with(cleaned)
            return


def _split_checkbox_paragraphs(soup: BeautifulSoup) -> None:
    """Turn run-on '[ ] item [ ] item' paragraphs into real checklist rows."""
    for p in list(soup.find_all("p")):
        raw = p.get_text("\n", strip=False)
        if "[ ]" not in raw and not re.search(r"\[\s*[xX]\s*\]", raw):
            continue
        chunks = [c.strip() for c in _CHECKBOX_SPLIT_RE.split(raw) if c and c.strip()]
        items = [c for c in chunks if _CHECKBOX_PREFIX_RE.match(c)]
        intro = [c for c in chunks if not _CHECKBOX_PREFIX_RE.match(c)]
        if len(items) < 2 and not (len(items) == 1 and intro):
            if len(items) == 1 and not intro:
                ul = soup.new_tag("ul")
                ul["class"] = ["checklist"]
                li = soup.new_tag("li")
                li.string = _CHECKBOX_PREFIX_RE.sub("", items[0]).strip()
                ul.append(li)
                p.replace_with(ul)
            continue
        wrapper = soup.new_tag("div")
        if intro:
            lead = soup.new_tag("p")
            lead.string = " ".join(intro).strip()
            wrapper.append(lead)
        ul = soup.new_tag("ul")
        ul["class"] = ["checklist"]
        for item in items:
            li = soup.new_tag("li")
            li.string = _CHECKBOX_PREFIX_RE.sub("", item).strip()
            ul.append(li)
        wrapper.append(ul)
        p.replace_with(wrapper)


def _promote_section_headings(soup: BeautifulSoup) -> None:
    """Lift heading-like lines out of body paragraphs without rewriting copy."""
    for p in list(soup.find_all("p")):
        text = p.get_text(" ", strip=True)
        if not text:
            continue
        embedded = _EMBEDDED_HEADING_RE.match(text)
        if embedded and len(embedded.group(1).split()) <= 12:
            heading = soup.new_tag("h3")
            heading["class"] = ["section-heading"]
            heading.string = embedded.group(1).strip()
            body = soup.new_tag("p")
            body.string = embedded.group(2).strip()
            p.insert_before(heading)
            p.replace_with(body)
            continue
        only_strong = False
        strong = p.find("strong")
        if strong and p.get_text(" ", strip=True) == strong.get_text(" ", strip=True):
            only_strong = True
        heading_like = (
            only_strong
            or bool(_HEADING_LINE_RE.match(text))
            or text.lower().startswith("checklist:")
        )
        if heading_like and len(text) <= 90 and not text.endswith((".", "!", "?")):
            p.name = "h3"
            classes = p.get("class") or []
            if isinstance(classes, str):
                classes = [classes]
            if "section-heading" not in classes:
                classes.append("section-heading")
            p["class"] = classes


def _normalize_checklist_items(soup: BeautifulSoup) -> None:
    for ul in soup.find_all("ul"):
        items = ul.find_all("li", recursive=False)
        if not items:
            continue
        checkboxy = sum(
            1
            for li in items
            if _CHECKBOX_PREFIX_RE.match(li.get_text(" ", strip=True))
        )
        classes = ul.get("class") or []
        if isinstance(classes, str):
            classes = [classes]
        if checkboxy >= 1 or "checklist" in classes:
            if "checklist" not in classes:
                classes.append("checklist")
            ul["class"] = classes
            for li in items:
                _strip_checkbox_prefix_node(li)


def _keep_headings_with_next(soup: BeautifulSoup) -> None:
    for heading in list(soup.find_all(["h2", "h3", "h4"])):
        parent_classes = heading.parent.get("class") if heading.parent else []
        if "heading-keep" in (parent_classes or []):
            continue
        nxt = heading.find_next_sibling()
        if nxt is None or getattr(nxt, "name", None) not in ("p", "ul", "ol"):
            continue
        wrap = soup.new_tag("div")
        wrap["class"] = ["heading-keep"]
        heading.insert_before(wrap)
        wrap.append(heading.extract())
        wrap.append(nxt.extract())


_HEADER_SLASH_SPLIT_RE = re.compile(r"\s+/\s+")
_KNOWN_HEADER_ROWS = (
    (
        "Event niche",
        "Typical client need",
        "Guest interaction level",
        "Planning complexity",
        "Sales opportunity for on-site prints",
        "Main beginner caution",
    ),
    (
        "Startup lane",
        "Typical planning range",
        "What it usually includes",
        "Legal/insurance priority",
        "Launch risk if skipped",
    ),
    (
        "Kit level",
        "Camera bodies",
        "Lenses",
        "Lighting",
        "Computing/editing",
        "Printing equipment",
        "Best use",
    ),
    (
        "Package",
        "Coverage and deliverables",
        "Price charged",
        "Planning + labor cost stack",
        "Estimated remaining amount",
    ),
    ("Stage", "When", "What to confirm", "Why it matters"),
    (
        "Printer",
        "Documented print focus",
        "Documented sizes/examples",
        "Documented speed/examples",
        "Documented media capacity/examples",
        "Best-fit event use",
    ),
)


def _compact_header_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def _split_concatenated_header_row(soup: BeautifulSoup, tr) -> None:
    cells = tr.find_all(["th", "td"])
    if not cells:
        return
    joined = _compact_header_text("".join(c.get_text(" ", strip=True) for c in cells))
    if len(cells) == 1:
        parts = [p.strip() for p in _HEADER_SLASH_SPLIT_RE.split(cells[0].get_text(" ", strip=True)) if p.strip()]
        if len(parts) >= 3:
            tr.clear()
            for part in parts:
                th = soup.new_tag("th")
                th.string = part
                tr.append(th)
            return
    for labels in _KNOWN_HEADER_ROWS:
        jammed = _compact_header_text("".join(labels))
        if joined == jammed or (len(cells) == 1 and jammed and jammed in joined):
            if len(cells) == len(labels):
                return
            tr.clear()
            for part in labels:
                th = soup.new_tag("th")
                th.string = part
                tr.append(th)
            return


def extract_ebook_table_model(table) -> dict[str, list] | None:
    """Canonical table model: ordered headers plus rows of equal length."""
    rows = table.find_all("tr")
    if not rows:
        return None
    headers = [c.get_text(" ", strip=True) for c in rows[0].find_all(["th", "td"])]
    if not headers:
        return None
    body: list[list[str]] = []
    for tr in rows[1:]:
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        if not any(cells):
            continue
        if len(cells) < len(headers):
            cells = cells + [""] * (len(headers) - len(cells))
        body.append(cells[: len(headers)])
    return {"headers": headers, "rows": body}


def portrait_table_is_readable(headers: list[str], rows: list[list[str]] | None = None) -> bool:
    """Keep grid tables only when every column stays at or above the design minimum."""
    n = len(headers or [])
    if n <= 3:
        return True
    if n >= 5:
        return False
    content_pt = (8.5 - 2 * float(LAYOUT_GUARDS["safe_margins_in"])) * 72.0
    col_pt = content_pt / n
    min_pt = float(LAYOUT_GUARDS["min_font_pt"])
    if col_pt < 72:
        return False
    samples = [str(h or "") for h in headers]
    for row in rows or []:
        samples.extend(str(c or "") for c in row)
    longest = max((len(s) for s in samples), default=0)
    needed = longest * min_pt * 0.5 + 16
    return needed <= col_pt


def _render_comparison_cards(
    soup: BeautifulSoup,
    headers: list[str],
    rows: list[list[str]],
    *,
    extra_class: str | None = None,
):
    """One stacked card per body row; each original header is its own <th>."""
    wrap = soup.new_tag("div")
    classes = ["ebook-comparison"]
    if extra_class:
        classes.append(extra_class)
    wrap["class"] = classes
    wrap["data-fields"] = str(len(headers))
    for row in rows:
        card = soup.new_tag("table")
        card["class"] = ["ebook-card"]
        card["width"] = "100%"
        card["cellpadding"] = "4"
        card["cellspacing"] = "0"
        for i, label in enumerate(headers):
            value = row[i] if i < len(row) else ""
            tr = soup.new_tag("tr")
            th = soup.new_tag("th")
            th["class"] = ["ebook-card-label"]
            th.string = f"{label}:"
            td = soup.new_tag("td")
            td["class"] = ["ebook-card-value"]
            td.string = value
            tr.append(th)
            tr.append(td)
            card.append(tr)
        wrap.append(card)
    return wrap


def _style_readable_table(soup: BeautifulSoup, table, headers: list[str]) -> None:
    col_count = len(headers)
    classes = table.get("class") or []
    if isinstance(classes, str):
        classes = [classes]
    existing = table.find("colgroup")
    if existing:
        existing.decompose()
    table["width"] = "100%"
    table["cellpadding"] = "8"
    table["cellspacing"] = "0"
    pct = f"{max(1.0, 100.0 / col_count):.4f}%"
    colgroup = soup.new_tag("colgroup")
    for _ in range(col_count):
        col = soup.new_tag("col")
        col["width"] = pct
        col["style"] = f"width:{pct}"
        colgroup.append(col)
    table.insert(0, colgroup)
    header_row = table.find("tr")
    if header_row is not None:
        for cell, label in zip(header_row.find_all(["th", "td"]), headers):
            cell.name = "th"
            cell.clear()
            cell.string = label
            cell["width"] = pct
            cell["valign"] = "top"
    for cell in table.find_all("td"):
        cell["width"] = pct
        cell["valign"] = "top"
    if "ebook-table" not in classes:
        classes.append("ebook-table")
    table["class"] = classes


def _prepare_ebook_tables(soup: BeautifulSoup) -> None:
    for table in list(soup.find_all("table")):
        classes = table.get("class") or []
        if isinstance(classes, str):
            classes = [classes]
        if "ebook-card" in classes or "ebook-comparison" in classes:
            continue
        if _LAYOUT_TABLE_CLASSES.intersection(classes):
            continue
        if "chapter-last-keep" in classes or "chapter-last-block" in classes:
            table.unwrap()
            continue
        if not table.get_text(" ", strip=True):
            table.decompose()
            continue
        first_tr = table.find("tr")
        if first_tr is not None:
            _split_concatenated_header_row(soup, first_tr)
        model = extract_ebook_table_model(table)
        if not model or not model["headers"] or not model["rows"]:
            table.decompose()
            continue
        headers = model["headers"]
        extra = None
        is_timeline = [h.strip() for h in headers] == ["Stage", "When", "What to confirm", "Why it matters"]
        if is_timeline:
            extra = "ebook-timeline"
        rows_for_fit = model["rows"] if is_timeline else None
        if not portrait_table_is_readable(headers, rows_for_fit):
            table.replace_with(
                _render_comparison_cards(soup, headers, model["rows"], extra_class=extra)
            )
            continue
        _style_readable_table(soup, table, headers)


def _ensure_table_headers(soup: BeautifulSoup) -> None:
    for table in soup.find_all("table"):
        if table.find("thead"):
            continue
        first_tr = table.find("tr")
        if first_tr is None:
            continue
        thead = soup.new_tag("thead")
        first_tr.extract()
        for cell in first_tr.find_all("td"):
            cell.name = "th"
        thead.append(first_tr)
        table.insert(0, thead)
        remaining = [
            tr
            for tr in table.find_all("tr")
            if tr.parent is not None and tr.parent.name != "thead"
        ]
        if remaining and table.find("tbody") is None:
            tbody = soup.new_tag("tbody")
            for tr in remaining:
                tr.extract()
                tbody.append(tr)
            table.append(tbody)


def _decorate_structured_html(fragment: str) -> str:
    soup = BeautifulSoup(fragment or "", "html.parser")
    for table in soup.find_all("table"):
        classes = table.get("class") or []
        if isinstance(classes, str):
            classes = [classes]
        if "ebook-table" not in classes:
            classes.append("ebook-table")
        table["class"] = classes

    for p in list(soup.find_all("p")):
        text = p.get_text(" ", strip=True)
        if re.match(r"^(example scenario|example:|callout:|note:)", text, re.I):
            p["class"] = (p.get("class") or []) + ["example-callout", "callout"]

    for heading in soup.find_all(["p", "h3", "h4", "strong"]):
        label = heading.get_text(" ", strip=True).lower()
        sibling = heading.find_next_sibling()
        if sibling and sibling.name == "ul" and "checklist" in label:
            sibling["class"] = (sibling.get("class") or []) + ["checklist"]
        if sibling and sibling.name == "ol" and any(k in label for k in ("workflow", "steps", "sequence")):
            sibling["class"] = (sibling.get("class") or []) + ["workflow"]

    for ul in soup.find_all("ul"):
        items = ul.find_all("li", recursive=False)
        if len(items) >= 3:
            prev = ul.find_previous(["p", "h3", "h4"])
            prev_text = (prev.get_text(" ", strip=True) if prev else "").lower()
            if "checklist" in prev_text or prev_text.endswith("checklist"):
                ul["class"] = (ul.get("class") or []) + ["checklist"]

    for ol in soup.find_all("ol"):
        items = ol.find_all("li", recursive=False)
        if len(items) >= 3:
            ol["class"] = (ol.get("class") or []) + ["workflow"]

    _split_checkbox_paragraphs(soup)
    _promote_section_headings(soup)
    _normalize_checklist_items(soup)
    _promote_numbered_paragraphs(soup)
    _ensure_table_headers(soup)
    _prepare_ebook_tables(soup)
    _keep_headings_with_next(soup)
    return str(soup)


def unresolved_placeholders(manuscript_md: str) -> list[str]:
    text = manuscript_md or ""
    found = [m.group(0) for m in _PLACEHOLDER_RE.finditer(text)]
    found.extend(m.group(0) for m in _URL_PLACEHOLDER_RE.finditer(text))
    return found


def rewrite_bracketed_website_placeholders(manuscript_md: str) -> tuple[str, list[dict[str, str]]]:
    """Remove bracketed website placeholders by rewriting only the known sentences.

    Does not invent URLs, businesses, or contact information.
    """
    text = str(manuscript_md or "")
    replacements: list[dict[str, str]] = []
    for pat, after, canonical_before in _BRACKETED_WEBSITE_SENTENCE_REWRITES:
        match = pat.search(text)
        if not match:
            continue
        before = match.group(0)
        text = pat.sub(after, text, count=1)
        replacements.append({"before": before, "after": after, "canonical_before": canonical_before})
    return text, replacements


def collapse_consecutive_page_breaks(html_doc: str) -> str:
    """Collapse duplicated xhtml2pdf page breaks that would insert a blank page."""
    return _CONSECUTIVE_NEXTPAGE_RE.sub("<pdf:nextpage />", html_doc or "")


def _nbsp_glue_last_words(root, count: int = 8) -> None:
    texts = [t for t in root.find_all(string=True) if str(t).strip()]
    if not texts:
        return
    node = texts[-1]
    parts = str(node).split()
    if len(parts) < 2:
        return
    n = min(count, len(parts))
    glued = "\u00a0".join(parts[-n:])
    head = " ".join(parts[:-n])
    node.replace_with((head + " " + glued).strip())


def _keep_chapter_last_block(fragment: str) -> str:
    """Keep the last chapter blocks together with CSS, never a table wrapper."""
    soup = BeautifulSoup(fragment or "", "html.parser")
    container = soup.body if soup.body else soup
    blocks = [
        child
        for child in getattr(container, "children", [])
        if getattr(child, "name", None) in _LAST_BLOCK_TAGS
    ]
    if not blocks:
        found = soup.find_all(_LAST_BLOCK_TAGS)
        blocks = found[-2:] if found else []
    if not blocks:
        return fragment
    skip = {"ebook-table", "ebook-comparison", "ebook-card", "ebook-timeline"}
    keep = [b for b in blocks[-2:] if not skip.intersection(b.get("class") or [])]
    if not keep:
        keep = [b for b in blocks[-1:] if not skip.intersection(b.get("class") or [])]
    if not keep:
        return str(soup)
    if (
        len(keep) == 1
        and keep[0].name == "div"
        and "chapter-last-block" in (keep[0].get("class") or [])
    ):
        _nbsp_glue_last_words(keep[0])
        return str(soup)
    wrapper = soup.new_tag("div")
    wrapper["class"] = ["chapter-last-block"]
    keep[0].insert_before(wrapper)
    for block in keep:
        wrapper.append(block.extract())
    _nbsp_glue_last_words(wrapper)
    return str(soup)


def _sentence_case_audience(audience: str) -> str:
    text = str(audience or "").strip()
    if not text:
        return ""
    if text[0].isupper() and (len(text) == 1 or not text[1].isupper()):
        return text[0].lower() + text[1:]
    return text


def _strip_identity_preamble(fragment: str, *, title: str, subtitle: str, author: str) -> str:
    soup = BeautifulSoup(fragment or "", "html.parser")
    identity = {
        (title or "").strip().lower(),
        (subtitle or "").strip().lower(),
        (author or "").strip().lower(),
        "copyright",
        "**copyright**",
    }
    identity.discard("")
    for tag in list(soup.find_all(["h1", "h2", "h3", "p"])):
        text = tag.get_text(" ", strip=True)
        low = re.sub(r"^[\s*]+|[\s*]+$", "", text.lower())
        if low in identity:
            tag.decompose()
            continue
        if "typeset from the approved manuscript" in low or "design does not rewrite" in low:
            tag.decompose()
            continue
        if "beginner and intermediate photographer" in low:
            tag.decompose()
    return str(soup)


def _linkify_sources(fragment: str) -> str:
    from services.ebook_customer_facing import source_url_is_displayable, unescape_source_url

    soup = BeautifulSoup(fragment or "", "html.parser")
    for li in soup.find_all("li"):
        raw = li.get_text(" ", strip=True)
        url = unescape_source_url(raw)
        if not url:
            continue
        if source_url_is_displayable(url):
            li.clear()
            anchor = soup.new_tag("a", href=url)
            anchor.string = url
            li.append(anchor)
        elif raw != url:
            li.clear()
            li.string = url
    ul = soup.find("ul")
    if ul:
        classes = ul.get("class") or []
        if isinstance(classes, str):
            classes = [classes]
        if "sources-list" not in classes:
            classes.append("sources-list")
        ul["class"] = classes
    return str(soup)


def find_designed_chapter_pages(pdf_bytes: bytes, chapter_titles: list[str]) -> dict[str, int]:
    """Map chapter title -> 1-based page using 'Chapter N' openers, skipping TOC."""
    if not pdf_bytes or not chapter_titles:
        return {}
    try:
        import fitz
    except Exception:
        return {}
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return {}
    found: dict[str, int] = {}
    try:
        pages = [(doc.load_page(i).get_text("text") or "") for i in range(doc.page_count)]
        start = 0
        for i, text in enumerate(pages):
            low = text.lower()
            if re.search(r"(?m)^\s*contents\s*$", text, re.I) or "table of contents" in low:
                start = i + 1
                break
        for idx, title in enumerate(chapter_titles, start=1):
            needle = re.sub(r"\s+", " ", (title or "").strip()).lower()
            if len(needle) < 6:
                continue
            opener = re.compile(rf"chapter\s+{idx}\b", re.I)
            for i in range(start, len(pages)):
                compact = re.sub(r"\s+", " ", pages[i]).strip()
                if opener.search(compact) and needle[:40] in compact.lower():
                    found[title] = i + 1
                    break
    finally:
        doc.close()
    return found


def render_designed_ebook_html(
    *,
    title: str,
    subtitle: str,
    author: str,
    manuscript_md: str,
    design: EbookDesign,
    audience: str = "",
    visual_plan: dict | None = None,
    toc_page_numbers: dict[str, int] | None = None,
    include_title_page: bool = True,
) -> str:
    """Build full interior HTML. Does not mutate manuscript_md.

    include_title_page=False omits the interior's own title-page section.
    render_designed_bundle() always prepends a separate designed cover PDF
    (photo-backed or generated) ahead of this interior document, so the
    interior's title/subtitle/author front-matter page was a second,
    duplicate title page in the merged output — caught by the
    "duplicate_page" preflight finding. Every other caller renders this HTML
    standalone (no separate cover prepended) and keeps the default True.
    """
    original = str(manuscript_md or "")
    body_md, disclaimer_md, sources_md = peel_back_matter(original)
    preamble, _chapters_raw = _split_chapters(body_md)
    chapters = numbered_chapters(original)
    css = theme_css(design.theme_id)
    css = re.sub(r"letter-spacing\s*:\s*[^;\"']+;?", "", css, flags=re.I)

    parts: list[str] = [
        '<!doctype html><html lang="en" xmlns:pdf="http://www.xhtml2pdf.com/ns/"><head><meta charset="utf-8"/>',
        f"<title>{_e(title)}</title>",
        f"<style>{css}</style></head><body>",
    ]
    if include_title_page:
        parts.append('<section class="title-page" id="title-page">')
        parts.append(f'<h1 class="book-title">{_e(title)}</h1>')
        if subtitle:
            parts.append(f'<p class="title-sub">{_e(subtitle)}</p>')
        parts.append(f'<p class="title-author">{_e(author or "")}</p>')
        if audience:
            parts.append(f'<p class="caption">For {_e(_sentence_case_audience(audience))}</p>')
        parts.append("</section>")
        parts.append("<pdf:nextpage />")

    parts.append('<section class="legal-page" id="copyright">')
    parts.append("<h2>Copyright</h2>")
    parts.append(
        f"<p>Title: {_e(title)}. Author: {_e(author)}. All rights reserved.</p>"
    )
    if preamble:
        toc_only = all(
            (not ln.strip()) or _MD_TOC_LINE_RE.match(ln) or ln.strip().startswith("#")
            for ln in preamble.splitlines()
        )
        if not toc_only:
            stripped = _strip_identity_preamble(
                _strip_leading_heading(_md_fragment(preamble), title),
                title=title,
                subtitle=subtitle,
                author=author,
            )
            if BeautifulSoup(stripped, "html.parser").get_text(" ", strip=True):
                parts.append(stripped)
    parts.append(
        '<p class="caption">The full disclaimer and source list appear as unnumbered back matter. '
        "They are not numbered chapters.</p>"
    )
    parts.append("</section>")
    parts.append("<pdf:nextpage />")

    if chapters:
        parts.append('<section class="toc-page" id="toc">')
        parts.append("<h2>Contents</h2>")
        parts.append('<ol class="toc-list">')
        for i, (ctitle, _cmd) in enumerate(chapters, start=1):
            page = ""
            if toc_page_numbers:
                page = toc_page_numbers.get(ctitle) or toc_page_numbers.get(str(i)) or ""
            page_span = (
                f' <span class="toc-page-num">{_e(str(page))}</span>'
                if page not in ("", None)
                else ""
            )
            parts.append(
                "<li>"
                f'<span class="toc-num">{i}</span> '
                f'<a href="#chapter-{i}">{_e(ctitle)}</a>'
                f"{page_span}"
                "</li>"
            )
        parts.append("</ol></section>")

    for i, (ctitle, cmd) in enumerate(chapters, start=1):
        body = _strip_leading_heading(_md_fragment(cmd), ctitle)
        body = _decorate_structured_html(body)
        body = _keep_chapter_last_block(body)
        parts.append("<pdf:nextpage />")
        parts.append(f'<section class="chapter-page" id="chapter-{i}">')
        parts.append(f'<p class="chapter-num">Chapter {i}</p>')
        parts.append(f'<h2 class="chapter-title">{_e(ctitle)}</h2>')
        parts.append(body)
        parts.append("</section>")

    if disclaimer_md:
        disc_html = _md_fragment(disclaimer_md)
        parts.append("<pdf:nextpage />")
        parts.append('<section class="back-matter-page" id="disclaimer">')
        parts.append("<h2>Disclaimer</h2>")
        parts.append(disc_html)
        parts.append("</section>")
    if sources_md:
        src_html = _linkify_sources(_md_fragment(sources_md))
        parts.append("<pdf:nextpage />")
        parts.append('<section class="back-matter-page" id="sources">')
        parts.append("<h2>Sources</h2>")
        parts.append(src_html)
        parts.append("</section>")

    parts.append("</body></html>")
    html_doc = "\n".join(parts)
    html_doc = re.sub(r"letter-spacing\s*:\s*[^;\"']+;?", "", html_doc, flags=re.I)
    html_doc = collapse_consecutive_page_breaks(html_doc)
    if visual_plan:
        from services.ebook_visual_pipeline import insert_planned_visuals_into_html

        html_doc = insert_planned_visuals_into_html(html_doc, visual_plan)
    return html_doc


def manuscript_text_fingerprint(manuscript_md: str) -> str:
    """Normalized manuscript text used to prove design did not rewrite content."""
    return re.sub(r"\s+", " ", str(manuscript_md or "")).strip()
