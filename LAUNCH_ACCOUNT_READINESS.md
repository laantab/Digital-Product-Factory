# Account launch checkpoint — v1.9.49

## Verified and deployed

PR72 is merged. The website is live on v1.9.49; the builder startup reports the same version. All 3,234 acceptance cases across 231 files and 38 protection/Command Center checks passed. Raw JUnit evidence, exact node IDs and checksums are preserved in `release_evidence/`.

The intended public flow is subscription plans → join or sign in → dashboard. The plans page and links are deployed. Existing private invitation access remains unchanged; public accounts mode is not enabled. The live Account/sign-in navigation confusion is fixed. Real test users completed joining, dashboard navigation, sign-out, wrong-password error and sign-in successfully. Two accounts could not cross-read projects or downloads.

Existing Saved Projects remain visible. Project20 retained its prior update timestamp and legacy owner field. No production user promotion, password reset, ownership backfill, payment, configuration change or product-generation task was performed.

## Read-only account and billing findings

Production currently has one active administrator and no rows in `billing_subscriptions`. This was checked with aggregate queries only; no password hashes or provider credentials were read. The owner's administrator sign-in is still unverified. The supplied screenshot shows Subscription Plans, not a password error.

The existing private billing UI mints and stores a browser account reference. `app.py::_account_ref()` accepts that reference from a request body, query or header. Checkout likewise accepts the supplied email. These endpoints are deliberately unavailable to non-admin account-mode customers; that restriction must stay until server-side signed-user binding is proven.

## Required launch gates, in order

1. Verify the existing owner administrator through secure sign-in. Do not create or promote a replacement administrator as a shortcut.
2. Bind billing account creation, subscription reads, checkout metadata and email to the signed user. Ignore client ownership claims. Preserve legacy owner references and verify signature-checked webhook ownership and idempotency with disposable provider fixtures and PostgreSQL.
3. Connect the advertised usage limits and entitlements to signed-user product creation and finished-product accounting. Prove concurrent requests cannot exceed allowance; retries/resumes must not double count. No real purchase is needed for this verification.
4. Review the remaining customer product and marketing routes before adding them to the explicit allowlist. Coloring books, planners, generic writes and other unreviewed customer flows must not be advertised as publicly available while blocked. Preserve all existing protected generator behavior and legacy owner access.
5. Verify the advertised paid joining flow and dashboard with separate customers, then obtain approval for production access configuration. Check public first visit, authenticated dashboard, private downloads and owner legacy access after activation. Keep marketing and actual membership acceptance closed until these gates pass.

The immediate production change still requires owner access and configuration approval under `AUTONOMOUS_UPGRADE_STANDING_ORDERS.md`; all remaining code and fixture work can be prepared without charging customers or invoking paid generation.
