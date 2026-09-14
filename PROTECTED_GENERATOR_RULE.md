# PROTECTED GENERATOR RULE

**Date established:** 2026-09-08. **Extended 2026-09-12** to enroll every major
customer-facing function, not just Crossword, and to back this rule with a
machine-checked registry instead of documentation alone — see
`command_center/function_lock_registry.json`, `tests/test_function_lock_registry_integrity.py`,
and `tests/test_function_lock_enforcement.py`. That registry, not this file, is now
the authoritative source for each function's current status and last-known-good
commit; this file records the workflow and the reasoning, the registry records the
current facts.

**Status:** STANDING FACTORY POLICY — applies to every product generator once it has a protected-baseline contract (a `*_LOCKED_STATE.md` file and/or a dedicated `test_*_protected_baseline*.py` / equivalent regression suite pinning its customer-facing behavior).

## Why this was extended (2026-09-12)

A read-only audit found that `*_LOCKED_STATE.md` files existed for Coloring Book
(seven of them), Ebook, Word Search, and others, each reading exactly like a real
lock — but none of them were ever enrolled in this rule, none were re-verified by an
automated test after the day they were written, and one of Coloring Book's directly
claimed the exact behavior ("no header/footer/page number when captions = No") that
regressed and shipped to a live customer two months later. The manual test behind
that claim used a theme ("Farm House") that happened to avoid the one illustration
branch with the actual defect. A markdown file said "locked"; nothing machine-checked
it. See `SESSION_HANDOFF_2026-09-11.md` and the Coloring Book v1.7.3 fix (`984b268`)
for the full incident.

## Functions now enrolled under this rule

Status, last-known-good commit, and protected test files for each function below are
tracked in `command_center/function_lock_registry.json` — read that file for current
truth, not the table below, which is a plain-language summary as of 2026-09-12:

| Function | Status | Last-known-good |
|---|---|---|
| **Word Search** | LOCKED | `a021385` (v1.7.2) |
| **Coloring Book** | LOCKED | `984b268` (v1.7.3) |
| **Crossword** | LOCKED | `e81298e` (v1.5.0) |
| **Invite protection** | LOCKED | `0a9a713` (v1.7.1) |
| Factory Market Advantage | PROTECTED | unknown — has real tests, no Fast Gate coverage, and the 2026-09-11 Render-config incident was invisible to every existing test |
| Ebook | PROTECTED | unknown — largest test family in the Factory, but only 1–2 files run in the Fast Gate |
| Math Worksheet | PROTECTED | unknown — Full Gate only |
| Faith Planner | PROTECTED | unknown — Full Gate only, shares `services/planner/` with Budget Planner |
| Budget Planner | PROTECTED | unknown — Full Gate only, shares `services/planner/` with Faith Planner |
| Saved Projects | PROTECTED | unknown — has real code-level enforcement (`services/quality/artifact_state.py`), not merely tests |
| PDF/ZIP export | PROTECTED | unknown — highest-blast-radius shared file in the Factory |

A status of PROTECTED, not LOCKED, is deliberate: real test coverage exists for each
of these, but no specific commit has been proven as its customer-path last-known-good,
so none is claimed here — see Rule 9 below.

## The rule

Once a product generator has a protected-baseline contract:

1. Unrelated work must not change its customer-facing controls.
2. Normalization must not silently replace a valid customer choice.
3. Save/reopen must preserve those choices.
4. Generation must honor those choices.
5. Rendering and packaging must agree with those choices.
6. Its protected regression suite must remain green.
7. A shared-code change that affects it requires **before/after protected-suite proof** — run the protected suite before touching the shared function, and again after, and both runs must show identical pass results for every protected behavior.
8. No test may be weakened merely to accommodate a regression. If a protected suite fails after a change, the change is wrong, not the test.
9. Never manufacture a last-known-good commit. If it isn't proven, the registry says `null` (unknown), never a guessed hash — a false LKG is worse than an honest "unknown."
10. **A LOCKED function may not be changed, directly or through a shared dependency, without going through the workflow below.** This is now checked by a real test (`tests/test_function_lock_enforcement.py`), not only by this document.

## The unlock → change → protected tests → relock workflow

1. **Unlock.** In `command_center/function_lock_registry.json`, set the function's
   `status` to `"UNLOCKED"`, and fill in `unlocked_by` (who) and `unlocked_reason`
   (why — one sentence is enough, but it must be real). Leave `relocked_by` /
   `relocked_after_tests` as `null` — they belong to the *next* lock, not this one.
2. **Change.** Make the smallest safe edit. `tests/test_function_lock_enforcement.py`
   will not block an UNLOCKED function's own files or declared shared dependencies —
   but it still blocks every *other* LOCKED function's files, including shared ones.
3. **Protected tests.** Run every file the function lists under `protected_test_files`
   in `function_lock_registry.json`, and — if the change touched a shared dependency —
   every *other* function that also lists that same file (this is exactly what
   `tests/test_function_lock_enforcement.py` prints when it fires: which locked
   functions share the file you touched).
4. **Relock.** Set `status` back to `"LOCKED"`, update `last_known_good_commit` to the
   real commit hash the change was verified at, set `factory_version` if one applies,
   fill in `relocked_by` and `relocked_after_tests` (which protected suites you ran and
   that they passed), and clear `unlocked_by` / `unlocked_reason` back to `null`.
   `tests/test_function_lock_registry_integrity.py` enforces that this metadata is
   internally consistent — it fails on a LOCKED function still carrying an open
   unlock reason, an UNLOCKED function with no reason, or a LOCKED function with no
   `last_known_good_commit`.

## How to apply it

For every production function you are about to change, ask: **"What other generators call this?"**

- If the answer includes a protected generator, either:
  - **(A)** avoid changing the shared function — prefer a product-specific fix inside the generator that actually has the defect (see `services/product.py`'s `crossword_include_cover_choice()` for the pattern: a small, product-owned helper that mirrors an already-correct sibling's logic instead of editing the shared planner every generator uses), or
  - **(B)** if a shared change is truly unavoidable, prove — with the protected generator's own regression suite, run before and after — that every one of its protected behaviors is bit-for-bit unchanged.
- Prefer localized, product-specific fixes over broad "cleanup" refactors.
- Do not make speculative improvements while repairing an unrelated defect.

## Enforcement

Each protected generator's regression suite is expected to include a permanent "protected baseline contract" test class whose assertions check *actual resolved generation and packaging behavior* (real PDFs, real page counts, real save/reopen functions) — never only HTML/JS source strings. Any change to Factory code should leave every protected generator's contract suite green; a red protected suite blocks the change, not the other way around.

**Two machine-checked layers, added 2026-09-12, back this document instead of leaving it as a policy nobody re-verifies:**

- **`tests/test_function_lock_registry_integrity.py`** — checks the registry itself:
  every LOCKED function has a real `last_known_good_commit` that actually exists in
  git history, at least one protected test file that exists on disk *and* is
  registered in `tests/acceptance_manifest.json`, and consistent unlock/relock
  metadata. This is what stops a `*_LOCKED_STATE.md`-style claim from ever being
  accepted again without something real behind it.
- **`tests/test_function_lock_enforcement.py`** — for every file a LOCKED function
  depends on, diffs from a durable baseline (the most recent `last_known_good_commit`
  among every LOCKED function that shares that file) against the current working
  tree. If a changed file belongs to a LOCKED function's own files or one of its
  declared shared dependencies, the check fails and names every locked function
  affected — unless that function's registry entry says `"UNLOCKED"`. Because the
  baseline is a historical commit, not `HEAD`, this catches the change whether it is
  still uncommitted, already committed locally, evaluated by a clean-tree Fast/Full
  Gate run, or evaluated by CI/GitHub against the pushed tree — not only while it is
  sitting uncommitted in the working tree.

Both run in the Fast Stability Gate and the Full Release Gate — see `CLAUDE.md`.

## Global Cover Policy — declared final-QA authority per product (2026-09-12)

The global rule: **no final cover may reach the customer without passing its
declared final QA authority.** Not every product is required to call the same
`services/cover_quality_agent.py` function — a product with an equivalent,
product-specific final-cover QA system that genuinely evaluates the real
rendered artifact may use that instead. A 2026-09-12 audit traced every cover
path to find and pin down which authority actually applies:

| Product | Cover path | Declared final QA authority | Evaluates the actual rendered artifact? | Blocks/gates delivery? |
|---|---|---|---|---|
| Ebook | Primary guided flow (`services/ebook_photo_cover.py`, `/ebook-workspace/*`) | `inspect_variant` (raster typography QA) + `_first_passing_layout` (`services/ebook_customer_path.py`) | Yes — measures the actual composited PIL image written to disk per candidate layout | Yes — `_first_passing_layout` returns `""` (blocking, `PhotoCoverError`/`NO_SAFE_COVER_MESSAGE`) unless a variant both reports `quality.pass=True` *and* has a real file on disk |
| Ebook | Older Cover Editor route (`/cover/*`) | `services/cover_quality_agent.py::evaluate_cover_quality` | Yes — checks the rendered `preview_html`/`pdf_html` | Yes — `ensure_professional_cover` retries/corrects, attaches `cover_quality` |
| Word Search | `_build_word_search_cover` + Cover Editor | `evaluate_cover_quality` (via `ensure_professional_cover`) | Yes | Yes |
| Crossword | `_build_crossword_cover` + Cover Editor | `evaluate_cover_quality` (via `ensure_professional_cover`, called unconditionally by `generate_cover_from_payload` regardless of `use_ai_image`) | Yes | Yes |
| Coloring Book | Automatic build (`_coloring_book_pdf_payload`) | `services/coloring_book/final_cover_qa.py::validate_coloring_book_final_cover` (new 2026-09-12; a small adapter, not `evaluate_cover_quality`, because Coloring Book's cover renders PDF-native with no `preview_html`/`pdf_html` to check) | Yes — reads title/subtitle back out of the actual rendered PDF page via `pypdf` | Yes — raises `RuntimeError` on any error-level finding (missing title, placeholder/gibberish/template wording, malformed characters, unrecognized `cover_source`); a title-not-found-in-extracted-text signal is a warning only, to avoid false positives from PDF text-extraction quirks on an otherwise-correct render |
| Coloring Book | Cover Editor route (`/cover/*`) | `evaluate_cover_quality` (via `_adapt_coloring_book`) | Yes | Yes |
| Faith Planner | `/export-product` | `services/editor_in_chief_planner.py::review_planner` (which calls `services/planner/design_rating.py::rate_planner_design` for the cover-specific checks: title size/hierarchy, font pairing, DPI, and *measured pixel contrast* of the title against its background) | Yes — `review_planner` explicitly reviews "the PDF the customer will actually receive," rendering real page images and measuring real pixel luminance under the title | Yes, via `overall` score vs. `MIN_OVERALL=9` (not via individual `Finding.blocks()`, since every cover-rating deduction is `severity=minor` by design — an intentional choice like a painted, non-photographic cover must never single-handedly block release). `data["export_ready"] = bool(eic_ok)` in `app.py`'s `/export-product` handler is the actual gate a customer's download depends on. |
| Budget Planner | `/export-product` | Same as Faith Planner | Yes | Yes |

Two things this audit found and corrected:

1. **Coloring Book's automatic build had no final-QA authority at all** before
   2026-09-12 — a real gap, now closed by the adapter above.
2. **Coloring Book and Crossword's initial/automatic build paths do not
   themselves call the paid AI cover call automatically** (Crossword
   deliberately, via `use_ai_image=False`; Coloring Book depending on
   `generation_stage`) — this is pre-existing, intentional cost-avoidance
   behavior, not a QA gap; the declared authority above still runs against
   whatever the build actually produced (a template/procedural cover
   included).

Ebook's primary guided flow and both Planners were reviewed and found to have
a genuine, real-artifact-evaluating, delivery-gating final QA system already
in place — they are **not** routed through `evaluate_cover_quality`, by
design, and this table is the record of that decision so it is never
mistaken for an unreviewed gap later.
