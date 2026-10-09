"""Offline English copy editing, with reversible edits and honest coverage.

This is a conservative rules editor, not semantic fact checking or a complete
English grammar engine. Ambiguous changes are suggestions, never silent edits.
"""
from __future__ import annotations

import hashlib
import re

VERSION = "1"
SPELLING = {
    "teh": "the", "recieve": "receive", "seperate": "separate",
    "definately": "definitely", "occured": "occurred", "untill": "until",
    "becuase": "because", "wich": "which", "thier": "their",
}
# Protect source material and Markdown syntax. Never edit quotations, URLs,
# code, tables, headings, image captions, or quoted source blocks.
PROTECTED = re.compile(
    r'(`+[^`\n]*`+|!?\[[^\]\n]*\]\([^\)\n]*\)|https?://[^\s]+|'
    r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\'[^\'\n]+\'(?!\w)|‘[^’\n]*’)'
)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _case(source: str, replacement: str) -> str:
    if source.isupper():
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def edit_text(text: str, *, target_grade: int = 8) -> dict:
    """Return an edited draft plus an auditable list; never mutate input.

    Only explicit English rules are applied. Reading-level and sentence-length
    findings are advisory, so a heuristic cannot strand a valid manuscript.
    """
    changes = []
    suggestions = []
    output = []
    fenced = False
    fence_marker = ""
    prose = []

    def edit_span(span: str, line: int) -> str:
        def replace(pattern, replacement, code):
            nonlocal span
            def sub(match):
                before = match.group(0)
                after = replacement(match)
                if before != after:
                    changes.append({"code": code, "line": line,
                                    "before": before, "after": after})
                return after
            span = re.sub(pattern, sub, span, flags=re.I)
        replace(r"\b(" + "|".join(SPELLING) + r")\b",
                lambda m: _case(m[0], SPELLING[m[0].lower()]), "SPELLING")
        replace(r"\b(could|would|should|must) of\b",
                lambda m: _case(m[0], m[1].lower() + " have"), "MODAL_HAVE")
        replace(r"\b(the|a|an)[ \t]+\1\b", lambda m: m[1], "REPEATED_ARTICLE")
        replace(r"\b(he|she|it) (are)\b",
                lambda m: _case(m[0], m[1].lower() + (" is" if m[2].lower() == "are" else " was")),
                "SUBJECT_VERB_AGREEMENT")
        for sentence in re.split(r"(?<=[.!?])\s+", span):
            if len(re.findall(r"\b[\w'-]+\b", sentence)) > 35:
                suggestions.append({"code": "LONG_SENTENCE", "line": line,
                                    "excerpt": sentence[:240],
                                    "suggestion": "Consider splitting this sentence without removing facts."})
        prose.append(span)
        return span

    for line_number, line in enumerate(text.splitlines(keepends=True), 1):
        stripped = line.lstrip()
        fence = re.match(r"(`{3,}|~{3,})", stripped)
        if fence:
            marker = fence[1][0]
            if not fenced:
                fenced, fence_marker = True, marker
            elif marker == fence_marker:
                fenced = False
            output.append(line)
            continue
        if fenced or stripped.startswith(("#", ">", "|", "<!--")) or "|" in line:
            output.append(line)
            continue
        parts = PROTECTED.split(line)
        output.append("".join(part if i % 2 else edit_span(part, line_number)
                              for i, part in enumerate(parts)))
    edited = "".join(output)
    words = re.findall(r"\b[A-Za-z]+\b", " ".join(prose))
    sentences = max(1, len(re.findall(r"[.!?](?:\s|$)", " ".join(prose))))
    # Approximate syllables: informational only, explicitly labeled estimate.
    syllables = sum(max(1, len(re.findall(r"[aeiouy]+", w.lower().rstrip("e")))) for w in words)
    grade = round(0.39 * len(words) / sentences + 11.8 * syllables / max(1, len(words)) - 15.59, 1) if words else None
    if len(words) >= 100 and grade is not None and grade > target_grade + 2:
        suggestions.append({"code": "READING_LEVEL", "line": None,
                            "suggestion": f"Estimated grade {grade}; consider simpler wording toward grade {target_grade}."})
    return {"version": VERSION, "original": text, "edited": edited,
            "original_sha256": _digest(text), "edited_sha256": _digest(edited),
            "changes": changes, "suggestions": suggestions,
            "reading_grade_estimate": grade, "target_grade": target_grade,
            "coverage": "conservative English spelling and grammar rules; clarity suggestions",
            "not_checked": ["comprehensive grammar", "external plagiarism", "factual accuracy"],
            "paid_calls": 0}
