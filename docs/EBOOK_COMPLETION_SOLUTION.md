# Ebook completion contract

Owner-authorized engineering work, 2026-10-26. Audited against main commit
30fd93cc74504e88fab53c730eb870829e6ff287. This is a delivery contract and
implementation sequence, not a claim that the redesign is deployed or proven.

## Customer promise

Start once, select the title and cover when requested, and leave the page.
The server continues from saved work. A completed book has a verified current
PDF and ZIP. A blocked book gives one actionable reason, preserves its work,
and does not spend indefinitely. Automatic mode delegates production decisions;
manual mode retains explicit review stops. Neither mode bypasses quality gates.

## Findings from current code

* Durable jobs, conditional leases, heartbeats, per-chapter checkpoints and a
  separate Render builder already exist. Replacing those would repeat work.
* `executor._drive` catches an unexpected interruption and releases the job to
  QUEUED. `workflow_runner.run_build` then returns `failed=True` normally, and
  `workflow_task.build_ebook` returns that dictionary. A normally returned
  dictionary does not invoke the configured exception retry. The saved job can
  remain unfinished with no executing worker.
* The workflow deadline likewise returns normally with the reason “the next
  trigger resumes it,” but that branch schedules no next trigger.
* A quality failure at export is deliberately final. Rendering the same inputs
  repeatedly cannot fix a wrong photo, chart wording or unsupported prose.
  The missing solution is a targeted repair stage, not more export retries.
* Work is represented by the workspace rail, build stages, job status, export
  identity and release-review decisions. They serve different purposes, but
  the customer needs one derived completion state and evidence for that state.
* Trigger failure preserves a queued row but does not itself guarantee later
  dispatch. A durable dispatcher/reconciler is needed for delivery guarantees
  across initial trigger outages and exhausted task retries.

Render's documented retry contract confirms that a task which returns normally
is successful; exception, timeout and instance failure activate configured retries:
https://render.com/docs/workflows-defining#retry-logic.

## Execution contract

1. The database records the request before any task is submitted. A single
   leased worker owns a book. Browser polling is read-only.
2. Each stage writes its artifact identity, input digest, validation report and
   checkpoint before advancing. Reopening a book must not regenerate accepted
   chapters or replace a valid export.
3. Worker outcomes are explicit: complete, waiting for a choice, quality blocked,
   temporary interruption, deadline continuation, or already owned by another
   worker. Only temporary interruption and deadline continuation invoke bounded
   automatic retry. No retry resets stage or spend limits.
4. A periodic reconciler checks durable queued jobs and expired leases, starts
   eligible work through the existing trigger claim, and records dispatch
   failures. It never reopens succeeded or quality-blocked jobs. Deployment of
   the reconciler must be independently verified; a queued row alone is not
   evidence of an active builder.
5. Every failure records stage, revision, reason code, last successful checkpoint,
   attempt count, next permitted action and last actual worker contact. Customer
   status must distinguish running, scheduled, waiting and blocked.

## Quality repair contract

Use the existing `EbookDocument` as the content authority, rather than adding
another manuscript model. Its chapter blocks, visual slots and revision digests
must survive round trips through workspace edits and export. New instructional
graphics should consume validated structured steps, comparisons or timelines;
they should not infer instructions from arbitrary headings or introductory prose.
Normalize legacy books without rewriting accepted chapter text. Keep decorative
photo selection separate from evidence that a specific instruction is illustrated.

Run inexpensive deterministic checks before committing assets to layout. Render
and inspect the actual pages before final delivery. Keep Editor-in-Chief and
release gates as the final authority.

Route a finding to its owning input: photo relevance/resolution to that photo;
chart semantics/readability to that chart; unsupported claims to the affected
paragraph or citation; sparse/clipped pages to layout. Preserve accepted chapter
text, chosen cover and unrelated visuals. Invalidate only artifacts depending on
the changed input, then rerender and rerun the same checks.

Persist repair fingerprints (finding code, input digest, proposed change) and a
small attempt ceiling. An unchanged finding after an unchanged input is a stall,
not permission to repeat the same paid call. Paid repair requires available
authorization and remaining budget. Unknown findings stop with a specific reason;
no generic “try again” loop, automatic approval of uncertainty, or weakened check.

## Final evidence contract

Completion requires the same current revision throughout:

* all required chapters and assets present and validated;
* readable cover, body, tables and diagrams on rendered pages;
* measured and editorial findings resolved or explicitly reviewed under the
  existing approval rules;
* PDF parses completely, ZIP CRC passes, and its embedded PDF is byte-identical;
* persisted PDF/ZIP hashes match the delivery records;
* authenticated production download routes return those actual bytes;
* review records include engine version, review version, timestamp and input
  hashes so an old pass cannot certify a new file;
* closing the page, retrying delivery and reopening the finished book cause no
  new generation, duplicate spend or export replacement.

An automated pass is not a guarantee of factual accuracy, copyright clearance or
commercial success. Do not label a book sale-ready without final artifact review.

## Implementation and proof order

1. Close the worker-outcome/retry gap with regression tests showing a released
   interruption retries and completes without the browser. Verify that genuine
   quality failures and customer decisions never enter that retry path.
2. Add durable dispatch reconciliation and owner-visible blocked/retry state.
   Prove initial dispatch failure, process death, expired lease, duplicate start,
   provider timeout, deadline handoff and exhausted retry behavior.
3. Add the finding-to-repair loop for the existing supported correction actions,
   with persisted input digests and stall limits. Prove preservation of accepted
   content and spend caps. Add unsupported finding types only with artifact tests.
4. Unify completion reporting around final artifact evidence and record the
   exact review engine/version. Prove stale approval and altered downloads fail.
5. Finish Small-Space Home Organization from saved material, verify actual
   production PDF and ZIP and final quality, then recover the next accessible
   book. Use a fresh book only after saved recovery is proven to test the full
   one-button path from creation. These are separate acceptance milestones.

Keep changes on an isolated branch. Run baseline and post-change protected suites,
the required release gate, and live acceptance. Preserve puzzle, coloring and
planner generators, existing customer exports, spending guards and rollback paths.
Do not equate a code merge, a 100% label, or a test fixture with live acceptance.
