# Lemon Squeezy product copy

Paste-ready descriptions for the four products currently published in the
Lemon Squeezy store:

| Product | Price |
|---|---|
| Starter | $19.00/month |
| Founder Launch | $29.00/month |
| Pro | $39.00/month |
| Agency | $99.00/month |

Every feature claim below maps to something that ships today. See
"Claims held back" at the end for what was left out and why.

The monthly product counts (10 / 50 / 50 / 200) match `services/billing/plans.py`
as of this write-up and are covered by `tests/test_billing.py`. If you want
different caps, change `plans.py` first — the pricing page and checkout both
read from it, and the numbers below need to move with it.

---

## Starter · $19/month

**Everything you need to publish your first products.**

Take an idea to a finished, listable PDF without a designer, a ghostwriter, or
a weekend lost to formatting.

- 10 finished products per month
- Every product type — ebooks, coloring books, puzzle books, Faith planners, Budget planners
- Editor-in-Chief quality review on every export
- PDF and ZIP export packages
- Publishing Studio templates
- KDP and Etsy listing preflight
- Email support

Billed monthly. Cancel anytime.

---

## Founder Launch · $29/month

**For the first 100 people who back the Factory.**

Full Pro access at a permanently discounted rate. Your price never rises —
through every future increase — for as long as your subscription stays active.

- Everything in Pro
- 50 finished products per month
- **Price locked for life** — your rate never goes up
- Direct line to the roadmap: founders vote on what gets built next
- First access to every new product type

Limited to 100 seats. When they're gone, this plan closes for good.

---

## Pro · $39/month

**For a real catalog and a real launch.**

Fifty finished products a month, plus the tooling to actually sell them
instead of just making them.

- 50 finished products per month
- Everything in Starter
- Factory Market Advantage research — find what sells before you build it
- Launch Package: landing page, freebie, ad copy, and email sequence
- Ad and promotion package generator
- Priority support

Billed monthly. Cancel anytime.

---

## Agency · $99/month

**For client work and publishing at volume.**

The plan for a catalog you are actively scaling, or products you are building
on behalf of clients.

- 200 finished products per month
- Everything in Pro
- Bulk export and batch generation
- Commercial use across unlimited client projects
- Named support contact

200 a month is a fair-use ceiling, not a hard stop — talk to us before you
hit it.

Billed monthly. Cancel anytime.

---

## Claims held back

Left out of the copy above because nothing in the codebase implements them.
Add each line back on the day it ships:

| Claim | Plan it belongs to | Status |
|---|---|---|
| White-label exports with your brand on every page | Agency | `white_label` computed in `plans.py`, read by nothing |
| Priority generation queue | Pro, Agency, Founder | `priority_queue` computed, read by nothing; there is one queue |
| Founding member badge on your account | Founder Launch | `founding_member` computed, never rendered |

One caveat on Agency's **"commercial use across unlimited client projects"** —
that is a licensing decision rather than a code feature, so it is safe to
publish, but only once the wording exists in your terms. Write it there before
the first Agency sale.

**Plan caps are not enforced yet.** `/generate-product` never checks
`usage_payload()`, so every tier currently behaves identically. The product
counts above describe intent, not behaviour.
