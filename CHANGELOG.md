# Changelog

What changed in the Digital Product Factory, in plain language.
The version shown in the bottom-left of the app matches the newest entry here.

---

## 1.7.1 — 2026-09-11

**A locked front door for the private beta, and a public host that keeps
what you save.**

### What changed

- **The Factory can now ask for an invite code.** When the host sets
  `FACTORY_INVITE_CODE`, every page and every button requires the code
  once (typed into a one-field page, or opened from an invite link); after
  that a 90-day cookie remembers you. Without the code, browsers see the
  invite page and the app's own calls are refused. The code is never
  echoed back. Static files and the payment-provider webhooks stay
  reachable, because they must. Leave the variable unset and nothing
  changes — the Factory on this PC, and the whole test suite, still open
  straight away.

### What was fixed

- **First boot on an empty disk failed.** On a freshly mounted persistent
  disk (the Render setup from the 28 Aug runbook) the database folder did
  not exist yet and SQLite refused to create it, so the site could not
  start. The Factory now creates the folder first, and
  `FACTORY_DB_PATH=/var/data/projects.db` starts cleanly the first time.
- **The public site was open to anyone.** Every route — including the
  ones that spend on OpenAI, Tavily and Pexels, and the admin routes —
  answered to whoever found the domain. With the invite code set on the
  host, it no longer does.

### Do my steps change?

- **On your own PC: no.** Nothing asks for a code unless you put
  `FACTORY_INVITE_CODE` in the environment, and it does not belong in the
  local `.env`.
- **On the public site: one step, once.** Enter the invite code from your
  welcome email (or open the invite link) and you are in for 90 days.

### Release gate

- Fast Stability Gate: 139 passed, 595 subtests, zero paid calls.
- Full Windows release gate on this commit: 2,613 tests, 0 failures,
  0 errors, 0 skipped, 0 paid API calls (log:
  `Factory Control Center/Logs/full_release_gate_v1.7.1_20260911.txt`).
- New protection: `tests/test_invite_gate.py` (14 tests) and
  `tests/test_render_persistence_patch.py` (2 tests), both in the
  acceptance manifest and the fast Stability Gate.

---

## 1.7.0 — 2026-09-09

**Pick a cover photograph in two clicks, and a reviewer that no longer hands
out a 10 for free.**

### What changed

- **Choose a cover photograph without knowing anything about APIs.** The Faith
  Planner form has a Cover image choice: let the Factory choose, choose a
  Pexels photo, or use theme artwork. Choosing a photo shows six free
  photographs found from your title and theme; click one, press Use This
  Photo, and the Factory places your title on it. The chosen photograph is
  kept with the project so a rebuild draws the same cover. If free photos are
  unavailable, the Factory paints a themed cover and says so on the result.
- **A design rating that means something.** The Editor-in-Chief now grades the
  look on a marketplace scale: 7 functional, 8 professional, 9 premium, 10
  exceptional. Ten needs positive evidence on every criterion, measured on the
  finished PDF: a photographic cover with strong contrast on the title and on
  every label, a clear type hierarchy and pairing, no bare or crowded pages,
  no empty lower halves, writing lines with pen room, restrained ornament, and
  cover colours from the theme's own palette. Painted covers top out at 9.

### What was fixed

- **Small labels on covers and tinted panels could fall under the contrast a
  small type size needs.** Cover labels now use the cover ink, full-photo
  covers fade softly at the foot so the ownership line and caption read, the
  band eyebrow only uses the accent when it clears 4.5:1, and the muted label
  colour is darker in every theme.
- **The Budget Planner's cover lost its depth and its monthly tables stopped
  mid-page.** Its cover uses the teal overlay, and short category tables gain
  a notes block.
- **Two renders of the same photo cover were not pixel-identical.** The cover
  grain is now seeded, so a rebuild draws exactly the same cover.

### Do the steps change for you?

Only if you want a photograph. Pick "Choose a Pexels photo", press Find
photos, click one, press Use This Photo, then Generate as usual. Leaving the
default "Let the Factory choose" picks one for you when free photos are
available and paints a themed cover when they are not.

### Release gate

Full Windows release gate run on the committed code with a temporary database;
planner suites and the fast Stability Gate re-run on the final code. One live
Pexels verification (one search, one download) was run through the real form
after the protected tests passed; automated tests make no live call.

### Files

- New: `services/planner/cover_photos.py`, `services/planner/design_rating.py`,
  `tests/test_planner_cover_photos.py`.
- Changed: `services/planner/renderer.py`, `cover.py`, `components.py`,
  `themes.py`, `services/editor_in_chief_planner.py`, `services/product.py`,
  `static/js/app.js`, `app.py`, `tests/test_ebook_real_browser_customer_path.py`
  (case-insensitive progress check).

---

## 1.6.0 — 2026-09-09

**Faith planners are now built by a design system, so every one of them looks
like a product you would be happy to pay for — and the reviewer checks that.**

### What changed

- **Five design themes, chosen from a menu.** Warm Grace (burgundy and gold),
  Modern Minimal Faith (black, grey and taupe), Floral Devotion (blush and
  sage botanicals), Family Heritage (walnut and amber) and Joyful Light (sky
  blue and sun gold). A theme sets the colours, the type pairing, the header
  style, the ornament, the writing-line style and the cover artwork for every
  page at once. Picking one is a form field; no code changes.
- **Covers have artwork now.** The old cover was a flat block of colour with
  a title on it. Each theme paints its own hero artwork locally (light, glow,
  linen, botanicals, sky) in one of four cover styles: full photo, photo with
  a text panel, soft image with overlay, or elegant minimal. A photograph can
  be dropped into the cover image slot, and the Pexels workflow can fill that
  slot when a key is installed; nothing is fetched unless you ask.
- **Interior pages read as a guided devotional, not a school worksheet.**
  Reflection questions sit in soft cards with numbered badges; the weekly page
  opens with a reading card and pairs the prayer focus with gratitude; tables
  have rounded frames and gentle zebra rows; the belongs-to page is a proper
  title page; the contents page tells a beginner where to start; the 52-week
  plan reads in seasons; every page carries the same footer with an ornament
  and a page number.
- **The Budget Planner keeps its teal-and-brass identity** and gains the same
  page furniture, without any change to what its pages contain.
- **The Editor-in-Chief now judges design, not only content.** It checks that
  every page carries its heading, footer and the right page number; that no
  text sits inside the print-safe margin or runs off the page; that nothing
  the plan asked for was silently dropped; that the cover artwork will print
  sharp; that page colours stay on the chosen theme's palette; and that the
  working pages are not bare forms. A planner that is technically valid but
  visually weak is reported as needing improvement instead of passing.
### What was fixed

- **A finished manuscript could be sent back over grocery items.** The
  duplicate-checklist rule counted repeated bullets across the whole book, so
  "frozen vegetables" listed once in three different chapters read as padding
  and demoted an 11,000-word manuscript that had passed every other check. It
  now counts inside each chapter, where repetition really is padding.
- **The Factory had no logo.** The Digital Product Factory mark now appears on
  the home page, the two standalone builders and the cover editor, served
  from the Factory's own files.
- **Long worksheet labels could run off the page.** Labels now wrap.
- **The 52-week reading plan could lose its last week** on themes with a
  taller header. It always fits all 52 rows now.

### Do the steps change for you?

No. Generate a Faith Planner exactly as before. Two new menus appear on the
form, Design theme and Cover style, both with sensible defaults, so leaving
them alone still produces a finished planner. Budget Planner is unchanged
apart from the refreshed page furniture.

### Release gate

Full Windows release gate run once with a temporary database before this
release; the fast Stability Gate and both planner suites re-run on the final
code. Results are recorded with the release commit. No OpenAI, Tavily or
Pexels call was made.

### Files

- New: `services/planner/themes.py`, `services/planner/components.py`,
  `services/planner/cover.py`, `tests/test_planner_design_system.py`,
  `tests/test_duplicate_checklist_chapter_scope.py`,
  `tests/test_factory_logo_branding.py`.
- Changed: `services/planner/renderer.py` (rewritten on the component
  library), `builder.py`, `pdf_builder.py`, `services/product.py`,
  `services/editor_in_chief_planner.py`, `services/ebook_document.py`,
  `static/js/app.js`, `app.py`, the four templates.

---

## 1.5.0 — 2026-09-06

**Books are illustrated now, not just supplied with image files — and the
hashes on your screen belong to the file you would actually download.**

### What changed

- **The Factory decides what a book should look like before it fills in the
  pictures.** Until now each chapter was asked on its own "what does your text
  support?", and prose can always be cut into a list, so every chapter answered
  "a list". A finished 44-page book came out with nine pictures, eight of them
  the same rounded box of bullet points, and passed every check. The media mix
  is now chosen once for the whole book: chapters whose box carried the least
  give up their slot to a photograph, spread through the book rather than
  bunched at the front. Chapters holding a real plan or comparison keep it.
- **A new editorial review judges the set of pictures, not one file at a
  time.** It refuses a book whose pictures are all text boxes, requires more
  than one kind, stops any single kind from dominating, requires photographs
  where the subject supports them, and rejects two pictures that share a
  design. It is a fixed set of rules — no model is asked for an opinion, and
  nothing is invented to satisfy it.
- **Pictures must be inside the book.** The Factory used to confirm that image
  files existed in the export folder and the ZIP. It now opens the finished PDF
  and counts the images that are actually on its pages, which is what a
  customer opens.

### What was fixed

- **The Export panel could show a PDF and ZIP hash from an earlier version of
  the book.** Those hashes were recorded when the design check last ran, while
  the downloadable files are written later by a separate step that saved its
  own hash somewhere else and never updated the display. A hash you cannot
  reproduce is worse than no hash, so a hash is now shown only when it was read
  from the file currently on disk; otherwise the panel says it is not yet
  verified, and packaging records the file it just wrote.
- **A picture could be approved for being a valid file.** Existence, size,
  hash and caption all passed while the book was unusable. Those checks remain;
  they are no longer the whole standard.
- **A chart with research-sounding figures and no source is refused**, and a
  diagram with fewer than three steps is not accepted as an explanation.
- **Low-resolution images are caught before print**, with a higher bar for
  photographs than for graphics the Factory draws itself.

### Do the steps change for you?

No. Build as before. You will see more photographs and more variety, and a
book that would previously have been approved with nine near-identical boxes
now stops and asks for better pictures instead of shipping.

### Release gate

Run once before release with a temporary database; results recorded with the
release commit.

---

## 1.4.1 — 2026-09-04

**Books now carry page numbers, a matching contents page, a disclaimer about
the right subject, and a typeface we are allowed to sell.**

A quality release. One-click builds could stall at 80% or repeat a photograph;
both are fixed. Beyond that, a full editorial and design review of a finished
book found a set of faults that had been shipping in every ebook, and those are
fixed too.

### What changed
Nothing new to learn — the corrections listed below happen on their own during
a normal one-click build. The visible differences: a book reaches 100% without
stopping, every chapter carries its own picture, every page after the cover
shows a page number, the contents page agrees with those numbers, and the
disclaimer talks about the book's actual subject.

### Reading and navigation
- **Books had no page numbers at all.** The design settings asked for a running
  footer, but nothing drew one. Meanwhile the contents page quoted page numbers
  the pages themselves never showed.
- **The contents page numbered every line twice** — "1. 1 Why Five Minutes
  Counts". The list added its own number in front of the one already there.
- **The contents page pointed to the wrong pages.** Its numbers counted the
  cover; the printed page numbers did not. Every entry was out by one, so
  turning to "page 4" landed you on the wrong chapter.
- **The copyright page explained the Factory's own filing rules to the reader**
  ("They are not numbered chapters"). Replaced with a normal reservation notice.

### Wording and sources
- **Every book carried the same disclaimer, whatever it was about.** A
  mindfulness guide warned readers about business registration, insurance,
  profit margins and printer specifications. The disclaimer is now built from
  the book's own subject: health books get a health notice, food books a
  nutrition notice, business books the business one, and a book that raises no
  special risk gets a short plain notice.
- **Weak sources were only checked for one kind of book.** Quora, Goodreads,
  Reddit, social sites and retail listings are now rejected as authorities for
  any book.
- **A reference list headed "References" was treated as missing** and glued onto
  the end of the disclaimer, where it printed as legal text.
- **Chapters were judged on whether they used the word "example"** rather than
  on whether they contained one. A chapter with a full worked scenario failed;
  one that said "for example, you might…" passed.

### Pictures
- **Cards were built by cutting sentences in half.** Text was accepted up to 150
  characters and then trimmed at 78, so cards printed lines ending in "…".
- **Two-column tables were skipped.** Myth-versus-reality, is-versus-is-not and
  problem-versus-fix tables were passed over for a cut-up summary card instead.
- **The same table was printed twice** — once as a small picture and again as
  the real table just below it. The book keeps the real table.
- **A day-by-day plan was drawn as a comparison grid**, losing the order, and a
  plan written as two tables was drawn showing only half of it.
- **Numbers were doubled** on step cards: "1  1 — Feet on the floor".

### Typeface
- **The typeface in every book was Monotype Arial, copied from Windows and
  renamed "EbookSans".** A Windows licence does not cover putting that font
  inside a book you sell. Books now use Liberation Sans and Liberation Serif,
  which are free to redistribute and to sell with, and which match the old
  metrics closely enough that page breaks did not move.
- **The designed page layouts asked for Georgia and Calibri**, neither of which
  was actually included, so every designed book quietly printed in Times
  instead of the typeface it was meant to use.

### What was fixed
- **The same photograph could appear on several chapters.** Neighbouring
  chapters have similar subjects, so stock search kept returning the same top
  result — one cookbook had chapters 5, 6 and 7 sharing one image. Pictures
  already used are now excluded from later searches, and a final check across
  the whole book refuses a repeat by image, asset id, or source link.
- **Books could stall before finishing.** Long source web addresses ran off the
  edge of the page, which the print check correctly rejected. Long addresses
  are now shortened, with the site kept whole and the working link intact.
- **Every link on the Sources page printed as a row of black boxes.** The first
  attempt at the fix above added invisible characters to let addresses wrap;
  the print font had no shape for them and drew a box for each one. Nothing
  invisible is added any more.
- **Checklist graphics showed an empty box instead of a tick.** The mark was a
  font character the machine did not have. It is now drawn directly.
- **Checklist lines were cut mid-word** — "helps you buil". Lines now end on a
  whole word.
- **Table graphics printed raw formatting marks.** A totals row written as
  `**Total**` in the manuscript appeared with the asterisks in the finished
  book. Formatting marks are now removed before drawing.
- **A five-column table lost its last column** in the chapter graphic. Graphics
  now keep up to six columns.
- **Two books could overwrite each other's finished files.** Every ebook shared
  one asset folder when it had no id of its own; each book now gets its own.
- **Section headings taken from the writing instructions** — such as a table's
  internal name — are now rejected before a chapter is accepted, along with
  other unfinished template text.

### Do the steps change for you?
No. Build as before; the corrections happen automatically.

### Release gate
New generic regression tests cover every fault listed above, so none of them
can return unnoticed.

Run once before release with a temporary database; results recorded with the
release commit.

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
