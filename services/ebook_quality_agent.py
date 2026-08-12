"""
Ebook Content Quality Agent.

Inspects ebook Markdown/text before PDF/ZIP export. Returns a structured
quality result with blocking errors, warnings, and suggested fixes.

This is NOT the rendering QA gate (ebook_qa_validator.py — that handles PDF
formatting). This handles CONTENT quality: specificity, safety, claim accuracy,
and usefulness.

No external API calls — pure Python, fully deterministic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from services.ebook_contract import (
    EbookContract,
    GENERIC_FILLER_PHRASES,
    PLACEHOLDER_PHRASES,
    UNSUPPORTED_CLAIM_PHRASES,
    FOREVER_FORBIDDEN_MARKETING,
    REQUIRED_CHAPTER_ELEMENTS,
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class QualityCheck:
    name: str
    passed: bool
    message: str = ""
    severity: str = "error"   # error | warning


@dataclass
class EbookQualityResult:
    """Result from running ebook content quality checks."""

    passed: bool
    score: int                              # 0-100
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    checks: list[QualityCheck] = field(default_factory=list)
    blocking: bool = False                   # True = do not mark as successful

    def summary(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        lines = [f"[{status}] Score={self.score}/100"]
        for c in self.checks:
            tag = "OK" if c.passed else c.severity.upper()
            lines.append(f"  [{tag}] {c.name}: {c.message}")
        if self.warnings:
            lines.append("  Warnings:")
            for w in self.warnings:
                lines.append(f"    - {w}")
        if self.suggestions:
            lines.append("  Suggestions:")
            for s in self.suggestions:
                lines.append(f"    - {s}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Chapter extraction helpers
# ---------------------------------------------------------------------------

_H2_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)


def _extract_chapters(md_text: str) -> list[tuple[str, str]]:
    """Return [(chapter_title, chapter_content), ...] from Markdown."""
    matches = list(_H2_RE.finditer(md_text))
    if not matches:
        return []
    chapters: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md_text)
        chapters.append((m.group(1).strip(), md_text[start:end].strip()))
    return chapters


def _extract_intro(text: str) -> str:
    """Get the intro paragraph(s) before the first ## heading."""
    idx = text.find("##")
    if idx == -1:
        return text.strip()
    return text[:idx].strip()


def _extract_conclusion(text: str) -> str:
    """Get the last ~800 chars (likely conclusion/summary)."""
    return text[-800:].strip() if text else ""


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text or ""))


def _chapter_word_count(chapters: list[tuple[str, str]]) -> list[int]:
    return [len(re.findall(r"\w+", ch[1])) for ch in chapters]


def _normalize(text: str) -> str:
    return text.lower()


# ---------------------------------------------------------------------------
# Claim detectors
# ---------------------------------------------------------------------------

def _find_unsupported_claims(text: str) -> list[str]:
    """Find phrases that require research but research was not performed."""
    found: list[str] = []
    t = _normalize(text)
    for phrase in UNSUPPORTED_CLAIM_PHRASES:
        if phrase.lower() in t:
            found.append(phrase)
    return found


# Honest disclaimer / risk language that uses a forever-forbidden token in the
# negative ("it is not guaranteed", "nothing is guaranteed"). These must NOT
# trip the marketing gate — the bare hype forms still must.
_FORBIDDEN_NEGATION_BEFORE = re.compile(
    r"(?:"
    r"\bnot\b|"
    r"\bnever\b|"
    r"\bno\b|"
    r"\bwithout\b|"
    r"\bnothing\s+is\b|"
    r"\bisn'?t\b|"
    r"\baren'?t\b|"
    r"\bwasn'?t\b|"
    r"\bweren'?t\b|"
    r"\bcannot\b|"
    r"\bcan'?t\b|"
    r"\bwon'?t\b"
    r")"
    r"(?:\s+\w+){0,3}\s*$",
    re.IGNORECASE,
)


def _has_non_negated_forbidden_phrase(text: str, phrase: str) -> bool:
    """True if ``phrase`` appears at least once without an honest negation."""
    needle = (phrase or "").lower().strip()
    if not needle:
        return False
    start = 0
    while True:
        idx = text.find(needle, start)
        if idx < 0:
            return False
        # Require word-ish boundaries so "secret" does not match inside
        # longer tokens, while still catching multi-word phrases.
        before_ch = text[idx - 1] if idx > 0 else " "
        after_idx = idx + len(needle)
        after_ch = text[after_idx] if after_idx < len(text) else " "
        if before_ch.isalnum() or after_ch.isalnum():
            start = idx + 1
            continue
        window = text[max(0, idx - 48) : idx]
        if not _FORBIDDEN_NEGATION_BEFORE.search(window):
            return True
        start = idx + 1


def _find_forbidden_marketing(text: str) -> list[str]:
    """Find hype/overclaim phrases that are always forbidden.

    Negated disclaimer uses (e.g. "it is not guaranteed") are allowed; bare
    marketing uses of the same tokens still block export.
    """
    found: list[str] = []
    t = _normalize(text)
    for phrase in FOREVER_FORBIDDEN_MARKETING:
        if _has_non_negated_forbidden_phrase(t, phrase):
            found.append(phrase)
    return found


def _find_generic_filler(text: str) -> list[str]:
    """Find repeated generic motivational filler phrases."""
    found: list[str] = []
    t = _normalize(text)
    for phrase in sorted(GENERIC_FILLER_PHRASES, key=len, reverse=True):
        if phrase.lower() in t:
            found.append(phrase)
    return found


def _find_placeholders(text: str) -> list[str]:
    """Find placeholder/generic text that should not appear in finished content."""
    found: list[str] = []
    t = _normalize(text)
    for phrase in sorted(PLACEHOLDER_PHRASES, key=len, reverse=True):
        if phrase.lower() in t:
            found.append(phrase)
    return found


def _find_fake_examples(text: str) -> list[str]:
    """Find example scenarios that are NOT labeled as fictional/sample."""
    # Look for story-like patterns without a clear "Example scenario" label nearby.
    # Patterns like "Meet Sarah, a 42-year-old..." without any disclaimer.
    lines = text.split("\n")
    flagged: list[str] = []
    for i, line in enumerate(lines):
        lower = line.lower().strip()
        # Heuristic: a personal story pattern (name + age +做了什么)
        if re.search(r"\b[A-Z][a-z]+,?\s+a\s+\d+-year-old", line):
            # Check a window of 2 lines before for a label
            window = "\n".join(lines[max(0, i - 2):i + 1]).lower()
            label_indicators = {"example", "sample", "fictional", "scenario", "imagined", "hypothetical", "illustration"}
            if not any(ind in window for ind in label_indicators):
                flagged.append(line.strip()[:80])
    return flagged


def _has_actionable_content(text: str) -> bool:
    """Check whether a chapter contains steps, checklists, or practical methods."""
    indicators = [
        r"\d+\.\s+\w",       # numbered steps: "1. Do X"
        r"step\s+\d",         # "step 1", "step two"
        r"action\s+item",
        r"checklist",
        r"practice\s+this",
        r"try\s+this:",
        r"exercise:",
        r"worksheet",
        r"\bhow to\b.{0,30}\b\d+\b",  # "how to ... in 3 steps"
    ]
    t = _normalize(text)
    return any(re.search(p, t) for p in indicators)


# ---------------------------------------------------------------------------
# Per-chapter analysis
# ---------------------------------------------------------------------------

def _analyze_chapter(
    title: str,
    content: str,
    contract: EbookContract,
    chapter_num: int,
) -> list[QualityCheck]:
    """Analyze one chapter and return a list of quality checks."""
    checks: list[QualityCheck] = []
    t = content.lower()

    # 1. Topic specificity — does the chapter mention the topic?
    topic_words = contract.topic.lower().split()
    topic_mentions = sum(1 for w in topic_words if len(w) > 3 and w in t)
    checks.append(QualityCheck(
        name=f"chapter_{chapter_num}_topic_specificity",
        passed=topic_mentions >= 1,
        message=f"Topic mentions: {topic_mentions}. "
               f"Chapter must address the topic '{contract.topic}'.",
        severity="error" if topic_mentions == 0 else "warning",
    ))

    # 2. Chapter length — too short = filler
    wc = _word_count(content)
    min_words = 120
    checks.append(QualityCheck(
        name=f"chapter_{chapter_num}_depth",
        passed=wc >= min_words,
        message=f"Word count: {wc} (minimum: {min_words}). "
               f"Chapters must have substantive content, not just a few sentences.",
        severity="error" if wc < 60 else "warning",
    ))

    # 3. Actionable content — steps, methods, checklists
    has_action = _has_actionable_content(content)
    checks.append(QualityCheck(
        name=f"chapter_{chapter_num}_practical",
        passed=has_action,
        message="Chapter lacks actionable steps, methods, or checklists.",
        severity="warning",
    ))

    # 4. Common mistakes section
    has_mistakes = any(kw in t for kw in ["mistake", "error", "avoid", "don't", "shouldn't", "common pitfall"])
    checks.append(QualityCheck(
        name=f"chapter_{chapter_num}_mistakes",
        passed=has_mistakes,
        message="No common mistakes or pitfalls section found in chapter.",
        severity="warning",
    ))

    # 5. Unsupported claims in chapter
    unsupported = _find_unsupported_claims(content)
    checks.append(QualityCheck(
        name=f"chapter_{chapter_num}_unsupported_claims",
        passed=len(unsupported) == 0,
        message=f"Unsupported claims found: {unsupported}. "
               f"Research was not requested — these claims cannot be made.",
        severity="error",
    ))

    # 6. Generic filler in chapter
    filler = _find_generic_filler(content)
    checks.append(QualityCheck(
        name=f"chapter_{chapter_num}_generic_filler",
        passed=len(filler) <= 1,  # Allow up to 1 occurrence
        message=f"Generic filler found: {filler}",
        severity="warning",
    ))

    # 7. Placeholder text
    placeholders = _find_placeholders(content)
    checks.append(QualityCheck(
        name=f"chapter_{chapter_num}_placeholder",
        passed=len(placeholders) == 0,
        message=f"Placeholder text found: {placeholders}",
        severity="error",
    ))

    # 8. Fake unlabeled examples
    fake_examples = _find_fake_examples(content)
    checks.append(QualityCheck(
        name=f"chapter_{chapter_num}_fake_examples",
        passed=len(fake_examples) == 0,
        message=f"Potentially unlabeled fictional stories/examples: {fake_examples}. "
               f"Label examples as 'Example scenario:' or 'Sample situation:'.",
        severity="warning",
    ))

    return checks


# ---------------------------------------------------------------------------
# Main quality check function
# ---------------------------------------------------------------------------

def validate_ebook_content(
    md_text: str,
    contract: EbookContract,
    title: str = "",
) -> EbookQualityResult:
    """
    Run all content quality checks against ebook Markdown text.

    Args:
        md_text: The raw ebook Markdown (from generate_ebook or ebook_package).
        contract: The EbookContract that guided generation.
        title: Optional ebook title for context.

    Returns:
        EbookQualityResult with passed/failed, score, blocking errors, warnings.
    """
    errors: list[str] = []
    warnings: list[str] = []
    suggestions: list[str] = []
    checks: list[QualityCheck] = []
    blocking_count = 0

    t = _normalize(md_text)

    # ── 1. Placeholder/generic content check ──────────────────────────────────
    placeholders = _find_placeholders(md_text)
    if placeholders:
        errors.append(f"Placeholder text found: {placeholders}")
        checks.append(QualityCheck(
            "placeholder_content", False,
            f"Found: {placeholders}", "error"
        ))
        blocking_count += 1
    else:
        checks.append(QualityCheck("placeholder_content", True))

    # ── 1b. Visual-production instructions must never enter customer manuscript ─
    from services.ebook_document import find_customer_content_defects

    content_defects = find_customer_content_defects(md_text)
    leak_defects = [
        d for d in content_defects
        if d.startswith("leaked_visual_instruction")
        or d.startswith("blocked_customer_phrase")
    ]
    if leak_defects:
        errors.append(f"Manuscript content defects: {leak_defects[:8]}")
        checks.append(QualityCheck(
            "customer_content_integrity", False,
            f"Found: {leak_defects[:6]}", "error"
        ))
        blocking_count += 1
    else:
        checks.append(QualityCheck("customer_content_integrity", True))

    # ── 2. Forbidden marketing/overclaim check ────────────────────────────────
    forbidden = _find_forbidden_marketing(md_text)
    if forbidden:
        errors.append(f"Forever-forbidden marketing claims found: {forbidden}")
        checks.append(QualityCheck(
            "forbidden_marketing_claims", False,
            f"Found: {forbidden}", "error"
        ))
        blocking_count += 1
    else:
        checks.append(QualityCheck("forbidden_marketing_claims", True))

    # ── 3. Unsupported research claims (only errors if research NOT done) ──────
    if not contract.research_requested:
        unsupported = _find_unsupported_claims(md_text)
        if unsupported:
            errors.append(
                f"Research-dependent claims found but research was NOT performed: "
                f"{unsupported}. Do not claim 'cutting-edge research', "
                f"'fact-checked', 'scientifically proven', or similar phrases "
                f"without actual evidence."
            )
            checks.append(QualityCheck(
                "unsupported_research_claims", False,
                f"Found: {unsupported}", "error"
            ))
            blocking_count += 1
        else:
            checks.append(QualityCheck("unsupported_research_claims", True))
    else:
        # Research was done — only flag if there are still forbidden claims
        checks.append(QualityCheck(
            "unsupported_research_claims", True,
            "Research was requested — claims allowed.", "warning"
        ))

    # ── 4. Disclaimer check (health/finance/legal topics) ──────────────────
    if contract.disclaimer_required:
        has_disclaimer = any(
            phrase in t
            for phrase in [
                "consult your physician",
                "consult a qualified",
                "consult a licensed",
                "not a substitute for professional",
                "not intended to diagnose",
                "educational and informational purposes only",
                "no warranties",
                "accept no liability",
            ]
        )
        if not has_disclaimer:
            errors.append(
                f"Disclaimer required for topic category {contract.risk_categories} "
                f"but no disclaimer found. Required text:\n{contract.disclaimer_text[:200]}..."
            )
            checks.append(QualityCheck(
                "disclaimer_present", False,
                "Disclaimer required but not found.", "error"
            ))
            blocking_count += 1
        else:
            checks.append(QualityCheck("disclaimer_present", True))
    else:
        checks.append(QualityCheck("disclaimer_present", True, "Disclaimer not required."))

    # ── 5. Chapter count check ───────────────────────────────────────────────
    chapters = _extract_chapters(md_text)
    if len(chapters) < 4:
        errors.append(
            f"Only {len(chapters)} chapters found. Standard ebooks need at least "
            f"5 meaningful chapters. Thin ebooks cannot be marked as complete products."
        )
        checks.append(QualityCheck(
            "chapter_count", False,
            f"Found {len(chapters)} chapters, need at least 4.", "error"
        ))
        blocking_count += 1
    elif len(chapters) < 5:
        warnings.append(
            f"Only {len(chapters)} chapters — consider expanding to 5-8 for a full ebook."
        )
        checks.append(QualityCheck(
            "chapter_count", False,
            f"Found {len(chapters)} chapters (warning, not blocking).", "warning"
        ))
    else:
        checks.append(QualityCheck(
            "chapter_count", True,
            f"{len(chapters)} chapters — adequate."
        ))

    # ── 6. Chapter depth check (average word count) ────────────────────────
    if chapters:
        counts = _chapter_word_count(chapters)
        avg = sum(counts) / len(counts) if counts else 0
        min_avg = 150
        if avg < min_avg:
            errors.append(
                f"Average chapter word count is {avg:.0f} — below minimum of "
                f"{min_avg} words. Chapters may be too thin to be useful."
            )
            checks.append(QualityCheck(
                "chapter_depth_average", False,
                f"Avg {avg:.0f} words/chapter (min: {min_avg}).", "error"
            ))
            blocking_count += 1
            suggestions.append(
                "Expand each chapter with topic-specific structure: explanation, "
                "a concrete example or script, practical guidance, and a descriptive "
                "closing action — vary headings across chapters."
            )
        else:
            checks.append(QualityCheck(
                "chapter_depth_average", True,
                f"Avg {avg:.0f} words/chapter — adequate."
            ))

        # ── 7. Per-chapter analysis ───────────────────────────────────────────
        for i, (ch_title, ch_content) in enumerate(chapters):
            ch_checks = _analyze_chapter(ch_title, ch_content, contract, i + 1)
            checks.extend(ch_checks)
            for c in ch_checks:
                if not c.passed:
                    if c.severity == "error":
                        blocking_count += 0.5
                    else:
                        warnings.append(f"[Chapter {i+1}] {c.message}")

    # ── 8. Repetition / generic filler across whole ebook ────────────────────
    filler = _find_generic_filler(md_text)
    if len(filler) >= 3:
        errors.append(
            f"Repetitive generic filler found ({len(filler)} occurrences): "
            f"{filler}. Each chapter must be unique and topic-specific."
        )
        checks.append(QualityCheck(
            "repetition_control", False,
            f"Filler phrases: {filler}", "error"
        ))
        blocking_count += 1
    elif filler:
        warnings.append(f"Some generic filler phrases found: {filler}")
        checks.append(QualityCheck(
            "repetition_control", False,
            f"Filler phrases: {filler}", "warning"
        ))
    else:
        checks.append(QualityCheck("repetition_control", True))

    # ── 9. Conclusion/summary quality ─────────────────────────────────────
    conclusion = _extract_conclusion(md_text)
    if conclusion:
        conc_wc = _word_count(conclusion)
        if conc_wc < 50:
            warnings.append(
                f"Conclusion appears very short ({conc_wc} words). "
                "Ensure it summarizes key takeaways specifically, not just generic motivation."
            )
            checks.append(QualityCheck(
                "conclusion_quality", False,
                f"Conclusion word count: {conc_wc} (very short).", "warning"
            ))
        else:
            checks.append(QualityCheck("conclusion_quality", True))

    # ── 10. Worksheet/workbook alignment ────────────────────────────────────
    if contract.worksheet_required:
        has_action_steps = bool(
            re.search(r"(action|worksheet|exercise|checklist|practice)", conclusion.lower())
        )
        if not has_action_steps:
            warnings.append(
                "Worksheet was requested but no action-steps/worksheet content found "
                "in conclusion/action section."
            )
            checks.append(QualityCheck(
                "worksheet_alignment", False,
                "Worksheet requested but not clearly present.", "warning"
            ))
        else:
            checks.append(QualityCheck("worksheet_alignment", True))

    # ── Compute score ──────────────────────────────────────────────────────
    total_checks = len(checks)
    passed_checks = sum(1 for c in checks if c.passed)
    error_count = sum(1 for c in checks if not c.passed and c.severity == "error")

    # Score: 100 base minus penalties
    score = 100
    score -= error_count * 12
    score -= (total_checks - passed_checks - error_count) * 4
    score = max(0, min(100, score))

    # Blocking: more than 3 errors = blocking
    blocking = blocking_count >= 3 or error_count >= 3
    passed = not blocking and len(errors) == 0

    # If score is very low, also block
    if score < 35:
        blocking = True
        if "Content quality score too low to export." not in errors:
            errors.insert(0, f"Content quality score too low to export: {score}/100. "
                             f"The ebook needs significant improvement before export.")

    result = EbookQualityResult(
        passed=passed,
        score=score,
        errors=errors,
        warnings=warnings,
        suggestions=suggestions,
        checks=checks,
        blocking=blocking,
    )
    return result


# ---------------------------------------------------------------------------
# User-facing message builder
# ---------------------------------------------------------------------------

def blocking_message(result: EbookQualityResult, topic: str = "") -> str:
    """Build a user-facing message when ebook quality is too low to export."""
    if result.passed:
        return "Ebook passed quality checks."

    lines = [
        "This ebook needs more topic-specific content before it can be marked as complete.",
        "",
    ]

    if result.errors:
        lines.append("Issues found:")
        for err in result.errors[:5]:
            lines.append(f"  - {err}")
        if len(result.errors) > 5:
            lines.append(f"  ... and {len(result.errors) - 5} more.")

    if result.suggestions:
        lines.append("")
        lines.append("How to improve:")
        for s in result.suggestions[:3]:
            lines.append(f"  - {s}")

    lines.append("")
    if topic:
        lines.append(
            f"Please revise the draft with more specific content about '{topic}', "
            f"or regenerate with a more specific topic and audience."
        )
    else:
        lines.append(
            "Please revise the draft with more specific content, "
            "a clearer audience, and concrete examples."
        )

    return "\n".join(lines)
