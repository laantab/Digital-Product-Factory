# October 20 editorial and output quality — performed early October 18

Owner authorized continued work while away. Continue from this record, not older pending-release notes.

## Current candidate

Version 1.9.48, PR71. Exact tested runtime source: GitHub 3778616d5bc29aea7b5d090af111fbb952cb3a44, local 62607c209781b5de9c7465a0304435a5721e1373, tree 9bda2f6dc7c914d9b53de74360f4972bcb6534c6. Full release verification PASSED: 3,197 unique cases across all 230 files; zero failures/errors/skips and exact identity reconciliation. All 3,191 baseline cases retained. Deployment VERIFIED: PR71 merged as 4fb69ac36e4903e6f4059e03dceb7632d18913d0. Website deploy dep-dbagaau7bikc73ekc2j0 LIVE at 2026-10-18 17:44:22 UTC; authenticated footer shows v1.9.48. Builder startup log at 17:44:15 UTC explicitly reports VERSION1.9.48. Saved Projects loaded existing coloring/word-search/ebook records. Project20 opens its reviewed prior version at100% with saved PDF/ZIP links and the newer-draft review notice. Its raw updated_at, DRAFT state and ledger14/$2.35 are unchanged before/after. No production generation or edits. Local original recovery pair hash comparison passed; no new live download byte comparison in this check.

## Reproduced defects and fixes

1. The free proofreader closed a protected Markdown block on a shorter inner fence or a fence followed by example text. Four regressions failed before the fix. Track the opening marker length and require a matching, sufficiently long, otherwise empty closing fence. Outside prose is still corrected and edits remain reversible.
2. Practice-step extraction accepted instructions up to 150 characters but shortened them to the 78-character key-point-card limit. One regression reproduced ellipses replacing the instruction endings. Preserve the complete eligible instruction for the existing wrapping renderer. Other visual selection and rendering behavior is unchanged.

Only services/ebook_copy_editor.py and services/ebook_visual_pipeline.py production behavior changed. No coloring, crossword, word-search or planner implementation changes. No production database, export, environment, billing or DNS changes; no paid provider calls.

## Verification already completed

- 82 editorial/editor/chart/export baseline cases passed.
- 86 editorial cases passed after the four source-protection fixes.
- New real integration case passed: preview/apply free proofreading, invalidate old release approval, rebind design, render actual PDF and ZIP, extract corrected PDF text, and require the identical PDF inside the ZIP. Original input stays unchanged.
- 71 visual/readability cases passed after retaining full practice instructions. Rendered a diagnostic three-step graphic and visually confirmed complete wrapped instructions.
- 40 version/registry/enforcement cases passed after committing the candidate and completing the changelog headings. After extending the dependency/test registry at the exact verified source, all 44 version/protection/fast-gate-coverage checks passed. Dependency and compilation preflights also passed.
- The earlier 3,196-case release run was intentionally interrupted when page review exposed the second defect. It is not passing release evidence. Final candidate passed all 3,197 cases across the complete 230-file manifest.
- PR67 remains an unfinished draft mode-policy foundation and is excluded. Existing automatic generation already applies conservative copy edits. Optional provider rewriting is not advertised as completed; no new mode interface added.

## Preserved sample review

Reviewed all 64 rendered pages of Project20's original PDF on eight contact sheets, with text geometry and cover rendering inspection. Exact PDF SHA256: 20792e8fcce4ab4fcc7daa8e49df1d0a634f7c624d9197d346d0fda83f8d025d. ZIP SHA256: f7cc37a90f71e8563039c412f23f7ba11deff52edb055419117197921d572d26. Both ZIP CRC checks pass; embedded PDF is byte-identical. No files were regenerated or approved.

No blank pages, no extracted text below 8pt, and no interior extracted text outside page bounds. The cover's off-page text box is invisible accessibility text (PDF render mode 3), not visible clipped typography. Embedded raster chart text is not measured by extracted-text font sizes.

Recorded legacy review items: the preserved practice chart on physical page27 contains shortened instruction labels; the table on physical pages55–56 continues without a repeated header. The source extraction repair prevents the first problem in future derived practice graphics; do not rewrite the accepted original just to update it. Current table continuation behavior has existing regression coverage. These notes are not a fresh approval of Project20's newer unapproved draft or a full Factory launch certification.

## Next launch work

Final live rehearsal and sample approval remain. Public Factory memberships require verified customer-account isolation and purchase/access proof. Saved Projects responses are small now, but server latency remains: listing still checks candidate output availability and enriches every eligible row before pagination, under a shared serialized-listing lock. Any optimization must retain strict visibility/readiness checks and bounded memory; do not fix latency by removing quality checks or collecting all full project blobs in memory.
