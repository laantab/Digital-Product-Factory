"""
Download Pipeline Agent — single controlled path for all generated downloads.

Purpose:
  Every route that returns a PDF or ZIP to the user must pass through this
  agent. It is the central coordinator that identifies the download context,
  applies product-specific validation rules, routes to the correct QA agents,
  records audit entries, and either serves, repairs, or blocks the download.

Why this exists:
  The Final Output Gate was applied to /download/<package_id>/<filename> but
  the crossword-builder and word-search-builder blueprints had their own
  /download/<filename> routes that bypassed ALL validation. A bad crossword
  or word search PDF could be downloaded without any checks.

  The Download Pipeline Agent closes that gap and adds:
    - Unified download context detection
    - Product-specific rules for every download path
    - Audit logging for every download attempt
    - Coordinated repair via existing QA agents
    - Single source of truth for "can this file be served?"

How it works:
  1. resolve_download_request(route, **kwargs) → DownloadContext
     Identifies what is being downloaded and where it came from.
  2. validate_download(context) → DownloadResult
     Applies all product-specific rules via QA agents.
  3. record_download_audit(context, result)
     Writes every attempt to the audit log.
  4. serve_download(context, result) → Flask response
     Returns the final response: corrected bytes, blocked error, or file.

Relationship to other agents:
  - Final Output Gate: handles /download/<package_id>/<filename> for all product types
  - Cover Eligibility Agent: consulted for every product under 5 pages
  - Coloring Book QA Agent: handles single-sheet auto-correction
  - This agent: orchestrates all paths, logs everything, blocks/allows

Scope:
  All generated product downloads from:
    /download/<package_id>/<filename>  (via Final Output Gate)
    /crossword-builder/download/<filename>
    /word-search-builder/download/<filename>
"""
from __future__ import annotations

import datetime
import fitz
import io
import json
import logging
import os
import re
import zipfile
from dataclasses import asdict, dataclass, field
from typing import Any

# --------------------------------------------------------------------------- //
# Paths
# --------------------------------------------------------------------------- //
# Path resolution: download_pipeline_agent.py is at services/quality/
# We need flask_app/ (3 levels up)
_F = os.path.abspath(__file__)  # .../flask_app/services/quality/download_pipeline_agent.py
_FLASK_DIR = os.path.dirname(os.path.dirname(os.path.dirname(_F)))  # .../flask_app/
_EXPORTS_DIR = os.path.join(_FLASK_DIR, "exports")   # .../flask_app/exports
_AUDIT_LOG = os.path.join(_FLASK_DIR, "logs", "download_audit.log")

# --------------------------------------------------------------------------- //
# Dataclasses
# --------------------------------------------------------------------------- //
@dataclass
class DownloadContext:
    """Complete context for a download request."""
    route: str                          # e.g. "/download/<package_id>/<filename>"
    filename: str                       # bare filename
    file_path: str                      # absolute path on disk
    file_type: str                      # "pdf" | "zip"
    source: str                         # "main" | "crossword_builder" | "word_search_builder"
    package_id: str | None              # only for main route
    project_id: int | None              # DB project id if known
    project_name: str | None
    product_type: str | None            # e.g. "coloring_book", "word_search"
    product_mode: str | None             # e.g. "Single Sheet", "book"
    fields: dict                         # form fields if available
    is_single_sheet: bool = False
    expected_page_count: int = 0
    cover_eligible: bool = False
    metadata: dict = field(default_factory=dict)


@dataclass
class DownloadResult:
    """Result of download validation."""
    status: str          # "passed" | "blocked" | "repaired"
    served_bytes: bytes | None = None  # if repaired, the corrected bytes
    served_path: str | None = None     # if passed from disk, the path
    violations: list[str] = field(default_factory=list)
    auto_repaired: bool = False
    repair_attempted: bool = False
    page_count: int = 0
    zip_pdf_page_count: int = 0
    message: str = ""
    error_response: dict | None = None   # JSON error body for blocked downloads
    status_code: int = 200              # HTTP status to return


# --------------------------------------------------------------------------- //
# Audit logging
# --------------------------------------------------------------------------- //
def _ensure_log_dir():
    os.makedirs(os.path.dirname(_AUDIT_LOG), exist_ok=True)


def record_download_audit(
    context: DownloadContext,
    result: DownloadResult,
) -> None:
    """
    Write one entry per download attempt to the audit log.

    NO secrets, NO API keys, NO pdf_bytes content.
    """
    _ensure_log_dir()
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = {
        "timestamp": now,
        "route": context.route,
        "filename": context.filename,
        "file_type": context.file_type,
        "source": context.source,
        "package_id": context.package_id or "",
        "project_id": context.project_id,
        "project_name": context.project_name or "",
        "product_type": context.product_type or "",
        "product_mode": context.product_mode or "",
        "validation_status": result.status,
        "auto_repaired": result.auto_repaired,
        "repair_attempted": result.repair_attempted,
        "violations": result.violations,
        "page_count": result.page_count,
        "zip_pdf_page_count": result.zip_pdf_page_count,
        "message": result.message,
    }
    line = json.dumps(entry, ensure_ascii=False)
    try:
        with open(_AUDIT_LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass  # Never let audit logging failure block a download


# --------------------------------------------------------------------------- //
# Context resolution
# --------------------------------------------------------------------------- //
def _load_project_by_package_id(package_id: str) -> dict | None:
    """Find the project that owns this export package_id."""
    from database import get_conn
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, name, type, data FROM projects WHERE type='product'"
        ).fetchall()
    finally:
        conn.close()
    for pid, name, ptype, data_str in rows:
        try:
            d = json.loads(data_str or "{}")
            if str(d.get("package_id", "")) == package_id:
                return {"id": pid, "name": name, "type": ptype, "data": d}
            # Also check export_package_id — build_product_export stores the new
            # export package_id here (not nested in product_exports.files).
            if str(d.get("export_package_id", "")) == package_id:
                return {"id": pid, "name": name, "type": ptype, "data": d}
            exports = d.get("product_exports") or {}
            if isinstance(exports, dict):
                for key, val in exports.items():
                    if isinstance(val, dict) and str(val.get("package_id", "")) == package_id:
                        return {"id": pid, "name": name, "type": ptype, "data": d}
        except Exception:
            pass
    return None


def resolve_download_request(
    route: str,
    filename: str,
    file_path: str,
    package_id: str | None = None,
    project: dict | None = None,
    fields: dict | None = None,
    product_mode: str | None = None,
) -> DownloadContext:
    """
    Resolve a download request into a full DownloadContext.

    For the main /download/ route: package_id is required.
    For builder routes: project/fields may come from the generation request.
    """
    filename_lower = filename.lower()
    file_type = "pdf" if filename_lower.endswith(".pdf") else (
        "zip" if filename_lower.endswith(".zip") else "other"
    )

    source = "main"
    if "crossword" in route:
        source = "crossword_builder"
    elif "word-search" in route or "word_search" in route:
        source = "word_search_builder"

    # Resolve project context
    project_id = None
    project_name = None
    product_type = None
    product_mode_resolved = product_mode
    fields_resolved = dict(fields) if fields else {}
    data: dict = {}
    pdf_has_cover_page = False

    if project:
        project_id = project.get("id")
        project_name = project.get("name")
        data = project.get("data") or {}
        product_type = data.get("product_type", "")
        product_mode_resolved = product_mode_resolved or data.get("output_format") or data.get("product_mode")
        fields_resolved = {**fields_resolved, **(data.get("fields") or {})}
        pdf_has_cover_page = bool(data.get("pdf_has_cover_page"))

    elif package_id:
        proj = _load_project_by_package_id(package_id)
        if proj:
            project_id = proj.get("id")
            project_name = proj.get("name")
            data = proj.get("data") or {}
            product_type = data.get("product_type", "")
            product_mode_resolved = product_mode_resolved or data.get("output_format") or data.get("product_mode")
            fields_resolved = {**fields_resolved, **(data.get("fields") or {})}
            pdf_has_cover_page = bool(data.get("pdf_has_cover_page"))

    # Pass 2: package must belong to the resolved project identity.
    if package_id and data:
        try:
            from services.quality.artifact_identity import package_belongs_to_project

            if not package_belongs_to_project(data, package_id):
                project_id = None
                project_name = None
                product_type = None
                data = {}
                fields_resolved = dict(fields) if fields else {}
                pdf_has_cover_page = False
        except Exception:
            pass

    # Determine expected page count (must come before is_single_sheet)
    # Crossword books: each puzzle occupies ~2 pages (front + back).
    # Also read output_format from fields_resolved (not just top-level data).
    pages_val = fields_resolved.get("pages") or fields_resolved.get("num_pages") or ""
    try:
        expected_page_count = int(pages_val)
    except (ValueError, TypeError):
        expected_page_count = 0

    # Crossword: use puzzles × 2 as page count when no explicit pages field.
    if product_type == "crossword" and expected_page_count == 0:
        puzzles_raw = fields_resolved.get("puzzles") or fields_resolved.get("worksheets")
        if puzzles_raw:
            try:
                expected_page_count = int(puzzles_raw) * 2
            except (ValueError, TypeError):
                pass

    # Coloring books: form fields.pages can go stale after regenerate/repair while
    # data.pages (interior page list) stays accurate. Prefer the richer signal so
    # a 12-page book with a cover is not treated as a 4-page no-cover product.
    if product_type == "coloring_book":
        pages_list = data.get("pages") if isinstance(data.get("pages"), list) else None
        if pages_list:
            expected_page_count = max(expected_page_count, len(pages_list))
        elif data.get("is_book") and expected_page_count < 5:
            # Book flag without a page list — do not force the <5-page cover ban
            # from a stale fields.pages alone; validate_download refines from PDF.
            pass

    # Resolve output_format from fields_resolved (top-level data may not have it).
    product_mode_resolved = (
        product_mode_resolved
        or fields_resolved.get("output_format")
        or fields_resolved.get("product_mode")
        or product_mode_resolved  # fallback to earlier resolution
    )

    # Determine if single sheet
    mode_lower = str(product_mode_resolved or "").lower()
    is_single_sheet = mode_lower in {
        "single sheet", "single_sheet", "single page", "single_page", "1 page", "one page", "sheet",
    } or expected_page_count == 1

    # Cover eligibility (from Cover Eligibility Agent)
    try:
        from services.quality.cover_eligibility_agent import determine_cover_eligibility
        eligibility = determine_cover_eligibility(
            product_type=product_type or "",
            fields=fields_resolved,
            planned_page_count=expected_page_count if expected_page_count > 0 else None,
            product_mode=product_mode_resolved,
        )
        cover_eligible = eligibility.cover_allowed
    except Exception:
        cover_eligible = True  # permissive fallback

    return DownloadContext(
        route=route,
        filename=filename,
        file_path=file_path,
        file_type=file_type,
        source=source,
        package_id=package_id,
        project_id=project_id,
        project_name=project_name,
        product_type=product_type,
        product_mode=product_mode_resolved,
        fields=fields_resolved,
        is_single_sheet=is_single_sheet,
        expected_page_count=expected_page_count,
        cover_eligible=cover_eligible,
        metadata={
            "pdf_has_cover_page": pdf_has_cover_page,
            "content_digest": str((data or {}).get("content_digest") or "").strip(),
            "artifact_id": str(
                (data or {}).get("artifact_id")
                or (data or {}).get("package_id")
                or ""
            ).strip(),
        },
    )


def _refine_coloring_book_cover_eligibility(
    context: DownloadContext,
    page_count: int,
) -> None:
    """
    Recompute cover eligibility from the actual PDF page count.

    Generation/repair can leave fields.pages stale (e.g. form still says 4 while
    the saved PDF is a 12-page Digital Book with cover). Blocking that download as
    ``illegal_cover`` makes PDF/ZIP appear unavailable after a successful export.
    """
    if context.product_type != "coloring_book" or context.is_single_sheet:
        return
    if page_count <= 0 or context.cover_eligible:
        return
    try:
        from services.quality.cover_eligibility_agent import determine_cover_eligibility
    except Exception:
        context.cover_eligible = True
        return

    has_cover = bool(context.metadata.get("pdf_has_cover_page"))
    interior = page_count - 1 if has_cover and page_count > 1 else page_count
    planned = max(context.expected_page_count or 0, interior)
    eligibility = determine_cover_eligibility(
        product_type="coloring_book",
        fields=context.fields,
        planned_page_count=planned if planned > 0 else page_count,
        product_mode=context.product_mode,
    )
    context.cover_eligible = eligibility.cover_allowed


# --------------------------------------------------------------------------- //
# PDF inspection helpers
# --------------------------------------------------------------------------- //
def _inspect_pdf(pdf_bytes: bytes) -> dict:
    """Return page_count, all_text, all_lower from PDF bytes."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = doc.page_count
    all_text = []
    for page in doc:
        all_text.append(page.get_text().strip())
    doc.close()
    return {
        "page_count": page_count,
        "all_text": all_text,
        "all_lower": " ".join(all_text).lower(),
    }


def _inspect_zip(zip_bytes: bytes) -> dict:
    """Inspect the PDF inside a ZIP. Returns dict with zip_pdfs, pdf_bytes, pdf_page_count."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
            if not pdf_names:
                return {"pdf_names": [], "pdf_bytes": None, "pdf_page_count": 0}
            pdf_bytes = zf.read(pdf_names[0])
            doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            page_count = doc.page_count
            all_text = []
            for page in doc:
                all_text.append(page.get_text().strip())
            doc.close()
            return {
                "pdf_names": pdf_names,
                "pdf_bytes": pdf_bytes,
                "pdf_page_count": page_count,
                "all_text": all_text,
                "all_lower": " ".join(all_text).lower(),
            }
    except Exception as exc:
        return {"pdf_names": [], "pdf_bytes": None, "pdf_page_count": 0, "error": str(exc)}


# --------------------------------------------------------------------------- //
# Product-specific validation rules
# --------------------------------------------------------------------------- //
def _validate_coloring_book_single_sheet(
    context: DownloadContext,
    pdf_bytes: bytes,
) -> tuple[bool, list[str]]:
    """Validate a coloring book single sheet PDF. Returns (passed, violations)."""
    insp = _inspect_pdf(pdf_bytes)
    page_count = insp["page_count"]
    all_text = insp["all_text"]
    all_lower = insp["all_lower"]
    text_length = sum(len(t) for t in all_text)
    violations: list[str] = []

    # Rule 1: Must be exactly 1 page
    if page_count != 1:
        violations.append(f"page_count={page_count} (expected 1)")

    # Rule 2: Expected pages mismatch (stale export detection)
    if context.expected_page_count > 0 and page_count != context.expected_page_count:
        violations.append(f"expected_pages={context.expected_page_count}, actual={page_count}")

    # Rule 3: No cover text
    cover_keywords = [
        "coloring book", "cover page", "front cover", "book cover",
        "title page", "coloring book cover",
    ]
    for i, txt in enumerate(all_text):
        if any(kw in txt.lower() for kw in cover_keywords):
            violations.append(f"cover_text: page {i+1}: {txt[:60]!r}")

    # Rule 4: No page numbering
    if "page" in all_lower and "of" in all_lower:
        for i, txt in enumerate(all_text):
            if "page" in txt.lower() and "of" in txt.lower():
                violations.append(f"page_number: page {i+1}: {txt[:60]!r}")

    # Rule 5: No "Page 1 of 1" title card
    for i, txt in enumerate(all_text):
        if "page 1 of 1" in txt.lower():
            violations.append(f"title_card: page {i+1}: {txt[:60]!r}")

    # Rule 6: No text when captions=No
    captions_val = context.fields.get("captions", context.fields.get("include_captions", ""))
    captions_no = str(captions_val).lower() in ("no", "false", "0", "")
    if captions_no and text_length > 0:
        for i, txt in enumerate(all_text):
            if len(txt.strip()) > 3:
                violations.append(f"text_when_captions_no: page {i+1}: {txt[:60]!r}")
                break

    return len(violations) == 0, violations


def _validate_cover_rules(
    context: DownloadContext,
    pdf_bytes: bytes,
) -> tuple[bool, list[str]]:
    """Validate cover rules for any product type. Returns (passed, violations)."""
    if context.cover_eligible:
        return True, []  # Cover is allowed — no violation

    insp = _inspect_pdf(pdf_bytes)
    page_count = insp["page_count"]
    all_lower = insp["all_lower"]
    violations: list[str] = []

    cover_keywords = [
        "cover page", "front cover", "book cover", "cover",
        "coloring book", "workbook", "planner", "ebook",
        "coloring book cover", "title page",
    ]
    if any(kw in all_lower for kw in cover_keywords):
        for i, txt in enumerate(insp["all_text"]):
            if any(kw in txt.lower() for kw in cover_keywords):
                violations.append(f"illegal_cover: keyword on page {i+1}: {txt[:60]!r}")

    # Single-page with cover keywords = cover violation
    if page_count == 1 and violations:
        violations.append("single_page_with_cover: 1-page PDF contains cover text")

    return len(violations) == 0, violations


def _validate_orphan_suspected(
    pdf_bytes: bytes,
) -> tuple[bool, list[str]]:
    """
    Detect orphan PDFs that look like stale coloring book exports.
    Used when no project context is available.
    """
    page_num_re = re.compile(r"page\s+\d+\s+of\s+\d+", re.IGNORECASE)
    insp = _inspect_pdf(pdf_bytes)
    page_count = insp["page_count"]
    all_text = insp["all_text"]
    text_length = sum(len(t) for t in all_text)
    violations: list[str] = []

    # Pattern A: Multi-page with page numbering = suspected stale coloring book
    if page_count > 1:
        for txt in all_text:
            if page_num_re.search(txt):
                violations.append(f"orphan_suspected_coloring_book: page_count={page_count} with page numbering")
                break

    # Pattern B: Single-page "Page 1 of 1" + text = suspected orphan title card
    if page_count == 1 and text_length > 0:
        for txt in all_text:
            if re.search(r"page\s+1\s+of\s+1", txt, re.IGNORECASE):
                violations.append(f"orphan_suspected_coloring_book: single-page with title card 'Page 1 of 1'")
                break

    return len(violations) == 0, violations


# --------------------------------------------------------------------------- //
# Repair for coloring book single sheets
# --------------------------------------------------------------------------- //
def _attempt_single_sheet_repair(
    context: DownloadContext,
    original_bytes: bytes,
) -> tuple[bytes | None, bool]:
    """
    Attempt to repair a bad coloring book single sheet PDF.
    Returns (corrected_bytes or None, was_repaired: bool).
    """
    try:
        # Get the contract
        contract = {}
        try:
            from services.quality.user_instruction_controller import build_coloring_book_contract
            c = build_coloring_book_contract(context.fields)
            contract = c.to_dict()
        except Exception:
            pass

        # Rebuild via QA agent
        from services.coloring_book.coloring_book_qa_agent import _auto_correct_single_sheet
        corrected = _auto_correct_single_sheet(
            fields=context.fields,
            contract=contract,
            package_id=context.package_id or "",
        )

        # Verify correction
        insp = _inspect_pdf(corrected)
        new_page_count = insp["page_count"]
        new_all_lower = insp["all_lower"]
        new_text_length = sum(len(t) for t in insp["all_text"])

        violations: list[str] = []
        if new_page_count != 1:
            violations.append(f"rebuild page_count={new_page_count} (expected 1)")
        captions_val = context.fields.get("captions", context.fields.get("include_captions", ""))
        if str(captions_val).lower() in ("no", "false", "0", "") and new_text_length > 0:
            for txt in insp["all_text"]:
                if len(txt.strip()) > 3:
                    violations.append(f"rebuild text_when_captions_no: {txt[:60]!r}")
                    break
        if "page" in new_all_lower and "of" in new_all_lower:
            violations.append("rebuild has page numbering")
        cover_kw = ["coloring book", "cover", "title page"]
        if any(kw in new_all_lower for kw in cover_kw):
            violations.append("rebuild has cover text")

        if violations:
            return None, False  # Repair failed — still bad

        return corrected, True  # Repair succeeded

    except Exception:
        return None, False  # Repair threw — treat as failure


# --------------------------------------------------------------------------- //
# Core validation
# --------------------------------------------------------------------------- //
def validate_download(context: DownloadContext) -> DownloadResult:
    """
    Main entry point: validate a download request against all rules.

    Returns DownloadResult with the decision and any corrected bytes.
    """
    file_path = context.file_path

    # File must exist
    if not os.path.exists(file_path):
        return DownloadResult(
            status="blocked",
            violations=["File not found on disk."],
            message=f"Download blocked: file not found.",
            error_response={"error": "download_blocked", "message": "File not found."},
            status_code=404,
        )

    # Read file bytes
    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
    except Exception as exc:
        return DownloadResult(
            status="blocked",
            violations=[f"Cannot read file: {exc}"],
            message="Download blocked: cannot read file.",
            error_response={"error": "download_blocked", "message": "Cannot read file."},
            status_code=500,
        )

    filename_lower = context.filename.lower()
    is_pdf = filename_lower.endswith(".pdf")
    is_zip = filename_lower.endswith(".zip")

    # ── ZIP handling ─────────────────────────────────────────────────────────
    if is_zip:
        zip_insp = _inspect_zip(file_bytes)
        zip_pdf_bytes = zip_insp.get("pdf_bytes")
        zip_page_count = zip_insp.get("pdf_page_count", 0)

        if zip_insp.get("error"):
            return DownloadResult(
                status="blocked",
                violations=[f"Cannot read ZIP: {zip_insp['error']}"],
                page_count=0,
                zip_pdf_page_count=0,
                message="Download blocked: cannot read ZIP.",
                error_response={"error": "download_blocked", "message": "Cannot read ZIP."},
                status_code=500,
            )

        if not zip_pdf_bytes:
            return DownloadResult(
                status="blocked",
                violations=["ZIP contains no PDF."],
                zip_pdf_page_count=0,
                message="Download blocked: ZIP contains no PDF.",
                error_response={"error": "download_blocked", "message": "ZIP contains no PDF."},
                status_code=400,
            )

        # Validate PDF inside ZIP with same rules as direct PDF
        pdf_insp = _inspect_pdf(zip_pdf_bytes)
        page_count = pdf_insp["page_count"]
        all_lower = pdf_insp["all_lower"]
        all_text = pdf_insp["all_text"]
        text_length = sum(len(t) for t in all_text)
        violations: list[str] = []
        _refine_coloring_book_cover_eligibility(context, page_count)

        # Coloring book single sheet inside ZIP
        if context.product_type == "coloring_book" and context.is_single_sheet:
            if page_count != 1:
                violations.append(f"zip_pdf_page_count={page_count} (expected 1)")
            if context.expected_page_count > 0 and page_count != context.expected_page_count:
                violations.append(f"zip_expected_pages={context.expected_page_count}, actual={page_count}")

            cover_keywords = ["coloring book", "cover page", "front cover", "book cover", "title page"]
            for i, txt in enumerate(all_text):
                if any(kw in txt.lower() for kw in cover_keywords):
                    violations.append(f"zip_cover_text: page {i+1}: {txt[:60]!r}")
            if "page" in all_lower and "of" in all_lower:
                violations.append("zip_has_page_numbering")
            for i, txt in enumerate(all_text):
                if "page 1 of 1" in txt.lower():
                    violations.append(f"zip_title_card: page {i+1}")
            captions_val = context.fields.get("captions", context.fields.get("include_captions", ""))
            if str(captions_val).lower() in ("no", "false", "0", "") and text_length > 0:
                violations.append("zip_text_when_captions_no")

        # Cover rules for ZIP — independent of coloring-book single-sheet logic.
        # Only block if cover is not eligible.
        if not context.cover_eligible:
            cover_keywords = ["cover page", "front cover", "book cover", "cover", "coloring book", "title page"]
            if any(kw in all_lower for kw in cover_keywords):
                violations.append("zip_contains_illegal_cover")

        # Orphan / stale-revision ZIP: must belong to a current project package.
        if context.project_id is None and context.product_type is None:
            return DownloadResult(
                status="blocked",
                violations=["stale_or_orphan_export_package"],
                page_count=0,
                zip_pdf_page_count=zip_page_count,
                message=(
                    "Download blocked: this export package is not linked to the current "
                    "saved artifact revision. Open the project and export again."
                ),
                error_response={
                    "error": "download_blocked",
                    "message": (
                        "Download blocked: this export package is not linked to the current "
                        "saved artifact revision. Open the project and export again."
                    ),
                    "violations": ["stale_or_orphan_export_package"],
                },
                status_code=403,
            )

        if violations:
            return DownloadResult(
                status="blocked",
                violations=violations,
                page_count=0,
                zip_pdf_page_count=zip_page_count,
                message=f"Download blocked: ZIP contains a bad PDF. Violations: {'; '.join(violations)}",
                error_response={
                    "error": "download_blocked",
                    "message": f"Download blocked: ZIP contains a bad PDF. Violations: {'; '.join(violations)}",
                    "violations": violations,
                },
                status_code=403,
            )

        return DownloadResult(
            status="passed",
            served_path=file_path,
            page_count=0,
            zip_pdf_page_count=zip_page_count,
            message=f"ZIP valid; PDF inside ({zip_insp['pdf_names'][0]}) passed validation.",
        )

    # ── PDF handling ─────────────────────────────────────────────────────────
    if not is_pdf:
        # Non-PDF/ZIP file — permissive (images, HTML, TXT)
        return DownloadResult(
            status="passed",
            served_path=file_path,
            page_count=0,
            message="Non-PDF file served.",
        )

    # Inspect PDF
    try:
        insp = _inspect_pdf(file_bytes)
    except Exception as exc:
        return DownloadResult(
            status="blocked",
            violations=[f"Cannot open PDF: {exc}"],
            message="Download blocked: cannot read PDF.",
            error_response={"error": "download_blocked", "message": "Cannot read PDF."},
            status_code=500,
        )

    page_count = insp["page_count"]
    all_lower = insp["all_lower"]
    all_text = insp["all_text"]
    text_length = sum(len(t) for t in all_text)
    violations: list[str] = []
    _refine_coloring_book_cover_eligibility(context, page_count)

    # ── Orphan / stale-revision detection (no project context) ─────────────
    # PDF product exports must belong to a current project package_id or
    # export_package_id. Orphan folders from earlier revisions are not served.
    # package_belongs_to_project is enforced in resolve_download_request.
    if context.project_id is None and context.product_type is None:
        return DownloadResult(
            status="blocked",
            violations=["stale_or_orphan_export_package"],
            page_count=page_count,
            message=(
                "Download blocked: this export package is not linked to the current "
                "saved artifact revision. Open the project and export again."
            ),
            error_response={
                "error": "download_blocked",
                "message": (
                    "Download blocked: this export package is not linked to the current "
                    "saved artifact revision. Open the project and export again."
                ),
                "violations": ["stale_or_orphan_export_package"],
            },
            status_code=403,
        )

    # ── Coloring Book Single Sheet ─────────────────────────────────────────
    if context.product_type == "coloring_book" and context.is_single_sheet:
        passed, violations = _validate_coloring_book_single_sheet(context, file_bytes)
        if passed:
            return DownloadResult(
                status="passed",
                served_path=file_path,
                page_count=page_count,
                message="Coloring Book Single Sheet passed validation.",
            )

        # Attempt ONE auto-correction
        corrected_bytes, was_repaired = _attempt_single_sheet_repair(context, file_bytes)
        if was_repaired and corrected_bytes:
            return DownloadResult(
                status="repaired",
                served_bytes=corrected_bytes,
                auto_repaired=True,
                repair_attempted=True,
                page_count=page_count,
                message="File was regenerated to match your instructions.",
            )

        # Still bad
        return DownloadResult(
            status="blocked",
            violations=violations,
            repair_attempted=True,
            page_count=page_count,
            message=f"Download blocked: file violates Single Sheet requirements. Violations: {'; '.join(violations)}",
            error_response={
                "error": "download_blocked",
                "message": f"Download blocked: file violates Single Sheet requirements. Violations: {'; '.join(violations)}",
                "violations": violations,
            },
            status_code=403,
        )

    # ── Cover rules (all product types) ──────────────────────────────────────
    if not context.cover_eligible:
        cover_passed, cover_violations = _validate_cover_rules(context, file_bytes)
        if not cover_passed:
            violations.extend(cover_violations)

    if violations:
        return DownloadResult(
            status="blocked",
            violations=violations,
            page_count=page_count,
            message=f"Download blocked: {violations[0]}",
            error_response={
                "error": "download_blocked",
                "message": f"Download blocked: {violations[0]}",
                "violations": violations,
            },
            status_code=403,
        )

    # ── Passed ───────────────────────────────────────────────────────────────
    return DownloadResult(
        status="passed",
        served_path=file_path,
        page_count=page_count,
        message="Download passed validation.",
    )


# --------------------------------------------------------------------------- //
# Main public API
# --------------------------------------------------------------------------- //
def pipeline_download(
    route: str,
    filename: str,
    file_path: str,
    package_id: str | None = None,
    project: dict | None = None,
    fields: dict | None = None,
    product_mode: str | None = None,
) -> tuple[DownloadContext, DownloadResult]:
    """
    Full pipeline: resolve context → validate → record audit → return.

    Call this from every download route. Returns (context, result) so the
    caller can build the appropriate Flask response.
    """
    context = resolve_download_request(
        route=route,
        filename=filename,
        file_path=file_path,
        package_id=package_id,
        project=project,
        fields=fields,
        product_mode=product_mode,
    )
    result = validate_download(context)
    record_download_audit(context, result)
    return context, result
