# Ebook template acceptance — 2026-10-14

## Start here

The owner clarified that the task is ebook templates, not sales setup or cross-product expansion. All six existing templates were checked; do not recreate them. Project 20 remains on Modern Business and its approved PDF/ZIP were not rebuilt or changed.

Warm Wellness, Modern Business, Bold Creator, Elegant Editorial, Bright Workbook, and Minimal Professional render genuinely distinct chapter openings, TOC layouts, typography, checklists, quotations, tables and page furniture. The same authored sample was rendered under all six themes; the comparison PDF contains 30 pages with bookmarks for each theme. Chapter, TOC, table and second-chapter pages were visually inspected. The comparison image updates the existing Library item libfile_7168088a0c4c819183fb3d56bbf96bb7; the PDF is libfile_c9ec848ebf0c8191a510cf18b08ea330.

## Layout repair

Visual inspection found a table header stranded at a page bottom while its rows continued without labels. Version 1.9.37 gives readable ebook grid tables the renderer's native repeat=1 header support. Regression coverage renders an 80-row table in every theme, requiring column headings on every page containing rows and preserving the last row. No manuscript, photograph, cover, approval or storage logic changed.

## Validation

715 stability baseline checks passed. 226 focused template/layout checks passed after the repair. Full release acceptance covers exactly 3,055 unique cases, with no missing or duplicated nodes. Initial run had one release-note format failure; required Changelog headings were restored and all 31 version-management tests passed. Reconciled results contain zero failures, errors or skips; original partition reports were retained. Python compile, JavaScript syntax and acceptance manifest checks passed. No paid APIs called.

The legacy Project 351 reference ZIP was truncated in this execution workspace. Owner explicitly authorized restoration. Its complete original was retrieved from Factory_Reference_Files_20261007-132004_3d857a.zip, CRC checked, restored only after matching SHA256 5044f086b7335e139bcec94e1b743c4f7effd4fe9eb7738973140176ef6d5c1f, and read back verified. The truncated copy was retained separately. Reference PDF still matches SHA256 6202e3a559db9313b61ec2d54ff689f6236a3b037308820bc77cfedf4d01f5bd.

## Live scope

The v1.9.36 website's six-template chooser was observed; Modern Business remains selected. Preview opens a blob window, which this cloud browser cannot inspect under its protocol policy; production renderer samples were inspected locally instead. Render Workflows deployment inspection requires a dashboard sign-in and was not completed. Do not claim builder deployment verified based on website version alone. PR 55 contains the v1.9.37 repair; verify its merge and website deployment record before claiming the repair live.

The ebook template family is verified. The broader cross-product Upgrade 2 is not COMPLETE_LOCKED, and ebook generator Function Lock remains PROTECTED. No original exports were removed; no paid generation, new book, hosting configuration, schema, secret or marketing changes were made.
