# Five-day launch completion — October 17, 2026

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
