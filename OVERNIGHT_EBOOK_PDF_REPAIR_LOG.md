# Overnight Ebook PDF Repair Log

Workspace: `flask_app`
Project: #20090 Beginner’s Guide to Container Gardening
Started: 2026-08-30 22:33 (local)
Finished: 2026-08-31 ~06:15 (local)
Branch: `main`
Rule: do not commit, push, merge, PR, approve, lock, or deploy.

## STEP 1 — Safety checkpoint

### Git
- Branch: `main` (tracks `origin/main`)
- Working tree at start: **clean**
- Pre-existing modified/untracked files at start: **none**
- No commit / push / merge / PR performed

### Protected projects (read-only)
- #4249 cover SHA still `465a3e10861cd056a98008a8131be157be9dc0d22ec93464fa831fcbb03367cd`
- #4249 live `content` SHA is `79f0dbbb3d6901f93662676023539796eea5201dade5344202e93ea3b8b604d0` (pre-existing; this session did not write #4249)
- #17365 Thunder Volt / Deep Sea — not touched

### Backup
- Recovery folder: `overnight_recovery_20090_20260830`
- Live defective PDF SHA: `95f75fe28040022f12b5796e260781c617e3697443b801ff732592d7f197e434`
- Manuscript SHA (unchanged): `f3aee3ff8dbb753f87be8f2487954876c49ab4f7b6414a0112d7e2a6342da075`
- Cover source jpg SHA (unchanged): `82eabce680e9f5d45ffba0b3ee6c170f40fe60470f06c5d2f9714ad73bafe56d`
- Cover composite png SHA (unchanged on disk): `d84c9055b2d82ca828ed5fe49af5d1e5a84a5937b6ad6e16f3b73cf2cc336985`

### Test baseline
- Focused ebook tests before renderer repairs: 51 passed (prior session)
- Last known full suite: 950 passed
- Full `preflight_check.py` run at end of this session (see below)

---

## STEP 2 — Root causes (confirmed on the 30-page / 32 MB PDF)

1. **Abnormal character/word spacing** — xhtml2pdf fell back to Helvetica; `@font-face` temp files failed on Windows. CSS `letter-spacing` also splits glyphs.
2. **Page 2 raw Markdown** — `product_summary` / TOC source (`[Chapter](#anchor)`) was dumped onto the title page.
3. **Page 3 nearly blank** — legal sheet was skipped; a one-line disclaimer overflowed onto its own page. After cover-strip, `@page { margin: 0 }` (cover template) applied to every interior page.
4. **Page 30 raw Markdown / fake Summary** — trailing Summary restated the opening paragraph (and could leak TOC markdown). Skip-then-reinject via `product_summary` put it back.
5. **Body too small/faint** — `th, td { font-size: 9.5pt }` won over body 11pt; color `#1e293b`.
6. **Walls of text** — no callouts; keep-together tables stacked and overlapped; zero interior margins packed type.
7. **Orange-pot photo repeated** — near-duplicate embeds of similar starter-pot shots; full-res PNGs. Remaining p7 vs p11 are *different* files (sowing vs filled mix), not byte duplicates.
8. **Mechanical captions** — stock-photo title and caption were the same string, both printed.
9. **Cover white perimeter** — cover sat inside xhtml2pdf `@page` margins. Source PNG also had a thin white frame. Fixed by fitz full-bleed + crop.
10. **No running headers/page numbers** — preview `.page-foot` stripped for PDF; no stamp. After adding stamps, they collided with body because interior pages still used margin-0.
11. **~32 MB** — uncompressed PNG data-URIs; ZIP stuffed the whole exports directory.
12. **Raw manuscript formatting** — markdown TOC/preamble reached customer PDF.

**Universal (not title-specific):** font embed, `@page main` after cover strip, legal/TOC page breaks, JPEG embed, near-dup skip, caption dedupe, summary duplicate skip, QA gates.

---

## Timeline

- 22:35 — Backup of #20090 to `overnight_recovery_20090_20260830`
- Diagnose 30-page PDF: Helvetica, markdown, blank legal, 32 MB PNGs, white cover frame
- Font embed via Arial → `EbookSans-*.ttf`; designed-path kept Georgia (Vera wrap broke fixture tests)
- First rebuild: 17 pages / 1.3 MB, QA pass, **legal missing** (TOC rebuild replaced copyright+TOC combo), **no interior margins** (cover `@page margin:0` after strip), overlapping type, duplicate Summary
- Fixes: separate legal/TOC page-breaks; remove blanks *before* TOC rebuild; restore `<pdf:nexttemplate name="main"/>` after stripping HTML cover; skip duplicate Summary without re-injecting; stamp in header/footer band; JPEG cover bleed
- Final unapproved export: **35 pages, 1,381,319 bytes**, QA passed, 34/34 interior pages numbered

---

## STEP 3–4 — Universal pipeline changes (uncommitted)

Tracked diffs:
- `services/pdf_export.py` — visual CSS 12pt/#111827; legal+TOC page breaks; cover-strip keeps `@page main`; JPEG embed; callouts; summary skip; blank-before-TOC; Arial @font-face only on EbookSans HTML
- `services/ebook_fonts.py` — prefer Windows Arial over Vera; copy into `services/fonts/`
- `services/ebook_pdf_images.py` — JPEG, white-crop, near-dup, full-bleed cover, running-matter stamp
- `services/ebook_qa_validator.py` — white perimeter, sparse pages, payload size, embedded font, page numbers (fix ValueError after `doc.close()`)
- `services/ebook_design_system.py` — restore Georgia/Calibri as designed-path fonts (do not force EbookSans)
- `tests/test_ebook_pdf_sale_quality.py` — 19 sale-quality gates

Already on `main` from earlier factory work (not modified this night beyond what's in the diff):
- `services/ebook_customer_path.py` — ZIP customer files only; `preview_source=visual`; QA blocks Ready
- `services/ebook_factory_pipeline.py` — “Repair PDF quality defects before Ready”
- `services/ebook_package.py` — photo caption vs duplicate title

## Project-specific data
- Manuscript bytes **not rewritten**
- Cover source jpg **not rewritten**
- New unapproved PDF/ZIP written to package `a76d99d229864ca9b326dd26e0bee9fa` and `overnight_work/unapproved_20090/`
- Flags: `unapproved_test_export=True`, `cover_approved=False`, `export_ready=False`, `ebook_ready=False`, `customer_keep=True`, unlocked

---

## STEP 5 — Tests

- Focused after repairs: **70 passed** (`test_ebook_pdf_sale_quality` 19, design_export, customer_facing, quality_repair, interior_layout, qa_validator_extraction)
- Paid API keys blanked; `FACTORY_TEST_MODE=1`; network guard not weakened
- Complete suite: `python preflight_check.py` — **1224 passed, 0 failed, 0 errors, 0 skipped**, paid calls permitted **0** (7m 06s). Pytest line: 1056 passed. JUnit: `test-results/factory-junit.xml`

---

## STEP 6 — Visual inspection of unapproved PDF (35 pages)

| Gate | Result |
|---|---|
| Cover full-bleed, title/subtitle/author preserved | Pass (pixel band white=0.00) |
| No markdown `](#` | Pass |
| Copyright page present (p3) | Pass |
| TOC with correct chapter page numbers | Pass (5, 9, 15, 22, 27, 32) |
| Body 12pt Arial, not Helvetica-only | Pass |
| Running headers + page numbers | Pass (34 interior pages numbered) |
| JPEG images, no duplicate xref | Pass (~1.38 MB) |
| Duplicate opening Summary removed | Pass (book ends on chapter 6 continuation) |
| Captions not duplicating headings | Pass |
| Orange-pot *file* not repeated | Pass (p7 sowing vs p11 mix are different hashes) |

Remaining limitations (not claimed 10/10):
- p14 is a short leftover paragraph (chapter-2 closer) with empty lower half
- Two different orange starter-pot photographs remain (instructional, not byte-identical)
- Running headers use Helvetica stamp; body is Arial
- Most heading spans are ArialMT rather than Arial-BoldMT
- 35 pages vs old 30 because interior margins are now real
- Designed-path ebooks still use Georgia (intentional, to keep fixture metrics)

---

## Digests (final unapproved test)

- Manuscript: `f3aee3ff8dbb753f87be8f2487954876c49ab4f7b6414a0112d7e2a6342da075`
- Cover source: `82eabce680e9f5d45ffba0b3ee6c170f40fe60470f06c5d2f9714ad73bafe56d`
- PDF: `5d62a269b1efb6b753aa0efbc4cd2a2f34450e12e89bd91cf0edc5095c732486` (1,381,319 bytes, 35 pages)
- ZIP: `7baa3f76d8dc59f5ecb1144fc7f27d3ac7e7fb766c9358f28b2fbc5406062539`
- Before: 30 pages, 32,187,117 bytes, SHA `95f75fe28040022f12b5796e260781c617e3697443b801ff732592d7f197e434`

Paid/external calls: **0**
Approved / locked / Ready / committed / pushed / merged / published / deployed: **none**
