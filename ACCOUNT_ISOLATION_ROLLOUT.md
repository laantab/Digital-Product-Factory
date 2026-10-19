# Customer account isolation — staged rollout

Candidate: v1.9.49. The v1.9.49 code is live with the existing private access policy. Public account mode is not activated. This document does not authorize a production configuration change.

## Implemented boundary

`FACTORY_ACCESS_MODE=accounts` requires active signed-in users and a durable `SECRET_KEY` of at least 32 characters. Ownership comes from the signed session. Project lists, reads, updates, deletes, build references and package lookups are scoped to that owner. Standalone word-search and crossword exports use account directories. Administrators retain legacy owner access; unowned legacy products are never assigned to a new registrant. Public registration cannot create an administrator in accounts mode.

The customer endpoint allowlist is explicit. Reviewed ebook workspace/build flows and standalone puzzle flows are available. Generic raw project writes, operator actions, billing and marketing are unavailable to customer accounts in this stage. Other product workflows and paid membership onboarding remain launch work. Private mode retains the existing owner workflow.

The intended entry flow is first visit → subscription plans → join or sign in → dashboard. Successful authentication redirects automatically; Sign out returns to the entry page and ends access to account projects. Private mode keeps the existing invitation protection. Explicit accounts mode replaces the shared invitation with signed user authentication; its session-readiness guard still fails closed. Production account-mode activation is still required before this becomes the live default.

## Before activation

1. Require exact-source full acceptance results, PostgreSQL integration results, and protection relock evidence. Keep the candidate draft if any required result is unresolved.
2. Verify the owner can sign in to an existing administrator account and read the existing legacy products. An invite cookie is not proof of an administrator identity. Do not promote the first customer or silently reassign legacy products.
3. Obtain the owner's approval for the production configuration change under `AUTONOMOUS_UPGRADE_STANDING_ORDERS.md`. Verify durable session configuration without exposing secret values. Keep the invitation boundary closed during verification.
4. After approved activation, verify two separate accounts, own project creation/resume/download, foreign project and package denial, and owner access to legacy products. Use provider-free fixtures or an explicitly approved product build.
5. Keep public marketing and paid customer onboarding closed until purchase/account binding and all advertised customer workflows have passed their own gates.

## Recovery

Preserve every legacy product and export. If verification fails, close customer access and restore the last proven deployment/configuration through the approved production process. Do not switch to the legacy shared private workspace while untrusted customers retain an accepted invite or session. Keep access closed until isolation is restored. No destructive database cleanup or bulk ownership backfill is part of this release.

## Evidence at candidate creation

- Original cross-account read reproduced against v1.9.48 with disposable users and no live data.
- Focused account/auth batch: 44 passed; the real-browser case was excluded from that batch and passed separately.
- Real signed-in ebook creation, matching PDF/ZIP downloads, and second-account denial passed without paid provider calls.
- Earlier candidate b84596c: all 3,229 unique cases across 231 files passed after complete-file browser reruns; original missing-browser failures retained in the evidence. The subsequently requested first-visit/sign-in/dashboard repair adds two cases and requires final validation.
- First-visit UI check: signed-out browser sees plans first and can then reach both forms, registration opens Dashboard, Sign out closes project access, wrong-password sign-in displays an error, and correct sign-in opens Dashboard; both targeted cases passed.
- Disposable PostgreSQL integration: seven cases; GitHub Actions job 117750384785 passed against the candidate source (run 39153022326).
- Source tree under full verification: `1bb0b49be9f015e8b54dc3de9b89b21bd89a6c79` (local `2776ff355213ba7dc9669f3c2761364e2aa839bf`, GitHub `ffccfa1e822cdb64652f6d311a33c6d7fb9f4fdb`). Documentation and subsequent lock metadata require their own final validation.

## Screenshot clarification

The attachment became available and was inspected: it shows Subscription Plans, not a sign-in error. The requested first page is therefore the pricing page. The public `/plans` page uses the existing server catalog, accepts no customer billing reference, hides private dashboard navigation, and links to joining/sign-in. Live seat counts are shown only when read successfully. Joining does not grant paid entitlements or charge a customer. Payment/account binding remains a separate launch gate. The signed-out dashboard header now links to Sign in instead of opening Subscription Plans under an Account label.

## Final candidate verification

All 3,234 cases across 231 acceptance files passed on source tree `5df25b7a13c4922657517bee4d0932d677e41f7d` (GitHub `25ff6760c61e34cad643bc58d919dc496868d534`). All prior 3,197 cases remain. PostgreSQL runs 39194518287 and 39194513592 succeeded. Machine-readable proof is in `release_evidence/account-isolation-final.json`. Production remains unchanged. Read-only production query confirmed one active administrator account exists. The secure owner sign-in request returned declined; administrator sign-in is unverified. No sign-in retry or ownership promotion was performed. The screenshot was later available and inspected: it shows the subscription plans page, not a credential error. The signed-out Account button incorrectly opened Subscription Plans; the candidate gives signed-out visitors a Sign in link. The requested public flow is plans first, joining/sign-in second, then Dashboard.

## Live verification

v1.9.49 was merged through PR72 and website deploy `dep-dbap0tm7bikc73esok7g` became live at 2026-10-19 03:38:40 UTC. The live footer, Sign in link, pricing page and Join-to-forms navigation were verified. Existing Saved Projects rendered. Builder startup reports VERSION1.9.49; registration start was observed without invoking a product task. Project20 retained its exact previous update timestamp and legacy ownership. See `release_evidence/account-isolation-live.json`.

Existing private access remains in place. Public root-to-plans enforcement and account isolation are staged behind the unactivated accounts mode. Administrator login, purchase/account binding, quota enforcement and all advertised customer workflows remain launch gates; this deployment does not authorize accepting memberships.
