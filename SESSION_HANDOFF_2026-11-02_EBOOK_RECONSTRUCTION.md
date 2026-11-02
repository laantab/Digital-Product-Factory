# Book Studio reconstruction checkpoint — November 2 2026

Candidate VERSION1.9.69. Source is isolated in services/ebook_v2, standalone
loopback5088 with separate SQLite/auth/storage. Legacy app.py, customer files,
production database/configuration, billing and other generators are unchanged.
User authorizes continued work and access to GitHub/Render. No paid calls.

## Implemented and checked
Durable fenced per-stage jobs, bounded validated repair memory, partial drafting
and expansion, local-only Ollama writing/review, automatic/manual decisions,
three saved cover previews, bounded Pexels/Unsplash stock acquisition with credits,
source-derived chapter overviews, owner editing and linked retained editions.
PDF/EPUB/Word/Markdown/cover JPEG/ZIP exports verify actual bytes and package
identity. Eligible24–150page interiors get measured6x9B&W white-paper print packs;
that is this renderer's range, not Amazon's maximum. KDP Previewer/proof required.

88 reconstruction cases +9 protection +31 version cases:128 passed83.74sec.
This includes actual browser preview loads, worker restart, edition edits and
unchanged original PDF bytes. API fixtures prove protocol/limits, not live-key
search quality. A manually selected public Pexels image was checked in3covers,
all6PDF fixture pages and all4Word fixture pages. EPUBCheck5.4.0:zero errors or
warnings. Mechanical QA text is NOT FOR SALE and is not topic-quality proof.

## Failures and precise corrections
The full Factory run at e140f60 source tree35d1de3 passed3468 cases and failed
one release-note heading contract,1071.75sec. Corrected CHANGELOG and current
version checks pass31cases; whole gate must run again on frozen final code.
Actual1.7B/4B books reached technical READY but manual text review rejected
repetition, markup, author-experience invention and stray CJK text. Independent
guards cover these defects. Design name wellness had leaked into model briefs;
new brief filtering prevents it. Actual fresh8B run retained titles then failed
outline when the8GB test environment exhausted memory during overlapping full
suite/model work. Kernel oom_kill counters and provider logs confirm it. Do not
count it as model acceptance; run inference separately after tests. Memory
exhaustion now has a safe specific message and no identical automatic retries.

## Next required work
Publish and verify this exact source checkpoint before more work. Last prior
remote backup is e140f60e7379ee731b9be67962d054007aa35c2a on
rebuild/ebook-engine-v2-20261102. Native git has no push credentials; use GitHub
create_tree/create_commit/update_ref with expected SHA and exact tree comparison.
Never commit runtime DBs, generated books, credentials or preservation originals.

Run fresh local8B acceptance without concurrent large tests; inspect actual text
and every page, not just READY. Default-size8x650 and Windows RTX3060/8B execution
remain unproved. Authenticated stock search needs configured provider keys.
Market demand, external factual/originality certification, hosted SQL/R2 parity,
Windows execution and deployment remain uncertified. Do not claim completed
replacement or legacy70percent repair. Current source is not enabled in the
hosted Factory. Production configuration/cutover remains a distinct boundary.

## Runtime evidence locations in this workspace
Original source checkout factory; isolated visual-development checkout factory-visuals.
Frozen first full gate:/tmp/factory-v2-full-release.log. Focused final:
/tmp/factory-v2-visuals-freeze-tests.log. Failed8B resource pilot:
/tmp/factory-v2-fresh-8b-topic. Ollama binary:/tmp/factory-ollama/bin/ollama;
models:/tmp/factory-v2-topic-pilot/models. CPU memory ceiling8GiB. Run server
and client as children of the same exec orchestrator; separate exec loopbacks
are isolated. Current real-model harness:/tmp/factory_v2_fresh_8b_topic.py.
Actual original preservation PDF/ZIP are restored, ignored by git and hash
verified. Keep these exact bytes for the full gate; never substitute newer PDFs.

## Remote continuation after execution loss
The local execution environment became unavailable. Runtime source through
8b8b2e4e0083e8ec630b92021d0fd6f4a6f2221b was already backed up. The last
observed local eight-chapter 8B pilot had744words saved and was reviewing
chapter1; its final result is unknown. Do not claim it finished or is running.

GitHub PR107 is draft. CI run41498734431 passed97Studio/protection cases on
Windows/Python3.14 and Linux/Python3.12,31version cases and914fast-gate cases.
The model job in that run failed during setup because the official asset is
tar.zst, not tgz. The URL and pinned checksum are now verified against the
official release. Existing fast-gate workflows now install python-docx as a
test dependency. No application runtime files changed in those CI fixes.

The prior explicit acceptance criteria also require six distinct templates and
one AI operation per processing step. VERSION1.9.70 separates copyediting from
independent recheck and checkpoints the pending review. Its fixed editorial
budget is five attempts; two new tests must pass in CI before acceptance.
There are still only three templates. Do not call the complete rebuild finished.

Fresh model acceptance now has its own workflow, triggered by changing
release_evidence/ebook_v2_model_acceptance_request.json. Request it only after
the next runtime candidate and its checks are ready; no request file exists
yet. This avoids rerunning an expensive fresh book for every intermediate
source checkpoint. The former955d660 model run is baseline evidence only.
No customer artifacts, runtime databases or credentials were committed.
