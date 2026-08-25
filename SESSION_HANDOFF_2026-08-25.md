# Session Handoff — 2026-08-25 (supersedes 2026-08-24)

**Start a new session with:** "Read flask_app/SESSION_HANDOFF_2026-08-25.md and continue."

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
