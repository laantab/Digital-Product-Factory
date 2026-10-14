# Coloring background build repair — v1.9.39

Owner approved the background coloring workflow after the 2026-10-14 live failure.
Render event evt-db7tcics728c73bd5t60 reports OOM kill at 19:21:45Z, limit 512Mi.
The coloring request began at 19:17:37Z. The website restarted; the customer saw 502.

## Changes

Workflow-mode coloring requests are recorded atomically and handed to the existing
build_ebook task, which dispatches coloring records to their own driver. No new
service, schema or secrets. Queued metadata and leases survive requests/restarts.
The website does not generate artwork or render the finished background package.

Source images are verified in shared storage before the next image request.
Prompt plans are persisted and reused. Ambiguous interrupted image requests block
instead of being automatically billed again. Lost leases and failed handoffs are
visible with Continue saved build. Preview stages retain cover/sample approvals.
New jobs reject page counts that would silently expand a paid request (4 -> 12).
Existing completed books, legacy PDF bytes, exports and inline execution stay intact.

Print prep uses exact RGB thresholds through image histograms and closes image
buffers. A separate process measures native peak memory below 256 MiB for twelve
300-DPI print pages. Progress is restored when reopening Product Factory; finished
PDF/ZIP downloads reuse the builder's checked package. Metadata Save preserves
server checkpoints and original PDF bytes.

## Verification

Before edits: Fast Stability Gate 715 passed. First after run: 721 passed, two
failures (missing explicit invite shared-file unlock; memory check incorrectly
included inherited pre-exec pytest high-water memory). Both were corrected:
invite baseline tests are preserved and its registry now records the exception;
the native memory check reads the new process's actual VmHWM on Linux (Windows
uses PeakWorkingSetSize), without raising its 256 MiB limit.

Focused background cases: 11 passed. Existing coloring/workflow/route checks:
88 passed. Actual browser refresh-to-PDF/ZIP fixture: passed. Provider output is
local fixture artwork; no live paid calls or new production books were used.
Final Fast Gate: 726 passed. Full release: exactly 3077 unique cases, no missing
or duplicate nodes, zero failures/errors/skips. The unchanged official release
runner's compile, JS, manifest and JUnit checks passed with isolated partitions.
Original before/after reports remain under /workspace/scratch/14eabf73e52d.
Remote verified core: 40e15763d6163aac5740528c13e12417c1f904a9; tree
579ba5031b1ebc8be5b6a677f4eaa83f78b4f887 matches the tested local core.
Word Search, Coloring Book, Crossword and invite protection are relocked at this
real verified commit. Final metadata checks and deployment remain pending.
PR57: https://github.com/laantab/Digital-Product-Factory/pull/57.
Both Render services are on main with On Commit auto-deploy (owner screenshots).
Do not claim live until website/builder deployments have been verified.

## Original failed production attempt

No new production generation, resume, or regeneration was performed for checks.
The earlier failed synchronous attempt did not record a durable build; recovering
its artwork has not been proven. Do not claim the original sea-creatures book is
finished or that its previous provider charges have been recovered.
