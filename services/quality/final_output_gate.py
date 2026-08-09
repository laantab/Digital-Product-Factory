"""
Final Output Gate — last-chance enforcement before any file is returned to the user.

Purpose:
  Every route that returns a PDF or ZIP to the user must pass through this gate.
  It is the unavoidable enforcement layer: if any file violates the instruction
  contract or cover eligibility rules, it is either regenerated or the download
  is BLOCKED with a clear user-facing error.

Why this exists:
  The `/download/<package_id>/<filename>` route served files directly from disk
  without any validation. Old stale exports (13-page coloring books, PDFs with
  "Page 1 of 1" headers, PDFs with cover pages) were downloadable directly via
  URL regardless of what the User Instruction Contract or Cover Eligibility Agent
  said. This gate closes that bypass.

Scope:
  - Any PDF file being served as a download
  - Any ZIP file containing PDFs
  - Any route that returns file bytes to the user

How it works:
  1. validate_download_file(package_id, filename, file_path) → validation result
     - Inspects the file with fitz
     - Looks up the associated project from DB via package_id
     - Checks against instruction contract and cover eligibility
     - Returns (passed, violations, corrected_bytes_or_None)
  2. serve_validated_file(package_id, filename) → Flask response
     - Calls validate_download_file
     - If invalid: attempts ONE auto-correction
     - If still invalid: raises error (blocked)
     - If valid: serves the file
  3. quarantine_export_folder(package_id) → moves to quarantine subfolder
     - Marks bad exports so they cannot be served again

Anti-bypass rules:
  - Old export folders on disk CANNOT be served directly
  - Any stale PDF is regenerated on demand
  - No static file serving for coloring book PDFs without gate validation
"""
from __future__ import annotations

import base64
import fitz
import os
import shutil
from dataclasses import dataclass


EXPORTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "exports")
QUARANTINE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "exports", "_quarantined")


@dataclass
class ValidationResult:
    """Result of Final Output Gate validation."""
    passed: bool
    violations: list[str]
    file_bytes: bytes | None       # corrected bytes if regenerated, None if served as-is
    was_regenerated: bool
    project_id: int | None
    product_type: str | None
    is_coloring_book: bool
    is_single_sheet: bool
    cover_eligible: bool
    page_count: int
    text_length: int
    message: str = ""


# -------------------------------------------------------------------------- //
# Core validation
# -------------------------------------------------------------------------- //

def _load_project_by_package_id(package_id: str) -> dict | None:
    """Find the project that owns this export package_id."""
    import sqlite3, json
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
            exports = d.get("product_exports") or {}
            if isinstance(exports, dict):
                for key, val in exports.items():
                    if isinstance(val, dict) and str(val.get("package_id", "")) == package_id:
                        return {"id": pid, "name": name, "type": ptype, "data": d}
        except Exception:
            pass
    return None


def _inspect_pdf_bytes(pdf_bytes: bytes) -> dict:
    """Inspect PDF bytes — returns page_count, all_text, all_lower."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page_count = doc.page_count
    all_text = []
    for page in doc:
        all_text.append(page.get_text().strip())
    doc.close()
    all_lower = " ".join(all_text).lower()
    return {
        "page_count": page_count,
        "all_text": all_text,
        "all_lower": all_lower,
    }


def _check_placeholder_phrases(all_text: list[str]) -> list[str]:
    """
    Scan PDF text for placeholder/generic phrases that indicate a failed product.
    Blocks: themed answer, placeholder, sample clue, lorem ipsum, FALLBACK EXPORT,
    generic fallback, insert topic here, TBD, TBC, no saved content found.
    Returns list of violations (empty if clean).
    """
    from services.factory.topic_intelligence import PLACEHOLDER_PHRASES

    violations = []
    for page_num, txt in enumerate(all_text, start=1):
        txt_lower = txt.lower()
        for phrase in PLACEHOLDER_PHRASES:
            if phrase.lower() in txt_lower:
                violations.append(
                    f"placeholder_phrase (page {page_num}): \"{phrase}\" found in text: {txt[:80]!r}"
                )
    return violations


def validate_download_file(package_id: str, filename: str, file_path: str) -> ValidationResult:
    """
    Validate a file being served via /download/ before it reaches the user.

    This is the ONLY public entry point for file downloads.

    Returns ValidationResult with:
      - passed: True if file is valid
      - violations: list of violation strings if invalid
      - file_bytes: corrected bytes if regenerated, else None (use original file)
      - was_regenerated: True if bytes were regenerated
    """
    if not os.path.exists(file_path):
        return ValidationResult(
            passed=False,
            violations=["File not found on disk."],
            file_bytes=None,
            was_regenerated=False,
            project_id=None,
            product_type=None,
            is_coloring_book=False,
            is_single_sheet=False,
            cover_eligible=False,
            page_count=0,
            text_length=0,
            message="File not found.",
        )

    # Read file
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    filename_lower = filename.lower()
    is_pdf = filename_lower.endswith(".pdf")
    is_zip = filename_lower.endswith(".zip")

    # Load associated project
    project = _load_project_by_package_id(package_id)
    if project:
        data = project.get("data") or {}
        product_type = data.get("product_type", "")
        fields = data.get("fields") or {}
        is_coloring_book = (product_type == "coloring_book")
    else:
        # No project found — be permissive for non-coloring-book files
        data = {}
        product_type = ""
        fields = {}
        is_coloring_book = False

    # For ZIP files: inspect the PDF inside inline (no recursive call)
    if is_zip:
        import zipfile, io
        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
                if not pdf_names:
                    return ValidationResult(
                        passed=True, violations=[], file_bytes=None, was_regenerated=False,
                        project_id=project["id"] if project else None,
                        product_type=product_type,
                        is_coloring_book=is_coloring_book,
                        is_single_sheet=False, cover_eligible=False,
                        page_count=0, text_length=0,
                        message="ZIP contains no PDF.",
                    )
                pdf_bytes = zf.read(pdf_names[0])
                # Inline PDF validation for ZIP contents
                try:
                    insp = _inspect_pdf_bytes(pdf_bytes)
                except Exception as exc:
                    return ValidationResult(
                        passed=False,
                        violations=[f"Cannot read PDF inside ZIP: {exc}"],
                        file_bytes=None, was_regenerated=False,
                        project_id=project["id"] if project else None,
                        product_type=product_type,
                        is_coloring_book=is_coloring_book,
                        is_single_sheet=False, cover_eligible=False,
                        page_count=0, text_length=0,
                        message="Cannot read PDF inside ZIP.",
                    )
                page_count = insp["page_count"]
                all_text = insp["all_text"]
                all_lower = insp["all_lower"]
                text_length = sum(len(t) for t in all_text)
                violations: list[str] = []
                # Global placeholder phrase block — applies to ALL product types
                placeholder_violations = _check_placeholder_phrases(all_text)
                if placeholder_violations:
                    return ValidationResult(
                        passed=False,
                        violations=placeholder_violations,
                        file_bytes=None, was_regenerated=False,
                        project_id=project["id"] if project else None,
                        product_type=product_type,
                        is_coloring_book=is_coloring_book,
                        is_single_sheet=False, cover_eligible=False,
                        page_count=page_count, text_length=text_length,
                        message=(
                            f"Download blocked: PDF contains placeholder phrases. "
                            f"Violations: {'; '.join(placeholder_violations)}"
                        ),
                    )
                contract: dict = {}  # Always defined before if/else below

                if is_coloring_book:
                    contract = data.get("_instruction_contract") or {}
                    if not contract:
                        try:
                            from services.quality.user_instruction_controller import build_coloring_book_contract
                            c = build_coloring_book_contract(fields)
                            contract = c.to_dict()
                        except ValueError:
                            # Same fallback as PDF handler — infer from pages field
                            pages_val = fields.get("pages") or fields.get("num_pages") or ""
                            try:
                                pages_int = int(pages_val)
                            except (ValueError, TypeError):
                                pages_int = 0
                            contract = {
                                "is_single_sheet": (pages_int == 1),
                                "is_digital_book": (pages_int > 1),
                                "expected_pdf_pages": pages_int if pages_int > 0 else 12,
                                "captions": fields.get("captions", fields.get("include_captions", "")),
                                "cover_allowed": False,
                            }
                    is_single_sheet = contract.get("is_single_sheet", False)
                    is_digital_book = contract.get("is_digital_book", False)
                    captions = contract.get("captions", fields.get("captions", ""))
                    captions_no = captions.lower() in ("no", "false", "0", "")
                    cover_allowed = contract.get("cover_allowed", False)
                    expected_pages = contract.get("expected_pdf_pages", 0)

                    if is_single_sheet and page_count != 1:
                        violations.append(f"page_count={page_count} (expected 1)")
                    if expected_pages > 0 and page_count != expected_pages:
                        violations.append(
                            f"expected_pages={expected_pages}, actual_page_count={page_count}"
                        )
                    if not cover_allowed:
                        for i, txt in enumerate(all_text):
                            if any(kw in txt.lower() for kw in [
                                "coloring book", "cover page", "front cover",
                                "book cover", "title page", "coloring book cover",
                            ]):
                                violations.append(f"cover_text: page {i+1}: {txt[:60]!r}")
                    if is_single_sheet:
                        for i, txt in enumerate(all_text):
                            if "page" in txt.lower() and "of" in txt.lower():
                                violations.append(f"page_number: page {i+1}: {txt[:60]!r}")
                    if is_single_sheet and captions_no and text_length > 0:
                        for txt in all_text:
                            if len(txt.strip()) > 3:
                                violations.append(f"text_when_captions_no: {txt[:60]!r}")
                                break
                    if is_single_sheet:
                        for i, txt in enumerate(all_text):
                            if "page 1 of 1" in txt.lower() or ("page" in txt.lower() and "of" in txt.lower() and "1" in txt):
                                violations.append(f"title_card: page {i+1}: {txt[:60]!r}")
                else:
                    # Orphan folder ZIP: multi-page PDF with page numbers = stale coloring book
                    if project is None and page_count > 1:
                        import re
                        page_num_pattern = re.compile(r"page\s+\d+\s+of\s+\d+", re.IGNORECASE)
                        for txt in all_text:
                            if page_num_pattern.search(txt):
                                violations.append(f"orphan_suspected_coloring_book: page_count={page_count}")
                                break

                passed = len(violations) == 0
                if passed:
                    return ValidationResult(
                        passed=True, violations=[], file_bytes=None, was_regenerated=False,
                        project_id=project["id"] if project else None,
                        product_type=product_type,
                        is_coloring_book=is_coloring_book,
                        is_single_sheet=contract.get("is_single_sheet", False),
                        cover_eligible=contract.get("cover_allowed", False),
                        page_count=page_count, text_length=text_length,
                        message=f"ZIP is valid; PDF inside ({pdf_names[0]}) passed validation.",
                    )
                return ValidationResult(
                    passed=False,
                    violations=violations,
                    file_bytes=None,
                    was_regenerated=False,
                    project_id=project["id"] if project else None,
                    product_type=product_type,
                    is_coloring_book=is_coloring_book,
                    is_single_sheet=contract.get("is_single_sheet", False),
                    cover_eligible=contract.get("cover_allowed", False),
                    page_count=page_count,
                    text_length=text_length,
                    message=(
                        f"Download blocked: ZIP contains a bad PDF ({pdf_names[0]}). "
                        f"Violations: {'; '.join(violations)}"
                    ),
                )
        except Exception as exc:
            return ValidationResult(
                passed=False,
                violations=[f"Cannot read ZIP: {exc}"],
                file_bytes=None,
                was_regenerated=False,
                project_id=project["id"] if project else None,
                product_type=product_type,
                is_coloring_book=is_coloring_book,
                is_single_sheet=False,
                cover_eligible=False,
                page_count=0,
                text_length=0,
                message="Invalid ZIP.",
            )

    # For PDFs: full validation
    if not is_pdf:
        return ValidationResult(
            passed=True, violations=[], file_bytes=None, was_regenerated=False,
            project_id=project["id"] if project else None,
            product_type=product_type,
            is_coloring_book=is_coloring_book,
            is_single_sheet=False, cover_eligible=False,
            page_count=0, text_length=0,
        )

    # Inspect PDF
    try:
        insp = _inspect_pdf_bytes(file_bytes)
    except Exception as exc:
        return ValidationResult(
            passed=False,
            violations=[f"Cannot open PDF: {exc}"],
            file_bytes=None, was_regenerated=False,
            project_id=project["id"] if project else None,
            product_type=product_type,
            is_coloring_book=is_coloring_book,
            is_single_sheet=False, cover_eligible=False,
            page_count=0, text_length=0,
            message="Cannot read PDF.",
        )

    page_count = insp["page_count"]
    all_text = insp["all_text"]
    all_lower = insp["all_lower"]
    text_length = sum(len(t) for t in all_text)
    violations: list[str] = []

    # Global placeholder phrase block — applies to ALL product types
    placeholder_violations = _check_placeholder_phrases(all_text)
    if placeholder_violations:
        return ValidationResult(
            passed=False,
            violations=placeholder_violations,
            file_bytes=None, was_regenerated=False,
            project_id=project["id"] if project else None,
            product_type=product_type,
            is_coloring_book=is_coloring_book,
            is_single_sheet=False, cover_eligible=False,
            page_count=page_count, text_length=text_length,
            message=(
                f"Download blocked: PDF contains placeholder phrases. "
                f"Violations: {'; '.join(placeholder_violations)}"
            ),
        )

    if not is_coloring_book:
        # Safety net for orphan folders (no project found).
        # Two patterns indicate a stale coloring book export:
        #   (a) Multi-page with "Page X of Y" page numbering
        #   (b) Single-page with "Page 1 of 1" title card AND text content
        if project is None:
            import re
            page_num_pattern = re.compile(r"page\s+\d+\s+of\s+\d+", re.IGNORECASE)
            for txt in all_text:
                if page_num_pattern.search(txt):
                    return ValidationResult(
                        passed=False,
                        violations=[f"orphan_suspected_coloring_book: page_count={page_count} with page numbering"],
                        file_bytes=None,
                        was_regenerated=False,
                        project_id=None,
                        product_type=None,
                        is_coloring_book=True,
                        is_single_sheet=False,
                        cover_eligible=False,
                        page_count=page_count,
                        text_length=text_length,
                        message=(
                            "Download blocked: this file appears to be a stale coloring book export "
                            "from a deleted project. Please regenerate the export from the current project."
                        ),
                    )
            # Case (b): single-page with "Page 1 of 1" title card + text content
            if page_count == 1 and text_length > 0:
                for txt in all_text:
                    if re.search(r"page\s+1\s+of\s+1", txt, re.IGNORECASE):
                        return ValidationResult(
                            passed=False,
                            violations=[f"orphan_suspected_coloring_book: single-page PDF with title card 'Page 1 of 1' and text content"],
                            file_bytes=None,
                            was_regenerated=False,
                            project_id=None,
                            product_type=None,
                            is_coloring_book=True,
                            is_single_sheet=False,
                            cover_eligible=False,
                            page_count=page_count,
                            text_length=text_length,
                            message=(
                                "Download blocked: this single-page PDF has a 'Page 1 of 1' title card "
                                "and appears to be a stale coloring book from a deleted project. "
                                "Please regenerate the export from the current project."
                            ),
                        )
        # Non-coloring-book: permissive
        return ValidationResult(
            passed=True, violations=[], file_bytes=None, was_regenerated=False,
            project_id=project["id"] if project else None,
            product_type=product_type,
            is_coloring_book=False,
            is_single_sheet=False, cover_eligible=False,
            page_count=page_count, text_length=text_length,
        )

    # ── COLORING BOOK VALIDATION ─────────────────────────────────────────────
    # Get instruction contract
    contract = data.get("_instruction_contract") or {}
    if not contract:
        # Rebuild contract from fields
        try:
            from services.quality.user_instruction_controller import build_coloring_book_contract
            c = build_coloring_book_contract(fields)
            contract = c.to_dict()
        except ValueError:
            # Old projects without output_format field.
            # Infer single sheet from pages=1 (a digital book would never have pages=1).
            pages_val = fields.get("pages") or fields.get("num_pages") or ""
            try:
                pages_int = int(pages_val)
            except (ValueError, TypeError):
                pages_int = 0
            contract = {
                "is_single_sheet": (pages_int == 1),
                "is_digital_book": (pages_int > 1),
                "expected_pdf_pages": pages_int if pages_int > 0 else 12,
                "captions": fields.get("captions", fields.get("include_captions", "")),
                "cover_allowed": False,
            }

    is_single_sheet = contract.get("is_single_sheet", False)
    is_digital_book = contract.get("is_digital_book", False)
    captions = contract.get("captions", fields.get("captions", ""))
    captions_no = captions.lower() in ("no", "false", "0", "")
    expected_pages = contract.get("expected_pdf_pages", 0)
    cover_allowed = contract.get("cover_allowed", False)

    # Rule 1: Page count — single sheet must be exactly 1 page
    if is_single_sheet and page_count != 1:
        violations.append(f"page_count={page_count} (expected 1 for Single Sheet)")

    # Rule 1b: Expected pages mismatch — catches stale exports where the project was
    # reconfigured (e.g. from digital book to single sheet) but old PDF is still on disk.
    # Only applies when expected_pdf_pages is a specific non-zero value.
    if expected_pages > 0 and page_count != expected_pages:
        violations.append(
            f"expected_pages={expected_pages}, actual_page_count={page_count}"
        )

    # Rule 2: Cover text
    if not cover_allowed:
        for i, txt in enumerate(all_text):
            txt_lower = txt.lower()
            if any(kw in txt_lower for kw in [
                "coloring book", "cover page", "front cover", "book cover",
                "title page", "coloring book cover",
            ]):
                violations.append(f"cover_text: page {i+1}: {txt[:60]!r}")

    # Rule 3: Page numbering
    if is_single_sheet:
        for i, txt in enumerate(all_text):
            if "page" in txt.lower() and "of" in txt.lower():
                violations.append(f"page_number: page {i+1}: {txt[:60]!r}")

    # Rule 4: Title text when captions=No
    if is_single_sheet and captions_no and text_length > 0:
        # Any non-trivial text is a violation when captions=No
        for i, txt in enumerate(all_text):
            if len(txt.strip()) > 3:
                violations.append(f"text_when_captions_no: page {i+1}: {txt[:60]!r}")
                break

    # Rule 5: "Page 1 of 1" header (title card on single sheet)
    if is_single_sheet:
        for i, txt in enumerate(all_text):
            if "page 1 of 1" in txt.lower() or ("page" in txt.lower() and "of" in txt.lower() and "1" in txt):
                violations.append(f"title_card: page {i+1}: {txt[:60]!r}")

    passed = len(violations) == 0

    if passed:
        return ValidationResult(
            passed=True, violations=[], file_bytes=None, was_regenerated=False,
            project_id=project["id"] if project else None,
            product_type=product_type,
            is_coloring_book=True,
            is_single_sheet=is_single_sheet,
            cover_eligible=cover_allowed,
            page_count=page_count, text_length=text_length,
        )

    # ── VIOLATIONS FOUND: attempt ONE auto-correction ───────────────────────
    if is_single_sheet and not is_digital_book:
        try:
            from services.coloring_book.coloring_book_qa_agent import (
                _auto_correct_single_sheet,
            )
            corrected_bytes = _auto_correct_single_sheet(
                fields=fields,
                contract=contract,
                package_id=package_id,
            )
            # Re-inspect corrected PDF
            new_insp = _inspect_pdf_bytes(corrected_bytes)
            new_violations = []
            new_page_count = new_insp["page_count"]
            new_all_text = new_insp["all_text"]
            new_all_lower = new_insp["all_lower"]
            new_text_length = sum(len(t) for t in new_all_text)

            if new_page_count != 1:
                new_violations.append(f"rebuild page_count={new_page_count} (expected 1)")
            if captions_no and new_text_length > 0:
                for txt in new_all_text:
                    if len(txt.strip()) > 3:
                        new_violations.append(f"rebuild text_when_captions_no: {txt[:60]!r}")
            if new_page_count == 1 and ("page" in new_all_lower and "of" in new_all_lower):
                new_violations.append(f"rebuild has page numbering")
            if new_page_count == 1 and any(kw in new_all_lower for kw in ["coloring book", "cover"]):
                new_violations.append(f"rebuild has cover text")

            if new_violations:
                return ValidationResult(
                    passed=False,
                    violations=new_violations,
                    file_bytes=None,
                    was_regenerated=False,
                    project_id=project["id"] if project else None,
                    product_type=product_type,
                    is_coloring_book=True,
                    is_single_sheet=True,
                    cover_eligible=False,
                    page_count=new_page_count,
                    text_length=new_text_length,
                    message=(
                        f"Download blocked: the file violates Single Sheet requirements. "
                        f"Violations: {'; '.join(new_violations)}"
                    ),
                )

            # Correction succeeded
            return ValidationResult(
                passed=True,
                violations=[],
                file_bytes=corrected_bytes,
                was_regenerated=True,
                project_id=project["id"] if project else None,
                product_type=product_type,
                is_coloring_book=True,
                is_single_sheet=True,
                cover_eligible=False,
                page_count=new_page_count,
                text_length=new_text_length,
                message="File was regenerated to match your instructions.",
            )
        except Exception as exc:
            return ValidationResult(
                passed=False,
                violations=violations + [f"Auto-correction failed: {exc}"],
                file_bytes=None,
                was_regenerated=False,
                project_id=project["id"] if project else None,
                product_type=product_type,
                is_coloring_book=True,
                is_single_sheet=True,
                cover_eligible=False,
                page_count=page_count,
                text_length=text_length,
                message=(
                    f"Download blocked: the file violates Single Sheet requirements. "
                    f"Violations: {'; '.join(violations)}. "
                    f"Auto-correction also failed: {exc}"
                ),
            )

    # Cannot auto-correct (e.g. digital book violations)
    return ValidationResult(
        passed=False,
        violations=violations,
        file_bytes=None,
        was_regenerated=False,
        project_id=project["id"] if project else None,
        product_type=product_type,
        is_coloring_book=True,
        is_single_sheet=is_single_sheet,
        cover_eligible=cover_allowed,
        page_count=page_count,
        text_length=text_length,
        message=(
            f"Download blocked: the file violates your instructions. "
            f"Violations: {'; '.join(violations)}"
        ),
    )


def quarantine_export_folder(package_id: str) -> bool:
    """
    Move a bad export folder to quarantine so it cannot be served.
    Returns True if quarantined, False if not found.
    """
    src = os.path.join(EXPORTS_DIR, package_id)
    if not os.path.exists(src):
        return False

    os.makedirs(QUARANTINE_DIR, exist_ok=True)
    dst = os.path.join(QUARANTINE_DIR, package_id)

    # Avoid overwriting existing quarantine
    if os.path.exists(dst):
        # Append timestamp
        import time
        dst = os.path.join(QUARANTINE_DIR, f"{package_id}_{int(time.time())}")

    shutil.move(src, dst)
    return True


def quarantine_export_folder_by_pid(pid: int) -> list[str]:
    """Quarantine all export folders belonging to a project ID."""
    import sqlite3, json
    from database import get_conn

    quarantined = []
    conn = get_conn()
    try:
        row = conn.execute(
            "SELECT data FROM projects WHERE id=?", (pid,)
        ).fetchone()
        if not row:
            return []
        d = json.loads(row[0] or "{}")
        pkg_id = d.get("package_id", "")
        exports = d.get("product_exports") or {}
        pkg_ids = [pkg_id] if pkg_id else []
        if isinstance(exports, dict):
            pkg_ids.extend(
                str(v.get("package_id", ""))
                for v in exports.values()
                if isinstance(v, dict)
            )
        for pkg_id in pkg_ids:
            if pkg_id and quarantine_export_folder(pkg_id):
                quarantined.append(pkg_id)
    finally:
        conn.close()
    return quarantined
