# Ebook slow-chapter lease repair

## Verified production state

Factory 1.9.17 was merged in PR #34 at 61b2759. The website footer was
verified live. The owner's Render screenshot also confirmed the builder
deployment as ready and its startup log as VERSION 1.9.17.

The latest supplied run was for project 18, using the previous 3e92e9c
version. It ended after two seconds. The supplied run list showed no active
jobs and no 1.9.17 runs. Its detailed logs and the project's persisted state
were not supplied, so the reason it exited and the book's completion remain
unverified. Do not claim that a successful workflow run means a finished PDF.

## Current repair

An executor lease expires after 180 seconds, but renewal previously occurred
only after advance_build returned. A long chapter provider call could therefore
leave its job claimable by another executor while the chapter was still being
written. A new regression advances an isolated job clock past lease expiry
during a provider call and requires renewal before another worker claims it.
It failed on the pre-repair executor.

The ebook executor now renews ownership every 60 seconds during a bounded
unit. It stops its renewal thread when that unit exits. Failed renewal stops
the executor after the current unit; it does not finish or release a job whose
ownership it can no longer establish. Crash recovery still uses the original
short lease. No generation, QA, stage, storage or payment logic is changed.

Focused executor, workflow, Continue and registry suites: 103 passed.
Full enforced 1.9.18 release gate: 2,963 passed, zero failures, errors or skips in 1,302.46 seconds, all 209 acceptance files. The first attempt reported missing test-browser errors and was interrupted; Chromium was restored, all five browser checks passed, and the complete gate was then restarted and passed. Install Playwright Chromium when recreating the test environment.

The tested implementation is in PR #35. Merge and deployment are authorized. Verify the new website footer after merging; do not claim project 18 is finished without reading its actual state.
No paid calls or real product generation were made.

The owner asked us to stop the manual Render navigation loop and continue
completion work directly. Do not ask for console commands or repeated tests.
Prior authorization covers routine commit, push, merge and deployment.
Budget restrictions and preservation of existing customer artifacts remain.


## Editor-in-Chief copy editing — PR #36

Owner requested actual editing capabilities on October 9. Implementation is
on feature/editor-in-chief-copy-editing, remote commit a557341, with the same
code tree as local commit 4d3e1ec: f59d8cb838887c22fdf700040b59b972b7215c14.
Version is 1.9.19. The PR is draft pending full enforced release validation.

A distinct offline English rules pass edits new/generated or repaired chapter
bodies before acceptance. It preserves Markdown headings/tables/code, quoted
material, and links; checks the edited chapter against its content contract;
and rolls back any edit that introduces a new finding. Original and proposed
drafts, hashes and edit lists are checkpointed in editorial_revisions and
exposed in the ebook workspace response. Previously accepted chapters are
preserved. No extra provider requests or paid calls are introduced.

Coverage is deliberately limited to explicit spelling/grammar rules, with
advisory long-sentence and estimated-grade suggestions. The generation and
correction prompt also requests grammatical/clarity editing. Do not describe
this as comprehensive grammar, semantic editing, factual verification or
external plagiarism checking. The shared results screen was left unchanged
to avoid expanding this patch to locked puzzle/coloring UI.

Focused checks: 67 copy-editor/editorial/recovery plus 64 manuscript/workspace/
correction checks passed. Originals from the already supplied reference ZIP
match the expected Project 351 PDF/ZIP digests and have been placed in the
ignored preservation-check directory. Full release gate is running. Earlier
attempts were stopped: shared-UI function-lock enforcement required a broader
change, so that UI addition was reverted; then missing original reference
files caused a preservation skip, resolved by retrieving and verifying the
supplied originals. Do not report those interrupted attempts as a passing gate.

Latest owner screenshot confirms project 20 at 30%, reason failed, on builder
1.9.18. Traceback is approve_stage(manuscript) refusing remaining structural/
content findings. This editing patch does not establish the exact remaining
findings or claim that project 20 is fixed/finished. Keep the quality gate;
read those findings before any further correction or paid build.


### Validation outcome for PR #36

Full 210-file gate completed in 1,375.51 seconds: 2,967 passed, one failure,
zero errors and zero skips. The only failure was the new changelog entry
missing the required customer-question headings. No production code changed
after that run. The documentation was corrected and all 61 checks in
version management, Command Center and copy-editor suites passed afterward.
This is combined full-suite plus focused documentation validation; do not
claim the original enforced gate invocation returned PASS. Original PDF/ZIP
checksums still match after testing. No paid calls or live book generation.


## v1.9.20 — existing-manuscript editing completed

PR: https://github.com/laantab/Digital-Product-Factory/pull/37
Published production code: `96029eefbbb4c8e28ad134f443cd233b29cb110e`; tested source tree: `b43ccf45bac0b2104d38795496e8237903b508ad`.

The manuscript reader now links to a dedicated editor. It offers conservative copy-edit suggestions or customer-authored rewrites, a diff and current quality findings, apply, and undo. Saves preserve exact source bytes and original revisions, reject stale writes and active/queued builds, refresh accepted chapters from current validation, cancel stale pending estimates, and require fresh manuscript approval and export validation. Original exported files are preserved. Incomplete chapters can be improved in several saves without changing word-count messages being mistaken for new defects. Remaining findings still block approval.

Validation: the complete 211-file release gate passed with **2,976 tests, 0 failures, 0 errors, 0 skips**, in 1,318.81 seconds. No external or paid calls were permitted. The first complete run had 2,975 passes and one route-classification failure; the editor route was classified as light, 32 routing/editor/lock checks passed, and the entire gate was rerun to the clean result. Browser tests exercise real Review, Apply, and Undo controls. Eight new editor tests are in the acceptance manifest. Invite-protection lock is closed; its hook and exemptions are unchanged.

Preservation: reference PDF SHA-256 `6202e3a559db9313b61ec2d54ff689f6236a3b037308820bc77cfedf4d01f5bd`; ZIP `5044f086b7335e139bcec94e1b743c4f7effd4fe9eb7738973140176ef6d5c1f` remain unchanged.

Coverage: this completes a usable editing workflow, not comprehensive automated grammar or factual verification. Automatic proofreading remains explicit English rules. No Java server, paid service, production configuration, or new provider call was added.

Live follow-up: the public website displayed v1.9.19 before this merge. Project 20’s saved-data navigation returned `net::ERR_BLOCKED_BY_CLIENT`; no workaround was attempted to read that blocked data. Its actual remaining findings and the builder’s current deployed commit were not obtained. Do not claim project 20 is repaired. Check deployed versions after merge, obtain its actual findings, and respect the no-additional-spending constraint.
