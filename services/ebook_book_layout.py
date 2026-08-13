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
from services.ebook_design_system import theme_css
from services.ebook_package import _split_chapters, _sanitize_html, fix_inline_hyphen_lists_html

_PLACEHOLDER_RE = re.compile(
    r"\[(?:insert|image|photo|visual|todo|placeholder)[^\]]*\]|\bTODO\b|\blorem ipsum\b",
    re.I,
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

    _promote_numbered_paragraphs(soup)
    _ensure_table_headers(soup)
    return str(soup)


def unresolved_placeholders(manuscript_md: str) -> list[str]:
    return [m.group(0) for m in _PLACEHOLDER_RE.finditer(manuscript_md or "")]


def render_designed_ebook_html(
    *,
    title: str,
    subtitle: str,
    author: str,
    manuscript_md: str,
    design: EbookDesign,
    audience: str = "",
) -> str:
    """Build full interior HTML. Does not mutate manuscript_md."""
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
        '<section class="title-page" id="title-page">',
        f'<h1 class="book-title">{_e(title)} </h1>',
    ]
    if subtitle:
        parts.append(f'<p class="title-sub">{_e(subtitle)} </p>')
    parts.append(f'<p class="title-author">{_e(author or "")} </p>')
    if audience:
        parts.append(f'<p class="caption">For {_e(audience)}</p>')
    parts.append("</section>")
    parts.append("<pdf:nextpage />")

    parts.append('<section class="legal-page" id="copyright">')
    parts.append('<p class="back-matter-label">Copyright </p>')
    parts.append("<h2>Copyright </h2>")
    parts.append(
        f"<p>Title: {_e(title)}. Author: {_e(author)}. All rights reserved. "
        "This interior is typeset from the approved manuscript. Design does not rewrite manuscript content.</p>"
    )
    if preamble:
        stripped = _strip_leading_heading(_md_fragment(preamble), title)
        parts.append(stripped)
    parts.append(
        '<p class="caption">The full disclaimer and source list appear as unnumbered back matter. '
        "They are not numbered chapters.</p>"
    )
    parts.append("</section>")
    parts.append("<pdf:nextpage />")

    if chapters:
        parts.append('<section class="toc-page" id="toc"><h2>Contents</h2><ol class="toc-list">')
        for i, (ctitle, _cmd) in enumerate(chapters, start=1):
            parts.append(f'<li><a href="#chapter-{i}">{_e(ctitle)}</a></li>')
        parts.append("</ol></section>")

    for i, (ctitle, cmd) in enumerate(chapters, start=1):
        body = _strip_leading_heading(_md_fragment(cmd), ctitle)
        body = _decorate_structured_html(body)
        parts.append("<pdf:nextpage />")
        parts.append(
            f'<section class="chapter-page" id="chapter-{i}">'
            f'<p class="chapter-num">Chapter {i} </p>'
            f'<h2 class="chapter-title">{_e(ctitle)} </h2>'
            f"{body}"
            "</section>"
        )

    if disclaimer_md:
        disc_html = _md_fragment(disclaimer_md)
        parts.append("<pdf:nextpage />")
        parts.append(
            '<section class="back-matter-page" id="disclaimer">'
            '<p class="back-matter-label">Unnumbered </p>'
            "<h2>Disclaimer </h2>"
            f"{disc_html}"
            "</section>"
        )
    if sources_md:
        src_html = _md_fragment(sources_md)
        soup = BeautifulSoup(src_html, "html.parser")
        ul = soup.find("ul")
        if ul:
            ul["class"] = (ul.get("class") or []) + ["sources-list"]
        parts.append("<pdf:nextpage />")
        parts.append(
            '<section class="back-matter-page" id="sources">'
            '<p class="back-matter-label">Unnumbered </p>'
            "<h2>Sources </h2>"
            f"{str(soup)}"
            "</section>"
        )

    parts.append("</body></html>")
    html_doc = "".join(parts)
    html_doc = re.sub(r"letter-spacing\s*:\s*[^;\"']+;?", "", html_doc, flags=re.I)
    return html_doc


def manuscript_text_fingerprint(manuscript_md: str) -> str:
    """Normalized manuscript text used to prove design did not rewrite content."""
    return re.sub(r"\s+", " ", str(manuscript_md or "")).strip()
