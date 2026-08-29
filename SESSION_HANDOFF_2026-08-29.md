# Session Handoff — 2026-08-29 (supersedes SESSION_HANDOFF_2026-08-24.md)

**Start a new session with:** "Read SESSION_HANDOFF_2026-08-29.md and continue."

## This week at a glance

- **08-21** (Fable, audit session): Drove the app live, ran the release gate (884/1 error —
  playwright missing locally), wrote `AUDIT_REPORT_2026-08-21.md`. No fixes made, audit only.
- **08-23** (repair session): Merged the user's web upload, gate green **885/885**. Repo confirmed
  live and public on GitHub (`laantab/Digital-Product-Factory`).
- **08-24** (fix session): Fixed 3 systemic Editor-in-Chief gaps (bad-cover detection, a
  word-boundary bug, front-matter photo requirement), removed customer-facing raw technical
  details from the UI, fixed a real perf bug (slow-loading saved projects). App versioned
  `v1.0.0` → `v1.2.0`. Gate green **928/928**.
- **08-28/29** (this session — domain/hosting setup): No hosting existed for the purchased
  domain. Investigated, confirmed state, and started wiring up deployment. Details below.

## State right now

- **App:** `v1.2.0`, release gate last green 08-24 (928 tests). Not re-run this session (no code
  logic touched, only `requirements.txt`).
- **Domain:** `digitalproductfactorypro.com` — registered on Namecheap (Aug 27 2026 → Aug 27
  2027, auto-renew on, WithheldForPrivacy on). Nameservers already switched to **Custom DNS
  pointed at Cloudflare** (`lilith.ns.cloudflare.com` / `thomas.ns.cloudflare.com`); the zone is
  active in Cloudflare. This part is done — nothing left to do in Namecheap.
- **Hosting: none live yet.** This is the actual gap that stalled domain setup — Cloudflare has
  no DNS record pointing anywhere because nothing has ever been deployed. The app only ever ran
  as a local Flask dev server.
- **In progress — Render:**
  - Opened draft PR **[#1](https://github.com/laantab/Digital-Product-Factory/pull/1)**: adds
    `gunicorn` to `requirements.txt` so the app can run under a production server instead of the
    Flask dev server. Currently open, draft, clean, no CI configured on the repo, no review
    comments — has been idle waiting on the Render deploy to actually happen.
  - On Render's "Create a new Service" screen, the user first opened **"New Static Site"** by
    mistake — that only serves static files and won't run Python. **Needs to redo under "New Web
    Service"** instead, same repo (`laantab/Digital-Product-Factory`).
- **Known gap to handle before going live:** `projects.db` (SQLite) and `exports/` are gitignored
  and local-only. Render's (and most hosts') default disk is **ephemeral** — wiped on every
  redeploy/restart. The code already supports overriding both locations via env vars
  (`FACTORY_DB_PATH`, `FACTORY_EXPORTS_DIR`), so this just needs a Render **persistent Disk**
  mounted (e.g. `/var/data`) with those two env vars pointed at it — not yet done.

## Next session: do these first

1. On Render: click **"New Web Service"** (not Static Site) → repo
   `laantab/Digital-Product-Factory` → branch `main` (once PR #1 is merged, or the feature branch
   if deploying before merge).
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn app:app --bind 0.0.0.0:$PORT`
2. Add a **persistent Disk** in Render (mount e.g. `/var/data`), then set env vars
   `FACTORY_DB_PATH=/var/data/projects.db` and `FACTORY_EXPORTS_DIR=/var/data/exports`.
3. Add the remaining env vars (real values, from local `.env`): `SECRET_KEY`, `OPENAI_API_KEY`,
   `TAVILY_API_KEY`, `PEXELS_API_KEY`, `AI_INTEGRATIONS_OPENAI_API_KEY`,
   `AI_INTEGRATIONS_OPENAI_BASE_URL`, `FLASK_ENV=production`.
4. Once deployed, take the Render app URL and add the DNS record for
   `digitalproductfactorypro.com` in Cloudflare's DNS Records screen (CNAME to the Render URL, or
   per Render's own custom-domain instructions once the service exists).
5. Take PR #1 out of draft and merge once the deploy is verified working.

## Standing items, still open (carried from prior handoffs, unchanged)

- Rotate the Tavily and Pexels API keys.
- Owner decisions still pending: payments stub (build real checkout vs. remove it), 1.5 GB
  `projects.db` purge, move the tree out of OneDrive sync, public repo visibility.
- Never accept work on a red gate — run `preflight_check.py` before and after any change.

## Notes for whoever picks this up

- This session (Claude Code on the web) has **no Chrome/browser access** — Namecheap, Cloudflare,
  and Render screens were driven by the user, with screenshots relayed back for guidance. The
  user's separate **Claude in Chrome** extension (local, in their own browser) can drive these
  UIs directly if handed a precise instruction, but wasn't used this session.
- PR #1 was being watched with periodic background check-ins (CI status / mergeable state /
  review comments) — safe to disregard those check-ins once the PR is merged or closed.
