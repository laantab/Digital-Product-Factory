# Factory 1.9.16 repair — awaiting release verification

## Current state

The repair is on `fix/v1.9.16-guided-ebook-generation`, PR #33. Main and the
live website remain at 1.9.15. Do not describe this change as deployed.
Implementation commit: `157dc7f610377a802012f5c55164aff3b35d4004`.

## Customer behavior

- The ebook workspace's primary **Generate Project** button runs research,
  draft title, outline, manuscript and verified visuals automatically.
- Generation pauses at one combined title-and-cover choice. A changed title
  updates the cover previews while preserving manuscript content, verified
  image paths, attribution and the paid-call ledger.
- Choosing a passing cover resumes design, review, preflight and PDF/ZIP export.
  Quality failures remain blocking. No paid-image authorization is bypassed.
- Existing individual workspace controls and the older Build My Ebook entry
  path remain available. This change does not migrate every legacy entry point.
- Stale workspace polling stops after navigation or a newer action, including
  when a delayed workspace response arrives after cancellation. Failed or
  cancelled polling no longer triggers a later success toast. A polling timeout
  tells the customer to use Continue to recover progress.

## Completed checks

No paid API calls were made. Tests use isolated databases and local fixtures.

- Before and after Fast Stability Gate: 710 passed on each run.
- Additional shared-file protected suites: 160 passed before, 161 passed after;
  the extra passing test is the new guided browser flow. 45 subtests passed.
- New polling and guided-pipeline tests: 9 passed.
- New Chromium customer path: passed with a changed title, loaded cover
  previews, selected cover and actual PDF/ZIP downloads.
- After relocking: registry integrity and enforcement, 9 passed and 97 subtests.
- Python compilation, JavaScript syntax and acceptance-manifest validation
  completed in the release-gate run.

## Release blocker and next action

The full release gate was started with all 209 acceptance files. It reached
33% before being stopped after a confirmed environment blocker. It was not a
completed passing run. The independently reproduced blocker is:

`tests/test_warm_wellness_template.py::RevisionIdentityAndIsolation::test_preserved_project_351_package_is_untouched_if_present`

Invoking `-k preserved_project_351` reproduces it independently:
1 skipped, 27 deselected. The skip reason is
"Project 351 preserved package not present on this machine". The release script
explicitly rejects any skipped acceptance test.

Restore the original reference exports on the release-check machine:

- `exports/ebook-visuals-local/ebook.pdf`, SHA-256
  `6202e3a559db9313b61ec2d54ff689f6236a3b037308820bc77cfedf4d01f5bd`
- `exports/ebook-visuals-local/package.zip`, SHA-256
  `5044f086b7335e139bcec94e1b743c4f7effd4fe9eb7738973140176ef6d5c1f`

Do not regenerate substitute files or weaken the existing preservation test.
Then run `python scripts/run_factory_tests.py` to completion, resolve any genuine
failures, and only after a passing gate merge/release and verify the live build.
No Render configuration or secrets were changed.

The four LOCKED shared-file owners were explicitly unlocked before editing and
relocked at the verified implementation commit after their before/after
protected checks. Their relock records protected behavior, not full release
approval.
