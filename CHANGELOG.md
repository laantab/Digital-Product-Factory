# Changelog

What changed in the Digital Product Factory, in plain language.
The version shown in the bottom-left of the app matches the newest entry here.

---

## 1.8.11 — 2026-09-22

**The builder can finish a book whose files it did not make itself.**

### What changed

- When the final quality check re-makes the book, it now fetches the
  approved cover and the interior pictures from saved storage if they are
  not on the machine doing the work.

### What was fixed

- A book stopped at 80% with "We couldn't complete this step automatically"
  because the approved cover file had been made on a different machine,
  which had since been recycled. The cover was safely saved all along; the
  final check simply never went and got it.

### Do your steps change?

- No. Nothing about the way you use the Factory changes. A book that had
  stopped at the final check can simply be continued.

### Cost

- No paid calls. Fetching a file that was already saved costs nothing, and
  no writing, pictures or cover are made again.

### Release gate

- Focused tests for the repair plus the full stability gate, with no new
  failures against main.

---

## 1.8.10 — 2026-09-22

**The final quality check uses the same heading rule as the release check.**

### What changed

- A section heading that appears once in several chapters, with different
  text under each one, is now accepted by the final quality check (for
  example a "Try this" or "Planning example" section in every chapter). The
  release check already accepted this; the two checks now agree.

### What was fixed

- Container Gardening for Beginners passed every step through the preview
  and was then refused at the final quality check: "duplicate heading:
  5. Water deeply". That step appears in two different procedures, and the
  book also has its own planning example in eight chapters. Each of those
  sections has its own text (at most a quarter of the words in common).

### Still refused

- The same chapter title twice; any heading repeated inside one chapter;
  repeated filler labels such as "Chapter Takeaway"; and repeated sections
  whose text is nearly copied (80% or more of the words shared).

### Do your steps change?

No.

### Release gate

8 new checks, including the book's real layout, where each heading sits in
its own box. They confirm distinct sections pass and copied ones still fail.
The existing recurring-heading and customer-facing checks all still pass.
No paid calls.

## 1.8.9 — 2026-09-22

**Picture plans pass the Factory's own quality check.**

### What changed

- When one kind of chapter chart would fill more than 55% of a book's
  pictures, the Factory now swaps the weakest extra ones for free Pexels
  photographs while planning, the same way it already adds photographs to
  reach the minimum. Photos you already approved, and charts with real
  substance, are never touched.

### What was fixed

- Container Gardening for Beginners could never leave the pictures step:
  "5 of 9 visuals are the same kind (workflow). That repetition reads as a
  template." The planner met the photograph minimum but let one chart style
  fill 5 of 9 chapters, and every rebuild made the same plan. The quality
  rule is unchanged; the planner now makes a plan that passes it.

### Do your steps change?

No. A book may get one more free Pexels photo to review.

### Release gate

7 new checks, including this book's exact mix (3 photos, 5 workflows, 1
checklist): it now comes out at 4 photos, 4 workflows and 1 checklist,
approved photos unchanged. A balanced book is left exactly as it was, and
nothing changes when photos cannot be fetched. No paid calls.

## 1.8.8 — 2026-09-22

**Approving a photo works again.**

### What changed

- Nothing you click is different.

### What was fixed

- Pressing "accept" on a photo, or approving the pictures, said
  "Photograph file is missing" even though the photo was showing on the
  review screen. The review screen fetched the photo from the Factory's
  shared storage, but accept and approve looked only on the website's own
  disk, which never holds the builder's pictures. They now fetch the book's
  stored pictures first, the same way the builder and the review screen do.
  This is what stopped Container Gardening for Beginners at the photo review.

### Do your steps change?

No. Accepting and approving photos now simply work. They are free: they only
read pictures the Factory already stored.

### Release gate

6 new checks that recreate the live problem: pictures made on the builder,
the builder's disk gone, and the website accepting and approving them. The
same checks fail on the previous version with the exact live error message.
A photo that storage genuinely does not have still fails honestly, and
nothing is charged. No paid calls.

## 1.8.7 — 2026-09-21

**Free Images and Covers by Default.**

### What changed

- A picture budget saved when a book was created no longer authorizes paid
  AI pictures or AI covers on its own.
- AI pictures and AI covers now need a separate authorization that names
  who gave it and sets its own maximum amount. Without it, the amount
  available for AI pictures is $0.
- Free options are always tried first: Pexels photos, then a photo the book
  has already approved for one of its chapters. AI is reached only if none
  of those works and a separate authorization exists.
- Prior spending history is unchanged. Nothing already recorded is reset or
  removed; an authorization only notes where picture spending stood when it
  was given.

### What was fixed

- A book created with "pictures authorized" could spend on its own at the
  cover step if four Pexels candidates did not fit the cover layout.
  Container Gardening for Beginners was set up that way and could have spent
  up to $0.48 without anyone being asked.

### Do your steps change?

No. Pictures come from the Factory's own charts and Pexels photos, and the
cover from Pexels or your approved chapter photos, at no cost. There is
nothing new to click. There is no screen yet for giving a paid-picture
authorization, so paid AI pictures stay off.

### Release gate

12 new checks, including one built from Container Gardening for Beginners'
exact settings: no paid picture is allowed, no charge is recorded, the cover
uses an approved chapter photo before any AI, and an authorization is named,
capped, dated, can be withdrawn, and never resets spending history. Four
older checks were updated to give an explicit authorization where they test
paid pictures. No paid calls.

## 1.8.6 — 2026-09-21

**A sign-in screen.**

### What changed

- New page at /auth/signin with two small forms: "Sign in" and "Create an
  account". Once signed in it shows your email and role, a link back to the
  Factory, and a "Sign out" button.
- The very first account created becomes the admin, as before.

### What was fixed

- 1.8.5 added accounts but no screen to use them, so the only way to make
  the admin account was a command on the server. Now it is done in the
  browser.

### Do your steps change?

Yes, once: open digitalproductfactorypro.com/auth/signin and create your
account under "Create an account". Do this first, before sharing the invite
code with anyone else, because the first account becomes the admin. Book
building is unchanged, and the invite code still protects every page,
including this one.

### Release gate

10 new checks: the page is served, is never cached or shown inside another
site, echoes nothing it is sent, keeps the secret out of web addresses, and
the sign-in and sign-up routes still refuse plain form posts from other
sites. The page lives in routes/auth.py, so app.py and the invite-protection
lock are untouched. No paid calls.

## 1.8.5 — 2026-09-21

**Real logins, and a safe link to Pin Factory Pro.**

### What changed

- The Factory now has user accounts: register, log in and log out, with an
  admin role. Sign-in secrets are scrambled with bcrypt before they are
  stored and are never shown or logged.
- Projects can now record which account owns them. Nothing existing was
  moved: every project keeps working exactly as before, and ownership is only
  assigned when the owner runs `scripts/migrate_phase_a.py --owner-email ...`.
- New Pin Factory Pro link at /pin-factory/text, image, export, microtools and
  health, for logged-in users only.

### What was fixed

- **Pin Factory Pro could be told the wrong user.** The first version of the
  link trusted a user id sent by the browser and fell back to "anonymous".
  It now uses only the logged-in account, strips any user id the browser
  tries to send, never sends a request without the private Pin Factory key,
  never passes Pin Factory's cookies or internal address back to the browser,
  and refuses redirects.
- On Windows the link's path check let "/etc/passwd" through; it now checks
  paths the same way on every computer.

### Do your steps change?

Not for building books. The invite code still works exactly as before. To use
the Pin Factory link you will need to log in; create your admin account with
`python scripts\create_admin.py you@example.com` (you type your sign-in
secret privately). The link stays switched off until PIN_FACTORY_BASE_URL and
PIN_FACTORY_INTERNAL_KEY are set.

### Release gate

37 new login and Pin Factory checks. The Fast Stability Gate passes, the
invite-protection lock was unlocked and relocked the approved way
(3a5c6b0 then ed6dfe4), and the full gate shows no new failures against main.
No paid calls were made.

## 1.8.4 — 2026-09-21

**The builder's pictures and finished files reach the website.**

### What changed

- Pictures the builder makes, and the finished PDF and ZIP, are now saved
  to the storage both machines share, and read back from it wherever needed.

### What was fixed

- **The website showed none of the pictures.** Container Gardening for
  Beginners reached the pictures step on the builder, but the website showed
  0 of 9 pictures. The builder was meant to copy each picture to shared
  storage, but a missing label meant it never copied a single one. Every
  picture made while a book is being built is now copied, under that book.
- **Pictures went missing between runs.** The builder's disk is wiped at the
  end of every run, and the website never had the files at all. Both now
  fetch a picture from shared storage when it is not on their own disk, so
  the picture review screen can show them and a later run can keep using them.
- **The finished PDF and ZIP stayed on the builder.** They are now copied to
  shared storage as soon as they are made, so the download buttons work.

### Do your steps change?

No. After this update you can open the picture review screen and approve or
swap the Chapter 3 photo, which needs a person to check it.

### Release gate

Eleven new checks, with a storage stand-in that has no disk behind it, so a
file can only arrive through storage. The old code reproduces the live
problem exactly (0 pictures published, 0 visible on the website). The full
suite was run; the remaining failures are the same ones the current live code
already has on this test machine. No paid calls were made.

## 1.8.3 — 2026-09-20

**Continue really does pick your book back up.**

### What changed

- Clicking Continue on a stuck book now gives it a fresh set of tries.

### What was fixed

- **Continue gave a stuck book to the builder, and the builder said no.**
  Every book gets 60 tries before the Factory stops retrying it on its own.
  "Container Gardening for Beginners" had used all 60. Clicking Continue
  asked the builder to carry on (that was the 1.8.2 fix), but it never gave
  the book a fresh set of tries, so the builder turned it away every time.
  Now your Continue click, and only your click, starts the count again. The
  automatic checking the screen does while you wait never resets it, so a
  book still can't retry forever on its own. No paid work was done while
  the book was stuck.

- The Resume Build button had the same gap for a book that was waiting in
  line, and is fixed the same way.

### Do your steps change?

No. Click Continue exactly as before.

### Release gate

Nine new checks, which fail without the fix. The builder and resume test
suites pass. No paid calls were made while testing.

## 1.8.2 — 2026-09-19

- Continue where you left off now asks the builder to do the work, instead
  of quietly waiting for nobody.

---

## 1.8.1 — 2026-09-18

**Finishing the job 1.8.0 started: the pictures move too.**

### What was fixed

- **The step-by-step screen was still building books inside the website.**
  1.8.0 moved the one-click Build My Ebook button onto the separate builder
  machine and left every other button behind. On the evening of 18 September
  a test book built through the step-by-step screen failed: writing the
  chapters took longer than the website is allowed to spend on one request,
  and a few minutes later the website ran out of memory and restarted. The
  builder was never asked to do anything all evening. Now every step that
  does real work — writing chapters, correcting them, preparing visuals,
  replacing a photograph, asking for a different image, building the cover,
  uploading your own cover photograph, choosing a design, building the
  preview, and the quality check — is done by the builder.

- **Your pictures come back.** The website and the builder are two separate
  machines that do not share a hard disk. Covers and photographs the builder
  makes are now saved somewhere both machines can reach, so they appear on
  your screen instead of going missing.

### What changed

- **The screen no longer freezes on a long step.** Each button now starts
  the work and then shows progress, with the same "You can leave this page"
  promise the one-click build already makes.

- **The builder stops and waits for you after every step.** It used to be
  able to wait only after the manuscript. Now it pauses wherever you are, so
  a single click can never run ahead and spend your budget on choices you
  have not made yet. Approving a step is what lets it carry on.

- **Nothing can be forgotten again.** Every button on the site is now listed
  with a note saying whether it does real work or not, and a test refuses to
  let a new one be added without that decision being made. This is what was
  missing in 1.8.0: the gap existed because nothing forced anyone to look.

### Does anything about the steps change?

No. The steps are the same steps, in the same order, and each one still
waits for you to approve it before the next one runs. What changed is which
machine does the work, and that a long step now shows progress instead of
freezing the page.

On your own PC nothing changes at all, and if the live site is switched
back, everything behaves exactly as it did before.

### Cost

No change to what a book costs. The safety checks on spending are untouched:
a request that would have been refused before is still refused, and still
refused before anything is started or charged for. The builder machine is
still only paid for while it is actually working.

### Release gate

The Fast Stability Gate and the full Windows release gate were both run.
Six new zero-cost test files were added and registered in the acceptance
manifest, including one that refuses to let a new button be added to the
site without someone deciding whether it does real work. No paid provider
was called anywhere in the new tests.

### Still to do

- Seven older buttons that also do heavy work — finished-file export, the
  older ebook tools, and the KDP packaging — still run in the website. They
  work on older records rather than a step-by-step project, so there is
  nothing on the builder for them to join yet. They are listed and labelled
  so they are not lost.

---

## 1.8.0 — 2026-09-17

**The builder is its own machine, not a thread in the website.**

### What changed

- **Writing a book no longer happens inside the website.** When a customer
  clicks Build or Continue, the Factory writes down that the book must be
  finished and hands the work to a separate machine that starts up just for
  that book. The website goes straight back to answering pages.
- **Nothing changes until it is switched on.** Out of the box this release
  behaves exactly like 1.7.29, and on a local PC it always will. The new
  way of working is turned on by one setting on the live site, and turned
  off again by deleting it.

### What was fixed

- **One customer's book could take the whole site down.** A real build
  ("Container Gardening for Beginners") used more memory than the website
  was allowed, because the book was being written inside the same program
  that serves pages. Now a book gets its own machine with about eight times
  the memory, which starts when the book starts and shuts down when it is
  finished.
- **Clicking Continue five times no longer starts five builds.** Impatience
  used to be able to set several copies of the same book going at once. The
  Factory now refuses all but the first.
- **A book that is already finished is never built a second time.** If the
  hosting platform retries a job it thinks went wrong, the Factory checks
  first and hands back the finished book instead of making another one.
- **Progress screens can never move a build along by accident.** Looking at
  a book, refreshing a page, or an old browser tab left open cannot make the
  website start writing.

### Does anything about the steps change?

No. The steps are the same, the quality checks are the same and the prices
are the same. A book that was part-way through carries on from exactly where
it stopped. The only difference is which machine does the writing.

### Cost

The new machine is only paid for while a book is actually being written, and
costs nothing when the Factory is idle.

### Release gate

Code and tests complete. The paid hosting has not been created yet, so this
version is not live.

---

## 1.7.29 — 2026-09-17

**A book could get stuck asking to be approved over and over. It can now
repair itself and move on.**

### What changed

- **A book that gets stuck at the manuscript step now fixes itself.**
  Before, some books reached a point where the Factory kept saying the
  manuscript still needed work, kept saying it was correcting it, and yet
  nothing ever changed. The only way out was for someone to go in behind
  the scenes and reset the book by hand. That loop is closed.

### What was fixed

- **Chapters approved under the old rules were never re-checked under the
  new ones.** When the Factory's quality rules improve, chapters written
  before the change can fall below the new standard. The approval check
  noticed this every time. The repair step did not — it only looked at a
  list of chapters marked "already fine" and trusted it, so it never sent
  the outdated chapters back to be rewritten. Approval refused the book,
  the repair had nothing to do, and the two disagreed forever.
- **Only the chapters that actually fail are rewritten.** Nothing else in
  the book is touched, so a stuck book costs one or two chapter repairs
  to rescue, not a whole rewrite.

### Does anything about the steps change?

No. The steps are the same, the prices are the same, and a book that was
already moving through them is unaffected. The only difference is that a
book which used to get stuck now keeps going.

### Release gate

Run the full Windows release gate before releasing this. The defect is
covered by `tests/test_ebook_accepted_chapter_revalidation.py`, which
reproduces the stuck book end to end and fails on the previous release.

---

## 1.7.28 — 2026-09-16

**Every download on the live site was being refused. They work again.**

### What changed

- **Your Download PDF and Download ZIP buttons work on the live site
  again.** Nothing about how products are made, priced or presented has
  changed — this release repairs a lookup that was refusing to hand over
  files it should have handed over.

### What was fixed

- **"Download blocked" on files that were perfectly fine.** Every PDF and
  ZIP download on the live site returned an error saying the package was
  not linked to your saved project — even though it was, and even though
  the file was sitting there ready to send. The same download worked
  correctly on a local copy of the Factory, which is why it went
  unnoticed.
- **The cause was the live site's database answering in a different
  shape.** The code that looks up "which project does this download
  belong to?" read each database row by position rather than by name.
  The local database hands rows back in a form where that happens to
  work; the live database hands them back in a form where it quietly
  produces nonsense. The lookup then decided every package belonged to no
  project, and the safety check correctly refused to send a file it had
  been told was orphaned. The check was right; what it was told was
  wrong.
- **There were two copies of that lookup**, both with the same mistake,
  and one of them had never checked the newer kind of package id at all.
  There is now one shared lookup, used by both, that behaves identically
  on either database.
- **A row that cannot be read is now reported instead of ignored.** The
  original code hid the failure inside a catch-all that discarded the
  error, which is why this survived a whole release without anyone
  seeing a single message about it.

### Does anything about the steps change?

No. Same screens, same buttons, same prices. Your Download PDF and
Download ZIP buttons simply work again.

The safety check that refuses genuinely orphaned packages is unchanged
and still refuses them. Only the lookup feeding it was repaired.

### Release gate

Twenty-four new checks. They run the real lookup and the real download
route against BOTH database row shapes — including the live site's shape,
reproduced exactly, so this can never again be a defect that only appears
in production. They also prove a genuinely orphaned package is still
refused, so the fix cannot be mistaken for weakening the guard. Full
Windows release gate: green, with no paid API calls.

---

## 1.7.27 — 2026-09-16

**The Factory now finishes a whole ebook on its own: nine chapters, a designed interior, a cover, a 31-page PDF and a ZIP, with the browser closed.**

### What changed

- **Your book is now *required* to contain the things a designed interior
  is made from.** Every third chapter is asked for a real checklist and
  every third for a numbered procedure, on different chapters, leaving the
  rest free for a photograph. Before this, the Factory asked for a table
  only if your outline happened to use the word "table" — so whether your
  book could be designed at all depended on whether the writing model
  volunteered extra structure nobody had requested.
- **Checklists and procedures now vary in length through the book**, so
  three of them do not read as three copies of one box.

### What was fixed

- **A finished book could not be designed, and said so in jargon.**
  "Container Gardening for Beginners" was written, passed every writing
  check with no complaints, and then stopped dead at "Only 1 kind(s) of
  visual across 9: photo." One part of the Factory demanded three kinds of
  visual; another part had asked the writer for none. They now agree.
- **A repair instruction the writer could not act on.** When a chapter was
  missing its checklist or its procedure, the writer was handed the words
  "Missing required workflow: chapter-workflow" — an internal name, not an
  instruction. One chapter was rewritten six times and got longer and
  wordier each time. The instruction now spells out the exact format, the
  way the table instruction already did.
- **An internal name could be printed in your book.** A writing model
  handed "chapter-workflow" duly printed "chapter-workflow" as a heading
  above the list it had just written. The final quality check caught it,
  but only after the writing was approved, leaving the book stuck with no
  way forward. Those names are now stripped before they can reach a page.
- **A finished book said "Paused".** The progress bar reached 100% and
  read "Your ebook is ready" while the indicator beside it said "Paused",
  because the two were reading different things. They now read the same
  one.

### Does anything about the steps change?

No new steps and no price change. Books will contain more checklists and
step-by-step procedures than before, which is what makes a designed
interior possible — and what a practical how-to book should have had all
along.

### Release gate

Thirty-six new checks, most of them guarding one rule learned the hard
way: a requirement is only real if the thing demanded is the same thing
the checker accepts AND the same thing the interior can draw. They assert
that agreement directly, in all three places. Full Windows release gate:
green, with no paid API calls.

---

## 1.7.26 — 2026-09-15

**A finished book could be thrown away over a source that was never wrong, and a retry could never actually retry. Both are fixed.**

### What changed

- **A nine-chapter book that was already written now gets published
  instead of discarded.** Nothing about how the Factory writes, designs
  or prices a book has changed — these are all cases where finished work
  was being thrown away by a check that was wrong, or by a retry that
  quietly did nothing.

### What was fixed

- **"earthbox.com" was read as the social site "x.com".** The check for
  weak sources asked whether a banned web address appeared anywhere in
  your sources list, as plain text. "earthbo(x.com)" contains it. So
  "Container Gardening for Beginners" — which cited EarthBox, the planter
  maker, exactly the sort of place a container-gardening book should cite
  — was told its sources were not trustworthy, and could never be
  approved. Web addresses are now matched properly, as addresses.
  linux.com, dropbox.com, netflix.com and equinox.com were unusable as
  sources for the same reason.
- **A retry now actually retries.** Each step carried a fixed reference
  that was recorded the first time it ran, and every later attempt was
  treated as a repeat of that first one: it returned the old answer
  instantly, did no work and saved nothing. So a book needing a second
  correction pass could never get one, in its whole life. The nine good
  chapters of "Container Gardening" were written, then sixty attempts
  were used up in about a minute without a single one doing anything,
  and the book was declared unfinishable.
- **The Continue button now actually hands your book to the Factory.**
  It cleared the stuck step and then gave the work to nobody, so if you
  clicked Continue and closed the tab — which the screen invites you to
  do — nothing happened. The promise "you can leave this page" was false
  on the one path that exists to rescue a stalled book.
- **A book that had used up its attempts could get stuck "being picked
  back up" forever.** Reopening it put it back in the queue but left the
  used-up count in place, and nothing will pick up a book in that state.
  Pressing Continue yourself now clears it; automatic retries still stop
  where they always did.
- **A source used for market research is no longer mislabelled.** The
  same address-matching mistake showed a legitimate research source as a
  "Social signal" in the evidence behind your idea score.

### Does anything about the steps change?

No. Same screens, same buttons, same prices. The difference is that a
book which has genuinely been written now reaches you, and pressing
Continue on a stalled book now actually restarts it — including when you
close the tab straight afterwards.

The quality checks themselves are unchanged. Quora, Reddit, Pinterest,
Facebook, X and the rest are still refused as sources when a book
genuinely cites them.

### Release gate

Sixty-eight new checks across three areas: web addresses must be matched
as addresses and never as plain text (every banned site is still caught
when truly cited, and hosts that merely end in one are not), a repeat of
the same attempt must still be charged once while a genuine retry must be
allowed to do real work, and Continue must leave a runnable job behind
even when the queue is broken. One long-standing order-dependent failure
between two existing test files was also fixed at its cause: a test that
left projects behind in the shared test database. Full Windows release
gate: green, with no paid API calls.

---

## 1.7.25 — 2026-09-15

**You can now see at a glance whether the Factory is actually working on your book — and if it has stopped, it says so and offers a button.**

### What changed

- **A live activity light sits beside the progress bar.** It spins only
  when something is genuinely working on your book, and it says what is
  happening: Working, Retrying a step, Picking this back up, Paused, or
  Finished.
- **If nothing is running, the screen says "This book is paused"** and
  gives you a Continue button, instead of an animation over a build that
  has stopped.
- **The promise on the screen now matches reality.** It used to say to
  pick the book up from Saved Projects — a list that deliberately shows
  only finished products, so an unfinished book was never in it. It now
  points at "Continue where you left off", where the book actually is.

### What was fixed

- **An indicator that always animates is worse than none**, because it
  cannot tell "working" from "abandoned" — and that is the one thing you
  need to know. This one is driven by two real facts: how long ago your
  book last saved real progress, and whether something currently holds
  the job. If neither is true it stops spinning and turns amber.
- **A worker that died is no longer mistaken for one that is busy.** If
  the Factory was interrupted, its claim on your book expires, and the
  screen reports paused rather than pretending.

### Does anything about the steps change?

No extra steps. The same screen, with the truth added to it. In normal
use you should never see the paused state at all — the Factory finishes
books on its own now. It exists for the day something goes wrong, so that
you are told instead of left watching.

### Release gate

Thirteen new checks, most of them written to make the spinner STOP: no
recent progress and no active worker must read as paused, an expired
claim must not look like work in progress, a missing or malformed
timestamp must never be treated optimistically, and the paused case must
be handled before the spinning one. Full Windows release gate: green,
with no paid API calls.

---

## 1.7.24 — 2026-09-15

**"You can leave this page" is now true. The Factory finishes your ebook itself, instead of relying on your browser staying open.**

### What changed

- **The Factory now finishes your book on its own.** Until now the page
  you were watching was quietly doing the work: it asked the Factory for
  one chapter, then the next, then the next. Close the tab and the book
  simply stopped — which is exactly what happened to a real book at
  "Writing your chapters (5 of 9)".
- **Starting a book now records a lasting instruction to finish it.** That
  instruction is written down, not held in the page or in memory, so it
  survives closing the tab, refreshing, losing your connection, and the
  Factory itself being restarted or updated.
- **If the Factory is interrupted mid-chapter, it picks the book back up
  by itself.** No tidy-up has to happen first and nobody has to press
  anything — a recovery that depends on a clean shutdown is no recovery
  at all, so this one does not.
- **Finished chapters are never rewritten.** The part that decides what to
  write is completely unchanged; only who asks it to keep going is
  different. A book stopped after chapter five carries on at chapter six.
- **A book is never finished twice**, so no duplicate PDF, ZIP or
  chapters.

### What was fixed

- **The real cause of the stuck book.** Work stopping when a browser tab
  closed was never a timing problem or a provider problem — it was that
  nothing on the Factory's side was responsible for finishing the job.
  Now something is.

### Does anything about the steps change?

Yes, in the way that matters: start a book, close the tab, and come back
later to find it further along or finished. Everything else — the
chapters, the quality checks, the cover, the design, the PDF and ZIP — is
untouched.

### Honest limitation

The Factory finishes books while it is awake. If the whole service is
idle or stopped, work pauses safely and resumes when it wakes; nothing is
lost. Removing that last gap needs a dedicated always-on helper, which is
the next infrastructure step.

If anything about this needs undoing, one setting switches it straight
back to the old behaviour.

### Release gate

Twenty-eight new checks: two workers can never claim the same book, a
book whose worker died is picked up again once its claim expires, a
crashed attempt is retried rather than abandoned, a finished book is
never finished twice, one long book cannot hog the Factory, and the
switch-off works. Full Windows release gate: green, with no paid API
calls.

---

## 1.7.23 — 2026-09-15

**Fixes the worst possible bug: an ebook that stopped halfway and could not be found again from any screen.**

### What changed

- **A book that is still being written now appears in "Continue where you
  left off"** from the moment it starts, instead of only once it reaches
  the later design stages.

### What was fixed

- **A half-finished ebook could become unreachable.** A live book stopped
  at "Writing your chapters (5 of 9)" and there was no way back to it —
  not from Saved Projects, not from the continue list, not by reopening
  the browser. The five finished chapters were safe in storage the whole
  time; there was simply no door left open to them.
- **Why it happened.** The "Continue where you left off" list only
  recognised books that had got as far as the design stages. A book still
  writing its chapters had not created that record yet, so the list
  skipped it. Saved Projects could not help either, because it lists
  finished, downloadable products and this book had no PDF yet. And the
  only other memory — the browser's own — is wiped the moment the tab is
  closed. Three separate doors, all shut.
- **A book being written is now recognised in its own right**, with no
  dependence on the browser remembering anything.

### Does anything about the steps change?

Yes, and for the better: an ebook you start now stays reachable from
"Continue where you left off" for its whole life, not just near the end.
Nothing else changes, no finished chapter is ever rewritten, and no
product is regenerated.

### Honest limitation

This makes a stopped book **findable and resumable**. It does not yet
make it keep building after you close the tab — the writing is still
driven by the open page. Making "you can leave this page" completely
true needs the background worker, which is the next infrastructure step.

### Release gate

Sixteen new checks covering the exact live failure: a five-of-nine
manuscript is recognised as resumable, finished and failed books are not
offered, already-written chapters are never discarded, the check writes
nothing at all, and the listing stays behind the private-beta gate. Full
Windows release gate: green, with no paid API calls.

---

## 1.7.22 — 2026-09-15

**Fixes the fault that stopped the first attempt to move to the new database. The live site was never at risk and was already safely back on the old one.**

### What changed

- **Translating between the two databases now happens in the one place
  every part of the Factory shares**, instead of being handled separately
  by each part that creates its own tables.
- Settings that only mean something to the old database are skipped
  rather than passed on and rejected.

### What was fixed

- **The billing tables were still being created using an instruction the
  new database does not understand.** The first switch-over attempt
  failed at start-up with a syntax error, and the live site rolled
  straight back to the old database as designed. Nothing was lost and no
  customer data was affected.
- **The real mistake was fixing only half the problem last time.** The
  earlier work taught the *main* records table to speak the new
  database's language, but each part of the Factory that creates its own
  tables was left to fend for itself — so billing failed, and the next
  one would have too.
- **The translation now happens in the one place every part of the
  Factory shares.** Any section can go on writing tables the way it
  always has; if the new database is in use, the wording is corrected on
  the way through. No future table can repeat this failure.
- **Settings that only mean something to the old database are now quietly
  skipped** rather than sent onward and rejected. Failing a start-up over
  a tuning hint would be absurd.

### Does anything about the steps change?

No. Nothing changes for anyone using the Factory. The old database is
still in use and still holds everything; the new one is not switched on.

### Release gate

Seventeen new checks, including one that reproduces the exact start-up
that failed live and would have caught it beforehand. It was confirmed to
genuinely fail when the fix is removed — a test that cannot fail proves
nothing. Full Windows release gate: green, with no paid API calls.

---

## 1.7.21 — 2026-09-15

**The Factory can now actually run on the new professional database — but only when told to, in two separate steps. Nothing has switched yet.**

### What changed

- **Two separate settings are now required to move the Factory onto the
  new database**, and this is the most important safety decision in the
  whole change. One setting says *where* the new database is. A second,
  separate setting says *use it*.
- **Why it matters:** if the Factory switched the moment the database was
  connected, then simply linking it would have pointed the live site at a
  brand-new, completely empty database. Every customer's Saved Projects
  would have appeared to vanish and every download would have failed —
  with an empty list as the only clue that anything was wrong. Keeping
  the two apart means the new database can be created, filled and checked
  while customers carry on using the old one, and the actual switch is
  one deliberate act that is undone by deleting one setting.
- **A short set of commands** to back up, create, copy, check and report —
  including one that says which database the Factory is really using,
  rather than assuming.

### What was fixed

- **A wrong-database hazard, caught by its own test.** The switch
  originally accepted *any* database address. That would have let the
  Factory try to reach a completely different kind of database with the
  wrong software. It now requires the address to genuinely be the new
  database's.

### Does anything about the steps change?

No. Nothing changes for anyone using the Factory. Both settings are
absent, so the Factory runs exactly as before, and the existing database
file is never deleted — it stays as the way back.

### Release gate

Twenty-five new checks. Most prove the switch CANNOT happen by accident:
neither setting alone moves anything, only an exact value counts, a
wrong-database address is refused, and if the check itself fails the
Factory stays on the old database rather than falling over. Full Windows
release gate: green, with no paid API calls.

---

## 1.7.20 — 2026-09-15

**Groundwork for moving the Factory's records to a stronger database — with a checker that proves nothing was lost. Nothing has moved yet.**

### What changed

- **The Factory can now speak to a professional database (PostgreSQL) as
  well as the simple file-based one it uses today.** This is preparation
  for the bigger change that lets products be built in the background
  instead of while a customer waits.
- **Nothing changes until it is switched on.** With the new setting
  absent — which is how every copy of the Factory runs right now — the
  Factory behaves exactly as before. Switching it on without the required
  software fails loudly rather than quietly doing something unexpected.
- **A copy tool and, more importantly, a proof tool.** The copy tool moves
  every saved product and file record across. The proof tool then
  compares the two databases record by record and field by field, and
  reports every single difference it finds.

### What was fixed

- Nothing was broken. This is new groundwork.

### Does anything about the steps change?

No. Nothing changes for anyone using the Factory today.

### Release gate

Twenty-five new checks. Most of them deliberately try to make the proof
tool FAIL — a checker that always says "fine" would be worthless. It is
required to catch a missing record, a secretly altered field, a lost
version number, and an unexpected extra record. It also must never write
to the original database, which stays as the way back.

Rehearsed against the real Factory database: 114 saved products and 73
file records copied and compared with zero differences, and the original
left untouched.

---

## 1.7.19 — 2026-09-15

**A new read-only check that answers the one question that matters when cloud storage is switched on: which copy is the Factory actually using?**

### What changed

- **`readcheck` reports, for every moved PDF, whether the Factory read it
  from cloud storage or from the original copy** — and confirms the bytes
  are identical either way. The existing check proved the cloud copies
  were intact; this proves which one the product-building code actually
  picks up, which is a different and more useful thing once cloud reading
  is switched on.
- **It also proves the safety net still works, on real data, without
  breaking anything.** It temporarily pretends — inside its own run only —
  that cloud storage is down, that the file is missing, that it is
  corrupted, and that it is the wrong size. In all four cases the Factory
  must fall back to the original copy and produce the right bytes. No real
  stored file is touched, moved, changed or deleted.
- **It only reads.** It does not copy, delete, rebuild a product, alter a
  saved project, or contact any paid service.

### What was fixed

- Nothing was broken. This closes the last blind spot before switching
  cloud reading on: there was no way to confirm which copy was being used.

### Does anything about the steps change?

No. Nothing changes for anyone using the Factory.

### Release gate

Five new checks: the right copy is chosen with cloud reading off, the
right copy is chosen with it on, all four safety-net situations fall back
correctly, the check itself writes nothing whatsoever, and — importantly —
it reports FAILURE if an original copy has gone missing, because the
safety net is only real while the original is still there. Full Windows
release gate: green, with no paid API calls.

---

## 1.7.18 — 2026-09-15

**One short command now does the whole live-site PDF copy safely: check, back up, copy, check again — and stops at the first sign of trouble.**

### What changed

- **`migrate` became a single guarded operation** instead of a bare copy.
  In order: it checks the situation is safe, takes a backup and proves it
  is identical, re-checks that nothing moved underneath it, copies each
  PDF while verifying every one, checks them all again afterwards, and
  reports a plain PASS or FAIL.
- **It refuses to start unless everything is right**: the database must be
  on the live site's permanent disk, all four cloud-storage settings must
  be present, cloud reading must still be switched off, and no record may
  be malformed. If any of those is wrong it stops before touching
  anything — it does not even take the backup.
- **No backup, no migration.** If the backup cannot be proven
  byte-for-byte identical to the original, nothing is copied at all.
- **It stops at the first failure** rather than carrying on.

### What was fixed

- **Two backups taken in the same second no longer collide.** The rule
  that a backup may never overwrite an earlier one was right, but it
  meant a legitimate second attempt within the same second was refused.
  Backups now get a numbered suffix instead, so nothing is ever lost and
  nothing is ever blocked.

### Does anything about the steps change?

No. Nothing changes for anyone using the Factory. Original PDFs are never
deleted, exported files are never touched, saved products are never
rewritten, and cloud reading stays switched off.

### Release gate

Nine new checks, most of them about refusing: no backup means no
migration, incomplete settings mean no migration, cloud reading already
on means no migration, a database in the wrong place means no migration,
and one malformed record stops the whole run. Full Windows release gate:
green, with no paid API calls.

---

## 1.7.17 — 2026-09-15

**The "what's the situation?" command now also reports how storage is configured — without ever showing a secret value.**

### What changed

- **The read-only status command now says whether cloud storage is
  switched on**, whether all four cloud-storage settings are present, and
  where the exported files live and how many there are. This matters
  because it is the only way to see, from the live site itself, whether
  it is set up the way we think it is.
- **It reports presence, never values.** For each setting it says only
  "yes, this is set" or "no, this is missing". A secret value can never
  appear on screen, in a log, or in a report.

### What was fixed

- Nothing was broken. This closes a blind spot: there was no safe way to
  confirm the live site's storage configuration from the live site.

### Does anything about the steps change?

No. Nothing changes for anyone using the Factory. The command still only
looks — it copies nothing, changes nothing, and deletes nothing.

### Release gate

Two new checks, both about secrecy: four deliberately planted fake
credentials must not appear anywhere in the output, and the command must
correctly report whether cloud storage is switched on. Full Windows
release gate: green, with no paid API calls.

---

## 1.7.16 — 2026-09-14

**A few typed words can now start the live site's PDF copying. Still nothing has been copied, and nothing changes for anyone using the Factory.**

### What changed

- **The copying work can now be run by typing a short command** on the
  live site's own command line, instead of through the private web
  address added in 1.7.15. The hosting plan does have a command line
  after all, and its window mangles anything long that is pasted in — so
  the commands are now a few words each.
- **The safe option is the default.** Typing the command with no extra
  words only *looks*: it reports what it would copy and changes nothing.
  Copying has to be asked for deliberately, by name, and is limited to a
  small number at a time.

### What was fixed

- Nothing was broken. This makes an already-safe job practical to run in
  a window that cannot handle long pasted commands.

### Does anything about the steps change?

No. Nothing changes for anyone using the Factory. No PDF has been copied
on the live site yet, every original copy stays exactly where it is, and
cloud storage is still switched off.

### Release gate

Three new checks covering the command line itself: the no-argument
default only reads, an unrecognised word does nothing at all, and the
checking option can never copy anything. Full Windows release gate:
green, with no paid API calls.

---

## 1.7.15 — 2026-09-14

**Upgrade 0, Phase 0B-3E: a safe way to move the live site's PDFs into cloud storage. Nothing has been moved yet, and nothing changes for anyone using the Factory.**

### What changed

- **The live site can now be asked to copy its own PDFs into cloud
  storage.** Everything moved so far was moved on the office computer.
  The live site keeps its own separate copy of the database on its own
  disk, which no other machine can reach — and the hosting plan has no
  way to run a command on that machine. So the Factory gained one
  private, locked door that can be knocked on from outside to start the
  same copying work that has already been proven.
- **The door does not exist unless it is switched on.** Until a secret
  is set on the host, the address behaves exactly like a page that was
  never built — it says "not found". Once switched on, it still says
  "not found" to anyone who does not present the exact secret, so no one
  can even discover that it is there.
- **It can only do four things**: report what it *would* copy, make a
  backup, copy a small batch, and check its own work. Copying requires
  asking for it deliberately and is limited to a small number at a time.

### What was fixed

- Nothing was broken. This closes a gap: the copying work was finished
  on the office computer but had no way to reach the live site.

### Does anything about the steps change?

No. Nothing changes for anyone using the Factory. The new address is
invisible and inactive on any host where the secret is not set, and it
can never delete a PDF, change a saved product, or rebuild anything.
Every original copy stays exactly where it is.

### Release gate

17 new checks, most of them about what the new address *refuses* to do:
stay invisible without a secret, refuse a wrong secret without admitting
it exists, never leak a credential, never touch a saved product, and stop
rather than hide a mismatch. The private-beta gate was re-tested and is
unchanged. Full Windows release gate: green, with no paid API calls.

---

## 1.7.14 — 2026-09-14

**Upgrade 0, Phase 0B-3B2B: the part of the Factory that builds a customer's download can now read a product's PDF from cloud storage. Still only one PDF has been moved.**

### What changed

- **The Factory now looks in cloud storage first when it builds a
  customer's download**, and uses the copy stored inside the project
  record when it does not find a good one there. Before this, the code
  that packages a product only ever read the copy inside the project
  record, so moving a file to cloud storage had no effect on what the
  customer actually received.
- This applies to every product that stores its PDF this way: word
  search, crossword, coloring book, spelling worksheet, math worksheet,
  and both planners.
- **Nothing about the packages themselves changed** — same files, same
  names, same layout, same quality checks. Only where the PDF is read
  from can differ, and only for a product that has already been moved
  and verified.

### What was fixed

- **A product whose cloud copy is missing, damaged, the wrong size, or
  unreachable now quietly uses the copy in the project record instead.**
  This was the whole point of the change: a customer must never lose
  access to something they own because a second copy went wrong
  somewhere else. Every failure was tested one at a time — storage
  switched off, storage unreachable, the stored file replaced with
  rubbish, the stored file deleted, and a move that was never finished —
  and in every single case the customer still got the correct product,
  byte for byte.
- **A half-finished move is no longer trusted.** A file is only used once
  the Factory has finished checking it and marked it good. Until then the
  original copy stays in charge.

### Does anything about the steps change?

No. Nothing changes for anyone using the Factory. With cloud storage
switched off — which is how it is set up today — every product is built
exactly as it was in 1.7.13. The original copy of all 73 PDFs is still in
place, and all 3,224 export files are untouched.

### Release gate

18 new checks on the packaging path, plus every protected test for word
search, coloring book, crossword, the ebook, math worksheet, both
planners, Saved Projects and the export pipeline. Full Windows release
gate: green, with no paid API calls.

---

## 1.7.13 — 2026-09-14

**Upgrade 0, Phase 0B-3B1: the Factory can now talk to cloud storage, and knows exactly where every existing file really lives. Still nothing has been moved.**

### What changed

- **The Factory can now store customer files in Cloudflare R2**, the
  shared storage that a future background worker will need in order to
  reach the same files as the website. The connection is built and
  tested, but it is switched off: no bucket has been created, no
  credentials exist yet, and not one customer file has been sent
  anywhere.
- **Every place that serves a customer their file now checks the new
  storage first, and falls back to the old copy.** Because nothing has
  been moved, the new check finds nothing and every download behaves
  exactly as it did before. It is the plumbing, proven in place, before
  anything travels through it.
- **Saved Projects can now recognise a product whose file lives in cloud
  storage**, as well as one sitting on the server's disk. Today every
  product is still on disk, so the list looks exactly the same.
- **There is now a migration tool that copies a file safely** — copy,
  check the size, check the fingerprint, write down where it went, read
  it back, check the fingerprint again, and only then call it done. It
  never deletes the original. It refuses to run at all until it is
  explicitly switched on, which has not happened.

### What was fixed

- **A serious hazard was caught before it could do any harm.** The
  Factory records a "package id" for each product, and the obvious
  assumption was that this is the folder the product's files sit in. It
  is not. Thirty-eight of the 114 local projects disagree — the id says
  one thing and the actual PDF lives somewhere else entirely. Downloads
  work today only because the Factory follows the real stored path.
  Had the move been planned around the package id, those 38 products
  would have been filed under names that point at nothing. Every
  destination is now worked out from the real path instead, and all 292
  of them were checked to confirm each one leads back to the exact file
  it came from.
- **Eight projects were found with no usable file path at all**, seven of
  which still carry their PDF inside the project record. They are now
  reported rather than guessed at, so nothing gets invented for them.

### Does anything about the steps change?

No. Nothing changes for anyone using the Factory. Every product, every
download, and every saved project behaves exactly as it did in 1.7.12.
All 73 PDFs stored inside project records are still there, and all 3,224
files in the exports folder are untouched.

### Release gate

Targeted storage tests: 54 new checks covering the R2 connection,
credential safety, the fallback rules, the key rule, and every failure
mode of the migration tool. Full Windows release gate: green, with no
paid API calls.

---

## 1.7.12 — 2026-09-14

**Upgrade 0, Phase 0B-3A: the storage foundation is built and proven. Nothing has been moved yet — on purpose.**

### What changed

- **There is now one place the Factory can put a customer file**, instead
  of the two different places it uses today (files on the server's own
  disk, and files packed inside the project record itself). For now it
  writes to the same disk everything already uses, so nothing external is
  needed and nothing about the Factory's behaviour changes.
- **The Factory can now record where a file lives** — its size, a
  fingerprint to prove it is intact, and its type — without putting the
  file itself in the project record.
- **A dry-run report** can now show exactly what a future move would do,
  without doing any of it.

### What was fixed

- **The Factory had no single way to store a customer file.** PDFs for
  most product types were packed inside the project record itself, which
  meant saving any small detail about a project rewrote the entire PDF
  along with it — for the largest project, about 40 MB rewritten every
  time. Ebooks used a different approach again, writing files to the
  server's own disk. Neither can be reached by anything except the one
  server process, which is what blocks the reliability work this upgrade
  exists to deliver. There is now one place to put a file, and one way to
  prove it arrived intact.

### What was NOT changed, deliberately

- **No customer file was moved.** Not one.
- **Nothing was deleted from any existing project.** Products that keep
  their PDF inside the project record still do, untouched.
- **Downloads work exactly as before**, reading from exactly where they
  read yesterday. The old path stays as a permanent fallback.
- No external storage account, bucket, or provider was created or chosen.

### Why do it this way?

The eventual move affects **73 of 114 projects and about 49 MB** of
customer PDFs. Moving customer files is the kind of work that must never
be half-done, so the rule is: copy, check the copy is byte-for-byte
identical, record it, read it back, and only then remove the original —
never move-and-hope. This release builds and proves the machinery for
that, so the actual move happens on a foundation that has already been
tested.

### Do my steps change?

- **No.** Nothing about creating, previewing, approving or downloading a
  product changes in any way.

### Release gate

- `tests/test_storage_foundation.py` (29 tests) proves put/get is
  byte-identical, checksums are preserved and detect corruption, `exists`
  and deletion behave, assets map to the right project and do not leak
  between projects, keys are deterministic across retries, repeated
  recording never duplicates, legacy files and embedded PDFs remain
  untouched, downloads and Saved Projects do not regress,
  APPROVED/LOCKED is unaffected, a storage failure falls back to the
  legacy copy rather than destroying it, and the dry run makes zero
  persistent changes.
- Dry run against the real local Factory: 114 projects scanned, 73
  affected, 73 binaries / 51,727,628 bytes proposed, largest 39.83 MB,
  **0 malformed or conflicting rows**.
- Fast Stability Gate and Full Windows release gate: see this commit's run.
- Function Lock: `database.py` is a declared dependency of `ebook` and
  `saved_projects`, both PROTECTED. No LOCKED function declares it.

---

## 1.7.11 — 2026-09-14

**Upgrade 0, Phase 0B-2: two things saving the same project at once can no longer erase each other's work.**

### What changed

- **Each project now carries a version number that goes up every time it
  is saved.** When the Factory saves, it checks that nobody else saved
  first. If someone did, the save is refused instead of quietly wiping
  out the newer work.

### What was fixed

- **A save could silently erase newer work.** Everything about a project
  — its chapters, its quality findings, what has been paid for — is
  stored together as one record, and saving replaced that whole record.
  Anything holding an older copy would overwrite whatever had been saved
  in the meantime. This is exactly what went wrong in 1.7.9, where a
  failure step wrote back an older copy and erased chapters that had
  already been written and paid for.
- This lands now, ahead of the rest of the Upgrade 0 work, because the
  planned background worker will be a second thing saving projects. What
  used to be an occasional bug would have become a guaranteed one.

### Do my steps change?

- **No.** Nothing about creating, previewing, approving or downloading a
  product changes. This only affects what happens when two saves collide,
  which previously lost work silently and now does not.

### Release gate

- Targeted proof first: the lost update was reproduced on a throwaway
  database before the fix (one writer's two chapters erased by another's
  stale copy), then confirmed prevented afterwards.
- `tests/test_project_optimistic_concurrency.py` (15 tests) covers the
  full contract: two readers at the same version, a successful save, a
  stale save rejected, the first writer's work intact, normal saves
  unaffected, repeated saves from the same working copy staying
  protected, freshly built data still saving, the version never being
  stored inside the record, no silent retry, the 1.7.9 failure shape
  specifically, APPROVED/LOCKED protections intact, and customer routes
  unaffected.
- 106 persistence/lifecycle/orchestrator tests re-run green, then the
  Fast Stability Gate (160 passed, 698 subtests), then the Full Release
  Gate.
- Full Windows release gate: pending this commit's own run.
- Function Lock: `database.py` is a declared dependency of `ebook` and
  `saved_projects`, both PROTECTED. No LOCKED function declares it, so
  none needed unlocking.

---

## 1.7.10 — 2026-09-14

**Found the deeper cause behind this week's build failures: writing a whole book inside one web request was long enough to be killed by the server itself. Chapters are now written one at a time, the way every other step already works.**

### What changed

- **A book is now written one chapter at a time**, the same way the
  Factory already handles every other step. Each check-in writes (or
  fixes) one chapter, saves it, and reports progress; the next check-in
  picks up exactly where the last one left off. A ten-chapter book that
  used to be written inside a single, several-minutes-long request now
  takes several short check-ins instead — invisible to the customer,
  who just sees "Writing your chapters" continue to completion.

### What was fixed

- **The web server was killing the process partway through a book.**
  Writing an entire manuscript inside one request could take minutes;
  the production server has its own time limit on how long any one
  request may run, and a long manuscript could exceed it, killing the
  in-progress request outright — which is what the customer experienced
  as the build losing its place and needing to restart.
- Because a legitimate book now needs many check-ins to finish, the
  manuscript step alone is allowed many more check-ins before the
  Factory gives up on it — every other step's limit is unchanged.

### Do my steps change?

- **No.** A finished book looks identical either way. This only changes
  how long the Factory pauses to check in with itself while writing it.

### Release gate

- Targeted proof first (per the recovery sprint, before any broader
  gate): a real 10-chapter book proves each check-in writes at most one
  chapter, progress never regresses, and a chapter that already exists
  is never rewritten or re-billed — including a version of the same test
  with a real, measurable delay on every chapter, proving no single
  check-in ever waits for more than about one chapter's worth of that
  delay, no matter how many remain.
- 195 + 176 broader manuscript/ebook tests re-run green, then the Fast
  Stability Gate (160 passed, 698 subtests), then the Full Release Gate
  — in that order, per the recovery sprint's required sequencing.
- Full Windows release gate: pending this commit's own run.
- Function Lock: no LOCKED function shares the changed files.
- Known follow-up (not part of this change): the exact production web
  server timeout could not be confirmed from this repository -- it is
  configured on the hosting platform, not in code. Confirming and, if
  useful, raising it further is a reasonable additional safety margin,
  but this release no longer depends on that number to work correctly.

---

## 1.7.9 — 2026-09-13

**The provider-routing fix held. The very next thing a live build hit: a manuscript with a fixable issue was treated as a dead end instead of being fixed automatically, and a failed check was silently throwing away already-written chapters.**

### What changed

- **A manuscript with a real, fixable quality issue is no longer a dead
  end.** The Factory already had a correction step for exactly this
  situation — the same one used when a customer asks for a manuscript to
  be corrected by hand — and it now runs automatically, once, before
  giving up. Only a manuscript that still has a real problem after that
  automatic correction stops the build.

### What was fixed

- **A failed quality check was silently discarding already-written
  chapters.** When the Factory found something wrong with a finished
  manuscript, the recovery step was saving the OLD, incomplete version of
  the project over the new one — throwing away chapters that had already
  been written and paid for. The next attempt then had to write the whole
  book over again, and because writing isn't perfectly identical every
  time, that second attempt could come out worse, not better. Both odd
  error messages a build could show ("needs correction" on one attempt,
  then "empty" on the very next) came from this one underlying mistake,
  not two separate problems.
- **Fixed at the source**: finished work is now saved as soon as it's
  produced, a failed check can only ever add information, never erase
  saved work, and a project that already needs a fix now goes straight to
  fixing it instead of starting over.

### Do my steps change?

- **No.** A book that needed no correction looks identical. A book that
  needed one now gets it automatically instead of getting stuck.

### Release gate

- Targeted proof first, using the Factory's own real generation pipeline
  (not just mocks): a real 10-chapter book where one chapter genuinely
  needs a rewrite proves the 9 good chapters are never regenerated or
  re-billed, the one flawed chapter is repaired automatically, and the
  build advances from 30% to 40%. Plus 4 more tests pinning the exact
  failure this release fixes: a rejected manuscript's content survives,
  a resumed attempt goes straight to repair instead of starting over, and
  a genuinely empty manuscript still fails clearly and honestly.
- 189 + 188 broader manuscript/ebook tests re-run green, then the Fast
  Stability Gate (160 passed, 698 subtests), then the Full Release Gate —
  in that order, per the recovery sprint's required sequencing.
- Full Windows release gate: pending this commit's own run.
- Function Lock: no LOCKED function shares the changed files.

---

## 1.7.8 — 2026-09-13

**The previous fix (1.7.7) did not work: a new live build still failed at the manuscript step, still trying to reach the owner's home computer. This time the fix does not depend on recognizing which computer the Factory is running on at all.**

### What changed

- **Writing a chapter locally is now something you turn ON, not something
  you turn OFF.** Before, the hosted Factory needed one setting to be
  correctly present to stay off the owner's home-computer engine; if that
  setting was ever missing, wrong, or not carried forward, hosted
  chapter-writing would silently try that engine and fail. Now the hosted
  Factory uses the paid cloud writer unless a person deliberately switches
  it to local generation — there is no "missing setting" state that can
  accidentally choose the wrong engine.

### What was fixed

- **1.7.7's attempted fix also did not hold up in production.** It tried to
  recognize "am I the hosted Factory?" automatically and refuse the
  home-computer engine when so. A brand-new live build after that fix
  deployed hit the identical failure — the automatic recognition did not
  reliably work in the real hosted environment. Rather than try a third
  detection method, the underlying assumption changed: the Factory no
  longer needs to recognize where it's running. It simply never chooses the
  home-computer engine unless someone explicitly asks for it.
- **The owner's own computer is unaffected** — it now has the same explicit,
  one-line "yes, use local writing here" setting already turned on for it,
  so nothing changes there.

### Do my steps change?

- **No.** Invisible to a customer either way.

### Release gate

- Targeted proof first (per the recovery sprint, before any broader gate):
  `tests/test_ai_providers.py` (31 tests) and
  `tests/test_ai_provider_render_safety.py` (10 tests, rewritten for this
  release) prove the new default is safe with nothing configured, stays
  safe against a mistyped setting, and still genuinely reaches local
  writing when explicitly turned on — plus a real-call-chain proof through
  the exact function named in both live tracebacks, and a Resume-Build
  proof that an already-accepted chapter is never regenerated or re-billed
  after a real provider failure.
- 249 broader ebook/manuscript tests, then the Fast Stability Gate (160
  passed, 698 subtests), then the Full Release Gate — in that order, per the
  recovery sprint's required sequencing.
- Full Windows release gate: pending this commit's own run.
- Function Lock: no LOCKED function shares the changed files.

---

## 1.7.7 — 2026-09-13

**A live ebook build kept failing at the manuscript step even after the "Resume Build" fix. The real cause: the hosted Factory could still try to reach the owner's home computer to write chapters. It can no longer do that, no matter what.**

### What changed

- **The hosted Factory now recognizes it is hosted** and refuses to reach
  the owner's home-computer writing engine for any reason, in any
  configuration — closing the gap that a single setting used to be
  responsible for on its own.

### What was fixed

- **The manuscript step was trying to contact a writing engine that only
  exists on the owner's own computer, from the hosted Factory.** This has
  nothing to do with content, research, or the customer's topic — it is a
  configuration gap that made chapter-writing fail every single time on the
  hosted Factory, while every other step (research, title, outline) kept
  working normally because they never depended on that engine.
- **The hosted Factory can no longer reach that home-computer engine at
  all, under any configuration.** Previously, one specific setting had to be
  entered correctly for the hosted Factory to stay off it; if that setting
  was ever missing, mistyped, or not applied, hosted chapter-writing would
  silently try the home-computer engine and fail. Now the hosted Factory
  recognizes itself as hosted and refuses that engine outright — the setting
  is no longer the only thing standing between customers and this failure.
- **The owner's own computer is unaffected.** Local writing there still
  works exactly as it did; nothing about that setup changed.

### Do my steps change?

- **No.** This is invisible to a customer either way — it only changes
  which engine writes chapters behind the scenes on the hosted Factory,
  never on the owner's own computer.

### Release gate

- Targeted proof first, before broader gates (per the recovery sprint):
  `tests/test_ai_provider_render_safety.py` (10 tests, including the exact
  production chapter-writing function and a real Resume-Build-style retry
  that proves an already-written chapter is never regenerated or re-billed
  after a provider failure), plus the full existing `test_ai_providers.py`
  and `test_local_manuscript_pilot.py` suites (43 tests) — all green,
  unchanged behavior confirmed for local development.
- 207 broader ebook/manuscript-adjacent tests re-run green.
- Fast Stability Gate: 160 passed, 698 subtests.
- Full Windows release gate: pending this commit's own run.
- Function Lock: `ebook` (PROTECTED, unchanged classification) gained
  `services/ai_providers.py` and `services/ebook.py` as declared, real
  shared dependencies. No LOCKED function shares either file, so none
  needed to be unlocked for this fix.

---

## 1.7.6 — 2026-09-13

**A stalled ebook build no longer strands a paying customer. "Try again" is gone — the Factory now offers Resume Build, and Resume Build actually works.**

### What changed

- **"Try again" is gone.** A stalled one-click ebook build now offers
  **Resume Build** and **Make Changes** instead — no technical wording, no
  dead-end button.
- **Resume Build actually resumes.** It gives the one stalled step a fresh
  chance and continues the build from exactly where it stopped, using the
  Factory's existing, unchanged checkpoint system.

### What was fixed

- **A live customer build of "Container Gardening for Beginners" stopped at
  30% and stayed stuck**, showing "We couldn't finish your ebook" with a
  "Try again" button that did nothing. Two real defects caused this, both
  now fixed:
  - Once a build stage failed three times, the Factory never gave it another
    chance — every later attempt failed instantly without even trying,
    forever.
  - The "Try again" button only re-checked status; it never actually asked
    the Factory to continue the build. Clicking it repeatedly just showed
    the same stuck screen.
- **A new "Resume Build" action replaces "Try again"** and genuinely works:
  it gives the one stalled step a fresh chance and continues the build from
  exactly where it stopped. Nothing already finished is redone, and nothing
  already paid for is charged again — the chapters the Factory had already
  written stay written.
- **The wording on a stalled build changed**: "Your project is safely saved.
  We couldn't complete this step automatically," with "Resume Build" and
  "Make Changes" as the two things you can do next. No technical language.

### Do my steps change?

- **No.** A one-click build looks and works the same when everything
  succeeds. This only changes what happens on the rare step that needs a
  second try, and there is nothing to figure out — one button, and the
  Factory picks up where it left off.

### Release gate

- Fast Stability Gate: 160 passed, 660 subtests, zero paid calls.
- Full Windows release gate: 1868 passed, 946 subtests passed, 0 real
  failures (one VERSION-bump-required failure was expected and resolved by
  this entry).
- New tests: `tests/test_ebook_build_resume_recovery.py` (17 tests) — proves
  a stalled build cannot advance on its own, Resume Build clears the stalled
  step without ever calling a stage runner (no paid call, no regeneration),
  Resume followed by the normal poll makes real progress, a transient
  failure still recovers automatically with no customer action at all, and
  a normal successful build is unaffected.
- Function Lock: `word_search`, `crossword`, `coloring_book`, and
  `invite_protection` were explicitly UNLOCKED for this change because they
  share `static/js/app.js` / `app.py` with the fix; all four had their own
  protected tests re-run green and were relocked at this release's commit.
  `ebook` (PROTECTED, not LOCKED) gained `services/ebook_build_orchestrator.py`,
  `services/ebook_project_workspace.py`, and `services/ebook_manuscript_engine.py`
  as declared, real shared dependencies — they always were, this just makes
  the registry tell the truth about it.

---

## 1.7.5 — 2026-09-12

**Coloring Book covers now get a final quality check before a book is considered finished, and the free-photo-first policy is extended to Word Search and Crossword covers.**

### What changed

- **Coloring Book's automatic cover build now passes through a real final
  quality check** before a product is considered complete — required title,
  no placeholder or malformed text, and a recognized cover source. Previously
  the automatic build had no check on the actual rendered cover page at all.
- **Word Search and Crossword covers now also try a free, appropriate Pexels
  photograph first**, the same policy already shipped for Ebook in 1.7.4 —
  only falling back to paid AI image generation when no suitable free photo
  is found. A Black-History-topic cover, and Coloring Book's illustrated
  cover style, correctly never attempt a stock photo — those keep their
  existing, unchanged behavior.
- **Every generated cover now records exactly what produced it** —
  `pexels`, `ai_fallback`, `ai_only`, or `template_fallback` (the Factory's
  existing professional deterministic cover design, used only when neither a
  free photo nor paid AI produced an image) — and whether a paid AI call
  actually ran, separate from whether one was merely attempted.
- **Faith Planner and Budget Planner's free-photo auto-selection now runs
  through the same real quality/relevance check** as every other product,
  instead of accepting the first search result. The planner's own painted
  cover option is unchanged.
- Documented, in `PROTECTED_GENERATOR_RULE.md`, exactly which quality check
  governs the final cover for every product — most products share one
  system, and Ebook's guided cover flow and both Planners were confirmed to
  already have an equivalent, real check of their own.

### What was fixed

- **Coloring Book's automatic build could ship a cover with no quality check
  on the final rendered page at all.** This is a new protection, not a
  response to a live customer defect — no coloring book has been confirmed
  to ship a bad cover this way, but the gap existed and is now closed.

### Do my steps change?

- **No.** Every product's generation steps are identical. Word Search,
  Crossword, and Ebook customers may occasionally see a free stock photo
  used where a paid AI image would have been generated before — the cover
  looks the same either way from the customer's side, and the Factory picks
  the better option automatically.

### Release gate

- Fast Stability Gate: 160 passed, 666 subtests, zero paid calls.
- Full Windows release gate: pending final confirmation on this commit.
- New tests: `tests/test_coloring_book_final_cover_qa.py`,
  `tests/test_cover_qa_contract_map.py`, and extensions to
  `tests/test_cover_source_policy.py` and `tests/test_planner_cover_photos.py`.
  In the acceptance manifest and the Fast Stability Gate.
- Function Lock: `word_search`, `crossword`, and `coloring_book` remain
  explicitly UNLOCKED pending this release's commit (a last-known-good
  commit cannot be recorded before the commit exists).

---

## 1.7.4 — 2026-09-12

**Ebook covers now try a free professional photograph first, and only use paid AI artwork if nothing suitable is found.**

### What changed

- **Ebook cover generation now follows a Pexels-first policy**: when you
  generate or regenerate an ebook's cover, the Factory searches free Pexels
  stock photography for your book's actual title/topic first. A candidate
  photograph is only accepted if it clears a real quality and relevance
  check — high enough resolution for print, portrait-suitable framing, and
  genuine topic relevance based on the photo's own description — never
  because a search simply returned something. Only when no Pexels
  photograph passes that check does the Factory fall back to paid AI image
  generation, exactly as before. The finished cover always uses the same
  deterministic Factory typography for the title, subtitle, and author name
  either way — never AI-generated lettering.
- Every generated cover now records which source actually produced it
  (`pexels` or `ai_fallback`) and whether a paid image-generation call was
  made, so the Factory can report paid-cover usage going forward.
- **Word Search, Crossword, and Coloring Book covers are unchanged** — they
  keep their existing, heavily-tuned AI-only cover generation exactly as it
  was. This release only adds the new policy for Ebook; extending it to the
  other three products is a separate, deliberate decision for later, not
  something this release does.

### What was fixed

- Nothing was broken before this release. This is a new capability, not a
  bug fix: Ebook covers previously went straight to paid AI image
  generation with no attempt to use a free, appropriate photograph first.

### Do my steps change?

- **No**, for every product. Ebook customers still generate and regenerate
  a cover exactly the same way; the Factory now quietly tries a free photo
  first behind the scenes before spending on AI artwork. Word Search,
  Crossword, and Coloring Book customers see no difference at all.

### Release gate

- Fast Stability Gate: 160 passed, 666 subtests, zero paid calls.
- Full Windows release gate on this commit: 2,761 tests, 0 failures,
  0 errors, 0 skipped, 0 paid API calls.
- New protection: `tests/test_cover_source_policy.py` — proves the Pexels
  quality/relevance gate never accepts a weak or irrelevant candidate, that
  a passing candidate is used with zero paid calls, that Ebook falls back
  to AI only when Pexels genuinely has nothing suitable, and that Word
  Search, Crossword, and Coloring Book never even attempt Pexels and keep
  their prior AI-only behavior byte-for-byte. In the acceptance manifest.
- Function Lock: `word_search`, `crossword`, and `coloring_book` were
  explicitly unlocked (a 2026-09-12 audit found `services/cover_agent.py`,
  `services/product_cover_agent.py`, and `services/cover_quality_agent.py`
  were real, previously-undeclared shared dependencies of all three),
  their full protected suites re-verified green with no behavior change,
  and all three relocked with this commit as the new last-known-good.

---

## 1.7.3 — 2026-09-12

**Coloring Book interior pages no longer print unwanted text when captions are off.**

### What changed

- Coloring Book's local fallback illustration renderer (used for the zero-cost
  "Basic Test Fallback" quality mode, and as the emergency fallback for any
  single page whose paid AI image fails to generate) now behaves the same way
  for every theme: no visible text on the page unless you explicitly turned
  captions on. Previously, one specific illustration style — the generic
  fallback used for themes that don't match a specific animal, superhero,
  fantasy, vehicle, or pattern illustration — printed the page's topic as a
  visible label regardless of your captions choice. Every other illustration
  style already had no text; this one now matches them.

### What was fixed

- **A Single Sheet Coloring Book with "Add short captions?" set to No could
  fail after generation** with "Coloring Book QA failed after
  auto-correction," for any theme that didn't match a specific illustration
  keyword set (an example that failed live: "Sea Creatures in the Reef").
  The cause was a leftover developer label ("Topic label") in one fallback
  illustration routine, printed unconditionally — present in the Factory's
  code since before version tracking began, never previously fixed. The
  quality check that caught it was working correctly the whole time; only
  the renderer needed the fix. Removed the label entirely.
- **A generic "Fix any missing fields above" message appeared after this kind
  of failure**, even though nothing was missing from the form. The retry
  message now says so only for genuine field-validation errors; a
  regeneration/quality-check failure gets accurate wording instead.

### Do my steps change?

- **No.** Nothing about filling out the Coloring Book form changes. The only
  difference is that a captions-off book with this specific fallback
  illustration style now generates cleanly on the first try instead of
  failing.

### Release gate

- Fast Stability Gate: 151 passed, 609 subtests, zero paid calls.
- Full Windows release gate on this commit: 2,656 tests, 0 failures,
  0 errors, 0 skipped, 0 paid API calls (log:
  `Factory Control Center/Logs/full_release_gate_v1.7.3_20260912.txt`).
- New protection: `tests/test_coloring_book_interior_no_text_contract.py` —
  proves every illustration branch draws zero text, and the real customer
  path (Single Sheet, captions off, an affected theme) passes QA on the
  first attempt with no auto-correction needed. In the acceptance manifest
  and the fast Stability Gate.

---

## 1.7.2 — 2026-09-11

**Word Search topic vocabulary now matches the subject you actually typed.**

### What changed

- **Word Search, in Topic mode, now always resolves its word list from
  the Factory's own local topic library** — the same curated library
  Crossword has used since v1.5.0 — instead of asking an outside AI
  service. A topic that matches a real local topic (Ocean Animals,
  American Automobiles, Flower Parts, and every other topic that library
  already covers) gets real, on-topic words every time, with no outside
  call and nothing to configure. A topic that matches nothing now says so
  plainly, right away, and asks for a more specific topic or a custom
  word list — it no longer guesses.

### What was fixed

- **Word Search, in Topic mode, could return words that had nothing to do
  with your subject.** A request for "Flower Parts" could come back with
  apple, banana, cherry, dragon, energy, forest, garden, harbor, island,
  jungle — a leftover placeholder list with no connection to the topic.
  The cause: the Word Search product tile asked an outside AI service for
  the word list instead of using the local topic library, and silently
  fell back to that placeholder list whenever the outside service could
  not be reached — which is always true on the live website, since it has
  no key for that service. No outside AI call is made to build a Word
  Search word list anymore, on this PC or on the live website.
- **"Flower Parts" specifically now returns flower anatomy** — petal,
  sepal, stamen, pistil, stigma, style, ovary, anther, filament, pollen,
  stem, receptacle, corolla, calyx, nectar — instead of quietly widening
  to generic plant words (leaf, root, soil, and the like).

### Do my steps change?

- **No.** Word Search Topic mode works exactly as before from your side —
  type a topic, get a book. The only difference is that the words you get
  now genuinely match what you typed, every time.

### Release gate

- Fast Stability Gate: 148 passed, 603 subtests, zero paid calls.
- Full Windows release gate on this commit: 2,647 tests, 0 failures,
  0 errors, 0 skipped, 0 paid API calls (log:
  `Factory Control Center/Logs/full_release_gate_v1.7.2_20260911.txt`).
- New protection: `tests/test_word_search_topic_scope_contract.py`
  (8 tests, 8 subtests), plus a word-list assertion added to the Word
  Search journey in `tests/test_customer_journey_every_product_type.py`.
  Both are in the acceptance manifest and the fast Stability Gate.

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
