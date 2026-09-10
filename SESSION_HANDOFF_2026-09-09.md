# Session Handoff — 2026-09-09 (supersedes 2026-09-04)

**Start a new session with:** "Read CLAUDE.md and the newest handoff first. Confirm the
current Factory path, current Git branch, current commit, and that the working tree is
clean before making any changes."

---

## Owner's handoff (authoritative, written by the owner on 2026-09-09)

### Current status

The Digital Product Factory is stable and cleaned up. Use this as the only live Factory
checkout: `C:\Users\user\Documents\Product-Pipeline\Factory-v1.3`. Do not go back to old
Desktop or OneDrive working copies unless specifically needed for recovery.

### GitHub

The correct and only live GitHub repository is `laantab/Digital-Product-Factory`. The old
repository `laantab/The-Digital-Product-Factory` has been deleted and confirmed gone. The
live GitHub repository and the local Factory checkout are synchronized. Main is clean and
matches GitHub.

### Today's completed work

- Confirmed one live Factory checkout.
- Confirmed one live GitHub repository.
- Deleted the stale duplicate GitHub repository.
- Retired old scripts that pointed to the stale repository.
- Preserved one OneDrive source snapshot.
- Rescued the branch `onedrive-workspace-phase-a`.
- Updated and pushed the handoff.
- Stability Gate is green. Main branch is clean.

### Do not do these things automatically

- Do not delete any more repositories.
- Do not move the live Factory.
- Do not overwrite the live Factory with an older Desktop or OneDrive copy.
- Do not run old repair scripts unless the current handoff specifically says they are needed.
- Do not merge or delete the rescued branch without reviewing it first.

### Only open decision

Review the rescued GitHub branch `onedrive-workspace-phase-a`. Determine whether it
contains anything useful that should be merged into main. If nothing useful remains,
recommend whether the branch can safely be archived or deleted. Do not merge or delete it
without first explaining what is on the branch and whether it differs from main.

### Next session

Open Claude in `C:\Users\user\Documents\Product-Pipeline\Factory-v1.3`, then: read
CLAUDE.md and the newest handoff first; confirm path, branch, commit, clean tree. Inspect
`onedrive-workspace-phase-a` against main and report: (1) what exists only on the branch,
(2) whether any of it is useful, (3) whether anything should be merged, (4) whether the
branch can be kept, archived, or deleted. Do not merge, delete, move, overwrite, or
generate products yet. Do not call OpenAI, Tavily, or any paid external service. Do not
modify the live Factory until the findings and the smallest safe next step are reported.

### Important Factory goal

The Digital Product Factory is a beginner-friendly, one-click system for creating
high-quality, sellable digital products. The long-term goal remains:

Idea → Market Research → Title → Outline → Manuscript → Visuals → Cover → Design →
Preview → Editor-in-Chief Quality Check → Preflight → Export → Ready-to-Sell PDF + ZIP

The Factory should remain easy for beginners while maintaining professional
Designrr-level quality.

### Preservation rule

Protect the working Factory first. When uncertain: inspect first, back up second, make the
smallest safe change, test it. Do not disturb working features unnecessarily.

---

## Detail (written by Claude, same day)

### Where things stand

- `main` = `origin/main`, tree clean. VERSION `1.5.0`.
- Fast Stability Gate: GREEN (123 passed, 593 subtests) at 2026-09-09 14:00.
- Full Windows release gate: GREEN this morning per the audit session (2,451 tests,
  0 failures, 0 paid calls) after the African Animals fix.
- Source snapshot of this folder plus the Factory Control Center docs:
  `OneDrive\Desktop\Factory_Stabilized_Source_V2_20260809\safety_snapshots\Factory-v1.3_source_2026-09-09`.

### What happened today

1. **Morning audit session** (Sonnet): Universal Topic Vocabulary engine
   (`services/factory/topic_vocabulary.py`, `data/topic_vocabulary_packs.json`) now
   feeds Crossword, Word Search and Spelling Worksheet. Added real Ocean Animals and
   African Animals categories. Fixed Crossword topic contamination and the dropped
   answer key on Single page. Released Spelling Worksheet. Fixed Coloring Book
   local-fallback theme classification. Created the Factory Stability Gate, the
   Golden Customer-Path Smoke Suite, `FACTORY_STABILITY_RULES.md`, and the stability
   matrix in the Factory Control Center.
2. **Afternoon** (Fable): committed the uncommitted v1.5.0 ebook work from Sep 6 to 8
   (`279415a`) and this morning's work (`e81298e`), pushed all waiting commits.
3. **Two checkouts found.** The OneDrive copy had its own unpushed edits from Sep 1 to 3.
   Rescued, untouched, on branch `onedrive-workspace-phase-a` (`19fdd51`, pushed).
   Added `CLAUDE.md` here and a redirect `CLAUDE.md` in the OneDrive folder.
4. **GitHub repo decided.** `laantab/Digital-Product-Factory` is the real one. The
   owner deleted `laantab/The-Digital-Product-Factory` (verified 404). The two scripts
   that pushed to it are renamed `*.RETIRED-2026-09-09` in `Desktop\Factory Backup` and
   `Desktop\Push to GitHub`, with a READ-ME-FIRST.txt beside each.

### What the rescued branch holds (for the review)

Based on `91dfc60` (2026-08-30). 25 files, about 5,970 added lines. Branch-only:
Ebook Project workspace Phase A (Run Research / Approve Title / Draft Outline controls
with seeded research), Factory Market Advantage readiness tagging and single-notice
fix, one-click "Build My Whole Book" (`services/ebook_auto_build.py`), live progress
for long actions (`services/progress_tracker.py`), in-progress projects reachable from
Saved Projects, manuscript panel in plain language, free manuscript recheck and
duplicate-checklist scope fix, the logo on `index.html` and the three standalone builder
pages (untested per its own PROJECT_STATUS.md), and `FACTORY_BLUEPRINT.md` /
`PROJECT_STATUS.md`. Main solved some of the same problems separately on Sep 4
(`77c5dbd` pre-manuscript actions, `26280ed`/`796ae28`/`8ab30d8` one-click builds,
`e909c9c` unfinished ebooks in Saved Projects).

### Still open from earlier handoffs

Rotate Tavily and Pexels keys; real user accounts before live payments; enforce plan
limits in `/generate-product`; make the Cloudflare tunnel a Windows service; sweep
Farm / Rainforest / Arctic Animals topics for the vocabulary gap; restart the 5055
server if it predates this morning's vocabulary edit.

---

## Evening (written by Claude, 2026-09-09)

### Done this evening

1. **Rescued-branch review.** `onedrive-workspace-phase-a` compared against main:
   almost everything on it was re-solved on main between Sep 4 and 9. Two pieces
   were worth porting and were ported by hand, each as its own commit: the
   per-chapter duplicate-checklist fix (`58c7aa1`) and the Factory logo
   (`e9dd93b`, visible on the home page, both builders and the cover editor).
   The branch is untouched and can be archived once the plain-language
   manuscript panel has been considered separately.
2. **Planner design system, v1.6.0.** The Faith Planner engine now renders
   through themes (`services/planner/themes.py`), a component library
   (`components.py`) and a cover-art engine with an image slot (`cover.py`).
   Five faith themes are selectable from the builder form (Design theme,
   Cover style). The Editor-in-Chief gained design checks (page furniture,
   print safety, truncation, cover artwork resolution, theme consistency,
   design richness) and reports a visually weak planner as "needs improvement".
   Tests: `tests/test_planner_design_system.py` (new) and
   `tests/test_planner_products.py` (unchanged behaviour, one expectation
   updated because image resolution is now a real check). Demo outputs:
   `Factory Control Center\Reviews\Planner Design System 2026-09-09\`.

### Still open

- The plain-language manuscript panel from the rescued branch (held by the owner).
- A Pexels picker for the planner cover image slot in the UI. The engine accepts
  `cover_image_path` and `cover_image_source="pexels"` today; the form does not
  yet expose them. No Pexels call was made this session.
- The cover editor page loads the main bundle and logs one harmless console
  error (it expects the home page's research button).
