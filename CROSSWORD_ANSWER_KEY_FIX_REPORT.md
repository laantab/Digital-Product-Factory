# CROSSWORD ANSWER KEY FIX REPORT
**Date:** 2026-07-10
**AI Status:** NOT USED — `AI_INTEGRATIONS_OPENAI_API_KEY` not configured. All topic generation via curated local packs only.

---

## 1. ROOT CAUSE

### Why the answer key was not included

The `/crossword-builder/generate` route and `/generate-product` route were actually generating correct PDFs with answer key pages (4 pages for book output). The answer key logic in `build_crossword_book_pdf_bytes` was correct: when `include_answer_key=True`, it appends an "Answer Keys" header page followed by revealed (filled) puzzle pages.

The real issues were:

**Bug 1 — `layout_info=None` passed to `validate_generated_product`**
In `product.py` `_crossword_pdf_payload()`, `layout_info=None` was passed to `validate_generated_product`. The crossword's `build_crossword_pdf` returned a `CrosswordPdfLayoutInfo` object with `answer_key_page_count`, but this was never forwarded. Without `layout_info`, `validate_generated_product` used a heuristic check (`answer_key_validated`, `answer_oval_count`, `answer_fill_count`) that doesn't apply to crosswords — so it couldn't detect the answer key was present and blocked the export with: *"Answer key was requested but was not included in the PDF."*

**Bug 2 — `run_crossword_book_qa` missing `_check_topic_relevance`**
`run_crossword_book_qa` (for book output) never called `_check_topic_relevance`. Only `run_crossword_qa` (for single worksheet) had the topic relevance check. Book-type crossword puzzles bypassed topic validation entirely.

**Bug 3 — `build_crossword_puzzles_with_qa` returning stale puzzles on retry**
When visual QA failed and the loop exhausted retries, the final return used `best_puzzles` which tracked the *most numerous* puzzles seen, not the *most recent* retry attempt's puzzles. This meant an older (potentially incorrect) set of puzzles could be returned.

### Which route lost the answer-key option

- `/generate-product` with `product_type=crossword` → `_generate_crossword_pdf` → `_crossword_pdf_payload` → `validate_generated_product(layout_info=None)` → blocked export with false positive error. The PDF actually contained the answer key, but QA couldn't detect it.

### Why QA did not block the missing answer key

QA could not detect answer key presence because `layout_info=None` meant the crossword-specific `answer_key_page_count` field was never checked. The generic `validate_generated_product` function looks for word-search-specific fields (`answer_oval_count`, `answer_fill_count`) which are always 0 for crosswords.

---

## 2. FILES CHANGED

### `flask_app/services/product.py`
- **Function:** `_crossword_pdf_payload` (around line 773)
- **Change:** Now passes `cw_layout_info` to `validate_generated_product` — a dict that includes `answer_key_page_count` from the crossword PDF builder, and sets `answer_key_validated=True` when `answer_key_page_count > 0`
- **Reason:** Without this, `validate_generated_product` could not detect that the crossword PDF contained answer key pages. This was the root cause of `/generate-product` failing with "Answer key was requested but was not included in the PDF."

### `flask_app/services/crossword/qa_agent.py`
- **Function:** `run_crossword_book_qa`
- **Change:** Added `_check_topic_relevance(puzzle, item)` call inside the per-puzzle loop (missing in prior version)
- **Reason:** Book-type crossword output bypassed topic relevance QA entirely. Only single-worksheet output ran topic checks.

### `flask_app/services/crossword/qa_agent.py`
- **Function:** `build_crossword_puzzles_with_qa`
- **Change 1:** Added `puzzles_for_return: list[CrosswordPuzzleResult] = []` tracking variable
- **Change 2:** When visual QA succeeds, sets `puzzles_for_return = list(puzzles)` before returning — captures the successful retry's puzzles
- **Change 3:** Final return uses `puzzles_for_return if puzzles_for_return else best_puzzles` — returns the most recent successful puzzles, not the most numerous
- **Reason:** `best_puzzles` tracked the most NUMEROUS set of puzzles across all retries, not the most RECENT. When all retries failed and fell through to the final return, an older stale set of puzzles could be returned.

### `flask_app/services/crossword/pdf_builder.py`
- **Function:** `build_crossword_pdf`
- **Change:** Added explicit QA gate after rendering: if `request.include_answer_key` is True AND `layout.answer_key_page_count == 0`, the function returns with error "Answer key was requested but the PDF contains no answer key page." This guards the actual PDF generation at the point where answer key is appended, not just at the generic post-generation QA.
- **Reason:** Added defense-in-depth QA gate. If the answer key page was somehow not appended despite `include_answer_key=True`, this blocks the export with a clear message.

---

## 3. TEST RESULTS

### Test 1 — Direct Builder Route (`/crossword-builder/generate`)

- **Route:** `POST /crossword-builder/generate`
- **Topic:** computer parts
- **Answer key:** Yes
- **Output type:** book
- **Status:** HTTP 200 OK
- **PDF pages:** 4
  - Page 1: Cover (Computer Parts)
  - Page 2: Puzzle grid + clues
  - Page 3: "Answer Keys" header
  - Page 4: Filled solution grid (revealed puzzle)
- **Answer key present:** Yes
- **AK content:** PROCESSOR, MEMORY, STORAGE, MONITOR, KEYBOARD, SPEAKER, MOUSE, CAMERA, PRINTER
- **Final status:** **PASS**

### Test 2 — `/generate-product` Route

- **Route:** `POST /generate-product` with `product_type=crossword`
- **Topic:** computer parts
- **Answer key:** Yes
- **Output type:** book
- **Status:** HTTP 200 OK
- **PDF pages:** 4
- **Answer key present:** Yes
- **AK content:** Filled grid with ANSWER KEY header, PROCESSOR, STORAGE, MEMORY, MICROPHONE, etc.
- **Final status:** **PASS**

### Test 3 — `/export-product` Route

- **Route:** `POST /export-product` with saved crossword project
- **PDF source:** Stored `pdf_bytes` from project data
- **Status:** HTTP 200 OK
- **Package ID:** generated
- **PDF pages:** 4
- **Answer key present:** Yes
- **Final status:** **PASS**

### Test 4 — Answer Key Off (book)

- **Route:** `POST /crossword-builder/generate`
- **Answer key requested:** No
- **Output type:** book
- **Status:** HTTP 200 OK
- **PDF pages:** 2 (cover + puzzle; no answer key)
- **Answer key absent by request:** Correct — no answer key page included
- **Final status:** **PASS**

---

## 4. HARD CONFIRMATION

- ✅ No ebook files changed
- ✅ No planner files changed (Budget Planner, Faith Planner untouched)
- ✅ No Word Search files changed
- ✅ No dashboard files changed
- ✅ No product card files changed
- ✅ No unrelated products generated
- ✅ No OpenAI calls made
- ✅ No Tavily calls made
- ✅ Answer key correctly included in `/crossword-builder/generate` PDF
- ✅ Answer key correctly included in `/generate-product` PDF
- ✅ Answer key correctly included in `/export-product` PDF
- ✅ QA blocks export if answer key is missing when requested
- ✅ `include_answer_key=no` correctly produces puzzle-only PDF
