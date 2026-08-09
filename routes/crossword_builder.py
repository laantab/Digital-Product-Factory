"""Crossword Builder browser routes — separate from Word Search Builder."""
from __future__ import annotations

import os
import re
import uuid

from flask import Blueprint, jsonify, make_response, render_template, request, send_from_directory

from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf
from services.ebook_package import EXPORTS_DIR
from services.quality.download_pipeline_agent import pipeline_download

crossword_builder_bp = Blueprint(
    "crossword_builder",
    __name__,
    url_prefix="/crossword-builder",
)

CROSSWORD_EXPORT_DIR = os.path.join(EXPORTS_DIR, "crossword_builder")
_FILENAME_RE = re.compile(r"^[A-Za-z0-9._-]+\.pdf$")


def _yes(value: object) -> bool:
    return str(value or "").strip().lower() in {"yes", "true", "1", "on"}


def _validate_form(body: dict) -> list[str]:
    errors: list[str] = []
    title = str(body.get("product_title") or body.get("theme") or "").strip()
    if not title:
        errors.append("Theme / product title is required.")
    mode = str(body.get("creation_mode") or body.get("mode") or "topic").strip().lower()
    if mode in {"custom", "custom_list"}:
        mode = "custom_word_list"
    if mode == "custom_word_list" and not str(body.get("custom_words") or "").strip():
        errors.append("Add at least one crossword answer in the custom word list.")
    return errors


def _parse_custom_clues(raw: str) -> dict[str, str]:
    """Parse custom clues from 'WORD: clue text' format, one per line."""
    clues: dict[str, str] = {}
    if not raw:
        return clues
    for line in str(raw).strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        # Split on first colon only
        word_part, clue_part = line.split(":", 1)
        word = word_part.strip().upper()
        clue = clue_part.strip()
        if word and clue and word.isalpha():
            clues[word] = clue
    return clues


def _request_from_body(body: dict) -> CrosswordPdfRequest:
    mode = str(body.get("creation_mode") or body.get("mode") or "topic").strip().lower()
    if mode in {"custom", "custom_list"}:
        mode = "custom_word_list"

    output_type = str(body.get("output_type") or "book").strip().lower()
    if output_type not in {"single_worksheet", "book"}:
        output_type = "book"

    product_title = str(body.get("product_title") or body.get("theme") or "").strip()
    theme = str(body.get("theme") or product_title).strip()
    cover_design = None
    if _yes(body.get("include_cover", "yes")):
        cover_design = {
            "title": product_title,
            "subtitle": str(body.get("subtitle") or "").strip(),
            "author": str(body.get("author") or "").strip(),
            "topic": theme,
            "cover_prompt": f"Crossword puzzle book about {theme}" if theme else None,
        }

    return CrosswordPdfRequest(
        product_title=product_title,
        subtitle=str(body.get("subtitle") or "").strip(),
        theme=theme,
        sub_topic=str(body.get("sub_topic") or "").strip(),
        difficulty=str(body.get("difficulty") or "medium").strip().lower(),
        grid_size=int(body.get("grid_size") or 15),
        number_of_puzzles=int(body.get("number_of_puzzles") or body.get("puzzles") or 1),
        mode=mode,
        custom_words=str(body.get("custom_words") or ""),
        custom_clues=_parse_custom_clues(str(body.get("custom_clues") or "")),
        include_answer_key=_yes(body.get("include_answer_key", "yes")),
        output_type=output_type,
        words_per_puzzle=int(body.get("words_per_puzzle") or 10),
        include_cover=_yes(body.get("include_cover", "yes")),
        cover_design=cover_design,
        use_ai_words=_yes(body.get("use_ai_words", "no")),
        seed=int(body["seed"]) if body.get("seed") not in (None, "") else None,
    )


def _unique_filename(base_name: str) -> str:
    stem = os.path.splitext(base_name)[0]
    token = uuid.uuid4().hex[:10]
    return f"{stem}_{token}.pdf"


@crossword_builder_bp.get("")
@crossword_builder_bp.get("/")
def crossword_builder_page():
    return render_template("crossword_builder.html")


@crossword_builder_bp.post("/generate")
def crossword_builder_generate():
    body = request.get_json(silent=True) if request.is_json else None
    if body is None:
        body = request.form.to_dict()

    validation_errors = _validate_form(body)
    if validation_errors:
        return jsonify({"ok": False, "errors": validation_errors, "warnings": []}), 400

    pdf_request = _request_from_body(body)
    result = build_crossword_pdf(pdf_request)
    if result.errors or not result.pdf_bytes:
        return jsonify(
            {
                "ok": False,
                "errors": result.errors or ["Could not generate the Crossword PDF."],
                "warnings": result.warnings,
            }
        ), 400

    os.makedirs(CROSSWORD_EXPORT_DIR, exist_ok=True)
    stored_name = _unique_filename(result.filename)
    file_path = os.path.join(CROSSWORD_EXPORT_DIR, stored_name)
    with open(file_path, "wb") as handle:
        handle.write(result.pdf_bytes)

    return jsonify(
        {
            "ok": True,
            "message": "Crossword PDF created successfully.",
            "download_url": f"/crossword-builder/download/{stored_name}",
            "filename": stored_name,
            "warnings": result.warnings,
            "puzzle_count": len(result.puzzles),
        }
    )


@crossword_builder_bp.get("/download/<filename>")
def crossword_builder_download(filename: str):
    """Download a crossword PDF through the Download Pipeline Agent."""
    safe_name = os.path.basename(filename)
    if not _FILENAME_RE.match(safe_name):
        return jsonify({"error": "Invalid download file."}), 404
    directory = CROSSWORD_EXPORT_DIR
    file_path = os.path.join(directory, safe_name)
    if not os.path.isfile(file_path):
        return jsonify({"error": "PDF not found."}), 404

    # Run through Download Pipeline Agent
    context, result = pipeline_download(
        route="/crossword-builder/download/<filename>",
        filename=safe_name,
        file_path=file_path,
        fields={
            "output_format": "single_worksheet",  # crossword builder default
            "product_type": "crossword",
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
