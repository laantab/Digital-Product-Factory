"""Planner PDF builder — plan, render, write to the package directory.

Mirrors the shape of `services/math_worksheet/pdf_builder.py` so the planner
sits inside the same export, download, and QA plumbing as every other
deterministic product type.
"""
from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass, field

from services.planner.builder import (
    PlannerPlan,
    PlannerRequest,
    build_planner_plan,
    clamp_pages,
)
from services.planner.renderer import build_planner_pdf_bytes

EXPORTS_DIR = os.environ.get(
    "FLASK_EXPORTS_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "exports"),
)


def _slugify(value: str, fallback: str = "planner") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip())
    return cleaned.strip("_").lower() or fallback


@dataclass
class PlannerPdfRequest:
    planner_type: str = "faith_planner"
    title: str = ""
    subtitle: str = ""
    theme: str = ""
    audience: str = ""
    author: str = ""
    pages: int = 60
    page_size: str = "US Letter"
    include_cover: bool = True
    include_toc: bool = True
    include_notes: bool = True
    include_habit_tracker: bool = True
    include_calendar: bool = True
    include_reflection: bool = True
    package_id: str = ""


@dataclass
class PlannerPdfResult:
    pdf_bytes: bytes = b""
    plan: PlannerPlan | None = None
    filename: str = "planner.pdf"
    pdf_path: str = ""
    package_dir: str = ""
    render_engine: str = "planner_direct"
    layout_info: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def build_planner_pdf(request: PlannerPdfRequest) -> PlannerPdfResult:
    result = PlannerPdfResult()
    try:
        pages = clamp_pages(request.pages, request.planner_type)
        plan_req = PlannerRequest(
            planner_type=request.planner_type,
            title=request.title,
            subtitle=request.subtitle,
            theme=request.theme,
            audience=request.audience,
            pages=pages,
            page_size=request.page_size,
            include_cover=request.include_cover,
            include_toc=request.include_toc,
            include_notes=request.include_notes,
            include_habit_tracker=request.include_habit_tracker,
            include_calendar=request.include_calendar,
            include_reflection=request.include_reflection,
        )
        plan = build_planner_plan(plan_req)
        pdf_bytes, info = build_planner_pdf_bytes(
            plan, page_size=request.page_size, author=request.author
        )
    except Exception as exc:  # noqa: BLE001
        result.errors.append(str(exc))
        return result

    pkg = request.package_id or uuid.uuid4().hex
    slug = _slugify(plan.title, request.planner_type)
    filename = f"{slug}.pdf"
    package_dir = os.path.join(EXPORTS_DIR, pkg)
    os.makedirs(package_dir, exist_ok=True)
    pdf_path = os.path.join(package_dir, filename)
    with open(pdf_path, "wb") as fh:
        fh.write(pdf_bytes)

    result.pdf_bytes = pdf_bytes
    result.plan = plan
    result.filename = filename
    result.pdf_path = pdf_path
    result.package_dir = package_dir
    result.layout_info = {
        "render_engine": info.render_engine,
        "page_size": info.page_size,
        "total_pages": info.total_pages,
        "cover_page_count": info.cover_page_count,
        "page_kinds": info.kinds or {},
        "declared_pages": plan.page_count,
    }
    result.warnings = list(plan.warnings)
    return result
