# FINAL OUTPUT GATE — LOCKED STATE

**Date:** 2026-07-12
**Problem:** `/download/<package_id>/<filename>` served files directly from disk via `send_from_directory()` with zero validation — bypassing all QA agents.

## What Was Fixed

### 1. New File: `flask_app/services/quality/final_output_gate.py`

The Final Output Gate — last-chance enforcement before any file is returned to the user.

**Public API:**
- `validate_download_file(package_id, filename, file_path) → ValidationResult`
- `quarantine_export_folder(package_id) → bool`
- `quarantine_export_folder_by_pid(pid) → list[str]`

**Validation rules for coloring books:**
1. Page count must match `expected_pdf_pages` (from contract or inferred)
2. No cover/title text when `cover_allowed=False`
3. No "Page X of Y" numbering when `page_numbers_allowed=False`
4. No text content when `captions=No`
5. No "Page 1 of 1" title cards (singles are just the image)

**Safety nets for orphan folders (no project found):**
- Multi-page PDF with "Page X of Y" text → BLOCKED
- Single-page PDF with "Page 1 of 1" title card + text → BLOCKED

**Auto-correction:**
- Single Sheet violations → ONE auto-regeneration via `_auto_correct_single_sheet()`
- Still bad after correction → BLOCKED with clear 403 + user message
- Never serves a bad file silently

### 2. `flask_app/app.py` — `/download/` route patched

**Before:**
```python
@app.get("/download/<package_id>/<filename>")
def download_export_route(package_id, filename):
    return send_from_directory(directory, filename, as_attachment=...)
```

**After:**
```python
@app.get("/download/<package_id>/<filename>")
def download_export_route(package_id, filename):
    # 404 if file doesn't exist
    # FINAL OUTPUT GATE: validate before serving
    result = validate_download_file(package_id, filename, file_path)
    if not result.passed:
        return jsonify({error, message, violations}), 403
    if result.was_regenerated:
        return make_response(result.file_bytes)  # serve corrected bytes
    return send_from_directory(directory, filename, ...)  # serve clean file
```

### 3. `flask_app/services/quality/user_instruction_controller.py` — contract builder fixed

**Before:** `build_coloring_book_contract()` raised `ValueError` when `output_format=None` (old projects without format field).

**After:** Falls back to inferring single sheet from `pages=1`:
```python
is_single_sheet = (
    of_lower in _SINGLE_SHEET_PATTERNS
    or output_type == COLORING_OUTPUT_SINGLE_PAGE
    or (not output_format and num_pages == "1")  # NEW
)
```

This ensures old Farm House projects (projects 69, 70, 73, 76, 79) with `pages=1` and no `format` field are correctly identified as Single Sheet.

## What Was Quarantined

**14 bad export folders** moved to `flask_app/exports/_quarantined/`:

| Folder | Project | Issue |
|--------|---------|-------|
| c14fd76f... | Project 79 (Farm House) | 12 pages, expected 1 |
| aafbfe96... | Project 73 (farm house) | 12 pages, expected 1 |
| f644c07d... | Project 76 (Farm House) | 12 pages, expected 1 |
| 250aaa00... | Project 70 (The Farm House) | 12 pages, expected 1 |
| bd315aae... | Project 69 (The Farm House) | 12 pages, expected 1 |
| 101ed84f... | ORPHAN | 13 pages with page numbering |
| 4e9ea7a7... | ORPHAN | 13 pages with page numbering |
| 7abc358b... | ORPHAN | 13 pages with page numbering |
| 912f3544... | ORPHAN | 13 pages with page numbering |
| b36b46e0... | ORPHAN | 13 pages with page numbering |
| d10e38e0... | ORPHAN | 13 pages with page numbering |
| f940e8e4... | ORPHAN | 13 pages with page numbering |
| 88a1c5ef... | ORPHAN | 13 pages with page numbering |
| 770f5c27... | ORPHAN | already gone (pre-existing) |

## Anti-Bypass Guarantees

1. **No static file serving** — `send_from_directory()` is only called after gate validation passes
2. **Regeneration on demand** — bad files are rebuilt, not deleted; user always gets something
3. **Clear 403 errors** — user sees exactly why download was blocked and what the violations are
4. **Orphan safety net** — even files from deleted projects with no project record are blocked if they show coloring book patterns

## Files Changed

- `flask_app/services/quality/final_output_gate.py` — NEW
- `flask_app/app.py` — `/download/` route patched (added gate call)
- `flask_app/services/quality/user_instruction_controller.py` — `build_coloring_book_contract()` fixed (pages=1 fallback)
- `flask_app/exports/_quarantined/` — 13 bad folders moved here

## Related Lock Docs

- `COLORING_BOOK_ZIP_EXPORT_ALL_PATHS_LOCKED_STATE.md` — ZIP export gate (build time)
- `COLORING_BOOK_USER_INSTRUCTION_QA_AGENTS_LOCKED_STATE.md` — QA agents (build time)
