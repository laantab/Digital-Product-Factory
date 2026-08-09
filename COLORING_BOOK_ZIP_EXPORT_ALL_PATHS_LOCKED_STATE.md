# COLORING BOOK ZIP EXPORT ALL-PATHS — LOCKED STATE

**Locked:** 2026-07-12
**Agent:** General
**Status:** ACCEPTED — LOCKED

---

## 1. ACCEPTED ROOT CAUSE

- `build_product_export()` was blindly using the stored `pdf_bytes` from the project record with zero validation
- Old 13-page Single Sheet PDFs saved in the database could be re-packaged on every export without being checked
- `/generate-product` could pass validation while `/export-product` still packaged the stale wrong PDF
- The ZIP export path had no enforcement of Single Sheet rules — it was a silent passthrough of whatever was stored
- The fix required validation at the export layer, independent of the generation layer

---

## 2. ACCEPTED BEHAVIOR

- Single Sheet standalone PDF = 1 page
- Single Sheet ZIP PDF = 1 page
- Stale 13-page Single Sheet PDFs are rejected at export time and rebuilt
- ZIP export no longer packages old 13-page Single Sheet PDFs
- Digital Book behavior is fully preserved
- Digital Book can still have cover + multiple pages — Single Sheet rules do not apply to it

---

## 3. FILES CHANGED

### `flask_app/services/packaging.py`
- **Function:** `build_product_export()`
- **Change:** Added Single Sheet PDF validation before packaging
- **Mechanism:**
  - Decodes stored `pdf_bytes` from the project record
  - Opens with `fitz` and checks `page_count`
  - Fast path: if `page_count == 1`, uses stored PDF directly (no rebuild needed)
  - Slow path: if `page_count != 1` AND `_is_single_sheet(fields)` is True, rejects the stale PDF
  - On rejection: calls `regenerate_coloring_book_pdf_for_export()` from `sheet_validator.py`
  - The regenerated PDF (1 page, no cover, no page numbers) is then packaged into the ZIP
- **Scope:** Only affects coloring_book products with `is_pdf=True` and `output_format=Single Sheet`
- **No effect on:** Digital Book, ebook, Word Search, Crossword, or any planner products

### `flask_app/services/coloring_book/sheet_validator.py`
- **New module** — shared Single Sheet validation and regeneration
- **`regenerate_coloring_book_pdf_for_export()`** — the full PDF rebuild function called from `packaging.py`
  - Calls `_coloring_book_pdf_payload()` with the stored fields
  - Returns raw PDF bytes
  - Raises `RuntimeError` if regeneration fails (propagated as `ValueError` by the caller)
- **`_is_single_sheet()`** — normalizes and detects Single Sheet output format
- **`_validate_single_sheet_pdf()`** — validates a PDF meets Single Sheet rules (1 page, no cover, no numbering)
- Used by: `packaging.py` (export path, new), and potentially by other paths that need guaranteed-correct Single Sheet output

---

## 4. VERIFIED TESTS

### Real export route: `POST /export-product`

**Project:** ID=71 — "Farm House", `product_type=coloring_book`, `output_format=Single Sheet`

**Request:**
```
POST /export-product
{"project_id": 71}
```

**ZIP path:** `exports/84a3570e8f3b4d9ba9c22e4fb5140852/package.zip`

**PDF inside ZIP:** `farm_house.pdf`

| Property | Result |
|---|---|
| ZIP PDF page count | **1** ✅ |
| ZIP PDF extracted text length | **0 chars** ✅ |
| Cover present in ZIP PDF | **No** ✅ |
| "Page 1 of 12" present in ZIP PDF | **No** ✅ |
| Stored PDF matched ZIP PDF | Yes (2,074,027 bytes — fast path, already correct) |

### Standalone PDF (DB record for project 71)

| Property | Result |
|---|---|
| Page count | **1** ✅ |
| Extracted text | **0 chars** ✅ |
| Cover text | **None** ✅ |

---

## 5. STALE PDF REJECTION TEST

**Test method:** Injected a synthetic 13-page fake PDF with cover + "Page X of 12" into a fresh test project (ID=75) with `is_pdf=True` and `output_format=Single Sheet`.

**Injected stale PDF (before export):**
- 13 pages
- Page 1 text: `"Farm House Coloring Book\nSingle Sheet\nCover Page"`
- Pages 2–13: `"Farm House coloring page\nPage X of 12"`
- Size: 8,943 bytes

**Export call:** `POST /export-product {"project_id": 75}`

**ZIP PDF (after export):**
- **Page count: 1** ✅
- **"Page X of 12": No** ✅
- **Cover text: No** ✅
- **Same bytes as stale: No** (regenerated) ✅
- **Size: 1,201,025 bytes** (corrected 1-page PDF)

**Verdict:** Stale 13-page PDF was **rejected** at the `page_count != 1` guard. `_is_single_sheet(fields) = True` triggered full regeneration. Corrected 1-page PDF was packaged. The stale PDF was **never** included in the ZIP.

---

## 6. DIGITAL BOOK PRESERVATION

**Project:** ID=73 — "farm house", `product_type=coloring_book`, `fields.output_format=Digital Book`

**Stored PDF:** 13 pages, 12,259,331 bytes

**Export call:** `POST /export-product {"project_id": 73}`

**ZIP PDF:**
- **Pages: 13** ✅
- **First page text: empty** ✅ (image-based coloring page)
- **Cover behavior preserved: Yes** ✅

**Mechanism:** `_is_single_sheet()` returns `False` for `output_format=Digital Book`. `_validate_and_maybe_regenerate()` returns the stored PDF unchanged. Digital Book multi-page structure is fully preserved.

---

## 7. PROTECTED BEHAVIOR

These behaviors are protected by the fix and must not be reverted:

- Do NOT package stale 13-page Single Sheet PDFs in any ZIP export
- Do NOT let ZIP export bypass Single Sheet page-count rules
- Do NOT let old export folders on disk become current downloads (the fix validates at export time, not by trusting old disk artifacts)
- Do NOT use Basic Test Fallback as proof of correctness for Single Sheet output
- Do NOT weaken the AI Image Coloring Page quality gate for Single Sheet products
- Do NOT change Digital Book behavior — it must still support cover pages and multi-page structure

---

## 8. HARD CONFIRMATION

- ✅ No ebook files changed
- ✅ No Word Search files changed
- ✅ No Crossword files changed
- ✅ No planner files changed
- ✅ No Budget Planner changes
- ✅ No Faith Planner changes
- ✅ No Tavily calls made during this fix or testing
- ✅ No unrelated products generated
- ✅ Single Sheet standalone PDF = 1 page
- ✅ Single Sheet ZIP PDF = 1 page
- ✅ No stale 13-page Single Sheet PDF can be packaged in any ZIP export
- ✅ Digital Book export preserved (13 pages, cover OK)
- ✅ No Basic Test Fallback used as proof
- ✅ PDF inside ZIP was inspected with fitz before declaring success
- ✅ `/export-product` route (not just `/generate-product`) was the tested path
