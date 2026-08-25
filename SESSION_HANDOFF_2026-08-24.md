# Session Handoff — 2026-08-24 evening (supersedes the morning 2026-08-24 handoff)

**Start a new session with:** "Read flask_app/SESSION_HANDOFF_2026-08-24.md and continue."

## State right now

- **Release gate GREEN: 928 tests**, 0 failures, 0 errors, 0 skipped, 0 paid API calls.
- App now has a version number: `APP_VERSION` in `app.py`, shown as a small footer
  (bottom-left of the sidebar, e.g. "v1.2.0") in `templates/index.html`. Bump it by hand
  and `git tag -a vX.Y.Z` with each real change — that's the standing convention now.
- Currently tagged and pushed: `v1.0.0` → `v1.1.0` → `v1.2.0` (latest = `53cd5e8`).
- Live dev server: started via `.venv/Scripts/python.exe _run_factory_5055.py` on
  `127.0.0.1:5055` (`debug=False, use_reloader=False` — **must be manually killed and
  restarted after every code change**, it will NOT pick up edits on its own). Find it with
  `Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where CommandLine -like
  '*_run_factory_5055.py*'`, kill with `taskkill /PID <id> /F`, relaunch the same way.

## What happened this session (in order)

1. Confirmed the Editor-in-Chief gate is live and wired into `/export-product`.
2. Owner reviewed project **#14626** ("How to keep your teen safe online") and **#1961**
   and found both had a flat vector-icon placeholder cover that scored 10/10 on cover
   quality — a real rubber-stamp gap. Root-caused and fixed 3 systemic Editor-in-Chief
   bugs (commit `94c22c6`, still the most important commit this session):
   - Added `check_cover_is_photo_backed` — a cover with no real photo now blocks.
   - Fixed a word-boundary substring bug (`"dance"` matching inside `"guidance"`, etc.)
     in `services/ebook_visual_match.py::classify_ebook_subject`.
   - Fixed Table-of-Contents/front-matter pages being wrongly required to carry a
     content photo (`services/ebook_visual_requirements.py`).
   - Rebuilt real Pexels photo covers for #14626 and #1961, manually re-synced their
     stale `img_cover.png` and `preview_html` (the sanctioned pipeline does this
     automatically; only needed manual repair because these two records predate it).
3. Added the version marker described above (`v1.0.0`).
4. Owner reported 3 saved books ("photography business" #4249, "gardening" #20090,
   "deep sea ocean" #17365 coloring book) looked like they'd lost their images. **Investigated
   and confirmed the underlying data/files/exported PDFs were never actually missing
   anything** — re-rendered pages straight from disk and every image was present. The real
   cause was the app being slow/stalling while loading these screens (see #6).
5. Owner spotted a raw "View Technical Details" panel (sha256 hashes, `needs_user_review`
   codes, `package_id`/`contamination` JSON) on the customer-facing visuals-review screen
   and said the customer should never see that. Removed all 3 occurrences of this pattern
   app.js-wide (visuals-review stage, finished-product screen, pre-save review screen).
   `v1.1.0`.
6. Root-caused and fixed the real perf bug behind #4 above:
   - `visual_review_payload()` computed a **second, full-resolution copy** of every chapter
     photo (`preview_data_uri`, 100–250KB each) that `app.js` never once rendered — only
     the small `thumb_data_uri` was ever used. Removed it.
     `services/ebook_visual_pipeline.py`.
   - The plain `/projects` list endpoint (Dashboard, Saved Projects) shipped the full
     `preview_html`/`ebook_preview_html`/`content` blobs for every project — including
     `ebook_workspace`-flagged ones, which *never* render that list-embedded copy (they
     always do a fresh `GET /ebook-workspace/<id>` fetch on Open). Added
     `_slim_workspace_list_item()` in `app.py` to blank those 3 fields **only** for
     workspace-flagged items; non-workspace items are untouched since they genuinely
     need the inline copy.
   - Measured: `/ebook-workspace/4249` response 1.22MB → 549KB. A 5-item `/projects` list
     3.14MB → 2.1MB. Verified live in a clean browser tab: opening the exact screen the
     owner screenshotted went from "never finishes loading" to ~1.3 seconds, images intact.
   - Caveat for whoever picks this up: my *own* repeated automated test clicks in one
     reused browser tab produced a much worse (45–60s) freeze than a real user would ever
     see — that was leftover/stuck requests piling up in that one tab, not a server bug.
     Always retest perf claims in a **fresh tab**.
   `v1.2.0`.

## Answered directly for the owner this session (don't re-litigate)

- **"Does the Editor-in-Chief catch a bad cover?"** No before this session, yes now
  (`check_cover_is_photo_backed`).
- **"Isn't Editor-in-Chief supposed to catch [images looking missing]?"** No — that gate
  reviews the *built artifact* at export time (which was always complete/correct for all
  three books); a slow/stalled *browser render* after the fact is a different failure
  surface it has no visibility into. Now fixed anyway (item 6 above).
- **AI-cover-generation permission the owner remembered granting:** it's a real, gated
  fallback in the legacy path (`services/ebook_customer_path.py::_generate_ai_cover_candidate`,
  gated by `data.visuals_authorized` + `data.visual_budget_cap_usd > 0`) — but neither
  #14626 nor #1961 ever had those fields set, so it was never eligible to fire for them.
  The *other* "Optional AI cover" control visible in the workspace UI is a permanently
  disabled stub ("not configured") — unrelated, no provider wired up.

## Standing items, still open (unchanged from prior handoffs, not touched this session)

- Rotate the Tavily and Pexels API keys.
- Owner decisions still pending: payments stub, 1.5 GB DB purge, OneDrive move, public
  repo visibility.
- `exports/` and `projects.db` are gitignored — PDFs, images, project rows are LOCAL ONLY,
  never pushed to GitHub. Only code and docs are pushed.
- Never accept work on a red gate. Run `preflight_check.py` before and after every change.
- User does audits in Fable / fixes in Opus (established workflow pattern).
