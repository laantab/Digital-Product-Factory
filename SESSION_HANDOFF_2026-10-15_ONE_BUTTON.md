# Ebook one-button completion — 2026-10-15

## Start here

Owner authorized improving one-button completion and explicitly required preserving working coloring books, crosswords, ebooks and all other generators. Baseline main: 2da48d6 (v1.9.42). Work branch: work/ebook-one-button-reconnection. This release is v1.9.43.

## Scope

Only ebook progress/reopen browser functions change. Temporary network/server errors reconnect with capped backoff, retaining last reported progress. Old pollers retire before a newly opened book owns the single progress-request lock. Late responses cannot render into the current book. Access-denied responses stop safely. No generation retry counters are reset by reconnecting. No new project is created by reconnecting. Intentional guided cover/picture holds and real build failure remain explicit. Existing automatic and custom creation choices remain intact.

No Python production logic, database, generator, rendering, packaging, provider, secrets or hosting configuration was changed. Word Search, Coloring Book, Crossword and the narrow ebook_one_button_completion protection are LOCKED at tested source commit 7acc927ab444e7c37f4280747217865d93f2daf5. The broader ebook feature remains PROTECTED; this is not a claim that every ebook feature is proven live.

## Verification

Baseline Fast Gate: 757 passed in 497.76 seconds, 55 files. Guided real-output fixture: 6 passed in 148.89 seconds, including title/cover choice and real PDF/ZIP delivery. New real-browser tests first reproduced four failures across disconnect, HTTP503, reopen-status failure and overlapping reopen/late failure. After repair, five browser cases passed in 16.42 seconds (including denied requests); routing/version/registry checks: 57 passed in 3.32 seconds. First release run encountered the pre-existing optional preservation skip because original Project351 files were absent. Retrieved original Factory_Reference_Files_20261007-132004_3d857a.zip (Library libfile_7a2dd8b025d881918b2522acb5a4bbed); both exact historical checksums matched and the unchanged preservation test passed. Restored only gitignored reference bytes, never regenerated them. Interrupted the first run and restarted the entire 223-file gate with originals available. The complete run passed: 3115 unique tests, all 223 manifest files covered, zero failures/errors/skips, 3499.846 seconds. Tested source tree: b1e7744e4783d24735767e7100dfc1e5e48d9a8d. Paid/external calls blocked; customer data and outputs are isolated.

## Publication

Publication and exact served-asset verification are tracked durably in PR #61: https://github.com/laantab/Digital-Product-Factory/pull/61. Expected app.js SHA256: 09ee55a8de03d87e155a4e2b98132b59931c16392055fff7ab4f7d3e38e8a070. Preserve original PDF/ZIPs and customer projects. No live generation is authorized by these verification fixtures.
