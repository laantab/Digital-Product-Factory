# COLORING BOOK USER INSTRUCTION CONTROLLER AND QA AGENT — LOCKED STATE

**Locked:** 2026-07-12
**Agent:** General
**Status:** ACCEPTED — LOCKED

---

## 1. ACCEPTED ROOT CAUSE

The same failure repeated across every iteration because there was no shared record of what the user asked for and no gate that enforced it on every path:

- `/generate-product` and `/export-product` made independent decisions about what PDF to return. They could disagree. A correct 1-page PDF from generation could be overwritten by a stale 13-page PDF on export.
- Stored `pdf_bytes` in the database was trusted without inspection. Old iterations of a project — with wrong page counts, cover pages, or "Page X of Y" numbering — would be re-packaged silently on every export.
- No QA layer existed between generation and download. The app returned whatever was stored without checking whether it matched the user's selected output format.
- No auto-correction existed. When a bad PDF was detected, nothing had the authority or ability to rebuild it correctly and return the fixed version.

The two guard agents close all four gaps with a single source of truth (the instruction contract) that travels with the product through every path.

---

## 2. ACCEPTED AGENTS

### Agent 1 — User Instruction Controller

**File:** `flask_app/services/quality/user_instruction_controller.py`

**Purpose:** Reads the user's actual selected form fields and builds a strict, machine-verifiable execution contract before any PDF is generated or returned. The contract travels with the product data so every downstream path — generation, export, download — reads from the same source of truth.

**Key function:** `build_coloring_book_contract(fields)` — raises `ValueError` if the contract cannot be determined (fail-fast: do not generate). Returns a `ColoringBookContract` dataclass.

**For Coloring Book Single Sheet, the contract enforces:**

```
expected_pdf_pages             = 1
cover_allowed                  = False
title_page_allowed             = False
front_matter_allowed           = False
headers_allowed               = False
footers_allowed               = False
page_numbers_allowed          = False
scene_labels_allowed          = False  (when captions = No)
captions_allowed              = False  (when captions = No)
book_assembly_allowed          = False
digital_book_behavior_allowed  = False
stale_export_allowed          = False
zip_pdf_must_match_standalone  = True
is_single_sheet               = True
is_digital_book               = False
```

**Other functions:**
- `build_instruction_contract(product_type, fields)` — public entry point, delegates per product type
- `save_instruction_contract(contract, data)` — stamps contract into product data
- `get_instruction_contract(data)` — retrieves saved contract
- `verify_coloring_book_contract(contract, pdf_bytes)` — fitz-based contract verification
- `enforce_coloring_book_or_raise(contract, pdf_bytes, context)` — hard block on violation

---

### Agent 2 — Coloring Book QA Auto-Corrector

**File:** `flask_app/services/coloring_book/coloring_book_qa_agent.py`

**Purpose:** Inspects every coloring book PDF before it is returned or packaged. If violations are found, performs exactly one automatic correction, then re-inspects. If the second check still fails, the output is blocked and a clear error is returned.

**Key function:** `validate_and_correct_coloring_book_output(fields, pdf_bytes, contract, package_id)` — main gate. Returns `(pdf_bytes, was_corrected)`. Raises `ValueError` on hard block.

**QA inspection rules for Single Sheet — fails on any of:**
- PDF page count is not exactly 1
- cover page exists (text containing "Coloring Book", "cover", "cover page", "front cover")
- title page exists
- "Page X of Y" numbering detected
- text on any page when `captions = No`
- header text at top of any page
- footer text at bottom of any page
- title phrase repeated on page when `captions = No`

**Auto-correction:** If QA fails for Single Sheet, calls `_coloring_book_pdf_payload()` directly with corrected fields (`output_type=single_page`, `pages=1`, `include_cover=False`). Re-checks. Raises on second failure.

**Other functions:**
- `validate_coloring_book_pdf(pdf_bytes, contract)` — fitz-based inspection, returns `(passed, violations)`
- `_auto_correct_single_sheet(fields, contract, package_id)` — rebuild + re-check
- `qa_coloring_book_zip(zip_bytes, contract, pdf_filename_in_zip)` — inspect PDF inside a ZIP without disk extraction
- `_inspect_pdf(pdf_bytes)` — fitz wrapper returning page count, all text, and detection flags

---

## 3. FILES CHANGED

### `flask_app/services/product.py`
**Function:** `_generate_coloring_book_pdf()`
**Change:** Wrapped the existing `_coloring_book_pdf_payload()` call with the full guard pipeline:
1. Build instruction contract before generation (fails fast on bad fields)
2. Generate PDF via existing logic
3. QA the generated PDF with `validate_and_correct_coloring_book_output()`
4. Auto-correct if violations found
5. Attach `instruction_contract`, `qa_passed`, `qa_corrected` to result
6. Stamp contract into `result["fields"]` via `save_instruction_contract()`

**Why:** The `/generate-product` route must create a verified, contract-compliant PDF and save the contract for all downstream paths to use.

---

### `flask_app/services/packaging.py`
**Function:** `build_product_export()` — coloring_book path
**Change:** Replaced the inline stale-PDF check with the full QA agent pipeline:
1. Load saved `_instruction_contract` from product data
2. If absent (old projects), rebuild contract from `data.fields` via `build_coloring_book_contract()`
3. Call `validate_and_correct_coloring_book_output()` on stored `pdf_bytes`
4. Auto-correct if QA fails (stale 13-page PDFs trigger rebuild here)
5. If QA fails a second time, raise `ValueError` (hard block — error returned to user, no bad file downloaded)

**Why:** The `/export-product` route was the original failure point — it blindly used stored `pdf_bytes`. The QA agent now guards it.

---

### `flask_app/services/quality/user_instruction_controller.py`
**Status:** New file — Agent 1

---

### `flask_app/services/coloring_book/coloring_book_qa_agent.py`
**Status:** New file — Agent 2

---

## 4. VERIFIED TESTS

| Test | Route / Method | Result |
|---|---|---|
| Test 1 — User Instruction Contract | Direct function call: `build_coloring_book_contract()` | **PASS** — `expected_pdf_pages=1`, `cover_allowed=False`, `headers_allowed=False`, `page_numbers_allowed=False`, `captions_allowed=False`, `is_single_sheet=True` |
| Test 2 — Generate Product | `POST /generate-product` | **PASS** — 1 page, 0 text, `qa_passed=True`, `qa_corrected=False`, `is_single_sheet=True` |
| Test 3 — Export Product / ZIP | `POST /export-product {"project_id": 71}` | **PASS** — ZIP PDF 1 page, 0 text |
| Test 4 — Bad 13-page Auto-Correction | `POST /export-product` on simulated stale project | **PASS** — stale rejected, corrected 1-page PDF in ZIP |
| Test 5 — Digital Book Preservation | `POST /export-product {"project_id": 73}` | **PASS** — 13 pages preserved, Single Sheet rules not applied |
| Test 6 — Saved Project Reopen | `POST /export-product {"project_id": 71}` | **PASS** — 1 page, 0 text |

---

## 5. FARM HOUSE FINAL PROOF

**Test 2 — Fresh generation via `POST /generate-product`:**

Request fields:
```
product_type:  coloring_book
output_format: Single Sheet
theme:         Farm House
num_pages:     1
quality_mode:  AI Image Coloring Page
art_style:     realistic coloring-page line art
captions:      No
```

Response:
```
status:              200
time:                54.2s
qa_passed:           True
qa_corrected:        False
instruction_contract.is_single_sheet: True
```

**Tests 3 & 6 — ZIP export via `POST /export-product`:**

Request: `{"project_id": 71}` (Farm House Single Sheet, saved with contract)

Fresh ZIP: `http://127.0.0.1:5000/download/a0441f43ed5841f397b6418142bc6e6b/package.zip`

| Property | Standalone PDF (Test 2) | ZIP PDF (Test 3) |
|---|---|---|
| Page count | **1** | **1** |
| Text length | **0 chars** | **0 chars** |
| Cover present | No | No |
| "Page 1 of 12" | No | No |
| QA passed | Yes | Yes |

---

## 6. AUTO-CORRECTION PROOF

**Test 4 — Regression: simulated 13-page stale PDF injected into test project ID=78**

Injected bad PDF:
- 13 pages
- Page 1: "Farm House Coloring Book\nSingle Sheet\nCover Page"
- Pages 2–13: "Farm House coloring page\nPage X of 12"
- Size: 8,943 bytes

Contract stored: `is_single_sheet=True`, `expected_pdf_pages=1`

| Step | Result |
|---|---|
| Stale 13-page PDF detected | **Yes** — `page_count=13 != 1` |
| QA rejected stale PDF | **Yes** — triggered `validate_and_correct_coloring_book_output()` |
| Auto-correction attempted | **Yes** — `_auto_correct_single_sheet()` called `_coloring_book_pdf_payload()` |
| Corrected output page count | **1** |
| ZIP PDF page count | **1** |
| Same bytes as stale | **No** — 8,943 bytes → 1,201,025 bytes corrected |
| Bad PDF blocked from download | **Yes** — stale bytes never packaged |

---

## 7. DIGITAL BOOK PRESERVATION

**Test 5 — Project 73 (Farm House Digital Book)**

- `fields.output_format: Digital Book` → `is_digital_book=True`
- Stored PDF: 13 pages, 12,259,331 bytes
- `POST /export-product {"project_id": 73}`
- Digital Book QA path: `page_count >= 1` passes (permissive for books)
- Single Sheet QA rules (1-page, no cover, no numbering) **not applied**

| Check | Result |
|---|---|
| Digital Book still supports multi-page output | **Yes** — 13 pages |
| Digital Book can include cover | **Yes** |
| Single Sheet rules applied to Digital Book | **No** — correctly skipped |
| Digital Book export blocked | **No** — passes |

---

## 8. PROTECTED BEHAVIOR

These behaviors are locked and must not be reverted or weakened:

- Single Sheet PDFs must always be exactly 1 page — enforced by contract + QA agent
- Single Sheet PDFs must never include a cover page — enforced by QA violation check
- Single Sheet PDFs must never include headers, footers, or page numbers when `captions = No` — enforced by QA violation check
- ZIP export must never package a stale 13-page Single Sheet PDF — QA agent rejects and rebuilds
- Bad stored Single Sheet PDFs must be corrected or blocked before any download is returned
- Auto-correction must rebuild using `_coloring_book_pdf_payload()` with `output_type=single_page`, `pages=1`, `include_cover=False`
- Digital Book behavior must remain separate from Single Sheet rules — `is_digital_book=True` bypasses Single Sheet QA
- Instruction contract must travel with the product data (`_instruction_contract` key) so all downstream paths share the same source of truth

---

## 9. HARD CONFIRMATION

- ✅ No ebook files changed
- ✅ No Word Search files changed
- ✅ No Crossword files changed
- ✅ No planner files changed
- ✅ No Budget Planner changes
- ✅ No Faith Planner changes
- ✅ No Tavily calls
- ✅ No unrelated products generated
- ✅ All 6 tests passed
- ✅ Single Sheet cannot return 13-page output
- ✅ Single Sheet cannot return a cover
- ✅ Single Sheet cannot return headers/page numbers when captions = No
- ✅ ZIP cannot package stale 13-page Single Sheet PDF
- ✅ Bad stored PDFs are corrected or blocked before download
- ✅ Auto-correction rebuilds via `_coloring_book_pdf_payload()` with correct fields
- ✅ Digital Book multi-page and cover behavior preserved
- ✅ Agents are created AND wired into real HTTP routes
