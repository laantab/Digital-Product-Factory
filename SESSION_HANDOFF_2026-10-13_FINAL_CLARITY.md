# Final ebook clarity repair — 2026-10-13

## Start here
Version 1.9.29 is live; version 1.9.30 is pending release checks and PR 48 merge.
Project 20 manuscript and approved cover remain unchanged. Three approved photos are restored to 2400px; nine charts are 2800px. Larger print uses 13pt sans body and 11pt captions. Current downloaded PDF is 64 pages, 10,413,549 bytes, SHA256 1e324c6b1959a67822976ec6c385dece61168fccd90d585d70112b04b908ae0d. ZIP is 28,889,845 bytes, SHA256 f608f84075b81b6de44e8a40547c9a33d112f495d7a18abebe34a70e7231cde5. This is not the final approved revision.

## Fixes in 1.9.30
Image paragraph keeps captions on the same PDF page. Review controls select the clicked visual by array index, even with two visuals on one page. Image analysis is bounded to 1200px while native dimensions are retained for real printed DPI checks; chart label-size and approved-file checks remain unchanged. Local real-book scan recognizes 13 visuals with zero hard failures, peak RSS 261.9MiB versus 291.9MiB before; including app import peaks at 286.3MiB. Focused checks: 37 passed. Full gate and production verification remain pending.

## Production diagnostic safety
Never repeatedly cast projects.data to JSONB on production: Project 20 has a roughly 15MB TEXT preview record. Our diagnostic queries caused PostgreSQL process OOM/recovery at 12:59:37 and 13:03:01 UTC. Use lightweight jobs/assets queries, octet_length(data), actual customer UI, and downloaded files. Do not change DB schema, hosting plan, secrets or environment configuration. The subsequent website review OOM at 13:44:44 is separate and is the current repair target.

## Completion sequence
Pass full gate; publish LOCKED invite registry (last-known-good app source 7decdbfbe9bf26009406bcf844099f4a189b23b5), merge PR48, verify website and builder 1.9.30. Reflow existing Project20 without rewriting manuscript or acquiring more photos. Verify PDF/ZIP and caption placement; complete actual release review and owner-approved visual decisions, then normal product approval. Preserve all earlier exports. Replace existing Library PDF libfile_4276d52d69c4819193af95ec96e82ee6 and ZIP libfile_b3a77cb1d76081918fd43a01ff0193a4 using expected version0 after final verification. Do not claim final approval or all Factory functions verified until observed.

## Spending
Last verified Project20 ledger: 14 paid calls, $2.35. No paid provider calls authorized for repair. No hosting upgrade, configuration changes, marketing implementation, or deletion of originals.
