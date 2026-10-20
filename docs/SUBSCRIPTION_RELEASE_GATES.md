# Day 3 and Day 4 closeout — October 19, 2026

Day 3 engineering is complete. Day 4 engineering verification is complete for
the implemented monthly subscription; operational acceptance remains open.
Do not equate a green test suite with merchant or production verification.

## Verified candidate

Draft PR73, runtime c34066b1b785bc46c8053c2ae8d5b476ea5aa095, v1.9.50.
All 3,287 acceptance cases passed, including editorial, recovery, protected
generators and the 390px subscriber journey. Native PostgreSQL billing/account
checks passed 11/7 cases. On October 20 at 02:02 UTC the six archived reports
were rehashed and reconciled with the saved proof: all matched, with no failed,
errored or skipped cases. This was evidence verification, not a new test run.

Day 3: conservative proofreading reaches regenerated PDF output; manual editing
and source protection retain their regression coverage; stale approval and
export checks prevent delivering a prior revision. ZIP/PDF byte equality is
verified. Optional unfinished rewriting controls stay unavailable. PR67's
unfinished mode interface is excluded. See the editorial-quality handoff for
the full preserved 64-page sample review and its legacy observations.

## Fresh read-only production preflight

Render reports website deployment dep-dbbchp49v7es73entilg live, finished
2026-10-20T01:51:53.722044Z, at 711b696d4a7a1c8e5dc01b0cb23f05469f5f1990
(v1.9.49). This manual redeployment was observed, not triggered by this work.
No error-level logs were returned for October 19 through the check. That query
alone does not prove successful generation, provider configuration or health.
The workflow builder is absent from the connector's service inventory; its
current version remains unverified. Main auto-deploys on commits.

## Remaining acceptance gates, in execution order

1. Verify the existing administrator can sign in. Do not reset credentials,
   create an administrator or change roles to make this check pass.
2. Inspect website and builder configuration in the authorized Render workspace.
   Record provider names, non-secret routing/model settings, dependent service
   identifiers and version evidence. Record secret presence only. Do not copy
   key values into logs, documents or source. Both services need the same tested
   runtime before the final live rehearsal.
3. In the existing Lemon Squeezy store, verify test mode and the selected monthly
   variant, currency, amount, interval, no trial/variable price, webhook signature
   setup, subscribed events and customer portal. Use test-only checkout and
   signed merchant deliveries to prove account binding, paid grant, duplicate
   immunity, renewal, failed payment, cancellation, refund/reversal and portal.
   Keep merchant IDs and screenshots containing private data out of public git.
   Local fixtures do not substitute for this rehearsal. No live charge is
   authorized.
4. Reconcile authoritative, timestamped provider spending with completed build
   ledgers, including failed calls/retries, stock images and editing. The known
   Project20 ledger (14 calls/$2.35) is insufficient to establish a global
   baseline or unit cost. Include payment, hosting and support costs. Obtain
   owner approval for price, allowance and terms. Do not initialize a budget
   from remembered spending or raise the existing $7 ceiling. No new paid
   benchmarking is authorized.
5. Top-ups have no verified purchase/grant implementation in this candidate.
   They remain unavailable and must not be advertised. The approved launch
   checklist includes a top-up rehearsal: implement and test it, or obtain an
   explicit scope decision to defer it before calling the whole checklist done.
   Scheduled off-app provider reminders are also not implemented; current
   notices require owner-recorded observations and an in-app visit.
6. Complete the exact-version live subscriber rehearsal and owner configuration
   approval. Deployment/restart and final iPad Safari acceptance belong to Day5.
   Do not enable public subscriptions before the applicable gates pass.

## Release and rollback procedure prepared for review

Before deployment, record current website AND builder deploy IDs, commits,
configuration names/modes, durable storage attachments and verified backup
recovery points. Preserve customer records/artifact hashes and accounting
evidence. Resolve or hold in-flight subscriber work before changing workers.
Do not disclose secrets in that record.

Deploy the exact verified candidate to both workloads only after deployment is
authorized. Check authenticated version evidence on each, existing admin access,
old product reopening/download hashes and the new subscriber test account.
Do not start new paid work to test availability without spending authorization.

Rollback triggers: cross-account exposure, missing/incorrect credits, duplicate
charge/grant, failed or stale output shown ready, inaccessible existing products,
or unresolved website/builder mismatch. Hold new subscriber work and checkout
first. Disabling the rollout flag alone does not stop stored subscriber workers
or payment events: preserve their checkpoints, ledger and webhook processing,
and reconcile in-flight work explicitly. Do not delete or reinitialize billing
tables, replay refunds blindly, or restore the whole database over newer
customer writes.

Before any v1.9.50 customer use, the fallback code target is the verified v1.9.49
commit above on BOTH workloads with the prior private-access configuration.
After customer use begins, v1.9.49 lacks the subscriber processing boundary;
do not roll it back blindly. Prepare a forward repair or a controlled maintenance
rollback that preserves and reconciles new payment events, reservations and
completed files. Preserve additive schema and data. After recovery, verify the
admin session, prior products and hashes, and all affected billing events and
reservations before reopening work. The recovery has not been exercised live.

No deployment, production mutation, paid call or live payment was performed by
this closeout work. Dashboard sign-in was unavailable; these gates remain open.

## Top-up implementation checkpoint — October 19 evening

The earlier missing top-up implementation is now being addressed in this draft.
A default-off Lemon Squeezy one-time credit offer has isolated checkout, signed
paid-order grants, replay/concurrency/refund safeguards and customer controls.
The initial focused run passed 68 cases. Full release and PostgreSQL CI for this
new source are pending; the 3,287-case proof above certifies the prior runtime.
The shared access allowlist is unlocked for its before/after protected checks.
No top-up price, quantity, expiry terms or merchant configuration is approved or
activated. Credits currently expire with the paid billing period; the owner must
approve this visible policy before launch. Optional SMTP/off-app reminders have
not been added. Nothing was deployed or charged.

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
