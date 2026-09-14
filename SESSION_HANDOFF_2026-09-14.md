# Session Handoff — 2026-09-14, end of day

**Start a new session with:** "Read CLAUDE.md and the newest handoff first. Confirm the
current Factory path, current Git branch, current commit, and that the working tree is
clean before making any changes."

---

## CLOSEOUT — Upgrade 0, Phase 0B-3B1 — v1.7.13 — COMPLETE, committed and pushed

Upgrade 0's next phase shipped on top of the 0B-3A storage foundation (v1.7.12):
the Factory can now *talk* to shared cloud storage, and every reader knows where
every existing file really lives — **while not one customer file has moved.**

**Current ground (verified):** `main` == `origin/main` == `d5b8dca`, working tree
clean. `VERSION` = `1.7.13`; plain-language `CHANGELOG.md` entry present.

- **Release commit `efb1e90`** — "Release v1.7.13 - Upgrade 0 Phase 0B-3B1:
  Cloudflare R2 + reader-first cutover". 18 files, +2521/−55.
- **Relock commit `d5b8dca`** — "Relock invite_protection at efb1e90 after the
  Phase 0B-3B1 app.py change". Restores `invite_protection` to LOCKED with
  `last_known_good_commit = efb1e90`, `factory_version 1.7.13`.
  (The commit message itself claims Fast Gate 160 passed, but this session's
  independent Fast Gate run on the final HEAD is 248 passed, 698 subtests — see
  below; the 160 figure in the commit message appears stale. The registry
  integrity and enforcement tests, which are the machine-checked part of the
  relock, pass on the exact committed state.)
- **Gate proof (this session, real):** Full Windows release gate — **2967 tests,
  0 failures, 0 errors, 0 skipped, 0 paid API calls**
  (log: `Factory Control Center/Logs/full_release_gate_v1.7.13_20260914.txt`, run
  against the working tree that `efb1e90` then committed — the [4/4] step ran 140
  acceptance files including `test_storage_r2_cutover.py`). After the relock
  landed, re-ran the registry integrity + enforcement + invite-gate subset on the
  new HEAD: **25 passed, 91 subtests** — so the relocked registry is internally
  consistent against the exact committed state.

### What 0B-3B1 actually delivered

- **Cloudflare R2 driver** (`services/storage/r2.py`): S3 API via boto3, endpoint
  derived `https://{account}.r2.cloudflarestorage.com`, region `auto`, private
  bucket, credentials from the environment only. Fail-closed: missing/incomplete
  config raises `R2ConfigurationError`, never silently falls back. Credential
  redaction keeps secrets out of errors/logs. `probe()` does a round-trip – but it
  is never wired to customer data and no bucket/credentials exist. **Not switched
  on.**
- **Canonical key rule** (`services/storage/keys.py` + `resolve.py`): a storage key
  is derived from the artifact's **real stored path**
  (`projects/{id}/exports/{path}`), never from `package_id` — because 38 of 114
  local projects disagree about that id. Every proposed key is *proved* to invert
  back to the exact existing file before it enters a plan.
- **Migration executor** (`services/storage/executor.py`): COPY → VERIFY SIZE →
  VERIFY SHA-256 → RECORD → READ BACK → VERIFY SHA-256 → MARK VERIFIED → KEEP
  LEGACY. No deletion step exists. It refuses to run unless
  `enable_customer_migration=True` is passed, and nothing passes it.
- **Readers** (`services/storage/compat.py` + `app.py` + `database.py`): every
  serve path prefers a **fully verified** asset (record + object + byte count +
  SHA-256 all match) and falls back to the legacy copy on any failure — a broken
  asset can never hide a good legacy file. Saved Projects recognises asset-backed
  products (`_asset_backed_customer_outputs`). With zero asset rows, all of it is a
  no-op; downloads behave exactly as in 1.7.12.
- **Dry-run plans** verify against real data every time they run. This session's
  live measurements (read-only): 114 projects; 73 embedded PDFs to move (49.33 MB,
  largest 39.83 MB, 0 problems); 292 export files across 78 projects (211.46 MB,
  46 problems); 3,224 total files under `exports/`. The 46 export problems are the
  honest picture of legacy data (38 package-id mismatches, 8 projects with no
  resolvable path — 7 of which still hold their PDF embedded).

### What 0B-3B1 did NOT do (deliberate, and still true)

- No bucket provisioned, no R2 credentials created, no `FACTORY_STORAGE_DRIVER=r2`
  set anywhere, no connectivity probe run, no Render change, no Postgres, no
  worker. `FACTORY_STORAGE_DRIVER` is documented in `.env.example` as **unset =
  local = exactly today's behaviour**.

## START HERE next session

1. **Confirm the ground.** In `Factory-v1.3` run `git status` (expect clean,
   `main` == `origin/main`) and `git log --oneline -3` (expect `d5b8dca` on top,
   v1.7.13).
2. **Run the Fast Stability Gate** (CLAUDE.md line ~32; now 22 test files,
   including both storage suites). Do not start new work on a RED gate.
3. **Upgrade 0's next step is 0B-3B2 — the approved real migration.** It is a
   customer-data move: it will actually COPY the 73 embedded PDFs and the export
   files into R2 and only then, per the 0B-3B1 executor's rules, decide on legacy
   data. It needs: (a) an R2 bucket + credentials on the host (Render secrets or
   local `.env`), (b) `FACTORY_STORAGE_DRIVER=r2`, (c) the owner's explicit
   approval to migrate real customer artifacts. **Nothing here auto-fires.** Read
   the harness gate/safety notes in `services/storage/executor.py` and the
   blueprint's § on the copy/verify/record/keep sequence before starting it.
4. **Nothing in this phase is a regression or reopened item** — do not re-investigate
   storage components unless a new report comes in. If a storage report does come
   in, first confirm which version was actually running (the runtime-audit lesson
   from the 2026-09-11 handoff still applies).

## Notes on how this close-out actually happened (be honest about it)

A concurrent Claude session committed `efb1e90` and `d5b8dca` and pushed them to
`origin/main` while this session's Full Gate was still running. The gate result
recorded here is this session's own run against the working tree whose exact
content those commits carry (verified file-for-file), and the registry subset was
re-run after the relock landed. Both commits are on `origin/main`, so the published
tree and the tested tree are the same object. Nothing further was committed by this
session.

## Still open / owner decisions

- **Approve the 0B-3B2 real migration** (the next Upgrade 0 phase) — see START
  HERE above. This is the first phase that actually touches customer files, so it
  should be a considered, explicit decision.
- Older, genuinely open items carried forward from 2026-09-11 and the recovery
  sprint are unchanged by this release: the owner's live ebook-build re-test on
  Render (v1.7.10 bounded-generation fix), Tavily/Pexels key rotation, the
  onedrive-workspace-phase-a archive decision, and the v2 plan's Day 3/Day 4 items.

## Source of truth

Only `C:\Users\user\Documents\Product-Pipeline\Factory-v1.3` on branch `main`.
`Factory_Stabilized_V2` and the OneDrive snapshots are archives for reading only.