# Session Handoff — 2026-08-25 (supersedes 2026-08-24)

**Start a new session with:** "Read flask_app/SESSION_HANDOFF_2026-08-25.md and continue."

---

# PICK UP HERE — Billing is DONE and verified end to end with a real transaction

Updated 2026-08-26 evening. **Every piece of the billing system has now been
proven working with a real Lemon Squeezy test-mode purchase, not just code
review or a dry run.** This closes out the multi-session billing effort that
started 2026-08-25. Everything below "## 2. Billing" in this file is now
historical background — read it for the *reasoning*, but for *current status*
trust this section, not that one (it still says "NOT connected", which is
stale).

## What was proven, live, this session

Full loop, checked at every step via the Lemon Squeezy API and the app's own
DB, not just the UI:

1. **All 4 product images fixed.** Root cause: clicking the visible "browse"
   button opens the OS's native file picker, which browser automation cannot
   see or click — so every earlier upload attempt silently did nothing. Fixed
   by uploading directly to the underlying file input element instead (see
   `mcp__claude-in-chrome__file_upload` in this session's transcript). Also
   found and deleted stray copies of each image sitting in the wrong section
   (**Files** — deliverables — instead of **Media** — the checkout thumbnail).
   All 4 confirmed via `large_thumb_url` on the product record.
2. **A real test purchase completed.** Founder Launch, $29/mo, test card
   `4242 4242 4242 4242`, real Lemon Squeezy order and subscription created.
3. **Found and fixed a real bug: the webhook pointed at the wrong URL.**
   `https://testme.com/webhooks` — a leftover placeholder from 2026-06-05, not
   the tunnel. Lemon Squeezy tried to deliver and got nowhere; the purchase
   above never activated until manually reconciled from Lemon Squeezy's own
   record. **Fixed via the API**: webhook URL now points at
   `<FACTORY_PUBLIC_URL>/billing/webhook/lemonsqueezy`, secret resynced to
   match `.env`, events corrected to the documented 5.
4. **Verified the fix holds, not just patched around:** cancelled that same
   test subscription via the API, and this time — with no manual
   intervention — the `subscription_cancelled` webhook arrived, was recorded
   in `billing_events`, and the founder seat released itself (99 → 100)
   automatically. That second event landing on its own, unassisted, is the
   proof the fix is real.
5. **Fixed a second real bug found along the way**, unrelated to the webhook
   URL: `services/billing/providers.py::lemon_create_checkout` sent
   `"email": customer_email or None`, which Lemon Squeezy's API rejects
   ("must be a valid email address") whenever the key is present at all, even
   as JSON `null`. Fixed to omit the key entirely when there is no email on
   file. Covered by 4 new tests in `LemonCheckoutPayloadTests` (`tests/test_billing.py`)
   that pin the exact payload shape sent to `POST /checkouts` — this class did
   not exist before and is why nothing had caught it.

## Current live state (checked just before this handoff)

- App (5055) and cloudflared tunnel both up, same URL as the last several
  handoffs: `https://arguments-enormous-rivers-glasses.trycloudflare.com`.
  Restart commands unchanged if they've died — see the historical section
  below. **If the tunnel URL changes, three things need updating**:
  `FACTORY_PUBLIC_URL` in `.env`, the webhook URL in the Lemon Squeezy
  dashboard (now editable via API too — see `services/billing/providers.py`,
  no helper script for it yet), and restart the app.
- Founder seats: **100/100** (the test purchase was cleanly cancelled).
- `checkout_available: true`. All 4 products have images and correct prices.
- The webhook is correctly configured — confirm with:
  ```python
  from services.billing import providers as PR
  b = PR._lemon_request('GET', '/webhooks?filter[store_id]=397800')
  for w in b.get('data') or []:
      print((w.get('attributes') or {}).get('url'))
  ```
  Should print the tunnel URL, not `testme.com`. If the tunnel URL has since
  changed and this still shows the old one, that is the very bug from item 3
  above recurring — fix it the same way.

## Real gaps, not oversights — each needs an owner decision

None of these block what exists today; each is a deliberate stopping point.

1. **No user accounts.** The browser holds an anonymous `account_ref` in
   `localStorage`. It identifies a subscription but authenticates nothing —
   clearing browser data loses the link to a paid subscription. Should land
   before taking money from strangers who aren't the owner testing on their
   own machine.
2. **Plan limits are computed but not enforced.** `usage_payload()` correctly
   knows the cap and current usage; `/generate-product` does not check it.
   Every plan is effectively unlimited in practice right now.
3. **The public URL is a temporary quick tunnel.** Fine for testing,
   needs a real domain (or at minimum a stable named tunnel) before anyone
   outside this machine can actually subscribe.

## Traps, still true

- **Two Lemon Squeezy stores exist**: `397800 Digital Product Factory AI`
  (real, everything belongs here) and `145172 Tryme` (empty, ignore).
- **ngrok is a dead end** here: account needs agent >= 3.20, winget ships
  3.3.1, self-update gets blocked by Windows Defender. Do not add an
  antivirus exclusion — cloudflared works, keep using it.
- **Never type the owner's keys, tokens, or card details.** They enter those
  themselves; verify results via the API/DB instead. This was tested for real
  this session — the owner filled in the test card personally while I only
  focused the field.
- Owner's ngrok authtoken was exposed in a screenshot two sessions ago; unclear
  if they revoked it. Low urgency since ngrok is unused, but worth a check.
- The `1316638`/`1316646`/`1318410`/`1316656` product ids and the `2058724`
  etc. variant ids are already correct in `.env` — do not re-run
  `scripts/lemonsqueezy_ids.py` unless a product is actually added or changed,
  it is safe but unnecessary.

## Repo state — verified purchase, but NOTHING pushed, gate not re-run

- Uncommitted: `plans.py`, `providers.py` (new fix this session),
  `.env.example`, `docs/BILLING_SETUP.md`, `static/js/app.js`,
  `templates/index.html`, `tests/test_billing.py`, this handoff, plus new
  `docs/BILLING_COPY.md`, `scripts/lemonsqueezy_ids.py`,
  `scripts/setup_billing_keys.ps1`, `scripts/generate_plan_images.py`,
  `Setup_Billing_Keys.bat`.
- `tests/test_billing.py` passes (59, up from 55 — added
  `LemonCheckoutPayloadTests`), but **`preflight_check.py` has still not been
  run since any of this session's changes** — run the full gate before
  committing anything.
- `56b72b8` (v1.3.0) remains **local only, 1 commit ahead of origin/main**.
  Repo is public; owner has deliberately not pushed unlaunched pricing.
  **Do not push without asking** — this is now more true than ever, since a
  push would also publish a real (if cancelled) test transaction's plumbing.

---

## State right now

- **Release gate GREEN: 1016 tests**, 0 failures, 0 errors, 0 skipped, 0 paid API calls.
  (928 at the start of the session, + 37 planner, + 55 billing, − 4 net from re-counting
  parametrised cases.) Baseline was re-confirmed green at 928 *before* any change.
- **`APP_VERSION` is now `1.3.0`** (`app.py:6`, shown bottom-left of the sidebar).
- Two new shipped product types: **Faith Planner** and **Budget Planner**.
- A complete **billing layer** — plan catalog, checkout, webhooks, founder cohort —
  built and tested, but **not connected to any account**. No Stripe or Lemon Squeezy
  API call has ever been made from this machine.
- Dev servers: the owner's `_run_factory_5055.py` on 127.0.0.1:5055 is untouched and
  still running. This session used its own `_run_factory_5077.py` on :5077 (new
  `factory-5077` entry in `.claude/launch.json`) so the two never collided. Both run
  `use_reloader=False` — **kill and relaunch after every code change**.

---

## 1. Faith Planner and Budget Planner

Both are **deterministic**: no AI call, no image credits, same input → same PDF.
A 60-page planner builds in about 150–400 ms.

New code:

- `services/planner/content.py` — the written material (reading plan, budgeting
  methods, prayer method, emergency-fund guidance, etc.)
- `services/planner/builder.py` — page planner; emits a typed page list
- `services/planner/renderer.py` — ReportLab drawing for each page kind
- `services/planner/pdf_builder.py` — orchestration, mirrors `math_worksheet`
- `services/editor_in_chief_planner.py` — the review gate (see below)

Wiring: `services/product.py` (builders + labels + routing), `services/packaging.py`
(export branch), `app.py` (export gate), `static/js/app.js` (picker),
`services/factory_advantage.py` (Market Advantage routing),
`services/quality/cover_eligibility_agent.py` (explicit planner branch).

The old generic `planner` type is **still hidden** and unchanged. These are separate,
first-class types.

### The Editor-in-Chief could not be reused as-is, and that matters

`review_ebook` would block every planner forever, for two reasons that are not defects:

- A planner is fifty near-identical worksheet pages **on purpose**, so
  `check_self_duplication` over the PDF text reports a hundred duplicate paragraphs.
  `editor_in_chief_planner` therefore checks duplication over the *instructional prose
  only*, and records the exclusion in `checks_skipped`.
- A planner has **no photographs**, so photo-backed cover, image resolution, and
  safety-sensitive visual verification have nothing to run against. Those categories
  are excluded from scoring rather than scored 10 for free, and each is listed in
  `checks_skipped` with a reason.

Three checks exist only for planners: contents entries that point at the wrong page,
a cover that advertises a page count the book does not have, and a "planner" that is
blank grids with no instruction in it.

**Both planners currently score EDITOR-IN-CHIEF PASS 10.0 with zero findings**, verified
through the real customer path (generate → save → export → download).

### Things the gate caught that were genuinely wrong

Worth knowing, because they are the reason to trust the 10.0:

1. **The first draft was too thin.** 330 words of instruction across 60 pages was
   blocked as "a pad of blank forms rather than a book". Fixed by writing three more
   instructional pages, not by lowering the floor. Now ~1040 words.
2. **The budgeting-methods page never used the word "budget."** Flagged as off-topic.
   The copy was genuinely weak and was rewritten.
3. **Packaging shipped the wrong file.** `build_product_export` had no planner branch,
   so the generic ebook path rendered a PDF from `data["content"]` — which a planner
   leaves empty — and the download pointer landed on a near-blank `ebook.pdf`. The
   customer would have downloaded a broken book. Fixed with a planner packaging branch
   plus a page-count regression test.
4. **My own contents check was toothless.** It compared each page against its own
   planned title, which is true by construction. Rewritten to compare the contents
   *label* against the page it points at; a wrong-page entry is now caught.

If you change planner content or layout, re-run the adversarial probes in
`tests/test_planner_products.py::PlannerEditorInChiefTests` — the negative tests are
the ones that matter.

---

## 2. Billing (built, NOT connected)

Read `docs/BILLING_SETUP.md` first — it has the full walkthrough and the reasoning.

### Pricing decided

| Plan | Monthly | Annual | Products / month |
|---|---|---|---|
| Free | $0 | — | 3 |
| Starter | $9.99 | $99 | 10 |
| **Pro** (Most Popular) | **$24.99** | **$249** | 50 |
| Studio | $39.99 | $399 | 200 |
| **Founder's Plan** | — | **$119, locked for life** | 50 (Pro-level) |

Prices live only in `services/billing/plans.py`. The pricing page reads them, and
checkout re-checks the provider's amount against them and **refuses** on disagreement.

Two judgement calls you may want to overrule:

- **Every paid tier is metered.** Each product costs real money to make, so "unlimited"
  at $9.99 means the heaviest users pay the least and cost the most. The caps are high
  enough that a normal seller never notices.
- **The Founder's Plan is $119/year, not a lifetime deal.** A lifetime deal takes cash
  once and creates a cost that recurs forever, which is a poor trade for a product with
  per-use costs. $119/yr locked for life is under half of Pro and still pays for itself
  annually. It started at $99 and was moved up because $99 was *identical to Starter
  annual*, which flattened the offer and left Starter annual pointless. If you want a
  true lifetime deal, that is a number in `plans.py` plus a copy change, not a rebuild.

### Founder cohort safety

The cap is enforced **in SQL inside an IMMEDIATE transaction**, not by hiding a button,
so two simultaneous buyers cannot both be sold seat 100. A seat is reserved at checkout,
auto-released after 30 minutes if abandoned, confirmed only by a signature-verified
webhook, and returned to the pool on cancellation. All of that is tested at the
boundary.

### New code

`services/billing/{plans,store,providers,service}.py`, routes in `app.py`
(`/billing/plans`, `/billing/subscription`, `/billing/account`, `/billing/checkout`,
two webhook endpoints), the pricing UI in `templates/index.html` + `static/js/app.js`,
`scripts/setup_billing_products.py`, `docs/BILLING_SETUP.md`, and an expanded
`.env.example`.

Built on `requests`, not the Stripe SDK — no new runtime dependency, and the gate stays
green offline. `requirements.txt` is unchanged.

### To turn it on (owner only — needs your credentials)

1. Put `STRIPE_SECRET_KEY=sk_test_...` in `.env`.
2. `.venv/Scripts/python.exe scripts/setup_billing_products.py` (dry run, writes nothing).
3. Same command with `--apply` to create the products, then paste the printed
   `STRIPE_PRICE_*` lines into `.env`.
4. Add the webhook endpoint and put its signing secret in `STRIPE_WEBHOOK_SECRET`.
5. Restart the server.

The pricing page currently shows live prices with an honest banner saying checkout is
not connected — no buttons that fail when clicked.

### Deliberate gaps — each needs a decision from you

- **No user accounts.** The browser holds an opaque `account_ref` in `localStorage`.
  It identifies a subscription but authenticates nothing, so clearing browser data
  loses the link to a paid subscription. **Real accounts should land before you take
  live payments from strangers.**
- **Entitlements are computed but not enforced.** `usage_payload()` knows the cap and
  the usage; `/generate-product` does not check it yet. Turning enforcement on should be
  a dated decision, not a surprise.
- No customer billing portal, no tax handling, no proration/plan switching.

---

## Standing items, still open

- **Rotate the Tavily and Pexels API keys** — the owner asked to hold off this session.
- Owner decisions pending: 1.5 GB DB purge, OneDrive move, public repo visibility.
- `exports/` and `projects.db` are gitignored — PDFs and project rows are LOCAL ONLY.
- Never accept work on a red gate. Run `preflight_check.py` before and after changes.
- User does audits in Fable / fixes in Opus.
- Smoke-test project rows created this session (21245–21249) were deleted; 21244 was
  rejected before creation.
