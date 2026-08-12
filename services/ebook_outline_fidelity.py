"""Exact approved-outline fidelity checks for Ebook manuscripts.

Deterministic. No network. Used after generation and before Approve.
"""
from __future__ import annotations

import re
from typing import Any

_H2_RE = re.compile(r"(?m)^##\s+(.+?)\s*$")

# Numbered-chapter back matter that must not appear unless outline-approved.
PROHIBITED_BACK_MATTER_TITLES = frozenset(
    {
        "conclusion",
        "disclaimer",
        "sources",
        "references",
        "bibliography",
        "about the author",
        "appendix",
    }
)


def normalize_chapter_title(title: str) -> str:
    t = str(title or "").strip().lower()
    t = re.sub(r"^chapter\s+\d+[.:)\-–—]?\s*", "", t)
    t = re.sub(r"\s+", " ", t)
    t = t.strip(" .:-\u2013\u2014")
    return t


def approved_outline_chapters(data: dict | None) -> list[dict[str, Any]]:
    """Authoritative approved outline chapters from project data."""
    data = data or {}
    outline = data.get("outline") or []
    chapters: list[dict[str, Any]] = []
    for i, item in enumerate(outline):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        if not title:
            continue
        chapters.append(
            {
                "order": int(item.get("order") or i + 1),
                "title": title,
                "purpose": str(item.get("purpose") or "").strip(),
            }
        )
    chapters.sort(key=lambda c: c["order"])
    return chapters


def extract_manuscript_h2_titles(md_text: str) -> list[str]:
    return [m.group(1).strip() for m in _H2_RE.finditer(md_text or "")]


def split_body_and_back_matter(md_text: str) -> tuple[list[str], list[str]]:
    """Return (chapter_titles, back_matter_titles) from H2 headings.

    Back matter = trailing H2s whose normalized titles are in the prohibited
    set AND are not present in the body chapter set yet. Callers that know the
    approved outline should use ``validate_manuscript_outline_fidelity`` instead.
    """
    titles = extract_manuscript_h2_titles(md_text)
    body: list[str] = []
    back: list[str] = []
    for title in titles:
        if normalize_chapter_title(title) in PROHIBITED_BACK_MATTER_TITLES:
            back.append(title)
        else:
            # Once back matter starts, later H2s stay back matter.
            if back:
                back.append(title)
            else:
                body.append(title)
    return body, back


def validate_manuscript_outline_fidelity(
    *,
    approved_outline: list[dict[str, Any]] | None,
    manuscript_md: str,
    prompt_outline_titles: list[str] | None = None,
    token_outline_digest: str | None = None,
    current_outline_digest: str | None = None,
) -> dict[str, Any]:
    """Compare approved outline to generated manuscript structure.

    Returns ``{ok, findings, approved_titles, generated_titles, back_matter}``.
    """
    approved = []
    for i, item in enumerate(approved_outline or []):
        if isinstance(item, dict):
            title = str(item.get("title") or "").strip()
            purpose = str(item.get("purpose") or "").strip()
            order = int(item.get("order") or i + 1)
        else:
            title = str(item or "").strip()
            purpose = ""
            order = i + 1
        if title:
            approved.append({"order": order, "title": title, "purpose": purpose})

    generated = extract_manuscript_h2_titles(manuscript_md)
    findings: list[str] = []

    if token_outline_digest and current_outline_digest:
        if str(token_outline_digest) != str(current_outline_digest):
            findings.append(
                "OUTLINE_DIGEST_MISMATCH: confirmation token outline digest does not "
                "match the stored approved outline."
            )

    if prompt_outline_titles is not None:
        prompt_norm = [normalize_chapter_title(t) for t in prompt_outline_titles]
        approved_norm = [normalize_chapter_title(c["title"]) for c in approved]
        if prompt_norm != approved_norm:
            findings.append(
                "PROMPT_OUTLINE_MISMATCH: generator prompt outline does not match "
                "the stored approved outline."
            )
            for i, (a, p) in enumerate(zip(approved_norm, prompt_norm), 1):
                if a != p:
                    findings.append(
                        f"Prompt chapter {i} mismatch: approved={approved[i-1]['title']!r} "
                        f"prompted={prompt_outline_titles[i-1]!r}"
                    )
            if len(prompt_norm) != len(approved_norm):
                findings.append(
                    f"Prompt chapter count mismatch: approved={len(approved_norm)} "
                    f"prompted={len(prompt_norm)}"
                )

    approved_norm = [normalize_chapter_title(c["title"]) for c in approved]
    approved_set = set(approved_norm)

    body_titles: list[str] = []
    back_matter: list[str] = []
    for title in generated:
        norm = normalize_chapter_title(title)
        if norm in PROHIBITED_BACK_MATTER_TITLES and norm not in approved_set:
            back_matter.append(title)
            continue
        if back_matter:
            # Extra H2 after unapproved back matter still counts as back/extra.
            back_matter.append(title)
            continue
        body_titles.append(title)

    if len(body_titles) != len(approved):
        findings.append(
            f"CHAPTER_COUNT_MISMATCH: approved={len(approved)} generated={len(body_titles)}"
        )

    for i, expected in enumerate(approved):
        got = body_titles[i] if i < len(body_titles) else "<missing>"
        if normalize_chapter_title(got) != normalize_chapter_title(expected["title"]):
            findings.append(
                f"CHAPTER_TITLE_MISMATCH order={expected['order']}: "
                f"approved={expected['title']!r} generated={got!r}"
            )
        purpose = expected.get("purpose") or ""
        if purpose and i < len(body_titles):
            matches = list(_H2_RE.finditer(manuscript_md or ""))
            try:
                gen_idx = generated.index(body_titles[i])
            except ValueError:
                gen_idx = -1
            if 0 <= gen_idx < len(matches):
                start = matches[gen_idx].end()
                end = (
                    matches[gen_idx + 1].start()
                    if gen_idx + 1 < len(matches)
                    else len(manuscript_md)
                )
                section = (manuscript_md[start:end] or "").strip()
                if len(section) < 40:
                    findings.append(
                        f"CHAPTER_PURPOSE_COVERAGE_WEAK order={expected['order']}: "
                        "chapter body is empty or too short to cover approved purpose."
                    )

    if back_matter:
        findings.append(
            "PROHIBITED_NUMBERED_BACK_MATTER: Conclusion/Disclaimer/Sources (or similar) "
            f"appeared as H2 chapters without outline approval: {back_matter!r}"
        )

    # Extra body chapters beyond approved count already covered; also flag renamed extras
    if len(body_titles) > len(approved):
        extras = body_titles[len(approved) :]
        findings.append(f"EXTRA_CHAPTERS: {extras!r}")

    ok = not findings
    return {
        "ok": ok,
        "findings": findings,
        "approved_titles": [c["title"] for c in approved],
        "generated_titles": body_titles,
        "back_matter": back_matter,
        "raw_h2_titles": generated,
    }


def fidelity_findings_block_approval(findings: list[str] | None) -> bool:
    """True when findings include structural outline-fidelity failures."""
    for f in findings or []:
        s = str(f)
        if s.startswith(
            (
                "OUTLINE_",
                "PROMPT_OUTLINE_",
                "CHAPTER_",
                "PROHIBITED_NUMBERED_BACK_MATTER",
                "EXTRA_CHAPTERS",
                "OUTLINE_FIDELITY_FAIL",
            )
        ):
            return True
    return False
