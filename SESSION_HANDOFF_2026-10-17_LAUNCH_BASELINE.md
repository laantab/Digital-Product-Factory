# Five-day launch completion — October 17, 2026

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
