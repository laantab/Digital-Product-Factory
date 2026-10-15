# Saved Projects recovery — v1.9.41

Owner reported Saved Projects would not open, then asked about the coloring book.
Verified main at7378ac6 / v1.9.40 before edits. Do not repeat the preview-count fix.

## Production evidence

Saved records remain: Project20 Eco Home Makeover, PLANETS14, Container Gardening5,
and other records verified by read-only Postgres ID/name queries. Website events
at11:51:25Z,11:52:32Z and11:57:47Z report OOM kills with a512Mi memory limit while
list requests were in flight. Existing listing buffered every full saved record;
sidebar navigation fired both an own onclick and delegated data-go listener.

Latest coloring attempt is Project21 "Deep sea creature", created02:57:20Z.
Its checkpoint records two coloring images and a cover. The workflow failed at
03:00:35Z on a Postgres connection EOF while recording final export metadata.
It still says running, job lease expired, user_saved0. However, all three source
images AND final PDF/ZIP assets were published and approved before that failure.
No production regeneration/resume/re-export has been performed during diagnosis.

Existing package22940f0253774431b91af4041086a871:
- deep_sea_creature.pdf:15492430bytes, SHA256 a3652fc4143f1ceed4a245d4695a40e21e5f0a4ae97c44a519d010b6265a8fc0
- package.zip:12584170bytes, SHA256 16d9c25fe9371d8f73cbfe172bac86650e335991f4f5391f87b536e80e4a65fc
Both existing download routes successfully produced completed browser downloads;
links were given to the owner. Browser/main file synchronization did not expose
local copies, so no attachment, independent binary checksum, CRC or visual QA is
claimed. Project21 final metadata/save status is NOT repaired just by retrieving
these files. Preserve existing data, artifacts and all legacy PDF bytes.

## Changes

Customer listing reads IDs then one full record at a time. It applies the same
visibility, actual output and enrichment checks before retaining only a compact
list projection. Only customer list/dashboard payloads are compacted; legacy
admin/factory-source behavior is preserved. Open fetches the unchanged full record.
A shared lock serializes expensive customer-list and unfinished-ebook reads for
production's one threaded worker. Sidebar clicks now navigate once. List failures
and malformed responses offer retry instead of falsely reporting no saved products.

## Verification so far

Baseline Fast Gate734 passed. New cases3 passed: compact list/full detail/unchanged
stored data; three concurrent list reads over12 records carrying12MB previews,
with native process peak below320MiB; actual browser failed-load retry, single
navigation request and Open retrieving the original full record/fields.
Focused saved/version/registry/enforcement checks77 passed. Initial browser test
caught the duplicate navigation; corrected product behavior. A subsequent test
selector matched both heading and title span; made it a precise heading locator.
No test assertions about artifact identity or visibility were relaxed.
Full and Fast release gates are running. Do not merge before they pass and the
four temporarily unlocked functions are relocked at a real verified commit.
No paid provider calls, production config/secrets/schema changes, legacy deletion,
or changes to the approved Project20 artifacts.


## Completed release verification

Core source tree7003c856dede4d66951ea8549d907bbe4c1d7958 verified at actual
GitHub commit902680a391af674e2cadff0fd430c5a76d242d59.
After Fast Gate737 passed (54 files). Full gate3090 passed, failures0, errors0,
skips0 across222 files; exact unique-node coverage, missing0, duplicates0.
Python compile, JS syntax, manifest checks passed. Paid API calls permitted0.
Four shared-dependency protections relocked at that verified source commit.

The first full run encountered an already truncated local reference PDF and was
superseded. Before repair it was1971200 bytes, SHA256
adb374ba4eb8e44b9761cf2848dbc0e74092addbb8307b67746d7cce6f7f091b,
an exact prefix without EOF of the original4951720-byte PDF. The intact companion
ZIP passed CRC and contained the original PDF matching expected SHA256
6202e3a559db9313b61ec2d54ff689f6236a3b037308820bc77cfedf4d01f5bd.
Preserved the prefix at ../fixture-preservation-20261015/ebook-prefix-before-recovery.pdf,
then restored only that local fixture from the verified original ZIP and checked
its hash before the final full run. Production exports and preservation tests
were unchanged. Final reports: ../release-1941-saved-final-results/ and
../saved_products_full_release_final.log; Fast ../saved_products_fast.log.
Project21 metadata/save status still needs a separate recovery; retrieval did not
mark it completed or saved. Existing original PDF and ZIP remain accessible.
