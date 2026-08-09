"""Crossword PDF builder — separate entry point from Word Search pdf_builder."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from services.crossword.book import build_crossword_puzzles
from services.crossword.builder import CrosswordPuzzleResult
from services.crossword.direct_pdf_renderer import (
    CrosswordPdfLayoutInfo,
    build_crossword_book_pdf_bytes,
    build_single_crossword_pdf_bytes,
)
from services.crossword.qa_agent import CrosswordQAResult, build_crossword_puzzles_with_qa, run_crossword_book_qa, run_crossword_qa


def _slugify(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "crossword").strip())
    return cleaned.strip("_").lower() or "crossword"


@dataclass
class CrosswordPdfRequest:
    product_title: str
    subtitle: str = ""
    theme: str = ""
    sub_topic: str = ""
    difficulty: str = "medium"
    grid_size: int | str = 15
    number_of_puzzles: int = 12
    mode: str = "topic"
    custom_words: str = ""
    custom_clues: dict[str, str] = field(default_factory=dict)
    include_answer_key: bool = True
    output_type: str = "book"
    words_per_puzzle: int = 10
    include_cover: bool = True
    cover_design: dict | None = None
    package_id: str = ""
    use_ai_words: bool = False
    seed: int | None = None


@dataclass
class CrosswordPdfResult:
    pdf_bytes: bytes = b""
    puzzles: list[CrosswordPuzzleResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    filename: str = "crossword.pdf"
    render_engine: str = "crossword_direct"
    layout_info: dict = field(default_factory=dict)
    qa_report: CrosswordQAResult | None = None

    def as_dict(self) -> dict:
        return {
            "puzzle_count": len(self.puzzles),
            "warnings": self.warnings,
            "errors": self.errors,
            "filename": self.filename,
            "pdf_size": len(self.pdf_bytes),
            "render_engine": self.render_engine,
            "layout_info": self.layout_info,
            "qa_report": self.qa_report.as_dict() if self.qa_report else {},
        }


def _layout_dict(layout: CrosswordPdfLayoutInfo) -> dict:
    return {
        "render_engine": layout.render_engine,
        "page_count": layout.page_count,
        "cover_page_count": layout.cover_page_count,
        "puzzle_page_count": layout.puzzle_page_count,
        "answer_key_page_count": layout.answer_key_page_count,
    }


def build_crossword_pdf(request: CrosswordPdfRequest) -> CrosswordPdfResult:
    output_type = str(request.output_type or "book").strip().lower()
    result = CrosswordPdfResult(filename=f"{_slugify(request.product_title)}.pdf")

    mode = str(request.mode or "topic").strip().lower()
    if mode in {"custom", "custom_list"}:
        mode = "custom_word_list"

    puzzle_count = 1 if output_type in {"single_worksheet", "single_page"} else max(1, int(request.number_of_puzzles or 1))
    exports_dir = os.environ.get("FLASK_EXPORTS_DIR") or ""
    puzzles, warnings, errors, qa = build_crossword_puzzles_with_qa(
        build_crossword_puzzles,
        mode=mode,
        product_title=request.product_title,
        custom_words=request.custom_words,
        custom_clues=dict(request.custom_clues),
        theme=request.theme or request.product_title,
        sub_topic=request.sub_topic,
        difficulty=request.difficulty,
        grid_size=request.grid_size,
        number_of_puzzles=puzzle_count,
        words_per_puzzle=int(request.words_per_puzzle or 10),
        output_type=output_type,
        use_ai_words=bool(request.use_ai_words),
        seed=request.seed,
        include_answer_key=bool(request.include_answer_key) and output_type != "single_page",
        exports_dir=exports_dir,
    )
    result.puzzles = puzzles
    result.warnings = warnings
    result.errors = errors
    result.qa_report = qa

    if not qa.passed:
        result.errors.extend(qa.errors)
        result.warnings.extend(qa.warnings)
        return result

    valid = [p for p in puzzles if not p.errors and p.clues]
    if not valid:
        result.errors.append("No crossword puzzles could be rendered.")
        return result

    # Full Book must not silently shrink below the requested puzzle count.
    if output_type == "book" and len(valid) < puzzle_count:
        result.errors.append(
            f"Crossword Full Book requires {puzzle_count} puzzles, but only {len(valid)} passed validation. "
            "No PDF was produced. Please try again or provide a custom word list."
        )
        return result

    cover = request.cover_design if request.include_cover and output_type == "book" else None
    # Keep subtitle/metadata aligned with the actual puzzle count.
    difficulty = str(request.difficulty or "easy").strip().title() or "Easy"
    book_subtitle = str(request.subtitle or "").strip()
    if output_type == "book":
        book_subtitle = f"{len(valid)} Crossword Puzzles - {difficulty} Level"
        if cover is not None:
            cover = dict(cover)
            cover["subtitle"] = book_subtitle
            cover["title"] = cover.get("title") or request.product_title

    if output_type in {"single_worksheet", "single_page"}:
        pdf_bytes, layout = build_single_crossword_pdf_bytes(
            valid[0],
            product_title=request.product_title,
            subtitle=book_subtitle or request.subtitle,
            include_answer_key=bool(request.include_answer_key) and output_type != "single_page",
            cover_design=None,
        )
    else:
        pdf_bytes, layout = build_crossword_book_pdf_bytes(
            valid,
            product_title=request.product_title,
            subtitle=book_subtitle,
            include_answer_key=bool(request.include_answer_key),
            cover_design=cover,
        )

    if not pdf_bytes.startswith(b"%PDF"):
        result.errors.append("Crossword PDF output is missing or invalid.")
        return result

    if output_type == "book":
        final_qa = run_crossword_book_qa(
            valid,
            expected_puzzle_count=puzzle_count,
            include_answer_key=bool(request.include_answer_key),
            pdf_bytes=pdf_bytes,
            words_per_puzzle=int(request.words_per_puzzle or 10),
        )
    else:
        final_qa = run_crossword_qa(
            valid[0],
            include_answer_key=bool(request.include_answer_key) and output_type != "single_page",
            pdf_bytes=pdf_bytes,
            expected_word_count=int(request.words_per_puzzle or 10),
        )
    final_qa.regeneration_attempts = qa.regeneration_attempts
    final_qa.fixes_applied = list(qa.fixes_applied)
    result.qa_report = final_qa

    # QA gate: if answer key was requested but layout shows no answer key pages, block export.
    # For single_worksheet/single_page: include_answer_key is conditioned on output_type != "single_page"
    ak_requested_for_type = (
        bool(request.include_answer_key)
        and output_type not in {"single_page"}
    )
    if ak_requested_for_type and layout.answer_key_page_count == 0:
        final_qa.errors.append(
            "Answer key was requested but the PDF contains no answer key page. "
            "QA blocked this export. Please regenerate."
        )
        final_qa.passed = False
        final_qa.blocked_export = True
        result.errors.extend(final_qa.errors)
        result.warnings.extend(final_qa.warnings)
        return result

    if not final_qa.passed:
        result.errors.extend(final_qa.errors)
        result.warnings.extend(final_qa.warnings)
        return result

    result.pdf_bytes = pdf_bytes
    result.render_engine = layout.render_engine
    result.layout_info = _layout_dict(layout)
    return result


def save_crossword_pdf(request: CrosswordPdfRequest, output_dir: str) -> CrosswordPdfResult:
    result = build_crossword_pdf(request)
    if result.errors or not result.pdf_bytes:
        return result
    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, result.filename)
    with open(path, "wb") as handle:
        handle.write(result.pdf_bytes)
    result.warnings.append(f"Saved PDF to {path}")
    return result
