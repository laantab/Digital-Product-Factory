# Session handoff — 2026-09-18 (v1.8.1)

## Start here

Branch **`fix/v1.8.1-workspace-to-builder`**, four commits, based on
`origin/main`. **Nothing is pushed, merged or deployed. No production
setting was changed.** The working tree is clean.

```
310189d Relock the four Function Locks at 23a6a4f (v1.8.1)
23a6a4f Release v1.8.1 - the pictures move to the builder too
07c379a v1.8.1 part 2: stage holds, the paid pre-manuscript routes, four suites
1b81cad v1.8.1 part 1: the route registry, the hand-off, the step-by-step routes
```

Read `V1_8_1_DEPLOYMENT.md` before doing anything in Render. Its step 2 —
pointing the builder service at `main` — is the one that will bite if it is
skipped.

## What v1.8.1 does

Closes the gap v1.8.0 left: the step-by-step ebook screen, the visuals
buttons and the cover buttons were still doing heavy work inside the web
process. On 2026-09-18 that killed a gunicorn worker at the 120-second
timeout and then took the 512 MB instance out of memory, while the builder
showed zero runs all evening.

Fourteen routes now hand their work to the builder. The builder can stop
after any stage and wait, and approving a stage is what releases it. Covers
and photographs the builder makes go through the storage driver, because the
two services share no disk. Every POST route is classified in
`services/jobs/route_registry.py`, and `tests/test_post_route_registry.py`
fails the gate when a new one is added without that decision being made.

## State of the repository, verified not assumed

- `origin/main` is `e9654c5`, which already contains v1.8.0 (PR #3). The
  local `main` was stale at v1.7.29 before this session; it was left alone,
  and the branch was cut from `origin/main` directly.
- Every file in the checkout shows as modified to git. It is CRLF-vs-LF
  only: `git diff --ignore-cr-at-eol --numstat` reports zero changed lines
  on all 477. All commits in this session were made with
  `git -c core.autocrlf=input` so the diffs contain real changes only.
  **Worth fixing separately** — a `.gitattributes`, or setting
  `core.autocrlf=input` permanently — because it hides real changes.
- A stale `.git/index.lock` was blocking every git command at the start of
  the session. Removed.

## Release gate

All 160 manifest files were run. Every new v1.8.1 suite is green, and the
Fast Stability Gate is green.

**Nine failures are PRE-EXISTING.** Each was confirmed by running the same
file at `origin/main` in a separate worktree, and each was left untouched:

| File | Count |
|---|---|
| `test_template_system_v1.py` | 1 |
| `test_coloring_open_skin_and_text_rules.py` | 1 |
| `test_ebook_interior_layout.py` | 2 |
| `test_ebook_chapter_production.py` | 1 |
| `test_postgres_compatibility.py` | 1 (artifact: psycopg is installed here) |

These are not v1.8.1's to fix, but they were already red before this
session and somebody should decide what to do about them.

**Three tests could not be run and must be run on Windows before merge:**
`tests/test_ebook_real_browser_customer_path.py` needs Playwright's
Chromium, which the Linux VM this session used cannot download. It drives
the ebook customer path in a real browser, so it is the test that covers
the `static/js/app.js` change. Treat the release as unverified on that
front until it has been run.

One failure was genuinely introduced and fixed: a comment added to
`app.js` contained the phrase "paid call", which
`test_ebook_customer_interface_language.py` scans the shipped file for. The
test was right; the comment was reworded, not the test.

## Function Locks

`invite_protection`, `coloring_book`, `crossword` and `word_search` were
unlocked and relocked at `23a6a4f`, following the registry procedure. They
trip on any change because `app.py` and `static/js/app.js` are declared as
whole-file shared dependencies. Neither protected behaviour was touched,
and both claims were checked by diff rather than asserted.

## Open, and needing the owner

1. **Project 11 was not inspected.** It exists only in the production
   PostgreSQL database. The local `.env` sets no `DATABASE_URL`, so this
   repository runs on SQLite and project 11 is not in it. Reading production
   needs a credential only the owner holds. The read-only way to see it,
   from a browser and with no shell: `GET /ebook/build/11/status` on the
   live site. It makes no paid call. **It was not resumed and nothing was
   spent on it.**

2. **Seven heavy routes were deliberately not moved**: `/export-product`,
   `/render-visual-image`, `/retry-ebook-visual`, `/enhance-ebook`,
   `/generate-ebook`, `/ebook/regenerate-cover`,
   `/projects/<id>/kdp/prepare-package`. They work on a `package_id` or an
   older non-workspace record, and the builder's only task is `build_ebook`,
   which drives a step-by-step build — there is nothing for them to join.
   Registered heavy, with that reason written down, in the route registry.
   Moving them needs a second builder task: its own release.

3. **Nine more heavy routes** belong to the coloring book, crossword, word
   search and planner lines, and are registered the same way for the same
   reason.
