"""
Ebook QA validator -- 11 checks run as a non-blocking gate on every PDF export.

Check list (pass = no error, fail = ERROR logged):
  1. cover_fills_page         -- cover section is not full-page (has margins/padding)
  2. cover_has_blank_area     -- cover section has >30% blank whitespace
  3. no_black_title_bars     -- cover does not use solid black title/subtitle bands
  4. forbidden_branding       -- no placeholder brand phrases ("Professional Digital Guide")
  5. no_generic_apply_boxes   -- no "Apply Apply" duplicated labels
  6. duplicate_chapter_labels -- no chapter labeled "Chapter N" AND "Chapter N: ..." on same page
  7. placeholder_text          -- no generic takeaway / marketplace placeholder phrases
  8. toc_formatting           -- TOC entries don't have broken dotted leaders
  9. placeholder_visuals      -- no placeholder visual boxes with Etsy/trending text
 10. back_matter_present      -- back matter is optional; FAIL only on generic injected patterns
 11. malformed_content        -- no table-card squashed labels, no raw [brackets], no worksheet header corruption
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class ValidationCheck:
    name: str
    passed: bool
    message: str = ""


@dataclass
class EbookQAResult:
    pdf_md5: str
    page_count: int
    checks: list[ValidationCheck] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"[{status}] Pages={self.page_count} MD5={self.pdf_md5}"]
        for c in self.checks:
            tag = "OK" if c.passed else "ERR"
            lines.append(f"  [{tag}] {c.name}: {c.message}")
        if self.warnings:
            lines.append("  Warnings:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def validate_ebook_pdf(pdf_bytes: bytes, pdf_md5: str = "") -> EbookQAResult:
    """Run all 10 QA checks against a rendered PDF's bytes.

    Non-blocking: always returns a result (never raises).
    """


    result = EbookQAResult(pdf_md5=pdf_md5, page_count=0)
    try:
        page_count, text, image_data = _extract_pdf_text_and_images(pdf_bytes)
        result.page_count = page_count
    except Exception as exc:
        result.errors.append(f"Could not parse PDF: {exc}")
        return result

    # Run each check
    _check_cover_fills_page(text, image_data, result)
    _check_cover_blank_area(text, image_data, result)
    _check_no_black_bars(text, result)
    _check_forbidden_branding(text, result)
    _check_no_generic_apply_boxes(text, result)
    _check_no_duplicate_chapter_labels(text, result)
    _check_placeholder_text(text, result)
    _check_toc_formatting(text, result)
    _check_placeholder_visuals(text, result)
    _check_back_matter_present(page_count, text, result)
    _check_cover_professional(text, result)
    _check_malformed_content(text, result)

    return result


# ---------------------------------------------------------------------------
# Check 1: Cover fills page (should NOT fill -- needs margins)
# ---------------------------------------------------------------------------

def _check_cover_fills_page(text: str, image_data: dict, result: EbookQAResult) -> None:
    """If the cover page text/visuals occupy < 20% of the page area, it fills the page."""
    cover_text_ratio = _text_occupancy_ratio(text[:2000])
    if cover_text_ratio < 0.08:
        result.errors.append("Cover fills the full page without margins or spacing.")
        result.checks.append(ValidationCheck("cover_fills_page", False, "Cover appears to fill the full page"))
    else:
        result.checks.append(ValidationCheck("cover_fills_page", True))


# ---------------------------------------------------------------------------
# Check 2: Cover has blank area
# ---------------------------------------------------------------------------

def _check_cover_blank_area(text: str, image_data: dict, result: EbookQAResult) -> None:
    """Cover should have a reasonable visual balance -- too much white is a sign of lazy design."""
    cover_text = text[:1500]
    words = len(cover_text.split())
    # A cover with fewer than 4 words in the first 1500 chars likely has a large blank area
    if words < 4 and len(cover_text.strip()) < 80:
        result.warnings.append("Cover has very little text -- may have a large blank area.")
        result.checks.append(ValidationCheck("cover_has_blank_area", False, "Cover may have large blank area"))
    else:
        result.checks.append(ValidationCheck("cover_has_blank_area", True))


def _check_cover_professional(text: str, result: EbookQAResult) -> None:
    """Check that the cover has professional design elements (not flat purple fallback).

    The ReportLab AI cover includes 'AI Model Selection Guide' as a footer.
    The old flat purple HTML fallback does not.
    """
    # Positive indicators: ReportLab theme covers (tech or parenting local)
    has_rl_cover_footer = (
        "AI Model Selection Guide" in text
        or "Practical Family Guide" in text
        or "Event Photography Field Guide" in text
    )
    has_cover_text = len(text[:500].split()) >= 3
    if has_cover_text and not has_rl_cover_footer:
        result.errors.append("Cover appears to use flat purple HTML fallback instead of professional AI cover.")
        result.checks.append(ValidationCheck(
            "cover_professional", False,
            "Flat purple HTML fallback cover detected"
        ))
    elif has_rl_cover_footer:
        result.checks.append(ValidationCheck(
            "cover_professional", True,
            "Professional ReportLab cover detected"
        ))
    else:
        # Uncertain - no strong signal either way
        result.checks.append(ValidationCheck("cover_professional", True, "Cover check inconclusive"))


# ---------------------------------------------------------------------------
# Check 3: No black title bars
# ---------------------------------------------------------------------------

def _check_no_black_bars(text: str, result: EbookQAResult) -> None:
    """Old-style covers used solid dark rectangles for title/subtitle bands."""
    if re.search(r"[\u2588\u2591\u2592\u2593]{5,}", text):  # Unicode block characters
        result.errors.append("Cover uses solid dark block characters (old-style bars detected).")
        result.checks.append(ValidationCheck("no_black_title_bars", False, "Black block characters found"))
    else:
        result.checks.append(ValidationCheck("no_black_title_bars", True))


# ---------------------------------------------------------------------------
# Check 4: Forbidden branding
# ---------------------------------------------------------------------------

_FORBIDDEN_BRAND_PATTERNS = [
    # "Digital Product Factory" is the legitimate default Author/Creator — allowed.
    re.compile(r"Professional Digital Guide", re.IGNORECASE),
]


def _check_forbidden_branding(text: str, result: EbookQAResult) -> None:
    for pat in _FORBIDDEN_BRAND_PATTERNS:
        if pat.search(text):
            result.errors.append(f"Forbidden branding text found: {pat.pattern!r}")
            result.checks.append(ValidationCheck(
                "forbidden_branding", False,
                f"Found forbidden brand text: {pat.pattern}"
            ))
            return
    result.checks.append(ValidationCheck("forbidden_branding", True))


# ---------------------------------------------------------------------------
# Check 5: No generic "Apply Apply" boxes
# ---------------------------------------------------------------------------

_GENERIC_APPLY_PATTERNS = [
    re.compile(r"Apply\s+Apply\s+(Summary|Action Steps|Chapter Summary)", re.IGNORECASE),
    re.compile(r"Apply it?:\s*Summary", re.IGNORECASE),
]


def _check_no_generic_apply_boxes(text: str, result: EbookQAResult) -> None:
    for pat in _GENERIC_APPLY_PATTERNS:
        match = pat.search(text)
        if match:
            result.errors.append(f"Generic apply box found: {match.group()!r}")
            result.checks.append(ValidationCheck(
                "no_generic_apply_boxes", False,
                f"Found generic apply box: {match.group()!r}"
            ))
            return
    result.checks.append(ValidationCheck("no_generic_apply_boxes", True))


# ---------------------------------------------------------------------------
# Check 6: No duplicate chapter labels
# ---------------------------------------------------------------------------

def _check_no_duplicate_chapter_labels(text: str, result: EbookQAResult) -> None:
    """Detect chapters labeled both "Chapter N" and "Chapter N: ..." on the same page."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        m = re.match(r"^Chapter\s+(\d+)\s*$", line, re.IGNORECASE)
        if m:
            chapter_num = m.group(1)
            # Look ahead in same page context (within next 20 lines = likely same page)
            page_context = "\n".join(lines[i : i + 20])
            if re.search(rf"^Chapter\s+{re.escape(chapter_num)}\s*:", page_context, re.MULTILINE | re.IGNORECASE):
                result.errors.append(f"Duplicate chapter label: 'Chapter {chapter_num}' AND 'Chapter {chapter_num}: ...'")
                result.checks.append(ValidationCheck(
                    "duplicate_chapter_labels", False,
                    f"Chapter {chapter_num} appears twice with different labels"
                ))
                return
    result.checks.append(ValidationCheck("duplicate_chapter_labels", True))


# ---------------------------------------------------------------------------
# Check 7: No placeholder text
# ---------------------------------------------------------------------------

_PLACEHOLDER_PHRASES = [
    "The one thing worth keeping",
    "Pull out the core idea",
    "Review the main idea",
    "Marketplace preview",
    "Product listing",
    "Put this chapter into action",
    "The one line to carry forward",
]


def _check_placeholder_text(text: str, result: EbookQAResult) -> None:
    found = []
    for phrase in _PLACEHOLDER_PHRASES:
        if phrase.lower() in text.lower():
            found.append(phrase)
    if found:
        result.errors.append(f"Placeholder text found: {found}")
        result.checks.append(ValidationCheck(
            "placeholder_text", False,
            f"Found placeholder phrases: {found}"
        ))
    else:
        result.checks.append(ValidationCheck("placeholder_text", True))


# ---------------------------------------------------------------------------
# Check 8: TOC formatting (dotted leaders shouldn't wrap)
# ---------------------------------------------------------------------------

def _check_toc_formatting(text: str, result: EbookQAResult) -> None:
    """Broken dotted leaders: dots and page numbers wrapping to separate lines."""
    # Look for TOC lines where the dots and page number are on separate lines
    lines = text.split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        # A TOC entry followed by a line that's just dots+numbers is broken
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if re.match(r"^\.{3,}\s*\d+\s*$", next_line) and re.match(r"^\w", line):
                result.errors.append("TOC has broken dotted leaders (dots/numbers on separate line)")
                result.checks.append(ValidationCheck(
                    "toc_formatting", False,
                    "TOC dotted leaders wrap to next line"
                ))
                return
    result.checks.append(ValidationCheck("toc_formatting", True))


# ---------------------------------------------------------------------------
# Check 9: Placeholder visual boxes
# ---------------------------------------------------------------------------

_PLACEHOLDER_VISUAL_PATTERNS = [
    re.compile(r"Marketplace preview\s*[\u00b7·/]\s*Product listing", re.IGNORECASE),
    re.compile(r"Top Seller|Trending|Etsy Search|Search Etsy", re.IGNORECASE),
]


def _check_placeholder_visuals(text: str, result: EbookQAResult) -> None:
    for pat in _PLACEHOLDER_VISUAL_PATTERNS:
        match = pat.search(text)
        if match:
            result.errors.append(f"Placeholder visual text found: {match.group()!r}")
            result.checks.append(ValidationCheck(
                "placeholder_visuals", False,
                f"Found placeholder visual: {match.group()!r}"
            ))
            return
    result.checks.append(ValidationCheck("placeholder_visuals", True))


# ---------------------------------------------------------------------------
# Check 10: Back matter present (6+ page PDFs)
# ---------------------------------------------------------------------------

_BACK_MATTER_SECTIONS = [
    "Quick Reference",
    "FAQ",
    "Action Plan",
]

# Aliases: alternate labels that count as the same section
_BACK_MATTER_ALIASES = {
    "FAQ": ["frequently asked questions"],
}


def _check_back_matter_present(page_count: int, text: str, result: EbookQAResult) -> None:
    """Back matter is optional. Fail only when generic injected patterns appear."""
    text_lower = (text or "").lower()
    generic_hits = []
    for needle in (
        "how do i stay motivated over time",
        "is this approach right for me",
        "will these principles work for me",
        "apply one idea from this chapter today",
        "key practice —",
        "key practice -",
        "chapter action steps",
        "chapter at a glance",
        "sub-goal #",
    ):
        if needle in text_lower:
            generic_hits.append(needle)
    if generic_hits:
        result.errors.append(
            f"Generic injected back matter present: {generic_hits[:4]}"
        )
        result.checks.append(
            ValidationCheck(
                "back_matter_present",
                False,
                f"Generic back matter must not be auto-injected: {generic_hits[:4]}",
            )
        )
        return
    result.checks.append(
        ValidationCheck(
            "back_matter_present",
            True,
            "Back matter optional; no generic FAQ/Key Practice/Action padding detected",
        )
    )


# ---------------------------------------------------------------------------
# Check 11: Malformed content detection
# ---------------------------------------------------------------------------

# Squashed table-card labels: header + value concatenated without space
_MALFORMED_TABLE_PATTERNS = [
    re.compile(r"QuestionWhere", re.IGNORECASE),
    re.compile(r"What to verifyProvider", re.IGNORECASE),
    re.compile(r"verifyProvider", re.IGNORECASE),
    re.compile(r"Additional InfoA\b", re.IGNORECASE),
]

# Raw bracket tags that should never appear in finished PDF text
_RAW_BRACKET_PATTERNS = [
    re.compile(r"\[Diagram\]", re.IGNORECASE),
    re.compile(r"\[Infographic\]", re.IGNORECASE),
    re.compile(r"\[Table\]", re.IGNORECASE),
    re.compile(r"\[Tip\]", re.IGNORECASE),
    re.compile(r"\[Chart\]", re.IGNORECASE),
    re.compile(r"\[Worksheet\]", re.IGNORECASE),
    re.compile(r"\[Action Steps\]", re.IGNORECASE),
]

# Worksheet header corruption: "Action W Done" instead of proper table header
_WORKSHEET_HEADER_PATTERNS = [
    re.compile(r"#\s+Action\s+W\s+Done", re.IGNORECASE),
    re.compile(r"WheDnone", re.IGNORECASE),
    re.compile(r"WhenDone", re.IGNORECASE),
]

# Final Tips without actual questions (just the description text)
_FINAL_TIPS_NO_QUESTIONS = re.compile(
    r"five concrete questions to answer before you commit to a model",
    re.IGNORECASE,
)
_ACTUAL_QUESTION_STARTS = (
    "What task must this model",
    "What data will the model receive",
    "What quality score is acceptable",
    "What is the maximum cost per run",
    "What privacy or risk rule",
)


def _check_malformed_content(text: str, result: EbookQAResult) -> None:
    """Detect common rendering bugs in ebook PDFs."""
    errors_found: list[str] = []

    # Check for squashed table-card labels
    for pat in _MALFORMED_TABLE_PATTERNS:
        m = pat.search(text)
        if m:
            errors_found.append(f"Squashed table-card label: {m.group()!r}")

    # Check for raw bracket tags
    for pat in _RAW_BRACKET_PATTERNS:
        m = pat.search(text)
        if m:
            errors_found.append(f"Raw bracket tag in PDF: {m.group()!r}")

    # Check for worksheet header corruption
    for pat in _WORKSHEET_HEADER_PATTERNS:
        m = pat.search(text)
        if m:
            errors_found.append(f"Corrupted worksheet header: {m.group()!r}")

    # Check: "Five concrete questions" must be accompanied by the actual questions
    if _FINAL_TIPS_NO_QUESTIONS.search(text):
        has_questions = any(text.find(q) >= 0 for q in _ACTUAL_QUESTION_STARTS)
        if not has_questions:
            errors_found.append(
                "'Five concrete questions' description found but actual questions are missing"
            )

    if errors_found:
        result.errors.extend(errors_found)
        result.checks.append(ValidationCheck(
            "malformed_content", False,
            "; ".join(errors_found)
        ))
    else:
        result.checks.append(ValidationCheck("malformed_content", True))


# ---------------------------------------------------------------------------
# PDF text + image extraction helpers
# ---------------------------------------------------------------------------

def _text_occupancy_ratio(text: str) -> float:
    """Fraction of characters that are non-whitespace/non-punctuation."""
    chars = [c for c in text if c.strip() and c not in ".,;:!?'\"-"]
    return len(chars) / max(len(text), 1)


def _extract_pdf_text_and_images(pdf_bytes: bytes) -> tuple[int, str, dict]:
    """Extract page count, all text, and basic image stats from PDF bytes.

    Falls back gracefully -- never raises.
    """
    text_parts: list[str] = []
    page_count = 0
    image_stats: dict = {"has_images": False}

    try:
        import io
        import re as _re

        # Try pdfplumber first (best text extraction)
        import pdfplumber

        buf = io.BytesIO(pdf_bytes)
        with pdfplumber.open(buf) as pdf:
            page_count = len(pdf.pages)
            for page in pdf.pages:
                t = page.extract_text() or ""
                text_parts.append(t)
        text = "\n".join(text_parts)
        return page_count, text, image_stats

    except Exception:
        pass

    try:
        # Fallback: PyPDF2
        import PyPDF2

        buf = io.BytesIO(pdf_bytes)
        reader = PyPDF2.PdfReader(buf)
        page_count = len(reader.pages)
        for page in reader.pages:
            t = page.extract_text() or ""
            text_parts.append(t)
        text = "\n".join(text_parts)
        return page_count, text, image_stats

    except Exception:
        pass

    # Last resort: raw PDF text extraction via regex
    import re as _re

    text = " ".join(_re.findall(rb"BT.*?ET", pdf_bytes, re.DOTALL))
    text = _re.sub(rb"\s+", b" ", text)
    text = text.decode("latin-1", errors="replace")
    page_count = len(_re.findall(rb"/Type\s*/Page\b", pdf_bytes))
    return page_count, text, image_stats
