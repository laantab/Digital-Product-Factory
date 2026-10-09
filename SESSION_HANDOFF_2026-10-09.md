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
Full 1.9.18 release validation is running; do not deploy before it passes.
No paid calls or real product generation were made.

The owner asked us to stop the manual Render navigation loop and continue
completion work directly. Do not ask for console commands or repeated tests.
Prior authorization covers routine commit, push, merge and deployment.
Budget restrictions and preservation of existing customer artifacts remain.
