# Billing setup

The Factory's pricing, checkout, and subscription state are built and tested.
What is **not** done is connecting them to your accounts — that needs your
Stripe and Lemon Squeezy credentials, which only you should ever type. Nothing
in this repo has touched either account.

Until you complete the steps below, the pricing page renders live prices and
says plainly that checkout is not connected. It does not show buttons that
fail when clicked.

---

## What was decided, and why

Four plans, monthly-only, matching the products built by hand in the Lemon
Squeezy dashboard on 2026-08-25:

| Plan | Monthly | Products / month |
|---|---|---|
| Free | $0 | 3 |
| Starter | $19.00 | 10 |
| Founder Launch | $29.00, locked for life, 100 seats | 50 (Pro-level) |
| **Pro** (Most Popular) | **$39.00** | 50 |
| Agency | $99.00 | 200 |

Prices live in `services/billing/plans.py`. That file is the single source of
truth: the pricing page reads it, and checkout re-checks the provider's amount
against it and refuses if they disagree. Because Lemon Squeezy has no API for
creating products, the dashboard is what actually decides these numbers —
`plans.py` was written to match it, not the other way around. If a price ever
changes in the dashboard, change `plans.py` first, or every checkout on that
plan starts failing the price-agreement check.

There are no annual variants right now — all four products are monthly-only.
`plans.py` keeps `annual_cents = 0` rather than removing the concept, so an
annual tier can be turned on later by setting a price, without touching the
pricing page or the checkout code.

**Why every paid tier is metered.** Each finished product costs real money to
make — model calls, sometimes a stock-photo lookup. Unmetered generation on
the cheapest tier means the heaviest users pay the least and cost the most.
The caps are generous enough that a normal seller never notices, and they keep
the bottom of the ladder from being the thing that loses money.

**Why Founder Launch is $29/month and not "under half of Pro."** The offer
used to be priced as an annual plan at under half of Pro's annual price. Now
that both are flat monthly numbers, $29 against Pro's $39 is a real discount —
about 26% off, for the life of the subscription — but it is *not* half price.
Don't reintroduce a "half the price of Pro" line in marketing copy; it's no
longer true. `docs/BILLING_COPY.md` was written without that claim.

**Agency currently reads as "Pro plus more volume," not a distinct tier.**
Two features that would justify Agency's higher price — white-label exports
and a commercial resale licence — are computed as entitlement flags in
`plans.py` but implemented nowhere else in the codebase. They are deliberately
left out of `BILLING_COPY.md` rather than sold and not delivered. Build them,
or decide Agency is a volume tier and price/copy it as one.

**Founder seat safety.** The cohort is exactly 100 people. The cap is enforced
by the database inside a transaction, not by hiding the button, so two
simultaneous buyers cannot both be sold seat 100. A seat is *reserved* when
checkout starts, released automatically if checkout is abandoned (30 minutes),
confirmed only by a verified webhook, and returned to the pool if the
subscription is later cancelled.

---

## 1. Stripe

1. **Get your keys.** Stripe Dashboard → Developers → API keys.
   Start with the **test** key (`sk_test_...`). Put it in `.env`:

   ```
   STRIPE_SECRET_KEY=sk_test_...
   ```

2. **Create the products and prices.** From `flask_app/`:

   ```bash
   .venv/Scripts/python.exe scripts/setup_billing_products.py
   ```

   That is a dry run — it prints what it would create and writes nothing. When
   the list looks right:

   ```bash
   .venv/Scripts/python.exe scripts/setup_billing_products.py --apply
   ```

   It prints the `STRIPE_PRICE_*` lines to paste into `.env`. Re-running is
   safe; it reuses anything that already exists and refuses to silently change
   a price that is already live.

3. **Add the webhook.** Dashboard → Developers → Webhooks → Add endpoint.

   - URL: `<FACTORY_PUBLIC_URL>/billing/webhook/stripe`
   - Events: `checkout.session.completed`, `customer.subscription.updated`,
     `customer.subscription.deleted`, `invoice.payment_failed`

   Copy the signing secret into `.env` as `STRIPE_WEBHOOK_SECRET`.

   Locally, use the Stripe CLI instead of a public URL:

   ```bash
   stripe listen --forward-to 127.0.0.1:5055/billing/webhook/stripe
   ```

4. **Set your public URL** so customers return to the right place after paying:

   ```
   FACTORY_PUBLIC_URL=https://your-domain.example
   ```

5. **Restart the app.** The 5055 dev server does not reload on its own.

6. **Go live** only after a full test-mode purchase works end to end: swap in
   `sk_live_...`, re-run the setup script with `--apply --live`, create a live
   webhook endpoint, and update the price ids.

## 2. Lemon Squeezy

Lemon Squeezy has no API for creating products, so they're built by hand in
the dashboard. Four subscription products, each with one monthly variant,
already exist there as of 2026-08-25:

| Product | Price | Billing |
|---|---|---|
| Starter | $19.00 | every 1 month |
| Founder Launch | $29.00 | every 1 month |
| Pro | $39.00 | every 1 month |
| Agency | $99.00 | every 1 month |

Every variant must be a **subscription** with **no free trial** — a trial
makes the first invoice $0, which the price check below reads as a mismatch
and refuses the sale.

1. Settings → API → create an API key, with **test mode** on → `LEMONSQUEEZY_API_KEY`.
2. Settings → Webhooks → add `<FACTORY_PUBLIC_URL>/billing/webhook/lemonsqueezy`
   with events `subscription_created`, `subscription_cancelled`,
   `subscription_expired`, `subscription_payment_failed`,
   `subscription_resumed`. Copy the signing secret to
   `LEMONSQUEEZY_WEBHOOK_SECRET`.
3. Put the API key and webhook secret in `.env`, then run:

   ```bash
   .venv/Scripts/python.exe scripts/lemonsqueezy_ids.py
   ```

   Read-only — it never creates, changes, or prints your API key. It fetches
   your store id, lists every subscription variant, matches each one to a
   plan in `plans.py` by price and billing interval, and prints the exact
   `LEMONSQUEEZY_STORE_ID` and `LEMONSQUEEZY_VARIANT_*` lines to paste into
   `.env`. If a variant's price doesn't match `plans.py` exactly, it says so
   instead of guessing.

If both providers are configured, Stripe is used for checkout. Both webhook
endpoints stay active either way, so an existing Lemon Squeezy subscriber keeps
working.

---

## 3. Verifying it works

```bash
.venv/Scripts/python.exe -m pytest tests/test_billing.py -q
```

Then, with a test-mode key in place:

1. Open the Subscription screen. The provider warning banner should be gone.
2. Buy the Starter plan. In Lemon Squeezy test mode, Stripe's test card
   `4242 4242 4242 4242` works at their hosted checkout too.
3. Confirm the webhook arrived (the dashboard's event log) and that
   `GET /billing/subscription?account_ref=...` reports `active`.
4. Claim a founding seat and confirm the seat counter drops by one.
5. Cancel it in the Lemon Squeezy dashboard and confirm the seat comes back.

This needs a public URL for the webhook to reach — see the ngrok setup this
session already walked through. Only run the tunnel while actively testing.

---

## What is deliberately not built yet

These are real gaps, not oversights. Each one needs a decision from you:

- **No user accounts.** The browser holds an opaque `account_ref` in
  `localStorage`. It identifies a subscription but authenticates nothing, so
  clearing browser data loses the link to a paid subscription. Real accounts
  (email + login) should land before you take live payments from strangers.
  When they do, `account_ref` becomes the user id and nothing else in the
  billing layer changes.
- **Entitlements are computed but not enforced.** `usage_payload()` knows how
  many products a plan allows and how many have been used, and
  `/generate-product` does not yet check it. Enforcement is a deliberate second
  step so that turning it on is a decision with a date, not a surprise.
- **No customer billing portal.** Cancellation and card updates happen in the
  provider's own dashboard. Stripe's hosted Customer Portal is the cheapest way
  to add this.
- **No tax handling.** Stripe Tax and Lemon Squeezy's merchant-of-record
  handling are both off. Lemon Squeezy acting as merchant of record is the main
  reason to prefer it over Stripe for EU/UK sales.
- **No proration or plan switching.** An upgrade currently means a new
  checkout.
