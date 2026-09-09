# PROTECTED GENERATOR RULE

**Date established:** 2026-09-08
**Status:** STANDING FACTORY POLICY — applies to every product generator once it has a protected-baseline contract (a `*_LOCKED_STATE.md` file and/or a dedicated `test_*_protected_baseline*.py` / equivalent regression suite pinning its customer-facing behavior).

Generators currently under this rule: **Crossword** (see `CROSSWORD_GENERATOR_LOCKED_STATE.md`, `tests/test_crossword_customer_options_restored.py`, `tests/test_crossword_cover_selection_repair.py`).

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

## How to apply it

For every production function you are about to change, ask: **"What other generators call this?"**

- If the answer includes a protected generator, either:
  - **(A)** avoid changing the shared function — prefer a product-specific fix inside the generator that actually has the defect (see `services/product.py`'s `crossword_include_cover_choice()` for the pattern: a small, product-owned helper that mirrors an already-correct sibling's logic instead of editing the shared planner every generator uses), or
  - **(B)** if a shared change is truly unavoidable, prove — with the protected generator's own regression suite, run before and after — that every one of its protected behaviors is bit-for-bit unchanged.
- Prefer localized, product-specific fixes over broad "cleanup" refactors.
- Do not make speculative improvements while repairing an unrelated defect.

## Enforcement

Each protected generator's regression suite is expected to include a permanent "protected baseline contract" test class whose assertions check *actual resolved generation and packaging behavior* (real PDFs, real page counts, real save/reopen functions) — never only HTML/JS source strings. Any change to Factory code should leave every protected generator's contract suite green; a red protected suite blocks the change, not the other way around.
