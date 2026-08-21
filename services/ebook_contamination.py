"""Central ebook contamination validator.

Errors belong in application state. They must never become book content.
Zero paid calls.
"""
from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

DEFAULT_AUTHOR = "Anonymous Author"
FACTORY_BRAND = "Digital Product Factory"

_LEADING_PUNCT_RE = re.compile(r"^[\s:;,\-–—|•·]+")
_TRAILING_PUNCT_TITLE_RE = re.compile(r"[\s:;,\-–—|]+$")
_HTTP_ERROR_RE = re.compile(
    r"\b(401|403|404|429|500|502|503)\b.{0,80}(unauthorized|forbidden|not found|rate limit|internal server|client error)|"
    r"\b(unauthorized|authorization failed|pexels request failed|client error)\b.{0,80}\b(401|403|404|429)?",
    re.I,
)
_TRACEBACK_RE = re.compile(r"traceback \(most recent call last\)|file \".+\", line \d+", re.I)
_PLACEHOLDER_RE = re.compile(
    r"\[(?:insert|todo|tbd|placeholder|image here|prompt)[^\]]*\]|"
    r"\{\{[^{}]+\}\}|<<[^>]+>>|TODO:|FIXME:",
    re.I,
)
_PROVIDER_URL_RE = re.compile(
    r"https?://(?:api\.pexels\.com|api\.openai\.com|api\.tavily\.com|api\.minimax)",
    re.I,
)
_LOCAL_RE = re.compile(r"127\.0\.0\.1|localhost|about:srcdoc|/ebook-workspace/|full-preview\?digest=", re.I)
_INTERFACE_RE = re.compile(
    r"retry missing image|choose cover photo|view technical details|"
    r"approve & save|needs correction\.|pexels connected|factory test mode",
    re.I,
)
_PROMPT_RE = re.compile(
    r"\b(you are a|return only json|mandatory deliverable|system prompt|"
    r"do not invent unrelated facts)\b",
    re.I,
)
_HASH_RE = re.compile(r"\b[a-f0-9]{64}\b")
_ADJACENT_HEADING_RE = re.compile(r"(?m)^(#{2,4})\s+(.+)\n+\1\s+\2\s*$")


def normalize_book_title(title: str) -> str:
    text = str(title or "").replace("\ufeff", "").strip()
    text = text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = _LEADING_PUNCT_RE.sub("", text)
    text = _TRAILING_PUNCT_TITLE_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_author(author: str | None, *fallbacks: Any) -> str:
    for value in (author, *fallbacks):
        text = str(value or "").strip()
        if not text:
            continue
        if text.lower() in {FACTORY_BRAND.lower(), "digital guide", "factory"}:
            continue
        return text
    return DEFAULT_AUTHOR


def is_description_heading(title: str, *, book_title: str = "", subtitle: str = "") -> bool:
    heading = str(title or "").strip()
    if not heading:
        return False
    low = heading.lower()
    if low in {"table of contents", "contents", "toc"}:
        return True
    if subtitle and low == str(subtitle).strip().lower():
        return True
    if book_title and low == str(book_title).strip().lower():
        return True
    if heading.startswith("#"):
        return True
    words = heading.split()
    if len(words) >= 12 and not heading.lower().startswith("chapter"):
        return True
    if re.search(r"\b(handbook|practical guide|this book|this ebook)\b", low) and len(words) >= 8:
        return True
    return False


def sanitize_manuscript(md: str, *, title: str = "", subtitle: str = "", author: str = "") -> str:
    text = str(md or "").replace("\ufeff", "")
    text = text.replace(FACTORY_BRAND, author or DEFAULT_AUTHOR)
    lines = text.splitlines()
    out: list[str] = []
    seen_h2: set[str] = set()
    skipped_description = False
    for line in lines:
        h2 = re.match(r"^##\s+(.+)$", line)
        if h2:
            heading = h2.group(1).strip()
            key = re.sub(r"\s+", " ", heading.lower())
            if not skipped_description and is_description_heading(
                heading, book_title=title, subtitle=subtitle
            ):
                skipped_description = True
                continue
            if key in {"table of contents", "contents", "toc"}:
                continue
            if key in seen_h2:
                continue
            seen_h2.add(key)
            out.append(f"## {heading}")
            continue
        if _HTTP_ERROR_RE.search(line) or _PROVIDER_URL_RE.search(line) or _TRACEBACK_RE.search(line):
            continue
        if _INTERFACE_RE.search(line) and not line.startswith("#"):
            continue
        out.append(line)
    cleaned = "\n".join(out)
    cleaned = _ADJACENT_HEADING_RE.sub(r"\1 \2", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip() + "\n"
    return cleaned


def detect_contamination(text: str, *, allow_factory_metadata: bool = False) -> list[dict[str, str]]:
    blob = str(text or "")
    findings: list[dict[str, str]] = []

    def add(code: str, message: str) -> None:
        findings.append({"code": code, "message": message})

    if _LOCAL_RE.search(blob):
        add("local_url", "Preview or localhost URL leaked into book content")
    if _PROVIDER_URL_RE.search(blob):
        add("provider_url", "Provider API URL leaked into book content")
    if _HTTP_ERROR_RE.search(blob):
        add("http_error", "HTTP or authorization error leaked into book content")
    if _TRACEBACK_RE.search(blob):
        add("traceback", "Traceback leaked into book content")
    if re.search(r"retry missing image", blob, re.I):
        add("retry_missing_image", "Retry-missing-image text leaked into book content")
    if _PLACEHOLDER_RE.search(blob):
        add("placeholder", "Unresolved placeholder leaked into book content")
    if _PROMPT_RE.search(blob):
        add("raw_prompt", "Prompt or production instruction leaked into book content")
    if not allow_factory_metadata and FACTORY_BRAND.lower() in blob.lower():
        add("factory_brand", "Factory interface language leaked into book content")
    if _INTERFACE_RE.search(blob):
        add("interface_language", "Factory interface language leaked into book content")
    return findings


def inspect_html_contamination(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    visible = soup.get_text("\n", strip=True)
    findings = detect_contamination(visible)
    raw_findings = detect_contamination(html or "")
    for row in raw_findings:
        if row.get("code") in {"local_url", "provider_url", "http_error", "toc_app_url"}:
            findings.append(row)
    for a in soup.find_all("a"):
        href = str(a.get("href") or "")
        parent = a.find_parent(class_=lambda c: c and "toc" in str(c).lower())
        if _LOCAL_RE.search(href) or "ebook-workspace" in href or "full-preview" in href:
            findings.append({"code": "toc_app_url", "message": href[:160]})
        elif parent is not None and (href.startswith("http://") or href.startswith("https://")):
            findings.append({"code": "toc_app_url", "message": href[:160]})
    headings = soup.find_all(["h1", "h2", "h3"])
    for prev, cur in zip(headings, headings[1:]):
        prev_text = prev.get_text(" ", strip=True)
        cur_text = cur.get_text(" ", strip=True)
        if prev.name == "h1" and cur.name == "h1":
            continue
        if prev_text and cur_text and prev_text.strip().lower() == cur_text.strip().lower():
            findings.append({"code": "duplicate_heading", "message": cur_text[:120]})
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)
        if title.startswith((":", "-", "–", "—", "|")):
            findings.append({"code": "leading_title_punct", "message": title[:80]})
    author_el = soup.select_one("[data-ebook-author], .title-author, .cover-author")
    if author_el is not None and not str(author_el.get_text(" ", strip=True)).strip():
        findings.append({"code": "missing_author", "message": "Author is missing from front matter"})
    return findings


def gate_ebook_output(
    *,
    title: str,
    author: str,
    manuscript: str,
    html: str = "",
    pdf_text: str = "",
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not normalize_book_title(title):
        findings.append({"code": "missing_title", "message": "Title is required"})
    if normalize_book_title(title) != str(title or "").strip():
        findings.append({"code": "malformed_title", "message": "Title has leading or trailing punctuation"})
    if not str(author or "").strip() or str(author).strip().lower() == FACTORY_BRAND.lower():
        findings.append({"code": "missing_author", "message": "Author is missing or malformed"})
    findings.extend(detect_contamination(manuscript))
    if html:
        findings.extend(inspect_html_contamination(html))
    if pdf_text:
        findings.extend(detect_contamination(pdf_text, allow_factory_metadata=True))
    # Deduplicate
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for row in findings:
        key = (row.get("code") or "", row.get("message") or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique
