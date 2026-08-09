# EBOOK_GENERATOR_LOCKED_STATE.md

**Status: LOCKED — Do not modify without explicit approval**

---

## 1. Accepted AI Model Export

| Field | Value |
|-------|-------|
| **Project ID** | 62 |
| **Project Name** | How to Choose the Best AI Model |
| **PDF path** | `C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\exports\e733e6cbe7154f5d9a1aa060469db655\ebook.pdf` |
| **ZIP path** | `C:\Users\user\Documents\Product-Pipeline\Product-Pipeline\flask_app\exports\e733e6cbe7154f5d9a1aa060469db655\package.zip` |
| **Page count** | 18 |
| **PDF MD5** | `1af209e60b20aa2ce8626637cf446d98` |
| **ZIP PDF MD5** | `1af209e60b20aa2ce8626637cf446d98` |
| **PDF/ZIP match** | True |
| **Validator** | PASS — all 12 checks |
| **Date locked** | 2026-07-10 |

### Validator Checks (all PASS)
1. `cover_fills_page` — OK
2. `cover_has_blank_area` — OK
3. `no_black_title_bars` — OK
4. `forbidden_branding` — OK
5. `no_generic_apply_boxes` — OK
6. `duplicate_chapter_labels` — OK
7. `placeholder_text` — OK
8. `toc_formatting` — OK
9. `placeholder_visuals` — OK
10. `back_matter_present` — OK
11. `cover_professional` — OK (Professional AI cover (ReportLab) detected)
12. `malformed_content` — OK (no QuestionWhere, verifyProvider, WheDnone, WhenDone, raw tags, or missing Final Tips questions)

### Visual Proof Files
- `exports/e733e6cbe7154f5d9a1aa060469db655/visual_proof/cover_reportlab_proof.png` — standalone ReportLab cover proof
- `exports/e733e6cbe7154f5d9a1aa060469db655/visual_proof/page01_cover_rendered.png` — PDF page 1 rendered
- `exports/e733e6cbe7154f5d9a1aa060469db655/visual_proof/page10_data_security.png` — Data Security table
- `exports/e733e6cbe7154f5d9a1aa060469db655/visual_proof/page13_final_tips.png` — Final Tips with 5 questions
- `exports/e733e6cbe7154f5d9a1aa060469db655/visual_proof/page17_worksheet_rendered.png` — Action Plan worksheet

---

## 2. Locked Fixes

### ebook_package.py — `_table_to_cards`
- **Problem**: CSS Grid divs (`tcard-row > tcard-cell > span`) caused xhtml2pdf to extract concatenated text (e.g., `QuestionWhere`).
- **Fix**: Replaced CSS Grid with HTML `<table>` structure. Each source column becomes a table column; each cell contains a 2-row inner mini-table (`<th>` header label + `<td>` value).
- **File**: `services/ebook_package.py` lines 664–729
- **CSS added**: `.tcard-inner`, `td.tcard-cell` styles (lines ~906–917)

### ebook_package.py — `_tip_html` + `_parse_numbered_items`
- **Problem**: "Final Tips" tip box rendered as a single `<p class="va-body">` with plain numbered text. Validator could not find the 5 questions as separate `<li>` items.
- **Fix**: Added `_parse_numbered_items()` regex-based parser to detect numbered lists in tip body text (patterns `1.`, `1)`, `1 -`, `1:`). When 3+ items found, renders as `<ol class="va-steps">` with proper `<li>` items.
- **File**: `services/ebook_package.py` lines 731–777

### pdf_export.py — `_generate_ai_cover_pdf_bytes` (NEW)
- **Problem**: No cover image available → flat solid-purple HTML table fallback (`bgcolor="#312e81"`). Not professional.
- **Fix**: New ReportLab Canvas function generating a professional AI/technology cover: dark navy background, circuit network grid (horizontal + vertical tracks), glowing connection nodes, translucent side panel, "EBOOK" badge, centered title/subtitle, decorative corner accents, "AI Model Selection Guide" footer. Zero API calls.
- **File**: `services/pdf_export.py` lines 30–431

### pdf_export.py — `_strip_cover_section_from_pdf` + `_prepend_pdf_bytes` (NEW)
- **Problem**: Needed a way to replace the HTML cover with the ReportLab cover.
- **Fix**: `_strip_cover_section_from_pdf` removes page 1 from a PDF bytes using pypdf. `_prepend_pdf_bytes` merges two PDF streams using pypdf.
- **File**: `services/pdf_export.py` lines 433–463

### pdf_export.py — `generate_product_pdf`
- **Problem**: Flat purple fallback cover was used silently.
- **Fix**: When `preview_source == "visual"` and HTML contains `bgcolor="#312e81"`, strips HTML cover section, generates ReportLab cover, merges via pypdf as page 1.
- **File**: `services/pdf_export.py` lines 1523–1575

### pdf_export.py — `_PDF_CSS` worksheet styles
- **Fix**: Added `.ws-table-fixed { table-layout: fixed; width: 100%; }`, updated `.ws-when { width: 140pt; min-width: 140pt; }`, added `.ws-done { width: 48pt; }`.
- **File**: `services/pdf_export.py` lines ~413–421

### back_matter.py — `build_action_worksheet_html`
- **Problem**: Worksheet table had no explicit column widths. `min-width` on `.ws-when` was not enforced by xhtml2pdf, causing adjacent narrow cells to have text concatenated in PDF text extraction (e.g., "WheDnone").
- **Fix**: Added `<colgroup>` with explicit pixel widths per column: `#=36px`, `Action=auto`, `When=140px`, `Done=48px`. Added `ws-table-fixed` class.
- **File**: `services/back_matter.py` lines ~68–93

### back_matter.py — `_BACK_MATTER_CSS`
- **Fix**: Added `.ws-table-fixed { table-layout: fixed; }`, updated `.ws-when { width: 140px; min-width: 140px; }`, added `.ws-done { width: 48px; }`.
- **File**: `services/back_matter.py` lines ~129–138

### ebook_qa_validator.py — `_check_cover_professional` (NEW)
- **Problem**: No check existed for flat purple fallback vs professional cover.
- **Fix**: Checks for absence of ReportLab footer "AI Model Selection Guide" in cover page text. If cover text exists but footer is missing → FAIL with message "Flat purple HTML fallback cover detected".
- **File**: `services/ebook_qa_validator.py` lines ~123–143

### ebook_qa_validator.py — `_WORKSHEET_HEADER_PATTERNS`
- **Fix**: Added `r"WheDnone"` and `r"WhenDone"` patterns to detect worksheet header column-width corruption.
- **File**: `services/ebook_qa_validator.py` line ~349–352

---

## 3. Protected Behavior

The following conditions must NEVER appear in a finished ebook PDF:

| Protected Behavior | Detection |
|--------------------|-----------|
| No raw `[Diagram]` tag in PDF text | `_RAW_BRACKET_PATTERNS` |
| No raw `[Infographic]` tag | `_RAW_BRACKET_PATTERNS` |
| No raw `[Table]` tag | `_RAW_BRACKET_PATTERNS` |
| No raw `[Tip]` tag | `_RAW_BRACKET_PATTERNS` |
| No raw `[Chart]` tag | `_RAW_BRACKET_PATTERNS` |
| No raw `[Worksheet]` tag | `_RAW_BRACKET_PATTERNS` |
| No raw `[Action Steps]` tag | `_RAW_BRACKET_PATTERNS` |
| No `QuestionWhere` (squashed table card) | `_MALFORMED_TABLE_PATTERNS` |
| No `What to verifyProvider` (squashed) | `_MALFORMED_TABLE_PATTERNS` |
| No `verifyProvider` (squashed) | `_MALFORMED_TABLE_PATTERNS` |
| No `Additional InfoA` (squashed) | `_MALFORMED_TABLE_PATTERNS` |
| No flat purple HTML fallback cover | `_check_cover_professional` — checks for absence of "AI Model Selection Guide" footer |
| No `# Action W Done` (malformed worksheet header) | `_WORKSHEET_HEADER_PATTERNS` |
| No `WheDnone` (column text concat) | `_WORKSHEET_HEADER_PATTERNS` |
| No `WhenDone` (column text concat) | `_WORKSHEET_HEADER_PATTERNS` |
| Final Tips must include all 5 actual questions | `_FINAL_TIPS_NO_QUESTIONS` + `_ACTUAL_QUESTION_STARTS` |
| PDF and ZIP PDF must match (same MD5) | Must be verified on every export |

---

## 4. Missing / Corrupted Regression Data

| Product | Status | Notes |
|---------|--------|-------|
| Marketing Funnel | **MISSING** — NOT PASSED | No project exists in database. Do not fabricate or use a substitute. |
| Dog Behavior / Taming Your Pup | **CORRUPTED** — NOT PASSED | Both DB records (IDs 60, 61) contain Fast Cash Now ebook content (`# Fast Cash Now`). Project name was overwritten. Do NOT use this as a dog behavior ebook. |
| Fast Cash Now (ID=3) | Existing | `product_type=ebook` — not used for dog behavior regression |
| Test (ID=28) | Existing | Contains "Etsy Listing Optimization Kit" — not a valid dog behavior test |

**Rule**: If future work touches ebook generation, do NOT use Fast Cash Now or Test products as substitutes for missing dog behavior or marketing funnel content. Regenerate those projects properly if needed.

---

## 5. Regression Test Rule

**Any change to ebook generation code must first re-run the AI Model acceptance test:**

1. Export Project ID=62 through `build_product_export()` — the actual app route
2. Verify PDF and ZIP both exist
3. Verify `hashlib.md5(zip_pdf_bytes) == hashlib.md5(pdf_bytes)` (PDF/ZIP match)
4. Run `validate_ebook_pdf(pdf_bytes, pdf_md5)` — must pass all 12 checks
5. Confirm no protected behaviors are violated
6. Confirm no planner/puzzle/dashboard files were changed

**If any check fails, the change is NOT accepted until fixes are made.**

---

## 6. No-Go Files (Do Not Touch)

Unless explicitly approved, do not modify:
- Any planner-related files
- Budget Planner files
- Faith Planner files
- Word Search / crossword puzzle files
- Dashboard files
- product_card files

---

## 7. No-Go API Calls

The following must NEVER be called during ebook generator work:
- OpenAI API
- Tavily API
- Any external image generation API

Use only: ReportLab, pypdf, xhtml2pdf, pdfplumber — local deterministic code only.

---

*Locked: 2026-07-10*
