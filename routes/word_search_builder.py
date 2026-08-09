"""Word Search Builder browser routes (Phase 3)."""
from __future__ import annotations

import os
import re
import uuid

from flask import Blueprint, jsonify, make_response, render_template, request, send_from_directory

from services.ebook_package import EXPORTS_DIR
from services.word_search.pdf_builder import WordSearchPdfRequest, build_word_search_pdf
from services.quality.download_pipeline_agent import pipeline_download

word_search_builder_bp = Blueprint(
    "word_search_builder",
    __name__,
    url_prefix="/word-search-builder",
)

WORD_SEARCH_EXPORT_DIR = os.path.join(EXPORTS_DIR, "word_search_builder")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.pdf$")


def _yes(value: object) -> bool:
    return str(value or "").strip().lower() in {"yes", "true", "1", "on"}


def _validate_form(body: dict) -> list[str]:
    errors: list[str] = []
    title = str(body.get("product_title") or "").strip()
    if not title:
        errors.append("Product Title is required.")

    mode = str(body.get("creation_mode") or body.get("mode") or "topic").strip().lower()
    if mode in {"custom", "custom_list"}:
        mode = "custom_word_list"

    if mode == "custom_word_list":
        if not str(body.get("custom_words") or "").strip():
            errors.append("Add at least one word or phrase in the Custom Word List box.")
    else:
        if not str(body.get("theme") or "").strip():
            errors.append("Theme / Topic is required for Create From Topic mode.")

    try:
        grid_size = int(body.get("grid_size") or 15)
        if grid_size < 8 or grid_size > 25:
            errors.append("Grid Size must be between 8 and 25.")
    except (TypeError, ValueError):
        errors.append("Grid Size must be a number.")

    output_type = str(body.get("output_type") or "single_worksheet").strip().lower()
    if output_type == "book":
        try:
            count = int(body.get("number_of_puzzles") or 1)
            if count < 1:
                errors.append("Number of Puzzles must be at least 1.")
        except (TypeError, ValueError):
            errors.append("Number of Puzzles must be a number.")

    return errors


def _request_from_body(body: dict) -> WordSearchPdfRequest:
    mode = str(body.get("creation_mode") or body.get("mode") or "topic").strip().lower()
    if mode in {"custom", "custom_list"}:
        mode = "custom_word_list"

    output_type = str(body.get("output_type") or "single_worksheet").strip().lower()
    if output_type not in {"single_worksheet", "book"}:
        output_type = "single_worksheet"

    raw_words_per = body.get("words_per_puzzle") or body.get("words_per_worksheet")
    if raw_words_per not in (None, ""):
        words_per_puzzle = int(raw_words_per)
    elif output_type == "book":
        words_per_puzzle = 10
    else:
        words_per_puzzle = 0

    # Build cover_design for themed template covers
    product_title = str(body.get("product_title") or "").strip()
    subtitle = str(body.get("subtitle") or "").strip()
    author = str(body.get("author") or "").strip()
    theme = str(body.get("theme") or "").strip()

    # Cover page: only for books, never for single worksheets
    is_book = output_type == "book"
    include_cover = is_book and _yes(body.get("include_cover", "yes"))
    cover_design = None
    if include_cover:
        cover_design = {
            "title": product_title,
            "subtitle": subtitle,
            "author": author,
            "topic": theme,  # Used for theme-aware color palette
            "cover_prompt": f"Word search puzzle about {theme}" if theme else None,
        }

    return WordSearchPdfRequest(
        product_title=product_title,
        subtitle=subtitle,
        audience=str(body.get("audience") or "").strip(),
        theme=theme,
        difficulty=str(body.get("difficulty") or "medium").strip().lower(),
        grid_size=int(body.get("grid_size") or 15),
        number_of_puzzles=int(body.get("number_of_puzzles") or body.get("count") or 5),
        mode=mode,
        custom_words=str(body.get("custom_words") or ""),
        include_answer_key=_yes(body.get("include_answer_key", "yes")),
        output_type=output_type,
        words_per_puzzle=words_per_puzzle,
        include_cover=include_cover,
        cover_design=cover_design,
        seed=int(body["seed"]) if body.get("seed") not in (None, "") else None,
    )


def _unique_filename(base_name: str) -> str:
    stem = os.path.splitext(base_name)[0]
    token = uuid.uuid4().hex[:10]
    return f"{stem}_{token}.pdf"


@word_search_builder_bp.get("")
@word_search_builder_bp.get("/")
def word_search_builder_page():
    return render_template("word_search_builder.html")


@word_search_builder_bp.post("/generate")
def word_search_builder_generate():
    body = request.get_json(silent=True) if request.is_json else None
    if body is None:
        body = request.form.to_dict()

    validation_errors = _validate_form(body)
    if validation_errors:
        return jsonify({"ok": False, "errors": validation_errors, "warnings": []}), 400

    pdf_request = _request_from_body(body)
    result = build_word_search_pdf(pdf_request)

    if result.errors or not result.pdf_bytes:
        return jsonify(
            {
                "ok": False,
                "errors": result.errors or ["Could not generate the Word Search PDF."],
                "warnings": result.warnings,
                "qa_report": result.qa_report.as_dict() if result.qa_report else {},
            }
        ), 400

    os.makedirs(WORD_SEARCH_EXPORT_DIR, exist_ok=True)
    stored_name = _unique_filename(result.filename)
    file_path = os.path.join(WORD_SEARCH_EXPORT_DIR, stored_name)
    with open(file_path, "wb") as handle:
        handle.write(result.pdf_bytes)

    download_url = f"/word-search-builder/download/{stored_name}"
    return jsonify(
        {
            "ok": True,
            "message": "Word Search PDF created successfully.",
            "download_url": download_url,
            "filename": stored_name,
            "warnings": result.warnings,
            "puzzle_count": len(result.puzzles),
            "qa_report": result.qa_report.as_dict() if result.qa_report else {},
        }
    )


@word_search_builder_bp.get("/download/<filename>")
def word_search_builder_download(filename: str):
    """Download a word search PDF through the Download Pipeline Agent."""
    safe_name = os.path.basename(filename)
    if not _FILENAME_RE.match(safe_name):
        return jsonify({"error": "Invalid download file."}), 404
    directory = WORD_SEARCH_EXPORT_DIR
    file_path = os.path.join(directory, safe_name)
    if not os.path.isfile(file_path):
        return jsonify({"error": "PDF not found."}), 404

    # Run through Download Pipeline Agent
    context, result = pipeline_download(
        route="/word-search-builder/download/<filename>",
        filename=safe_name,
        file_path=file_path,
        fields={
            "output_format": "single_worksheet",  # word search builder default
            "product_type": "word_search",
        },
        product_mode="single_worksheet",
    )

    if result.status == "blocked":
        return jsonify(result.error_response or {
            "error": "download_blocked",
            "message": result.message,
            "violations": result.violations,
        }), result.status_code

    if result.status == "repaired" and result.served_bytes:
        response = make_response(result.served_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = f"attachment; filename={safe_name}"
        return response

    # Passed — serve from disk
    return send_from_directory(directory, safe_name, as_attachment=True)
