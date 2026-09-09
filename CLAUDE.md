# CLAUDE.md — Digital Product Factory

This file sets how every future Claude session must work in this repository.
It is the permanent project memory. Read it first, then follow it for the whole
session.

## Every session must do this

Before changing anything in this repository, every Claude session **must**:

0. **Read `FACTORY_BLUEPRINT.md` first.** It is the permanent north star —
   the mission, the production workflow, the quality standard, the
   Editor-in-Chief gate, saving/lifecycle protection, export rules, spending
   safety, and the definition of done. **It must be read before every change.**
1. **Read `PROJECT_STATUS.md` next.** It is the single source of truth for
   where work stands. Never start from assumptions.
2. **Inspect the repository and `git status` before assuming prior work is
   missing.** Files, tests, and completed features may already exist even when
   a request is phrased as new.
3. **Continue from recorded completed work instead of restarting it.** Don't
   redo finished tasks, re-litigate settled decisions, or rebuild what is
   already recorded as working.
4. **Update `PROJECT_STATUS.md` immediately after every meaningful completed
   task** — not only at the end of a session. If you complete a real piece of
   work, record it before moving on.
5. **Record the following in `PROJECT_STATUS.md`** whenever it changes:
   - current objective
   - completed work
   - confirmed working features
   - files changed
   - tests run and results
   - current blockers
   - decisions awaiting Lonnie
   - exact safest next step
   - date last updated

## Safety rules — never break these

6. **Never write API keys, passwords, tokens, or `.env` contents into any
   memory file** (including `PROJECT_STATUS.md` and `CLAUDE.md`).
   `.env` holds live credentials. Refer to its locations by name only.
7. **Never call paid or external services, generate or overwrite a product,
   approve, lock, commit, push, delete, or deploy without Lonnie's explicit
   approval.** These actions are outward-facing or destructive; ask first every
   time.
8. **Use focused tests first.** When changing a specific area, run the relevant
   focused tests first. Avoid repeatedly running the entire test suite
   unnecessarily.
9. **Preserve unrelated user changes.** Don't revert, overwrite, or "clean up"
   files or edits that belong to the user or another task, even if they look
   messy.
10. **Explain actions in beginner-friendly language, and clearly separate:**
    Claude Code instructions, Terminal/PowerShell instructions, `.env`
    instructions, and browser instructions. Never blur these together.

## How to run things (verified facts)

- The app is a Flask backend, entry point `app.py`.
- The app normally runs on **port 5055** via `_run_factory_5055.py`
  (`python _run_factory_5055.py`). A second launcher `_run_factory_5077.py`
  exists for port 5077.
- `use_reloader=False` — **kill and relaunch the app after every code change.**
  A stale process is a common cause of "the fix didn't work."
- `preflight_check.py` is the zero-paid-call release gate. It compiles and runs
  the acceptance suite without starting Flask or calling paid APIs.
  Run it before and after changes when a full gate is warranted.
- Tests live in `tests/`; the full test list is
  `tests/acceptance_manifest.json`, driven by `scripts/run_factory_tests.py`.
- Front-end is `static/js/app.js`. After editing it, hard-refresh the browser
  (Ctrl+F5).

## Project nature

Digital Product Factory — a Flask app that researches product ideas and builds
sellable digital products (ebooks, puzzles, worksheets, coloring books,
planners). Production infrastructure includes Cloudflare tunneled public URL
and Lemon Squeezy payments. Full standing history and recent context live in
the `SESSION_HANDOFF_*.md` and `*_LOCKED_STATE.md` files in this directory.

## Standing open items (see PROJECT_STATUS.md for the live list)

- ~~Ebook Project workspace launch blocker~~ — **RESOLVED 2026-09-01 (Phase A).**
  Ebook workspaces now start from Research correctly: Build This Product seeds
  the research it already has (research auto-approved, title pre-filled
  AWAITING), and fresh/blank workspaces get visible Run Research / Approve
  Research / Save Title / Approve Title / Generate Draft Outline / Approve
  Outline controls (wired in `static/js/app.js` + backend routes
  `/ebook-workspace/<id>/run-research` and `/draft-outline`), reaching the
  working Generate Manuscript flow. Full preflight gate green; next step is
  Lonnie's browser verification.
- Make the Cloudflare tunnel durable as a Windows service or accept ad hoc.
- Unify the three inconsistent review-key names across product types.

Start by reading `FACTORY_BLUEPRINT.md` (required north star), then
`PROJECT_STATUS.md` (required), then continue from the most recent
`SESSION_HANDOFF_*.md` for detailed narrative context.
