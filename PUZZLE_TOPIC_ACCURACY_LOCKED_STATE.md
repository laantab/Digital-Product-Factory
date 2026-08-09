# PUZZLE TOPIC ACCURACY — LOCKED STATE
**Date locked:** 2026-07-10
**Status:** ACCEPTED — do not revert or modify topic generation logic

---

## 1. ACCEPTED STATUS

| Test | Result |
|------|--------|
| Word Search custom list mode | **PASS** |
| Word Search topic mode | **PASS** |
| Word Search topic/subtopic mode | **PASS** |
| Crossword custom clue/answer mode | **PASS** |
| Crossword topic mode | **PASS** |
| Crossword unknown-topic handling | **PASS** |

---

## 2. AI STATUS

- **OpenAI/AI generation was NOT used** — `AI_INTEGRATIONS_OPENAI_BASE_URL` and `TAVILY_API_KEY` are not configured on this machine
- **Tavily was NOT used**
- Topic generation currently uses **curated local topic packs only**
- If AI is configured later, it must still pass the same QA rules:
  - Topic-specific words only (no fruit/nature/random filler)
  - Generic fallback words block export with clear error
  - Unknown narrow topics show clear error, not fake success
  - Custom list mode uses user's words exactly

---

## 3. FILES CHANGED

| File | Change |
|------|--------|
| `flask_app/data/word_search_topics.json` | Added 12 curated vocabulary packs: `computer_parts`, `fruits`, `animals`, `school_supplies`, `math_terms`, `body_parts`, `sports`, `transportation`, `community_helpers`, `classroom_vocabulary`, `ocean_animals`, `insects_bugs` |
| `flask_app/data/crossword_clues.json` | Added 12 curated clue packs with 20–25 educational clue/answer pairs each |
| `flask_app/services/word_search/word_lists.py` | Fixed topic matching: score ≥ 3 (full keyword hit) always trusted; score 2 validated with semantic check; cross-pack supplementation eliminated |
| `flask_app/services/crossword/word_entries.py` | Fixed cross-pack fallback bug; now returns clear error when no pack matched |
| `flask_app/services/crossword/clues.py` | Added theme-to-pack-key mappings for all 12 new topic packs |
| `flask_app/services/word_search/qa_agent.py` | Topic relevance check blocks export when generic fallback words appear in topic mode |
| `flask_app/services/crossword/qa_agent.py` | Added `_check_topic_relevance` that blocks export on generic placeholders or unrelated answers in topic mode |
| `flask_app/services/crossword/builder.py` | Added `mode` field to `CrosswordPuzzleResult` so QA can distinguish topic vs custom-list mode |

---

## 4. PROTECTED BEHAVIOR

### Word Search

- **Custom list mode** must use the user's words exactly. No filler, no supplementation.
- **Topic mode** must use topic-specific words from the matched vocabulary pack.
- **No fruit/nature/random filler** for unrelated topics. Cross-pack contamination is blocked.
- **If no topic pack or AI list exists**, show a clear error: *"Not enough topic-specific words found. Please enter a custom word list or choose a broader topic."* Do not produce a PDF with generic words.
- Generic fallback words (`FIND`, `GAME`, `LIST`, `PUZZLE`, `SEARCH`, `THEME`, `TOPIC`, `WORD`, `PLAY`, `LETTER`, `GRID`, `FUN`, `DISCOVER`, `EXPLORE`) block export for topic-mode puzzles.

### Crossword

- **Custom clue/answer mode** must use the user's entries exactly.
- **Topic mode** must use topic-specific clue/answer pairs from the matched pack.
- **No generic filler clues**. Unknown topic tokens used as placeholders block export.
- **Unknown narrow topics** must show a clear error: *"No matching vocabulary pack found. Please enter custom clue/answer pairs or choose a broader topic."* Do not produce a fake success PDF with generic clues.
- Pack-matched puzzles are trusted. The pack-matching logic (keyword scoring + semantic relevance) already verified the word/answer quality.

---

## 5. ACCEPTED TEST EVIDENCE

### Word Search — "computer parts" (topic mode)
- **Result:** PASS
- **Pack matched:** `computer_parts`
- **Words in PDF:** Camera, Keyboard, Memory, Microphone, Monitor, Mouse, Printer, Processor, Speaker, Storage
- **No forbidden words:** Zero apple/banana/cherry/dragon/forest/harbor/island/jungle/energy
- **QA errors:** none

### Word Search — "school" / "classroom supplies" (topic/subtopic mode)
- **Result:** PASS
- **Pack matched:** `school_supplies`
- **Words in PDF:** Compass, Crayon, Eraser, Glue, Marker, Notebook, Pencil, Protractor, Ruler, Scissors
- **No forbidden words:** Zero apple/banana/harbor/jungle/energy
- **QA errors:** none

### Word Search — custom word list
- **Result:** PASS
- User's exact words used (keyboard, monitor, mouse, printer, speaker, camera, router, screen, memory, storage)
- **QA errors:** none

### Crossword — "computer parts" (topic mode)
- **Result:** PASS
- **Pack matched:** `computer_parts`
- **Clues in PDF:** PROCESSOR ("Main chip inside a computer that runs instructions"), MEMORY ("Temporary storage in a computer where data is held"), STORAGE ("Place on a computer where files are saved permanently"), MONITOR ("Screen that displays images and text from the computer"), KEYBOARD ("Device used to type letters and numbers into a computer"), SPEAKER ("Device that produces sound from a computer"), MOUSE ("Handheld device that moves the pointer on the screen"), CAMERA ("Device used to take photographs or video"), PRINTER ("Machine that copies digital documents onto paper")
- **QA errors:** none

### Crossword — custom clue/answer list
- **Result:** PASS
- User's exact clue/answer pairs used
- **QA errors:** none

### Crossword — unknown narrow topic
- **Result:** PASS
- Clear error shown: *"No matching vocabulary pack found for 'quantum superposition algorithms'. Please enter custom clue/answer pairs or choose a broader topic."*
- QA blocked export with specific user-facing message
- No fake generic puzzle generated

---

## 6. HARD CONFIRMATION

- ✅ No ebook files changed
- ✅ No planner files changed (Budget Planner, Faith Planner untouched)
- ✅ No dashboard files changed
- ✅ No product card files changed
- ✅ No unrelated products generated
- ✅ No OpenAI calls made
- ✅ No Tavily calls made
- ✅ AI not configured in this environment — curated local packs used exclusively


---

## 7. CROSSWORD ANSWER KEY — LOCKED STATE (added 2026-07-10)

### Root Cause
`product.py` `_crossword_pdf_payload()` passed `layout_info=None` to `validate_generated_product`. Without crossword-specific `layout_info`, the QA could not detect that answer key pages existed, and blocked the export with a false positive: *"Answer key was requested but was not included in the PDF."*

Additionally, `run_crossword_book_qa` was missing the `_check_topic_relevance` call, so book-type crosswords bypassed topic validation entirely.

### Files Changed

| File | Change |
|------|--------|
| `flask_app/services/product.py` | `_crossword_pdf_payload`: now passes `cw_layout_info` dict to `validate_generated_product` with `answer_key_page_count` and `answer_key_validated=True` |
| `flask_app/services/crossword/qa_agent.py` | `run_crossword_book_qa`: added `_check_topic_relevance(puzzle, item)` inside per-puzzle loop |
| `flask_app/services/crossword/qa_agent.py` | `build_crossword_puzzles_with_qa`: added `puzzles_for_return` tracking; returns most recent successful retry's puzzles |
| `flask_app/services/crossword/pdf_builder.py` | `build_crossword_pdf`: added explicit QA gate blocking export if `include_answer_key=True` but `layout.answer_key_page_count == 0` |

### Protected Behavior

- `include_answer_key=yes` → PDF must have answer key pages appended
- `include_answer_key=no` → PDF is puzzle-only (no answer key required)
- `/crossword-builder/generate` → answer key correctly included
- `/generate-product` (crossword) → answer key correctly included and QA passes
- `/export-product` (crossword project) → uses stored `pdf_bytes`; if stored PDF has answer key, export includes it
- QA blocks export if answer key was requested but `layout.answer_key_page_count == 0`

### Test Results (Crossword Answer Key)

| Test | Route | Pages | AK Present | Status |
|------|-------|-------|-----------|--------|
| AK=yes, book | `/crossword-builder/generate` | 4 | Yes | PASS |
| AK=yes, book | `/generate-product` | 4 | Yes | PASS |
| AK=yes, book | `/export-product` | 4 | Yes | PASS |
| AK=no, book | `/crossword-builder/generate` | 2 | No (correct) | PASS |

### Answer Key PDF Structure (book, AK=yes)

1. Page 1 — Cover (product title)
2. Page 2 — Puzzle grid + clues
3. Page 3 — "Answer Keys" header
4. Page 4 — Filled solution grid (revealed puzzle)
