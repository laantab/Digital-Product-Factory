# Ebook replacement reconstruction — November 2, 2026

## Durable baseline
- Repository: laantab/Digital-Product-Factory
- Reconstruction branch: rebuild/ebook-engine-v2-20261102
- Baseline commit: 19068c448be08e0da28b62b110a928afaba320a0
- This baseline is the existing Factory, not the missing replacement implementation.
- Prior replacement test counts in conversation are historical reports, not reproduced evidence for this branch.

## Authorized objective
Reconstruct an isolated ebook engine with durable per-stage work, bounded recovery, verified repair memory, automatic/manual modes, professional layout, editable content, and verified downloads. Preserve existing customer projects and other generators. Default to no paid calls. User explicitly requested saving work to GitHub.

## Milestones
1. Reconstruct isolated durable jobs; test interruption, concurrent claims, stale workers, retry exhaustion, and corruption.
2. Build a supplied-manuscript customer workflow and verify actual PDF/ZIP routes plus reopening after restart. Label supplied input honestly.
3. Connect an available approved writing provider and verify a fresh topic-to-book run. Provider availability is not yet confirmed.
4. Complete editorial, visual, preview/editing, and export requirements. Validate EPUB if offered.
5. Run protected regression checks before live cutover.

## Persistence rule
Commit and push each verified milestone to this branch. Confirm the remote commit before describing it as backed up. Do not depend on a temporary checkout or local commit alone. Keep a current status record with exact checks and blockers. Never commit customer files, secrets, generated books, or runtime databases.

## Current status
Durable-job foundation reconstructed. New failure-injection suite: 21 passed
in 3.62 seconds. Covers restart reuse, request conflicts, tenant isolation,
prerequisite barriers, concurrent claims, subsecond stale-worker fencing,
crash retry exhaustion, input/output corruption, invalid-output rejection,
verified versioned repair memory, code-owned repair allowlists, persistent
backoff, handler/validator deadlines, process exits and exception redaction.

The new package is not imported by the live app. No providers or production
systems were called. This adapter is SQLite-only; hosted SQL parity is pending.
Supplied-text workflow, UI, downloads and fresh-topic generation are not yet
implemented in this reconstruction. The existing Factory fast baseline is
running separately; no full-release pass is claimed for this candidate.
