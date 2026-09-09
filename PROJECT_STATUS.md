# PROJECT_STATUS.md — Digital Product Factory

Single source of truth for where the project stands. Updated after every
meaningful completed task. **Read before changing anything.** Last updated:
2026-09-03 (logo extended to the three standalone builder pages — UNTESTED and
UNVERIFIED, like the 2026-09-02 index.html edit it builds on; see the first two
entries under "Completed work").

---

## Current objective

Maintain and stabilize the Digital Product Factory Flask app so customers can go
from idea → researched plan → built product → reviewed → exportable (PDF + ZIP)
for every sellable product type, with all gates holding. **Phase A of the launch
blocker is implemented and green**: fresh Ebook Project workspaces can now
advance from Research in the UI (seeded research + Run Research / Approve
Research / Save Title / Approve Title / Generate Draft Outline / Approve Outline
controls), unblocking the already-working Generate Manuscript path.
**On top of Phase A, the Factory Market Advantage repeated-warning defect is now
corrected** (research page no longer stacks large red "product type is not ready"
warnings). Both are awaiting Lonnie's browser verification; Phase B has not
started.

## Completed work (verified)

- **2026-09-03 — Logo extended to the three standalone builder pages.
  CODE CHANGE ONLY — NOT TESTED, NOT VERIFIED IN A BROWSER, NOT APPROVED.**
  Lonnie chose this (item 0c below) as the next step. Three edits, one per
  template, nothing else touched:
  1. **`templates/crossword_builder.html` (header, ~line 18)** — the text-only
     eyebrow `<p>Digital Product Factory</p>` replaced by the logo:
     `url_for('static', filename='images/branding/digital_product_factory_logo.png')`,
     `alt="Digital Product Factory"`,
     `class="h-8 w-auto max-w-[11rem] object-contain mb-1"`. The `<h1>Crossword
     Builder</h1>` beneath it is unchanged. No white card here — this header is
     already `bg-white`, unlike the dark sidebar in `index.html`.
  2. **`templates/word_search_builder.html` (header, ~line 18)** — identical
     change; `<h1>Word Search Builder</h1>` unchanged.
  3. **`templates/cover_editor.html` (`.editor-header`, ~line 396)** — logo
     inserted between the "← Back to Factory" button and `<h1>Cover Editor</h1>`.
     This file uses plain CSS, not Tailwind, so the sizing is an inline style
     (`height:1.75rem;width:auto;max-width:11rem;object-fit:contain;
     flex-shrink:0`) rather than utility classes, and no rule was added to the
     page's stylesheet.
  - **Status-file correction:** item 0c described all three pages as having a
    text-only "Digital Product Factory" eyebrow. Only the two builder pages did.
    `cover_editor.html` had **no** brand mark at all, so this change *adds*
    branding there rather than replacing text. Worth an extra look.
  - Aspect ratio preserved everywhere (`object-contain` / `object-fit:contain`
    with `w-auto`). No paid or external service was called. No new files.
  - **NO TESTS WERE RUN.** The sandboxed Linux shell failed to start this
    session (`HYPERVISOR_VIRT_DISABLED`), so neither `preflight_check.py` nor
    any focused test was executed. `git status` was likewise not inspected
    (`CLAUDE.md` step 2) — no shell. The preflight gate has NOT been re-run
    since either logo edit. Treat both as unproven.
  - **Checked by reading, not running:** no test in `tests/` asserts on these
    templates' header markup. The `Digital Product Factory` matches in the test
    suite are about generated product content and cover brand-leak detection
    (`test_cover_regression.py`, `test_ebook_customer_path.py`,
    `test_coloring_book_*`), not template HTML. Per blueprint §15, this is code
    inspection and is not a substitute for the gate.
  - **NOT seen in a browser.** Nothing rendered was looked at by anyone.

- **2026-09-02 (evening) — Logo added to the UI. CODE CHANGE ONLY —
  NOT TESTED, NOT VERIFIED IN A BROWSER, NOT APPROVED.**
  Lonnie asked for the "Digital Product Factory" logo to be placed in the main
  header/sidebar. Two edits to `templates/index.html`, nothing else touched:
  1. **Sidebar (lines ~65-73)** — replaced the placeholder "DP" square and the
     "Digital Product / FACTORY" text with the real logo, served via
     `url_for('static', filename='images/branding/digital_product_factory_logo.png')`,
     `alt="Digital Product Factory"`, `class="block w-full h-auto"`, sitting on a
     white rounded card (`rounded-xl bg-white px-3 py-1 shadow-sm`) because the
     PNG has a white background and the sidebar is dark (`bg-brand-950`). The
     card also absorbs the logo's built-in vertical whitespace.
  2. **Top header (lines ~84-88)** — added a `md:hidden` copy
     (`h-10 w-auto max-w-[9rem] object-contain`) so branding survives below the
     `md` breakpoint, where the sidebar is hidden.
  No stretching or cropping; `w-full h-auto` / `object-contain` preserve the
  aspect ratio. No paid or external service was called.
  - **The logo file already existed** at
    `static/images/branding/digital_product_factory_logo.png` and is the same
    artwork Lonnie uploaded. Nothing was copied, replaced, or regenerated.
  - **NO TESTS WERE RUN.** The sandboxed shell was denied for the whole session,
    so neither `preflight_check.py` nor any focused test was executed. The
    preflight gate has NOT been re-run since this edit. Treat the change as
    unproven until it is.
  - **NOT seen in a browser.** The Factory was never successfully started this
    session and the rendered result has not been looked at by anyone.
  - **Process failure to note:** this edit was made *before* reading
    `PROJECT_STATUS.md`, contrary to `CLAUDE.md` steps 0-1. The direct
    consequence appears below (duplicate launcher).

- **2026-09-02 (evening) — Redundant launcher created in error; awaiting
  Lonnie's decision to delete.**
  `flask_app/Start_Factory_5055.bat` was created to start the Factory, without
  first checking `PROJECT_STATUS.md`, which already records
  `C:\Users\user\OneDrive\Desktop\START_DIGITAL_PRODUCT_FACTORY_WORK.bat` as the
  single unified one-click launcher (2026-08-31), with older launchers
  deliberately archived to `OLD_FACTORY_LAUNCHERS_DO_NOT_USE\`. The new `.bat`
  is additive and touches no existing file, but it competes with a launcher
  setup that was intentionally consolidated. **It should almost certainly be
  deleted.** Not deleted — deletion needs Lonnie's approval (`CLAUDE.md` rule 7).

- **2026-09-02 — An unfinished book had no route back to it; fixed
  (full gate green).**
  Lonnie asked "how do i get to zero-waste project" — and there was no answer.
  Saved Projects lists only completed products with usable output
  (`is_customer_saved_product` requires `_customer_status_allows_saved_list`
  and `_has_usable_customer_output`), which is right for a shelf of finished
  work. The consequence was that an Ebook Project that had been started, saved
  and **already paid for**, but left at "needs correction", appeared **nowhere
  in the interface**. `/projects?limit=12` returned four unrelated products and
  none of his three most recent books. This breaks blueprint §10 ("Reopening
  restores the actual saved product") and §3 ("Where am I?").
  - `database.list_in_progress_workspaces()` — query-time view of Ebook
    Projects that have a workspace and are not finished. Returns a small menu
    row only (id, name, stage, next action, steps done/total); never the stored
    manuscript. Deletes, mutates and reclassifies nothing.
  - `app.py`: `GET /projects/in-progress`.
  - `templates/index.html` + `static/js/app.js`: a **"Still working on these"**
    section above the now-labelled **"Finished products"** shelf, each row
    showing progress ("3 of 10 steps done · next: Fix one chapter") with a
    **Continue** button that reopens the workspace. Hidden entirely when
    nothing is in progress.
  - The finished shelf is unchanged — a test asserts a half-written book does
    **not** start appearing there.
  - Verified live: 12 in-progress books listed, the Zero-Waste project first,
    each with a working Continue button.
  - Tests: new `tests/test_in_progress_projects_reachable.py` (13 tests) in the
    manifest (now 86 files).
  - **Full preflight release gate: PASS.** `1408` total, `0` failures, `0`
    errors, `0` skipped, `0` paid API calls permitted.

- **2026-09-02 — The real reason a build never finished, fixed; and the
  confirmation step removed (full gate green).**
  Lonnie: "I had to click 5 times, and the project still didn't build. Take out
  the paid authorization part so the build goes through."
  - **Diagnosis from project 21318's own record — the checkbox was not the
    problem.** The server log shows he never reached `run-full-build` at all;
    he used the step-by-step buttons. The book stopped because
    `run_chapter_pipeline` runs with `stop_on_failure=True`: chapter 1 passed,
    chapter 2 failed, and `skipped_ungenerated: [3,4,5,6,7,8]` — six chapters
    were never written. Correction then retried **only** chapter 2, failed the
    same way and stopped again, so the book could never complete while each
    attempt charged $0.15. Ledger: $0.45 over 3 calls for a 2-chapter book.
  - **Fix 1 (the dead end).** `execute_generate_manuscript` and
    `execute_correct_manuscript` take `complete_all_chapters` (default
    `False`, so the step-by-step path and its cost guard are unchanged). The
    one-click build passes `True`: every chapter is written first, then the
    weak ones are corrected. Regression test replays the exact failure
    (chapter 2 misaligned, others fine) and asserts chapters after it are still
    written.
  - **Fix 2 (chapter purposes).** `_chapter_purpose()` opened with editorial
    meta-language and appended the topic, so *reader/background/framing* filled
    the twelve-word window `validate_chapter` uses for purpose alignment while
    the subject fell outside it. Purposes now lead with topic and audience.
    Measured on the live chapter: margin moved from exactly-at-threshold
    (3 hits, 3 needed) to 4 hits. **Robustness, not the proven root cause** —
    Fix 1 is what unblocks the build.
  - **Fix 3 (chapter counting).** `plan_full_build` priced the manuscript from
    `len(outline_options)` — the number of outline *options*, not chapters — so
    an 8-chapter book could be priced as one. Now counts the approved outline.
  - **Fix 4 (dangling phrases).** `_title_phrase` could cut mid-phrase, giving
    the live outline a chapter titled "The Core Method: Practical ways to
    reduce waste **in**". A trailing function-word trim removes it.
  - **Authorization step removed, as asked.** No confirmation dialog and no
    checkbox: pressing **Build My Whole Book** is the go-ahead. The cost line
    is shown on the card *before* the click, and the ceiling is now recomputed
    **server-side** from `plan_full_build`, so the browser cannot raise it and
    the project's budget cap still binds.
  - Verified live on 21318: button reads "Build My Whole Book", 0 authorization
    checkboxes on the page, cost line reads "Costs at most $0.75 of your own AI
    credit — images, cover, layout, preview and checks are free." Nothing run
    or spent.
  - Also fixed: the Factory had stopped serving because the background process
    I launch does not survive its launching session. It now writes
    `logs/factory_5055.log` / `.err.log` so a death leaves evidence.
  - **Full preflight release gate: PASS.** `1389` total, `0` failures, `0`
    errors, `0` skipped, `0` paid API calls permitted.

- **2026-09-01 — One-click "Build My Whole Book" (full gate green).**
  Lonnie: "I don't think the user should have to keep clicking a dam button to
  complete a project... we should be able to do this with one click."
  - `services/ebook_auto_build.py` (new): `plan_full_build()` (free; totals the
    remaining paid steps, clamped to the remaining budget) and
    `run_full_build()` (walks Research → Title → Outline → Manuscript →
    Visuals → Cover → Design → Preview → Preflight from ONE authorization).
  - **It automates the clicking, never the gates.** Every stage still goes
    through the same executor and the same `approve_stage`, so a stage whose
    quality gate refuses stops the run, keeps the work, and reports why in
    plain words — nothing weak is ever auto-approved (§7). Spending is
    authorized once with a stated maximum and still charged through the
    existing per-project ledger and cap (§13); the run stops rather than
    exceeding it. Already-approved stages are skipped, never rebuilt (§10).
    Auto-correction is bounded at one attempt (`MAX_AUTO_CORRECTIONS`), so it
    can never sit in a paid retry loop.
  - `app.py`: `POST /ebook-workspace/<id>/estimate-full-build` and
    `/run-full-build`; `_auto_build_stage_functions()` supplies the same free
    stage steps the individual buttons call, so the one-click path cannot drift
    from the step-by-step path.
  - `static/js/app.js`: one "Build My Whole Book…" card at the top of the
    workspace with a single cost estimate, one authorization checkbox (confirm
    stays disabled until ticked) and the live progress bar. The step-by-step
    controls remain, now under "Or step by step:".
  - **Bug found and fixed while testing:** all 26 workspace routes did
    `return err[0], err[1]` where `err[0]` was already a `(response, status)`
    pair — so *any* missing or non-ebook project id returned **500** instead of
    a clean 404/400. Now `return err[0]`; verified 404 with "Project not found."
  - Tests: new `tests/test_one_click_full_build.py` (20 tests, 19 subtests) in
    the manifest (now 85 files). The happy path runs the **real, unpatched**
    quality/fidelity/content gates using the repo's own
    `build_event_photo_strong_manuscript()` fixture and asserts every stage is
    genuinely approved; separate tests assert a failing gate stops the run and
    that zero authorization cannot reach a paid step.
  - Verified live on project 21314: the free estimate returns 6 remaining
    steps, max **$0.30** (only "Writing your chapters" is paid; images, cover,
    layout, preview and checks are $0). Nothing was run or spent.
  - **Full preflight release gate: PASS.** `1381` total, `0` failures, `0`
    errors, `0` skipped, `0` paid API calls permitted.

- **2026-09-01 — Manuscript stage rewritten in plain language (full gate green).**
  Lonnie: "I don't think the user needs to see all of this information, I didn't
  see anything like this in the Designr app... Let's not scare off the user."
  The panel had been opening with a per-chapter PASS/NEEDS_CORRECTION list with
  word counts, a raw engine code (`PURPOSE_MISALIGN — Chapter body does not
  cover the approved purpose for this title`), a monospace dump of the raw
  markdown, and two competing action boxes (one free, one paid). This is
  already what FACTORY_BLUEPRINT.md §3 forbids.
  - `static/js/app.js`: extracted `manuscriptStagePanelHtml()`;
    `MANUSCRIPT_FINDING_PLAIN` translates ~19 engine codes into plain sentences
    (unmapped codes fall back to the engine's own message, never to silence);
    `plainManuscriptIssues()` names the chapter and the problem
    ("Chapter 7 — Tools, Templates, and Checklists You Can Use: this chapter
    drifts from what its title promises"). Default view = one plain headline,
    the issue in plain words, one primary action. The draft is now a *rendered*
    collapsed "Read your draft"; the chapter list, word counts, quality verdict
    and raw codes moved intact into a collapsed "Technical details". Nothing
    was deleted.
  - One obvious next action: primary **Fix This For Me…** with the free
    re-check demoted to a quiet "Check again first (free)" link; cost and
    remaining budget stated in one line. The top ribbon now shows the same
    single action instead of two competing buttons.
  - `services/ebook_project_workspace.py`: `CUSTOMER_ACTION_LABELS` gives the
    ribbon plain wording ("Write your chapters", "Fix one chapter") while the
    internal `next_action` names are unchanged.
  - Verified in a real browser on live project 21314: ribbon reads "Fix one
    chapter", panel reads "Your draft is written and saved — 6 of 7 chapters
    are ready. One thing needs a small fix before you approve it.", both
    disclosures closed by default. No paid call; project not modified.
  - Tests: new `tests/test_manuscript_panel_plain_language.py` (13 tests) in
    the manifest (now 84 files), pinning both the calm default view *and* that
    the technical evidence is still present one disclosure away. Two older
    tests were updated to the new intended wording (a spending ceiling is still
    asserted in the confirm dialog; the label assertion is still an exact
    equality) — no test was weakened.
  - **Full preflight release gate: PASS.** `1342` total, `0` failures, `0`
    errors, `0` skipped, `0` paid API calls permitted.

- **2026-09-01 — Live progress for long paid actions (full gate green).**
  Lonnie asked for "a progress bar, or a spinning star to let the user know the
  app is not stuck". Generating an 8-chapter manuscript is one HTTP request
  making eight sequential provider calls over several minutes; the page showed
  only a busy button, which is indistinguishable from a hung app — on a paid
  action, where the instinct is to click again.
  - `services/progress_tracker.py` (new): process-local, thread-safe,
    self-pruning (300s retention, 200-job cap) progress registry. Every public
    call swallows its own errors so reporting can never break the work it
    reports on. Never persisted, never a source of truth.
  - `services/ebook_manuscript_engine.py`: `run_chapter_pipeline` takes an
    optional `on_progress` callback and emits `chapter_start` / `chapter_done`
    per chapter, guarded so a failing callback cannot stop generation. `done`
    counts *finished* chapters, so the bar never claims a chapter is complete
    while its provider call is still running.
  - `services/ebook_project_workspace.py`: `chapter_progress_reporter()` maps
    pipeline events to readable labels ("Writing chapter 3 of 8 — <title>");
    `execute_generate_manuscript` / `execute_correct_manuscript` take an
    optional `progress_key` (absent = unchanged behaviour).
  - `app.py`: `GET /ebook-workspace/<id>/progress` (read-only, no DB, no
    provider); generate/correct routes start and finish the job, including on
    the error path.
  - `static/js/app.js`: `startWorkspaceProgress()` renders a spinner, a real
    progress bar, the current chapter and elapsed mm:ss, polling every 1.5s.
    Before the first chapter lands the bar creeps to 60% so it never looks
    frozen; polling failures are swallowed rather than shown. Wired into all
    three long actions — manuscript, correction and research — and always
    stopped on both success and failure.
  - Verified in a real browser (no paid call): the fallback bar moved 8%→14%
    with the clock at 0:04, and the determinate path rendered "Writing chapter
    3 of 8" at 25% then "chapter 6 of 8" at 63%.
  - Tests: new `tests/test_long_action_progress.py` (20 tests) in the manifest
    (now 83 files), including thread-safety under 5 concurrent writers, a
    failing callback not breaking generation, and the progress payload
    containing no spend/ledger fields.
  - **Full preflight release gate: PASS.** `1317` total, `0` failures, `0`
    errors, `0` skipped, `0` paid API calls permitted.

- **2026-09-01 — A paid manuscript was being stranded by a false-positive
  quality finding; fixed, plus a free way to recover (full gate green).**
  Reported live from project 21312 ("Budget Meal Prep for Nurses"): Lonnie
  confirmed Generate Manuscript, **$1.20 of provider spend across 8 chapter
  calls produced a complete 11,197-word, 8-chapter manuscript with every
  chapter graded PASS** by the quality engine (`quality_ok: true`,
  `outline_ok: true`) — and the stage was still demoted to **Needs
  correction**, whose only control is another *paid* Request Correction.

  Root causes, all three fixed:
  1. **The duplicate-checklist rule counted book-wide.**
     `find_customer_content_defects` failed a book when any bullet item
     appeared 3+ times anywhere. In a meal-prep book "frozen vegetables" and
     "peanut butter" legitimately recur across the starter list, the weekly
     plan and the 30-day plan (measured: 3–4 times across 3–4 *different*
     chapters, never 3 in one). Now scoped **per chapter**, matching the
     reasoning already used by the recurring-heading rule directly above it.
     Padding inside one chapter still fails.
  2. **There was no free way to re-check an already-paid manuscript.** Added
     `recheck_manuscript_quality()` — re-runs outline fidelity, the manuscript
     quality engine and the content checks against the manuscript already on
     disk. Zero provider calls, asserts the ledger cannot move, never edits the
     text, never approves, refuses on an approved manuscript, and can only move
     the stage between `needs_correction` and `awaiting_approval`. Route
     `POST /ebook-workspace/<id>/recheck-manuscript`; UI adds a **Re-check
     Quality (free)** button (primary) with Request Correction demoted to
     secondary.
  3. **Derived outline titles pasted whole research sentences into title
     slots** — a Phase A defect. The live outline produced *"The Core Method:
     Steps to They need practical meal-planning help tailored to long shifts
     and limited time."*, and that title went into the **paid** manuscript
     prompt. Added `_title_phrase()` (strips the subject-verb opener, cuts at
     the first clause boundary, caps length, never ends on punctuation) and
     `_clean_outline_title()` (repairs a sentence buried mid-title, applied to
     template *and* previously-staged titles). Optional audience/topic clauses
     are now only added when they still read as a title.

  - **Verified against the real saved project, read-only and in memory:** the
    re-check clears 21312 from `needs_correction` → `awaiting_approval`
    (`next_action: approve_manuscript`) with **spend unchanged at $1.20 / 8
    paid calls** and the manuscript byte-identical. The project on disk was
    **not** modified — Lonnie clicks the button himself.
  - Tests: new `tests/test_manuscript_recheck_and_title_repair.py` (19 tests,
    14 subtests), added to `tests/acceptance_manifest.json` (now 82 files).
    Includes an unpatched test proving the real quality engine still blocks a
    thin manuscript, so the gate was not weakened.
  - Follow-up the same evening: Lonnie's first attempt still showed Needs
    correction. Cause was **timing, not the fix** — his two Request Correction
    clicks ran at 02:46:43/02:46:54Z against the *previous* server process; the
    fixed server did not start until 02:49:38Z, and his browser page predated
    the relaunch so the new free button was not rendered. Both clicks charged
    **$0.00**. Re-verified read-only against the current saved state:
    `find_customer_content_defects` returns **NONE**, and the re-check clears
    21312 to `awaiting_approval` / `approve_manuscript` with spend unchanged.
  - Also fixed the message that caused the confusion: the manuscript panel said
    "Approve is blocked while structural FAIL findings remain" regardless of
    cause, while this manuscript had **no** structural findings. It now names
    the real blocker (outline/structure, chapter quality, or content findings).
  - **Full preflight release gate: PASS.** `1297` total, `0` failures, `0`
    errors, `0` skipped, `0` paid API calls permitted.
  - Answered the standing cost question: the budget ledger and confirm panel
    have been committed since **2026-08-12** (`bf251ce`, `66bb61a`) — not new,
    and not a Factory fee. Only the five text-generation actions in
    `PAID_ACTIONS` cost anything (research $0.50, title options $0.15, outline
    options $0.20, manuscript $1.50 max, correction $0.75). **Visuals, Cover,
    Design, Preview, Preflight and Export are not paid actions** — the design
    system (`services/ebook_design_system.py`, bundled `services/fonts/`,
    local PDF rendering) is entirely offline, and Pexels stock is free-licence.
    Only AI *image generation* is paid, and it stays separately authorized.

- **2026-09-01 — Factory Market Advantage: repeated "product type is not ready"
  warnings corrected (full gate green).**
  Root cause (two parts, both real):
  1. The research page offered **Build This Product** for every opportunity
     regardless of whether a builder exists. `/research-to-builder` answers
     `409 "This product type is not ready in the public builder yet."` for any
     type that is not an *active* builder, so the click always failed.
  2. The browser handled that failure with
     `out.insertAdjacentHTML("afterbegin", card(...))` in `buildThisProduct()`
     — an **append**, so every click left one more full-width red card stacked
     at the top of the results.
  It fired constantly because the Factory Market Advantage product-type menu
  offers types with no builder (Planner, Flip Book, Spelling Worksheet), and
  when the customer picks one, `coerce_selected_product_type` forces *all five*
  researched opportunities to that type — so nothing on the page was buildable.

  Fixed generically (no product, title, or project is hardcoded anywhere):
  - `services/factory_advantage.py`: added `COMING_SOON_LABEL`,
    `build_readiness()` (one shared yes/no answer, read from the same builder
    registry `/research-to-builder` enforces), `annotate_build_readiness()`
    (purely additive per-opportunity tag — research is never dropped, reordered,
    or rewritten) and `preferred_opportunity()` (headline the normal top pick
    unless its type has no builder **and** a researched alternative does).
    `attach_advantage()` now tags every opportunity; `build_recommendation_summary()`
    headlines the buildable opportunity and reports `build_readiness`.
  - `static/js/app.js`: added `opportunityReadiness()` (trusts the server tag,
    falls back to the browser routing for research saved earlier),
    `isBuildableOpportunity()`, `productTypeIsComingSoon()`,
    `pickBestOpportunity()` (mirrors the server rule), `comingSoonNoticeText/Html()`,
    `comingSoonChipHtml()` and `setFmaNotice()` — **one** notice slot
    (`#fmaNotice`) that is replaced, never appended. `buildThisProduct()` no
    longer calls `insertAdjacentHTML`, and stops with one plain notice instead
    of calling a handoff that must refuse. The recommendation card renders
    **no Build action** for an unsupported type plus exactly one neutral
    notice; opportunity cards get a small grey **Coming soon** chip; the
    product-type menu labels unsupported types "(coming soon)" without changing
    the submitted value.
  - Behaviour preserved on purpose: the research itself, its evidence, sources,
    Save Research, See Research Summary, View Full Research, Improve This Idea,
    and the server-side 409 guard are all unchanged.
  - Tests: 18 focused tests added to `tests/test_factory_market_advantage.py`
    (`ComingSoonProductTypeTests`, `ComingSoonEbookHandoffTests`), including a
    check that an **active Ebook opportunity still opens the repaired Ebook
    workspace seeded with its research approved**.
  - **Full preflight release gate re-run after the change: PASS.** `1080` tests
    passed (182 subtests; runner summary `1262` total), `0` failures, `0`
    errors, `0` skipped, `0` paid API calls permitted.
  - Factory killed and relaunched on port 5055 so the browser gets the new code.
  - Nothing generated, approved, locked, committed, pushed, or deployed.

- **2026-09-01 — Phase A shipped (launch blocker fixed): research seeding +
  run/approve/generate controls for the Ebook workspace (full gate green).**
  Root cause: Build This Product created an Ebook workspace at stage 1 with
  `next_action: "run_research"`, empty research, and no UI control that
  `static/js/app.js` rendered, so every fresh workspace dead-ended and downstream
  gates never unlocked. Fixed in the smallest safe pieces:
  - `services/ebook_project_workspace.py`: added `RUN_RESEARCH_STANDARD_AUTH_USD`
    (0.50); `map_fma_research_to_payload()` (pure FMA→workspace mapper);
    `seed_research_from_build()` (records + auto-approves the research the
    customer explicitly chose, pre-fills title/subtitle as AWAITING);
    `derive_draft_outline()` + `apply_draft_outline()` (free, deterministic
    8-chapter DRAFT outline — zero paid calls); `execute_run_research()`
    (confirmation-token + artifact/revision + budget-capped executor with
    injectable `research_fn` for zero-paid tests, mirrors
    `execute_generate_manuscript`); added 5 gates to `workspace_public_view`
    (`run_research_enabled`, `approve_research_enabled`, `approve_title_enabled`,
    `draft_outline_enabled`, `approve_outline_enabled`; the outline gate turns
    off once an outline exists).
  - `app.py`: `create_ebook_workspace_route` now accepts `research`/
    `opportunity`/`title`/`subtitle` and seeds when research is present (returns
    `seeded`); added `POST /ebook-workspace/<id>/run-research` and
    `POST /ebook-workspace/<id>/draft-outline`.
  - `static/js/app.js`: Build This Product's ebook branch now POSTs the full
    research + opportunity + title/subtitle so the workspace is seeded; the
    "Next production action" ribbon and the Research/Title/Outline stage panels
    now render Run Research / Approve Research / Save Title / Approve Title /
    Generate Draft Outline / Approve Outline controls wired to
    `estimateRunResearchInWorkspace` (estimate→confirm flow), `approveEbookStage`,
    `generateEbookDraftOutline`, `saveEbookTitle`.
  - Tests: added 7 focused Phase A tests
    (`tests/test_ebook_project_workspace.py` → `EbookWorkspacePhaseASeedTests`,
    already in the acceptance manifest).
  - **Full preflight release gate re-run after the change: PASS.**
    `1063` tests passed (168 subtests; runner summary 1231 total),
    `0` failures, `0` errors, `0` skipped, `0` paid API calls permitted.

- **Earlier this session (2026-09-01) — project audit vs. the master blueprint;
  blueprints written** (no app code change at that time, no paid calls, nothing
  generated/approved/locked/committed/pushed). Created `FACTORY_BLUEPRINT.md`
  (permanent north star), updated `CLAUDE.md` (read the blueprint before every
  change), produced a beginner-friendly gap report + prioritized completion
  roadmap (see [Blueprint audit] section).

- **2026-08-31 — one unified Desktop launcher created; older launchers archived**
  (no app change). `C:\Users\user\OneDrive\Desktop\START_DIGITAL_PRODUCT_FACTORY_WORK.bat`
  is the single one-click launcher for all Factory work. It: (1) uses the
  Factory folder path directly; (2) checks OmniRoute on port 20128 and starts
  `omniroute.cmd serve` in its own window **only if not already listening**
  (never a duplicate, never kills an existing process); (3) checks the Factory
  on port 5055 and starts `python _run_factory_5055.py` from the Factory folder
  in its own window **only if not already listening**; (4) waits for both ports
  with a timeout and clear error messages; (5) opens the browser at
  `http://localhost:5055`; (6) launches Claude Code inside the Factory folder
  via `omniroute.cmd launch`. Beginner-friendly errors if the Factory folder,
  `_run_factory_5055.py`, Python, or `omniroute.cmd` is missing. Contains NO
  API keys/passwords/tokens/.env contents (verified by scan). Created but **not
  executed** this session, as requested (OmniRoute was already listening on
  20128; Factory was not running on 5055).

- **2026-08-31 — older launchers archived** (reversible move, no delete). Created
  `C:\Users\user\OneDrive\Desktop\OLD_FACTORY_LAUNCHERS_DO_NOT_USE\` and moved
  `Start_OmniRoute_And_Claude.bat` into it. `Run_Factory.bat` did not exist on
  the Desktop, so nothing was moved for it.

Verified from on-disk files and live port checks (`netstat`), not from memory.

- **2026-08-31 — one-click OmniRoute+Claude launcher created** (no app change).
  `C:\Users\user\OneDrive\Desktop\Start_OmniRoute_And_Claude.bat` starts the
  OmniRoute server in its own window (`omniroute.cmd serve`), waits 8s, then
  opens Claude Code inside the Factory folder via `omniroute.cmd launch`.
  Validates the Factory folder and `omniroute.cmd` presence with beginner
  errors. Contains no API keys/passwords/tokens/.env contents. Not executed
  this session (OmniRoute and Claude already running). Kept the server window
  open via `cmd /k`.

Verified from git history, on-disk files, and session handoffs — not from memory
claims.

- **Most recent commits (newest first):**
  - `91dfc60` — Fix overnight ebook PDF layout so legal, TOC, fonts, and
    sale-quality QA hold.
  - `d5cba3a` — Fix ebook customer PDF sale quality so Ready and downloads stay
    QA-gated.
  - `8d7b157` — Add 2026-08-29 session handoff.
  - `40c78b7` — Route every ebook build to the exportable pipeline; add
    per-type journey tests.
  - `13186be` — Fix Build This Product refusing buildable types; make `.env`
    authoritative.
  - `e383d01` — Fix what Factory Market Advantage shows when research degrades.
  - `362d4c1` — Fix `_lemon_request` crashing on 204 No Content responses.
  - `e436281` — Rework pricing ladder to match live Lemon Squeezy products; fix
    checkout email bug.
- **Branch:** `main`, up to date with `origin/main` (verified via `git status` /
  `git log`).
- The 2026-08-29 handoff reported 1056 tests passing, 0 failed, 0 paid API
  calls at that point. **Not re-run this session** (memory-only task).
- Session handoffs present: `SESSION_HANDOFF_2026-08-21` through
  `SESSION_HANDOFF_2026-08-29.md`.
- Full test list lives in `tests/acceptance_manifest.json` (~80 test files),
  driven by `scripts/run_factory_tests.py` via `preflight_check.py`.

## Confirmed working features (from git history + handoffs)

- Public URL `digitalproductfactorypro.com` served via a Cloudflare named
  tunnel → `http://localhost:5055` (tunnel runs ad hoc, not as a Windows
  service).
- Lemon Squeezy checkout/webhook flow (single clean webhook `130242`;
  `_lemon_request` handles 204 responses).
- Factory Market Advantage research with graceful degraded mode (no raw
  provider exceptions leaked; BUILD/IMPROVE/AVOID headings; input-backed draft).
- Build This Product routing by head noun; `.env` authoritative for keys
  (with a test-mode carve-out so the paid-call guard holds in tests).
- Ebook builds routed to the exportable pipeline from every entry point;
  per-type customer journeys (ebook, word search, crossword, coloring book,
  math worksheet, faith planner, budget planner) each produce a reviewed
  PDF + ZIP.

## Files changed (most recent task: logo on the three builder pages, 2026-09-03)

- `templates/crossword_builder.html` — header eyebrow text → logo `<img>`.
- `templates/word_search_builder.html` — header eyebrow text → logo `<img>`.
- `templates/cover_editor.html` — logo `<img>` added to `.editor-header`.
- `PROJECT_STATUS.md` — this record.

No Python, no JavaScript, no routes, no tests, no static assets added or
changed. The logo PNG already existed. Nothing committed, pushed, or deployed.

## Files changed (earlier task: one-click Build My Whole Book)

- `services/ebook_auto_build.py` (new) — `plan_full_build()`,
  `run_full_build()`, `AutoBuildStop`, bounded auto-correction.
- `app.py` — `estimate-full-build` / `run-full-build` routes,
  `_auto_build_stage_functions()`, and the 26-route 404 fix.
- `static/js/app.js` — `estimateFullBuild()` and the "Build My Whole Book…" card.
- `tests/test_one_click_full_build.py` (new, 20 tests),
  `tests/acceptance_manifest.json`; slice/expectation updates in
  `tests/test_manuscript_panel_plain_language.py`,
  `tests/test_long_action_progress.py`,
  `tests/test_manuscript_recheck_and_title_repair.py`.

## Files changed (earlier task: plain-language manuscript stage)

- `static/js/app.js` — `manuscriptStagePanelHtml()`, `MANUSCRIPT_FINDING_PLAIN`,
  `plainManuscriptFinding()`, `plainManuscriptIssues()`; collapsed "Read your
  draft" / "Technical details"; single primary action in panel and ribbon.
- `services/ebook_project_workspace.py` — `CUSTOMER_ACTION_LABELS`.
- `tests/test_manuscript_panel_plain_language.py` (new, 13 tests),
  `tests/acceptance_manifest.json`; wording updates in
  `tests/test_ebook_project_workspace.py` and
  `tests/test_manuscript_recheck_and_title_repair.py`.

## Files changed (earlier task: live progress for long actions)

- `services/progress_tracker.py` (new) — in-memory, thread-safe progress registry.
- `services/ebook_manuscript_engine.py` — `on_progress` hook on the chapter pipeline.
- `services/ebook_project_workspace.py` — `chapter_progress_reporter()`,
  `progress_key` on the generate/correct executors.
- `app.py` — `GET /ebook-workspace/<id>/progress`; job start/finish around
  generate and correct.
- `static/js/app.js` — `startWorkspaceProgress()` + wiring for manuscript,
  correction and research.
- `tests/test_long_action_progress.py` (new, 20 tests), `tests/acceptance_manifest.json`.

## Files changed (earlier task: manuscript false-positive + free re-check)

- `services/ebook_document.py` — `_chapter_sections()`; duplicate-checklist rule
  scoped per chapter instead of book-wide.
- `services/ebook_project_workspace.py` — `recheck_manuscript_quality()`;
  `_title_phrase()`, `_clean_outline_title()`, repaired `derive_draft_outline()`
  titles; `import re`.
- `app.py` — `POST /ebook-workspace/<id>/recheck-manuscript`.
- `static/js/app.js` — `recheckManuscriptQuality()`, Re-check Quality (free)
  button in the manuscript panel and the next-action ribbon.
- `tests/test_manuscript_recheck_and_title_repair.py` (new, 19 tests),
  `tests/acceptance_manifest.json`.

## Files changed (earlier task: FMA repeated-warning correction)

- `services/factory_advantage.py` — `COMING_SOON_LABEL`, `build_readiness()`,
  `annotate_build_readiness()`, `preferred_opportunity()`; `attach_advantage()`
  tags opportunities; `build_recommendation_summary()` prefers a buildable
  headline and reports readiness.
- `static/js/app.js` — build-readiness helpers, single `#fmaNotice` slot,
  Coming soon chip/notice, Build action gated on readiness, product-type menu
  labels, `buildThisProduct()` no longer stacks warnings.
- `tests/test_factory_market_advantage.py` — 17 new focused tests.
- Phase A files from earlier today are untouched and still uncommitted:
  `app.py`, `services/ebook_project_workspace.py`, `static/js/app.js`,
  `tests/test_ebook_project_workspace.py`.

## Files changed (earlier task: blueprint audit)

- Created `FACTORY_BLUEPRINT.md` (permanent north star; mirrors the master
  blueprint and anchors it to repo services/tests).
- Updated `CLAUDE.md` (must now read `FACTORY_BLUEPRINT.md` before every
  change).
- Updated `PROJECT_STATUS.md` (this file).
- No application code changed.

Earlier task (2026-08-31, unified launcher; cross-reference): created
  `C:\Users\user\OneDrive\Desktop\START_DIGITAL_PRODUCT_FACTORY_WORK.bat` and
  archived older launchers; recorded above in "Completed work".

## Tests run and results

- **After one-click Build My Whole Book (2026-09-01): full preflight release
  gate PASS.** `1381` total, `0` failures, `0` errors, `0` skipped, `0` paid
  API calls. Focused first: 20 new one-click tests, then the panel, progress
  and re-check suites (73 passed).

- **After the plain-language manuscript stage (2026-09-01): full preflight
  release gate PASS.** `1342` total, `0` failures, `0` errors, `0` skipped,
  `0` paid API calls. Focused first: 13 new panel tests, then the workspace,
  manuscript, correction, re-check and progress suites (120 passed).

- **After adding long-action progress (2026-09-01): full preflight release
  gate PASS.** `1317` total, `0` failures, `0` errors, `0` skipped, `0` paid
  API calls. Focused first: 20 new progress tests, then the chapter-pipeline
  and workspace suites (145 passed).

- **After the manuscript false-positive fix (2026-09-01): full preflight
  release gate PASS.** `1296` total, `0` failures, `0` errors, `0` skipped,
  `0` paid API calls. Focused first: 19 new tests green, then the ebook
  workspace/manuscript/quality/outline/designrr suites (149 passed), then the
  quality-gate and per-type customer-journey suites (168 passed).

- **After the FMA repeated-warning correction (2026-09-01): full preflight
  release gate PASS.** `1081` tests passed (182 subtests; runner summary
  `1263` total), `0` failures, `0` errors, `0` skipped, `0` paid API calls
  permitted. Focused first: baseline `119 passed / 11 subtests` across
  `test_factory_market_advantage.py`, `test_research_to_build_handoff.py`,
  `test_choose_idea_build_handoff.py`, `test_ebook_project_workspace.py`;
  after the change `139 passed / 25 subtests` across those plus
  `test_saved_projects_reopen_build.py`.

- **After Phase A code change (2026-09-01): full preflight release gate PASS.**
  `1063` tests passed (168 subtests; runner summary `1231 total`), `0`
  failures, `0` errors, `0` skipped, `0` paid API calls permitted. Ran via
  `python preflight_check.py` (compiles source, `node --check` on `app.js`,
  validates the manifest, runs all 81 acceptance files in test-DB isolation).
- Focused Phase A tests green first: 7 new tests in
  `tests/test_ebook_project_workspace.py` (`EbookWorkspacePhaseASeedTests`),
  then the whole `test_ebook_project_workspace.py` file (29 tests) passed.

## Known gap — visuals are photos only (raised 2026-09-01)

Lonnie: "I have [not] seen any images, photos, graphs, charts added to text."
Two separate reasons, both confirmed in code:

1. **Visuals had never run on his books.** `prepare_visuals_for_review()`
   refuses until the manuscript is approved, and no book had got past
   manuscript approval. The one-click build now reaches that stage, so stock
   photos will appear for the first time.
2. **Diagrams, charts and comparison tables are hardcoded to one topic.**
   `services/ebook_interior_visuals.py` gates its whole catalogue —
   balance diagram, content checklist, decision chart, sequence diagram —
   behind `is_screens_parenting_topic()`. Every other topic gets stock
   photography only. This is both a blueprint §8 gap (visuals should include
   diagrams, data charts, comparison tables, timelines, checklists, callout
   boxes) and a §14 violation (do not hardcode a fix for one topic).

**Not yet started.** The fix is a topic-agnostic instructional-visual
generator that derives aids from the approved outline and chapter content
(chart from any numeric comparison, table from any either/or decision,
checklist from any step list) and renders them locally — no paid image
generation. Awaiting Lonnie's go-ahead.

## Current blockers

1. ~~**Ebook Project workspace cannot be started from the UI**~~ — **RESOLVED
   in Phase A (2026-09-01).** Fresh workspaces now advance from Research via
   seeded research and/or Run Research / Approve Research / Save Title /
   Approve Title / Generate Draft Outline / Approve Outline controls, reaching
   the already-working Generate Manuscript flow. Re-verify in the browser
   (steps in the 2026-09-01 session handoff / live status).
2. **Cloudflare tunnel runs ad hoc** (dies on reboot); not yet a durable
   Windows service (Phase D — unchanged).
3. **Review-key names still unify** (`qa_report` vs `qa_result` vs
   `editor_in_chief`, plus `quality_result` in packaging/KDP) — Phase C,
   unchanged.

## Decisions awaiting Lonnie

00. ~~**Delete `flask_app/Start_Factory_5055.bat`?**~~ — **DONE 2026-09-03.**
    Lonnie approved; deleted via File Explorer's toolbar (the sandboxed shell
    was unavailable, `HYPERVISOR_VIRT_DISABLED`). It went to the **Recycle Bin**,
    so it is recoverable if ever wanted. Verified gone by directory listing:
    `flask_app` now holds 8 `.bat` files, all pre-existing
    (`Run_Factory_Preflight`, `Setup_Factory_Development`,
    `Initialize_Factory_Git`, `Update_API_Key_Anywhere`, `Setup_Billing_Keys`,
    `Setup_API_Keys`, `Set_OpenAI_Key`, `Set_OpenAI_Key_From_File`).
    `START_DIGITAL_PRODUCT_FACTORY_WORK.bat` on the Desktop remains the single
    unified launcher. Note: the folder is OneDrive-synced, so the deletion
    propagates to the cloud copy as well.
0a. **Run the preflight gate, then visually approve the logo.** The logo edit to
    `templates/index.html` is untested and unseen — run
    `preflight_check.py` (zero paid calls), then start the Factory via
    `START_DIGITAL_PRODUCT_FACTORY_WORK.bat` and hard-refresh (Ctrl+F5, needed
    because `use_reloader=False` and `debug=False` mean templates are cached).
    Check: logo at the top of the dark sidebar on a white card, not stretched or
    cropped; then narrow the window below ~768px and confirm the compact logo
    appears in the top header. **Then check the three builder pages** (added
    2026-09-03): Crossword Builder and Word Search Builder — logo above the page
    title in the white header, aspect ratio intact, `h-8` not visually
    overpowering the `<h1>`; Cover Editor — logo sitting between "← Back to
    Factory" and "Cover Editor" on one row without wrapping or crowding the
    `{{ product_type }}` badge. Nothing is committed, pushed, or locked.
0b. ~~**Alt text wording.**~~ — **SETTLED 2026-09-03.** Lonnie said "fix it";
    the trailing period from his original request is now applied to all five
    logo `<img>` tags (2 in `index.html`, 1 each in the three builder pages), so
    every one reads `alt="Digital Product Factory."`. Consistent across the app
    and harmless for screen readers, which treat the period as a pause. Purely
    cosmetic and trivially reversible; still covered by the untested/unverified
    flag above.
0c. ~~**Should the standalone builder pages get the logo too?**~~ —
    **DECIDED YES and DONE in code 2026-09-03** (see the first entry under
    "Completed work"). All three now carry the logo; all three are UNTESTED and
    UNSEEN. Folded into the 0a verification below. Note that `cover_editor.html`
    had no brand mark before, so it changed more than the other two.

0. **Browser verification of the Factory Market Advantage repeated-warning fix**
   (do this first). Go to Factory Market Advantage, choose a product type marked
   **(coming soon)** — Planner, Flip Book, or Spelling Worksheet — run the
   research, and confirm: one small neutral notice, a grey **Coming soon** chip
   on the opportunity cards, **no Build This Product button**, and that clicking
   around never stacks a second red warning. Then run a normal research (Ebook /
   Coloring Book / Workbook) and confirm Build This Product is back and works.
1. **Browser verification of Phase A** (next). Recommended flow: run the
   Factory (`START_DIGITAL_PRODUCT_FACTORY_WORK.bat`), go to
   Factory Market Advantage, run research on a topic, choose an opportunity,
   click **Build This Product** → a new Ebook Project should open already
   seeded at **Approve Title**. Also test the blank path (Build This Product
   without research, or a new workspace) → **Run Research…** → confirm → review
   → **Approve Research** → set title → **Approve Title** → **Generate Draft
   Outline** → **Approve Outline** → **Generate Manuscript…**. Confirm before
   further phases.
2. Make the Cloudflare tunnel durable as a Windows service, or accept ad hoc
   (dies on reboot) — Phase D, not started.
2. Make the Cloudflare tunnel durable as a Windows service, or accept ad hoc
   (dies on reboot).
3. Finish Lemon Squeezy's business-details form with
   `https://digitalproductfactorypro.com`.
4. Unify the inconsistent review-key names across the catalogue
   (`qa_report` vs `qa_result` vs `editor_in_chief`, plus `quality_result` in
   packaging/KDP — confirmed live 2026-09-01).

## Blueprint audit 2026-09-01 (see chat report for the full gap report)

- **Working now:** research + degraded mode; editor-in-chief as a real export
  gate (`export_ready` derived from it); per-type PDF+ZIP exportable pipeline;
  cover + visual gates; explicit-approval lifecycle with immutability guards;
  paid-image authorization + budget guards; spending-capped ebook workspace
  ledger; billing; launchers.
- **Partially working:** research→build handoff (Build This Product creates a
  workspace but discards the research); ebook workspace UI (later-stage panels
  have controls; Research/Title/Outline have none); review-key naming.
- **Broken/unreliable:** fresh ebook workspace dead-ends at Research in the
  UI (single launch blocker). Secondary: 1.5 GB `projects.db` (hygiene risk);
  tunnel dies on reboot.
- **Missing:** durable tunnel; research seeding; run/approve controls for the
  first three stages; unify review keys.
- **Launch blockers:** the ebook workspace Research dead-end.

### Prioritized completion roadmap (smallest safe phases)

1. **Phase A — unblock the ebook workspace start** (recommended first):
   seed research into new workspaces + render Run Research / Approve Research
   (and Title/Outline generate+approve) controls; focused tests
   (`test_ebook_project_workspace.py`, `test_research_to_build_handoff.py`).
2. **Phase B — guide the customer:** per-stage "what's next" copy and one clear
   next action on every workspace stage; verify in browser.
3. **Phase C — unify review keys:** pick one canonical key across catalogue +
   packaging/KDP; keep read-compat for old saved projects; run full gate.
4. **Phase D — durability/hygiene:** tunnel as a Windows service; DB compaction
   and test-data cleanup (1.5 GB `projects.db`); archive stray `_*.py` scripts.
5. **Phase E — polish to launch:** contact-sheet visual review parity, cover
   "Use This Cover in PDF" across all types, publishing/marketing paths gated
   behind QA, full browser journey pass per product type.

## Exact safest next step

### Resume point — 2026-09-03, Lonnie rebooting into BIOS

Lonnie left mid-session to enable hardware virtualization (Intel VT-x / AMD SVM)
so the sandboxed Linux shell can start. **Nothing is in a volatile state.** All
template edits and this status file are written to disk; there is nothing
unsaved, no process that needs a clean shutdown, and no in-flight generation,
paid call, or approval. A reboot is safe.

Expect after the reboot:

- Any running Factory process on port 5055 is gone — relaunch with
  `START_DIGITAL_PRODUCT_FACTORY_WORK.bat`.
- The Cloudflare tunnel is gone too (known: it is ad hoc and dies on reboot —
  blocker 2). Only matters if a public URL is needed.
- Whether the sandbox now starts is unknown. Even if it does, it is **Linux**:
  it cannot run the Windows `.venv`, cannot serve `localhost:5055`, and so
  cannot run `preflight_check.py`. What it would add is `git status`, file
  deletion, and scratch scripting.

Then continue with the preflight step below — unchanged by the reboot.

**FIRST (added 2026-09-02 evening, widened 2026-09-03): run
`preflight_check.py` to prove the logo edits did not break anything.** It is a
zero-paid-call gate and has NOT been run since any of them. Four templates are
now involved: `index.html` (sidebar + mobile header) and
`crossword_builder.html`, `word_search_builder.html`, `cover_editor.html`
(headers). If it is green, start the Factory with
`START_DIGITAL_PRODUCT_FACTORY_WORK.bat`, hard-refresh (Ctrl+F5), and look at
the sidebar, then open each builder page.

If it is red, the logo edits are the prime suspect and each one reverts
independently — every change is a single self-contained `<img>` block:
reverting the two in `index.html` restores the previous "DP" square exactly;
reverting the builder-page ones restores the `<p class="text-xs font-semibold
uppercase tracking-wide text-indigo-600">Digital Product Factory</p>` eyebrow;
reverting the `cover_editor.html` one leaves the header as it was, with no
brand mark. A template-only edit cannot break Python imports, so a red gate
here more likely points at something else — read the failure before reverting.

Then, unchanged from before:

**Lonnie hard-refreshes (Ctrl+F5), opens Ebook Project 21312 and clicks
"Re-check Quality (free)"** — the button only exists on a page loaded from the
server started at 03:02:31Z.
Expected: $0 spent, the manuscript moves to Awaiting approval, and Approve
Manuscript becomes available — then Visuals → Cover → Design → Preview →
Export, none of which are paid actions. The project has deliberately been left
untouched so that click is his.

After that:

Phase A **and** the Factory Market Advantage repeated-warning correction are
implemented, the full preflight gate is green, and the Factory has been
relaunched on port 5055 with the new code. **Next: Lonnie verifies both in the
browser** — first the Coming soon behaviour on the research page (no stacked red
warnings, one neutral notice, no Build action for an unsupported type), then the
Ebook path (Build This Product → workspace opens seeded at Approve Title with
the research preserved). See "Decisions awaiting Lonnie" for the exact clicks.
After visual approval we decide whether to continue to Phase B (per-stage
guidance) or another phase. Nothing is committed, pushed, generated, approved,
locked, or deployed.

## Date last updated

2026-09-03 (logo extended to `crossword_builder.html`,
`word_search_builder.html` and `cover_editor.html` — NOT tested, NOT verified
in a browser, NOT approved; the sandboxed shell failed to start
(`HYPERVISOR_VIRT_DISABLED`) so again no tests and no `git status`; alt text
now reads `Digital Product Factory.` with the trailing period in all five logo
tags; the redundant `Start_Factory_5055.bat` was deleted to the Recycle Bin
with Lonnie's approval; Lonnie first chose to skip the BIOS/virtualization fix
but then decided to attempt it — he left to reboot into BIOS at the end of this
session, outcome UNKNOWN, so the next session must not assume the sandboxed
shell works or that it doesn't: try one command and see. Either way
`preflight_check.py` runs on Windows, not in the sandbox);
earlier 2026-09-02 evening (logo added to the sidebar + mobile header in
`templates/index.html` — NOT tested, NOT verified in a browser, NOT approved;
redundant `Start_Factory_5055.bat` created in error and pending deletion;
shell access was denied all session so no tests were run);
earlier 2026-09-02 (unfinished books reachable again; build dead end fixed +
confirmation step removed;
one-click Build My Whole Book; manuscript stage in plain
language; live progress
for long paid actions; manuscript
false-positive fixed + free Re-check Quality, on
top of the FMA repeated-warning correction and Phase A; full release gate green
at 1408 tests; Factory relaunched; project 21312 left untouched pending
Lonnie's free re-check)
