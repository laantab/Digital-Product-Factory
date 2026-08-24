# Session Handoff — 2026-08-24 (supersedes SESSION_HANDOFF_2026-08-23.md)

**Start a new session with:** "Read flask_app/SESSION_HANDOFF_2026-08-24.md and continue."

## State right now

- **Release gate GREEN: 920 tests**, 0 failures, 0 errors, 0 skipped, 0 paid API calls.
- Pushed: `a810843` (project 20090 repair + Editor-in-Chief gate) and `c2c5620`
  (the three "Needs correction" ebooks + 5 more pipeline root causes).
- The Editor-in-Chief gate runs on **every** ebook export. Verdict, scores and findings
  persist on the project (`data.editor_in_chief`); `export_ready` requires a PASS.
- `.env.backup_*` (old revoked OpenAI key) deleted 08-24. Git history scanned: no secrets.

## The four books

| # | Book | PDF | Editor-in-Chief | Blocker |
|---|---|---|---|---|
| 20090 | Container Gardening | 30p, photo cover | **PASS 9.85** | none — sellable |
| 4249 | Event Photography | 62p, 11 images | not re-reviewed | 1 chapter wants a demonstration visual |
| 1961 | Average Joe / money online | 42p, 3 images | CORRECTION 9.69 | 4 minor "sparse page" notes only |
| 14626 | Teen Safe Online | 33p, 4 images | BLOCKED 9.54 | one chart has fake data (see below) |

All four PDFs are clean: no raw markdown, no leaked production notes, real covers,
QA validator PASS, downloads verified through the customer path.

## What needs the owner (in priority order)

1. **#14626 — the "Main Types of Online Risk" chart is not real data.** Its values are
   `[1, 1, 1, 1]` — four labels drawn as identical bars. The Editor-in-Chief blocks it as
   "numeric chart has no recorded data source; confirm the figures are real." It should
   almost certainly become a plain list or a labelled diagram, not a bar chart. I did not
   fabricate a data source and did not silently redesign it. **Decide: convert to a list,
   or supply real figures + source.**
2. **#1961 is one calibration decision from PASS.** Its only findings are 4 minor
   PAGE_SPARSE notes on list-heavy pages (bulleted checklists have low ink coverage, so
   the rule reads them as "mostly empty"). The pages were visually inspected and are fine.
   Options: accept as-is, or make PAGE_SPARSE proportional to book length / cap cumulative
   minor penalties. **I deliberately did not retune the gate to make a book pass.**
3. **#4249** — needs 1 demonstration visual; re-run its release check after.
4. Standing decisions, unchanged: payments stub, 1.5 GB DB purge, OneDrive move,
   public repo visibility. Also still open: rotate the Tavily and Pexels keys.

## Notes for whoever picks this up

- Pexels image fetching works and is free: `POST /retry-ebook-visual` with
  `{project_id, package_id, visual_id, aid, fields, title, chapter, visual_plan}`.
  6 images were fetched this session (3 photos + 3 "infographic"-typed slots that were
  really unfilled image slots with `needs_image: True`).
- Local, no-API cover generation: `services/ebook_cover_local.cover_design_from_local()`.
  Themes: event_photography, parenting_screens, finance, general.
- `exports/` and `projects.db` are gitignored — PDFs, images and project rows are LOCAL
  ONLY and are not on GitHub. Only code and docs are pushed.
- Never accept work on a red gate. Run `preflight_check.py` before and after.
