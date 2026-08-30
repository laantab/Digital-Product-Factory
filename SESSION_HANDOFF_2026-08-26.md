# Session Handoff — 2026-08-26 (supersedes 2026-08-25 only in date; no code work)

**Start a new session with:** "Read flask_app/SESSION_HANDOFF_2026-08-26.md and continue."

---

## PICK UP HERE — owner is setting up a real domain, paused mid-task

The owner is in the middle of activating the Lemon Squeezy store for live
payments (see "What the screenshot showed" below) and hit the **website
location** field on Lemon Squeezy's business-details form. We determined the
Factory has **no stable public URL** — `FACTORY_PUBLIC_URL` in `.env` is
still the free cloudflared *quick* tunnel
(`https://arguments-enormous-rivers-glasses.trycloudflare.com`), which is
randomly generated and temporary, not something to put on a payment
processor's business record. No registered domain exists anywhere in the
repo/config. The owner paused this session to go set up a real domain before
continuing the Lemon Squeezy form.

**Next session: ask whether the domain is set up yet.** If yes, and they want
to wire it to the app, that means: point the domain at a **named** cloudflare
tunnel (not a quick tunnel — those aren't stable across restarts), then
update `FACTORY_PUBLIC_URL` in `.env`, update the webhook URL in the Lemon
Squeezy dashboard to match (see `services/billing/providers.py` for the API
way to do this, no helper script yet), and restart the app. Then they can go
back and finish the Lemon Squeezy activation form with a real website URL.

No code was touched this session. Everything below is otherwise unchanged
from before.

## Nothing changed on the app/repo side this session — read 2026-08-25 for actual state

This session did no code work. The user shared one screenshot of the Lemon
Squeezy dashboard (Home view, store "Digital Product..." — 397800 Digital
Product Factory AI) and asked to hand off immediately. For everything
substantive — billing status, the two planner product types, open owner
decisions — `SESSION_HANDOFF_2026-08-25.md` is still accurate and current;
nothing in it is stale as of this handoff.

## What the screenshot showed (informational only, not verified via API)

- Period 27 Jul – 26 Aug, 2026, **Test mode ON**.
- All revenue: **$39.00** (same as "last period," i.e. unchanged since the
  prior comparison window) — consistent with the one test purchase made and
  then cancelled during the 2026-08-25 session.
- New orders: 0, new order revenue: $0.00, avg order revenue: $0.00 for the
  period — i.e. no fresh orders landed in this specific 30-day window shown.
- A banner prompts "Fill out your business details to activate your store
  and accept live payments" — **the store has not been activated for live
  payments yet**. Worth flagging to the owner as a prerequisite before any
  real (non-test-mode) transaction can occur.

No API calls were made to confirm any of the above; it is read directly off
the dashboard screenshot the user shared.

## Everything else — unchanged from 2026-08-25

See that file in full for: billing architecture, webhook fix, Founder seat
count (100/100), repo state (v1.3.0 local, 1 commit ahead of origin/main,
not pushed), and standing open items (Tavily/Pexels key rotation, real user
accounts, plan-limit enforcement, DB purge, OneDrive move, repo visibility).
