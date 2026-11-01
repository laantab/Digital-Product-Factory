# Saved Projects memory repair — October 31, 2026 (Pacific)

## Current state
PR #105 is merged. v1.9.66 is LIVE on web service srv-da8qisegekts7380vdvg, deployment dep-dbjcqcjncjis73dfb68g, exact merge b86a666172186322c7b697e0ec2ca81af8ef1c9a, live at 2026-11-01T05:26:26.772326Z. The owner reported a persistent Saved Projects loading error after a separate-browser success. Do not dismiss a fresh customer failure based on another browser's success.

## Confirmed failure and repair
Render server_failed events explicitly recorded 512Mi OOM kills at 04:26:28, 04:27:31 and 04:33:42 UTC November 1. List requests overlapped these failures. Native/JSON/image temporary memory remained retained between serialized requests. The existing serialized_listing wrapper now collects cycles and returns free glibc native heap pages before and after each read, including exceptional exit. Platforms without native trim retain portable cleanup. No product records, visibility/ownership checks, validation logic, generation implementation, production settings or paid services changed.

A controlled fragmented-native-heap regression retained 64,126,976 bytes before repair and 471,040 bytes in the final standalone check. The cyclic temporary-object regression also failed on the old implementation and passes with cleanup. These establish the cleanup behavior; they are not a complete allocation profile of production.

## Test evidence
Tested runtime head 17370deee9bf4cc1d049e3453d7196c2aa23958d, source tree b7fb5b5d3128e1068ee7589d623937df7edab038, base f16ebac1e63efb83b2d14d7302977c12ce645b3d.
- Existing Saved Projects protections before: 54 passed.
- Same protections plus new regressions after: 56 passed.
- Fast Stability Gate: 822 passed, 60 files.
- Unchanged full release script: 3,386 passed, zero failures/errors/skips, 2,477.22 seconds, zero paid calls.
- JUnit SHA-256: 7372d3898d39aeafdb884b197a9a53aa714650dfdd9a711f6ebe0ebdc0238a30.
- Both GitHub workflows succeeded (runs 41274201191 and 41274201054).
- Exact original Room-by-Room preservation PDF/ZIP pair restored in isolated testing and unchanged expected checksums passed; no customer bytes committed.
An initial fresh-environment stability run had missing Chromium, shallow-history failure and a skip. Dependencies/history were restored; the completed full and fast runs above supersede that environmental attempt. No assertion was weakened.

## Live checks
Browser displayed v1.9.66 and existing finished/unfinished product rows. Four sequential Saved Projects loads completed HTTP 200 with the existing 3,241-byte response. In-progress responses also returned HTTP 200. Finished Small-Space Home Organization still showed PDF/ZIP controls; Mindfulness in Motion remained honestly marked Needs correction. No build or approval was triggered.

No new server_failed/server_restarted events occurred from deployment through 05:34 UTC. Sampled memory bytes: 05:27 245256200; 05:28 359038980; 05:29 464609280; 05:30 409100300; 05:31 409100300; 05:32 409313280; 05:33 432824320 during another load; 05:34 409104400 after completion. The later request returned to the prior settled baseline rather than continuing the earlier rise. Limit is 536870900 bytes. This is observed repeated-use verification, not a long-duration guarantee.

Earlier same-session project 23 download verification: HTTP 200 PDF 11,558,208 bytes, 56 readable pages, SHA-256 e25f2da4a1ae4acca49b6e204f4861f90be331b627ea41b2af83c70434f906c6; HTTP 200 ZIP 29,756,231 bytes, SHA-256 b9e71f6dc97fbe121a91a6cd6caa85181403c6128167fad96fb25a18349036f0. CRC passed, embedded ebook.pdf equals standalone bytes, both match current listing metadata.

## Next actual work
Owner should hard-refresh the Factory to load v1.9.66, then open Saved Projects. A fresh production topic-to-book journey and separate builder version/deployment remain unverified. Keep issue #98 and completion automation tied to stronger complete-one-button criteria. Never describe this scoped list-memory repair as completion of every historical 40%/50% stall. If the owner reports another list error, check exact timestamped server events and request failures first; do not repeat generic retry advice.
