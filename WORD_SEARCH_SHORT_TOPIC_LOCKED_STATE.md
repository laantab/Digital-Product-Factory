# WORD SEARCH SHORT-WORD CRASH — LOCKED STATE

**Date locked:** 2026-09-08
**Status:** ACCEPTED — do not revert or modify without re-running `tests/test_word_search_short_topic_repair.py`.

---

## 1. REPRODUCTION

`build_word_search_puzzles(mode="custom_word_list", custom_words="<8 real words>", number_of_puzzles=2, words_per_puzzle=10, output_type="book")` — 8 words submitted, 20 required, a small enough deficit to trigger the top-up path → `UnboundLocalError: cannot access local variable 'matched_pack_id'`.

## 2. ROOT CAUSE

`services/word_search/book.py`'s `build_word_search_puzzles()` assigned `matched_pack_id` only inside the `elif mode_key == "topic":` branch. The shared top-up block further down (reached by either mode whenever a book's word requirement comes up short) unconditionally reads that name. Custom-word-list mode never bound it.

## 3. FILES CHANGED

| File | Change |
|------|--------|
| `services/word_search/book.py` | Initialize `matched_pack_id = ""` before branching on mode, so both modes reach the shared top-up block with a bound value. |

## 4. INTENDED BEHAVIOR (not invented)

`services.word_search.word_lists.supplement_entries_to_count()` already implements the correct, safe path for "no specific pack matched": skip pack-specific re-fetching, use only the topic-agnostic `generic_fallback` pool, never cross-pollinate with unrelated topic packs. `_collect_entries_from_topic()` itself returns `matched_pack_id=""` in exactly this situation. The fix makes custom-word-list mode take the identical, pre-existing path — no new behavior, no fabricated/duplicate words.

## 5. ACCEPTED TEST RESULTS

| Case | Result |
|------|--------|
| Slightly short custom list (deficit within safe top-up threshold) | Tops up from generic fallback, builds normally, no crash |
| Severely short custom list (deficit too large) | Clean customer-safe error, no crash, no fabricated words |
| Normal topic with enough words | Unaffected |
| Manual/custom word list with plenty of words | Unaffected (top-up path never reached) |
| Save/reopen | `normalize_word_search_project_data` preserves the custom list, no crash |
| External calls | None — `ai_client.chat`/`chat_json` confirmed uncalled |

See `tests/test_word_search_short_topic_repair.py` for the full protected-baseline contract, including a parametrized sweep across deficit sizes proving `UnboundLocalError` can never recur.
