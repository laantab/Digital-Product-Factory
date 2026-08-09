# CROSSWORD ANSWER KEY — LOCKED STATE
**Date locked:** 2026-07-10
**Status:** ACCEPTED — do not revert or modify crossword answer key logic

---

## 1. ACCEPTED FIX STATUS

| Test | Result |
|------|--------|
| Crossword answer key requested = included in PDF | **PASS** |
| Crossword answer key off = puzzle-only PDF allowed | **PASS** |
| `/crossword-builder/generate` | **PASS** |
| `/generate-product` (crossword) | **PASS** |
| `/export-product` (crossword) | **PASS** |

---

## 2. FILES CHANGED

| File | Function | Change |
|------|----------|--------|
| `flask_app/services/product.py` | `_crossword_pdf_payload` | Passes `cw_layout_info` dict to `validate_generated_product` with `answer_key_page_count` and `answer_key_validated=True`. Without this, generic QA could not detect crossword answer key presence and blocked valid exports. |
| `flask_app/services/crossword/qa_agent.py` | `run_crossword_book_qa` | Added `_check_topic_relevance(puzzle, item)` inside per-puzzle loop. Previously, book-type crossword output bypassed topic validation entirely — only single-worksheet ran topic checks. |
| `flask_app/services/crossword/qa_agent.py` | `build_crossword_puzzles_with_qa` | Added `puzzles_for_return` tracking variable; returns most recent successful retry's puzzles instead of the most numerous set. |
| `flask_app/services/crossword/pdf_builder.py` | `build_crossword_pdf` | Added explicit QA gate: if `include_answer_key=True` but `layout.answer_key_page_count == 0`, export is blocked with clear error message. |

---

## 3. ACCEPTED TEST RESULTS

### `/crossword-builder/generate` — AK=yes, book
- **Status:** PASS
- **Pages:** 4
  - Page 1: Cover
  - Page 2: Puzzle grid + clues
  - Page 3: "Answer Keys" header
  - Page 4: Filled solution grid (revealed puzzle)
- **Answer key present:** Yes
- **AK content:** PROCESSOR, MEMORY, STORAGE, MONITOR, KEYBOARD, SPEAKER, MOUSE, CAMERA, PRINTER

### `/generate-product` — AK=yes, book
- **Status:** PASS
- **Pages:** 4
- **Answer key present:** Yes
- **QA error blocked:** No — `layout_info` now correctly passed through

### `/export-product` — AK=yes, book
- **Status:** PASS
- **Pages:** 4
- **Answer key present:** Yes
- Uses stored `pdf_bytes` from project; if stored PDF has answer key, export includes it

### `/crossword-builder/generate` — AK=no, book
- **Status:** PASS
- **Pages:** 2 (cover + puzzle only; no answer key)
- **Answer key absent by request:** Correct

---

## 4. PROTECTED BEHAVIOR

- **Answer key requested (`include_answer_key=yes`)** → PDF must include answer key pages appended after puzzle pages. QA must verify `answer_key_page_count > 0`.
- **Answer key off (`include_answer_key=no`)** → PDF is puzzle-only. No answer key page required. This is allowed.
- **QA must block export** if `include_answer_key=True` but the PDF has no answer key pages.
- **Product export** (`/export-product`) must preserve the answer key from stored `pdf_bytes`.
- **Crossword topic validation** (`_check_topic_relevance`) must still run for all crossword output types — both single worksheet and book.
- **Word Search files must remain untouched.** Changes are restricted to `crossword/qa_agent.py`, `crossword/pdf_builder.py`, and `services/product.py` only.

---

## 5. HARD CONFIRMATION

- ✅ No ebook files changed
- ✅ No planner files changed (Budget Planner, Faith Planner untouched)
- ✅ No Word Search files changed
- ✅ No dashboard files changed
- ✅ No product card files changed
- ✅ No unrelated products generated
- ✅ No OpenAI calls made
- ✅ No Tavily calls made
