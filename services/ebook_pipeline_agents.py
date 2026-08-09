"""Step-by-step ebook quality pipeline (Designrr-oriented gates).

Runs after generate / enhance / before export. Does not call paid APIs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.ebook_contract import EbookContract, build_contract
from services.ebook_originality_agent import (
    ORIGINALITY_TARGET,
    extract_research_sources,
    score_originality,
)
from services.ebook_quality_agent import validate_ebook_content


@dataclass
class PipelineStepResult:
    step: str
    passed: bool
    score: float | None = None
    messages: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "passed": self.passed,
            "score": self.score,
            "messages": list(self.messages),
            "details": dict(self.details),
        }


@dataclass
class EbookPipelineReport:
    passed: bool
    overall_score: float
    originality_score: float | None
    steps: list[PipelineStepResult] = field(default_factory=list)
    blocking: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "overall_score": round(self.overall_score, 2),
            "originality_score": (
                None
                if self.originality_score is None
                else round(self.originality_score, 4)
            ),
            "originality_target": ORIGINALITY_TARGET,
            "steps": [s.to_dict() for s in self.steps],
            "blocking": list(self.blocking),
        }


def run_ebook_quality_pipeline(
    *,
    title: str,
    manuscript: str,
    fields: dict | None = None,
    data: dict | None = None,
    contract: EbookContract | None = None,
    visual_plan: dict | None = None,
    cover_design: dict | None = None,
    require_visuals: bool = True,
    require_cover: bool = True,
    block_on_originality: bool = True,
) -> EbookPipelineReport:
    """Run contract → content → originality → visuals → cover gates."""
    fields = fields or {}
    data = data or {}
    steps: list[PipelineStepResult] = []
    blocking: list[str] = []

    # 1. Contract / author / research framing
    if contract is None:
        contract = build_contract(
            topic=fields.get("topic") or title,
            audience=fields.get("audience") or "",
            tone=fields.get("tone") or "friendly and clear",
            reading_level=fields.get("reading_level") or "6th-8th grade",
            research_requested=bool(
                fields.get("use_research")
                or fields.get("research_requested")
                or data.get("research_notes")
                or data.get("research_brief")
            ),
        )
    author = (
        fields.get("author_brand")
        or fields.get("author")
        or data.get("author_brand")
        or ""
    ).strip()
    author_ok = bool(author)
    steps.append(
        PipelineStepResult(
            step="author_and_contract",
            passed=author_ok and bool(contract.topic),
            messages=(
                []
                if author_ok
                else ["Author name is required on the finished ebook."]
            )
            + (
                ["Research-backed mode enabled."]
                if contract.research_requested
                else ["No research mode — factual claims must stay general."]
            ),
            details={"author": author, "research_requested": contract.research_requested},
        )
    )
    if not author_ok:
        blocking.append("Add an author name before export.")

    # 2. Content quality agent
    content_qa = validate_ebook_content(
        md_text=manuscript, contract=contract, title=title
    )
    content_score = float(getattr(content_qa, "score", 0) or 0)
    content_passed = bool(getattr(content_qa, "passed", content_score >= 70))
    steps.append(
        PipelineStepResult(
            step="content_quality",
            passed=content_passed,
            score=content_score,
            messages=list(getattr(content_qa, "errors", []) or [])[:8]
            or list(getattr(content_qa, "warnings", []) or [])[:4],
            details={"score": content_score},
        )
    )
    if not content_passed:
        blocking.append("Content quality agent failed — revise chapters before export.")

    # 3. Originality / plagiarism gate
    sources = extract_research_sources(data, data.get("research_brief"))
    # Also compare against raw source field if present
    if data.get("source") and str(data.get("source_type") or "") != "topic":
        if data.get("source_content"):
            sources.append(str(data["source_content"]))
    orig = score_originality(manuscript, sources)
    steps.append(
        PipelineStepResult(
            step="originality",
            passed=orig.passed if (sources or not block_on_originality) else True,
            score=orig.score * 100,
            messages=orig.messages,
            details=orig.to_dict(),
        )
    )
    if sources and block_on_originality and not orig.passed:
        blocking.append(
            f"Originality {orig.score:.1%} is below the {ORIGINALITY_TARGET:.0%} target."
        )

    # 4. Visual plan / Designrr aids
    chapters = []
    if isinstance(visual_plan, dict):
        chapters = visual_plan.get("chapters") or []
    aid_count = sum(len(ch.get("aids") or []) for ch in chapters if isinstance(ch, dict))
    visuals_ok = (aid_count >= 3) if require_visuals else True
    steps.append(
        PipelineStepResult(
            step="visuals",
            passed=visuals_ok,
            score=min(100.0, aid_count * 15),
            messages=(
                [f"{aid_count} visual aids attached."]
                if visuals_ok
                else ["Need charts/diagrams/worksheets — run Enhance / visual package."]
            ),
            details={"aid_count": aid_count},
        )
    )
    if require_visuals and not visuals_ok:
        blocking.append("Add research-supporting visuals before claiming Designrr quality.")

    # 5. Cover readiness
    cover_ok = True
    cover_msgs = []
    if require_cover:
        if not cover_design:
            cover_ok = False
            cover_msgs.append("Cover design missing — open Edit Cover or regenerate.")
        else:
            if not (cover_design.get("title") or title):
                cover_ok = False
                cover_msgs.append("Cover title missing.")
            if not (
                cover_design.get("image_path")
                or cover_design.get("local_cover_pdf")
                or cover_design.get("local_generated")
            ):
                cover_msgs.append("Cover artwork not finalized (local or uploaded).")
    steps.append(
        PipelineStepResult(
            step="cover",
            passed=cover_ok,
            messages=cover_msgs or ["Cover present."],
            details={"has_cover": bool(cover_design)},
        )
    )
    if require_cover and not cover_ok:
        blocking.append("Finish the cover (Edit Cover) before final export.")

    # Overall score (weighted)
    weights = []
    scores = []
    for s in steps:
        if s.score is None:
            scores.append(100.0 if s.passed else 40.0)
        else:
            scores.append(float(s.score))
        weights.append(1.0)
    overall = sum(scores) / max(1, len(scores))
    # Originality heavily weighted when sources exist
    if sources and orig.score is not None:
        overall = overall * 0.55 + (orig.score * 100) * 0.45

    passed = not blocking and overall >= 85
    return EbookPipelineReport(
        passed=passed,
        overall_score=overall,
        originality_score=orig.score if sources else None,
        steps=steps,
        blocking=blocking,
    )
