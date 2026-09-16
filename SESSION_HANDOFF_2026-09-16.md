# Session handoff — 2026-09-16

## Start here

**The ebook acceptance test passed end to end.** "Container Gardening for
Beginners" (project 370) went from a stranded build to a finished, downloadable
product, driven entirely by the server with the browser closed.

Released **v1.7.27**. Full Windows release gate green: 2280 passed, 0 failed,
984 subtests, no paid API calls.

The long-running "the Factory cannot reliably produce a simple ebook" problem
has a root cause, and it is fixed. It was never the writing model.

---

## PRIORITY 1 — ebook end-to-end: PASS

Project 370, one resume request, then **no client call of any kind**. Progress
was read by opening the database read-only.

```
research COMPLETE  title COMPLETE  outline COMPLETE  manuscript COMPLETE (9/9)
visuals  COMPLETE  cover COMPLETE  design COMPLETE   preview   COMPLETE
preflight COMPLETE (PASS)          export COMPLETE   job SUCCEEDED
```

| Acceptance requirement | Result |
| --- | --- |
| Chapters 1–9 complete | 9 of 9 accepted |
| Browser can be closed | design, preview, preflight and export all ran with no client |
| Persisted progress truthful | yes (one contradiction found and fixed, below) |
| Resumes after interruption | resumed repeatedly, never lost a chapter |
| Cover / design / preview | complete |
| Preflight | **PASS** |
| Valid PDF | 6,583,189 bytes, `%PDF` header, **31 pages** |
| ZIP package | 12,226,438 bytes, 14 members, no corrupt entry |
| Saved Projects entry | "Container Gardening for Beginners" |
| Working download | `ebook.pdf` 200 `application/pdf`; `package.zip` 200 `application/x-zip-compressed` |

---

## The root cause, and the four defects fixed

### 1. Two gates that had never agreed (the real one)

The interior editorial floor demands **three distinct kinds of visual**. The
generic book contract demanded **no structured material at all** —
`required_table` / `required_workflow` / `required_checklist` were set only when
the outline's *purpose* text happened to contain a keyword like "table" or
"checklist".

So whether a book could be designed depended on whether the writing model
volunteered structure nobody had asked for:

| Project | Asked for | Model volunteered | Kinds | Visuals |
| --- | --- | --- | --- | --- |
| 351 Mindfulness | 2 chapters' worth | 105 table rows, 6 checkboxes, 30 steps | 7 | passed |
| 353 Meal Plan | 5 chapters' worth | — | 3 | passed |
| **370 Container Gardening** | 3 tables | **nothing** | **1** | **died** |

370 was asked for exactly three tables and wrote exactly three tables. Passing
was luck, and it had nothing to do with which provider wrote the book.

**Fixed:** every third chapter is now required to carry a real checklist and
every third a numbered procedure, on different chapters, leaving the rest free
for a photograph — which is precisely the shape the interior floor asks for
(three distinct kinds, three photographs, three visuals that carry more than a
paragraph). Lengths deliberately vary, because the interior compares visuals by
shape and three identical four-item boxes are reported as one repeated design.

### 2. A repair instruction the writer could not act on

When a chapter lacked its checklist or procedure, the writer was handed
*"Missing required workflow: chapter-workflow"* — an internal spec name, not an
instruction. Chapter 6 was rewritten six times and got longer and wordier each
time, burning roughly **$2.65 of the book's $3.50 budget for zero progress**.

The table branch had already learned this lesson years earlier — *"'Fix the
chapter' is not actionable when the failure is a format the model may believe it
already satisfied in prose"* — but workflow and checklist never got one. They do
now, and they name the exact accepted format.

### 3. An internal name printed in the customer's book

A model handed "chapter-workflow" duly printed `### chapter-workflow` as a
heading above the list it had just written. Preflight caught it — but only
*after* the manuscript was approved, so the book was stuck with no way forward.
Those names are now stripped before they can reach a page.

### 4. A finished book that said "Paused"

The bar reached 100% reading "Your ebook is ready" while the indicator beside it
said "Paused". `status_payload` derives "finished" from the rail; `activity_for`
read only the persisted flag, which is written by `advance_build` and so is
never set when the last stage completes inside an executor drain. Both now read
the same truth.

---

## PRIORITY 2 — core product regressions: all PASS

Ebook, Planner, Word Search, Crossword, Coloring Book, Spelling Worksheet, Math
Worksheet — 239 customer-path tests passed. Fast Stability Gate: 248 passed.
Nothing was redesigned; no release-blocking regression was found.

## PRIORITY 3 — release verification

| Check | Result |
| --- | --- |
| R2 | PASS (probe OK) |
| SQLite rollback retained | PASS (projects.db, 115 rows) |
| Legacy `pdf_bytes` retained | PASS (73 projects, nothing deleted) |
| Saved Projects | PASS |
| Downloads | PASS |
| Job / resume behaviour | PASS |
| Function Locks | PASS (no LOCKED function touched; enforcement + integrity green) |
| Fast Gate | PASS (248) |
| Full Gate | PASS (2280, 0 failures, 0 paid API calls) |
| **PostgreSQL** | **PASS** — verified by the owner via the Render shell (below) |

**PostgreSQL (owner-supplied, corrects my earlier "unverified"):**
`active_backend: postgres`, `connection_class: PostgresConnection`,
`projects: 9`, `assets: 4`, `sqlite_file_retained: true`, `storage_driver: r2`,
`r2_reads_enabled: true`. I could not reach it from this machine (no
`DATABASE_URL` locally, production behind the invite gate), but that is a limit
of my access, not an unverified backend. Later the same day I confirmed
PostgreSQL *reads* independently through the live app.

---

## What needs you

**The live production copy of "Container Gardening for Beginners" is untouched**
as of this section. See the addendum at the end of this file — it was resumed
later the same day, and the production acceptance attempt is recorded there.

---

## Found but NOT fixed — two real defects, deliberately left

1. **`services/ebook_visual_pipeline.py:1215`** gives a photograph to *every*
   aid-less chapter with no cap, pre-empting `_commission_media_mix`, whose job
   is to cap photographs at the interior requirement. Carried over from
   yesterday; today's contract fix removes its practical impact but not the bug.
2. **An already-accepted chapter is never re-validated when the book contract
   changes.** `reconcile_validated_preserved_chapters` only *adds* chapters that
   now pass; `execute_correct_manuscript` computes `failed_orders` as "not in
   accepted", so a book caught across a contract change repairs nothing and
   loops. I cleared the acceptance cache on 370 by hand to get past it. A
   general fix must be careful: naively re-opening accepted chapters could
   trigger mass regeneration and real spend on customers' books.

Also worth knowing: a **4- or 5-chapter** ebook can never satisfy the interior
floor, which wants 3 photographs *and* 3 distinct kinds while capping any one
kind at 55% — three photographs out of four or five visuals is 75% and 60%. One
aid per chapter cannot meet both. Pre-existing; the Factory's outlines produce
8–9 chapters, so it is not blocking.

## Local test actions taken on project 370 (disclosure)

Two deliberate interventions on the local reproduction, neither a product change:

- **Cleared the accepted-chapter cache** so the correction pass would re-derive
  which chapters satisfy the new contract. Chapters 1, 5 and 9 already passed and
  were preserved, not rewritten; 6 were repaired.
- **Reset the project's spend ledger** after the non-actionable repair
  instruction had consumed its $3.50 budget on rounds that produced nothing. The
  provider throughout was local Ollama and **no money was actually spent** — the
  ledger charges the Factory's cost model regardless of provider.

No paid provider call was made today. Pexels supplied the nine chapter
photographs and the cover, as it did yesterday.

## State

- Branch `main`, clean tree, **v1.7.27**, `main == origin/main`.
- Yesterday's v1.7.26 was pushed at the start of today's session (it had been
  committed but blocked from pushing).
- Local test server on port 5077 throughout; the owner's 5055 window untouched.

## New tests

`tests/test_generic_book_carries_designable_material.py` (36 checks), registered
in `tests/acceptance_manifest.json`. Most of it guards one rule learned the hard
way and stated in the file's own docstring: *a requirement is only real if the
thing demanded is the same thing the validator detects AND the same thing the
interior can draw.* It asserts that three-way agreement directly — contract,
validator, interior planner — because the previous release shipped a check that
demanded something no generator could satisfy, and a book burned sixty attempts
on it.

Two further checks added to `tests/test_ebook_activity_truthfulness.py` for the
finished-book-says-Paused contradiction.

---

# Addendum — live production acceptance of v1.7.27 (same day)

**Verdict: NOT READY. Three production blockers, all human-only.**
None of them was introduced by v1.7.27; all three predate it.

I reached production through the owner's own signed-in Chrome session (the
invite code lives only in Render's environment, by design, so this was the only
route). Read-only checks first, then the one authorised action: pressing
Continue on the existing book.

## Verified working in production

| Check | Evidence |
| --- | --- |
| Deployment | App footer reads **v1.7.27**. Deployed `static/js/app.js` is content-identical to the repo (differs only by CRLF/LF), `Last-Modified 2026-09-16T16:11:28Z` — 19s after commit `3939779`, so the push auto-deployed. |
| App health | Serving normally behind the invite gate; no 500s seen on any route. |
| PostgreSQL reads | `/projects` returns rows; `/ebook-workspaces/in-progress` returns all five stranded books. |
| Saved Projects | Loads, lists finished products and unfinished builds. |
| "Continue where you left off" (v1.7.25) | Live, and lists all five stranded ebooks with truthful per-book status. |
| Continue → resume handoff (v1.7.26) | `POST /ebook/build/5/resume` → **200**; screen showed "Working" and "You can leave this page." |
| **Browser-independent execution** | **Proven.** Tab closed for five minutes; project 5's manuscript grew **11,477 → 11,658 words** with no client attached. |

The original customer symptom is also confirmed fixed at the reporting layer:
the stalled book reports `state: failed`, `label: "Stopped"`, `spinning: false`
— not a spinner over a dead build.

## Blocker 1 — the book's budget is spent (billing decision)

Project 5's ledger: `cap_usd 3.5, spent_usd 3.5, remaining_usd 0.0, paid_calls 22`.

My resume ran eight correction rounds between 16:23 and 16:25 UTC, each charging
$0.15, each returning `status=needs_correction` with `structure_ok=true`. That
consumed the last of the cap. Nothing further can run on this book until the cap
is raised — that is a spend authorisation, not a code change.

Note the rounds were *progressing* (the manuscript grew), not spinning.

## Blocker 2 — Pexels is not configured in production (missing credential)

The workspace reports `pexels.configured=false`, `code=missing_config`,
`ai_cover.configured=false`, and the cover sits at "Step 1 of 3 — Choose a
photo". Vector covers are disabled by policy
(`generate_and_stage_cover` raises "Search Pexels or upload your own
photograph").

So **no ebook in production can complete its cover**, and therefore cannot reach
design → preview → preflight → export, until either a `PEXELS_API_KEY` is set on
Render or a photograph is uploaded by hand. My local runs passed this stage only
because this machine has a Pexels key.

## Blocker 3 — the one finished product cannot be downloaded

Word Search "Flower Parts" (project 4). The download URL **the app itself
stores** returns 403:

```
GET /download/6c905b99847a48aeb2eddb29c00c92b8/flower_parts.pdf
403 {"error":"download_blocked",
     "violations":["stale_or_orphan_export_package"]}
```

The guard fires when `context.project_id is None and context.product_type is
None` — the package resolved to no project. But the project row's `data`
contains that exact `export_package_id`, and `_project_for_package` matches on
it via `WHERE type IN ('product','ebook') AND data LIKE ?`. The PDF file itself
is present: the guard runs *after* the PDF has been opened and paged.

Requesting the other id (`package_id`, `cee4f49…`) gives a different error,
"Export file not found" — so that one *does* resolve to the project. The
resolution is failing specifically for the stored `export_package_id`.

The same route serves HTTP 200 locally on SQLite for project 370. That points at
the PostgreSQL backend, and diagnosing it needs production database access.

## What I did not do

- Did not raise any spend cap, change any environment variable, touch the
  database, or alter R2/PostgreSQL configuration.
- Did not delete or re-export anything.
- Did not create a replacement project — the real one (id 5) exists and is
  recoverable.
- Did not start a second live build after the budget was exhausted.

## To finish production acceptance, in order

1. Raise the spend cap on project 5 (or confirm a new per-book budget).
2. Set `PEXELS_API_KEY` on Render, or upload a cover photograph by hand.
3. Give me production database access (or run a query yourself) so blocker 3 can
   be diagnosed — this one affects every download, so it should be treated as
   the most serious of the three.

With 1 and 2 cleared, project 5 should run to completion: its manuscript is
already 9 chapters and ~11.7k words, and the local end-to-end run proved the
remaining stages work on v1.7.27.

---

# Addendum 2 — v1.7.28: the download defect, fixed and verified live

**Blocker 1 is closed.** Released **v1.7.28** (`d86139a`), deployed, and verified
against the real production URL.

```
GET /download/6c905b99847a48aeb2eddb29c00c92b8/flower_parts.pdf
  -> HTTP 200 · 5,012 bytes · %PDF · application/pdf      (was 403)
GET /download/6c905b99847a48aeb2eddb29c00c92b8/package.zip
  -> HTTP 200 · 3,861 bytes · PK · application/zip        (was 403)
```

Production footer reads **v1.7.28**.

## Root cause: a row shape, not a data problem

Two copies of the package → project lookup read their rows **positionally**:

```python
for pid, name, ptype, data_str in rows:
    try:
        d = json.loads(data_str or "{}")
    except Exception:
        pass
```

SQLite returns `sqlite3.Row`, which unpacks as a sequence, so this worked.
PostgreSQL is opened with psycopg's `dict_row`, so every row is a **mapping** —
and unpacking a mapping yields its **keys**. `data_str` became the literal
string `"data"`, `json.loads` raised, and the bare `except: pass` swallowed it.
The lookup then reported "no project owns this package" for every row, and the
orphan guard correctly refused to serve a package it had been told was orphaned.

**The guard was right; its input was wrong.** Proven by running the old code
against both row shapes:

```
OLD code, SQLite-shaped rows  -> {'id': '4'}
OLD code, Postgres dict rows  -> None          <-- every download 403'd
unpacking a dict row yields:     ['id', 'name', 'type', 'data']
```

## The fix

One canonical resolver, `database.find_project_by_package`:

- rows are read **by column name** (`sqlite3.Row` and `dict` both support it);
- ownership is decided by **structured parsing** of the project's own metadata —
  `package_id`, `export_package_id`, `product_exports`/`exports` package ids, and
  the package id inside a stored `/download/<pkg>/` URL, because Saved Projects
  builds the customer's buttons from those;
- the SQL `LIKE` is a **prefilter only** and cannot produce a false negative: an
  id stored in the row's JSON is by definition a substring of that TEXT column;
- an unparseable row is **logged and skipped**, never silently swallowed — the
  bare `except` is what hid this for an entire release.

Both call sites now delegate to it. The second copy (`final_output_gate`) had
never checked `export_package_id` at all, so it could not have resolved a modern
export even on SQLite.

**The stale/orphan guard is unchanged** and still returns 403 for a genuine
orphan — there is a test for exactly that, on both backends.

## Audit (as instructed, not just the one symptom)

Every other positional row read was checked. `services/db/connection.py` and
`services/db/cutover.py` already handle both shapes
(`row["n"] if isinstance(row, dict) else row[0]`), and `database._row_to_dict`
reads by name throughout — which is precisely why the rest of the app worked in
production and only these two resolvers failed.

## Tests

`tests/test_download_package_resolver_both_backends.py` — 25 checks, registered
in the manifest. They run the real resolver **and the real Flask download
route** against both row shapes, reproducing the live site's shape exactly, so a
PostgreSQL-only download defect cannot recur unseen: package_id and
export_package_id on each backend, the stored customer URL, PDF 200, ZIP 200,
both call sites on both backends, a genuine orphan still 403, and a grep guard
against positional row reads.

Full Windows release gate: **2305 passed, 0 failed**, 984 subtests, 0 paid API
calls.

One self-inflicted lesson worth keeping: my first version of the unreadable-row
test wrote invalid JSON into the shared test database. `delete_project` could
not parse it to remove it, so the bad row leaked and broke 29 unrelated tests
later in the gate. The test now exercises a malformed row through a fake
connection and never writes bad data anywhere.

## What remains — two owner actions, nothing else

Both are the ones already identified; neither is a code defect.

1. **PEXELS_API_KEY is genuinely absent on Render.** `pexels_configured()`
   returns `bool(os.environ.get("PEXELS_API_KEY"))`, and `/pexels-status`
   reports `code: missing_config`. Until it is set, no ebook can complete its
   cover (vector covers are disabled by policy), so none can reach design →
   preview → preflight → export.

2. **Project 5's budget is spent** — cap $3.50, spent $3.50, remaining $0.00.

### Evidence for the bounded budget ask

The identical book finished **locally**, under this same contract, from the
identical stuck point (manuscript correction), for **$2.85 in 20 paid calls**:

```
correct_manuscript  $0.45  (3 chapter calls)   x5
correct_manuscript  $0.60  (5 chapter calls)
TOTAL               $2.85  -> finished 31-page PDF + 12.23 MB ZIP
```

Every charge was manuscript correction. **Visuals, cover, design, preview,
preflight and export added nothing to the ledger** — they use free stock
photography and local rendering. Production's manuscript is better structured
than the local one (it was written by the premium provider), so it should need
no more correction than this, and plausibly less.
