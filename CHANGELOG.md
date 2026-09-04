# Changelog

What changed in the Digital Product Factory, in plain language.
The version shown in the bottom-left of the app matches the newest entry here.

---

## 1.4.0 — 2026-09-04

**One-click ebook builds, and the Factory now tracks its own version.**

Building an ebook used to mean clicking through ten separate production
stages. Now there is one button.

### What changed
- **Build My Ebook is one click.** Fill in the form, press the button once, and
  the Factory researches, writes, checks, illustrates, designs and packages the
  book on its own. A progress bar and plain-language messages show where it is.
- **You can read your manuscript as soon as it is written**, without waiting for
  the cover or the PDF. The finished-manuscript panel shows the chapter count
  and word count with an Open Manuscript button.
- **Leaving the page is safe.** Every finished step is saved. Refreshing or
  coming back later picks up exactly where it left off, and clicking Build a
  second time joins the build already running instead of starting a duplicate.
- **Pictures are chosen far more carefully.** Photographs that only matched a
  word in the chapter heading — clocks for "five minutes", letter tiles for
  "feel" — are now rejected. Chapters that suit a diagram get a practice
  sequence or checklist built from the book's own words instead of a stock photo.
- **The version number is now shown and managed properly.** It lives in one
  file, appears in the bottom-left corner, and cannot be forgotten at release
  time.

### What was fixed
- A failed illustration step no longer throws away the work already downloaded.
- The export step could never finish; it called the wrong internal routine.
- The cover step failed the same way, and could not recover when stock search
  was unavailable.
- Approving a stage quietly discarded the pictures already prepared for the book.
- A book title typed with a leading colon kept the colon all the way onto the
  cover.
- Finished books that had not yet been approved could disappear from both the
  saved list and the continue-where-you-left-off list.
- The test suite could reach the real project database. It now refuses to start
  unless it is pointed at a temporary one.

### Do the steps change for you?
Yes, and there are fewer of them. Ebooks are built with a single click. Existing
unfinished projects reopen on the new progress screen and carry on from where
they stopped. Nothing you have already made was altered.

### Release gate
1,485 tests — 0 failures, 0 errors, 0 skipped, 0 paid API calls.

---

## 1.3.0 — earlier

Local-model manuscript pipeline, customer-safe error messages, and the
resume-where-you-left-off list. Recorded here for continuity; this changelog
began at 1.4.0.
