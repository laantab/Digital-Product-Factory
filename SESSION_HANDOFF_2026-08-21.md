# Session Handoff — 2026-08-21 (Audit Session, Fable)

**Read this first, then `AUDIT_REPORT_2026-08-21.md` (in this folder). The audit report is the
work order; this file is the context.**

## What happened this session
- Ran the Digital Product Factory live (Flask dev server, `python app.py`; port 5000 busy →
  ran on 50401) and drove every view in Chrome. No fixes were made — audit only, by request.
- Ran the enforced release gate (`preflight_check.py`): **884 passed, 1 error** —
  `test_ebook_real_browser_customer_path.py` errors because `playwright` is not installed in
  `.venv`. Gate is red for environment reasons only.
- Wrote `AUDIT_REPORT_2026-08-21.md` with all findings and a recommended work order (§7).
- Committed this state to the existing `flask_app` git repo and pushed to GitHub (first remote).

## Start here (work order from the audit, §7)
1. `.venv\Scripts\python -m pip install -r requirements-dev.txt` and
   `.venv\Scripts\python -m playwright install chromium`, re-run `preflight_check.py` → expect
   885/885 green. The project rule: never accept a change while the gate is red.
2. Fix the four UI bugs:
   - `/crossword-builder/` 500 — `templates/crossword_builder.html` missing
     (`routes/crossword_builder.py:112`).
   - Dashboard "Launch Package" card clicks nonexistent `launchDashBtn`
     (`templates/index.html:126`).
   - Dashboard "Spelling Worksheet" tile leads to a builder where the type is hidden — hide the
     tile or finish the product.
   - Saved Projects "Open" renders the product below the fold under a stale blank form in
     Product Factory — no auto-scroll (`openProject()` in `static/js/app.js` ~line 1194).
3. Filter internal QA records ("Customer Real Product Check", "Cover Guided Step Project",
   "Thunder Volt…") out of Publishing Studio + Platform Packages dropdowns — reuse the
   customer-visible filter Saved Projects already uses.
4. Then: checkout stub decision, spelling_worksheet completion, DB/exports cleanup — details in
   the audit report §4–§7.

## Key facts you'd otherwise rediscover slowly
- Whole UI is one SPA: `templates/index.html` + `static/js/app.js` (~458 KB). Sidebar views are
  JS-driven; direct URLs 404 by design.
- Hidden product types (UI `hidden:true` + server guard `_HIDDEN_PRODUCT_TYPES` in
  `app.py:1527`): spelling_worksheet, planner, flip_book, cover_design, marketing_kit.
  spelling_worksheet has a full backend (`services/spelling_worksheet/`) and only lacks an
  acceptance contract in `tests/acceptance_manifest.json`.
- `projects.db` = 1.5 GB / 14,011 rows (12,094 ebooks, mostly QA runs). PDF bytes stored as
  blobs in rows. Two more multi-GB backup DBs sit nearby; `exports/` is 6.2 GB. All gitignored.
- Everything lives under OneDrive sync — move DBs/exports out or exclude them (SQLite +
  OneDrive = corruption risk).
- `.env` holds live OpenAI/Tavily/Pexels keys (gitignored, never committed) — user should
  rotate the OpenAI key.
- AI status endpoints: `/coloring-ai-status`, `/pexels-status` — both ready.
- 3 of 6 customer ebooks are in "Needs correction." state; one has no download buttons.

## User workflow preferences (stated this session)
- Audit/report in one session; **fixes done in a separate Opus session** (this handoff exists
  for that session).
- Likes watching work happen live in the Chrome browser drive.
