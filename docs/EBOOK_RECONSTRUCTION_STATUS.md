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
The isolated supplied-manuscript milestone is implemented. Focused reconstruction
suite: 38 passed in18.21seconds. Real browser + independent CLI worker acceptance
stopped the worker after a saved chapter, closed the browser, restarted the
worker, reopened the saved book and downloaded matching PDF/ZIP files. The first
chapter remained at one attempt. Actual HTTP downloads passed authentication,
ownership, signatures, CRC, embedded PDF equality and SHA256 header checks.
All four pages of a separate supplied-text acceptance PDF were visually reviewed.

Existing Factory fast baseline: 826 passed in378.08seconds before new registry
coverage. This is not the final expanded gate or full release evidence. No paid
provider calls or production changes. Source is isolated; app.py is unchanged.
See release_evidence/ebook_v2_supplied_milestone.json and docs/BOOK_STUDIO_LOCAL.md.

Fresh-topic writing, independent editorial checks, photographs, chapter editing,
retained versions, EPUB/DOCX and KDP preparation remain to reconstruct. Hosted
SQL/R2, Windows execution and deployment have not been verified. This milestone
is deliberately not called the completed replacement generator.
