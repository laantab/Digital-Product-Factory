# Ebook reconstruction supplied-text milestone

Branch rebuild/ebook-engine-v2-20261102, base19068c4. Candidate1.9.68 is isolated;
no live app registration, deployment, hosted schema or customer data changed.
The previous missing replacement source has not been recovered. This is new
reconstruction, not a claim to have restored the missing63-test implementation.

Foundation21 cases and supplied-book/customer-path17 cases:38 passed18.21sec.
Registry integrity/enforcement9 passed0.16sec. Existing fast baseline826 passed
378.08sec before expanding registry coverage. Expanded/full gate pending.
See docs/EBOOK_RECONSTRUCTION_STATUS.md and release_evidence/ebook_v2_supplied_milestone.json.

Real browser acceptance uses an independent CLI worker. It stops the worker
after a completed chapter, closes the browser, restarts the worker, reopens
Saved Books, approves the edition and downloads actual matching PDF/ZIP bytes.
The first completed chapter stays at one attempt. HTTP proofs include200,
SHA256 response checksums, signatures, CRC, embedded PDF equality, cross-owner404,
unauthenticated401 and CSRF403. Read-only status never advances work. Missing
worker creation503 creates no failed attempt. Worker heartbeat stays independent
of long-running work. PDF review inspected every page of a four-page supplied
fixture explicitly labeled NOT FOR SALE. No paid or model calls occurred.

Current workflow supports supplied prose, three simple templates, PDF/ZIP,
editable Markdown, saved books, authenticated local login and manual recovery.
It does not yet reconstruct topic writing, independent editorial checks, photos,
chapter editing/versions, EPUB/DOCX or KDP. Do not call the generator complete.
Windows launcher is supplied but not executed on Windows. Hosted SQL/R2 are
unverified. sqlite is deliberate until hosted parity is proved.

User explicitly authorized GitHub backup. Push every tested milestone and verify
remote source before saying backed up. Never claim local commits are durable
backup. The six-file foundation2c3a6f6 is already remotely verified; next is the
supplied-book checkpoint. Never put customer files, runtime DBs or secrets in git.
