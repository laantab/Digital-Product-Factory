# Session Handoff — 2026-08-23 (supersedes SESSION_HANDOFF_2026-08-21.md)

**Start a new session with:** "Read flask_app/SESSION_HANDOFF_2026-08-23.md and continue."

## State right now (all verified)

- **Release gate GREEN:** 885 passed / 0 failed / 0 skipped. Repair session's fixes all landed.
- **GitHub live:** `github.com/laantab/Digital-Product-Factory` (main). Local and remote are in
  sync after merging the user's web upload (`c27a2d9`: session notes + Update_API_Key_Anywhere.bat).
  A backup repo exists: `The-Digital-Product-Factory`. **Repo is PUBLIC** — user knows; flip to
  private in Settings → Danger Zone if they ask.
- **OpenAI key was rotated by the user on 08-23** (old key dead, new one in `.env`).
- History: `4a80869` audit checkpoint → `74f852d` repair session (see REPAIR_REPORT_2026-08-21.md)
  → `c27a2d9` user upload → merge + this handoff.

## Next session: do these first

1. **Delete `flask_app/.env.backup_*`** — user's own notes ask for this; it holds the OLD
   (revoked) OpenAI key. Confirm with user, delete, verify it was never committed (it wasn't —
   `.env.*` is gitignored).
2. **Project #20090 — "Beginner's Guide to Container Gardening."** The user's chosen priority:
   closest product to sellable. A prior agent was repairing its Ebook PDF pipeline. Open the app
   (`python app.py` from flask_app; port 5000, autoPort fallback), open project 20090, check the
   PDF state end to end (preview → export → download → open the actual PDF).
3. Re-run `preflight_check.py` before and after any change (project rule: never accept work on red).

## Open decisions (still owned by the user, unchanged from repair report §4)

- Payments: build real checkout vs. remove the fake Free/Starter/Pro UI ("Checkout coming soon!" stub).
- Purge 1.5 GB projects.db (14k mostly-QA rows) + 6.2 GB exports/ — destructive, needs a backup + user OK.
- Move the tree out of OneDrive sync (SQLite corruption risk).
- Archive ~150 loose debug_*/_swap_* scripts in flask_app root.
- spelling_worksheet stays hidden — it has 4 real content defects (see REPAIR_REPORT §3), not just a missing test.

## Working agreements with this user

- Audit/report and fixes can be separate sessions; user likes watching work live in the Chrome
  browser drive — use claude-in-chrome tools and show the result on screen.
- Commit + push to GitHub at the end of each work session (remote is wired; pull first — the
  user sometimes uploads files via the GitHub website).
- Their own running log is `Factory_Session_Notes_*.md` — read the newest one at session start,
  and remind them to update it at session end.
