# Ebook one-button completion — 2026-10-15

## Start here

Owner authorized improving one-button completion and explicitly required preserving working coloring books, crosswords, ebooks and all other generators. Baseline main: 2da48d6 (v1.9.42). Work branch: work/ebook-one-button-reconnection. This release is v1.9.43.

## Scope

Only ebook progress/reopen browser functions change. Temporary network/server errors reconnect with capped backoff, retaining last reported progress. Old pollers retire before a newly opened book owns the single progress-request lock. Late responses cannot render into the current book. Access-denied responses stop safely. No generation retry counters are reset by reconnecting. No new project is created by reconnecting. Intentional guided cover/picture holds and real build failure remain explicit. Existing automatic and custom creation choices remain intact.

No Python production logic, database, generator, rendering, packaging, provider, secrets or hosting configuration was changed. The three existing shared-app.js locks are temporarily UNLOCKED for their before/after verification, with reasons in the registry. A new narrow one-button completion protection is pending its actual verified commit. The broader ebook feature remains PROTECTED; this is not a claim that every ebook feature is proven live.

## Evidence so far

Baseline Fast Gate: 757 passed in 497.76 seconds, 55 files. Guided real-output fixture: 6 passed in 148.89 seconds, including title/cover choice and real PDF/ZIP delivery. New real-browser tests first reproduced four failures across disconnect, HTTP503, reopen-status failure and overlapping reopen/late failure. After repair, five browser cases passed in 16.42 seconds (including denied requests); routing/version/registry checks: 57 passed in 3.32 seconds. First release run encountered the pre-existing optional preservation skip because original Project351 files were absent. Retrieved original Factory_Reference_Files_20261007-132004_3d857a.zip (Library libfile_7a2dd8b025d881918b2522acb5a4bbed); both exact historical checksums matched and the unchanged preservation test passed. Restored only gitignored reference bytes, never regenerated them. Interrupted the first run and restarted the entire 223-file gate with originals available; do not merge before it passes. Paid/external calls blocked; customer data and outputs are isolated.

## Publication

No release deployed yet. Update this section with actual release counts, actual remote source commit, relock proof and website asset verification. Preserve original PDF/ZIPs and customer projects. No live generation is authorized by these verification fixtures.
