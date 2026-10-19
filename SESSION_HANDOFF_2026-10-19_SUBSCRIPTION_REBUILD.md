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
