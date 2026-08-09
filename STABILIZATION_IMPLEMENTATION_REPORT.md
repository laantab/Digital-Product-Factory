# Factory stabilization implementation report

## Scope

Changes were made only to the uploaded sanitized copy. The live Windows Factory
was not accessed, restarted, or changed. No product, image, PDF, or paid API call
was generated.

## Safeguards added

- Exact production and development dependency manifests.
- A repository-wide `.gitignore` and safe `.env.example`.
- Cursor rules that require one-product scope, before/after preflight, zero paid
  calls, zero skipped acceptance tests, and customer-download inspection.
- A single acceptance manifest spanning shared QA, covers, Ebook, Word Search,
  Crossword, Coloring Book, theme isolation, and download naming.
- A global test fixture that blocks all non-local network and clears paid-service
  keys during tests.
- One enforced preflight runner. The previous preflight ran the same cover test
  twice and mislabeled that as all tests.
- Self-contained Ebook fixture; tests no longer depend on project #336 or a
  private local database.
- Deterministic Ebook font fallback using ReportLab's bundled Vera TrueType
  family when Arial or bundled application fonts are unavailable.
- A Word Search deterministic/answer-key regression test.
- Windows batch files for one-time setup, preflight, and Git initialization.

## Defects corrected

1. Single-page safe-fix now disables a separate answer-key page.
2. A full Coloring Book with `blocked_export=true` now returns no PDF bytes and
   an explicit error. Preview stages remain available for review.
3. Ebook font registration no longer depends entirely on one Windows machine.

## Verification completed here

- Python syntax compilation: passed for every changed Python file.
- Browser JavaScript syntax: passed (`node --check static/js/app.js`).
- Shared product QA tests: 37 passed.
- Targeted Ebook fixture/font tests: 2 passed.
- Deterministic Ebook font registered as `EbookSans` from ReportLab Vera.
- Paid API calls: 0.

## Verification still required on the Windows Factory

This review environment does not contain the application's declared third-party
packages, so the complete acceptance manifest correctly stops with a missing-
dependency error instead of pretending to pass. Run
`Setup_Factory_Development.bat` on Windows; it creates `.venv`, installs the
locked dependencies, and automatically runs the complete gate. A release is not
approved until it reports failures 0, errors 0, and skipped 0.

After the automated gate passes, each changed product family still requires a
real customer-path UI test and inspection of the downloaded PDF and ZIP. The
test gate deliberately does not spend money or generate customer products.
