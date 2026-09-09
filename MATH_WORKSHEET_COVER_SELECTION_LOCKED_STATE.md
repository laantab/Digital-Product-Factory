# MATH WORKSHEET COVER SELECTION — LOCKED STATE

**Date locked:** 2026-09-08
**Status:** ACCEPTED — do not revert or modify Math Worksheet's Include Cover logic without re-running `tests/test_math_worksheet_cover_selection_repair.py`.

---

## 1. BASELINE DEFECT

Include Cover was a customer-facing no-op: Yes and No produced identical PDFs for every problem count tried. The customer-facing form did not even expose an "Include cover page" control.

## 2. ROOT CAUSE

Not merely "ignored" — there was no working cover mechanism at all:
- `services/math_worksheet/renderer.py`'s `build_math_worksheet_pdf_bytes()` only ever drew a cover `if cover_image_path and os.path.isfile(...)`.
- Nothing in the pipeline ever produced a real cover image path (no local AI-free cover builder exists for Math Worksheet, unlike Crossword/Word Search).
- `services/math_worksheet/pdf_builder.py`'s `build_math_worksheet_pdf()` never even passed `request.include_cover` to the renderer.
- `services/product.py`'s `_math_worksheet_pdf_payload()` passed `include_cover=cover_allowed` (eligibility only), never reading the customer's own field.
- `services/quality/cover_eligibility_agent.py`'s math_worksheet/spelling_worksheet branch never checked output mode — Single Worksheet could get `cover_allowed=True`, caught only by a downstream QA hard-block that rejected the whole export.

## 3. FILES CHANGED

| File | Change |
|------|--------|
| `static/js/app.js` | Added the missing `include_cover` field to the math_worksheet customer form (mirrors Crossword/Word Search). |
| `services/math_worksheet/renderer.py` | `build_math_worksheet_pdf_bytes` gained `include_cover: bool = False`; draws a plain text-only cover (title + grade/topic) when true and no image is available — zero-cost, no AI/network call. |
| `services/math_worksheet/pdf_builder.py` | Threads `request.include_cover` to the renderer (previously dropped). Dataclass default changed `True → False` (was inert before; now must default conservatively so every pre-existing direct construction of the request keeps its prior observable behavior). |
| `services/product.py` | `_math_worksheet_pdf_payload` now resolves `eligibility.cover_allowed and customer_choice` (explicit Yes/No from the field, default Yes only when missing). |
| `services/quality/cover_eligibility_agent.py` | math_worksheet/spelling_worksheet branch gained an `is_book` gate matching Crossword/Word Search's own branches — Single Worksheet is now correctly ineligible up front instead of raising a QA error. |

## 4. ACCEPTED TEST RESULTS

| Case | Result |
|------|--------|
| Full Workbook, Cover Yes | Cover included (+1 page) |
| Full Workbook, Cover No | Cover excluded |
| Single Worksheet, Cover Yes | Still blocked (valid business rule preserved) |
| Single Worksheet, Cover No | Still blocked |
| Missing/legacy `include_cover` field | Defaults to Yes (backward-compatible) |
| Unrecognized value (e.g. "maybe") | Resolves to No (matches `_yes_default`'s existing, pre-established semantics) |
| Save → Reopen → Generate | Selection preserved (no dedicated normalize step exists for Math Worksheet; fields pass through verbatim) |
| Packaging/export | Accepts both cover and no-cover PDFs |
| External calls | None — `ai_client.chat`/`chat_json` confirmed uncalled |

See `tests/test_math_worksheet_cover_selection_repair.py` for the full protected-baseline contract.
