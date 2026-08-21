# Repair Report — 2026-08-21 (follow-up to AUDIT_REPORT_2026-08-21.md)

Every fix below was verified by driving the live app in Chrome and by a full run of the enforced
release gate. **Release gate: 885 passed, 0 failures, 0 errors, 0 skipped, 0 paid API calls.**

---

## 1. Fixed

| # | Problem (audit ref) | Fix |
|---|---|---|
| 1 | `/crossword-builder/` returned 500 — `TemplateNotFound` (§2.1) | Created `templates/crossword_builder.html` + `static/js/crossword_builder.js`, modelled on the working Word Search builder and matching every field the existing `CrosswordPdfRequest` already accepted (incl. custom clues, cover, answers-per-puzzle). Route code needed no change. |
| 2 | Dashboard "Launch Package" card was dead (§2.2) | Card called `launchDashBtn`, an element that never existed. Added `goLaunchPackage()` which routes to Saved Projects with accurate guidance. |
| 3 | Dashboard advertised unbuildable Spelling Worksheet (§2.3) | Removed the tile (grid 6→5 cols). See §3 — the product is genuinely unfinished, so hiding it is correct. |
| 4 | Reopened product rendered ~2 screens below the fold (§2.4) | Added `_focusReopenedProduct()`: hides the leftover blank build form and scrolls the product into view. Also gave `<main>` an id and reset its `scrollTop` on every view change, so navigation no longer lands mid-content. |
| 5 | Publishing Studio / Platform Packages dropdowns polluted (§2.6) | Added `database.list_factory_source_projects()`, reusing the existing customer newest-wins dedupe. **1026 options → 18.** (483 copies of one QA record collapsed to 1.) |
| 6 | Header "Plan: Starter" contradicted pricing page "Free — Current Plan" (§2.5) | Header now reads "Plan: Free", matching the only real state. Checkout itself is still a stub — see §4. |
| 7 | Release gate red (§3) | Installed `requirements-dev.txt` + `playwright install chromium`. 884→**885 passing**. |

## 2. Bugs found during repair that the audit MISSED

These were not in the audit and are more serious than several items that were:

1. **Both standalone builder downloads were completely broken (403).** The audit checked that
   `/word-search-builder/` returned 200 but never clicked Download. Generating a PDF then
   downloading it failed with `stale_or_orphan_export_package` on **both** builders.
   *Cause:* `resolve_download_request()` only read `product_type` from a project row or
   `package_id`. Standalone builders have neither and declare it in `fields`, which was never
   read, so `product_type` stayed `None` and tripped the orphan gate.
   *Fix:* fall back to `fields["product_type"]`, scoped strictly to callers with no project and
   no package_id, so the main `/download/` route keeps its orphan protection intact.

2. **Cover-rule false positive blocked legitimate downloads.** After fixing (1), the crossword
   download still 403'd on `illegal_cover`. The keyword list matched the bare substring
   `"cover"`, so the clue *"precious yellow metal **discover**ed in california"* was read as
   cover text. Any product whose content contains "discover", "recovery", "uncover" etc. could
   be blocked at random.
   *Fix:* added `_has_cover_keyword()` using word-boundary matching, applied to the two checks
   that contained the bare `"cover"` keyword. Both builder downloads now serve valid PDFs
   (verified: crossword 2 pages / 112KB, word search 2 pages / 5.7KB).

3. **Launch Package has no customer-facing entry point at all.** The row-level button is gated
   behind `adminView`; the only real path is inside an opened product under a collapsed
   `<details>` "Optional: marketing & launch tools". The dashboard toast now names that exact
   path rather than a button customers cannot see.

## 3. Audit finding CORRECTED: spelling_worksheet is not "the cheapest win"

The audit (§4) called it "closest to done — needs acceptance tests + unhide". I generated one
before touching it. It produces a PDF, but with **four real content defects**:

- **Topic accuracy failure** — theme "ocean animals" produced `elephant, giraffe, tiger, lion,
  zebra, monkey, rabbit, fox`. Only 2 of 10 words matched the theme.
- **Word bank truncated** — 10 numbered questions but only 8 words in the bank; items 9–10 are
  unanswerable.
- **Answer key silently missing** despite `include_answer_key=Yes`.
- **Title bug + mojibake** — uses the theme instead of `worksheet_title`, rendered as
  "Spelling Practice <?> ocean animals".

Notably, the Word Search builder *refuses* to export on exactly this class of topic mismatch
("Word list contains generic fallback words ... unrelated to topic"), while spelling worksheet
happily ships it. Keeping it hidden is correct; finishing it is a real project, not a quick win.

## 4. Deliberately NOT done (needs your decision)

- **Payments / accounts (§2.5, §4).** Still a stub — "Checkout coming soon!". Implementing
  Stripe vs. stripping the Free/Starter/Pro surface is a business decision, not a bug fix.
- **Data hygiene (§5).** `projects.db` is 1.5 GB / 14,011 rows; `exports/` 6.2 GB. Purging is
  destructive and irreversible — say the word and I'll do it behind a backup.
- **Moving the tree out of OneDrive, rotating the OpenAI key (§5).** Both need you.
- **Archiving ~150 loose `debug_*`/`_swap_*` scripts (§7.8).** Cosmetic; happy to do on request.

## 5. Audit finding WITHDRAWN

**§2.8 "SPA re-fetches `/projects?factory_sources=1` once per second."** There is no polling —
no `setInterval`, no timer. The repeated log lines came from the audit session itself: two
browser surfaces (the preview pane and the Chrome tab) both had the app open while I clicked
through views rapidly. No fix needed, and none made.

## 6. Files changed

```
flask_app/templates/crossword_builder.html          (new)
flask_app/static/js/crossword_builder.js            (new)
flask_app/templates/index.html                      (launch card, spelling tile, plan badge, main id)
flask_app/static/js/app.js                          (goLaunchPackage, _focusReopenedProduct, go() scroll reset)
flask_app/database.py                               (list_factory_source_projects)
flask_app/app.py                                    (factory_sources uses deduped list)
flask_app/services/quality/download_pipeline_agent.py (product_type fallback, word-boundary cover match)
```
