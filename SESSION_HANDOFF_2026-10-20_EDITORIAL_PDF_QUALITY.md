# Editorial PDF quality candidate — October 20, 2026

Continue from this record and the repository, not the older subscription work.
PR74 is v1.9.51. Runtime source: 9e794ae68655095735195b6090b9eb226b70ca88.
No merge, deployment, production write, paid provider call, or saved-book rebuild.

## Completed correction

The actual 38-page synthetic fixture stranded Chapter 4's title on page 15.
A new rendered-page assertion failed on that source. Tall measured diagrams now
use smaller HTML display dimensions only when the smallest printed label remains
at least 8pt. Unknown or insufficient label measurements retain the original
size. Full high-resolution PNG pixels and all source instructions are preserved.
The repaired fixture has 37 pages; page 15 contains its title, full diagram,
caption and opening paragraph. The repaired graphic's smallest label is 10.41pt.
Native PDF text is at least 8pt; ZIP CRC passes and its PDF is byte-identical.

Reviewed the before/after contact sheets and the repaired page at readable size.
Chapter-placement experiments under all six theme styles found ten chapter
openers per style and no stranded title pages. These are synthetic local proofs,
not approval of a current production customer book or proof of Designrr parity.

The prior PDF-inspection correction also remains: inspect actual image
placements, exclude all cover images, and refuse a false pass when the PDF
reader is unavailable. Original regression proof is in GitHub run 39491251425.

## Verification

- Fast Gate: 809 passed before and after.
- All nine previously registered protected ebook suites: 178 passed before
  and after, identical case identities, zero failures/errors/skips.
- Expanded design/export suite: 16 passed, including three new size safeguards
  and the real chapter-opening layout regression.
- Complete collection: 3,240 unique cases across the unchanged 231-file manifest;
  all previous 3,234 retained, six added, no missing or duplicate identities.
  Collection is not execution of the full suite.
- Dependency, Python compilation and browser JavaScript syntax checks passed.
- Scoped ebook lock restored; the visual-review dependency and design/export
  suite are now enrolled. Other product implementations and locks are unchanged.
- Evidence and XML archive: release_evidence/editorial-pdf-quality-candidate.json
  and release_evidence/v1.9.51-editorial-tests.tar.gz.

## Release blocker — do not waive

The unchanged preservation case in tests/test_warm_wellness_template.py skips
because exports/ebook-visuals-local/ebook.pdf and package.zip are absent here.
Their required SHA256 values remain 6202e3a559db9313b61ec2d54ff689f6236a3b037308820bc77cfedf4d01f5bd
and 5044f086b7335e139bcec94e1b743c4f7effd4fe9eb7738973140176ef6d5c1f.
Never regenerate substitutes, rewrite hashes, or drop this case to obtain green.
The full gate requires zero skips and has NOT been certified on this candidate.

The Factory browser is signed out. The authorized read-only database inspection
confirmed the production ebook record exists; no production data was changed.
Original reference files could not be retrieved through the available file
connection. Restore the exact preserved pair, then run the unchanged full gate,
review the current production book and verify website/builder versions before
any merge/deploy. Billing and PR73 remain separate and unchanged. PR67 remains
an unfinished draft; its manual-mode interface is not part of this candidate.
