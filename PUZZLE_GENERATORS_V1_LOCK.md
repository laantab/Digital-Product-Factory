# Puzzle Generators — V1 LOCK

**Lock ID:** `puzzle_generators_v1`
**Locked on:** 2026-07-29
**Scope:** Four visible puzzle/worksheet product types in the Factory menu.
**Status:** LOCKED

This lock freezes the behavior of the four puzzle/worksheet product builders after
the customer-path validation pass. The four products are: **Word Search**,
**Crossword**, **Math Worksheet**, and **Spelling Worksheet**.

Two source files in the dispatch / export path were intentionally modified for
this lock cycle: `flask_app/services/packaging.py` (added a dedicated
`math_worksheet` export branch; preserves stored `pdf_bytes` for all four
products) and `flask_app/static/js/app.js` (added the
`include_challenge` form field on the math_worksheet card). Their md5s are
recorded in `PUZZLE_GENERATORS_V1_REGRESSION.json` and must not drift without
re-locking.

---

## What is locked

| Product | Customer-path test | Test topic | Result |
| ------- | ------------------ | ---------- | ------ |
| Word Search | PASS | Computer Parts (Grade 3-5) | ✅ |
| Crossword | PASS | Office Supplies | ✅ |
| Math Worksheet (challenge=No default) | PASS | Mixed Arithmetic, Grade 3 | ✅ |
| Math Worksheet (challenge=Yes) | PASS | Mixed Arithmetic, Grade 3 | ✅ |
| Spelling Worksheet | PASS | Farm Animals, Grade 3 | ✅ |

All four products pass the full customer path:
1. `POST /generate-product` (HTTP 200, returns valid PDF bytes)
2. `POST /projects` (save as `product` type, marked `system_test=true`)
3. `POST /export-product` (HTTP 200, returns PDF + ZIP URLs)
4. `GET /download/.../file.pdf` (HTTP 200, real PDF content)
5. `GET /download/.../package.zip` (HTTP 200, real ZIP)
6. ZIP-inside PDF == direct download PDF (byte-identical)

No product falls through to the generic ebook fallback. No product is missing
its answer key when one is requested. No product requires an OpenAI / Tavily
call for normal generation.

---

## Per-product approved behavior

### 1. Word Search

- **Customer-path test:** Computer Parts, 17 curated words, 12×12 grid, Single Puzzle format, answer key included. Word list sourced from `creation_mode: "Custom word list"` with `custom_words` provided by the user — **no AI call**.
- **Behavior:**
  - When the user supplies `custom_words`, those exact words are used.
  - When `custom_words` is empty, the local pack matcher runs first
    (`word_search/word_lists.py:suggest_words_from_topic`). Whole-token and exact-phrase
    matching only. AI fallback only if no local pack matches and the local fallback pool
    is empty. Never cross-supplements from unrelated topic packs.
  - No fruit, plant, animal, or other topic contamination.
  - Answer Key page is included when `include_answer_key: "Yes"`.
  - No "themed answer" / placeholder content.
- **Customer download:** PDF + ZIP, byte-identical ZIP-inside PDF.

### 2. Crossword

- **Customer-path test:** Office Supplies, 10 real office-supply clues, Single Puzzle format, answer key included. Word list sourced from `custom_words` (curated) — **no AI call**.
- **Behavior:**
  - When the user supplies `custom_words`, those exact words are used.
  - When `custom_words` is empty, `crossword/word_entries.py:suggest_crossword_words_from_topic`
    runs first (local topic vocabulary; no API). Only if that returns zero words does
    `fetch_crossword_words_from_ai` (OpenAI) get called as a last resort.
  - No "themed answer" / placeholder / sample / example clues.
  - Real clues with reference numbers (1-10) and across/down split.
  - Answer Key page is included when `include_answer_key: "Yes"`.
- **Customer download:** PDF + ZIP, byte-identical ZIP-inside PDF.

### 3. Math Worksheet

- **Customer-path test A:** Mixed Arithmetic, Grade 3, 20 problems, Medium difficulty, answer key: Yes, **challenge: No (default)**. PDF: 2 pages (worksheet + answer key). No challenge problem appears.
- **Customer-path test B:** Mixed Arithmetic, Grade 3, 20 problems, Medium difficulty, answer key: Yes, **challenge: Yes**. PDF: 4 pages (worksheet + challenge + main answer key + challenge answer key).
- **Behavior:**
  - **Fully local / procedural.** No `chat_json`, no OpenAI, no API key dependency,
    no Tavily. The `chat_json` import has been removed from
    `math_worksheet/builder.py`. The generator uses `random.randint` with
    grade-aware number ranges and an operator mix derived from the topic.
  - Form field `include_challenge` is a Yes/No select with **default No**.
  - When `include_challenge="Yes"`, 1-3 challenge problems are generated (medium/hard
    difficulty only). The renderer draws an additional
    **"Answer Key — Challenge Section"** page with the challenge answers
    (in the PDF) and the export ZIP's `answer_key.txt` gets a
    `--- Challenge Answers ---` block.
  - When `include_challenge="No"`, no challenge page, no challenge answer.
  - No "FALLBACK EXPORT" in any downloaded PDF.
  - ZIP contains only product-specific files (PDF + metadata.json + problems.txt
    + answer_key.txt). Never `ebook.html` / `ebook.txt` / `ebook.pdf`.
- **Customer download:** PDF + ZIP, byte-identical ZIP-inside PDF.

### 4. Spelling Worksheet

- **Customer-path test:** Farm Animals, Grade 3, 10 words, Word List activity, answer key: Yes. **No AI call** — uses local `_TOPIC_BANKS["farm"]` match in `spelling_worksheet/builder.py`.
- **Behavior:**
  - Local topic bank or grade-level word bank. Builder file header is explicit:
    "No OpenAI, no chat_json, no Tavily. All word generation is from built-in
    topic banks and grade-level word banks. The only external dependency
    removed is the AI word-generation path."
  - WORD BANK appears only on the appropriate page (not leaked onto student
    answer pages or the answer key).
  - Answer Key page lists the correct farm animal spellings.
  - ZIP contains PDF + metadata.json + spelling_words.txt + answer_key.txt.
- **Customer download:** PDF + ZIP, byte-identical ZIP-inside PDF.

---

## Locked decisions (do not change without re-locking)

1. **No AI calls in the normal customer path for any of the four products.**
   Word Search / Crossword use the user's `custom_words` (no API). Math Worksheet
   is fully local procedural (no `chat_json`). Spelling Worksheet uses local
   topic banks. The user policy "AI fallback is the right answer" is preserved
   for **edge cases** (no local pack match for word search / crossword) — but
   the default test topics all use local resources.
2. **No fallback ebook packages.** Each product has a dedicated export branch
   in `packaging.py:build_product_export` that uses the stored `pdf_bytes`
   directly. The export branch raises `ValueError` if the stored PDF contains
   `b"FALLBACK EXPORT"`. The export ZIP must not contain `ebook.html`,
   `ebook.txt`, or `ebook.pdf`. The PDF inside the ZIP must be byte-identical
   to the directly downloaded PDF.
3. **Math Worksheet challenge behavior is fixed.** `include_challenge` defaults
   to `No`. When `Yes`, the renderer emits a separate "Answer Key — Challenge
   Section" page AND the ZIP's `answer_key.txt` includes a
   `--- Challenge Answers ---` block.
4. **Word Search and Crossword have NO `themed answer` / placeholder content.**
   Real clues, real word lists, real answer keys.
5. **Spelling Worksheet word bank appears only where intended** (typically
   the Word List Practice page), not leaked onto the answer key.
6. **Saved Projects filter remains active** — `isUserSavedProject` (JS) +
   `system_test=true` / `temporary=true` flag in `data` JSON. Customer-path
   tests must use these flags so they don't pollute the user's Saved Projects.

## What is NOT affected by this lock

- **Ebook Generator V1** — `EBOOK_GENERATOR_V1_LOCK.md` and
  `EBOOK_GENERATOR_V1_REGRESSION.json` remain authoritative. The two md5s in
  that file for `app.py` and `app.js` are EXPECTED to differ from this lock;
  that's the whole reason both lock files exist.
- **Budget Planner V1** — `BUDGET_PLANNER_V1_LOCK.md` unchanged.
- **Faith Planner V1** — `FAITH_PLANNER_V1_LOCK.md` unchanged.
- **Bold & Easy Kawaii Coloring Book** — `COLORING_BOOK_GENERATOR_LOCKED_STATE.md` unchanged.
- **Public Factory Menu Cleanup** — `flask_app/PUBLIC_FACTORY_MENU_CLEANUP_LOCK.md` unchanged.
- **Ebook Export Pipeline V2** — 10-check validator, unchanged.
- **Download Pipeline Agent** — unchanged.

## Allowed changes (no re-lock required)

- Adding new product types to the public Factory picker (must follow the
  same customer-path-proof + regression-lock bar).
- Editing copy/labels on the 4 visible product cards.
- Updating the user-facing "not ready" message text in the backend guard for
  hidden product types, as long as the HTTP 400 contract is preserved.
- Editing the spelling_worksheet `_TOPIC_BANKS` to add new topics
  (no structural change to the builder).
- Editing `word_search/word_lists.py` to add new local topic packs
  (no AI behavior change).

## Disallowed changes (require re-lock)

- Re-enabling `chat_json` in `math_worksheet/builder.py` for normal generation.
- Removing the dedicated `math_worksheet` branch in `packaging.py:build_product_export`.
- Weakening the export QA guard (no FALLBACK EXPORT, no ebook files in ZIP,
  ZIP PDF must match direct PDF).
- Changing the default `include_challenge` to `Yes` for Math Worksheet.
- Removing the challenge answer key from the renderer when challenge is on.
- Adding fruit, plant, animal, or unrelated topic words to the Word Search
  computer_parts local pack.
- Adding placeholder / "themed answer" / sample clue text to the Crossword
  builder.
- Adding `ebook.html` / `ebook.txt` / `ebook.pdf` to any puzzle/worksheet ZIP.
- Calling OpenAI or Tavily from `/generate-product` for any of the four
  product types during normal customer use.
- Removing the `system_test=true` / `temporary=true` flag from test projects
  (would pollute user Saved Projects).

---

## Regression fingerprint

See `PUZZLE_GENERATORS_V1_REGRESSION.json` (in this same directory) for:

- All 4 product builder source-file md5s (word_search / crossword /
  math_worksheet / spelling_worksheet)
- `flask_app/services/packaging.py` md5 (export branches)
- `flask_app/services/product.py` md5 (dispatch)
- `flask_app/static/js/app.js` md5 (form fields)
- Generated / downloaded / ZIP-inside PDF md5s and page counts for all 4 products
- ZIP md5s and required / forbidden contents
- Forbidden text patterns: `FALLBACK EXPORT`, `themed answer`, `placeholder`,
  `Failed to fetch`

**Approved post-lock fingerprint refresh** (2026-07-30 12:18 PT): `app.js` md5 was refreshed to `A4CD469CF7CE793CF33C0A892138212C` after the approved Product Planning → Product Builder handoff fix. The previous md5 (`26F6365084CC607919EE48AB2FDF750E`) is preserved in `previous_md5` for traceability. The handoff fix added `resolveFactoryTypeFromPlan` + `hiddenReasonFor` and updated `sendToBuilder` and the Saved Projects row handler; it did not change the puzzle builder code, the math_worksheet include_challenge form field, or the four product type cards.

**Approved post-lock fingerprint refresh** (2026-07-30 18:25 PT): `app.js` md5 was refreshed to `7787B601E149D5C7F841D2C7E3F14348` after the approved Market Research → Factory → Downloadable Product flow upgrade. The previous md5 (`A4CD469CF7CE793CF33C0A892138212C`) is preserved in `previous_md5` for traceability. The flow upgrade added three approved UX changes inside `runProduct` and `renderProduct`: (1) auto-trigger PDF download on Generate success for the workflow case (the `wasWorkflow` branch calls `/export-product` after auto-save and fires `triggerDownload` on the PDF), (2) scroll the post-save Next Steps panel into view via a new `scrollNextStepsPanelIntoView` helper called right after `renderProduct`, and (3) a prominent "Download PDF" button on the product preview card (top-right of the title row) that reuses the same `/export-product` endpoint as the panel button. None of these changes alter the puzzle builder code, the math_worksheet include_challenge form field, the spelling worksheet, the word_search topic pack matcher, the crossword engine, the PDF renderers, the ZIP packaging, the QA agents, or any of the four product type cards.

## Provenance

- Customer-path validation runs: `workspace/_test_puzzles.py` (all 4 products)
  and `workspace/_test_math_final.py` (math challenge on/off).
- PDF fixture downloads: `workspace/puzzle_validation/` (standard tests) and
  `workspace/puzzle_validation_final/` (math challenge on/off).
- All test projects flagged `system_test=true` + `temporary=true` in
  `data.product_exports.meta.package_id` so the Download Pipeline Agent
  can resolve them and the `isUserSavedProject` filter hides them.
- Source backup taken at `C:\Users\user\.mavis\sessions\mvs_9a97078a3fc040fa9def5ae297f5e02a\workspace\Product-Pipeline_BACKUP_2026-07-28_PRE_EBOOK_V1_LOCK.zip`
  (unchanged; not re-taken for this lock since the changes here are
  product-specific to math_worksheet and the new packaging branch).

---

**Current status: PUZZLE GENERATORS V1 LOCKED** 🔒

**Approved post-lock fingerprint refresh** (2026-07-30 19:00 PT): `app.js` md5 was refreshed to `f4e5658f1423086eb3d73d93773b2a15` after the approved **Build Product auto-fire fix**. The previous md5 (`7787b601e149d5c7f841d2c7e3f14348`) is preserved in `previous_md5` for traceability. The change is in `sendToBuilder()`'s ebook branch: after routing to the Ebook Builder view, the code now calls `runEbook()` so the user's one click on "Build Product" / "Send to Product Builder" produces the ebook without requiring a second click on "Generate Ebook". The misleading "click Generate Ebook to use it" toast was replaced with "Building your ebook from the research...". No backend changes, no locked generator behavior change, no PDF/ZIP/cover renderer change. `app.py` md5 unchanged.

**Approved post-lock fingerprint refresh** (2026-07-30 19:45 PT): `app.js` md5 was refreshed to `1bc136c7fad323277989b61a7b773acf` after the approved **Ebook Builder full-flow fix**. The previous md5 (`f4e5658f1423086eb3d73d93773b2a15`) is preserved in `previous_md5` for traceability. The change is in `renderEbook()`:
- Normalizes the data shape (d.content = d.ebook, d.title = d.source, d.product_type = 'ebook', d.fields = {}) so loadEbookEnhancements and the post-save panel can use the same field names the Product Factory path produces.
- Wires a preview-card Download PDF button (top-right of the title row) that reuses the same /export-product endpoint as the post-save panel.
- Auto-calls loadEbookEnhancements so the cover + visual plan render in the Ebook Builder view (previously only the Product Factory path did this; the Ebook Builder view showed only raw markdown with no cover).
- Auto-saves the ebook in place and renders the Post-Save Next Steps panel (Download PDF / ZIP / Open / Selling) when the ebook came in through the sendToBuilder workflow (pendingEbookBrief._project_id). One click on "Build Product" now lands the user on a saved, downloadable, cover-equipped ebook.

No backend changes, no locked generator behavior change, no PDF/ZIP/cover renderer change. `app.py` md5 unchanged.

**Approved post-lock fingerprint refresh** (2026-07-30 20:50 PT): `app.js` md5 was refreshed to `f59629484fb08e3a563a098ce8686da0` after the approved **full-pipeline fix**. The previous md5 (`1bc136c7fad323277989b61a7b773acf`) is preserved in `previous_md5` for traceability. Four approved UX changes that complete the Market Research -> Plan -> Build Product -> Downloadable Product chain:
1. `autoSaveEbookForWorkflow` now auto-fires the PDF download (with ZIP fallback) right after auto-save completes. The user always gets a downloadable file from one click on Build Product.
2. `renderEbook` now shows the Post-Save Next Steps panel directly for already-saved ebooks (skips the Save as Project bar), so reopening a saved ebook from Saved Projects lands the user on the download buttons immediately.
3. `runNextAction` (the Saved Projects 'Build Product' next-action) now auto-fires `runEbook` so a saved plan builds the ebook in one click (no second click on Generate Ebook).
4. `projectRow` now renders a direct 'Download PDF' and 'Download ZIP' button on every Saved Projects row, so the user can download any saved product without opening it first.

No backend changes, no locked generator behavior change, no PDF/ZIP/cover renderer change. `app.py` md5 unchanged.


**Approved post-lock fingerprint refresh** (2026-08-04 08:30 PT): `app.js` md5 refreshed to `e5d8798be79ef4cd8cce7e9a920be165` after fixing three crossword regressions. Previous md5 `f59629484fb08e3a563a098ce8686da0` preserved in `previous_md5` for traceability. Changes:

1. Added `creation_mode` and `custom_words` fields to the crossword factory form (was missing; word search had them).
2. Added `default: "Yes"` to `include_answer_key` field (was defaulting to "No" — answer keys never worked by default).
3. Fixed `services/product.py:_crossword_plan` to check `creation_mode == "Custom word list"` instead of `use_custom_words` field (which was never set by the form).

**Approved post-lock fingerprint refresh** (2026-08-04): `services/product.py` md5 refreshed to `1e8eb8b96a7817f14e0d528bf55fa197` for the `creation_mode` fix. Previous md5 preserved in file.

**Approved post-lock fingerprint refresh** (2026-08-04): Three files updated — this session's crossword export fixes:

1. `app.py` md5: `9c77709860ba9febfaa2fabe6bc2c17b` (previous: `e2e6f8aec9a5b...` — added `data["is_pdf"] = True` when persisting crossword pdf_bytes on generate).
2. `services/packaging.py` md5: `ebb5337a31309afb76b23f5d0d147788` (previous: `7c4b9f...` — added crossword rebuild fallback + ebook fallback hard blocker).
3. `services/product.py` md5: `58f5b2ccfe4d33821c0645768e6f1931` (previous: `b7796cb...` — added `word_placement` + minimum word count guard).

No changes to crossword engine, QA agent, PDF renderer, or any other product type.
