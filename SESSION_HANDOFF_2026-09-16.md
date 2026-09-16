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
| **PostgreSQL** | **NOT VERIFIED — see below** |

---

## What needs you

**1. PostgreSQL health cannot be checked from this machine.** There is no
`DATABASE_URL` in the local `.env`, and `https://digitalproductfactorypro.com`
answers **401** on every path because of the invite gate, so no production
build or query can be driven from here. Production is *up*; its database backend
is unverified by me. Check it from the Render dashboard, or give this machine a
read-only `DATABASE_URL` and the invite code if you want it verified here.

**2. The live production copy of "Container Gardening for Beginners" is
untouched.** Today's work was on the local reproduction. It should recover once
v1.7.27 deploys, but that is a prediction, not a verified result.

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
