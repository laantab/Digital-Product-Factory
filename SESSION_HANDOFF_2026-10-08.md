# Ebook background-builder and Continue repair — release in progress

## Reproduced defect

The executor stopped on `paused_after`, which is the requested future review
point. The orchestrator sets that before the stage is finished and reports an
actual review hold separately as `held_after`. Consequently a step-by-step
manuscript job exited after one bounded unit, reporting waiting for the
customer while incomplete chapters still left progress at 30%.

The executor now stops on `held_after`. Picture and cover approval waits,
failures, durable leases, chapter checkpoints and export idempotency remain
unchanged. Existing deliberate-pause test fixtures now include the real
status contract's `held_after` field; their pause assertions remain intact.

## Verification

- New executor and workflow regressions failed before the code fix: one unit
  instead of twelve and one claim instead of two. Both passed after it.
- A real manuscript pipeline test replaces only the paid chapter provider:
  the background workflow reaches 40%, writes each of ten chapters once,
  and pauses only after the approved manuscript is ready for review.
- Focused executor, workflow, manuscript recovery and activity tests:
  103 passed. Registry integrity and enforcement also passed independently.
- Fast Stability Gate: 710 passed, 1,020 subtests passed, in 167.25 seconds.
- No paid API calls were made; tests use isolated databases and local fixtures.

## Continue recovery repair

A second route-level regression reproduced Continue leaving the stage failed
even after the durable job was reopened. Explicit Continue now calls the
existing resume_build checkpoint recovery only for a failed build without a
live worker lease. It preserves workspace content and uses a fresh resume
generation for retry idempotency. Ordinary polls and live workers are unchanged.
Focused recovery, executor, workflow, activity and lock checks: 145 passed.

## Remaining release work

This repair demonstrates a cause of 30% stalls when a stage review hold is
requested. It is not production-log proof of the current customer's specific
project: its ID and persisted build state were unavailable in this workspace.
The guided Generate Project flow clears review holds at startup, so this test
does not prove that every guided-build stall has this cause.

The owner authorized whatever is needed to complete the Factory on October 8.
VERSION and changelog are prepared as 1.9.17. The full enforced release gate
passed: 2,960 tests, zero failures, zero errors and zero skips in 1,389.72
seconds. All 209 acceptance files ran, with paid APIs blocked.
Original reference exports were restored and their checksums verified.
The tested code tree is 7b0e767b3d83f10b7a0e240ecef3178ab631c4c8,
published as commit 1fb24429b9b0920edb36b5deb5f17ae9d91be35a.
The following release-result edits change documentation only.
Shell git push has no credentials; the connected GitHub tools published
the branch and PR #34. Merge is authorized. Verify both website and builder
deployments and the resumed project after merging.
Render dashboard sign-in is awaiting the owner-selected Google passkey method.
The Factory cloud-browser Saved Projects screen did not expose Document It Once.
No hosted paid generation has been started during this repair.
Do not claim a local passing test means the live site is repaired.
