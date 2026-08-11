"""Post-generation product workflow: generic exports, marketplace seller
packages, sales-page copy and multi-length ad scripts.

These power the Product Factory "Next Steps" panel. Everything operates on a
SAVED project (loaded from the DB, never trusting client content) so generated
artifacts are persisted back into the SAME project record (no duplicates).

Exports reuse the ebook export plumbing (``_write_package`` + the
``/download/<package_id>/<filename>`` route) and deliberately write the
whitelisted filenames (ebook.html / ebook.txt / package.zip) so they pass
``is_allowed_download`` for any product type, not just ebooks.
"""
import html
import json
import os
import re
import uuid

import markdown as _markdown
from bs4 import BeautifulSoup

from ai_client import chat, chat_json
from services.pdf_export import generate_product_pdf
from services.publishing import detect_template_key
from services.ebook_package import (
    EXPORTS_DIR,
    _download_url,
    _sanitize_html,
    _write_package,
    is_allowed_download,
    render_preview_html,
    render_txt,
)

# On-disk name -> fallback browser download filename for project export routes.
EXPORT_DOWNLOAD_FILES = {
    "html": ("ebook.html", "product.html"),
    "txt": ("ebook.txt", "product.txt"),
    "pdf": ("ebook.pdf", "product.pdf"),
    "zip": ("package.zip", "product.zip"),
}


def safe_export_basename(title: str) -> str:
    """Filesystem-safe stem from project title for attachment filenames."""
    base = re.sub(r"[^\w\s-]", "", str(title or "").strip())
    base = re.sub(r"\s+", "_", base)
    base = re.sub(r"_+", "_", base).strip("_")
    return (base[:120] if base else "product") or "product"


def project_export_download_name(project: dict, kind: str) -> str:
    """Return a safe attachment filename derived from the project title."""
    data = project.get("data") or {}
    title = data.get("title") or project.get("name") or "product"
    ext = {"html": "html", "txt": "txt", "pdf": "pdf", "zip": "zip"}[kind]
    return f"{safe_export_basename(title)}.{ext}"


def _e(value) -> str:
    return html.escape(str(value or ""))


def _yes(fields: dict, key: str) -> bool:
    """Check if a boolean field is truthy."""
    return str(fields.get(key, "")).strip().lower() in {"yes", "true", "1", "on"}


def _project_text(project: dict) -> tuple[str, str, str]:
    """Pull (title, markdown content, product_type label) from a saved project."""
    data = project.get("data") or {}
    title = (data.get("title") or project.get("name") or "Untitled Product").strip()
    content = (data.get("content") or data.get("ebook") or "").strip()
    ptype = data.get("product_label") or data.get("product_type") or "digital product"
    return title, content, ptype


def _html_to_plain_text(html_doc: str) -> str:
    soup = BeautifulSoup(str(html_doc or ""), "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    text = soup.get_text("\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _markdown_export_docs(title: str, subtitle: str, content: str) -> tuple[str, str]:
    body_html = _sanitize_html(
        _markdown.markdown(content or "", extensions=["extra", "sane_lists"])
    )
    doc_html = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{_e(title)}</title><style>{_EXPORT_CSS}</style></head><body>"
        f"<h1>{_e(title)}</h1>"
        + (f"<p class='subtitle'>{_e(subtitle)}</p>" if subtitle else "")
        + f"{body_html}</body></html>"
    )
    txt_lines = [title]
    if subtitle:
        txt_lines.append(subtitle)
    txt_lines.append("")
    txt_lines.append(content or "")
    return doc_html, "\n".join(txt_lines).strip() + "\n"


def refresh_visual_preview_html(project: dict) -> str | None:
    """Rebuild ebook preview HTML from saved visual plan (no new AI calls)."""
    from services.cover_agent import apply_cover_to_preview, sync_cover_html_if_needed

    data = project.get("data") or {}
    visual_plan = data.get("visual_plan")
    if not isinstance(visual_plan, dict):
        return None
    content = (data.get("content") or data.get("ebook") or "").strip()
    if not content:
        return None
    plan_chapters = visual_plan.get("chapters") or []
    title = (data.get("title") or project.get("name") or "Untitled Product").strip()
    subtitle = (data.get("subtitle") or "").strip()
    package_id = str(data.get("package_id") or data.get("export_package_id") or "")
    summary = (data.get("product_summary") or "").strip()
    cover_design = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None
    if cover_design:
        cover_design = sync_cover_html_if_needed(cover_design, package_id)
    topic = ""
    fields = data.get("fields") or {}
    topic = (fields.get("topic") or "").strip()
    html = render_preview_html(
        title, subtitle, content, plan_chapters, package_id, summary, cover_design,
        topic=topic,
    )
    if cover_design:
        html = apply_cover_to_preview(html, cover_design)
    return html


def _resolve_export_sources(project: dict, publishing_layout: dict | None = None) -> tuple:
    """Choose export HTML/TXT from saved project + optional publishing layout."""
    data = project.get("data") or {}
    layout_data = (publishing_layout or {}).get("data") or {}
    details = layout_data.get("details") or {}

    title = (
        details.get("product_title")
        or data.get("title")
        or project.get("name")
        or "Untitled Product"
    ).strip()
    subtitle = (details.get("subtitle") or data.get("subtitle") or "").strip()
    author = (details.get("author_brand") or data.get("author_brand") or "").strip()
    content = (data.get("content") or data.get("ebook") or "").strip()
    preview_html = (layout_data.get("preview_html") or data.get("preview_html") or "").strip()
    preview_source = (
        "publishing"
        if (layout_data.get("preview_html") or "").strip()
        else ("visual" if (data.get("preview_html") or "").strip() else "markdown")
    )
    using_publishing_preview = bool((layout_data.get("preview_html") or "").strip())
    if isinstance(data.get("visual_plan"), dict) and not using_publishing_preview:
        refreshed = refresh_visual_preview_html(project)
        if refreshed:
            preview_html = refreshed
            preview_source = "visual"
    template_key = str(layout_data.get("template") or "").strip()
    summary = data.get("product_summary")
    cover_prompt = data.get("cover_prompt")
    visual_plan = data.get("visual_plan")
    cover_design = data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None

    if preview_html:
        doc_html = preview_html
        plan_chapters = []
        if isinstance(visual_plan, dict):
            plan_chapters = visual_plan.get("chapters") or []
        if content and plan_chapters:
            txt_doc = render_txt(title, subtitle, content, plan_chapters)
        else:
            body = _html_to_plain_text(preview_html)
            txt_lines = [title]
            if subtitle:
                txt_lines.append(subtitle)
            txt_lines.append("")
            txt_lines.append(body)
            txt_doc = "\n".join(txt_lines).strip() + "\n"
    elif content:
        doc_html, txt_doc = _markdown_export_docs(title, subtitle, content)
    else:
        note = "[FALLBACK EXPORT — no saved content found on this project.]"
        doc_html = (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<title>{_e(title)}</title></head><body>"
            f"<h1>{_e(title)}</h1><p>{_e(note)}</p></body></html>"
        )
        txt_doc = f"{title}\n\n{note}\n"

    return title, subtitle, author, doc_html, txt_doc, content, summary, cover_prompt, visual_plan, preview_source, template_key, cover_design


# ---------------------------------------------------------------------------
# Generic export package (HTML / TXT / ZIP) for ANY product type
# ---------------------------------------------------------------------------

_EXPORT_CSS = """
*{box-sizing:border-box}body{font-family:Georgia,'Times New Roman',serif;max-width:760px;
margin:0 auto;padding:48px 28px;color:#1f2937;line-height:1.7}
h1{font-size:30px;margin:0 0 6px}h2{font-size:22px;margin:32px 0 10px;border-bottom:1px solid #e5e7eb;padding-bottom:6px}
h3{font-size:18px;margin:22px 0 8px}p{margin:0 0 14px}ul,ol{margin:0 0 14px 22px}
table{border-collapse:collapse;width:100%;margin:0 0 16px}th,td{border:1px solid #d1d5db;padding:8px 10px;text-align:left}
.subtitle{color:#6b7280;font-size:16px;margin:0 0 28px}
"""


def _reuse_existing_export_package(data: dict) -> dict | None:
    """Return prior export payload when package files still exist on disk."""
    package_id = str((data or {}).get("export_package_id") or "").strip()
    exports = (data or {}).get("product_exports")
    if not package_id or not isinstance(exports, dict):
        return None
    pkg_dir = os.path.join(EXPORTS_DIR, package_id)
    if not os.path.isdir(pkg_dir):
        return None
    return {"package_id": package_id, "exports": exports}


def _finalize_export_result(
    package_id: str,
    exports: dict,
    *,
    data: dict | None = None,
) -> dict:
    """Attach artifact identity meta + per-file SHA-256 digests to export payload.

    Digests are recorded when files exist on disk so download can verify bytes
    against the authoritative export record. Does not regenerate content.
    """
    import hashlib

    from services.quality.artifact_state import current_revision

    exports_out = dict(exports or {})
    meta = (
        dict(exports_out["meta"])
        if isinstance(exports_out.get("meta"), dict)
        else {}
    )
    meta["package_id"] = str(package_id)
    if isinstance(data, dict):
        art_id = str(data.get("artifact_id") or data.get("package_id") or "").strip()
        if art_id:
            meta["artifact_id"] = art_id
        try:
            meta["artifact_revision"] = current_revision(data)
        except Exception:
            pass
        content_digest = str(data.get("content_digest") or "").strip()
        if content_digest:
            meta["content_digest"] = content_digest
    exports_out["meta"] = meta

    files = exports_out.get("files")
    if isinstance(files, dict):
        pkg_dir = os.path.join(EXPORTS_DIR, package_id)
        stamped: dict = {}
        for key, entry in files.items():
            if not isinstance(entry, dict):
                stamped[key] = entry
                continue
            entry_out = dict(entry)
            disk_name = ""
            url = str(entry_out.get("url") or "")
            if "/download/" in url:
                disk_name = url.rstrip("/").rsplit("/", 1)[-1]
            if str(key) == "zip" or str(entry_out.get("name") or "").lower().endswith(
                ".zip"
            ):
                disk_name = "package.zip"
            if not disk_name:
                disk_name = str(entry_out.get("name") or "")
            path = os.path.join(pkg_dir, disk_name) if disk_name else ""
            if path and os.path.isfile(path):
                digest = hashlib.sha256()
                with open(path, "rb") as fh:
                    for chunk in iter(lambda: fh.read(65536), b""):
                        digest.update(chunk)
                entry_out["sha256"] = digest.hexdigest()
            stamped[key] = entry_out
        exports_out["files"] = stamped

    return {"package_id": package_id, "exports": exports_out}


def build_product_export(project: dict, publishing_layout: dict | None = None) -> dict:
    """Render a self-contained HTML + TXT + PDF + ZIP export for any product."""
    data = project.get("data") or {}
    from services.quality.artifact_state import (
        ArtifactState,
        ArtifactStateError,
        assert_packaging_allowed,
        packaging_may_rebuild_content,
    )

    try:
        packaging_state = assert_packaging_allowed(data if isinstance(data, dict) else {})
    except ArtifactStateError:
        raise
    # LOCKED: serve existing approved exports when present; never replace them.
    if packaging_state is ArtifactState.LOCKED:
        existing = _reuse_existing_export_package(data if isinstance(data, dict) else {})
        if existing is not None:
            return _finalize_export_result(
                existing["package_id"],
                existing["exports"] if isinstance(existing.get("exports"), dict) else {},
                data=data if isinstance(data, dict) else None,
            )

    # Ebook repair: never export a bare markdown dump when we can assemble a
    # local visual package (cover + TOC aids + rewritten headings) with zero
    # paid API calls. Skips crossword/coloring/word_search paths below.
    # Missing visuals mutate content/cover — gated by assert_content_mutation_allowed
    # inside ensure_ebook_visual_package (DRAFT only; APPROVED/LOCKED blocked).
    is_ebook = (
        project.get("type") == "ebook"
        or data.get("product_type") == "ebook"
        or bool(data.get("ebook"))
    )
    if is_ebook and not (
        data.get("product_type") in {"word_search", "crossword", "coloring_book", "math_worksheet", "spelling_worksheet"}
    ):
        from services.ebook_local_package import ensure_ebook_visual_package
        from services.ebook_pipeline_agents import run_ebook_quality_pipeline

        try:
            updated = ensure_ebook_visual_package(project)
        except ArtifactStateError:
            raise
        # Mutate caller's project so /export-product can persist visual_plan/cover.
        project["data"] = updated.get("data") or project.get("data") or {}
        data = project.get("data") or {}

        manuscript = (data.get("content") or data.get("ebook") or "").strip()
        fields = dict(data.get("fields") or {})
        if data.get("author_brand") and not fields.get("author_brand"):
            fields["author_brand"] = data.get("author_brand")
        pipeline = run_ebook_quality_pipeline(
            title=(data.get("title") or project.get("name") or "Ebook"),
            manuscript=manuscript,
            fields=fields,
            data=data,
            visual_plan=data.get("visual_plan") if isinstance(data.get("visual_plan"), dict) else None,
            cover_design=data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None,
            require_visuals=True,
            require_cover=True,
            block_on_originality=bool(
                data.get("research_notes") or data.get("source_content") or fields.get("research_notes")
            ),
        )
        data["pipeline"] = pipeline.to_dict()
        project["data"] = data
        if pipeline.blocking:
            raise ValueError(
                "Ebook quality pipeline blocked export: " + "; ".join(pipeline.blocking)
            )

    if data.get("product_type") == "word_search" and data.get("is_pdf"):
        from services.product import normalize_word_search_project_data, rebuild_word_search_pdf_from_data
        import base64

        data = normalize_word_search_project_data(data)
        project = {**project, "data": data}
        title = (data.get("title") or project.get("name") or "Word Search").strip()
        subtitle = (data.get("subtitle") or "").strip()
        try:
            # HARD GUARD: ALWAYS prefer the stored pdf_bytes — the original generation
            # passed QA and produced a valid PDF. Rebuilding can introduce new bugs
            # (e.g. different word placement that fails the answer-key path validator).
            # Only unstamped DRAFT may rebuild for export bytes; never persist content.
            if data.get("pdf_bytes"):
                pdf_bytes = base64.b64decode(data["pdf_bytes"])
            elif packaging_may_rebuild_content(data) and (
                data.get("fields") or data.get("custom_words")
            ):
                rebuilt = rebuild_word_search_pdf_from_data(data)
                pdf_bytes = base64.b64decode(rebuilt.get("pdf_bytes") or "")
            else:
                raise FileNotFoundError(
                    "Word Search PDF is not available on this project. "
                    "Packaging will not silently regenerate missing content."
                )
        except Exception as exc:
            raise FileNotFoundError(f"Word Search PDF export failed: {exc}") from exc

        if not pdf_bytes.startswith(b"%PDF"):
            raise FileNotFoundError("Word Search PDF export is invalid.")

        # ── Cover Eligibility Agent ───────────────────────────────────────────────
        # Universal rule: < 5 pages = no cover for ALL product types.
        # For word_search single puzzle: cover always blocked.
        # For word_search book: block if page count < 5.
        from services.quality.cover_eligibility_agent import (
            determine_cover_eligibility,
            block_or_raise,
        )
        ws_fields = data.get("fields") or {}
        ws_output_format = ws_fields.get("output_format") or (
            "Book" if data.get("is_book") else "Single Puzzle"
        )
        try:
            ws_page_count = int(ws_fields.get("pages") or ws_fields.get("num_puzzles") or 1)
        except (ValueError, TypeError):
            ws_page_count = None
        ws_eligibility = determine_cover_eligibility(
            product_type="word_search",
            fields=ws_fields,
            planned_page_count=ws_page_count,
            product_mode=ws_output_format,
        )
        if ws_eligibility.must_block_cover:
            block_or_raise(ws_eligibility, pdf_bytes, context="Word Search export")
        # ── End Cover Eligibility ──────────────────────────────────────────────

        slug = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").lower() or "word_search"
        doc_html = (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<title>{_e(title)}</title></head><body>"
            f"<h1>{_e(title)}</h1>"
            + (f"<p>{_e(subtitle)}</p>" if subtitle else "")
            + "<p>Word Search PDF export. Open the PDF file for puzzles.</p></body></html>"
        )
        txt_doc = f"{title}\n\n{subtitle}\n\nWord Search PDF export.\n" if subtitle else f"{title}\n\nWord Search PDF export.\n"
        pdf_name = data.get("filename") or f"{slug}.pdf"
        files: dict[str, str | bytes] = {
            "ebook.html": doc_html,
            "ebook.txt": txt_doc,
            pdf_name: pdf_bytes,
        }
        package_id = uuid.uuid4().hex
        _write_package(package_id, files)
        exports_files = {
            "html": {"name": f"{slug}.html", "url": _download_url(package_id, "ebook.html")},
            "txt": {"name": f"{slug}.txt", "url": _download_url(package_id, "ebook.txt")},
            "pdf": {"name": pdf_name, "url": _download_url(package_id, pdf_name)},
            "zip": {"name": f"{slug}.zip", "url": _download_url(package_id, "package.zip")},
        }
        return _finalize_export_result(
            package_id,
            {"pdf_available": True, "files": exports_files},
            data=data if isinstance(data, dict) else None,
        )

    # Special handling for crossword — use the dedicated crossword PDF builder
    if data.get("product_type") == "crossword" and data.get("is_pdf"):
        import base64

        from services.product import (
            _crossword_pdf_payload,
            crossword_full_book_pdf_is_valid,
            normalize_crossword_project_data,
        )

        # Normalize first so Full Book legacy puzzles=10 becomes 12 before rebuild/export.
        data = normalize_crossword_project_data(data)
        project = {**project, "data": data}
        cw_fields = data.get("fields") or {}
        is_full_book = bool(data.get("is_book")) or "book" in str(cw_fields.get("output_format") or "").lower()

        pdf_bytes = b""
        needs_rebuild = not data.get("pdf_bytes")
        if data.get("pdf_bytes"):
            try:
                pdf_bytes = base64.b64decode(data["pdf_bytes"])
            except Exception as exc:
                raise ValueError(f"Crossword PDF decode failed: {exc}") from exc
            if is_full_book and not crossword_full_book_pdf_is_valid(pdf_bytes, expected_puzzles=12):
                # Stale thin books (e.g. 10 puzzles / 21 pages) must not be re-exported.
                needs_rebuild = True

        if needs_rebuild:
            # Pass 2: packaging must not mutate project content/assets/state/revision
            # or bypass the write-policy gateway via database.update_project.
            # Unstamped DRAFT may rebuild export bytes only; digested / APPROVED /
            # LOCKED artifacts must block instead of silently regenerating.
            if not packaging_may_rebuild_content(data):
                raise ValueError(
                    "Crossword PDF export blocked: stored PDF is missing or invalid "
                    "for this artifact identity/state. Packaging will not silently "
                    "regenerate content for APPROVED, LOCKED, or digested DRAFT "
                    "artifacts. Generate and save a valid crossword first."
                )
            try:
                rebuilt = _crossword_pdf_payload(
                    cw_fields,
                    stored_words="" if str(cw_fields.get("creation_mode") or "").strip() != "Custom word list" else str(data.get("custom_words") or ""),
                    cover_design=data.get("cover_design") if isinstance(data.get("cover_design"), dict) else None,
                    package_id=str(data.get("package_id") or ""),
                )
                # Export-package bytes only — do not write back into project data.
                pdf_bytes = base64.b64decode(rebuilt["pdf_bytes"])
                if rebuilt.get("filename") and not data.get("filename"):
                    # Filename for package naming only; leave stored project untouched.
                    pass
            except Exception as rebuild_err:
                raise ValueError(
                    f"Crossword PDF export failed: stored PDF was invalid for Full Book "
                    f"and rebuild also failed ({rebuild_err}). Generate the crossword again "
                    f"and re-save before exporting."
                ) from rebuild_err

        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("Crossword PDF export is invalid.")
        if is_full_book and not crossword_full_book_pdf_is_valid(pdf_bytes, expected_puzzles=12):
            raise ValueError(
                "Crossword Full Book export must be exactly 25 pages "
                "(1 cover + 12 puzzles + 12 answer keys) with metadata "
                "'12 Crossword Puzzles'."
            )
        # ── Cover Eligibility Agent ───────────────────────────────────────────────
        from services.quality.cover_eligibility_agent import (
            determine_cover_eligibility,
            block_or_raise,
        )
        cw_fields = data.get("fields") or {}
        cw_output_format = cw_fields.get("output_format") or (
            "Book" if data.get("is_book") else "Single Puzzle"
        )
        try:
            # Crossword books: each puzzle occupies ~2 pages (front + back of sheet).
            # Use the puzzles field to estimate page count; the actual PDF page
            # count is what the QA gate validates against.
            cw_puzzles_raw = cw_fields.get("puzzles") or cw_fields.get("worksheets")
            if cw_puzzles_raw:
                cw_page_count = int(cw_puzzles_raw) * 2
            else:
                cw_page_count = None
        except (ValueError, TypeError):
            cw_page_count = None
        cw_eligibility = determine_cover_eligibility(
            product_type="crossword",
            fields=cw_fields,
            planned_page_count=cw_page_count,
            product_mode=cw_output_format,
        )
        if cw_eligibility.must_block_cover:
            block_or_raise(cw_eligibility, pdf_bytes, context="Crossword export")
        # ── End Cover Eligibility ──────────────────────────────────────────────

        slug = re.sub(r"[^A-Za-z0-9]+", "_", data.get("title") or project.get("name") or "crossword").strip("_").lower() or "crossword"
        doc_html = (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<title>{_e(slug.replace('_', ' ').title())}</title></head><body>"
            f"<h1>{_e(slug.replace('_', ' ').title())}</h1>"
            "<p>Crossword PDF export. Open the PDF file for puzzles.</p></body></html>"
        )
        txt_doc = f"{slug.replace('_', ' ').title()}\n\nCrossword PDF export.\n"
        pdf_name = data.get("filename") or f"{slug}.pdf"
        html_name = f"{slug}.html"
        txt_name = f"{slug}.txt"
        files = {
            html_name: doc_html,
            txt_name: txt_doc,
            pdf_name: pdf_bytes,
        }
        package_id = uuid.uuid4().hex
        _write_package(package_id, files)

        # QA hard block: crossword ZIP must not contain ebook.* files
        pkg_dir = os.path.join(EXPORTS_DIR, package_id)
        zip_path = os.path.join(pkg_dir, "package.zip")
        if os.path.isfile(zip_path):
            import zipfile as _zipfile
            with _zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                forbidden = [n for n in names if n.startswith("ebook.")]
                if forbidden:
                    raise ValueError(
                        f"Crossword ZIP must not contain ebook.* files. "
                        f"Found: {forbidden}. QA blocked this export."
                    )

        exports_files = {
            "html": {"name": html_name, "url": _download_url(package_id, html_name)},
            "txt": {"name": txt_name, "url": _download_url(package_id, txt_name)},
            "pdf": {"name": pdf_name, "url": _download_url(package_id, pdf_name)},
            "zip": {"name": f"{slug}.zip", "url": _download_url(package_id, "package.zip")},
        }
        return _finalize_export_result(
            package_id,
            {"pdf_available": True, "files": exports_files},
            data=data if isinstance(data, dict) else None,
        )

    # Special handling for spelling_worksheet — use the stored PDF, never fall through to ebook.
    # Spelling worksheet ZIP contains ONLY product-specific files. No ebook.html / ebook.txt.
    if data.get("product_type") == "spelling_worksheet" and data.get("is_pdf"):
        import base64

        if not data.get("pdf_bytes"):
            raise ValueError("Spelling Worksheet PDF is not available on this project.")
        try:
            pdf_bytes = base64.b64decode(data["pdf_bytes"])
        except Exception as exc:
            raise ValueError(f"Spelling Worksheet PDF decode failed: {exc}") from exc
        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("Spelling Worksheet PDF export is invalid.")

        slug = re.sub(r"[^A-Za-z0-9]+", "_", data.get("title") or project.get("name") or "spelling_worksheet").strip("_").lower() or "spelling_worksheet"
        pdf_name = data.get("filename") or f"{slug}.pdf"
        fields = data.get("fields") or {}
        include_answer = _yes(fields, "include_answer_key")
        words = data.get("words") or []

        # Build ZIP files — ONLY spelling-worksheet-specific files
        files: dict[str, str | bytes] = {
            pdf_name: pdf_bytes,
            "metadata.json": json.dumps({
                "product_type": "spelling_worksheet",
                "title": data.get("title") or fields.get("theme") or slug,
                "theme": fields.get("theme") or "",
                "grade": fields.get("grade") or "",
                "activity_type": fields.get("activity_type") or "word list",
                "word_count": len(words),
                "words": words[:20],
                "include_answer_key": include_answer,
                "filename": pdf_name,
            }, indent=2),
        }

        # Optional: plain text word list
        if words:
            word_text = "\n".join(f"{i+1}. {w}" for i, w in enumerate(words))
            files["spelling_words.txt"] = f"Spelling Words\n{'-'*30}\n{word_text}\n"

        # Optional: answer key text
        if include_answer and words:
            ak_text = "\n".join(f"{i+1}. {w.upper()}" for i, w in enumerate(words))
            files["answer_key.txt"] = f"Answer Key\n{'-'*30}\n{ak_text}\n"

        package_id = uuid.uuid4().hex
        _write_package(package_id, files)

        # QA: verify ZIP contains no ebook fallback files
        pkg_dir = os.path.join(EXPORTS_DIR, package_id)
        zip_path = os.path.join(pkg_dir, "package.zip")
        if os.path.isfile(zip_path):
            import zipfile as _zipfile
            with _zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                if "ebook.html" in names or "ebook.txt" in names or "ebook.pdf" in names:
                    raise ValueError(
                        "Spelling Worksheet ZIP must not contain ebook fallback files "
                        "(ebook.html / ebook.txt / ebook.pdf). Blocked by QA."
                    )
        # QA: verify answer key presence matches request
        if include_answer and not words:
            raise ValueError(
                "Answer key was requested but no spelling words were found. "
                "Cannot generate answer key for an empty word list."
            )

        exports_files = {
            "pdf": {"name": pdf_name, "url": _download_url(package_id, pdf_name)},
            "zip": {"name": f"{slug}.zip", "url": _download_url(package_id, "package.zip")},
        }
        return _finalize_export_result(
            package_id,
            {"pdf_available": True, "files": exports_files},
            data=data if isinstance(data, dict) else None,
        )

    # Special handling for math_worksheet — use the stored PDF, never fall through to ebook.
    # Math worksheet ZIP contains ONLY product-specific files. No ebook.html / ebook.txt / ebook.pdf.
    if data.get("product_type") == "math_worksheet" and data.get("is_pdf"):
        import base64
        import zipfile as _zipfile

        if not data.get("pdf_bytes"):
            raise ValueError("Math Worksheet PDF is not available on this project.")
        try:
            pdf_bytes = base64.b64decode(data["pdf_bytes"])
        except Exception as exc:
            raise ValueError(f"Math Worksheet PDF decode failed: {exc}") from exc
        if not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("Math Worksheet PDF export is invalid.")

        fields = data.get("fields") or {}
        title = data.get("title") or fields.get("worksheet_title") or project.get("name") or "math_worksheet"
        slug = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_").lower() or "math_worksheet"
        pdf_name = data.get("filename") or f"{slug}.pdf"
        include_answer = _yes(fields, "include_answer_key")
        include_challenge = bool(data.get("include_challenge") or _yes(fields, "include_challenge"))
        problems = data.get("problems") or []
        challenge_problems = data.get("challenge_problems") or []

        # QA: exported PDF must never be the generic fallback stub
        if b"FALLBACK EXPORT" in pdf_bytes:
            raise ValueError(
                "Math Worksheet PDF export is the generic fallback stub. "
                "Stored pdf_bytes is missing or invalid. Blocked by QA."
            )

        # QA: answer key was requested but PDF is suspiciously small (< 1 page)
        # Generated math worksheet PDFs always have >= 2 pages (problems + answer key).
        # If the stored PDF is 1 page, the answer key is likely missing.
        try:
            from pypdf import PdfReader as _MathPdfReader
            _reader = _MathPdfReader(io.BytesIO(pdf_bytes))
            _page_count = len(_reader.pages)
            _text_all = "\n".join((p.extract_text() or "") for p in _reader.pages)
        except Exception:
            _page_count = None
            _text_all = ""
        if include_answer and _page_count is not None and _page_count < 2:
            raise ValueError(
                f"Math Worksheet answer key was requested but exported PDF has only "
                f"{_page_count} page(s). At least 2 pages expected (worksheet + answer key). "
                "Blocked by QA."
            )

        # Build ZIP files — ONLY math-worksheet-specific files
        files: dict[str, str | bytes] = {
            pdf_name: pdf_bytes,
            "metadata.json": json.dumps({
                "product_type": "math_worksheet",
                "title": title,
                "worksheet_title": fields.get("worksheet_title") or title,
                "grade": fields.get("grade") or "",
                "math_topic": fields.get("math_topic") or "",
                "difficulty": fields.get("difficulty") or "",
                "problems": len(problems),
                "challenge_problems": len(challenge_problems),
                "include_answer_key": include_answer,
                "include_challenge": include_challenge,
                "filename": pdf_name,
            }, indent=2),
        }

        def _fmt_problem_line(p, i):
            if isinstance(p, dict):
                expr = p.get("problem") or p.get("expression") or p.get("question") or str(p)
                ans = p.get("answer")
            else:
                expr = str(p)
                ans = None
            if ans is not None:
                return f"{i}. {expr} = {ans}"
            return f"{i}. {expr}"

        def _fmt_answer_line(p, i):
            if isinstance(p, dict):
                ans = p.get("answer")
                expr = p.get("problem") or p.get("expression") or p.get("question") or str(p)
            else:
                ans = None
                expr = str(p)
            if ans is not None:
                return f"{i}. {ans}"
            return f"{i}. {expr}"

        # Optional: plain text problem list (main + challenge)
        if problems or challenge_problems:
            lines = []
            for i, p in enumerate(problems, start=1):
                lines.append(_fmt_problem_line(p, i))
            if include_challenge and challenge_problems:
                lines.append("")
                lines.append("--- Challenge Problems ---")
                for i, p in enumerate(challenge_problems, start=1):
                    lines.append(_fmt_problem_line(p, i))
            files["problems.txt"] = "Math Problems\n" + ("-" * 30) + "\n" + "\n".join(lines) + "\n"

        # Optional: answer key text (main + challenge, when included)
        if include_answer and (problems or challenge_problems):
            ak_lines = []
            for i, p in enumerate(problems, start=1):
                ak_lines.append(_fmt_answer_line(p, i))
            if include_challenge and challenge_problems:
                ak_lines.append("")
                ak_lines.append("--- Challenge Answers ---")
                for i, p in enumerate(challenge_problems, start=1):
                    ak_lines.append(_fmt_answer_line(p, i))
            files["answer_key.txt"] = "Answer Key\n" + ("-" * 30) + "\n" + "\n".join(ak_lines) + "\n"

        package_id = uuid.uuid4().hex
        _write_package(package_id, files)

        # QA: verify ZIP contains no ebook fallback files
        pkg_dir = os.path.join(EXPORTS_DIR, package_id)
        zip_path = os.path.join(pkg_dir, "package.zip")
        zip_pdf_bytes = pdf_bytes
        if os.path.isfile(zip_path):
            with _zipfile.ZipFile(zip_path, "r") as zf:
                names = zf.namelist()
                if "ebook.html" in names or "ebook.txt" in names or "ebook.pdf" in names:
                    raise ValueError(
                        "Math Worksheet ZIP must not contain ebook fallback files "
                        "(ebook.html / ebook.txt / ebook.pdf). Blocked by QA."
                    )
                # Extract ZIP PDF and verify it matches the direct PDF exactly
                for n in names:
                    if n.lower().endswith(".pdf"):
                        zip_pdf_bytes = zf.read(n)
                        break
        if zip_pdf_bytes != pdf_bytes:
            raise ValueError(
                "Math Worksheet ZIP PDF does not match the direct PDF bytes. "
                "Blocked by QA."
            )

        exports_files = {
            "pdf": {"name": pdf_name, "url": _download_url(package_id, pdf_name)},
            "zip": {"name": f"{slug}.zip", "url": _download_url(package_id, "package.zip")},
        }
        # NOTE: include a `meta` dict at the top level of `exports` so the
        # Download Pipeline Agent's `_load_project_by_package_id` lookup can
        # find the owning project record. The DPA iterates `product_exports.items()`
        # and looks for a *dict value* with a `package_id` field. Without this
        # the orphan-detection heuristic mis-classifies a math worksheet as a
        # "stale coloring book export" because the worksheet has page numbering.
        return _finalize_export_result(
            package_id,
            {
                "meta": {"package_id": package_id},
                "pdf_available": True,
                "files": exports_files,
            },
            data=data if isinstance(data, dict) else None,
        )

    # Special handling for coloring_book — use the dedicated coloring book PDF
    # Note: is_pdf may be absent from old projects; check product_type + pdf_bytes
    # or package_id (large books may save metadata only and keep PDF on disk).
    if data.get("product_type") == "coloring_book" and (
        data.get("pdf_bytes") or data.get("package_id") or data.get("is_pdf")
    ):
        import base64
        import glob as _glob

        # ── USER INSTRUCTION CONTRACT + QA AGENT ─────────────────────────────────
        # Load the saved instruction contract (from generate-product).
        # If absent (e.g. old projects saved before this fix), rebuild it from fields.
        # QA the stored PDF. Auto-correct if violations found.
        # ─────────────────────────────────────────────────────────────────────────
        contract = data.get("_instruction_contract") or data.get("instruction_contract")
        if not contract:
            try:
                from services.quality.user_instruction_controller import (
                    build_coloring_book_contract,
                )
                contract = build_coloring_book_contract(
                    data.get("fields") or {}
                ).to_dict()
            except ValueError:
                # Cannot determine contract — use permissive fallback (preserve old behavior)
                contract = {"product_type": "coloring_book", "is_single_sheet": False}

        stored_fields = data.get("fields") or {}
        stored_pdf_bytes = data.get("pdf_bytes") or ""

        if stored_pdf_bytes:
            try:
                decoded = base64.b64decode(stored_pdf_bytes)
            except Exception:
                decoded = b""
        else:
            decoded = b""

        # Fallback: load PDF written under exports/<package_id>/ when Save omitted
        # huge base64 (AI full books are often 25–35 MB encoded).
        if (not decoded or not decoded.startswith(b"%PDF")) and data.get("package_id"):
            pkg_dir = os.path.join(EXPORTS_DIR, str(data.get("package_id")))
            candidates = []
            preferred = str(data.get("filename") or "").strip()
            if preferred:
                candidates.append(os.path.join(pkg_dir, preferred))
            candidates.extend(sorted(_glob.glob(os.path.join(pkg_dir, "*.pdf"))))
            for cand in candidates:
                if cand and os.path.isfile(cand):
                    try:
                        with open(cand, "rb") as fh:
                            decoded = fh.read()
                        if decoded.startswith(b"%PDF"):
                            break
                    except OSError:
                        continue

        if decoded and decoded.startswith(b"%PDF"):
            # QA the stored PDF using the Coloring Book QA Agent.
            # Pass decoded bytes (not the base64 string) so QA receives raw PDF bytes.
            try:
                from services.coloring_book.coloring_book_qa_agent import (
                    validate_and_correct_coloring_book_output,
                )
                qa_result = validate_and_correct_coloring_book_output(
                    fields=stored_fields,
                    pdf_bytes=decoded,  # already decoded to raw bytes above
                    contract=contract,
                    package_id=data.get("package_id", ""),
                )
                # Unpack: QA returns (bytes, was_corrected)
                if not isinstance(qa_result, tuple) or len(qa_result) != 2:
                    raise ValueError(f"Unexpected QA return type: {type(qa_result)}")
                pdf_bytes, was_corrected = qa_result
            except ValueError as exc:
                # QA failed and auto-correct failed — hard block
                raise ValueError(
                    f"Coloring Book QA blocked export: {exc}"
                ) from exc
        else:
            # Fail closed: never silently regenerate paid AI pages on Save/Export.
            raise ValueError(
                "Coloring Book PDF is missing from this project. "
                "Generate and approve the book again before exporting. "
                "Export will not call image generation."
            )

        # Honor in-project quality hard-blocks (QA-failed books are not downloadable).
        qr = data.get("quality_result") or data.get("qa_result") or {}
        if isinstance(qr, dict) and qr.get("blocked_export"):
            raise ValueError(
                "Coloring Book QA blocked export: quality issues remain on one or more pages. "
                "Fix or regenerate approved pages before downloading PDF/ZIP."
            )
        if data.get("qa_blocked") or data.get("blocked_export"):
            raise ValueError(
                "Coloring Book QA blocked export: this project is marked non-downloadable."
            )

        if not pdf_bytes or not pdf_bytes.startswith(b"%PDF"):
            raise ValueError("Coloring Book PDF export is invalid.")

        # Full Thunder Volt-sized books: enforce cover + interior page count.
        # Do not apply this to short/legacy projects with mismatched metadata.
        pages_meta = data.get("pages") if isinstance(data.get("pages"), list) else []
        if pages_meta and data.get("is_book") and len(pages_meta) >= 25:
            try:
                from pypdf import PdfReader
                from io import BytesIO as _BytesIO

                actual = len(PdfReader(_BytesIO(pdf_bytes)).pages)
            except Exception:
                actual = 0
            expected = len(pages_meta) + (1 if data.get("pdf_has_cover_page") else 0)
            if actual and expected and actual != expected:
                raise ValueError(
                    f"Coloring Book QA blocked export: PDF has {actual} pages but "
                    f"project metadata expects {expected} (cover + interiors)."
                )
        # ── END QA AGENT ─────────────────────────────────────────────────────────

        slug = re.sub(r"[^A-Za-z0-9]+", "_", data.get("title") or project.get("name") or "coloring_book").strip("_").lower() or "coloring_book"
        doc_html = (
            "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            f"<title>{_e(slug.replace('_', ' ').title())}</title></head><body>"
            f"<h1>{_e(slug.replace('_', ' ').title())}</h1>"
            "<p>Coloring Book PDF export. Open the PDF file for coloring pages.</p></body></html>"
        )
        txt_doc = f"{slug.replace('_', ' ').title()}\n\nColoring Book PDF export.\n"
        # Download route only allows safe PDF basenames (no spaces). Prefer stored
        # filename when it passes the allowlist; otherwise fall back to slug.pdf.
        pdf_name = str(data.get("filename") or f"{slug}.pdf").strip() or f"{slug}.pdf"
        if not is_allowed_download(pdf_name):
            pdf_name = f"{slug}.pdf"
            data["filename"] = pdf_name

        # Keep fields.pages aligned with the real interior page list / PDF so the
        # download pipeline's cover-eligibility check does not use a stale count.
        pages_list = data.get("pages") if isinstance(data.get("pages"), list) else None
        if pages_list:
            synced_fields = dict(stored_fields)
            synced_fields["pages"] = str(len(pages_list))
            data["fields"] = synced_fields
            stored_fields = synced_fields

        files: dict[str, str | bytes] = {
            "ebook.html": doc_html,
            "ebook.txt": txt_doc,
            pdf_name: pdf_bytes,
        }
        # Preserve the generation package_id so cover/page images remain addressable
        package_id = str(data.get("package_id") or "").strip() or uuid.uuid4().hex
        _write_package(package_id, files)
        exports_files = {
            "html": {"name": "product.html", "url": _download_url(package_id, "ebook.html")},
            "txt": {"name": "product.txt", "url": _download_url(package_id, "ebook.txt")},
            "pdf": {"name": pdf_name, "url": _download_url(package_id, pdf_name)},
            "zip": {"name": f"{slug}.zip", "url": _download_url(package_id, "package.zip")},
        }
        return _finalize_export_result(
            package_id,
            {"pdf_available": True, "files": exports_files},
            data=data if isinstance(data, dict) else None,
        )

    # ── HARD BLOCK: crossword must never reach the ebook fallback ─────────────────
    # If crossword has is_pdf=True but pdf_bytes is somehow missing, the rebuild
    # branch above handles it. If crossword has neither is_pdf nor pdf_bytes, it
    # lands here. Block it — do NOT silently serve ebook.html fallback.
    if data.get("product_type") == "crossword":
        raise ValueError(
            "Crossword PDF is not available on this project. "
            "Please generate the crossword and save it before exporting. "
            "(Crossword must not use the generic ebook fallback export path.)"
        )
    # ── End HARD BLOCK ───────────────────────────────────────────────────────────

    title, subtitle, author, doc_html, txt_doc, content, summary, cover_prompt, visual_plan, preview_source, template_key, cover_design = (
        _resolve_export_sources(project, publishing_layout)
    )

    summary_for_pdf = None
    if summary:
        summary_for_pdf = (
            summary if isinstance(summary, str) else json.dumps(summary, indent=2, ensure_ascii=False)
        )

    # ── Cover Eligibility Agent — ebook / generic path ──────────────────────────
    # Universal rule: < 5 pages = no cover for ALL product types.
    # Check before generate_product_pdf prepended a cover.
    data_fields = data.get("fields") or {}
    _product_type = data.get("product_type") or "ebook"
    _product_mode = (
        data.get("output_format") or
        data_fields.get("output_format") or
        ""
    )
    try:
        planned_count = int(
            data_fields.get("pages") or
            data_fields.get("num_pages") or
            data.get("num_pages") or
            1
        )
    except (ValueError, TypeError):
        planned_count = None

    from services.quality.cover_eligibility_agent import (
        determine_cover_eligibility,
        block_or_raise,
    )
    generic_eligibility = determine_cover_eligibility(
        product_type=_product_type,
        fields=data_fields,
        planned_page_count=planned_count,
        product_mode=_product_mode,
    )
    # Strip cover design if cover not eligible
    effective_cover_design = cover_design if generic_eligibility.cover_allowed else None
    # ── End Cover Eligibility ──────────────────────────────────────────────────

    files: dict[str, str | bytes] = {"ebook.html": doc_html, "ebook.txt": txt_doc}
    pdf_available = False
    try:
        data_fields = data.get("fields") or {}
        topic = (
            (data_fields.get("topic") if isinstance(data_fields, dict) else "")
            or data.get("source")
            or title
        )
        audience = (
            (data_fields.get("audience") if isinstance(data_fields, dict) else "")
            or data.get("audience")
            or ""
        )
        pdf_bytes = generate_product_pdf(
            doc_html=doc_html,
            title=title,
            subtitle=subtitle,
            author=author or "Digital Product Factory",
            content=content,
            summary=summary_for_pdf,
            visual_plan=visual_plan if isinstance(visual_plan, dict) else None,
            preview_source=preview_source,
            template_key="" if preview_source == "visual" else (template_key or detect_template_key(doc_html)),
            cover_design=effective_cover_design,
            subject=subtitle or str(summary_for_pdf or "")[:180],
            keywords=", ".join(
                p
                for p in [
                    str(topic or "").strip(),
                    str(audience or "").strip(),
                    "ebook",
                    "digital product factory",
                ]
                if p
            ),
            topic=str(topic or ""),
            audience=str(audience or ""),
        )
        files["ebook.pdf"] = pdf_bytes
        pdf_available = True
    except Exception as exc:
        # Log PDF export failure so regression testing can detect it
        import logging
        logging.error("[PDF-EXPORT-FAIL] %s: %s (title=%r)", type(exc).__name__, exc, title)
        pdf_available = False

    if summary:
        files["product_summary.txt"] = (
            summary if isinstance(summary, str) else json.dumps(summary, indent=2, ensure_ascii=False)
        )
    if cover_prompt:
        files["cover_prompt.txt"] = str(cover_prompt)
    if visual_plan:
        files["visual_plan.json"] = json.dumps(visual_plan, indent=2, ensure_ascii=False)

    package_id = uuid.uuid4().hex
    _write_package(package_id, files)
    exports_files = {
        "html": {"name": "product.html", "url": _download_url(package_id, "ebook.html")},
        "txt": {"name": "product.txt", "url": _download_url(package_id, "ebook.txt")},
        "zip": {"name": "product.zip", "url": _download_url(package_id, "package.zip")},
    }
    if pdf_available:
        exports_files["pdf"] = {"name": "product.pdf", "url": _download_url(package_id, "ebook.pdf")}
    return _finalize_export_result(
        package_id,
        {
            "pdf_available": pdf_available,
            "files": exports_files,
        },
        data=data if isinstance(data, dict) else None,
    )


def project_export_file_path(
    package_id: str, kind: str, project: dict | None = None
) -> tuple[str, str]:
    """Return (absolute_path, attachment_filename) for a freshly built export."""
    kind = (kind or "").strip().lower()
    spec = EXPORT_DOWNLOAD_FILES.get(kind)
    if not spec:
        raise ValueError("Unknown export type.")
    disk_name, fallback_name = spec
    path = os.path.join(EXPORTS_DIR, package_id, disk_name)
    if not os.path.isfile(path):
        raise FileNotFoundError("Export file could not be created.")
    attachment_name = (
        project_export_download_name(project, kind) if project else fallback_name
    )
    return path, attachment_name


def existing_project_export_path(
    project: dict, kind: str
) -> tuple[str, str] | None:
    """Return (path, attachment_name) when a prior export for this project exists."""
    data = project.get("data") or {}
    package_id = (data.get("export_package_id") or "").strip()
    if not package_id:
        return None
    try:
        return project_export_file_path(package_id, kind, project)
    except (FileNotFoundError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Marketplace seller packages (KDP / Etsy & Gumroad / Lemon Squeezy)
# ---------------------------------------------------------------------------

# Each platform is a separate marketplace package with its own field schema.
# ``generate_seller_package`` is generic over these key descriptions, so adding a
# platform only requires a new entry here (and a matching button in the frontend).
_PLATFORMS = {
    "kdp": {
        "label": "Amazon KDP",
        "keys": {
            "book_title": "string",
            "subtitle": "string",
            "author_brand": "string (author or brand name)",
            "book_description": "string (compelling 150-250 word book description)",
            "keywords": "array of EXACTLY 7 KDP search keyword strings",
            "categories": "array of 2 suggested KDP category path strings",
            "short_description": "string (one to two sentence summary)",
            "long_description": "string (full marketing description)",
            "backend_search_terms": "array of backend search term strings",
            "suggested_price": "string price range with rationale",
            "cover_requirements": "array of cover requirement checklist item strings",
            "manuscript_checklist": "array of manuscript preparation checklist item strings",
            "upload_checklist": "array of KDP upload step checklist item strings",
        },
    },
    "etsy": {
        "label": "Etsy",
        "keys": {
            "product_title": "string (Etsy SEO product title)",
            "short_description": "string (one punchy line)",
            "long_description": "string (full listing description)",
            "tags": "array of EXACTLY 13 short Etsy tag strings (max 20 chars each)",
            "suggested_price": "string suggested price",
            "product_image_ideas": "array of product image / mockup idea strings",
            "files_received": "array of strings describing the files the buyer receives",
            "listing_bullets": "array of listing highlight bullet strings",
            "faq": "array of FAQ strings, each written as 'Q: question A: answer'",
            "seller_notes": "string of seller notes / processing info",
        },
    },
    "gumroad": {
        "label": "Gumroad",
        "keys": {
            "product_name": "string",
            "short_description": "string (one punchy line)",
            "long_description": "string (full description)",
            "sales_page_copy": "string of conversion-focused sales page copy",
            "suggested_price": "string suggested price",
            "included_files": "array of included file / deliverable strings",
            "customer_benefits": "array of customer benefit strings",
            "faq": "array of FAQ strings, each written as 'Q: question A: answer'",
            "thank_you_message": "string shown to the customer after purchase",
        },
    },
    "lemon_squeezy": {
        "label": "Lemon Squeezy",
        "keys": {
            "product_name": "string",
            "product_description": "string",
            "suggested_price": "string suggested price",
            "sales_page_headline": "string (bold sales headline)",
            "product_benefits": "array of product benefit strings",
            "download_file_list": "array of deliverable file name strings",
            "fulfillment_notes": "string on delivery / fulfillment setup",
            "refund_terms": "string with a suggested refund / terms policy",
            "customer_delivery_message": "string delivered to the customer with their download",
        },
    },
    "zazzle": {
        "label": "Zazzle",
        "keys": {
            "product_title": "string (Zazzle product title)",
            "product_description": "string (full Zazzle product description)",
            "tags": "array of Zazzle search tag strings",
            "design_placement_notes": "array of notes on how the design should be placed/positioned on products",
            "product_mockup_guidance": "array of product mockup / presentation guidance strings",
            "recommended_product_types": "array of recommended Zazzle product type strings (e.g. poster, mug, t-shirt, tote bag)",
            "suggested_price": "string suggested price or markup guidance",
        },
    },
}


def generate_seller_package(platform: str, project: dict) -> dict:
    platform = (platform or "").strip()
    spec = _PLATFORMS.get(platform)
    if not spec:
        raise ValueError("Unknown marketplace platform.")
    title, content, ptype = _project_text(project)
    excerpt = (content or "")[:4000]
    keys_desc = "\n".join(f'- "{k}": {v}' for k, v in spec["keys"].items())
    result = chat_json(
        system=(
            "You are an expert digital-product marketplace listing strategist. "
            "You write accurate, conversion-focused marketplace listings. Never "
            "use emojis."
        ),
        user=(
            f"Prepare a {spec['label']} seller package for the digital product "
            f"below (a {ptype}). Return ONLY a JSON object with EXACTLY these keys:\n"
            f"{keys_desc}\n\n"
            f"PRODUCT TITLE: {title}\n\nPRODUCT CONTENT (excerpt):\n{excerpt}"
        ),
        max_completion_tokens=2500,
    )
    # Keep only the declared keys so the saved shape is predictable.
    cleaned = {k: result.get(k) for k in spec["keys"]}
    cleaned["platform"] = platform
    cleaned["platform_label"] = spec["label"]
    return cleaned


# ---------------------------------------------------------------------------
# Sales page + ad scripts
# ---------------------------------------------------------------------------

def generate_sales_page(project: dict) -> str:
    title, content, ptype = _project_text(project)
    excerpt = (content or "")[:4000]
    return chat(
        system=(
            "You are a direct-response copywriter. You write high-converting "
            "long-form sales pages. Never use emojis."
        ),
        user=(
            f"Write a complete sales page in Markdown for the {ptype} below. "
            "Include: a bold headline, a subheadline, the problem, the promise, "
            "what's inside / key benefits (bulleted), who it's for, an offer "
            "with pricing framing, social-proof angle suggestions, an FAQ, and a "
            "strong closing call to action. Use Markdown headings. Return only "
            "the sales page.\n\n"
            f"PRODUCT TITLE: {title}\n\nPRODUCT CONTENT (excerpt):\n{excerpt}"
        ),
    )


def generate_product_ad_scripts(project: dict) -> dict:
    title, content, ptype = _project_text(project)
    excerpt = (content or "")[:3000]

    def _script(seconds: int) -> str:
        return chat(
            system=(
                "You are a direct-response video ad copywriter. You write punchy, "
                "high-converting short-form video scripts. Never use emojis."
            ),
            user=(
                f"Write a {seconds}-second video ad script for the {ptype} below. "
                "Format the script as a two-column Markdown table with exactly two "
                "columns: 'Visuals' and 'Audio'. Flow as a timed storyboard from "
                "hook to call-to-action. Return only the Markdown table.\n\n"
                f"PRODUCT TITLE: {title}\n\nPRODUCT DETAILS (excerpt):\n{excerpt}"
            ),
        )

    return {"ad_30": _script(30), "ad_60": _script(60)}
