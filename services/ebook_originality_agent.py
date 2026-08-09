"""Originality / anti-plagiarism gate for ebook manuscripts.

Compares generated text to source/research material using word n-gram overlap.
Target: >= 98% originality (overlap <= 2%) against provided sources.

This is a local deterministic gate — not a commercial Turnitin clone — but it
blocks near-copy paste from research notes, URLs, and transcripts before export.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


ORIGINALITY_TARGET = 0.98  # 98% original vs sources


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", (text or "").lower())


def _ngrams(tokens: list[str], n: int = 5) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


@dataclass
class OriginalityReport:
    score: float
    overlap_ratio: float
    target: float = ORIGINALITY_TARGET
    passed: bool = False
    shared_ngram_count: int = 0
    manuscript_ngram_count: int = 0
    sources_checked: int = 0
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "score": round(self.score, 4),
            "overlap_ratio": round(self.overlap_ratio, 4),
            "target": self.target,
            "passed": self.passed,
            "shared_ngram_count": self.shared_ngram_count,
            "manuscript_ngram_count": self.manuscript_ngram_count,
            "sources_checked": self.sources_checked,
            "messages": list(self.messages),
        }


def score_originality(
    manuscript: str,
    sources: list[str] | None = None,
    *,
    n: int = 5,
    target: float = ORIGINALITY_TARGET,
) -> OriginalityReport:
    """Return originality score = 1 - (shared n-grams / manuscript n-grams)."""
    sources = [s for s in (sources or []) if (s or "").strip()]
    ms_tokens = _tokens(manuscript)
    ms_grams = _ngrams(ms_tokens, n)
    if not ms_grams:
        return OriginalityReport(
            score=1.0,
            overlap_ratio=0.0,
            target=target,
            passed=True,
            messages=["Manuscript too short to score; treated as pass."],
        )
    if not sources:
        return OriginalityReport(
            score=1.0,
            overlap_ratio=0.0,
            target=target,
            passed=True,
            sources_checked=0,
            manuscript_ngram_count=len(ms_grams),
            messages=[
                "No source/research text provided for comparison. "
                "Score assumes original drafting; attach research for a real check."
            ],
        )

    source_grams: set[tuple[str, ...]] = set()
    for src in sources:
        source_grams |= _ngrams(_tokens(src), n)

    shared = ms_grams & source_grams
    overlap = len(shared) / max(1, len(ms_grams))
    score = max(0.0, 1.0 - overlap)
    passed = score >= target
    messages = []
    if passed:
        messages.append(
            f"Originality {score:.1%} meets target {target:.0%} "
            f"({len(shared)} overlapping {n}-grams)."
        )
    else:
        messages.append(
            f"Originality {score:.1%} is below target {target:.0%}. "
            f"Rewrite passages that closely mirror research/source wording "
            f"({len(shared)} overlapping {n}-grams)."
        )
    return OriginalityReport(
        score=score,
        overlap_ratio=overlap,
        target=target,
        passed=passed,
        shared_ngram_count=len(shared),
        manuscript_ngram_count=len(ms_grams),
        sources_checked=len(sources),
        messages=messages,
    )


def extract_research_sources(data: dict | None, contract_brief: dict | None = None) -> list[str]:
    """Collect research/source blobs from project data or ebook brief."""
    blobs: list[str] = []
    data = data or {}
    brief = contract_brief or data.get("research_brief") or data.get("contract") or {}
    if isinstance(brief, dict):
        for key in (
            "research_notes",
            "research_summary",
            "findings",
            "sources_text",
            "source_material",
            "market_research",
            "opportunity_summary",
        ):
            val = brief.get(key)
            if isinstance(val, str) and val.strip():
                blobs.append(val)
            elif isinstance(val, list):
                blobs.append("\n".join(str(x) for x in val))
        plan = brief.get("plan") if isinstance(brief.get("plan"), dict) else {}
        for key in ("research_notes", "summary", "findings", "evidence"):
            val = plan.get(key)
            if isinstance(val, str) and val.strip():
                blobs.append(val)
        op = brief.get("opportunity") if isinstance(brief.get("opportunity"), dict) else {}
        for key in ("summary", "evidence", "why_now"):
            val = op.get(key)
            if isinstance(val, str) and val.strip():
                blobs.append(val)

    for key in ("research_notes", "source_material", "source_content", "research_text"):
        val = data.get(key)
        if isinstance(val, str) and val.strip():
            blobs.append(val)

    # Deduplicate
    seen = set()
    out = []
    for b in blobs:
        h = hash(b[:200])
        if h in seen:
            continue
        seen.add(h)
        out.append(b)
    return out
