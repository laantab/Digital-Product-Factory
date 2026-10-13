# Factory completion: release review and final customer path

The owner authorized independent completion on October 12 at 11:49 p.m. EDT. No further routine permission requests are needed. Preserve the no-additional-spending rule, accepted manuscript and photographs, original exports and rollback paths. Final human visual/editorial judgments remain the owner's decision; never mark them accepted merely to clear a gate.

## Verified production state

GitHub PR #44 is merged at 0d5f1ad4eb164dab32a14744c183fe2f458d1a3c. Render website deployment dep-db6po5e7bikc73ffsa90 is live at v1.9.26. Actual Project 20 cover loaded; the owner approved its title and cover. The normal Finish button completed cover, design, preview, preflight and export. The downloadable PDF has 56 pages; the ZIP passed integrity and its embedded ebook.pdf is byte-identical to the downloaded PDF. Project 20 is saved, remains DRAFT, and reopens to its completed download screen without generation. Final release review/approval is still pending.

## Current repair

Opening Editor-in-Chief review caused HTTP 502. Render event evt-db6q5hss728c73arvtlg at 2026-10-13T03:17:27.509562Z confirms a 512Mi memory-limit kill. The exported-book review copied embedded images during text extraction, retained native image caches between pages, and allowed simultaneous full scans. Local v1.9.27 repair extracts text only, evicts MuPDF cache after each image-info pass, closes resources, and serializes scans. The actual saved-book standalone reproduction peaked at 289 MiB before and 204 MiB after. No exports or production data were modified by the code repair.

The same review falsely rejected the action-plan chart's distinct 30/90/365-day numeric milestones as repeated points. Distinct numeric tokens now distinguish comparison/timeline entries; repeated identical entries remain rejected. The repaired actual-book review reports all 13 visuals and Needs human review, with no hard findings.

## GitHub and validation

Draft PR #45: https://github.com/laantab/Digital-Product-Factory/pull/45 . Published source commit 4af372353924ca72bd896c783e85e8790f74d0bb has tree d6473d58c71e991f8bb583e7154832c33aa000c2, identical to local tested source tree. Not merged or deployed yet.

Baseline Fast Gate: 710 passed. Baseline review/browser suites: 33 passed. Initial post-change run: 36 passed plus one new test failed because the installed PyMuPDF store_size API is a stub. Corrected the test to verify actual full cache-eviction calls on every page and at scan completion. All 35 new regression/version checks passed. Protected lock checks: 9 passed. No test assertion about customer quality was weakened. The full 214-file release run stopped around 31% without final XML or completion; it is NOT counted as passed. Required acceptance coverage completed in four isolated manifest partitions: 873 + 732 + 724 + 681 = 3,010 unique cases. One reference-preservation case in the 732-case partition initially skipped because the isolated checkout lacked the real Project 351 files. Copied the already-verified originals and reran that case with the standard gate: one passed, no skips. XML reconciliation against all 3,010 collected node identities proves no missing cases and no unresolved failures/errors/skips. Preserve the original reports and corrected rerun; do not describe this as a single uninterrupted all-green run. Do not rerun already-proven completed work because a record is stale.

## Scope and next steps

Deploy the review repair only after full required coverage passes; verify v1.9.27 live, retry the actual review, inspect all returned findings, retain PDF/ZIP fingerprints, verify no new OOM event, and prepare the final review for the owner. Themes and one-click ebook orchestration are implemented; Command Center records were stale and now state implemented with acceptance pending. Cross-product unified editing, EPUB/Kindle, Flipbook and marketing remain separate unfinished extensions, not claimed complete. Do not add paid calls or hosting changes to clear this scope.
