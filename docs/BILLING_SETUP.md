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

| Plan | Monthly | Annual | Products / month |
|---|---|---|---|
| Free | $0 | — | 3 |
| Starter | $9.99 | $99 | 10 |
| **Pro** (Most Popular) | **$24.99** | **$249** | 50 |
| Studio | $39.99 | $399 | 200 |
| **Founder's Plan** | — | **$99, locked for life** | 50 (Pro-level) |

Prices live in `services/billing/plans.py`. That file is the single source of
truth: the pricing page reads it, and checkout re-checks the provider's amount
against it and refuses if they disagree.

**Why every paid tier is metered.** Each finished product costs real money to
make — model calls, sometimes a stock-photo lookup. "Unlimited" on a $9.99 tier
means the heaviest users pay the least and cost the most. The caps are
generous enough that a normal seller never notices, and they keep the bottom of
the ladder from being the thing that loses money.

**Why Pro is $24.99 and Studio exists.** Pro is the plan intended to be bought;
Studio's job is partly to make Pro read as the sensible middle. Studio also
carries the two things that genuinely justify a higher price — white-label
exports and a resale licence — rather than being the same product with a bigger
number.

**Why the Founder's Plan is $99/year and not a lifetime deal.** A lifetime deal
takes cash once and creates a cost that recurs forever, which is a bad trade
for a product with per-use costs. $99/year locked for life is close to the same
emotional offer — it is under half the Pro price and it never rises — while
still paying for itself every year the customer stays. If you would rather run
a true lifetime deal, that is a pricing decision, not a code change: set the
amount in `plans.py` and say so in the plan copy.

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

Lemon Squeezy has no API for creating products, so build them by hand:

1. Settings → API → create an API key → `LEMONSQUEEZY_API_KEY`.
2. Your store id is the number in the store dashboard URL → `LEMONSQUEEZY_STORE_ID`.
3. Create one **subscription** product per plan and period, with the exact
   amounts in the table above. Copy each **variant id** into the matching
   `LEMONSQUEEZY_VARIANT_*` line in `.env`.
4. Settings → Webhooks → add `<FACTORY_PUBLIC_URL>/billing/webhook/lemonsqueezy`
   with events `subscription_created`, `subscription_cancelled`,
   `subscription_expired`, `subscription_payment_failed`,
   `subscription_resumed`. Copy the signing secret to
   `LEMONSQUEEZY_WEBHOOK_SECRET`.

If both providers are configured, Stripe is used for checkout. Both webhook
endpoints stay active either way, so an existing Lemon Squeezy subscriber keeps
working.

---

## 3. Verifying it works

```bash
.venv/Scripts/python.exe -m pytest tests/test_billing.py -q
```

Then, with test keys in place:

1. Open the Subscription screen. The provider warning banner should be gone.
2. Buy the Starter plan with Stripe's test card `4242 4242 4242 4242`.
3. Confirm the webhook arrived (Stripe CLI output, or the dashboard's event
   log) and that `GET /billing/subscription?account_ref=...` reports `active`.
4. Claim a founding seat and confirm the seat counter drops by one.
5. Cancel it in the Stripe dashboard and confirm the seat comes back.

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
