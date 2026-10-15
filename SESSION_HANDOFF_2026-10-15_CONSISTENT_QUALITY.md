# Consistent ebook quality — 2026-10-15

## Start here

Owner approved moving from completed one-button recovery (v1.9.43, main 10763bb4c377a8ad4d1dff6d40df254430c7ad0d) to consistent quality, while preserving all working generators. Work branch: work/consistent-ebook-quality. Release: v1.9.44. No paid generation or production data/configuration changes.

## Repair

Manual /export-product already ran an Editor-in-Chief artifact review. The one-button exporter bypassed it and marked readiness from design preflight alone. Both now call services/ebook_completion_quality.py against the actual PDF and ZIP. The report records file digests and findings; missing files, reviewer errors and incomplete rendered-page analysis fail closed. All temporary page images and open PDF documents are released. Concrete failed quality findings retain the draft and stop repeating the same export until explicit resume. Approved content and output files are not rewritten by the review.

Final designed PDF assembly now retains the actual approved title/author metadata and chapter bookmarks. The reader uses actual PDF document metadata, including Unicode, rather than a raw /Title scan that misidentified the Contents bookmark as the title.

The stronger review exposed artificial defects in existing dual-gated acceptance inputs: repeated paragraphs/purpose words and identical geometric pictures. Those fixture producers now supply distinct paragraphs and distinct deterministic geometric images, and synthetic chart data is explicitly attributed as test data. Live provider behavior is unchanged; quality rules were not relaxed. AST comparison confirms that only export_product_route changed among app.py functions (153 others unchanged), and only fixture_one_chapter, _fill_photo_aid_fixture and _fixture_requirement_plan changed in the three fixture-containing services.

## Verification

Six regression cases were reproduced against v1.9.43 before repair. Focused contract/version/registry checks: 59 passed after repair. New cases also cover PDF/ZIP mismatch, incomplete image analysis, preservation of failed candidates and avoiding repeated export on quality defects. Complete automatic/custom/guided build and protected Fast Gate checks are running. Do not merge until required gates pass.

Fresh baseline Fast Gate: 756 passed; one browser case failed solely because Chromium was absent following the execution-environment restart. Installed the required browser; that exact case passed (1 test). Preceding source also has the completed 3,115-test full release proof from v1.9.43.

Original Project351 reference ebook.pdf SHA256 remains 6202e3a559db9313b61ec2d54ff689f6236a3b037308820bc77cfedf4d01f5bd; package.zip remains 5044f086b7335e139bcec94e1b743c4f7effd4fe9eb7738973140176ef6d5c1f. They are gitignored and must never be uploaded to the public repository.

## Publication and protection

Invite protection is temporarily UNLOCKED solely because its whole-file dependency app.py changed inside the ebook export route. One-button completion is temporarily UNLOCKED for its expanded final quality contract. Coloring Book, Crossword and Word Search locks remain LOCKED: their implementation and shared dependencies were not edited. Relock affected entries only at the actual tested source commit; do not manufacture a hash. The broader ebook remains PROTECTED, not a claim that every editorial or factual check has been verified live.

Next: finish focused complete builds, Fast Gate and Full Release Gate; record exact counts and source identity; publish source and protection follow-up, merge and verify deployment. Do not regenerate or re-export existing customer books. Review records explicitly retain comprehensive grammar/external plagiarism as not run; do not claim those checks passed.
