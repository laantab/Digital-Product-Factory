# Factory 1.9.16 repair — release verification passed

## Current state

The repair is on `fix/v1.9.16-guided-ebook-generation`, PR #33. The final release
gate passed. Consult PR #33 and the live website for the subsequent merge and
deployment state; a passing local gate alone is not a deployment claim.
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

## Final release verification

The final full gate completed at verified code-and-release-note commit
`380446bd5236d063095b55ef8f46ffb4fd6cacce`: **2,954 passed**, zero failures,
zero errors, zero skipped, in 1,324.91 seconds. The enforced script reported
`PASS: release gate completed`. No paid API calls were permitted or made.
All 209 acceptance files ran, including the real browser customer paths,
polling regressions, guided title-and-cover flow, quality gates and original
reference-file preservation test. This handoff update changes documentation
only after that passing run.

## Verification history

### Update after the owner's reference upload

The owner supplied `Factory_Reference_Files_20261007-132004_3d857a.zip`.
Both original exports matched the hashes below and were restored without
altering their bytes. The preservation test now passes (1 passed, 27 deselected).
The fresh Fast Stability Gate passed 710 tests in 163.15 seconds.

The complete full gate ran all 209 acceptance files: 2,953 passed, one failed,
zero skipped, in 1,303.46 seconds. Its only failure was the missing required
customer-facing section headings in the new 1.9.16 changelog entry. That
documentation has been corrected; all 31 version-management tests now pass.
The final full gate was then run with the corrected notes. No production code
was changed after the completed 2,953-test passing portion of the first run.
Main was unchanged and PR #33 remained a draft during those checks. The final
passing result above supersedes the earlier blocker.

### Earlier blocker, retained as history

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
