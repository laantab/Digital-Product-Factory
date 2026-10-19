# Subscription controls recovery — October 19, 2026

The unpublished v1.9.50 source was lost when its temporary workspace reset. Earlier 3,286-case results belong to that unavailable source and do not certify this reconstruction. Production remains v1.9.49 at 711b696.

The owner explicitly authorized public branch publication and a draft PR. This branch is a durable reconstruction checkpoint, not a deployable release. No production settings, customer products, credentials or prices are changed.

Required replacement proof: signed account binding; paid-invoice-only grants; atomic event handling and replay; durable credit/budget reservations; verified PDF/ZIP settlement and recovery; cancellation/refund holds; provider maintenance notices; subscriber dashboard and mobile journey; protected release manifest; real PostgreSQL CI. Merchant test mode, administrator sign-in, actual costs/pricing, both deployed service versions and live subscriber rehearsal remain launch gates. No additional paid calls are authorized.

Checkpoint 0: restored exact main baseline. Replacement implementation and tests pending. No merge or deployment authorized by this draft.


## Reconstructed behavior (draft candidate)

The signed session determines checkout identity and email; client identity fields
are ignored. One configured, metered monthly ebook offer is available only with
FACTORY_SUBSCRIPTIONS_ENABLED=1 and a valid FACTORY_SUBSCRIPTION_PLAN_ID. These
flags do not configure a merchant or certify catalog prices for a launch.

Paid invoices grant their recorded checkout allowance, once per invoice/cycle.
Subscription creation and redirect URLs grant nothing. Event receipts and state
changes share one SQL transaction. Both provider payload formats have fixtures;
merchant test-mode delivery is still required. Scheduled cancellation preserves
the paid period, terminal expiry cannot be reversed by a late event, and refunds
hold further work for review while retaining consumed-product history.

Before work, one credit and the existing per-book spending ceiling are reserved.
An unknown business spend baseline blocks subscriber builds. No budget was
initialized on production; the seven-dollar authorization is not raised. Failed
builds release product credits but retain conservative spending holds, because
a failed vendor call may still have cost money. Those holds are not vendor bills.

Workers honor stored enrollment across rollout-switch differences. Settlement
checks the current revision, actual PDF/ZIP hashes, ZIP CRC and identical embedded
PDF. Accounting outages retry settlement without rendering again. Downloads are
held until settlement completes. Existing saved owner books are not reassigned.

Subscriber UI exposes ebook creation, the single title/cover choice, progress,
matching downloads, saved books and provider-hosted subscription management.
Advanced operator actions and other generators remain unavailable only in this
opt-in subscriber surface; private owner tools are preserved. Expiry/balance
warnings use dated owner observations, never secret key values or invented live
balances. Failure notices store fixed categories, not private exception text.

Checkpoints are retained in draft PR #73. The original 3,286-case report belongs
to lost source and is not reused. Native billing PostgreSQL CI passed 11 cases on
f943ebd and subsequently on c565068; account PostgreSQL CI also passed on c565068.
A reconstructed 390px browser journey passed with matching downloads, one credit,
refresh through cover choice and zero paid calls. Exact final-source reruns and
function relocking follow; no production action has occurred.

Remaining production gates: verify administrator sign-in; merchant test-mode
checkout, renewal and cancellation; actual provider routing and measured unit
costs; owner approval of price/allowance and a verified business-spend baseline;
website/builder version match; subscriber rehearsal and original export hashes.
Public access/payment activation requires those gates and owner configuration.


## Exact-source release closure

The reconstruction passed all 3,287 unique cases across 237 acceptance files on
c34066b1b785bc46c8053c2ae8d5b476ea5aa095, retaining every one of the 3,234 baseline
case identities. Zero final failures/errors/skips/missing/extra/duplicates. An
entire group was rerun unchanged outside the OS temporary directory to exercise
production-path guards correctly; both initial and final raw reports remain.
Native billing/account PostgreSQL checks passed 11/7 cases. The final source
includes the phone workflow, readable template labels, hidden completed-book
recovery controls, and visible candidate version. Original reference hashes
remain unchanged and the five shared locks are restored. No paid provider calls,
production changes, merge or deployment. See the reconstruction handoff and
release_evidence/subscription-rebuild-final.json for exact evidence and remaining
live gates. Earlier pending notes above are historical checkpoints.
