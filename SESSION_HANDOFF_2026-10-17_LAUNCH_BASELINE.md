# Five-day launch completion — October 17, 2026

## LIVE VERIFIED — 1.9.47 repair complete, October 18, 2026

PR70 merged as 78069be3babc5b429e486e6cb3e9f819c7145f3b. Render website deployment dep-dbaevh2vcj2c73a5hl90 is LIVE; authenticated footer shows 1.9.47. Builder checked out that merge and startup explicitly logs VERSION1.9.47. All3,191 unique release checks passed; final65 metadata/version/lock checks passed and affected protections are LOCKED.

Live Project20 now shows100% with “Your reviewed version is ready to download. A newer draft needs review.” Both actual UI download controls returned the exact original PDF/ZIP hashes recorded below. ZIP CRC passes; its PDF is byte-identical to the standalone PDF. Opening sent only GETstatus, zero advance/resume POSTs; downloads were GETs to verified previous-export URLs. Project20 updated_at remains14:01:14.127997UTC, the pre-repair value. Ledger remains14calls/$2.35, last recorded call October9. No new generation or paid calls; no customer record/output writes during live verification. Earlier failed ZIP synchronization was superseded by successful actual UI downloads and exact local verification.

PLANETS coloring book and existing word searches remain Export Ready in Saved Projects. The newer Project20 draft is in Continue where you left off; its Ready-to-download entry opens the reviewed saved version at100%. Do not claim newer draft approval. Listing latency remains a separate launch issue, even though payload size is now small. Public memberships remain gated on customer-account isolation. This repair is complete.


## Final 1.9.47 verification — supersedes earlier pending records

All 3,191 unique cases across all 230 manifest files passed with zero failures/errors/skips, missing/extra/duplicate cases. All 3,171 prior case identities remain, plus 20 regressions. Local tested source de0abb3c0468f6e37b6316093eb4dcfbc54e388d; identical remote source 8a123ae3ebb673c678d08927b90f5884649d142b; tree d8db554aeb0f2aeb46779bbfe75995dac6e35c26. See RELEASE_PROOF_1.9.47.json. All affected protection records relocked on that real GitHub source commit. Five standalone real-browser customer paths passed.

The earlier full run's single reopen timeout was a real defect: record_preview_opened synchronized an older ebook_document.release_status over the certified top-level status, withdrawing export readiness merely by viewing the preview. A regression failed before the metadata-only repair and passed afterward. The entire final suite was rerun. Earlier interrupted runs and the failing run are retained as diagnosis, not success evidence.

Live history serves the exact original PDF. Its fresh download checksum matches 20792e8fcce4ab4fcc7daa8e49df1d0a634f7c624d9197d346d0fda83f8d025d. The original ZIP is retained in history and in the independently CRC/hash-verified recovery archive. Fresh ZIP browser download reported a path but did not synchronize locally; do not claim an additional local checksum for that attempt. The new status helper validates history bytes against the prior review plus ZIP integrity and embedded PDF equality before exposing both links.

Next: publish evidence, merge PR70 and verify live website/footer, read-only Saved Open, reviewed saved version at 100%, original download links, no new build requests. Newer draft remains separate and unapproved. No production configuration, customer records or exports were rewritten by this code repair; no new paid calls. Public account isolation remains outside this repair and blocks public memberships.


## Saved ebook preservation repair — October 18, 2026

PR70 is draft pending the complete release gate. Runtime source afd57edc107b1d31147b07bb04239e1277b89c60, tree 6a190941f58d5523ed5fcbb46c78403132c77a31, exact remote source 8e1d867fdbe9fd4b25c54c1e396ca1d224b7b2ee. Focused suite: 128 passed. Full manifest collects 3,190 cases across 230 files, retaining all 3,171 previous case identities and adding 19 regressions. Final six-checkout run is the authority; earlier interrupted checks are superseded, not passes.

Repairs: Saved Open reads status without POST advance/resume; stale finished flags cannot outrank file validation; old advance/resume requests cannot dispatch or rewrite a formerly completed artifact; a verified original release-review PDF/ZIP pair is served from existing previous-export URLs, separately from the newer draft; missing retired factory-copy pictures use an acquired checksum-verified source. No generator implementation or production configuration changes. Do not claim newer draft approval.

Live evidence before repair: prior release-review hashes exactly match the original pair in eight-entry previous-export history. Verified original pair also saved in Factory_Project20_Verified_Recovery_Copy_2026-10-18.zip. Current PDF has 64 pages and the same 13 image digests, but differs from the original in document metadata and repeated table header/page break on pages56–57 after the automatic builder export. Preserve both. Project20 ledger remains 14 calls/$2.35, last entry October9; no new paid call.

Next: finish gate and exact reconciliation, relock affected shared dependencies, publish evidence, merge/deploy, verify website version and Saved Open with zero advance/resume requests, and download original pair to prove exact hashes. Public membership account isolation remains a separate launch blocker.


## Live release verification — October 18, 2026, 07:01 Pacific

PR68 merged as 4c804ded691660c01214022a5c5c6ef422466ed3. Render website deployment dep-dbad0e7lk1mc73cngd10 is LIVE; authenticated footer shows 1.9.46. Website briefly returned 502 during the disk-backed restart and recovered. Saved Projects loaded existing ebook, PLANETS coloring book, House Plants and Flower Parts word searches. List responses now 4,147 bytes for limit=3 (previously 5,896,166) and 6,694 bytes for limit=10 (previously 6,456,310). Loading remains slow: payload size is repaired, server-side listing work remains a separate performance issue. Live manuscript editor loads with compare/reject controls, without saving edits. PR66 and PR69 closed as superseded. PR67 remains excluded.

IMPORTANT NEW BLOCKER: Project20 reopen shows activity Finished but 90%, finished=false and message Building your final files. Read-only GET /ebook/build/20/status confirms a DRAFT, complete manuscript, existing PDF/ZIP URLs, activity.state=done, finished=false, attempts_left=0. Do not treat this as launch ready or automatically regenerate the accepted exports. Opening the saved ebook unexpectedly started automatic POST /ebook/build/20/advance polling (200), despite only clicking Open. Closed the Factory tab to stop it. No explicit save/edit/approve/rebuild was clicked. No provider-charge event observed in inspected logs; zero new spend is NOT independently verified by ledger yet. Check ledger and preserve original files before any further action. The unchanged frontend resume behavior and stale finished/validation disagreement need isolated reproduction and repair. Do not simply force ready=true.

Render builder workflow checked out the merge commit and its build succeeded. No new runtime startup/version log was available; runtime verification remains pending. Do not trigger a paid ebook build to prove deployment. Public memberships also remain gated on account isolation (auth Phase A is additive; project routes do not yet enforce per-user ownership). No production settings changed.


## Final verification — October 18, 2026

Release 1.9.46 passed all 3,171 unique tests across all 230 manifest files, with zero failures, errors, skips, missing or duplicate cases. Exact tested tree: ce933d0eab891a037a0d7893e9765744f8da9e57; GitHub source: 740756d408ad2db8734b0a815649a2de62a3a618. Exact-source PostgreSQL integration run 39095302129 succeeded (six cases). Original reference PDF/ZIP hashes match. No paid provider calls. See RELEASE_PROOF_1.9.46.json.

Next: merge PR68 and verify website and builder deployment plus read-only Saved Projects, editor and downloads. Deployment is pending; the historical pending-verification notes below are superseded by this result. Public memberships remain gated pending customer-account isolation verification. No customer records, exports or production configuration were changed.


## Current combined candidate — supersedes pending items in the historical record

The editor-only 228-file baseline completed: 3,154 unique cases, zero failures,
errors or skips; all four reports reconcile exactly against collection, including
68 root-level test cases. Source tree e31b6bb385102b104fefeb97a458cef213042d7c
matches GitHub source e549c6f09eb6cd12b544fe914f0b349fe4d30f70.

Further release audit found Apply and Undo lacked the established artifact
mutation gateway. Eight isolated regressions reproduced mutation of APPROVED/
LOCKED manuscripts through both the pure service and actual HTTP route. Added
assert_content_mutation_allowed at the start of apply_edit, reusing the Factory's
existing policy. No shared route or generator was changed. The eight new checks passed after the guard was added. The editor also shows
a confirmed protection rejection directly, while still requiring reload after
an uncertain save. The final combined 230-file candidate includes these checks
and must be fully verified before deployment.

Release 1.9.46 now combines three targeted repairs in PR68: manuscript compare/
reject and pending-request safety; bounded Saved Projects metadata that excludes
nested books/images/history; and PostgreSQL billing transaction/event replay
compatibility. Generator implementations, shared app.js, production settings,
prices, payment credentials and customer records/exports are unchanged.

The standalone listing regression reproduced oversized nested payloads before
the fix. Afterward, 52 listing/reopen/visibility/lock checks passed. The billing
regressions reproduced both PostgreSQL errors before their fixes; 108 local
checks passed. GitHub Actions run39094194689, commit04004b29cbf8715383b494eb0beac6e3e6350b86,
passed all six real PostgreSQL16 checks (final-seat concurrency, rollback,
webhook replay/concurrency and seat reuse) in a disposable localhost database.
PR69 preserves the independent billing review; its code is included in PR68.

The editor-only 228-file release validation is baseline evidence for the next
combined 230-file gate. New manifest entries cover all four billing adapter
cases and four nested-list cases. Run the entire combined candidate and require
exact unique collected-case reconciliation and zero skips/failures/errors.

Live read-only check: authenticated Saved Projects loaded existing products;
Project20 reopened after an initial timeout/retry and displayed Finished/100%.
PDF and ZIP downloads completed, ZIP CRC passed, and its ebook.pdf is identical
to the downloaded PDF. Current PDF64 pages, SHA256
20792e8fcce4ab4fcc7daa8e49df1d0a634f7c624d9197d346d0fda83f8d025d;
ZIP SHA256 f7cc37a90f71e8563039c412f23f7ba11deff52edb055419117197921d572d26.
No extracted text spans below8pt. Cover and page32 visually inspected; this is
not a claim that every page was visually reviewed. Open Product's full-preview
tab also loaded the correct title and approved preview. No approval/build/save
was submitted and no paid provider requested. Existing unfinished books were
not resumed. The live website restarted during the check; cause is unproven.
Logs showed a6.46MB saved list and19.86MB detail response, motivating the bounded
list fix. Full detail stays unchanged; do not claim the timeout is solved until
the deployed combined release is checked.

No new generation or new paid build was performed. Public marketing readiness,
mode-policy PR67, and final live acceptance remain unclaimed. Do not merge or
deploy until the current exact-source combined gate and PostgreSQL CI pass.

## Historical development record

Owner approved the October 18–22 completion plan and confirmed the Render
workspace by saying Continue. Work is scoped to launch-critical ebook completion,
editorial quality, preservation and release verification. Do not expand product
types or modify accepted coloring/puzzle/planner behavior.

## Verified baseline

- Main/source: 6d143d2aeb8141f5d76234e91d94435197fbf6ea, version 1.9.45.
- Website deploy dep-db8sbnfavr4c739l1va0 reports live at that commit.
- Builder resource wfl-damqq8uk1f9s738jtgc0 logs checkout of that commit and
  startup VERSION 1.9.45 on October 16. Render service listing does not expose
  workflows; use logs rather than interpreting a service-lookup 404 as absence.
- Website error log query since that deploy returned no error-level entries.
- Initial Fast Gate: 756 passed, one failed and seven setup errors because the
  workspace lacked Chromium. After installing the pinned browser, both complete
  affected files passed (10 cases; includes two cases already in the 756).
  Reconciled baseline Fast Gate coverage: all 764 cases passed. No test weakened.
- Existing chapter generation already runs conservative copy edits before
  structural acceptance and rolls back edits that add findings. Do not duplicate
  this merely because the audit initially described integration as unfinished.
- Preserved original reference archive retrieved from the owner's Library:
  Factory_Reference_Files_20261007-132004_3d857a.zip. CRC passed. PDF 4,951,720
  bytes, SHA256 6202e3a559db9313b61ec2d54ff689f6236a3b037308820bc77cfedf4d01f5bd;
  ZIP 4,433,813 bytes, SHA256
  5044f086b7335e139bcec94e1b743c4f7effd4fe9eb7738973140176ef6d5c1f.
  ZIP CRC passed and its ebook.pdf is byte-identical. Installed only the local
  ignored test-reference copies under exports/ebook-visuals-local; no live files
  were accessed or changed.

## Candidate 1.9.46

Branch work/five-day-launch-editor builds on the compare/reject UI from draft
PR66. Added pending-request protection, a 30-second timeout and reload-before-
retry protection for uncertain saves. Side-by-side comparison wraps on mobile.
No Python generator, billing, storage, database, shared app.js, approved customer
data or original artifact was changed. No paid provider request made.

Added five review-control checks: one rendering check and four real-browser
cases covering reject/full-record preservation, late preview vs typing, failed
preview retry, and a successful save whose response is lost. Combined with
existing manuscript-editor and lock-enforcement checks: 14 passed. The first
run caught horizontal overflow; CSS corrected, complete focused run passed.
Version checks initially caught missing changelog headings; corrected, all 31
version checks passed. Earlier proofreading/rewrite checks also passed.

The merged proofreading and rewrite files were absent from the acceptance
manifest. Added them, along with the new review-control tests. Current manifest
has 228 files. No test assertion or exclusion was weakened.

## Verification still in progress — DO NOT CLAIM COMPLETE OR DEPLOY

Full acceptance run began with the 226-file manifest before the two preexisting
editor test files were enrolled. That run also skipped the reference-preservation
case before the verified reference files were restored. Final release proof must
cover the complete current 228-file manifest with zero final skips, failures or
errors. Rerun affected complete files or run a fresh full gate; retain initial
results and reconcile unique case identities if combining reports.

Existing automatic/custom creation, guided cover, quality and export suites are
also running separately against fixture providers. Check actual results before
reporting success. No live end-to-end generation or paid build was performed.

## Additional audit item

Historical production logs show billing plans failing with PostgreSQL syntax
error near IMMEDIATE. services/billing/store.py::_tx still unconditionally uses
BEGIN IMMEDIATE. Do not translate this to plain BEGIN and lose seat-allocation
serialization. Before selling subscriptions, reproduce using an isolated real
PostgreSQL database, implement billing-local transaction/serialization support,
and verify founder-seat concurrency and webhook idempotency. This candidate
does not change payment behavior or claim checkout is ready.

## Remaining launch work

1. Finish exact-source release validation and preserve the source on GitHub.
2. Review PR67 without blindly importing its new mode switch: it changes picture
   auto-approval and is not a completed automatic/manual experience.
3. Verify title/cover decision, current output quality and recovery end to end.
4. Resolve billing/PostgreSQL compatibility if marketing Factory subscriptions.
5. Deploy only after the required gate is green; verify both services, downloads,
   saving/reopening, desktop/iPad paths and cost-counter deltas. Preserve rollback.
