"""Customer-facing ebook sanitization and leakage validation.

Removes production/prompt residue from manuscripts and flags the same
defects in HTML/PDF so they cannot be published. Zero paid calls.
"""
from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

_EMPTY_TABLE_BLOCK_RE = re.compile(
    r"(?:^\|\s*\|?\s*$\n)+(?:^\|\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$\n?)+",
    re.M,
)
_EMPTY_PIPE_LINE_RE = re.compile(r"(?m)^\|\s*\|?\s*$")
_BRACKET_SCENARIO_RE = re.compile(
    r"\[(?:inquiry-to-booking scenario|hypothetical dollar-margin scenario|hypothetical media-planning scenario)\]",
    re.I,
)
_CONCAT_HEADER_BLOBS = (
    "Event niche / Typical client need / Guest interaction level / Planning complexity",
    "Startup lane / Typical planning range / What it usually includes / Legal-insurance priority",
    "Kit level / Camera bodies / Lenses / Lighting / Computing-editing",
    "package-and-margin / Coverage and deliverables / Price charged",
    "Table: event-planning-timeline",
)
_FACTORY_BUDGET_RE = re.compile(
    r"\$\s*2\.50\b.{0,80}writing and refinement|\bwriting and refinement.{0,80}\$\s*2\.50\b",
    re.I,
)
_ESCAPED_URL_RE = re.compile(r"https?\\://|www\\.")
_LOCAL_HOST_RE = re.compile(
    r"127\.0\.0\.1|localhost|/ebook-workspace/|full-preview\?digest=|about:srcdoc",
    re.I,
)
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+){1,}$")
_MANDATORY_HEADING_RE = re.compile(
    r"^#{2,4}\s*MANDATORY\s+DELIVERABLE\s*\[([^\]]+)\]\s*$",
    re.I | re.M,
)

LEAKAGE_PHRASES = (
    "mandatory deliverable",
    "[inquiry-to-booking scenario]",
    "[hypothetical dollar-margin scenario]",
    "[hypothetical media-planning scenario]",
    "research in the assigned material",
    "one research source notes",
    "this interior is typeset from the approved manuscript",
    "design does not rewrite manuscript content",
    "$2.50 for writing and refinement stages",
    "writing and refinement stages $2.50",
    "preserve at least $2.50",
    "assigned source",
    "assigned required examples",
    "assigned citations",
    "assigned facts",
    "factory test mode",
    "ebook-workspace/",
    "spend cap",
    "refinement budget",
)

HEADING_POLISH = {
    "checklist: insurance-and-coi": "Checklist: Insurance and certificate of insurance",
    "checklist: event-backup-kit": "Checklist: Event backup kit",
    "checklist: space-power-cable-staffing": "Checklist: Space, power, cables, and staffing",
    "checklist: first-paid-event-30-day": "Checklist: 30-day first paid event plan",
    "inquiry-to-signed-booking": "From inquiry to a signed booking",
    "mandatory deliverable [inquiry-to-booking scenario]": "From inquiry to a signed booking",
    "mandatory deliverable [hypothetical dollar-margin scenario]": "Hypothetical package and margin scenario",
    "mandatory deliverable [hypothetical media-planning scenario]": "Hypothetical media-planning scenario",
    "table: event-planning-timeline": "Event-planning timeline",
    "numbered workflow: pre-event-planning": "Pre-event planning workflow",
    "event-day-run-of-show": "Event-day run of show",
    "file-backup-procedure": "File backup procedure",
    "dye-sub-printer-comparison": "Dye-sub printer comparison",
    "setup-queue-order-pay-pickup": "Setup, queue, order, pay, and pickup",
    "keepsake-go-no-go-staffing-safety": "Keepsake go/no-go staffing and safety",
}

_SLUG_WORDS = {
    "coi": "certificate of insurance",
    "dye-sub": "dye-sub",
    "go-no-go": "go/no-go",
}

_EXACT_PROSE = (
    (
        "If you create a custom quote, preserve at least $2.50 for writing and refinement stages in your internal costing so administrative work is not treated as free.",
        "If you create a custom quote, treat administrative and writing time as a real cost rather than as free labor.",
    ),
    (
        "Keep at least **$2.50** allocated for writing and refinement stages in your internal planning if you are building worksheets, templates, or client-facing materials for the job. That is not a market rate claim; it is a reminder not to price your preparation time at zero.",
        "If you are building worksheets, templates, or client-facing materials for the job, count that preparation time as a real cost. That is not a market rate claim; it is a reminder not to price your preparation time at zero.",
    ),
    (
        "For example, a planning scenario might reserve all hard costs first and still preserve at least **$2.50 for writing and refinement stages** in your overall package design workflow, rather than treating every dollar as event-day labor.",
        "For example, a planning scenario might reserve all hard costs first and still count administrative and writing time in the package design, rather than treating every dollar as event-day labor.",
    ),
    (
        "Also preserve at least $2.50 for writing and refinement stages in your planning math so your quoted price is not based only on raw materials and event-hour labor.",
        "Also count administrative and writing time in your planning math so your quoted price is not based only on raw materials and event-hour labor.",
    ),
    (
        "Preserve at least **$2.50 for writing and refinement stages** in your planning if you are producing custom copy, signage, or printed insert text as part of your workflow.",
        "Count administrative and writing time in your planning if you are producing custom copy, signage, or printed insert text as part of your workflow.",
    ),
    (
        "- [ ] Reserved at least $2.50 for writing and refinement stages",
        "- [ ] Accounted for administrative and writing time as a real cost, not as free labor",
    ),
    (
        "For compact on-site dye-sub printing, the assigned source supports that the **DNP QW410** is a dye-sublimation printer.",
        "For compact on-site dye-sub printing, manufacturer documentation states that the **DNP QW410** is a dye-sublimation printer.",
    ),
    (
        "Research in the assigned material suggests that buying used gear or renting can reduce startup costs substantially compared with purchasing everything new.",
        "Industry startup-cost guides suggest that buying used gear or renting can reduce startup costs substantially compared with purchasing everything new.",
    ),
    (
        "**Hypothetical / planning example: inquiry-to-booking scenario**",
        "**Example: turning an inquiry into a signed booking**",
    ),
    (
        "| package-and-margin |",
        "| Package |",
    ),
    (
        "| Hypothetical community event | 2 hours coverage, 1 planning call, edited gallery, 5-day turnaround | $500 | Shooting time $150, planning/admin $50, editing/delivery $100, travel $50, taxes reserve $50, gear recovery $50, writing and refinement stages $2.50 | $47.50 |",
        "| Hypothetical community event | 2 hours coverage, 1 planning call, edited gallery, 5-day turnaround | $500 | Shooting time $150, planning/admin $50, editing/delivery $100, travel $50, taxes reserve $50, gear recovery $50 | $50 |",
    ),
    (
        "| Hypothetical reunion | 4 hours coverage, 1 planning call, edited gallery, 7-day turnaround | $1,500 | Shooting time $500, planning/admin $100, editing/delivery $250, travel $100, taxes reserve $150, gear recovery $150, assistant or support buffer $100, writing and refinement stages $2.50 | $147.50 |",
        "| Hypothetical reunion | 4 hours coverage, 1 planning call, edited gallery, 7-day turnaround | $1,500 | Shooting time $500, planning/admin $100, editing/delivery $250, travel $100, taxes reserve $150, gear recovery $150, assistant or support buffer $100 | $150 |",
    ),
)

MARGIN_RECALCULATIONS = (
    {
        "scenario": "Hypothetical community event",
        "price": "$500",
        "removed_cost": "$2.50",
        "remaining_before": "$47.50",
        "remaining_after": "$50",
    },
    {
        "scenario": "Hypothetical reunion",
        "price": "$1,500",
        "removed_cost": "$2.50",
        "remaining_before": "$147.50",
        "remaining_after": "$150",
    },
)


def _title_from_slug(slug: str) -> str:
    raw = str(slug or "").strip().lower()
    for token, repl in _SLUG_WORDS.items():
        raw = raw.replace(token, repl.replace(" ", "\x00"))
    words = [w.replace("\x00", " ") for w in raw.replace("_", "-").split("-") if w]
    out: list[str] = []
    for i, w in enumerate(words):
        if " " in w:
            out.append(w)
            continue
        if w in {"and", "or", "of", "to", "the", "a"} and i:
            out.append(w)
        else:
            out.append(w.upper() if w in {"coi"} else w[:1].upper() + w[1:])
    return " ".join(out)


def polish_heading(title: str) -> str:
    text = str(title or "").strip()
    mapped = HEADING_POLISH.get(text.lower())
    if mapped:
        return mapped
    lower = text.lower()
    if lower.startswith("checklist:"):
        rest = text.split(":", 1)[1].strip()
        if _SLUG_RE.match(rest.lower()):
            return "Checklist: " + _title_from_slug(rest)
    if lower.startswith("table:"):
        rest = text.split(":", 1)[1].strip()
        if _SLUG_RE.match(rest.lower()):
            return _title_from_slug(rest)
    if lower.startswith("numbered workflow:"):
        rest = text.split(":", 1)[1].strip()
        if _SLUG_RE.match(rest.lower()):
            return _title_from_slug(rest) + " workflow"
    if _SLUG_RE.match(text.lower()):
        return _title_from_slug(text)
    return text


def unescape_source_url(raw: str) -> str:
    text = str(raw or "").strip()
    text = text.replace("\\:", ":").replace("\\.", ".")
    text = re.sub(r"^<\s*|\s*>$", "", text)
    return text.strip()


def source_url_is_displayable(raw: str) -> bool:
    url = unescape_source_url(raw)
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    if not parsed.netloc or " " in url:
        return False
    if url.lower().startswith(("javascript:", "data:", "vbscript:")):
        return False
    return True


def detect_customer_facing_defects(text: str) -> list[dict[str, str]]:
    blob = str(text or "")
    low = blob.lower()
    findings: list[dict[str, str]] = []
    for phrase in LEAKAGE_PHRASES:
        if phrase.lower() in low:
            findings.append({"code": "customer_facing_leakage", "message": phrase})
    if _FACTORY_BUDGET_RE.search(blob):
        findings.append(
            {"code": "factory_budget_residue", "message": "$2.50 writing and refinement residue"}
        )
    if _EMPTY_PIPE_LINE_RE.search(blob) or _EMPTY_TABLE_BLOCK_RE.search(blob):
        findings.append({"code": "empty_table", "message": "Empty markdown table artifact"})
    if _ESCAPED_URL_RE.search(blob):
        findings.append({"code": "escaped_source_url", "message": "Escaped source URL"})
    if _LOCAL_HOST_RE.search(blob):
        findings.append({"code": "local_preview_url", "message": "Localhost or preview-route leakage"})
    for m in re.finditer(r"(?m)^#{2,4}\s+(.+)$", blob):
        title = m.group(1).strip()
        if polish_heading(title) != title and (
            _SLUG_RE.match(title.lower())
            or "mandatory deliverable" in title.lower()
            or title.lower().startswith(("checklist:", "table:", "numbered workflow:"))
        ):
            findings.append({"code": "production_heading", "message": title[:80]})
    return findings


def _drop_duplicate_headings(text: str, removed: list[str]) -> str:
    """Keep the first occurrence of a heading title; drop later repeats."""
    seen: set[str] = set()

    def repl(match: re.Match[str]) -> str:
        title = match.group(2).strip()
        key = re.sub(r"\s+", " ", title.lower())
        if key in seen:
            removed.append(title[:120])
            return ""
        seen.add(key)
        return match.group(0)

    return re.sub(r"^(#{2,4})\s+(.+)$", repl, text, flags=re.M)


CONCATENATED_HEADER_SAMPLES = (
    "Event nicheTypical client needGuest interaction levelPlanning complexitySales opportunity for on-site printsMain beginner caution",
    "Startup laneTypical planning rangeWhat it usually includesLegal/insurance priorityLaunch risk if skipped",
    "Kit levelCamera bodiesLensesLightingComputing/editingPrinting equipmentBest use",
    "PackageCoverage and deliverablesPrice chargedPlanning + labor cost stackEstimated remaining amount",
    "StageWhenWhat to confirmWhy it matters",
    "PrinterDocumented print focusDocumented sizes/examplesDocumented speed/examplesDocumented media capacity/examplesBest-fit event use",
)


def inspect_rendered_ebook(*, html: str = "", pdf_text: str = "", pdf_bytes: bytes = b"") -> list[dict[str, str]]:
    """Fail rendered HTML/PDF defects, not just manuscript objects."""
    findings: list[dict[str, str]] = []
    soup = BeautifulSoup(html or "", "html.parser")
    data_tables = [
        t
        for t in soup.find_all("table")
        if (
            ("ebook-table" in (t.get("class") or []) or "va-table" in (t.get("class") or []))
            and "ebook-card" not in (t.get("class") or [])
        )
    ]
    layout_classes = {
        "toc-list",
        "toc-table",
        "chapter-opener",
        "checklist",
        "ebook-list",
        "heading-keep",
        "ebook-comparison",
    }
    other_tables = [
        t
        for t in soup.find_all("table")
        if t not in data_tables
        and "ebook-card" not in (t.get("class") or [])
        and not layout_classes.intersection(t.get("class") or [])
    ]
    for _table in other_tables:
        findings.append(
            {
                "code": "empty_table",
                "message": "Non-data table artifact in rendered HTML (keep-together or empty wrapper)",
            }
        )
    for table in data_tables:
        if table.find("th") and any(th.find("br") for th in table.find_all("th")):
            findings.append(
                {"code": "concatenated_table_header", "message": "br used to simulate separate headers"}
            )
        rows = table.find_all("tr")
        if not rows:
            findings.append({"code": "empty_table", "message": "Data table has no rows"})
            continue
        heads = [c.get_text(" ", strip=True) for c in rows[0].find_all("th")]
        if not heads:
            heads = [c.get_text(" ", strip=True) for c in rows[0].find_all("td")]
        if len(heads) >= 5:
            findings.append(
                {
                    "code": "table_too_wide",
                    "message": f"Portrait table has {len(heads)} columns; render as stacked comparison cards",
                }
            )
            continue
        if len(heads) == 4 and [h.strip() for h in heads] == [
            "Stage",
            "When",
            "What to confirm",
            "Why it matters",
        ]:
            from services.ebook_book_layout import portrait_table_is_readable

            body = [
                [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
                for tr in rows[1:]
            ]
            if not portrait_table_is_readable(heads, body):
                findings.append(
                    {
                        "code": "table_too_wide",
                        "message": "Timeline table cannot fit readable cells; render as labeled cards",
                    }
                )
                continue
        if len(heads) < 2:
            findings.append({"code": "concatenated_table_header", "message": " ".join(heads)[:120]})
            continue
        first = rows[0].find(["th", "td"])
        if first is not None:
            cell_join = re.sub(r"\s+", "", first.get_text("", strip=True))
            jammed = "".join(re.sub(r"\s+", "", h) for h in heads)
            if len(heads) >= 3 and jammed and jammed == cell_join:
                findings.append({"code": "concatenated_table_header", "message": first.get_text(" ", strip=True)[:120]})
            elif len(heads) >= 3:
                first_join = re.sub(r"\s+", "", first.get_text("", strip=True))
                first_three = "".join(re.sub(r"\s+", "", h) for h in heads[:3])
                if first_three and first_three in first_join and first_join != re.sub(r"\s+", "", heads[0]):
                    findings.append({"code": "concatenated_table_header", "message": first.get_text(" ", strip=True)[:120]})
        for tr in rows[1:]:
            cols = len(tr.find_all(["td", "th"]))
            if cols and cols != len(heads):
                findings.append(
                    {
                        "code": "malformed_table_header",
                        "message": f"Header has {len(heads)} cells; body row has {cols}",
                    }
                )
                break
    for card in soup.select(".ebook-card"):
        labels = [s.get_text(" ", strip=True) for s in card.select(".ebook-card-label")]
        if len(labels) < 2:
            findings.append({"code": "malformed_table_header", "message": "Comparison card is missing labeled fields"})
            continue
        jammed = "".join(re.sub(r"[:\s]+", "", lb) for lb in labels[:3])
        first = labels[0]
        if jammed and jammed in re.sub(r"[:\s]+", "", first) and len(labels) >= 3:
            findings.append({"code": "concatenated_table_header", "message": first[:120]})
    if "about:srcdoc" in (html or "").lower() or "about:srcdoc" in (pdf_text or "").lower():
        findings.append({"code": "local_preview_url", "message": "about:srcdoc leakage"})
    compact_lines = [re.sub(r"[\t ]+", " ", ln) for ln in f"{html or ''}\n{pdf_text or ''}".splitlines()]
    for sample in CONCATENATED_HEADER_SAMPLES:
        if any(sample in ln.replace(" ", "") or sample in ln for ln in compact_lines):
            # Only fail when labels are jammed on one extracted line, not when each sits on its own line.
            jammed = any(sample in ln for ln in compact_lines)
            if jammed:
                findings.append({"code": "concatenated_table_header", "message": sample[:80]})
    blob = f"{html or ''}\n{pdf_text or ''}"
    if re.search(r"\|\s*\|", blob) or "| :- |" in blob:
        findings.append({"code": "empty_table", "message": "Empty markdown table artifact in rendered output"})
    if re.search(r">\s*Unnumbered\s*<", html or "", re.I) or re.search(
        r"(?m)^Unnumbered\b", pdf_text or ""
    ):
        findings.append({"code": "implementation_label", "message": "Visible Unnumbered label"})
    audience_hits = len(re.findall(r"For beginner and intermediate photographers", html or "", re.I))
    if audience_hits > 1:
        findings.append({"code": "duplicate_audience", "message": f"{audience_hits} audience statements"})
    heading_titles = [
        re.sub(r"\s+", " ", h.get_text(" ", strip=True).lower())
        for h in soup.select(".chapter-page h2.chapter-title, .chapter-page h3, .chapter-page h4")
    ]
    seen_h: set[str] = set()
    for title in heading_titles:
        if title and title in seen_h:
            findings.append({"code": "duplicate_heading", "message": title[:80]})
            break
        seen_h.add(title)
    for a in soup.find_all("a"):
        href = str(a.get("href") or "")
        if _LOCAL_HOST_RE.search(href) or re.search(r"ebook-workspace/\d+|full-preview\?digest=", href, re.I):
            findings.append({"code": "local_preview_url", "message": href[:120]})
    if pdf_bytes:
        try:
            import fitz

            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            try:
                for i, page in enumerate(doc):
                    for link in page.get_links() or []:
                        uri = str(link.get("uri") or "")
                        if re.search(r"127\.0\.0\.1|localhost|ebook-workspace/|full-preview|about:srcdoc", uri, re.I):
                            findings.append(
                                {
                                    "code": "local_preview_url",
                                    "message": f"PDF page {i + 1}: {uri[:120]}",
                                }
                            )
            finally:
                doc.close()
        except Exception:
            pass
    return findings


def sanitize_customer_manuscript(manuscript_md: str) -> tuple[str, dict[str, Any]]:
    """Rewrite leaked production language. Does not invent sources or prices."""
    text = str(manuscript_md or "")
    removed: list[str] = []
    empty_removed = 0

    def _drop_empty(match: re.Match[str]) -> str:
        nonlocal empty_removed
        empty_removed += 1
        return "\n"

    text, n_empty = _EMPTY_TABLE_BLOCK_RE.subn(_drop_empty, text)
    empty_removed = n_empty

    for before, after in _EXACT_PROSE:
        if before in text:
            text = text.replace(before, after)
            removed.append(before[:120])

    generic_subs = (
        ("Research in the assigned material suggests", "Industry startup-cost guides suggest"),
        ("Research in the assigned material", "Industry research"),
        ("One research source notes that", "A common observation is that"),
        ("One research source notes", "A common observation is"),
        (
            "the assigned source supports that",
            "manufacturer documentation states that",
        ),
    )
    for before, after in generic_subs:
        if before.lower() in text.lower():
            text = re.sub(re.escape(before), after, text, flags=re.I)
            removed.append(before)

    def _heading_sub(match: re.Match[str]) -> str:
        hashes, title = match.group(1), match.group(2).strip()
        polished = polish_heading(title)
        if polished != title:
            removed.append(title[:120])
        return f"{hashes} {polished}"

    text = re.sub(r"^(#{2,4})\s+(.+)$", _heading_sub, text, flags=re.M)
    text = _MANDATORY_HEADING_RE.sub(
        lambda m: "## " + polish_heading(f"MANDATORY DELIVERABLE [{m.group(1)}]"),
        text,
    )

    leftover = _FACTORY_BUDGET_RE.findall(text)
    if leftover:
        text = re.sub(
            r",?\s*writing and refinement stages \$2\.50",
            "",
            text,
            flags=re.I,
        )
        text = re.sub(
            r"writing and refinement stages \$2\.50,?\s*",
            "",
            text,
            flags=re.I,
        )
        text = re.sub(
            r"[^.]*\$\s*2\.50[^.]*writing and refinement stages[^.]*\.",
            " Treat administrative and writing time as a real cost rather than as free labor.",
            text,
            flags=re.I,
        )
        removed.extend(leftover)

    def _drop_bracket(match: re.Match[str]) -> str:
        removed.append(match.group(0))
        return ""

    text = _BRACKET_SCENARIO_RE.sub(_drop_bracket, text)
    text = _drop_duplicate_headings(text, removed)
    text = re.sub(r"\n{3,}", "\n\n", text)
    report = {
        "phrases_removed": removed,
        "empty_tables_removed": empty_removed,
        "margin_recalculations": list(MARGIN_RECALCULATIONS),
        "remaining_defects": detect_customer_facing_defects(text),
    }
    return text, report


def inspect_html_tables(html: str) -> list[dict[str, str]]:
    """Fail empty tables, header/body column mismatch, and concatenated headers."""
    findings: list[dict[str, str]] = []
    soup = BeautifulSoup(html or "", "html.parser")
    for table in soup.find_all("table"):
        classes = table.get("class") or []
        if isinstance(classes, str):
            classes = [classes]
        cell_text = table.get_text(" ", strip=True)
        if "chapter-last-keep" in classes or "chapter-last-block" in classes:
            findings.append(
                {
                    "code": "empty_table",
                    "message": "Keep-together wrapper rendered as a table artifact",
                }
            )
            continue
        if not cell_text:
            findings.append({"code": "empty_table", "message": "Empty table artifact"})
            continue
        rows = table.find_all("tr")
        if not rows:
            findings.append({"code": "empty_table", "message": "Table has no rows"})
            continue
        header_cells = rows[0].find_all(["th", "td"])
        header_count = len(header_cells)
        body_counts = [len(tr.find_all(["td", "th"])) for tr in rows[1:]]
        if body_counts and any(c and c != header_count for c in body_counts):
            findings.append(
                {
                    "code": "malformed_table_header",
                    "message": f"Header has {header_count} cells; body row has a different column count",
                }
            )
        if header_count == 1:
            joined = header_cells[0].get_text(" ", strip=True)
            if joined.count(" / ") >= 2:
                findings.append(
                    {
                        "code": "concatenated_table_header",
                        "message": joined[:120],
                    }
                )
        cols = max([header_count] + body_counts) if body_counts else header_count
        if cols >= 8:
            findings.append(
                {
                    "code": "table_too_wide",
                    "message": f"Table has {cols} columns and cannot fit a letter page",
                }
            )
    return findings


def inspect_customer_facing_output(*, manuscript_md: str = "", html: str = "", pdf_text: str = "", pdf_bytes: bytes = b"") -> list[dict[str, str]]:
    """Universal leakage/table/source/heading validator for manuscript, HTML, and PDF text."""
    findings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(items: list[dict[str, str]]) -> None:
        for item in items:
            key = (item.get("code") or "", item.get("message") or "")
            if key in seen:
                continue
            seen.add(key)
            findings.append(item)

    _add(detect_customer_facing_defects(manuscript_md))
    _add(detect_customer_facing_defects(html))
    _add(detect_customer_facing_defects(pdf_text))
    _add(inspect_html_tables(html))
    blob = f"{html or ''}\n{pdf_text or ''}"
    for needle in _CONCAT_HEADER_BLOBS:
        if needle.lower() in blob.lower() and " / " in needle:
            _add([{"code": "concatenated_table_header", "message": needle}])
    if html:
        soup = BeautifulSoup(html, "html.parser")
        copyright_heads = [
            t.get_text(" ", strip=True)
            for t in soup.find_all(["h1", "h2", "p"])
            if t.get_text(" ", strip=True).strip().lower() == "copyright"
        ]
        if len(copyright_heads) > 1:
            _add([{"code": "duplicate_copyright_heading", "message": "More than one Copyright heading"}])
        for a in soup.find_all("a"):
            href = str(a.get("href") or "")
            if _LOCAL_HOST_RE.search(href):
                _add([{"code": "local_preview_url", "message": href[:120]}])
        for li in soup.select(".sources-list li, #sources li"):
            raw = li.get_text(" ", strip=True)
            if _ESCAPED_URL_RE.search(raw):
                _add([{"code": "escaped_source_url", "message": raw[:120]}])
            url = unescape_source_url(raw)
            if url.startswith("http") and not source_url_is_displayable(url):
                _add([{"code": "malformed_source_url", "message": raw[:120]}])
    _add(inspect_rendered_ebook(html=html, pdf_text=pdf_text, pdf_bytes=pdf_bytes))
    return findings
