# Word Search Topic Accuracy — Fix Report
**Date:** 2026-07-10
**Status:** All fixes applied, all tests pass (4/4)

---

## Problem

When generating a Word Search puzzle from a topic (e.g., "Computer Parts"), the word
list was contaminated with unrelated words from other topic packs — e.g., HARBOR,
ISLAND (travel_places), ENERGY (positive_mindset), SNOW, REINDEER (christmas) instead
of computer-specific words like KEYBOARD, MONITOR, MOUSE.

Root cause: `supplement_entries_to_count` iterated ALL topic packs when no pack matched
the user's topic. It pulled the first 8 words from every pack, cross-pollinating
unrelated vocabularies into the puzzle.

---

## Fixes Applied

### 1. `word_lists.py` — Restrict supplementation pool

**`suggest_words_from_topic`** (`word_lists.py:198`)
- Now returns a 4-tuple: `(words, warnings, errors, matched_pack_id)`
- `matched_pack_id` tells callers whether a topic pack was confidently matched
- Added `_semantic_relevance()` check: requires ≥40% of pack words to share ≥4 chars
  with the topic before accepting the pack — prevents "plant_parts" from matching
  "computer parts" via a single shared "parts" token
- Score threshold lowered to `_MIN_SCORE = 2` so common topics with partial keyword
  overlap can still use packs
- Fallback branch no longer prepends generic_fallback words — supplementation is the
  sole responsibility of `supplement_entries_to_count`

**`supplement_entries_to_count`** (`word_lists.py:128`)
- Now accepts `matched_pack_id` parameter
- When a pack IS matched: supplements ONLY from that pack + generic_fallback
- When NO pack matched: supplements ONLY from generic_fallback — never cross-pack
- **Result: zero cross-pack contamination is possible**

### 2. `book.py` — Pass matched_pack_id downstream

**`_collect_entries_from_topic`** → returns 4-tuple including `matched_pack_id`
**`build_word_search_puzzles`** → passes `matched_pack_id` to `supplement_entries_to_count`

### 3. `qa_agent.py` — Topic relevance QA guard

**`_check_topic_relevance`** (`qa_agent.py:87`)
- Checks topic-mode puzzles for generic fallback words (FIND, GAME, LIST, PUZZLE,
  SEARCH, THEME, TOPIC, WORD, PLAY, etc.) and unrelated words (via character overlap)
- Generic fallback words → **WARNING** (not error): guides users to use a custom word
  list for tighter accuracy, but allows export
- Unrelated words from a wrong pack → **ERROR**: blocked export
- `_GENERIC_FALLBACK_WORDS` set covers all words that can appear in any topic pack
  but are not topic-specific (holidays, generic game terms, etc.)

---

## Test Results (4/4 PASS)

| Test | Topic | Result | Notes |
|------|-------|--------|-------|
| 1 | Computer Parts | PASS | No pack → topic tokens + generic warning |
| 2 | Fruits | PASS | No pack → topic tokens + generic warning |
| 3 | Custom word list | PASS | Exact words, no warnings |
| 4 | Quantum Computing Algorithms | PASS | No pack → topic tokens + generic warning |

No test produced cross-pack contamination (apple/banana/dragon/harbor/etc. for
non-matching topics).

---

## What's Working vs. What's a Known Gap

**Working:**
- Cross-pack contamination is eliminated — the supplementation pool is now restricted
- Wrong-pack matches (plant_parts for computer parts) are blocked by semantic relevance check
- Topic tokens (COMPUTER, PARTS) are always used as starter words
- Generic fallback words are used only when no pack matches, and only as last resort
- QA warns when generic words are used, guiding users to custom word lists

**Known gap:**
- The topics data (`data/word_search_topics.json`) has no "computer parts", "fruits",
  "animals", "sports", or other common K-12 topics
- Topic-mode generation for unmatched topics falls back to topic tokens + generic words
- Users who want accurate topic-specific puzzles should use **custom word lists** for now
- The QA warning message guides them to do exactly this

---

## Files Changed

- `flask_app/services/word_search/word_lists.py` — 4-tuple return, semantic relevance,
  restricted supplementation
- `flask_app/services/word_search/book.py` — pass matched_pack_id downstream
- `flask_app/services/word_search/qa_agent.py` — topic relevance QA check with warning
- `flask_app/test_ws_topic_fix.py` — regression test (4 test cases)

---

## No Changes To

- `pdf_builder.py` — PDF title already sourced from product_title
- Generator logic, layout, oval rendering, answer key generation
- Any other product type (Crossword, ebook, planners, dashboard)
