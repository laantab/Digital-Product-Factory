# Approved two-path ebook workflow — 2026-10-14

## Owner requirement

The owner approved: AI finds ebook recommendations; after choosing one, Build My Ebook starts complete automatic production and the Factory selects the template. Customers making their own ebooks select from the six templates, then the Factory completes their build. Template selection never interrupts the recommendation path.

## Implementation

Version 1.9.38, PR 56. FMA's ebook branch calls the existing durable /ebook/build path immediately instead of creating an unstarted workspace. An author-name field is shown alongside ebook recommendations. Its build button reads Build My Ebook. Other product handoffs remain draft-only.

The custom Ebook Builder and Product Factory form expose six template choices. The old prose-only Generate Ebook button is replaced by the complete builder entry. New fields.ebook_creation_mode is ai_recommended or custom. Automatic design uses the existing local topic/title/audience recommendation; custom design honors fields.theme_id. Both new modes use the existing strict free-visual recovery/approval and validated cover pipeline without intermediate picture/cover-choice pauses. Quality failures still prevent export. Legacy requests with no new mode keep their existing idempotency keys, review, cover-choice and resume behavior. Mode and custom template choice distinguish new request identities; repeat clicks attach to the existing build.

## Verification

110 focused checks passed; both browser handoffs passed. New real fixture builds for automatic and custom modes reached valid PDF and ZIP downloads, retained the expected template, refused invalid visual quality, and did not rebuild on repeat completion. The existing full browser customer journey now verifies automatic custom production and still checks refresh recovery, exact project count, manuscript/visual quality, actual downloads, save/reopen and no paid calls. Its obsolete manual picture-review segment was replaced to match the owner's approved behavior; the dedicated legacy picture-approval and guided-cover suites remain unchanged and pass.

Complete acceptance contains exactly 3,065 unique cases, no missing or duplicate nodes. Original run: 3,064 passed and one old entry-point assertion failed because it expected an unstarted workspace. The guard was updated to require the complete recommendation build while preserving the manual saved-plan entry and the legacy-export refusal. Its exact original node passed on rerun. Reconciled results have zero failures/errors/skips, with original partition XML retained. Fast stability likewise covered 715 cases: its same obsolete assertion was corrected and passed; no production code changed during that correction. Python compile, JavaScript syntax and manifest checks are required on final metadata as well.

184 Word Search/Coloring Book/Crossword protected cases passed before (v1.9.37) and after (v1.9.38). Siblings are relocked at the actual verified GitHub source commit 51bb6bcdc9ad054c1ef0ffc5bfdf4eafa6d9e6a5, tree 979e13b86e62a651e8c7d9b727e2442f7fbf443e. New creation-mode tests are enrolled in the full acceptance manifest; the updated complete real browser journey is also an ebook protected suite. Ebook remains PROTECTED, not a fabricated LOCKED state.

## Deployment boundary

Do not claim the workflow is live until website and builder deployment are verified. Website v1.9.37 remains the last verified live release. Render's connected tools expose the website but not Workflows. CLI/API credentials are unavailable; dashboard access redirected to Google sign-in. The owner previously authorized Google sign-in, but credentials require the secure browser-auth form. No secrets are entered through chat or ordinary page automation. PR 56 is reviewable and the code/checks are prepared before requesting that final access step.

No production book was started, resumed, rewritten, approved, or exported for these checks. Project 20 remains unchanged on Modern Business. No paid provider calls, host configuration, schema, secret, DNS, billing or marketing changes were made.
