# Session Handoff — 2026-09-04 (supersedes 2026-08-31)

**Start a new session with:** "Read SESSION_HANDOFF_2026-09-04.md and continue."

---

## Start here: one action is outstanding

**The live `projects.db` still holds the OLD version of project 351.** Everything
was built and verified against a temporary copy. Nothing was written to the live
database, because that has to happen with the Factory closed and only the owner
can do that safely.

To apply it:

1. Close the Factory completely (the window running on port 5055).
2. Open a terminal in `C:\Users\user\Documents\Product-Pipeline\Factory-v1.3`.
3. Dry run first — this writes nothing:

   ```
   python "C:\Users\user\Desktop\Handoff 2026-09-04\recovery-scripts\apply_to_live_db.py" --repo . --from-db C:\path\to\projects_test.db
   ```

   **Note:** the temporary database lived at `/tmp/f351/projects_test.db` inside
   the previous session's sandbox and is **gone**. See "If the temp database is
   missing" below — you must rebuild it first.
4. Then re-run with `--commit`.

The script refuses to run if the database is locked or the write-ahead files are
non-empty, takes its own timestamped backup first, verifies the PDF/ZIP/manifest
hashes, writes project 351 only, and leaves the project DRAFT.

### If the temp database is missing (it will be)

Rebuild it from the live database in three commands. This makes no paid calls
and does not touch the live database:

```
set FACTORY_TEST_MODE=1
set FACTORY_DB_PATH=C:\Users\user\Desktop\Handoff 2026-09-04\projects_test.db
python -c "import sqlite3;c=sqlite3.connect('file:projects.db?mode=ro',uri=True);o=sqlite3.connect(r'C:\Users\user\Desktop\Handoff 2026-09-04\projects_test.db');c.backup(o);o.close();c.close()"
python "...\recovery-scripts\install_manuscript_351.py" --repo . --manuscript "...\manuscript\manuscript-final.md"
python "...\recovery-scripts\rebuild_351.py" --repo .
```

`rebuild_351.py` should end with `preflight: PASS  pages=44  findings=0`.
Then run `apply_to_live_db.py` as above.

---

## What happened this session

### 1. Project 351 was rewritten and rebuilt to a sellable standard

The book was 5,622 words with a contents page reading "1. 1", no page numbers,
a disclaimer about business registration and printer specifications, sources
from Quora and Goodreads, a "Column A / Column B" table, and three chapters
sharing one photograph.

It is now **9,506 words across 9 chapters**, reading level Flesch-Kincaid 6.6,
44 pages, preflight PASS with zero findings. Contents matches the printed page
numbers on all nine chapters. No duplicate images, no clipped text, no raw URLs.

- `pdf_sha256` `6202e3a559db9313b61ec2d54ff689f6236a3b037308820bc77cfedf4d01f5bd`
- `zip_sha256` `5044f086b7335e139bcec94e1b743c4f7effd4fe9eb7738973140176ef6d5c1f`

**The manuscript was written by Claude, not Qwen3 8B.** Ollama was not reachable
from the environment that session ran in. This was authorised for project 351
only. The Qwen production path was not modified — if you rebuild a *different*
book, it still goes through Qwen as normal.

### 2. Most of those faults were Factory-wide, not project data

They had been shipping in every ebook, including the cookbook (project 353):

- `assemble_back_matter()` **hardcoded** the business/printing disclaimer for
  every book regardless of topic. Now built from the book's own subject.
- The design spec declared `footer_mode: page_number` and `header_mode:
  running_title`; nothing rendered either. Books had no page numbers at all.
- The contents page was an `<ol>` whose rows also carried their own number.
- Contents numbers counted the prepended cover; printed numbers did not. Every
  entry was out by one.
- Key-point cards accepted 150-character sentences and trimmed at 78, so they
  printed half-sentences ending in "…".
- Two-column tables (myth/reality, is/is not, problem/fix) were skipped entirely.
- A chapter's own table was drawn as a PNG *and* typeset below it.
- Themes asked for Georgia and Calibri, neither of which shipped, so every
  designed book printed in base-14 Times.
- The embedded font was Monotype **Arial**, copied from `C:\Windows\Fonts` and
  renamed `EbookSans`. Replaced with Liberation Sans + Liberation Serif
  (SIL OFL 1.1), which are metric-compatible, so pagination held.

Commit **`8e724ea`** — "Release v1.4.1 - Raise ebook editorial and design
quality". 26 files, ebook scope only, **not pushed**.

Note there are now two v1.4.1 commits: `8ab30d8` (yours, from the PC, during the
session) and `8e724ea` on top of it. Both are in CHANGELOG.md under one 1.4.1
entry.

### 3. New regression protection

- `tests/test_ebook_font_licensing.py` — 9 tests. Fails the build if a
  proprietary face reappears in `services/fonts/`, if a font file is renamed to
  hide its origin, if the loader reads the OS font directory, or if the licence
  and provenance files go missing.
- `tests/test_ebook_quality_regressions_v141.py` — 40 tests, one group per
  defect above. Generic: no project id, topic or book is named anywhere.

Four existing tests were updated because they asserted the old buggy behaviour
(`ol.toc-list li`, Arial-ranked-first, `EbookSans` font names, and a chapter
regex that assumed no footer).

---

## Open items

### Carried from 2026-08-31, still open
1. Make the Cloudflare tunnel durable (Windows service) or accept ad hoc.
2. Finish Lemon Squeezy's business-details form with `digitalproductfactorypro.com`.
3. Cosmetic: `".,"` collision when an AI idea name ends in a period.
4. Unify the three review-key names (`qa_report` / `qa_result` / `editor_in_chief`).
5. Retire `Update_API_Key_Anywhere.bat`.
6. Long-standing: plan limits in `/generate-product`; rotate Tavily + Pexels keys;
   real user accounts before live payments; 1.5 GB DB purge; repo visibility.
7. Push `8ab30d8` and `8e724ea` to origin/main from the owner's PC.

### New, raised this session
8. **Apply project 351 to the live database** — see the top of this file.
9. **The full release gate has not been run.** Only the ebook/design/visual/
   cover/font surface was exercised: ~46 test files, ~690 tests, 0 failures.
   Run the complete suite on the PC before calling v1.4.1 released.
10. **`test_math_worksheet_pdf_visual_qa` fails on Linux only.** Its font
    resolver needs `C:\Windows\Fonts\arial.ttf`. It should pass on the PC.
    Confirm this rather than assuming it.
11. **The math worksheet builder has the same licensing exposure the ebook just
    had.** `services/math_worksheet/pdf_fonts.py` embeds Windows Arial, Calibri
    and Segoe UI into worksheets that are sold. Not touched this session, because
    the brief said not to change another product builder. The ebook fix is the
    template: bundle Liberation, delete the OS-font lookup, add a licensing test.
    The same pattern likely exists in `crossword/pdf_fonts.py` and
    `word_search/`, `coloring_book/`, `planner/`, `spelling_worksheet/` — worth
    a sweep.
12. **Two books shipped the same cover image.**
    `exports/ebook-353/img_cover.png` and `exports/ebook-visuals-local/img_cover.png`
    are byte-identical (`3f12edbb…`). Project 351's cover has been rebuilt from
    its own photograph, but the underlying cause was not investigated.
13. **A book made only of local instructional graphics cannot get a cover.**
    `_run_cover` tries Pexels, then falls back to promoting an approved interior
    *photograph*. When every visual is a locally drawn graphic there is no
    photograph to promote, and the cover stage fails outright. Project 351 was
    recovered by reusing its own previously-downloaded photo. A typographic
    cover fallback would close this properly.
14. **DOCX export does not exist.** The brief asked for an editable Word file
    with real heading styles; it was explicitly deferred. The export package is
    HTML, PDF, ZIP, images and manifest. Do not describe DOCX as available.
15. Several chapter-end pages run 60–80% white. Normal for a book, but if you
    want tighter pages that is the place to look.

---

## Working notes

* The owner is a **novice** — plain language, one next step at a time.
* Never run tests or scripts against the live `projects.db`. Every script here
  refuses if `FACTORY_DB_PATH` points at it.
* This session spent **$0.00**. Project 351's ledger is unchanged at 5 paid
  calls / $0.85, all from before. Visuals are local graphics (`paid_images:
  false`); the cover reuses a photograph already downloaded and licensed
  (Pexels 6798809, Michelle Leman).
* The removed Arial files are preserved outside the repo at
  `Desktop\Factory Backup\project351_backup_20260904_211737\arial_fonts_removed\`
  for recovery only. Do not put them back.
* Everything from this session is gathered in `Desktop\Handoff 2026-09-04\`:
  the finished PDF and ZIP, the manuscript source, the three recovery scripts,
  the original project record, and rendered proof sheets of every page.
