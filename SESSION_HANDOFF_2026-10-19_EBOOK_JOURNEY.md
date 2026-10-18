# October 19 beginner ebook journey — started early October 18

## Scope

Owner requested starting the October 19 milestone immediately. Baseline is live v1.9.47 (main 78069be3babc5b429e486e6cb3e9f819c7145f3b), with post-deployment evidence at b05f53408d45d12000153a604ebf5bc6ee83a4a8. No production implementation changes were needed in this verification pass. Protected generators, production data/configuration, version and release remain unchanged. No paid provider calls.

## Stronger acceptance checks

- AI-recommended and custom browser entry checks now observe actual /ebook/build requests instead of returning a simulated finished response. Deterministic local providers feed the real orchestrator, database, release gates and PDF/ZIP exports. Real download buttons are clicked; ZIP CRC and byte-identical embedded PDF are required. Existing creation-mode/template assertions remain.
- Guided title/cover browser check now closes the tab after saving a selected title, opens a new tab, navigates through Saved Projects and Continue, and verifies the same title survives. Completion must retain the same project IDs and deliver an intact ZIP containing the exact downloaded PDF.
- Download selectors target the ebook screen, avoiding ambiguity with other saved products. No timing assertion, quality check or product guarantee was weakened.

## Validation

- Baseline Fast Stability Gate: 767 passed, 56 files, 0 failures.
- Baseline full real-browser file: 5 passed, 162.96 seconds.
- Recovery/routing batch: 71 passed, 0 failures/errors/skips, 137.99 seconds.
- Final tab-closure/title-choice/download scenario: 1 passed, 80.20 seconds. Four other browser cases passed unchanged in the preceding full-file run; that run's new tab scenario failed on test setup, then was corrected and rerun.
- Final complete creation-mode suite: 15 passed, 0 failures/errors/skips, 264.69 seconds. Includes both real browser entry paths and all existing reconnect/denied-request checks. The isolated October 19 engineering acceptance milestone is verified; live release rehearsal remains a Day 5 requirement.

Earlier expanded checks exposed test setup issues: ambiguous navigation controls, a fixture project name classified as internal metadata, a missing unittest helper instance, and ambiguous Download PDF buttons after real saved products existed. These were corrected in the checks. No production defect was inferred from these setup failures. The first complete creation-mode run with real exports passed 13 cases and failed 2 on ambiguous PDF controls; the complete affected file then passed after scoping those controls.

## Exact source

GitHub source commit: 19d5156b5d6edcb43cf3a17f0bd0037cc5329685.
Source tree: ab81b7211d66e00dc1d1688399066a99f0e5f745.
Local source commit: 7d57018 (same tree).
Branch: work/oct19-ebook-journey. Tests only; no production deployment is needed for this change.

## Remaining launch work

This is isolated deterministic-provider proof, not a new paid production build or a public-launch certification. Final live rehearsal, full sample-page review, customer-account isolation for public memberships, purchase/access proof and Saved Projects server latency remain launch work. No marketing implementation or additional feature expansion started.
