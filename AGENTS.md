# Factory continuity and release instructions

Read command_center/continuation.json, SESSION_HANDOFF_2026-11-02_EBOOK_RECONSTRUCTION.md and PROTECTED_GENERATOR_RULE.md before changing code.

## Resume without repeated approvals
The owner has authorized completing the Factory rebuild, ordinary fixes, GitHub pushes and deployment within the agreed scope. Preserve the no-paid-generation constraint and protected generators. A status question does not cancel the active task.

At the start of each active session:
1. Fetch the current branch head and PR #107. Do not trust an earlier chat's branch head.
2. Inspect the exact recorded Actions runs and their artifacts. A successful job is technical evidence, not human review or production certification.
3. Resume the first unfinished item in continuation.json. Do not regenerate completed books or repeat green checks without a changed input, failure or unresolved concern.
4. After a transient interruption, inspect whether the preceding operation completed before retrying. Never blindly repeat a mutation, deployment or generation.
5. If the execution environment disappears, use connected GitHub operations for durable checkpoints; record inaccessible evidence as unknown.

Before ending an active turn:
- Commit source and an accurate checkpoint with the expected-head lease; never commit credentials, runtime databases or customer books.
- Record exact run IDs, failures, evidence locations, next action and a clear blocker if any.
- Distinguish queued/running/completed tests, source publication, deployment and production acceptance.
- Never imply active engineering continues after the turn ends. Already-started external jobs may continue.

## Completion contract
Do not mark complete until a fresh topic-to-book run has passed, actual manuscript and rendered pages have been reviewed, PDF and ZIP bytes are verified, required full release checks are green, and the intended supported deployment has been verified. Local-only Studio technical acceptance does not prove hosted Factory integration.
