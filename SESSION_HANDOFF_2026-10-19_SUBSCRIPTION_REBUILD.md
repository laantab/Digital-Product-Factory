# Subscription reconstruction — October 19, 2026

Draft PR: https://github.com/laantab/Digital-Product-Factory/pull/73
Branch: work/subscription-launch-controls. Candidate version: 1.9.50.
Runtime source: c34066b1b785bc46c8053c2ae8d5b476ea5aa095.
Runtime tree: 699a92a3cd2ce39fda5055a1e8308e084c5cc962.
Later closure changes are protection metadata, documentation and evidence only.

## Completed and verified

Rebuilt signed checkout identity, paid-invoice credit grants, durable credit and
conservative spending reservations, exact current-revision PDF/ZIP settlement,
failed-build credit release, accounting recovery without re-rendering, payment
replay/order/renewal/cancellation/refund safeguards, maintenance observations,
and the opt-in subscriber dashboard with one persisted title/cover decision.
Private owner controls and unrelated generator implementations are preserved.

All 3,287 unique acceptance cases passed across all 237 files; all 3,234 baseline
case identities retained. Zero final failures/errors/skips/missing/extra or
duplicate case identities. One group initially ran under the OS temporary root,
which made two production-path guard assertions invalid. The identical source
and entire group were rerun in a normal workspace; the guard was not changed.
Both raw initial and final reports are retained. Native PostgreSQL: 11 billing
and seven account-isolation cases passed at this source. The real 390px browser
journey built a book, refreshed through title/cover choice, downloaded a CRC-valid
ZIP with identical PDF bytes, reopened it, and consumed exactly one credit.
Its provider fixture recorded zero paid or live stock-provider calls.

Five shared function locks restored at the real tested source commit. The source
of coloring, puzzle, planner and math generator implementations did not change.
Dependencies, Python compilation and both JavaScript syntax checks passed.
Proof: release_evidence/subscription-rebuild-final.json and the matching archive.

## Production and reference preservation

No merge, deployment, production write, setting change or paid provider request
was performed. Read-only Render checks still show v1.9.49 at 711b696. The checked
legacy saved-project record, ownership, version, timestamp and ledger are
unchanged. This is not a provider-wide bill or verified business spend baseline.

Original Project351 reference hashes remain:
PDF 6202e3a559db9313b61ec2d54ff689f6236a3b037308820bc77cfedf4d01f5bd
ZIP 5044f086b7335e139bcec94e1b743c4f7effd4fe9eb7738973140176ef6d5c1f
Original bytes are local, gitignored test references; never publish the products.

## Remaining gates

- Existing administrator sign-in and actual dependent provider configuration.
- Merchant test-mode checkout, renewal, cancellation, refund and portal settings;
  local signed fixtures and native SQL tests are not a merchant API rehearsal.
- Actual unit costs, owner-approved monthly price/allowance, and a timestamped
  verified spending baseline. No business budget was initialized or raised.
- Exact website/builder versions, subscriber rehearsal and production configuration
  approval. Public access and subscriptions stay disabled until those pass.

The Render connector does not expose the required environment settings, and no
Lemon Squeezy connector was found. Browser fallback needs user approval under the
browser access rules before attempting signed-in settings inspection. Workspace
My Workspace and public branch/draft-PR publication are already authorized; do not
ask for those permissions again. Publication checkpoints are durable on GitHub.
The earlier unpublished 3,286-case candidate was lost and its proof is not reused.

After relocking, all 72 registry/enforcement, Command Center, route and version
checks passed. No application source changes followed the full release run.

## Completed one-time credit purchases — October 19 evening

This supersedes the earlier missing-top-up and pending-test notes above.
Runtime: 7bd623b20de7580f03b85c3196eb9dd120c578dd, tree
e03cf2785379aec742ff4da12c1d0a2ab30ac846, still v1.9.50 in draft PR73.
All 3,310 unique acceptance cases across 238 files passed, retaining every prior
3,287 case and adding 23 top-up cases. Zero failures, errors, skips, missing or
duplicate cases. Native PostgreSQL billing/account CI passed 13/7 cases on this
source (runs39360086577/39360086371). All 72 post-lock metadata checks passed.
The original reference PDF/ZIP hashes are unchanged in every isolated checkout.
The five shared function locks are restored at this real tested source; the
subscriber accounting and purchase tests/dependencies are enrolled under staged
customer-account protection. No generator implementation was changed.

One-time Lemon Squeezy purchases now bind the signed account, fixed provider
variant, merchant customer, amount, currency and test/live mode. Paid signed
orders grant the recorded quantity once. Return redirects grant nothing. SQL
receipts/grants/claim state are atomic. Duplicate and simultaneous requests
reuse one checkout; uncertain outcomes stay held for review. Refunds, including
a refund arriving before payment, revoke unused top-up credits and hold new
work while preserving completed products and cost history. An older checkout
cannot be presented as a changed offer. Phone tests prove clear one-time/expiry
terms, stable retries and delayed payment confirmation without a new purchase.
The real subscriber phone build/download/reopen flow passed again on this source.

Activation requires FACTORY_TOPUPS_ENABLED=1, FACTORY_TOPUP_CREDITS,
FACTORY_TOPUP_PRICE_CENTS (USD cents), LEMONSQUEEZY_TOPUP_VARIANT_ID and the
existing Lemon Squeezy store/secret/public-URL configuration. Both subscription
and account rollout prerequisites still apply. There are no default prices or
allowances. New purchases require an active paid Lemon Squeezy subscription.
Stripe top-ups are unavailable. Top-up credits currently expire with the
recorded paid period; owner approval of price, quantity and these terms remains
required. No configured production value was set or changed. Purchasing credits
does not initialize or increase the business budget or authorize provider spend.

Evidence: release_evidence/subscription-topup-final.json and the corresponding
v1.9.50-subscription-topup-tests.tar.gz. The preceding pre-review local run was
intentionally superseded after two checkout edge cases were fixed. Its earlier
OpenCV import crash was resolved by reinstalling the identical pinned wheel.
Every final group ran after repair; no assertion or guard was weakened.

Still open: signed-in administrator/Render settings and builder-version proof;
merchant test-mode rehearsal; authoritative costs/spending baseline and approved
commercial terms; configured provider-expiry records and any scheduled off-app
reminder delivery. Current maintenance notices are in-app only. No live payment,
paid provider call, production mutation, merge or deployment occurred. Fresh
Render read-only verification still reports v1.9.49 at711b696, deploy
dep-dbbchp49v7es73entilg. Day3 engineering is complete. Day4 code verification
for monthly subscriptions and top-ups is complete; operational gates remain.
