# COLORING BOOK GENERATOR — LOCKED STATE
**Locked:** 2026-07-10
**Status:** LOCKED — DO NOT MODIFY

---

## 1. ACCEPTED BEHAVIOR

| Feature | Status |
|---------|--------|
| Works without AI configured | PASS |
| Single Sheet mode | PASS |
| Digital Book mode | PASS |
| Cartoon art style | PASS |
| Realistic / adult art style | PASS |
| Local procedural line-art fallback (ReportLab vector drawings) | PASS |
| Local procedural cover fallback (ReportLab + fitz PNG) | PASS |
| PDF export | PASS |
| ZIP export (PDF in ZIP) | PASS |

---

## 2. FILES CHANGED

### `flask_app/services/coloring_book/builder.py`
- `chat_json()` wrapped in try/except — AI failure does not crash generator
- Added `_local_page_planner()` — deterministic themed page generation, no AI required
  - Theme types: superhero, fantasy, nature, vehicle, seasonal, generic
  - Age/style aware: kids, teens, adults, cartoon, realistic
  - Superhero detection keywords: volt, hero, power, captain, warrior, guardian, lightning, thunder, storm, superhero, etc.
- Added helpers: `_extract_noun()`, `_seed_from_theme()`, `_get_nature_animals()`, `_get_generic_topics()`, `_build_pages()`
- Added `warnings` list to surface "AI not available" as info, not blocking error
- Added `ai_failed` flag — skips AI vision quality gate when running local-only

### `flask_app/services/coloring_book/renderer.py`
- `_draw_coloring_page()` — calls `_draw_line_art()` instead of placeholder box when no image exists
- `_draw_line_art()` — dispatches to themed ReportLab drawing functions based on topic keywords
- `_draw_superhero()` — hero silhouette with lightning emblem, city skyline, lightning bolts
- `_draw_fantasy()` — dragon (wings/body), castle (towers/battlements), generic fantasy scene
- `_draw_animal()` — cat, bird, fish, flower/botanical, generic animal silhouettes
- `_draw_vehicle()` — car (wheels/windows), plane (fuselage/wings), boat (sail/waves)
- `_draw_mandala()` — geometric rings with petals and radial lines
- `_draw_generic_scene()` — tree, sun, ground line fallback
- `_polygon()` — helper for ReportLab closed polygon paths
- `draw_coloring_book_cover()` — procedural cover using ReportLab + fitz (PyMuPDF)
  - Superhero: circular emblem + lightning bolt + radiating sparks
  - Nature: flower mandala
  - Fantasy: castle silhouette + moon
  - Generic: decorative circular border
  - Renders cover to PNG using fitz (not PIL) for sharp output

### `flask_app/services/coloring_book/pdf_builder.py`
- Added call to `draw_coloring_book_cover()` when no AI-generated cover.png exists
- Falls through gracefully if cover generation fails

### `flask_app/services/coloring_book/quality_agent.py`
- Added `validate_coloring_book_local()` — QA for locally-generated coloring books
- Added `ColoringBookQAResult` dataclass
- Added `_GENERIC_FALLBACK_TOPICS` — generic filler words (apple, banana, dragon, harbor, island, jungle, etc.)
- QA rules:
  - Page count >= requested
  - Digital book has cover image
  - Pages are not blank
  - Pages related to theme (word overlap check)
  - No crossword/ebook/planner field markers in page topics

### `flask_app/services/packaging.py`
- `build_product_export()` — added coloring_book branch
- Returns PDF + HTML + TXT + package.zip
- `pdf_available: True` with proper download URLs

---

## 3. ACCEPTED TESTS

| Test | Input | Result |
|------|-------|--------|
| Thunder Volt Man Single Sheet | Single Sheet, Cartoon, 12-adult, 1 page | PASS — PDF, no AI crash |
| Thunder Volt Man Digital Book | Digital Book, 12 pages, Cartoon, 12-adult | PASS — 13 pages (cover + 12), cover PNG, ZIP |
| Desert Wildlife Adult Realistic | Digital Book, 6 pages, Realistic, Adults, captions | PASS — 7 pages (cover + 6), cover PNG, ZIP |
| AI Unconfigured | AI vars absent | PASS — local fallback used, no RuntimeError |

---

## 4. PROTECTED BEHAVIOR

These behaviors are locked — any change that breaks them is a regression:

1. **AI unavailable is not a blocking error.** Generator must still produce output using local fallback.
2. **No "AI is not configured" error shown to the user.** Falls back gracefully.
3. **No blank pages.** Local planner always generates topic strings.
4. **Digital Book always has a cover.** Local procedural cover used when AI cover is unavailable.
5. **Pages are themed to the title/theme.** Local planner detects theme keywords and generates matching page concepts.
6. **No ebook/puzzle/planner fields in Coloring Book output.** QA rejects topics containing crossword, word search, clue, answer key, budget, expense, chapter, worksheet, planner, calendar, todo, meeting.
7. **ZIP export works for Coloring Book.** PDF is included in the ZIP.
8. **AI mode still works when configured.** chat_json fallback does not remove AI support.

---

## 5. PROTECTED FILES (DO NOT TOUCH)

The following files and directories are protected by this lock and by prior locks:

| Protected file / directory | Lock document |
|--------------------------|--------------|
| `flask_app/services/ebook.py` | — |
| `flask_app/services/ebook_package.py` | — |
| `flask_app/services/ebook/` | — |
| `flask_app/ebook/` | — |
| `flask_app/services/word_search/` | `PUZZLE_TOPIC_ACCURACY_LOCKED_STATE.md` |
| `flask_app/services/crossword/` | `PUZZLE_TOPIC_ACCURACY_LOCKED_STATE.md`, `CROSSWORD_ANSWER_KEY_LOCKED_STATE.md` |
| `flask_app/services/math_worksheet/` | — |
| `flask_app/services/spelling_worksheet/` | — |
| `flask_app/services/planner/` | — |
| `flask_app/templates/` | — |
| `flask_app/static/` | — |
| `flask_app/AI_MODEL_EBOOK_LOCKED_STATE.md` | AI Model Ebook lock |

---

## 6. HARD CONFIRMATION

- no ebook files changed (ebook.py, ebook_package.py, ebook routes — untouched)
- no Word Search files changed (word_search service — untouched)
- no Crossword files changed (crossword service — untouched)
- no planner files changed (planner service — untouched)
- no dashboard changes (templates/, static/ — untouched)
- no OpenAI API calls made (AI env vars confirmed absent)
- no Tavily calls made (not needed for coloring book)

---

## 7. DEPENDENCIES USED

All existing environment dependencies:
- `reportlab` — PDF generation, line-art vector drawing
- `fitz` (PyMuPDF) — cover PDF page to PNG conversion
- `PIL` (Pillow) — image handling in renderer
- No new dependencies added.
