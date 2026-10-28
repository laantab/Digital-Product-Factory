Warning: truncated output (original token count: 51965)
Total output lines: 4015

## 1.9.64 — Save chapter photograph choices after full-size review

### What changed
The ebook Visuals screen links each photograph to a full-size review page. Use this photograph saves through the existing acceptance action and confirms the saved match status before reporting success. Full-size images load separately rather than being embedded in the workspace response.

### What was fixed
Keep current visual only displayed a message and did not save a choice. Review and acceptance now recover verified image files from storage before evaluating their local paths, so a website disk path cannot falsely block a photograph that exists on the builder.

### Do the steps change?
Open Edit a Visual, review the full-size photograph, save the choice, and return to Visuals to continue the saved book. Hard photo rejections, project ownership, manuscript, cover and paid-provider restrictions remain enforced.

### Release gate
Six focused route, ownership, image-integrity, recovery and browser regressions passed. Required protected and full release checks are in progress. Live saved-book PDF and ZIP verification is required before claiming the book is finished.

## 1.9.63 — Resume interrupted ebook workers and expose chart corrections (candidate)

### What changed
Recoverable workflow exits and deadline continuations request the existing bounded Render retry instead of returning normal success. New final quality reviews record their engine, contract and Factory version alongside the reviewed PDF and ZIP hashes and timestamp.
The release review now links each chart to its saved heading and items. Saving uses the existing free correction action, then requests the existing chart redraw before continuing layout and quality checks. A failed redraw can be retried without submitting the saved words twice. Manuscript and paid image generation are unchanged.
Introductory home-organization and clear-counter kitchen scenes now use concrete room, furniture and storage requirements. Stale abstract briefs are retired, and their concrete free-photo searches run before the old chapter-caption searches. Physical image, mismatch, source and spend checks remain enabled.
Section headings use the PDF renderer's keep-with-next instruction so they stay with their first supporting paragraph at page boundaries.

### What was fixed
An unfinished book could remain queued after its worker stopped, because the task returned its error summary normally and Render never retried it. Review records also lacked the version evidence needed to identify which editor checked a downloaded book.
The chart correction backend existed without a review-screen control, leaving owners unable to correct editorial chart findings through the website.
An abstract home-organization heading was being treated as a list of visible objects such as "start", "what" and "really". Free replacements selected a model house and a paper box instead of a usable room scene. Those examples are now regression cases rather than approved substitutes.
Standard CSS break avoidance did not stop the PDF renderer stranding section headings at the foot of a page. Three rendered page-boundary regressions reproduced the problem before the correction.

### Do the steps change?
The intended recovery requires no extra Resume click for these interruptions. Genuine quality failures and customer choices still stop safely. Existing reviews are not retroactively certified, retry and spending limits are unchanged, and this does not implement automatic repair of every editorial finding.

### Release gate
The unchanged baseline passed 820 stability tests, 84 execution checks and all 442 protected ebook checks. Two continuation regressions and one provenance regression failed before the change. Post-change verification passed all 448 protected ebook checks, 820 stability checks and 142 focused checks. Full release and live acceptance remain required before claiming deployment or one-button completion. See docs/EBOOK_COMPLETION_SOLUTION.md for the remaining delivery contract.

## 1.9.62 — Recognize native chapter comparison tables

### What changed
Visual completion counts a valid comparison table printed from the chapter's current Markdown, without requiring a duplicate image of that table. Empty tables and fenced example markup do not qualify. Photograph and physical-demonstration requirements remain unchanged.

### What was fixed
A saved ebook with a real comparison table and a separate checklist could be stopped by a false missing-comparison finding. The checker now recognizes the table that the reader actually sees in the interior.

### Do the steps change?
Resume the saved build, then inspect the finished PDF and its visuals through the existing release review. No manuscript rewrite or additional paid image generation is required for this correction.

### Release gate
The fast baseline passed 816 tests and the targeted visual checks passed 17 tests. The full acceptance run passed 3,342 tests; its only failure identified missing required headings in these release notes. The release notes were corrected and the complete version-management test file rerun. This is combined run-and-rerun evidence, not one uninterrupted green run. Live deployment and saved-book export verification follow the test gate.

## 1.9.61 — Bound workspace ebook project responses

- General project reads omit duplicate workspace preview HTML and cached review thumbnails. Dedicated preview/review routes and stored manuscripts, decisions, PDFs, ZIPs remain unchanged.
- Added regression coverage for response size, source preservation, and legacy detail compatibility. Live memory verification remains required.

## 1.9.60 — Discard stale previews when recovering ebook visuals

### What changed
Changing the ebook style or redrawing charts invalidates both the current preview and its legacy fallback. Previous PDF and ZIP downloads remain preserved.

### What was fixed
A saved book could fail visual approval with “preview HTML is missing rendered figures” because an old preview survived a layout repair. The current manuscript, photographs and cover do not need regeneration.

### Do the steps change?
For an already affected saved book, select its existing style again to invalidate the old preview, then review the visuals and resume the saved build. Future print redraws clear both preview fields automatically. All visual, preview and export quality checks still apply.

### Release gate
The original failure was reproduced before the fix; both recovery regressions pass. All 3,343 acceptance cases have passing results on the final runtime: the broad run passed 3,342 cases and its one missing preservation-file failure passed unchanged after restoring the exact original PDF and ZIP. No skipped cases or weakened quality gates. This is combined run-and-rerun evidence, not one uninterrupted green run. Live recovery and re-export remain to be verified.

## 1.9.59 — Recover blocked ebook visuals after an old approval

### What changed
Retry Automatically remains available when the current visual set fails its checks, even if Visuals still records an old approval. The existing retry preserves completed visuals and the cover, repairs blocked slots, and restores the required photograph count.

### What was fixed
Project 23 retained an approved Visuals stage while its Chapter 1 photograph failed its current brief. The hidden retry button left no route to the existing chapter-based graphic fallback and photograph recovery. Backend approval checks are unchanged.

### Do the steps change?
Open Visuals and use Retry Automatically when a saved visual set is blocked. Wait for the repair to finish, inspect and approve the visuals, then resume the existing book. No new manuscript generation is needed.

### Release gate
Combined exact-case evidence covers all 3,341 acceptance cases with no unresolved failures or skips. The broad run passed 3,330 cases; its two release-note failures pass after correcting this entry. Shared UI protection passed 1,007 cases and initially reported a timing failure and a custom browser timeout under heavy concurrent load; both pass unchanged in a serial rerun. All 31 version checks pass. This is combined run-and-rerun evidence, not one uninterrupted green run. No tests or quality limits were weakened. Live recovery and re-export remain to be verified.

## 1.9.58 — Preserve manuscript boundaries in practice charts (candidate)

### What changed
Practice charts keep paragraph, heading and list boundaries. Questions and introductions ending in a colon cannot become action steps. Redrawing a defective saved automatic practice chart derives complete instructions from its original chapter, keeps the previous wording, and preserves owner edits.

### What was fixed
A kitchen chart joined “ask three questions” to its first question, mixing questions and actions. The redraw control previously rendered those same invalid words again.

### Do the steps change?
New practice charts use the corrected extraction automatically. For an existing generated practice chart, use “Use clearer type and redraw charts”, then rebuild and review the revised PDF and ZIP. Human approval and release checks remain required.

### Release gate
Combined verification covers all 3,341 unique acceptance cases with zero unresolved failures or skips. Final runtime source passed 434 completion checks and 29 design/export checks; all 40 final lock/version checks pass. The initial broad run needed the original preservation fixture restored and an unchanged crossword case rerun. This is not one uninterrupted green run. Three new regressions remain enrolled in both the acceptance manifest and completion lock. No deployment or live re-export is claimed.

## 1.9.57 — Recognize chapter endings and keep household photos on topic

### What changed
Rendered page review recognizes standalone back-matter headings despite PDF footer extraction order. A substantive closing page is recognized only when the next rendered page begins a numbered chapter or back matter. Blank pages, tiny orphan fragments and sparse midchapter pages remain findings. Gardening photo routing now requires whole-word horticultural context; ordinary household containers and bedside water bottles inherit gardening context only from a gardening book. Cached canonical gardening briefs are rederived when the chapter belongs to another subject.

### What was fixed
Fresh project 23 reached export, but the reviewer classified its short chapter endings on pages 8 and 51 and its legal disclaimer on page 52 as ordinary sparse body pages. Real rendered text reproduces all three false findings. The bedroom photo also retried gardening images because “pot” matched inside “spots,” and the saved gardening brief survived retries. No manuscript, font size, image resolution or quality threshold is changed.

### Do the steps change?
Resume the saved build after deployment. The unchanged PDF content is checked using its real page boundaries. No manuscript generation or budget increase is needed.

### Release gate
The full pinned-dependency run passed 3,275 cases with zero failures, errors or skips. The editor unit suite had not been enrolled in the manifest: it is now permanently registered and adds 63 passing cases. Combined exact-case evidence covers all 3,338 unique cases, including every prior 3,269 case, with no missing or duplicate cases. Runtime source did not change after the full run. Three page-context and four photo-routing regressions were proved to fail before their respective repairs. The actual saved PDF clears all three page-context false alarms locally. Completion is relocked to verified candidate 12799f347d383aa0b2569a9b9fef175c4c88f786. Live deployment and final export remain pending. See release_evidence/ebook-page-photo-recovery.json.

## 1.9.56 — Keep research signals out of ebook references

### What changed
Generated ebook references exclude sources rejected by the existing manuscript authority policy. The original research evidence and book contract remain intact. A source-only correction reassembles references while retaining every accepted chapter and making no chapter-provider calls.

### What was fixed
Fresh project 23 wrote nine passing chapters but stopped at 30% because Facebook research was copied into Sources. Correction copied the same rejected citation repeatedly. The unchanged validator now passes the locally recovered saved manuscript with all nine chapter bodies byte-for-byte preserved.

### Do the steps change?
Use the ordinary automatic ebook builder. For a saved source-only failure, use Request Correction, approve the recovered manuscript, and resume the build. Accepted chapters and the original research evidence are preserved. No budget increase or chapter regeneration is required for this correction.

### Release gate
The 232-file pinned-dependency acceptance run passed 3,268 cases; its only failure was this missing release-note section. All 31 version-management checks pass after correcting the note; the combined evidence retains all 3,269 unique acceptance cases, with zero failures, errors, skips, missing or duplicate cases. See release_evidence/ebook-reference-recovery.json. This is not a claim of one uninterrupted green run. All 61 source-policy tests pass, including three regressions proved to fail before the repair. The baseline Fast Stability Gate passed 814 tests. Live deployment and PDF/ZIP verification remain pending.

## 1.9.55 — Give chapter repairs exact targets and stop stalled retries

### What changed
Filler repairs name the exact forbidden wording and ask for a concrete replacement while preserving valid prose. Automatic corrections stop after two attempts without another accepted chapter; the durable counter survives worker restarts. Accepted chapter progress starts a fresh allowance.

### What was fixed
A fresh weekly desk reset book repeatedly failed chapter 4 for “keep going”. Its repair prompt named only a defect class, and the manuscript checkpoint ceiling allowed repeated paid failures. The quality validator and customer budget cap remain enforced.

### Do the steps change?
Use the ordinary automatic ebook build. A stalled repair preserves the draft and accepted chapters and stops for an engine correction rather than spending through repeated retries.

### Release gate
All 3266 unique acceptance cases pass at c4c009581ec0205bffcc4ba46fa6c90e14e2b412, including three added checks. Two defect regressions fail before the repair. The initial run lacked Chromium headless shell; all 38 affected checks pass after restoring it, and the initial reports are retained. No source or test changes were made between runs. No successful fresh-book export is claimed; project22 reached its authorized $3.50 cap before this source change.

## 1.9.54 — Do not approve chapter photos from planned filenames (candidate)

### What changed
A local photo filename can no longer supply a missing subject or chapter activity. Filename conflicts still reject unsuitable candidates. Rechecking a saved visual plan revokes an approval that depended on its planned filename.

### What was fixed
The same meditation image could fail the Mindful Eating check under its original name and pass when renamed person-eating-mindful-meal.jpg. Three regression cases reproduce the filename-only, misleading-metadata and saved-approval paths. Existing chapter-activity checks and genuine scene descriptions remain required.

### Do the steps change?
Use the existing ebook picture review and replacement controls. Revalidate saved pictures before building corrected downloads. Existing exported files remain available until corrected files are explicitly rebuilt and reviewed.

### Release gate
Candidate only. The original 26 photo-matching cases passed before the source change; all 29 pass after it. Complete workflow and release verification are pending. No customer projects were overwritten and no paid generation calls were made by this repair. Existing saved exports require an explicit corrected rebuild; a code deployment does not replace their bytes.

## 1.9.53 — Preserve instructional meaning and strengthen ebook cover titles

### What changed
Checklist extraction keeps each bullet list with its own heading and introduction. Lists of things the reader does not need cannot become positive checklists. Numbered instruction headings can supply the chapter's real practice sequence. The editor checks existing saved graphics for the same reversal before reuse.

Portrait photographs now fit beneath chapter openers using measured HTML dimensions. Their complete pixels, aspect ratio and stored bytes remain intact; the heading is no longer stranded on a separate page.

### What was fixed
The completed Mindfulness in Motion PDF exposed defects that file-integrity checks missed: unnecessary equipment appeared as a checklist, the eating chapter used a generic meditation photograph, and a brief cover title passed at a weak thumbnail size. Concrete chapter activities now constrain automatic photo matching and lead the free search queries. Cached pictures are rechecked before acquisition so an outdated match can be replaced. Brief cover titles have a larger rendering and thumbnail floor; long titles retain safe wrapping, and render cache identities change with the typography policy. Approved wording and paid-provider safeguards remain intact.

### Do the steps change?
Use the existing ebook editing and build controls. Accepted manuscripts are preserved. Previously downloaded PDFs and ZIPs remain intact; they are not silently replaced. A corrected export still requires the normal quality checks and any existing cover choice.

### Release gate
The unchanged baseline passed 809 stability checks and five real-browser customer-path checks. Seven regression cases cover the exported defects, a correct activity match, and a real PDF portrait placement without cropping or resampling. Full acceptance and actual deployment results are recorded in release evidence before this candidate is released. No paid provider calls are authorized by this repair.

## 1.9.52 — Mindfulness picture classification and free-search recovery

### What changed
Ordinary mugs, plates, shirts and ceramic objects no longer turn unrelated ebook chapters into printed-merchandise briefs. Classification requires merchandise intent and word boundaries. A stale inconsistent brief is rederived from the chapter. Free photo searches continue past uncertain candidates through the existing query ladder and configured sources. Only the selected image is stored; uncertainty still requires review and paid-image safeguards remain.

### What was fixed
Mindfulness in Motion stopped at 40% because everyday scenes were incorrectly judged against printed-keepsake requirements. The fallback then produced an all-text-box set rejected by the unchanged editorial standard. The release also retains the readable tall-diagram sizing and accurate interior PDF picture inspection from the earlier quality candidate.

### Do the steps change?
Use the existing Resume Build control for saved unfinished ebooks after deployment. Accepted manuscripts are reused. Title, cover and picture decisions continue to use their existing controls. Existing saved products are preserved; no paid image authorization is added.

### Release gate
Owner authorized the uploaded completed Room-by-Room PDF and ZIP as the required preservation reference on October 20. Its exact hashes, ZIP integrity and embedded PDF identity are checked. Missing or altered reference files fail rather than skip. Original Project 351 checksum assertions remain additional checks when its pair is present. The customer reference bytes remain outside the public repository.

The prior candidate passed 339 protected ebook/photo checks and 809 stability checks. The complete 232-file acceptance run and final source proof are recorded in release evidence before deployment. See the newest release handoff and PR74 for actual deployment status; a test pass alone does not certify the live book as finished.

## 1.9.51 — Readable diagrams and verified PDF picture placements (candidate)

### What changed
Tall, measured ebook diagrams fit beneath chapter openers when they can retain labels of at least 8 pt. The complete high-resolution image is preserved. Unmeasured graphics and graphics that cannot safely shrink keep their existing size for review.

### What was fixed
A real rendered fixture stranded Chapter 4's heading on a separate page. The corrected 37-page fixture keeps all ten chapter openers with their visuals; the original had 38 pages. PDF visual inspection now counts image placements rather than unused image resources, excludes every cover-page image from the interior count, and reports an unavailable PDF reader instead of a false pass.

### Do the steps change?
Use the existing ebook build and review controls. No paid provider calls are required. Existing saved products and protected coloring, puzzle, and planner implementations are preserved.

### Release gate
Candidate only. Before/after protected ebook workflow checks: 178 passed each. Focused design/export checks: 16 passed. The earlier PDF-inspection regressions were proved to fail on unchanged main and pass after correction. Complete acceptance collection retains all 3,234 prior cases and adds six (3,240 unique cases); collection is not a full test run. Final stability and metadata verification are recorded in the release evidence. Full release remains blocked because the preserved Project 351 PDF/ZIP pair is absent from this environment; its preservation case skips. No gate or reference hash was weakened. No merge or deployment.

## 1.9.49 — Customer account isolation candidate

### What changed
An explicit accounts mode binds project access and standalone puzzle files to signed-in users. Private invite mode remains the default for the existing owner workspace.

### What was fixed
Account-mode project reads, listings, writes through the database, build references and package downloads must use the signed session identity. Client owner IDs and admin flags cannot select another customer's work. Registration cannot grant a new customer the administrator role in accounts mode. The public entry page shows the existing subscription plans and leads to joining or signing in. Signed-out Account navigation is replaced by a clear Sign in link. In explicit accounts mode, signed identity replaces the shared beta invitation. The sign-in page is explicitly permitted before authentication; successful registration and sign-in open the dashboard automatically. Signed-in users can sign out from the dashboard.

### Do the steps change?
This candidate is not enabled in production. Account mode requires a verified owner sign-in and stable session key before activation. Unreviewed generic project writes, marketing and billing endpoints are unavailable to customers in this staged mode; owner/admin access is retained. Do not advertise public memberships as complete.

### Release gate
All 3234 acceptance cases across 231 files passed, including all prior 3197 cases and the real plans-first/join/sign-out/sign-in flow. Zero failures, errors, skips, missing, extra or duplicate cases. Disposable PostgreSQL CI passed on the same runtime source. Existing locks restored; customer isolation remains PROTECTED pending production activation proof. No live configuration changes or paid provider calls. See release_evidence/account-isolation-final.json.

## 1.9.48 — Preserve source examples and complete chart instructions

### What changed
The free ebook proofreader respects the full Markdown code fence. Practice-step graphics retain complete source instructions for the existing renderer to wrap.

### What was fixed
Shorter inner code markers and markers followed by example text no longer expose protected examples to automatic corrections. Practice instructions between 79 and 150 characters no longer lose their endings at the shorter key-point-card limit. Existing saved books and protected generator implementations are unchanged.

### Do the steps change?
Use the same build and review controls. Existing saved PDFs and ZIPs are preserved; these repairs apply when editing or generating a new draft. No paid provider calls are needed for the repairs.

### Release gate
All 3,197 unique cases passed across all 230 manifest files, with zero failures, errors, skips, missing or duplicate cases. All 3,191 prior cases retained. Includes real local browser builds from both entry paths, tab recovery, reviewed-edit PDF/ZIP output and protected product checks. No paid provider calls; accepted files preserved. Deployment verification pending.

## 1.9.47 — Preserve saved ebooks when reopening

### What changed
Saved ebook Open reads status without automatically resuming a build. Continue remains explicit.

### What was fixed
Stale finished flags no longer contradict failed export verification. A verified saved PDF/ZIP pair remains downloadable as saved files while release approval is pending. Quality review uses the verified acquired picture when a factory-copy path belongs to an old builder. Completed or review-blocked workflow polls do not start a builder task. Opening the full preview now records only its viewed identity and preserves the certified export status, rather than copying an older document status over it.

### Do the steps change?
Open a saved ebook to inspect it; choose Continue for unfinished work. A previously finished book requiring verification opens its quality review instead of rebuilding automatically.

### Release gate
All 3,191 unique release cases passed across all 230 manifest files, with zero failures, errors or skips and exact case reconciliation. Five real-browser customer journeys passed. No paid provider calls; protected generator implementations and existing customer exports preserved.

# Changelog

## 1.9.46 — 2026-10-17

**Safer manuscript editing, smaller saved-product lists and PostgreSQL billing repairs.**

### What changed

The manuscript editor shows the saved original beside the proposed revision,
with a Reject button that restores the original in the editor without saving.
The comparison fits narrow screens.
Saved lists carry display metadata and PDF/ZIP links instead of nested book and
image payloads. Opening a project still retrieves its full unchanged record.

### What was fixed

Editing while a review is pending prevents
that older response from replacing newer typing. Requests time out after 30
seconds; a save whose response is lost requires a reload before another write.
Manuscript Apply and Undo now enforce the existing APPROVED/LOCKED content
guard before editing. Protected artifacts cannot be changed in place.
Nested document, cover and edit-history data made saved lists unnecessarily
large. PostgreSQL billing also received SQLite-only transaction syntax, and
duplicate payment events could raise a database error. Billing now serializes
seat reservations with the active database's locking mechanism and handles
event replays idempotently. Prices, payment configuration and seat limits stay
the same.

### Do the steps change?

Review the comparison, then choose Apply or Reject.
An approved artifact needs Create Draft Revision before editing; locked
artifacts remain unchanged.
Existing acceptance, undo, quality checks and original exported files remain
protected. No new provider or paid call is introduced.

### Release gate

Browser regressions verify complete-record preservation on rejection, delayed
review responses, failed-review recovery, and a save that succeeds before its
response is lost. Saved-list checks verify metadata, download links and unchanged
full records. Isolated PostgreSQL integration covers final-seat contention,
rollback, repeated/concurrent webhooks and seat reuse. Required release gates
must pass on the combined candidate before deployment.

## 1.9.45 — 2026-10-15

**Reopen saved products without saving or replacing them.**

### What changed

Saved Open keeps the latest product selection, cancels pending reads when the customer leaves, and bounds stalled reads to 30 seconds. Failed, malformed or mismatched responses keep the current screen and allow retry. Existing PDF/ZIP links display directly without an automatic Save or Export.

### What was fixed

Late detail responses could open the wrong product or undo navigation. Opening a finished product also invoked Save before showing downloads, changing stored metadata and removing its saved preview PDF.

### Do the steps change?

No. Choose Open as before. Completed content and stored files stay unchanged; explicit Save, Export and recovery actions remain available.

### Release gate

Real-browser cases cover read-only reopening, overlapping selections, navigation, failed/malformed/mismatched reads and stalled-request retry. They compare the complete stored records and PDF/ZIP hashes before and after. Full protected-generator and recovery checks remain required before release.

## 1.9.44 — 2026-10-15

**Use the same final ebook quality review for manual and one-button exports.**

### What changed

Both paths inspect the real PDF pages and ZIP before calling a book ready. Reviews record the exact PDF/ZIP hashes, retain correction findings with the draft, and clean up temporary page images. A concrete quality failure stops repeated export attempts until the customer resumes after correcting it.

### What was fixed

One-button completion previously skipped the final editorial review. Missing outputs or incomplete page inspection could also go unreviewed. Final PDF assembly now retains the approved title, author and chapter navigation; the reviewer reads actual document metadata, including Unicode, instead of bookmark headings.

### Do the steps change?

Passing books continue automatically with no additional click or paid call. A failed quality check retains the draft and explains the correction needed. Existing customer outputs and other generator workflows are preserved.

### Release gate

Regression coverage checks both final-review verdicts, missing files, reviewer failure, temporary-file cleanup, PDF/ZIP consistency, incomplete page inspection, Unicode metadata and stopped quality failures. Complete automatic, custom and guided build fixtures must deliver real PDF/ZIP files with a passing final review. Actual release counts are recorded in the session handoff.

## 1.9.43 — 2026-10-15

**Keep ebook progress connected without another build click.**

### What changed

The ebook screen reconnects after temporary connection and server failures while retaining the last reported progress. Reopening a book retries reading its status automatically. A reopened screen waits for an older progress request to finish, and late responses from the older screen cannot overwrite the current book.

### What was fixed

A temporary connection error previously stopped the screen and displayed zero progress. Reopening during an older request could also abandon the new screen's progress loop.

### What stays protected

Reconnection never starts a replacement project or resets generation attempts. Only one progress request runs at a time. Actual build failures and intentional approval pauses retain their existing controls. Coloring books, crosswords, word searches and other generators retain their existing paths.

### Do the steps change?

No additional click is needed after a temporary connection failure. Keep the page open and it reconnects automatically.

### Release gate

Real-browser regression checks cover disconnection, temporary server failures, reopening, late responses and denied requests. Existing automatic/guided ebook fixtures verify real PDF/ZIP downloads and preservation of completed content. Release verification is recorded in the session handoff.

## 1.9.42 — 2026-10-15

**Reconnect completed coloring-book files after an interrupted final save.**

### What changed

The Factory checks expired or failed coloring builds at startup and every minute. It verifies the original stored PDF and ZIP and reconnects their download records without requesting artwork or rebuilding exports. Existing Save consent stays unchanged.

### What was fixed

A database disconnect after publishing both files could leave a completed book marked running. Completion and download metadata now save together, with bounded fresh-connection retries. Status checks and Workflow retries also recognize existing finished packages. A missing or mismatched package is preserved and cannot silently fall back to paid generation.

### Do the steps change?

No extra recovery step is required for a verified finished package. Return to the Factory to review and save the completed book. Interrupted artwork requests and approval pauses still require their existing review.

### Release gate

Coverage includes lost commit acknowledgements, restart recovery without local files, exact PDF/ZIP downloads, active leases, concurrent edits, corrupt packages and zero provider calls during recovery.

## 1.9.41 — 2026-10-15

**Open Saved Projects without loading every book into the list.**

### What changed

Saved Projects and the dashboard send compact product details. Open retrieves the original full record. Saved PDFs, ZIPs, artwork and approval records stay intact.

### What was fixed

Several concurrent list requests could exhaust the website memory limit by holding full books and checking their assets at once. Customer lists now process one record at a time and serialize these heavy reads. A loading failure offers Try again instead of falsely saying there are no saved products.

### Do the steps change?

Open Saved Projects, choose your product, and click Open or its download button. The product visibility and download quality rules are unchanged.

### Release gate

Checks cover large saved records, bounded memory, original-data preservation, fresh full-record reads on Open, and browser recovery from a failed list request. No new production books or paid artwork calls are used.

## 1.9.40 — 2026-10-14

**Preview a coloring book using the number of pages you enter.**

### What changed

Enter a small count, such as 2 or 4 coloring pages, to build a short preview. The Factory honors that count through artwork generation, refresh, and PDF/ZIP downloads. A book cover is additional; one page retains the existing Single Sheet behavior.

### What was fixed

The previous 12-page minimum blocked short previews. Small requests now generate only the requested coloring pages. Invalid counts are refused before artwork starts. Settings errors no longer display the misleading interrupted-build guidance.

### Do the steps change?

Enter your theme and page count, then click Generate Product. The form explains how to request a short preview. Existing progress, save, cover checks, and download actions remain available.

### Release gate

Checks use local provider fixtures and real PDFs and ZIPs for small previews. Actual browser checks cover 2-, 4-, and 12-page books, settings errors, refresh, and downloads. No paid artwork calls or new production books are used for verification.

## 1.9.39 — 2026-10-14

**Build coloring books on the background builder and preserve finished artwork.**

### What changed

In Workflow mode, coloring generation records a durable request and returns promptly. The existing builder creates the artwork, checks quality, and prepares PDF/ZIP downloads. Progress survives closing and reopening Product Factory. Concurrent repeat requests attach to the same recorded build.

### What was fixed

A live coloring request exhausted the website's 512 MiB memory limit. Heavy generation and packaging now run on the existing builder. Each source image is verified in shared storage before the next artwork request. Saved prompts and artwork are reused on recovery; uncertain interrupted image calls stop for review instead of automatically charging again. Local print-layout measurements use exact pixel histograms with explicitly released image buffers. Downloading a completed background package reuses its exports rather than rendering on the website again.

### Do the steps change?

Click Generate Product and watch the saved progress. Existing cover/sample approval stages are retained. Completed products still offer PDF and ZIP. The website rejects a count that would silently be expanded beyond the customer's entered page count before starting paid artwork. Local inline mode and legacy saved products remain supported.

### Release gate

Provider fixtures exercise real generated PDF/ZIP files, verified storage reads after a simulated container replacement, Save/reopen preservation, concurrent duplicate protection, interrupted-call refusal, and print-processing memory limits. No paid provider calls or new production books are used for verification.

## 1.9.38 — 2026-10-14

**Build a recommended ebook from one button, or choose a style for your own.**

### What changed

Factory Market Advantage's ebook recommendation now starts the durable ebook build immediately. The Factory selects a template suited to the topic and completes production through the quality checks and PDF/ZIP export. The custom Ebook Builder and Product Factory form offer all six templates and build with the customer's selected style.

### What was fixed

The research handoff no longer opens an unstarted ebook workspace requiring another build click. Recommended ebooks no longer all receive the same fixed default template. New automatic and custom builds use the existing validated free-visual recovery and cover pipeline without intermediate picture or cover-choice pauses. Failed quality checks still block completion. Older saved projects retain their existing review and resume behavior.

### Do the steps change?

For recommendations: select the ebook, enter the author name, and click Build My Ebook. The Factory chooses the style and produces the PDF and ZIP. For your own ebook: enter its details, choose one of six templates, and click Build My Ebook. Each new path has its own repeat-click identity; completed products are never regenerated by a repeat request.

### Release gate

Checks cover Factory-selected and customer-selected templates, refusal of failed visual quality, duplicate-click recovery, actual fixture PDF/ZIP downloads, and both browser handoffs. Legacy review and guided-cover tests remain enrolled. No real paid calls are permitted during verification.

## 1.9.37 — 2026-10-14

**Keep ebook table headings with their rows across page breaks.**

### What changed

All six ebook templates now repeat column headings on continuation pages. A page break cannot strand a table heading by itself at the bottom of the preceding page. The change uses the PDF renderer's native repeated-header support and preserves the manuscript, pictures, and chosen template.

### What was fixed

Tables could lose their column labels when rows continued onto another page. Native repeated headers keep those labels visible and keep the first row with its headings.

### Do the steps change?

No. Choose a template, preview, and export as before. Existing approved exports are preserved.

### Release gate

Validation includes a real 80-row table rendered under every ebook template, requiring column headings on every page containing table rows and preserving the final row.

## 1.9.36 — 2026-10-14

**Recover the registered original when an ebook's local picture copy changed.**

### What changed

Picture localization now checks an existing copy against the visual plan's SHA. When it differs, recovery uses verified storage bytes only if they match that same planned SHA, then replaces the local cache atomically. Final readiness reports an actual asset-validation failure before a secondary inferred chapter requirement.

### What was fixed

A packaged or changed chart copy on the website could be mistaken for the registered source merely because its file existed. This blocked the final save of an otherwise reviewed ebook and hid the real cache mismatch behind a missing demonstration message.

### Do customer steps change?

No. No generation, manuscript, PDF, ZIP, storage originals, or review decisions are changed. Unavailable or mismatched stored originals still block approval.

### Release gate

Regression checks cover a changed website cache, an already-local changed path, and refusal to replace a cache with bytes that differ from the planned SHA. Existing cross-machine recovery, reviewed-workspace, and customer-save checks remain required, followed by the full release gate.

## 1.9.35 — 2026-10-13

**Keep the completed workspace's approved visual plan through final save.**

### What changed

For a structured workspace with approved visual/cover/design/preview/preflight stages, passing preflight, and a passing final review of the exact current PDF and ZIP, final readiness uses the chosen visual types. Actual assets still undergo their existing hash, dimension, source, caption, matching and legibility checks.

### What was fixed

The legacy topic inference demanded new demonstration photos for chapters deliberately planned and approved as charts, after the workspace's own preflight and final review had passed.

### Do customer steps change?

No. No content, approved visual, export, or paid generation changes. Unreviewed and legacy books retain inferred requirements. Stale exports, failed reviews and changed/missing originals never qualify for the reviewed-workspace contract.

### Release gate

Regression checks cover the approved plan, stale PDF/ZIP reviews, failed or incomplete review, unapproved visuals, failed preflight, legacy behavior, and changed asset refusal. Full release validation is required before deployment.

## 1.9.34 — 2026-10-13

**Use the saved original pictures during final ebook approval.**

### What changed

Before final save checks readiness, restore this project's existing pictures and PDF/ZIP from storage using the same recovery helpers used by preview, review and finished-book status. Rebase export pointers onto the website's copies only after both export files verify.

### What was fixed

The website treated a builder's retired disk paths as missing pictures and exports, even when the finished book and stored originals were available. Approval now checks the original files on the website's disk.

### Do customer steps change?

No. The approved manuscript, images, PDF and ZIP are preserved. No regeneration or paid image call is involved. A picture that storage cannot supply still blocks save.

### Release gate

Cross-machine save/reopen checks cover restored original bytes, unchanged manuscript/PDF/ZIP bytes, the correct project identity, and rejection when an original picture or ZIP is unavailable. Full release validation is required before deployment.

## 1.9.33 — 2026-10-13

**Allow ordinary reader guidance through final ebook approval.**

### What changed

Recognize model and production roles instead of blocking every occurrence of “you are a.” Actual AI role assignments and production instructions remain blocked in manuscript, HTML, and PDF text.

### What was fixed

Final save incorrectly treated headings such as “If you are a renter” and “If you are a homeowner” as leaked AI instructions, stopping final approval of an otherwise reviewed book.

### Do customer steps change?

No. Existing approved content and exports remain intact. No rebuild or paid generation is needed.

### Release gate

23 focused approval and save/reopen checks passed. Reader headings pass on all content surfaces; real model roles and production instructions still fail. The save/reopen regression retains both reader headings. Full release validation is required before deployment.

## 1.9.32 — 2026-10-13

**Keep repeated full-book reviews within memory limits.**

### What changed

Chart contrast uses exact weighted colour quantiles instead of a Python tuple for every pixel. Freed request/image buffers are collected before and after serialized scans, after PDF resources close; glibc returns unused native heap pages where available. Non-glibc platforms retain portable garbage collection.

### What was fixed

The final revised book exported successfully on1.9.31, but another review after the longer session exceeded the512MiB website limit. The earlier successful cold review had not established repeated-request stability.

### Do customer steps change?

No. No rebuild, paid provider call, hosting/config change or quality-threshold change. Native image resolution, accepted source identities, chart contrast values and printed label checks are preserved.

### Release gate

Three actual-book scans recognized13 visuals with zero hard failures. With app loaded, peak RSS252.2->258.7->264.0MiB; after repeated scans current RSS177.8/177.9MiB. Exact contrast equivalence and cleanup-after-error regressions added. 31 focused checks and710 stability checks passed. All3,026 unique full-release cases passed (873+735+733+685), zero failures/errors/skips/missing cases. Production repeated-review verification follows deployment.

## 1.9.31 — 2026-10-13

**Save large ebook previews without duplicate HTML.**

### What changed

Identical ebook-workspace preview HTML is stored once in the existing project record. Reads restore both expected preview fields, keeping the exact legacy HTML available. Older records, different previews, other products, manuscripts and PDF backups are unchanged.

### What was fixed

After the release-review memory repair passed live, the final layout rebuild repeatedly exhausted PostgreSQL memory during large project UPDATEs. The saved record had grown to 19,870,300 bytes. Duplicating the same inline full-resolution preview increased every save unnecessarily.

### Do customer steps change?

No. Preview and export resolution stay intact. No database schema, hosting plan, production configuration or secrets change. No customer originals are deleted.

### Release gate

16 focused storage, legacy preservation and Saved Projects checks passed. Stability gate710 passed. All3,024 unique full-release cases passed (873+733+733+685), zero failures/errors/skips/missing cases. Actual book preview serialization13,843,809->6,921,961bytes with exact HTML roundtrip. Production recovery verification follows deployment.

## 1.9.30 — 2026-10-13

**Keep picture captions with their images and open the visual you clicked.**

### What changed

The release review bounds image-analysis buffers while measuring photo resolution from the original embedded pixels. The print renderer keeps each image with its caption across page breaks. Enlarged review and photo restoration controls target the exact selected card even when two visuals share one PDF page.

### What was fixed

Large images could exhaust the website's memory during final review. A photograph's caption could fall onto the next page in the larger-type layout. The second visual on a shared page could open the first visual or send the first visual's identity to photo restoration.

### Do customer steps change?

No. Existing manuscript, photographs and cover choices stay the same. No additional paid generation is added.

### Release gate

Both regressions were reproduced in actual PDF rendering and a real browser before the fixes. Invite-protection checks passed 16 before changes. 37 focused checks, 710 stability checks and all 3,020 unique full-release cases passed without failures, errors or skips. Actual 64-page review recognized 13 visuals with zero hard failures; peak RSS fell from 291.9 to 261.9 MiB (286.3 MiB including app import). Production verification follows deployment.

## 1.9.29 — 2026-10-13

**Keep the requested ebook correction ahead of progress polling.**

### What changed

Automatic build-progress requests preserve a pending workspace correction until the builder takes it. A newer explicit customer choice can still supersede an unrun choice.

### What was fixed

The clearer-print button queued its update, then opened the build screen. That screen could replace the queued update with an ordinary advance before the builder applied it. The print update also now releases the completed-visuals hold so the design, preview, quality checks and export can continue.

### Do customer steps change?

No. One clearer-print click performs the update and continues the build. Existing photos, manuscript, cover and original exports are preserved; no paid generation is added.

### Release gate

Queue and builder checks passed before the repair (35 cases), and 45 focused checks passed after it. Fast Gate: 710 passed. All 3,017 unique required acceptance checks passed in four isolated partitions (873 + 732 + 731 + 681), with zero failures, errors, skips or missing cases. The regression exercises 20 actual progress requests and verifies that the builder applies the pending correction exactly once. Live export verification follows deployment.

## 1.9.28 — 2026-10-13

**Larger, clearer ebook type, sharp chart files and readable visual previews.**

### What changed

List-shaped chapter graphics use larger sans-serif labels (about 13.4 points at the narrowest normal column), full wrapping and lossless double-resolution PNGs in the ZIP as well as the PDF. A book-specific clearer-print update selects a clean sans-serif design with 13-point body text and 11-point captions. The review offers an enlarged visual viewer backed by previews up to 1200 pixels wide.

### What was fixed

Small chart lettering, 260-pixel review thumbnails and unnecessarily reduced interior photos. Photographs can restore the same verified licensed Pexels original at up to 2400 pixels, keeping a checksum-verified copy of the former file. Photo identity, credit, manuscript and cover are preserved. PDF photo embedding keeps up to 2400 pixels with higher JPEG quality; chart fallbacks use PNG.

### Do customer steps change?

Use View clearly to inspect a visual, Restore original resolution for the same stock photograph, or Use clearer type and redraw charts to rebuild the layout and exports. Approval remains a separate decision. No paid image generation is added.

### Release gate

Fast Gate: 710 passed. Full acceptance: 3,016 unique required cases verified across four isolated partitions, with no missing cases or unresolved failures, errors or skips. Initial browser setup errors and three failing cases were corrected and all eight affected cases passed a recorded rerun. Image/browser checks passed 50; chapter/clarity/design checks passed 31; invite/lock checks passed 25. Resolution expectations now require 2800-pixel charts and 2400-pixel photo embedding; the 8-point refusal threshold remains unchanged. Live book export verification follows deployment.

## 1.9.27 — 2026-10-12

**Finish the exported-book review without retaining every decoded photograph.**

### What changed

Editor-in-Chief text checks extract only text, image checks release MuPDF caches between pages, and PDF/ZIP resources close after each review. Complete-book scans run one at a time within the website process so simultaneous review requests cannot multiply image buffers.

### What was fixed

Project 20's release review caused a confirmed 512 MiB out-of-memory restart. The same saved PDF/ZIP review peaked at 289 MiB before and 204 MiB after in a standalone reproduction. The duplicate-point check also preserves distinct numeric milestones, such as 30-day and 90-day timeline entries, while still rejecting repeated identical points.

### Do customer steps change?

No. Open Editor-in-Chief review, inspect its findings, and make the final product decision. The manuscript, pictures and PDF/ZIP are not regenerated. Human judgments remain required; no paid reviewer call is added.

### Release gate

Baseline Fast Stability Gate: 710 passed; baseline review suites: 33 passed. All 3,010 required checks across 214 acceptance files subsequently passed in four isolated manifest partitions. One reference-preservation check initially skipped because its isolated checkout lacked the real preserved files; after supplying the already-verified originals, that check passed through the release runner. XML reconciliation against the full collected manifest proves no missing checks and no unresolved failures, errors or skips. No tests were weakened and no paid calls were permitted. The earlier incomplete run is not counted as a pass.

## 1.9.26 — 2026-10-12

**Open high-resolution ebook cover previews without exhausting website memory.**

### What changed

Registered cover sources are verified by file hash, image headers, project ownership, resolution and provenance without decoding full-resolution pixels during progress, preview, selection and preflight requests. Only cover rendering explicitly loads the original pixels.

### What was fixed

Repeated 512 MB out-of-memory restarts while opening Project 20's 4000 × 6000 photograph. Three concurrent source-verification requests peaked at 541.4 MiB before the repair and 54.3 MiB after it in a local reproduction.

### Do customer steps change?

No. Reopen the existing book and choose the title and cover. Existing image files, cover identity and quality checks are preserved; no paid provider calls or hosting-plan changes are added.

### Release gate

The full 213-file run completed 3,006 tests: 3,005 passed, one release-note heading check failed, and none errored or skipped. After correcting the headings, all 31 version/release-note checks passed. This is full coverage followed by the corrected check, not a claim that a second fresh full run passed. The production code passed its cover, recovery, browser and export checks. The earlier baseline Fast Stability Gate passed 710; focused post-repair cover and recovery checks passed 98.

## 1.9.25 — 2026-10-12

**Recover missing ebook cover previews.**

**What changed:** Cover photograph and variant paths follow the project when the builder and website use different export folders. The preview update button can refresh the existing cover even when its title has not changed.

**What was fixed:** A registered photo could appear missing on a different machine. Updating previews with the same title did nothing. Finishing now stays blocked until the selected preview loads. The author-credit route is also recorded as a lightweight update.

**Do steps change?** The existing title and cover choice remains. Refreshing retains the manuscript, pictures, title, and photo; no paid image generation is added.

**Release gate:** Stability, cover recovery, real-browser checks, and the full acceptance suite are checked before publication. No failing or skipped check is treated as a pass.

## 1.9.24 — 2026-10-12

**Correct a missing author without rebuilding the book.**

The ebook workspace now lets you save the author credit. Updating it preserves approved research, titles, chapters, and visuals while invalidating covers and later packaging that contain the old credit. Cover preparation refuses a missing author before any stock search or rendering, with a specific recovery message instead of exhausting every photograph and layout.

## 1.9.23 — 2026-10-12

**Restore the photograph minimum after free graphic fallbacks.**

Visual preparation now checks the photograph count after acquisition. If free local fallbacks leave too few photographs, it adds matched free stock photos beside existing chapter graphics. Each pass tries at most four chapters, retains unsuccessful search history, excludes already-used photos, and stops once the minimum is met. Uncertain, missing, or duplicate candidates never enter the plan; no paid image path is used. Useful existing graphics are kept when additional photographs can resolve the remaining media-count findings. The final editorial, relevance, resolution, attribution, and export gates remain required.

## 1.9.22 — 2026-10-12

**Apply requested corrections before advancing the book.**

The workflow builder previously advanced the book before applying a pending picture or cover action. An exhausted visual stage could therefore fail first, then save the replacement after the job had already stopped. Requested actions now run first, under the same renewable worker lease. A successful correction resumes a saved failed stage; failed corrections and automatic retries retain the existing attempt limits. Completed work and quality checks remain intact.

Verification: two new regressions fail on the original code. The repaired worker, workflow, and action suites pass with external and paid calls blocked. Live PDF/ZIP completion remains unverified.

## 1.9.21 — 2026-10-12

**Automatic picture recovery now uses the existing free fallback and saves progress.**

### What changed

When a stock photograph needs review, the automatic build tries an honest graphic derived from that chapter's approved text. Guided retries use this same free path and render the replacement before approval. Already passing pictures are retained.

### What was fixed

An uncertain photo previously stopped acquisition but could not pass approval. Guided retries called only the stock-photo editor path, bypassing the free fallback. That fallback also missed structured chapter lists and tables when no short prose sentences were available; it now uses the existing structured planner too. Visual work is checkpointed before approval and after each replacement, so a later failure does not erase completed assets or retry history.

### Do customer steps change?

No extra step is added. Photo matching, editorial variety, readability, attribution, and export checks remain required. If no honest free fallback exists, the photo still requires review; uncertainty never authorizes a paid image.

### Release gate

The complete 211-file release gate passed: 2,981 tests, zero failures, errors, or skips. Focused regressions reproduced the earlier recovery failures before the repair. Original reference PDF/ZIP checksums match. All verification blocked external and paid calls. Live book completion remains unverified.

## 1.9.20 — 2026-10-09

**Existing manuscripts now have a free, reversible editor.**

### What changed

Open “Edit manuscript” from the manuscript reader. Suggest conservative copy edits or rewrite the Markdown, review a diff and quality findings, then apply the reviewed draft. The previous text is saved for undo. No paid provider calls are made.

### What was fixed

The earlier copy editor ran only during chapter generation. Existing drafts can now be edited without regenerating chapters. Saves reject stale drafts, active builds, empty text, and newly introduced quality findings. Every save or undo rechecks quality, invalidates final approval, and preserves old exported files. Structural findings are shown rather than bypassed.

### Do customer steps change?

Editing is optional. After saving, review and approve the manuscript again, then rebuild and check final files. Automated proofreading remains limited English rules; comprehensive grammar and factual accuracy require human review.

### Release gate

Complete 211-file acceptance run passed: 2,976 tests, zero failures, errors or skips, with external and paid calls blocked. The first complete attempt had 2,975 passes and one missing-route-classification failure; that classification was fixed, all 32 routing/editor/lock checks passed, and the entire gate was rerun successfully. The reference PDF and ZIP checksums remain unchanged.

## 1.9.19 — 2026-10-09

**Editor-in-Chief now makes conservative copy edits before chapter acceptance.**

### What changed

- Corrects a defined set of English spelling, repeated-article, modal-verb and subject-verb errors without another AI call.
- Preserves quotations, links, code, tables and headings. Original…21965 tokens truncated…
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
