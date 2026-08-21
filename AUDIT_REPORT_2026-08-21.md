# Digital Product Factory — Full Audit Report (2026-08-21)

Audit performed by driving the live app in Chrome (http://localhost:50401, Flask dev server from
`flask_app/app.py`, port 5000 was occupied so autoPort picked 50401), plus code inspection and a
full run of the enforced release gate (`preflight_check.py`).

---

## 1. What works (verified live)

- All 11 sidebar views render without JS errors: Dashboard, Saved Projects, Factory Market
  Advantage, Product Planning, Product Factory, Ebook Builder, Visual Review, Publishing Studio,
  Platform Packages, Ad Generator, Subscription.
- Product Factory offers 5 working builders: Ebook, Coloring Book, Word Search Book, Crossword
  Puzzle Book, Math Worksheet — forms are complete and well-structured.
- Saved Projects list, per-project Download PDF / Download ZIP buttons work; the download audit
  log shows validated downloads (e.g. Kettlebell ebook: 34-page PDF passed validation).
- Publishing Studio and Platform Packages dropdowns populate; publishing templates load.
- AI integrations are configured and ready: `/coloring-ai-status` → ready (gpt-image-1);
  `/pexels-status` → connected. Tavily key present.
- Standalone `/word-search-builder/` page loads (200).
- Release gate: **884 of 885 tests pass** (see §3).

## 2. Bugs found (live, reproducible)

1. **`/crossword-builder/` returns 500** — `jinja2.TemplateNotFound: crossword_builder.html`.
   `routes/crossword_builder.py:112` renders a template that does not exist in
   `flask_app/templates/` (only `index.html`, `cover_editor.html`, `word_search_builder.html`
   exist). The `flask_app/crossword_builder/` directory is EMPTY. The standalone crossword
   builder page was never created (or was lost). Fix: create the template or remove/redirect
   the blueprint page route.

2. **Dashboard "Launch Package" card is a dead button.** `templates/index.html:126` does
   `document.getElementById('launchDashBtn') && ...click()`, but `launchDashBtn` does not exist
   anywhere in the codebase (grep confirms). Clicking the card silently does nothing.
   Dashboard also shows "0 Launch Packages generated" with no working path from the dashboard.

3. **Dashboard advertises "Spelling Worksheet" but it is not buildable.** The Popular Product
   Types row includes a Spelling Worksheet tile; clicking it routes to Product Factory where the
   type is hidden (`hidden: true` in `static/js/app.js` ~line 240). Backend guard in `app.py`
   (`/generate-product`, `_HIDDEN_PRODUCT_TYPES`) rejects it with "not ready yet". Either finish
   it (see §4) or remove the dashboard tile.

4. **"Open" on a saved project renders the product below the fold with no scroll.** Opening
   e.g. the Kettlebell ebook switches to Product Factory and renders the full product *below*
   the product-type picker and an unrelated blank form (whatever type was last selected —
   Word Search in my test). No auto-scroll, no visual feedback → looks completely broken until
   you scroll ~2 screens down. Fix: scroll the rendered product into view (or hide the blank
   form when reopening a finished product).

5. **Checkout is a stub.** "Upgrade to Starter"/"Upgrade to Pro" show a toast:
   "Checkout coming soon!" (`index.html:896,913`). There is no payment integration, no auth,
   no user accounts; "Plan: Starter" in the header is hardcoded while the pricing page shows
   Free as "Current Plan" (inconsistent). The whole subscription system is cosmetic.

6. **Dropdowns are polluted with internal QA/test records.** Publishing Studio's project
   dropdown (52KB of options) and Platform Packages' product dropdown are full of duplicates of
   "Customer Real Product Check", "Cover Guided Step Project", "Thunder Volt Bank Rescue…"
   (dozens of copies). Saved Projects view filters to customer-visible records, but these two
   dropdowns do not apply the same filter.

7. *(Minor)* "Account" header button just goes to Subscription — there is no account page.
8. *(Minor)* While Publishing Studio is open the SPA re-fetches `/projects?factory_sources=1`
   roughly once per second (visible in server logs) — wasteful polling against a 14k-row DB.

## 3. Release gate status

`preflight_check.py` → **FAIL (exit 1): 884 passed, 1 error in 5m34s.**
The single error is environmental, not a code failure:

- `tests/test_ebook_real_browser_customer_path.py` → `ModuleNotFoundError: No module named
  'playwright'`. Playwright is pinned in `requirements-dev.txt` (1.52.0) but is not installed
  in `flask_app/.venv`.

Fix: `.venv\Scripts\python -m pip install -r requirements-dev.txt` then
`.venv\Scripts\python -m playwright install chromium`, and re-run the gate. Until then the
project's own rule ("do not release or accept changes while the gate is red") is unmet.

## 4. Features scaffolded but unfinished (the "to finish the app" list)

Five product types have complete form definitions in `static/js/app.js` but are hidden from the
public picker AND blocked server-side in `/generate-product` (`_HIDDEN_PRODUCT_TYPES`,
app.py:1527):

| Type | State |
|---|---|
| `spelling_worksheet` | Full backend service exists (`services/spelling_worksheet/`), wired into packaging, KDP preflight, QA agent, puzzle_plan. Hidden ONLY because there is no end-to-end acceptance contract in `tests/acceptance_manifest.json`. Closest to done — needs acceptance tests + unhide. |
| `planner` | Form defined; no dedicated service package found. |
| `flip_book` | Form defined; no dedicated service package found. |
| `cover_design` | Form defined as standalone product; cover engine exists but not exposed as a product. |
| `marketing_kit` | Form defined; overlaps with Ad Generator / promotion packages. |

Also unfinished:
- **Payments/accounts** (see §2.5): Stripe (or similar) + real plan enforcement, or strip the
  Free/Starter/Pro UI entirely for a single-user tool.
- **Launch Package from dashboard** (see §2.2).
- **Crossword standalone builder page** (see §2.1).

## 5. Data, disk, and operational risks

- `flask_app/projects.db` is **1.5 GB with 14,011 rows** (12,094 ebooks) — overwhelmingly QA/test
  runs; PDF bytes are stored as blobs inside project rows. Saved Projects UI shows only the
  last 10 customer records, but the DB carries everything.
- Backups everywhere: `projects_BACKUP_BEFORE_HARD_SAVED_PROJECTS_CLEANUP.db` (1.0 GB, inside
  flask_app), `projects_PRE_TEST_CLEANUP_BACKUP_20260820.db` (1.5 GB, repo root), plus a keep10
  backup. `flask_app/exports/` is **6.2 GB**. Total working tree ≈ **10.5 GB**.
- The whole tree lives under **OneDrive Desktop sync**. OneDrive syncing a live SQLite DB (with
  -shm/-wal files) is a known corruption/locking risk and is uploading ~10 GB of test artifacts.
  Recommendation: move the project (or at least the DBs/exports) out of OneDrive, or exclude
  those paths from sync.
- **Not a git repository.** `Initialize_Factory_Git.bat` exists but was never run. There is no
  version control safety net. (`.gitignore` is already prepared and correctly excludes
  `.env`, `*.db`, `exports/`.)
- **Live API keys sit in `flask_app/.env` in plaintext** (OpenAI, Tavily, Pexels) inside a
  OneDrive-synced folder. Rotate the OpenAI key at minimum, and keep `.env` out of any ZIP/git
  (gitignore already handles git).
- **Dev server posture:** `app.run(host="0.0.0.0", debug=True)` — Werkzeug debugger (with PIN)
  exposed to the whole LAN, `/admin/backup-db` unauthenticated, Tailwind loaded from CDN with a
  console warning ("should not be used in production"). Fine for local use; must change before
  any deployment (waitress/gunicorn, debug off, bind 127.0.0.1, auth on admin routes, build
  Tailwind).

## 6. Current customer-visible data state

Of the 6 customer projects: 3 ebooks are stuck in "Needs correction." status ("How to start a
profitable event photography business…", "How to keep your teen safe online", "Can the Average
Joe Make money online in 2026" — the last has no PDF/ZIP buttons at all). If these are meant to
ship, they need to be run through the correction flow; otherwise delete them.

## 7. Recommended work order (for the fix session)

1. Install dev deps (`requirements-dev.txt` + playwright browsers) → re-run the gate → green
   baseline (884→885 pass).
2. Run `Initialize_Factory_Git.bat` to get the first recoverable checkpoint (gate must be green
   first per the project's own workflow).
3. Fix the 4 UI bugs: dead Launch Package card, Open-below-the-fold, crossword-builder 500,
   Spelling Worksheet tile (hide or finish).
4. Filter test/QA records out of Publishing Studio + Platform Packages dropdowns (reuse the
   Saved Projects customer-visible filter).
5. Decide the monetization story: implement checkout + real plan gating, or remove the
   Free/Starter/Pro surface.
6. Finish `spelling_worksheet` (acceptance contract + unhide) — cheapest new product win.
7. Data hygiene: archive/purge QA rows from projects.db (there is already
   `cleanup_test_records.py` / hard-cleanup test machinery), prune exports/, move DB + exports
   out of OneDrive.
8. Clean the ~150 loose debug/one-off scripts (`debug_*.py`, `_swap_*.py`, `_diag_*.py`, etc.)
   out of `flask_app/` root into a `scripts/archive/` folder — they drown the real code.
9. Production posture when ready to deploy (WSGI server, debug off, auth, built Tailwind).
