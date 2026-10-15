# Automatic coloring completion recovery — v1.9.42

Owner authorized automatic recovery after Project21 published its PDF and ZIP but
lost the final database save. Current base47cf2ab (v1.9.41), PR59 merged and both
Render services verified live. Saved Projects listing and PLANETS Open verified.

## Preservation and live evidence

Project21 Deep sea creature remains the sole target for completion recovery.
Existing package22940f0253774431b91af4041086a871, original PDF15492430 bytes,
SHA256 a3652fc4143f1ceed4a245d4695a40e21e5f0a4ae97c44a519d010b6265a8fc0;
ZIP12584170 bytes SHA256 16d9c25fe9371d8f73cbfe172bac86650e335991f4f5391f87b536e80e4a65fc.
Read-only bounded SQL reconfirmed running checkpoint,3 saved images, filename and
matching content_digest. Do not regex-match or cast the full24MB JSON in Postgres:
a full regex query caused EOF; bounded position/substrings read successfully.
No regeneration/resume/re-export/paid calls used. Project20 and legacy exports
must remain untouched. User Save consent is preserved; recovery does not mark an
unsaved build user_saved. Owner's original iPad status poll can reopen completion
and show the existing Save choice after recovery.

## Implemented

A metadata-only daemon checks up to10 expired/failed coloring jobs per minute,
rotating through IDs without loading every book. It shares the listing memory
lock. Startup, authorized status polls and Workflow retries recognize approved
stored exports. PDF must match stamped original content/asset identity; ZIP must
pass CRC and contain exactly that PDF. Files are never written by recovery.
New completion receipts bind export hashes to the exact request/revision.
Pre-receipt recovery accepts only first-revision matching page counts. Unverified
packages stop before paid generation. Web recovery limits each stored object to
64MiB to preserve the512MiB website; oversized objects remain preserved/pending.
No automatic provider retry for ambiguous artwork calls or approval bypass.

Completion and export metadata save together with three bounded fresh-read
retries, including uncertain commits and optimistic conflicts. Other customer
metadata and Save flags survive. Connection outages leave durable files for the
next check. Monitor is off under tests and starts once in production. No new
service, secrets, schema, billing or DNS changes.

## Verification

Baseline Fast Gate737 passed (54 files,422.57s). New recovery20 tests and
version/protection metadata checks60 passed. A real two-page local-provider build
lost the final save, lost its temporary directory, then recovered the original
PDF/ZIP with exactly3 initial artwork calls and zero additional calls. Stored
asset checksums and original project fields/identity remain unchanged.
One test initially assumed its job was in the first10 rows despite earlier test
fixtures; isolated its scan cursor and verified bounded rotation. No preservation
assertion was weakened. Final release gates pending; do not merge until green.


## Final release verification

Verified core source at actual GitHub commit9c652329693e23af4a094436f660a88e10f2e581,
tree d963756e9a131c04c747dca1a61d8aa4b5f1a867 (identical to local f934049).
After Fast Gate757 passed across55 files (548.69s). Full gate3110 passed across
223 files, failures0/errors0/skipped0, exact unique coverage missing0/duplicates0.
Python compile, JavaScript syntax and manifest validation passed. No paid calls.
Results ../recovery_full_release.log and ../release-1942-recovery-results/;
Fast ../recovery_fast_after.log. Four protections relocked at that core commit.
Read-only live preflight confirms Project21 first revision, full generation,
qa_passed true, fields.pages2 and original content/asset digests. No live recovery
is claimed before deployment; verify boot log, Project21 complete/export_ready,
job SUCCEEDED, original PDF/ZIP asset hashes, and unchanged user_saved consent.
