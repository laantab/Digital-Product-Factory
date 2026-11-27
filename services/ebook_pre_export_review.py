"""Deterministic Editor-in-Chief checks that run before ebook PDF rendering.

This gate checks the actual manuscript and visual copy that will be typeset.
It is deliberately conservative: safe spelling fixes are already applied and
logged by the chapter pipeline; this module blocks clear defects instead of
guessing at facts or completing an author's sentence.
"""
from __future__ import annotations

import re
import hashlib


RULESET_VERSION = "pre-export-eic-v1"


class PreExportReviewBlocked(ValueError):
    """The manuscript needs a correction before any PDF can be rendered."""

    def __init__(self, report: dict):
        self.report = report
        first = next(iter(report.get("findings") or []), {})
        detail = str(first.get("summary") or "Editor-in-Chief review needs correction.")
        super().__init__(detail)

_DANGLING_ENDINGS = frozenset({
    "a", "an", "and", "are", "as", "at", "because", "be", "been", "but",
    "by", "can", "could", "for", "from", "had", "has", "have", "if", "in",
    "into", "is", "it", "may", "might", "must", "of", "on", "or", "should",
    "since", "than", "that", "the", "then", "to", "was", "were", "when",
    "which", "while", "who", "with", "would",
})
_PRODUCTION_LANGUAGE = re.compile(
    r"\b(?:workflow graphic for|comparison graphic for|timeline graphic for|"
    r"follow the chapter steps in order|insert (?:an? )?(?:image|graphic|diagram)|"
    r"image placeholder|visual placeholder|production note)\b",
    re.I,
)
_URL = re.compile(r"https?://[^\s)\]]+", re.I)


def _clean_sentence(text: str) -> str:
    normalized = re.sub(r"\s+", " ", re.sub(r"[`*_~]", "", text)).strip().lower()
    return re.sub(r"[.!?…]+$", "", normalized).strip()


def _prose_paragraphs(markdown: str):
    """Yield prose paragraphs, leaving headings, lists, tables and code alone."""
    chunks = re.split(r"\n\s*\n", str(markdown or ""))
    in_fence = False
    fence_char = ""
    for chunk in chunks:
        value = chunk.strip()
        if not value:
            continue
        if re.match(r"^(`{3,}|~{3,})", value):
            marker = value[0]
            if not in_fence:
                in_fence, fence_char = True, marker
            elif marker == fence_char:
                in_fence = False
            continue
        if in_fence or value.startswith(("#", ">", "|", "- ", "* ", "+ ")):
            continue
        if re.match(r"^\d+[.)]\s", value):
            continue
        yield value


def review_before_pdf(data: dict, *, rendered_html: str = "") -> dict:
    """Return a revision-bound manuscript/visual-copy gate; never calls a provider."""
    manuscript = str(data.get("content") or data.get("ebook") or "")
    visual_plan = data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else {}
    findings: list[dict] = []

    # Check full sentence duplication across the manuscript, including cases
    # where the repeated sentence is separated into different paragraphs.
    seen: dict[str, int] = {}
    for paragraph in _prose_paragraphs(manuscript):
        for sentence in re.split(r"(?<=[.!?])\s+", paragraph):
            normalized = _clean_sentence(sentence)
            if len(normalized.split()) >= 9:
                seen[normalized] = seen.get(normalized, 0) + 1
    for sentence, count in seen.items():
        if count > 1:
            findings.append({
                "code": "REPEATED_SENTENCE", "severity": "major",
                "summary": "A full sentence is repeated in the manuscript.",
                "detail": sentence[:220], "occurrences": count,
                "action": "Keep the intended occurrence and remove the duplicate.",
            })

    # Catch a prose paragraph cut off at a conjunction/article/preposition.
    # It is a review flag, never an automatic completion of missing author text.
    for index, paragraph in enumerate(_prose_paragraphs(manuscript), 1):
        words = re.findall(r"[A-Za-z]+", paragraph)
        has_terminal_punctuation = bool(re.search(r"[.!?…][\"”’')\]]*\s*$", paragraph))
        if (len(words) >= 8 and words[-1].lower() in _DANGLING_ENDINGS
                and not has_terminal_punctuation):
            findings.append({
                "code": "INCOMPLETE_PARAGRAPH", "severity": "major",
                "summary": "A prose paragraph appears to stop before its sentence is complete.",
                "detail": paragraph[-240:], "paragraph": index,
                "action": "Complete the sentence from the author's source; the reviewer will not invent the missing words.",
            })

    # Review visible strings in visual aids as well as manuscript prose.
    aids = []
    for chapter in visual_plan.get("chapters") or []:
        if not isinstance(chapter, dict):
            continue
        for aid in chapter.get("aids") or []:
            if isinstance(aid, dict):
                aids.append(aid)
    html_blob = str(rendered_html or "")
    visible_seen: dict[str, int] = {}
    if html_blob:
        try:
            from bs4 import BeautifulSoup

            soup = BeautifulSoup(html_blob, "html.parser")
            for node in soup.find_all(["p", "figcaption", "li"]):
                for sentence in re.split(r"(?<=[.!?])\s+", node.get_text(" ", strip=True)):
                    normalized = _clean_sentence(sentence)
                    if len(normalized.split()) >= 9:
                        visible_seen[normalized] = visible_seen.get(normalized, 0) + 1
        except Exception:  # malformed/unsupported HTML is caught by post-render checks
            pass
    for sentence, count in visible_seen.items():
        if count > 1 and not any(
            f.get("code") == "REPEATED_SENTENCE" and f.get("detail") == sentence[:220]
            for f in findings
        ):
            findings.append({
                "code": "REPEATED_SENTENCE", "severity": "major",
                "summary": "A full sentence is repeated in the rendered book text.",
                "detail": sentence[:220], "occurrences": count,
                "action": "Keep the intended occurrence and remove the duplicate.",
            })
    for aid in aids:
        for field in ("title", "caption", "alt", "description"):
            value = str(aid.get(field) or "")
            if _PRODUCTION_LANGUAGE.search(value):
                findings.append({
                    "code": "PRODUCTION_COPY_LEAK", "severity": "major",
                    "summary": "A visual contains internal production wording.",
                    "detail": value[:240],
                    "asset": str(aid.get("visual_id") or aid.get("title") or ""),
                    "action": "Replace the production instruction with a reader-facing caption.",
                })

    visible_source = manuscript + "\n" + "\n".join(
        " ".join(str(aid.get(k) or "") for k in ("title", "caption", "alt", "description"))
        for aid in aids
    ) + "\n" + html_blob
    for match in _URL.finditer(visible_source):
        if "…" in match.group(0) or "..." in match.group(0):
            findings.append({
                "code": "TRUNCATED_SOURCE_URL", "severity": "major",
                "summary": "A source URL appears to be truncated.",
                "detail": match.group(0)[:240],
                "action": "Restore and verify the complete source link.",
            })
    if _PRODUCTION_LANGUAGE.search(manuscript) or _PRODUCTION_LANGUAGE.search(html_blob):
        findings.append({
            "code": "PRODUCTION_NOTE_LEAK", "severity": "major",
            "summary": "Internal production wording appears in customer-facing book copy.",
            "action": "Replace it with finished reader-facing copy.",
        })

    # The existing release checker catches unresolved placeholders. Reuse its
    # objective rule rather than maintaining a second placeholder vocabulary.
    from services.editor_in_chief import check_placeholder_and_leak
    for finding in check_placeholder_and_leak(manuscript):
        findings.append({
            "code": finding.code, "severity": str(finding.severity).lower(),
            "summary": finding.summary, "detail": finding.detail,
            "action": "Remove or replace the unresolved placeholder before rendering.",
        })

    identity = hashlib.sha256(manuscript.encode("utf-8")).hexdigest()
    blockers = [f for f in findings if f.get("severity") in {"major", "critical"}]
    return {
        "ruleset_version": RULESET_VERSION,
        "status": "PASS" if not blockers else "NEEDS_CORRECTION",
        "manuscript_digest": identity,
        "paid_calls": 0,
        "reviewed_before_pdf": True,
        "findings": findings,
        "next_action": blockers[0]["action"] if blockers else "Continue to PDF rendering.",
    }
