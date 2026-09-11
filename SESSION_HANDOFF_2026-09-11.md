# Session Handoff — 2026-09-11 (supersedes 2026-09-09)

**Start a new session with:** "Read CLAUDE.md and the newest handoff first. Confirm the
current Factory path, current Git branch, current commit, and that the working tree is
clean before making any changes."

---

## Start here

The Factory is on **v1.7.1** (private-beta invite gate + Render first-boot fix).
Full Windows release gate on this commit: **2,613 tests, 0 failures, 0 errors,
0 skipped, 0 paid API calls.** Fast Stability Gate: 139 passed, 595 subtests.

Strategy has moved from "build features" to "put the Factory in front of ten paying
Founding Members." The plan is in `Factory Control Center\Marketing\Digital Product
Factory Pro - Marketing & Launch Master Plan v2 (Execution Edition).md` (also a Google
Doc). Today executed **Day 1** of that plan. Read Part 18 of it before doing anything else.

## What was done today (2026-09-11)

1. **Audit (read-only)** of the whole product for the v2 plan. Key facts, all verified:
   - 8 builders live; 6 are zero-cost (planners, puzzles, worksheets).
   - Ebook: 12 real projects in the DB, 1 reached export, and it shows "Needs correction."
     Cost caps in code ≈ $2.35–3.10 per book. Founder-assisted only at beta.
   - Billing layer (Lemon Squeezy + Stripe) is built and tested but switched off;
     no user accounts exist; Free-plan cap is displayed, not enforced.
   - `digitalproductfactorypro.com` is live on **Render free tier** (gunicorn behind
     Cloudflare), running the current build, empty DB, ~93 routes open to anyone,
     ephemeral disk. Whether API keys are set on Render: **UNVERIFIED** (owner to check).
   - Pin Factory Pro v1.3.0 is on GitHub (`laantab/pin-factory-pro`), mock mode only
     (MiniMax keys empty), not wired to the Factory.
2. **Invite-code gate** (`app.py`): when `FACTORY_INVITE_CODE` is set on the host, every
   route except `/static/*`, `/billing/webhook/*` and `/invite` requires the code (cookie,
   `X-Factory-Invite` header, or `?invite=CODE` once → 90-day cookie). Unset → gate off,
   nothing changes. Under `FACTORY_TEST_MODE` the gate is always off; `tests/conftest.py`
   also blanks the variable so a local `.env` value can never gate the suite.
3. **Render first-boot fix** (`database.py::get_conn`): creates the DB's parent directory,
   so `FACTORY_DB_PATH=/var/data/projects.db` works on an empty disk.
4. Tests: `tests/test_invite_gate.py` (14), `tests/test_render_persistence_patch.py` (2);
   both in `acceptance_manifest.json`, the `.bat` gate and the CLAUDE.md gate command.
   `.env.example` documents `FACTORY_INVITE_CODE`.
5. **Beta Launch Kit** (no code): `Factory Control Center\Marketing\Beta Launch Kit\`
   — Founders page copy, outreach messages, beta agreement + welcome email, tester
   scorecard + bug log. All drafts; the offer is $149 one-time, 10 seats, 90 days,
   14-day build-or-refund, $29/mo Founder rate locked afterwards.

## Owner actions that unblock the next step (Render dashboard, ~15 minutes)

1. Settings → Instance Type → **Starter**; Settings → Disks → add `factory-data` at
   `/var/data`, 10 GB.
2. Environment → add `FACTORY_DB_PATH=/var/data/projects.db`,
   `FACTORY_EXPORTS_DIR=/var/data/exports`, `FACTORY_INVITE_CODE=<a phrase>`.
3. While there, note whether OPENAI / TAVILY / PEXELS keys are set (reminder item).
4. Deploy this commit. Then verify: open the domain → invite page appears; enter the code;
   create a product; Manual Deploy → Restart; Saved Projects still lists it and its
   download still serves.
5. Cloudflare → Email Routing → forward `support@digitalproductfactorypro.com` to Gmail.
6. New Tavily and Pexels keys (rotation has been open since August).

## Still open

- Push `v1.7.1` to `origin/main` (owner has not yet said to push this commit).
- Render steps above; confirm live with the verification in step 4.
- Day 3 of the v2 plan: Founding Member product in Lemon Squeezy, first 10 messages.
- Day 4: MiniMax keys into Pin Factory Pro; 50 real pins.
- Rescued branch `onedrive-workspace-phase-a`: can be archived at owner's discretion.
- Plain-language manuscript panel (held by owner). Cover-editor console error (harmless).
- Per-member invite codes, real accounts, plan-limit enforcement: Month 2, after
  paying customers exist (v2 plan, Part 17).
