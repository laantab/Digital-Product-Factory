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

## Local writing checkpoint
Local-only topic writing is implemented with title choices, an approved chapter
plan, per-chapter writing and independent editorial review, and cover/theme
choice. Automatic mode asks for title and cover; manual mode also holds for
outline and final-page approval. Supplied text still requires human review.
Worker capability preflight refuses a topic attempt when the installed local
model is absent. Cloud-backed model metadata, remote URLs, proxies and redirects
are refused by the text adapter. No paid fallback exists.

57 reconstructed cases passed62.35sec, including a real browser using an
explicit protocol fixture. An actual local qwen3:1.7b CPU development run reached
READY with a six-page guide, but included operator corrections. A separate
bounded fresh run is in progress and is not yet certified. Current app default
remainsqwen3:8b for the owner's desktop. Do not substitute fixture tests or the
small development book for complete fresh/default-size acceptance.

Response schemas now bound paragraph growth and token counts. Short drafts are
retained and expanded, including after explicit manual continuation; validated
completed chapters remain untouched. Independent review uses positive checks
and a separate numerical-percentage guard. It does not certify plagiarism
absence or external facts. Actual book-quality review is still required.

Expanded fast gate on the supplied milestonef30faa0:864 passed400.33sec. See
release_evidence/ebook_v2_local_writing_checkpoint.json for exact limits.

## Quality guard correction
Manual text review rejected the seven-page1.7B run despite its technical READY
state: internal model markup had appeared inside chapter prose. It is not
accepted fresh completion evidence. Separate deterministic guards now reject
chat/control tokens and leaked internal field labels at writing and review.
Four regression inputs reproduce the defect, including an approving fake model.
61 reconstructed checks passed53.12sec after the correction. A larger4B local
run is in progress. The owner's8B default and all minimum-length checks remain
unchanged. Do not deliver the rejected draft as a finished book.

## Durable partial drafting and independent prose checks
Drafting, measured expansion and final assembly now have separate immutable
checkpoints. A short draft is preserved without consuming the retry budget for
a finished chapter; only final assembly satisfying the requested length can
reach editorial review. Expansion excludes exact echoed paragraphs, and requires
actual new words. Status reports saved words and the current stage rather than
a synthetic progress percentage. Completed chapters remain intact on resume.

63 focused checks passed57.38sec before the additional prose guards. The4B CPU
development recovery run finished2chapters/6pages, but actual text inspection
REJECTED it: repeated sentences split across paragraph boundaries, unsupported
first-person author experience, and stray CJK text escaped model approval.
Independent guards now address these defects; final tests are recorded in the
next evidence update. This run is not accepted quality or uninterrupted fresh
completion evidence. No production changes or paid calls occurred.

Final focused follow-up:66 passed41.22sec. Includes real browser/worker
integration fixtures, interruption/restart and independent prose guard cases.
This is not the final full Factory release gate.

## EPUB and editable Word checkpoint
Exports now include EPUB3, editable Word manuscript and a cover JPEG alongside
the PDF and Markdown. All standalone files must match their ZIP entries; approval
revalidates every file, closing a corruption gap found by the new EPUB test.
EPUBCheck5.4.0 reported zero errors/warnings on the actual supplied-fixture EPUB.
Its downloaded official archive SHA256 is
33350c61038e71dfb3d45a76aed04bf5481e6d5500cb780f6e98db8bbd15a28c.
Word uses native editable paragraphs and headings; all3rendered fixture pages
were inspected after removing a default template title border. Content is checked
against the same approved source.78 focused/registry checks passed47.94sec.
The local launcher installs python-docx1.2.0 in its own environment. Legacy
Factory runtime requirements remain unchanged; test setup includes the new
dependency through requirements-dev.txt. Final whole-Factory release is pending.
