"""Multi-format digital product generation (the Product Factory).

Each product type defines a system persona and a builder that turns the
submitted form fields into a precise instruction. All generators return clean,
export-ready Markdown so the frontend can preview and the project store can save
the raw output.
"""
import base64
import os
import re
import uuid

from ai_client import chat
from services.product_cover_agent import (
    build_crossword_payload_from_fields,
    build_word_search_payload_from_fields,
    cover_image_job,
    generate_cover_from_payload,
    regenerate_cover_image_for_cover,
)
from services.ebook_package import EXPORTS_DIR
from services.coloring_book.pdf_builder import ColoringBookPdfRequest, build_coloring_book_pdf
from services.crossword.pdf_builder import CrosswordPdfRequest, build_crossword_pdf
from services.math_worksheet.pdf_builder import MathWorksheetPdfRequest, build_math_worksheet_pdf
from services.spelling_worksheet.pdf_builder import SpellingWorksheetPdfRequest, build_spelling_worksheet_pdf
from services.word_search.pdf_builder import WordSearchPdfRequest, build_word_search_pdf
from services.word_search.word_lists import word_list_fetch_target

_NO_EMOJI = "Do not use emojis. Return only the Markdown document, no preamble."


def _f(fields: dict, key: str, default: str = "") -> str:
    return str(fields.get(key, default) or default).strip()


def _yes(fields: dict, key: str) -> bool:
    return str(fields.get(key, "")).strip().lower() in {"yes", "true", "1", "on"}


# Map display labels from the form to internal quality_mode values.
QUALITY_MODE_MAP = {
    "ai image coloring page": "ai_image_coloring_page",
    "basic test fallback": "basic_test",
    "basic_test": "basic_test",          # programmatic/internal key
    "basic test": "basic_test",          # common variant
    "basic": "basic_test",               # shorthand
}


def _normalize_quality_mode(fields: dict) -> str:
    raw = str(fields.get("quality_mode") or "").strip().lower()
    return QUALITY_MODE_MAP.get(raw, "ai_image_coloring_page")


# ---------------------------------------------------------------------------
# Per-type prompt builders
# ---------------------------------------------------------------------------


def _ebook(fields: dict) -> tuple[str, str, str]:
    title = _f(fields, "ebook_title") or _f(fields, "topic") or "Untitled Ebook"
    topic = _f(fields, "topic")
    audience = _f(fields, "audience")
    tone = _f(fields, "tone", "professional")
    reading_level = _f(fields, "reading_level", "General adult")
    chapter_count_str = _f(fields, "chapters", "6")
    worksheet_requested = _yes(fields, "include_worksheets")
    images_requested = _yes(fields, "include_images")
    author = _f(fields, "author_brand") or _f(fields, "author")
    research_notes = _f(fields, "research_notes")
    use_research = _yes(fields, "use_research") or bool(research_notes)

    # Build a lightweight contract for prompt guidance.
    from services.ebook_contract import build_contract, contract_to_prompt_guidance
    contract = build_contract(
        topic=topic,
        audience=audience,
        tone=tone,
        reading_level=reading_level,
        chapter_count=int(chapter_count_str) if chapter_count_str.isdigit() else 6,
        research_requested=use_research,
        worksheet_required=worksheet_requested,
        worksheet_expectation=(
            "Each chapter should end with a brief action-steps section containing "
            "3-5 concrete prompts the reader can complete immediately."
            if worksheet_requested else ""
        ),
    )

    contract_guidance = contract_to_prompt_guidance(contract)

    extras = (
        "Include a worksheet / action-steps section at the end of each chapter."
        if worksheet_requested
        else "Do not include worksheets."
    )
    images = (
        "Include suggestions for charts, diagrams, and photo placements that support "
        "the research points (visual plan will render them)."
        if images_requested
        else "Do not include images — text and formatting only."
    )
    research_block = ""
    if use_research and research_notes:
        research_block = (
            "\nRESEARCH NOTES (paraphrase fully — never copy sentences):\n"
            f"{research_notes[:8000]}\n"
            "Include a Sources section listing only sources named in these notes.\n"
        )
    elif use_research and not research_notes:
        research_block = (
            "\nResearch mode is ON but no research notes were attached. "
            "Do not invent studies or statistics.\n"
        )
    system = (
        "You are a professional non-fiction author and instructional designer "
        "who produces topic-specific, audience-appropriate, practical digital ebooks "
        "that are honest, useful, and sellable. Rewrite all research into original prose "
        "(Designrr-quality clarity). Never copy source sentences. You do not invent "
        "statistics, studies, testimonials, or case studies. You do not use hype language. "
        "You do not make unsupported health, financial, or legal claims. "
        "Every chapter must be substantive, specific, and actionable — not generic filler."
    )
    user = (
        "Write a complete, structured ebook in Markdown.\n\n"
        f"Title: {title}\n"
        f"Author / brand: {author or 'Digital Product Factory'}\n"
        f"Topic: {topic}\n"
        f"Target audience: {audience}\n"
        f"Number of chapters: {chapter_count_str}\n"
        f"Tone: {tone}\n"
        f"Reading level: {reading_level}\n"
        f"{extras}\n"
        f"{images}\n"
        f"{research_block}\n"
        "Structure the output with these sections, in order:\n"
        "1. Title (H1) and a compelling subtitle.\n"
        "2. Table of Contents.\n"
        "3. The chapters (H2), each with substantive multi-paragraph content "
        "and H3 subsections. Vary chapter structure — do NOT reuse the same H3 "
        "labels in every chapter. Never use these generic repeated headings: "
        "'What this chapter helps you solve and why it matters', "
        "'A step-by-step method', 'Common mistakes', or 'Chapter takeaway'. "
        "Instead use descriptive labels (decision guides, scripts, checklists, "
        "routines, troubleshooting, worksheets) appropriate to each chapter. "
        "Include plain-English explanation, at least one concrete example, and "
        "something the reader can try within 24 hours.\n"
        "4. A Summary section.\n"
        "5. An Action Steps section.\n"
        "6. An optional Worksheet section if requested above.\n\n"
        f"QUALITY CONTRACT:\n{contract_guidance}\n\n"
        f"{_NO_EMOJI}"
    )
    return system, user, title


def _planner(fields: dict) -> tuple[str, str, str]:
    title = _f(fields, "planner_title") or "Planner"
    planner_type = _f(fields, "planner_type") or "Daily"
    theme = _f(fields, "theme") or ""
    audience = _f(fields, "audience") or "General"
    pages = _f(fields, "pages", "30")
    page_size = _f(fields, "page_size", "US Letter")
    interior = _f(fields, "interior_style", "Modern")
    include_cover = _yes(fields, "include_cover")
    include_toc = _yes(fields, "include_toc")
    include_notes = _yes(fields, "include_notes")
    include_habit = _yes(fields, "include_habit_tracker")
    include_calendar = _yes(fields, "include_calendar")
    include_reflection = _yes(fields, "include_reflection")
    output_fmt = _f(fields, "output_format", "PDF")
    system = (
        "You are a professional planner and workbook designer who creates "
        "highly usable, beautifully structured digital planners."
    )
    section_reqs = []
    if include_cover:
        section_reqs.append("- A cover page with the title and a subtitle")
    if include_toc:
        section_reqs.append("- A table of contents")
    if include_habit:
        section_reqs.append("- Habit tracker pages")
    if include_calendar:
        section_reqs.append("- Calendar / monthly overview pages")
    if include_reflection:
        section_reqs.append("- Reflection and gratitude pages")
    if include_notes:
        section_reqs.append("- Notes pages (lined or grid)")
    section_text = "\n".join(section_reqs) if section_reqs else "- Core planning pages only"
    user = (
        f"Create a complete {planner_type} planner in Markdown, designed for {audience}"
        + (f" with the theme: {theme}" if theme else "")
        + f".\n\n"
        f"Requirements:\n"
        f"- {pages} pages total, formatted for {page_size}\n"
        f"- Interior style: {interior}\n"
        f"- Output format: {output_fmt}\n"
        f"- For each section: clear headers, useful prompts, and actionable checkboxes\n"
        f"- Make it practical, visually organized with tables and lists\n"
        f"- Output in clean Markdown format\n\n"
        f"Include these sections:\n"
        f"{section_text}\n\n"
        f"{_NO_EMOJI}"
    )
    return system, user, title


def _coloring_book(fields: dict) -> tuple[str, str, str]:
    from services.factory.puzzle_plan import parse_puzzle_output_plan

    plan = parse_puzzle_output_plan(fields, product_type="coloring_book")
    pages = plan["page_count"] if plan["is_book"] else 1
    title = _f(fields, "coloring_title") or _f(fields, "theme") or "Coloring Book"
    captions = (
        "Include a short caption for every page."
        if _yes(fields, "include_captions")
        else "Do not include captions."
    )
    system = (
        "You are a children's and adult coloring-book creator who writes vivid, "
        "drawable line-art prompts. All pages use the Bold & Easy Kawaii style: "
        "cute kawaii illustrations with simple rounded shapes, bold clean outlines, "
        "consistent line weight, large open coloring areas, and friendly features. "
        "IMPORTANT style rules for every prompt: bold and easy, cute kawaii, "
        "simple rounded shapes, clean black line art, large open spaces, clear subject separation, "
        "not crowded, not too empty. No shading, no gray, no color, no realistic rendering, "
        "no tiny details, no clutter."
    )
    user = (
        "Create a complete coloring book plan in Markdown.\n\n"
        f"Theme: {_f(fields, 'theme')}\n"
        f"Age group: {_f(fields, 'age_group')}\n"
        f"Number of pages: {pages}\n"
        f"Art style: {_f(fields, 'art_style')}\n"
        f"Difficulty level: {_f(fields, 'difficulty')}\n"
        f"{captions}\n\n"
        "Structure the output with these sections, in order:\n"
        "1. Book Title (H1) and target age group.\n"
        "2. Page List (a numbered list of every page with a one-line subject).\n"
        "3. Coloring Page Prompts (for each page, a Bold & Easy Kawaii style "
        "detailed line-art image prompt: cute kawaii, simple rounded shapes, bold clean outlines, "
        "large open coloring areas, black and white only, no shading, no color).\n"
        "4. Page Captions (only if requested).\n"
        "5. Cover Design Prompt.\n\n"
        f"{_NO_EMOJI}"
    )
    return system, user, title


def _word_search(fields: dict) -> tuple[str, str, str]:
    title = _f(fields, "book_title") or _f(fields, "theme") or "Word Search Book"
    output_format = _f(fields, "output_format") or "Full Book"
    puzzles = "1" if "Single" in output_format else _f(fields, "puzzles", "5")
    answers = (
        "Include answer-key data for every puzzle."
        if _yes(fields, "include_answer_key")
        else "Do not include answer keys."
    )
    system = (
        "You are a puzzle-book author who designs themed word-search puzzles."
    )
    if "Single" in output_format:
        user = (
            "Create a single word search worksheet in Markdown.\n\n"
            f"Theme: {_f(fields, 'theme')}\n"
            f"Words: {_f(fields, 'words_per_puzzle', '10')}\n"
            f"Difficulty level: {_f(fields, 'difficulty')}\n"
            f"{answers}\n\n"
            "Structure the output with these sections, in order:\n"
            "1. Worksheet Title (H1).\n"
            "2. Word List.\n"
            "3. Clear Puzzle Instructions.\n"
            "4. Answer Key data (only if requested).\n\n"
            f"{_NO_EMOJI}"
        )
    else:
        user = (
            "Create a complete word search book in Markdown.\n\n"
            f"Book title: {title}\n"
            f"Theme: {_f(fields, 'theme')}\n"
            f"Target age group: {_f(fields, 'audience')}\n"
            f"Number of puzzles: {puzzles}\n"
            f"Words per puzzle: {_f(fields, 'words_per_puzzle', '10')}\n"
            f"Difficulty level: {_f(fields, 'difficulty')}\n"
            f"Page size: {_f(fields, 'page_size', 'US Letter')}\n"
            f"{answers}\n\n"
            "Structure the output with these sections, in order:\n"
            "1. Book Title (H1).\n"
            "2. For each puzzle: a Puzzle Title, the Word List, and clear Puzzle "
            "Instructions.\n"
            "3. Answer Key data section (only if requested), listing the words to "
            "find per puzzle.\n"
            "4. Cover Design Prompt.\n\n"
            f"{_NO_EMOJI}"
        )
    return system, user, title


def normalize_word_search_project_data(data: dict) -> dict:
    """Fill missing Word Search metadata on older saved projects."""
    data = dict(data or {})
    if data.get("product_type") != "word_search":
        return data

    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    title = (data.get("title") or fields.get("theme") or "Word Search").strip()
    if not fields.get("theme"):
        fields = {**fields, "theme": title}
        data["fields"] = fields  # preserve reassigned fields
    if not fields.get("generator"):
        meta = data.get("word_search_meta") if isinstance(data.get("word_search_meta"), dict) else {}
        output_type = str(meta.get("output_type") or "").strip()
        fields["generator"] = (
            "Book Generator" if output_type == "book" or int(data.get("puzzle_count") or 1) > 1 else "Worksheet Generator"
        )
    if not fields.get("worksheets"):
        count = int(data.get("puzzle_count") or 1)
        fields["worksheets"] = f"{count} - {'Full book' if count >= 10 else 'Mini pack'}"

    meta = data.get("word_search_meta") if isinstance(data.get("word_search_meta"), dict) else {}
    puzzle_count = int(data.get("puzzle_count") or meta.get("worksheets") or 1)
    is_book = data.get("is_book")
    if is_book is None:
        is_book = puzzle_count > 1 or meta.get("output_type") == "book" or "Book" in str(fields.get("generator") or "")

    package_id = str(data.get("package_id") or "")
    cover_design = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None
    if not package_id and cover_design:
        package_id = str(cover_design.get("package_id") or "")
    if not package_id:
        package_id = uuid.uuid4().hex

    if not meta:
        meta = {
            "output_type": "book" if is_book else "single_worksheet",
            "worksheets": puzzle_count,
            "words_per_puzzle": int(fields.get("words_per_puzzle") or 10),
            "difficulty": str(fields.get("difficulty") or "Medium"),
            "grid_size": 12,
            "include_answer_key": _yes(fields, "include_answers"),
        }

    data["title"] = title
    data["fields"] = fields
    data["is_book"] = bool(is_book)
    data["is_pdf"] = True
    data["puzzle_count"] = puzzle_count
    data["word_search_meta"] = meta
    data["package_id"] = package_id
    return data


def _word_search_plan(fields: dict) -> dict:
    """Shared Word Search PDF settings used for generation and rebuilds."""
    from services.factory.puzzle_plan import OUTPUT_BOOK, parse_puzzle_output_plan

    # Product title: book_title (new form) > theme (legacy) > default
    title = _f(fields, "book_title") or _f(fields, "theme") or "Word Search Puzzle"
    output = parse_puzzle_output_plan(fields, product_type="word_search")
    # Puzzle count: puzzles (new form) > worksheets/page_count (legacy)
    worksheets_raw = _f(fields, "puzzles") or _f(fields, "worksheets") or str(output["page_count"])
    worksheets = int(worksheets_raw) if worksheets_raw.isdigit() else output["page_count"]
    output_type = output["output_type"]
    if output_type == OUTPUT_BOOK:
        normalized_output = "book"
    elif output_type == "single_page":
        normalized_output = "single_page"
    else:
        normalized_output = "single_worksheet"
    difficulty = _f(fields, "difficulty", "Medium").lower()
    words_per_puzzle = int(_f(fields, "words_per_puzzle", "10"))

    # Grid size: explicit selection (new form) > auto from word count (legacy)
    explicit_grid = _f(fields, "grid_size", "")
    if "12" in explicit_grid:
        grid_size = 12
    elif "18" in explicit_grid:
        grid_size = 18
    elif explicit_grid and explicit_grid.isdigit():
        grid_size = int(explicit_grid)
    elif words_per_puzzle <= 8:
        grid_size = 12
    elif words_per_puzzle <= 12:
        grid_size = 15
    else:
        grid_size = 18

    # Creation mode: "Custom word list" (new form) > use_custom_words (legacy)
    creation_mode = _f(fields, "creation_mode", "")
    if "Custom" in creation_mode or "custom" in creation_mode:
        use_custom = True
    elif creation_mode:
        use_custom = False
    else:
        use_custom = "Yes" in _f(fields, "use_custom_words", "")

    return {
        "title": title,
        "is_book": output["is_book"],
        "worksheets": worksheets,
        "output_type": normalized_output,
        "difficulty": difficulty,
        "words_per_puzzle": words_per_puzzle,
        "grid_size": grid_size,
        "include_answer_key": output["include_answer_key"],
        "use_custom": use_custom,
        "include_cover": output["include_cover"],
    }


def _resolve_word_search_words(fields: dict, plan: dict, *, stored_words: str = "") -> str:
    # Only use stored words from a saved project when the user explicitly selected
    # "Custom word list" mode.  If they switched to "Topic" mode, generate fresh words.
    custom_words = str(stored_words or _f(fields, "custom_words", "")).strip()
    if plan["use_custom"]:
        return custom_words

    # Topic / AI mode: generate fresh words from the topic, not old saved words.
    total_words_needed = plan["words_per_puzzle"]
    if plan["output_type"] == "book":
        total_words_needed = plan["words_per_puzzle"] * plan["worksheets"]
    fetch_count = word_list_fetch_target(total_words_needed)

    if not plan["use_custom"]:
        # Pre-check: verify the topic has a confident local vocabulary pack match
        # before spending an AI call. Topics with no local match will fall back to
        # generic words and get blocked at export QA. Catch it here with a clear
        # message instead.
        from services.word_search.word_lists import suggest_words_from_topic

        topic_theme = _f(fields, "theme") or ""
        matched_words, w_warnings, w_errors, matched_pack_id = suggest_words_from_topic(
            topic_theme,
            max_words=max(12, fetch_count),
        )
        # matched_pack_id == "" means no local pack matched — AI would produce
        # generic fallback words that export QA will reject. Block now.
        if not matched_pack_id and not w_errors:
            raise ValueError(
                f'The topic "{topic_theme}" does not match any known vocabulary pack '
                "and the AI fallback would produce generic words. "
                "Please choose a more specific, recognizable topic "
                "(e.g. 'Animals', 'Food', 'Science', 'Sports', 'Space')."
            )

        system = "You are a word list generator. Generate only words, one per line, no explanations."
        user = (
            f"Generate {fetch_count} unique single words for word search puzzles about: "
            f"{_f(fields, 'theme')}. Use only letters A-Z, one word per line, no numbers."
        )
        try:
            custom_words = chat(
                system=system,
                user=user,
                max_completion_tokens=max(800, fetch_count * 12),
            )
            custom_words = "\n".join([w.strip() for w in custom_words.split("\n") if w.strip()])
        except Exception:
            custom_words = "apple\nbanana\ncherry\ndragon\nenergy\nforest\ngarden\nharbor\nisland\njungle"
    return custom_words


def _build_word_search_cover(fields: dict, plan: dict, package_id: str) -> dict | None:
    os.makedirs(os.path.join(EXPORTS_DIR, package_id), exist_ok=True)
    puzzle_count = plan["worksheets"] if plan["output_type"] == "book" else 1
    payload = build_word_search_payload_from_fields(
        fields,
        title=plan["title"],
        puzzle_count=puzzle_count,
        package_id=package_id,
    )
    cover = generate_cover_from_payload(payload, overrides={"use_ai_image": True})
    try:
        cover, _asset = regenerate_cover_image_for_cover(cover, package_id)
    except Exception:
        pass
    return cover


def _word_search_pdf_payload(
    fields: dict,
    *,
    stored_words: str = "",
    cover_design: dict | None = None,
    package_id: str = "",
) -> dict:
    from services.factory.product_qa_agent import (
        ProductQAResult,
        safe_fix_plan,
        validate_generated_product,
        validate_product_plan,
    )

    plan = _word_search_plan(fields)

    # QA pre-flight: validate plan and auto-fix safe issues
    qa_pre = validate_product_plan("word_search", fields, plan)
    if qa_pre.blocked_export:
        raise RuntimeError(
            f"QA blocked export: {'; '.join(qa_pre.errors)}. "
            "Please check your output format and cover settings."
        )

    # Apply auto-fixes (e.g. strip cover from single worksheet)
    fixed_fields, fixes = safe_fix_plan("word_search", fields, plan)
    if fixes:
        # Re-parse plan after field fixes
        plan = _word_search_plan(fixed_fields)

    custom_words = _resolve_word_search_words(fixed_fields, plan, stored_words=stored_words)
    pkg = package_id or uuid.uuid4().hex

    # Only build a cover when output format allows it
    is_book = plan["output_type"] == "book"
    # include_cover: explicit form override > default to True for books
    form_include_cover = _f(fields, "include_cover", "")
    if form_include_cover.lower() in {"yes", "true"}:
        include_cover = True
    elif form_include_cover.lower() in {"no", "false"}:
        include_cover = False
    else:
        include_cover = is_book
    cover = None
    if is_book and include_cover:
        cover = cover_design
        if cover is None:
            cover = _build_word_search_cover(fixed_fields, plan, pkg)
        elif cover is not None:
            cover = dict(cover)
            cover["package_id"] = pkg

    pdf_request = WordSearchPdfRequest(
        product_title=plan["title"],
        subtitle=(cover or {}).get("subtitle") or _f(fields, "subtitle") or "",
        audience=_f(fields, "audience") or "",
        theme=_f(fields, "theme") or "",
        mode="custom_word_list",
        custom_words=custom_words,
        grid_size=plan["grid_size"],
        difficulty=plan["difficulty"],
        output_type=plan["output_type"],
        number_of_puzzles=plan["worksheets"],
        words_per_puzzle=plan["words_per_puzzle"],
        include_answer_key=plan["include_answer_key"],
        include_cover=include_cover,
        cover_design=cover if is_book else None,
        package_id=pkg,
        seed=None,
    )
    result = build_word_search_pdf(pdf_request)
    if result.errors or not result.pdf_bytes:
        raise RuntimeError(f"Failed to generate Word Search PDF: {result.errors}")

    pdf_bytes = result.pdf_bytes
    pdf_has_cover_page = bool(cover) and is_book

    # QA post-generation: verify cover not in wrong output, answer key correct
    qa_post = validate_generated_product(
        product_type="word_search",
        fields=fixed_fields,
        plan=plan,
        pdf_bytes=pdf_bytes,
        layout_info=result.layout_info if hasattr(result, "layout_info") else None,
        result_so_far=qa_pre,
    )

    if qa_post.blocked_export:
        raise RuntimeError(
            f"QA post-generation blocked export: {'; '.join(qa_post.errors)}. "
            "The PDF was regenerated incorrectly — please try again."
        )

    image_jobs = []
    job = cover_image_job(cover) if cover else None
    if job:
        image_jobs.append(job)

    return {
        "product_type": "word_search",
        "product_label": "Word Search",
        "title": plan["title"],
        "subtitle": (cover or {}).get("subtitle") or "",
        "fields": fixed_fields,
        "content": "",
        "pdf_bytes": base64.b64encode(pdf_bytes).decode("utf-8"),
        "filename": result.filename,
        "puzzle_count": plan["worksheets"],
        "is_pdf": True,
        "is_book": is_book,
        "custom_words": custom_words,
        "package_id": pkg,
        "cover_design": cover,
        "cover_prompt": (cover or {}).get("image_prompt") or "",
        "image_jobs": image_jobs,
        "word_search_meta": {
            "output_type": plan["output_type"],
            "worksheets": plan["worksheets"],
            "words_per_puzzle": plan["words_per_puzzle"],
            "difficulty": plan["difficulty"],
            "grid_size": plan["grid_size"],
            "include_answer_key": plan["include_answer_key"],
        },
        "pdf_has_cover_page": pdf_has_cover_page,
        "qa_report": qa_post.as_dict(),
    }


def apply_word_search_cover_to_saved_data(data: dict, cover_design: dict) -> dict:
    """Update a saved Word Search project cover without regenerating puzzle content."""
    import base64

    from services.word_search.pdf_cover import merge_cover_into_word_search_pdf

    data = normalize_word_search_project_data(data)

    # HARD GUARD: single worksheet / single page must NEVER have a cover.
    # Only process cover for book output types.
    if not data.get("is_book"):
        # Single worksheet: strip any cover_design passed and return without changes
        if cover_design:
            data["cover_design"] = None
            data["pdf_has_cover_page"] = False
        return data

    cover_design = dict(cover_design or {})
    package_id = str(cover_design.get("package_id") or data.get("package_id") or "")
    cover_design["package_id"] = package_id
    had_cover_page = bool(data.get("pdf_has_cover_page"))
    stored_words = str(data.get("custom_words") or "").strip()

    if stored_words:
        payload = _word_search_pdf_payload(
            data.get("fields") or {},
            stored_words=stored_words,
            cover_design=cover_design,
            package_id=package_id,
        )
        data.update(
            {
                "pdf_bytes": payload.get("pdf_bytes"),
                "filename": payload.get("filename"),
                "cover_design": payload.get("cover_design") or cover_design,
                "package_id": payload.get("package_id") or package_id,
                "custom_words": stored_words,
                "pdf_has_cover_page": bool(cover_design) and data.get("is_book"),
            }
        )
        return data

    existing_pdf = data.get("pdf_bytes")
    if not existing_pdf:
        raise ValueError("Regenerate the word search product before saving a cover.")

    merged = merge_cover_into_word_search_pdf(
        base64.b64decode(existing_pdf),
        cover_design,
        replace_first_page=had_cover_page,
    )
    data["pdf_bytes"] = base64.b64encode(merged).decode("ascii")
    data["cover_design"] = cover_design
    data["package_id"] = package_id
    data["pdf_has_cover_page"] = True
    return data


def rebuild_word_search_pdf_from_data(data: dict) -> dict:
    """Rebuild Word Search PDF from saved project data without regenerating word lists."""
    data = normalize_word_search_project_data(data)
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    payload = _word_search_pdf_payload(
        fields,
        stored_words=str(data.get("custom_words") or ""),
        cover_design=data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None,
        package_id=str(data.get("package_id") or ""),
    )
    return payload


def _generate_word_search_pdf(fields: dict) -> dict:
    """Generate actual Word Search PDF using the pdf_builder."""
    return _word_search_pdf_payload(fields)


def normalize_crossword_project_data(data: dict) -> dict:
    """Fill missing Crossword metadata on saved projects."""
    data = dict(data or {})
    if data.get("product_type") != "crossword":
        return data

    fields = dict(data.get("fields") if isinstance(data.get("fields"), dict) else {})
    title = _normalize_crossword_theme_title(
        (data.get("title") or fields.get("theme") or "Crossword Puzzle Book").strip()
    )
    if fields.get("theme"):
        fields["theme"] = _normalize_crossword_theme_title(fields.get("theme"))
    else:
        fields["theme"] = title
    if fields.get("book_title"):
        fields["book_title"] = _normalize_crossword_theme_title(fields.get("book_title"))

    output_format = str(fields.get("output_format") or "").strip().lower()
    meta = data.get("crossword_meta") if isinstance(data.get("crossword_meta"), dict) else {}
    is_book = data.get("is_book")
    if is_book is None:
        is_book = (
            "book" in output_format
            or str(meta.get("output_type") or "") == "book"
            or "Book" in str(fields.get("generator") or "")
            or int(data.get("puzzle_count") or 1) > 1
        )

    if not fields.get("generator"):
        fields["generator"] = "Book Generator" if is_book else "Worksheet Generator"

    # Full Book sellable standard: always 12 puzzles / 25 pages.
    # Rewrite legacy saved fields (puzzles=5/10) so export/rebuild cannot
    # re-serve a thin book from stale form values.
    if is_book or "book" in output_format:
        fields["output_format"] = fields.get("output_format") or "Full Book"
        if "book" not in str(fields.get("output_format")).lower():
            fields["output_format"] = "Full Book"
        fields["puzzles"] = "12"
        fields["worksheets"] = "12"
        puzzle_count = 12
        is_book = True
    else:
        puzzle_count = 1
        fields["puzzles"] = "1"

    if not meta:
        meta = {}
    meta = {
        **meta,
        "output_type": "book" if is_book else "single_worksheet",
        "worksheets": puzzle_count,
        "words_per_puzzle": int(meta.get("words_per_puzzle") or _f(fields, "words_per_puzzle", "10") or 10),
        "difficulty": str(meta.get("difficulty") or fields.get("difficulty") or "Medium"),
        "grid_size": int(meta.get("grid_size") or 15),
        "include_answer_key": bool(meta.get("include_answer_key", _yes(fields, "include_answer_key") or _yes(fields, "include_answers"))),
    }

    package_id = str(data.get("package_id") or "")
    cover_design = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None
    if not package_id and cover_design:
        package_id = str(cover_design.get("package_id") or "")
    if not package_id:
        package_id = uuid.uuid4().hex

    if cover_design is not None and is_book:
        cover_design = dict(cover_design)
        cover_design["title"] = title
        difficulty_label = str(meta.get("difficulty") or "Easy").strip().title() or "Easy"
        cover_design["subtitle"] = f"{puzzle_count} Crossword Puzzles - {difficulty_label} Level"
        cover_design["use_ai_image"] = False
        data["cover_design"] = cover_design

    data["title"] = title
    data["fields"] = fields
    data["is_book"] = bool(is_book)
    data["is_pdf"] = True
    data["puzzle_count"] = puzzle_count
    data["crossword_meta"] = meta
    data["package_id"] = package_id
    return data


def crossword_full_book_pdf_is_valid(pdf_bytes: bytes, *, expected_puzzles: int = 12) -> bool:
    """Return True only for a Full Book PDF with cover + N puzzles + N keys."""
    import io

    try:
        from pypdf import PdfReader
    except Exception:
        return False
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
    except Exception:
        return False
    expected_pages = 1 + (expected_puzzles * 2)
    if len(reader.pages) != expected_pages:
        return False
    subject = ""
    if reader.metadata is not None:
        subject = str(reader.metadata.subject or "")
    needle = f"{expected_puzzles} Crossword Puzzles"
    return needle in subject


_GOAL_RUSH_TITLE_RE = re.compile(r"(?i)\bGoal\s+Rush\b")


def _normalize_crossword_theme_title(text: str) -> str:
    """Correct the known Gold Rush near-match typo in titles/themes only."""
    return _GOAL_RUSH_TITLE_RE.sub("Gold Rush", str(text or ""))


def _crossword_plan(fields: dict) -> dict:
    """Shared Crossword PDF settings used for generation and rebuilds."""
    from services.factory.puzzle_plan import OUTPUT_BOOK, parse_puzzle_output_plan

    # Product title: book_title (new form) > theme (legacy) > default
    title = _normalize_crossword_theme_title(
        _f(fields, "book_title") or _f(fields, "theme") or "Crossword Puzzle Book"
    )
    # sub_topic is the theme for word selection — use theme field
    sub_topic = _normalize_crossword_theme_title(
        _f(fields, "theme") or _f(fields, "subtitle")
    )
    output = parse_puzzle_output_plan(fields, product_type="crossword")
    # Puzzle count: puzzles (new form) > worksheets/page_count (legacy)
    worksheets_raw = _f(fields, "puzzles") or _f(fields, "worksheets") or str(output["page_count"])
    worksheets = int(worksheets_raw) if worksheets_raw.isdigit() else output["page_count"]
    output_type = output["output_type"]
    difficulty = _f(fields, "difficulty", "Medium").lower()
    words_per_puzzle = int(_f(fields, "words_per_puzzle", "10") or 10)
    grid_size = 15 if words_per_puzzle <= 10 else 17
    normalized_output = output_type
    if output_type == OUTPUT_BOOK:
        normalized_output = "book"
        # Full Book sellable standard: always 12 puzzles → 25 pages
        # (1 cover + 12 puzzles + 12 answer keys). Legacy UI values of 5/10
        # and browser autofill must not silently produce a thin book.
        worksheets = 12
        words_per_puzzle = max(8, words_per_puzzle)
    elif output_type == "single_page":
        normalized_output = "single_page"
        worksheets = 1
    else:
        normalized_output = "single_worksheet"
        worksheets = 1
    return {
        "title": title,
        "sub_topic": sub_topic,
        "is_book": output["is_book"],
        "worksheets": worksheets,
        "output_type": normalized_output,
        "difficulty": difficulty,
        "words_per_puzzle": words_per_puzzle,
        "grid_size": grid_size,
        "include_answer_key": output["include_answer_key"],
        "use_custom": str(_f(fields, "creation_mode", "")).strip() == "Custom word list",
        "include_cover": output["include_cover"],
    }


def _resolve_crossword_words(fields: dict, plan: dict, *, stored_words: str = "") -> str:
    # Only use stored words from a saved project when the user explicitly selected
    # "Custom word list" mode.  If they switched to "Topic" mode, generate fresh words
    # from the topic regardless of what was saved previously.
    custom_words = str(stored_words or _f(fields, "custom_words", "")).strip()
    if plan["use_custom"]:
        # User chose Custom word list — use whatever words are available.
        # If none, return empty so the downstream guard fires with a clear message.
        return custom_words

    # Topic mode: ignore any previously saved custom words and resolve locally.
    # Do not call paid AI word generation during topic resolution.
    from services.crossword.word_entries import suggest_crossword_words_from_topic

    words_per = int(plan["words_per_puzzle"] or 10)
    if plan["output_type"] == "book":
        # Oversubscribe so book.py can place ≥8 answers per puzzle after interlocking.
        candidates_per = max(words_per + 4, 12)
        total = candidates_per * int(plan["worksheets"] or 1)
    else:
        total = words_per
    needed = max(12, total)
    # sub_topic is the primary word-selection signal (normalized theme)
    sub_topic = _normalize_crossword_theme_title(
        plan.get("sub_topic") or _f(fields, "subtitle") or _f(fields, "theme")
    )
    words, _warnings, errors = suggest_crossword_words_from_topic(sub_topic, max_words=needed)
    if words and len(words) >= min(8, needed):
        return "\n".join(words)
    message = (
        "Crossword could not find enough topic-relevant words and clues for this theme. "
        "Please correct the theme or provide a custom word list."
    )
    if errors:
        raise ValueError(errors[0] if errors[0] else message)
    raise ValueError(message)


def _build_crossword_cover(fields: dict, plan: dict, package_id: str) -> dict | None:
    os.makedirs(os.path.join(EXPORTS_DIR, package_id), exist_ok=True)
    puzzle_count = plan["worksheets"] if plan["output_type"] == "book" else 1
    # Keep theme/title corrections on the cover payload fields.
    cover_fields = dict(fields or {})
    if cover_fields.get("book_title"):
        cover_fields["book_title"] = _normalize_crossword_theme_title(cover_fields.get("book_title"))
    if cover_fields.get("theme"):
        cover_fields["theme"] = _normalize_crossword_theme_title(cover_fields.get("theme"))
    payload = build_crossword_payload_from_fields(
        cover_fields,
        title=plan["title"],
        puzzle_count=puzzle_count,
        package_id=package_id,
    )
    # Local cover design only — do not auto-call AI image generation.
    cover = generate_cover_from_payload(payload, overrides={"use_ai_image": False})
    # Enforce ASCII subtitle so PDF metadata/headings never say a wrong count
    # and never use unicode middle-dots that render with broken spacing.
    difficulty_label = (plan.get("difficulty") or "Easy").strip().title() or "Easy"
    if plan["output_type"] == "book":
        cover["subtitle"] = f"{puzzle_count} Crossword Puzzles - {difficulty_label} Level"
    cover["use_ai_image"] = False
    cover["text_overlay"] = True
    cover["title"] = plan["title"]
    cover["topic"] = plan.get("sub_topic") or plan["title"]
    cover["difficulty"] = difficulty_label
    cover["audience"] = str(cover_fields.get("audience") or "").strip()
    cover["package_id"] = package_id
    # Customer Cover Editor "Download Cover" needs exports/<pkg>/img_cover.png.
    from services.crossword.pdf_cover import ensure_crossword_cover_png

    ensure_crossword_cover_png(cover, package_id, force=True)
    return cover


def _crossword_pdf_payload(
    fields: dict,
    *,
    stored_words: str = "",
    cover_design: dict | None = None,
    package_id: str = "",
) -> dict:
    from services.factory.product_qa_agent import (
        ProductQAResult,
        safe_fix_plan,
        validate_generated_product,
        validate_product_plan,
    )

    plan = _crossword_plan(fields)

    # QA pre-flight
    qa_pre = validate_product_plan("crossword", fields, plan)
    if qa_pre.blocked_export:
        raise RuntimeError(
            f"QA blocked export: {'; '.join(qa_pre.errors)}. "
            "Please check your output format and cover settings."
        )

    fixed_fields, fixes = safe_fix_plan("crossword", fields, plan)
    if fixes:
        plan = _crossword_plan(fixed_fields)

    custom_words = _resolve_crossword_words(fixed_fields, plan, stored_words=stored_words)

    # Guard: crossword requires at least 4 words to build a usable puzzle.
    # Fewer words causes a confusing multi-error cascade from the engine + QA agent.
    # Catch it here with one clear message.
    submitted_lines = [ln.strip() for ln in custom_words.splitlines() if ln.strip()]
    if len(submitted_lines) < 4:
        raise ValueError(
            f"Crossword requires at least 4 words, but only {len(submitted_lines)} were submitted. "
            f"Please enter at least 4 words (one per line) in the Custom Words field. "
            f"For shorter lists, use the 'Topic (AI generates words)' option instead. "
            f"Note: the 'Topic' option may use the configured AI service and may create an API charge."
        )

    pkg = package_id or uuid.uuid4().hex
    is_book = plan["output_type"] == "book"
    cover = None
    if is_book:
        cover = cover_design
        if cover is None:
            cover = _build_crossword_cover(fixed_fields, plan, pkg)
        else:
            cover = dict(cover)
            cover["package_id"] = pkg

    mode = "custom_word_list" if plan["use_custom"] and custom_words.strip() else "topic"
    theme_label = plan.get("sub_topic") or plan["title"]
    # Keep Topic-mode resolved vocabulary authoritative for book.py.
    # Custom Word List mode continues to use the user's custom words above.
    pdf_request = CrosswordPdfRequest(
        product_title=plan["title"],
        subtitle=(cover or {}).get("subtitle") or "",
        theme=theme_label,
        sub_topic=theme_label,
        difficulty=plan["difficulty"],
        grid_size=plan["grid_size"],
        output_type=plan["output_type"],
        number_of_puzzles=plan["worksheets"],
        words_per_puzzle=plan["words_per_puzzle"],
        include_answer_key=plan["include_answer_key"],
        include_cover=is_book and bool(cover),
        cover_design=cover if is_book else None,
        custom_words=custom_words,
        mode=mode,
        package_id=pkg,
        use_ai_words=False,
    )
    result = build_crossword_pdf(pdf_request)
    if result.errors or not result.pdf_bytes:
        raise RuntimeError(f"Failed to generate Crossword PDF: {result.errors}")

    pdf_bytes = result.pdf_bytes
    pdf_has_cover_page = bool(cover) and is_book

    # Aggregate word placement stats across all puzzles for user feedback
    all_placed = []
    all_rejected = []
    for puz in result.puzzles:
        all_placed.extend(puz.placed_words or [])
        all_rejected.extend(puz.rejected_words or [])
    submitted_words = [w.strip().upper() for w in custom_words.splitlines() if w.strip()]
    placed_words = [w.strip().upper() for w in all_placed]
    rejected_words = [w.strip().upper() for w in all_rejected]
    # Words the grid explicitly tried and couldn't interlock
    _placed_set = {w.upper() for w in placed_words}
    _grid_rejected = {w.upper() for w in rejected_words if w.upper() not in _placed_set}
    # Words that were submitted but never reached the grid at all
    _submitted_set = {w.upper() for w in submitted_words}
    unplaced_words = sorted(_submitted_set - _placed_set - _grid_rejected)

    # QA post-generation: pass crossword layout info so answer key detection works
    cw_layout_info = dict(result.layout_info or {})
    if cw_layout_info.get("answer_key_page_count", 0) > 0:
        cw_layout_info["answer_key_validated"] = True
    qa_post = validate_generated_product(
        product_type="crossword",
        fields=fixed_fields,
        plan=plan,
        pdf_bytes=pdf_bytes,
        layout_info=cw_layout_info,
        result_so_far=qa_pre,
    )
    if qa_post.blocked_export:
        raise RuntimeError(
            f"QA post-generation blocked export: {'; '.join(qa_post.errors)}."
        )

    image_jobs = []
    if is_book and cover:
        job = cover_image_job(cover)
        if job:
            image_jobs.append(job)

    # Persist the enforced plan count into saved fields so re-open/export never
    # reintroduces a stale UI value such as puzzles=10 for Full Book.
    out_fields = dict(fixed_fields)
    if plan["output_type"] == "book":
        out_fields["puzzles"] = str(plan["worksheets"])
        out_fields["worksheets"] = str(plan["worksheets"])
        if "book" not in str(out_fields.get("output_format") or "").lower():
            out_fields["output_format"] = "Full Book"
    else:
        out_fields["puzzles"] = "1"

    return {
        "product_type": "crossword",
        "product_label": "Crossword Puzzle Book",
        "title": plan["title"],
        "subtitle": (cover or {}).get("subtitle") or "",
        "fields": out_fields,
        "content": "",
        "pdf_bytes": base64.b64encode(pdf_bytes).decode("utf-8"),
        "filename": result.filename,
        "puzzle_count": plan["worksheets"],
        "is_pdf": True,
        "is_book": is_book,
        "custom_words": custom_words,
        "package_id": pkg,
        "cover_design": cover if is_book else None,
        "cover_prompt": (cover or {}).get("image_prompt") or "" if is_book else "",
        "image_jobs": image_jobs,
        "crossword_meta": {
            "output_type": plan["output_type"],
            "worksheets": plan["worksheets"],
            "words_per_puzzle": plan["words_per_puzzle"],
            "difficulty": plan["difficulty"],
            "grid_size": plan["grid_size"],
            "include_answer_key": plan["include_answer_key"],
        },
        # Word placement feedback: tells the user exactly which words were placed
        # and which could not fit in the crossword grid (by letter overlap constraints).
        "word_placement": {
            "submitted_count": len(submitted_words),
            "placed_count": len(placed_words),
            "unplaced_count": len(unplaced_words),
            "placed_words": placed_words,
            "rejected_words": list(_grid_rejected),
            "unplaced_words": unplaced_words,
            "note": (
                f"{len(placed_words)} of {len(submitted_words)} submitted words were placed."
                + (f" {', '.join(unplaced_words)} could not fit in the grid."
                   if unplaced_words else
                   " All submitted words were placed in the grid.")
            ),
        },
        "pdf_has_cover_page": pdf_has_cover_page,
        "qa_report": qa_post.as_dict(),
    }


def apply_crossword_cover_to_saved_data(data: dict, cover_design: dict) -> dict:
    """Update a saved Crossword project cover without regenerating puzzle content.

    Topic-mode books store the resolved word pool in custom_words for packaging
    continuity. That must NOT trigger a full puzzle rebuild — merge the cover
    into the QA-approved PDF bytes instead.
    """
    import base64

    from services.crossword.pdf_cover import (
        ensure_crossword_cover_png,
        merge_cover_into_crossword_pdf,
    )

    data = normalize_crossword_project_data(data)
    meta = data.get("crossword_meta") if isinstance(data.get("crossword_meta"), dict) else {}
    if meta.get("output_type") != "book" and not data.get("is_book"):
        raise ValueError("Single crossword worksheets do not include a cover page.")

    cover_design = dict(cover_design or {})
    package_id = str(cover_design.get("package_id") or data.get("package_id") or "")
    cover_design["package_id"] = package_id
    had_cover_page = bool(data.get("pdf_has_cover_page"))

    existing_pdf = data.get("pdf_bytes")
    if not existing_pdf:
        # No approved PDF to merge into — only then rebuild from fields/words.
        stored_words = str(data.get("custom_words") or "").strip()
        if not stored_words:
            raise ValueError("Regenerate the crossword product before saving a cover.")
        payload = _crossword_pdf_payload(
            data.get("fields") or {},
            stored_words=stored_words,
            cover_design=cover_design,
            package_id=package_id,
        )
        data.update(
            {
                "pdf_bytes": payload.get("pdf_bytes"),
                "filename": payload.get("filename"),
                "cover_design": payload.get("cover_design") or cover_design,
                "package_id": payload.get("package_id") or package_id,
                "custom_words": stored_words,
                "pdf_has_cover_page": True,
            }
        )
        return data

    if package_id and not cover_design.get("local_image_path"):
        candidate = os.path.join(EXPORTS_DIR, package_id, "img_cover.png")
        if os.path.isfile(candidate):
            cover_design["local_image_path"] = candidate

    ensure_crossword_cover_png(cover_design, package_id, force=True)

    merged = merge_cover_into_crossword_pdf(
        base64.b64decode(existing_pdf),
        cover_design,
        replace_first_page=had_cover_page,
    )
    data["pdf_bytes"] = base64.b64encode(merged).decode("ascii")
    data["cover_design"] = cover_design
    data["package_id"] = package_id
    data["pdf_has_cover_page"] = True
    return data


def rebuild_crossword_pdf_from_data(data: dict) -> dict:
    data = normalize_crossword_project_data(data)
    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    return _crossword_pdf_payload(
        fields,
        stored_words=str(data.get("custom_words") or ""),
        cover_design=data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None,
        package_id=str(data.get("package_id") or ""),
    )


def _coloring_book_plan(fields: dict) -> dict:
    """Parse coloring book form fields into a structured plan dict."""
    from services.factory.puzzle_plan import parse_puzzle_output_plan

    return parse_puzzle_output_plan(fields, product_type="coloring_book")


def _coloring_book_pdf_payload(fields: dict, *, package_id: str = "") -> dict:
    from services.factory.puzzle_plan import normalize_coloring_page_count

    plan = _coloring_book_plan(fields)
    pkg = package_id or uuid.uuid4().hex
    print(f"[_coloring_book_pdf_payload] fields: output_format={fields.get('output_format')!r} pages={fields.get('pages')!r}")
    print(f"[_coloring_book_pdf_payload] plan: output_type={plan.get('output_type')!r} is_book={plan.get('is_book')} page_count={plan.get('page_count')}")

    # Normalize page count (respects Single Sheet → 1, caps excessive counts at 40)
    output_type = plan.get("output_type", "book")
    raw_pages = fields.get("pages", "")
    try:
        requested_count = int(raw_pages) if str(raw_pages).strip() else None
    except (ValueError, TypeError):
        requested_count = None
    pages, page_warnings = normalize_coloring_page_count(output_type, requested_count)

    # ── SINGLE SHEET ENFORCEMENT ────────────────────────────────────────────
    # Rule: output_type="single_page" ALWAYS means one coloring page, no cover.
    # Apply at source — not derivable from is_book alone (form may send wrong
    # output_format, or pages field may default to 12 regardless of selection).
    # ────────────────────────────────────────────────────────────────────────
    if output_type == "single_page":
        pages = 1
        plan = dict(plan, include_cover=False)  # override without mutating original

    creation_mode = str(fields.get("creation_mode", "theme")).lower()

    # Determine title and theme based on creation mode.
    # Theme must remain the full user niche/story — never replaced by a short title.
    from services.coloring_book.prompt_engine import derive_cover_copy

    if creation_mode == "scratch":
        theme = _f(fields, "theme") or "Fun Adventure"
        product_title = _f(fields, "product_title") or _f(fields, "coloring_title") or ""
    elif creation_mode == "market_research":
        theme = _f(fields, "theme") or _f(fields, "_cb_benchmark_niche") or "Coloring Book"
        product_title = _f(fields, "product_title") or _f(fields, "coloring_title") or ""
    else:
        theme = _f(fields, "theme") or _f(fields, "coloring_title") or "Coloring Book"
        product_title = _f(fields, "coloring_title") or ""

    cover_copy = derive_cover_copy(
        theme,
        product_title=product_title,
        subtitle=_f(fields, "subtitle"),
    )
    if not product_title or product_title.lower() == theme.lower() or len(product_title) > 48:
        product_title = cover_copy.title
    subtitle = _f(fields, "subtitle") or cover_copy.subtitle

    quality_mode = _normalize_quality_mode(fields)
    from services.coloring_book.prompt_engine import is_bank_rescue_theme

    # Staged approval for bank-rescue AI books — never silently spend on 12 interiors.
    stage = (
        _f(fields, "generation_stage")
        or _f(fields, "coloring_generation_stage")
        or ""
    ).strip().lower()
    if stage not in {"cover_preview", "sample_interior", "full"}:
        if is_bank_rescue_theme(theme) and quality_mode == "ai_image_coloring_page" and output_type != "single_page":
            stage = "cover_preview"
        else:
            stage = "full"

    character_approved = str(fields.get("character_approved") or "").lower() in {
        "1", "true", "yes", "on",
    }
    sample_approved = str(fields.get("sample_approved") or "").lower() in {
        "1", "true", "yes", "on",
    }
    reference_image_path = _f(fields, "reference_image_path") or _f(fields, "approved_cover_path")
    if not reference_image_path and pkg:
        candidate = os.path.join(EXPORTS_DIR, pkg, "img_cover.png")
        if os.path.isfile(candidate):
            reference_image_path = candidate

    # Reuse package_id across staged approval so cover/sample images persist.
    pkg = _f(fields, "package_id") or pkg

    pdf_request = ColoringBookPdfRequest(
        product_title=product_title,
        subtitle=subtitle,
        theme=theme,
        topic=_f(fields, "topic") or "",
        setting=_f(fields, "setting") or "",
        main_character=_f(fields, "main_character") or _f(fields, "character_name") or "",
        page_count=pages,
        age_group=_f(fields, "age_group"),
        art_style=_f(fields, "art_style"),
        include_captions=_yes(fields, "include_captions"),
        output_type=output_type,
        include_cover=plan.get("include_cover", plan.get("is_book", True)),
        package_id=pkg,
        seed=None,
        quality_mode=quality_mode,
        creation_mode=creation_mode,
        benchmark_niche=_f(fields, "_cb_benchmark_niche"),
        benchmark_audience=_f(fields, "_cb_benchmark_audience"),
        benchmark_reason=_f(fields, "_cb_benchmark_reason"),
        generation_stage=stage,
        character_approved=character_approved,
        sample_approved=sample_approved,
        reference_image_path=reference_image_path,
        force_image_regen=str(fields.get("force_image_regen") or "").lower() in {
            "1", "true", "yes", "on",
        },
    )
    result = build_coloring_book_pdf(pdf_request)
    if result.errors:
        # Preview stages may return structured approval errors without PDF bytes.
        if stage in {"cover_preview", "sample_interior"} or "Approval required" in " ".join(result.errors):
            return {
                "product_type": "coloring_book",
                "product_label": "Coloring Book",
                "title": product_title,
                "subtitle": subtitle,
                "fields": fields,
                "content": "",
                "warnings": list(result.warnings or []),
                "errors": list(result.errors or []),
                "package_id": pkg,
                "generation_stage": stage,
                "cover_prompt": result.cover_prompt or "",
                "sample_prompt": result.sample_prompt or "",
                "character_bible": result.character_bible,
                "consistency_notes": list(result.consistency_notes or []),
                "pages": list(result.pages or []),
                "needs_approval": True,
                "is_pdf": False,
            }
        raise RuntimeError(f"Failed to generate Coloring Book PDF: {result.errors}")
    if not result.pdf_bytes:
        raise RuntimeError(f"Failed to generate Coloring Book PDF: {result.errors}")

    image_jobs = []
    cover = result.cover_design if isinstance(result.cover_design, dict) else None
    if cover:
        job = cover_image_job(cover)
        if job:
            image_jobs.append(job)

    # Include benchmark info in response for display
    benchmark_info: dict | None = None
    if creation_mode == "market_research" and fields.get("_cb_benchmark_niche"):
        benchmark_info = {
            "niche": fields.get("_cb_benchmark_niche", ""),
            "audience": fields.get("_cb_benchmark_audience", ""),
            "reason": fields.get("_cb_benchmark_reason", ""),
        }

    # Embed FULL-PAGE cover preview (US Letter PDF page 1) for the factory UI.
    # Prefer the composed cover page (art + title overlay), not a tiny comic strip.
    cover_preview_b64 = ""
    try:
        import fitz

        if result.pdf_bytes:
            doc = fitz.open(stream=result.pdf_bytes, filetype="pdf")
            if len(doc) > 0:
                pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
                png_bytes = pix.tobytes("png")
                cover_preview_b64 = base64.b64encode(png_bytes).decode("ascii")
                preview_path = os.path.join(EXPORTS_DIR, pkg, "cover_page_preview.png")
                os.makedirs(os.path.dirname(preview_path), exist_ok=True)
                with open(preview_path, "wb") as fh:
                    fh.write(png_bytes)
            doc.close()
    except Exception:  # noqa: BLE001
        cover_preview_b64 = ""
    if not cover_preview_b64:
        cover_path = result.cover_image_path or ""
        if cover_path and os.path.isfile(cover_path):
            try:
                with open(cover_path, "rb") as fh:
                    cover_preview_b64 = base64.b64encode(fh.read()).decode("ascii")
            except Exception:  # noqa: BLE001
                cover_preview_b64 = ""

    sample_preview_b64 = ""
    if stage == "sample_interior":
        for p in result.pages or []:
            if int(p.get("page_number") or 0) == 1 and p.get("image_path") and os.path.isfile(p["image_path"]):
                try:
                    with open(p["image_path"], "rb") as fh:
                        sample_preview_b64 = base64.b64encode(fh.read()).decode("ascii")
                except Exception:  # noqa: BLE001
                    sample_preview_b64 = ""
                break

    return {
        "product_type": "coloring_book",
        "product_label": "Coloring Book",
        "title": product_title,
        "warnings": list(page_warnings) + list(result.warnings or []),
        "subtitle": subtitle,
        "fields": {**fields, "package_id": pkg, "generation_stage": stage},
        "content": "",
        "pdf_bytes": base64.b64encode(result.pdf_bytes).decode("utf-8"),
        "filename": result.filename,
        "is_pdf": True,
        "is_book": plan.get("output_type", "book") == "book",
        "package_id": pkg,
        "layout_info": result.layout_info,
        "qa_result": result.qa_result,
        "pages": list(result.pages or []),
        "cover_design": cover,
        "cover_prompt": result.cover_prompt or (cover or {}).get("image_prompt") or "",
        "cover_image_path": result.cover_image_path or "",
        "pdf_has_cover_page": bool(cover) and plan.get("output_type", "book") == "book",
        "image_jobs": image_jobs,
        "creation_mode": creation_mode,
        "character_name": _f(fields, "character_name") or _f(fields, "main_character"),
        "benchmark_info": benchmark_info,
        "generation_stage": stage,
        "character_bible": result.character_bible,
        "sample_prompt": result.sample_prompt or "",
        "consistency_notes": list(result.consistency_notes or []),
        "cover_preview_b64": cover_preview_b64,
        "sample_preview_b64": sample_preview_b64,
        "needs_approval": stage in {"cover_preview", "sample_interior"},
        "character_approved": character_approved,
        "sample_approved": sample_approved,
        "supports_reference_image": False,
        "paid_api_warning": (
            "This step uses AI image credits. Approve the cover and one sample page "
            "before we generate the rest of the book — this keeps quality high and "
            "avoids wasting credits."
            if quality_mode == "ai_image_coloring_page"
            else ""
        ),
    }


def apply_ebook_cover_to_saved_data(data: dict, cover_design: dict) -> dict:
    """Apply an edited ebook cover (title/subtitle/author/image) and refresh local cover PDF.

    Does not call paid image APIs. If img_cover.png was uploaded, it is kept.
    Export rebuilds the finished PDF with the new cover page.
    """
    data = dict(data or {})
    product_type = str(data.get("product_type") or "").lower()
    if product_type and product_type != "ebook":
        # Allow type=ebook projects that omit product_type
        if product_type not in {"", "ebook"}:
            return data

    cover_design = dict(cover_design or {})
    package_id = str(
        cover_design.get("package_id") or data.get("package_id") or data.get("export_package_id") or ""
    ).strip()
    if not package_id:
        import uuid

        package_id = uuid.uuid4().hex
    cover_design["package_id"] = package_id

    title = str(cover_design.get("title") or data.get("title") or "Untitled Ebook").strip()
    subtitle = str(cover_design.get("subtitle") or data.get("subtitle") or "").strip()
    author = str(
        cover_design.get("author")
        or cover_design.get("author_brand")
        or data.get("author_brand")
        or ""
    ).strip()
    fields = dict(data.get("fields") or {})
    if author:
        fields["author_brand"] = author
        data["author_brand"] = author
    if subtitle:
        fields["subtitle"] = subtitle
        data["subtitle"] = subtitle
    data["title"] = title

    # Prefer uploaded / regenerated PNG if present
    img_path = os.path.join(EXPORTS_DIR, package_id, "img_cover.png")
    if os.path.isfile(img_path):
        cover_design["image_path"] = img_path
        cover_design["local_image_path"] = img_path

    from services.ebook_cover_local import cover_design_from_local

    local = cover_design_from_local(
        title=title,
        subtitle=subtitle,
        author=author or "Digital Product Factory",
        package_id=package_id,
        topic=str(fields.get("topic") or data.get("source") or title),
        audience=str(fields.get("audience") or ""),
        fields=fields,
    )
    # Preserve user PNG if they uploaded one (cover_design_from_local may overwrite)
    if os.path.isfile(img_path) and os.path.getsize(img_path) > 20_000:
        local["image_path"] = img_path
        local["local_image_path"] = img_path
        local["user_uploaded_cover"] = bool(cover_design.get("user_uploaded_cover"))
    local.update({k: v for k, v in cover_design.items() if k in {"preview_html", "layout", "theme"}})
    local["title"] = title
    local["subtitle"] = subtitle
    local["author"] = author
    local["package_id"] = package_id

    data["cover_design"] = local
    data["cover_prompt"] = local.get("cover_prompt") or data.get("cover_prompt") or ""
    data["package_id"] = package_id
    data["fields"] = fields
    data["product_type"] = "ebook"
    # Force export to rebuild PDF with the new cover
    data.pop("pdf_bytes", None)
    data["cover_dirty"] = True
    return data


def apply_coloring_book_cover_to_saved_data(data: dict, cover_design: dict) -> dict:
    """Update a saved Coloring Book cover without regenerating interior pages."""
    import base64

    from services.coloring_book.pdf_cover import merge_cover_into_coloring_book_pdf

    data = dict(data or {})
    if data.get("product_type") != "coloring_book":
        return data

    fields = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    output_format = str(fields.get("output_format") or "").strip().lower()
    is_book = bool(data.get("is_book")) or "book" in output_format
    if not is_book or output_format in {"single sheet", "single page", "single_page"}:
        data["cover_design"] = None
        data["pdf_has_cover_page"] = False
        return data

    cover_design = dict(cover_design or {})
    package_id = str(cover_design.get("package_id") or data.get("package_id") or "")
    cover_design["package_id"] = package_id
    had_cover_page = bool(data.get("pdf_has_cover_page"))

    existing_pdf = data.get("pdf_bytes")
    if not existing_pdf:
        raise ValueError("Regenerate the coloring book product before saving a cover.")

    # Prefer editor asset path when present
    if package_id and not cover_design.get("local_image_path"):
        candidate = os.path.join(EXPORTS_DIR, package_id, "img_cover.png")
        if os.path.isfile(candidate):
            cover_design["local_image_path"] = candidate

    merged = merge_cover_into_coloring_book_pdf(
        base64.b64decode(existing_pdf),
        cover_design,
        replace_first_page=had_cover_page,
    )
    data["pdf_bytes"] = base64.b64encode(merged).decode("ascii")
    data["cover_design"] = cover_design
    data["package_id"] = package_id
    data["pdf_has_cover_page"] = True
    if cover_design.get("image_prompt"):
        data["cover_prompt"] = cover_design.get("image_prompt")
    # Preserve interior page metadata through cover edits
    if data.get("pages"):
        data["pages"] = list(data.get("pages") or [])
    return data


def _generate_coloring_book_pdf(fields: dict) -> dict:
    """
    Generate actual Coloring Book PDF using the coloring_book pdf_builder.

    Guarded by User Instruction Controller + Coloring Book QA Auto-Corrector:
      1. Build instruction contract before generation (fails fast on bad fields)
      2. Generate PDF normally via _coloring_book_pdf_payload
      3. QA the generated PDF against the contract
      4. Auto-correct if violations found (exactly one retry)
      5. Attach contract + QA status to the result
    """
    from services.quality.user_instruction_controller import (
        build_coloring_book_contract,
        save_instruction_contract,
    )
    from services.coloring_book.coloring_book_qa_agent import (
        validate_and_correct_coloring_book_output,
    )

    # Step 1: Build instruction contract — raises if fields are incomplete
    contract = build_coloring_book_contract(fields)

    # Step 2: Generate PDF (existing logic)
    result = _coloring_book_pdf_payload(fields)

    # Step 3: Attach contract to result
    result["instruction_contract"] = contract.to_dict()

    # Preview / approval stages: do not auto-correct or regenerate images.
    stage = str(result.get("generation_stage") or fields.get("generation_stage") or "").lower()
    if result.get("needs_approval") or stage in {"cover_preview", "sample_interior"}:
        result["qa_passed"] = bool(result.get("pdf_bytes"))
        result["qa_corrected"] = False
        result["qa_warnings"] = list(result.get("warnings") or [])
        return result

    # Step 4: QA + auto-correct the generated PDF
    try:
        pdf_b64 = result.get("pdf_bytes", "")
        if pdf_b64:
            corrected_bytes, was_corrected = validate_and_correct_coloring_book_output(
                fields=fields,
                pdf_bytes=pdf_b64,
                contract=contract.to_dict(),
                package_id=result.get("package_id", ""),
            )
            result["pdf_bytes"] = base64.b64encode(corrected_bytes).decode("utf-8")
            result["qa_passed"] = True
            result["qa_corrected"] = was_corrected
            result["qa_warnings"] = []
        else:
            result["qa_passed"] = False
            result["qa_corrected"] = False
            result["qa_warnings"] = ["No PDF bytes to QA"]
    except ValueError as exc:
        # QA failed and auto-correction also failed — propagate as error
        result["qa_passed"] = False
        result["qa_corrected"] = False
        result["qa_error"] = str(exc)
        raise

    # Step 5: Stamp contract into result data for downstream persistence
    result["fields"] = save_instruction_contract(
        contract.to_dict(),
        result.get("fields") or {},
    )

    return result


# -------------------------------------------------------------------------- //
# Math Worksheet
# -------------------------------------------------------------------------- //
def _math_worksheet_plan(fields: dict) -> dict:
    from services.factory.puzzle_plan import parse_puzzle_output_plan
    return parse_puzzle_output_plan(fields, product_type="math_worksheet")


def _math_worksheet_pdf_payload(fields: dict, *, package_id: str = "") -> dict:
    from services.factory.product_qa_agent import (
        safe_fix_plan,
        validate_generated_product,
        validate_product_plan,
    )
    from services.quality.cover_eligibility_agent import (
        determine_cover_eligibility,
        apply_cover_eligibility_to_fields,
    )

    plan = _math_worksheet_plan(fields)
    fixed_fields, fixes = safe_fix_plan("math_worksheet", fields, plan)
    if fixes:
        plan = _math_worksheet_plan(fixed_fields)

    pkg = package_id or uuid.uuid4().hex
    title = _f(fixed_fields, "worksheet_title") or "Math Worksheet"
    grade = _f(fixed_fields, "grade") or "3"
    math_topic = _f(fixed_fields, "math_topic") or ""
    difficulty = _f(fixed_fields, "difficulty") or "Medium"
    # problem_count: problems per worksheet — use explicit field or default
    problem_count = int(
        fixed_fields.get("problems") or
        fixed_fields.get("page_count") or
        20
    )

    # ── Cover Eligibility Agent ───────────────────────────────────────────────
    # Universal rule: < 5 pages = no cover for all product types
    eligibility = determine_cover_eligibility(
        product_type="math_worksheet",
        fields=fixed_fields,
        planned_page_count=problem_count,
        product_mode=plan.get("output_type", "book"),
    )
    cover_eligible_fields = apply_cover_eligibility_to_fields(eligibility, fixed_fields)
    cover_allowed = eligibility.cover_allowed

    request = MathWorksheetPdfRequest(
        worksheet_title=title,
        grade=grade,
        math_topic=math_topic,
        difficulty=difficulty,
        problem_count=problem_count,
        include_answer_key=_yes(fixed_fields, "include_answer_key"),
        include_challenge=_yes(fixed_fields, "include_challenge"),
        output_type=plan.get("output_type", "book"),
        include_cover=cover_allowed,
        package_id=pkg,
    )
    result = build_math_worksheet_pdf(request)
    if result.errors or not result.pdf_bytes:
        raise RuntimeError(f"Failed to generate Math Worksheet PDF: {result.errors}")

    pdf_bytes = result.pdf_bytes
    qa_post = validate_generated_product(
        product_type="math_worksheet",
        fields=fixed_fields,
        plan=plan,
        pdf_bytes=pdf_bytes,
        layout_info=result.layout_info,
        result_so_far=None,
    )
    if qa_post.blocked_export:
        raise RuntimeError(f"QA blocked export: {'; '.join(qa_post.errors)}")

    return {
        "product_type": "math_worksheet",
        "product_label": "Math Worksheet",
        "title": title,
        "fields": fixed_fields,
        "content": "",
        "pdf_bytes": base64.b64encode(pdf_bytes).decode("utf-8"),
        "filename": result.filename,
        "is_pdf": True,
        "is_book": plan.get("output_type", "book") == "book",
        "package_id": pkg,
        "layout_info": result.layout_info,
        "warnings": result.warnings,
        "image_jobs": [],
        "problems": result.problems,
        "challenge_problems": result.challenge_problems,
        "include_challenge": result.include_challenge,
        "qa_report": qa_post.as_dict(),
    }


def _generate_math_worksheet_pdf(fields: dict) -> dict:
    return _math_worksheet_pdf_payload(fields)


# -------------------------------------------------------------------------- //
# Spelling Worksheet
# -------------------------------------------------------------------------- //
def _spelling_worksheet_plan(fields: dict) -> dict:
    from services.factory.puzzle_plan import parse_puzzle_output_plan
    return parse_puzzle_output_plan(fields, product_type="spelling_worksheet")


def _spelling_worksheet_pdf_payload(fields: dict, *, package_id: str = "") -> dict:
    from services.factory.product_qa_agent import (
        safe_fix_plan,
        validate_generated_product,
        validate_product_plan,
    )
    from services.quality.cover_eligibility_agent import (
        determine_cover_eligibility,
        apply_cover_eligibility_to_fields,
    )

    plan = _spelling_worksheet_plan(fields)
    fixed_fields, fixes = safe_fix_plan("spelling_worksheet", fields, plan)
    if fixes:
        plan = _spelling_worksheet_plan(fixed_fields)

    pkg = package_id or uuid.uuid4().hex
    theme = _f(fixed_fields, "theme") or _f(fixed_fields, "topic") or "Spelling Practice"
    grade = _f(fixed_fields, "grade") or "3"
    # word_count comes from the user's "number of words" field — NOT from plan.page_count.
    # plan.page_count = 1 for single worksheet output format, which is not the word count.
    _wc_raw = fixed_fields.get("word_count") or fixed_fields.get("pages") or "10"
    try:
        word_count = int(_wc_raw)
    except (ValueError, TypeError):
        word_count = 10
    word_count = max(1, min(word_count, 20))  # cap between 1 and 20
    # Map creation_mode from form → use_custom_words
    creation_mode = str(fixed_fields.get("creation_mode", "")).strip()
    if creation_mode == "My custom word list":
        use_custom = True
    elif creation_mode == "Themed (AI generates words)":
        use_custom = False
    else:
        use_custom = str(fixed_fields.get("use_custom_words", "")).lower() in {"yes", "true", "1"}
    custom_words = _f(fixed_fields, "custom_words") if use_custom else ""

    # Normalize activity_type from form labels to builder keys
    activity_type_raw = str(fixed_fields.get("activity_type", "word list")).strip().lower()
    activity_map = {
        "word list": "word list",
        "mixed practice": "word list",
        "unscramble": "unscramble",
        "missing letters": "missing letters",
        "fill in the blank": "fill in the blank",
        "fill in blank": "fill in the blank",
    }
    activity_type = activity_map.get(activity_type_raw, "word list")

    # ── Cover Eligibility Agent ───────────────────────────────────────────────
    eligibility = determine_cover_eligibility(
        product_type="spelling_worksheet",
        fields=fixed_fields,
        planned_page_count=word_count,
        product_mode=plan.get("output_type", "book"),
    )
    cover_eligible_fields = apply_cover_eligibility_to_fields(eligibility, fixed_fields)
    cover_allowed = eligibility.cover_allowed

    request = SpellingWorksheetPdfRequest(
        theme=theme,
        grade=grade,
        word_count=word_count,
        custom_words=custom_words,
        include_answer_key=_yes(fixed_fields, "include_answer_key"),
        output_type=plan.get("output_type", "book"),
        include_cover=cover_allowed,
        package_id=pkg,
        activity_type=activity_type,
    )
    result = build_spelling_worksheet_pdf(request)
    if result.errors or not result.pdf_bytes:
        raise RuntimeError(f"Failed to generate Spelling Worksheet PDF: {result.errors}")

    pdf_bytes = result.pdf_bytes
    qa_post = validate_generated_product(
        product_type="spelling_worksheet",
        fields=fixed_fields,
        plan=plan,
        pdf_bytes=pdf_bytes,
        layout_info=result.layout_info,
        result_so_far=None,
    )
    if qa_post.blocked_export:
        raise RuntimeError(f"QA blocked export: {'; '.join(qa_post.errors)}")

    return {
        "product_type": "spelling_worksheet",
        "product_label": "Spelling Worksheet",
        "title": theme,
        "fields": fixed_fields,
        "content": "",
        "pdf_bytes": base64.b64encode(pdf_bytes).decode("utf-8"),
        "filename": result.filename,
        "is_pdf": True,
        "is_book": plan.get("output_type", "book") == "book",
        "package_id": pkg,
        "layout_info": result.layout_info,
        "warnings": result.warnings,
        "image_jobs": [],
        "words": result.words,
        "qa_report": qa_post.as_dict(),
    }


def _generate_spelling_worksheet_pdf(fields: dict) -> dict:
    return _spelling_worksheet_pdf_payload(fields)


def _generate_crossword_pdf(fields: dict) -> dict:
    """Generate actual Crossword PDF using the crossword pdf_builder."""
    return _crossword_pdf_payload(fields)


def _crossword(fields: dict) -> tuple[str, str, str]:
    title = _f(fields, "book_title") or _f(fields, "theme") or "Crossword Puzzle Book"
    answers = (
        "Include answer-key data for every puzzle."
        if _yes(fields, "include_answer_key")
        else "Do not include answer keys."
    )
    system = (
        "You are a crossword constructor who writes clean clues and answers."
    )
    user = (
        "Create a complete crossword puzzle book in Markdown.\n\n"
        f"Book title: {title}\n"
        f"Theme: {_f(fields, 'theme')}\n"
        f"Target age group: {_f(fields, 'audience')}\n"
        f"Number of puzzles: {_f(fields, 'puzzles', '5')}\n"
        f"Difficulty level: {_f(fields, 'difficulty')}\n"
        f"Clue style: {_f(fields, 'clue_style', 'Easy')}\n"
        f"Page size: {_f(fields, 'page_size', 'US Letter')}\n"
        f"{answers}\n\n"
        "Structure the output with these sections, in order:\n"
        "1. Book Title (H1).\n"
        "2. For each puzzle: a Puzzle Title, then a Clues list split into Across "
        "and Down, each clue paired with its Answer.\n"
        "3. Difficulty level note.\n"
        "4. Answer Key data section (only if requested).\n"
        "5. Cover Design Prompt.\n\n"
        f"{_NO_EMOJI}"
    )
    return system, user, title


def _flip_book(fields: dict) -> tuple[str, str, str]:
    title = _f(fields, "flip_title") or _f(fields, "topic") or "Flip Book"
    system = (
        "You are a content designer who storyboards flip books and slide decks "
        "page by page."
    )
    user = (
        "Create a complete flip book in Markdown.\n\n"
        f"Title: {title}\n"
        f"Topic / story: {_f(fields, 'topic')}\n"
        f"Target audience: {_f(fields, 'audience')}\n"
        f"Number of scenes: {_f(fields, 'scenes', '12')}\n"
        f"Character style: {_f(fields, 'character_style', 'Cartoon')}\n"
        f"Visual style: {_f(fields, 'visual_style', 'Modern')}\n"
        f"Page size: {_f(fields, 'page_size', 'US Letter')}\n\n"
        "Structure the output with these sections, in order:\n"
        "1. Title (H1) and subtitle.\n"
        "2. Page-by-page content: for every page, give the Visual Direction, the "
        "Short Text shown on the page, and any notes.\n"
        "3. Call-to-action (if relevant to the topic).\n"
        "4. Cover Design Prompt.\n\n"
        f"{_NO_EMOJI}"
    )
    return system, user, title


def _math_worksheet(fields: dict) -> tuple[str, str, str]:
    from services.factory.puzzle_plan import parse_puzzle_output_plan

    plan = parse_puzzle_output_plan(fields, product_type="math_worksheet")
    # Number of problems per worksheet; fall back to worksheets field or page_count
    problems = _f(fields, "problems", "10") or _f(fields, "worksheets", str(plan["page_count"])) or "10"
    title = _f(fields, "worksheet_title") or "Math Worksheet"
    answer_key = (
        "Include a full answer key."
        if _yes(fields, "include_answer_key")
        else "Do not include an answer key."
    )
    system = (
        "You are a K-12 math teacher who writes grade-appropriate, accurate "
        "worksheets and verified answer keys."
    )
    user = (
        "Create a complete math worksheet in Markdown.\n\n"
        f"Worksheet title: {_f(fields, 'worksheet_title')}\n"
        f"Grade level (1-12): {_f(fields, 'grade')}\n"
        f"Math topic: {_f(fields, 'math_topic')}\n"
        f"Number of problems: {problems}\n"
        f"Difficulty level: {_f(fields, 'difficulty')}\n"
        f"{answer_key}\n\n"
        "Structure the output with these sections, in order:\n"
        "1. Worksheet Title (H1) and Grade Level.\n"
        "2. Instructions.\n"
        "3. Math Problems (numbered).\n"
        "4. Answer Key (only if requested) — make sure every answer is correct.\n"
        "5. An optional Challenge Section with 1-3 harder problems.\n\n"
        f"{_NO_EMOJI}"
    )
    return system, user, title


def _spelling_worksheet(fields: dict) -> tuple[str, str, str]:
    from services.factory.puzzle_plan import parse_puzzle_output_plan

    plan = parse_puzzle_output_plan(fields, product_type="spelling_worksheet")
    title = _f(fields, "worksheet_title") or _f(fields, "theme") or "Spelling Worksheet"
    page_count = plan["page_count"]
    words_per = _f(fields, "words_per_puzzle") or _f(fields, "word_count", "10")
    answer_key = (
        "Include a full answer key."
        if plan["include_answer_key"]
        else "Do not include an answer key."
    )
    custom = _f(fields, "custom_words", "").strip()
    word_source = (
        f"Use this exact word list:\n{custom}"
        if custom
        else f"Generate themed spelling words about: {_f(fields, 'theme')}"
    )
    system = (
        "You are an elementary spelling specialist who creates classroom-ready spelling worksheets."
    )
    if plan["is_book"]:
        user = (
            "Create a complete spelling workbook in Markdown.\n\n"
            f"Theme: {_f(fields, 'theme')}\n"
            f"Number of worksheets: {page_count}\n"
            f"Words per worksheet: {words_per}\n"
            f"Difficulty level: {_f(fields, 'difficulty')}\n"
            f"{word_source}\n"
            f"{answer_key}\n\n"
            "Structure the output with these sections, in order:\n"
            "1. Book Title (H1).\n"
            "2. For each worksheet: title, word list, practice activities, and optional answer key.\n"
            "3. Cover Design Prompt.\n\n"
            f"{_NO_EMOJI}"
        )
    else:
        user = (
            "Create one spelling worksheet in Markdown.\n\n"
            f"Theme: {_f(fields, 'theme')}\n"
            f"Words per worksheet: {words_per}\n"
            f"Difficulty level: {_f(fields, 'difficulty')}\n"
            f"{word_source}\n"
            f"{answer_key}\n\n"
            "Structure the output with these sections, in order:\n"
            "1. Worksheet Title (H1).\n"
            "2. Word List.\n"
            "3. Practice Activities (write each word, fill in blanks, use in a sentence).\n"
            "4. Answer Key (only if requested).\n\n"
            f"{_NO_EMOJI}"
        )
    return system, user, title


def _cover_design(fields: dict) -> tuple[str, str, str]:
    title = _f(fields, "product_title") or "Cover Design"
    system = (
        "You are a professional book cover designer who creates production-ready "
        "cover design briefs with clear visual direction."
    )
    sections = []
    sections.append(f"- Product title: {_f(fields, 'product_title')}")
    if _f(fields, "subtitle"):
        sections.append(f"- Subtitle: {_f(fields, 'subtitle')}")
    sections.append(f"- Product type: {_f(fields, 'product_type', 'ebook')}")
    sections.append(f"- Target audience: {_f(fields, 'audience')}")
    sections.append(f"- Cover style: {_f(fields, 'cover_style', 'Modern')}")
    sections.append(f"- Size / format: {_f(fields, 'page_size', 'US Letter')}")
    sections_text = "\n".join(sections)
    user = (
        "Write a complete cover design brief in Markdown.\n\n"
        f"{sections_text}\n\n"
        "Structure the output with these sections:\n"
        "1. Cover Title Layout (suggested title placement, font style, size hierarchy).\n"
        "2. Visual Concept (describe the cover image or illustration direction in detail).\n"
        "3. Color Palette (suggest 3-5 hex color codes with mood notes).\n"
        "4. Typography Notes (font suggestions for title, subtitle, tagline).\n"
        "5. Back Cover / Spine Notes (if applicable).\n"
        "6. AI Image Prompt (one detailed prompt suitable for an AI image generator).\n\n"
        f"{_NO_EMOJI}"
    )
    return system, user, title


def _marketing_kit(fields: dict) -> tuple[str, str, str]:
    title = _f(fields, "product_name") or "Marketing Kit"
    system = (
        "You are a digital product marketing specialist who writes high-converting "
        "sales copy, ad scripts, and promotional content."
    )
    sections = []
    sections.append(f"- Product name: {_f(fields, 'product_name')}")
    sections.append(f"- Product type: {_f(fields, 'product_type')}")
    sections.append(f"- Target audience: {_f(fields, 'audience')}")
    sections.append(f"- Platforms: {_f(fields, 'platforms')}")
    sections_text = "\n".join(sections)
    deliverable_intro = "Create a complete marketing kit in Markdown.\n\n" + sections_text + "\n\n"
    deliverable_list = []
    if _yes(fields, "include_description"):
        deliverable_list.append("1. Product description (2-3 compelling paragraphs)")
    if _yes(fields, "include_sales_page"):
        deliverable_list.append("2. Sales page copy (headline, subheadline, benefits, CTA)")
    if _yes(fields, "include_social"):
        deliverable_list.append("3. Social media captions (Facebook, Instagram, Pinterest, X/Twitter — 3 each)")
    if _yes(fields, "include_email"):
        deliverable_list.append("4. Email promo (subject line + body, 150-200 words)")
    if _yes(fields, "include_ad_script"):
        deliverable_list.append("5. Ad script (Facebook/Instagram ad, 2 variants at 15s and 30s)")
    if not deliverable_list:
        deliverable_list.append("All sections (description, sales page, social, email, ad script)")
    deliverable_text = "\n".join(deliverable_list)
    user = (
        f"{deliverable_intro}"
        "Write the following marketing deliverables:\n"
        f"{deliverable_text}\n\n"
        f"{_NO_EMOJI}"
    )
    return system, user, title


_BUILDERS = {
    "ebook": _ebook,
    "coloring_book": _coloring_book,
    "word_search": _word_search,
    "crossword": _crossword,
    "flip_book": _flip_book,
    "cover_design": _cover_design,
    "math_worksheet": _math_worksheet,
    "spelling_worksheet": _spelling_worksheet,
    "planner": _planner,
    "marketing_kit": _marketing_kit,
}

PRODUCT_LABELS = {
    "ebook": "Ebook",
    "coloring_book": "Coloring Book",
    "word_search": "Word Search Book",
    "crossword": "Crossword Puzzle Book",
    "flip_book": "Flip Book",
    "cover_design": "Cover Design",
    "math_worksheet": "Math Worksheet",
    "spelling_worksheet": "Spelling Worksheet",
    "planner": "Planner",
    "marketing_kit": "Marketing Kit",
}


def generate_product(product_type: str, fields: dict) -> dict:
    product_type = (product_type or "").strip()
    if product_type not in _BUILDERS:
        raise ValueError(f"Unknown product type: {product_type or '(empty)'}")
    if not isinstance(fields, dict):
        raise ValueError("Form fields are required.")

    # Special handling for word_search - use actual PDF generator
    if product_type == "word_search":
        return _generate_word_search_pdf(fields)

    # Special handling for crossword - use dedicated crossword PDF generator
    if product_type == "crossword":
        return _generate_crossword_pdf(fields)

    # Special handling for coloring_book - use dedicated PDF generator
    if product_type == "coloring_book":
        return _generate_coloring_book_pdf(fields)

    # Special handling for math_worksheet - use dedicated PDF generator
    if product_type == "math_worksheet":
        return _generate_math_worksheet_pdf(fields)

    # Special handling for spelling_worksheet - use dedicated PDF generator
    if product_type == "spelling_worksheet":
        return _generate_spelling_worksheet_pdf(fields)

    system, user, title = _BUILDERS[product_type](fields)
    content = chat(system=system, user=user, max_completion_tokens=12000)

    return {
        "product_type": product_type,
        "product_label": PRODUCT_LABELS[product_type],
        "title": title,
        "fields": fields,
        "content": content,
    }
