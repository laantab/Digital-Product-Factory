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
Fast/full final release gates and deployment are pending. Do not claim released
until website deployment and builder deployment have been verified.
